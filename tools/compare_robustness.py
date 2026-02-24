"""
Robustness Comparison Tool

Compares the 2 most recent trade logs for a given asset/strategy.
Generates side-by-side metrics, yearly breakdown, core-vs-border analysis,
and runs the 10-criteria pre-evaluation checklist.

Usage:
    python tools/compare_robustness.py                # Auto-detect 2 latest logs
    python tools/compare_robustness.py DIA             # Filter by asset
    python tools/compare_robustness.py DIA_PRO         # Filter by config name
    python tools/compare_robustness.py log1.txt log2.txt  # Compare specific files
    python tools/compare_robustness.py DIA_PRO --wf    # Walk-forward mode (relaxed criteria)

Modes:
    Standard (default): Compares same-params across 2 periods (e.g. 5Y vs 6Y).
    Walk-forward (--wf): Log A = training period, Log B = full period (train + OOS).
        Relaxes criteria 1 (core match allows edge-of-training year diff) and
        criteria 9 (PF degradation 25% allowed instead of 15%).
        Adds OOS-specific evaluation section.
"""
import re
import os
import sys
import math
import random
from datetime import datetime
from collections import defaultdict


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
STARTING_CASH = 100_000.0
RISK_FREE_RATE = 0.0
MC_SIMULATIONS = 10_000

# Checklist thresholds
CHECK_PF_MIN = 1.5
CHECK_SHARPE_MIN = 1.0
CHECK_DD_MAX = 15.0
CHECK_MC95_MAX = 20.0
CHECK_DOMINANT_YEAR_MAX = 40.0  # percent
CHECK_NEGATIVE_YEARS_MAX = 1
CHECK_PF_DEGRADATION_MAX = 15.0  # percent
CHECK_TRADES_PER_YEAR_MIN = 10

# Walk-forward relaxed thresholds
WF_PF_DEGRADATION_MAX = 25.0  # percent (IS→OOS degradation is expected)
WF_CORE_TOLERANCE_TRADES = 5  # edge-of-training year may differ slightly
WF_CORE_TOLERANCE_PNL = 1500.0
WF_OOS_PF_MIN = 1.0            # minimum PF for OOS to be considered viable
WF_OOS_PF_TARGET = 1.3         # target PF for OOS to confirm real edge


# ---------------------------------------------------------------------------
# Log discovery
# ---------------------------------------------------------------------------
def find_latest_logs(log_dir, name_filter=None, count=2):
    """Find the N most recent log files, optionally filtered by name.

    Args:
        log_dir: Path to logs/ directory.
        name_filter: Optional string to filter filenames (e.g. 'DIA', 'DIA_PRO').
        count: How many logs to return (default 2).

    Returns:
        List of filenames sorted by modification time (newest first).
    """
    all_logs = [f for f in os.listdir(log_dir) if f.endswith('.txt')]
    if name_filter:
        # Match either exact config prefix (DIA_PRO_) or asset prefix (DIA_)
        all_logs = [f for f in all_logs if f.startswith(name_filter + '_') or
                    f.startswith(name_filter.split('_')[0] + '_')]
        # If config-level filter given, narrow further
        if '_' in name_filter:
            all_logs = [f for f in all_logs if f.startswith(name_filter + '_')]

    if len(all_logs) < 2:
        return all_logs

    all_logs.sort(key=lambda f: os.path.getmtime(os.path.join(log_dir, f)), reverse=True)
    return all_logs[:count]


