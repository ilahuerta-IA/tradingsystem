"""
ALTAIR Live vs BT comparison (one-shot, 2026-04 window).

Runs ALTAIR on M5 Dukascopy CSVs (resampled per-ticker to live TF) for
the 4 tickers also active on the live demo (NVDA, GOOGL, JPM, V), and
prints every entry/exit that fell within the live window so we can
diff against the MT5 trade log.

Periodo live observado en MT5 (UTC+3 broker, DST):
    NVDA buy 2026-04-15 21:50 -> exit 2026-04-17 16:30   (+699.60)
    NVDA buy 2026-04-20 19:20 -> exit 2026-04-21 16:30   (+647.15)
    NVDA buy 2026-04-21 21:35 -> exit 2026-04-23 16:30   (+572.40)

UTC = broker - 3h (April DST). BT runs on UTC (Dukascopy).

Usage:
    python tools/altair_live_bt_compare.py
"""
from __future__ import annotations

import contextlib
import datetime as dt
import io
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import backtrader as bt  # noqa: E402

from strategies.altair_strategy import ALTAIRStrategy  # noqa: E402
from config.settings_altair import (  # noqa: E402
    ALTAIR_STRATEGIES_CONFIG,
    ALTAIR_BROKER_CONFIG,
    _DEFAULT_PARAMS,
    _make_config,
)
from lib.commission import ETFCommission, ETFCSVData  # noqa: E402


# Window of the live screenshot. Inclusive on both ends.
# Run #3 (2026-06-02): window 2026-05-16 -> 2026-05-30 (last 2 weeks).
# Only live ALTAIR entry in window: JPM 2026-05-27 (entry) -> 2026-05-28 (exit).
LIVE_WINDOW_START_UTC = dt.datetime(2026, 5, 16, 0, 0, 0)
LIVE_WINDOW_END_UTC = dt.datetime(2026, 5, 30, 23, 59, 59)

# BT warmup: ALTAIR D1 regime needs SMA(252d) -> ~13 months minimum.
# Use 2024-01-01 to be safe; resample is M5 -> 15/30/60m.
BT_FROM = dt.datetime(2024, 1, 1)
BT_TO = dt.datetime(2026, 5, 30)

STARTING_CASH = 100_000.0

# Per-ticker setup matching live (bot_settings.ALTAIR_LIVE_TF).
TICKERS = [
    # (asset_name, csv_filename, resample_minutes, bars_per_day,
    #  base_config_key_in_settings_altair)
    ("NVDA",  "NVDA_5m_8Yea.csv",  15, 26, "NVDA_ALTAIR"),
    ("GOOGL", "GOOGL_5m_8Yea.csv", 15, 26, "GOOGL_ALTAIR"),
    ("JPM",   "JPM_5m_8Yea.csv",   30, 13, "JPM_ALTAIR"),
    ("V",     "V_5m_8Yea.csv",     60,  7, "V_ALTAIR"),
]

# Live trades from MT5 screenshot (Run #3, window 2026-05-16 -> 2026-05-30).
# Time conversion: bot JSONL timestamps = CEST (UTC+2 summer), MT5 screenshot = UTC+3.
# Both map to the same UTC: bot 21:35 CEST == screenshot 22:35 UTC+3 == 19:35 UTC.
# Only ALTAIR live entry in this window: JPM 2026-05-27 (ticket 12980057).
# Real fills per MT5 screenshot (NOT bot's ESTIMATED $0 TRADE_CLOSED event).
LIVE_TRADES = {
    "NVDA":  [],
    "GOOGL": [],
    "JPM": [
        # (entry_utc, entry_price, exit_utc, exit_price, pnl, ticket)
        # Bot SIGNAL log: 2026-05-27 21:35 CEST = 19:35 UTC, entry=299.04
        #   SL=297.19 TP=306.11, volume=152, slippage 0 (stock market order).
        # MT5 real fills: buy @ 299.040, exit @ 297.50 = -224.96 (close above SL,
        #   not PROT_STOP; ~13:30 UTC 2026-05-28).
        (dt.datetime(2026, 5, 27, 19, 35), 299.040,
         dt.datetime(2026, 5, 28, 13, 30), 297.500, -224.96, 12980057),
    ],
    "V":     [],
}


