"""
CERES Strategy Analyzer

Comprehensive analysis tool for CERES strategy optimization.
Analyzes trade logs to find optimal parameters for Opening Range + Pullback entries.

Usage:
    python analyze_ceres.py                           # Analyze latest CERES log
    python analyze_ceres.py CERES_trades_xxx.txt      # Analyze specific log
    python analyze_ceres.py --all                     # Analyze all CERES logs combined

Key Parameters to Analyze:
- OR Height ranges (Opening Range size)
- OR ER ranges (Efficiency Ratio of the OR)
- OR ATR ranges (volatility during OR)
- SL pips ranges
- Entry hour / Day of week
- Exit reason distribution

Author: Ivan
Version: 1.0.0
"""
import os
import sys
import re
from datetime import datetime
from collections import defaultdict
from typing import List, Dict, Optional
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

def find_latest_log(log_dir, prefix='CERES_trades_'):
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


def find_all_logs(log_dir, prefix='CERES_trades_'):
    """Find all log files with given prefix."""
    if not os.path.exists(log_dir):
        return []
    return sorted([f for f in os.listdir(log_dir)
                   if f.startswith(prefix) and f.endswith('.txt')])


def parse_config_header(content):
    """Parse configuration header from CERES trade log."""
    config = {}

    # Opening Range
    match = re.search(
        r'Opening Range: (\d+) candles, open=(\d+):(\d+) UTC', content)
    if match:
        config['or_candles'] = int(match.group(1))
        config['open_hour'] = int(match.group(2))
        config['open_minute'] = int(match.group(3))

    # PB Angle filter
    match = re.search(r'PB Angle Filter: ENABLED \| Range: ([\-\d.]+)-([\-\d.]+) deg', content)
    if match:
        config['pb_angle_filter'] = True
        config['pb_angle_min'] = float(match.group(1))
        config['pb_angle_max'] = float(match.group(2))
    else:
        config['pb_angle_filter'] = 'PB Angle Filter: DISABLED' not in content

    # ER OR filter
    match = re.search(r'ER OR Filter: ENABLED \| (?:Threshold|Range): ([\d.]+)(?:-([\d.]+))?', content)
    if match:
        config['er_or_filter'] = True
        config['er_or_threshold'] = float(match.group(1))
    else:
        config['er_or_filter'] = False

    # ER HTF filter
    match = re.search(
        r'ER HTF Filter: ENABLED \| Threshold: ([\d.]+), Period: (\d+), TF: (\d+)m',
        content)
    if match:
        config['er_htf_filter'] = True
        config['er_htf_threshold'] = float(match.group(1))
        config['er_htf_period'] = int(match.group(2))
        config['er_htf_tf'] = int(match.group(3))
    else:
        config['er_htf_filter'] = False

    # Pullback (new Ogle format or legacy)
    match = re.search(r'Pullback Candles: (\d+) bearish, max_bars=(\d+), max_retries=(\d+)', content)
    if match:
        config['pb_candles'] = int(match.group(1))
        config['pb_max'] = int(match.group(2))
        config['pb_retries'] = int(match.group(3))
    else:
        # Legacy format
        match = re.search(r'Pullback: min=(\d+), max=(\d+) bars', content)
        if match:
            config['pb_min'] = int(match.group(1))
            config['pb_max'] = int(match.group(2))

    # Window config (new Ogle format)
    match = re.search(r'Window: periods=(\d+), offset_mult=([\d.]+), buffer=([\d.]+) pips', content)
    if match:
        config['window_periods'] = int(match.group(1))
        config['offset_mult'] = float(match.group(2))
        config['breakout_buffer'] = float(match.group(3))
    else:
        # Legacy breakout buffer
        match = re.search(r'Breakout Buffer: ([\d.]+) pips', content)
        if match:
            config['breakout_buffer'] = float(match.group(1))

    # SL Mode
    match = re.search(r'SL Mode: (\w+)', content)
    if match:
        config['sl_mode'] = match.group(1)

    # TP Mode
    match = re.search(r'TP Mode: (\w+)', content)
    if match:
        config['tp_mode'] = match.group(1)

    # SL Pips Filter
    match = re.search(
        r'SL Pips Filter: ENABLED \| Range: ([\d.]+)-([\d.]+)', content)
    if match:
        config['sl_pips_filter'] = True
        config['sl_pips_min'] = float(match.group(1))
        config['sl_pips_max'] = float(match.group(2))
    else:
        config['sl_pips_filter'] = False

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

    # EOD
    match = re.search(r'EOD Close: (\d+):(\d+) UTC', content)
    if match:
        config['eod_hour'] = int(match.group(1))
        config['eod_minute'] = int(match.group(2))

    # Pip value
    match = re.search(r'Pip Value: ([\d.]+)', content)
    if match:
        config['pip_value'] = float(match.group(1))

    # Risk
    match = re.search(r'Risk: ([\d.]+)%', content)
    if match:
        config['risk_pct'] = float(match.group(1))

    return config


