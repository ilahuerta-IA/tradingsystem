"""
Connors RSI(2) Study v2 — H4 timeframe + Forex/Gold extension.

Compares Daily vs H4 on 8 assets:
  Indices:  SP500, NDX, GDAXI, NI225
  Gold:     XAUUSD
  Forex:    EURUSD, USDJPY, USDCHF

Same Connors parameters (zero optimization):
  RSI(2), Close > SMA(200) filter, exit Close > SMA(5), LONG only.

NOTE: SMA(200) on H4 ≈ 33 market days (vs ~200 on Daily).
      This is a DIFFERENT regime filter — not Connors-equivalent.

Usage:
  python tools/connors_rsi2_h4_study.py
"""

import os
import time
import numpy as np
import pandas as pd
from math import sqrt as msqrt

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')

# ── Asset definitions ──────────────────────────────────────────────
# swap_per_day_usd: positive = cost (you pay), negative = income
# point_value: USD PnL per 1 full price-point move (1 standard lot)

ASSETS = {
    'SP500': {
        'files': ['SP500_5m_15Yea.csv'],
        'swap_per_day_usd': 9.28,
        'point_value': 10.0,           # CFD $10/point
    },
    'NDX': {
        'files': ['NDX_5m_15Yea.csv'],
        'swap_per_day_usd': 35.62,
        'point_value': 1.0,            # CFD $1/point
    },
    'GDAXI': {
        'files': ['GDAXI_5m_15Yea.csv'],
        'swap_per_day_usd': 22.46,
        'point_value': 1.0,            # CFD ~€1/point
    },
    'NI225': {
        'files': ['NI225_5m_15Yea.csv'],
        'swap_per_day_usd': 10.0,
        'point_value': 0.01,           # JPY micro conversion
    },
    'XAUUSD': {
        'files': ['XAUUSD_5m_5Yea.csv'],
        'swap_per_day_usd': 42.0,      # gold has no yield, high carry cost
        'point_value': 100.0,           # 100oz lot: $100 per $1 move
    },
    'EURUSD': {
        'files': ['EURUSD_5m_5Yea.csv'],
        'swap_per_day_usd': 6.5,       # EUR rate < USD rate → you pay
        'point_value': 100000.0,        # 100K lot: full price-point
    },
    'USDJPY': {
        'files': ['USDJPY_5m_5Yea.csv'],
        'swap_per_day_usd': -7.0,      # USD rate > JPY rate → you RECEIVE
        'point_value': 667.0,           # ~100K/150
    },
    'USDCHF': {
        'files': ['USDCHF_5m_5Yea.csv'],
        'swap_per_day_usd': -4.0,      # USD rate > CHF rate → you RECEIVE
        'point_value': 113636.0,        # ~100K/0.88
    },
}

# ── Connors parameters (100% published, zero optimization) ────────
RSI_PERIOD = 2
SMA_FILTER = 200
SMA_EXIT = 5
RSI_THRESHOLDS = [5, 10, 15]
ATR_PERIOD = 14
MAX_HOLD_DAYS = 20             # calendar days (same for Daily & H4)

TIMEFRAMES = ['1D', '4h']     # compare both

SEP = "=" * 80
SUBSEP = "-" * 80


# ── Data loading ──────────────────────────────────────────────────

def load_raw(asset_key):
    """Load 5m CSV into DataFrame."""
    info = ASSETS[asset_key]
    for fname in info['files']:
        p = os.path.join(DATA_DIR, fname)
        if os.path.exists(p):
            df = pd.read_csv(p)
            df['datetime'] = pd.to_datetime(
                df['Date'].astype(str) + ' ' + df['Time'])
            df = df.set_index('datetime').sort_index()
            df = df[df.index.dayofweek < 5]
            return df
    return None


