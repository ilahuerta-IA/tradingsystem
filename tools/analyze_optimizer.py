"""
Generic Optimizer JSON Analyzer

Analyzes optimizer output JSON files from any strategy.
Works with the standard JSON format produced by *_optimizer.py tools.

Usage:
    python tools/analyze_optimizer.py <json_path> [options]

Options:
    --top N             Show top N results (default: 10)
    --min-trades N      Minimum trades to include (default: 10)
    --min-pf X          Minimum Profit Factor (default: 1.0)
    --consistency X     Min PF per year to count as "consistent" (default: 0.95)
    --sort-by FIELD     Sort by: pf, sharpe, net_pnl, max_dd, wr, cagr (default: pf)
    --filter KEY=VAL    Filter by param value (e.g. --filter atr_sl_multiplier=1.5)
    --patterns          Show parameter pattern analysis
    --yearly            Show detailed yearly breakdown for top results
    --compare JSON2     Compare two JSON files side by side (IS vs OOS)
    --export CSV_PATH   Export top results to CSV

Examples:
    python tools/analyze_optimizer.py logs/LUYTEN_optimizer_20260316_075318.json
    python tools/analyze_optimizer.py logs/LUYTEN_optimizer_20260316_075318.json --top 20 --sort-by sharpe
    python tools/analyze_optimizer.py logs/IS.json --compare logs/OOS.json --top 10
"""
import sys
import os
import json
import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path


# =============================================================================
# DATA LOADING
# =============================================================================

def load_json(path):
    """Load and validate optimizer JSON."""
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    required = ['results', 'sweep_keys', 'total_combinations']
    for key in required:
        if key not in data:
            print("ERROR: JSON missing required key '%s'" % key)
            sys.exit(1)

    return data


def get_valid_results(data, min_trades=10):
    """Filter results: no errors, meets min trades."""
    valid = []
    for r in data['results']:
        if 'error' in r:
            continue
        if r.get('overall', {}).get('trades', 0) < min_trades:
            continue
        valid.append(r)
    return valid


# =============================================================================
# SORTING & FILTERING
# =============================================================================

SORT_FIELDS = {
    'pf': lambda r: r['overall'].get('pf') or 0,
    'sharpe': lambda r: r['overall'].get('sharpe', 0),
    'net_pnl': lambda r: r['overall'].get('net_pnl', 0),
    'max_dd': lambda r: -(r['overall'].get('max_dd_pct', 100)),  # lower is better
    'wr': lambda r: r['overall'].get('wr', 0),
    'cagr': lambda r: r['overall'].get('cagr_pct', 0),
}


def sort_results(results, sort_by='pf'):
    """Sort results by specified field, descending."""
    key_fn = SORT_FIELDS.get(sort_by)
    if not key_fn:
        print("ERROR: Unknown sort field '%s'. Use: %s" % (sort_by, ', '.join(SORT_FIELDS)))
        sys.exit(1)
    return sorted(results, key=key_fn, reverse=True)


def filter_results(results, filters):
    """Filter results by param key=value pairs."""
    if not filters:
        return results

    filtered = []
    for r in results:
        match = True
        for key, val in filters.items():
            param_val = r['params'].get(key)
            if param_val is None:
                match = False
                break
            # Compare as float if possible
            try:
                if float(param_val) != float(val):
                    match = False
                    break
            except (ValueError, TypeError):
                if str(param_val) != str(val):
                    match = False
                    break
        if match:
            filtered.append(r)
    return filtered


def filter_by_min_pf(results, min_pf):
    """Keep only results with overall PF >= min_pf."""
    return [r for r in results if (r['overall'].get('pf') or 0) >= min_pf]


# =============================================================================
# CONSISTENCY ANALYSIS
# =============================================================================

