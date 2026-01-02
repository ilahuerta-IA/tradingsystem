"""
Análisis profundo del log de trades para identificar filtros óptimos
"""
import re
from collections import defaultdict
from datetime import datetime

# Datos parseados del log
trades = []

log_content = open(r'logs\EURJPY_PRO_20260102_122906.txt', 'r').read()

# Regex para extraer datos de cada trade
entry_pattern = r'ENTRY #(\d+)\nTime: (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?ATR Current: ([\d.]+).*?Angle Current: ([\d.]+).*?SL Pips: ([\d.]+)'
exit_pattern = r'EXIT #(\d+)\nTime: (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?Exit Reason: (\w+).*?P&L: ([-\d.]+)'

entries = re.findall(entry_pattern, log_content, re.DOTALL)
exits = re.findall(exit_pattern, log_content, re.DOTALL)

for entry, exit_data in zip(entries, exits):
    trade_num, entry_time, atr, angle, sl_pips = entry
    _, exit_time, exit_reason, pnl = exit_data
    
    entry_dt = datetime.strptime(entry_time, '%Y-%m-%d %H:%M:%S')
    trades.append({
        'num': int(trade_num),
        'entry_time': entry_dt,
        'hour': entry_dt.hour,
        'day': entry_dt.strftime('%A'),
        'atr': float(atr),
        'angle': float(angle),
        'sl_pips': float(sl_pips),
        'exit_reason': exit_reason,
        'pnl': float(pnl),
        'is_win': exit_reason == 'TAKE_PROFIT'
    })

print("=" * 80)
print("ANÁLISIS PROFUNDO DE TRADES - EURJPY PRO")
print("=" * 80)
print(f"\nTotal Trades: {len(trades)}")
print(f"Wins: {sum(1 for t in trades if t['is_win'])}")
print(f"Losses: {sum(1 for t in trades if not t['is_win'])}")
print(f"Win Rate: {sum(1 for t in trades if t['is_win'])/len(trades)*100:.1f}%")
print(f"PF Actual: {sum(t['pnl'] for t in trades if t['pnl'] > 0) / abs(sum(t['pnl'] for t in trades if t['pnl'] < 0)):.2f}")

# ============================================================================
# 1. ANÁLISIS POR HORA DE ENTRADA
# ============================================================================
print("\n" + "=" * 80)
print("1. ANÁLISIS POR HORA DE ENTRADA")
print("=" * 80)

hourly_stats = defaultdict(lambda: {'trades': 0, 'wins': 0, 'pnl': 0, 'losses': []})
for t in trades:
    h = t['hour']
    hourly_stats[h]['trades'] += 1
    hourly_stats[h]['pnl'] += t['pnl']
    if t['is_win']:
        hourly_stats[h]['wins'] += 1
    else:
        hourly_stats[h]['losses'].append(t['pnl'])

print(f"\n{'Hora':<6} {'Trades':<8} {'Wins':<6} {'WR%':<8} {'PnL':<12} {'PF':<8} {'Recomendación'}")
print("-" * 80)

for hour in sorted(hourly_stats.keys()):
    stats = hourly_stats[hour]
    wr = (stats['wins'] / stats['trades'] * 100) if stats['trades'] > 0 else 0
    gross_profit = sum(t['pnl'] for t in trades if t['hour'] == hour and t['pnl'] > 0)
    gross_loss = abs(sum(t['pnl'] for t in trades if t['hour'] == hour and t['pnl'] < 0))
    pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    rec = "✓ MANTENER" if pf >= 1.5 and stats['trades'] >= 5 else ("⚠ REVISAR" if pf >= 1.0 else "✗ FILTRAR")
    print(f"{hour:02d}:00  {stats['trades']:<8} {stats['wins']:<6} {wr:<7.1f}% ${stats['pnl']:<10.0f} {pf:<7.2f} {rec}")

