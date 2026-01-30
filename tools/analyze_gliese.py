"""
GLIESE Mean Reversion Strategy Analyzer

Comprehensive analysis tool for GLIESE strategy optimization.
Analyzes trade logs and raw price data to find optimal parameters.

Usage:
    python analyze_gliese.py                           # Analyze latest GLIESE log
    python analyze_gliese.py GLIESE_trades_xxx.txt    # Analyze specific log
    python analyze_gliese.py --data USDCHF_5m.csv     # Analyze raw data for mean reversion patterns
    python analyze_gliese.py --optimize USDCHF        # Run optimization analysis

Features:
- Trade log analysis (hour, day, SL pips, ATR ranges)
- Mean reversion pattern detection in raw data
- Parameter sensitivity analysis
- Optimal entry/exit zone identification

Author: Ivan
Version: 1.0.0
"""
import os
import sys
import re
import numpy as np
import pandas as pd
from datetime import datetime
from collections import defaultdict
from typing import List, Dict, Optional, Tuple
import argparse


# =============================================================================
# CONFIGURATION
# =============================================================================

# Default paths (relative to this script)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, '..', 'logs'))
DATA_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, '..', 'data'))


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


# =============================================================================
# LOG PARSING
# =============================================================================

def find_latest_log(log_dir: str, prefix: str = 'GLIESE_trades_') -> Optional[str]:
    """Find the most recent log file with given prefix."""
    if not os.path.exists(log_dir):
        return None
    logs = [f for f in os.listdir(log_dir) if f.startswith(prefix) and f.endswith('.txt')]
    return max(logs) if logs else None


