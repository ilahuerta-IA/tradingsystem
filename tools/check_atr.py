"""Quick ATR check for index viability analysis."""
import pandas as pd
import numpy as np
import sys

files = {
    'EUR50': 'data/EUR50_5m_5Yea.csv',
    'UK100': 'data/UK100_5m_15Yea.csv',
    'GDAXI': 'data/GDAXI_5m_15Yea.csv',
    'NI225': 'data/NI225_5m_15Yea.csv',
    'SP500': 'data/SP500_5m_15Yea.csv',
}

spreads = {
    'EUR50': 0.9,
    'UK100': 1.0,
    'GDAXI': 0.8,
    'NI225': 3.0,
    'SP500': 0.6,
}

print(f"{'Index':<8} {'Price':>8} {'ATR_H4':>8} {'Spread':>7} {'Sprd/ATR':>9} {'Viable':>8}")
print("-" * 58)

for name, path in files.items():
    try:
        df = pd.read_csv(path)
        df['datetime'] = pd.to_datetime(df['Date'].astype(str) + ' ' + df['Time'])
        df.set_index('datetime', inplace=True)
        h4 = df.resample('4h').agg({
            'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last'
        }).dropna()

        high = h4['High']
        low = h4['Low']
        close = h4['Close']
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs()
        ], axis=1).max(axis=1)
        atr24 = tr.rolling(24).mean().dropna()

        price = h4['Close'].iloc[-100:].mean()
        atr_mean = atr24.mean()
        spread = spreads[name]
        ratio = spread / atr_mean * 100

        viable = 'YES' if ratio < 1.5 else ('MAYBE' if ratio < 2.0 else 'NO')
        print(f"{name:<8} {price:>8.0f} {atr_mean:>8.2f} {spread:>7.1f} {ratio:>8.2f}% {viable:>8}")
    except Exception as e:
        print(f"{name:<8} ERROR: {e}")