# Mejor rango horario
print("\n📊 RESUMEN HORARIO:")
good_hours = [h for h, s in hourly_stats.items() if s['trades'] >= 5 and 
              sum(t['pnl'] for t in trades if t['hour'] == h and t['pnl'] > 0) / 
              max(abs(sum(t['pnl'] for t in trades if t['hour'] == h and t['pnl'] < 0)), 1) >= 1.5]
bad_hours = [h for h, s in hourly_stats.items() if s['trades'] >= 3 and 
             sum(t['pnl'] for t in trades if t['hour'] == h and t['pnl'] > 0) / 
             max(abs(sum(t['pnl'] for t in trades if t['hour'] == h and t['pnl'] < 0)), 1) < 1.0]
print(f"  Horas productivas (PF >= 1.5): {sorted(good_hours)}")
print(f"  Horas a filtrar (PF < 1.0): {sorted(bad_hours)}")

# ============================================================================
# 2. ANÁLISIS POR SL PIPS (RANGOS)
# ============================================================================
print("\n" + "=" * 80)
print("2. ANÁLISIS POR SL PIPS (RANGOS)")
print("=" * 80)

sl_ranges = [
    (0, 15, "< 15 pips"),
    (15, 20, "15-20 pips"),
    (20, 25, "20-25 pips"),
    (25, 30, "25-30 pips"),
    (30, 35, "30-35 pips"),
    (35, 40, "35-40 pips"),
    (40, 50, "40-50 pips"),
    (50, 100, "> 50 pips")
]

print(f"\n{'Rango SL':<14} {'Trades':<8} {'Wins':<6} {'WR%':<8} {'PnL':<12} {'PF':<8} {'Recomendación'}")
print("-" * 80)

for sl_min, sl_max, label in sl_ranges:
    range_trades = [t for t in trades if sl_min <= t['sl_pips'] < sl_max]
    if not range_trades:
        continue
    
    wins = sum(1 for t in range_trades if t['is_win'])
    total = len(range_trades)
    wr = (wins / total * 100) if total > 0 else 0
    pnl = sum(t['pnl'] for t in range_trades)
    gross_profit = sum(t['pnl'] for t in range_trades if t['pnl'] > 0)
    gross_loss = abs(sum(t['pnl'] for t in range_trades if t['pnl'] < 0))
    pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    rec = "✓ MANTENER" if pf >= 1.5 else ("⚠ REVISAR" if pf >= 1.0 else "✗ FILTRAR")
    print(f"{label:<14} {total:<8} {wins:<6} {wr:<7.1f}% ${pnl:<10.0f} {pf:<7.2f} {rec}")

# ============================================================================
# 3. ANÁLISIS POR ÁNGULO (RANGOS)
# ============================================================================
print("\n" + "=" * 80)
print("3. ANÁLISIS POR ÁNGULO (RANGOS)")
print("=" * 80)

angle_ranges = [
    (45, 55, "45-55°"),
    (55, 65, "55-65°"),
    (65, 75, "65-75°"),
    (75, 85, "75-85°"),
    (85, 95, "85-95°")
]

print(f"\n{'Rango Angle':<14} {'Trades':<8} {'Wins':<6} {'WR%':<8} {'PnL':<12} {'PF':<8} {'Recomendación'}")
print("-" * 80)

for ang_min, ang_max, label in angle_ranges:
    range_trades = [t for t in trades if ang_min <= t['angle'] < ang_max]
    if not range_trades:
        continue
    
    wins = sum(1 for t in range_trades if t['is_win'])
    total = len(range_trades)
    wr = (wins / total * 100) if total > 0 else 0
    pnl = sum(t['pnl'] for t in range_trades)
    gross_profit = sum(t['pnl'] for t in range_trades if t['pnl'] > 0)
    gross_loss = abs(sum(t['pnl'] for t in range_trades if t['pnl'] < 0))
    pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    rec = "✓ MANTENER" if pf >= 1.5 else ("⚠ REVISAR" if pf >= 1.0 else "✗ FILTRAR")
    print(f"{label:<14} {total:<8} {wins:<6} {wr:<7.1f}% ${pnl:<10.0f} {pf:<7.2f} {rec}")

