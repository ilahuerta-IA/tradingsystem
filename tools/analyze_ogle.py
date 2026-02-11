"""
Sunset Ogle (PRO) Strategy Trade Log Analyzer

Analyzes SunsetOgle trade logs to find patterns by:
- Hour of entry
- Day of week
- SL Pips ranges
- ATR ranges
- Angle ranges
- Yearly breakdown

Usage:
    python tools/analyze_ogle.py                          # Analyze latest log
    python tools/analyze_ogle.py EURJPY_PRO_20260211.txt  # Analyze specific log
"""
import re
import os
import sys
from datetime import datetime
from collections import defaultdict


def find_latest_log(log_dir):
    """Find the most recent PRO (SunsetOgle) log file."""
    logs = [f for f in os.listdir(log_dir) if '_PRO_' in f and f.endswith('.txt')]
    if not logs:
        return None
    return max(logs)


def parse_log(filepath):
    """Parse SunsetOgle trade log file."""
    with open(filepath, 'r') as f:
        content = f.read()

    # Parse entries - format from run_backtest.py save_trade_log
    entries = re.findall(
        r'ENTRY #(\d+)\n'
        r'Time: ([\d-]+ [\d:]+)\n'
        r'Direction: (\w+)\n'
        r'ATR Current: ([\d.]+)\n'
        r'(?:ATR (?:Increment|Change): [^\n]+\n)?'
        r'Angle Current: ([\d.-]+) deg\n'
        r'[^\n]*\n'  # Angle Filter line
        r'SL Pips: ([\d.]+)',
        content
    )

    # Parse exits
    exits = re.findall(
        r'EXIT #(\d+)\n'
        r'Time: ([\d-]+ [\d:]+)\n'
        r'Exit Reason: (\w+)\n'
        r'P&L: ([-\d,.]+)\n'
        r'Pips: ([-\d,.]+)\n'
        r'Duration: (\d+) bars',
        content
    )

    # Build trades list
    trades = []
    for i, entry in enumerate(entries):
        trade = {
            'id': int(entry[0]),
            'entry_time': datetime.strptime(entry[1], '%Y-%m-%d %H:%M:%S'),
            'direction': entry[2],
            'atr': float(entry[3]),
            'angle': float(entry[4]),
            'sl_pips': float(entry[5]),
        }
        if i < len(exits):
            trade['exit_time'] = datetime.strptime(exits[i][1], '%Y-%m-%d %H:%M:%S')
            trade['exit_reason'] = exits[i][2]
            trade['pnl'] = float(exits[i][3].replace(',', ''))
            trade['pips'] = float(exits[i][4].replace(',', ''))
            trade['duration_bars'] = int(exits[i][5])
            trade['duration_min'] = trade['duration_bars'] * 5  # 5m timeframe
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
            print(f'No PRO (SunsetOgle) log files found in {log_dir}')
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

    # Angle stats
    angles = [t['angle'] for t in trades]
    print(f'\nAngle - Min: {min(angles):.1f}, Max: {max(angles):.1f}, Avg: {sum(angles)/len(angles):.1f}')
    if winners:
        print(f'Angle Winners Avg: {sum(t["angle"] for t in winners)/len(winners):.1f}')
    if losers:
        print(f'Angle Losers Avg:  {sum(t["angle"] for t in losers)/len(losers):.1f}')

    # Duration stats
    durations = [t.get('duration_bars', 0) for t in trades if 'duration_bars' in t]
    if durations:
        print(f'\nDuration (bars) - Min: {min(durations)}, Max: {max(durations)}, Avg: {sum(durations)/len(durations):.0f}')

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

    # By Exit Reason
    print_section('ANALYSIS BY EXIT REASON')
    analyze_by_group(
        trades,
        lambda t: t.get('exit_reason', 'N/A'),
        'Exit Reason',
        str
    )

    # By SL Pips ranges
    print_section('ANALYSIS BY SL PIPS')
    sl_ranges = [(0, 5), (5, 10), (10, 15), (15, 20), (20, 30), (30, 50), (50, 80), (80, 120)]
    analyze_by_range(trades, lambda t: t['sl_pips'], sl_ranges, 'SL Pips')

    # By Angle ranges
    print_section('ANALYSIS BY ANGLE')
    angle_ranges = [(0, 15), (15, 30), (30, 45), (45, 60), (60, 75), (75, 90), (90, 120)]
    analyze_by_range(trades, lambda t: abs(t['angle']), angle_ranges, 'Angle (deg)')

    # By ATR ranges (auto-detect based on data)
    print_section('ANALYSIS BY ATR')
    min_atr = min(atrs)
    max_atr = max(atrs)
    # For JPY pairs (ATR ~0.03-0.09) vs standard pairs (ATR ~0.0002-0.0004)
    if max_atr > 0.01:
        # JPY pair ranges
        atr_ranges = [
            (0.02, 0.03), (0.03, 0.04), (0.04, 0.05), (0.05, 0.06),
            (0.06, 0.07), (0.07, 0.08), (0.08, 0.09), (0.09, 0.10), (0.10, 0.15)
        ]
    else:
        # Standard pair ranges
        atr_ranges = [
            (0.00010, 0.00020), (0.00020, 0.00025), (0.00025, 0.00030),
            (0.00030, 0.00035), (0.00035, 0.00040), (0.00040, 0.00050),
            (0.00050, 0.00070), (0.00070, 0.00100)
        ]
    analyze_by_range(trades, lambda t: t['atr'], atr_ranges, 'ATR Range', decimals=5)

    # By Duration ranges
    print_section('ANALYSIS BY DURATION (bars)')
    dur_ranges = [(0, 5), (5, 10), (10, 20), (20, 50), (50, 100), (100, 200), (200, 500)]
    analyze_by_range(
        [t for t in trades if 'duration_bars' in t],
        lambda t: t['duration_bars'],
        dur_ranges,
        'Duration'
    )

    print('\n' + '=' * 60)


if __name__ == '__main__':
    main()
