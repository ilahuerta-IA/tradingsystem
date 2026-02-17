"""
HELIX Strategy Analyzer

Comprehensive analysis tool for HELIX strategy optimization.
Analyzes trade logs to find optimal parameters for Spectral Entropy-based entries.

Usage:
    python analyze_helix.py                           # Analyze latest HELIX log
    python analyze_helix.py HELIX_trades_xxx.txt      # Analyze specific log
    python analyze_helix.py --all                     # Analyze all HELIX logs combined

Key Parameters to Analyze:
- SE (Spectral Entropy) range [se_min, se_max]
- Entry hour (UTC)
- Day of week
- SL pips ranges
- ATR ranges

Author: Ivan
Version: 1.0.0
"""
import os
import sys
import re
import math
import numpy as np
import pandas as pd
from datetime import datetime
from collections import defaultdict
from typing import List, Dict, Optional, Tuple
import argparse


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
# CONFIGURATION
# =============================================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, '..', 'logs'))


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


def format_se(se: float) -> str:
    """Format SE value."""
    return f'{se:.3f}'


# =============================================================================
# LOG PARSING
# =============================================================================

def find_latest_log(log_dir: str, prefix: str = 'HELIX_trades_') -> Optional[str]:
    """Find the most recent log file with given prefix, by modification time."""
    if not os.path.exists(log_dir):
        return None
    logs = [f for f in os.listdir(log_dir) if f.startswith(prefix) and f.endswith('.txt')]
    if not logs:
        return None
    logs.sort(key=lambda f: os.path.getmtime(os.path.join(log_dir, f)), reverse=True)
    return logs[0]


def find_all_logs(log_dir: str, prefix: str = 'HELIX_trades_') -> List[str]:
    """Find all log files with given prefix."""
    if not os.path.exists(log_dir):
        return []
    return sorted([f for f in os.listdir(log_dir) if f.startswith(prefix) and f.endswith('.txt')])