# ============================================================================
# 4. ANÁLISIS POR ATR (RANGOS)
# ============================================================================
print("\n" + "=" * 80)
print("4. ANÁLISIS POR ATR (RANGOS)")
print("=" * 80)

atr_ranges = [
    (0.03, 0.04, "0.030-0.040"),
    (0.04, 0.05, "0.040-0.050"),
    (0.05, 0.06, "0.050-0.060"),
    (0.06, 0.07, "0.060-0.070"),
    (0.07, 0.08, "0.070-0.080"),
    (0.08, 0.09, "0.080-0.090"),
    (0.09, 0.15, "> 0.090")
]

print(f"\n{'Rango ATR':<14} {'Trades':<8} {'Wins':<6} {'WR%':<8} {'PnL':<12} {'PF':<8} {'Recomendación'}")
print("-" * 80)

for atr_min, atr_max, label in atr_ranges:
    range_trades = [t for t in trades if atr_min <= t['atr'] < atr_max]
    if not range_trades:
        continue
    
    wins = sum(1 for t in range_trades if t['is_win'])
    total = len(range_trades)
    wr = (wins / total * 100) if total > 0 else 0
    pnl = sum(t['pnl'] for t in range_trades)
    gross_profit = sum(t['pnl'] for t in range_trades if t['pnl'] > 0)
    gross_loss = abs(sum(t['pnl'] for t in range_trades if t['pnl'] < 0))
    pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    rec = "✓ MANTENER" if pf >= 1.5 else ("⚠ REVISAR" if pf >= 1.0 else "✗ FILTRAR")
    print(f"{label:<14} {total:<8} {wins:<6} {wr:<7.1f}% ${pnl:<10.0f} {pf:<7.2f} {rec}")

# ============================================================================
# 5. ANÁLISIS POR DÍA DE LA SEMANA
# ============================================================================
print("\n" + "=" * 80)
print("5. ANÁLISIS POR DÍA DE LA SEMANA")
print("=" * 80)

day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
day_stats = defaultdict(lambda: {'trades': 0, 'wins': 0, 'pnl': 0})
for t in trades:
    d = t['day']
    day_stats[d]['trades'] += 1
    day_stats[d]['pnl'] += t['pnl']
    if t['is_win']:
        day_stats[d]['wins'] += 1

print(f"\n{'Día':<12} {'Trades':<8} {'Wins':<6} {'WR%':<8} {'PnL':<12} {'PF':<8}")
print("-" * 70)

for day in day_order:
    if day not in day_stats:
        continue
    stats = day_stats[day]
    wr = (stats['wins'] / stats['trades'] * 100) if stats['trades'] > 0 else 0
    gross_profit = sum(t['pnl'] for t in trades if t['day'] == day and t['pnl'] > 0)
    gross_loss = abs(sum(t['pnl'] for t in trades if t['day'] == day and t['pnl'] < 0))
    pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    print(f"{day:<12} {stats['trades']:<8} {stats['wins']:<6} {wr:<7.1f}% ${stats['pnl']:<10.0f} {pf:<7.2f}")

# ============================================================================
# 6. COMBINACIONES ÓPTIMAS
# ============================================================================
print("\n" + "=" * 80)
print("6. SIMULACIÓN DE FILTROS COMBINADOS")
print("=" * 80)

