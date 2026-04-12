"""
lyra_short_prestudy.py -- Regime-based short-selling prestudy on index CFDs
============================================================================
Analyses historical 5-minute data for SP500 and NDX, resampled to H1, to
answer the key viability questions for the LYRA short strategy:

1. How often does the D1 regime leave CALM_UP?
2. How long do non-CALM_UP periods last?
3. What is the index return during each non-CALM_UP period?
4. Does DTOSC overbought provide a timing edge for short entries?
5. What is the overall expectancy of shorting during non-CALM_UP windows?

Regime detection reuses ALTAIR logic exactly (computed on H1 bars):
  - Mom12M:  close > SMA(close, 252 * bpd)
  - CALM:    ATR(14 * bpd) / SMA(ATR, 252 * bpd) < 1.0
  - Mom63d:  close > close[63 * bpd]
  - CALM_UP: all three True

DTOSC: Robert Miner's double-smoothed stochastic (period=8, sk=5, sd=3, sig=3)
  - ALTAIR long: fast crosses above slow from oversold (<25)
  - LYRA short:  fast crosses below slow from overbought (>75)

Usage:
    python tools/lyra_short_prestudy.py
    python tools/lyra_short_prestudy.py --index NDX
    python tools/lyra_short_prestudy.py --index SP500 --bpd 7 --ob 75

Output: console tables  + summary statistics
"""

import argparse
import csv
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

INDEX_FILES = {
    "SP500": DATA_DIR / "SP500_5m_15Yea.csv",
    "NDX":   DATA_DIR / "NDX_5m_15Yea.csv",
    "GDAXI": DATA_DIR / "GDAXI_5m_15Yea.csv",
    "NI225": DATA_DIR / "NI225_5m_15Yea.csv",
    "UK100": DATA_DIR / "UK100_5m_15Yea.csv",
    "EUR50": DATA_DIR / "EUR50_5m_5Yea.csv",
}

# Regular trading hours (UTC) per index for H1 resampling
INDEX_HOURS = {
    "SP500": (14, 20),   # US open 14:30 -> 21:00 close (7 bars)
    "NDX":   (14, 20),
    "GDAXI": (8, 16),    # Frankfurt 08:00-16:30 (9 bars)
    "NI225": (1, 7),     # Tokyo 01:00-07:00 UTC (7 bars, shifts w/ DST)
    "UK100": (8, 16),    # London 08:00-16:30 (9 bars)
    "EUR50": (8, 16),    # Eurex 08:00-16:30 (9 bars)
}

# Bars-per-day defaults per index
INDEX_BPD = {
    "SP500": 7, "NDX": 7, "GDAXI": 9, "NI225": 7, "UK100": 9, "EUR50": 9,
}

# Valid regime codes for entry filter
REGIME_FILTER_MAP = {
    "all":           {1, 2, 3},        # any non-CALM_UP
    "volatile_up":   {1},
    "calm_down":     {2},
    "volatile_down": {3},
    "bearish":       {2, 3},           # CALM_DOWN + VOLATILE_DOWN
}

# ---------------------------------------------------------------------------
# CSV loading
# ---------------------------------------------------------------------------

def load_5m_csv(path: Path) -> list[dict]:
    """Load Dukascopy 5-min CSV into list of dicts with datetime key."""
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            dt = datetime.strptime(f"{r['Date']},{r['Time']}", "%Y%m%d,%H:%M:%S")
            rows.append({
                "dt": dt,
                "open":  float(r["Open"]),
                "high":  float(r["High"]),
                "low":   float(r["Low"]),
                "close": float(r["Close"]),
                "vol":   float(r["Volume"]),
            })
    return rows


def resample_to_h1(bars_5m: list[dict],
                   hour_start: int = 14, hour_end: int = 20) -> list[dict]:
    """Aggregate 5-min bars to 1-hour OHLCV.

    Groups by date + hour.  Each H1 bar is labelled at the hour boundary
    (e.g. all 5-min bars from 14:00-14:55 -> H1 bar at 14:00).
    Only keeps hours in [hour_start, hour_end] inclusive.
    """
    groups: dict[tuple, list] = defaultdict(list)
    for b in bars_5m:
        h = b["dt"].hour
        if h < hour_start or h > hour_end:
            continue
        key = (b["dt"].date(), h)
        groups[key].append(b)

    h1 = []
    for (d, h) in sorted(groups):
        subs = groups[(d, h)]
        if not subs:
            continue
        h1.append({
            "dt":    datetime(d.year, d.month, d.day, h, 0, 0),
            "open":  subs[0]["open"],
            "high":  max(s["high"] for s in subs),
            "low":   min(s["low"] for s in subs),
            "close": subs[-1]["close"],
            "vol":   sum(s["vol"] for s in subs),
        })
    return h1


