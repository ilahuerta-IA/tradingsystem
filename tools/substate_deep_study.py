"""
Comprehensive Sub-State & Transition Study

Opens ALL promising research avenues for the momentum stock strategy:

VIA 1 — PULLBACK IN CALM TREND
  CALM_UP + Mom1M < 0 showed high edge in 4-state study for several stocks.
  Is this a real "buy the dip in trend" signal, or small sample noise?
  Deep forward curves + yearly consistency.

VIA 2 — TRANSITION DETECTION (1M CROSS)
  Detect the exact moment Mom1M crosses from negative to positive.
  Does buying at the 1M cross yield concentrated edge?
  Test: edge in 5 days AFTER cross vs 5 days BEFORE.

VIA 3 — OPTIMAL SHORT-TERM LOOKBACK
  Compare Mom1M (21d), Mom2M (42d), Mom3M (63d) as sub-filters.
  Which lookback best discriminates high-edge vs low-edge days?

VIA 4 — STOCK-LEVEL REGIME vs NDX-LEVEL
  Instead of using NDX state, use the STOCK'S OWN regime classification.
  Hypothesis: stock's own CALM_UP is more predictive than NDX's.

VIA 5 — ATR REGIME INTERACTION
  Within CALM_UP: does low vs high stock ATR matter?
  Hypothesis: low ATR + trend = best edge (clean moves).

VIA 6 — YEARLY BREAKDOWN OF EVERY COMBINATION
  Full year-by-year consistency for the top findings.

Data: yfinance daily. Top 20 NDX stocks.

Usage:
  python tools/substate_deep_study.py
  python tools/substate_deep_study.py --stocks NVDA AVGO MU AMAT
  python tools/substate_deep_study.py --years 10
"""

import argparse
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

try:
    import yfinance as yf
except ImportError:
    print("ERROR: yfinance not installed. Run: pip install yfinance")
    sys.exit(1)


# ====================================================================
# CONFIG
# ====================================================================

DEFAULT_STOCKS = [
    'NVDA', 'AVGO', 'MU', 'AMAT', 'APP', 'PLTR',
    'KLAC', 'ASML', 'GOOGL', 'AMD', 'LRCX', 'ADI',
    'NFLX', 'META', 'TSLA', 'CRWD', 'PANW', 'MSFT', 'AMZN', 'AAPL',
]

NDX_TICKER = 'QQQ'

SWAP_LONG_DAILY = 0.0002
COMMISSION_PER_ORDER = 0.02

MOM_LONG_DAYS = 252
ATR_PERIOD = 24
ATR_RATIO_THRESHOLD = 1.0

# Multiple short-term lookbacks to test (Via 3)
SHORT_LOOKBACKS = [10, 21, 42, 63]  # ~2wk, 1M, 2M, 3M

FORWARD_DAYS = [1, 2, 3, 5, 10, 20]

MIN_YEARS = 3
MIN_BARS = MIN_YEARS * 252
DOWNLOAD_YEARS = 10


# ====================================================================
# DATA
# ====================================================================

def download_data(tickers, years=DOWNLOAD_YEARS):
    """Download daily OHLCV from yfinance."""
    end = datetime.now()
    start = end - timedelta(days=years * 365)
    print(f"\nDownloading data ({start.strftime('%Y-%m-%d')} to "
          f"{end.strftime('%Y-%m-%d')})...")
    all_data = {}
    for ticker in tickers:
        try:
            df = yf.download(ticker, start=start, end=end, interval="1d",
                             auto_adjust=True, progress=False)
            if df is not None and len(df) >= MIN_BARS:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                all_data[ticker] = df
                print(f"  {ticker}: {len(df)} bars OK")
            else:
                n = len(df) if df is not None else 0
                print(f"  {ticker}: SKIP ({n} bars < {MIN_BARS})")
        except Exception as e:
            print(f"  {ticker}: ERROR ({str(e)[:50]})")
    return all_data