# ---------------------------------------------------------------------------
# Log parsing
# ---------------------------------------------------------------------------
def parse_log(filepath):
    """Parse a trade log file and return list of trade dicts."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Extract config name from header
    config_match = re.search(r'Configuration: (\S+)', content)
    config_name = config_match.group(1) if config_match else 'Unknown'

    # Extract asset name
    asset_match = re.search(r'Asset: (\S+)', content)
    asset_name = asset_match.group(1) if asset_match else 'Unknown'

    # Parse entries
    entries = re.findall(
        r'ENTRY #(\d+)\n'
        r'Time: ([\d-]+ [\d:]+)\n'
        r'Direction: (\w+)\n'
        r'ATR Current: ([\d.]+)\n'
        r'(?:[^\n]*\n)?'  # Optional ATR Increment/Change line
        r'Angle Current: ([\d.-]+) deg\n'
        r'[^\n]*\n'       # Angle Filter line
        r'SL Pips: ([\d.]+)',
        content
    )

    # Parse exits
    exits_raw = re.findall(
        r'EXIT #(\d+)\n'
        r'Time: ([^\n]+)\n'
        r'Exit Reason: ([^\n]+)\n'
        r'P&L: ([-\d,.]+)\n'
        r'Pips: ([-\d,.]+)\n'
        r'Duration: (\d+) bars',
        content
    )

    exits_by_id = {}
    for ex in exits_raw:
        exits_by_id[int(ex[0])] = ex

    # Parse commission info
    commission_match = re.search(r'Total Commission: \$([\d,.]+)', content)
    total_commission = float(commission_match.group(1).replace(',', '')) if commission_match else 0.0

    trades = []
    for entry in entries:
        trade_id = int(entry[0])
        trade = {
            'id': trade_id,
            'entry_time': datetime.strptime(entry[1], '%Y-%m-%d %H:%M:%S'),
            'direction': entry[2],
            'atr': float(entry[3]),
            'angle': float(entry[4]),
            'sl_pips': float(entry[5]),
        }
        ex = exits_by_id.get(trade_id)
        if ex:
            exit_time_str = ex[1].strip()
            exit_reason = ex[2].strip()
            if exit_time_str == 'N/A' or exit_reason == 'N/A':
                continue
            trade['exit_time'] = datetime.strptime(exit_time_str, '%Y-%m-%d %H:%M:%S')
            trade['exit_reason'] = exit_reason
            trade['pnl'] = float(ex[3].replace(',', ''))
            trade['pips'] = float(ex[4].replace(',', ''))
            trade['duration_bars'] = int(ex[5])
            trade['win'] = trade['pnl'] > 0
            trades.append(trade)

    return {
        'config': config_name,
        'asset': asset_name,
        'trades': trades,
        'commission': total_commission,
    }


# ---------------------------------------------------------------------------
# Metrics calculation
# ---------------------------------------------------------------------------
def calc_metrics(trades, starting_cash=STARTING_CASH):
    """Calculate comprehensive metrics from a list of trades."""
    if not trades:
        return None

    closed = [t for t in trades if 'pnl' in t]
    if not closed:
        return None

    winners = [t for t in closed if t['pnl'] > 0]
    losers = [t for t in closed if t['pnl'] <= 0]

    gross_profit = sum(t['pnl'] for t in winners)
    gross_loss = sum(abs(t['pnl']) for t in losers)
    net_pnl = gross_profit - gross_loss

    pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    wr = len(winners) / len(closed) * 100 if closed else 0.0

    # -- Date range --
    first_date = min(t['entry_time'] for t in closed)
    last_date = max(t.get('exit_time', t['entry_time']) for t in closed)
    years = max((last_date - first_date).days / 365.25, 0.5)

    # -- CAGR --
    final_value = starting_cash + net_pnl
    cagr = (final_value / starting_cash) ** (1.0 / years) - 1.0

    # -- Max Drawdown --
    equity = starting_cash
    peak = equity
    max_dd = 0.0
    dd_series = []
    for t in sorted(closed, key=lambda x: x['entry_time']):
        equity += t['pnl']
        peak = max(peak, equity)
        dd = (peak - equity) / peak * 100 if peak > 0 else 0
        max_dd = max(max_dd, dd)
        dd_series.append(dd)

    # -- Sharpe Ratio (annualized from trade returns) --
    returns = [t['pnl'] / starting_cash for t in closed]
    if len(returns) > 1:
        avg_r = sum(returns) / len(returns)
        std_r = (sum((r - avg_r) ** 2 for r in returns) / (len(returns) - 1)) ** 0.5
        trades_per_year = len(closed) / years
        sharpe = (avg_r / std_r) * math.sqrt(trades_per_year) if std_r > 0 else 0
    else:
        sharpe = 0.0

    # -- Sortino Ratio --
    downside = [r for r in returns if r < 0]
    if downside and len(downside) > 1:
        avg_r = sum(returns) / len(returns)
        downside_dev = (sum(r ** 2 for r in downside) / len(downside)) ** 0.5
        trades_per_year = len(closed) / years
        sortino = (avg_r / downside_dev) * math.sqrt(trades_per_year) if downside_dev > 0 else 0
    else:
        sortino = 0.0

    # -- Monte Carlo DD 95th/99th --
    pnls = [t['pnl'] for t in closed]
    mc_dds = []
    random.seed(42)
    for _ in range(MC_SIMULATIONS):
        shuffled = random.sample(pnls, len(pnls))
        eq = starting_cash
        pk = eq
        sim_max_dd = 0.0
        for p in shuffled:
            eq += p
            pk = max(pk, eq)
            dd = (pk - eq) / pk * 100 if pk > 0 else 0
            sim_max_dd = max(sim_max_dd, dd)
        mc_dds.append(sim_max_dd)
    mc_dds.sort()
    mc95 = mc_dds[int(0.95 * len(mc_dds))]
    mc99 = mc_dds[int(0.99 * len(mc_dds))]

    # -- Calmar --
    calmar = (cagr * 100) / max_dd if max_dd > 0 else 0

    return {
        'trades': len(closed),
        'wins': len(winners),
        'losses': len(losers),
        'wr': wr,
        'gross_profit': gross_profit,
        'gross_loss': gross_loss,
        'net_pnl': net_pnl,
        'pf': pf,
        'cagr': cagr * 100,
        'max_dd': max_dd,
        'sharpe': sharpe,
        'sortino': sortino,
        'calmar': calmar,
        'mc95': mc95,
        'mc99': mc99,
        'mc_ratio': mc95 / max_dd if max_dd > 0 else 0,
        'years': years,
        'trades_per_year': len(closed) / years,
        'first_date': first_date,
        'last_date': last_date,
        'final_value': starting_cash + net_pnl,
    }


def calc_yearly(trades, starting_cash=STARTING_CASH):
    """Calculate yearly breakdown."""
    by_year = defaultdict(list)
    for t in trades:
        if 'pnl' in t:
            by_year[t['entry_time'].year].append(t)

    yearly = {}
    for year in sorted(by_year.keys()):
        yt = by_year[year]
        winners = [t for t in yt if t['pnl'] > 0]
        losers = [t for t in yt if t['pnl'] <= 0]
        gp = sum(t['pnl'] for t in winners)
        gl = sum(abs(t['pnl']) for t in losers)
        yearly[year] = {
            'trades': len(yt),
            'wins': len(winners),
            'wr': len(winners) / len(yt) * 100 if yt else 0,
            'pf': gp / gl if gl > 0 else float('inf'),
            'pnl': gp - gl,
            'gross_profit': gp,
            'gross_loss': gl,
        }
    return yearly


# ---------------------------------------------------------------------------
# Core vs border analysis
# ---------------------------------------------------------------------------
def analyze_core_border(yearly_a, yearly_b):
    """Identify core years (shared) and border years (only in longer period).

    Returns dict with core years, border years, and match analysis.
    """
    years_a = set(yearly_a.keys())
    years_b = set(yearly_b.keys())
    core_years = sorted(years_a & years_b)
    border_a = sorted(years_a - years_b)
    border_b = sorted(years_b - years_a)

    # Determine which is shorter and which is longer
    all_a = sorted(years_a)
    all_b = sorted(years_b)

    if len(all_a) <= len(all_b):
        shorter_yearly = yearly_a
        longer_yearly = yearly_b
        border_only = border_b
        labels = ('Shorter', 'Longer')
    else:
        shorter_yearly = yearly_b
        longer_yearly = yearly_a
        border_only = border_a
        labels = ('Longer', 'Shorter')

    # Check core match
    core_match = True
    core_diffs = []
    for y in core_years:
        diff_trades = abs(yearly_a[y]['trades'] - yearly_b[y]['trades'])
        diff_pnl = abs(yearly_a[y]['pnl'] - yearly_b[y]['pnl'])
        if diff_trades > 2 or diff_pnl > 500:
            core_match = False
        core_diffs.append({
            'year': y,
            'trades_a': yearly_a[y]['trades'],
            'trades_b': yearly_b[y]['trades'],
            'pnl_a': yearly_a[y]['pnl'],
            'pnl_b': yearly_b[y]['pnl'],
            'match': diff_trades <= 2 and diff_pnl <= 500,
        })

    return {
        'core_years': core_years,
        'border_a': border_a,
        'border_b': border_b,
        'border_only': border_only,
        'core_match': core_match,
        'core_diffs': core_diffs,
    }


# ---------------------------------------------------------------------------
# Checklist
# ---------------------------------------------------------------------------
def run_checklist(metrics_a, metrics_b, yearly_a, yearly_b, walk_forward=False):
    """Run 10-criteria pre-evaluation checklist.

    Returns list of (criterion, pass/fail, details) tuples.
    Convention: A = shorter/5Y-like period, B = longer/6Y-like period.
    If both have same length, A = first log, B = second log.

    Args:
        walk_forward: If True, relax criteria 1 (core match) and 9 (PF degradation)
                      because IS→OOS degradation is expected and edge-of-training
                      year may have different trade counts.
    """
    checks = []
    mode_tag = ' [WF]' if walk_forward else ''

    # Determine which is shorter
    if metrics_a['years'] <= metrics_b['years']:
        ma, mb = metrics_a, metrics_b
        ya, yb = yearly_a, yearly_b
        label_a, label_b = ('A (train)', 'B (full)') if walk_forward else ('A (shorter)', 'B (longer)')
    else:
        ma, mb = metrics_b, metrics_a
        ya, yb = yearly_b, yearly_a
        label_a, label_b = ('A (train)', 'B (full)') if walk_forward else ('A (shorter)', 'B (longer)')

    # 1. Core match (relaxed in walk-forward: edge-of-training year allowed to differ)
    core_info = analyze_core_border(ya, yb)
    if walk_forward:
        # In WF mode, check core with relaxed tolerance
        wf_core_match = True
        for diff in core_info['core_diffs']:
            if diff['match']:
                continue
            # Allow larger diff only for the LAST core year (edge of training)
            is_last_core = diff['year'] == max(y['year'] for y in core_info['core_diffs'])
            if is_last_core:
                if abs(diff['trades_a'] - diff['trades_b']) <= WF_CORE_TOLERANCE_TRADES and \
                   abs(diff['pnl_a'] - diff['pnl_b']) <= WF_CORE_TOLERANCE_PNL:
                    continue
            wf_core_match = False
        checks.append(('1. CORE MATCH' + mode_tag, wf_core_match,
                        f'Core years {core_info["core_years"]} OK (WF tolerance)' if wf_core_match
                        else 'Core years DIFFER (even with WF tolerance)'))
    else:
        checks.append(('1. CORE MATCH', core_info['core_match'],
                        f'Core years {core_info["core_years"]} identical' if core_info['core_match']
                        else 'Core years DIFFER'))

    # 2. Borders add or subtract
    border_pnl = 0
    border_trades = 0
    for y in core_info['border_only']:
        if y in yb:
            border_pnl += yb[y]['pnl']
            border_trades += yb[y]['trades']
        elif y in ya:
            border_pnl += ya[y]['pnl']
            border_trades += ya[y]['trades']
    border_positive = border_pnl >= 0
    checks.append(('2. BORDERS', border_positive,
                    f'+{border_trades} trades, ${border_pnl:+,.0f} PnL' if border_positive
                    else f'+{border_trades} trades, ${border_pnl:+,.0f} PnL (NEGATIVE)'))

    # 3. PF > 1.5 both
    pf_pass = ma['pf'] >= CHECK_PF_MIN and mb['pf'] >= CHECK_PF_MIN
    checks.append(('3. PF > 1.5', pf_pass,
                    f'{label_a}: {ma["pf"]:.2f} | {label_b}: {mb["pf"]:.2f}'))

    # 4. Sharpe > 1.0 both
    sh_pass = ma['sharpe'] >= CHECK_SHARPE_MIN and mb['sharpe'] >= CHECK_SHARPE_MIN
    checks.append(('4. SHARPE > 1.0', sh_pass,
                    f'{label_a}: {ma["sharpe"]:.2f} | {label_b}: {mb["sharpe"]:.2f}'))

    # 5. DD < 15% both
    dd_pass = ma['max_dd'] <= CHECK_DD_MAX and mb['max_dd'] <= CHECK_DD_MAX
    checks.append(('5. DD < 15%', dd_pass,
                    f'{label_a}: {ma["max_dd"]:.2f}% | {label_b}: {mb["max_dd"]:.2f}%'))

    # 6. MC95 < 20% both
    mc_pass = ma['mc95'] <= CHECK_MC95_MAX and mb['mc95'] <= CHECK_MC95_MAX
    checks.append(('6. MC95 < 20%', mc_pass,
                    f'{label_a}: {ma["mc95"]:.2f}% | {label_b}: {mb["mc95"]:.2f}%'))

    # 7. Dominant year < 40%
    def dominant_pct(yearly_data, net_pnl):
        if net_pnl <= 0:
            return 0
        max_year_pnl = max((y['pnl'] for y in yearly_data.values()), default=0)
        return max_year_pnl / net_pnl * 100 if net_pnl > 0 else 0

    dom_a = dominant_pct(ya, ma['net_pnl'])
    dom_b = dominant_pct(yb, mb['net_pnl'])
    dom_pass = dom_a <= CHECK_DOMINANT_YEAR_MAX and dom_b <= CHECK_DOMINANT_YEAR_MAX
    checks.append(('7. DOMINANT < 40%', dom_pass,
                    f'{label_a}: {dom_a:.1f}% | {label_b}: {dom_b:.1f}%'))

    # 8. Negative years <= 1
    neg_a = sum(1 for y in ya.values() if y['pnl'] < 0)
    neg_b = sum(1 for y in yb.values() if y['pnl'] < 0)
    neg_pass = neg_a <= CHECK_NEGATIVE_YEARS_MAX and neg_b <= CHECK_NEGATIVE_YEARS_MAX
    checks.append(('8. NEG YEARS <= 1', neg_pass,
                    f'{label_a}: {neg_a} | {label_b}: {neg_b}'))

    # 9. PF degradation (15% standard, 25% walk-forward)
    if ma['pf'] > 0 and ma['pf'] < float('inf'):
        pf_delta = (mb['pf'] - ma['pf']) / ma['pf'] * 100
    else:
        pf_delta = 0
    pf_deg_limit = WF_PF_DEGRADATION_MAX if walk_forward else CHECK_PF_DEGRADATION_MAX
    pf_deg_pass = abs(pf_delta) <= pf_deg_limit
    pf_label = f'9. PF DEGRAD < {int(pf_deg_limit)}%'
    checks.append((pf_label, pf_deg_pass,
                    f'Delta: {pf_delta:+.1f}%{" (WF relaxed)" if walk_forward else ""}'))

    # 10. Trades/year >= 10
    tpy_a = ma['trades_per_year']
    tpy_b = mb['trades_per_year']
    tpy_pass = tpy_a >= CHECK_TRADES_PER_YEAR_MIN and tpy_b >= CHECK_TRADES_PER_YEAR_MIN
    checks.append(('10. TRADES/YR >= 10', tpy_pass,
                    f'{label_a}: {tpy_a:.1f} | {label_b}: {tpy_b:.1f}'))

    return checks


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------
def print_header(text, char='=', width=80):
    print(f'\n{char * width}')
    print(f'  {text}')
    print(f'{char * width}')


def print_comparison(log_a, log_b, metrics_a, metrics_b, yearly_a, yearly_b,
                     walk_forward=False):
    """Print full side-by-side comparison."""
    mode_str = 'WALK-FORWARD' if walk_forward else 'ROBUSTNESS'

    # Determine shorter/longer
    tag_a = 'TRAIN' if walk_forward else ''
    tag_b = 'FULL' if walk_forward else ''
    label_a = f'A: {os.path.basename(log_a)} ({metrics_a["years"]:.1f}y){" [" + tag_a + "]" if tag_a else ""}'
    label_b = f'B: {os.path.basename(log_b)} ({metrics_b["years"]:.1f}y){" [" + tag_b + "]" if tag_b else ""}'

    print_header(f'{mode_str} COMPARISON')
    print(f'  {label_a}')
    print(f'  {label_b}')

    # --- Main metrics ---
    print_header('METRICS COMPARISON', '-')
    rows = [
        ('Trades',     f'{metrics_a["trades"]}',         f'{metrics_b["trades"]}',
         f'{metrics_b["trades"] - metrics_a["trades"]:+d}'),
        ('Win Rate',   f'{metrics_a["wr"]:.1f}%',        f'{metrics_b["wr"]:.1f}%',
         f'{metrics_b["wr"] - metrics_a["wr"]:+.1f}%'),
        ('PF',         f'{metrics_a["pf"]:.2f}',         f'{metrics_b["pf"]:.2f}',
         f'{metrics_b["pf"] - metrics_a["pf"]:+.2f}'),
        ('Net PnL',    f'${metrics_a["net_pnl"]:,.0f}',  f'${metrics_b["net_pnl"]:,.0f}',
         f'${metrics_b["net_pnl"] - metrics_a["net_pnl"]:+,.0f}'),
        ('CAGR',       f'{metrics_a["cagr"]:.2f}%',      f'{metrics_b["cagr"]:.2f}%',
         f'{metrics_b["cagr"] - metrics_a["cagr"]:+.2f}%'),
        ('Max DD',     f'{metrics_a["max_dd"]:.2f}%',    f'{metrics_b["max_dd"]:.2f}%',
         f'{metrics_b["max_dd"] - metrics_a["max_dd"]:+.2f}%'),
        ('Sharpe',     f'{metrics_a["sharpe"]:.2f}',     f'{metrics_b["sharpe"]:.2f}',
         f'{metrics_b["sharpe"] - metrics_a["sharpe"]:+.2f}'),
        ('Sortino',    f'{metrics_a["sortino"]:.2f}',    f'{metrics_b["sortino"]:.2f}',
         f'{metrics_b["sortino"] - metrics_a["sortino"]:+.2f}'),
        ('Calmar',     f'{metrics_a["calmar"]:.2f}',     f'{metrics_b["calmar"]:.2f}',
         f'{metrics_b["calmar"] - metrics_a["calmar"]:+.2f}'),
        ('MC95 DD',    f'{metrics_a["mc95"]:.2f}%',      f'{metrics_b["mc95"]:.2f}%',
         f'{metrics_b["mc95"] - metrics_a["mc95"]:+.2f}%'),
        ('MC99 DD',    f'{metrics_a["mc99"]:.2f}%',      f'{metrics_b["mc99"]:.2f}%',
         f'{metrics_b["mc99"] - metrics_a["mc99"]:+.2f}%'),
        ('MC/DD Ratio', f'{metrics_a["mc_ratio"]:.2f}x', f'{metrics_b["mc_ratio"]:.2f}x',
         f'{metrics_b["mc_ratio"] - metrics_a["mc_ratio"]:+.2f}x'),
        ('Trades/Year', f'{metrics_a["trades_per_year"]:.1f}', f'{metrics_b["trades_per_year"]:.1f}',
         f'{metrics_b["trades_per_year"] - metrics_a["trades_per_year"]:+.1f}'),
        ('Period',     f'{metrics_a["first_date"].strftime("%Y-%m")} to {metrics_a["last_date"].strftime("%Y-%m")}',
                       f'{metrics_b["first_date"].strftime("%Y-%m")} to {metrics_b["last_date"].strftime("%Y-%m")}',
         ''),
    ]

    print(f'  {"Metric":<15} {"Log A":>14} {"Log B":>14} {"Delta":>14}')
    print(f'  {"-"*15} {"-"*14} {"-"*14} {"-"*14}')
    for label, va, vb, delta in rows:
        print(f'  {label:<15} {va:>14} {vb:>14} {delta:>14}')

    # --- Yearly breakdown ---
    print_header('YEARLY COMPARISON', '-')
    all_years = sorted(set(list(yearly_a.keys()) + list(yearly_b.keys())))
    core_info = analyze_core_border(yearly_a, yearly_b)

    print(f'  {"Year":<6} {"Tr A":>5} {"Tr B":>5} {"WR% A":>6} {"WR% B":>6} '
          f'{"PF A":>6} {"PF B":>6} {"PnL A":>10} {"PnL B":>10} {"Match":>6}')
    print(f'  {"-"*6} {"-"*5} {"-"*5} {"-"*6} {"-"*6} {"-"*6} {"-"*6} {"-"*10} {"-"*10} {"-"*6}')

    for y in all_years:
        ya_data = yearly_a.get(y, {'trades': 0, 'wr': 0, 'pf': 0, 'pnl': 0})
        yb_data = yearly_b.get(y, {'trades': 0, 'wr': 0, 'pf': 0, 'pnl': 0})

        is_core = y in core_info['core_years']
        pf_a = f'{ya_data["pf"]:.2f}' if ya_data['pf'] < 100 else 'INF'
        pf_b = f'{yb_data["pf"]:.2f}' if yb_data['pf'] < 100 else 'INF'

        if is_core:
            diff_ok = abs(ya_data['trades'] - yb_data['trades']) <= 2 and abs(ya_data['pnl'] - yb_data['pnl']) <= 500
            mark = 'OK' if diff_ok else 'DIFF!'
        else:
            mark = 'BORDER'

        print(f'  {y:<6} {ya_data["trades"]:>5} {yb_data["trades"]:>5} '
              f'{ya_data["wr"]:>5.1f}% {yb_data["wr"]:>5.1f}% '
              f'{pf_a:>6} {pf_b:>6} '
              f'${ya_data["pnl"]:>9,.0f} ${yb_data["pnl"]:>9,.0f} '
              f'{mark:>6}')

    # --- Concentration analysis ---
    print_header('CONCENTRATION ANALYSIS', '-')
    for label, yearly, metrics in [('Log A', yearly_a, metrics_a), ('Log B', yearly_b, metrics_b)]:
        if metrics['net_pnl'] > 0:
            sorted_years = sorted(yearly.items(), key=lambda x: x[1]['pnl'], reverse=True)
            best_y, best_d = sorted_years[0]
            pct = best_d['pnl'] / metrics['net_pnl'] * 100
            print(f'  {label}: Best year {best_y} = ${best_d["pnl"]:,.0f} ({pct:.1f}% of total)')
        else:
            print(f'  {label}: Net PnL negative - no concentration analysis')

    # --- Checklist ---
    checklist_title = 'PRE-EVALUATION CHECKLIST (WALK-FORWARD)' if walk_forward else 'PRE-EVALUATION CHECKLIST'
    print_header(checklist_title, '-')
    checks = run_checklist(metrics_a, metrics_b, yearly_a, yearly_b, walk_forward=walk_forward)
    passed = 0
    failed = 0
    for criterion, ok, details in checks:
        status = 'PASS' if ok else 'FAIL'
        icon = '[+]' if ok else '[X]'
        print(f'  {icon} {criterion:<22} {status:<5} {details}')
        if ok:
            passed += 1
        else:
            failed += 1

    print(f'\n  Result: {passed}/10 passed, {failed}/10 failed')

    # Verdict suggestion
    if failed == 0:
        print('  >>> VERDICT: ALL CRITERIA PASS - candidate for approval')
    elif any(not ok for crit, ok, _ in checks if 'PF' in crit and '1.5' in crit):
        if metrics_a['pf'] < 1.0 or metrics_b['pf'] < 1.0:
            print('  >>> VERDICT: IMMEDIATE DISCARD (PF < 1.0)')
        else:
            print(f'  >>> VERDICT: {failed} criteria fail - review required')
    elif any(not ok for crit, ok, _ in checks if 'SHARPE' in crit):
        if metrics_a['sharpe'] < 0.5 or metrics_b['sharpe'] < 0.5:
            print('  >>> VERDICT: IMMEDIATE DISCARD (Sharpe < 0.5)')
        else:
            print(f'  >>> VERDICT: {failed} criteria fail - review required')
    else:
        print(f'  >>> VERDICT: {failed} criteria fail - review required')

    # --- Walk-forward OOS analysis (only in --wf mode) ---
    if walk_forward:
        print_header('OUT-OF-SAMPLE ANALYSIS (Walk-Forward)', '-')
        # Identify OOS years: years in full (B) but not in training (A)
        if metrics_a['years'] <= metrics_b['years']:
            train_trades = parse_a_trades
            full_trades = parse_b_trades
        else:
            train_trades = parse_b_trades
            full_trades = parse_a_trades

        train_years = set(t['entry_time'].year for t in train_trades if 'pnl' in t)
        oos_trades = [t for t in full_trades if 'pnl' in t and t['entry_time'].year not in train_years]

        if oos_trades:
            oos_m = calc_metrics(oos_trades)
            oos_yearly = calc_yearly(oos_trades)
            if oos_m:
                oos_years = sorted(oos_yearly.keys())
                print(f'  OOS Period: {oos_years[0]}-{oos_years[-1]} ({len(oos_trades)} trades, {oos_m["years"]:.1f}y)')
                print(f'  OOS PF:     {oos_m["pf"]:.2f}')
                print(f'  OOS WR:     {oos_m["wr"]:.1f}%')
                print(f'  OOS PnL:    ${oos_m["net_pnl"]:,.0f}')
                print(f'  OOS Sharpe: {oos_m["sharpe"]:.2f}')
                print(f'  OOS DD:     {oos_m["max_dd"]:.2f}%')
                print()

                # Per-year OOS breakdown
                print(f'  {"Year":<6} {"Trades":>7} {"WR%":>6} {"PF":>6} {"PnL":>12}')
                print(f'  {"-"*6} {"-"*7} {"-"*6} {"-"*6} {"-"*12}')
                for y in oos_years:
                    yd = oos_yearly[y]
                    pf_str = f'{yd["pf"]:.2f}' if yd['pf'] < 100 else 'INF'
                    print(f'  {y:<6} {yd["trades"]:>7} {yd["wr"]:>5.1f}% {pf_str:>6} ${yd["pnl"]:>11,.0f}')
                print()

                # OOS verdict
                if oos_m['pf'] >= WF_OOS_PF_TARGET:
                    print(f'  >>> OOS VERDICT: STRONG EDGE (PF {oos_m["pf"]:.2f} >= {WF_OOS_PF_TARGET})')
                elif oos_m['pf'] >= WF_OOS_PF_MIN:
                    print(f'  >>> OOS VERDICT: VIABLE (PF {oos_m["pf"]:.2f} >= {WF_OOS_PF_MIN}, below target {WF_OOS_PF_TARGET})')
                else:
                    print(f'  >>> OOS VERDICT: FAIL (PF {oos_m["pf"]:.2f} < {WF_OOS_PF_MIN})')
        else:
            print('  No OOS trades found (training covers all years in full log)')

    # --- Recent period test (Test B) ---
    print_header('RECENT PERIOD TEST (2022-2025)', '-')
    for label, trades_list, metrics in [('Log A', parse_a_trades, metrics_a), ('Log B', parse_b_trades, metrics_b)]:
        recent = [t for t in trades_list if t['entry_time'].year >= 2022]
        if recent:
            rm = calc_metrics(recent)
            if rm:
                status = 'PASS' if rm['pf'] >= CHECK_PF_MIN else 'FAIL'
                print(f'  {label} (2022+): {rm["trades"]} trades, PF {rm["pf"]:.2f}, '
                      f'WR {rm["wr"]:.1f}%, PnL ${rm["net_pnl"]:,.0f} [{status}]')


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
# These are set in main() and used by print_comparison for the recent test
parse_a_trades = []
parse_b_trades = []


def main():
    global parse_a_trades, parse_b_trades

    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')

    # Parse arguments
    args = sys.argv[1:]
    walk_forward = '--wf' in args
    args = [a for a in args if a != '--wf']

    if len(args) == 2 and args[0].endswith('.txt') and args[1].endswith('.txt'):
        # Two specific files
        log_files = args
    elif len(args) == 1:
        # Filter by name
        log_files = find_latest_logs(log_dir, args[0])
    else:
        # Auto-detect
        log_files = find_latest_logs(log_dir)

    if len(log_files) < 2:
        print(f'ERROR: Need at least 2 log files. Found: {log_files}')
        print(f'Usage: python tools/compare_robustness.py [ASSET|CONFIG] or [log1.txt log2.txt]')
        sys.exit(1)

    # Build full paths
    paths = []
    for f in log_files:
        if os.path.isabs(f):
            paths.append(f)
        elif os.path.exists(os.path.join(log_dir, f)):
            paths.append(os.path.join(log_dir, f))
        else:
            paths.append(f)

    if walk_forward:
        print(f'Comparing (WALK-FORWARD mode):')
    else:
        print(f'Comparing:')
    print(f'  A: {os.path.basename(paths[0])}')
    print(f'  B: {os.path.basename(paths[1])}')

    # Parse both logs
    data_a = parse_log(paths[0])
    data_b = parse_log(paths[1])

    parse_a_trades = data_a['trades']
    parse_b_trades = data_b['trades']

    # Calculate metrics
    metrics_a = calc_metrics(data_a['trades'])
    metrics_b = calc_metrics(data_b['trades'])

    if not metrics_a or not metrics_b:
        print('ERROR: Could not calculate metrics from one or both logs.')
        sys.exit(1)

    yearly_a = calc_yearly(data_a['trades'])
    yearly_b = calc_yearly(data_b['trades'])

    # Print comparison
    print_comparison(paths[0], paths[1], metrics_a, metrics_b, yearly_a, yearly_b,
                     walk_forward=walk_forward)


if __name__ == '__main__':
    main()
