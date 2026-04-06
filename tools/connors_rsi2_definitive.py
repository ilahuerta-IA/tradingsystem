"""
Connors RSI(2) — Definitive Study for the 2 candidates.

1. SP500 Daily RSI<10  (15Y, resampled from 5m)
2. EURUSD H4  RSI<10   (23Y, native H4 data)

All params from literature. Detailed yearly breakdown for BOTH.

Usage:
  python tools/connors_rsi2_definitive.py
"""

import os
import time
import numpy as np
import pandas as pd
from math import sqrt as msqrt

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')

# ── Candidates ─────────────────────────────────────────────────────
CANDIDATES = {
    'SP500_1D': {
        'file': 'SP500_5m_15Yea.csv',
        'native_tf': None,                # needs resample from 5m
        'target_tf': '1D',
        'swap_per_day_usd': 9.28,
        'point_value': 10.0,              # CFD $10/point
        'label': 'SP500 Daily',
    },
    'EURUSD_4h': {
        'file': 'EURUSD_4h_23Yea.csv',
        'native_tf': '4h',                # already H4
        'target_tf': '4h',
        'swap_per_day_usd': 6.5,
        'point_value': 100000.0,           # 100K lot
        'label': 'EURUSD H4',
    },
}

# ── Connors parameters (100% published) ───────────────────────────
RSI_PERIOD = 2
SMA_FILTER = 200
SMA_EXIT = 5
RSI_THRESHOLDS = [5, 10, 15]
ATR_PERIOD = 14
MAX_HOLD_DAYS = 20

SEP = "=" * 80
SUBSEP = "-" * 80


# ── Data loading ───────────────────────────────────────────────────

def load_data(cand):
    """Load and prepare data. Resample from 5m if needed, or use native H4."""
    path = os.path.join(DATA_DIR, cand['file'])
    if not os.path.exists(path):
        return None

    df = pd.read_csv(path)
    df['datetime'] = pd.to_datetime(
        df['Date'].astype(str) + ' ' + df['Time'])
    df = df.set_index('datetime').sort_index()
    df = df[df.index.dayofweek < 5]

    if cand['native_tf'] is None:
        # Resample 5m → target_tf
        r = df.resample(cand['target_tf']).agg({
            'Open': 'first', 'High': 'max',
            'Low': 'min', 'Close': 'last', 'Volume': 'sum'
        }).dropna(subset=['Open'])
        r.columns = ['open', 'high', 'low', 'close', 'volume']
        return r
    else:
        # Already in target timeframe
        df.columns = [c.lower() for c in df.columns]
        # drop non-OHLCV columns that survived
        for col in ['date', 'time']:
            if col in df.columns:
                df = df.drop(columns=[col])
        return df


# ── Indicators ─────────────────────────────────────────────────────

def compute_rsi(close, period):
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


# ── Trade simulation ──────────────────────────────────────────────

def run_trades(data, cand, rsi_thresh):
    """Simulate Connors RSI(2) trades."""
    rsi2 = compute_rsi(data['close'], RSI_PERIOD)
    sma200 = data['close'].rolling(SMA_FILTER).mean()
    sma5 = data['close'].rolling(SMA_EXIT).mean()
    atr = compute_atr(data, ATR_PERIOD)

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

        entry_dt = idx[i + 1]
        entry_price = data.at[entry_dt, 'open']
        entry_atr = atr.get(dt, np.nan)

        if np.isnan(entry_price) or np.isnan(entry_atr) or entry_atr <= 0:
            i += 1
            continue

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
        hold_days = max((exit_dt - entry_dt).days, 0)
        swap_total = cand['swap_per_day_usd'] * hold_days
        pnl_usd = pnl_pts * cand['point_value']

        trades.append({
            'entry_date': entry_dt,
            'exit_date': exit_dt,
            'pnl_pts': pnl_pts,
            'pnl_atr': pnl_atr,
            'pnl_usd': pnl_usd,
            'hold_days': hold_days,
            'swap_usd': swap_total,
            'net_usd': pnl_usd - swap_total,
            'year': entry_dt.year,
        })

        i = j + 1

    return trades


# ── Reporting helpers ──────────────────────────────────────────────

