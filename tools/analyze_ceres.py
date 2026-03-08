"""
CERES Strategy Analyzer (v1.0 - Mobile Window)

Comprehensive analysis tool for CERES v1.0 strategy optimization.
Analyzes trade logs to find optimal parameters for Consolidation Window + Breakout entries.

Usage:
    python analyze_ceres.py                           # Analyze latest CERES log
    python analyze_ceres.py CERES_trades_xxx.txt      # Analyze specific log
    python analyze_ceres.py --all                     # Analyze all CERES logs combined

Key Parameters to Analyze:
- Window Height ranges (consolidation zone size in pips)
- Window ER ranges (Efficiency Ratio - how "sideways" the window is)
- Consolidation Bars (how many bars formed the window)
- Scan Bars (total bars spent in SCANNING state)
- Armed Bars (bars waiting for breakout once armed)
- Breakout Candle height (size of the breakout candle)
- SL pips ranges
- Entry hour / Day of week
- Exit reason distribution

Author: Ivan
Version: 2.0.0 (adapted for CERES v1.0 mobile window)
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


def _detect_version(content):
    """Detect log version: 'v1.0' (mobile window) or 'legacy' (OR-based)."""
    if 'Window High:' in content and 'Consolidation Bars:' in content:
        return 'v1.0'
    if 'OR HH:' in content:
        return 'legacy'
    return 'unknown'


def parse_config_header(content):
    """Parse configuration header from CERES trade log."""
    config = {}

    version = _detect_version(content)
    config['version'] = version

    if version == 'v1.0':
        # Consolidation Window
        match = re.search(
            r'Consolidation: (\d+) bars, delay=(\d+) bars', content)
        if match:
            config['consolidation_bars'] = int(match.group(1))
            config['delay_bars'] = int(match.group(2))

        # Window Height Filter
        match = re.search(
            r'Window Height Filter: ENABLED \| Range: ([\d.]+)-([\d.]+) pips',
            content)
        if match:
            config['window_height_filter'] = True
            config['window_height_min'] = float(match.group(1))
            config['window_height_max'] = float(match.group(2))
        else:
            config['window_height_filter'] = False

        # Window ER Filter
        match = re.search(
            r'Window ER Filter: ENABLED \| Range: ([\d.]+)-([\d.]+)', content)
        if match:
            config['window_er_filter'] = True
            config['window_er_min'] = float(match.group(1))
            config['window_er_max'] = float(match.group(2))
        else:
            config['window_er_filter'] = False

        # Window ATR Filter
        match = re.search(
            r'Window ATR Filter: ENABLED \| Range: ([\d.]+)-([\d.]+)', content)
        if match:
            config['window_atr_filter'] = True
            config['window_atr_min'] = float(match.group(1))
            config['window_atr_max'] = float(match.group(2))
        else:
            config['window_atr_filter'] = False

        # Breakout Offset
        match = re.search(
            r'Breakout Offset: ([\d.]+) \(min candle/window_height\)', content)
        if match:
            config['breakout_offset_mult'] = float(match.group(1))
        else:
            config['breakout_offset_mult'] = 0.0

    else:
        # Legacy OR-based config
        match = re.search(
            r'Opening Range: (\d+) candles, open=(\d+):(\d+) UTC', content)
        if match:
            config['or_candles'] = int(match.group(1))
            config['open_hour'] = int(match.group(2))
            config['open_minute'] = int(match.group(3))

    # ER HTF filter (common)
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

    version = config.get('version', 'unknown')
    print('Log Format: %s' % version)

    if version == 'v1.0':
        print('Consolidation: %d bars, delay=%d' % (
            config.get('consolidation_bars', 0),
            config.get('delay_bars', 0)))
        print('Window Height Filter: %s' % (
            'ENABLED %.1f-%.1f pips' % (
                config.get('window_height_min', 0),
                config.get('window_height_max', 0))
            if config.get('window_height_filter') else 'DISABLED'))
        print('Window ER Filter: %s' % (
            'ENABLED %.2f-%.2f' % (
                config.get('window_er_min', 0),
                config.get('window_er_max', 0))
            if config.get('window_er_filter') else 'DISABLED'))
        print('Window ATR Filter: %s' % (
            'ENABLED %.4f-%.4f' % (
                config.get('window_atr_min', 0),
                config.get('window_atr_max', 0))
            if config.get('window_atr_filter') else 'DISABLED'))
        print('Breakout Offset: %s' % (
            '%.2f' % config['breakout_offset_mult']
            if config.get('breakout_offset_mult', 0) > 0 else 'DISABLED'))
    else:
        if 'or_candles' in config:
            print('OR: %d candles, open=%d:%02d UTC' % (
                config['or_candles'], config.get('open_hour', 0),
                config.get('open_minute', 0)))

    if config.get('sl_mode'):
        print('SL Mode: %s' % config['sl_mode'])
    if config.get('tp_mode'):
        print('TP Mode: %s' % config['tp_mode'])
    if config.get('pip_value'):
        print('Pip Value: %s' % config['pip_value'])
    if config.get('risk_pct'):
        print('Risk: %s%%' % config['risk_pct'])

    print('\nFilters:')
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
    Parse CERES trade log file. Supports v1.0 (mobile window) and legacy (OR) formats.

    v1.0 format:
        ENTRY #N
        Time: YYYY-MM-DD HH:MM:SS
        Entry Price: X.XXXXX
        Stop Loss: X.XXXXX
        Take Profit: X.XXXXX | NONE (EOD)
        SL Pips: XX.X
        ATR (avg): X.XXXXXX
        Window High: X.XXXXX
        Window Low: X.XXXXX
        Window Height: X.XXXXX
        Window ER: X.XXXX
        Window ATR Avg: X.XXXXXX
        SL Mode: xxx
        TP Mode: xxx
        Consolidation Bars: N
        Scan Bars: N
        Armed Bars: N
        Breakout Candle: X.XXXXX
        --------------------------------------------------

    Legacy formats (OR-based) are also supported for backward compatibility.
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    version = _detect_version(content)
    format_version = None

    if version == 'v1.0':
        # v1.0 Mobile Window format
        entries = re.findall(
            r'ENTRY #(\d+)\s*\n'
            r'Time: ([\d-]+ [\d:]+)\s*\n'
            r'Entry Price: ([\d.]+)\s*\n'
            r'Stop Loss: ([\d.]+)\s*\n'
            r'Take Profit: ([\d.]+|NONE[^\n]*)\s*\n'
            r'SL Pips: ([\d.]+)\s*\n'
            r'ATR \(avg\): ([\d.]+)\s*\n'
            r'Window High: ([\d.]+)\s*\n'
            r'Window Low: ([\d.]+)\s*\n'
            r'Window Height: ([\d.]+)\s*\n'
            r'Window ER: ([\d.]+)\s*\n'
            r'Window ATR Avg: ([\d.]+)\s*\n'
            r'SL Mode: (\w+)\s*\n'
            r'TP Mode: (\w+)\s*\n'
            r'Consolidation Bars: (\d+)\s*\n'
            r'Scan Bars: (\d+)\s*\n'
            r'Armed Bars: (\d+)\s*\n'
            r'Breakout Candle: ([\d.]+)',
            content,
            re.IGNORECASE
        )
        format_version = 'v1.0' if entries else None

    if not format_version:
        # ---- Legacy OR-based formats (backward compat) ----

        # v0.8: with Rearm Count
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
            # v0.7: no Rearm Count
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
            format_version = 'v07' if entries else None

        if not entries:
            # Oldest: with OR Angle
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

    if not entries:
        print('WARNING: No entries parsed from %s' % filepath)
        config = parse_config_header(content)
        return [], config

    print('Parsed format: %s (%d entries)' % (format_version, len(entries)))

    # Parse exits
    exits = re.findall(
        r'EXIT #(\d+)\s*\n'
        r'Time: ([\d-]+ [\d:]+|N/A)\s*\n'
        r'Exit Reason: (\w+)\s*\n'
        r'P&L: \$([-\d,.]+)',
        content,
        re.IGNORECASE
    )

    exit_dict = {int(ex[0]): ex for ex in exits}

    trades = []
    for entry in entries:
        trade_id = int(entry[0])
        entry_time = datetime.strptime(entry[1], '%Y-%m-%d %H:%M:%S')

        tp_str = entry[4]
        tp_val = float(tp_str) if tp_str.replace('.', '').isdigit() else None

        if format_version == 'v1.0':
            trade = {
                'id': trade_id,
                'datetime': entry_time,
                'entry_price': float(entry[2]),
                'sl': float(entry[3]),
                'tp': tp_val,
                'sl_pips': float(entry[5]),
                'atr': float(entry[6]),
                'window_high': float(entry[7]),
                'window_low': float(entry[8]),
                'window_height': float(entry[9]),
                'window_er': float(entry[10]),
                'window_atr_avg': float(entry[11]),
                'sl_mode': entry[12],
                'tp_mode': entry[13],
                'consol_bars': int(entry[14]),
                'scan_bars': int(entry[15]),
                'armed_bars': int(entry[16]),
                'breakout_candle': float(entry[17]),
                'hour': entry_time.hour,
                'day_of_week': entry_time.weekday(),
            }
        elif format_version == 'v08':
            trade = {
                'id': trade_id,
                'datetime': entry_time,
                'entry_price': float(entry[2]),
                'sl': float(entry[3]),
                'tp': tp_val,
                'sl_pips': float(entry[5]),
                'atr': float(entry[6]),
                'window_high': float(entry[7]),
                'window_low': float(entry[8]),
                'window_height': float(entry[9]),
                'window_er': float(entry[10]),
                'window_atr_avg': float(entry[11]),
                'sl_mode': entry[12],
                'tp_mode': entry[13],
                'hour': entry_time.hour,
                'day_of_week': entry_time.weekday(),
                'pb_bars': int(entry[14]),
                'pb_angle': float(entry[15]),
                'pb_depth_pct': float(entry[16]),
                'rearm_count': int(entry[17]),
            }
        elif format_version == 'v07':
            trade = {
                'id': trade_id,
                'datetime': entry_time,
                'entry_price': float(entry[2]),
                'sl': float(entry[3]),
                'tp': tp_val,
                'sl_pips': float(entry[5]),
                'atr': float(entry[6]),
                'window_high': float(entry[7]),
                'window_low': float(entry[8]),
                'window_height': float(entry[9]),
                'window_er': float(entry[10]),
                'window_atr_avg': float(entry[11]),
                'sl_mode': entry[12],
                'tp_mode': entry[13],
                'hour': entry_time.hour,
                'day_of_week': entry_time.weekday(),
                'pb_bars': int(entry[14]),
                'pb_angle': float(entry[15]),
                'pb_depth_pct': float(entry[16]),
            }
        else:
            # Legacy: OR Angle at group 10
            trade = {
                'id': trade_id,
                'datetime': entry_time,
                'entry_price': float(entry[2]),
                'sl': float(entry[3]),
                'tp': tp_val,
                'sl_pips': float(entry[5]),
                'atr': float(entry[6]),
                'window_high': float(entry[7]),
                'window_low': float(entry[8]),
                'window_height': float(entry[9]),
                'window_er': float(entry[11]),
                'window_atr_avg': float(entry[12]),
                'sl_mode': entry[13],
                'tp_mode': entry[14],
                'hour': entry_time.hour,
                'day_of_week': entry_time.weekday(),
            }

        # Match exit
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

    # Filter to closed trades only (exclude Margin/Canceled/Rejected)
    skip_reasons = {'Margin', 'Canceled', 'Rejected'}
    closed_trades = [t for t in trades
                     if 'pnl' in t and t.get('exit_reason') not in skip_reasons]

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


def _auto_step(trades, key, target_bins=8):
    """Compute a nice step size for ~target_bins bins from actual data range."""
    import math
    values = [t[key] for t in trades if key in t]
    if not values:
        return 1.0
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
    """Generic range analysis for any numeric key. Reusable."""
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

    current = (min_v // step) * step  # Align to step
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


def analyze_by_window_height(trades, pip_value=0.01):
    """Analyze performance by Window Height (consolidation zone size)."""
    print_section('ANALYSIS BY WINDOW HEIGHT (pips)')
    if not trades:
        print('No trades to analyze')
        return
    for t in trades:
        t['_window_height_pips'] = t['window_height'] / pip_value if pip_value > 0 else 0
    step = 50.0 if pip_value <= 0.01 else 5.0
    _print_range_table(trades, '_window_height_pips', step, 'Window Height (pips)')


def analyze_by_window_er(trades, step=0.1):
    """Analyze performance by Window Efficiency Ratio."""
    print_section('ANALYSIS BY WINDOW EFFICIENCY RATIO')
    if not trades:
        print('No trades to analyze')
        return
    _print_range_table(trades, 'window_er', step, 'Window ER', fmt='%.2f')


def analyze_by_window_atr(trades):
    """Analyze performance by ATR during consolidation window."""
    print_section('ANALYSIS BY WINDOW ATR AVG')
    if not trades:
        print('No trades to analyze')
        return
    step = _auto_step(trades, 'window_atr_avg')
    _print_range_table(trades, 'window_atr_avg', step, 'Window ATR', fmt='%.4f')


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
    """Analyze performance by number of consolidation bars that formed the window."""
    print_section('ANALYSIS BY CONSOLIDATION BARS')
    consol_trades = [t for t in trades if 'consol_bars' in t]
    if not consol_trades:
        print('No consolidation data available (requires v1.0 log)')
        return
    _print_range_table(consol_trades, 'consol_bars', 1, 'Consol Bars', fmt='%.0f')


def analyze_by_scan_bars(trades, step=5):
    """Analyze performance by total bars spent in SCANNING state."""
    print_section('ANALYSIS BY SCAN BARS (time to form window)')
    scan_trades = [t for t in trades if 'scan_bars' in t]
    if not scan_trades:
        print('No scan data available (requires v1.0 log)')
        return
    _print_range_table(scan_trades, 'scan_bars', step, 'Scan Bars', fmt='%.0f')


def analyze_by_armed_bars(trades, step=1):
    """Analyze performance by bars spent in ARMED state (waiting for breakout)."""
    print_section('ANALYSIS BY ARMED BARS (wait for breakout)')
    armed_trades = [t for t in trades if 'armed_bars' in t]
    if not armed_trades:
        print('No armed data available (requires v1.0 log)')
        return
    _print_range_table(armed_trades, 'armed_bars', step, 'Armed Bars', fmt='%.0f')


def analyze_by_breakout_candle(trades, pip_value=0.01):
    """Analyze performance by breakout candle height."""
    print_section('ANALYSIS BY BREAKOUT CANDLE HEIGHT (pips)')
    bk_trades = [t for t in trades if 'breakout_candle' in t]
    if not bk_trades:
        print('No breakout candle data available (requires v1.0 log)')
        return
    for t in bk_trades:
        t['_bk_candle_pips'] = t['breakout_candle'] / pip_value if pip_value > 0 else 0
    step = 20.0 if pip_value <= 0.01 else 2.0
    _print_range_table(bk_trades, '_bk_candle_pips', step, 'BK Candle (pips)')


def analyze_by_breakout_ratio(trades):
    """Analyze by breakout candle height / window height (offset_mult equivalent)."""
    print_section('ANALYSIS BY BREAKOUT RATIO (candle/window_height)')
    bk_trades = [t for t in trades if 'breakout_candle' in t and t.get('window_height', 0) > 0]
    if not bk_trades:
        print('No breakout data available (requires v1.0 log)')
        return
    for t in bk_trades:
        t['_bk_ratio'] = t['breakout_candle'] / t['window_height']
    _print_range_table(bk_trades, '_bk_ratio', 0.25, 'BK Ratio', fmt='%.2f')


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

    # Window Height stats
    heights = [t['window_height'] for t in trades if 'window_height' in t]
    if heights:
        print('\nWindow Height Range: %.5f to %.5f' % (min(heights), max(heights)))
        print('Window Height Avg:   %.5f' % (sum(heights) / len(heights)))

    # Window ER stats
    ers = [t['window_er'] for t in trades if 'window_er' in t]
    if ers:
        print('\nWindow ER Range:     %.4f to %.4f' % (min(ers), max(ers)))
        print('Window ER Avg:       %.4f' % (sum(ers) / len(ers)))

    # SL pips stats
    sl_pips = [t['sl_pips'] for t in trades]
    print('\nSL Pips Range:    %.1f to %.1f' % (min(sl_pips), max(sl_pips)))
    print('SL Pips Avg:      %.1f' % (sum(sl_pips) / len(sl_pips)))

    # Bars held stats
    bars = [t.get('bars_held', 0) for t in trades if t.get('bars_held')]
    if bars:
        print('\nBars Held Range:  %d to %d' % (min(bars), max(bars)))
        print('Bars Held Avg:    %.1f' % (sum(bars) / len(bars)))

    # v1.0 specific stats
    consol = [t['consol_bars'] for t in trades if 'consol_bars' in t]
    if consol:
        print('\nConsolidation Bars: %d to %d (avg %.1f)' % (
            min(consol), max(consol), sum(consol) / len(consol)))
    scan = [t['scan_bars'] for t in trades if 'scan_bars' in t]
    if scan:
        print('Scan Bars:          %d to %d (avg %.1f)' % (
            min(scan), max(scan), sum(scan) / len(scan)))
    armed = [t['armed_bars'] for t in trades if 'armed_bars' in t]
    if armed:
        print('Armed Bars:         %d to %d (avg %.1f)' % (
            min(armed), max(armed), sum(armed) / len(armed)))
    bk = [t['breakout_candle'] for t in trades if 'breakout_candle' in t]
    if bk:
        pip_value = config.get('pip_value', 0.01) if config else 0.01
        bk_pips = [b / pip_value for b in bk]
        print('Breakout Candle:    %.1f to %.1f pips (avg %.1f)' % (
            min(bk_pips), max(bk_pips), sum(bk_pips) / len(bk_pips)))


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Analyze CERES strategy trade logs (v1.0 mobile window)')
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

    # Overall summary
    print_summary(trades, config)

    # Window-specific analyses (v1.0)
    pip_value = config.get('pip_value', 0.01)
    analyze_by_window_height(trades, pip_value=pip_value)
    analyze_by_window_er(trades)

    analyze_by_window_atr(trades)
    analyze_by_atr_range(trades)
    analyze_by_sl_pips(trades)
    analyze_by_sl_mode(trades)

    # Temporal analyses
    analyze_by_hour(trades)
    analyze_by_day(trades)
    analyze_by_exit_reason(trades)

    # v1.0: State machine analyses
    analyze_by_consol_bars(trades)
    analyze_by_scan_bars(trades)
    analyze_by_armed_bars(trades)
    analyze_by_breakout_candle(trades, pip_value=pip_value)
    analyze_by_breakout_ratio(trades)


if __name__ == '__main__':
    main()
