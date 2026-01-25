"""Deep analysis of SEDNA log file."""
import re
import sys
from datetime import datetime
from collections import defaultdict

# Allow passing log file as argument
if len(sys.argv) > 1:
    LOG_FILE = f'../logs/{sys.argv[1]}'
else:
    LOG_FILE = '../logs/SEDNA_trades_20260124_220450.txt'  # EURJPY default

with open(LOG_FILE, 'r') as f:
    content = f.read()

# Parse trades
pattern = r'ENTRY #(\d+)\nTime: (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\nEntry Price: ([\d.]+)\nStop Loss: ([\d.]+)\nTake Profit: ([\d.]+)\nSL Pips: ([\d.]+)\nATR \(avg\): ([\d.]+)\n-+\n\nEXIT #\d+\nTime: (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\nExit Reason: (\w+)\nP&L: \$(-?[\d.,]+)'

matches = re.findall(pattern, content)

trades = []
for m in matches:
    pnl = float(m[9].replace(',', ''))
    entry_time = datetime.strptime(m[1], '%Y-%m-%d %H:%M:%S')
    exit_time = datetime.strptime(m[7], '%Y-%m-%d %H:%M:%S')
    trades.append({
        'id': int(m[0]),
        'entry_time': entry_time,
        'exit_time': exit_time,
        'entry_price': float(m[2]),
        'sl': float(m[3]),
        'tp': float(m[4]),
        'sl_pips': float(m[5]),
        'atr': float(m[6]),
        'exit_reason': m[8],
        'pnl': pnl,
        'win': pnl > 0,
        'hour': entry_time.hour,
        'dow': entry_time.weekday(),
        'duration_hours': (exit_time - entry_time).total_seconds() / 3600
    })

print(f"Total trades parsed: {len(trades)}")

# Overall stats
wins = [t for t in trades if t['win']]
losses = [t for t in trades if not t['win']]
total_pnl = sum(t['pnl'] for t in trades)

print(f"\n{'='*60}")
print("OVERALL STATISTICS")
print(f"{'='*60}")
print(f"Wins: {len(wins)} ({len(wins)/len(trades)*100:.1f}%)")
print(f"Losses: {len(losses)} ({len(losses)/len(trades)*100:.1f}%)")
print(f"Total PnL: ${total_pnl:,.0f}")
print(f"Avg Win: ${sum(t['pnl'] for t in wins)/len(wins):,.0f}" if wins else "No wins")
print(f"Avg Loss: ${sum(t['pnl'] for t in losses)/len(losses):,.0f}" if losses else "No losses")

# ATR Analysis
print(f"\n{'='*60}")
print("ATR ANALYSIS")
print(f"{'='*60}")

atr_ranges = [(0, 0.0002), (0.0002, 0.0003), (0.0003, 0.0004), (0.0004, 0.0005), (0.0005, 0.0006), (0.0006, 0.001)]
print(f"{'ATR Range':<15} | {'Trades':>6} | {'Wins':>4} | {'WR%':>5} | {'Avg PnL':>10} | {'Total PnL':>12}")
print("-" * 70)

for low, high in atr_ranges:
    filtered = [t for t in trades if low <= t['atr'] < high]
    if filtered:
        w = len([t for t in filtered if t['win']])
        wr = w / len(filtered) * 100
        avg_pnl = sum(t['pnl'] for t in filtered) / len(filtered)
        total = sum(t['pnl'] for t in filtered)
        print(f"{low:.4f}-{high:.4f} | {len(filtered):>6} | {w:>4} | {wr:>4.0f}% | ${avg_pnl:>9,.0f} | ${total:>11,.0f}")

# Winner ATR vs Loser ATR
print(f"\nWinner avg ATR: {sum(t['atr'] for t in wins)/len(wins):.6f}" if wins else "")
print(f"Loser avg ATR: {sum(t['atr'] for t in losses)/len(losses):.6f}" if losses else "")

# SL Pips Analysis
print(f"\n{'='*60}")
print("SL PIPS ANALYSIS")
print(f"{'='*60}")

