"""
Debug script para Spectral Entropy - encontrar donde se pierden los datos
"""
import pandas as pd
import numpy as np
from scipy.signal import periodogram

# 1. Cargar datos
print("=" * 60)
print("1. CARGANDO DATOS")
print("=" * 60)

df = pd.read_csv('data/EURUSD_5m_5Yea.csv')
# Combinar Date y Time
df['datetime'] = pd.to_datetime(df['Date'].astype(str) + ' ' + df['Time'])
df.columns = df.columns.str.lower()  # Normalize column names
df = df[(df['datetime'] >= '2025-01-01') & (df['datetime'] < '2025-02-01')]
print(f"Datos 5m: {len(df)} barras")
print(f"Rango: {df['datetime'].min()} a {df['datetime'].max()}")
print(f"Primeros closes: {df['close'].head(10).tolist()}")

# 2. Resamplear a 60m
print("\n" + "=" * 60)
print("2. RESAMPLEANDO A 60M")
print("=" * 60)

df.set_index('datetime', inplace=True)
df_60m = df.resample('60min').agg({
    'open': 'first',
    'high': 'max',
    'low': 'min',
    'close': 'last',
    'volume': 'sum'
}).dropna()

print(f"Datos 60m: {len(df_60m)} barras")
print(f"Primeros closes 60m: {df_60m['close'].head(10).tolist()}")

# 3. Calcular SE manualmente
print("\n" + "=" * 60)
print("3. CALCULANDO SE MANUALMENTE")
print("=" * 60)

def calculate_se(prices):
    """Calcula Spectral Entropy."""
    if len(prices) < 4:
        return 1.0
    
    try:
        _, psd = periodogram(prices)
        total_power = np.sum(psd)
        if total_power <= 0:
            return 1.0
        
        psd_norm = psd / total_power
        psd_norm = psd_norm[psd_norm > 0]
        if len(psd_norm) == 0:
            return 1.0
        
        entropy = -np.sum(psd_norm * np.log2(psd_norm + 1e-12))
        max_entropy = np.log2(len(psd_norm))
        if max_entropy <= 0:
            return 1.0
        
        return float(min(max(entropy / max_entropy, 0.0), 1.0))
    except Exception as e:
        print(f"  Error: {e}")
        return 1.0

# Calcular SE con ventana de 30 barras
period = 30
closes_60m = df_60m['close'].values
se_values = []

print(f"Calculando SE con period={period} sobre {len(closes_60m)} barras de 60m...")

for i in range(period, len(closes_60m)):
    window = closes_60m[i-period:i+1]
    se = calculate_se(window)
    se_values.append(se)
    
    # Print primeros 10
    if i < period + 10:
        print(f"  Barra {i}: window_size={len(window)}, SE={se:.4f}")

print(f"\nTotal SE calculados: {len(se_values)}")
print(f"SE min: {min(se_values):.4f}")
print(f"SE max: {max(se_values):.4f}")
print(f"SE mean: {np.mean(se_values):.4f}")
print(f"SE std: {np.std(se_values):.4f}")

# 4. Distribucion de SE
print("\n" + "=" * 60)
print("4. DISTRIBUCION DE SE")
print("=" * 60)

bins = [0.0, 0.7, 0.8, 0.85, 0.9, 0.92, 0.95, 1.0]
hist, _ = np.histogram(se_values, bins=bins)
for i in range(len(bins)-1):
    pct = hist[i] / len(se_values) * 100
    print(f"  {bins[i]:.2f}-{bins[i+1]:.2f}: {hist[i]:>5} ({pct:>5.1f}%)")

# 5. Primeros 20 valores de SE
print("\n" + "=" * 60)
print("5. PRIMEROS 20 VALORES DE SE")
print("=" * 60)
for i, se in enumerate(se_values[:20]):
    print(f"  {i+period}: SE={se:.4f}")

print("\n" + "=" * 60)
print("DEBUG COMPLETO")
print("=" * 60)