def parse_gliese_log(filepath: str) -> List[Dict]:
    """
    Parse GLIESE trade log file.
    
    Expected format:
        ENTRY #N
        Time: YYYY-MM-DD HH:MM:SS
        Entry Price: X.XXXXX
        Stop Loss: X.XXXXX
        Take Profit: X.XXXXX
        SL Pips: XX.X
        ATR (avg): X.XXXXXX
        State: Extension=X bars
        
        EXIT #N
        Time: YYYY-MM-DD HH:MM:SS
        Exit Reason: REASON
        P&L: $X,XXX.XX
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Parse entries - updated pattern for actual log format
    entries = re.findall(
        r'ENTRY #(\d+)\s*\n'
        r'Time: ([\d-]+ [\d:]+)\s*\n'
        r'Entry Price: ([\d.]+)\s*\n'
        r'Stop Loss: ([\d.]+)\s*\n'
        r'Take Profit: ([\d.]+)\s*\n'
        r'SL Pips: ([\d.]+)\s*\n'
        r'ATR \(avg\): ([\d.]+)\s*\n'
        r'Extension Bars: (\d+)',
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
            'extension_bars': int(entry[7]),
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


def analyze_by_hour(trades: List[Dict]):
    """Analyze trades by entry hour."""
    print_section('ANALYSIS BY HOUR (UTC)')
    
    groups = defaultdict(list)
    for t in trades:
        if 'pnl' in t:
            hour = t['entry_time'].hour
            groups[hour].append(t)
    
    print(f'{"Hour":>6} | {"Trades":>6} | {"Win%":>5} | {"PF":>5} | {"Net P&L":>12} | {"Expectancy":>10}')
    print('-' * 60)
    
    for hour in range(24):
        if hour in groups:
            stats = calculate_stats(groups[hour])
            if stats:
                exp = calculate_expectancy(stats)
                print(f'{hour:>6} | {stats["total"]:>6} | {stats["win_rate"]:>4.0f}% | '
                      f'{format_pf(stats["profit_factor"]):>5} | ${stats["net_pnl"]:>10,.0f} | ${exp:>9,.0f}')
        else:
            print(f'{hour:>6} |      0 |     - |     - |            - |          -')


def analyze_by_day(trades: List[Dict]):
    """Analyze trades by day of week."""
    print_section('ANALYSIS BY DAY OF WEEK')
    
    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    groups = defaultdict(list)
    
    for t in trades:
        if 'pnl' in t:
            dow = t['entry_time'].weekday()
            groups[dow].append(t)
    
    print(f'{"Day":>12} | {"Trades":>6} | {"Win%":>5} | {"PF":>5} | {"Net P&L":>12}')
    print('-' * 50)
    
    for dow in range(7):
        stats = calculate_stats(groups[dow])
        if stats:
            print(f'{day_names[dow]:>12} | {stats["total"]:>6} | {stats["win_rate"]:>4.0f}% | '
                  f'{format_pf(stats["profit_factor"]):>5} | ${stats["net_pnl"]:>10,.0f}')


def analyze_by_sl_pips(trades: List[Dict]):
    """Analyze trades by SL pips ranges."""
    print_section('ANALYSIS BY SL PIPS')
    
    ranges = [(0, 10), (10, 15), (15, 20), (20, 30), (30, 50), (50, 100)]
    
    print(f'{"SL Pips":>12} | {"Trades":>6} | {"Win%":>5} | {"PF":>5} | {"Net P&L":>12}')
    print('-' * 50)
    
    for low, high in ranges:
        filtered = [t for t in trades if 'pnl' in t and 'sl_pips' in t and low <= t['sl_pips'] < high]
        if filtered:
            stats = calculate_stats(filtered)
            label = f'{low:>3}-{high:<3}'
            print(f'{label:>12} | {stats["total"]:>6} | {stats["win_rate"]:>4.0f}% | '
                  f'{format_pf(stats["profit_factor"]):>5} | ${stats["net_pnl"]:>10,.0f}')


def analyze_by_atr(trades: List[Dict]):
    """Analyze trades by ATR ranges."""
    print_section('ANALYSIS BY ATR')
    
    # Determine ATR ranges dynamically
    atrs = [t['atr'] for t in trades if 'atr' in t and 'pnl' in t]
    if not atrs:
        print('No ATR data available.')
        return
    
    min_atr = min(atrs)
    max_atr = max(atrs)
    step = (max_atr - min_atr) / 5
    
    ranges = []
    for i in range(5):
        low = min_atr + i * step
        high = min_atr + (i + 1) * step
        ranges.append((low, high))
    
    print(f'{"ATR Range":>18} | {"Trades":>6} | {"Win%":>5} | {"PF":>5} | {"Net P&L":>12}')
    print('-' * 58)
    
    for low, high in ranges:
        filtered = [t for t in trades if 'pnl' in t and 'atr' in t and low <= t['atr'] < high]
        if filtered:
            stats = calculate_stats(filtered)
            label = f'{low:.6f}-{high:.6f}'
            print(f'{label:>18} | {stats["total"]:>6} | {stats["win_rate"]:>4.0f}% | '
                  f'{format_pf(stats["profit_factor"]):>5} | ${stats["net_pnl"]:>10,.0f}')


def analyze_by_year(trades: List[Dict]):
    """Analyze trades by year."""
    print_section('YEARLY STATISTICS')
    
    groups = defaultdict(list)
    for t in trades:
        if 'pnl' in t:
            year = t['entry_time'].year
            groups[year].append(t)
    
    print(f'{"Year":>6} | {"Trades":>6} | {"Win%":>5} | {"PF":>5} | {"Net P&L":>12}')
    print('-' * 45)
    
    for year in sorted(groups.keys()):
        stats = calculate_stats(groups[year])
        if stats:
            print(f'{year:>6} | {stats["total"]:>6} | {stats["win_rate"]:>4.0f}% | '
                  f'{format_pf(stats["profit_factor"]):>5} | ${stats["net_pnl"]:>10,.0f}')


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
    print('-' * 42)
    
    for (low, high), label in zip(ranges, labels):
        filtered = [t for t in closed if low <= t['duration_min'] < high]
        if filtered:
            stats = calculate_stats(filtered)
            if stats:
                print(f'{label:>10} | {stats["total"]:>6} | {stats["win_rate"]:>4.0f}% | '
                      f'${stats["net_pnl"]:>10,.0f}')


def analyze_by_extension_bars(trades: List[Dict]):
    """Analyze trades by extension bars (GLIESE specific)."""
    print_section('ANALYSIS BY EXTENSION BARS')
    
    # Filter trades with extension_bars data
    filtered = [t for t in trades if 'extension_bars' in t and 'pnl' in t]
    if not filtered:
        print('No extension bars data available.')
        return
    
    groups = defaultdict(list)
    for t in filtered:
        groups[t['extension_bars']].append(t)
    
    print(f'{"Ext Bars":>10} | {"Trades":>6} | {"Win%":>5} | {"PF":>5} | {"Net P&L":>12}')
    print('-' * 50)
    
    for ext_bars in sorted(groups.keys()):
        stats = calculate_stats(groups[ext_bars])
        if stats:
            print(f'{ext_bars:>10} | {stats["total"]:>6} | {stats["win_rate"]:>4.0f}% | '
                  f'{format_pf(stats["profit_factor"]):>5} | ${stats["net_pnl"]:>10,.0f}')
    
    # Also show ranges
    print('\nGrouped by Extension Range:')
    ranges = [(2, 4), (4, 6), (6, 10), (10, 20)]
    print(f'{"Range":>10} | {"Trades":>6} | {"Win%":>5} | {"PF":>5} | {"Net P&L":>12}')
    print('-' * 50)
    
    for low, high in ranges:
        range_trades = [t for t in filtered if low <= t['extension_bars'] < high]
        if range_trades:
            stats = calculate_stats(range_trades)
            label = f'{low}-{high-1}'
            print(f'{label:>10} | {stats["total"]:>6} | {stats["win_rate"]:>4.0f}% | '
                  f'{format_pf(stats["profit_factor"]):>5} | ${stats["net_pnl"]:>10,.0f}')


# =============================================================================
# MEAN REVERSION DATA ANALYSIS
# =============================================================================

def load_price_data(filepath: str) -> pd.DataFrame:
    """Load OHLC data from CSV file."""
    # Try different date formats
    for date_col in ['datetime', 'date', 'time', 'timestamp']:
        try:
            df = pd.read_csv(filepath)
            if date_col in df.columns:
                df['datetime'] = pd.to_datetime(df[date_col])
                break
        except:
            continue
    else:
        # Try with index
        df = pd.read_csv(filepath, index_col=0, parse_dates=True)
        df['datetime'] = df.index
    
    # Normalize column names
    df.columns = [c.lower() for c in df.columns]
    
    return df


def calculate_kama(close: pd.Series, period: int = 10, fast: int = 2, slow: int = 30) -> pd.Series:
    """Calculate Kaufman's Adaptive Moving Average."""
    # Efficiency Ratio
    change = abs(close - close.shift(period))
    volatility = abs(close - close.shift(1)).rolling(window=period).sum()
    
    er = change / volatility
    er = er.fillna(0)
    
    # Smoothing constants
    fast_sc = 2 / (fast + 1)
    slow_sc = 2 / (slow + 1)
    
    sc = (er * (fast_sc - slow_sc) + slow_sc) ** 2
    
    # KAMA
    kama = pd.Series(index=close.index, dtype=float)
    kama.iloc[period - 1] = close.iloc[period - 1]
    
    for i in range(period, len(close)):
        kama.iloc[i] = kama.iloc[i - 1] + sc.iloc[i] * (close.iloc[i] - kama.iloc[i - 1])
    
    return kama


