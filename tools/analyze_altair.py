"""
ALTAIR Strategy Trade Log Analyzer

Analyzes ALTAIR trade logs to evaluate the DTOSC momentum entry
with D1 regime filter on NDX stocks.

Key dimensions: DTOSC levels, Regime state, ATR(H1), entry hour,
day of week, holding duration, exit reason, yearly stability.

Usage:
    python analyze_altair.py                              # Latest ALTAIR log
    python analyze_altair.py ALTAIR_NVDA_trades_xxx.txt   # Specific log
    python analyze_altair.py --all                        # All ALTAIR logs combined
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
    print(f'\n{char * width}')
    print(f'{title}')
    print(char * width)


def format_pf(pf: float) -> str:
    return f'{pf:.2f}' if pf < 100 else 'INF'


def _auto_ranges(values, num_bins=8):
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

def find_latest_log(log_dir: str, prefix: str = 'ALTAIR_') -> Optional[str]:
    if not os.path.exists(log_dir):
        return None
    logs = [f for f in os.listdir(log_dir)
            if f.startswith(prefix) and f.endswith('.txt')]
    if not logs:
        return None
    logs.sort(key=lambda f: os.path.getmtime(os.path.join(log_dir, f)),
              reverse=True)
    return logs[0]


def find_all_logs(log_dir: str, prefix: str = 'ALTAIR_') -> List[str]:
    if not os.path.exists(log_dir):
        return []
    return sorted([f for f in os.listdir(log_dir)
                   if f.startswith(prefix) and f.endswith('.txt')])


def parse_config_header(content: str) -> Dict:
    config = {}

    match = re.search(
        r'DTOSC: period=(\d+), smooth_k=(\d+), smooth_d=(\d+), signal=(\d+)',
        content)
    if match:
        config['dtosc_period'] = int(match.group(1))
        config['dtosc_smooth_k'] = int(match.group(2))
        config['dtosc_smooth_d'] = int(match.group(3))
        config['dtosc_signal'] = int(match.group(4))

    match = re.search(r'Oversold/Overbought: (\d+) / (\d+)', content)
    if match:
        config['dtosc_os'] = int(match.group(1))
        config['dtosc_ob'] = int(match.group(2))

    match = re.search(r'Regime: (.+)', content)
    if match:
        config['regime'] = match.group(1).strip()

    match = re.search(r'Session: (\d{2}):00-(\d{2}):00 UTC', content)
    if match:
        config['session_start'] = int(match.group(1))
        config['session_end'] = int(match.group(2))

    match = re.search(r'SL: ([\d.]+)x ATR \| TP: ([\d.]+)x ATR', content)
    if match:
        config['sl_atr_mult'] = float(match.group(1))
        config['tp_atr_mult'] = float(match.group(2))

    match = re.search(r'Max Holding: (\d+) bars', content)
    if match:
        config['max_holding_bars'] = int(match.group(1))

    match = re.search(r'Risk: ([\d.]+)%', content)
    if match:
        config['risk_pct'] = float(match.group(1))

    match = re.search(r'Asset: (\w+)', content)
    if match:
        config['asset'] = match.group(1)

    match = re.search(r"Allowed Days: \[([^\]]+)\]", content)
    if match:
        config['allowed_days'] = match.group(1)

    return config


def parse_altair_log(filepath: str) -> Tuple[List[Dict], Dict]:
    """
    Parse ALTAIR trade log file.

    Expected format:
        ENTRY #N
        Time: YYYY-MM-DD HH:MM:SS
        Direction: LONG
        Asset: TICKER
        Entry Price: X.XX
        Size: N shares
        ATR(H1): X.XX
        DTOSC Fast: X.X
        DTOSC Slow: X.X
        Regime: STATE (Mom12M=+X.X%, Mom63d=+X.X%, ATR_ratio=X.XX)
        Stop Loss: X.XX
        Take Profit: X.XX

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
        r'Direction: (LONG|SHORT)\s*\n'
        r'Asset: (\w+)\s*\n'
        r'Entry Price: ([\d.]+)\s*\n'
        r'Size: (\d+) shares\s*\n'
        r'ATR\(H1\): ([\d.]+)\s*\n'
        r'DTOSC Fast: ([\d.]+)\s*\n'
        r'DTOSC Slow: ([\d.]+)\s*\n'
        r'Regime: (\S+) \(Mom12M=([-+\d.]+)%, Mom63d=([-+\d.]+)%, ATR_ratio=([\d.]+)\)\s*\n'
        r'Stop Loss: ([\d.]+)\s*\n'
        r'Take Profit: ([\d.]+)',
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

    exits_by_id = {}
    for ex in exits_raw:
        exits_by_id[int(ex[0])] = ex

    trades = []
    skipped = 0
    for entry in entries:
        trade_id = int(entry[0])
        entry_time = datetime.strptime(entry[1], '%Y-%m-%d %H:%M:%S')

        trade = {
            'id': trade_id,
            'datetime': entry_time,
            'direction': entry[2],
            'asset': entry[3],
            'entry_price': float(entry[4]),
            'size': int(entry[5]),
            'atr_h1': float(entry[6]),
            'dtosc_fast': float(entry[7]),
            'dtosc_slow': float(entry[8]),
            'regime': entry[9],
            'mom12m': float(entry[10]),
            'mom63d': float(entry[11]),
            'atr_ratio': float(entry[12]),
            'stop_loss': float(entry[13]),
            'take_profit': float(entry[14]),
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
            trade['exit_time'] = datetime.strptime(
                exit_time_str, '%Y-%m-%d %H:%M:%S')
            trade['exit_reason'] = exit_reason
            trade['pnl'] = float(ex[3].replace(',', ''))
            trade['bars_held'] = int(ex[4])
            trade['duration_h'] = trade['bars_held']  # H1 bars ~ hours
            trade['win'] = trade['pnl'] > 0
        trades.append(trade)

    if skipped:
        print(f'  (Skipped {skipped} incomplete trades with N/A exit)')

    config = parse_config_header(content)

    closed = [t for t in trades if 'pnl' in t]
    return closed, config


# =============================================================================
# METRICS
# =============================================================================

def calculate_metrics(trades: List[Dict]) -> Optional[Dict]:
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
# ALTAIR-SPECIFIC ANALYSIS FUNCTIONS
# =============================================================================

def print_config(config: Dict):
    print_section('CONFIGURATION (from log header)')
    if not config:
        print("No configuration found")
        return

    if 'dtosc_period' in config:
        print(f"DTOSC:        period={config['dtosc_period']}, "
              f"smooth_k={config['dtosc_smooth_k']}, "
              f"smooth_d={config['dtosc_smooth_d']}, "
              f"signal={config['dtosc_signal']}")
    if 'dtosc_os' in config:
        print(f"Levels:       OS={config['dtosc_os']}, OB={config['dtosc_ob']}")
    if 'regime' in config:
        print(f"Regime:       {config['regime']}")
    if 'sl_atr_mult' in config:
        print(f"SL/TP:        {config['sl_atr_mult']}x / {config['tp_atr_mult']}x ATR")
    if 'max_holding_bars' in config:
        print(f"Max Holding:  {config['max_holding_bars']} bars")
    if 'session_start' in config:
        print(f"Session:      {config['session_start']:02d}:00-{config['session_end']:02d}:00 UTC")
    if 'risk_pct' in config:
        print(f"Risk:         {config['risk_pct']}%")
    if 'asset' in config:
        print(f"Asset:        {config['asset']}")
    if 'allowed_days' in config:
        print(f"Days:         {config['allowed_days']}")


def print_summary(trades: List[Dict]):
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

    # Asset distribution
    assets = defaultdict(int)
    for t in trades:
        assets[t['asset']] += 1
    if len(assets) > 1:
        print(f'\nAssets:')
        for a in sorted(assets):
            print(f'  {a}: {assets[a]} trades')

    # ATR stats
    atrs = [t['atr_h1'] for t in trades]
    print(f'\nATR(H1) Range:    {min(atrs):.2f} to {max(atrs):.2f}')
    print(f'ATR(H1) Avg:      {sum(atrs)/len(atrs):.2f}')

    # DTOSC stats
    fasts = [t['dtosc_fast'] for t in trades]
    print(f'\nDTOSC Fast Range: {min(fasts):.1f} to {max(fasts):.1f}')
    print(f'DTOSC Fast Avg:   {sum(fasts)/len(fasts):.1f}')

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


def analyze_by_asset(trades: List[Dict]):
    print_section('ANALYSIS BY ASSET')
    print('  Per-stock performance breakdown.')
    analyze_by_group(trades, lambda t: t['asset'], 'Asset')


def analyze_by_regime(trades: List[Dict]):
    print_section('ANALYSIS BY REGIME STATE')
    print('  CALM_UP is the target regime. Other states should have few/no trades')
    print('  if regime filter is enabled.')
    analyze_by_group(trades, lambda t: t['regime'], 'Regime')


def analyze_by_atr(trades: List[Dict]):
    print_section('ANALYSIS BY ATR(H1) (entry volatility)')
    print('  ATR(H1) affects SL/TP distance and position size.')
    print('  Higher ATR = wider stops = smaller position = potentially larger moves.')
    atrs = [t['atr_h1'] for t in trades]
    ranges = _auto_ranges(atrs, num_bins=8)
    decimals = 2 if max(atrs) >= 1 else 4
    analyze_by_range(trades, lambda t: t['atr_h1'], ranges,
                     'ATR(H1)', decimals=decimals)


def analyze_by_dtosc_fast(trades: List[Dict]):
    print_section('ANALYSIS BY DTOSC FAST (entry level)')
    print('  DTOSC Fast value at entry. Should cluster near oversold zone.')
    print('  Higher = cross happened further from oversold = weaker signal.')
    fasts = [t['dtosc_fast'] for t in trades]
    ranges = _auto_ranges(fasts, num_bins=8)
    analyze_by_range(trades, lambda t: t['dtosc_fast'], ranges,
                     'DTOSC Fast', decimals=1)


def analyze_by_hour(trades: List[Dict]):
    print_section('ANALYSIS BY ENTRY HOUR (UTC)')
    print('  US stock market: 14:30 open, 21:00 close (UTC).')
    print('  Adjustable via allowed_hours.')
    dow_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    analyze_by_group(
        trades, lambda t: t['hour'], 'Hour',
        lambda h: f'{h:02d}:00')


def analyze_by_day(trades: List[Dict]):
    print_section('ANALYSIS BY DAY OF WEEK')
    dow_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    analyze_by_group(
        trades, lambda t: t['day_of_week'], 'Day',
        lambda d: dow_names[d])


def analyze_by_year(trades: List[Dict]):
    print_section('ANALYSIS BY YEAR')
    print('  CRITICAL: edge must be positive across most years.')
    analyze_by_group(trades, lambda t: t['year'], 'Year', str)


def analyze_by_exit_reason(trades: List[Dict]):
    print_section('ANALYSIS BY EXIT REASON')
    print('  PROT_STOP = stop loss hit. TP_EXIT = take profit reached.')
    print('  TIME_EXIT = max holding bars exceeded.')
    analyze_by_group(
        trades, lambda t: t.get('exit_reason', 'UNKNOWN'),
        'Exit Reason')


def analyze_by_size(trades: List[Dict]):
    print_section('ANALYSIS BY SIZE (shares)')
    sizes = [t['size'] for t in trades]
    ranges = _auto_ranges(sizes, num_bins=6)
    analyze_by_range(trades, lambda t: t['size'], ranges,
                     'Size (shares)', decimals=0)


def analyze_holding_duration(trades: List[Dict]):
    print_section('ANALYSIS BY HOLDING DURATION (bars/hours)')
    print('  Duration in H1 bars (approx. hours of market time).')
    has_bars = [t for t in trades if 'bars_held' in t]
    if not has_bars:
        print('  No duration data available.')
        return

    durations = [t['bars_held'] for t in has_bars]
    max_dur = max(durations)

    # Create bins
    bins = []
    if max_dur <= 24:
        bins = [(h, h + 4) for h in range(0, max_dur + 4, 4)]
    elif max_dur <= 120:
        bins = [(h, h + 12) for h in range(0, max_dur + 12, 12)]
    else:
        bins = [(h, h + 24) for h in range(0, min(max_dur + 24, 168), 24)]
        if max_dur > 168:
            bins.append((168, max_dur + 1))

    analyze_by_range(has_bars, lambda t: t['bars_held'], bins,
                     'Bars Held', decimals=0)


def analyze_dtosc_os_sweep(trades: List[Dict]):
    print_section('DTOSC OVERSOLD THRESHOLD SWEEP')
    print('  Simulates changing the oversold level for entry qualification.')
    print('  Each row filters to trades where DTOSC Fast was below threshold.')
    print('  Lower threshold = stricter filter = fewer but potentially better entries.')

    thresholds = [15, 20, 25, 30, 35, 40]

    print(f'\n {"OS Threshold":>14} | Trades | Win%  | PF   | Avg PnL  | Net P&L')
    print('-' * 70)

    for thresh in thresholds:
        # Trades where DTOSC fast at entry was below this threshold
        filtered = [t for t in trades if t['dtosc_fast'] <= thresh]
        if not filtered:
            continue
        m = calculate_metrics(filtered)
        pf_str = format_pf(m['pf'])
        print(f' {"<= " + str(thresh):>14} | {m["n"]:6d} | {m["wr"]:4.0f}% '
              f'| {pf_str:>4} | ${m["avg_pnl"]:>+8.0f} | ${m["net_pnl"]:>+10,.0f}')


def analyze_regime_comparison(trades: List[Dict]):
    print_section('REGIME ON vs OFF COMPARISON')
    print('  Compares CALM_UP trades vs all other regime states.')
    print('  If regime filter adds edge, CALM_UP PF >> non-CALM_UP PF.')

    calm_up = [t for t in trades if t['regime'] == 'CALM_UP']
    non_calm_up = [t for t in trades if t['regime'] != 'CALM_UP']

    for label, group in [('CALM_UP', calm_up),
                         ('Other regimes', non_calm_up)]:
        if group:
            m = calculate_metrics(group)
            pf_str = format_pf(m['pf'])
            print(f' {label:15} | n={m["n"]:5d} | WR={m["wr"]:.0f}% | '
                  f'PF={pf_str:>4} | Avg=${m["avg_pnl"]:+.0f} | '
                  f'Net=${m["net_pnl"]:+,.0f}')
        else:
            print(f' {label:15} | n=    0 | (no trades)')

    # ATR ratio sub-analysis
    if calm_up:
        print(f'\n  CALM_UP ATR ratio stats:')
        ratios = [t['atr_ratio'] for t in calm_up]
        print(f'    Range: {min(ratios):.2f} - {max(ratios):.2f}')
        print(f'    Avg:   {sum(ratios)/len(ratios):.2f}')

    # Mom12M sub-analysis
    if calm_up:
        print(f'\n  CALM_UP Mom12M stats:')
        moms = [t['mom12m'] for t in calm_up]
        print(f'    Range: {min(moms):+.1f}% to {max(moms):+.1f}%')
        print(f'    Avg:   {sum(moms)/len(moms):+.1f}%')


def analyze_by_atr_ratio(trades: List[Dict]):
    print_section('ANALYSIS BY ATR RATIO (regime volatility)')
    print('  ATR_ratio = ATR_D1 / SMA(ATR_D1, 252). Lower = calmer market.')
    ratios = [t['atr_ratio'] for t in trades]
    ranges = _auto_ranges(ratios, num_bins=6)
    analyze_by_range(trades, lambda t: t['atr_ratio'], ranges,
                     'ATR Ratio', decimals=2)


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Analyze ALTAIR strategy trade logs')
    parser.add_argument('logfile', nargs='?',
                        help='Specific log file to analyze')
    parser.add_argument('--all', action='store_true',
                        help='Analyze all ALTAIR logs combined')
    args = parser.parse_args()

    trades = []
    config = {}

    if args.all:
        logs = find_all_logs(LOG_DIR)
        if not logs:
            print(f'No ALTAIR logs found in {LOG_DIR}')
            return
        print(f'Analyzing {len(logs)} log files...')
        for log in logs:
            filepath = os.path.join(LOG_DIR, log)
            log_trades, log_config = parse_altair_log(filepath)
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
        trades, config = parse_altair_log(filepath)
    else:
        latest = find_latest_log(LOG_DIR)
        if not latest:
            print(f'No ALTAIR logs found in {LOG_DIR}')
            return
        filepath = os.path.join(LOG_DIR, latest)
        print(f'Analyzing latest: {latest}')
        trades, config = parse_altair_log(filepath)

    if not trades:
        print('No trades parsed from log file(s)')
        return

    print(f'\nTotal trades parsed: {len(trades)}')

    # Run all analyses
    print_config(config)
    print_summary(trades)
    analyze_by_asset(trades)
    analyze_by_regime(trades)
    analyze_regime_comparison(trades)
    analyze_by_atr_ratio(trades)
    analyze_by_dtosc_fast(trades)
    analyze_dtosc_os_sweep(trades)
    analyze_by_atr(trades)
    analyze_by_hour(trades)
    analyze_by_day(trades)
    analyze_by_year(trades)
    analyze_by_exit_reason(trades)
    analyze_holding_duration(trades)
    analyze_by_size(trades)

    print('\n' + '=' * 70)
    print('Analysis complete.')


if __name__ == '__main__':
    main()
