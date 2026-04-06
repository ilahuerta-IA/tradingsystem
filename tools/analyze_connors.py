"""
CONNORS RSI(2) Strategy Trade Log Analyzer

Analyzes CONNORS trade logs to evaluate performance across key dimensions:
RSI at entry, bars held, exit reason, year stability, month seasonality,
ATR regime, and position size.

Usage:
    python analyze_connors.py                            # Analyze latest CONNORS log
    python analyze_connors.py CONNORS_trades_xxx.txt     # Analyze specific log
    python analyze_connors.py --all                      # Analyze all CONNORS logs combined

Author: Ivan
Version: 1.0.0
"""
import os
import sys
import re
import math
from datetime import datetime
from collections import defaultdict
from typing import List, Dict, Optional, Tuple
import argparse


# =============================================================================
# CONFIGURATION
# =============================================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, '..', 'logs'))

MIN_TRADES_FOR_BEST = 5


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def print_section(title: str, char: str = '=', width: int = 70):
    """Print formatted section header."""
    print(f'\n{char * width}')
    print(f'{title}')
    print(char * width)


def format_pf(pf: float) -> str:
    """Format profit factor."""
    return f'{pf:.2f}' if pf < 100 else 'INF'


def _auto_ranges(values, num_bins=8):
    """Generate adaptive range bins based on actual data distribution."""
    if not values:
        return []
    lo, hi = min(values), max(values)
    if lo == hi:
        return [(lo, lo + 1)]
    spread = hi - lo
    raw_step = spread / num_bins
    magnitude = 10 ** math.floor(math.log10(raw_step))
    residual = raw_step / magnitude
    if residual <= 1.0:
        nice = 1.0
    elif residual <= 2.0:
        nice = 2.0
    elif residual <= 2.5:
        nice = 2.5
    elif residual <= 5.0:
        nice = 5.0
    else:
        nice = 10.0
    step = nice * magnitude
    bin_lo = math.floor(lo / step) * step
    bins = []
    while bin_lo < hi:
        bin_hi = bin_lo + step
        bins.append((bin_lo, bin_hi))
        bin_lo = bin_hi
    return bins


# =============================================================================
# LOG PARSING
# =============================================================================

def find_latest_log(log_dir: str, prefix: str = 'CONNORS_trades_') -> Optional[str]:
    """Find the most recent CONNORS log file by modification time."""
    if not os.path.exists(log_dir):
        return None
    logs = [f for f in os.listdir(log_dir)
            if f.startswith(prefix) and f.endswith('.txt')]
    if not logs:
        return None
    logs.sort(key=lambda f: os.path.getmtime(os.path.join(log_dir, f)),
              reverse=True)
    return logs[0]


def find_all_logs(log_dir: str, prefix: str = 'CONNORS_trades_') -> List[str]:
    """Find all CONNORS log files."""
    if not os.path.exists(log_dir):
        return []
    return sorted([f for f in os.listdir(log_dir)
                   if f.startswith(prefix) and f.endswith('.txt')])


def parse_config_header(content: str) -> Dict:
    """Parse CONNORS configuration header from trade log."""
    config = {}

    match = re.search(r'RSI: period=(\d+), threshold=<(\d+)', content)
    if match:
        config['rsi_period'] = int(match.group(1))
        config['rsi_threshold'] = int(match.group(2))

    match = re.search(r'SMA Trend: (\d+), SMA Exit: (\d+)', content)
    if match:
        config['sma_trend'] = int(match.group(1))
        config['sma_exit'] = int(match.group(2))

    match = re.search(r'Max Hold: (\d+) days', content)
    if match:
        config['max_hold_days'] = int(match.group(1))

    match = re.search(r'ATR: period=(\d+)', content)
    if match:
        config['atr_period'] = int(match.group(1))

    match = re.search(r'Protective Stop: ON \(([\d.]+)x ATR\)', content)
    if match:
        config['protective_stop'] = float(match.group(1))
    elif 'Protective Stop: OFF' in content:
        config['protective_stop'] = None

    match = re.search(r'Take Profit: ON \(([\d.]+)x ATR\)', content)
    if match:
        config['take_profit'] = float(match.group(1))
    elif 'Take Profit: OFF' in content:
        config['take_profit'] = None

    match = re.search(r'Sizing: (\w+)', content)
    if match:
        config['sizing_mode'] = match.group(1)

    return config