def print_summary(label, trades_by_thresh):
    """Print edge summary table."""
    print(f"\n  {label}:")
    print(f"  {'RSI<':<5} {'N':>5} {'Edge(ATR)':>10} {'WR%':>6} "
          f"{'Score':>7} {'AvgDays':>8} {'Net$/tr':>10} {'CumNet$':>12}")
    print(f"  {SUBSEP}")

    for rsi_thresh in RSI_THRESHOLDS:
        trades = trades_by_thresh[rsi_thresh]
        n = len(trades)
        if n < 5:
            print(f"  {rsi_thresh:<5} {n:>5}  (insufficient)")
            continue

        df_t = pd.DataFrame(trades)
        edge = df_t['pnl_atr'].mean()
        wr = (df_t['pnl_atr'] > 0).mean() * 100
        sc = calc_score(edge, n)
        avg_days = df_t['hold_days'].mean()
        avg_net = df_t['net_usd'].mean()
        cum_net = df_t['net_usd'].sum()

        flag = " ***" if sc >= 2.0 else " *" if sc >= 1.5 else ""
        print(f"  {rsi_thresh:<5} {n:>5} {edge:>+10.4f} {wr:>5.1f}% "
              f"{sc:>+7.2f} {avg_days:>7.1f}d {avg_net:>+10.1f} "
              f"{cum_net:>+12,.0f}{flag}")


def print_yearly(label, trades, cand):
    """Print detailed yearly breakdown."""
    if len(trades) < 5:
        return

    df_t = pd.DataFrame(trades)
    sc_overall = calc_score(df_t['pnl_atr'].mean(), len(df_t))

    print(f"\n  {label} (overall Score={sc_overall:+.2f}, "
          f"N={len(df_t)}, swap=${cand['swap_per_day_usd']:+.2f}/day)")
    print(f"  {'Year':<6} {'N':>4} {'Edge(ATR)':>10} {'WR%':>6} "
          f"{'Score':>7} {'GrossPnL$':>11} {'Swap$':>9} "
          f"{'Net$':>11} {'Net/Tr$':>9}")
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
        gross = sub['pnl_usd'].sum()
        swap = sub['swap_usd'].sum()
        net = sub['net_usd'].sum()
        net_per_tr = sub['net_usd'].mean()
        tag = "+" if net > 0 else "-"
        if net > 0:
            pos_years += 1
        print(f"  {yr:<6} {n:>4} {e:>+10.4f} {wr:>5.1f}% "
              f"{sc:>+7.2f} {gross:>+11,.0f} {swap:>9,.0f} "
              f"{net:>+11,.0f} {net_per_tr:>+9.0f}  {tag}")

    if total_years > 0:
        pct = pos_years / total_years * 100
        print(f"\n  Positive years (net): "
              f"{pos_years}/{total_years} ({pct:.0f}%)")

    # Cumulative stats
    total_gross = df_t['pnl_usd'].sum()
    total_swap = df_t['swap_usd'].sum()
    total_net = df_t['net_usd'].sum()
    swap_pct = (total_swap / total_gross * 100
                if total_gross > 0 else float('inf'))
    print(f"\n  Totals: Gross=${total_gross:+,.0f}  "
          f"Swap=${total_swap:,.0f} ({swap_pct:.1f}%)  "
          f"Net=${total_net:+,.0f}")


# ── Main ──────────────────────────────────────────────────────────

