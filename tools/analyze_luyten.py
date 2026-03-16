"""
LUYTEN Strategy Analyzer (v1.0 - Opening Range Breakout)

Analysis tool for LUYTEN ORB strategy optimization.
Analyzes trade logs to find optimal parameters.

Usage:
    python analyze_luyten.py                           # Analyze latest LUYTEN log
    python analyze_luyten.py LUYTEN_trades_xxx.txt     # Analyze specific log
    python analyze_luyten.py --all                     # Analyze all LUYTEN logs combined

Key Parameters to Analyze:
- SL pips ranges
- ATR average at entry
- Consolidation bars (N bars observed)
- Entry hour / Day of week
- Exit reason distribution
"""
import os
import sys
import re
import math
from datetime import datetime
from collections import defaultdict
import argparse


# =============================================================================
# CONFIGURATION
# =============================================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, '..', 'logs'))


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def print_section(title, char='=', width=70):
    """Print formatted section header."""
    print('\n%s' % (char * width))
    print(title)
    print(char * width)


def format_pf(pf):
    """Format profit factor."""
    return '%.2f' % pf if pf < 100 else 'INF'


# =============================================================================
# LOG PARSING
# =============================================================================

def find_latest_log(log_dir, prefix='LUYTEN_trades_'):
    """Find the most recent log file with given prefix, by modification time."""
    if not os.path.exists(log_dir):
        return None
    logs = [f for f in os.listdir(log_dir)
            if f.startswith(prefix) and f.endswith('.txt')]
    if not logs:
        return None
    logs.sort(key=lambda f: os.path.getmtime(os.path.join(log_dir, f)),
              reverse=True)
    return logs[0]


def find_all_logs(log_dir, prefix='LUYTEN_trades_'):
    """Find all log files with given prefix."""
    if not os.path.exists(log_dir):
        return []
    return sorted([f for f in os.listdir(log_dir)
                   if f.startswith(prefix) and f.endswith('.txt')])


def parse_config_header(content):
    """Parse configuration header from LUYTEN trade log."""
    config = {}

    # Consolidation bars
    match = re.search(r'Consolidation: (\d+) bars', content)
    if match:
        config['consolidation_bars'] = int(match.group(1))

    # BK filters
    match = re.search(
        r'BK Above Min: ([\d.]+) pips \| BK Body Min: ([\d.]+) pips',
        content)
    if match:
        config['bk_above_min_pips'] = float(match.group(1))
        config['bk_body_min_pips'] = float(match.group(2))

    # ATR SL/TP
    match = re.search(
        r'ATR SL Mult: ([\d.]+) \| ATR TP Mult: ([\d.]+) \| SL Buffer: ([\d.]+)',
        content)
    if match:
        config['atr_sl_mult'] = float(match.group(1))
        config['atr_tp_mult'] = float(match.group(2))
        config['sl_buffer'] = float(match.group(3))

    # SL Pips Filter
    match = re.search(
        r'SL Pips Filter: ([\d.]+)-([\d.]+)', content)
    if match:
        config['sl_pips_filter'] = True
        config['sl_pips_min'] = float(match.group(1))
        config['sl_pips_max'] = float(match.group(2))
    else:
        config['sl_pips_filter'] = False

    # EOD
    match = re.search(r'EOD Close: (\d+):(\d+) UTC', content)
    if match:
        config['eod_hour'] = int(match.group(1))
        config['eod_minute'] = int(match.group(2))

    # Time filter
    match = re.search(r'Time Filter: \[([\d, ]+)\]', content)
    if match:
        config['time_filter'] = True
        config['allowed_hours'] = [
            int(h.strip()) for h in match.group(1).split(',')]
    else:
        config['time_filter'] = False

    # Day filter
    match = re.search(r'Day Filter: \[([\d, ]+)\]', content)
    if match:
        config['day_filter'] = True
        config['allowed_days'] = match.group(1)
    else:
        config['day_filter'] = False

    # Risk
    match = re.search(r'Risk: ([\d.]+)%', content)
    if match:
        config['risk_pct'] = float(match.group(1))

    # ATR
    match = re.search(r'ATR: length=(\d+), avg_period=(\d+)', content)
    if match:
        config['atr_length'] = int(match.group(1))
        config['atr_avg_period'] = int(match.group(2))

    return config