def count_consistent_years(result, threshold=0.95):
    """Count how many years have PF >= threshold (ignoring years with <5 trades)."""
    yearly = result.get('yearly', {})
    consistent = 0
    total_years = 0
    for y, yd in yearly.items():
        if yd.get('trades', 0) < 5:
            continue
        total_years += 1
        pf = yd.get('pf') or 0
        if pf >= threshold:
            consistent += 1
    return consistent, total_years


# =============================================================================
# DISPLAY
# =============================================================================

def fmt_pf(pf):
    if pf is None:
        return 'INF'
    return '%.2f' % pf if pf < 100 else 'INF'


def fmt_money(val):
    sign = '+' if val >= 0 else ''
    return '%s%s' % (sign, format(val, ',.0f'))


def print_header(data, path):
    """Print file metadata header."""
    print('\n' + '=' * 100)
    print('OPTIMIZER RESULTS ANALYSIS')
    print('=' * 100)
    print('File: %s' % path)
    print('Strategy: %s' % data.get('optimizer', 'Unknown'))
    print('Asset: %s' % data.get('asset', 'Unknown'))
    period = data.get('period', {})
    print('Period: %s to %s' % (period.get('from', '?'), period.get('to', '?')))
    print('Starting cash: $%s' % format(data.get('starting_cash', 0), ',.0f'))
    print('Sweep keys: %s' % ', '.join(data.get('sweep_keys', [])))
    print('Total combinations: %d' % data.get('total_combinations', 0))