def build_config(asset_name, csv_filename, resample_minutes, bars_per_day,
                 base_key):
    """Build ad-hoc ALTAIR config pointing to M5 Dukascopy CSV with
    resample to the live timeframe."""
    base = ALTAIR_STRATEGIES_CONFIG[base_key]
    cfg = _make_config(
        asset_name,
        csv_filename,
        BT_FROM,
        active=True,
        universe=base.get("universe", "ndx"),
    )
    # Inherit per-ticker tuning (max_sl_atr_mult, dtosc_os) from base config.
    base_params = base["params"]
    for key in ("max_sl_atr_mult", "dtosc_os"):
        if key in base_params:
            cfg["params"][key] = base_params[key]
    cfg["params"]["bars_per_day"] = bars_per_day
    cfg["params"]["export_reports"] = True   # populates strat.trade_reports
    cfg["params"]["print_signals"] = False
    cfg["from_date"] = BT_FROM
    cfg["to_date"] = BT_TO
    cfg["resample_minutes"] = resample_minutes
    return cfg


def run_bt(asset_name, cfg):
    cerebro = bt.Cerebro(stdstats=False)
    data_path = PROJECT_ROOT / cfg["data_path"]
    data = ETFCSVData(
        dataname=str(data_path),
        dtformat="%Y%m%d", tmformat="%H:%M:%S",
        datetime=0, time=1, open=2, high=3, low=4, close=5,
        volume=6, openinterest=-1,
        fromdate=cfg["from_date"], todate=cfg["to_date"],
    )
    rs = cfg.get("resample_minutes", 0)
    if rs > 0:
        d = cerebro.resampledata(
            data, timeframe=bt.TimeFrame.Minutes, compression=rs,
        )
        d._name = asset_name
    else:
        cerebro.adddata(data, name=asset_name)

    cerebro.broker.setcash(STARTING_CASH)
    broker_cfg = ALTAIR_BROKER_CONFIG.get("darwinex_zero_stock", {})
    ETFCommission.total_commission = 0.0
    ETFCommission.total_contracts = 0.0
    ETFCommission.commission_calls = 0
    cerebro.broker.addcommissioninfo(ETFCommission(
        commission=broker_cfg.get("commission_per_contract", 0.02),
        margin_pct=broker_cfg.get("margin_percent", 20.0),
    ))
    cerebro.addstrategy(ALTAIRStrategy, **cfg["params"])

    f = io.StringIO()
    with contextlib.redirect_stdout(f):
        results = cerebro.run()
    return results[0]


def filter_window(reports, start, end):
    """Keep trades whose entry OR exit lies in the window."""
    out = []
    for r in reports:
        et = r.get("entry_time")
        xt = r.get("exit_time")
        in_w = False
        if et and start <= et <= end:
            in_w = True
        if xt and start <= xt <= end:
            in_w = True
        if in_w:
            out.append(r)
    return out


def fmt(x, w=8, prec=2):
    if x is None:
        return " " * w
    return f"{x:>{w}.{prec}f}"


def print_bt_trades(asset, trades):
    print(f"\n--- BT trades for {asset} ({len(trades)} in window) ---")
    if not trades:
        print("  (none)")
        return
    print(f"  {'entry_utc':<19} {'entry_px':>9} {'sl':>9} {'tp':>9} "
          f"{'exit_utc':<19} {'pnl':>9} {'reason':<14} {'bars':>5}")
    for r in trades:
        et = r["entry_time"].strftime("%Y-%m-%d %H:%M")
        xt = (r.get("exit_time") or dt.datetime(1970, 1, 1)).strftime(
            "%Y-%m-%d %H:%M") if r.get("exit_time") else "OPEN"
        print(f"  {et:<19} "
              f"{fmt(r.get('entry_price'), 9, 3)} "
              f"{fmt(r.get('stop_loss'),   9, 3)} "
              f"{fmt(r.get('take_profit'), 9, 3)} "
              f"{xt:<19} "
              f"{fmt(r.get('pnl'),         9, 2)} "
              f"{(r.get('exit_reason') or 'OPEN'):<14} "
              f"{(r.get('bars_held') or 0):>5d}")