# ---------------------------------------------------------------------------
# Indicator calculations (pure numpy, mirrors ALTAIR exactly)
# ---------------------------------------------------------------------------

def sma(data: np.ndarray, period: int) -> np.ndarray:
    """Simple moving average. NaN-safe via pandas rolling."""
    return pd.Series(data).rolling(period, min_periods=period).mean().values


def true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    """True range array."""
    tr = np.empty_like(high)
    tr[0] = high[0] - low[0]
    for i in range(1, len(high)):
        tr[i] = max(high[i] - low[i],
                     abs(high[i] - close[i - 1]),
                     abs(low[i] - close[i - 1]))
    return tr


def atr_sma(high: np.ndarray, low: np.ndarray, close: np.ndarray,
            period: int) -> np.ndarray:
    """ATR via SMA of true-range (matches backtrader default)."""
    tr = true_range(high, low, close)
    return sma(tr, period)


def highest(data: np.ndarray, period: int) -> np.ndarray:
    """Rolling highest."""
    out = np.full_like(data, np.nan)
    for i in range(period - 1, len(data)):
        out[i] = np.max(data[i - period + 1: i + 1])
    return out


def lowest(data: np.ndarray, period: int) -> np.ndarray:
    """Rolling lowest."""
    out = np.full_like(data, np.nan)
    for i in range(period - 1, len(data)):
        out[i] = np.min(data[i - period + 1: i + 1])
    return out


def dtosc(high: np.ndarray, low: np.ndarray, close: np.ndarray,
          period: int = 8, sk: int = 5, sd: int = 3,
          sig: int = 3) -> tuple[np.ndarray, np.ndarray]:
    """DT Oscillator: returns (fast, slow) arrays."""
    hh = highest(high, period)
    ll = lowest(low, period)
    raw_k = 100.0 * (close - ll) / (hh - ll + 1e-10)
    fast = sma(sma(raw_k, sk), sd)
    slow = sma(fast, sig)
    return fast, slow


# ---------------------------------------------------------------------------
# Regime computation (mirrors ALTAIR exactly)
# ---------------------------------------------------------------------------

def compute_regime(close: np.ndarray, high: np.ndarray, low: np.ndarray,
                   bpd: int) -> np.ndarray:
    """
    Compute regime for each H1 bar.

    Returns array of ints:
        0 = CALM_UP
        1 = VOLATILE_UP
        2 = CALM_DOWN
        3 = VOLATILE_DOWN
    """
    p252 = 252 * bpd
    p63 = 63 * bpd
    p14 = 14 * bpd

    regime_sma = sma(close, p252)
    atr_short = atr_sma(high, low, close, p14)
    atr_long = sma(atr_short, p252)

    n = len(close)
    regime = np.full(n, 3, dtype=int)  # default VOLATILE_DOWN

    for i in range(max(p252, p63), n):
        mom12m = close[i] > regime_sma[i] if not np.isnan(regime_sma[i]) else False
        calm = (atr_short[i] / (atr_long[i] + 1e-10)) < 1.0 \
            if not (np.isnan(atr_short[i]) or np.isnan(atr_long[i])) else False
        mom63d = close[i] > close[i - p63]

        if mom12m and calm and mom63d:
            regime[i] = 0  # CALM_UP
        elif mom12m and not calm:
            regime[i] = 1  # VOLATILE_UP
        elif not mom12m and calm:
            regime[i] = 2  # CALM_DOWN
        else:
            regime[i] = 3  # VOLATILE_DOWN

    return regime


REGIME_NAMES = {0: "CALM_UP", 1: "VOLATILE_UP", 2: "CALM_DOWN", 3: "VOLATILE_DOWN"}


# ---------------------------------------------------------------------------
# Period extraction: identify contiguous non-CALM_UP windows
# ---------------------------------------------------------------------------