def simulate_filter(trades, hour_filter=None, sl_min=None, sl_max=None, angle_min=None, angle_max=None, atr_min=None, atr_max=None):
    filtered = trades.copy()
    if hour_filter:
        filtered = [t for t in filtered if t['hour'] in hour_filter]
    if sl_min is not None:
        filtered = [t for t in filtered if t['sl_pips'] >= sl_min]
    if sl_max is not None:
        filtered = [t for t in filtered if t['sl_pips'] <= sl_max]
    if angle_min is not None:
        filtered = [t for t in filtered if t['angle'] >= angle_min]
    if angle_max is not None:
        filtered = [t for t in filtered if t['angle'] <= angle_max]
    if atr_min is not None:
        filtered = [t for t in filtered if t['atr'] >= atr_min]
    if atr_max is not None:
        filtered = [t for t in filtered if t['atr'] <= atr_max]
    
    if not filtered:
        return None
    
    wins = sum(1 for t in filtered if t['is_win'])
    total = len(filtered)
    gross_profit = sum(t['pnl'] for t in filtered if t['pnl'] > 0)
    gross_loss = abs(sum(t['pnl'] for t in filtered if t['pnl'] < 0))
    pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    pnl = sum(t['pnl'] for t in filtered)
    
    return {
        'trades': total,
        'wins': wins,
        'wr': wins/total*100,
        'pf': pf,
        'pnl': pnl
    }

# Escenarios de filtro
scenarios = [
    ("SIN FILTROS (actual)", {}),
    ("Filtrar horas 05-06", {'hour_filter': list(range(7, 19))}),
    ("Solo horas 07-15", {'hour_filter': list(range(7, 16))}),
    ("SL >= 20 pips", {'sl_min': 20}),
    ("SL 20-35 pips", {'sl_min': 20, 'sl_max': 35}),
    ("SL 15-30 pips", {'sl_min': 15, 'sl_max': 30}),
    ("Ángulo 55-85°", {'angle_min': 55, 'angle_max': 85}),
    ("Ángulo 60-80°", {'angle_min': 60, 'angle_max': 80}),
    ("ATR 0.04-0.07", {'atr_min': 0.04, 'atr_max': 0.07}),
    ("ATR 0.05-0.08", {'atr_min': 0.05, 'atr_max': 0.08}),
    ("COMBO: SL 20-35 + Angle 55-85", {'sl_min': 20, 'sl_max': 35, 'angle_min': 55, 'angle_max': 85}),
    ("COMBO: SL 15-30 + ATR 0.04-0.07", {'sl_min': 15, 'sl_max': 30, 'atr_min': 0.04, 'atr_max': 0.07}),
    ("COMBO: Horas 07-15 + SL 20-35", {'hour_filter': list(range(7, 16)), 'sl_min': 20, 'sl_max': 35}),
    ("COMBO: ATR 0.05-0.08 + Angle 60-85", {'atr_min': 0.05, 'atr_max': 0.08, 'angle_min': 60, 'angle_max': 85}),
]

print(f"\n{'Escenario':<45} {'Trades':<8} {'WR%':<8} {'PF':<8} {'PnL':<12}")
print("-" * 85)

results = []
for name, params in scenarios:
    result = simulate_filter(trades, **params)
    if result:
        results.append((name, result))
        print(f"{name:<45} {result['trades']:<8} {result['wr']:<7.1f}% {result['pf']:<7.2f} ${result['pnl']:<10.0f}")

# ============================================================================
# 7. RECOMENDACIONES FINALES
# ============================================================================
print("\n" + "=" * 80)
print("7. RECOMENDACIONES FINALES")
print("=" * 80)

# Ordenar por PF manteniendo mínimo de trades
best_scenarios = sorted(
    [(n, r) for n, r in results if r['trades'] >= 50],  # Mínimo 50 trades
    key=lambda x: x[1]['pf'],
    reverse=True
)[:5]

print("\n🏆 TOP 5 MEJORES CONFIGURACIONES (min 50 trades):")
for i, (name, result) in enumerate(best_scenarios, 1):
    reduction = (1 - result['trades']/len(trades)) * 100
    print(f"\n  {i}. {name}")
    print(f"     Trades: {result['trades']} (-{reduction:.0f}% reducción)")
    print(f"     Win Rate: {result['wr']:.1f}%")
    print(f"     Profit Factor: {result['pf']:.2f}")
    print(f"     P&L: ${result['pnl']:,.0f}")

print("\n" + "=" * 80)