def print_config(config):
    """Print parsed configuration."""
    print_section('CONFIGURATION (from log header)')

    if not config:
        print('No configuration found in log header')
        return

    if 'or_candles' in config:
        print('OR: %d candles, open=%d:%02d UTC' % (
            config['or_candles'], config.get('open_hour', 0),
            config.get('open_minute', 0)))

    if config.get('sl_mode'):
        print('SL Mode: %s' % config['sl_mode'])
    if config.get('tp_mode'):
        print('TP Mode: %s' % config['tp_mode'])

    # Pullback config (new Ogle format or legacy)
    if config.get('pb_candles') is not None:
        print('Pullback: %d bearish candles, max_bars=%d, max_retries=%d' % (
            config['pb_candles'], config.get('pb_max', 0),
            config.get('pb_retries', 0)))
    elif config.get('pb_min') is not None:
        print('Pullback: min=%d, max=%d bars (legacy)' % (
            config['pb_min'], config.get('pb_max', 0)))

    if config.get('window_periods') is not None:
        print('Window: periods=%d, offset_mult=%.2f, buffer=%.1f pips' % (
            config['window_periods'], config.get('offset_mult', 0),
            config.get('breakout_buffer', 0)))
    elif config.get('breakout_buffer') is not None:
        print('Breakout Buffer: %.1f pips' % config['breakout_buffer'])

    if config.get('pip_value'):
        print('Pip Value: %s' % config['pip_value'])
    if config.get('risk_pct'):
        print('Risk: %s%%' % config['risk_pct'])

    print('\nFilters:')
    print('  PB Angle Filter: %s' % (
        'ENABLED %.1f-%.1f deg' % (config.get('pb_angle_min', 0),
                                    config.get('pb_angle_max', 0))
        if config.get('pb_angle_filter') else 'DISABLED'))
    print('  ER OR Filter:    %s' % (
        'ENABLED >= %.2f' % config.get('er_or_threshold', 0)
        if config.get('er_or_filter') else 'DISABLED'))
    print('  ER HTF Filter:   %s' % (
        'ENABLED >= %.2f (period=%d, %dm)' % (
            config.get('er_htf_threshold', 0),
            config.get('er_htf_period', 0),
            config.get('er_htf_tf', 0))
        if config.get('er_htf_filter') else 'DISABLED'))
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

    if config.get('eod_hour') is not None:
        print('  EOD Close:       %d:%02d UTC' % (
            config['eod_hour'], config.get('eod_minute', 0)))