def extract_non_calm_up_periods(dates: list, close: np.ndarray,
                                 regime: np.ndarray) -> list[dict]:
    """Find contiguous non-CALM_UP windows and measure their return."""
    periods = []
    in_period = False
    start_idx = 0

    for i in range(len(regime)):
        if np.isnan(close[i]):
            continue

        is_calm_up = regime[i] == 0

        if not is_calm_up and not in_period:
            in_period = True
            start_idx = i
        elif is_calm_up and in_period:
            in_period = False
            end_idx = i - 1
            if end_idx > start_idx:
                entry_price = close[start_idx]
                exit_price = close[end_idx]
                pct_return = (entry_price - exit_price) / entry_price * 100  # short P&L
                days = (dates[end_idx] - dates[start_idx]).days
                periods.append({
                    "start": dates[start_idx],
                    "end":   dates[end_idx],
                    "days":  days,
                    "entry_price": entry_price,
                    "exit_price":  exit_price,
                    "index_move_pct": (exit_price - entry_price) / entry_price * 100,
                    "short_pnl_pct": pct_return,
                    "regime_at_start": REGIME_NAMES[regime[start_idx]],
                })

    # Handle period still open at end of data
    if in_period:
        end_idx = len(regime) - 1
        entry_price = close[start_idx]
        exit_price = close[end_idx]
        pct_return = (entry_price - exit_price) / entry_price * 100
        days = (dates[end_idx] - dates[start_idx]).days
        periods.append({
            "start": dates[start_idx],
            "end":   dates[end_idx],
            "days":  days,
            "entry_price": entry_price,
            "exit_price":  exit_price,
            "index_move_pct": (exit_price - entry_price) / entry_price * 100,
            "short_pnl_pct": pct_return,
            "regime_at_start": REGIME_NAMES[regime[start_idx]],
            "note": "OPEN (still in non-CALM_UP)",
        })

    return periods


# ---------------------------------------------------------------------------
# DTOSC short signals within non-CALM_UP windows
# ---------------------------------------------------------------------------

def simulate_dtosc_shorts(dates: list, close: np.ndarray, regime: np.ndarray,
                          fast: np.ndarray, slow: np.ndarray,
                          ob: float, max_bars: int = 35,
                          sl_pct: float = 2.0,
                          allowed_regimes: set | None = None) -> list[dict]:
    """
    Simulate short entries when DTOSC fast crosses below slow from overbought
    zone, but ONLY during allowed regime states.

    Each trade:
      - Entry: close of signal bar
      - Exit:  first of: regime returns to CALM_UP, SL hit, max_bars holding
      - P&L:   (entry - exit) / entry * 100
    """
    if allowed_regimes is None:
        allowed_regimes = {1, 2, 3}  # all non-CALM_UP

    trades = []
    i = 1
    in_trade = False

    while i < len(close):
        if np.isnan(fast[i]) or np.isnan(slow[i]) or np.isnan(close[i]):
            i += 1
            continue

        # Check for entry signal (not in trade, regime in allowed set)
        if not in_trade and regime[i] in allowed_regimes:
            # DTOSC bearish cross from overbought
            crossed_down = fast[i] < slow[i] and fast[i - 1] >= slow[i - 1]
            from_ob = fast[i - 1] > ob or slow[i - 1] > ob
            if crossed_down and from_ob:
                entry_price = close[i]
                entry_idx = i
                entry_date = dates[i]
                sl_price = entry_price * (1 + sl_pct / 100)
                in_trade = True
                i += 1
                continue

        # Manage open trade
        if in_trade:
            exit_reason = None
            exit_price = close[i]

            # Check SL (using high of bar would be better but we only have close)
            if close[i] >= sl_price:
                exit_reason = "SL"
                exit_price = sl_price

            # Check regime return to CALM_UP
            elif regime[i] == 0:
                exit_reason = "REGIME"

            # Check max holding
            elif (i - entry_idx) >= max_bars:
                exit_reason = "MAX_BARS"

            if exit_reason:
                pnl_pct = (entry_price - exit_price) / entry_price * 100
                trades.append({
                    "entry_date": entry_date,
                    "exit_date":  dates[i],
                    "entry_price": entry_price,
                    "exit_price":  exit_price,
                    "pnl_pct":    round(pnl_pct, 4),
                    "bars_held":  i - entry_idx,
                    "exit_reason": exit_reason,
                    "regime_at_entry": REGIME_NAMES[regime[entry_idx]],
                })
                in_trade = False

        i += 1

    return trades


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_separator(char: str = "=", width: int = 90):
    print(char * width)


