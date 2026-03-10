"""
Quick correlation check between two forex pairs.
Usage: python tools/check_correlation.py XAUUSD USDJPY
       python tools/check_correlation.py GBPUSD USDCHF
       python tools/check_correlation.py EURUSD USDCHF
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def load_csv(symbol):
    """Load Dukascopy CSV and return DataFrame with datetime index."""
    path = Path(f'data/{symbol}_5m_5Yea.csv')
    if not path.exists():
        print(f'File not found: {path}')
        sys.exit(1)

    df = pd.read_csv(
        path,
        header=0,
        names=['date', 'time', 'open', 'high', 'low', 'close', 'volume'],
        skiprows=1,
    )
    df['datetime'] = pd.to_datetime(
        df['date'].astype(str) + ' ' + df['time'],
        format='%Y%m%d %H:%M:%S',
    )
    df.set_index('datetime', inplace=True)
    return df[['close']]


def main():
    if len(sys.argv) < 3:
        print('Usage: python tools/check_correlation.py SYMBOL1 SYMBOL2')
        print('Example: python tools/check_correlation.py XAUUSD USDJPY')
        sys.exit(1)

    sym1 = sys.argv[1].upper()
    sym2 = sys.argv[2].upper()

    print(f'Loading {sym1} and {sym2}...')
    df1 = load_csv(sym1)
    df2 = load_csv(sym2)

    # Align on common timestamps
    merged = df1.join(df2, lsuffix=f'_{sym1}', rsuffix=f'_{sym2}', how='inner')
    merged.columns = [sym1, sym2]
    print(f'Common bars: {len(merged):,}')
    print(f'Period: {merged.index[0]} to {merged.index[-1]}')

    # Overall correlation (close prices)
    corr_price = merged[sym1].corr(merged[sym2])
    print(f'\n=== PRICE CORRELATION (full period) ===')
    print(f'{sym1} vs {sym2}: {corr_price:.4f}')

    # Returns correlation (more meaningful for trading)
    returns = merged.pct_change().dropna()
    corr_returns = returns[sym1].corr(returns[sym2])
    print(f'\n=== RETURNS CORRELATION (full period) ===')
    print(f'{sym1} vs {sym2}: {corr_returns:.4f}')

    # Rolling correlation (1 month = ~8640 bars on 5min, use ~6000 for trading days)
    window = 6000  # ~1 month of 5min forex bars
    rolling_corr = returns[sym1].rolling(window).corr(returns[sym2])
    rolling_clean = rolling_corr.dropna()

    print(f'\n=== ROLLING CORRELATION (window={window} bars, ~1 month) ===')
    print(f'Median:    {rolling_clean.median():.4f}')
    print(f'Mean:      {rolling_clean.mean():.4f}')
    print(f'Std:       {rolling_clean.std():.4f}')
    print(f'Min:       {rolling_clean.min():.4f}')
    print(f'Max:       {rolling_clean.max():.4f}')
    print(f'P5:        {rolling_clean.quantile(0.05):.4f}')
    print(f'P25:       {rolling_clean.quantile(0.25):.4f}')
    print(f'P75:       {rolling_clean.quantile(0.75):.4f}')
    print(f'P95:       {rolling_clean.quantile(0.95):.4f}')

    # Yearly breakdown
    print(f'\n=== YEARLY RETURNS CORRELATION ===')
    print(f'{"Year":<6} {"Corr":>8} {"Bars":>10}')
    print('-' * 26)
    for year in sorted(returns.index.year.unique()):
        yr = returns[returns.index.year == year]
        if len(yr) > 100:
            c = yr[sym1].corr(yr[sym2])
            print(f'{year:<6} {c:>8.4f} {len(yr):>10,}')

    # Gate check
    print(f'\n=== GATE CHECK ===')
    median_corr = rolling_clean.median()
    if abs(median_corr) >= 0.75:
        print(f'PASS: |median| = {abs(median_corr):.4f} >= 0.75 --> promising')
    elif abs(median_corr) >= 0.65:
        print(f'CAUTION: |median| = {abs(median_corr):.4f} in [0.65, 0.75) --> moderate risk')
    else:
        print(f'FAIL: |median| = {abs(median_corr):.4f} < 0.65 --> correlation too weak')


if __name__ == '__main__':
    main()
