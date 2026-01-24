"""
SEDNA Strategy Trade Log Analyzer

Analyzes SEDNA trade logs to find patterns by:
- Hour of entry
- Day of week
- SL Pips ranges
- ATR ranges
- Yearly breakdown

Usage:
    python analyze_sedna.py                    # Analyze latest log
    python analyze_sedna.py SEDNA_trades_xxx.txt  # Analyze specific log
"""
import re
import os
import sys
from datetime import datetime
from collections import defaultdict


def find_latest_log(log_dir):
    """Find the most recent SEDNA log file."""
    logs = [f for f in os.listdir(log_dir) if f.startswith('SEDNA_trades_') and f.endswith('.txt')]
    if not logs:
        return None
    return max(logs)


def parse_log(filepath):
    """Parse SEDNA trade log file."""
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Parse entries
    entries = re.findall(
        r'ENTRY #(\d+)\nTime: ([\d-]+ [\d:]+)\nEntry Price: ([\d.]+)\n'
        r'Stop Loss: ([\d.]+)\nTake Profit: ([\d.]+)\nSL Pips: ([\d.]+)\n'
        r'ATR \(avg\): ([\d.]+)',
        content
    )
    
    # Parse exits
    exits = re.findall(
        r'EXIT #(\d+)\nTime: ([\d-]+ [\d:]+)\nExit Reason: (\w+)\n'
        r'P&L: \$([-\d,.]+)',
        content
    )
    
    # Build trades list
    trades = []
    for i, entry in enumerate(entries):
        trade = {
            'id': int(entry[0]),
            'entry_time': datetime.strptime(entry[1], '%Y-%m-%d %H:%M:%S'),
            'entry_price': float(entry[2]),
            'sl': float(entry[3]),
            'tp': float(entry[4]),
            'sl_pips': float(entry[5]),
            'atr': float(entry[6]),
        }
        if i < len(exits):
            trade['exit_time'] = datetime.strptime(exits[i][1], '%Y-%m-%d %H:%M:%S')
            trade['exit_reason'] = exits[i][2]
            trade['pnl'] = float(exits[i][3].replace(',', ''))
            trade['duration_min'] = (trade['exit_time'] - trade['entry_time']).total_seconds() / 60
            trade['win'] = trade['pnl'] > 0
        trades.append(trade)
    
    return trades


def calculate_stats(trades):
    """Calculate basic statistics for a list of trades."""
    if not trades:
        return None
    
    closed = [t for t in trades if 'pnl' in t]
    if not closed:
        return None
    
    winners = [t for t in closed if t['pnl'] > 0]
    losers = [t for t in closed if t['pnl'] < 0]
    
    gross_profit = sum(t['pnl'] for t in winners)
    gross_loss = sum(abs(t['pnl']) for t in losers)
    
    return {
        'total': len(closed),
        'wins': len(winners),
        'losses': len(losers),
        'win_rate': len(winners) / len(closed) * 100 if closed else 0,
        'gross_profit': gross_profit,
        'gross_loss': gross_loss,
        'net_pnl': gross_profit - gross_loss,
        'profit_factor': gross_profit / gross_loss if gross_loss > 0 else float('inf'),
    }


def print_section(title):
    """Print section header."""
    print(f'\n{"=" * 60}')
    print(f'{title}')
    print("=" * 60)


def analyze_by_group(trades, key_func, group_name, format_func=str):
    """Generic analysis by grouping key."""
    groups = defaultdict(list)
    for t in trades:
        if 'pnl' in t:
            key = key_func(t)
            groups[key].append(t)
    
    print(f'\n{group_name:15} | Trades | Win%  | PF   | Net P&L')
    print('-' * 55)
    
    for key in sorted(groups.keys()):
        stats = calculate_stats(groups[key])
        if stats:
            pf_str = f'{stats["profit_factor"]:.2f}' if stats['profit_factor'] < 100 else 'INF'
            print(f'{format_func(key):15} | {stats["total"]:6d} | {stats["win_rate"]:4.0f}% | {pf_str:>4} | ${stats["net_pnl"]:>10,.0f}')


