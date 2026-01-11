import re
from collections import defaultdict

with open('KOI_trades_20260111_172447.txt', 'r') as f:
    content = f.read()

entries = re.findall(r'ENTRY #(\d+)\nTime: (\d{4})-(\d{2})-\d{2} (\d{2}):(\d{2}):\d{2}.*?SL Pips: ([\d.]+)\nATR: ([\d.]+)\nCCI: ([\d.]+)', content, re.DOTALL)
exits = re.findall(r'EXIT #(\d+).*?Exit Reason: (\w+).*?P&L: \$([-\d,.]+)', content, re.DOTALL)

trades = []
for entry, exit_info in zip(entries, exits):
    trade_num, year, month, hour, minute, sl_pips, atr, cci = entry
    exit_num, reason, pnl = exit_info
    pnl = float(pnl.replace(',', ''))
    trades.append({'num': int(trade_num), 'year': int(year), 'hour': int(hour), 'sl_pips': float(sl_pips), 'atr': float(atr), 'pnl': pnl, 'win': pnl > 0})

def calc_stats(filtered):
    if not filtered:
        return None
    wins = sum(1 for t in filtered if t['win'])
    total_pnl = sum(t['pnl'] for t in filtered)
    gross_profit = sum(t['pnl'] for t in filtered if t['pnl'] > 0)
    gross_loss = abs(sum(t['pnl'] for t in filtered if t['pnl'] < 0))
    pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    return len(filtered), wins/len(filtered)*100, pf, total_pnl

print(f'Total: {len(trades)} trades')
print()

print('=== POR AÑO (actual) ===')
by_year = defaultdict(list)
for t in trades:
    by_year[t['year']].append(t)
for year in sorted(by_year.keys()):
    s = calc_stats(by_year[year])
    if s: print(f'{year}: {s[0]:3d} trades, WR={s[1]:5.1f}%, PF={s[2]:.2f}, P&L=${s[3]:>10,.0f}')

print()
print('=== ATR EN AÑOS 2020-2022 vs 2023-2025 ===')
early = [t for t in trades if t['year'] <= 2022]
late = [t for t in trades if t['year'] >= 2023]
print(f'2020-22: {len(early)} trades, ATR medio={sum(t["atr"] for t in early)/len(early):.3f}, SL medio={sum(t["sl_pips"] for t in early)/len(early):.1f}')
print(f'2023-25: {len(late)} trades, ATR medio={sum(t["atr"] for t in late)/len(late):.3f}, SL medio={sum(t["sl_pips"] for t in late)/len(late):.1f}')

print()
print('=== ATR RANGOS (todo el periodo) ===')
for low, high in [(0.20,0.25),(0.25,0.30),(0.30,0.35),(0.35,0.40),(0.20,0.30),(0.25,0.35),(0.30,0.40),(0.25,0.40)]:
    f = [t for t in trades if low <= t['atr'] < high]
    s = calc_stats(f)
    if s and s[0] >= 5: print(f'ATR {low:.2f}-{high:.2f}: {s[0]:3d} trades, WR={s[1]:5.1f}%, PF={s[2]:.2f}, P&L=${s[3]:>10,.0f}')

print()
print('=== SL PIPS RANGOS (todo el periodo) ===')
for low, high in [(60,65),(65,70),(70,75),(75,80),(60,70),(65,75),(70,80),(60,75),(65,80),(60,80)]:
    f = [t for t in trades if low <= t['sl_pips'] < high]
    s = calc_stats(f)
    if s and s[0] >= 5: print(f'SL {low:2d}-{high:2d}: {s[0]:3d} trades, WR={s[1]:5.1f}%, PF={s[2]:.2f}, P&L=${s[3]:>10,.0f}')

print()
print('=== ATR SOLO EN 2020-2022 ===')
for low, high in [(0.20,0.25),(0.25,0.30),(0.30,0.35),(0.35,0.40),(0.25,0.35),(0.30,0.40)]:
    f = [t for t in early if low <= t['atr'] < high]
    s = calc_stats(f)
    if s and s[0] >= 3: print(f'ATR {low:.2f}-{high:.2f}: {s[0]:3d} trades, WR={s[1]:5.1f}%, PF={s[2]:.2f}, P&L=${s[3]:>10,.0f}')

print()
print('=== SL PIPS SOLO EN 2020-2022 ===')
for low, high in [(60,65),(65,70),(70,75),(75,80),(60,70),(65,75),(70,80),(60,75)]:
    f = [t for t in early if low <= t['sl_pips'] < high]
    s = calc_stats(f)
    if s and s[0] >= 3: print(f'SL {low:2d}-{high:2d}: {s[0]:3d} trades, WR={s[1]:5.1f}%, PF={s[2]:.2f}, P&L=${s[3]:>10,.0f}')

print()
print('=== COMBINACIONES ATR+SL (min 20 trades) ===')
combos = []
for atr_min, atr_max in [(0.25,0.35),(0.25,0.40),(0.30,0.40),(0.20,0.35),(0.20,0.40)]:
    for sl_min, sl_max in [(60,75),(65,80),(60,80),(65,75),(70,80)]:
        f = [t for t in trades if atr_min <= t['atr'] < atr_max and sl_min <= t['sl_pips'] < sl_max]
        s = calc_stats(f)
        if s and s[0] >= 20:
            combos.append((s[2], atr_min, atr_max, sl_min, sl_max, s[0], s[1], s[3]))
combos.sort(reverse=True)
for pf, atr_min, atr_max, sl_min, sl_max, n, wr, pnl in combos[:10]:
    print(f'ATR {atr_min:.2f}-{atr_max:.2f}, SL {sl_min}-{sl_max}: {n:3d} trades, WR={wr:5.1f}%, PF={pf:.2f}, P&L=${pnl:>10,.0f}')

print()
print('=== IMPACTO EN 2020-22 SI APLICAMOS FILTROS ===')
for atr_min, atr_max in [(0.30,0.40),(0.25,0.35)]:
    for sl_min, sl_max in [(65,80),(60,75)]:
        f_early = [t for t in early if atr_min <= t['atr'] < atr_max and sl_min <= t['sl_pips'] < sl_max]
        f_late = [t for t in late if atr_min <= t['atr'] < atr_max and sl_min <= t['sl_pips'] < sl_max]
        s_early = calc_stats(f_early)
        s_late = calc_stats(f_late)
        if s_early and s_late:
            print(f'ATR {atr_min:.2f}-{atr_max:.2f}, SL {sl_min}-{sl_max}:')
            print(f'  2020-22: {s_early[0]:2d} trades, WR={s_early[1]:5.1f}%, PF={s_early[2]:.2f}, P&L=${s_early[3]:>8,.0f}')
            print(f'  2023-25: {s_late[0]:2d} trades, WR={s_late[1]:5.1f}%, PF={s_late[2]:.2f}, P&L=${s_late[3]:>8,.0f}')
