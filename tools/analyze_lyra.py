"""
LYRA Strategy Trade Log Analyzer

Analyzes LYRA trade logs to find optimal filters for short-selling
on index CFDs. Key dimensions: ATR(H1), entry hour, day of week,
exit reason, bars held, DTOSC level, yearly stability.

Usage:
    python tools/analyze_lyra.py                           # Analyze latest LYRA log
    python tools/analyze_lyra.py LYRA_NDX_trades_xxx.txt   # Analyze specific log
    python tools/analyze_lyra.py --all                     # Analyze all LYRA logs combined

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

def find_latest_log(log_dir: str, prefix: str = 'LYRA_') -> Optional[str]:
    """Find the most recent LYRA log file by modification time."""
    if not os.path.exists(log_dir):
        return None
    logs = [f for f in os.listdir(log_dir)
            if f.startswith(prefix) and '_trades_' in f and f.endswith('.txt')]
    if not logs:
        return None
    logs.sort(key=lambda f: os.path.getmtime(os.path.join(log_dir, f)),
              reverse=True)
    return logs[0]


def find_all_logs(log_dir: str, prefix: str = 'LYRA_') -> List[str]:
    """Find all LYRA log files."""
    if not os.path.exists(log_dir):
        return []
    return sorted([f for f in os.listdir(log_dir)
                   if f.startswith(prefix) and '_trades_' in f
                   and f.endswith('.txt')])


def parse_config_header(content: str) -> Dict:
    """Parse LYRA configuration header from trade log."""
    config = {}

    match = re.search(r'Asset: (\S+)', content)
    if match:
        config['asset'] = match.group(1)

    match = re.search(r'Allowed Regimes: (.+)', content)
    if match:
        config['allowed_regimes'] = match.group(1).strip()

    match = re.search(r'DTOSC OB: (\d+)', content)
    if match:
        config['dtosc_ob'] = int(match.group(1))

    match = re.search(r'SL: ([\d.]+)x ATR \(max ([\d.]+)x\)', content)
    if match:
        config['sl_atr_mult'] = float(match.group(1))
        config['max_sl_atr_mult'] = float(match.group(2))

    match = re.search(r'TP: ([\d.]+)x ATR', content)
    if match:
        config['tp_atr_mult'] = float(match.group(1))

    match = re.search(r'Max Holding: (\d+) bars', content)
    if match:
        config['max_holding_bars'] = int(match.group(1))

    match = re.search(r'Risk: ([\d.]+)%', content)
    if match:
        config['risk_pct'] = float(match.group(1))

    match = re.search(r'Time Filter: \[([^\]]+)\]', content)
    if match:
        config['allowed_hours'] = [int(h.strip()) for h in match.group(1).split(',')]

    match = re.search(r'Day Filter: \[([^\]]+)\]', content)
    if match:
        config['allowed_days'] = [int(d.strip()) for d in match.group(1).split(',')]

    match = re.search(r'Min ATR Entry: ([\d.]+)', content)
    if match:
        config['min_atr_entry'] = float(match.group(1))

    match = re.search(r'Max ATR Entry: ([\d.]+)', content)
    if match:
        config['max_atr_entry'] = float(match.group(1))

    match = re.search(r'Tr-1BL: (ON|OFF)', content)
    if match:
        config['use_tr1bl'] = match.group(1) == 'ON'

    match = re.search(r'Use Swing High SL: (True|False)', content)
    if match:
        config['use_swing_high_sl'] = match.group(1) == 'True'

    return config


def parse_lyra_log(filepath: str) -> Tuple[List[Dict], Dict]:
    """
    Parse LYRA trade log file.

    Expected format:
        ENTRY #N
        Time: YYYY-MM-DD HH:MM:SS
        Direction: SHORT
        Entry Price: X.XX
        Size: N
        ATR(H1): X.XX
        DTOSC: X.X/X.X
        Regime: VOLATILE_UP
        SL: X.XX
        TP: X.XX

        EXIT #N
        Time: YYYY-MM-DD HH:MM:SS
        Exit Reason: REASON
        P&L: $X.XX
        Bars Held: N
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Parse entries
    entries = re.findall(
        r'ENTRY #(\d+)\s*\n'
        r'Time: ([\d-]+ [\d:]+)\s*\n'
        r'Direction: (SHORT)\s*\n'
        r'Entry Price: ([\d.]+)\s*\n'
        r'Size: (\d+)\s*\n'
        r'ATR\(H1\): ([\d.]+)\s*\n'
        r'DTOSC: ([\d.]+)/([\d.]+)\s*\n'
        r'Regime: (\w+)\s*\n'
        r'SL: ([\d.]+)\s*\n'
        r'TP: ([\d.]+)',
        content,
        re.IGNORECASE
    )

    # Parse exits
    exits_raw = re.findall(
        r'EXIT #(\d+)\s*\n'
        r'Time: ([^\n]+)\s*\n'
        r'Exit Reason: ([^\n]+)\s*\n'
        r'P&L: \$([-\d,.]+)\s*\n'
        r'Bars Held: (\d+)',
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
        entry_price = float(entry[3])
        atr_h1 = float(entry[5])
        sl_level = float(entry[9])

        # SL distance (short: SL is above entry)
        sl_dist = sl_level - entry_price
        sl_atr_ratio = sl_dist / atr_h1 if atr_h1 > 0 else 0

        trade = {
            'id': trade_id,
            'datetime': entry_time,
            'direction': 'SHORT',
            'entry_price': entry_price,
            'size': int(entry[4]),
            'atr_h1': atr_h1,
            'dtosc_fast': float(entry[6]),
            'dtosc_slow': float(entry[7]),
            'regime': entry[8],
            'sl': sl_level,
            'tp': float(entry[10]),
            'sl_distance': sl_dist,
            'sl_atr_ratio': sl_atr_ratio,
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
            trade['bars_held'] = int(ex[4])
            trade['win'] = trade['pnl'] > 0
        else:
            skipped += 1
            continue

        trades.append(trade)

    if skipped:
        print(f'  (Skipped {skipped} incomplete trades without matching exit)')

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
# LYRA-SPECIFIC ANALYSIS FUNCTIONS
# =============================================================================

def print_config(config: Dict):
    """Print parsed configuration."""
    print_section('CONFIGURATION (from log header)')
    if not config:
        print("No configuration found in header")
        return

    if 'asset' in config:
        print(f"Asset:            {config['asset']}")
    if 'allowed_regimes' in config:
        print(f"Regimes:          {config['allowed_regimes']}")
    if 'dtosc_ob' in config:
        print(f"DTOSC OB:         {config['dtosc_ob']}")
    if 'sl_atr_mult' in config:
        print(f"SL:               {config['sl_atr_mult']}x ATR "
              f"(max {config.get('max_sl_atr_mult', '?')}x)")
    if 'tp_atr_mult' in config:
        print(f"TP:               {config['tp_atr_mult']}x ATR")
    if 'max_holding_bars' in config:
        print(f"Max Holding:      {config['max_holding_bars']} bars")
    if 'risk_pct' in config:
        print(f"Risk:             {config['risk_pct']}%")
    if 'allowed_hours' in config:
        print(f"Time Filter:      {config['allowed_hours']}")
    if 'allowed_days' in config:
        print(f"Day Filter:       {config['allowed_days']}")
    if 'min_atr_entry' in config:
        val = config['min_atr_entry']
        print(f"Min ATR Entry:    {val}" + (" (disabled)" if val == 0 else ""))
    if 'max_atr_entry' in config:
        val = config['max_atr_entry']
        print(f"Max ATR Entry:    {val}" + (" (disabled)" if val == 0 else ""))
    if 'use_tr1bl' in config:
        print(f"Tr-1BL:           {'ON' if config['use_tr1bl'] else 'OFF'}")
    if 'use_swing_high_sl' in config:
        print(f"Swing High SL:    {config['use_swing_high_sl']}")


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

    # ATR stats
    atrs = [t['atr_h1'] for t in trades]
    print(f'\nATR(H1) Range:    {min(atrs):.2f} to {max(atrs):.2f}')
    print(f'ATR(H1) Avg:      {sum(atrs)/len(atrs):.2f}')

    # SL distance stats
    sl_dists = [t['sl_distance'] for t in trades]
    print(f'\nSL Dist Range:    {min(sl_dists):.2f} to {max(sl_dists):.2f}')
    sl_ratios = [t['sl_atr_ratio'] for t in trades]
    print(f'SL/ATR Range:     {min(sl_ratios):.2f}x to {max(sl_ratios):.2f}x')

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


def analyze_by_atr(trades: List[Dict]):
    """Analyze performance by ATR(H1) ranges."""
    print_section('ANALYSIS BY ATR(H1) (entry volatility)')
    print('  ATR(H1) = 14-period ATR on H1 bars at moment of entry.')
    print('  High ATR = high volatility = bigger SL/TP distances.')
    print('  Adjustable via: min_atr_entry, max_atr_entry in settings.')
    print()
    atrs = [t['atr_h1'] for t in trades]
    ranges = _auto_ranges(atrs, num_bins=8)
    analyze_by_range(trades, lambda t: t['atr_h1'], ranges,
                     'ATR(H1)', decimals=1)


def analyze_atr_sweep(trades: List[Dict]):
    """Sweep min/max ATR entry to find optimal filter range.

    THE KEY VALIDATION TABLE for ATR filtering.
    Shows cumulative effect of raising min_atr_entry or lowering max_atr_entry.
    """
    print_section('ATR ENTRY SWEEP (cumulative min ATR filter)')
    print('  Each row is CUMULATIVE: ">= X" includes ALL trades with ATR(H1) >= X.')
    print('  Look for threshold where PF stabilizes above 1.10+ with enough trades.')
    print('  Adjustable via: min_atr_entry in settings.')
    print()

    atrs = sorted(set(int(t['atr_h1']) for t in trades))
    if not atrs:
        print('No ATR data')
        return

    # Generate thresholds from data percentiles
    all_atrs = sorted([t['atr_h1'] for t in trades])
    n = len(all_atrs)
    percentiles = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90]
    thresholds = sorted(set(
        round(all_atrs[min(int(n * p / 100), n - 1)], 0)
        for p in percentiles
    ))

    print(f' {"Min ATR":>10} | Trades | Win%  | PF   | Avg PnL  | Net P&L')
    print('-' * 70)

    best_pf, best_thresh = 0, 0
    for thresh in thresholds:
        filtered = [t for t in trades if t['atr_h1'] >= thresh]
        if not filtered:
            continue
        m = calculate_metrics(filtered)
        pf_str = format_pf(m['pf'])
        print(f' {">= " + str(int(thresh)):>10} | {m["n"]:6d} | '
              f'{m["wr"]:4.0f}% | {pf_str:>4} | ${m["avg_pnl"]:>+8.0f} '
              f'| ${m["net_pnl"]:>+10,.0f}')
        if m['pf'] > best_pf and m['n'] >= MIN_TRADES_FOR_BEST:
            best_pf = m['pf']
            best_thresh = thresh

    if best_thresh:
        print(f'\n >> Optimal min ATR: >= {int(best_thresh)} '
              f'(PF={format_pf(best_pf)})')

    # Max ATR sweep (inverse)
    print_section('ATR ENTRY SWEEP (cumulative max ATR filter)')
    print('  Each row is CUMULATIVE: "<= X" includes ALL trades with ATR(H1) <= X.')
    print('  Filters out extreme volatility entries.')
    print('  Adjustable via: max_atr_entry in settings.')
    print()

    thresholds_max = sorted(set(
        round(all_atrs[min(int(n * p / 100), n - 1)], 0)
        for p in [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    ))

    print(f' {"Max ATR":>10} | Trades | Win%  | PF   | Avg PnL  | Net P&L')
    print('-' * 70)

    best_pf2, best_thresh2 = 0, 0
    for thresh in thresholds_max:
        filtered = [t for t in trades if t['atr_h1'] <= thresh]
        if not filtered:
            continue
        m = calculate_metrics(filtered)
        pf_str = format_pf(m['pf'])
        print(f' {"<= " + str(int(thresh)):>10} | {m["n"]:6d} | '
              f'{m["wr"]:4.0f}% | {pf_str:>4} | ${m["avg_pnl"]:>+8.0f} '
              f'| ${m["net_pnl"]:>+10,.0f}')
        if m['pf'] > best_pf2 and m['n'] >= MIN_TRADES_FOR_BEST:
            best_pf2 = m['pf']
            best_thresh2 = thresh

    if best_thresh2:
        print(f'\n >> Optimal max ATR: <= {int(best_thresh2)} '
              f'(PF={format_pf(best_pf2)})')


def analyze_by_hour(trades: List[Dict]):
    """Analyze by entry hour."""
    print_section('ANALYSIS BY ENTRY HOUR (UTC)')
    print('  Entry hour of H1 bar when trade was opened.')
    print('  Adjustable via: allowed_hours in settings.')
    print()
    analyze_by_group(
        trades, lambda t: t['hour'], 'Hour',
        lambda h: f'{h:02d}:00')


def analyze_by_day(trades: List[Dict]):
    """Analyze by day of week."""
    print_section('ANALYSIS BY DAY OF WEEK')
    print('  Edge may vary by weekday due to positioning/flows.')
    print('  Adjustable via: allowed_days in settings (0=Mon .. 4=Fri).')
    print()
    dow_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    analyze_by_group(
        trades, lambda t: t['day_of_week'], 'Day',
        lambda d: dow_names[d])


def analyze_by_year(trades: List[Dict]):
    """Analyze by year for stability check."""
    print_section('ANALYSIS BY YEAR')
    print('  CRITICAL for validation: the edge must be positive in MOST years.')
    print('  If only 1-2 years carry all profit, the edge may be regime-dependent.')
    print()
    analyze_by_group(
        trades, lambda t: t['year'], 'Year', str)


def analyze_by_exit_reason(trades: List[Dict]):
    """Analyze by exit reason distribution."""
    print_section('ANALYSIS BY EXIT REASON')
    print('  PROT_STOP = swing high SL hit.  TP_EXIT = take profit reached.')
    print('  TIME_EXIT = max holding bars.  REGIME_EXIT = regime returned to CALM_UP.')
    print()
    analyze_by_group(
        trades, lambda t: t.get('exit_reason', 'UNKNOWN'),
        'Exit Reason')


def analyze_by_bars_held(trades: List[Dict]):
    """Analyze by bars held ranges."""
    print_section('ANALYSIS BY BARS HELD')
    print('  How many H1 bars the trade was open before exit.')
    print('  Adjustable via: max_holding_bars in settings.')
    print()
    bars = [t['bars_held'] for t in trades]
    max_bars = max(bars) if bars else 35
    # Create bins: 1-5, 6-10, 11-15, etc.
    step = 5
    ranges = [(i, min(i + step, max_bars + step))
              for i in range(0, max_bars + 1, step)]
    analyze_by_range(trades, lambda t: t['bars_held'], ranges,
                     'Bars Held', decimals=0)


def analyze_by_dtosc(trades: List[Dict]):
    """Analyze by DTOSC fast value at entry."""
    print_section('ANALYSIS BY DTOSC (fast at entry)')
    print('  DTOSC fast value when bearish cross signal fired.')
    print('  Higher values = stronger overbought reversal.')
    print('  Adjustable via: dtosc_ob (minimum OB level for signal).')
    print()
    dtosc_vals = [t['dtosc_fast'] for t in trades]
    ranges = _auto_ranges(dtosc_vals, num_bins=6)
    analyze_by_range(trades, lambda t: t['dtosc_fast'], ranges,
                     'DTOSC Fast', decimals=1)


def analyze_by_sl_atr(trades: List[Dict]):
    """Analyze by SL distance in ATR multiples."""
    print_section('ANALYSIS BY SL/ATR RATIO')
    print('  Stop loss distance as multiple of ATR(H1).')
    print('  Lower = tighter stop (more stops hit, but smaller losses).')
    print('  Higher = wider stop (fewer stops, but bigger losses when hit).')
    print('  Adjustable via: max_sl_atr_mult in settings.')
    print()
    ratios = [t['sl_atr_ratio'] for t in trades]
    ranges = _auto_ranges(ratios, num_bins=6)
    analyze_by_range(trades, lambda t: t['sl_atr_ratio'], ranges,
                     'SL/ATR', decimals=1)


def analyze_holding_quality(trades: List[Dict], config: Dict):
    """Analyze exit type quality and holding period distribution."""
    print_section('HOLDING QUALITY (exit type breakdown)')
    print('  Compares exit types by profitability.')
    print('  High TP_EXIT % = convergence captured early (good).')
    print('  REGIME_EXIT = market changed regime while in trade.')
    print()

    exit_types = ['TP_EXIT', 'TIME_EXIT', 'PROT_STOP', 'REGIME_EXIT']
    for label in exit_types:
        group = [t for t in trades if t.get('exit_reason') == label]
        if group:
            m = calculate_metrics(group)
            pf_str = format_pf(m['pf'])
            pct = len(group) / len(trades) * 100
            print(f' {label:12} | n={m["n"]:5d} ({pct:4.0f}%) | '
                  f'WR={m["wr"]:.0f}% | PF={pf_str:>4} | '
                  f'Avg=${m["avg_pnl"]:+.0f} | Net=${m["net_pnl"]:+,.0f}')

    other = [t for t in trades
             if t.get('exit_reason') not in exit_types]
    if other:
        m = calculate_metrics(other)
        pf_str = format_pf(m['pf'])
        pct = len(other) / len(trades) * 100
        print(f' {"OTHER":12} | n={m["n"]:5d} ({pct:4.0f}%) | '
              f'WR={m["wr"]:.0f}% | PF={pf_str:>4} | '
              f'Avg=${m["avg_pnl"]:+.0f} | Net=${m["net_pnl"]:+,.0f}')

    # Avg bars held by exit type
    print()
    for label in exit_types:
        group = [t for t in trades if t.get('exit_reason') == label]
        if group:
            avg_bars = sum(t['bars_held'] for t in group) / len(group)
            print(f'  {label:12} avg bars held: {avg_bars:.1f}')


def analyze_hour_x_day_matrix(trades: List[Dict]):
    """Cross-analysis: entry hour x day of week."""
    print_section('HOUR x DAY MATRIX')
    print('  Rows = entry hour, Columns = day of week.')
    print('  Useful to find specific hour+day combos with edge.')
    print()

    dow_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
    hours = sorted(set(t['hour'] for t in trades))

    header = f'{"Hour":>6}'
    for d in range(5):
        header += f' | {dow_names[d]:>11}'
    print(header)
    print('-' * len(header))

    for h in hours:
        row = f'{h:02d}:00 '
        for d in range(5):
            cell = [t for t in trades
                    if t['hour'] == h and t['day_of_week'] == d]
            if cell:
                m = calculate_metrics(cell)
                pf = format_pf(m['pf'])
                row += f' | {m["n"]:3d} PF={pf:>4}'
            else:
                row += f' |    {"---":>8}'
        print(f' {row}')


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Analyze LYRA strategy trade logs')
    parser.add_argument('logfile', nargs='?',
                        help='Specific log file to analyze')
    parser.add_argument('--all', action='store_true',
                        help='Analyze all LYRA logs combined')
    args = parser.parse_args()

    trades = []
    config = {}

    if args.all:
        logs = find_all_logs(LOG_DIR)
        if not logs:
            print(f'No LYRA logs found in {LOG_DIR}')
            return
        print(f'Analyzing {len(logs)} log files...')
        for log in logs:
            filepath = os.path.join(LOG_DIR, log)
            log_trades, log_config = parse_lyra_log(filepath)
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
        trades, config = parse_lyra_log(filepath)
    else:
        latest = find_latest_log(LOG_DIR)
        if not latest:
            print(f'No LYRA logs found in {LOG_DIR}')
            return
        filepath = os.path.join(LOG_DIR, latest)
        print(f'Analyzing latest: {latest}')
        trades, config = parse_lyra_log(filepath)

    if not trades:
        print('No trades parsed from log file(s)')
        return

    print(f'\nTotal trades parsed: {len(trades)}')

    # Run all analyses
    print_config(config)
    print_summary(trades)
    analyze_by_atr(trades)
    analyze_atr_sweep(trades)
    analyze_by_hour(trades)
    analyze_by_day(trades)
    analyze_hour_x_day_matrix(trades)
    analyze_by_year(trades)
    analyze_by_exit_reason(trades)
    analyze_by_bars_held(trades)
    analyze_by_dtosc(trades)
    analyze_by_sl_atr(trades)
    analyze_holding_quality(trades, config)

    print('\n' + '=' * 70)
    print('Analysis complete.')


if __name__ == '__main__':
    main()