def calculate_efficiency_ratio(close: pd.Series, period: int = 20) -> pd.Series:
    """Calculate Efficiency Ratio."""
    change = abs(close - close.shift(period))
    volatility = abs(close - close.shift(1)).rolling(window=period).sum()
    return change / volatility


def analyze_mean_reversion_patterns(filepath: str, symbol: str = 'SYMBOL'):
    """
    Analyze price data for mean reversion patterns.
    
    Identifies:
    - Times when price touches band and returns to KAMA
    - Success rate of mean reversion by various parameters
    - Optimal band width
    """
    print_section(f'MEAN REVERSION ANALYSIS: {symbol}')
    
    df = load_price_data(filepath)
    
    # Calculate indicators
    df['kama'] = calculate_kama(df['close'])
    df['atr'] = df['high'].rolling(14).max() - df['low'].rolling(14).min()
    df['atr'] = df['atr'].rolling(14).mean()  # Smoothed ATR approximation
    df['er'] = calculate_efficiency_ratio(df['close'], 20)
    
    # Test different band multipliers
    print('\nBAND MULTIPLIER OPTIMIZATION')
    print(f'{"Mult":>6} | {"Touches":>8} | {"Reversals":>10} | {"Success%":>8} | {"Avg Bars":>8}')
    print('-' * 55)
    
    for mult in [1.0, 1.5, 2.0, 2.5, 3.0]:
        df['upper_band'] = df['kama'] + mult * df['atr']
        df['lower_band'] = df['kama'] - mult * df['atr']
        
        # Count touches of lower band and subsequent reversals
        touches = 0
        reversals = 0
        reversal_bars = []
        
        i = 50
        while i < len(df) - 20:
            if df['close'].iloc[i] < df['lower_band'].iloc[i]:
                touches += 1
                # Check for reversal back to KAMA within 20 bars
                for j in range(1, 21):
                    if i + j < len(df):
                        if df['close'].iloc[i + j] >= df['kama'].iloc[i + j]:
                            reversals += 1
                            reversal_bars.append(j)
                            break
                i += 5  # Skip ahead to avoid counting same touch multiple times
            else:
                i += 1
        
        success_rate = reversals / touches * 100 if touches > 0 else 0
        avg_bars = np.mean(reversal_bars) if reversal_bars else 0
        
        print(f'{mult:>6.1f} | {touches:>8} | {reversals:>10} | {success_rate:>7.1f}% | {avg_bars:>7.1f}')
    
    # ER threshold analysis
    print('\n\nER THRESHOLD OPTIMIZATION')
    print(f'{"ER Max":>8} | {"Touches":>8} | {"Reversals":>10} | {"Success%":>8}')
    print('-' * 45)
    
    df['lower_band'] = df['kama'] - 2.0 * df['atr']  # Use 2.0x ATR for this test
    
    for er_max in [0.25, 0.30, 0.35, 0.40, 0.45, 0.50]:
        touches = 0
        reversals = 0
        
        i = 50
        while i < len(df) - 20:
            if (df['close'].iloc[i] < df['lower_band'].iloc[i] and 
                df['er'].iloc[i] < er_max):
                touches += 1
                for j in range(1, 21):
                    if i + j < len(df):
                        if df['close'].iloc[i + j] >= df['kama'].iloc[i + j]:
                            reversals += 1
                            break
                i += 5
            else:
                i += 1
        
        success_rate = reversals / touches * 100 if touches > 0 else 0
        print(f'{er_max:>8.2f} | {touches:>8} | {reversals:>10} | {success_rate:>7.1f}%')
    
    # Hourly pattern analysis
    print('\n\nHOURLY TOUCH PATTERNS')
    print(f'{"Hour":>6} | {"Touches":>8} | {"Reversals":>10} | {"Success%":>8}')
    print('-' * 42)
    
    hourly_stats = defaultdict(lambda: {'touches': 0, 'reversals': 0})
    
    df['lower_band'] = df['kama'] - 2.0 * df['atr']
    
    i = 50
    while i < len(df) - 20:
        if df['close'].iloc[i] < df['lower_band'].iloc[i]:
            hour = df['datetime'].iloc[i].hour
            hourly_stats[hour]['touches'] += 1
            
            for j in range(1, 21):
                if i + j < len(df):
                    if df['close'].iloc[i + j] >= df['kama'].iloc[i + j]:
                        hourly_stats[hour]['reversals'] += 1
                        break
            i += 5
        else:
            i += 1
    
    for hour in range(24):
        stats = hourly_stats[hour]
        if stats['touches'] > 0:
            success = stats['reversals'] / stats['touches'] * 100
            print(f'{hour:>6} | {stats["touches"]:>8} | {stats["reversals"]:>10} | {success:>7.1f}%')


