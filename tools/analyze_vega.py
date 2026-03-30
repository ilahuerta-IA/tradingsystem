"""
VEGA Strategy Trade Log Analyzer

Analyzes VEGA trade logs to find optimal parameters for z-score divergence
entries. Key dimensions: Spread, Forecast strength, ATR(B), Direction,
entry hour, day of week, yearly stability.

Usage:
    python analyze_vega.py                           # Analyze latest VEGA log
    python analyze_vega.py VEGA_trades_xxx.txt       # Analyze specific log
    python analyze_vega.py --all                     # Analyze all VEGA logs combined

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

MIN_TRADES_FOR_BEST = 5  # Minimum trades to consider a range "best"


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

def find_latest_log(log_dir: str, prefix: str = 'VEGA_trades_') -> Optional[str]:
    """Find the most recent VEGA log file by modification time."""
    if not os.path.exists(log_dir):
        return None
    logs = [f for f in os.listdir(log_dir)
            if f.startswith(prefix) and f.endswith('.txt')]
    if not logs:
        return None
    logs.sort(key=lambda f: os.path.getmtime(os.path.join(log_dir, f)),
              reverse=True)
    return logs[0]


def find_all_logs(log_dir: str, prefix: str = 'VEGA_trades_') -> List[str]:
    """Find all VEGA log files."""
    if not os.path.exists(log_dir):
        return []
    return sorted([f for f in os.listdir(log_dir)
                   if f.startswith(prefix) and f.endswith('.txt')])


def parse_config_header(content: str) -> Dict:
    """Parse VEGA configuration header from trade log."""
    config = {}

    match = re.search(r'Z-score: SMA=(\d+), ATR=(\d+)', content)
    if match:
        config['sma_period'] = int(match.group(1))
        config['atr_period'] = int(match.group(2))

    match = re.search(r'Dead Zone: ([\d.]+)', content)
    if match:
        config['dead_zone'] = float(match.group(1))

    match = re.search(r'Holding: (\d+)h', content)
    if match:
        config['holding_hours'] = int(match.group(1))

    match = re.search(r'Session: (\d{2}):00-(\d{2}):00 UTC', content)
    if match:
        config['session_start'] = int(match.group(1))
        config['session_end'] = int(match.group(2))

    match = re.search(r'Protective Stop: ON \(([\d.]+)x ATR\)', content)
    if match:
        config['protective_atr_mult'] = float(match.group(1))
    elif 'Protective Stop: OFF' in content:
        config['protective_atr_mult'] = None

    match = re.search(r'Risk: ([\d.]+)%', content)
    if match:
        config['risk_pct'] = float(match.group(1))

    match = re.search(r'Time Filter: \[([^\]]+)\]', content)
    if match:
        config['allowed_hours'] = [int(h.strip()) for h in match.group(1).split(',')]

    match = re.search(r"Day Filter: \[([^\]]+)\]", content)
    if match:
        config['allowed_days'] = match.group(1)

    return config


def parse_vega_log(filepath: str) -> Tuple[List[Dict], Dict]:
    """
    Parse VEGA trade log file.

    Expected format:
        ENTRY #N
        Time: YYYY-MM-DD HH:MM:SS
        Direction: LONG/SHORT
        Entry Price: X.XX
        Size: N contracts
        Spread: X.XXXX
        Forecast: XX.X
        ATR(B): XX.XX
        Protective Stop: XX.XX   (optional)

        EXIT #N
        Time: YYYY-MM-DD HH:MM:SS
        Exit Reason: REASON
        P&L: $X.XX
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Parse entries
    entries = re.findall(
        r'ENTRY #(\d+)\s*\n'
        r'Time: ([\d-]+ [\d:]+)\s*\n'
        r'Direction: (LONG|SHORT)\s*\n'
        r'Entry Price: ([\d.]+)\s*\n'
        r'Size: (\d+) contracts\s*\n'
        r'Spread: ([-\d.]+)\s*\n'
        r'Forecast: ([-\d.]+)\s*\n'
        r'ATR\(B\): ([\d.]+)',
        content,
        re.IGNORECASE
    )

    # Parse exits
    exits_raw = re.findall(
        r'EXIT #(\d+)\s*\n'
        r'Time: ([^\n]+)\s*\n'
        r'Exit Reason: ([^\n]+)\s*\n'
        r'P&L: \$([-\d,.]+)',
        content,
        re.IGNORECASE
    )

    # Index exits by trade ID
    exits_by_id = {}
    for ex in exits_raw:
        exits_by_id[int(ex[0])] = ex

    # Build trades list
    trades = []
    skipped = 0
    for entry in entries:
        trade_id = int(entry[0])
        entry_time = datetime.strptime(entry[1], '%Y-%m-%d %H:%M:%S')
        spread_val = float(entry[5])
        forecast_val = float(entry[6])

        trade = {
            'id': trade_id,
            'datetime': entry_time,
            'direction': entry[2],
            'entry_price': float(entry[3]),
            'size': int(entry[4]),
            'spread': spread_val,
            'abs_spread': abs(spread_val),
            'forecast': forecast_val,
            'abs_forecast': abs(forecast_val),
            'atr_b': float(entry[7]),
            'hour': entry_time.hour,
            'day_of_week': entry_time.weekday(),
            'year': entry_time.year,
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
            trade['duration_h'] = (trade['exit_time'] - trade['datetime']).total_seconds() / 3600
            trade['win'] = trade['pnl'] > 0
        trades.append(trade)

    if skipped:
        print(f'  (Skipped {skipped} incomplete trades with N/A exit)')

    # Parse configuration
    config = parse_config_header(content)

    closed = [t for t in trades if 'pnl' in t]
    return closed, config


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
# VEGA-SPECIFIC ANALYSIS FUNCTIONS
# =============================================================================

def print_config(config: Dict):
    """Print parsed configuration."""
    print_section('CONFIGURATION (from log header)')
    if not config:
        print("No configuration found")
        return

    if 'sma_period' in config:
        print(f"Z-score:      SMA={config['sma_period']}, ATR={config['atr_period']}")
    if 'dead_zone' in config:
        print(f"Dead Zone:    {config['dead_zone']}")
    if 'holding_hours' in config:
        print(f"Holding:      {config['holding_hours']}h")
    if 'session_start' in config:
        print(f"Session:      {config['session_start']:02d}:00-{config['session_end']:02d}:00 UTC")
    if config.get('protective_atr_mult') is not None:
        print(f"Prot. Stop:   {config['protective_atr_mult']}x ATR")
    else:
        print(f"Prot. Stop:   OFF")
    if 'risk_pct' in config:
        print(f"Risk:         {config['risk_pct']}%")
    if 'allowed_hours' in config:
        print(f"Time Filter:  {config['allowed_hours']}")
    if 'allowed_days' in config:
        print(f"Day Filter:   {config['allowed_days']}")


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

    # Date range
    dates = sorted([t['datetime'] for t in trades])
    print(f'\nDate Range:       {dates[0]} to {dates[-1]}')

    # Direction distribution
    longs = [t for t in trades if t['direction'] == 'LONG']
    shorts = [t for t in trades if t['direction'] == 'SHORT']
    print(f'\nLONG trades:      {len(longs)} ({len(longs)/len(trades)*100:.0f}%)')
    print(f'SHORT trades:     {len(shorts)} ({len(shorts)/len(trades)*100:.0f}%)')

    # Spread stats
    spreads = [t['spread'] for t in trades]
    print(f'\nSpread Range:     {min(spreads):.4f} to {max(spreads):.4f}')
    print(f'Spread Avg:       {sum(spreads)/len(spreads):.4f}')

    # Forecast stats
    forecasts = [t['abs_forecast'] for t in trades]
    print(f'\n|Forecast| Range:  {min(forecasts):.1f} to {max(forecasts):.1f}')
    print(f'|Forecast| Avg:    {sum(forecasts)/len(forecasts):.1f}')

    # ATR stats
    atrs = [t['atr_b'] for t in trades]
    print(f'\nATR(B) Range:     {min(atrs):.2f} to {max(atrs):.2f}')
    print(f'ATR(B) Avg:       {sum(atrs)/len(atrs):.2f}')

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


def analyze_by_spread(trades: List[Dict]):
    """Analyze performance by absolute spread ranges (signal trigger level)."""
    print_section('ANALYSIS BY |SPREAD| (z-score divergence)')
    spreads = [t['abs_spread'] for t in trades]
    ranges = _auto_ranges(spreads, num_bins=10)
    analyze_by_range(trades, lambda t: t['abs_spread'], ranges,
                     '|Spread|', decimals=2)


def analyze_by_forecast(trades: List[Dict]):
    """Analyze by absolute forecast (signal strength).
    
    Higher |forecast| = stronger signal = larger position.
    This reveals the minimum forecast threshold for profitable trades.
    """
    print_section('ANALYSIS BY |FORECAST| (signal strength)')
    forecasts = [t['abs_forecast'] for t in trades]
    ranges = _auto_ranges(forecasts, num_bins=8)
    analyze_by_range(trades, lambda t: t['abs_forecast'], ranges,
                     '|Forecast|', decimals=1)


def analyze_by_atr(trades: List[Dict]):
    """Analyze by ATR(B) ranges (volatility of target index)."""
    print_section('ANALYSIS BY ATR(B) (target volatility)')
    atrs = [t['atr_b'] for t in trades]
    ranges = _auto_ranges(atrs, num_bins=8)
    # Determine decimals from data magnitude
    decimals = 2 if max(atrs) >= 1 else 4
    analyze_by_range(trades, lambda t: t['atr_b'], ranges,
                     'ATR(B)', decimals=decimals)


def analyze_by_direction(trades: List[Dict]):
    """Analyze LONG vs SHORT performance."""
    print_section('ANALYSIS BY DIRECTION')
    analyze_by_group(
        trades, lambda t: t['direction'], 'Direction')


def analyze_by_hour(trades: List[Dict]):
    """Analyze by entry hour."""
    print_section('ANALYSIS BY ENTRY HOUR (UTC)')
    analyze_by_group(
        trades, lambda t: t['hour'], 'Hour',
        lambda h: f'{h:02d}:00')


def analyze_by_day(trades: List[Dict]):
    """Analyze by day of week."""
    print_section('ANALYSIS BY DAY OF WEEK')
    dow_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    analyze_by_group(
        trades, lambda t: t['day_of_week'], 'Day',
        lambda d: dow_names[d])


def analyze_by_year(trades: List[Dict]):
    """Analyze by year for stability check."""
    print_section('ANALYSIS BY YEAR')
    analyze_by_group(
        trades, lambda t: t['year'], 'Year', str)


def analyze_by_exit_reason(trades: List[Dict]):
    """Analyze by exit reason distribution."""
    print_section('ANALYSIS BY EXIT REASON')
    analyze_by_group(
        trades, lambda t: t.get('exit_reason', 'UNKNOWN'),
        'Exit Reason')


def analyze_by_size(trades: List[Dict]):
    """Analyze by position size (contracts)."""
    print_section('ANALYSIS BY SIZE (contracts)')
    analyze_by_group(
        trades, lambda t: t['size'], 'Size',
        lambda s: f'{s} contracts')


def analyze_spread_vs_forecast_matrix(trades: List[Dict]):
    """Cross-analysis: spread quintiles x forecast quintiles.
    
    This is the most important VEGA optimization table.
    Shows which spread+forecast combinations are profitable.
    """
    print_section('SPREAD x FORECAST MATRIX (quintiles)')

    # Compute quintile thresholds
    abs_spreads = sorted([t['abs_spread'] for t in trades])
    abs_forecasts = sorted([t['abs_forecast'] for t in trades])
    n = len(trades)

    if n < 25:
        print('Not enough trades for matrix analysis (need 25+)')
        return

    spread_q = [abs_spreads[int(n * p)] for p in [0.2, 0.4, 0.6, 0.8]]
    fcast_q = [abs_forecasts[int(n * p)] for p in [0.2, 0.4, 0.6, 0.8]]

    spread_bins = [
        (0, spread_q[0]), (spread_q[0], spread_q[1]),
        (spread_q[1], spread_q[2]), (spread_q[2], spread_q[3]),
        (spread_q[3], float('inf'))
    ]
    fcast_bins = [
        (0, fcast_q[0]), (fcast_q[0], fcast_q[1]),
        (fcast_q[1], fcast_q[2]), (fcast_q[2], fcast_q[3]),
        (fcast_q[3], float('inf'))
    ]

    # Header
    header = f'{"Spread\\Fcast":>14}'
    for lo, hi in fcast_bins:
        hi_str = f'{hi:.1f}' if hi < 1000 else 'MAX'
        header += f' | {lo:.1f}-{hi_str:>4}'
    print(header)
    print('-' * len(header))

    for s_lo, s_hi in spread_bins:
        s_hi_str = f'{s_hi:.2f}' if s_hi < 1000 else 'MAX'
        row = f'{s_lo:.2f}-{s_hi_str:>5}'
        for f_lo, f_hi in fcast_bins:
            cell = [t for t in trades
                    if s_lo <= t['abs_spread'] < s_hi
                    and f_lo <= t['abs_forecast'] < f_hi]
            if cell:
                m = calculate_metrics(cell)
                pf = format_pf(m['pf'])
                row += f' | {m["n"]:3d} PF={pf:>4}'
            else:
                row += f' |    {"---":>8}'
        print(f' {row}')

    # Best cell
    best_pf, best_cell_label = 0, ''
    for s_lo, s_hi in spread_bins:
        for f_lo, f_hi in fcast_bins:
            cell = [t for t in trades
                    if s_lo <= t['abs_spread'] < s_hi
                    and f_lo <= t['abs_forecast'] < f_hi]
            if cell and len(cell) >= MIN_TRADES_FOR_BEST:
                m = calculate_metrics(cell)
                if m['pf'] > best_pf:
                    best_pf = m['pf']
                    s_str = f'{s_lo:.2f}-{s_hi:.2f}' if s_hi < 1000 else f'{s_lo:.2f}+'
                    f_str = f'{f_lo:.1f}-{f_hi:.1f}' if f_hi < 1000 else f'{f_lo:.1f}+'
                    best_cell_label = f'|Spread|={s_str}, |Fcast|={f_str}'
    if best_cell_label:
        print(f'\n >> Best cell: {best_cell_label} (PF={format_pf(best_pf)})')


def analyze_dead_zone_sweep(trades: List[Dict], config: Dict):
    """Sweep min_forecast_entry to find optimal dead zone.
    
    Since forecast = clip(spread/dead_zone * 20, -20, +20),
    filtering by |forecast| >= threshold is equivalent to
    raising the effective dead zone.
    """
    print_section('DEAD ZONE EQUIVALENT SWEEP (min |forecast| filter)')
    current_dz = config.get('dead_zone', 1.0)
    print(f'Config dead_zone = {current_dz}\n')

    thresholds = [1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 18, 20]

    print(f' {"Min |Fcast|":>12} | {"Eff. DZ":>7} | Trades | Win%  | PF   '
          f'| Avg PnL  | Net P&L')
    print('-' * 75)

    best_pf, best_thresh = 0, 0
    for thresh in thresholds:
        # Effective dead zone = current_dz * (thresh / 20) / (1/20) = current_dz * thresh
        # Actually: forecast = spread/dz * 20, so |forecast| >= thresh <==> |spread| >= thresh/20 * dz
        eff_dz = current_dz * thresh / 20.0 if current_dz > 0 else thresh / 20.0
        filtered = [t for t in trades if t['abs_forecast'] >= thresh]
        if not filtered:
            continue
        m = calculate_metrics(filtered)
        pf_str = format_pf(m['pf'])
        print(f' {">= " + str(thresh):>12} | {eff_dz:>7.2f} | {m["n"]:6d} | '
              f'{m["wr"]:4.0f}% | {pf_str:>4} | ${m["avg_pnl"]:>+8.0f} '
              f'| ${m["net_pnl"]:>+10,.0f}')
        if m['pf'] > best_pf and m['n'] >= MIN_TRADES_FOR_BEST:
            best_pf = m['pf']
            best_thresh = thresh

    if best_thresh:
        print(f'\n >> Optimal: min |forecast| >= {best_thresh} '
              f'(PF={format_pf(best_pf)})')
        print(f'    To implement: set min_forecast_entry={best_thresh} in config')


def analyze_holding_quality(trades: List[Dict]):
    """Analyze whether trades that exit via TIME_EXIT are profitable
    vs those hitting protective stop. Shows if holding period is optimal."""
    print_section('HOLDING QUALITY (time exit vs stop)')
    
    time_exits = [t for t in trades if t.get('exit_reason') == 'TIME_EXIT']
    stop_exits = [t for t in trades if t.get('exit_reason') == 'PROT_STOP']
    other_exits = [t for t in trades
                   if t.get('exit_reason') not in ('TIME_EXIT', 'PROT_STOP', None)]

    for label, group in [('TIME_EXIT', time_exits),
                         ('PROT_STOP', stop_exits),
                         ('OTHER', other_exits)]:
        if group:
            m = calculate_metrics(group)
            pf_str = format_pf(m['pf'])
            print(f' {label:12} | n={m["n"]:5d} | WR={m["wr"]:.0f}% | '
                  f'PF={pf_str:>4} | Avg=${m["avg_pnl"]:+.0f} | '
                  f'Net=${m["net_pnl"]:+,.0f}')

    # Time exit P&L distribution by duration
    if time_exits and 'duration_h' in time_exits[0]:
        print(f'\n  Duration of TIME_EXIT trades:')
        durations = [t['duration_h'] for t in time_exits]
        dur_ranges = _auto_ranges(durations, num_bins=6)
        analyze_by_range(time_exits, lambda t: t['duration_h'],
                         dur_ranges, 'Duration (h)', decimals=0)


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Analyze VEGA strategy trade logs')
    parser.add_argument('logfile', nargs='?',
                        help='Specific log file to analyze')
    parser.add_argument('--all', action='store_true',
                        help='Analyze all VEGA logs combined')
    args = parser.parse_args()

    trades = []
    config = {}

    if args.all:
        logs = find_all_logs(LOG_DIR)
        if not logs:
            print(f'No VEGA logs found in {LOG_DIR}')
            return
        print(f'Analyzing {len(logs)} log files...')
        for log in logs:
            filepath = os.path.join(LOG_DIR, log)
            log_trades, log_config = parse_vega_log(filepath)
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
        trades, config = parse_vega_log(filepath)
    else:
        latest = find_latest_log(LOG_DIR)
        if not latest:
            print(f'No VEGA logs found in {LOG_DIR}')
            return
        filepath = os.path.join(LOG_DIR, latest)
        print(f'Analyzing latest: {latest}')
        trades, config = parse_vega_log(filepath)

    if not trades:
        print('No trades parsed from log file(s)')
        return

    print(f'\nTotal trades parsed: {len(trades)}')

    # Run all analyses
    print_config(config)
    print_summary(trades)
    analyze_by_direction(trades)
    analyze_by_spread(trades)
    analyze_by_forecast(trades)
    analyze_spread_vs_forecast_matrix(trades)
    analyze_dead_zone_sweep(trades, config)
    analyze_by_atr(trades)
    analyze_by_hour(trades)
    analyze_by_day(trades)
    analyze_by_year(trades)
    analyze_by_exit_reason(trades)
    analyze_holding_quality(trades)
    analyze_by_size(trades)

    print('\n' + '=' * 70)
    print('Analysis complete.')


if __name__ == '__main__':
    main()