def print_config(config):
    """Print parsed configuration."""
    print_section('CONFIGURATION (from log header)')

    if not config:
        print('No configuration found in log header')
        return

    print('Consolidation: %d bars' % config.get('consolidation_bars', 0))
    print('BK Above Min: %.1f pips' % config.get('bk_above_min_pips', 0))
    print('BK Body Min: %.1f pips' % config.get('bk_body_min_pips', 0))
    print('ATR SL Mult: %.1f | ATR TP Mult: %.1f | SL Buffer: %.1f pips' % (
        config.get('atr_sl_mult', 0), config.get('atr_tp_mult', 0),
        config.get('sl_buffer', 0)))

    if config.get('eod_hour') is not None:
        print('EOD Close: %d:%02d UTC' % (
            config['eod_hour'], config.get('eod_minute', 0)))

    print('\nFilters:')
    print('  SL Pips Filter:  %s' % (
        'ENABLED %.1f-%.1f' % (config.get('sl_pips_min', 0),
                                config.get('sl_pips_max', 0))
        if config.get('sl_pips_filter') else 'DISABLED'))
    print('  Time Filter:     %s' % (
        'ENABLED %s' % config.get('allowed_hours', [])
        if config.get('time_filter') else 'DISABLED'))
    print('  Day Filter:      %s' % (
        'ENABLED %s' % config.get('allowed_days', '')
        if config.get('day_filter') else 'DISABLED'))

    if config.get('risk_pct'):
        print('  Risk: %s%%' % config['risk_pct'])