# =============================================================================
# DETAILED YEARLY ANALYSIS
# =============================================================================

def analyze_detailed_by_year(trades: List[Dict]):
    """Analyze all metrics broken down by year."""
    
    # Group trades by year
    years = defaultdict(list)
    for t in trades:
        if 'pnl' in t:
            year = t['entry_time'].year
            years[year].append(t)
    
    for year in sorted(years.keys()):
        year_trades = years[year]
        
        print_section(f'DETAILED ANALYSIS - YEAR {year}', char='#', width=70)
        
        # Overall stats for this year
        stats = calculate_stats(year_trades)
        if not stats:
            continue
        
        exp = calculate_expectancy(stats)
        print(f"\nYear {year} Summary:")
        print(f"  Trades: {stats['total']} | WR: {stats['win_rate']:.1f}% | PF: {format_pf(stats['profit_factor'])} | Net: ${stats['net_pnl']:,.0f}")
        print(f"  Avg Win: ${stats['avg_win']:.0f} | Avg Loss: ${stats['avg_loss']:.0f} | Expectancy: ${exp:.2f}/trade")
        
        # Hour analysis for this year
        print(f'\n  BY HOUR:')
        print(f'    {"Hour":>4} | {"Tr":>3} | {"WR%":>4} | {"PF":>5} | {"P&L":>10}')
        print(f'    ' + '-' * 38)
        
        hour_groups = defaultdict(list)
        for t in year_trades:
            hour_groups[t['entry_time'].hour].append(t)
        
        for hour in range(24):
            if hour in hour_groups and len(hour_groups[hour]) >= 3:
                h_stats = calculate_stats(hour_groups[hour])
                if h_stats:
                    print(f'    {hour:>4} | {h_stats["total"]:>3} | {h_stats["win_rate"]:>3.0f}% | '
                          f'{format_pf(h_stats["profit_factor"]):>5} | ${h_stats["net_pnl"]:>9,.0f}')
        
        # Day analysis for this year
        print(f'\n  BY DAY:')
        day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        print(f'    {"Day":>4} | {"Tr":>3} | {"WR%":>4} | {"PF":>5} | {"P&L":>10}')
        print(f'    ' + '-' * 38)
        
        day_groups = defaultdict(list)
        for t in year_trades:
            day_groups[t['entry_time'].weekday()].append(t)
        
        for dow in range(7):
            if dow in day_groups:
                d_stats = calculate_stats(day_groups[dow])
                if d_stats:
                    print(f'    {day_names[dow]:>4} | {d_stats["total"]:>3} | {d_stats["win_rate"]:>3.0f}% | '
                          f'{format_pf(d_stats["profit_factor"]):>5} | ${d_stats["net_pnl"]:>9,.0f}')
        
        # SL Pips analysis for this year
        print(f'\n  BY SL PIPS:')
        print(f'    {"SL":>6} | {"Tr":>3} | {"WR%":>4} | {"PF":>5} | {"P&L":>10}')
        print(f'    ' + '-' * 38)
        
        sl_ranges = [(0, 5), (5, 10), (10, 15), (15, 20), (20, 30), (30, 50)]
        for low, high in sl_ranges:
            sl_filtered = [t for t in year_trades if 'sl_pips' in t and low <= t['sl_pips'] < high]
            if sl_filtered:
                sl_stats = calculate_stats(sl_filtered)
                if sl_stats:
                    label = f'{low}-{high}'
                    print(f'    {label:>6} | {sl_stats["total"]:>3} | {sl_stats["win_rate"]:>3.0f}% | '
                          f'{format_pf(sl_stats["profit_factor"]):>5} | ${sl_stats["net_pnl"]:>9,.0f}')
        
        # Extension Bars analysis for this year
        print(f'\n  BY EXTENSION BARS:')
        print(f'    {"Ext":>4} | {"Tr":>3} | {"WR%":>4} | {"PF":>5} | {"P&L":>10}')
        print(f'    ' + '-' * 38)
        
        ext_groups = defaultdict(list)
        for t in year_trades:
            if 'extension_bars' in t:
                ext_groups[t['extension_bars']].append(t)
        
        for ext in sorted(ext_groups.keys()):
            if len(ext_groups[ext]) >= 2:
                e_stats = calculate_stats(ext_groups[ext])
                if e_stats:
                    print(f'    {ext:>4} | {e_stats["total"]:>3} | {e_stats["win_rate"]:>3.0f}% | '
                          f'{format_pf(e_stats["profit_factor"]):>5} | ${e_stats["net_pnl"]:>9,.0f}')
        
        # Extension ranges
        print(f'\n    Extension Ranges:')
        ext_ranges = [(8, 10), (10, 12), (12, 15), (15, 20), (20, 30)]
        for low, high in ext_ranges:
            ext_filtered = [t for t in year_trades if 'extension_bars' in t and low <= t['extension_bars'] < high]
            if ext_filtered:
                ext_stats = calculate_stats(ext_filtered)
                if ext_stats:
                    label = f'{low}-{high-1}'
                    print(f'    {label:>6} | {ext_stats["total"]:>3} | {ext_stats["win_rate"]:>3.0f}% | '
                          f'{format_pf(ext_stats["profit_factor"]):>5} | ${ext_stats["net_pnl"]:>9,.0f}')
        
        # ATR analysis for this year
        print(f'\n  BY ATR:')
        atrs = [t['atr'] for t in year_trades if 'atr' in t]
        if atrs:
            min_atr = min(atrs)
            max_atr = max(atrs)
            step = (max_atr - min_atr) / 4 if max_atr > min_atr else 0.0001
            
            print(f'    {"ATR Range":>16} | {"Tr":>3} | {"WR%":>4} | {"PF":>5} | {"P&L":>10}')
            print(f'    ' + '-' * 46)
            
            for i in range(4):
                low = min_atr + i * step
                high = min_atr + (i + 1) * step
                atr_filtered = [t for t in year_trades if 'atr' in t and low <= t['atr'] < high]
                if atr_filtered:
                    atr_stats = calculate_stats(atr_filtered)
                    if atr_stats:
                        label = f'{low:.5f}-{high:.5f}'
                        print(f'    {label:>16} | {atr_stats["total"]:>3} | {atr_stats["win_rate"]:>3.0f}% | '
                              f'{format_pf(atr_stats["profit_factor"]):>5} | ${atr_stats["net_pnl"]:>9,.0f}')
        
        # Duration analysis for this year
        print(f'\n  BY DURATION:')
        print(f'    {"Dur":>6} | {"Tr":>3} | {"WR%":>4} | {"PF":>5} | {"P&L":>10}')
        print(f'    ' + '-' * 38)
        
        dur_ranges = [(0, 30), (30, 60), (60, 120), (120, 240), (240, 480), (480, float('inf'))]
        dur_labels = ['<30m', '30-60m', '1-2h', '2-4h', '4-8h', '>8h']
        
        for (low, high), label in zip(dur_ranges, dur_labels):
            dur_filtered = [t for t in year_trades if 'duration_min' in t and low <= t['duration_min'] < high]
            if dur_filtered:
                dur_stats = calculate_stats(dur_filtered)
                if dur_stats:
                    print(f'    {label:>6} | {dur_stats["total"]:>3} | {dur_stats["win_rate"]:>3.0f}% | '
                          f'{format_pf(dur_stats["profit_factor"]):>5} | ${dur_stats["net_pnl"]:>9,.0f}')
        
        # Exit reason for this year
        print(f'\n  BY EXIT REASON:')
        print(f'    {"Reason":>12} | {"Tr":>3} | {"WR%":>4} | {"Avg P&L":>10}')
        print(f'    ' + '-' * 38)
        
        exit_groups = defaultdict(list)
        for t in year_trades:
            if 'exit_reason' in t:
                exit_groups[t['exit_reason']].append(t)
        
        for reason in sorted(exit_groups.keys()):
            trades_list = exit_groups[reason]
            total = len(trades_list)
            wins = sum(1 for t in trades_list if t.get('pnl', 0) > 0)
            avg_pnl = sum(t.get('pnl', 0) for t in trades_list) / total
            win_rate = wins / total * 100 if total > 0 else 0
            print(f'    {reason:>12} | {total:>3} | {win_rate:>3.0f}% | ${avg_pnl:>9,.2f}')
    
    # =========================================================================
    # GLOBAL SUMMARY (ALL YEARS COMBINED)
    # =========================================================================
    print_section('GLOBAL SUMMARY (ALL YEARS)', char='#', width=70)
    
    all_trades = [t for t in trades if 'pnl' in t]
    stats = calculate_stats(all_trades)
    if stats:
        exp = calculate_expectancy(stats)
        print(f"\nTotal Summary:")
        print(f"  Trades: {stats['total']} | WR: {stats['win_rate']:.1f}% | PF: {format_pf(stats['profit_factor'])} | Net: ${stats['net_pnl']:,.0f}")
        print(f"  Gross Profit: ${stats['gross_profit']:,.0f} | Gross Loss: ${stats['gross_loss']:,.0f}")
        print(f"  Avg Win: ${stats['avg_win']:.0f} | Avg Loss: ${stats['avg_loss']:.0f} | Expectancy: ${exp:.2f}/trade")
        print(f"  Max Win: ${stats['max_win']:.0f} | Max Loss: ${stats['max_loss']:.0f}")
        
        # Global hour analysis
        print(f'\n  GLOBAL BY HOUR:')
        print(f'    {"Hour":>4} | {"Tr":>3} | {"WR%":>4} | {"PF":>5} | {"P&L":>10}')
        print(f'    ' + '-' * 38)
        
        hour_groups = defaultdict(list)
        for t in all_trades:
            hour_groups[t['entry_time'].hour].append(t)
        
        for hour in range(24):
            if hour in hour_groups and len(hour_groups[hour]) >= 5:
                h_stats = calculate_stats(hour_groups[hour])
                if h_stats:
                    print(f'    {hour:>4} | {h_stats["total"]:>3} | {h_stats["win_rate"]:>3.0f}% | '
                          f'{format_pf(h_stats["profit_factor"]):>5} | ${h_stats["net_pnl"]:>9,.0f}')
        
        # Global day analysis
        print(f'\n  GLOBAL BY DAY:')
        day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        print(f'    {"Day":>4} | {"Tr":>3} | {"WR%":>4} | {"PF":>5} | {"P&L":>10}')
        print(f'    ' + '-' * 38)
        
        day_groups = defaultdict(list)
        for t in all_trades:
            day_groups[t['entry_time'].weekday()].append(t)
        
        for dow in range(7):
            if dow in day_groups:
                d_stats = calculate_stats(day_groups[dow])
                if d_stats:
                    print(f'    {day_names[dow]:>4} | {d_stats["total"]:>3} | {d_stats["win_rate"]:>3.0f}% | '
                          f'{format_pf(d_stats["profit_factor"]):>5} | ${d_stats["net_pnl"]:>9,.0f}')
        
        # Global extension bars analysis
        print(f'\n  GLOBAL BY EXTENSION BARS:')
        print(f'    {"Ext":>4} | {"Tr":>3} | {"WR%":>4} | {"PF":>5} | {"P&L":>10}')
        print(f'    ' + '-' * 38)
        
        ext_groups = defaultdict(list)
        for t in all_trades:
            if 'extension_bars' in t:
                ext_groups[t['extension_bars']].append(t)
        
        for ext in sorted(ext_groups.keys()):
            if len(ext_groups[ext]) >= 3:
                e_stats = calculate_stats(ext_groups[ext])
                if e_stats:
                    print(f'    {ext:>4} | {e_stats["total"]:>3} | {e_stats["win_rate"]:>3.0f}% | '
                          f'{format_pf(e_stats["profit_factor"]):>5} | ${e_stats["net_pnl"]:>9,.0f}')
        
        # Global duration analysis
        print(f'\n  GLOBAL BY DURATION:')
        print(f'    {"Dur":>6} | {"Tr":>3} | {"WR%":>4} | {"PF":>5} | {"P&L":>10}')
        print(f'    ' + '-' * 38)
        
        dur_ranges = [(0, 30), (30, 60), (60, 120), (120, 240), (240, 480), (480, float('inf'))]
        dur_labels = ['<30m', '30-60m', '1-2h', '2-4h', '4-8h', '>8h']
        
        for (low, high), label in zip(dur_ranges, dur_labels):
            dur_filtered = [t for t in all_trades if 'duration_min' in t and low <= t['duration_min'] < high]
            if dur_filtered:
                dur_stats = calculate_stats(dur_filtered)
                if dur_stats:
                    print(f'    {label:>6} | {dur_stats["total"]:>3} | {dur_stats["win_rate"]:>3.0f}% | '
                          f'{format_pf(dur_stats["profit_factor"]):>5} | ${dur_stats["net_pnl"]:>9,.0f}')
        
        # Global SL Pips analysis
        print(f'\n  GLOBAL BY SL PIPS:')
        print(f'    {"SL":>6} | {"Tr":>3} | {"WR%":>4} | {"PF":>5} | {"P&L":>10}')
        print(f'    ' + '-' * 38)
        
        sl_ranges = [(0, 5), (5, 10), (10, 15), (15, 20), (20, 30), (30, 50)]
        for low, high in sl_ranges:
            sl_filtered = [t for t in all_trades if 'sl_pips' in t and low <= t['sl_pips'] < high]
            if sl_filtered:
                sl_stats = calculate_stats(sl_filtered)
                if sl_stats:
                    label = f'{low}-{high}'
                    print(f'    {label:>6} | {sl_stats["total"]:>3} | {sl_stats["win_rate"]:>3.0f}% | '
                          f'{format_pf(sl_stats["profit_factor"]):>5} | ${sl_stats["net_pnl"]:>9,.0f}')


