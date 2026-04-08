"""
NDX 4-State Regime Study — Where does stock edge concentrate?

Instead of binary ON/OFF, classifies NDX into 4 regimes:

  1. CALM UP:   Mom12M > 0, ATR_ratio < threshold  → Steady uptrend
  2. HOT UP:    Mom12M > 0, ATR_ratio >= threshold  → Volatile uptrend / rally
  3. CRASH:     Mom12M < 0, ATR_ratio >= threshold  → Active selloff
  4. REBOUND:   Mom12M < 0, ATR_ratio < threshold   → Post-crash recovery

Additionally detects TRANSITION states using short-term momentum:
  - Mom1M (21 days) to detect early turns within each state
  - CRASH + Mom1M>0 = "Turning" (early rebound signal)
  - REBOUND + Mom1M>0 = "Recovering" (confirmed recovery)

For each state: measures stock forward returns to find where edge concentrates.

Hypothesis: Post-crash rebound is the sweet spot (high vol + direction change).
The binary ON/OFF study killed edge because it averaged CALM UP with HOT UP,
missing that the real juice is in the transition from CRASH → REBOUND.

Data: yfinance (daily). Top 20 NDX stocks by momentum.

Usage:
  python tools/ndx_regime_4state_study.py
  python tools/ndx_regime_4state_study.py --stocks NVDA AVGO MU AMAT
  python tools/ndx_regime_4state_study.py --atr-threshold 1.2
  python tools/ndx_regime_4state_study.py --years 10
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

# Top 20 stocks from pre-study (tiers 1-3 + extras)
DEFAULT_STOCKS = [
    # Tier 1: proven edge + data
    'NVDA', 'AVGO', 'MU', 'AMAT',
    # Tier 2: high edge, fewer years
    'APP', 'PLTR',
    # Tier 3: stable, modest edge
    'KLAC', 'ASML', 'GOOGL', 'AMD', 'LRCX', 'ADI',
    # Extra: diversification
    'NFLX', 'META', 'TSLA', 'CRWD', 'PANW', 'MSFT', 'AMZN', 'AAPL',
]

NDX_TICKER = 'QQQ'

# Costs
SWAP_LONG_DAILY = 0.0002
COMMISSION_PER_ORDER = 0.02

# Momentum
MOM_LONG_DAYS = 252    # 12M for regime classification
MOM_SHORT_DAYS = 21    # 1M for transition detection

# ATR
ATR_PERIOD = 24
ATR_RATIO_THRESHOLD = 1.0

# Forward days
FORWARD_DAYS = [1, 2, 3, 5, 10, 20]

# Data
MIN_YEARS = 3
MIN_BARS = MIN_YEARS * 252
DOWNLOAD_YEARS = 10


# ====================================================================
# REGIME NAMES & COLORS
# ====================================================================

REGIMES = {
    'CALM_UP':  '🟢 CALM UP',
    'HOT_UP':   '🔥 HOT UP',
    'CRASH':    '🔴 CRASH',
    'REBOUND':  '🟡 REBOUND',
}

# Sub-states with 1M momentum
SUBSTATES = {
    'CALM_UP_pos':  'CALM UP  (1M↑)',
    'CALM_UP_neg':  'CALM UP  (1M↓)',
    'HOT_UP_pos':   'HOT UP   (1M↑)',
    'HOT_UP_neg':   'HOT UP   (1M↓)',
    'CRASH_pos':    'CRASH    (1M↑)',   # = turning!
    'CRASH_neg':    'CRASH    (1M↓)',
    'REBOUND_pos':  'REBOUND  (1M↑)',   # = recovering!
    'REBOUND_neg':  'REBOUND  (1M↓)',
}


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
    """Add momentum (12M + 1M), ATR, forward returns."""
    close = df['Close'].copy()
    high = df['High'].copy()
    low = df['Low'].copy()

    df = df.copy()

    # Momentum 12M and 1M
    df['mom12'] = close / close.shift(MOM_LONG_DAYS) - 1
    df['mom1'] = close / close.shift(MOM_SHORT_DAYS) - 1

    # ATR
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    df['atr'] = tr.rolling(ATR_PERIOD).mean()
    df['atr_pct'] = df['atr'] / close * 100

    # ATR ratio (vs 250-day mean)
    df['atr_mean250'] = df['atr'].rolling(250).mean()
    df['atr_ratio'] = df['atr'] / df['atr_mean250']

    # Daily return normalized by ATR
    df['ret_atr'] = (close - close.shift(1)) / df['atr']

    # Cost
    df['cost_1d'] = (SWAP_LONG_DAILY * close + 2 * COMMISSION_PER_ORDER)
    df['cost_atr_1d'] = df['cost_1d'] / df['atr'] * 100

    # Forward returns (ATR-normalized)
    for fwd in FORWARD_DAYS:
        df[f'fwd_{fwd}d'] = (close.shift(-fwd) - close) / df['atr']

    return df.dropna(subset=['mom12', 'mom1', 'atr', 'atr_ratio'])


# ====================================================================
# NDX 4-STATE REGIME
# ====================================================================

def classify_ndx_regime(ndx_df, atr_threshold):
    """
    Classify NDX into 4 regimes + 8 sub-states.
    Returns DataFrame with 'regime' and 'substate' columns.
    """
    ndx = compute_features(ndx_df)

    mom12_pos = ndx['mom12'] > 0
    mom1_pos = ndx['mom1'] > 0
    atr_high = ndx['atr_ratio'] >= atr_threshold

    # 4 main states
    ndx['regime'] = 'UNKNOWN'
    ndx.loc[mom12_pos & ~atr_high, 'regime'] = 'CALM_UP'
    ndx.loc[mom12_pos & atr_high, 'regime'] = 'HOT_UP'
    ndx.loc[~mom12_pos & atr_high, 'regime'] = 'CRASH'
    ndx.loc[~mom12_pos & ~atr_high, 'regime'] = 'REBOUND'

    # 8 sub-states (with 1M momentum direction)
    ndx['substate'] = ndx['regime'] + np.where(mom1_pos, '_pos', '_neg')

    # Print regime summary
    print(f"\n{'=' * 80}")
    print(f"NDX 4-STATE REGIME ({NDX_TICKER})")
    print(f"  Mom12M threshold: 0 | ATR ratio threshold: {atr_threshold:.1f}x")
    print(f"{'=' * 80}")

    total = len(ndx)

    # Main 4 states
    print(f"\n  --- 4 MAIN STATES ---")
    print(f"  {'State':<14} {'%time':>6} {'Days':>6} {'NDX Edge/d':>11} "
          f"{'NDX WR%':>8}")
    print(f"  {'-' * 50}")

    for regime in ['CALM_UP', 'HOT_UP', 'CRASH', 'REBOUND']:
        mask = ndx['regime'] == regime
        pct = mask.mean() * 100
        n = mask.sum()
        sub = ndx[mask]
        edge = sub['fwd_1d'].mean() if len(sub) > 0 else 0
        wr = (sub['fwd_1d'] > 0).mean() * 100 if len(sub) > 0 else 0
        label = REGIMES[regime]
        print(f"  {label:<14} {pct:>5.1f}% {n:>6} {edge:>+11.4f} {wr:>7.1f}%")

    # 8 sub-states
    print(f"\n  --- 8 SUB-STATES (with 1M momentum direction) ---")
    print(f"  {'Sub-state':<22} {'%time':>6} {'Days':>6} {'NDX Edge/d':>11} "
          f"{'NDX WR%':>8} {'Signal':>10}")
    print(f"  {'-' * 70}")

    for sub in ['CALM_UP_pos', 'CALM_UP_neg', 'HOT_UP_pos', 'HOT_UP_neg',
                'CRASH_neg', 'CRASH_pos', 'REBOUND_neg', 'REBOUND_pos']:
        mask = ndx['substate'] == sub
        pct = mask.mean() * 100
        n = mask.sum()
        data = ndx[mask]
        edge = data['fwd_1d'].mean() if len(data) > 0 else 0
        wr = (data['fwd_1d'] > 0).mean() * 100 if len(data) > 0 else 0

        # Signal interpretation
        signal = ''
        if sub == 'CRASH_pos':
            signal = '⚡ TURNING'
        elif sub == 'REBOUND_pos':
            signal = '🚀 RECOVER'
        elif sub == 'CRASH_neg':
            signal = '☠️  AVOID'
        elif sub == 'HOT_UP_neg':
            signal = '⚠️  TOPPING?'

        label = SUBSTATES[sub]
        print(f"  {label:<22} {pct:>5.1f}% {n:>6} {edge:>+11.4f} "
              f"{wr:>7.1f}% {signal:>10}")

    # Yearly regime heatmap
    print(f"\n  --- YEARLY REGIME DISTRIBUTION ---")
    ndx['year'] = ndx.index.year
    years = sorted(ndx['year'].unique())

    print(f"  Year  {'CALM_UP':>8} {'HOT_UP':>8} {'CRASH':>8} {'REBOUND':>8}")
    print(f"  {'-' * 42}")
    for year in years:
        yr_data = ndx[ndx['year'] == year]
        n = len(yr_data)
        if n < 20:
            continue
        calm = (yr_data['regime'] == 'CALM_UP').sum() / n * 100
        hot = (yr_data['regime'] == 'HOT_UP').sum() / n * 100
        crash = (yr_data['regime'] == 'CRASH').sum() / n * 100
        reb = (yr_data['regime'] == 'REBOUND').sum() / n * 100
        print(f"  {year}   {calm:>7.0f}% {hot:>7.0f}% {crash:>7.0f}% {reb:>7.0f}%")

    return ndx[['regime', 'substate', 'mom12', 'mom1', 'atr_ratio']]


# ====================================================================
# STOCK EDGE BY REGIME
# ====================================================================

def analyze_stock_by_regime(stock_df, ndx_regimes, ticker):
    """Analyze stock edge in each of the 4 NDX regimes + sub-states."""

    df = compute_features(stock_df)

    # Align NDX regimes
    aligned = ndx_regimes.reindex(df.index)
    df['ndx_regime'] = aligned['regime'].fillna('UNKNOWN')
    df['ndx_substate'] = aligned['substate'].fillna('UNKNOWN')

    # Stock's own long filter
    df['stock_long'] = df['mom12'] > 0

    n_years = len(df) / 252
    price = df['Close'].iloc[-1]

    print(f"\n{'━' * 80}")
    print(f"  {ticker}  ({n_years:.1f}yr, ${price:.2f})")
    print(f"{'━' * 80}")

    # --- Edge by 4 main regimes (LONG only = stock mom12 > 0) ---
    print(f"\n  STOCK EDGE BY NDX REGIME (filtered: stock Mom12M > 0)")
    print(f"  {'Regime':<14} {'%time':>6} {'N':>6} {'Edge/d':>8} "
          f"{'WR%':>6} {'C/ATR':>6} {'Net/d':>8} {'Fwd10d':>8} {'Fwd20d':>8}")
    print(f"  {'-' * 80}")

    regime_results = {}
    for regime in ['CALM_UP', 'HOT_UP', 'CRASH', 'REBOUND']:
        mask = (df['ndx_regime'] == regime) & df['stock_long']
        sub = df[mask]

        if len(sub) < 30:
            label = REGIMES[regime]
            print(f"  {label:<14} {'—':>6} {len(sub):>6}   insufficient data")
            continue

        pct = mask.mean() * 100
        edge = sub['fwd_1d'].mean()
        wr = (sub['fwd_1d'] > 0).mean() * 100
        cost = sub['cost_atr_1d'].median()
        net = edge - cost / 100

        fwd10 = sub['fwd_10d'].mean() if len(sub[sub['fwd_10d'].notna()]) > 20 else 0
        fwd20 = sub['fwd_20d'].mean() if len(sub[sub['fwd_20d'].notna()]) > 20 else 0

        label = REGIMES[regime]
        print(f"  {label:<14} {pct:>5.1f}% {len(sub):>6} {edge:>+8.4f} "
              f"{wr:>5.1f}% {cost:>5.1f}% {net:>+8.4f} {fwd10:>+8.3f} {fwd20:>+8.3f}")

        regime_results[regime] = {
            'n': len(sub), 'pct': pct, 'edge': edge, 'wr': wr,
            'cost': cost, 'net': net, 'fwd10': fwd10, 'fwd20': fwd20
        }

    # --- Sub-state analysis (focus on transitions) ---
    print(f"\n  SUB-STATE DETAIL (stock Mom12M > 0)")
    print(f"  {'Sub-state':<22} {'N':>5} {'Edge/d':>8} {'WR%':>6} "
          f"{'Fwd5d':>8} {'Fwd10d':>8} {'Signal':>10}")
    print(f"  {'-' * 72}")

    substate_results = {}
    for sub_name in ['CALM_UP_pos', 'CALM_UP_neg', 'HOT_UP_pos', 'HOT_UP_neg',
                     'CRASH_neg', 'CRASH_pos', 'REBOUND_neg', 'REBOUND_pos']:
        mask = (df['ndx_substate'] == sub_name) & df['stock_long']
        sub = df[mask]

        if len(sub) < 20:
            continue

        edge = sub['fwd_1d'].mean()
        wr = (sub['fwd_1d'] > 0).mean() * 100
        fwd5 = sub['fwd_5d'].mean()
        fwd10 = sub['fwd_10d'].mean() if len(sub[sub['fwd_10d'].notna()]) > 15 else 0

        signal = ''
        if sub_name == 'CRASH_pos':
            signal = '⚡ TURN'
        elif sub_name == 'REBOUND_pos':
            signal = '🚀 RECOV'
        elif sub_name == 'CRASH_neg':
            signal = '☠️  AVOID'

        label = SUBSTATES[sub_name]
        print(f"  {label:<22} {len(sub):>5} {edge:>+8.4f} {wr:>5.1f}% "
              f"{fwd5:>+8.4f} {fwd10:>+8.4f} {signal:>10}")

        substate_results[sub_name] = {
            'n': len(sub), 'edge': edge, 'wr': wr, 'fwd5': fwd5, 'fwd10': fwd10
        }

    # --- Crash → Rebound transition: forward curve ---
    rebound_mask = (df['ndx_regime'] == 'REBOUND') & df['stock_long']
    crash_mask = (df['ndx_regime'] == 'CRASH') & df['stock_long']

    if rebound_mask.sum() >= 20:
        print(f"\n  FORWARD CURVE: REBOUND vs CRASH vs ALL (stock Long)")
        print(f"  {'fwd':>5} {'REBOUND':>10} {'CRASH':>10} {'ALL':>10} "
              f"{'REB/ALL':>8}")
        print(f"  {'-' * 50}")

        for fwd in FORWARD_DAYS:
            col = f'fwd_{fwd}d'
            reb_data = df.loc[rebound_mask, col].dropna()
            crash_data = df.loc[crash_mask, col].dropna()
            all_long = df.loc[df['stock_long'], col].dropna()

            reb_e = reb_data.mean() if len(reb_data) > 10 else 0
            crash_e = crash_data.mean() if len(crash_data) > 10 else 0
            all_e = all_long.mean() if len(all_long) > 10 else 0

            ratio = reb_e / all_e if abs(all_e) > 1e-6 else 0

            print(f"  {fwd:>4}d {reb_e:>+10.4f} {crash_e:>+10.4f} "
                  f"{all_e:>+10.4f} {ratio:>7.1f}x")

    return regime_results, substate_results


# ====================================================================
# GLOBAL SUMMARY
# ====================================================================

def print_global_summary(all_regime_results, all_substate_results, atr_threshold):
    """Print cross-stock comparison for each regime."""
    print(f"\n{'=' * 90}")
    print(f"GLOBAL SUMMARY — 4-State Regime Stock Edge")
    print(f"NDX states: CALM_UP / HOT_UP / CRASH / REBOUND  (ATR threshold: {atr_threshold:.1f}x)")
    print(f"{'=' * 90}")

    # --- Best regime per stock ---
    print(f"\n  {'Ticker':<8}", end='')
    for regime in ['CALM_UP', 'HOT_UP', 'CRASH', 'REBOUND']:
        print(f" {regime:>10}", end='')
    print(f"  {'BEST':>10} {'BEST Net':>9}")
    print(f"  {'-' * 68}")

    stock_bests = {}
    for ticker in sorted(all_regime_results.keys()):
        res = all_regime_results[ticker]
        print(f"  {ticker:<8}", end='')

        best_regime = None
        best_net = -999
        for regime in ['CALM_UP', 'HOT_UP', 'CRASH', 'REBOUND']:
            r = res.get(regime)
            if r:
                edge_str = f"{r['edge']:>+.4f}"
                print(f" {edge_str:>10}", end='')
                if r['net'] > best_net:
                    best_net = r['net']
                    best_regime = regime
            else:
                print(f" {'—':>10}", end='')

        if best_regime:
            print(f"  {best_regime:>10} {best_net:>+9.4f}")
            stock_bests[ticker] = (best_regime, best_net)
        else:
            print(f"  {'—':>10} {'—':>9}")

    # --- Regime ranking ---
    print(f"\n  WHICH REGIME HAS THE MOST EDGE ACROSS STOCKS?")
    for regime in ['CALM_UP', 'HOT_UP', 'CRASH', 'REBOUND']:
        edges = []
        nets = []
        for ticker, res in all_regime_results.items():
            r = res.get(regime)
            if r and r['n'] >= 30:
                edges.append(r['edge'])
                nets.append(r['net'])

        if edges:
            avg_edge = np.mean(edges)
            avg_net = np.mean(nets)
            pos = sum(1 for e in edges if e > 0)
            label = REGIMES[regime]
            print(f"    {label:<14}  avg edge: {avg_edge:>+.4f}  "
                  f"avg net: {avg_net:>+.4f}  "
                  f"positive: {pos}/{len(edges)} stocks")

    # --- Transition signal value ---
    print(f"\n  TRANSITION SIGNALS (sub-state value):")
    for sub_name, sub_label in [
        ('CRASH_pos', '⚡ CRASH + 1M↑ (TURNING)'),
        ('REBOUND_pos', '🚀 REBOUND + 1M↑ (RECOVERING)'),
        ('CRASH_neg', '☠️  CRASH + 1M↓ (FALLING)'),
    ]:
        edges = []
        for ticker, sres in all_substate_results.items():
            s = sres.get(sub_name)
            if s and s['n'] >= 15:
                edges.append(s['edge'])

        if edges:
            avg = np.mean(edges)
            pos = sum(1 for e in edges if e > 0)
            print(f"    {sub_label:<38}  avg edge: {avg:>+.4f}  "
                  f"positive: {pos}/{len(edges)}")

    # --- Actionable conclusion ---
    print(f"\n  CONCLUSION:")

    # Find which regime dominates
    regime_scores = {}
    for regime in ['CALM_UP', 'HOT_UP', 'CRASH', 'REBOUND']:
        nets = []
        for ticker, res in all_regime_results.items():
            r = res.get(regime)
            if r and r['n'] >= 30:
                nets.append(r['net'])
        if nets:
            regime_scores[regime] = (np.mean(nets), len(nets), sum(1 for n in nets if n > 0))

    best = max(regime_scores.items(), key=lambda x: x[1][0]) if regime_scores else None
    if best:
        name, (avg_net, n_stocks, pos) = best
        label = REGIMES[name]
        print(f"    Best regime: {label} (avg net: {avg_net:+.4f}, "
              f"{pos}/{n_stocks} stocks positive)")

    # Sweet spot candidates
    sweet = [(t, r, n) for t, (r, n) in stock_bests.items()
             if r == 'REBOUND' and n > 0.02]
    if sweet:
        print(f"    REBOUND sweet-spot stocks: {', '.join(t for t, _, _ in sweet)}")


# ====================================================================
# MAIN
# ====================================================================

def parse_args():
    p = argparse.ArgumentParser(description="NDX 4-State Regime Study")
    p.add_argument('--stocks', nargs='+', default=DEFAULT_STOCKS,
                   help='Stocks to test')
    p.add_argument('--atr-threshold', type=float, default=ATR_RATIO_THRESHOLD,
                   help='ATR ratio threshold for high/low vol (default: 1.0)')
    p.add_argument('--years', type=int, default=DOWNLOAD_YEARS,
                   help='Years of data (default: 10)')
    p.add_argument('--ndx-ticker', default=NDX_TICKER,
                   help='NDX proxy ticker (default: QQQ)')
    return p.parse_args()


def main():
    args = parse_args()

    print("=" * 90)
    print("NDX 4-STATE REGIME STUDY")
    print("  Does stock edge concentrate in post-crash rebounds?")
    print("=" * 90)
    print(f"  NDX proxy:       {args.ndx_ticker}")
    print(f"  ATR threshold:   {args.atr_threshold:.1f}x")
    print(f"  Mom lookbacks:   12M ({MOM_LONG_DAYS}d) + 1M ({MOM_SHORT_DAYS}d)")
    print(f"  Stocks ({len(args.stocks)}):    {', '.join(args.stocks[:10])}...")
    print(f"  Years:           {args.years}")
    print(f"  Cost:            swap {SWAP_LONG_DAILY*100:.2f}%/day + "
          f"${COMMISSION_PER_ORDER}/order")

    # Download data
    all_tickers = [args.ndx_ticker] + args.stocks
    # Remove duplicates preserving order
    seen = set()
    unique = []
    for t in all_tickers:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    all_data = download_data(unique, years=args.years)

    if args.ndx_ticker not in all_data:
        print(f"\nERROR: Could not download NDX proxy ({args.ndx_ticker})")
        sys.exit(1)

    # Classify NDX regime
    ndx_regimes = classify_ndx_regime(all_data[args.ndx_ticker], args.atr_threshold)

    # Analyze each stock
    all_regime_results = {}
    all_substate_results = {}
    for ticker in args.stocks:
        if ticker not in all_data:
            continue
        reg_res, sub_res = analyze_stock_by_regime(
            all_data[ticker], ndx_regimes, ticker)
        all_regime_results[ticker] = reg_res
        all_substate_results[ticker] = sub_res

    # Global summary
    print_global_summary(all_regime_results, all_substate_results,
                         args.atr_threshold)


if __name__ == '__main__':
    main()