def parse_helix_log(filepath: str) -> List[Dict]:
    """
    Parse HELIX trade log file.
    
    Expected format:
        ENTRY #N
        Time: YYYY-MM-DD HH:MM:SS
        Entry Price: X.XXXXX
        Stop Loss: X.XXXXX
        Take Profit: X.XXXXX
        SL Pips: XX.X
        ATR (avg): X.XXXXXX
        SE: X.XXX
        SE StdDev: X.XXXX
        Breakout Waited: N bars
        Pullback Bars: N
        
        EXIT #N
        Time: YYYY-MM-DD HH:MM:SS
        Exit Reason: REASON
        P&L: $X,XXX.XX
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Parse entries - pattern for HELIX log format (with optional new fields)
    entries = re.findall(
        r'ENTRY #(\d+)\s*\n'
        r'Time: ([\d-]+ [\d:]+)\s*\n'
        r'Entry Price: ([\d.]+)\s*\n'
        r'Stop Loss: ([\d.]+)\s*\n'
        r'Take Profit: ([\d.]+)\s*\n'
        r'SL Pips: ([\d.]+)\s*\n'
        r'ATR \(avg\): ([\d.]+)\s*\n'
        r'SE: ([\d.]+)\s*\n'
        r'(?:SE StdDev: ([\d.]+)\s*\n)?'       # Optional SE StdDev
        r'(?:Breakout Waited: (\d+) bars\s*\n)?' # Optional Breakout Waited
        r'(?:Pullback Bars: (\d+))?',           # Optional Pullback Bars
        content,
        re.IGNORECASE
    )
    
    # Parse exits
    exits = re.findall(
        r'EXIT #(\d+)\s*\n'
        r'Time: ([\d-]+ [\d:]+)\s*\n'
        r'Exit Reason: (\w+)\s*\n'
        r'P&L: \$([-\d,.]+)',
        content,
        re.IGNORECASE
    )
    
    # Build trades dictionary keyed by ID
    exit_dict = {int(ex[0]): ex for ex in exits}
    
    trades = []
    for entry in entries:
        trade_id = int(entry[0])
        trade = {
            'id': trade_id,
            'entry_time': datetime.strptime(entry[1], '%Y-%m-%d %H:%M:%S'),
            'entry_price': float(entry[2]),
            'sl': float(entry[3]),
            'tp': float(entry[4]),
            'sl_pips': float(entry[5]),
            'atr': float(entry[6]),
            'se': float(entry[7]),
            'se_stddev': float(entry[8]) if entry[8] else 0.0,  # SE StdDev (optional)
            'breakout_waited_bars': int(entry[9]) if entry[9] else 0,  # Breakout waited (optional)
            'pullback_bars': int(entry[10]) if entry[10] else 0,  # Pullback bars (optional)
        }
        
        # Match with exit if exists
        if trade_id in exit_dict:
            ex = exit_dict[trade_id]
            trade['exit_time'] = datetime.strptime(ex[1], '%Y-%m-%d %H:%M:%S')
            trade['exit_reason'] = ex[2]
            trade['pnl'] = float(ex[3].replace(',', ''))
            trade['duration_min'] = (trade['exit_time'] - trade['entry_time']).total_seconds() / 60
            trade['win'] = trade['pnl'] > 0
        
        trades.append(trade)
    
    return trades


# =============================================================================
# STATISTICS FUNCTIONS
# =============================================================================

def calculate_stats(trades: List[Dict]) -> Optional[Dict]:
    """Calculate statistics for a list of trades."""
    closed = [t for t in trades if 'pnl' in t]
    if not closed:
        return None
    
    winners = [t for t in closed if t['pnl'] > 0]
    losers = [t for t in closed if t['pnl'] < 0]
    
    gross_profit = sum(t['pnl'] for t in winners)
    gross_loss = sum(abs(t['pnl']) for t in losers)
    
    pnl_list = [t['pnl'] for t in closed]
    
    return {
        'total': len(closed),
        'wins': len(winners),
        'losses': len(losers),
        'win_rate': len(winners) / len(closed) * 100 if closed else 0,
        'gross_profit': gross_profit,
        'gross_loss': gross_loss,
        'net_pnl': gross_profit - gross_loss,
        'profit_factor': gross_profit / gross_loss if gross_loss > 0 else float('inf'),
        'avg_win': gross_profit / len(winners) if winners else 0,
        'avg_loss': gross_loss / len(losers) if losers else 0,
        'max_win': max(pnl_list) if pnl_list else 0,
        'max_loss': min(pnl_list) if pnl_list else 0,
    }


def calculate_expectancy(stats: Dict) -> float:
    """Calculate mathematical expectancy per trade."""
    if not stats or stats['total'] == 0:
        return 0
    wr = stats['win_rate'] / 100
    avg_win = stats['avg_win'] if stats['wins'] > 0 else 0
    avg_loss = stats['avg_loss'] if stats['losses'] > 0 else 0
    return (wr * avg_win) - ((1 - wr) * avg_loss)


# =============================================================================
# TRADE LOG ANALYSIS
# =============================================================================

def analyze_overall(trades: List[Dict]):
    """Print overall trade statistics."""
    print_section('OVERALL STATISTICS')
    stats = calculate_stats(trades)
    
    if not stats:
        print('No closed trades found.')
        return
    
    expectancy = calculate_expectancy(stats)
    
    # SE range used
    se_values = [t['se'] for t in trades if 'se' in t]
    se_min_used = min(se_values) if se_values else 0
    se_max_used = max(se_values) if se_values else 0
    
    print(f"Total Trades:    {stats['total']:>6}")
    print(f"Winners:         {stats['wins']:>6}  ({stats['win_rate']:.1f}%)")
    print(f"Losers:          {stats['losses']:>6}")
    print(f"Profit Factor:   {format_pf(stats['profit_factor']):>6}")
    print(f"")
    print(f"Gross Profit:    ${stats['gross_profit']:>12,.2f}")
    print(f"Gross Loss:      ${stats['gross_loss']:>12,.2f}")
    print(f"Net P&L:         ${stats['net_pnl']:>12,.2f}")
    print(f"")
    print(f"Avg Win:         ${stats['avg_win']:>12,.2f}")
    print(f"Avg Loss:        ${stats['avg_loss']:>12,.2f}")
    print(f"Expectancy:      ${expectancy:>12,.2f} per trade")
    print(f"")
    print(f"Max Win:         ${stats['max_win']:>12,.2f}")
    print(f"Max Loss:        ${stats['max_loss']:>12,.2f}")
    print(f"")
    print(f"SE Range Used:   {se_min_used:.3f} - {se_max_used:.3f}")


def analyze_by_se(trades: List[Dict]):
    """Analyze trades by SE (Spectral Entropy) ranges - KEY for HELIX."""
    print_section('ANALYSIS BY SE (SPECTRAL ENTROPY) - KEY METRIC')
    
    # SE ranges for forex typically 0.84-0.96
    ranges = [
        (0.80, 0.82), (0.82, 0.84), (0.84, 0.86), (0.86, 0.88),
        (0.88, 0.90), (0.90, 0.92), (0.92, 0.94), (0.94, 0.96), (0.96, 1.00)
    ]
    
    print(f'{"SE Range":>12} | {"Trades":>6} | {"Win%":>5} | {"PF":>5} | {"Net P&L":>12} | {"Expectancy":>10}')
    print('-' * 70)
    
    for low, high in ranges:
        filtered = [t for t in trades if 'pnl' in t and 'se' in t and low <= t['se'] < high]
        if filtered:
            stats = calculate_stats(filtered)
            if stats:
                exp = calculate_expectancy(stats)
                label = f'{low:.2f}-{high:.2f}'
                pf_color = '✅' if stats['profit_factor'] >= 1.5 else ('⚠️' if stats['profit_factor'] >= 1.0 else '❌')
                print(f'{label:>12} | {stats["total"]:>6} | {stats["win_rate"]:>4.0f}% | '
                      f'{format_pf(stats["profit_factor"]):>5} | ${stats["net_pnl"]:>10,.0f} | ${exp:>9,.0f} {pf_color}')
    
    # Summary recommendation
    print('\n📊 SE RANGE RECOMMENDATION:')
    best_pf = 0
    best_range = None
    for low, high in ranges:
        filtered = [t for t in trades if 'pnl' in t and 'se' in t and low <= t['se'] < high]
        if len(filtered) >= 5:  # Minimum trades for significance
            stats = calculate_stats(filtered)
            if stats and stats['profit_factor'] > best_pf:
                best_pf = stats['profit_factor']
                best_range = (low, high)
    
    if best_range:
        print(f'   Best single range: {best_range[0]:.2f}-{best_range[1]:.2f} (PF: {best_pf:.2f})')


def analyze_by_se_stddev(trades: List[Dict]):
    """Analyze trades by SE StdDev (stability) - KEY NEW METRIC."""
    print_section('ANALYSIS BY SE STDDEV (STABILITY) - KEY METRIC')
    
    # Check if we have SE StdDev data
    has_stddev = any(t.get('se_stddev', 0) > 0 for t in trades if 'pnl' in t)
    if not has_stddev:
        print('⚠️  No SE StdDev data found in log. Run backtest with use_se_stability=True.')
        return
    
    # SE StdDev ranges
    ranges = [
        (0.000, 0.005), (0.005, 0.010), (0.010, 0.015), (0.015, 0.020), 
        (0.020, 0.030), (0.030, 0.040), (0.040, 0.050), (0.050, 0.100), (0.100, 1.000)
    ]
    
    print(f'{"StdDev Range":>14} | {"Trades":>6} | {"Win%":>5} | {"PF":>5} | {"Net P&L":>12} | {"Expectancy":>10}')
    print('-' * 75)
    
    for low, high in ranges:
        filtered = [t for t in trades if 'pnl' in t and 'se_stddev' in t and low <= t['se_stddev'] < high]
        if filtered:
            stats = calculate_stats(filtered)
            if stats:
                exp = calculate_expectancy(stats)
                label = f'{low:.3f}-{high:.3f}'
                pf_color = '✅' if stats['profit_factor'] >= 1.5 else ('⚠️' if stats['profit_factor'] >= 1.0 else '❌')
                print(f'{label:>14} | {stats["total"]:>6} | {stats["win_rate"]:>4.0f}% | '
                      f'{format_pf(stats["profit_factor"]):>5} | ${stats["net_pnl"]:>10,.0f} | ${exp:>9,.0f} {pf_color}')
    
    # Find optimal range (min, max)
    print('\n📊 SE STDDEV OPTIMAL RANGE:')
    best_pf = 0
    best_range = None
    for min_val in [0.000, 0.005, 0.010]:
        for max_val in [0.020, 0.025, 0.030, 0.040, 0.050]:
            if max_val <= min_val:
                continue
            filtered = [t for t in trades if 'pnl' in t and 'se_stddev' in t and min_val <= t['se_stddev'] < max_val]
            if len(filtered) >= 15:
                stats = calculate_stats(filtered)
                if stats and stats['profit_factor'] > best_pf:
                    best_pf = stats['profit_factor']
                    best_range = (min_val, max_val, stats['total'])
    
    if best_range:
        print(f'   Best StdDev range: {best_range[0]:.3f} - {best_range[1]:.3f} (PF: {best_pf:.2f}, {best_range[2]} trades)')
        print(f'   Suggested: se_stability_min={best_range[0]:.3f}, se_stability_max={best_range[1]:.3f}')


def analyze_se_combinations(trades: List[Dict]):
    """Find optimal SE min/max combination."""
    print_section('SE RANGE OPTIMIZATION (se_min, se_max) [LEGACY]')
    
    # Test different combinations
    se_mins = [0.80, 0.82, 0.84, 0.85, 0.86]
    se_maxs = [0.88, 0.89, 0.90, 0.91, 0.92, 0.94]
    
    results = []
    
    for se_min in se_mins:
        for se_max in se_maxs:
            if se_max <= se_min:
                continue
            filtered = [t for t in trades if 'pnl' in t and 'se' in t 
                       and se_min <= t['se'] <= se_max]
            if len(filtered) >= 10:  # Minimum trades
                stats = calculate_stats(filtered)
                if stats:
                    results.append({
                        'se_min': se_min,
                        'se_max': se_max,
                        'trades': stats['total'],
                        'win_rate': stats['win_rate'],
                        'pf': stats['profit_factor'],
                        'net_pnl': stats['net_pnl'],
                    })
    
    # Sort by PF then by trades
    results.sort(key=lambda x: (-x['pf'], -x['trades']))
    
    print(f'{"SE Min":>8} | {"SE Max":>8} | {"Trades":>6} | {"Win%":>5} | {"PF":>5} | {"Net P&L":>12}')
    print('-' * 60)
    
    for r in results[:15]:  # Top 15
        pf_color = '✅' if r['pf'] >= 1.5 else ('⚠️' if r['pf'] >= 1.0 else '❌')
        print(f'{r["se_min"]:>8.2f} | {r["se_max"]:>8.2f} | {r["trades"]:>6} | '
              f'{r["win_rate"]:>4.0f}% | {format_pf(r["pf"]):>5} | ${r["net_pnl"]:>10,.0f} {pf_color}')


def analyze_by_hour(trades: List[Dict]):
    """Analyze trades by entry hour."""
    print_section('ANALYSIS BY HOUR (UTC)')
    
    groups = defaultdict(list)
    for t in trades:
        if 'pnl' in t:
            hour = t['entry_time'].hour
            groups[hour].append(t)
    
    print(f'{"Hour":>6} | {"Trades":>6} | {"Win%":>5} | {"PF":>5} | {"Net P&L":>12} | {"Avg SE":>8}')
    print('-' * 60)
    
    for hour in range(24):
        if hour in groups:
            stats = calculate_stats(groups[hour])
            if stats:
                avg_se = np.mean([t['se'] for t in groups[hour] if 'se' in t])
                pf_color = '✅' if stats['profit_factor'] >= 1.5 else ''
                print(f'{hour:>6} | {stats["total"]:>6} | {stats["win_rate"]:>4.0f}% | '
                      f'{format_pf(stats["profit_factor"]):>5} | ${stats["net_pnl"]:>10,.0f} | {avg_se:>8.3f} {pf_color}')


def analyze_by_day(trades: List[Dict]):
    """Analyze trades by day of week."""
    print_section('ANALYSIS BY DAY OF WEEK')
    
    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    groups = defaultdict(list)
    
    for t in trades:
        if 'pnl' in t:
            dow = t['entry_time'].weekday()
            groups[dow].append(t)
    
    print(f'{"Day":>12} | {"Trades":>6} | {"Win%":>5} | {"PF":>5} | {"Net P&L":>12} | {"Avg SE":>8}')
    print('-' * 60)
    
    for dow in range(7):
        stats = calculate_stats(groups[dow])
        if stats:
            avg_se = np.mean([t['se'] for t in groups[dow] if 'se' in t])
            pf_color = '✅' if stats['profit_factor'] >= 1.5 else ''
            print(f'{day_names[dow]:>12} | {stats["total"]:>6} | {stats["win_rate"]:>4.0f}% | '
                  f'{format_pf(stats["profit_factor"]):>5} | ${stats["net_pnl"]:>10,.0f} | {avg_se:>8.3f} {pf_color}')


def analyze_by_sl_pips(trades: List[Dict]):
    """Analyze trades by SL pips ranges (auto-adaptive)."""
    print_section('ANALYSIS BY SL PIPS')
    
    sl_values = [t['sl_pips'] for t in trades if 'sl_pips' in t and 'pnl' in t]
    if not sl_values:
        print('No SL pips data available.')
        return
    ranges = _auto_ranges(sl_values)
    
    print(f'{"SL Pips":>12} | {"Trades":>6} | {"Win%":>5} | {"PF":>5} | {"Net P&L":>12}')
    print('-' * 55)
    
    for low, high in ranges:
        filtered = [t for t in trades if 'pnl' in t and 'sl_pips' in t and low <= t['sl_pips'] < high]
        if filtered:
            stats = calculate_stats(filtered)
            label = f'{low:>3.0f}-{high:<3.0f}'
            pf_flag = '*' if stats['profit_factor'] >= 1.5 else ''
            print(f'{label:>12} | {stats["total"]:>6} | {stats["win_rate"]:>4.0f}% | '
                  f'{format_pf(stats["profit_factor"]):>5} | ${stats["net_pnl"]:>10,.0f} {pf_flag}')


def analyze_by_atr(trades: List[Dict]):
    """Analyze trades by ATR ranges."""
    print_section('ANALYSIS BY ATR')
    
    atrs = [t['atr'] for t in trades if 'atr' in t and 'pnl' in t]
    if not atrs:
        print('No ATR data available.')
        return
    
    min_atr = min(atrs)
    max_atr = max(atrs)
    step = (max_atr - min_atr) / 6
    
    ranges = []
    for i in range(6):
        low = min_atr + i * step
        high = min_atr + (i + 1) * step
        ranges.append((low, high))
    
    print(f'{"ATR Range":>18} | {"Trades":>6} | {"Win%":>5} | {"PF":>5} | {"Net P&L":>12}')
    print('-' * 60)
    
    for low, high in ranges:
        filtered = [t for t in trades if 'pnl' in t and 'atr' in t and low <= t['atr'] < high]
        if filtered:
            stats = calculate_stats(filtered)
            label = f'{low:.5f}-{high:.5f}'
            pf_color = '✅' if stats['profit_factor'] >= 1.5 else ''
            print(f'{label:>18} | {stats["total"]:>6} | {stats["win_rate"]:>4.0f}% | '
                  f'{format_pf(stats["profit_factor"]):>5} | ${stats["net_pnl"]:>10,.0f} {pf_color}')


def analyze_by_breakout_waited(trades: List[Dict]):
    """Analyze trades by how many bars waited for breakout."""
    print_section('ANALYSIS BY BREAKOUT WAITED BARS')
    
    # Check if we have data
    has_data = any(t.get('breakout_waited_bars', 0) >= 0 for t in trades if 'pnl' in t)
    if not has_data:
        print('No Breakout Waited data. Run backtest with updated strategy.')
        return
    
    # Analyze by individual bar count
    groups = defaultdict(list)
    for t in trades:
        if 'pnl' in t:
            bars = t.get('breakout_waited_bars', 0)
            groups[bars].append(t)
    
    print(f'{"Bars Waited":>12} | {"Trades":>6} | {"Win%":>5} | {"PF":>5} | {"Net P&L":>12}')
    print('-' * 55)
    
    for bars in sorted(groups.keys()):
        stats = calculate_stats(groups[bars])
        if stats and stats['total'] >= 3:
            pf_color = '✅' if stats['profit_factor'] >= 1.5 else ('⚠️' if stats['profit_factor'] >= 1.0 else '❌')
            print(f'{bars:>12} | {stats["total"]:>6} | {stats["win_rate"]:>4.0f}% | '
                  f'{format_pf(stats["profit_factor"]):>5} | ${stats["net_pnl"]:>10,.0f} {pf_color}')
    
    # Find optimal range
    print('\n📊 OPTIMAL BREAKOUT WINDOW:')
    best_pf = 0
    best_range = None
    for max_bars in range(1, 11):
        filtered = [t for t in trades if 'pnl' in t and t.get('breakout_waited_bars', 0) <= max_bars]
        if len(filtered) >= 15:
            stats = calculate_stats(filtered)
            if stats and stats['profit_factor'] > best_pf:
                best_pf = stats['profit_factor']
                best_range = (max_bars, stats['total'])
    
    if best_range:
        print(f'   Best max window: {best_range[0]} bars (PF: {best_pf:.2f}, {best_range[1]} trades) -> breakout_window_candles={best_range[0]}')


def analyze_by_pullback_bars(trades: List[Dict]):
    """Analyze trades by pullback duration (bars since HH)."""
    print_section('ANALYSIS BY PULLBACK DURATION (BARS)')
    
    # Check if we have data
    has_data = any(t.get('pullback_bars', 0) > 0 for t in trades if 'pnl' in t)
    if not has_data:
        print('No Pullback Bars data. Run backtest with updated strategy.')
        return
    
    # Analyze by individual bar count
    groups = defaultdict(list)
    for t in trades:
        if 'pnl' in t:
            bars = t.get('pullback_bars', 0)
            groups[bars].append(t)
    
    print(f'{"Pullback Bars":>14} | {"Trades":>6} | {"Win%":>5} | {"PF":>5} | {"Net P&L":>12}')
    print('-' * 58)
    
    for bars in sorted(groups.keys()):
        stats = calculate_stats(groups[bars])
        if stats and stats['total'] >= 3:
            pf_color = '✅' if stats['profit_factor'] >= 1.5 else ('⚠️' if stats['profit_factor'] >= 1.0 else '❌')
            print(f'{bars:>14} | {stats["total"]:>6} | {stats["win_rate"]:>4.0f}% | '
                  f'{format_pf(stats["profit_factor"]):>5} | ${stats["net_pnl"]:>10,.0f} {pf_color}')
    
    # Find optimal range (min, max)
    print('\n📊 OPTIMAL PULLBACK RANGE:')
    best_pf = 0
    best_range = None
    for min_bars in range(1, 4):
        for max_bars in range(min_bars + 1, 8):
            filtered = [t for t in trades if 'pnl' in t 
                       and min_bars <= t.get('pullback_bars', 0) <= max_bars]
            if len(filtered) >= 15:
                stats = calculate_stats(filtered)
                if stats and stats['profit_factor'] > best_pf:
                    best_pf = stats['profit_factor']
                    best_range = (min_bars, max_bars, stats['total'])
    
    if best_range:
        print(f'   Best range: {best_range[0]}-{best_range[1]} bars (PF: {best_pf:.2f}, {best_range[2]} trades)')
        print(f'   Suggested: pullback_min_bars={best_range[0]}, pullback_max_bars={best_range[1]}')


def analyze_by_year(trades: List[Dict]):
    """Analyze trades by year."""
    print_section('YEARLY STATISTICS')
    
    groups = defaultdict(list)
    for t in trades:
        if 'pnl' in t:
            year = t['entry_time'].year
            groups[year].append(t)
    
    print(f'{"Year":>6} | {"Trades":>6} | {"Win%":>5} | {"PF":>5} | {"Net P&L":>12}')
    print('-' * 50)
    
    for year in sorted(groups.keys()):
        stats = calculate_stats(groups[year])
        if stats:
            pf_color = '✅' if stats['profit_factor'] >= 1.5 else ''
            print(f'{year:>6} | {stats["total"]:>6} | {stats["win_rate"]:>4.0f}% | '
                  f'{format_pf(stats["profit_factor"]):>5} | ${stats["net_pnl"]:>10,.0f} {pf_color}')


def analyze_by_exit_reason(trades: List[Dict]):
    """Analyze trades by exit reason."""
    print_section('ANALYSIS BY EXIT REASON')
    
    groups = defaultdict(list)
    for t in trades:
        if 'exit_reason' in t:
            groups[t['exit_reason']].append(t)
    
    print(f'{"Reason":>15} | {"Trades":>6} | {"Win%":>5} | {"Avg P&L":>12}')
    print('-' * 45)
    
    for reason in sorted(groups.keys()):
        trades_list = groups[reason]
        total = len(trades_list)
        wins = sum(1 for t in trades_list if t.get('pnl', 0) > 0)
        avg_pnl = sum(t.get('pnl', 0) for t in trades_list) / total
        win_rate = wins / total * 100 if total > 0 else 0
        print(f'{reason:>15} | {total:>6} | {win_rate:>4.0f}% | ${avg_pnl:>10,.2f}')


def analyze_trade_duration(trades: List[Dict]):
    """Analyze trade duration patterns."""
    print_section('TRADE DURATION ANALYSIS')
    
    closed = [t for t in trades if 'duration_min' in t]
    if not closed:
        print('No duration data available.')
        return
    
    durations = [t['duration_min'] for t in closed]
    
    print(f'Average Duration: {np.mean(durations):.0f} minutes ({np.mean(durations)/60:.1f} hours)')
    print(f'Median Duration:  {np.median(durations):.0f} minutes')
    print(f'Min Duration:     {np.min(durations):.0f} minutes')
    print(f'Max Duration:     {np.max(durations):.0f} minutes')
    
    # Duration ranges
    ranges = [(0, 60), (60, 180), (180, 360), (360, 720), (720, 1440), (1440, float('inf'))]
    labels = ['<1h', '1-3h', '3-6h', '6-12h', '12-24h', '>24h']
    
    print(f'\n{"Duration":>10} | {"Trades":>6} | {"Win%":>5} | {"Net P&L":>12}')
    print('-' * 45)
    
    for (low, high), label in zip(ranges, labels):
        filtered = [t for t in closed if low <= t['duration_min'] < high]
        if filtered:
            stats = calculate_stats(filtered)
            if stats:
                print(f'{label:>10} | {stats["total"]:>6} | {stats["win_rate"]:>4.0f}% | '
                      f'${stats["net_pnl"]:>10,.0f}')


def generate_filter_suggestions(trades: List[Dict]):
    """Generate suggested filters based on analysis."""
    print_section('🎯 FILTER SUGGESTIONS FOR HELIX')
    
    closed = [t for t in trades if 'pnl' in t]
    if not closed:
        print('No data for suggestions.')
        return
    
    suggestions = []
    
    # 0. SE STDDEV suggestion (NEW - KEY METRIC)
    # Find optimal range (min, max) for se_stability
    best_stddev_pf = 0
    best_stddev_range = None
    for min_stddev in [0.000, 0.005, 0.010]:
        for max_stddev in [0.02, 0.025, 0.03, 0.04, 0.05]:
            if max_stddev <= min_stddev:
                continue
            filtered = [t for t in closed if 'se_stddev' in t and min_stddev <= t['se_stddev'] < max_stddev]
            if len(filtered) >= 15:
                stats = calculate_stats(filtered)
                if stats and stats['profit_factor'] > best_stddev_pf:
                    best_stddev_pf = stats['profit_factor']
                    best_stddev_range = (min_stddev, max_stddev, stats['total'])
    
    if best_stddev_range:
        suggestions.append(f"🔑 SE STABILITY: min={best_stddev_range[0]:.3f}, max={best_stddev_range[1]:.3f} "
                          f"(PF: {best_stddev_pf:.2f}, {best_stddev_range[2]} trades) ⬅️ KEY")
    
    # 1. SE Range suggestion [LEGACY - may be less effective]
    best_se_pf = 0
    best_se_range = None
    for se_min in [0.82, 0.84, 0.85, 0.86]:
        for se_max in [0.88, 0.89, 0.90, 0.91, 0.92]:
            if se_max <= se_min:
                continue
            filtered = [t for t in closed if 'se' in t and se_min <= t['se'] <= se_max]
            if len(filtered) >= 15:
                stats = calculate_stats(filtered)
                if stats and stats['profit_factor'] > best_se_pf:
                    best_se_pf = stats['profit_factor']
                    best_se_range = (se_min, se_max, stats['total'])
    
    if best_se_range:
        suggestions.append(f"SE Range [legacy]: {best_se_range[0]:.2f} - {best_se_range[1]:.2f} "
                          f"(PF: {best_se_pf:.2f}, {best_se_range[2]} trades)")
    
    # 2. Best hours
    hour_pfs = {}
    for hour in range(24):
        filtered = [t for t in closed if t['entry_time'].hour == hour]
        if len(filtered) >= 5:
            stats = calculate_stats(filtered)
            if stats and stats['profit_factor'] >= 1.2:
                hour_pfs[hour] = stats['profit_factor']
    
    if hour_pfs:
        best_hours = sorted(hour_pfs.keys(), key=lambda h: hour_pfs[h], reverse=True)[:8]
        suggestions.append(f"Best Hours (UTC): {sorted(best_hours)}")
    
    # 3. Best days
    day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    day_pfs = {}
    for dow in range(7):
        filtered = [t for t in closed if t['entry_time'].weekday() == dow]
        if len(filtered) >= 5:
            stats = calculate_stats(filtered)
            if stats and stats['profit_factor'] >= 1.2:
                day_pfs[dow] = stats['profit_factor']
    
    if day_pfs:
        best_days = sorted(day_pfs.keys(), key=lambda d: day_pfs[d], reverse=True)
        suggestions.append(f"Best Days: {[day_names[d] for d in best_days]}")
    
    # 4. SL pips range
    best_sl_pf = 0
    best_sl_range = None
    for sl_min in [5, 10, 15]:
        for sl_max in [15, 20, 25, 30]:
            if sl_max <= sl_min:
                continue
            filtered = [t for t in closed if 'sl_pips' in t and sl_min <= t['sl_pips'] <= sl_max]
            if len(filtered) >= 10:
                stats = calculate_stats(filtered)
                if stats and stats['profit_factor'] > best_sl_pf:
                    best_sl_pf = stats['profit_factor']
                    best_sl_range = (sl_min, sl_max)
    
    if best_sl_range:
        suggestions.append(f"SL Pips Range: {best_sl_range[0]:.0f} - {best_sl_range[1]:.0f} "
                          f"(PF: {best_sl_pf:.2f})")
    
    # Print suggestions
    print("\nBased on the analysis, consider these filters:\n")
    for i, sugg in enumerate(suggestions, 1):
        print(f"  {i}. {sugg}")
    
    print("\n⚠️  Always verify with forward testing before applying to live trading.")


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description='HELIX Strategy Trade Log Analyzer')
    parser.add_argument('logfile', nargs='?', help='Specific log file to analyze')
    parser.add_argument('--all', action='store_true', help='Analyze all HELIX logs combined')
    parser.add_argument('--dir', default=LOG_DIR, help='Log directory')
    args = parser.parse_args()
    
    trades = []
    
    if args.all:
        # Combine all logs
        logs = find_all_logs(args.dir, 'HELIX_trades_')
        if not logs:
            print(f'No HELIX logs found in {args.dir}')
            sys.exit(1)
        print(f'Analyzing {len(logs)} HELIX log files...')
        for log in logs:
            filepath = os.path.join(args.dir, log)
            trades.extend(parse_helix_log(filepath))
    elif args.logfile:
        # Specific file
        filepath = args.logfile if os.path.isabs(args.logfile) else os.path.join(args.dir, args.logfile)
        if not os.path.exists(filepath):
            print(f'File not found: {filepath}')
            sys.exit(1)
        trades = parse_helix_log(filepath)
        print(f'Analyzing: {filepath}')
    else:
        # Latest file
        latest = find_latest_log(args.dir, 'HELIX_trades_')
        if not latest:
            print(f'No HELIX logs found in {args.dir}')
            sys.exit(1)
        filepath = os.path.join(args.dir, latest)
        trades = parse_helix_log(filepath)
        print(f'Analyzing latest: {latest}')
    
    if not trades:
        print('No trades found in log file(s).')
        sys.exit(1)
    
    print(f'\nTotal entries parsed: {len(trades)}')
    
    # Run all analyses
    analyze_overall(trades)
    analyze_by_se(trades)
    analyze_by_se_stddev(trades)  # NEW: Key stability metric
    analyze_se_combinations(trades)
    analyze_by_hour(trades)
    analyze_by_day(trades)
    analyze_by_sl_pips(trades)
    analyze_by_atr(trades)
    analyze_by_breakout_waited(trades)  # NEW: Breakout window optimization
    analyze_by_pullback_bars(trades)    # NEW: Pullback duration optimization
    analyze_by_year(trades)
    analyze_by_exit_reason(trades)
    analyze_trade_duration(trades)
    generate_filter_suggestions(trades)
    
    print_section('ANALYSIS COMPLETE', '=')


if __name__ == '__main__':
    main()