def report_regime_periods(periods: list, index_name: str):
    """Print table of non-CALM_UP windows."""
    print_separator()
    print(f"  NON-CALM_UP PERIODS  --  {index_name}")
    print_separator()
    print(f"  {'#':>3}  {'Start':12}  {'End':12}  {'Days':>5}  "
          f"{'Idx Move%':>9}  {'Short P&L%':>10}  {'Regime':16}  {'Note'}")
    print_separator("-")

    total_short = 0.0
    winners = 0
    for n, p in enumerate(periods, 1):
        note = p.get("note", "")
        print(f"  {n:3d}  {p['start'].strftime('%Y-%m-%d'):12}  "
              f"{p['end'].strftime('%Y-%m-%d'):12}  {p['days']:5d}  "
              f"{p['index_move_pct']:+9.2f}  {p['short_pnl_pct']:+10.2f}  "
              f"{p['regime_at_start']:16}  {note}")
        total_short += p["short_pnl_pct"]
        if p["short_pnl_pct"] > 0:
            winners += 1

    print_separator("-")
    print(f"  Total periods: {len(periods)}")
    print(f"  Winners (short profit): {winners}/{len(periods)} "
          f"({100*winners/max(len(periods),1):.0f}%)")
    print(f"  Cumulative short P&L: {total_short:+.2f}%")
    avg_days = np.mean([p["days"] for p in periods]) if periods else 0
    print(f"  Avg duration: {avg_days:.0f} days")
    print()


def report_dtosc_trades(trades: list, index_name: str, ob: float):
    """Print trade-level and summary stats for DTOSC-timed shorts."""
    print_separator()
    print(f"  DTOSC SHORT TRADES (OB={ob})  --  {index_name}")
    print_separator()

    if not trades:
        print("  No trades generated.")
        print()
        return

    print(f"  {'#':>3}  {'Entry Date':12}  {'Exit Date':12}  "
          f"{'P&L%':>8}  {'Bars':>5}  {'Exit':8}  {'Regime'}")
    print_separator("-")

    pnls = []
    by_regime = defaultdict(list)
    by_exit = defaultdict(int)

    for n, t in enumerate(trades, 1):
        print(f"  {n:3d}  {t['entry_date'].strftime('%Y-%m-%d %H:%M'):12}  "
              f"{t['exit_date'].strftime('%Y-%m-%d %H:%M'):12}  "
              f"{t['pnl_pct']:+8.2f}  {t['bars_held']:5d}  "
              f"{t['exit_reason']:8}  {t['regime_at_entry']}")
        pnls.append(t["pnl_pct"])
        by_regime[t["regime_at_entry"]].append(t["pnl_pct"])
        by_exit[t["exit_reason"]] += 1

    pnls = np.array(pnls)
    winners = pnls[pnls > 0]
    losers = pnls[pnls <= 0]
    wr = len(winners) / len(pnls) * 100
    avg_win = np.mean(winners) if len(winners) > 0 else 0
    avg_loss = np.mean(losers) if len(losers) > 0 else 0
    expectancy = (wr / 100 * avg_win) + ((1 - wr / 100) * avg_loss)
    pf = abs(np.sum(winners) / np.sum(losers)) if np.sum(losers) != 0 else float('inf')

    print_separator("-")
    print(f"\n  SUMMARY STATISTICS:")
    print(f"  Total trades:    {len(pnls)}")
    print(f"  Win rate:        {wr:.1f}%")
    print(f"  Avg winner:      {avg_win:+.2f}%")
    print(f"  Avg loser:       {avg_loss:+.2f}%")
    print(f"  Expectancy:      {expectancy:+.3f}% per trade")
    print(f"  Profit Factor:   {pf:.2f}")
    print(f"  Cumulative P&L:  {np.sum(pnls):+.2f}%")
    print(f"  Max winner:      {np.max(pnls):+.2f}%")
    print(f"  Max loser:       {np.min(pnls):+.2f}%")
    print(f"  Sharpe (trades): {np.mean(pnls)/np.std(pnls):.2f}" if np.std(pnls) > 0 else "")

    print(f"\n  By exit reason:")
    for reason, count in sorted(by_exit.items()):
        subset = [t["pnl_pct"] for t in trades if t["exit_reason"] == reason]
        print(f"    {reason:10} : {count:3d} trades, avg P&L {np.mean(subset):+.2f}%")

    print(f"\n  By regime at entry:")
    for reg_name in ["VOLATILE_UP", "CALM_DOWN", "VOLATILE_DOWN"]:
        if reg_name in by_regime:
            subset = by_regime[reg_name]
            w = len([x for x in subset if x > 0])
            print(f"    {reg_name:16} : {len(subset):3d} trades, "
                  f"WR {100*w/len(subset):.0f}%, "
                  f"avg {np.mean(subset):+.2f}%, "
                  f"sum {np.sum(subset):+.2f}%")

    print()