def parse_luyten_log(filepath):
    """
    Parse LUYTEN trade log file.

    Log format:
        ENTRY #N
        Time: YYYY-MM-DD HH:MM:SS
        Entry Price: X.XXXXX
        Stop Loss: X.XXXXX
        Take Profit: X.XXXXX
        SL Pips: X.X
        ATR (avg): X.XXXXXX
        Consolidation High: X.XXXXX
        Consolidation Bars: N
        --------------------------------------------------
        EXIT #N
        Time: YYYY-MM-DD HH:MM:SS
        Exit Reason: REASON
        P&L: $X.XX

    Returns (trades, config).
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    config = parse_config_header(content)

    # Entry regex
    entry_pattern = re.compile(
        r'ENTRY #(\d+)\s*\n'
        r'Time: ([\d-]+ [\d:]+)\s*\n'
        r'Entry Price: ([\d.]+)\s*\n'
        r'Stop Loss: ([\d.]+)\s*\n'
        r'Take Profit: ([\d.]+|NONE[^\n]*)\s*\n'
        r'SL Pips: ([\d.]+)\s*\n'
        r'ATR \(avg\): ([\d.]+)\s*\n'
        r'Consolidation High: ([\d.]+)\s*\n'
        r'Consolidation Bars: (\d+)\s*\n'
        r'(?:BK Above Pips: ([\d.]+)\s*\n)?'
        r'(?:BK Body Pips: ([\d.]+))?',
        re.MULTILINE
    )

    # Exit regex
    exit_pattern = re.compile(
        r'EXIT #(\d+)\s*\n'
        r'Time: ([\d-]+ [\d:]+|N/A)\s*\n'
        r'Exit Reason: (\w+)\s*\n'
        r'P&L: \$([-\d,.]+)',
        re.MULTILINE
    )

    # Parse entries
    entries = {}
    for match in entry_pattern.finditer(content):
        trade_id = int(match.group(1))
        dt = datetime.strptime(match.group(2), '%Y-%m-%d %H:%M:%S')
        tp_raw = match.group(5)
        tp = None if tp_raw.startswith('NONE') else float(tp_raw)

        entries[trade_id] = {
            'id': trade_id,
            'datetime': dt,
            'entry_price': float(match.group(3)),
            'sl': float(match.group(4)),
            'tp': tp,
            'sl_pips': float(match.group(6)),
            'atr': float(match.group(7)),
            'consolidation_high': float(match.group(8)),
            'consol_bars': int(match.group(9)),
            'bk_above_pips': float(match.group(10)) if match.group(10) else None,
            'bk_body_pips': float(match.group(11)) if match.group(11) else None,
            'hour': dt.hour,
            'day_of_week': dt.weekday(),
        }

    # Parse exits and match to entries
    for match in exit_pattern.finditer(content):
        trade_id = int(match.group(1))
        exit_reason = match.group(3)
        pnl_str = match.group(4).replace(',', '')

        # Skip rejected/cancelled orders
        if exit_reason in ('Margin', 'Canceled', 'Rejected'):
            if trade_id in entries:
                del entries[trade_id]
            continue

        if trade_id in entries:
            entries[trade_id]['exit_reason'] = exit_reason
            entries[trade_id]['pnl'] = float(pnl_str)

            # Bars held
            if match.group(2) != 'N/A':
                try:
                    exit_dt = datetime.strptime(
                        match.group(2), '%Y-%m-%d %H:%M:%S')
                    delta = exit_dt - entries[trade_id]['datetime']
                    entries[trade_id]['bars_held'] = int(
                        delta.total_seconds() / 300)  # 5-min bars
                    entries[trade_id]['exit_time'] = exit_dt
                except ValueError:
                    pass

    # Filter to closed trades only
    closed_trades = [t for t in entries.values() if 'pnl' in t]
    closed_trades.sort(key=lambda t: t['datetime'])

    return closed_trades, config


# =============================================================================
# ANALYSIS FUNCTIONS
# =============================================================================

def calculate_metrics(trades):
    """Calculate trading metrics for a list of trades."""
    if not trades:
        return {
            'n': 0, 'wins': 0, 'losses': 0,
            'pf': 0, 'wr': 0, 'avg_pnl': 0,
            'avg_win': 0, 'avg_loss': 0,
            'gross_profit': 0, 'gross_loss': 0,
        }

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
        'avg_win': sum(t['pnl'] for t in wins) / len(wins) if wins else 0,
        'avg_loss': sum(t['pnl'] for t in losses) / len(losses) if losses else 0,
        'gross_profit': gross_profit,
        'gross_loss': gross_loss,
    }


def _auto_step(trades, key, target_bins=8):
    """Compute a nice step size for ~target_bins bins from actual data range.
    Uses 5th-95th percentile to ignore outliers that inflate the range."""
    values = sorted([t[key] for t in trades if key in t])
    if not values:
        return 1.0
    # Use percentile range to avoid outlier-inflated bins
    lo = values[max(0, int(len(values) * 0.05))]
    hi = values[min(len(values) - 1, int(len(values) * 0.95))]
    span = hi - lo
    if span <= 0:
        span = max(values) - min(values)
    if span <= 0:
        return 1.0
    raw = span / target_bins
    mag = 10 ** math.floor(math.log10(raw))
    for nice in [1, 2, 2.5, 5, 10]:
        step = nice * mag
        if span / step <= target_bins * 1.5:
            return step
    return raw


def _print_range_table(trades, key, step, label, fmt='%.0f'):
    """Generic range analysis for any numeric key."""
    valid_trades = [t for t in trades if key in t]
    if not valid_trades:
        print('No data available for %s' % label)
        return

    values = [t[key] for t in valid_trades]
    min_v = min(values)
    max_v = max(values)

    print('%s range: %s to %s' % (label, fmt % min_v, fmt % max_v))
    print('\n%-15s %8s %6s %8s %8s %10s' % (
        'Range', 'Trades', 'Wins', 'WR%', 'PF', 'Avg PnL'))
    print('-' * 60)

    current = (min_v // step) * step
    best_pf = 0
    best_range = None

    while current <= max_v + step:
        range_max = current + step
        range_trades = [t for t in valid_trades if current <= t[key] < range_max]
        if range_trades:
            m = calculate_metrics(range_trades)
            range_str = '%s-%s' % (fmt % current, fmt % range_max)
            print('%-15s %8d %6d %7.1f%% %8s %+10.1f' % (
                range_str, m['n'], m['wins'], m['wr'],
                format_pf(m['pf']), m['avg_pnl']))
            if m['pf'] > best_pf and m['n'] >= 3:
                best_pf = m['pf']
                best_range = (current, range_max)
        current += step

    if best_range:
        print('\nBest %s range: %s-%s (PF=%s)' % (
            label, fmt % best_range[0], fmt % best_range[1],
            format_pf(best_pf)))


# =============================================================================
# DIMENSION ANALYSES
# =============================================================================

def analyze_by_atr_range(trades):
    """Analyze performance by entry ATR average."""
    print_section('ANALYSIS BY ENTRY ATR RANGE')
    if not trades:
        print('No trades to analyze')
        return
    step = _auto_step(trades, 'atr')
    _print_range_table(trades, 'atr', step, 'ATR', fmt='%.4f')


def analyze_by_sl_pips(trades, step=10.0):
    """Analyze performance by SL pips ranges."""
    print_section('ANALYSIS BY SL PIPS RANGE')
    if not trades:
        print('No trades to analyze')
        return
    _print_range_table(trades, 'sl_pips', step, 'SL Pips', fmt='%.0f')


def analyze_by_consol_bars(trades):
    """Analyze performance by consolidation bars."""
    print_section('ANALYSIS BY CONSOLIDATION BARS')
    if not trades:
        print('No trades to analyze')
        return
    _print_range_table(trades, 'consol_bars', 1, 'Consol Bars', fmt='%.0f')


def analyze_by_hour(trades):
    """Analyze performance by entry hour."""
    print_section('ANALYSIS BY ENTRY HOUR (UTC)')
    if not trades:
        print('No trades to analyze')
        return

    hour_groups = defaultdict(list)
    for t in trades:
        hour_groups[t['hour']].append(t)

    print('\n%6s %8s %6s %8s %8s %10s' % (
        'Hour', 'Trades', 'Wins', 'WR%', 'PF', 'Avg PnL'))
    print('-' * 50)

    profitable_hours = []
    for hour in range(24):
        if hour in hour_groups:
            m = calculate_metrics(hour_groups[hour])
            print('%6d %8d %6d %7.1f%% %8s %+10.1f' % (
                hour, m['n'], m['wins'], m['wr'],
                format_pf(m['pf']), m['avg_pnl']))
            if m['pf'] >= 1.5 and m['n'] >= 5:
                profitable_hours.append(hour)

    if profitable_hours:
        print('\nSuggested hours (PF >= 1.5, n >= 5): %s' % profitable_hours)


def analyze_by_day(trades):
    """Analyze performance by day of week."""
    print_section('ANALYSIS BY DAY OF WEEK')
    if not trades:
        print('No trades to analyze')
        return

    day_names = ['Monday', 'Tuesday', 'Wednesday',
                 'Thursday', 'Friday', 'Saturday', 'Sunday']
    day_groups = defaultdict(list)
    for t in trades:
        day_groups[t['day_of_week']].append(t)

    print('\n%-12s %8s %6s %8s %8s %10s' % (
        'Day', 'Trades', 'Wins', 'WR%', 'PF', 'Avg PnL'))
    print('-' * 55)

    profitable_days = []
    for day in range(7):
        if day in day_groups:
            m = calculate_metrics(day_groups[day])
            print('%-12s %8d %6d %7.1f%% %8s %+10.1f' % (
                day_names[day], m['n'], m['wins'], m['wr'],
                format_pf(m['pf']), m['avg_pnl']))
            if m['pf'] >= 1.5:
                profitable_days.append(day)

    if profitable_days:
        print('\nSuggested days (PF >= 1.5): %s' %
              [day_names[d] for d in profitable_days])


def analyze_by_exit_reason(trades):
    """Analyze performance by exit reason."""
    print_section('ANALYSIS BY EXIT REASON')
    if not trades:
        print('No trades to analyze')
        return

    reason_groups = defaultdict(list)
    for t in trades:
        reason_groups[t.get('exit_reason', 'UNKNOWN')].append(t)

    print('\n%-15s %8s %6s %8s %8s %10s' % (
        'Reason', 'Trades', 'Wins', 'WR%', 'PF', 'Avg PnL'))
    print('-' * 58)

    for reason in sorted(reason_groups.keys()):
        m = calculate_metrics(reason_groups[reason])
        print('%-15s %8d %6d %7.1f%% %8s %+10.1f' % (
            reason, m['n'], m['wins'], m['wr'],
            format_pf(m['pf']), m['avg_pnl']))


def analyze_by_consolidation_high(trades, pip_value=0.01):
    """Analyze performance by distance from consolidation high to entry."""
    print_section('ANALYSIS BY DISTANCE FROM CONSOLIDATION HIGH (pips)')
    if not trades:
        print('No trades to analyze')
        return
    for t in trades:
        t['_above_pips'] = (
            (t['entry_price'] - t['consolidation_high']) / pip_value
            if pip_value > 0 else 0
        )
    step = _auto_step(trades, '_above_pips')
    _print_range_table(trades, '_above_pips', step, 'Above Consol (pips)', fmt='%.1f')


def analyze_by_bk_above(trades):
    """Analyze performance by breakout above-consolidation-high distance (pips)."""
    print_section('ANALYSIS BY BK ABOVE PIPS')
    valid = [t for t in trades if t.get('bk_above_pips') is not None]
    if not valid:
        print('No BK Above Pips data available (re-run backtest to generate)')
        return
    step = _auto_step(valid, 'bk_above_pips')
    _print_range_table(valid, 'bk_above_pips', step, 'BK Above Pips', fmt='%.1f')


def analyze_by_bk_body(trades):
    """Analyze performance by breakout candle body size (pips)."""
    print_section('ANALYSIS BY BK BODY PIPS')
    valid = [t for t in trades if t.get('bk_body_pips') is not None]
    if not valid:
        print('No BK Body Pips data available (re-run backtest to generate)')
        return
    step = _auto_step(valid, 'bk_body_pips')
    _print_range_table(valid, 'bk_body_pips', step, 'BK Body Pips', fmt='%.1f')


def print_summary(trades, config=None):
    """Print overall summary."""
    print_section('OVERALL SUMMARY')
    if not trades:
        print('No trades to analyze')
        return

    m = calculate_metrics(trades)

    print('Total Trades:     %d' % m['n'])
    print('Wins:             %d' % m['wins'])
    print('Losses:           %d' % m['losses'])
    print('Win Rate:         %.1f%%' % m['wr'])
    print('Profit Factor:    %s' % format_pf(m['pf']))
    print('Avg PnL:          $%s' % format(m['avg_pnl'], '+,.0f'))
    print('Avg Win:          $%s' % format(m['avg_win'], '+,.0f'))
    print('Avg Loss:         $%s' % format(m['avg_loss'], ',.0f'))
    print('Gross Profit:     $%s' % format(m['gross_profit'], '+,.0f'))
    print('Gross Loss:       $%s' % format(m['gross_loss'], ',.0f'))

    # Date range
    dates = sorted([t['datetime'] for t in trades])
    print('\nDate Range: %s to %s' % (dates[0], dates[-1]))

    # SL pips stats
    sl_pips = [t['sl_pips'] for t in trades]
    print('\nSL Pips Range:    %.1f to %.1f' % (min(sl_pips), max(sl_pips)))
    print('SL Pips Avg:      %.1f' % (sum(sl_pips) / len(sl_pips)))

    # ATR stats
    atrs = [t['atr'] for t in trades]
    print('\nATR Range:        %.6f to %.6f' % (min(atrs), max(atrs)))
    print('ATR Avg:          %.6f' % (sum(atrs) / len(atrs)))

    # Consolidation high stats
    highs = [t['consolidation_high'] for t in trades]
    print('\nConsol High Range: %.5f to %.5f' % (min(highs), max(highs)))

    # Bars held stats
    bars = [t.get('bars_held', 0) for t in trades if t.get('bars_held')]
    if bars:
        print('\nBars Held Range:  %d to %d' % (min(bars), max(bars)))
        print('Bars Held Avg:    %.1f' % (sum(bars) / len(bars)))


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Analyze LUYTEN strategy trade logs (v1.0 ORB)')
    parser.add_argument('logfile', nargs='?',
                        help='Specific log file to analyze')
    parser.add_argument('--all', action='store_true',
                        help='Analyze all logs combined')
    args = parser.parse_args()

    trades = []
    config = {}

    if args.all:
        logs = find_all_logs(LOG_DIR)
        if not logs:
            print('No LUYTEN logs found in %s' % LOG_DIR)
            return
        print('Analyzing %d log files...' % len(logs))
        for log in logs:
            filepath = os.path.join(LOG_DIR, log)
            log_trades, log_config = parse_luyten_log(filepath)
            trades.extend(log_trades)
            if not config:
                config = log_config
    elif args.logfile:
        if os.path.exists(args.logfile):
            filepath = args.logfile
        else:
            filepath = os.path.join(LOG_DIR, args.logfile)
        if not os.path.exists(filepath):
            print('Log file not found: %s' % filepath)
            return
        print('Analyzing: %s' % filepath)
        trades, config = parse_luyten_log(filepath)
    else:
        latest = find_latest_log(LOG_DIR)
        if not latest:
            print('No LUYTEN logs found in %s' % LOG_DIR)
            return
        filepath = os.path.join(LOG_DIR, latest)
        print('Analyzing latest: %s' % filepath)
        trades, config = parse_luyten_log(filepath)

    if not trades:
        print('No trades parsed from log file(s)')
        return

    print('\nTotal trades parsed: %d' % len(trades))

    # Configuration
    print_config(config)

    # Overall summary
    print_summary(trades, config)

    # Analyses
    analyze_by_atr_range(trades)
    analyze_by_sl_pips(trades)
    analyze_by_consol_bars(trades)
    analyze_by_bk_above(trades)
    analyze_by_bk_body(trades)

    # Temporal analyses
    analyze_by_hour(trades)
    analyze_by_day(trades)
    analyze_by_exit_reason(trades)


if __name__ == '__main__':
    main()
