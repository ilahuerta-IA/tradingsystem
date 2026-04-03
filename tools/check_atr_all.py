"""Quick ATR check for forex + XAUUSD viability."""
import pandas as pd
import numpy as np

files = {
    'EURUSD': ('data/EURUSD_5m_5Yea.csv', 0.00010),   # spread in price units
    'USDJPY': ('data/USDJPY_5m_5Yea.csv', 0.010),
    'AUDUSD': ('data/AUDUSD_5m_5Yea.csv', 0.00020),
    'USDCHF': ('data/USDCHF_5m_5Yea.csv', 0.00015),
    'USDCAD': ('data/USDCAD_5m_5Yea.csv', 0.00015),
    'XAUUSD': ('data/XAUUSD_5m_5Yea.csv', 0.30),       # gold spread ~30 cents
    'GDAXI':  ('data/GDAXI_5m_15Yea.csv', 0.8),
    'NI225':  ('data/NI225_5m_15Yea.csv', 3.0),
    'NDX':    (None, 0.8),  # no data yet
}

print(f"{'Asset':<10} {'Price':>8} {'ATR_H4':>10} {'Spread':>10} {'Sprd/ATR':>9} {'Viable':>8}")
print("-" * 62)

for name, (path, spread) in files.items():
    if path is None:
        print(f"{name:<10} {'N/A':>8} {'N/A':>10} {spread:>10} {'N/A':>9} {'NO DATA':>8}")
        continue
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
        ratio = spread / atr_mean * 100

        viable = 'YES' if ratio < 1.5 else ('MAYBE' if ratio < 2.0 else 'NO')
        print(f"{name:<10} {price:>8.2f} {atr_mean:>10.4f} {spread:>10.4f} {ratio:>8.2f}% {viable:>8}")
    except Exception as e:
        print(f"{name:<10} ERROR: {e}")
