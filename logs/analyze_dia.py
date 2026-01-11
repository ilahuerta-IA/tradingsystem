import re
import os
from collections import defaultdict

script_dir = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(script_dir, 'KOI_trades_20260111_163838.txt'), 'r') as f:
    content = f.read()

# Extraer todos los trades con hora completa
entries = re.findall(r'ENTRY #(\d+)\nTime: (\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2}):\d{2}.*?SL Pips: ([\d.]+)\nATR: ([\d.]+)\nCCI: ([\d.]+)', content, re.DOTALL)
exits = re.findall(r'EXIT #(\d+).*?Exit Reason: (\w+).*?P&L: \$([-\d,.]+)', content, re.DOTALL)

trades = []
for entry, exit_info in zip(entries, exits):
    trade_num, date, hour, minute, sl_pips, atr, cci = entry
    exit_num, reason, pnl = exit_info
    pnl = float(pnl.replace(',', ''))
    trades.append({
        'num': int(trade_num),
        'hour': int(hour),
        'minute': int(minute),
        'sl_pips': float(sl_pips),
        'atr': float(atr),
        'cci': float(cci),
        'reason': reason,
        'pnl': pnl,
        'win': pnl > 0
    })

def calc_stats(filtered):
    if not filtered:
        return None
    wins = sum(1 for t in filtered if t['win'])
    total_pnl = sum(t['pnl'] for t in filtered)
    gross_profit = sum(t['pnl'] for t in filtered if t['pnl'] > 0)
    gross_loss = abs(sum(t['pnl'] for t in filtered if t['pnl'] < 0))
    pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    wr = wins/len(filtered)*100
    return len(filtered), wr, pf, total_pnl

print(f'Total trades: {len(trades)}')
print(f'Wins: {sum(1 for t in trades if t["win"])}')
print(f'Losses: {sum(1 for t in trades if not t["win"])}')
print(f'Win Rate: {sum(1 for t in trades if t["win"])/len(trades)*100:.1f}%')
print(f'Total P&L: ${sum(t["pnl"] for t in trades):,.0f}')
print()

# === ANÁLISIS POR CCI ===
print('=== ANÁLISIS POR CCI MÁXIMO ===')
for cci_max in [120, 130, 140, 150, 175, 200, 250, 999]:
    filtered = [t for t in trades if t['cci'] <= cci_max]
    stats = calc_stats(filtered)
    if stats:
        n, wr, pf, pnl = stats
        print(f'CCI <= {cci_max:3d}: {n:3d} trades, WR={wr:5.1f}%, PF={pf:.2f}, P&L=${pnl:>10,.0f}')

print()
print('=== DISTRIBUCIÓN POR RANGO CCI ===')
cci_ranges = [(100, 120), (120, 140), (140, 160), (160, 180), (180, 200), (200, 250), (250, 999)]
for low, high in cci_ranges:
    filtered = [t for t in trades if low <= t['cci'] < high]
    stats = calc_stats(filtered)
    if stats:
        n, wr, pf, pnl = stats
        print(f'CCI {low:3d}-{high:3d}: {n:3d} trades, WR={wr:5.1f}%, PF={pf:.2f}, P&L=${pnl:>10,.0f}')

# === ANÁLISIS POR HORA ===
print()
print('=== ANÁLISIS POR HORA (UTC) ===')
by_hour = defaultdict(list)
for t in trades:
    by_hour[t['hour']].append(t)

for hour in sorted(by_hour.keys()):
    stats = calc_stats(by_hour[hour])
    if stats:
        n, wr, pf, pnl = stats
        print(f'Hora {hour:02d}: {n:3d} trades, WR={wr:5.1f}%, PF={pf:.2f}, P&L=${pnl:>10,.0f}')

# === ANÁLISIS POR RANGO DE HORAS ===
print()
print('=== FILTROS POR RANGO DE HORAS ===')
hour_ranges = [(14, 17), (14, 18), (14, 19), (14, 20), (15, 18), (15, 19), (16, 19), (17, 20)]
for h_start, h_end in hour_ranges:
    filtered = [t for t in trades if h_start <= t['hour'] < h_end]
    stats = calc_stats(filtered)
    if stats:
        n, wr, pf, pnl = stats
        print(f'Horas {h_start:02d}-{h_end:02d}: {n:3d} trades, WR={wr:5.1f}%, PF={pf:.2f}, P&L=${pnl:>10,.0f}')

# === ANÁLISIS POR ATR ===
print()
print('=== ANÁLISIS POR RANGO ATR ===')
atr_ranges = [(0.20, 0.25), (0.25, 0.30), (0.30, 0.35), (0.35, 0.40)]
for low, high in atr_ranges:
    filtered = [t for t in trades if low <= t['atr'] < high]
    stats = calc_stats(filtered)
    if stats:
        n, wr, pf, pnl = stats
        print(f'ATR {low:.2f}-{high:.2f}: {n:3d} trades, WR={wr:5.1f}%, PF={pf:.2f}, P&L=${pnl:>10,.0f}')

# === ANÁLISIS POR SL PIPS ===
print()
print('=== ANÁLISIS POR RANGO SL PIPS ===')
sl_ranges = [(40, 50), (50, 60), (60, 70), (70, 80)]
for low, high in sl_ranges:
    filtered = [t for t in trades if low <= t['sl_pips'] < high]
    stats = calc_stats(filtered)
    if stats:
        n, wr, pf, pnl = stats
        print(f'SL {low:2d}-{high:2d} pips: {n:3d} trades, WR={wr:5.1f}%, PF={pf:.2f}, P&L=${pnl:>10,.0f}')

# === COMBINACIONES ÓPTIMAS ===
print()
print('=== COMBINACIONES ÓPTIMAS ===')
best_combos = []
for cci_max in [130, 140, 150, 175, 200]:
    for h_start in [14, 15, 16]:
        for h_end in [18, 19, 20]:
            if h_start < h_end:
                filtered = [t for t in trades if t['cci'] <= cci_max and h_start <= t['hour'] < h_end]
                stats = calc_stats(filtered)
                if stats and stats[0] >= 30:  # Al menos 30 trades
                    n, wr, pf, pnl = stats
                    best_combos.append((pf, cci_max, h_start, h_end, n, wr, pnl))

best_combos.sort(reverse=True)
print('Top 10 combinaciones (PF > 1, min 30 trades):')
for pf, cci_max, h_start, h_end, n, wr, pnl in best_combos[:10]:
    print(f'CCI<={cci_max:3d}, Horas {h_start:02d}-{h_end:02d}: {n:3d} trades, WR={wr:5.1f}%, PF={pf:.2f}, P&L=${pnl:>10,.0f}')
