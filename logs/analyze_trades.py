import re
import os
from collections import defaultdict

script_dir = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(script_dir, 'KOI_trades_20260111_163838.txt'), 'r') as f:
    content = f.read()

# Extraer todos los trades
entries = re.findall(r'ENTRY #(\d+)\nTime: (\d{4}-\d{2}-\d{2} (\d{2}):\d{2}:\d{2}).*?CCI: ([\d.]+)', content, re.DOTALL)
exits = re.findall(r'EXIT #(\d+).*?Exit Reason: (\w+).*?P&L: \$([-\d,.]+)', content, re.DOTALL)

trades = []
for entry, exit_info in zip(entries, exits):
    trade_num, entry_time, hour, cci = entry
    exit_num, reason, pnl = exit_info
    pnl = float(pnl.replace(',', ''))
    trades.append({
        'num': int(trade_num),
        'hour': int(hour),
        'cci': float(cci),
        'reason': reason,
        'pnl': pnl,
        'win': pnl > 0
    })

print(f'Total trades: {len(trades)}')
print(f'Wins: {sum(1 for t in trades if t["win"])}')
print(f'Losses: {sum(1 for t in trades if not t["win"])}')
print(f'Win Rate: {sum(1 for t in trades if t["win"])/len(trades)*100:.1f}%')
print(f'Total P&L: ${sum(t["pnl"] for t in trades):,.0f}')
print()

# Analizar por CCI
print('=== ANÁLISIS POR CCI MÁXIMO ===')
for cci_max in [150, 175, 200, 225, 250, 300, 400]:
    filtered = [t for t in trades if t['cci'] <= cci_max]
    if filtered:
        wins = sum(1 for t in filtered if t['win'])
        total_pnl = sum(t['pnl'] for t in filtered)
        gross_profit = sum(t['pnl'] for t in filtered if t['pnl'] > 0)
        gross_loss = abs(sum(t['pnl'] for t in filtered if t['pnl'] < 0))
        pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        print(f'CCI <= {cci_max:3d}: {len(filtered):3d} trades, WR={wins/len(filtered)*100:5.1f}%, PF={pf:.2f}, P&L=${total_pnl:>10,.0f}')

print()
print('=== ANÁLISIS POR HORA (UTC) ===')
by_hour = defaultdict(list)
for t in trades:
    by_hour[t['hour']].append(t)

for hour in sorted(by_hour.keys()):
    hour_trades = by_hour[hour]
    wins = sum(1 for t in hour_trades if t['win'])
    total_pnl = sum(t['pnl'] for t in hour_trades)
    gross_profit = sum(t['pnl'] for t in hour_trades if t['pnl'] > 0)
    gross_loss = abs(sum(t['pnl'] for t in hour_trades if t['pnl'] < 0))
    pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    print(f'Hora {hour:02d}: {len(hour_trades):3d} trades, WR={wins/len(hour_trades)*100:5.1f}%, PF={pf:.2f}, P&L=${total_pnl:>10,.0f}')

print()
print('=== FILTROS COMBINADOS (CCI + HORAS) ===')
# Probar eliminar horas malas
bad_hours = [23]  # La hora 23 es la única que aparece en datos diarios
# Para datos diarios, todos los trades son a las 23:59:59

# Analizar por CCI
print('\nDistribución de CCI:')
cci_ranges = [(100, 125), (125, 150), (150, 175), (175, 200), (200, 250), (250, 300), (300, 400)]
for low, high in cci_ranges:
    filtered = [t for t in trades if low <= t['cci'] < high]
    if filtered:
        wins = sum(1 for t in filtered if t['win'])
        total_pnl = sum(t['pnl'] for t in filtered)
        gross_profit = sum(t['pnl'] for t in filtered if t['pnl'] > 0)
        gross_loss = abs(sum(t['pnl'] for t in filtered if t['pnl'] < 0))
        pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        print(f'CCI {low:3d}-{high:3d}: {len(filtered):3d} trades, WR={wins/len(filtered)*100:5.1f}%, PF={pf:.2f}, P&L=${total_pnl:>10,.0f}')

# Mostrar los peores trades por CCI alto
print('\n=== TOP 10 PEORES TRADES ===')
worst = sorted(trades, key=lambda x: x['pnl'])[:10]
for t in worst:
    print(f"Trade #{t['num']}: CCI={t['cci']:.0f}, P&L=${t['pnl']:,.0f}, Reason={t['reason']}")

print('\n=== TOP 10 TRADES CON CCI MÁS ALTO ===')
highest_cci = sorted(trades, key=lambda x: x['cci'], reverse=True)[:10]
for t in highest_cci:
    print(f"Trade #{t['num']}: CCI={t['cci']:.0f}, P&L=${t['pnl']:,.0f}, Win={t['win']}")