def compute_features(df, extra_lookbacks=True):
    """Add all momentum variants, ATR, forward returns."""
    close = df['Close'].copy()
    high = df['High'].copy()
    low = df['Low'].copy()
    df = df.copy()

    # Mom 12M
    df['mom12'] = close / close.shift(MOM_LONG_DAYS) - 1

    # Multiple short-term lookbacks
    for lb in SHORT_LOOKBACKS:
        df[f'mom_{lb}d'] = close / close.shift(lb) - 1

    # ATR
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    df['atr'] = tr.rolling(ATR_PERIOD).mean()
    df['atr_pct'] = df['atr'] / close * 100
    df['atr_mean250'] = df['atr'].rolling(250).mean()
    df['atr_ratio'] = df['atr'] / df['atr_mean250']

    # Return normalized by ATR
    df['ret_atr'] = (close - close.shift(1)) / df['atr']

    # Cost
    df['cost_1d'] = (SWAP_LONG_DAILY * close + 2 * COMMISSION_PER_ORDER)
    df['cost_atr_1d'] = df['cost_1d'] / df['atr'] * 100

    # Forward returns (ATR-normalized)
    for fwd in FORWARD_DAYS:
        df[f'fwd_{fwd}d'] = (close.shift(-fwd) - close) / df['atr']

    # 4-state regime (for both NDX and stock-level)
    mom12_pos = df['mom12'] > 0
    atr_high = df['atr_ratio'] >= ATR_RATIO_THRESHOLD
    df['regime'] = 'UNKNOWN'
    df.loc[mom12_pos & ~atr_high, 'regime'] = 'CALM_UP'
    df.loc[mom12_pos & atr_high, 'regime'] = 'HOT_UP'
    df.loc[~mom12_pos & atr_high, 'regime'] = 'CRASH'
    df.loc[~mom12_pos & ~atr_high, 'regime'] = 'REBOUND'

    # 1M transition detection: did mom_21d just cross zero?
    mom1 = df['mom_21d']
    df['mom1_prev'] = mom1.shift(1)
    df['mom1_cross_up'] = (mom1 > 0) & (df['mom1_prev'] <= 0)
    df['mom1_cross_dn'] = (mom1 < 0) & (df['mom1_prev'] >= 0)

    # Days since last 1M cross up
    cross_up_dates = df.index[df['mom1_cross_up']]
    df['days_since_cross_up'] = np.nan
    for d in cross_up_dates:
        mask = (df.index >= d) & (df.index < d + pd.Timedelta(days=60))
        days = (df.index[mask] - d).days
        df.loc[mask, 'days_since_cross_up'] = days

    req = ['mom12', 'atr', 'atr_ratio'] + [f'mom_{lb}d' for lb in SHORT_LOOKBACKS]
    return df.dropna(subset=req)


# ====================================================================
# VIA 1: PULLBACK IN CALM TREND
# ====================================================================

