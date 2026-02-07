"""
GEMINI Strategy Analyzer

Comprehensive analysis tool for GEMINI strategy optimization.
Analyzes trade logs to find optimal parameters for correlation divergence entries.

Usage:
    python analyze_gemini.py                           # Analyze latest GEMINI log
    python analyze_gemini.py GEMINI_trades_xxx.txt     # Analyze specific log
    python analyze_gemini.py --all                     # Analyze all GEMINI logs combined

Key Parameters to Analyze:
- Harmony Score ranges
- Entry hour (UTC)
- Day of week
- SL pips ranges
- Exit reason distribution

Author: Ivan
Version: 1.1.0
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

def print_section(title: str, char: str = '=', width: int = 70):
    """Print formatted section header."""
    print(f'\n{char * width}')
    print(f'{title}')
    print(char * width)


def format_pf(pf: float) -> str:
    """Format profit factor."""
    return f'{pf:.2f}' if pf < 100 else 'INF'


# =============================================================================
# LOG PARSING (HELIX-style .txt format)
# =============================================================================

def find_latest_log(log_dir: str, prefix: str = 'GEMINI_trades_') -> Optional[str]:
    """Find the most recent log file with given prefix."""
    if not os.path.exists(log_dir):
        return None
    logs = [f for f in os.listdir(log_dir) if f.startswith(prefix) and f.endswith('.txt')]
    return max(logs) if logs else None


def find_all_logs(log_dir: str, prefix: str = 'GEMINI_trades_') -> List[str]:
    """Find all log files with given prefix."""
    if not os.path.exists(log_dir):
        return []
    return sorted([f for f in os.listdir(log_dir) if f.startswith(prefix) and f.endswith('.txt')])


def parse_config_header(content: str) -> Dict:
    """Parse configuration header from GEMINI trade log."""
    config = {}
    
    # KAMA
    match = re.search(r'KAMA: period=(\d+), fast=(\d+), slow=(\d+)', content)
    if match:
        config['kama_period'] = int(match.group(1))
        config['kama_fast'] = int(match.group(2))
        config['kama_slow'] = int(match.group(3))
    
    # KAMA Filter
    config['kama_filter'] = 'ENABLED' in re.search(r'KAMA Filter: (\w+)', content or '').group(1) if re.search(r'KAMA Filter: (\w+)', content) else False
    
    # Harmony Score
    match = re.search(r'Harmony: threshold=([\d.]+), scale=([\d.]+), bars=(\d+)', content)
    if match:
        config['harmony_threshold'] = float(match.group(1))
        config['harmony_scale'] = float(match.group(2))
        config['harmony_bars'] = int(match.group(3))
    
    # ATR
    match = re.search(r'ATR: length=(\d+), avg_period=(\d+)', content)
    if match:
        config['atr_length'] = int(match.group(1))
        config['atr_avg_period'] = int(match.group(2))
    
    # SL/TP multipliers
    match = re.search(r'SL: ([\d.]+)x ATR \| TP: ([\d.]+)x ATR', content)
    if match:
        config['sl_mult'] = float(match.group(1))
        config['tp_mult'] = float(match.group(2))
    
    # Pip Value
    match = re.search(r'Pip Value: ([\d.]+)', content)
    if match:
        config['pip_value'] = float(match.group(1))
    
    # Risk
    match = re.search(r'Risk: ([\d.]+)%', content)
    if match:
        config['risk_pct'] = float(match.group(1))
    
    # Filters
    config['sl_pips_filter'] = 'SL Pips Filter: DISABLED' not in content
    config['atr_filter'] = 'ATR Filter: DISABLED' not in content
    config['time_filter'] = 'Time Filter: DISABLED' not in content
    config['day_filter'] = 'Day Filter: DISABLED' not in content
    
    # Parse filter values if enabled
    if config.get('sl_pips_filter'):
        match = re.search(r'SL Pips Filter: (\d+)-(\d+) pips', content)
        if match:
            config['sl_pips_min'] = int(match.group(1))
            config['sl_pips_max'] = int(match.group(2))
    
    if config.get('time_filter'):
        match = re.search(r'Time Filter: \[([\d, ]+)\]', content)
        if match:
            config['allowed_hours'] = [int(h.strip()) for h in match.group(1).split(',')]
    
    if config.get('day_filter'):
        match = re.search(r'Day Filter: \[(.*?)\]', content)
        if match:
            config['allowed_days'] = match.group(1)
    
    return config


def print_config(config: Dict):
    """Print parsed configuration."""
    print_section('CONFIGURATION (from log header)')
    
    if not config:
        print("No configuration found in log header")
        return
    
    # KAMA
    if 'kama_period' in config:
        print(f"KAMA: period={config['kama_period']}, fast={config['kama_fast']}, slow={config['kama_slow']}")
    
    # Harmony
    if 'harmony_threshold' in config:
        print(f"Harmony: threshold={config['harmony_threshold']}, scale={config['harmony_scale']}, bars={config['harmony_bars']}")
    
    # ATR
    if 'sl_mult' in config:
        print(f"SL: {config['sl_mult']}x ATR | TP: {config['tp_mult']}x ATR")
    
    if 'pip_value' in config:
        print(f"Pip Value: {config['pip_value']}")
    
    if 'risk_pct' in config:
        print(f"Risk: {config['risk_pct']}%")
    
    # Filters
    print("\nFilters:")
    print(f"  SL Pips Filter: {'ENABLED ' + str(config.get('sl_pips_min', '?')) + '-' + str(config.get('sl_pips_max', '?')) + ' pips' if config.get('sl_pips_filter') else 'DISABLED'}")
    print(f"  ATR Filter: {'ENABLED' if config.get('atr_filter') else 'DISABLED'}")
    print(f"  Time Filter: {'ENABLED ' + str(config.get('allowed_hours', [])) if config.get('time_filter') else 'DISABLED'}")
    print(f"  Day Filter: {'ENABLED ' + str(config.get('allowed_days', '')) if config.get('day_filter') else 'DISABLED'}")


def parse_gemini_log(filepath: str) -> tuple:
    """
    Parse GEMINI trade log file (HELIX-style .txt format).
    
    Expected format:
        ENTRY #N
        Time: YYYY-MM-DD HH:MM:SS
        Entry Price: X.XXXXX
        Stop Loss: X.XXXXX
        Take Profit: X.XXXXX
        SL Pips: XX.X
        ATR (avg): X.XXXXXX
        Cross Bars: N
        ROC Angle: XX.X
        Harmony Angle: XX.X
        
        EXIT #N
        Time: YYYY-MM-DD HH:MM:SS
        Exit Reason: REASON
        P&L: $X,XXX.XX
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Parse entries - pattern for GEMINI log format (with Cross Bars, ROC Angle and Harmony Angle)
    entries = re.findall(
        r'ENTRY #(\d+)\s*\n'
        r'Time: ([\d-]+ [\d:]+)\s*\n'
        r'Entry Price: ([\d.]+)\s*\n'
        r'Stop Loss: ([\d.]+)\s*\n'
        r'Take Profit: ([\d.]+)\s*\n'
        r'SL Pips: ([\d.]+)\s*\n'
        r'ATR \(avg\): ([\d.]+)\s*\n'
        r'Cross Bars: (\d+)\s*\n'
        r'ROC Angle: ([\d.]+).*\n'
        r'Harmony Angle: ([\d.]+)',
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
        entry_time = datetime.strptime(entry[1], '%Y-%m-%d %H:%M:%S')
        
        trade = {
            'id': trade_id,
            'datetime': entry_time,
            'entry_price': float(entry[2]),
            'sl': float(entry[3]),
            'tp': float(entry[4]),
            'sl_pips': float(entry[5]),
            'atr': float(entry[6]),
            'cross_bars': int(entry[7]),
            'roc_angle': float(entry[8]),
            'harmony_angle': float(entry[9]),
            'hour': entry_time.hour,
            'day_of_week': entry_time.weekday(),
        }
        
        # Match with exit if exists
        if trade_id in exit_dict:
            ex = exit_dict[trade_id]
            exit_time = datetime.strptime(ex[1], '%Y-%m-%d %H:%M:%S')
            trade['exit_time'] = exit_time
            trade['exit_reason'] = ex[2]
            trade['pnl'] = float(ex[3].replace(',', ''))
            trade['bars_held'] = int((exit_time - entry_time).total_seconds() / 300)  # 5m bars
        
        trades.append(trade)
    
    # Filter to only closed trades
    closed_trades = [t for t in trades if 'pnl' in t]
    
    # Parse configuration header
    config = parse_config_header(content)
    
    return closed_trades, config


# =============================================================================
# ANALYSIS FUNCTIONS
# =============================================================================

def calculate_metrics(trades: List[Dict]) -> Dict:
    """Calculate trading metrics for a list of trades."""
    if not trades:
        return {'n': 0, 'pf': 0, 'wr': 0, 'avg_pnl': 0, 'gross_profit': 0, 'gross_loss': 0}
    
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


def analyze_by_roc_angle(trades: List[Dict], step: float = 5.0) -> None:
    """Analyze performance by ROC angle ranges."""
    print_section('ANALYSIS BY ROC ANGLE RANGE (degrees)')
    
    if not trades:
        print('No trades to analyze')
        return
    
    # Get ROC angle range
    angles = [t['roc_angle'] for t in trades]
    min_ang = min(angles)
    max_ang = max(angles)
    
    print(f'ROC Angle range: {min_ang:.1f} to {max_ang:.1f} degrees')
    print(f'\n{"Range":<15} {"Trades":>8} {"Wins":>6} {"WR%":>8} {"PF":>8} {"Avg PnL":>10}')
    print('-' * 60)
    
    # Analyze by ranges
    current = 0
    while current <= max_ang + step:
        range_max = current + step
        range_trades = [t for t in trades if current <= t['roc_angle'] < range_max]
        
        if range_trades:
            m = calculate_metrics(range_trades)
            range_str = f'{current:.0f}-{range_max:.0f}'
            print(f'{range_str:<15} {m["n"]:>8} {m["wins"]:>6} {m["wr"]:>7.1f}% {format_pf(m["pf"]):>8} {m["avg_pnl"]:>+10.1f}')
        
        current += step
    
    # Find optimal range (best PF with min 3 trades)
    best_pf = 0
    best_range = None
    current = 0
    while current <= max_ang:
        range_max = current + step
        range_trades = [t for t in trades if current <= t['roc_angle'] < range_max]
        if range_trades:
            m = calculate_metrics(range_trades)
            if m['pf'] > best_pf and m['n'] >= 3:
                best_pf = m['pf']
                best_range = (current, range_max)
        current += step
    
    if best_range:
        print(f'\nBest ROC Angle range: {best_range[0]:.0f}-{best_range[1]:.0f} degrees (PF={best_pf:.2f})')


def analyze_by_harmony_angle(trades: List[Dict], step: float = 5.0) -> None:
    """Analyze performance by Harmony angle ranges."""
    print_section('ANALYSIS BY HARMONY ANGLE RANGE (degrees)')
    
    if not trades:
        print('No trades to analyze')
        return
    
    # Get Harmony angle range
    angles = [t['harmony_angle'] for t in trades]
    min_ang = min(angles)
    max_ang = max(angles)
    
    print(f'Harmony Angle range: {min_ang:.1f} to {max_ang:.1f} degrees')
    print(f'\n{"Range":<15} {"Trades":>8} {"Wins":>6} {"WR%":>8} {"PF":>8} {"Avg PnL":>10}')
    print('-' * 60)
    
    # Analyze by ranges
    current = 0
    while current <= max_ang + step:
        range_max = current + step
        range_trades = [t for t in trades if current <= t['harmony_angle'] < range_max]
        
        if range_trades:
            m = calculate_metrics(range_trades)
            range_str = f'{current:.0f}-{range_max:.0f}'
            print(f'{range_str:<15} {m["n"]:>8} {m["wins"]:>6} {m["wr"]:>7.1f}% {format_pf(m["pf"]):>8} {m["avg_pnl"]:>+10.1f}')
        
        current += step
    
    # Find optimal range (best PF with min 3 trades)
    best_pf = 0
    best_range = None
    current = 0
    while current <= max_ang:
        range_max = current + step
        range_trades = [t for t in trades if current <= t['harmony_angle'] < range_max]
        if range_trades:
            m = calculate_metrics(range_trades)
            if m['pf'] > best_pf and m['n'] >= 3:
                best_pf = m['pf']
                best_range = (current, range_max)
        current += step
    
    if best_range:
        print(f'\nBest Harmony Angle range: {best_range[0]:.0f}-{best_range[1]:.0f} degrees (PF={best_pf:.2f})')


def analyze_by_cross_bars(trades: List[Dict]) -> None:
    """Analyze performance by cross_bars (bars from KAMA cross to entry)."""
    print_section('ANALYSIS BY CROSS BARS (bars from KAMA cross to entry)')
    
    if not trades:
        print('No trades to analyze')
        return
    
    # Get cross_bars range
    cross_bars = [t['cross_bars'] for t in trades]
    min_bars = min(cross_bars)
    max_bars = max(cross_bars)
    
    print(f'Cross Bars range: {min_bars} to {max_bars}')
    print(f'\n{"Bars":<10} {"Trades":>8} {"Wins":>6} {"WR%":>8} {"PF":>8} {"Avg PnL":>10}')
    print('-' * 55)
    
    # Analyze by each bar count
    for bar in range(min_bars, max_bars + 1):
        bar_trades = [t for t in trades if t['cross_bars'] == bar]
        
        if bar_trades:
            m = calculate_metrics(bar_trades)
            print(f'{bar:<10} {m["n"]:>8} {m["wins"]:>6} {m["wr"]:>7.1f}% {format_pf(m["pf"]):>8} {m["avg_pnl"]:>+10.1f}')
    
    # Find best bar count (best PF with min 3 trades)
    best_pf = 0
    best_bar = None
    for bar in range(min_bars, max_bars + 1):
        bar_trades = [t for t in trades if t['cross_bars'] == bar]
        if bar_trades:
            m = calculate_metrics(bar_trades)
            if m['pf'] > best_pf and m['n'] >= 3:
                best_pf = m['pf']
                best_bar = bar
    
    if best_bar is not None:
        print(f'\nBest Cross Bars: {best_bar} (PF={best_pf:.2f})')


def analyze_by_atr_range(trades: List[Dict], step: float = 0.0001) -> None:
    """Analyze performance by ATR ranges."""
    print_section('ANALYSIS BY ATR RANGE')
    
    if not trades:
        print('No trades to analyze')
        return
    
    # Get ATR range
    atrs = [t['atr'] for t in trades]
    min_atr = min(atrs)
    max_atr = max(atrs)
    
    print(f'ATR range: {min_atr:.6f} to {max_atr:.6f}')
    print(f'\n{"Range":<22} {"Trades":>8} {"Wins":>6} {"WR%":>8} {"PF":>8} {"Avg PnL":>10}')
    print('-' * 65)
    
    # Analyze by ranges
    current = round(min_atr, 4)
    while current <= max_atr:
        range_max = current + step
        range_trades = [t for t in trades if current <= t['atr'] < range_max]
        
        if range_trades:
            m = calculate_metrics(range_trades)
            range_str = f'{current:.5f}-{range_max:.5f}'
            print(f'{range_str:<22} {m["n"]:>8} {m["wins"]:>6} {m["wr"]:>7.1f}% {format_pf(m["pf"]):>8} {m["avg_pnl"]:>+10.1f}')
        
        current += step
    
    # Find optimal range (best PF with min 5 trades)
    best_pf = 0
    best_range = None
    current = round(min_atr, 4)
    while current <= max_atr:
        range_max = current + step
        range_trades = [t for t in trades if current <= t['atr'] < range_max]
        if range_trades:
            m = calculate_metrics(range_trades)
            if m['pf'] > best_pf and m['n'] >= 5:
                best_pf = m['pf']
                best_range = (current, range_max)
        current += step
    
    if best_range:
        print(f'\nBest ATR range: {best_range[0]:.5f}-{best_range[1]:.5f} (PF={best_pf:.2f})')
    
    # Show ATR stats
    print(f'\nATR Stats:')
    print(f'  Min: {min_atr:.6f}')
    print(f'  Max: {max_atr:.6f}')
    print(f'  Avg: {sum(atrs)/len(atrs):.6f}')


# Note: analyze_by_momentum removed - ROC approach uses sustained divergence_bars instead


def analyze_by_hour(trades: List[Dict]) -> None:
    """Analyze performance by entry hour."""
    print_section('ANALYSIS BY ENTRY HOUR (UTC)')
    
    if not trades:
        print('No trades to analyze')
        return
    
    hour_groups = defaultdict(list)
    for t in trades:
        hour_groups[t['hour']].append(t)
    
    print(f'\n{"Hour":>6} {"Trades":>8} {"Wins":>6} {"WR%":>8} {"PF":>8} {"Avg PnL":>10}')
    print('-' * 50)
    
    profitable_hours = []
    for hour in range(24):
        if hour in hour_groups:
            m = calculate_metrics(hour_groups[hour])
            print(f'{hour:>6} {m["n"]:>8} {m["wins"]:>6} {m["wr"]:>7.1f}% {format_pf(m["pf"]):>8} {m["avg_pnl"]:>+10.1f}')
            if m['pf'] >= 1.5 and m['n'] >= 5:
                profitable_hours.append(hour)
    
    if profitable_hours:
        print(f'\nSuggested hours (PF >= 1.5, n >= 5): {profitable_hours}')


def analyze_by_day(trades: List[Dict]) -> None:
    """Analyze performance by day of week."""
    print_section('ANALYSIS BY DAY OF WEEK')
    
    if not trades:
        print('No trades to analyze')
        return
    
    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    day_groups = defaultdict(list)
    for t in trades:
        day_groups[t['day_of_week']].append(t)
    
    print(f'\n{"Day":<12} {"Trades":>8} {"Wins":>6} {"WR%":>8} {"PF":>8} {"Avg PnL":>10}')
    print('-' * 55)
    
    profitable_days = []
    for day in range(7):
        if day in day_groups:
            m = calculate_metrics(day_groups[day])
            print(f'{day_names[day]:<12} {m["n"]:>8} {m["wins"]:>6} {m["wr"]:>7.1f}% {format_pf(m["pf"]):>8} {m["avg_pnl"]:>+10.1f}')
            if m['pf'] >= 1.5:
                profitable_days.append(day)
    
    if profitable_days:
        print(f'\nSuggested days (PF >= 1.5): {[day_names[d] for d in profitable_days]}')


def analyze_by_exit_reason(trades: List[Dict]) -> None:
    """Analyze performance by exit reason."""
    print_section('ANALYSIS BY EXIT REASON')
    
    if not trades:
        print('No trades to analyze')
        return
    
    reason_groups = defaultdict(list)
    for t in trades:
        reason_groups[t['exit_reason']].append(t)
    
    print(f'\n{"Reason":<12} {"Trades":>8} {"Wins":>6} {"WR%":>8} {"PF":>8} {"Avg PnL":>10}')
    print('-' * 55)
    
    for reason in sorted(reason_groups.keys()):
        m = calculate_metrics(reason_groups[reason])
        print(f'{reason:<12} {m["n"]:>8} {m["wins"]:>6} {m["wr"]:>7.1f}% {format_pf(m["pf"]):>8} {m["avg_pnl"]:>+10.1f}')


def analyze_by_sl_pips(trades: List[Dict], step: float = 5.0) -> None:
    """Analyze performance by SL pips ranges."""
    print_section('ANALYSIS BY SL PIPS RANGE')
    
    if not trades:
        print('No trades to analyze')
        return
    
    # Get SL pips range
    sl_pips = [t['sl_pips'] for t in trades]
    min_sl = min(sl_pips)
    max_sl = max(sl_pips)
    
    print(f'SL pips range: {min_sl:.1f} to {max_sl:.1f}')
    print(f'\n{"Range":<15} {"Trades":>8} {"Wins":>6} {"WR%":>8} {"PF":>8} {"Avg PnL":>10}')
    print('-' * 60)
    
    current = 0
    while current <= max_sl:
        range_max = current + step
        range_trades = [t for t in trades if current <= t['sl_pips'] < range_max]
        
        if range_trades:
            m = calculate_metrics(range_trades)
            range_str = f'{current:.0f}-{range_max:.0f}'
            print(f'{range_str:<15} {m["n"]:>8} {m["wins"]:>6} {m["wr"]:>7.1f}% {format_pf(m["pf"]):>8} {m["avg_pnl"]:>+10.1f}')
        
        current += step


def print_summary(trades: List[Dict]) -> None:
    """Print overall summary."""
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
    print(f'Avg Win:          ${m["avg_win"]:+,.0f}')
    print(f'Avg Loss:         ${m["avg_loss"]:,.0f}')
    print(f'Gross Profit:     ${m["gross_profit"]:+,.0f}')
    print(f'Gross Loss:       ${m["gross_loss"]:,.0f}')
    
    # Date range
    dates = sorted([t['datetime'] for t in trades])
    print(f'\nDate Range:       {dates[0]} to {dates[-1]}')
    
    # Cross Bars stats
    cross_bars = [t['cross_bars'] for t in trades]
    print(f'\nCross Bars Range:    {min(cross_bars)} to {max(cross_bars)} bars')
    print(f'Cross Bars Avg:      {sum(cross_bars)/len(cross_bars):.1f} bars')
    
    # ROC Angle stats
    roc_angles = [t['roc_angle'] for t in trades]
    print(f'\nROC Angle Range:     {min(roc_angles):.1f} to {max(roc_angles):.1f} degrees')
    print(f'ROC Angle Avg:       {sum(roc_angles)/len(roc_angles):.1f} degrees')
    
    # Harmony Angle stats
    harmony_angles = [t['harmony_angle'] for t in trades]
    print(f'\nHarmony Angle Range: {min(harmony_angles):.1f} to {max(harmony_angles):.1f} degrees')
    print(f'Harmony Angle Avg:   {sum(harmony_angles)/len(harmony_angles):.1f} degrees')
    
    # Bars held stats
    if 'bars_held' in trades[0]:
        bars = [t['bars_held'] for t in trades]
        print(f'\nBars Held Range:  {min(bars)} to {max(bars)}')
        print(f'Bars Held Avg:    {sum(bars)/len(bars):.1f}')


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description='Analyze GEMINI strategy trade logs')
    parser.add_argument('logfile', nargs='?', help='Specific log file to analyze')
    parser.add_argument('--all', action='store_true', help='Analyze all logs combined')
    args = parser.parse_args()
    
    trades = []
    config = {}
    
    if args.all:
        # Analyze all logs combined
        logs = find_all_logs(LOG_DIR)
        if not logs:
            print(f'No GEMINI logs found in {LOG_DIR}')
            return
        print(f'Analyzing {len(logs)} log files...')
        for log in logs:
            filepath = os.path.join(LOG_DIR, log)
            log_trades, log_config = parse_gemini_log(filepath)
            trades.extend(log_trades)
            if not config:
                config = log_config  # Use first log's config
    elif args.logfile:
        # Analyze specific log
        if os.path.exists(args.logfile):
            filepath = args.logfile
        else:
            filepath = os.path.join(LOG_DIR, args.logfile)
        if not os.path.exists(filepath):
            print(f'Log file not found: {filepath}')
            return
        print(f'Analyzing: {filepath}')
        trades, config = parse_gemini_log(filepath)
    else:
        # Analyze latest log
        latest = find_latest_log(LOG_DIR)
        if not latest:
            print(f'No GEMINI logs found in {LOG_DIR}')
            return
        filepath = os.path.join(LOG_DIR, latest)
        print(f'Analyzing latest: {filepath}')
        trades, config = parse_gemini_log(filepath)
    
    if not trades:
        print('No trades parsed from log file(s)')
        return
    
    print(f'\nTotal trades parsed: {len(trades)}')
    
    # Print configuration first
    print_config(config)
    
    # Run all analyses
    print_summary(trades)
    analyze_by_cross_bars(trades)
    analyze_by_roc_angle(trades)
    analyze_by_harmony_angle(trades)
    analyze_by_atr_range(trades)
    analyze_by_sl_pips(trades)
    analyze_by_hour(trades)
    analyze_by_day(trades)
    analyze_by_exit_reason(trades)


if __name__ == '__main__':
    main()