def resample_tf(df, tf):
    """Resample 5m data to tf (e.g. '1D', '4h')."""
    r = df.resample(tf).agg({
        'Open': 'first', 'High': 'max',
        'Low': 'min', 'Close': 'last', 'Volume': 'sum'
    }).dropna(subset=['Open'])
    r.columns = ['open', 'high', 'low', 'close', 'volume']
    return r


# ── Indicators ────────────────────────────────────────────────────

def compute_rsi(close, period):
    """Wilder RSI (exponential)."""
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def compute_atr(data, period):
    prev_c = data['close'].shift(1)
    tr = pd.concat([
        data['high'] - data['low'],
        (data['high'] - prev_c).abs(),
        (data['low'] - prev_c).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def calc_score(edge, n):
    if n < 1 or np.isnan(edge):
        return 0.0
    return edge * msqrt(n)


# ── Core study ────────────────────────────────────────────────────

def study(asset_key, tf, raw_df):
    """Run Connors RSI(2) study for one asset × one timeframe."""
    data = resample_tf(raw_df, tf)
    info = ASSETS[asset_key]

    rsi2 = compute_rsi(data['close'], RSI_PERIOD)
    sma200 = data['close'].rolling(SMA_FILTER).mean()
    sma5 = data['close'].rolling(SMA_EXIT).mean()
    atr = compute_atr(data, ATR_PERIOD)

    results = {}
    for rsi_thresh in RSI_THRESHOLDS:
        entry_mask = (rsi2 < rsi_thresh) & (data['close'] > sma200)
        entry_set = set(data.index[entry_mask])

        trades = []
        idx = data.index.tolist()
        i = 0

        while i < len(idx) - 1:
            dt = idx[i]
            if dt not in entry_set:
                i += 1
                continue

            # Entry on next bar open
            entry_dt = idx[i + 1]
            entry_price = data.at[entry_dt, 'open']
            entry_atr = atr.get(dt, np.nan)

            if np.isnan(entry_price) or np.isnan(entry_atr) or entry_atr <= 0:
                i += 1
                continue

            # Scan for exit: Close > SMA(5) or max hold exceeded
            exit_price = np.nan
            exit_dt = entry_dt
            j = i + 1

            while j < len(idx):
                exit_dt = idx[j]
                c = data.at[exit_dt, 'close']
                s5 = sma5.get(exit_dt, np.nan)

                if not np.isnan(s5) and c > s5:
                    exit_price = c
                    break

                cal_days = (exit_dt - entry_dt).days
                if cal_days >= MAX_HOLD_DAYS:
                    exit_price = c
                    break
                j += 1

            if np.isnan(exit_price):
                i += 1
                continue

            pnl_pts = exit_price - entry_price
            pnl_atr = pnl_pts / entry_atr

            # Swap: calendar nights held (NOT bar count)
            hold_days = max((exit_dt - entry_dt).days, 0)
            swap_total = info['swap_per_day_usd'] * hold_days
            pnl_usd = pnl_pts * info['point_value']

            trades.append({
                'entry_date': entry_dt,
                'exit_date': exit_dt,
                'pnl_atr': pnl_atr,
                'pnl_usd': pnl_usd,
                'hold_days': hold_days,
                'swap_usd': swap_total,
                'net_usd': pnl_usd - swap_total,
                'year': entry_dt.year,
            })

            # Skip past exit to avoid overlapping trades
            i = j + 1

        results[rsi_thresh] = trades

    return results, len(data), data.index[0].date(), data.index[-1].date()


# ── Reporting ─────────────────────────────────────────────────────

def main():
    os.chdir(BASE_DIR)
    t0 = time.time()

    print(SEP)
    print("CONNORS RSI(2) STUDY v2 — Daily vs H4 + Forex/Gold")
    print(SEP)
    print(f"RSI period: {RSI_PERIOD}")
    print(f"SMA filter: {SMA_FILTER}")
    print(f"SMA exit:   {SMA_EXIT}")
    print(f"RSI thresholds: {RSI_THRESHOLDS}")
    print(f"Timeframes: {TIMEFRAMES}")
    print(f"Max hold:   {MAX_HOLD_DAYS} calendar days")
    print(f"NOTE: SMA(200) on H4 ≈ 33 market days (vs ~200 on Daily)")
    print(f"Parameters: ALL from published literature (zero optimization)")
    print()

    # ── Load raw 5m data ──
    print("Loading data...")
    raw_data = {}
    for asset in ASSETS:
        df = load_raw(asset)
        if df is not None:
            raw_data[asset] = df
            print(f"  {asset}: {len(df):,} 5m bars")
        else:
            print(f"  {asset}: NOT FOUND")
    print(f"  Loaded in {time.time() - t0:.1f}s")
    print()

    # ── Run all studies ──
    print("Running studies...")
    all_results = {}
    for tf in TIMEFRAMES:
        for asset in raw_data:
            t1 = time.time()
            res, n_bars, start, end = study(asset, tf, raw_data[asset])
            all_results[(asset, tf)] = (res, n_bars, start, end)
            elapsed = time.time() - t1
            print(f"  {asset:8s} {tf:3s}: {n_bars:>6} bars "
                  f"({start} to {end}) [{elapsed:.1f}s]")
    print()

    # ══════════════════════════════════════════════════════════════
    # REPORT 1: EDGE SUMMARY
    # ══════════════════════════════════════════════════════════════
    print(SEP)
    print("REPORT 1: EDGE SUMMARY (Daily vs H4, all assets)")
    print(SEP)
    print(f"  {'Asset':<8} {'TF':<4} {'RSI<':<5} {'N':>5} {'Edge(ATR)':>10} "
          f"{'WR%':>6} {'Score':>7} {'AvgDays':>8} "
          f"{'SwpDir':>7} {'Net$/tr':>10}")
    print(f"  {SUBSEP}")

    for asset in ASSETS:
        for tf in TIMEFRAMES:
            key = (asset, tf)
            if key not in all_results:
                continue
            res, _, _, _ = all_results[key]

            for rsi_thresh in RSI_THRESHOLDS:
                trades = res[rsi_thresh]
                n = len(trades)
                if n < 5:
                    print(f"  {asset:<8} {tf:<4} {rsi_thresh:<5} {n:>5}  "
                          f"(insufficient)")
                    continue

                df_t = pd.DataFrame(trades)
                edge = df_t['pnl_atr'].mean()
                wr = (df_t['pnl_atr'] > 0).mean() * 100
                sc = calc_score(edge, n)
                avg_days = df_t['hold_days'].mean()
                avg_net = df_t['net_usd'].mean()

                # Swap direction indicator
                info = ASSETS[asset]
                swp = "RECV" if info['swap_per_day_usd'] < 0 else "PAY"

                flag = " ***" if sc >= 2.0 else " *" if sc >= 1.5 else ""
                print(f"  {asset:<8} {tf:<4} {rsi_thresh:<5} {n:>5} "
                      f"{edge:>+10.4f} {wr:>5.1f}% {sc:>+7.2f} "
                      f"{avg_days:>7.1f}d {swp:>7} "
                      f"{avg_net:>+10.1f}{flag}")

        print()  # blank line between assets

    # ══════════════════════════════════════════════════════════════
    # REPORT 2: YEARLY STABILITY (Score >= 1.5 candidates)
    # ══════════════════════════════════════════════════════════════
    print(SEP)
    print("REPORT 2: YEARLY STABILITY (Score >= 1.5 only)")
    print(SEP)

    for asset in ASSETS:
        for tf in TIMEFRAMES:
            key = (asset, tf)
            if key not in all_results:
                continue
            res, _, _, _ = all_results[key]

            for rsi_thresh in RSI_THRESHOLDS:
                trades = res[rsi_thresh]
                if len(trades) < 10:
                    continue

                df_t = pd.DataFrame(trades)
                sc_overall = calc_score(df_t['pnl_atr'].mean(), len(df_t))
                if sc_overall < 1.5:
                    continue

                print(f"\n  {asset} {tf} RSI<{rsi_thresh} "
                      f"(Score={sc_overall:+.2f})")
                print(f"  {'Year':<6} {'N':>4} {'Edge(ATR)':>10} {'WR%':>6} "
                      f"{'Score':>7} {'Net$':>10}")
                print(f"  {SUBSEP}")

                years = sorted(df_t['year'].unique())
                pos_years = 0
                total_years = 0
                for yr in years:
                    sub = df_t[df_t['year'] == yr]
                    n = len(sub)
                    if n < 1:
                        continue
                    total_years += 1
                    e = sub['pnl_atr'].mean()
                    wr = (sub['pnl_atr'] > 0).mean() * 100
                    sc = calc_score(e, n)
                    net = sub['net_usd'].sum()
                    tag = "+" if net > 0 else "-"
                    if net > 0:
                        pos_years += 1
                    print(f"  {yr:<6} {n:>4} {e:>+10.4f} {wr:>5.1f}% "
                          f"{sc:>+7.2f} {net:>+10.0f}  {tag}")

                if total_years > 0:
                    pct = pos_years / total_years * 100
                    print(f"\n  Positive years (net): "
                          f"{pos_years}/{total_years} ({pct:.0f}%)")

    # ══════════════════════════════════════════════════════════════
    # REPORT 3: SWAP IMPACT (Score >= 1.5 candidates)
    # ══════════════════════════════════════════════════════════════
    print()
    print(SEP)
    print("REPORT 3: SWAP IMPACT (Score >= 1.5 only)")
    print(SEP)

    for asset in ASSETS:
        info = ASSETS[asset]
        for tf in TIMEFRAMES:
            key = (asset, tf)
            if key not in all_results:
                continue
            res, _, _, _ = all_results[key]

            for rsi_thresh in RSI_THRESHOLDS:
                trades = res[rsi_thresh]
                if len(trades) < 10:
                    continue

                df_t = pd.DataFrame(trades)
                sc_overall = calc_score(df_t['pnl_atr'].mean(), len(df_t))
                if sc_overall < 1.5:
                    continue

                total_pnl = df_t['pnl_usd'].sum()
                total_swap = df_t['swap_usd'].sum()
                total_net = df_t['net_usd'].sum()

                if total_swap < 0:
                    swap_label = "INCOME"
                    swap_pct = (abs(total_swap) / abs(total_pnl) * 100
                                if total_pnl != 0 else 0)
                else:
                    swap_label = "COST"
                    swap_pct = (total_swap / total_pnl * 100
                                if total_pnl > 0 else float('inf'))

                print(f"\n  {asset} {tf} RSI<{rsi_thresh} "
                      f"(swap=${info['swap_per_day_usd']:+.2f}/day):")
                print(f"    Gross PnL:  ${total_pnl:>+14,.0f}")
                print(f"    Total Swap: ${total_swap:>+14,.0f} "
                      f"({swap_pct:.1f}% {swap_label})")
                print(f"    Net PnL:    ${total_net:>+14,.0f}")

    # ══════════════════════════════════════════════════════════════
    print()
    print(SEP)
    print("NOTES")
    print(SEP)
    print("  - Score >= 2.0 → implement candidate (Axiom 12)")
    print("  - SMA(200) H4 ≈ 33 market days ≠ SMA(200) Daily ≈ 10 months")
    print("  - SwpDir RECV = positive carry (USDJPY, USDCHF long)")
    print("  - Dollar PnL scale varies by lot convention — Score is "
          "comparable across assets")
    print("  - Swap counted per calendar night (not per bar)")
    print(f"  - Total runtime: {time.time() - t0:.1f}s")
    print(SEP)


if __name__ == '__main__':
    main()