def via1_pullback_calm(stock_df, ndx_regimes, ticker):
    """Deep analysis of pullback (1M<0) within CALM_UP."""
    df = compute_features(stock_df)
    ndx_aligned = ndx_regimes.reindex(df.index)
    df['ndx_regime'] = ndx_aligned['regime'].fillna('UNKNOWN')

    # NDX CALM_UP + stock long
    base = df[(df['ndx_regime'] == 'CALM_UP') & (df['mom12'] > 0)]
    if len(base) < 100:
        return None

    mom1 = base['mom_21d']
    pullback = base[mom1 < 0]
    momentum = base[mom1 >= 0]

    if len(pullback) < 30 or len(momentum) < 30:
        return None

    print(f"\n  VIA 1 — PULLBACK IN CALM TREND: {ticker}")
    print(f"  CALM_UP + Stock Long: {len(base)} days")
    print(f"    1M >= 0 (momentum): {len(momentum)} days ({len(momentum)/len(base)*100:.0f}%)")
    print(f"    1M < 0  (pullback): {len(pullback)} days ({len(pullback)/len(base)*100:.0f}%)")

    print(f"\n  {'fwd':>5} {'Momentum':>10} {'MomWR':>7} {'Pullback':>10} "
          f"{'PbWR':>7} {'PB/Mom':>8}")
    print(f"  {'-' * 55}")

    results = {}
    for fwd in FORWARD_DAYS:
        col = f'fwd_{fwd}d'
        mom_e = momentum[col].dropna()
        pb_e = pullback[col].dropna()

        if len(mom_e) < 20 or len(pb_e) < 20:
            continue

        m_edge = mom_e.mean()
        p_edge = pb_e.mean()
        m_wr = (mom_e > 0).mean() * 100
        p_wr = (pb_e > 0).mean() * 100
        ratio = p_edge / m_edge if abs(m_edge) > 1e-6 else 0

        print(f"  {fwd:>4}d {m_edge:>+10.4f} {m_wr:>6.1f}% {p_edge:>+10.4f} "
              f"{p_wr:>6.1f}% {ratio:>7.1f}x")

        results[fwd] = {'mom': m_edge, 'pb': p_edge, 'ratio': ratio}

    # Yearly consistency of pullback edge
    pb_yr = pullback.copy()
    pb_yr['year'] = pb_yr.index.year
    yearly = pb_yr.groupby('year').agg(
        N=('fwd_1d', 'count'),
        Edge=('fwd_1d', 'mean'),
        WR=('fwd_1d', lambda x: (x > 0).mean() * 100),
    )
    yearly = yearly[yearly['N'] >= 10]
    pos = (yearly['Edge'] > 0).sum()
    print(f"\n  Pullback yearly: {pos}/{len(yearly)} positive years")
    for year, row in yearly.iterrows():
        mk = '✓' if row['Edge'] > 0 else '✗'
        print(f"    {year}: N={int(row['N']):>3} Edge={row['Edge']:>+.4f} WR={row['WR']:>5.1f}% {mk}")

    return results


# ====================================================================
# VIA 2: TRANSITION DETECTION (1M CROSS)
# ====================================================================

def via2_transition(stock_df, ndx_regimes, ticker):
    """Measure edge around the 1M cross-up moment within bullish regime."""
    df = compute_features(stock_df)
    ndx_aligned = ndx_regimes.reindex(df.index)
    df['ndx_regime'] = ndx_aligned['regime'].fillna('UNKNOWN')

    # Within bullish NDX (CALM or HOT) + stock long
    bullish = df[((df['ndx_regime'] == 'CALM_UP') | (df['ndx_regime'] == 'HOT_UP'))
                 & (df['mom12'] > 0)]

    crosses = bullish[bullish['mom1_cross_up']]
    if len(crosses) < 10:
        return None

    print(f"\n  VIA 2 — 1M CROSS-UP TRANSITIONS: {ticker}")
    print(f"  Bullish regime days: {len(bullish)}")
    print(f"  1M cross-up events: {len(crosses)}")

    # Edge in windows around cross
    # Days 0-5 after cross, 0-10, 0-20
    print(f"\n  Window after cross → forward return:")
    print(f"  {'Window':>10} {'N':>5} {'Edge/d':>9} {'WR%':>7} {'vs ALL':>8}")
    print(f"  {'-' * 45}")

    all_edge = bullish['fwd_1d'].mean()
    windows = [(0, 5), (0, 10), (0, 20), (5, 15), (10, 20)]

    results = {}
    for w_start, w_end in windows:
        mask = (bullish['days_since_cross_up'] >= w_start) & \
               (bullish['days_since_cross_up'] < w_end)
        window_data = bullish[mask]

        if len(window_data) < 20:
            continue

        edge = window_data['fwd_1d'].mean()
        wr = (window_data['fwd_1d'] > 0).mean() * 100
        ratio = edge / all_edge if abs(all_edge) > 1e-6 else 0

        label = f"D+{w_start}-{w_end}"
        print(f"  {label:>10} {len(window_data):>5} {edge:>+9.4f} {wr:>6.1f}% "
              f"{ratio:>7.1f}x")

        results[label] = {'edge': edge, 'wr': wr, 'n': len(window_data)}

    # Also test: BEFORE cross (last 5 days of 1M<0)
    pre_cross = bullish[(bullish['mom_21d'] < 0) &
                        (bullish['mom_21d'].shift(-5) > 0)]  # approx before cross
    if len(pre_cross) >= 15:
        edge = pre_cross['fwd_1d'].mean()
        wr = (pre_cross['fwd_1d'] > 0).mean() * 100
        print(f"  {'PRE-cross':>10} {len(pre_cross):>5} {edge:>+9.4f} "
              f"{wr:>6.1f}%")

    return results