# =============================================================================
# RECOMMENDATIONS
# =============================================================================

def generate_recommendations(trades: List[Dict]):
    """Generate optimization recommendations based on analysis."""
    print_section('OPTIMIZATION RECOMMENDATIONS', char='*')
    
    stats = calculate_stats(trades)
    if not stats:
        print('Insufficient data for recommendations.')
        return
    
    recommendations = []
    
    # Win rate analysis
    if stats['win_rate'] < 35:
        recommendations.append('⚠ Low win rate (<35%). Consider:')
        recommendations.append('  - Tightening entry criteria (lower ER threshold)')
        recommendations.append('  - Increasing extension requirements')
        recommendations.append('  - Adding additional confirmation filters')
    
    # Profit factor analysis
    if stats['profit_factor'] < 1.0:
        recommendations.append('⚠ Losing strategy (PF<1.0). Immediate attention needed:')
        recommendations.append('  - Review SL/TP ratio')
        recommendations.append('  - Analyze losing trades for common patterns')
        recommendations.append('  - Consider increasing TP multiplier')
    elif stats['profit_factor'] < 1.3:
        recommendations.append('⚠ Marginal profitability (PF 1.0-1.3). Consider:')
        recommendations.append('  - Filtering out worst performing hours/days')
        recommendations.append('  - Adjusting SL/TP ratio')
    
    # Risk analysis
    if stats['max_loss'] < -5000:
        recommendations.append('⚠ Large max loss detected. Consider:')
        recommendations.append('  - Implementing SL pips filter')
        recommendations.append('  - Reducing position size')
    
    # Hour analysis
    groups = defaultdict(list)
    for t in trades:
        if 'pnl' in t:
            groups[t['entry_time'].hour].append(t)
    
    unprofitable_hours = []
    profitable_hours = []
    for hour, trade_list in groups.items():
        hour_stats = calculate_stats(trade_list)
        if hour_stats and hour_stats['net_pnl'] < -1000:
            unprofitable_hours.append(hour)
        elif hour_stats and hour_stats['net_pnl'] > 1000:
            profitable_hours.append(hour)
    
    if unprofitable_hours:
        recommendations.append(f'⚠ Unprofitable hours detected: {unprofitable_hours}')
        recommendations.append('  - Consider adding time filter to exclude these hours')
    
    if profitable_hours:
        recommendations.append(f'✓ Profitable hours: {profitable_hours}')
        recommendations.append('  - Consider focusing trades on these hours')
    
    if not recommendations:
        recommendations.append('✓ Strategy appears well-optimized based on available data.')
    
    for rec in recommendations:
        print(rec)


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='GLIESE Mean Reversion Strategy Analyzer',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python analyze_gliese.py                          # Analyze latest log
  python analyze_gliese.py trades.txt              # Analyze specific log
  python analyze_gliese.py --data USDCHF_5m.csv    # Analyze raw price data
        '''
    )
    
    parser.add_argument('logfile', nargs='?', help='Trade log file to analyze')
    parser.add_argument('--data', '-d', help='Price data CSV file for pattern analysis')
    parser.add_argument('--symbol', '-s', default='SYMBOL', help='Symbol name for labels')
    parser.add_argument('--optimize', '-o', action='store_true', 
                        help='Generate optimization recommendations')
    
    args = parser.parse_args()
    
    # Raw data analysis mode
    if args.data:
        data_path = args.data
        if not os.path.isabs(data_path):
            data_path = os.path.join(DATA_DIR, data_path)
        
        if not os.path.exists(data_path):
            print(f'Data file not found: {data_path}')
            return
        
        analyze_mean_reversion_patterns(data_path, args.symbol)
        return
    
    # Trade log analysis mode
    if args.logfile:
        logfile = args.logfile
    else:
        logfile = find_latest_log(LOG_DIR)
        if not logfile:
            print(f'No GLIESE log files found in {LOG_DIR}')
            print('Use --data option to analyze raw price data instead.')
            return
    
    filepath = logfile if os.path.isabs(logfile) else os.path.join(LOG_DIR, logfile)
    
    if not os.path.exists(filepath):
        print(f'Log file not found: {filepath}')
        return
    
    print(f'\nAnalyzing: {os.path.basename(filepath)}')
    
    # Parse log
    trades = parse_gliese_log(filepath)
    
    if not trades:
        print('No trades found in log file.')
        return
    
    print(f'Loaded {len(trades)} trades')
    
    # Run all analyses
    analyze_overall(trades)
    analyze_by_year(trades)
    analyze_by_hour(trades)
    analyze_by_day(trades)
    analyze_by_sl_pips(trades)
    analyze_by_atr(trades)
    analyze_by_extension_bars(trades)
    analyze_by_exit_reason(trades)
    analyze_trade_duration(trades)
    
    # Detailed yearly breakdown
    analyze_detailed_by_year(trades)
    
    if args.optimize:
        generate_recommendations(trades)
    
    print('\n' + '=' * 70)
    print('Analysis complete.')


if __name__ == '__main__':
    main()