def report_regime_distribution(regime: np.ndarray, dates: list):
    """Show % of time in each regime."""
    valid = regime[~np.isnan(np.array([float(r) for r in regime]))]
    total = len(valid)
    first_valid = None
    for i, d in enumerate(dates):
        if regime[i] in (0, 1, 2, 3):
            first_valid = d
            break

    print(f"  Regime distribution ({first_valid.strftime('%Y-%m') if first_valid else '?'}"
          f" - {dates[-1].strftime('%Y-%m')}):")
    for code in range(4):
        count = np.sum(regime == code)
        print(f"    {REGIME_NAMES[code]:16} : {count:6d} H1 bars "
              f"({100*count/total:.1f}%)")
    print()


# ---------------------------------------------------------------------------
# Baseline: always short when not CALM_UP (no DTOSC timing)
# ---------------------------------------------------------------------------

def report_baseline_vs_timed(periods: list, trades: list):
    """Compare 'always short' vs DTOSC-timed."""
    print_separator()
    print("  COMPARISON: ALWAYS-SHORT vs DTOSC-TIMED")
    print_separator()

    # Baseline
    baseline_pnl = sum(p["short_pnl_pct"] for p in periods)
    baseline_n = len(periods)

    # Timed
    timed_pnl = sum(t["pnl_pct"] for t in trades) if trades else 0
    timed_n = len(trades)

    print(f"  {'Metric':<25} {'Always-Short':>15} {'DTOSC-Timed':>15}")
    print(f"  {'-'*25} {'-'*15} {'-'*15}")
    print(f"  {'N trades/periods':<25} {baseline_n:>15d} {timed_n:>15d}")
    print(f"  {'Cumulative P&L %':<25} {baseline_pnl:>+15.2f} {timed_pnl:>+15.2f}")

    if timed_n > 0:
        timed_pnls = [t["pnl_pct"] for t in trades]
        timed_wr = 100 * len([x for x in timed_pnls if x > 0]) / timed_n
        print(f"  {'Win Rate %':<25} {'N/A':>15} {timed_wr:>15.1f}")
        timed_exp = np.mean(timed_pnls)
        print(f"  {'Avg P&L per trade %':<25} {'N/A':>15} {timed_exp:>+15.3f}")

    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Lyra short prestudy on index CFDs")
    ap.add_argument("--index", default="SP500", choices=list(INDEX_FILES),
                    help="Index to analyze (default: SP500)")
    ap.add_argument("--all", action="store_true",
                    help="Run prestudy on ALL available indices")
    ap.add_argument("--bpd", type=int, default=0,
                    help="Bars per day override (0 = auto-detect per index)")
    ap.add_argument("--ob", type=float, default=75,
                    help="DTOSC overbought threshold (default: 75)")
    ap.add_argument("--sl", type=float, default=2.0,
                    help="Stop loss %% for DTOSC trades (default: 2.0)")
    ap.add_argument("--max-bars", type=int, default=35,
                    help="Max holding period in H1 bars (default: 35 = ~5 days)")
    ap.add_argument("--from-year", type=int, default=2017,
                    help="Start year for analysis (default: 2017)")
    ap.add_argument("--regime", default="all",
                    choices=list(REGIME_FILTER_MAP),
                    help="Which regime(s) to allow short entries "
                         "(default: all non-CALM_UP)")
    args = ap.parse_args()

    allowed = REGIME_FILTER_MAP[args.regime]
    indices = list(INDEX_FILES) if args.all else [args.index]

    # Collect summary for --all mode
    summary_rows = []

    for idx_name in indices:
        csv_path = INDEX_FILES[idx_name]
        if not csv_path.exists():
            print(f"\n  SKIP {idx_name}: data file not found ({csv_path.name})")
            continue

        bpd = args.bpd if args.bpd > 0 else INDEX_BPD.get(idx_name, 7)
        h_start, h_end = INDEX_HOURS.get(idx_name, (14, 20))

        run_single(idx_name, csv_path, bpd, h_start, h_end,
                   args.from_year, args.ob, args.sl, args.max_bars,
                   allowed, summary_rows)

    # Final cross-index summary in --all mode
    if len(indices) > 1 and summary_rows:
        print_separator("=")
        print(f"  CROSS-INDEX SUMMARY  (regime filter: {args.regime})")
        print_separator("=")
        print(f"  {'Index':8} {'Trades':>7} {'WR%':>6} {'PF':>6} "
              f"{'Expect%':>9} {'CumPnL%':>9} {'Sharpe':>7}")
        print_separator("-")
        for r in summary_rows:
            print(f"  {r['index']:8} {r['trades']:>7d} {r['wr']:>6.1f} "
                  f"{r['pf']:>6.2f} {r['exp']:>+9.3f} {r['cum']:>+9.2f} "
                  f"{r['sharpe']:>7.2f}")
        print_separator("=")

    print("\n  PRESTUDY COMPLETE\n")