# ====================================================================
# VIA 3: OPTIMAL SHORT-TERM LOOKBACK
# ====================================================================

def via3_lookback(stock_df, ndx_regimes, ticker):
    """Compare different short-term momentum lookbacks as sub-filters."""
    df = compute_features(stock_df)
    ndx_aligned = ndx_regimes.reindex(df.index)
    df['ndx_regime'] = ndx_aligned['regime'].fillna('UNKNOWN')

    calm_long = df[(df['ndx_regime'] == 'CALM_UP') & (df['mom12'] > 0)]
    if len(calm_long) < 100:
        return None

    print(f"\n  VIA 3 — OPTIMAL LOOKBACK: {ticker}")
    print(f"  CALM_UP + Stock Long: {len(calm_long)} days")
    print(f"\n  Within CALM_UP: which short-term filter best separates edge?")
    print(f"  {'Lookback':>10} {'Pos%':>6} {'PosEdge':>9} {'NegEdge':>9} "
          f"{'Spread':>9} {'PosWR':>7} {'NegWR':>7}")
    print(f"  {'-' * 60}")

    results = {}
    for lb in SHORT_LOOKBACKS:
        col = f'mom_{lb}d'
        pos = calm_long[calm_long[col] >= 0]
        neg = calm_long[calm_long[col] < 0]

        if len(pos) < 30 or len(neg) < 30:
            continue

        pos_pct = len(pos) / len(calm_long) * 100
        pos_edge = pos['fwd_1d'].mean()
        neg_edge = neg['fwd_1d'].mean()
        spread = pos_edge - neg_edge
        pos_wr = (pos['fwd_1d'] > 0).mean() * 100
        neg_wr = (neg['fwd_1d'] > 0).mean() * 100

        label = f"Mom{lb}d"
        print(f"  {label:>10} {pos_pct:>5.0f}% {pos_edge:>+9.4f} "
              f"{neg_edge:>+9.4f} {spread:>+9.4f} {pos_wr:>6.1f}% {neg_wr:>6.1f}%")

        results[lb] = {
            'pos_edge': pos_edge, 'neg_edge': neg_edge,
            'spread': spread, 'pos_wr': pos_wr, 'neg_wr': neg_wr,
            'pos_pct': pos_pct
        }

    # Also test: fwd_10d and fwd_20d for each lookback
    print(f"\n  Forward 10d edge by lookback filter:")
    print(f"  {'Lookback':>10} {'Pos fwd10':>11} {'Neg fwd10':>11} {'Spread':>9}")
    print(f"  {'-' * 45}")
    for lb in SHORT_LOOKBACKS:
        col = f'mom_{lb}d'
        pos = calm_long[calm_long[col] >= 0]
        neg = calm_long[calm_long[col] < 0]
        if len(pos) < 30 or len(neg) < 30:
            continue
        p10 = pos['fwd_10d'].dropna().mean()
        n10 = neg['fwd_10d'].dropna().mean()
        label = f"Mom{lb}d"
        print(f"  {label:>10} {p10:>+11.4f} {n10:>+11.4f} {p10-n10:>+9.4f}")

    return results


# ====================================================================
# VIA 4: STOCK-LEVEL REGIME vs NDX-LEVEL
# ====================================================================