def analyze_by_range(trades, value_func, ranges, range_name, decimals=0):
    """Analyze by value ranges."""
    print(f'\n{range_name:15} | Trades | Win%  | PF   | Net P&L')
    print('-' * 55)
    
    for low, high in ranges:
        filtered = [t for t in trades if 'pnl' in t and low <= value_func(t) < high]
        if filtered:
            stats = calculate_stats(filtered)
            pf_str = f'{stats["profit_factor"]:.2f}' if stats['profit_factor'] < 100 else 'INF'
            if decimals > 0:
                label = f'{low:.{decimals}f}-{high:.{decimals}f}'
            else:
                label = f'{int(low):3d}-{int(high):3d}'
            print(f'{label:15} | {stats["total"]:6d} | {stats["win_rate"]:4.0f}% | {pf_str:>4} | ${stats["net_pnl"]:>10,.0f}')


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Get log file
    if len(sys.argv) > 1:
        log_file = sys.argv[1]
    else:
        log_file = find_latest_log(script_dir)
        if not log_file:
            print('No SEDNA log files found.')
            return
    
    filepath = os.path.join(script_dir, log_file)
    if not os.path.exists(filepath):
        print(f'Log file not found: {filepath}')
        return
    
    print(f'Analyzing: {log_file}')
    
    # Parse trades
    trades = parse_log(filepath)
    print(f'Total Entries: {len(trades)}')
    
    # Overall stats
    print_section('OVERALL STATISTICS')
    stats = calculate_stats(trades)
    if stats:
        print(f'Total Trades:   {stats["total"]}')
        print(f'Winners:        {stats["wins"]} ({stats["win_rate"]:.1f}%)')
        print(f'Losers:         {stats["losses"]} ({100-stats["win_rate"]:.1f}%)')
        print(f'Gross Profit:   ${stats["gross_profit"]:,.0f}')
        print(f'Gross Loss:     ${stats["gross_loss"]:,.0f}')
        print(f'Net P&L:        ${stats["net_pnl"]:,.0f}')
        print(f'Profit Factor:  {stats["profit_factor"]:.2f}')
    
    # Consecutive wins/losses
    max_wins, max_losses = 0, 0
    curr_wins, curr_losses = 0, 0
    for t in trades:
        if t.get('pnl', 0) > 0:
            curr_wins += 1
            max_wins = max(max_wins, curr_wins)
            curr_losses = 0
        elif 'pnl' in t:
            curr_losses += 1
            max_losses = max(max_losses, curr_losses)
            curr_wins = 0
    print(f'\nMax Consecutive Wins:   {max_wins}')
    print(f'Max Consecutive Losses: {max_losses}')
    
    # ATR stats
    atrs = [t['atr'] for t in trades]
    winners = [t for t in trades if t.get('pnl', 0) > 0]
    losers = [t for t in trades if t.get('pnl', 0) < 0]
    print(f'\nATR - Min: {min(atrs):.4f}, Max: {max(atrs):.4f}, Avg: {sum(atrs)/len(atrs):.4f}')
    if winners:
        print(f'ATR Winners Avg: {sum(t["atr"] for t in winners)/len(winners):.4f}')
    if losers:
        print(f'ATR Losers Avg:  {sum(t["atr"] for t in losers)/len(losers):.4f}')
    
    # By Hour
    print_section('ANALYSIS BY ENTRY HOUR')
    analyze_by_group(
        trades,
        lambda t: t['entry_time'].hour,
        'Hour',
        lambda h: f'{h:02d}:00'
    )
    
    # By Day of Week
    print_section('ANALYSIS BY DAY OF WEEK')
    dow_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    analyze_by_group(
        trades,
        lambda t: t['entry_time'].weekday(),
        'Day',
        lambda d: dow_names[d]
    )
    
    # By Year
    print_section('ANALYSIS BY YEAR')
    analyze_by_group(
        trades,
        lambda t: t['entry_time'].year,
        'Year',
        str
    )
    
    # By SL Pips ranges
    print_section('ANALYSIS BY SL PIPS')
    sl_ranges = [(0, 30), (30, 50), (50, 80), (80, 120), (120, 200)]
    analyze_by_range(trades, lambda t: t['sl_pips'], sl_ranges, 'SL Pips')
    
    # By ATR ranges
    print_section('ANALYSIS BY ATR')
    atr_ranges = [(0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8)]
    analyze_by_range(trades, lambda t: t['atr'], atr_ranges, 'ATR Range', decimals=2)
    
    print('\n' + '=' * 60)


if __name__ == '__main__':
    main()