sl_ranges = [(0, 10), (10, 15), (15, 20), (20, 25), (25, 30), (30, 40), (40, 50)]
print(f"{'SL Pips':<10} | {'Trades':>6} | {'Wins':>4} | {'WR%':>5} | {'Avg PnL':>10} | {'Total PnL':>12}")
print("-" * 65)

for low, high in sl_ranges:
    filtered = [t for t in trades if low <= t['sl_pips'] < high]
    if filtered:
        w = len([t for t in filtered if t['win']])
        wr = w / len(filtered) * 100
        avg_pnl = sum(t['pnl'] for t in filtered) / len(filtered)
        total = sum(t['pnl'] for t in filtered)
        print(f"{low:>3}-{high:<3} pips | {len(filtered):>6} | {w:>4} | {wr:>4.0f}% | ${avg_pnl:>9,.0f} | ${total:>11,.0f}")

print(f"\nWinner avg SL pips: {sum(t['sl_pips'] for t in wins)/len(wins):.1f}" if wins else "")
print(f"Loser avg SL pips: {sum(t['sl_pips'] for t in losses)/len(losses):.1f}" if losses else "")

# Hour Analysis
print(f"\n{'='*60}")
print("HOUR ANALYSIS (Entry Hour UTC)")
print(f"{'='*60}")

hours = defaultdict(list)
for t in trades:
    hours[t['hour']].append(t)

print(f"{'Hour':<6} | {'Trades':>6} | {'Wins':>4} | {'WR%':>5} | {'Avg PnL':>10} | {'Total PnL':>12}")
print("-" * 60)

for h in sorted(hours.keys()):
    h_trades = hours[h]
    w = len([t for t in h_trades if t['win']])
    wr = w / len(h_trades) * 100
    avg_pnl = sum(t['pnl'] for t in h_trades) / len(h_trades)
    total = sum(t['pnl'] for t in h_trades)
    marker = "✓" if total > 0 else ""
    print(f"{h:02d}:00  | {len(h_trades):>6} | {w:>4} | {wr:>4.0f}% | ${avg_pnl:>9,.0f} | ${total:>11,.0f} {marker}")

# Best/Worst hours
best_hours = sorted(hours.keys(), key=lambda h: sum(t['pnl'] for t in hours[h]), reverse=True)[:5]
worst_hours = sorted(hours.keys(), key=lambda h: sum(t['pnl'] for t in hours[h]))[:5]
print(f"\nBest hours: {[f'{h:02d}:00' for h in best_hours]}")
print(f"Worst hours: {[f'{h:02d}:00' for h in worst_hours]}")

# Day of Week Analysis
print(f"\n{'='*60}")
print("DAY OF WEEK ANALYSIS")
print(f"{'='*60}")

dow_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
dows = defaultdict(list)
for t in trades:
    dows[t['dow']].append(t)

print(f"{'Day':<5} | {'Trades':>6} | {'Wins':>4} | {'WR%':>5} | {'Avg PnL':>10} | {'Total PnL':>12}")
print("-" * 55)

for d in sorted(dows.keys()):
    d_trades = dows[d]
    w = len([t for t in d_trades if t['win']])
    wr = w / len(d_trades) * 100
    avg_pnl = sum(t['pnl'] for t in d_trades) / len(d_trades)
    total = sum(t['pnl'] for t in d_trades)
    marker = "✓" if total > 0 else ""
    print(f"{dow_names[d]:<5} | {len(d_trades):>6} | {w:>4} | {wr:>4.0f}% | ${avg_pnl:>9,.0f} | ${total:>11,.0f} {marker}")

# Trade Duration Analysis
print(f"\n{'='*60}")
print("TRADE DURATION ANALYSIS")
print(f"{'='*60}")

duration_ranges = [(0, 1), (1, 3), (3, 6), (6, 12), (12, 24), (24, 48), (48, 999)]
print(f"{'Duration':<12} | {'Trades':>6} | {'Wins':>4} | {'WR%':>5} | {'Avg PnL':>10} | {'Total PnL':>12}")
print("-" * 65)