def via4_stock_vs_ndx(stock_df, ndx_regimes, ticker):
    """Compare: using NDX regime vs stock's own regime classification."""
    df = compute_features(stock_df)
    ndx_aligned = ndx_regimes.reindex(df.index)
    df['ndx_regime'] = ndx_aligned['regime'].fillna('UNKNOWN')

    # Stock's own regime is already in df['regime'] from compute_features
    stock_long = df[df['mom12'] > 0]
    if len(stock_long) < 200:
        return None

    print(f"\n  VIA 4 — STOCK REGIME vs NDX REGIME: {ticker}")

    # NDX-based classification
    print(f"\n  A) Using NDX regime:")
    print(f"  {'NDX Regime':<12} {'N':>6} {'Edge/d':>9} {'WR%':>7} {'Fwd10d':>9}")
    print(f"  {'-' * 48}")

    results = {}
    for regime in ['CALM_UP', 'HOT_UP', 'CRASH', 'REBOUND']:
        sub = stock_long[stock_long['ndx_regime'] == regime]
        if len(sub) < 30:
            continue
        edge = sub['fwd_1d'].mean()
        wr = (sub['fwd_1d'] > 0).mean() * 100
        f10 = sub['fwd_10d'].dropna().mean()
        print(f"  {regime:<12} {len(sub):>6} {edge:>+9.4f} {wr:>6.1f}% {f10:>+9.4f}")
        results[f'ndx_{regime}'] = edge

    # Stock-based classification
    print(f"\n  B) Using STOCK's OWN regime:")
    print(f"  {'Stock Regime':<12} {'N':>6} {'Edge/d':>9} {'WR%':>7} {'Fwd10d':>9}")
    print(f"  {'-' * 48}")

    for regime in ['CALM_UP', 'HOT_UP', 'CRASH', 'REBOUND']:
        sub = stock_long[stock_long['regime'] == regime]
        if len(sub) < 30:
            continue
        edge = sub['fwd_1d'].mean()
        wr = (sub['fwd_1d'] > 0).mean() * 100
        f10 = sub['fwd_10d'].dropna().mean()
        print(f"  {regime:<12} {len(sub):>6} {edge:>+9.4f} {wr:>6.1f}% {f10:>+9.4f}")
        results[f'stock_{regime}'] = edge

    # Combined: stock CALM_UP + NDX CALM_UP vs stock CALM_UP alone
    both_calm = stock_long[(stock_long['regime'] == 'CALM_UP') &
                           (stock_long['ndx_regime'] == 'CALM_UP')]
    stock_calm = stock_long[stock_long['regime'] == 'CALM_UP']

    if len(both_calm) >= 30 and len(stock_calm) >= 30:
        e_both = both_calm['fwd_1d'].mean()
        e_stock = stock_calm['fwd_1d'].mean()
        print(f"\n  C) Combined:")
        print(f"    Stock CALM only:       N={len(stock_calm):>5} Edge={e_stock:>+.4f}")
        print(f"    Stock+NDX CALM:        N={len(both_calm):>5} Edge={e_both:>+.4f}")
        results['both_calm'] = e_both
        results['stock_calm_only'] = e_stock

    return results


# ====================================================================
# VIA 5: ATR INTERACTION WITHIN CALM_UP
# ====================================================================

def via5_atr_interaction(stock_df, ndx_regimes, ticker):
    """Within CALM_UP: does stock's own ATR level matter?"""
    df = compute_features(stock_df)
    ndx_aligned = ndx_regimes.reindex(df.index)
    df['ndx_regime'] = ndx_aligned['regime'].fillna('UNKNOWN')

    calm_long = df[(df['ndx_regime'] == 'CALM_UP') & (df['mom12'] > 0)]
    if len(calm_long) < 100:
        return None

    print(f"\n  VIA 5 — ATR INTERACTION IN CALM_UP: {ticker}")

    # Split stock ATR into terciles within CALM_UP
    atr_q = calm_long['atr_ratio'].quantile([0.33, 0.67])
    low_atr = calm_long[calm_long['atr_ratio'] < atr_q[0.33]]
    mid_atr = calm_long[(calm_long['atr_ratio'] >= atr_q[0.33]) &
                        (calm_long['atr_ratio'] < atr_q[0.67])]
    high_atr = calm_long[calm_long['atr_ratio'] >= atr_q[0.67]]

    print(f"  Stock ATR terciles within CALM_UP (thresholds: "
          f"{atr_q[0.33]:.2f}x / {atr_q[0.67]:.2f}x):")
    print(f"  {'Tercile':>10} {'N':>6} {'Edge/d':>9} {'WR%':>7} "
          f"{'Fwd10d':>9} {'C/ATR':>7}")
    print(f"  {'-' * 55}")

    results = {}
    for label, sub in [('LOW ATR', low_atr), ('MID ATR', mid_atr), ('HIGH ATR', high_atr)]:
        if len(sub) < 20:
            continue
        edge = sub['fwd_1d'].mean()
        wr = (sub['fwd_1d'] > 0).mean() * 100
        f10 = sub['fwd_10d'].dropna().mean()
        cost = sub['cost_atr_1d'].median()
        print(f"  {label:>10} {len(sub):>6} {edge:>+9.4f} {wr:>6.1f}% "
              f"{f10:>+9.4f} {cost:>6.1f}%")
        results[label] = {'edge': edge, 'wr': wr, 'fwd10': f10, 'cost': cost}

    return results


