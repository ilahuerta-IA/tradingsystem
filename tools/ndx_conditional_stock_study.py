"""
NDX-Conditional Stock Edge Study

Tests the hypothesis: individual stock edge is stable when NDX macro filter is ON.

Macro filter (NDX D1):
  - Mom12M > 0  (uptrend)
  - ATR_ratio >= threshold (active volatility)

For each stock, measures:
  - Edge/day in NDX-ON vs NDX-OFF regimes
  - Win rate, yearly consistency
  - Cost/ATR impact
  - Forward return curve (holding 1-20 days)
  - Stability: is edge concentrated in ON, or random?

This answers: "When NDX says GO, do stocks deliver?"

Data: yfinance (daily OHLCV). NDX = ^NDX100 or QQQ as proxy.

Cost model (Darwinex Zero CFD stocks):
  - Swap long: -0.02% / day on nominal value
  - Commission: 0.02 USD / order / contract
  - LONGS only

Usage:
  python tools/ndx_conditional_stock_study.py
  python tools/ndx_conditional_stock_study.py --stocks NVDA AVGO MU AMAT
  python tools/ndx_conditional_stock_study.py --atr-threshold 1.0
  python tools/ndx_conditional_stock_study.py --years 8
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

# Tier 1+2 stocks from pre-study (proven edge)
DEFAULT_STOCKS = [
    'NVDA', 'AVGO', 'MU', 'AMAT',   # Tier 1: edge + data
    'APP', 'PLTR',                     # Tier 2: edge, fewer years
    'KLAC', 'ASML', 'GOOGL', 'AMD',   # Tier 3: stable, modest edge
    'LRCX', 'ADI', 'NFLX', 'META',    # Extra: diversification candidates
]

# NDX proxy ticker (^NDX100 sometimes fails, QQQ is reliable ETF proxy)
NDX_TICKER = 'QQQ'

# Darwinex Zero CFD stock costs
SWAP_LONG_DAILY = 0.0002   # 0.02% per day
COMMISSION_PER_ORDER = 0.02  # USD per contract per order

# Momentum / ATR parameters
MOM_DAYS = 252
ATR_PERIOD = 24
ATR_RATIO_THRESHOLD = 1.0  # default: ATR >= its 250d average

# Forward days
FORWARD_DAYS = [1, 2, 3, 5, 10, 20]

# Data
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


def compute_features(df):
    """Add momentum, ATR, forward returns."""
    close = df['Close'].copy()
    high = df['High'].copy()
    low = df['Low'].copy()

    df = df.copy()
    df['mom12'] = close / close.shift(MOM_DAYS) - 1

    # ATR
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    df['atr'] = tr.rolling(ATR_PERIOD).mean()
    df['atr_pct'] = df['atr'] / close * 100

    # ATR ratio
    df['atr_mean250'] = df['atr'].rolling(250).mean()
    df['atr_ratio'] = df['atr'] / df['atr_mean250']

    # Return normalized by ATR
    df['ret_atr'] = (close - close.shift(1)) / df['atr']

    # Cost/ATR for 1 day
    df['cost_1d'] = (SWAP_LONG_DAILY * close + 2 * COMMISSION_PER_ORDER)
    df['cost_atr_1d'] = df['cost_1d'] / df['atr'] * 100

    # Forward returns (ATR-normalized)
    for fwd in FORWARD_DAYS:
        df[f'fwd_{fwd}d'] = (close.shift(-fwd) - close) / df['atr']

    return df.dropna(subset=['mom12', 'atr', 'atr_ratio'])


# ====================================================================
# NDX REGIME
# ====================================================================

def compute_ndx_regime(ndx_df, atr_threshold):
    """
    Compute NDX macro regime: ON when Mom12M > 0 AND ATR_ratio >= threshold.
    Returns Series of boolean (True = ON) aligned to ndx_df index.
    """
    ndx = compute_features(ndx_df)

    mom_on = ndx['mom12'] > 0
    atr_on = ndx['atr_ratio'] >= atr_threshold

    regime = mom_on & atr_on

    total = len(regime)
    on_pct = regime.mean() * 100
    mom_pct = mom_on.mean() * 100
    atr_pct_time = atr_on.mean() * 100

    print(f"\n{'=' * 80}")
    print(f"NDX MACRO REGIME ({NDX_TICKER})")
    print(f"{'=' * 80}")
    print(f"  Mom12M > 0:           {mom_pct:5.1f}% of time")
    print(f"  ATR_ratio >= {atr_threshold:.1f}x:     {atr_pct_time:5.1f}% of time")
    print(f"  COMBINED (ON):        {on_pct:5.1f}% of time ({regime.sum()} / {total} days)")
    print(f"  OFF:                  {100-on_pct:5.1f}% of time")

    # Yearly breakdown
    ndx['regime'] = regime
    ndx['year'] = ndx.index.year
    yearly = ndx.groupby('year')['regime'].agg(['sum', 'count'])
    yearly['pct_on'] = yearly['sum'] / yearly['count'] * 100

    print(f"\n  Year  Days-ON / Total  %ON")
    print(f"  {'-' * 35}")
    for year, row in yearly.iterrows():
        bar = '█' * int(row['pct_on'] / 5)
        print(f"  {year}    {int(row['sum']):>4} / {int(row['count']):<4}   "
              f"{row['pct_on']:5.1f}%  {bar}")

    return regime


# ====================================================================
# CONDITIONAL EDGE ANALYSIS
# ====================================================================

def analyze_stock_conditional(stock_df, ndx_regime, ticker, atr_threshold):
    """
    Analyze a single stock's edge conditional on NDX regime ON vs OFF.
    """
    df = compute_features(stock_df)

    # Align NDX regime to stock dates
    aligned = ndx_regime.reindex(df.index)
    df['ndx_on'] = aligned.fillna(False)

    # Also apply stock's own Mom12M > 0 filter
    df['stock_long'] = df['mom12'] > 0

    # Four regimes to compare:
    # A) NDX-ON + Stock-Long  (the "sweet spot")
    # B) NDX-ON only
    # C) Stock-Long only
    # D) Baseline (all data)
    masks = {
        'NDX-ON + Stock↑': df['ndx_on'] & df['stock_long'],
        'NDX-ON (any)':    df['ndx_on'],
        'Stock↑ (any)':    df['stock_long'],
        'Baseline (all)':  pd.Series(True, index=df.index),
    }

    n_years = len(df) / 252
    print(f"\n{'─' * 80}")
    print(f"  {ticker}  ({n_years:.1f}yr, price=${df['Close'].iloc[-1]:.2f}, "
          f"ATR={df['atr_pct'].iloc[-1]:.1f}%)")
    print(f"{'─' * 80}")

    # --- Regime comparison table ---
    print(f"\n  {'Regime':<20} {'%time':>6} {'N':>6} {'Edge/d':>8} "
          f"{'WR%':>6} {'Cost/ATR':>9} {'Net/d':>8}")
    print(f"  {'-' * 68}")

    regime_results = {}
    for label, mask in masks.items():
        sub = df[mask]
        if len(sub) < 50:
            print(f"  {label:<20} {'—':>6} {len(sub):>6}  insufficient data")
            continue

        pct = mask.mean() * 100
        edge = sub['fwd_1d'].mean()
        wr = (sub['fwd_1d'] > 0).mean() * 100
        cost = sub['cost_atr_1d'].median()
        net = edge - cost / 100  # approximate net edge/day

        print(f"  {label:<20} {pct:>5.1f}% {len(sub):>6} {edge:>+8.4f} "
              f"{wr:>5.1f}% {cost:>8.2f}% {net:>+8.4f}")

        regime_results[label] = {
            'pct': pct, 'n': len(sub), 'edge': edge,
            'wr': wr, 'cost': cost, 'net': net
        }

    # --- Forward curve for sweet spot ---
    sweet = df[masks['NDX-ON + Stock↑']]
    off = df[~masks['NDX-ON + Stock↑']]

    if len(sweet) >= 50:
        print(f"\n  Forward curve (NDX-ON + Stock↑ vs REST):")
        print(f"  {'fwd':>5} {'ON Edge':>9} {'ON WR%':>8} {'OFF Edge':>9} "
              f"{'OFF WR%':>8} {'Ratio':>7} {'ON Net/d':>9}")
        print(f"  {'-' * 60}")

        for fwd in FORWARD_DAYS:
            col = f'fwd_{fwd}d'
            on_ret = sweet[col].dropna()
            off_ret = off[col].dropna()

            if len(on_ret) < 30:
                continue

            on_edge = on_ret.mean()
            on_wr = (on_ret > 0).mean() * 100
            off_edge = off_ret.mean() if len(off_ret) > 30 else 0
            off_wr = (off_ret > 0).mean() * 100 if len(off_ret) > 30 else 0

            ratio = on_edge / off_edge if abs(off_edge) > 1e-6 else float('inf')

            # Net after costs
            swap_cost_atr = (fwd * SWAP_LONG_DAILY * sweet['Close'].median()) / sweet['atr'].median()
            comm_cost_atr = (2 * COMMISSION_PER_ORDER) / sweet['atr'].median()
            total_cost = swap_cost_atr + comm_cost_atr
            net_per_day = (on_edge - total_cost) / fwd

            r_str = f"{ratio:>6.1f}x" if ratio < 100 else "  >>>>"
            print(f"  {fwd:>4}d {on_edge:>+9.4f} {on_wr:>7.1f}% "
                  f"{off_edge:>+9.4f} {off_wr:>7.1f}% {r_str} {net_per_day:>+9.4f}")

    # --- Yearly consistency (sweet spot, fwd=1d) ---
    if len(sweet) >= 50:
        sweet_yr = sweet.copy()
        sweet_yr['year'] = sweet_yr.index.year
        yearly = sweet_yr.groupby('year').agg(
            N=('fwd_1d', 'count'),
            Edge=('fwd_1d', 'mean'),
            WR=('fwd_1d', lambda x: (x > 0).mean() * 100),
        )
        yearly = yearly[yearly['N'] >= 20]  # min 20 days/year
        pos = (yearly['Edge'] > 0).sum()
        total_yr = len(yearly)

        print(f"\n  Yearly consistency (NDX-ON + Stock↑, fwd=1d): "
              f"{pos}/{total_yr} positive years")
        print(f"  {'Year':>6} {'N':>5} {'Edge/d':>8} {'WR%':>7}")
        print(f"  {'-' * 30}")
        for year, row in yearly.iterrows():
            marker = '✓' if row['Edge'] > 0 else '✗'
            print(f"  {year:>6} {int(row['N']):>5} {row['Edge']:>+8.4f} "
                  f"{row['WR']:>6.1f}% {marker}")

    return regime_results


# ====================================================================
# GLOBAL SUMMARY
# ====================================================================

def print_global_summary(all_results, atr_threshold):
    """Print compact comparison across all stocks."""
    print(f"\n{'=' * 90}")
    print(f"GLOBAL SUMMARY — NDX-Conditional Stock Edge")
    print(f"NDX filter: Mom12M>0 AND ATR_ratio>={atr_threshold:.1f}x")
    print(f"{'=' * 90}")

    header_sweet = 'NDX-ON + Stock↑'
    header_base = 'Baseline (all)'
    header_stock = 'Stock↑ (any)'

    print(f"\n  {'Ticker':<8} {'Sweet%':>7} {'Edge/d':>8} {'Net/d':>8} "
          f"{'WR%':>6} {'C/ATR':>6} {'YrCon':>6} {'vs Base':>8} "
          f"{'vs Stock':>9} {'GRADE':>7}")
    print(f"  {'-' * 85}")

    grades = []
    for ticker, res in sorted(all_results.items()):
        sw = res.get(header_sweet)
        ba = res.get(header_base)
        st = res.get(header_stock)

        if not sw:
            print(f"  {ticker:<8} — insufficient data in sweet spot")
            continue

        edge = sw['edge']
        net = sw['net']
        wr = sw['wr']
        cost = sw['cost']
        pct = sw['pct']

        # Improvement ratios
        vs_base = edge / ba['edge'] if ba and abs(ba['edge']) > 1e-6 else 0
        vs_stock = edge / st['edge'] if st and abs(st['edge']) > 1e-6 else 0

        # Grade: A (excellent), B (good), C (marginal), F (fail)
        if net > 0.06 and wr > 53:
            grade = 'A'
        elif net > 0.03 and wr > 51:
            grade = 'B'
        elif net > 0.01 and wr > 50:
            grade = 'C'
        else:
            grade = 'F'

        grades.append((ticker, grade, net))

        vs_b = f"{vs_base:.1f}x" if 0 < vs_base < 50 else "  —"
        vs_s = f"{vs_stock:.1f}x" if 0 < vs_stock < 50 else "   —"

        print(f"  {ticker:<8} {pct:>6.1f}% {edge:>+8.4f} {net:>+8.4f} "
              f"{wr:>5.1f}% {cost:>5.1f}% {'—':>6} {vs_b:>8} "
              f"{vs_s:>9}    {grade}")

    # Tier summary
    print(f"\n  GRADE DISTRIBUTION:")
    for g in ['A', 'B', 'C', 'F']:
        tks = [t for t, gr, _ in grades if gr == g]
        if tks:
            print(f"    {g}: {', '.join(tks)}")

    # Key insight
    a_b = [t for t, g, n in grades if g in ('A', 'B')]
    if a_b:
        avg_net = np.mean([n for _, g, n in grades if g in ('A', 'B')])
        print(f"\n  Actionable stocks (A+B): {len(a_b)} → avg net edge/day: "
              f"{avg_net:+.4f} ATR")
        print(f"  At 10-20d holding, swap dilutes to ~{SWAP_LONG_DAILY*100*15:.1f}% "
              f"of nominal → negligible vs ATR edge")


# ====================================================================
# MAIN
# ====================================================================

def parse_args():
    p = argparse.ArgumentParser(
        description="NDX-Conditional Stock Edge Study")
    p.add_argument('--stocks', nargs='+', default=DEFAULT_STOCKS,
                   help='Stocks to test (default: pre-study Tier 1-3)')
    p.add_argument('--atr-threshold', type=float, default=ATR_RATIO_THRESHOLD,
                   help='NDX ATR ratio threshold for ON regime (default: 1.0)')
    p.add_argument('--years', type=int, default=DOWNLOAD_YEARS,
                   help='Years of data (default: 10)')
    p.add_argument('--ndx-ticker', default=NDX_TICKER,
                   help='NDX proxy ticker (default: QQQ)')
    return p.parse_args()


def main():
    args = parse_args()

    print("=" * 90)
    print("NDX-CONDITIONAL STOCK EDGE STUDY")
    print("=" * 90)
    print(f"  NDX proxy:       {args.ndx_ticker}")
    print(f"  ATR threshold:   {args.atr_threshold:.1f}x (NDX ATR >= {args.atr_threshold:.1f}x its 250d avg)")
    print(f"  Mom filter:      NDX Mom12M > 0")
    print(f"  Stocks:          {', '.join(args.stocks)}")
    print(f"  Years:           {args.years}")
    print(f"  Cost:            swap {SWAP_LONG_DAILY*100:.2f}%/day + ${COMMISSION_PER_ORDER}/order")

    # Download NDX + all stocks
    all_tickers = [args.ndx_ticker] + args.stocks
    all_data = download_data(all_tickers, years=args.years)

    if args.ndx_ticker not in all_data:
        print(f"\nERROR: Could not download NDX proxy ({args.ndx_ticker})")
        sys.exit(1)

    # Compute NDX regime
    ndx_regime = compute_ndx_regime(all_data[args.ndx_ticker], args.atr_threshold)

    # Analyze each stock
    all_results = {}
    for ticker in args.stocks:
        if ticker not in all_data:
            print(f"\n  {ticker}: NO DATA — skipped")
            continue
        res = analyze_stock_conditional(
            all_data[ticker], ndx_regime, ticker, args.atr_threshold)
        all_results[ticker] = res

    # Global summary
    print_global_summary(all_results, args.atr_threshold)


if __name__ == '__main__':
    main()
