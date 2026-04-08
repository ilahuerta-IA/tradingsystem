"""Quick script to rank all assets by Spread/ATR(H4) from actual data."""
import pandas as pd
import numpy as np
import os

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Spreads reales del broker (puntos)
SPREADS = {
    'SP500': 0.80, 'NDX': 1.80, 'GDAXI': 2.00, 'NI225': 12.0,
    'UK100': 1.00, 'EUR50': 1.50, 'AUS200': 3.00,
    'XAUUSD': 0.35, 'EURUSD': 0.00012, 'USDJPY': 0.014,
    'USDCHF': 0.00015, 'AUDUSD': 0.00015, 'NZDUSD': 0.00018,
    'GLD': 0.15, 'DIA': 0.20, 'XLE': 0.05, 'TLT': 0.10,
    'EWZ': 0.10, 'XLU': 0.05, 'SLV': 0.05,
}

ASSET_FILES = {
    'NI225':  ('data/NI225_5m_15Yea.csv',  'data/NI225_5m_5Yea.csv'),
    'GDAXI':  ('data/GDAXI_5m_15Yea.csv',  'data/GDAXI_5m_5Yea.csv'),
    'SP500':  ('data/SP500_5m_15Yea.csv',  'data/SP500_5m_5Yea.csv'),
    'UK100':  ('data/UK100_5m_15Yea.csv',  'data/UK100_5m_5Yea.csv'),
    'NDX':    ('data/NDX_5m_15Yea.csv',    'data/NDX_5m_5Yea.csv'),
    'EUR50':  ('data/EUR50_5m_5Yea.csv',),
    'AUS200': ('data/AUS200_5m_5Yea.csv',),
    'XAUUSD': ('data/XAUUSD_5m_5Yea.csv',),
    'SLV':    ('data/SLV_5m_5Yea.csv',),
    'TLT':    ('data/TLT_5m_5Yea.csv',),
    'EURUSD': ('data/EURUSD_5m_5Yea.csv',),
    'USDJPY': ('data/USDJPY_5m_5Yea.csv',),
    'USDCHF': ('data/USDCHF_5m_5Yea.csv',),
    'AUDUSD': ('data/AUDUSD_5m_5Yea.csv',),
    'NZDUSD': ('data/NZDUSD_5m_5Yea.csv',),
    'GLD':    ('data/GLD_5m_5Yea.csv',),
    'DIA':    ('data/DIA_5m_5Yea.csv',),
    'XLE':    ('data/XLE_5m_5Yea.csv',),
    'EWZ':    ('data/EWZ_5m_5Yea.csv',),
    'XLU':    ('data/XLU_5m_5Yea.csv',),
}

results = []
for sym, paths in ASSET_FILES.items():
    path = None
    for p in paths:
        if os.path.exists(p):
            path = p
            break
    if not path:
        continue

    df = pd.read_csv(path)
    df['datetime'] = pd.to_datetime(df['Date'].astype(str) + ' ' + df['Time'])
    df.set_index('datetime', inplace=True)

    h4 = df.resample('240min').agg({
        'Open': 'first', 'High': 'max',
        'Low': 'min', 'Close': 'last'
    }).dropna()

    prev_c = h4['Close'].shift(1)
    tr = np.maximum(
        h4['High'] - h4['Low'],
        np.maximum(abs(h4['High'] - prev_c), abs(h4['Low'] - prev_c))
    )
    atr24 = tr.rolling(24).mean()

    atr_mean = atr24.dropna().mean()
    atr_last = atr24.dropna().iloc[-100:].mean()

    spread = SPREADS.get(sym, 0)
    ratio = (spread / atr_mean * 100) if atr_mean > 0 else 99
    ratio_recent = (spread / atr_last * 100) if atr_last > 0 else 99

    results.append({
        'symbol': sym,
        'spread': spread,
        'atr_h4_avg': atr_mean,
        'atr_h4_recent': atr_last,
        'sprd_atr_avg': ratio,
        'sprd_atr_recent': ratio_recent,
        'bars': len(h4),
        'price': h4['Close'].iloc[-1],
    })

results.sort(key=lambda x: x['sprd_atr_avg'])

print('=' * 100)
print('ASSET LIQUIDITY RANKING -- Spread/ATR(H4) from actual data')
print('=' * 100)
hdr = (f"{'Symbol':<8} {'Price':>10} {'Spread':>8} {'ATR_avg':>10} "
       f"{'ATR_rec':>10} {'S/A_avg':>8} {'S/A_rec':>8} {'Bars':>6} {'Viable':>8}")
print(hdr)
print('-' * 100)
for r in results:
    viable = 'YES' if r['sprd_atr_avg'] < 2.0 else 'MAYBE' if r['sprd_atr_avg'] < 3.0 else 'NO'
    print(f"{r['symbol']:<8} {r['price']:>10.2f} {r['spread']:>8.5f} "
          f"{r['atr_h4_avg']:>10.4f} {r['atr_h4_recent']:>10.4f} "
          f"{r['sprd_atr_avg']:>7.2f}% {r['sprd_atr_recent']:>7.2f}% "
          f"{r['bars']:>6} [{viable:>5}]")

print()
print("Legend: S/A_avg = historical | S/A_rec = last 100 bars")
print("Viable: YES (<2%) | MAYBE (2-3%) | NO (>3%)")
print()

# Summary
viable = [r for r in results if r['sprd_atr_avg'] < 2.0]
maybe = [r for r in results if 2.0 <= r['sprd_atr_avg'] < 3.0]
print(f"VIABLE (<2%): {', '.join(r['symbol'] for r in viable)}")
print(f"MAYBE (2-3%): {', '.join(r['symbol'] for r in maybe)}")