# ====================================================================
# VIA 6: YEARLY CONSISTENCY FOR TOP FINDINGS
# ====================================================================

def via6_yearly(stock_df, ndx_regimes, ticker):
    """Full yearly breakdown of the key combinations."""
    df = compute_features(stock_df)
    ndx_aligned = ndx_regimes.reindex(df.index)
    df['ndx_regime'] = ndx_aligned['regime'].fillna('UNKNOWN')

    stock_long = df[df['mom12'] > 0]

    combos = {
        'All Long':
            stock_long,
        'NDX CALM + Long':
            stock_long[stock_long['ndx_regime'] == 'CALM_UP'],
        'Stock CALM + Long':
            stock_long[stock_long['regime'] == 'CALM_UP'],
        'Stock CALM + 1M↑':
            stock_long[(stock_long['regime'] == 'CALM_UP') &
                       (stock_long['mom_21d'] >= 0)],
        'Stock CALM + 1M↓':
            stock_long[(stock_long['regime'] == 'CALM_UP') &
                       (stock_long['mom_21d'] < 0)],
    }

    print(f"\n  VIA 6 — YEARLY CONSISTENCY: {ticker}")

    results = {}
    for label, sub in combos.items():
        if len(sub) < 50:
            continue

        sub_yr = sub.copy()
        sub_yr['year'] = sub_yr.index.year
        yearly = sub_yr.groupby('year').agg(
            N=('fwd_1d', 'count'),
            Edge=('fwd_1d', 'mean'),
            WR=('fwd_1d', lambda x: (x > 0).mean() * 100),
        )
        yearly = yearly[yearly['N'] >= 15]
        pos = (yearly['Edge'] > 0).sum()
        total = len(yearly)

        print(f"\n  {label}: {pos}/{total} positive years "
              f"(avg edge: {sub['fwd_1d'].mean():+.4f})")

        for year, row in yearly.iterrows():
            mk = '✓' if row['Edge'] > 0 else '✗'
            print(f"    {year}: N={int(row['N']):>4} "
                  f"Edge={row['Edge']:>+.4f} WR={row['WR']:>5.1f}% {mk}")

        results[label] = {'pos_years': pos, 'total_years': total,
                          'avg_edge': sub['fwd_1d'].mean()}

    return results


# ====================================================================
# GLOBAL CROSS-STOCK SUMMARIES
# ====================================================================