def main():
    os.chdir(BASE_DIR)
    t0 = time.time()

    print(SEP)
    print("CONNORS RSI(2) — DEFINITIVE STUDY")
    print(SEP)
    print(f"RSI period: {RSI_PERIOD}  |  SMA filter: {SMA_FILTER}  |  "
          f"SMA exit: {SMA_EXIT}")
    print(f"RSI thresholds: {RSI_THRESHOLDS}")
    print(f"Max hold: {MAX_HOLD_DAYS} calendar days")
    print(f"Parameters: ALL from published literature (zero optimization)")
    print()

    # ── Load data ──
    print("Loading data...")
    loaded = {}
    for key, cand in CANDIDATES.items():
        data = load_data(cand)
        if data is not None:
            loaded[key] = data
            print(f"  {cand['label']}: {len(data):,} bars "
                  f"({data.index[0].date()} to {data.index[-1].date()})")
        else:
            print(f"  {cand['label']}: NOT FOUND ({cand['file']})")
    print(f"  Loaded in {time.time() - t0:.1f}s")
    print()

    # ── Run trades ──
    print("Running trade simulations...")
    all_results = {}
    for key, cand in CANDIDATES.items():
        if key not in loaded:
            continue
        data = loaded[key]
        results = {}
        for rsi_thresh in RSI_THRESHOLDS:
            t1 = time.time()
            trades = run_trades(data, cand, rsi_thresh)
            results[rsi_thresh] = trades
            elapsed = time.time() - t1
            print(f"  {cand['label']} RSI<{rsi_thresh}: "
                  f"{len(trades)} trades [{elapsed:.1f}s]")
        all_results[key] = results
    print()

    # ══════════════════════════════════════════════════════════════
    # REPORT 1: EDGE SUMMARY
    # ══════════════════════════════════════════════════════════════
    print(SEP)
    print("REPORT 1: EDGE SUMMARY")
    print(SEP)

    for key, cand in CANDIDATES.items():
        if key in all_results:
            print_summary(cand['label'], all_results[key])

    # ══════════════════════════════════════════════════════════════
    # REPORT 2: YEARLY DETAIL — ALL THRESHOLDS
    # ══════════════════════════════════════════════════════════════
    print()
    print(SEP)
    print("REPORT 2: YEARLY BREAKDOWN (all thresholds)")
    print(SEP)

    for key, cand in CANDIDATES.items():
        if key not in all_results:
            continue
        for rsi_thresh in RSI_THRESHOLDS:
            trades = all_results[key][rsi_thresh]
            label = f"{cand['label']} RSI<{rsi_thresh}"
            print_yearly(label, trades, cand)

    # ══════════════════════════════════════════════════════════════
    # REPORT 3: HOLDING DISTRIBUTION (RSI<10 only)
    # ══════════════════════════════════════════════════════════════
    print()
    print(SEP)
    print("REPORT 3: HOLDING DISTRIBUTION (RSI<10)")
    print(SEP)

    for key, cand in CANDIDATES.items():
        if key not in all_results:
            continue
        trades = all_results[key][10]
        if len(trades) < 10:
            continue

        df_t = pd.DataFrame(trades)
        hold = df_t['hold_days']

        print(f"\n  {cand['label']} RSI<10:")
        max_d = min(15, int(hold.max()) + 1)
        for d in range(0, max_d):
            cnt = (hold == d).sum()
            pct = cnt / len(df_t) * 100
            sub = df_t[df_t['hold_days'] == d]
            e = sub['pnl_atr'].mean() if len(sub) > 0 else 0
            bar = "#" * int(pct / 2)
            print(f"    {d:>2}d: {cnt:>4} ({pct:>5.1f}%) "
                  f"Edge={e:>+.4f}  {bar}")
        longer = (hold >= max_d).sum()
        if longer > 0:
            print(f"  >={max_d:>2}d: {longer:>4} "
                  f"({longer / len(df_t) * 100:>5.1f}%)")
        print(f"    Median: {hold.median():.0f}d  "
              f"Mean: {hold.mean():.1f}d  "
              f"Max: {hold.max():.0f}d")

    # ══════════════════════════════════════════════════════════════
    # REPORT 4: DECADE COMPARISON (EURUSD only)
    # ══════════════════════════════════════════════════════════════
    if 'EURUSD_4h' in all_results:
        print()
        print(SEP)
        print("REPORT 4: DECADE COMPARISON — EURUSD H4 RSI<10")
        print(SEP)

        trades = all_results['EURUSD_4h'][10]
        if len(trades) >= 10:
            df_t = pd.DataFrame(trades)
            decades = [
                ('2003-2009', 2003, 2009),
                ('2010-2016', 2010, 2016),
                ('2017-2023', 2017, 2023),
                ('2024-2026', 2024, 2026),
            ]
            print(f"\n  {'Period':<12} {'N':>5} {'Edge(ATR)':>10} "
                  f"{'WR%':>6} {'Score':>7} {'Net$':>12} {'Net/Yr$':>10}")
            print(f"  {SUBSEP}")

            for label, y1, y2 in decades:
                sub = df_t[(df_t['year'] >= y1) & (df_t['year'] <= y2)]
                n = len(sub)
                if n < 3:
                    print(f"  {label:<12} {n:>5}  (insufficient)")
                    continue
                e = sub['pnl_atr'].mean()
                wr = (sub['pnl_atr'] > 0).mean() * 100
                sc = calc_score(e, n)
                net = sub['net_usd'].sum()
                yrs = y2 - y1 + 1
                net_yr = net / yrs
                print(f"  {label:<12} {n:>5} {e:>+10.4f} {wr:>5.1f}% "
                      f"{sc:>+7.2f} {net:>+12,.0f} {net_yr:>+10,.0f}")

    # ── Footer ──
    print()
    print(SEP)
    print("NOTES")
    print(SEP)
    print("  - Score >= 2.0 → implement candidate (Axiom 12)")
    print("  - SP500 Daily: SMA(200) ≈ 10 month trend filter (Connors original)")
    print("  - EURUSD H4: SMA(200) ≈ 33 market days (~7 weeks trend filter)")
    print("  - All parameters from published literature, zero optimization")
    print("  - Swap counted per calendar night (not per bar)")
    print(f"  - Total runtime: {time.time() - t0:.1f}s")
    print(SEP)


if __name__ == '__main__':
    main()