def parse_ceres_log(filepath):
    """
    Parse CERES trade log file.

    Expected format (v0.7+):
        ENTRY #N
        Time: YYYY-MM-DD HH:MM:SS
        Entry Price: X.XXXXX
        Stop Loss: X.XXXXX
        Take Profit: X.XXXXX | NONE (EOD)
        SL Pips: XX.X
        ATR (avg): X.XXXXXX
        OR HH: X.XXXXX
        OR LL: X.XXXXX
        OR Height: X.XXXXX
        OR ER: X.XXXX
        OR ATR Avg: X.XXXXXX
        SL Mode: xxx
        TP Mode: xxx
        PB Bars: N
        PB Angle: XX.XX
        PB Depth: XX.X%
        Rearm Count: N
        --------------------------------------------------

        EXIT #N
        Time: YYYY-MM-DD HH:MM:SS
        Exit Reason: REASON
        P&L: $X,XXX.XX

    Also supports legacy formats (v0.7 without Rearm Count, and older with OR Angle).
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Parse entries - flexible regex for CERES format
    # Try v0.8 format first (with Rearm Count)
    entries = re.findall(
        r'ENTRY #(\d+)\s*\n'
        r'Time: ([\d-]+ [\d:]+)\s*\n'
        r'Entry Price: ([\d.]+)\s*\n'
        r'Stop Loss: ([\d.]+)\s*\n'
        r'Take Profit: ([\d.]+|NONE[^\n]*)\s*\n'
        r'SL Pips: ([\d.]+)\s*\n'
        r'ATR \(avg\): ([\d.]+)\s*\n'
        r'OR HH: ([\d.]+)\s*\n'
        r'OR LL: ([\d.]+)\s*\n'
        r'OR Height: ([\d.]+)\s*\n'
        r'OR ER: ([\d.]+)\s*\n'
        r'OR ATR Avg: ([\d.]+)\s*\n'
        r'SL Mode: (\w+)\s*\n'
        r'TP Mode: (\w+)\s*\n'
        r'PB Bars: (\d+)\s*\n'
        r'PB Angle: ([-\d.]+)\s*\n'
        r'PB Depth: ([\d.]+)%\s*\n'
        r'Rearm Count: (\d+)',
        content,
        re.IGNORECASE
    )
    format_version = 'v08' if entries else None

    if not entries:
        # Fallback: v0.7 format (no Rearm Count, no OR Angle, with PB fields)
        entries = re.findall(
            r'ENTRY #(\d+)\s*\n'
            r'Time: ([\d-]+ [\d:]+)\s*\n'
            r'Entry Price: ([\d.]+)\s*\n'
            r'Stop Loss: ([\d.]+)\s*\n'
            r'Take Profit: ([\d.]+|NONE[^\n]*)\s*\n'
            r'SL Pips: ([\d.]+)\s*\n'
            r'ATR \(avg\): ([\d.]+)\s*\n'
            r'OR HH: ([\d.]+)\s*\n'
            r'OR LL: ([\d.]+)\s*\n'
            r'OR Height: ([\d.]+)\s*\n'
            r'OR ER: ([\d.]+)\s*\n'
            r'OR ATR Avg: ([\d.]+)\s*\n'
            r'SL Mode: (\w+)\s*\n'
            r'TP Mode: (\w+)\s*\n'
            r'PB Bars: (\d+)\s*\n'
            r'PB Angle: ([-\d.]+)\s*\n'
            r'PB Depth: ([\d.]+)%',
            content,
            re.IGNORECASE
        )
        format_version = 'new' if entries else None

    if not entries:
        # Fallback: legacy format with OR Angle + PB fields
        entries = re.findall(
            r'ENTRY #(\d+)\s*\n'
            r'Time: ([\d-]+ [\d:]+)\s*\n'
            r'Entry Price: ([\d.]+)\s*\n'
            r'Stop Loss: ([\d.]+)\s*\n'
            r'Take Profit: ([\d.]+|NONE[^\n]*)\s*\n'
            r'SL Pips: ([\d.]+)\s*\n'
            r'ATR \(avg\): ([\d.]+)\s*\n'
            r'OR HH: ([\d.]+)\s*\n'
            r'OR LL: ([\d.]+)\s*\n'
            r'OR Height: ([\d.]+)\s*\n'
            r'OR Angle: ([-\d.]+)\s*\n'
            r'OR ER: ([\d.]+)\s*\n'
            r'OR ATR Avg: ([\d.]+)\s*\n'
            r'SL Mode: (\w+)\s*\n'
            r'TP Mode: (\w+)\s*\n'
            r'PB Bars: (\d+)\s*\n'
            r'PB Angle: ([-\d.]+)\s*\n'
            r'PB Depth: ([\d.]+)%',
            content,
            re.IGNORECASE
        )
        format_version = 'legacy_pb' if entries else None

    if not entries:
        # Fallback: oldest format with OR Angle, no PB fields
        entries = re.findall(
            r'ENTRY #(\d+)\s*\n'
            r'Time: ([\d-]+ [\d:]+)\s*\n'
            r'Entry Price: ([\d.]+)\s*\n'
            r'Stop Loss: ([\d.]+)\s*\n'
            r'Take Profit: ([\d.]+|NONE[^\n]*)\s*\n'
            r'SL Pips: ([\d.]+)\s*\n'
            r'ATR \(avg\): ([\d.]+)\s*\n'
            r'OR HH: ([\d.]+)\s*\n'
            r'OR LL: ([\d.]+)\s*\n'
            r'OR Height: ([\d.]+)\s*\n'
            r'OR Angle: ([-\d.]+)\s*\n'
            r'OR ER: ([\d.]+)\s*\n'
            r'OR ATR Avg: ([\d.]+)\s*\n'
            r'SL Mode: (\w+)\s*\n'
            r'TP Mode: (\w+)',
            content,
            re.IGNORECASE
        )
        format_version = 'legacy' if entries else None

    # Parse exits
    exits = re.findall(
        r'EXIT #(\d+)\s*\n'
        r'Time: ([\d-]+ [\d:]+|N/A)\s*\n'
        r'Exit Reason: (\w+)\s*\n'
        r'P&L: \$([-\d,.]+)',
        content,
        re.IGNORECASE
    )

    # Build exit lookup
    exit_dict = {int(ex[0]): ex for ex in exits}

    trades = []
    for entry in entries:
        trade_id = int(entry[0])
        entry_time = datetime.strptime(entry[1], '%Y-%m-%d %H:%M:%S')

        tp_str = entry[4]
        tp_val = float(tp_str) if tp_str.replace('.', '').isdigit() else None

        if format_version == 'v08':
            # v0.8 format: no OR Angle, groups 10=or_er, 11=or_atr_avg,
            # 12=sl_mode, 13=tp_mode, 14=pb_bars, 15=pb_angle, 16=pb_depth, 17=rearm_count
            trade = {
                'id': trade_id,
                'datetime': entry_time,
                'entry_price': float(entry[2]),
                'sl': float(entry[3]),
                'tp': tp_val,
                'sl_pips': float(entry[5]),
                'atr': float(entry[6]),
                'or_hh': float(entry[7]),
                'or_ll': float(entry[8]),
                'or_height': float(entry[9]),
                'or_er': float(entry[10]),
                'or_atr_avg': float(entry[11]),
                'sl_mode': entry[12],
                'tp_mode': entry[13],
                'hour': entry_time.hour,
                'day_of_week': entry_time.weekday(),
                'pb_bars': int(entry[14]),
                'pb_angle': float(entry[15]),
                'pb_depth_pct': float(entry[16]),
                'rearm_count': int(entry[17]),
            }
        elif format_version == 'new':
            # v0.7 format: no OR Angle, groups 10=or_er, 11=or_atr_avg,
            # 12=sl_mode, 13=tp_mode, 14=pb_bars, 15=pb_angle, 16=pb_depth
            trade = {
                'id': trade_id,
                'datetime': entry_time,
                'entry_price': float(entry[2]),
                'sl': float(entry[3]),
                'tp': tp_val,
                'sl_pips': float(entry[5]),
                'atr': float(entry[6]),
                'or_hh': float(entry[7]),
                'or_ll': float(entry[8]),
                'or_height': float(entry[9]),
                'or_er': float(entry[10]),
                'or_atr_avg': float(entry[11]),
                'sl_mode': entry[12],
                'tp_mode': entry[13],
                'hour': entry_time.hour,
                'day_of_week': entry_time.weekday(),
                'pb_bars': int(entry[14]),
                'pb_angle': float(entry[15]),
                'pb_depth_pct': float(entry[16]),
            }
        else:
            # Legacy formats: have OR Angle at group 10 (skip it)
            # groups 11=or_er, 12=or_atr_avg, 13=sl_mode, 14=tp_mode
            trade = {
                'id': trade_id,
                'datetime': entry_time,
                'entry_price': float(entry[2]),
                'sl': float(entry[3]),
                'tp': tp_val,
                'sl_pips': float(entry[5]),
                'atr': float(entry[6]),
                'or_hh': float(entry[7]),
                'or_ll': float(entry[8]),
                'or_height': float(entry[9]),
                'or_er': float(entry[11]),
                'or_atr_avg': float(entry[12]),
                'sl_mode': entry[13],
                'tp_mode': entry[14],
                'hour': entry_time.hour,
                'day_of_week': entry_time.weekday(),
            }
            # Add PB fields if legacy_pb format
            if format_version == 'legacy_pb':
                trade['pb_bars'] = int(entry[15])
                trade['pb_angle'] = float(entry[16])
                trade['pb_depth_pct'] = float(entry[17])

        # Match with exit
        if trade_id in exit_dict:
            ex = exit_dict[trade_id]
            if ex[1] != 'N/A':
                exit_time = datetime.strptime(ex[1], '%Y-%m-%d %H:%M:%S')
                trade['exit_time'] = exit_time
                trade['bars_held'] = int(
                    (exit_time - entry_time).total_seconds() / 300)
            trade['exit_reason'] = ex[2]
            trade['pnl'] = float(ex[3].replace(',', ''))

        trades.append(trade)

    # Filter to only closed trades
    closed_trades = [t for t in trades if 'pnl' in t]

    # Parse configuration header
    config = parse_config_header(content)

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


def _print_range_table(trades, key, step, label, fmt='%.0f'):
    """Generic range analysis for any numeric key. Reusable."""
    values = [t[key] for t in trades]
    min_v = min(values)
    max_v = max(values)

    print('%s range: %s to %s' % (label, fmt % min_v, fmt % max_v))
    print('\n%-15s %8s %6s %8s %8s %10s' % (
        'Range', 'Trades', 'Wins', 'WR%', 'PF', 'Avg PnL'))
    print('-' * 60)

    current = (min_v // step) * step  # Align to step
    best_pf = 0
    best_range = None

    while current <= max_v + step:
        range_max = current + step
        range_trades = [t for t in trades if current <= t[key] < range_max]
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


def analyze_by_or_height(trades, pip_value=0.01):
    """Analyze performance by Opening Range height."""
    print_section('ANALYSIS BY OR HEIGHT')
    if not trades:
        print('No trades to analyze')
        return
    # Compute OR height in pips for clearer ranges
    for t in trades:
        t['_or_height_pips'] = t['or_height'] / pip_value if pip_value > 0 else 0
    step = 50.0 if pip_value <= 0.01 else 5.0
    _print_range_table(trades, '_or_height_pips', step, 'OR Height (pips)')


def analyze_by_or_er(trades, step=0.1):
    """Analyze performance by Opening Range Efficiency Ratio."""
    print_section('ANALYSIS BY OR EFFICIENCY RATIO')
    if not trades:
        print('No trades to analyze')
        return
    _print_range_table(trades, 'or_er', step, 'OR ER', fmt='%.2f')


def analyze_by_or_atr(trades, step=0.5):
    """Analyze performance by ATR during Opening Range."""
    print_section('ANALYSIS BY OR ATR AVG')
    if not trades:
        print('No trades to analyze')
        return
    _print_range_table(trades, 'or_atr_avg', step, 'OR ATR', fmt='%.4f')


def analyze_by_atr_range(trades, step=0.5):
    """Analyze performance by entry ATR average."""
    print_section('ANALYSIS BY ENTRY ATR RANGE')
    if not trades:
        print('No trades to analyze')
        return
    _print_range_table(trades, 'atr', step, 'ATR', fmt='%.4f')


def analyze_by_sl_pips(trades, step=10.0):
    """Analyze performance by SL pips ranges."""
    print_section('ANALYSIS BY SL PIPS RANGE')
    if not trades:
        print('No trades to analyze')
        return
    _print_range_table(trades, 'sl_pips', step, 'SL Pips', fmt='%.0f')


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


def analyze_by_pb_bars(trades):
    """Analyze performance by pullback bars count."""
    print_section('ANALYSIS BY PULLBACK BARS')
    pb_trades = [t for t in trades if 'pb_bars' in t]
    if not pb_trades:
        print('No pullback data available (regenerate trade log)')
        return
    _print_range_table(pb_trades, 'pb_bars', 1, 'PB Bars', fmt='%.0f')


def analyze_by_pb_angle(trades, step=10.0):
    """Analyze performance by pullback angle."""
    print_section('ANALYSIS BY PULLBACK ANGLE (degrees)')
    pb_trades = [t for t in trades if 'pb_angle' in t]
    if not pb_trades:
        print('No pullback data available (regenerate trade log)')
        return
    _print_range_table(pb_trades, 'pb_angle', step, 'PB Angle')


def analyze_by_pb_depth(trades, step=10.0):
    """Analyze performance by pullback depth (% of OR height)."""
    print_section('ANALYSIS BY PULLBACK DEPTH (% of OR Height)')
    pb_trades = [t for t in trades if 'pb_depth_pct' in t]
    if not pb_trades:
        print('No pullback data available (regenerate trade log)')
        return
    _print_range_table(pb_trades, 'pb_depth_pct', step, 'PB Depth %')


def analyze_by_rearm_count(trades):
    """Analyze performance by rearm count (0 = first pullback, 1+ = re-armed)."""
    print_section('ANALYSIS BY REARM COUNT')
    rc_trades = [t for t in trades if 'rearm_count' in t]
    if not rc_trades:
        print('No rearm data available (requires v0.8+ trade log)')
        return

    rearm_groups = defaultdict(list)
    for t in rc_trades:
        rearm_groups[t['rearm_count']].append(t)

    print('\n%-12s %8s %6s %8s %8s %10s' % (
        'Rearms', 'Trades', 'Wins', 'WR%', 'PF', 'Avg PnL'))
    print('-' * 55)

    for count in sorted(rearm_groups.keys()):
        m = calculate_metrics(rearm_groups[count])
        print('%-12d %8d %6d %7.1f%% %8s %+10.1f' % (
            count, m['n'], m['wins'], m['wr'],
            format_pf(m['pf']), m['avg_pnl']))


def analyze_by_sl_mode(trades):
    """Analyze performance by SL mode."""
    print_section('ANALYSIS BY SL MODE')
    if not trades:
        print('No trades to analyze')
        return

    mode_groups = defaultdict(list)
    for t in trades:
        mode_groups[t.get('sl_mode', 'unknown')].append(t)

    print('\n%-12s %8s %6s %8s %8s %10s' % (
        'SL Mode', 'Trades', 'Wins', 'WR%', 'PF', 'Avg PnL'))
    print('-' * 55)

    for mode in sorted(mode_groups.keys()):
        m = calculate_metrics(mode_groups[mode])
        print('%-12s %8d %6d %7.1f%% %8s %+10.1f' % (
            mode, m['n'], m['wins'], m['wr'],
            format_pf(m['pf']), m['avg_pnl']))


def print_summary(trades):
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

    # OR Height stats
    heights = [t['or_height'] for t in trades]
    print('\nOR Height Range:  %.5f to %.5f' % (min(heights), max(heights)))
    print('OR Height Avg:    %.5f' % (sum(heights) / len(heights)))

    # OR ER stats
    ers = [t['or_er'] for t in trades]
    print('\nOR ER Range:      %.4f to %.4f' % (min(ers), max(ers)))
    print('OR ER Avg:        %.4f' % (sum(ers) / len(ers)))

    # SL pips stats
    sl_pips = [t['sl_pips'] for t in trades]
    print('\nSL Pips Range:    %.1f to %.1f' % (min(sl_pips), max(sl_pips)))
    print('SL Pips Avg:      %.1f' % (sum(sl_pips) / len(sl_pips)))

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
        description='Analyze CERES strategy trade logs')
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
            print('No CERES logs found in %s' % LOG_DIR)
            return
        print('Analyzing %d log files...' % len(logs))
        for log in logs:
            filepath = os.path.join(LOG_DIR, log)
            log_trades, log_config = parse_ceres_log(filepath)
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
        trades, config = parse_ceres_log(filepath)
    else:
        latest = find_latest_log(LOG_DIR)
        if not latest:
            print('No CERES logs found in %s' % LOG_DIR)
            return
        filepath = os.path.join(LOG_DIR, latest)
        print('Analyzing latest: %s' % filepath)
        trades, config = parse_ceres_log(filepath)

    if not trades:
        print('No trades parsed from log file(s)')
        return

    print('\nTotal trades parsed: %d' % len(trades))

    # Configuration
    print_config(config)

    # Run all analyses
    print_summary(trades)

    # CERES-specific analyses
    pip_value = config.get('pip_value', 0.01)
    analyze_by_or_height(trades, pip_value=pip_value)
    analyze_by_or_er(trades)

    # ATR step: ETF ~0.1-3.0, forex ~0.0005
    atr_step = 0.5 if pip_value >= 0.01 else 0.0001
    analyze_by_or_atr(trades, step=atr_step)
    analyze_by_atr_range(trades, step=atr_step)
    analyze_by_sl_pips(trades)
    analyze_by_sl_mode(trades)
    analyze_by_hour(trades)
    analyze_by_day(trades)
    analyze_by_exit_reason(trades)

    # Pullback analyses (only if data available)
    analyze_by_pb_bars(trades)
    analyze_by_pb_angle(trades)
    analyze_by_pb_depth(trades)
    analyze_by_rearm_count(trades)


if __name__ == '__main__':
    main()