def print_summary(results, total):
    """Print quick summary stats."""
    profitable = sum(1 for r in results if (r['overall'].get('pf') or 0) >= 1.0)
    print('\nValid results: %d / %d' % (len(results), total))
    print('Profitable (PF≥1.0): %d (%d%%)' % (profitable, profitable * 100 // max(len(results), 1)))

    if results:
        pfs = [(r['overall'].get('pf') or 0) for r in results]
        sharpes = [r['overall'].get('sharpe', 0) for r in results]
        print('PF range: %.2f — %.2f (median %.2f)' % (
            min(pfs), max(pfs), sorted(pfs)[len(pfs) // 2]))
        print('Sharpe range: %+.2f — %+.2f' % (min(sharpes), max(sharpes)))


def print_top_table(results, sweep_keys, top_n, consistency_threshold):
    """Print formatted top N results table."""
    top = results[:top_n]
    if not top:
        print('\nNo results to display.')
        return

    # Collect years across results
    all_years = set()
    for r in top:
        all_years.update(r.get('yearly', {}).keys())
    years = sorted(all_years)

    # Short names for params
    short_names = {
        'consolidation_bars': 'CBars',
        'bk_above_min_pips': 'BkAbv',
        'bk_body_min_pips': 'BkBdy',
        'atr_tp_multiplier': 'TP',
        'atr_sl_multiplier': 'SL',
    }

    print('\n--- TOP %d RESULTS ---\n' % min(top_n, len(top)))

    # Build header
    param_hdrs = [short_names.get(k, k[:6]) for k in sweep_keys]
    hdr = '%3s  ' % '#'
    hdr += '  '.join('%-6s' % h for h in param_hdrs)
    hdr += '  %5s %5s %6s %5s %6s %10s  %s' % (
        'Trds', 'WR%', 'PF', 'DD%', 'Shrpe', 'Net PnL', 'Consist')

    if years:
        for y in years:
            hdr += '  | %s' % y

    print(hdr)
    print('-' * len(hdr))

    for i, r in enumerate(top, 1):
        o = r['overall']
        cons, total_y = count_consistent_years(r, consistency_threshold)

        line = '%3d  ' % i
        line += '  '.join('%-6s' % r['params'].get(k, '?') for k in sweep_keys)
        line += '  %5d %4.1f%% %6s %4.1f%% %+5.2f %10s  %d/%d yr' % (
            o['trades'], o['wr'], fmt_pf(o.get('pf')),
            o['max_dd_pct'], o['sharpe'],
            fmt_money(o['net_pnl']),
            cons, total_y)

        if years:
            for y in years:
                yd = r.get('yearly', {}).get(y)
                if yd:
                    line += '  | %s' % fmt_pf(yd.get('pf'))
                else:
                    line += '  |  -  '

        print(line)


def print_yearly_detail(results, sweep_keys, top_n):
    """Print detailed yearly breakdown for top results."""
    top = results[:top_n]
    if not top:
        return

    print('\n--- YEARLY DETAIL (Top %d) ---' % min(top_n, len(top)))

    for i, r in enumerate(top, 1):
        params_str = ', '.join('%s=%s' % (k, r['params'].get(k)) for k in sweep_keys)
        o = r['overall']
        print('\n#%d: %s  |  PF=%s, Sharpe=%+.2f, Net=%s' % (
            i, params_str, fmt_pf(o.get('pf')), o['sharpe'], fmt_money(o['net_pnl'])))

        yearly = r.get('yearly', {})
        if not yearly:
            print('  No yearly data.')
            continue

        print('  %6s  %5s  %5s  %6s  %10s' % ('Year', 'Trds', 'WR%', 'PF', 'PnL'))
        for y in sorted(yearly.keys()):
            yd = yearly[y]
            print('  %6s  %5d  %4.1f%%  %6s  %10s' % (
                y, yd['trades'], yd['wr'], fmt_pf(yd.get('pf')),
                fmt_money(yd['pnl'])))


# =============================================================================
# PATTERN ANALYSIS
# =============================================================================

def analyze_patterns(results, sweep_keys, top_n=20):
    """Analyze which parameter values appear most in top results."""
    top = results[:top_n]
    if not top:
        return

    print('\n--- PARAMETER PATTERNS (Top %d) ---\n' % len(top))

    for key in sweep_keys:
        counter = Counter()
        pf_by_val = defaultdict(list)

        for r in top:
            val = r['params'].get(key)
            counter[val] += 1
            pf_by_val[val].append(r['overall'].get('pf') or 0)

        short = {
            'consolidation_bars': 'CBars',
            'bk_above_min_pips': 'BkAbv',
            'bk_body_min_pips': 'BkBdy',
            'atr_tp_multiplier': 'TP',
            'atr_sl_multiplier': 'SL',
        }.get(key, key)

        print('%s:' % short)
        for val, count in counter.most_common():
            avg_pf = sum(pf_by_val[val]) / len(pf_by_val[val])
            print('  %s = %-8s  appears %2d/%d times  (avg PF=%.2f)' % (
                short, val, count, len(top), avg_pf))
        print()

    # Also show all-results stats for context
    print('--- FULL POPULATION STATS (All %d valid) ---\n' % len(results))
    for key in sweep_keys:
        pf_by_val = defaultdict(list)
        for r in results:
            val = r['params'].get(key)
            pf_by_val[val].append(r['overall'].get('pf') or 0)

        short = {
            'consolidation_bars': 'CBars',
            'bk_above_min_pips': 'BkAbv',
            'bk_body_min_pips': 'BkBdy',
            'atr_tp_multiplier': 'TP',
            'atr_sl_multiplier': 'SL',
        }.get(key, key)

        print('%s:' % short)
        for val in sorted(pf_by_val.keys()):
            pfs = pf_by_val[val]
            avg_pf = sum(pfs) / len(pfs)
            profitable = sum(1 for p in pfs if p >= 1.0)
            print('  %s = %-8s  n=%3d  avg PF=%.2f  profitable=%d/%d (%d%%)' % (
                short, val, len(pfs), avg_pf,
                profitable, len(pfs), profitable * 100 // max(len(pfs), 1)))
        print()


# =============================================================================
# COMPARISON (IS vs OOS)
# =============================================================================

def compare_results(is_data, oos_data, sweep_keys, top_n):
    """Compare IS and OOS results side by side for matching param combos."""
    print('\n' + '=' * 100)
    print('IS vs OOS COMPARISON')
    print('=' * 100)
    print('IS:  %s to %s' % (
        is_data.get('period', {}).get('from', '?'),
        is_data.get('period', {}).get('to', '?')))
    print('OOS: %s to %s' % (
        oos_data.get('period', {}).get('from', '?'),
        oos_data.get('period', {}).get('to', '?')))

    # Build OOS lookup by param tuple
    oos_lookup = {}
    for r in oos_data['results']:
        if 'error' in r:
            continue
        key = tuple(r['params'].get(k) for k in sweep_keys)
        oos_lookup[key] = r

    # Get IS top N (already sorted)
    is_results = get_valid_results(is_data)
    is_results = sort_results(is_results, 'pf')
    top = is_results[:top_n]

    short_names = {
        'consolidation_bars': 'CBars',
        'bk_above_min_pips': 'BkAbv',
        'bk_body_min_pips': 'BkBdy',
        'atr_tp_multiplier': 'TP',
        'atr_sl_multiplier': 'SL',
    }
    param_hdrs = [short_names.get(k, k[:6]) for k in sweep_keys]

    print('\n%3s  %s  |  %-28s  |  %-28s  | %s' % (
        '#',
        '  '.join('%-6s' % h for h in param_hdrs),
        'IN-SAMPLE', 'OUT-OF-SAMPLE', 'Delta'))
    print('     %s  |  %5s %6s %6s %10s  |  %5s %6s %6s %10s  | %s' % (
        '      ' * len(param_hdrs),
        'Trds', 'PF', 'Shrpe', 'Net PnL',
        'Trds', 'PF', 'Shrpe', 'Net PnL',
        'PF Δ'))
    print('-' * 130)

    robust_count = 0
    for i, is_r in enumerate(top, 1):
        key = tuple(is_r['params'].get(k) for k in sweep_keys)
        oos_r = oos_lookup.get(key)

        params_str = '  '.join('%-6s' % is_r['params'].get(k, '?') for k in sweep_keys)
        is_o = is_r['overall']

        if oos_r and 'error' not in oos_r:
            oos_o = oos_r['overall']
            pf_delta = (oos_o.get('pf') or 0) - (is_o.get('pf') or 0)
            is_robust = (oos_o.get('pf') or 0) >= 1.0

            if is_robust:
                robust_count += 1

            marker = ' ✓' if is_robust else ' ✗'

            print('%3d  %s  |  %5d %6s %+5.2f %10s  |  %5d %6s %+5.2f %10s  | %+.2f%s' % (
                i, params_str,
                is_o['trades'], fmt_pf(is_o.get('pf')), is_o['sharpe'],
                fmt_money(is_o['net_pnl']),
                oos_o['trades'], fmt_pf(oos_o.get('pf')), oos_o['sharpe'],
                fmt_money(oos_o['net_pnl']),
                pf_delta, marker))

            # Yearly detail for OOS
            oos_yearly = oos_r.get('yearly', {})
            if oos_yearly:
                yr_parts = []
                for y in sorted(oos_yearly.keys()):
                    yd = oos_yearly[y]
                    yr_parts.append('%s: PF=%s T=%d %s' % (
                        y, fmt_pf(yd.get('pf')), yd['trades'],
                        fmt_money(yd['pnl'])))
                print('     %s  OOS yearly: %s' % (' ' * (7 * len(sweep_keys)), '  |  '.join(yr_parts)))
        else:
            print('%3d  %s  |  %5d %6s %+5.2f %10s  |  %28s  |' % (
                i, params_str,
                is_o['trades'], fmt_pf(is_o.get('pf')), is_o['sharpe'],
                fmt_money(is_o['net_pnl']),
                '--- NO OOS DATA ---'))

    print('\n' + '=' * 100)
    print('ROBUSTNESS: %d / %d top IS combos remain profitable OOS (PF≥1.0)' % (
        robust_count, len(top)))
    if top:
        print('Survival rate: %d%%' % (robust_count * 100 // len(top)))
    print('=' * 100)


# =============================================================================
# CSV EXPORT
# =============================================================================

def export_csv(results, sweep_keys, csv_path, top_n):
    """Export top results to CSV."""
    top = results[:top_n]
    if not top:
        print('No results to export.')
        return

    headers = list(sweep_keys) + [
        'trades', 'wr', 'pf', 'max_dd_pct', 'sharpe', 'cagr_pct',
        'net_pnl', 'gross_profit', 'gross_loss',
    ]

    # Add year columns
    all_years = set()
    for r in top:
        all_years.update(r.get('yearly', {}).keys())
    years = sorted(all_years)
    for y in years:
        headers.extend(['%s_trades' % y, '%s_pf' % y, '%s_pnl' % y])

    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(headers)

        for r in top:
            o = r['overall']
            row = [r['params'].get(k, '') for k in sweep_keys]
            row += [
                o['trades'], o['wr'], o.get('pf'), o['max_dd_pct'],
                o['sharpe'], o['cagr_pct'], o['net_pnl'],
                o['gross_profit'], o['gross_loss'],
            ]
            for y in years:
                yd = r.get('yearly', {}).get(y, {})
                row += [yd.get('trades', 0), yd.get('pf'), yd.get('pnl', 0)]
            writer.writerow(row)

    print('\nExported %d results to: %s' % (len(top), csv_path))


# =============================================================================
# MAIN
# =============================================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description='Analyze optimizer JSON results (any strategy)')
    parser.add_argument('json_path', help='Path to optimizer JSON file')
    parser.add_argument('--top', type=int, default=10, help='Top N results (default: 10)')
    parser.add_argument('--min-trades', type=int, default=10, help='Min trades filter (default: 10)')
    parser.add_argument('--min-pf', type=float, default=0.0, help='Min PF filter (default: 0 = all)')
    parser.add_argument('--consistency', type=float, default=0.95, help='Min PF/year for consistency (default: 0.95)')
    parser.add_argument('--sort-by', default='pf', choices=list(SORT_FIELDS.keys()), help='Sort field (default: pf)')
    parser.add_argument('--filter', action='append', dest='filters', help='Filter: KEY=VALUE (repeatable)')
    parser.add_argument('--patterns', action='store_true', help='Show parameter pattern analysis')
    parser.add_argument('--yearly', action='store_true', help='Show yearly detail for top results')
    parser.add_argument('--compare', metavar='OOS_JSON', help='Compare with OOS JSON file')
    parser.add_argument('--export', metavar='CSV_PATH', help='Export top results to CSV')
    return parser.parse_args()


def main():
    args = parse_args()

    # Load primary JSON
    data = load_json(args.json_path)
    sweep_keys = data['sweep_keys']

    # Parse filters
    param_filters = {}
    if args.filters:
        for f in args.filters:
            if '=' not in f:
                print("ERROR: Filter must be KEY=VALUE, got: '%s'" % f)
                sys.exit(1)
            k, v = f.split('=', 1)
            param_filters[k] = v

    # If compare mode, delegate to comparison
    if args.compare:
        oos_data = load_json(args.compare)
        compare_results(data, oos_data, sweep_keys, args.top)
        return

    # Standard analysis
    print_header(data, args.json_path)

    results = get_valid_results(data, args.min_trades)
    results = filter_results(results, param_filters)

    if args.min_pf > 0:
        results = filter_by_min_pf(results, args.min_pf)

    results = sort_results(results, args.sort_by)

    print_summary(results, data['total_combinations'])
    print_top_table(results, sweep_keys, args.top, args.consistency)

    if args.yearly:
        print_yearly_detail(results, sweep_keys, args.top)

    if args.patterns:
        analyze_patterns(results, sweep_keys, min(args.top * 2, len(results)))

    if args.export:
        export_csv(results, sweep_keys, args.export, args.top)


if __name__ == '__main__':
    main()