def print_live_trades(asset, lives):
    print(f"\n--- Live trades for {asset} ({len(lives)} in window) ---")
    if not lives:
        print("  (none)")
        return
    print(f"  {'entry_utc':<19} {'entry_px':>9} "
          f"{'exit_utc':<19} {'exit_px':>9} {'pnl':>9} {'ticket':>10}")
    for entry_utc, ep, exit_utc, xp, pnl, tk in lives:
        print(f"  {entry_utc.strftime('%Y-%m-%d %H:%M'):<19} "
              f"{ep:>9.3f} "
              f"{exit_utc.strftime('%Y-%m-%d %H:%M'):<19} "
              f"{xp:>9.3f} {pnl:>9.2f} {tk:>10d}")


def diff_summary(asset, bt_trades, live_trades):
    """Match BT vs live by closest entry time (within 2h) and report deltas."""
    if not bt_trades and not live_trades:
        return
    print(f"\n--- DIFF for {asset} ---")
    used_bt = set()
    for entry_utc, ep, exit_utc, xp, pnl_l, tk in live_trades:
        best = None
        best_dt = None
        for i, r in enumerate(bt_trades):
            if i in used_bt:
                continue
            d = abs((r["entry_time"] - entry_utc).total_seconds())
            if best_dt is None or d < best_dt:
                best_dt = d
                best = i
        if best is None or best_dt is None or best_dt > 7200:
            print(f"  [LIVE only] entry {entry_utc} px={ep:.3f} "
                  f"pnl={pnl_l:+.2f} (no BT match within 2h)")
            continue
        used_bt.add(best)
        r = bt_trades[best]
        d_entry_min = (r["entry_time"] - entry_utc).total_seconds() / 60.0
        d_px = (r["entry_price"] - ep)
        print(f"  [MATCH ] live {entry_utc:%Y-%m-%d %H:%M} px={ep:.3f}  "
              f"<->  bt {r['entry_time']:%Y-%m-%d %H:%M} px={r['entry_price']:.3f}"
              f"  d_entry={d_entry_min:+.0f}min d_px={d_px:+.3f}")
    for i, r in enumerate(bt_trades):
        if i not in used_bt:
            print(f"  [BT only ] entry {r['entry_time']} px={r['entry_price']:.3f} "
                  f"pnl={r.get('pnl', 0):+.2f} reason={r.get('exit_reason')}")


def main():
    print("=" * 78)
    print(f"ALTAIR Live vs BT comparison")
    print(f"Window UTC: {LIVE_WINDOW_START_UTC} -> {LIVE_WINDOW_END_UTC}")
    print(f"BT period:  {BT_FROM.date()} -> {BT_TO.date()} (warmup included)")
    print("=" * 78)

    for asset_name, csv_file, rs_min, bpd, base_key in TICKERS:
        cfg = build_config(asset_name, csv_file, rs_min, bpd, base_key)
        print(f"\n### {asset_name} (M5 -> {rs_min}m, "
              f"max_sl={cfg['params'].get('max_sl_atr_mult')}, "
              f"dtosc_os={cfg['params'].get('dtosc_os')})")
        try:
            strat = run_bt(asset_name, cfg)
        except Exception as e:
            print(f"  ERROR: {e}")
            continue

        all_reports = strat.trade_reports
        in_window = filter_window(
            all_reports, LIVE_WINDOW_START_UTC, LIVE_WINDOW_END_UTC,
        )
        # Whole-period summary
        total = strat.total_trades
        wins = strat.wins
        gp = strat.gross_profit
        gl = strat.gross_loss
        pf = (gp / gl) if gl > 0 else float("inf")
        wr = (wins / total * 100) if total else 0
        print(f"  full BT: trades={total} wins={wins} ({wr:.1f}%) "
              f"PF={pf:.2f} GP=${gp:.0f} GL=${gl:.0f}")

        print_bt_trades(asset_name, in_window)
        print_live_trades(asset_name, LIVE_TRADES[asset_name])
        diff_summary(asset_name, in_window, LIVE_TRADES[asset_name])

    print("\n" + "=" * 78)
    print("DONE")
    print("=" * 78)


if __name__ == "__main__":
    main()
