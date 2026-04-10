"""
Stock Momentum Pre-Study -- Test individual stocks vs index (NDX).

Hypothesis: Individual top-tier stocks have higher ATR/volatility than the
index, making them more operable with lower relative costs.

Cost model (Darwinex Zero CFD stocks):
  - Swap long: -0.02% / day on nominal value
  - Swap short: +0.01% / day
  - Commission: 0.02 USD / order / contract
  - We focus on LONGS only (trend-following)

Data: Daily OHLCV from yfinance.

Tests:
  1. TREND:      Mom12M filter vs baseline daily returns
  2. VOLATILITY: ATR regime vs edge + dynamic cost/ATR
  3. HOLDING:    Forward return curve 1-20 days

Usage:
  python tools/stock_momentum_prestudy.py                           # Top 20 NDX stocks
  python tools/stock_momentum_prestudy.py --universe dj30           # All 30 DJ30 stocks
  python tools/stock_momentum_prestudy.py --universe dj30 --top 15  # Top 15 DJ30 by mom
  python tools/stock_momentum_prestudy.py --universe sp500 --top 50 --exclude-current  # SP500 legacy ~100
  python tools/stock_momentum_prestudy.py --universe sp500full --exclude-analyzed --top 300  # Remaining ~293
  python tools/stock_momentum_prestudy.py --stocks NVDA AAPL        # Specific stocks
  python tools/stock_momentum_prestudy.py --top 30                  # Top 30 by momentum
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

# Nasdaq 100 components (major, as of early 2026)
NDX100_TICKERS = [
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'META', 'GOOGL', 'GOOG', 'AVGO',
    'TSLA', 'COST', 'NFLX', 'AMD', 'ADBE', 'PEP', 'CSCO', 'TMUS',
    'LIN', 'INTC', 'INTU', 'QCOM', 'CMCSA', 'TXN', 'AMGN', 'ISRG',
    'HON', 'AMAT', 'BKNG', 'LRCX', 'VRTX', 'MU', 'ADI', 'PANW',
    'KLAC', 'ADP', 'REGN', 'SBUX', 'MDLZ', 'SNPS', 'MELI', 'CDNS',
    'GILD', 'PYPL', 'ASML', 'CRWD', 'CTAS', 'MAR', 'MRVL', 'ORLY',
    'CSX', 'ABNB', 'FTNT', 'PCAR', 'WDAY', 'DASH', 'CEG', 'MNST',
    'DXCM', 'ROP', 'ODFL', 'NXPI', 'AEP', 'FAST', 'CHTR', 'TTD',
    'PAYX', 'KDP', 'ROST', 'CPRT', 'TEAM', 'VRSK', 'EA', 'GEHC',
    'CTSH', 'KHC', 'IDXX', 'EXC', 'BKR', 'CCEP', 'ON', 'FANG',
    'MCHP', 'XEL', 'CDW', 'ANSS', 'DDOG', 'GFS', 'ZS', 'ILMN',
    'BIIB', 'MDB', 'WBD', 'SIRI', 'DLTR', 'LCID', 'RIVN', 'ARM',
    'SMCI', 'PLTR', 'APP', 'COIN',
]

# Dow Jones 30 components (as of 2025)
DJ30_TICKERS = [
    'AAPL', 'AMGN', 'AMZN', 'AXP', 'BA', 'CAT', 'CRM', 'CSCO', 'CVX',
    'DIS', 'GS', 'HD', 'HON', 'IBM', 'JNJ', 'JPM', 'KO', 'MCD', 'MMM',
    'MRK', 'MSFT', 'NKE', 'NVDA', 'PG', 'SHW', 'TRV', 'UNH', 'V', 'VZ',
    'WMT',
]

# S&P 500 top ~100 by market cap (legacy subset, kept for reference)
SP500_TICKERS = [
    'BRK-B', 'JPM', 'V', 'JNJ', 'UNH', 'XOM', 'PG', 'MA', 'HD', 'CVX',
    'MRK', 'ABBV', 'KO', 'PEP', 'BAC', 'PFE', 'WMT', 'MCD', 'CSCO', 'TMO',
    'ABT', 'DHR', 'ACN', 'NKE', 'NEE', 'LIN', 'PM', 'UPS', 'RTX', 'LOW',
    'SPGI', 'GS', 'CAT', 'BLK', 'AXP', 'DE', 'SCHW', 'MDLZ', 'CI', 'AMT',
    'CB', 'SYK', 'ZTS', 'BMY', 'MO', 'SO', 'DUK', 'CL', 'TGT', 'MMC',
    'ICE', 'CME', 'SHW', 'PNC', 'USB', 'APD', 'FDX', 'TFC', 'EMR', 'NSC',
    'ITW', 'HUM', 'ETN', 'AON', 'ECL', 'SLB', 'PSA', 'WM', 'CCI', 'GD',
    'AFL', 'F', 'GM', 'AIG', 'MET', 'PRU', 'TRV', 'ALL', 'COF', 'BK',
    'WELL', 'O', 'SPG', 'PLD', 'EQIX', 'DLR', 'PSX', 'VLO', 'MPC', 'OXY',
    'COP', 'EOG', 'DVN', 'FANG', 'HAL', 'WMB', 'KMI', 'LYB', 'DOW', 'PPG',
    'DD', 'FCX', 'NEM', 'IR', 'ROK', 'GE', 'HON', 'LMT', 'NOC', 'BA',
    'GEV', 'CARR', 'OTIS', 'JCI', 'A', 'WAT', 'IQV', 'EW', 'BSX', 'ISRG',
    'DXCM', 'PODD', 'MDT', 'BDX', 'GEHC', 'HCA', 'ELV', 'CNC', 'MCK',
]

# Full S&P 500 constituents (503 tickers, as of April 2026 from Wikipedia)
SP500_FULL_TICKERS = [
    'A', 'AAPL', 'ABBV', 'ABNB', 'ABT', 'ACGL', 'ACN', 'ADBE', 'ADI', 'ADM',
    'ADP', 'ADSK', 'AEE', 'AEP', 'AES', 'AFL', 'AIG', 'AIZ', 'AJG', 'AKAM',
    'ALB', 'ALGN', 'ALL', 'ALLE', 'AMAT', 'AMCR', 'AMD', 'AME', 'AMGN', 'AMP',
    'AMT', 'AMZN', 'ANET', 'AON', 'AOS', 'APA', 'APD', 'APH', 'APO', 'APP',
    'APTV', 'ARE', 'ARES', 'ATO', 'AVB', 'AVGO', 'AVY', 'AWK', 'AXON', 'AXP',
    'AZO', 'BA', 'BAC', 'BALL', 'BAX', 'BBY', 'BDX', 'BEN', 'BF-B', 'BG',
    'BIIB', 'BK', 'BKNG', 'BKR', 'BLDR', 'BLK', 'BMY', 'BR', 'BRK-B', 'BRO',
    'BSX', 'BX', 'BXP', 'C', 'CAG', 'CAH', 'CARR', 'CASY', 'CAT', 'CB',
    'CBOE', 'CBRE', 'CCI', 'CCL', 'CDNS', 'CDW', 'CEG', 'CF', 'CFG', 'CHD',
    'CHRW', 'CHTR', 'CI', 'CIEN', 'CINF', 'CL', 'CLX', 'CMCSA', 'CME', 'CMG',
    'CMI', 'CMS', 'CNC', 'CNP', 'COF', 'COHR', 'COIN', 'COO', 'COP', 'COR',
    'COST', 'CPAY', 'CPB', 'CPRT', 'CPT', 'CRH', 'CRL', 'CRM', 'CRWD', 'CSCO',
    'CSGP', 'CSX', 'CTAS', 'CTRA', 'CTSH', 'CTVA', 'CVNA', 'CVS', 'CVX', 'D',
    'DAL', 'DASH', 'DD', 'DDOG', 'DE', 'DECK', 'DELL', 'DG', 'DGX', 'DHI',
    'DHR', 'DIS', 'DLR', 'DLTR', 'DOC', 'DOV', 'DOW', 'DPZ', 'DRI', 'DTE',
    'DUK', 'DVA', 'DVN', 'DXCM', 'EA', 'EBAY', 'ECL', 'ED', 'EFX', 'EG',
    'EIX', 'EL', 'ELV', 'EME', 'EMR', 'EOG', 'EPAM', 'EQIX', 'EQR', 'EQT',
    'ERIE', 'ES', 'ESS', 'ETN', 'ETR', 'EVRG', 'EW', 'EXC', 'EXE', 'EXPD',
    'EXPE', 'EXR', 'F', 'FANG', 'FAST', 'FCX', 'FDS', 'FDX', 'FE', 'FFIV',
    'FICO', 'FIS', 'FISV', 'FITB', 'FIX', 'FOX', 'FOXA', 'FRT', 'FSLR', 'FTNT',
    'FTV', 'GD', 'GDDY', 'GE', 'GEHC', 'GEN', 'GEV', 'GILD', 'GIS', 'GL',
    'GLW', 'GM', 'GNRC', 'GOOG', 'GOOGL', 'GPC', 'GPN', 'GRMN', 'GS', 'GWW',
    'HAL', 'HAS', 'HBAN', 'HCA', 'HD', 'HIG', 'HII', 'HLT', 'HON', 'HOOD',
    'HPE', 'HPQ', 'HRL', 'HSIC', 'HST', 'HSY', 'HUBB', 'HUM', 'HWM', 'IBKR',
    'IBM', 'ICE', 'IDXX', 'IEX', 'IFF', 'INCY', 'INTC', 'INTU', 'INVH', 'IP',
    'IQV', 'IR', 'IRM', 'ISRG', 'IT', 'ITW', 'IVZ', 'J', 'JBHT', 'JBL',
    'JCI', 'JKHY', 'JNJ', 'JPM', 'KDP', 'KEY', 'KEYS', 'KHC', 'KIM', 'KKR',
    'KLAC', 'KMB', 'KMI', 'KO', 'KR', 'KVUE', 'L', 'LDOS', 'LEN', 'LH',
    'LHX', 'LII', 'LIN', 'LITE', 'LLY', 'LMT', 'LNT', 'LOW', 'LRCX', 'LULU',
    'LUV', 'LVS', 'LYB', 'LYV', 'MA', 'MAA', 'MAR', 'MAS', 'MCD', 'MCHP',
    'MCK', 'MCO', 'MDLZ', 'MDT', 'MET', 'META', 'MGM', 'MKC', 'MLM', 'MMM',
    'MNST', 'MO', 'MOS', 'MPC', 'MPWR', 'MRK', 'MRNA', 'MRSH', 'MS', 'MSCI',
    'MSFT', 'MSI', 'MTB', 'MTD', 'MU', 'NCLH', 'NDAQ', 'NDSN', 'NEE', 'NEM',
    'NFLX', 'NI', 'NKE', 'NOC', 'NOW', 'NRG', 'NSC', 'NTAP', 'NTRS', 'NUE',
    'NVDA', 'NVR', 'NWS', 'NWSA', 'NXPI', 'O', 'ODFL', 'OKE', 'OMC', 'ON',
    'ORCL', 'ORLY', 'OTIS', 'OXY', 'PANW', 'PAYX', 'PCAR', 'PCG', 'PEG', 'PEP',
    'PFE', 'PFG', 'PG', 'PGR', 'PH', 'PHM', 'PKG', 'PLD', 'PLTR', 'PM',
    'PNC', 'PNR', 'PNW', 'PODD', 'POOL', 'PPG', 'PPL', 'PRU', 'PSA', 'PSKY',
    'PSX', 'PTC', 'PWR', 'PYPL', 'Q', 'QCOM', 'RCL', 'REG', 'REGN', 'RF',
    'RJF', 'RL', 'RMD', 'ROK', 'ROL', 'ROP', 'ROST', 'RSG', 'RTX', 'RVTY',
    'SATS', 'SBAC', 'SBUX', 'SCHW', 'SHW', 'SJM', 'SLB', 'SMCI', 'SNA', 'SNDK',
    'SNPS', 'SO', 'SOLV', 'SPG', 'SPGI', 'SRE', 'STE', 'STLD', 'STT', 'STX',
    'STZ', 'SW', 'SWK', 'SWKS', 'SYF', 'SYK', 'SYY', 'T', 'TAP', 'TDG',
    'TDY', 'TECH', 'TEL', 'TER', 'TFC', 'TGT', 'TJX', 'TKO', 'TMO', 'TMUS',
    'TPL', 'TPR', 'TRGP', 'TRMB', 'TROW', 'TRV', 'TSCO', 'TSLA', 'TSN', 'TT',
    'TTD', 'TTWO', 'TXN', 'TXT', 'TYL', 'UAL', 'UBER', 'UDR', 'UHS', 'ULTA',
    'UNH', 'UNP', 'UPS', 'URI', 'USB', 'V', 'VICI', 'VLO', 'VLTO', 'VMC',
    'VRSK', 'VRSN', 'VRT', 'VRTX', 'VST', 'VTR', 'VTRS', 'VZ', 'WAB', 'WAT',
    'WBD', 'WDAY', 'WDC', 'WEC', 'WELL', 'WFC', 'WM', 'WMB', 'WMT', 'WRB',
    'WSM', 'WST', 'WTW', 'WY', 'WYNN', 'XEL', 'XOM', 'XYL', 'XYZ', 'YUM',
    'ZBH', 'ZBRA', 'ZTS',
]

# All tickers already analyzed in previous prestudy runs
# (union of NDX100 + DJ30 + SP500 top-100 runs)
ALREADY_ANALYZED = sorted(set(NDX100_TICKERS) | set(DJ30_TICKERS) | set(SP500_TICKERS))

# Current ALTAIR active assets (NDX-7 + DJ30-5) to exclude from new studies
ALTAIR_CURRENT = [
    'NVDA', 'AMAT', 'AMD', 'AVGO', 'GOOGL', 'MSFT', 'NFLX',  # NDX-7
    'CAT', 'V', 'JPM', 'AXP', 'GS',                            # DJ30-5
]

# Darwinex Zero CFD stock costs
SWAP_LONG_DAILY = 0.0002   # 0.02% per day
COMMISSION_PER_ORDER = 0.02  # USD per contract per order

# Momentum lookback
MOM_DAYS = 252

# ATR period
ATR_PERIOD = 24

# Forward days to test
FORWARD_DAYS = [1, 2, 3, 5, 10, 20]

# Minimum data requirement
MIN_YEARS = 3
MIN_BARS = MIN_YEARS * 252

# Years of data to download
DOWNLOAD_YEARS = 15


# ====================================================================
# DATA
# ====================================================================

def download_stock_data(tickers, years=DOWNLOAD_YEARS):
    """Download daily OHLCV from yfinance for multiple tickers."""
    end = datetime.now()
    start = end - timedelta(days=years * 365)

    print(f"\nDownloading {len(tickers)} stocks from yfinance ({start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')})...")

    all_data = {}
    failed = []

    for ticker in tickers:
        try:
            df = yf.download(ticker, start=start, end=end, interval="1d",
                             auto_adjust=True, progress=False)
            if df is not None and len(df) >= MIN_BARS:
                # Flatten MultiIndex columns if present
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                all_data[ticker] = df
            else:
                n = len(df) if df is not None else 0
                failed.append((ticker, f"only {n} bars"))
        except Exception as e:
            failed.append((ticker, str(e)[:50]))

    print(f"  OK: {len(all_data)} stocks loaded")
    if failed:
        print(f"  SKIP: {len(failed)} stocks (insufficient data or error)")

    return all_data


def compute_features(df):
    """Add momentum, ATR, and forward returns to a stock dataframe."""
    close = df['Close'].copy()
    high = df['High'].copy()
    low = df['Low'].copy()

    # Momentum 12M
    df = df.copy()
    df['mom12'] = close / close.shift(MOM_DAYS) - 1

    # ATR
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    df['atr'] = tr.rolling(ATR_PERIOD).mean()
    df['atr_pct'] = df['atr'] / close * 100  # ATR as % of price

    # ATR ratio (current vs 250-day rolling mean)
    df['atr_mean250'] = df['atr'].rolling(250).mean()
    df['atr_ratio'] = df['atr'] / df['atr_mean250']

    # Daily return normalized by ATR
    df['ret_atr'] = (close - close.shift(1)) / df['atr']

    # Cost per round-trip as fraction of ATR
    # Swap cost for N days holding = N * 0.02% * price
    # Commission = 2 * 0.02 = 0.04 USD (negligible for stocks >$50)
    # We measure cost/ATR for 1-day holding
    df['cost_1d'] = (SWAP_LONG_DAILY * close + 2 * COMMISSION_PER_ORDER)
    df['cost_atr_1d'] = df['cost_1d'] / df['atr'] * 100  # as percentage

    # Forward returns (ATR-normalized, directional based on mom12)
    for fwd in FORWARD_DAYS:
        fwd_ret = (close.shift(-fwd) - close) / df['atr']
        df[f'fwd_{fwd}d'] = fwd_ret

    return df.dropna(subset=['mom12', 'atr', 'atr_ratio'])


# ====================================================================
# SELECTION: Top stocks by recent momentum
# ====================================================================

def select_top_stocks(all_data, top_n=20):
    """Select top N stocks by 12M momentum (most recent value)."""
    mom_scores = {}
    for ticker, df in all_data.items():
        df_feat = compute_features(df)
        if len(df_feat) > 0:
            last_mom = df_feat['mom12'].iloc[-1]
            mom_scores[ticker] = last_mom

    ranked = sorted(mom_scores.items(), key=lambda x: x[1], reverse=True)

    print(f"\n--- Top {top_n} by 12M Momentum (current) ---")
    print(f"  {'#':>3} {'Ticker':<8} {'Mom12M':>8} {'Price':>10}")
    print(f"  {'-'*35}")
    for i, (ticker, mom) in enumerate(ranked[:top_n]):
        price = all_data[ticker]['Close'].iloc[-1]
        print(f"  {i+1:>3} {ticker:<8} {mom:>8.1%} {price:>10.2f}")

    selected = [t for t, _ in ranked[:top_n]]
    return selected


# ====================================================================
# TEST 1: TREND -- Does Mom12M filter improve daily returns?
# ====================================================================

def test_trend(all_data, tickers):
    """Test if 12M momentum filter improves forward returns."""
    print("\n" + "=" * 90)
    print("TEST 1: TREND -- Does 12M Momentum filter improve daily returns?")
    print("=" * 90)

    results = []

    for ticker in tickers:
        df = compute_features(all_data[ticker])
        n_years = len(df) / 252

        # Baseline vs filtered
        long_mask = df['mom12'] > 0
        short_mask = df['mom12'] < 0
        pct_long = long_mask.mean() * 100

        print(f"\n  {ticker}  (mom>0: {pct_long:.1f}% of time | {n_years:.0f} years)")
        print(f"   fwd |   --- Baseline ---   |  --- LONG regime ---")
        print(f"  days |      N    Edge    WR% |      N    Edge    WR%  vs base")
        print(f"  {'-'*68}")

        best_edge = 0
        for fwd in FORWARD_DAYS:
            col = f'fwd_{fwd}d'
            base = df[col].dropna()
            long = df.loc[long_mask, col].dropna()

            if len(base) < 100 or len(long) < 100:
                continue

            base_edge = base.mean()
            long_edge = long.mean()
            base_wr = (base > 0).mean() * 100
            long_wr = (long > 0).mean() * 100
            vs = ((long_edge / base_edge) - 1) * 100 if abs(base_edge) > 1e-6 else 0

            print(f"  {fwd:>4}d | {len(base):>6} {base_edge:>8.4f} {base_wr:>6.1f}% | "
                  f"{len(long):>6} {long_edge:>8.4f} {long_wr:>6.1f}%  {vs:>+6.0f}%")

            if fwd == 1:
                best_edge = long_edge

        # Yearly consistency (fwd=1, long regime)
        df_long = df[long_mask].copy()
        df_long['year'] = df_long.index.year
        yearly = df_long.groupby('year')['fwd_1d'].agg(['count', 'mean'])
        yearly.columns = ['N', 'Edge']
        yearly['WR'] = df_long.groupby('year')['fwd_1d'].apply(lambda x: (x > 0).mean() * 100)

        pos_years = (yearly['Edge'] > 0).sum()
        total_years = len(yearly[yearly['N'] > 50])
        yearly_filt = yearly[yearly['N'] > 50]
        pos_years = (yearly_filt['Edge'] > 0).sum()

        print(f"\n  Yearly (fwd=1d, long regime): {pos_years}/{total_years} positive years")

        results.append({
            'ticker': ticker,
            'edge_1d': best_edge,
            'pct_long': pct_long,
            'pos_years': pos_years,
            'total_years': total_years,
            'n_bars': len(df),
        })

    return results


# ====================================================================
# TEST 2: VOLATILITY -- ATR regime and cost analysis
# ====================================================================

def test_volatility(all_data, tickers):
    """Test how ATR regime affects edge and cost/ATR."""
    print("\n" + "=" * 90)
    print("TEST 2: VOLATILITY -- ATR regime and cost analysis")
    print(f"  Cost model: swap {SWAP_LONG_DAILY*100:.2f}%/day + commission ${COMMISSION_PER_ORDER}/order")
    print("=" * 90)

    results = []
    thresholds = [0.8, 1.0, 1.2, 1.5, 2.0]

    for ticker in tickers:
        df = compute_features(all_data[ticker])
        # Filter to long regime only
        df_long = df[df['mom12'] > 0].copy()

        if len(df_long) < 200:
            continue

        price = df['Close'].iloc[-1]
        atr_curr = df['atr'].iloc[-1]
        atr_pct = df['atr_pct'].iloc[-1]

        print(f"\n  {ticker}  (price=${price:.2f}, ATR={atr_curr:.2f} ({atr_pct:.1f}%), "
              f"cost_1d/ATR={df_long['cost_atr_1d'].median():.2f}%)")
        print(f"    ATR>  %time       N     Edge    WR%  Cost/ATR(med)  Holding cost")
        print(f"  {'-'*72}")

        best_cost = 999
        best_edge = 0
        for thr in thresholds:
            mask = df_long['atr_ratio'] >= thr
            pct_time = mask.mean() * 100
            sub = df_long[mask]

            if len(sub) < 50:
                continue

            edge = sub['fwd_1d'].mean()
            wr = (sub['fwd_1d'] > 0).mean() * 100
            cost_med = sub['cost_atr_1d'].median()

            # Holding cost for 5 days in pct of ATR
            hold_5d_cost = (5 * SWAP_LONG_DAILY * sub['Close'] + 2 * COMMISSION_PER_ORDER) / sub['atr']
            hold_5d_med = hold_5d_cost.median() * 100

            print(f"    {thr:.1f}x  {pct_time:5.1f}% {len(sub):>6}  {edge:>8.4f} "
                  f"{wr:>6.1f}%    {cost_med:>6.2f}%       {hold_5d_med:.2f}% (5d)")

            if cost_med < best_cost:
                best_cost = cost_med
                best_edge = edge

        results.append({
            'ticker': ticker,
            'price': price,
            'atr_pct': atr_pct,
            'cost_atr_1d': df_long['cost_atr_1d'].median(),
            'best_cost': best_cost,
            'best_edge': best_edge,
        })

    return results


# ====================================================================
# TEST 3: HOLDING -- Forward return curve
# ====================================================================

def test_holding(all_data, tickers):
    """Test forward return curve: does edge grow (trend) or decay?"""
    print("\n" + "=" * 90)
    print("TEST 3: HOLDING -- Does edge grow (trend) or decay (mean-reversion)?")
    print("  Filtered by Mom12 > 0 (long regime). Edge = ATR-normalized return.")
    print("=" * 90)

    results = []

    for ticker in tickers:
        df = compute_features(all_data[ticker])
        df_long = df[df['mom12'] > 0].copy()

        if len(df_long) < 200:
            continue

        print(f"\n  {ticker}")
        print(f"   fwd       N     Edge    WR%  Edge/day  Cost(swap)  Net/day   Profile")
        print(f"  {'-'*75}")

        edges = []
        for fwd in FORWARD_DAYS:
            col = f'fwd_{fwd}d'
            ret = df_long[col].dropna()
            if len(ret) < 100:
                continue

            edge = ret.mean()
            wr = (ret > 0).mean() * 100
            edge_per_day = edge / fwd

            # Swap cost for this holding period (ATR-normalized)
            swap_cost = (fwd * SWAP_LONG_DAILY * df_long['Close'] + 2 * COMMISSION_PER_ORDER) / df_long['atr']
            swap_med = swap_cost.median()
            net_per_day = edge_per_day - swap_med / fwd

            profile = ""
            if fwd == FORWARD_DAYS[-1]:
                if len(edges) >= 2 and edges[-1] > edges[0] * 0.8:
                    profile = "TREND"
                else:
                    profile = "DECAY"

            edges.append(edge)

            print(f"  {fwd:>4}d {len(ret):>6}  {edge:>8.4f} {wr:>6.1f}% "
                  f"{edge_per_day:>8.4f}  {swap_med:>8.4f}   {net_per_day:>+8.4f}   {profile}")

        if edges:
            results.append({
                'ticker': ticker,
                'edge_1d': edges[0] if edges else 0,
                'edge_max': max(edges) if edges else 0,
                'best_fwd': FORWARD_DAYS[edges.index(max(edges))] if edges else 0,
                'profile': 'TREND' if len(edges) >= 2 and edges[-1] > edges[0] * 0.8 else 'DECAY',
            })

    return results


# ====================================================================
# SUMMARY
# ====================================================================

def print_summary(trend_res, vol_res, hold_res):
    """Print global summary with pass/fail."""
    print("\n" + "=" * 90)
    print("GLOBAL SUMMARY -- Stock Momentum Pre-Study")
    print("=" * 90)

    # Merge results
    tickers = [r['ticker'] for r in trend_res]

    vol_dict = {r['ticker']: r for r in vol_res}
    hold_dict = {r['ticker']: r for r in hold_res}

    print(f"\n  {'Ticker':<8} {'Edge/d':>7} {'YR+':>5} {'Cost/ATR':>9} "
          f"{'Profile':>8} {'Trend':>6} {'Cost':>6} {'Hold':>6} {'TOTAL':>6}")
    print(f"  {'-'*72}")

    for t in trend_res:
        tk = t['ticker']
        v = vol_dict.get(tk, {})
        h = hold_dict.get(tk, {})

        edge = t.get('edge_1d', 0)
        yr = f"{t.get('pos_years', 0)}/{t.get('total_years', 0)}"
        cost = v.get('cost_atr_1d', 99)
        profile = h.get('profile', '?')

        # Pass/fail criteria
        # Trend: edge > 0 AND >50% years positive
        trend_pass = edge > 0 and t.get('pos_years', 0) > t.get('total_years', 1) * 0.5
        # Cost: median cost/ATR < 5% for 1-day (stocks are cheaper than indices)
        cost_pass = cost < 5.0
        # Holding: TREND profile
        hold_pass = profile == 'TREND'

        total = trend_pass and cost_pass and hold_pass

        print(f"  {tk:<8} {edge:>7.4f} {yr:>5} {cost:>8.2f}% "
              f"{profile:>8} {'✅' if trend_pass else '❌':>6} "
              f"{'✅' if cost_pass else '❌':>6} {'✅' if hold_pass else '❌':>6} "
              f"{'✅' if total else '❌':>6}")


# ====================================================================
# MAIN
# ====================================================================

def parse_args():
    p = argparse.ArgumentParser(description="Stock Momentum Pre-Study")
    p.add_argument('--stocks', nargs='+', help='Specific tickers to test')
    p.add_argument('--universe', choices=['ndx', 'dj30', 'sp500', 'sp500full'],
                   default='ndx',
                   help='Stock universe: ndx, dj30, sp500 (legacy ~100), sp500full (~503)')
    p.add_argument('--top', type=int, default=20, help='Top N stocks by momentum (default: 20)')
    p.add_argument('--years', type=int, default=DOWNLOAD_YEARS, help='Years of data to download')
    p.add_argument('--exclude-current', action='store_true',
                   help='Exclude current ALTAIR assets (NDX-7 + DJ30-5)')
    p.add_argument('--exclude-analyzed', action='store_true',
                   help='Exclude all previously analyzed stocks (NDX100+DJ30+SP500 top-100)')
    return p.parse_args()


def main():
    args = parse_args()

    print("=" * 90)
    print("STOCK MOMENTUM PRE-STUDY (Daily)")
    print("=" * 90)
    print(f"Cost model: swap {SWAP_LONG_DAILY*100:.2f}%/day long + commission ${COMMISSION_PER_ORDER}/order")
    print(f"Focus: LONGS only (trend-following)")
    print(f"Mom lookback: {MOM_DAYS} trading days")
    print(f"ATR period: {ATR_PERIOD} bars")
    print(f"Forward days: {FORWARD_DAYS}")

    if args.stocks:
        # Download specified tickers
        tickers_to_download = args.stocks
    else:
        # Download from selected universe
        if args.universe == 'sp500full':
            tickers_to_download = list(SP500_FULL_TICKERS)
            print(f"Universe: S&P 500 FULL ({len(SP500_FULL_TICKERS)} stocks)")
        elif args.universe == 'sp500':
            tickers_to_download = list(SP500_TICKERS)
            print(f"Universe: S&P 500 top ({len(SP500_TICKERS)} stocks)")
        elif args.universe == 'dj30':
            tickers_to_download = list(DJ30_TICKERS)
            print(f"Universe: Dow Jones 30 ({len(DJ30_TICKERS)} stocks)")
        else:
            tickers_to_download = list(NDX100_TICKERS)
            print(f"Universe: Nasdaq 100 ({len(NDX100_TICKERS)} stocks)")

    # Exclude current ALTAIR assets if requested
    if args.exclude_current:
        before = len(tickers_to_download)
        tickers_to_download = [t for t in tickers_to_download
                               if t not in ALTAIR_CURRENT]
        excluded = before - len(tickers_to_download)
        if excluded > 0:
            print(f"Excluded {excluded} current ALTAIR assets: "
                  f"{', '.join(t for t in ALTAIR_CURRENT if t not in tickers_to_download)}")
            print(f"Remaining: {len(tickers_to_download)} stocks")

    # Exclude all previously analyzed stocks if requested
    if args.exclude_analyzed:
        before = len(tickers_to_download)
        tickers_to_download = [t for t in tickers_to_download
                               if t not in ALREADY_ANALYZED]
        excluded = before - len(tickers_to_download)
        if excluded > 0:
            print(f"Excluded {excluded} already-analyzed stocks "
                  f"(NDX100 + DJ30 + SP500 top-100)")
            print(f"Remaining: {len(tickers_to_download)} stocks")

    all_data = download_stock_data(tickers_to_download, years=args.years)

    if not all_data:
        print("\nERROR: No data loaded. Check internet connection.")
        sys.exit(1)

    # Select stocks to study
    if args.stocks:
        study_tickers = [t for t in args.stocks if t in all_data]
    else:
        study_tickers = select_top_stocks(all_data, top_n=args.top)

    if not study_tickers:
        print("\nERROR: No stocks passed the data filter.")
        sys.exit(1)

    print(f"\nStudying {len(study_tickers)} stocks: {', '.join(study_tickers)}")

    # Run tests
    trend_res = test_trend(all_data, study_tickers)
    vol_res = test_volatility(all_data, study_tickers)
    hold_res = test_holding(all_data, study_tickers)

    # Summary
    print_summary(trend_res, vol_res, hold_res)


if __name__ == '__main__':
    main()
