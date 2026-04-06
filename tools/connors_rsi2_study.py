"""
Connors RSI(2) Mean-Reversion Study -- Axiom 12 compliance.

Tests the exact Larry Connors strategy on daily data:
  - Filter: Close > SMA(200) (structural uptrend)
  - Entry:  RSI(2) < threshold (extreme oversold, panic dip)
  - Exit:   Close > SMA(5)   (quick mean-reversion exit)
  - Direction: LONG only

Parameters are 100% from published literature (NOT optimized):
  RSI period = 2, SMA filter = 200, RSI threshold = 5/10,
  Exit SMA = 5.

Measures: N signals, edge (ATR-normalized), WR%, Score,
holding days, estimated swap cost, yearly stability.

Usage:
  python tools/connors_rsi2_study.py
"""

import os
import sys
import numpy as np
import pandas as pd
from math import sqrt as msqrt

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')

# Assets to study (must have 5m data files)
ASSETS = {
    'SP500': {
        'files': ['SP500_5m_15Yea.csv', 'SP500_5m_5Yea.csv'],
        'spread_atr': 2.10,
        'swap_per_day_usd': 9.28,    # from config/instruments.py
        'point_value': 10.0,         # USD per point
    },
    'NDX': {
        'files': ['NDX_5m_15Yea.csv', 'NDX_5m_5Yea.csv'],
        'spread_atr': 0.41,
        'swap_per_day_usd': 35.62,
        'point_value': 1.0,
    },
    'GDAXI': {
        'files': ['GDAXI_5m_15Yea.csv', 'GDAXI_5m_5Yea.csv'],
        'spread_atr': 0.96,
        'swap_per_day_usd': 22.46,
        'point_value': 1.0,
    },
    'NI225': {
        'files': ['NI225_5m_15Yea.csv', 'NI225_5m_5Yea.csv'],
        'spread_atr': 1.73,
        'swap_per_day_usd': 10.0,    # estimated
        'point_value': 0.01,         # JPY conversion
    },
}

# Connors parameters (ALL from literature, zero optimization)
RSI_PERIOD = 2
SMA_FILTER = 200
SMA_EXIT = 5
RSI_THRESHOLDS = [5, 10, 15]    # test 3 levels from literature
ATR_PERIOD = 14                  # for normalization only

SEP = "=" * 80
SUBSEP = "-" * 80


def load_daily(asset_key):
    """Load 5m CSV and resample to daily OHLC."""
    info = ASSETS[asset_key]
    path = None
    for fname in info['files']:
        p = os.path.join(DATA_DIR, fname)
        if os.path.exists(p):
            path = p
            break
    if path is None:
        return None

    df = pd.read_csv(path)
    df['datetime'] = pd.to_datetime(
        df['Date'].astype(str) + ' ' + df['Time'])
    df = df.set_index('datetime').sort_index()
    df = df[df.index.dayofweek < 5]

    daily = df.resample('1D').agg({
        'Open': 'first', 'High': 'max',
        'Low': 'min', 'Close': 'last', 'Volume': 'sum'
    }).dropna(subset=['Open'])

    daily.columns = ['open', 'high', 'low', 'close', 'volume']
    return daily