def parse_connors_log(filepath: str) -> Tuple[List[Dict], Dict]:
    """
    Parse CONNORS trade log file.

    Expected format:
        ENTRY #N
        Time: YYYY-MM-DD HH:MM:SS
        Entry Price: X.XX
        Size: N contracts
        RSI(2): X.X
        ATR: X.XX
        Protective Stop: X.XX   (optional)
        Take Profit: X.XX       (optional)

        EXIT #N
        Time: YYYY-MM-DD HH:MM:SS
        Exit Reason: REASON
        P&L: $X.XX
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Parse entries — flexible pattern for optional SL/TP lines
    entries = re.findall(
        r'ENTRY #(\d+)\s*\n'
        r'Time: ([\d-]+ [\d:]+)\s*\n'
        r'Entry Price: ([\d.]+)\s*\n'
        r'Size: (\d+) contracts\s*\n'
        r'RSI\(2\): ([\d.]+)\s*\n'
        r'ATR: ([\d.]+)',
        content,
        re.IGNORECASE
    )

    # Parse protective stop values per entry
    stop_values = {}
    for m in re.finditer(
        r'ENTRY #(\d+).*?Protective Stop: ([\d.]+)',
        content, re.DOTALL
    ):
        stop_values[int(m.group(1))] = float(m.group(2))

    # Parse take profit values per entry
    tp_values = {}
    for m in re.finditer(
        r'ENTRY #(\d+).*?Take Profit: ([\d.]+)',
        content, re.DOTALL
    ):
        tp_values[int(m.group(1))] = float(m.group(2))

    # Parse exits
    exits_raw = re.findall(
        r'EXIT #(\d+)\s*\n'
        r'Time: ([^\n]+)\s*\n'
        r'Exit Reason: ([^\n]+)\s*\n'
        r'P&L: \$([-\d,.]+)',
        content,
        re.IGNORECASE
    )

    exits_by_id = {}
    for ex in exits_raw:
        exits_by_id[int(ex[0])] = ex

    # Build trades list
    trades = []
    skipped = 0
    for entry in entries:
        trade_id = int(entry[0])
        entry_time = datetime.strptime(entry[1], '%Y-%m-%d %H:%M:%S')

        trade = {
            'id': trade_id,
            'datetime': entry_time,
            'entry_price': float(entry[2]),
            'size': int(entry[3]),
            'rsi': float(entry[4]),
            'atr': float(entry[5]),
            'stop': stop_values.get(trade_id),
            'tp': tp_values.get(trade_id),
            'year': entry_time.year,
            'month': entry_time.month,
            'day_of_week': entry_time.weekday(),
        }

        ex = exits_by_id.get(trade_id)
        if ex:
            exit_time_str = ex[1].strip()
            exit_reason = ex[2].strip()
            if exit_time_str == 'N/A' or exit_reason == 'N/A':
                skipped += 1
                continue
            trade['exit_time'] = datetime.strptime(exit_time_str, '%Y-%m-%d %H:%M:%S')
            trade['exit_reason'] = exit_reason
            trade['pnl'] = float(ex[3].replace(',', ''))
            trade['bars_held'] = (trade['exit_time'] - trade['datetime']).days
            trade['win'] = trade['pnl'] > 0
        else:
            skipped += 1
            continue

        trades.append(trade)

    if skipped:
        print(f'  (Skipped {skipped} incomplete trades)')

    config = parse_config_header(content)
    return trades, config


# =============================================================================
# METRICS
# =============================================================================

def calculate_metrics(trades: List[Dict]) -> Optional[Dict]:
    """Calculate trading metrics for a list of trades."""
    if not trades:
        return None

    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]

    gross_profit = sum(t['pnl'] for t in wins)
    gross_loss = sum(abs(t['pnl']) for t in losses)

    return {
        'n': len(trades),
        'wins': len(wins),
        'losses': len(losses),
        'pf': gross_profit / gross_loss if gross_loss > 0 else float('inf'),
        'wr': len(wins) / len(trades) * 100 if trades else 0,
        'avg_pnl': sum(t['pnl'] for t in trades) / len(trades),
        'net_pnl': gross_profit - gross_loss,
        'gross_profit': gross_profit,
        'gross_loss': gross_loss,
    }


# =============================================================================
# GENERIC ANALYSIS HELPERS
# =============================================================================

def analyze_by_group(trades: List[Dict], key_func, group_name: str,
                     format_func=str):
    """Generic analysis by grouping key."""
    groups = defaultdict(list)
    for t in trades:
        groups[key_func(t)].append(t)

    print(f'\n{"":1}{group_name:15} | Trades | Win%  | PF   | Avg PnL  | Net P&L')
    print('-' * 70)

    best_pf, best_key = 0, None
    for key in sorted(groups.keys()):
        m = calculate_metrics(groups[key])
        if m:
            pf_str = format_pf(m['pf'])
            print(f' {format_func(key):15} | {m["n"]:6d} | {m["wr"]:4.0f}% '
                  f'| {pf_str:>4} | ${m["avg_pnl"]:>+8.0f} | ${m["net_pnl"]:>+10,.0f}')
            if m['pf'] > best_pf and m['n'] >= MIN_TRADES_FOR_BEST:
                best_pf = m['pf']
                best_key = key
    if best_key is not None:
        print(f'\n >> Best: {format_func(best_key)} (PF={format_pf(best_pf)}, '
              f'n={len(groups[best_key])})')


def analyze_by_range(trades: List[Dict], value_func, ranges,
                     range_name: str, decimals: int = 1):
    """Analyze by value ranges with auto-adaptive bins."""
    print(f'\n{"":1}{range_name:15} | Trades | Win%  | PF   | Avg PnL  | Net P&L')
    print('-' * 70)

    best_pf, best_label = 0, None
    for low, high in ranges:
        filtered = [t for t in trades if low <= value_func(t) < high]
        if filtered:
            m = calculate_metrics(filtered)
            pf_str = format_pf(m['pf'])
            label = f'{low:.{decimals}f}-{high:.{decimals}f}'
            print(f' {label:15} | {m["n"]:6d} | {m["wr"]:4.0f}% '
                  f'| {pf_str:>4} | ${m["avg_pnl"]:>+8.0f} | ${m["net_pnl"]:>+10,.0f}')
            if m['pf'] > best_pf and m['n'] >= MIN_TRADES_FOR_BEST:
                best_pf = m['pf']
                best_label = label
    if best_label:
        print(f'\n >> Best range: {best_label} (PF={format_pf(best_pf)})')


# =============================================================================
# CONNORS-SPECIFIC ANALYSIS FUNCTIONS
# =============================================================================

def print_config(config: Dict):
    """Print parsed configuration."""
    print_section('CONFIGURATION (from log header)')
    if not config:
        print("No configuration found")
        return

    if 'rsi_period' in config:
        print(f"RSI:          period={config['rsi_period']}, threshold=<{config.get('rsi_threshold', '?')}")
    if 'sma_trend' in config:
        print(f"SMA Trend:    {config['sma_trend']}")
    if 'sma_exit' in config:
        print(f"SMA Exit:     {config['sma_exit']}")
    if 'max_hold_days' in config:
        print(f"Max Hold:     {config['max_hold_days']} days")
    if config.get('protective_stop') is not None:
        print(f"Prot. Stop:   {config['protective_stop']}x ATR")
    else:
        print("Prot. Stop:   OFF")
    if config.get('take_profit') is not None:
        print(f"Take Profit:  {config['take_profit']}x ATR")
    else:
        print("Take Profit:  OFF")
    if 'sizing_mode' in config:
        print(f"Sizing:       {config['sizing_mode']}")


def print_summary(trades: List[Dict]):
    """Print overall summary statistics."""
    print_section('OVERALL SUMMARY')
    if not trades:
        print('No trades to analyze')
        return

    m = calculate_metrics(trades)
    print(f'Total Trades:     {m["n"]}')
    print(f'Wins:             {m["wins"]}')
    print(f'Losses:           {m["losses"]}')
    print(f'Win Rate:         {m["wr"]:.1f}%')
    print(f'Profit Factor:    {format_pf(m["pf"])}')
    print(f'Avg PnL:          ${m["avg_pnl"]:+,.0f}')
    print(f'Gross Profit:     ${m["gross_profit"]:+,.0f}')
    print(f'Gross Loss:       ${m["gross_loss"]:,.0f}')
    print(f'Net P&L:          ${m["net_pnl"]:+,.0f}')

    dates = sorted([t['datetime'] for t in trades])
    print(f'\nDate Range:       {dates[0]} to {dates[-1]}')

    # RSI stats
    rsis = [t['rsi'] for t in trades]
    print(f'\nRSI(2) Range:     {min(rsis):.1f} to {max(rsis):.1f}')
    print(f'RSI(2) Avg:       {sum(rsis)/len(rsis):.1f}')

    # ATR stats
    atrs = [t['atr'] for t in trades]
    print(f'\nATR Range:        {min(atrs):.2f} to {max(atrs):.2f}')
    print(f'ATR Avg:          {sum(atrs)/len(atrs):.2f}')

    # Holding stats
    holds = [t.get('bars_held', 0) for t in trades]
    print(f'\nBars Held Range:  {min(holds)} to {max(holds)}')
    print(f'Bars Held Avg:    {sum(holds)/len(holds):.1f}')

    # Consecutive wins/losses
    max_wins, max_losses, curr_wins, curr_losses = 0, 0, 0, 0
    for t in trades:
        if t['pnl'] > 0:
            curr_wins += 1
            max_wins = max(max_wins, curr_wins)
            curr_losses = 0
        else:
            curr_losses += 1
            max_losses = max(max_losses, curr_losses)
            curr_wins = 0
    print(f'\nMax Consec. Wins:   {max_wins}')
    print(f'Max Consec. Losses: {max_losses}')


def analyze_by_rsi(trades: List[Dict]):
    """Analyze performance by RSI(2) at entry."""
    print_section('ANALYSIS BY RSI(2) AT ENTRY')
    print('  RSI(2) measures oversold depth. Lower RSI = deeper dip.')
    print('  Connors threshold = <10. This shows performance per RSI range.')
    print('  If RSI<5 outperforms RSI 5-10, consider tightening threshold.')
    print()
    rsis = [t['rsi'] for t in trades]
    ranges = _auto_ranges(rsis, num_bins=8)
    analyze_by_range(trades, lambda t: t['rsi'], ranges,
                     'RSI(2)', decimals=1)


def analyze_rsi_threshold_sweep(trades: List[Dict]):
    """Sweep RSI thresholds to find optimal entry level."""
    print_section('RSI THRESHOLD SWEEP (cumulative)')
    print('  Each row = ALL trades with RSI(2) < threshold.')
    print('  Shows what happens if we tighten/loosen the entry filter.')
    print('  Connors published: <10. This validates that choice.')
    print()

    thresholds = [3, 4, 5, 6, 7, 8, 9, 10, 12, 15, 20]

    print(f' {"RSI <":>10} | Trades | Win%  | PF   | Avg PnL  | Net P&L')
    print('-' * 65)

    best_pf, best_thresh = 0, 0
    for thresh in thresholds:
        filtered = [t for t in trades if t['rsi'] < thresh]
        if not filtered:
            continue
        m = calculate_metrics(filtered)
        pf_str = format_pf(m['pf'])
        print(f' {"< " + str(thresh):>10} | {m["n"]:6d} | {m["wr"]:4.0f}% '
              f'| {pf_str:>4} | ${m["avg_pnl"]:>+8.0f} '
              f'| ${m["net_pnl"]:>+10,.0f}')
        if m['pf'] > best_pf and m['n'] >= MIN_TRADES_FOR_BEST:
            best_pf = m['pf']
            best_thresh = thresh

    if best_thresh:
        print(f'\n >> Optimal: RSI < {best_thresh} '
              f'(PF={format_pf(best_pf)})')


def analyze_by_bars_held(trades: List[Dict]):
    """Analyze by number of bars (days) held."""
    print_section('ANALYSIS BY BARS HELD (days)')
    print('  Mean-reversion should resolve quickly (1-5 days).')
    print('  Trades held > 10 days may indicate the dip was structural, not transient.')
    print('  Max hold = 20 days (timeout). Many timeouts = weak mean-reversion.')
    print()
    bins = [(0, 1), (1, 2), (2, 3), (3, 5), (5, 8), (8, 12), (12, 20), (20, 30)]
    analyze_by_range(trades, lambda t: t.get('bars_held', 0), bins,
                     'Days held', decimals=0)


def analyze_by_exit_reason(trades: List[Dict]):
    """Analyze by exit reason distribution."""
    print_section('ANALYSIS BY EXIT REASON')
    print('  SMA_EXIT = normal exit (Close > SMA5). Best outcome.')
    print('  TIMEOUT = held max 20 days without recovery. Worst outcome.')
    print('  STOP_LOSS = protective stop hit (if enabled).')
    print('  TAKE_PROFIT = TP hit (if enabled).')
    print()
    analyze_by_group(
        trades, lambda t: t.get('exit_reason', 'UNKNOWN'),
        'Exit Reason')


def analyze_by_year(trades: List[Dict]):
    """Analyze by year for stability check."""
    print_section('ANALYSIS BY YEAR')
    print('  CRITICAL: edge must be positive in MOST years (target >= 77%).')
    print('  Connors validated: 80% positive years over 15Y.')
    print('  If only 1-2 years carry all profit, the edge is fragile.')
    print()
    analyze_by_group(
        trades, lambda t: t['year'], 'Year', str)


def analyze_by_month(trades: List[Dict]):
    """Analyze by month for seasonality."""
    print_section('ANALYSIS BY MONTH (seasonality)')
    print('  Mean-reversion may have seasonal patterns (e.g. stronger in volatile months).')
    print('  If certain months are consistently negative, consider a seasonal filter.')
    print()
    month_names = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    analyze_by_group(
        trades, lambda t: t['month'], 'Month',
        lambda m: month_names[m])


def analyze_by_day(trades: List[Dict]):
    """Analyze by day of week."""
    print_section('ANALYSIS BY DAY OF WEEK')
    print('  Entry day (Mon-Fri). Dips on Friday may resolve Monday (gap risk).')
    print()
    dow_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    analyze_by_group(
        trades, lambda t: t['day_of_week'], 'Day',
        lambda d: dow_names[d])


def analyze_by_atr(trades: List[Dict]):
    """Analyze by ATR regime (market volatility)."""
    print_section('ANALYSIS BY ATR (volatility regime)')
    print('  High ATR = volatile market = bigger dips AND bigger bounces.')
    print('  Low ATR = calm market = smaller dips, faster mean-reversion.')
    print('  If high-ATR trades have lower WR, the strategy prefers calm markets.')
    print()
    atrs = [t['atr'] for t in trades]
    ranges = _auto_ranges(atrs, num_bins=8)
    analyze_by_range(trades, lambda t: t['atr'], ranges,
                     'ATR', decimals=1)


def analyze_by_size(trades: List[Dict]):
    """Analyze by position size (contracts)."""
    print_section('ANALYSIS BY SIZE (contracts)')
    print('  In fixed mode, all trades same size. In risk mode, size varies.')
    print('  Check if larger positions amplify losses disproportionately.')
    print()
    sizes = [t['size'] for t in trades]
    if len(set(sizes)) <= 1:
        print(f'  All trades same size: {sizes[0]} contracts')
        return
    ranges = _auto_ranges(sizes, num_bins=6)
    analyze_by_range(trades, lambda t: t['size'], ranges,
                     'Size (units)', decimals=0)


def analyze_drawdown_periods(trades: List[Dict]):
    """Identify and analyze drawdown periods."""
    print_section('DRAWDOWN PERIODS')
    print('  Shows consecutive losing streaks and their total damage.')
    print('  Critical for understanding worst-case scenarios.')
    print()

    if not trades:
        return

    # Find losing streaks
    streaks = []
    current_streak = []

    for t in trades:
        if t['pnl'] <= 0:
            current_streak.append(t)
        else:
            if len(current_streak) >= 2:
                total_loss = sum(tr['pnl'] for tr in current_streak)
                streaks.append({
                    'start': current_streak[0]['datetime'],
                    'end': current_streak[-1]['datetime'],
                    'n': len(current_streak),
                    'total_loss': total_loss,
                })
            current_streak = []

    # Final streak
    if len(current_streak) >= 2:
        total_loss = sum(tr['pnl'] for tr in current_streak)
        streaks.append({
            'start': current_streak[0]['datetime'],
            'end': current_streak[-1]['datetime'],
            'n': len(current_streak),
            'total_loss': total_loss,
        })

    if not streaks:
        print('  No significant losing streaks (2+ consecutive losses)')
        return

    # Sort by total loss (worst first)
    streaks.sort(key=lambda s: s['total_loss'])

    print(f' {"Period":30} | {"Losses":>6} | {"Total Loss":>10}')
    print('-' * 55)
    for s in streaks[:10]:
        period = f"{s['start'].strftime('%Y-%m-%d')} to {s['end'].strftime('%Y-%m-%d')}"
        print(f' {period:30} | {s["n"]:6d} | ${s["total_loss"]:>+10,.0f}')


def analyze_rsi_vs_bars_matrix(trades: List[Dict]):
    """Cross-analysis: RSI quintiles x bars held."""
    print_section('RSI x BARS HELD MATRIX')
    print('  2D view: do deeper dips (lower RSI) resolve faster?')
    print('  If RSI<5 + held<3d has best PF, deep dips mean-revert quickly.')
    print()

    if len(trades) < 20:
        print('  Not enough trades for matrix analysis (need 20+)')
        return

    rsi_bins = [(0, 2), (2, 4), (4, 6), (6, 8), (8, 10)]
    bars_bins = [(0, 2), (2, 4), (4, 7), (7, 12), (12, 21)]

    header = f'{"RSI\\Days":>10}'
    for lo, hi in bars_bins:
        header += f' | {lo}-{hi:>2}d'
    print(header)
    print('-' * len(header))

    for r_lo, r_hi in rsi_bins:
        row = f'{r_lo:.0f}-{r_hi:.0f}'
        for b_lo, b_hi in bars_bins:
            cell = [t for t in trades
                    if r_lo <= t['rsi'] < r_hi
                    and b_lo <= t.get('bars_held', 0) < b_hi]
            if cell:
                m = calculate_metrics(cell)
                pf = format_pf(m['pf'])
                row += f' | {m["n"]:2d} PF={pf:>4}'
            else:
                row += f' |    {"---":>6}'
        print(f' {row}')


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Analyze CONNORS RSI(2) strategy trade logs')
    parser.add_argument('logfile', nargs='?',
                        help='Specific log file to analyze')
    parser.add_argument('--all', action='store_true',
                        help='Analyze all CONNORS logs combined')
    args = parser.parse_args()

    trades = []
    config = {}

    if args.all:
        logs = find_all_logs(LOG_DIR)
        if not logs:
            print(f'No CONNORS logs found in {LOG_DIR}')
            return
        print(f'Analyzing {len(logs)} log files...')
        for log in logs:
            filepath = os.path.join(LOG_DIR, log)
            log_trades, log_config = parse_connors_log(filepath)
            trades.extend(log_trades)
            if not config:
                config = log_config
    elif args.logfile:
        if os.path.exists(args.logfile):
            filepath = args.logfile
        else:
            filepath = os.path.join(LOG_DIR, args.logfile)
        if not os.path.exists(filepath):
            print(f'Log file not found: {filepath}')
            return
        print(f'Analyzing: {filepath}')
        trades, config = parse_connors_log(filepath)
    else:
        latest = find_latest_log(LOG_DIR)
        if not latest:
            print(f'No CONNORS logs found in {LOG_DIR}')
            return
        filepath = os.path.join(LOG_DIR, latest)
        print(f'Analyzing latest: {latest}')
        trades, config = parse_connors_log(filepath)

    if not trades:
        print('No trades parsed from log file(s)')
        return

    print(f'\nTotal trades parsed: {len(trades)}')

    # Run all analyses
    print_config(config)
    print_summary(trades)
    analyze_by_rsi(trades)
    analyze_rsi_threshold_sweep(trades)
    analyze_rsi_vs_bars_matrix(trades)
    analyze_by_bars_held(trades)
    analyze_by_exit_reason(trades)
    analyze_by_atr(trades)
    analyze_by_year(trades)
    analyze_by_month(trades)
    analyze_by_day(trades)
    analyze_by_size(trades)
    analyze_drawdown_periods(trades)

    print('\n' + '=' * 70)
    print('Analysis complete.')


if __name__ == '__main__':
    main()