def print_via1_summary(all_via1):
    """Pullback summary across stocks."""
    print(f"\n{'=' * 90}")
    print(f"CROSS-STOCK SUMMARY — VIA 1: PULLBACK IN CALM TREND")
    print(f"{'=' * 90}")

    print(f"\n  {'Ticker':<8} {'PB 1d':>8} {'Mom 1d':>8} {'PB/Mom':>8} "
          f"{'PB 10d':>8} {'Mom 10d':>8} {'PB/M 10d':>8}")
    print(f"  {'-' * 58}")

    pb_better_1d = 0
    pb_better_10d = 0
    total = 0

    for ticker, res in sorted(all_via1.items()):
        if not res:
            continue
        total += 1
        r1 = res.get(1, {})
        r10 = res.get(10, {})

        pb1 = r1.get('pb', 0)
        m1 = r1.get('mom', 0)
        rat1 = r1.get('ratio', 0)
        pb10 = r10.get('pb', 0)
        m10 = r10.get('mom', 0)
        rat10 = pb10 / m10 if abs(m10) > 1e-6 else 0

        if pb1 > m1:
            pb_better_1d += 1
        if pb10 > m10:
            pb_better_10d += 1

        print(f"  {ticker:<8} {pb1:>+8.4f} {m1:>+8.4f} {rat1:>7.1f}x "
              f"{pb10:>+8.4f} {m10:>+8.4f} {rat10:>7.1f}x")

    print(f"\n  Pullback > Momentum at 1d:  {pb_better_1d}/{total} stocks")
    print(f"  Pullback > Momentum at 10d: {pb_better_10d}/{total} stocks")


def print_via3_summary(all_via3):
    """Lookback summary across stocks."""
    print(f"\n{'=' * 90}")
    print(f"CROSS-STOCK SUMMARY — VIA 3: OPTIMAL LOOKBACK")
    print(f"{'=' * 90}")

    # Aggregate spread (pos_edge - neg_edge) per lookback
    lb_spreads = {lb: [] for lb in SHORT_LOOKBACKS}
    for ticker, res in all_via3.items():
        if not res:
            continue
        for lb, data in res.items():
            lb_spreads[lb].append(data['spread'])

    print(f"\n  Which short-term lookback best separates high/low edge days?")
    print(f"  {'Lookback':>10} {'Avg Spread':>12} {'Stocks+':>9} {'Best for':>10}")
    print(f"  {'-' * 45}")

    best_lb = None
    best_spread = -999
    for lb in SHORT_LOOKBACKS:
        spreads = lb_spreads[lb]
        if not spreads:
            continue
        avg = np.mean(spreads)
        pos = sum(1 for s in spreads if s > 0)
        print(f"  Mom{lb:>2}d    {avg:>+12.4f}    {pos}/{len(spreads)}")
        if avg > best_spread:
            best_spread = avg
            best_lb = lb

    if best_lb:
        print(f"\n  → Best lookback: Mom{best_lb}d (avg spread: {best_spread:+.4f})")


def print_via4_summary(all_via4):
    """Stock vs NDX regime summary."""
    print(f"\n{'=' * 90}")
    print(f"CROSS-STOCK SUMMARY — VIA 4: STOCK REGIME vs NDX REGIME")
    print(f"{'=' * 90}")

    print(f"\n  CALM_UP edge comparison:")
    print(f"  {'Ticker':<8} {'NDX CALM':>10} {'Stock CALM':>11} {'Both':>10} {'Best':>12}")
    print(f"  {'-' * 55}")

    ndx_wins = 0
    stock_wins = 0
    for ticker, res in sorted(all_via4.items()):
        if not res:
            continue
        n_calm = res.get('ndx_CALM_UP', 0)
        s_calm = res.get('stock_CALM_UP', 0)
        b_calm = res.get('both_calm', 0)

        best = 'NDX' if n_calm > s_calm else 'STOCK'
        if b_calm > max(n_calm, s_calm):
            best = 'BOTH'

        if n_calm > s_calm:
            ndx_wins += 1
        else:
            stock_wins += 1

        print(f"  {ticker:<8} {n_calm:>+10.4f} {s_calm:>+11.4f} "
              f"{b_calm:>+10.4f} {best:>12}")

    print(f"\n  NDX CALM wins: {ndx_wins} | Stock CALM wins: {stock_wins}")