def compute_rsi(close, period):
    """Wilder RSI (exponential)."""
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def compute_atr(daily, period):
    """ATR for normalization."""
    prev_close = daily['close'].shift(1)
    tr = pd.concat([
        daily['high'] - daily['low'],
        (daily['high'] - prev_close).abs(),
        (daily['low'] - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def score(edge, n):
    """Score = edge * sqrt(N)."""
    if n < 1 or np.isnan(edge):
        return 0.0
    return edge * msqrt(n)


def study_asset(asset_key):
    """Run full Connors RSI(2) study on one asset."""
    daily = load_daily(asset_key)
    if daily is None:
        print(f"  {asset_key}: data not found, skipping")
        return None

    info = ASSETS[asset_key]

    # Indicators
    rsi2 = compute_rsi(daily['close'], RSI_PERIOD)
    sma200 = daily['close'].rolling(SMA_FILTER).mean()
    sma5 = daily['close'].rolling(SMA_EXIT).mean()
    atr = compute_atr(daily, ATR_PERIOD)

    print(f"  {asset_key}: {len(daily)} daily bars "
          f"({daily.index[0].date()} to {daily.index[-1].date()})")

    results = {}

    for rsi_thresh in RSI_THRESHOLDS:
        # Entry: RSI(2) < threshold AND Close > SMA(200)
        entry_mask = (rsi2 < rsi_thresh) & (daily['close'] > sma200)
        entry_dates = daily.index[entry_mask]

        trades = []
        i = 0
        idx_list = daily.index.tolist()

        while i < len(idx_list):
            dt = idx_list[i]
            if dt not in entry_dates:
                i += 1
                continue

            # Entry on next day open (signal at close, enter next open)
            entry_idx = idx_list.index(dt)
            if entry_idx + 1 >= len(idx_list):
                break

            entry_dt = idx_list[entry_idx + 1]
            entry_price = daily.loc[entry_dt, 'open']
            entry_atr = atr.get(dt, np.nan)

            if np.isnan(entry_price) or np.isnan(entry_atr) or entry_atr <= 0:
                i += 1
                continue

            # Exit: Close > SMA(5) (check from entry day onwards)
            holding = 0
            exit_price = np.nan
            exit_dt = entry_dt

            for j in range(entry_idx + 1, len(idx_list)):
                exit_dt = idx_list[j]
                holding += 1
                c = daily.loc[exit_dt, 'close']
                s5 = sma5.get(exit_dt, np.nan)

                if not np.isnan(s5) and c > s5:
                    exit_price = c
                    break

                # Safety: max 20 days hold
                if holding >= 20:
                    exit_price = c
                    break

            if np.isnan(exit_price):
                i += 1
                continue

            pnl_pts = exit_price - entry_price
            pnl_atr = pnl_pts / entry_atr if entry_atr > 0 else 0

            # Swap cost estimate
            swap_total = info['swap_per_day_usd'] * holding
            pnl_usd = pnl_pts * info['point_value']
            swap_pct_of_pnl = (swap_total / abs(pnl_usd) * 100
                               if abs(pnl_usd) > 0 else 0)

            trades.append({
                'entry_date': entry_dt,
                'exit_date': exit_dt,
                'entry_price': entry_price,
                'exit_price': exit_price,
                'pnl_pts': pnl_pts,
                'pnl_atr': pnl_atr,
                'pnl_usd': pnl_usd,
                'holding': holding,
                'swap_usd': swap_total,
                'net_usd': pnl_usd - swap_total,
                'year': entry_dt.year,
                'rsi_at_signal': rsi2.get(dt, np.nan),
            })

            # Skip forward past exit to avoid overlapping trades
            i = idx_list.index(exit_dt) + 1

        results[rsi_thresh] = trades

    return results


def main():
    os.chdir(BASE_DIR)

    print(SEP)
    print("CONNORS RSI(2) MEAN-REVERSION STUDY -- Axiom 12")
    print(SEP)
    print(f"RSI period: {RSI_PERIOD}")
    print(f"SMA filter: {SMA_FILTER}")
    print(f"SMA exit: {SMA_EXIT}")
    print(f"RSI thresholds: {RSI_THRESHOLDS}")
    print(f"Parameters: ALL from published literature (zero optimization)")
    print()

    print("Loading data...")
    all_results = {}
    for asset in ASSETS:
        r = study_asset(asset)
        if r is not None:
            all_results[asset] = r
    print()

    # ==================================================================
    # REPORT 1: SUMMARY BY ASSET x RSI THRESHOLD
    # ==================================================================
    print(SEP)
    print("REPORT 1: EDGE SUMMARY (all from literature params)")
    print(SEP)

    header = (f"  {'Asset':<8} {'RSI<':<5} {'N':>5} {'Edge(ATR)':>10} "
              f"{'WR%':>6} {'Score':>7} {'AvgHold':>8} "
              f"{'AvgPnL$':>9} {'AvgSwap$':>9} {'Net$/tr':>9}")
    print(header)
    print(f"  {SUBSEP}")

    for asset in all_results:
        for rsi_thresh in RSI_THRESHOLDS:
            trades = all_results[asset][rsi_thresh]
            n = len(trades)
            if n < 5:
                print(f"  {asset:<8} {rsi_thresh:<5} {n:>5}  "
                      f"(insufficient data)")
                continue

            df_t = pd.DataFrame(trades)
            edge = df_t['pnl_atr'].mean()
            wr = (df_t['pnl_atr'] > 0).mean() * 100
            sc = score(edge, n)
            avg_hold = df_t['holding'].mean()
            avg_pnl = df_t['pnl_usd'].mean()
            avg_swap = df_t['swap_usd'].mean()
            avg_net = df_t['net_usd'].mean()

            flag = " ***" if sc >= 2.0 else " *" if sc >= 1.5 else ""
            print(f"  {asset:<8} {rsi_thresh:<5} {n:>5} {edge:>+10.4f} "
                  f"{wr:>5.1f}% {sc:>+7.2f} {avg_hold:>8.1f}d "
                  f"{avg_pnl:>+9.1f} {avg_swap:>9.1f} "
                  f"{avg_net:>+9.1f}{flag}")

    # ==================================================================
    # REPORT 2: YEARLY STABILITY (best candidates)
    # ==================================================================
    print()
    print(SEP)
    print("REPORT 2: YEARLY STABILITY")
    print(SEP)

    for asset in all_results:
        for rsi_thresh in RSI_THRESHOLDS:
            trades = all_results[asset][rsi_thresh]
            if len(trades) < 10:
                continue

            df_t = pd.DataFrame(trades)
            overall_score = score(df_t['pnl_atr'].mean(), len(df_t))
            if overall_score < 1.0:
                continue  # Skip weak candidates

            print(f"\n  {asset} RSI<{rsi_thresh} "
                  f"(overall Score={overall_score:+.2f})")
            print(f"  {'Year':<6} {'N':>4} {'Edge(ATR)':>10} {'WR%':>6} "
                  f"{'Score':>7} {'PnL$':>9} {'Swap$':>8} {'Net$':>9}")
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
                sc = score(e, n)
                pnl = sub['pnl_usd'].sum()
                swap = sub['swap_usd'].sum()
                net = sub['net_usd'].sum()
                tag = "+" if net > 0 else "-"
                if net > 0:
                    pos_years += 1
                print(f"  {yr:<6} {n:>4} {e:>+10.4f} {wr:>5.1f}% "
                      f"{sc:>+7.2f} {pnl:>+9.0f} {swap:>8.0f} "
                      f"{net:>+9.0f}  {tag}")

            if total_years > 0:
                pct = pos_years / total_years * 100
                print(f"\n  Positive years (net): {pos_years}/{total_years} "
                      f"({pct:.0f}%)")

    # ==================================================================
    # REPORT 3: HOLDING DISTRIBUTION
    # ==================================================================
    print()
    print(SEP)
    print("REPORT 3: HOLDING PERIOD DISTRIBUTION")
    print(SEP)

    for asset in all_results:
        for rsi_thresh in RSI_THRESHOLDS:
            trades = all_results[asset][rsi_thresh]
            if len(trades) < 10:
                continue
            df_t = pd.DataFrame(trades)
            overall_score = score(df_t['pnl_atr'].mean(), len(df_t))
            if overall_score < 1.0:
                continue

            print(f"\n  {asset} RSI<{rsi_thresh}:")
            hold = df_t['holding']
            for d in range(1, min(11, int(hold.max()) + 1)):
                cnt = (hold == d).sum()
                pct = cnt / len(df_t) * 100
                sub = df_t[df_t['holding'] == d]
                e = sub['pnl_atr'].mean() if len(sub) > 0 else 0
                bar = "#" * int(pct / 2)
                print(f"    {d:>2}d: {cnt:>4} ({pct:>5.1f}%) "
                      f"Edge={e:>+.4f}  {bar}")
            longer = (hold > 10).sum()
            if longer > 0:
                print(f"   >10d: {longer:>4} "
                      f"({longer / len(df_t) * 100:>5.1f}%)")
            print(f"    Median: {hold.median():.0f}d  "
                  f"Mean: {hold.mean():.1f}d  "
                  f"Max: {hold.max():.0f}d")

    # ==================================================================
    # REPORT 4: SWAP IMPACT ANALYSIS
    # ==================================================================
    print()
    print(SEP)
    print("REPORT 4: SWAP COST IMPACT")
    print(SEP)

    for asset in all_results:
        info = ASSETS[asset]
        for rsi_thresh in RSI_THRESHOLDS:
            trades = all_results[asset][rsi_thresh]
            if len(trades) < 10:
                continue
            df_t = pd.DataFrame(trades)
            overall_score = score(df_t['pnl_atr'].mean(), len(df_t))
            if overall_score < 1.0:
                continue

            total_pnl = df_t['pnl_usd'].sum()
            total_swap = df_t['swap_usd'].sum()
            total_net = df_t['net_usd'].sum()
            swap_pct = (total_swap / total_pnl * 100
                        if total_pnl > 0 else float('inf'))

            print(f"\n  {asset} RSI<{rsi_thresh} "
                  f"(swap=${info['swap_per_day_usd']:.2f}/day):")
            print(f"    Gross PnL:  ${total_pnl:>+12,.0f}")
            print(f"    Total Swap: ${total_swap:>12,.0f} "
                  f"({swap_pct:.1f}% of gross)")
            print(f"    Net PnL:    ${total_net:>+12,.0f}")
            winners = df_t[df_t['pnl_usd'] > 0]
            losers = df_t[df_t['pnl_usd'] <= 0]
            if len(winners) > 0:
                print(f"    Avg winner: ${winners['pnl_usd'].mean():>+,.0f} "
                      f"(swap ${winners['swap_usd'].mean():>,.0f})")
            if len(losers) > 0:
                print(f"    Avg loser:  ${losers['pnl_usd'].mean():>+,.0f} "
                      f"(swap ${losers['swap_usd'].mean():>,.0f})")

    # ==================================================================
    # SUMMARY
    # ==================================================================
    print()
    print(SEP)
    print("INTERPRETATION")
    print(SEP)
    print("- Score >= 2.0: implement candidate (Axiom 12)")
    print("- WR% > 60%: expected for mean-reversion dip-buying")
    print("- Holding 3-7 days: within Connors expected range")
    print("- Swap < 15% of gross PnL: acceptable for CFDs")
    print("- Positive years >= 70%: stable edge")
    print("- ALL parameters from literature: zero overfitting risk")
    print(SEP)


if __name__ == '__main__':
    main()