def run_single(idx_name, csv_path, bpd, h_start, h_end,
               from_year, ob, sl, max_bars, allowed, summary_rows):
    """Run full prestudy for one index."""
    print(f"\n{'#'*90}")
    print(f"  {idx_name}  (bpd={bpd}, hours={h_start:02d}-{h_end:02d} UTC)")
    print(f"{'#'*90}")

    print(f"\n  Loading {idx_name} 5-min data from {csv_path.name} ...")
    bars_5m = load_5m_csv(csv_path)
    print(f"  Loaded {len(bars_5m):,} x 5-min bars")

    print(f"  Resampling to H1 ({h_start:02d}:00-{h_end:02d}:00 UTC) ...")
    h1 = resample_to_h1(bars_5m, hour_start=h_start, hour_end=h_end)
    print(f"  {len(h1):,} H1 bars")

    # Filter by start year
    h1 = [b for b in h1 if b["dt"].year >= from_year]
    if not h1:
        print(f"  No data after {from_year} filter. Skipping.")
        return
    print(f"  After filtering >= {from_year}: {len(h1):,} H1 bars")
    print(f"  Date range: {h1[0]['dt'].strftime('%Y-%m-%d')} - "
          f"{h1[-1]['dt'].strftime('%Y-%m-%d')}")

    # Convert to numpy
    dates = [b["dt"] for b in h1]
    close = np.array([b["close"] for b in h1])
    high = np.array([b["high"] for b in h1])
    low = np.array([b["low"] for b in h1])

    # Compute regime
    print(f"\n  Computing regime (bpd={bpd}) ...")
    regime = compute_regime(close, high, low, bpd)
    report_regime_distribution(regime, dates)

    # Non-CALM_UP periods
    periods = extract_non_calm_up_periods(dates, close, regime)
    report_regime_periods(periods, idx_name)

    # DTOSC
    print(f"  Computing DTOSC (ob={ob}) ...")
    fast, slow = dtosc(high, low, close)

    # Simulate DTOSC-timed shorts
    trades = simulate_dtosc_shorts(dates, close, regime, fast, slow,
                                   ob=ob, max_bars=max_bars,
                                   sl_pct=sl, allowed_regimes=allowed)
    report_dtosc_trades(trades, idx_name, ob)

    # Comparison
    report_baseline_vs_timed(periods, trades)

    # Collect summary stats
    if trades:
        pnls = np.array([t["pnl_pct"] for t in trades])
        w = pnls[pnls > 0]
        l = pnls[pnls <= 0]
        summary_rows.append({
            "index": idx_name,
            "trades": len(pnls),
            "wr": 100 * len(w) / len(pnls),
            "pf": abs(np.sum(w) / np.sum(l)) if np.sum(l) != 0 else 999,
            "exp": np.mean(pnls),
            "cum": np.sum(pnls),
            "sharpe": np.mean(pnls) / np.std(pnls) if np.std(pnls) > 0 else 0,
        })
    else:
        summary_rows.append({
            "index": idx_name, "trades": 0, "wr": 0, "pf": 0,
            "exp": 0, "cum": 0, "sharpe": 0,
        })


if __name__ == "__main__":
    main()
