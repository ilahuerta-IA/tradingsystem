import re
from collections import defaultdict

with open('KOI_trades_20260111_171806.txt', 'r') as f:
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

print(f'Total: {len(trades)} trades, WR={sum(1 for t in trades if t["win"])/len(trades)*100:.1f}%')
gp = sum(t['pnl'] for t in trades if t['pnl'] > 0)
gl = abs(sum(t['pnl'] for t in trades if t['pnl'] < 0))
print(f'PF={gp/gl:.2f}, P&L=${sum(t["pnl"] for t in trades):,.0f}')
print()

print('=== POR HORA ===')
by_hour = defaultdict(list)
for t in trades:
    by_hour[t['hour']].append(t)
for hour in sorted(by_hour.keys()):
    s = calc_stats(by_hour[hour])
    if s: print(f'Hora {hour:02d}: {s[0]:3d} trades, WR={s[1]:5.1f}%, PF={s[2]:.2f}, P&L=${s[3]:>10,.0f}')

print()
print('=== POR SL PIPS ===')
for low, high in [(40,50),(50,55),(55,60),(60,65),(65,70),(70,75),(75,80),(40,55),(50,60),(55,65),(60,70),(65,75),(50,65),(55,70),(60,75),(50,70),(55,75),(50,75)]:
    f = [t for t in trades if low <= t['sl_pips'] < high]
    s = calc_stats(f)
    if s and s[0] >= 5: print(f'SL {low:2d}-{high:2d}: {s[0]:3d} trades, WR={s[1]:5.1f}%, PF={s[2]:.2f}, P&L=${s[3]:>10,.0f}')

print()
print('=== EXCLUIR HORAS MALAS ===')
for exclude in [[13], [20], [13,20], [18,20], [13,18,20], [19,20]]:
    f = [t for t in trades if t['hour'] not in exclude]
    s = calc_stats(f)
    if s: print(f'Sin {exclude}: {s[0]:3d} trades, WR={s[1]:5.1f}%, PF={s[2]:.2f}, P&L=${s[3]:>10,.0f}')

print()
print('=== POR AÑO (actual) ===')
by_year = defaultdict(list)
for t in trades:
    by_year[t['year']].append(t)
for year in sorted(by_year.keys()):
    s = calc_stats(by_year[year])
    if s: print(f'{year}: {s[0]:3d} trades, WR={s[1]:5.1f}%, PF={s[2]:.2f}, P&L=${s[3]:>10,.0f}')
