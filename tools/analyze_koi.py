"""
KOI Strategy Trade Log Analyzer

Analyzes KOI trade logs to find patterns by:
- Hour of entry
- Day of week
- SL Pips ranges
- ATR ranges
- CCI ranges
- Yearly breakdown

Usage:
    python analyze_koi.py                    # Analyze latest log
    python analyze_koi.py KOI_trades_xxx.txt  # Analyze specific log
"""
import re
import os
import sys
from datetime import datetime
from collections import defaultdict


def find_latest_log(log_dir):
    """Find the most recent KOI log file."""
    logs = [f for f in os.listdir(log_dir) if f.startswith('KOI_trades_') and f.endswith('.txt')]
    if not logs:
        return None
    return max(logs)


def parse_log(filepath):
    """Parse KOI trade log file."""
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Parse entries (KOI format includes CCI)
    entries = re.findall(
        r'ENTRY #(\d+)\nTime: ([\d-]+ [\d:]+)\nEntry Price: ([\d.]+)\n'
        r'Stop Loss: ([\d.]+)\nTake Profit: ([\d.]+)\nSL Pips: ([\d.]+)\n'
        r'ATR: ([\d.]+)\nCCI: ([\d.-]+)',
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
            'cci': float(entry[7]),
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
    # Log directory is ../logs relative to tools/
    script_dir = os.path.dirname(os.path.abspath(__file__))
    log_dir = os.path.join(script_dir, '..', 'logs')
    log_dir = os.path.abspath(log_dir)
    
    # Get log file
    if len(sys.argv) > 1:
        log_file = sys.argv[1]
    else:
        log_file = find_latest_log(log_dir)
        if not log_file:
            print(f'No KOI log files found in {log_dir}')
            return
    
    filepath = os.path.join(log_dir, log_file)
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
    print(f'\nATR - Min: {min(atrs):.5f}, Max: {max(atrs):.5f}, Avg: {sum(atrs)/len(atrs):.5f}')
    if winners:
        print(f'ATR Winners Avg: {sum(t["atr"] for t in winners)/len(winners):.5f}')
    if losers:
        print(f'ATR Losers Avg:  {sum(t["atr"] for t in losers)/len(losers):.5f}')
    
    # CCI stats
    ccis = [t['cci'] for t in trades]
    print(f'\nCCI - Min: {min(ccis):.1f}, Max: {max(ccis):.1f}, Avg: {sum(ccis)/len(ccis):.1f}')
    if winners:
        print(f'CCI Winners Avg: {sum(t["cci"] for t in winners)/len(winners):.1f}')
    if losers:
        print(f'CCI Losers Avg:  {sum(t["cci"] for t in losers)/len(losers):.1f}')
    
    # SL Pips stats
    sl_pips = [t['sl_pips'] for t in trades]
    print(f'\nSL Pips - Min: {min(sl_pips):.1f}, Max: {max(sl_pips):.1f}, Avg: {sum(sl_pips)/len(sl_pips):.1f}')
    if winners:
        print(f'SL Pips Winners Avg: {sum(t["sl_pips"] for t in winners)/len(winners):.1f}')
    if losers:
        print(f'SL Pips Losers Avg:  {sum(t["sl_pips"] for t in losers)/len(losers):.1f}')
    
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
    
    # By SL Pips ranges (dynamic based on actual data)
    print_section('ANALYSIS BY SL PIPS')
    sl_vals = [t['sl_pips'] for t in trades if 'pnl' in t]
    if sl_vals:
        sl_min_r = int(min(sl_vals))
        sl_max_r = int(max(sl_vals)) + 3
        sl_step = 3
        sl_ranges = [(i, i + sl_step) for i in range(sl_min_r, sl_max_r, sl_step)]
        analyze_by_range(trades, lambda t: t['sl_pips'], sl_ranges, 'SL Pips')
    
    # By ATR ranges (dynamic based on actual data)
    print_section('ANALYSIS BY ATR')
    atr_vals = [t['atr'] for t in trades if 'pnl' in t]
    if atr_vals:
        atr_min_r = min(atr_vals)
        atr_max_r = max(atr_vals)
        # Determine step based on magnitude
        atr_range_span = atr_max_r - atr_min_r
        if atr_range_span < 0.01:
            # Forex pairs like EURUSD (ATR ~0.0005-0.001)
            atr_step = 0.0001
            decimals_atr = 4
        elif atr_range_span < 0.1:
            # Medium volatility
            atr_step = 0.005
            decimals_atr = 3
        else:
            # JPY pairs or high volatility
            atr_step = 0.01
            decimals_atr = 2
        # Build ranges from floor to ceiling
        import math
        start = math.floor(atr_min_r / atr_step) * atr_step
        end = math.ceil(atr_max_r / atr_step) * atr_step + atr_step
        atr_ranges = []
        current = start
        while current < end:
            atr_ranges.append((round(current, 5), round(current + atr_step, 5)))
            current = round(current + atr_step, 5)
        analyze_by_range(trades, lambda t: t['atr'], atr_ranges, 'ATR Range', decimals=decimals_atr)
    
    # By CCI ranges
    print_section('ANALYSIS BY CCI')
    cci_ranges = [
        (120, 140), (140, 160), (160, 180), (180, 200), 
        (200, 250), (250, 300), (300, 500)
    ]
    analyze_by_range(trades, lambda t: t['cci'], cci_ranges, 'CCI Range')
    
    # By Exit Reason
    print_section('ANALYSIS BY EXIT REASON')
    analyze_by_group(
        trades,
        lambda t: t.get('exit_reason', 'UNKNOWN'),
        'Exit Reason',
        str
    )
    
    # Trade Duration Analysis
    print_section('ANALYSIS BY TRADE DURATION')
    duration_ranges = [
        (0, 60), (60, 240), (240, 480), (480, 1440), 
        (1440, 2880), (2880, 10000)
    ]
    duration_labels = ['<1h', '1-4h', '4-8h', '8-24h', '1-2d', '>2d']
    
    print(f'\n{"Duration":15} | Trades | Win%  | PF   | Net P&L')
    print('-' * 55)
    
    for i, (low, high) in enumerate(duration_ranges):
        filtered = [t for t in trades if 'duration_min' in t and low <= t['duration_min'] < high]
        if filtered:
            stats = calculate_stats(filtered)
            pf_str = f'{stats["profit_factor"]:.2f}' if stats['profit_factor'] < 100 else 'INF'
            print(f'{duration_labels[i]:15} | {stats["total"]:6d} | {stats["win_rate"]:4.0f}% | {pf_str:>4} | ${stats["net_pnl"]:>10,.0f}')
    
    print('\n' + '=' * 60)


if __name__ == '__main__':
    main()