def print_via5_summary(all_via5):
    """ATR interaction summary."""
    print(f"\n{'=' * 90}")
    print(f"CROSS-STOCK SUMMARY — VIA 5: ATR INTERACTION IN CALM_UP")
    print(f"{'=' * 90}")

    low_edges = []
    mid_edges = []
    high_edges = []

    for ticker, res in all_via5.items():
        if not res:
            continue
        if 'LOW ATR' in res:
            low_edges.append(res['LOW ATR']['edge'])
        if 'MID ATR' in res:
            mid_edges.append(res['MID ATR']['edge'])
        if 'HIGH ATR' in res:
            high_edges.append(res['HIGH ATR']['edge'])

    print(f"\n  ATR Tercile    Avg Edge/d   Stocks   Interpretation")
    print(f"  {'-' * 55}")
    if low_edges:
        print(f"  LOW ATR       {np.mean(low_edges):>+10.4f}    {len(low_edges):>3}     "
              f"Quiet trend")
    if mid_edges:
        print(f"  MID ATR       {np.mean(mid_edges):>+10.4f}    {len(mid_edges):>3}     "
              f"Normal vol")
    if high_edges:
        print(f"  HIGH ATR      {np.mean(high_edges):>+10.4f}    {len(high_edges):>3}     "
              f"Active but trending")

    if low_edges and high_edges:
        print(f"\n  → Low ATR vs High ATR in CALM_UP: "
              f"spread = {np.mean(low_edges) - np.mean(high_edges):+.4f}")


# ====================================================================
# MAIN
# ====================================================================

def parse_args():
    p = argparse.ArgumentParser(description="Comprehensive Sub-State Study")
    p.add_argument('--stocks', nargs='+', default=DEFAULT_STOCKS)
    p.add_argument('--years', type=int, default=DOWNLOAD_YEARS)
    p.add_argument('--ndx-ticker', default=NDX_TICKER)
    return p.parse_args()


def main():
    args = parse_args()

    print("=" * 90)
    print("COMPREHENSIVE SUB-STATE & TRANSITION STUDY")
    print("  6 research avenues for momentum stock strategy")
    print("=" * 90)
    print(f"  Stocks ({len(args.stocks)}): {', '.join(args.stocks[:8])}...")
    print(f"  Years: {args.years}")
    print(f"  Short lookbacks tested: {SHORT_LOOKBACKS}")

    # Download
    all_tickers = list(dict.fromkeys([args.ndx_ticker] + args.stocks))
    all_data = download_data(all_tickers, years=args.years)

    if args.ndx_ticker not in all_data:
        print(f"\nERROR: Could not download {args.ndx_ticker}")
        sys.exit(1)

    # NDX regime
    ndx_feat = compute_features(all_data[args.ndx_ticker])
    ndx_regimes = ndx_feat[['regime']].copy()

    # Run all vias per stock
    all_via1 = {}
    all_via2 = {}
    all_via3 = {}
    all_via4 = {}
    all_via5 = {}
    all_via6 = {}

    for ticker in args.stocks:
        if ticker not in all_data:
            continue

        print(f"\n{'#' * 80}")
        print(f"  {ticker}")
        print(f"{'#' * 80}")

        all_via1[ticker] = via1_pullback_calm(all_data[ticker], ndx_regimes, ticker)
        all_via2[ticker] = via2_transition(all_data[ticker], ndx_regimes, ticker)
        all_via3[ticker] = via3_lookback(all_data[ticker], ndx_regimes, ticker)
        all_via4[ticker] = via4_stock_vs_ndx(all_data[ticker], ndx_regimes, ticker)
        all_via5[ticker] = via5_atr_interaction(all_data[ticker], ndx_regimes, ticker)
        all_via6[ticker] = via6_yearly(all_data[ticker], ndx_regimes, ticker)

    # Cross-stock summaries
    print(f"\n\n{'#' * 90}")
    print(f"  CROSS-STOCK SUMMARIES")
    print(f"{'#' * 90}")

    print_via1_summary(all_via1)
    print_via3_summary(all_via3)
    print_via4_summary(all_via4)
    print_via5_summary(all_via5)

    print(f"\n{'=' * 90}")
    print(f"STUDY COMPLETE — 6 avenues analyzed for {len(args.stocks)} stocks")
    print(f"{'=' * 90}")


if __name__ == '__main__':
    main()
