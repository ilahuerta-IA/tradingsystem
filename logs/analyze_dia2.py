import re
import os
from collections import defaultdict

script_dir = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(script_dir, 'KOI_trades_20260111_165659.txt'), 'r') as f:
    content = f.read()

# Extraer todos los trades
entries = re.findall(r'ENTRY #(\d+)\nTime: (\d{4})-(\d{2})-\d{2} (\d{2}):(\d{2}):\d{2}.*?SL Pips: ([\d.]+)\nATR: ([\d.]+)\nCCI: ([\d.]+)', content, re.DOTALL)
exits = re.findall(r'EXIT #(\d+).*?Exit Reason: (\w+).*?P&L: \$([-\d,.]+)', content, re.DOTALL)

trades = []
for entry, exit_info in zip(entries, exits):
    trade_num, year, month, hour, minute, sl_pips, atr, cci = entry
    exit_num, reason, pnl = exit_info
    pnl = float(pnl.replace(',', ''))
    trades.append({
        'num': int(trade_num),
        'year': int(year),
        'hour': int(hour),
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

# === ANÁLISIS POR ATR ===
print('=== ANÁLISIS POR RANGO ATR ===')
atr_ranges = [(0.20, 0.25), (0.25, 0.30), (0.30, 0.35), (0.35, 0.40), (0.20, 0.30), (0.25, 0.35), (0.30, 0.40), (0.20, 0.35)]
for low, high in atr_ranges:
    filtered = [t for t in trades if low <= t['atr'] < high]
    stats = calc_stats(filtered)
    if stats:
        n, wr, pf, pnl = stats
        print(f'ATR {low:.2f}-{high:.2f}: {n:3d} trades, WR={wr:5.1f}%, PF={pf:.2f}, P&L=${pnl:>10,.0f}')

# === ANÁLISIS POR SL PIPS ===
print()
print('=== ANÁLISIS POR RANGO SL PIPS ===')
sl_ranges = [(40, 50), (50, 55), (55, 60), (60, 65), (65, 70), (70, 75), (75, 80), (40, 55), (50, 65), (55, 70), (60, 75), (40, 60), (50, 70), (55, 75)]
for low, high in sl_ranges:
    filtered = [t for t in trades if low <= t['sl_pips'] < high]
    stats = calc_stats(filtered)
    if stats and stats[0] >= 3:
        n, wr, pf, pnl = stats
        print(f'SL {low:2d}-{high:2d} pips: {n:3d} trades, WR={wr:5.1f}%, PF={pf:.2f}, P&L=${pnl:>10,.0f}')

# === ANÁLISIS POR HORA ===
print()
print('=== ANÁLISIS POR HORA (ya filtrado 15-17) ===')
by_hour = defaultdict(list)
for t in trades:
    by_hour[t['hour']].append(t)

for hour in sorted(by_hour.keys()):
    stats = calc_stats(by_hour[hour])
    if stats:
        n, wr, pf, pnl = stats
        print(f'Hora {hour:02d}: {n:3d} trades, WR={wr:5.1f}%, PF={pf:.2f}, P&L=${pnl:>10,.0f}')

# === ANÁLISIS POR AÑO ===
print()
print('=== ANÁLISIS POR AÑO ===')
by_year = defaultdict(list)
for t in trades:
    by_year[t['year']].append(t)

for year in sorted(by_year.keys()):
    stats = calc_stats(by_year[year])
    if stats:
        n, wr, pf, pnl = stats
        print(f'{year}: {n:3d} trades, WR={wr:5.1f}%, PF={pf:.2f}, P&L=${pnl:>10,.0f}')

# === COMBINACIONES ÓPTIMAS ATR + SL ===
print()
print('=== COMBINACIONES ÓPTIMAS (ATR + SL Pips) ===')
best_combos = []
for atr_min, atr_max in [(0.20, 0.30), (0.20, 0.35), (0.25, 0.35), (0.25, 0.40), (0.30, 0.40), (0.20, 0.40)]:
    for sl_min, sl_max in [(40, 60), (40, 65), (40, 70), (45, 65), (45, 70), (50, 70), (50, 75), (55, 75), (40, 75)]:
        filtered = [t for t in trades if atr_min <= t['atr'] < atr_max and sl_min <= t['sl_pips'] < sl_max]
        stats = calc_stats(filtered)
        if stats and stats[0] >= 15:  # Al menos 15 trades
            n, wr, pf, pnl = stats
            if pf > 1.0:
                best_combos.append((pf, atr_min, atr_max, sl_min, sl_max, n, wr, pnl))

best_combos.sort(reverse=True)
print('Top 15 combinaciones (min 15 trades, PF > 1):')
for pf, atr_min, atr_max, sl_min, sl_max, n, wr, pnl in best_combos[:15]:
    print(f'ATR {atr_min:.2f}-{atr_max:.2f}, SL {sl_min:2d}-{sl_max:2d}: {n:3d} trades, WR={wr:5.1f}%, PF={pf:.2f}, P&L=${pnl:>10,.0f}')

# === DISTRIBUCIÓN POR AÑO DE MEJOR COMBO ===
print()
if best_combos:
    pf, atr_min, atr_max, sl_min, sl_max, n, wr, pnl = best_combos[0]
    print(f'=== DISTRIBUCIÓN POR AÑO DEL MEJOR COMBO (ATR {atr_min:.2f}-{atr_max:.2f}, SL {sl_min}-{sl_max}) ===')
    filtered = [t for t in trades if atr_min <= t['atr'] < atr_max and sl_min <= t['sl_pips'] < sl_max]
    by_year_best = defaultdict(list)
    for t in filtered:
        by_year_best[t['year']].append(t)
    
    for year in sorted(by_year_best.keys()):
        stats = calc_stats(by_year_best[year])
        if stats:
            n, wr, pf, pnl = stats
            print(f'{year}: {n:3d} trades, WR={wr:5.1f}%, PF={pf:.2f}, P&L=${pnl:>10,.0f}')