for low, high in duration_ranges:
    filtered = [t for t in trades if low <= t['duration_hours'] < high]
    if filtered:
        w = len([t for t in filtered if t['win']])
        wr = w / len(filtered) * 100
        avg_pnl = sum(t['pnl'] for t in filtered) / len(filtered)
        total = sum(t['pnl'] for t in filtered)
        label = f"{low}-{high}h" if high < 999 else f">{low}h"
        print(f"{label:<12} | {len(filtered):>6} | {w:>4} | {wr:>4.0f}% | ${avg_pnl:>9,.0f} | ${total:>11,.0f}")

print(f"\nAvg duration (wins): {sum(t['duration_hours'] for t in wins)/len(wins):.1f}h" if wins else "")
print(f"Avg duration (losses): {sum(t['duration_hours'] for t in losses)/len(losses):.1f}h" if losses else "")

# Year Analysis
print(f"\n{'='*60}")
print("YEARLY ANALYSIS")
print(f"{'='*60}")

years = defaultdict(list)
for t in trades:
    years[t['entry_time'].year].append(t)

print(f"{'Year':<6} | {'Trades':>6} | {'Wins':>4} | {'WR%':>5} | {'Avg PnL':>10} | {'Total PnL':>12}")
print("-" * 55)

for y in sorted(years.keys()):
    y_trades = years[y]
    w = len([t for t in y_trades if t['win']])
    wr = w / len(y_trades) * 100
    avg_pnl = sum(t['pnl'] for t in y_trades) / len(y_trades)
    total = sum(t['pnl'] for t in y_trades)
    print(f"{y:<6} | {len(y_trades):>6} | {w:>4} | {wr:>4.0f}% | ${avg_pnl:>9,.0f} | ${total:>11,.0f}")

# Pattern: Winners vs Losers comparison
print(f"\n{'='*60}")
print("WINNERS vs LOSERS PROFILE")
print(f"{'='*60}")

if wins and losses:
    print(f"{'Metric':<20} | {'Winners':>12} | {'Losers':>12}")
    print("-" * 50)
    print(f"{'Count':<20} | {len(wins):>12} | {len(losses):>12}")
    print(f"{'Avg ATR':<20} | {sum(t['atr'] for t in wins)/len(wins):>12.6f} | {sum(t['atr'] for t in losses)/len(losses):>12.6f}")
    print(f"{'Avg SL Pips':<20} | {sum(t['sl_pips'] for t in wins)/len(wins):>12.1f} | {sum(t['sl_pips'] for t in losses)/len(losses):>12.1f}")
    print(f"{'Avg Duration (h)':<20} | {sum(t['duration_hours'] for t in wins)/len(wins):>12.1f} | {sum(t['duration_hours'] for t in losses)/len(losses):>12.1f}")
    print(f"{'Avg PnL':<20} | ${sum(t['pnl'] for t in wins)/len(wins):>11,.0f} | ${sum(t['pnl'] for t in losses)/len(losses):>11,.0f}")

# RECOMMENDATIONS
print(f"\n{'='*60}")
print("RECOMMENDATIONS")
print(f"{'='*60}")

# Find best filters
best_atr = max(atr_ranges, key=lambda r: sum(t['pnl'] for t in trades if r[0] <= t['atr'] < r[1]))
best_sl = max(sl_ranges, key=lambda r: sum(t['pnl'] for t in trades if r[0] <= t['sl_pips'] < r[1]))
profitable_hours = [h for h in hours if sum(t['pnl'] for t in hours[h]) > 0]

print(f"1. Best ATR range: {best_atr[0]:.4f} - {best_atr[1]:.4f}")
print(f"2. Best SL Pips range: {best_sl[0]} - {best_sl[1]}")
print(f"3. Profitable hours: {sorted(profitable_hours)}")
print(f"4. Consider excluding hours: {sorted(worst_hours[:3])}")
