"""ALTAIR multi-asset 15m sweep (periodic universe re-evaluation).

Scans every available stock CSV, runs ALTAIR at 15m with the native
regime hysteresis band (regime_atr_hyst_lower/upper, default 0.95/1.05)
and emits a per-ticker yearly PnL heatmap plus stability metrics. This is
the tool to re-run every 6-12 months to refresh the tradeable universe
(broker availability is decided separately, downstream).

Two disjoint universes (selected automatically from data/):
    native15m : *_15m_8Yea.csv  -> loaded as-is (15m bars)
    resample5m: *_5m_8Yea.csv   -> resampled 5m -> 15m

Stock CSVs are identified by the _8Yea suffix (forex/index feeds use
_5Yea / _15Yea / _23Yea / _daily and are skipped). The two universes do
not overlap, so --source all runs each ticker exactly once.

Config presets (entry aggressiveness / SL width), matching the screening
convention used across the ALTAIR tools:
    A : dtosc_os=25, max_sl_atr_mult=2.0  (default)
    B : dtosc_os=20, max_sl_atr_mult=4.0

For each ticker the best config (by PF) is highlighted; both are shown
when --config both (default).

Decision support (cold-read friendly): the analysis must weight number
of winning years, inter-year stability and recent-year strength, NOT the
8-year aggregate alone. Columns provided per ticker:
    PF, Sharpe, trades, max DD, winning-years / total-years,
    last-2-years net PnL, and the full year-by-year PnL grid.

Usage:
    python tools/altair_sweep.py                      # all, config both
    python tools/altair_sweep.py --source native15m   # only native 15m
    python tools/altair_sweep.py --source resample5m  # only 5m -> 15m
    python tools/altair_sweep.py --config A           # only preset A
    python tools/altair_sweep.py --tickers NVDA AJG   # subset
    python tools/altair_sweep.py --csv out.csv        # also dump CSV

ASCII-only (project axiom 4). English only (axiom 3).
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import io
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import backtrader as bt

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from strategies.altair_strategy import ALTAIRStrategy  # noqa: E402
from config.settings_altair import (  # noqa: E402
    ALTAIR_BROKER_CONFIG, _DEFAULT_PARAMS,
)
from lib.commission import ETFCommission, ETFCSVData  # noqa: E402


DATA_DIR = PROJECT_ROOT / "data"
BT_TO = dt.datetime(2025, 12, 31)
STARTING_CASH = 100_000.0
TARGET_TF_MIN = 15           # all runs evaluated at 15m
BARS_PER_DAY_15M = 26        # US RTH 14:30-21:00 = 6.5h -> 26 x 15m bars

# Config presets (entry aggressiveness / SL width).
CONFIG_PRESETS = {
    "A": {"dtosc_os": 25, "max_sl_atr_mult": 2.0},
    "B": {"dtosc_os": 20, "max_sl_atr_mult": 4.0},
}


# ---------------------------------------------------------------------
# Universe discovery
# ---------------------------------------------------------------------

def discover_universe(source):
    """Return list of (ticker, csv_name, resample_min) for the source.

    native15m  -> resample_min = 0  (loaded as 15m directly)
    resample5m -> resample_min = 15 (5m feed resampled to 15m)
    Stock CSVs only (the _8Yea suffix). Universes are disjoint.
    """
    items = []
    if source in ("native15m", "all"):
        for p in sorted(DATA_DIR.glob("*_15m_8Yea.csv")):
            ticker = p.name.split("_")[0]
            items.append((ticker, p.name, 0))
    if source in ("resample5m", "all"):
        for p in sorted(DATA_DIR.glob("*_5m_8Yea.csv")):
            ticker = p.name.split("_")[0]
            items.append((ticker, p.name, TARGET_TF_MIN))
    return items


def detect_from_date(csv_path):
    """Read the first data row to anchor the BT start date."""
    with open(csv_path, "r") as f:
        f.readline()  # header
        first = f.readline().strip()
    if first:
        ds = first.split(",")[0]
        return dt.datetime(int(ds[:4]), int(ds[4:6]), int(ds[6:8]))
    return dt.datetime(2017, 1, 1)


# ---------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------

def run_bt(ticker, csv_name, resample_min, preset):
    """Run one ALTAIR 15m backtest. Returns a metrics dict or {'error':}."""
    try:
        cerebro = bt.Cerebro(stdstats=False)
        csv_path = DATA_DIR / csv_name
        from_date = detect_from_date(csv_path)

        data = ETFCSVData(
            dataname=str(csv_path),
            dtformat="%Y%m%d", tmformat="%H:%M:%S",
            datetime=0, time=1, open=2, high=3, low=4, close=5,
            volume=6, openinterest=-1,
            fromdate=from_date, todate=BT_TO,
        )
        if resample_min > 0:
            d = cerebro.resampledata(
                data, timeframe=bt.TimeFrame.Minutes,
                compression=resample_min)
            d._name = ticker
        else:
            cerebro.adddata(data, name=ticker)

        cerebro.broker.setcash(STARTING_CASH)
        bcfg = ALTAIR_BROKER_CONFIG.get("darwinex_zero_stock", {})
        ETFCommission.total_commission = 0.0
        ETFCommission.total_contracts = 0.0
        ETFCommission.commission_calls = 0
        cerebro.broker.addcommissioninfo(ETFCommission(
            commission=bcfg.get("commission_per_contract", 0.02),
            margin_pct=bcfg.get("margin_percent", 20.0),
        ))

        params = dict(_DEFAULT_PARAMS)
        params.update(CONFIG_PRESETS[preset])
        params.update(dict(
            bars_per_day=BARS_PER_DAY_15M,
            export_reports=False,
            print_signals=False,
        ))
        cerebro.addstrategy(ALTAIRStrategy, **params)

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            res = cerebro.run()
        return extract(res[0], cerebro, from_date)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def extract(strat, cerebro, from_date):
    """Pull headline + yearly metrics from a finished strategy."""
    fv = cerebro.broker.getvalue()
    pnl = fv - STARTING_CASH
    t = strat.total_trades
    w = strat.wins
    gp = strat.gross_profit
    gl = strat.gross_loss
    wr = (w / t * 100) if t > 0 else 0.0
    pf = (gp / gl) if gl > 0 else (float("inf") if gp > 0 else 0.0)

    # Max drawdown from the equity curve.
    dd = 0.0
    pv = list(strat._portfolio_values) if strat._portfolio_values else [STARTING_CASH]
    peak = pv[0]
    for v in pv:
        if v > peak:
            peak = v
        d = (peak - v) / peak * 100.0
        if d > dd:
            dd = d

    # Annualized Sharpe from per-trade returns.
    first_dt = getattr(strat, "_first_bar_dt", None)
    last_dt = getattr(strat, "_last_bar_dt", None)
    years = max((last_dt - first_dt).days / 365.25, 0.5) if first_dt and last_dt else 1.0
    trade_pnls = [tp["pnl"] for tp in strat._trade_pnls]
    returns = [p / STARTING_CASH for p in trade_pnls]
    sharpe = 0.0
    if len(returns) > 1:
        avg_r = np.mean(returns)
        std_r = np.std(returns, ddof=1)
        tpy = t / years
        if std_r > 0:
            sharpe = (avg_r / std_r) * math.sqrt(tpy)

    # Yearly aggregation.
    yearly_raw = defaultdict(lambda: {"trades": 0, "pnl": 0.0,
                                      "gp": 0.0, "gl": 0.0})
    for tp in strat._trade_pnls:
        y = tp["year"]
        yearly_raw[y]["trades"] += 1
        yearly_raw[y]["pnl"] += tp["pnl"]
        if tp["is_winner"]:
            yearly_raw[y]["gp"] += tp["pnl"]
        else:
            yearly_raw[y]["gl"] += abs(tp["pnl"])

    yearly = {}
    pos_years = 0
    for y in sorted(yearly_raw.keys()):
        s = yearly_raw[y]
        y_pf = (s["gp"] / s["gl"]) if s["gl"] > 0 else (
            float("inf") if s["gp"] > 0 else 0.0)
        yearly[y] = {"trades": s["trades"], "pnl": s["pnl"], "pf": y_pf}
        if s["pnl"] > 0:
            pos_years += 1

    # Recent-year emphasis: net PnL of the last two calendar years present.
    last2 = 0.0
    for y in sorted(yearly.keys())[-2:]:
        last2 += yearly[y]["pnl"]

    return {
        "trades": t, "wr": wr, "pf": pf, "net_pnl": pnl,
        "max_dd": dd, "sharpe": sharpe, "yearly": yearly,
        "pos_years": pos_years, "total_years": len(yearly),
        "last2_pnl": last2,
    }


# ---------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------

def _pf_str(pf):
    return "inf" if pf == float("inf") else f"{pf:.2f}"


def print_report(results, all_years, source, configs):
    """results: list of (ticker, src_tag, preset, metrics)."""
    print("\n" + "=" * 118)
    print("  ALTAIR 15m SWEEP -- hysteresis ON (0.95/1.05)  "
          f"source={source}  configs={'/'.join(configs)}")
    print(f"  Period: per-ticker start -> {BT_TO.date()}    "
          f"capital ${STARTING_CASH:,.0f}")
    print("=" * 118)

    # Year columns (compact two-digit headers).
    yhead = "".join(f"{str(y)[2:]:>7}" for y in all_years)
    print(f"\n{'Ticker':<7}{'Cfg':>4}{'Tr':>5}{'PF':>6}{'Shrp':>6}"
          f"{'DD%':>6}{'Win/Y':>7}{'Last2$':>9}  {'NET$':>10}   {yhead}")
    print("-" * (62 + 7 * len(all_years)))

    # Sort by PF descending (cold ranking; visual review follows).
    def sort_key(row):
        m = row[3]
        return m.get("pf", 0.0) if m.get("pf") != float("inf") else 999.0

    for ticker, src_tag, preset, m in sorted(results, key=sort_key, reverse=True):
        if "error" in m:
            print(f"{ticker:<7}{preset:>4}  ERROR: {m['error']}")
            continue
        ygrid = ""
        for y in all_years:
            if y in m["yearly"]:
                pnl_k = m["yearly"][y]["pnl"] / 1000.0
                ygrid += f"{pnl_k:>+7.1f}"
            else:
                ygrid += f"{'.':>7}"
        win = f"{m['pos_years']}/{m['total_years']}"
        print(f"{ticker:<7}{preset:>4}{m['trades']:>5}{_pf_str(m['pf']):>6}"
              f"{m['sharpe']:>6.2f}{m['max_dd']:>6.1f}{win:>7}"
              f"{m['last2_pnl']/1000:>+8.1f}k{m['net_pnl']:>+11,.0f}   {ygrid}")

    print("-" * (62 + 7 * len(all_years)))
    print("  Year cells = net PnL in $k. Win/Y = winning years / years "
          "traded. Last2$ = net of last two years.")
    print("  COLD-READ: prefer stable green across years + strong recent "
          "years over a high 8-year aggregate alone.")


def print_robustness(results, configs):
    """Pair A/B per ticker and rank by parameter-robustness.

    The strongest signal of a real edge (vs a fit to one parameter set) is
    that BOTH presets are profitable. Example: HII (A 1.67 / B 1.54). A
    ticker that only works under one preset is treated as fragile.
    """
    if not ("A" in configs and "B" in configs):
        return

    by_ticker = {}
    for ticker, src_tag, preset, m in results:
        if "error" in m:
            continue
        by_ticker.setdefault(ticker, {})[preset] = m

    rows = []
    for ticker, d in by_ticker.items():
        if "A" not in d or "B" not in d:
            continue
        a, b = d["A"], d["B"]
        pf_a = a["pf"] if a["pf"] != float("inf") else 999.0
        pf_b = b["pf"] if b["pf"] != float("inf") else 999.0
        both_win = pf_a > 1.0 and pf_b > 1.0
        worst_pf = min(pf_a, pf_b)          # robustness = the weaker preset
        last2 = (a["last2_pnl"] + b["last2_pnl"]) / 2.0
        win_min = min(a["pos_years"], b["pos_years"])
        rows.append((ticker, pf_a, pf_b, worst_pf, both_win, last2,
                     win_min, a["total_years"]))

    # Rank: both-winners first, then by the weaker PF (worst-case strength).
    rows.sort(key=lambda r: (r[4], r[3]), reverse=True)

    print("\n" + "=" * 78)
    print("  PARAMETER ROBUSTNESS  (A and B paired -- both winning = real edge)")
    print("=" * 78)
    print(f"{'Ticker':<7}{'PF_A':>7}{'PF_B':>7}{'minPF':>7}"
          f"{'Both>1':>8}{'Last2avg$':>11}{'minWinY':>9}")
    print("-" * 56)
    for (ticker, pf_a, pf_b, worst_pf, both_win, last2,
         win_min, total_y) in rows:
        flag = "YES" if both_win else "-"
        pa = "inf" if pf_a >= 999.0 else f"{pf_a:.2f}"
        pb = "inf" if pf_b >= 999.0 else f"{pf_b:.2f}"
        mp = "inf" if worst_pf >= 999.0 else f"{worst_pf:.2f}"
        print(f"{ticker:<7}{pa:>7}{pb:>7}{mp:>7}{flag:>8}"
              f"{last2/1000:>+10.1f}k{win_min:>4}/{total_y:<4}")
    n_robust = sum(1 for r in rows if r[4])
    print("-" * 56)
    print(f"  {n_robust} ticker(s) with BOTH presets profitable "
          f"out of {len(rows)} paired.")
    print("  minPF = PF of the weaker preset (worst-case). minWinY = "
          "fewest winning years across A/B.")


def write_csv(path, results, all_years, quiet=False):
    lines = []
    header = ["ticker", "config", "trades", "pf", "sharpe", "max_dd",
              "pos_years", "total_years", "last2_pnl", "net_pnl"]
    header += [str(y) for y in all_years]
    lines.append(",".join(header))
    for ticker, src_tag, preset, m in results:
        if "error" in m:
            continue
        row = [ticker, preset, m["trades"],
               f"{m['pf']:.4f}" if m["pf"] != float("inf") else "inf",
               f"{m['sharpe']:.4f}", f"{m['max_dd']:.4f}",
               m["pos_years"], m["total_years"],
               f"{m['last2_pnl']:.2f}", f"{m['net_pnl']:.2f}"]
        for y in all_years:
            row.append(f"{m['yearly'][y]['pnl']:.2f}" if y in m["yearly"] else "")
        lines.append(",".join(str(c) for c in row))
    Path(path).write_text("\n".join(lines) + "\n", encoding="ascii")
    if not quiet:
        print(f"\n  CSV written: {path}")


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="ALTAIR 15m multi-asset sweep with regime hysteresis.")
    parser.add_argument("--source", choices=["native15m", "resample5m", "all"],
                        default="all", help="Which CSV universe to sweep.")
    parser.add_argument("--config", choices=["A", "B", "both"], default="both",
                        help="Entry/SL preset(s) to test per ticker.")
    parser.add_argument("--tickers", nargs="+", metavar="T",
                        help="Limit to specific tickers.")
    parser.add_argument("--csv", metavar="PATH",
                        help="Also dump the table to a CSV file.")
    parser.add_argument("--best-only", action="store_true",
                        help="With --config both, keep only the better PF "
                             "preset per ticker.")
    args = parser.parse_args()

    universe = discover_universe(args.source)
    if args.tickers:
        wanted = {t.upper() for t in args.tickers}
        universe = [u for u in universe if u[0].upper() in wanted]
    if not universe:
        print("No matching CSVs found.")
        return

    configs = ["A", "B"] if args.config == "both" else [args.config]

    print(f"Sweeping {len(universe)} ticker(s) x {len(configs)} config(s) "
          f"= {len(universe) * len(configs)} backtests ...")

    results = []
    all_years = set()
    for i, (ticker, csv_name, rs_min) in enumerate(universe, 1):
        src_tag = "rs5m" if rs_min > 0 else "15m"
        per_ticker = []
        for preset in configs:
            m = run_bt(ticker, csv_name, rs_min, preset)
            if "error" not in m:
                all_years.update(m["yearly"].keys())
            per_ticker.append((ticker, src_tag, preset, m))
        if args.best_only and len(per_ticker) > 1:
            ok = [r for r in per_ticker if "error" not in r[3]]
            if ok:
                best = max(ok, key=lambda r: (
                    r[3]["pf"] if r[3]["pf"] != float("inf") else 999.0))
                per_ticker = [best]
        results.extend(per_ticker)
        done = ", ".join(
            f"{p}:PF={_pf_str(m['pf'])}" if "error" not in m else f"{p}:ERR"
            for (_, _, p, m) in per_ticker)
        print(f"  [{i:>2}/{len(universe)}] {ticker:<6} ({src_tag})  {done}",
              flush=True)
        # Incremental persistence: rewrite the CSV after each ticker so a
        # long sweep survives an interruption without losing prior work.
        if args.csv:
            write_csv(args.csv, results, sorted(all_years), quiet=True)

    all_years = sorted(all_years)
    print_report(results, all_years, args.source, configs)
    print_robustness(results, configs)
    if args.csv:
        write_csv(args.csv, results, all_years)


if __name__ == "__main__":
    main()
