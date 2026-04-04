"""
VEGA Monthly Performance Analyzer

Parses VEGA trade logs and produces monthly/yearly P&L, PF, DD, and
combined portfolio analysis. Designed for risk rebalancing decisions.

Usage:
    python tools/vega_monthly_analysis.py                     # Latest 3 logs
    python tools/vega_monthly_analysis.py --logs LOG1 LOG2..  # Specific logs
    python tools/vega_monthly_analysis.py --capital 50000     # Custom capital

Author: Ivan
Version: 1.0.0
"""
import os
import sys
import re
import argparse
import math
from datetime import datetime
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
LOG_DIR = os.path.join(PROJECT_ROOT, 'logs')


# =============================================================================
# LOG PARSER (reuses analyze_vega pattern)
# =============================================================================

def parse_vega_log(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Detect config params from log header
    m_dz = re.search(r'Dead Zone:\s*([\d.]+)', content)
    dz = float(m_dz.group(1)) if m_dz else 0

    m_day = re.search(r'Day Filter:\s*\[([^\]]+)\]', content)
    day_filter = m_day.group(1) if m_day else None

    m_atr = re.search(r'ATR Filter:\s*\[([^\]]+)\]', content)
    atr_filter = m_atr.group(1) if m_atr else None

    entries = re.findall(
        r'ENTRY #(\d+)\s*\n'
        r'Time: ([\d-]+ [\d:]+)\s*\n'
        r'Direction: (LONG|SHORT)\s*\n'
        r'Entry Price: ([\d.]+)\s*\n'
        r'Size: (\d+) contracts\s*\n'
        r'Spread: ([-\d.]+)\s*\n'
        r'Forecast: ([-\d.]+)\s*\n'
        r'ATR\(B\): ([\d.]+)',
        content, re.IGNORECASE
    )

    exits_raw = re.findall(
        r'EXIT #(\d+)\s*\n'
        r'Time: ([^\n]+)\s*\n'
        r'Exit Reason: ([^\n]+)\s*\n'
        r'P&L: \$([-\d,.]+)',
        content, re.IGNORECASE
    )

    exits_by_id = {}
    for ex in exits_raw:
        exits_by_id[int(ex[0])] = ex

    trades = []
    for entry in entries:
        trade_id = int(entry[0])
        entry_time = datetime.strptime(entry[1], '%Y-%m-%d %H:%M:%S')
        ex = exits_by_id.get(trade_id)
        if not ex:
            continue
        exit_time_str = ex[1].strip()
        exit_reason = ex[2].strip()
        if exit_time_str == 'N/A' or exit_reason == 'N/A':
            continue
        pnl = float(ex[3].replace(',', ''))
        trades.append({
            'id': trade_id,
            'entry_time': entry_time,
            'exit_time': datetime.strptime(exit_time_str, '%Y-%m-%d %H:%M:%S'),
            'direction': entry[2],
            'size': int(entry[4]),
            'pnl': pnl,
            'exit_reason': exit_reason,
            'year': entry_time.year,
            'month': entry_time.month,
        })

    return trades, dz, day_filter, atr_filter


def identify_config(dz, day_filter, atr_filter, num_trades):
    """Identify config by unique parameter combinations from the log header.
    - NI225_VEGA: DZ=2.0, has Day Filter, ~1100 trades
    - GDAXI_VEGA: DZ=3.0, ATR Filter [50, 250], ~2300 trades
    - NDAXI_VEGA: DZ=3.0, no ATR lower bound, ~2200 trades
    """
    if dz == 2.0:
        return 'NI225_VEGA'
    if dz == 3.0:
        if atr_filter and '50' in atr_filter:
            return 'GDAXI_VEGA'
        return 'NDAXI_VEGA'
    return f'VEGA_DZ{dz}_{num_trades}t'


# =============================================================================
# MONTHLY METRICS
# =============================================================================

def compute_monthly(trades, capital):
    """Compute month-by-month metrics with running equity curve."""
    by_month = defaultdict(list)
    for t in trades:
        key = (t['year'], t['month'])
        by_month[key] = by_month.get(key, [])
        by_month[key].append(t)

    # Sort by date
    sorted_months = sorted(by_month.keys())

    equity = capital
    peak = capital
    results = []

    for (year, month) in sorted_months:
        month_trades = by_month[(year, month)]
        month_trades.sort(key=lambda t: t['entry_time'])

        wins = [t['pnl'] for t in month_trades if t['pnl'] > 0]
        losses = [t['pnl'] for t in month_trades if t['pnl'] <= 0]
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        net_pnl = sum(t['pnl'] for t in month_trades)
        pf = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
        wr = len(wins) / len(month_trades) * 100 if month_trades else 0

        # Intra-month drawdown (trade by trade within the month)
        month_equity = equity
        month_peak = equity
        month_max_dd = 0
        for t in month_trades:
            month_equity += t['pnl']
            if month_equity > month_peak:
                month_peak = month_equity
            dd = (month_peak - month_equity) / month_peak * 100 if month_peak > 0 else 0
            if dd > month_max_dd:
                month_max_dd = dd

        equity_start = equity
        equity += net_pnl
        if equity > peak:
            peak = equity
        running_dd = (peak - equity) / peak * 100 if peak > 0 else 0

        results.append({
            'year': year,
            'month': month,
            'trades': len(month_trades),
            'wins': len(wins),
            'wr': wr,
            'pf': pf,
            'net_pnl': net_pnl,
            'equity': equity,
            'return_pct': net_pnl / equity_start * 100 if equity_start > 0 else 0,
            'intra_month_dd': month_max_dd,
            'running_dd': running_dd,
        })

    return results


def compute_yearly_from_monthly(monthly_results):
    """Aggregate monthly results into yearly summaries."""
    by_year = defaultdict(list)
    for m in monthly_results:
        by_year[m['year']].append(m)

    yearly = []
    for year in sorted(by_year.keys()):
        months = by_year[year]
        total_trades = sum(m['trades'] for m in months)
        total_wins = sum(m['wins'] for m in months)
        total_pnl = sum(m['net_pnl'] for m in months)
        wr = total_wins / total_trades * 100 if total_trades > 0 else 0

        # Yearly PF from monthly aggregated wins/losses
        gross_p = sum(m['net_pnl'] for m in months if m['net_pnl'] > 0)
        gross_l = abs(sum(m['net_pnl'] for m in months if m['net_pnl'] <= 0))
        pf = gross_p / gross_l if gross_l > 0 else (999.0 if gross_p > 0 else 0.0)

        worst_month_dd = max(m['intra_month_dd'] for m in months)
        max_running_dd = max(m['running_dd'] for m in months)
        best_month = max(m['net_pnl'] for m in months)
        worst_month = min(m['net_pnl'] for m in months)
        positive_months = sum(1 for m in months if m['net_pnl'] > 0)

        yearly.append({
            'year': year,
            'trades': total_trades,
            'wins': total_wins,
            'wr': wr,
            'pf': pf,
            'net_pnl': total_pnl,
            'best_month': best_month,
            'worst_month': worst_month,
            'worst_intra_dd': worst_month_dd,
            'max_running_dd': max_running_dd,
            'positive_months': positive_months,
            'total_months': len(months),
        })

    return yearly


# =============================================================================
# PORTFOLIO COMBINATION
# =============================================================================

def combine_portfolio(all_configs_trades, capital):
    """Combine all configs into a single portfolio equity curve by month."""
    # Gather all month keys across all configs
    all_months = set()
    by_config_month = {}
    for name, trades in all_configs_trades.items():
        by_month = defaultdict(float)
        for t in trades:
            key = (t['year'], t['month'])
            by_month[key] += t['pnl']
            all_months.add(key)
        by_config_month[name] = by_month

    sorted_months = sorted(all_months)
    equity = capital
    peak = capital
    results = []

    for (year, month) in sorted_months:
        month_pnl = sum(by_config_month[name].get((year, month), 0)
                        for name in all_configs_trades)

        # Count trades
        month_trades = 0
        month_wins = 0
        for name, trades in all_configs_trades.items():
            for t in trades:
                if t['year'] == year and t['month'] == month:
                    month_trades += 1
                    if t['pnl'] > 0:
                        month_wins += 1

        equity_start = equity
        equity += month_pnl
        if equity > peak:
            peak = equity
        running_dd = (peak - equity) / peak * 100 if peak > 0 else 0

        results.append({
            'year': year,
            'month': month,
            'trades': month_trades,
            'wins': month_wins,
            'wr': month_wins / month_trades * 100 if month_trades > 0 else 0,
            'net_pnl': month_pnl,
            'equity': equity,
            'return_pct': month_pnl / equity_start * 100 if equity_start > 0 else 0,
            'running_dd': running_dd,
        })

    return results


# =============================================================================
# DISPLAY
# =============================================================================

MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
               'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def print_monthly_table(name, monthly_results, capital):
    print(f'\n{"=" * 100}')
    print(f'  {name} — MONTHLY P&L (capital: ${capital:,.0f})')
    print('=' * 100)
    print(f'{"Month":>8}  {"Trades":>6}  {"WR%":>5}  {"PF":>6}  {"Net P&L":>10}  '
          f'{"Equity":>12}  {"Ret%":>7}  {"IntraDD%":>9}  {"RunDD%":>7}')
    print('-' * 100)

    prev_year = None
    for m in monthly_results:
        if prev_year is not None and m['year'] != prev_year:
            print('-' * 100)
        prev_year = m['year']

        pf_str = f"{m['pf']:.2f}" if m['pf'] < 100 else 'INF'
        dd_str = f"{m.get('intra_month_dd', 0):.1f}" if 'intra_month_dd' in m else '-'
        print(f"{m['year']}-{MONTH_NAMES[m['month']-1]:>3}  {m['trades']:>6}  "
              f"{m['wr']:>4.0f}%  {pf_str:>6}  ${m['net_pnl']:>9,.0f}  "
              f"${m['equity']:>11,.0f}  {m['return_pct']:>6.1f}%  "
              f"{dd_str:>8}%  {m['running_dd']:>6.1f}%")


def print_yearly_summary(name, yearly_results, capital):
    print(f'\n{"=" * 110}')
    print(f'  {name} — YEARLY SUMMARY (capital: ${capital:,.0f})')
    print('=' * 110)
    print(f'{"Year":>6}  {"Trades":>6}  {"WR%":>5}  {"PF":>6}  {"Net P&L":>10}  '
          f'{"BestMo":>9}  {"WorstMo":>9}  {"MaxRunDD%":>10}  {"Mo+/Total":>10}')
    print('-' * 110)

    for y in yearly_results:
        pf_str = f"{y['pf']:.2f}" if y['pf'] < 100 else 'INF'
        print(f"{y['year']:>6}  {y['trades']:>6}  {y['wr']:>4.0f}%  {pf_str:>6}  "
              f"${y['net_pnl']:>9,.0f}  ${y['best_month']:>8,.0f}  ${y['worst_month']:>8,.0f}  "
              f"{y['max_running_dd']:>9.1f}%  {y['positive_months']:>3}/{y['total_months']:<3}")


def print_config_comparison(all_yearly, capital):
    """Side-by-side yearly comparison of all configs."""
    # Collect all years
    all_years = set()
    for name, yearly in all_yearly.items():
        for y in yearly:
            all_years.add(y['year'])
    all_years = sorted(all_years)

    configs = list(all_yearly.keys())
    col_width = 18

    print(f'\n{"=" * (8 + len(configs) * col_width + col_width)}')
    print(f'  CONFIG COMPARISON — Annual Return % (capital: ${capital:,.0f})')
    print('=' * (8 + len(configs) * col_width + col_width))

    header = f'{"Year":>6}'
    for name in configs:
        header += f'  {name:>{col_width - 2}}'
    header += f'  {"COMBINED":>{col_width - 2}}'
    print(header)
    print('-' * (8 + len(configs) * col_width + col_width))

    # Build lookup
    lookup = {}
    for name, yearly in all_yearly.items():
        for y in yearly:
            lookup[(name, y['year'])] = y

    for year in all_years:
        row = f'{year:>6}'
        combined_pnl = 0
        for name in configs:
            y = lookup.get((name, year))
            if y:
                pnl = y['net_pnl']
                combined_pnl += pnl
                ret = pnl / capital * 100
                sign = '+' if ret >= 0 else ''
                row += f'  {sign}{ret:>{col_width - 4}.1f}%'
            else:
                row += f'  {"—":>{col_width - 2}}'
        combined_ret = combined_pnl / capital * 100
        sign = '+' if combined_ret >= 0 else ''
        row += f'  {sign}{combined_ret:>{col_width - 4}.1f}%'
        print(row)

    # Totals
    print('-' * (8 + len(configs) * col_width + col_width))
    row = f'{"TOTAL":>6}'
    grand_total = 0
    for name in configs:
        total = sum(y['net_pnl'] for y in all_yearly[name])
        grand_total += total
        ret = total / capital * 100
        row += f'  {ret:>{col_width - 3}.1f}%'
    row += f'  {grand_total / capital * 100:>{col_width - 3}.1f}%'
    print(row)

    # Avg annual
    row = f'{"AVG/Y":>6}'
    for name in configs:
        total = sum(y['net_pnl'] for y in all_yearly[name])
        avg = total / len(all_yearly[name]) / capital * 100
        row += f'  {avg:>{col_width - 3}.1f}%'
    avg_all = grand_total / len(all_years) / capital * 100
    row += f'  {avg_all:>{col_width - 3}.1f}%'
    print(row)


def print_risk_summary(all_monthly, portfolio_monthly, capital):
    """Print risk-focused summary for rebalancing decisions."""
    print(f'\n{"=" * 90}')
    print(f'  RISK SUMMARY FOR REBALANCING')
    print('=' * 90)

    configs = list(all_monthly.keys())

    print(f'\n{"Metric":<25}', end='')
    for name in configs:
        print(f'  {name:>16}', end='')
    print(f'  {"PORTFOLIO":>16}')
    print('-' * 90)

    def stat_row(label, func):
        print(f'{label:<25}', end='')
        for name in configs:
            val = func(all_monthly[name])
            print(f'  {val:>16}', end='')
        val = func(portfolio_monthly)
        print(f'  {val:>16}')

    stat_row('Total P&L', lambda m: f"${sum(r['net_pnl'] for r in m):>12,.0f}")
    stat_row('Total Return', lambda m: f"{sum(r['net_pnl'] for r in m) / capital * 100:.1f}%")

    # Max running DD
    stat_row('Max Running DD', lambda m: f"{max(r['running_dd'] for r in m):.1f}%")

    # Worst single month
    stat_row('Worst Month P&L', lambda m: f"${min(r['net_pnl'] for r in m):>12,.0f}")
    stat_row('Best Month P&L', lambda m: f"${max(r['net_pnl'] for r in m):>12,.0f}")

    # Consecutive losing months
    def max_consec_loss(monthly):
        max_streak = 0
        streak = 0
        for r in monthly:
            if r['net_pnl'] <= 0:
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 0
        return f'{max_streak}'

    stat_row('Max Consec Loss Mo', max_consec_loss)

    # Monthly return stats
    def avg_monthly_ret(monthly):
        rets = [r['return_pct'] for r in monthly]
        return f"{sum(rets) / len(rets):.2f}%"

    def std_monthly_ret(monthly):
        rets = [r['return_pct'] for r in monthly]
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / len(rets)
        return f"{var ** 0.5:.2f}%"

    stat_row('Avg Monthly Return', avg_monthly_ret)
    stat_row('Std Monthly Return', std_monthly_ret)
    stat_row('Positive Months', lambda m: f"{sum(1 for r in m if r['net_pnl'] > 0)}/{len(m)}")

    # Worst year
    def worst_year_pnl(monthly):
        by_year = defaultdict(float)
        for r in monthly:
            by_year[r['year']] += r['net_pnl']
        worst = min(by_year.values())
        year = min(by_year, key=by_year.get)
        return f"${worst:>8,.0f} ({year})"

    stat_row('Worst Year P&L', worst_year_pnl)

    # Annual return std (how "explosive vs poor" the years are)
    def annual_return_std(monthly):
        by_year = defaultdict(float)
        for r in monthly:
            by_year[r['year']] += r['net_pnl']
        rets = [v / capital * 100 for v in by_year.values()]
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / len(rets)
        return f"{var ** 0.5:.1f}%"

    stat_row('Annual Return Std', annual_return_std)


def print_portfolio_monthly_heatmap(portfolio_monthly, capital):
    """Print a year x month return heatmap for the combined portfolio."""
    print(f'\n{"=" * 100}')
    print(f'  PORTFOLIO MONTHLY RETURN HEATMAP (% of ${capital:,.0f})')
    print('=' * 100)

    by_year_month = {}
    for r in portfolio_monthly:
        by_year_month[(r['year'], r['month'])] = r

    years = sorted(set(r['year'] for r in portfolio_monthly))

    header = f'{"Year":>6}'
    for m in MONTH_NAMES:
        header += f'  {m:>6}'
    header += f'  {"TOTAL":>8}'
    print(header)
    print('-' * 100)

    for year in years:
        row = f'{year:>6}'
        year_total = 0
        for month in range(1, 13):
            r = by_year_month.get((year, month))
            if r:
                ret = r['net_pnl'] / capital * 100
                year_total += ret
                sign = '+' if ret >= 0 else ''
                row += f'  {sign}{ret:>4.1f}%'
            else:
                row += f'  {"—":>6}'
        sign = '+' if year_total >= 0 else ''
        row += f'  {sign}{year_total:>5.1f}%'
        print(row)

    # Annual totals row
    print('-' * 100)
    row = f'{"AVG":>6}'
    for month in range(1, 13):
        vals = []
        for year in years:
            r = by_year_month.get((year, month))
            if r:
                vals.append(r['net_pnl'] / capital * 100)
        if vals:
            avg = sum(vals) / len(vals)
            sign = '+' if avg >= 0 else ''
            row += f'  {sign}{avg:>4.1f}%'
        else:
            row += f'  {"—":>6}'
    total_avg = sum(r['net_pnl'] for r in portfolio_monthly) / len(years) / capital * 100
    sign = '+' if total_avg >= 0 else ''
    row += f'  {sign}{total_avg:>5.1f}%'
    print(row)


# =============================================================================
# RISK SIMULATION
# =============================================================================

def scale_trades(trades, risk_mult):
    """Scale trade P&L by risk multiplier (linear scaling from 1% baseline)."""
    return [{**t, 'pnl': t['pnl'] * risk_mult} for t in trades]


def simulate_portfolio(all_trades, risk_map, capital):
    """Simulate portfolio with specific risk per config, return key metrics."""
    scaled = {}
    for name, trades in all_trades.items():
        mult = risk_map.get(name, 1.0)
        scaled[name] = scale_trades(trades, mult)

    # Combine all trades by month
    all_months = set()
    by_config_month = {}
    for name, trades in scaled.items():
        by_month = defaultdict(list)
        for t in trades:
            key = (t['year'], t['month'])
            by_month[key].append(t['pnl'])
            all_months.add(key)
        by_config_month[name] = by_month

    sorted_months = sorted(all_months)
    equity = capital
    peak = capital
    max_dd = 0
    by_year_pnl = defaultdict(float)
    monthly_rets = []
    worst_month_pnl = 0
    negative_years = 0

    for (year, month) in sorted_months:
        month_pnl = sum(
            sum(by_config_month[name].get((year, month), []))
            for name in scaled
        )
        equity_start = equity
        equity += month_pnl
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak * 100 if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd
        by_year_pnl[year] += month_pnl
        monthly_rets.append(month_pnl / equity_start * 100 if equity_start > 0 else 0)
        if month_pnl < worst_month_pnl:
            worst_month_pnl = month_pnl

    years = sorted(by_year_pnl.keys())
    annual_rets = [by_year_pnl[y] / capital * 100 for y in years]
    negative_years = sum(1 for r in annual_rets if r < 0)
    avg_annual = sum(annual_rets) / len(annual_rets) if annual_rets else 0
    std_annual = (sum((r - avg_annual) ** 2 for r in annual_rets) / len(annual_rets)) ** 0.5 if annual_rets else 0
    worst_year = min(annual_rets) if annual_rets else 0
    total_return = (equity - capital) / capital * 100

    # Monthly std
    avg_mo = sum(monthly_rets) / len(monthly_rets) if monthly_rets else 0
    std_mo = (sum((r - avg_mo) ** 2 for r in monthly_rets) / len(monthly_rets)) ** 0.5 if monthly_rets else 0

    return {
        'total_return': total_return,
        'avg_annual': avg_annual,
        'std_annual': std_annual,
        'max_dd': max_dd,
        'worst_year': worst_year,
        'worst_month_pnl': worst_month_pnl,
        'negative_years': negative_years,
        'avg_monthly': avg_mo,
        'std_monthly': std_mo,
        'final_equity': equity,
        'annual_rets': annual_rets,
        'years': years,
    }


def run_simulation_grid(all_trades, capital):
    """Run a grid of risk allocations and display results."""
    configs = sorted(all_trades.keys())

    # Risk levels to test (as multiplier of baseline 1%)
    risk_levels = [0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60, 0.75, 1.00]

    print(f'\n{"=" * 110}')
    print(f'  RISK SIMULATION GRID — Target: ~15% annual, <10% max DD')
    print(f'  Capital: ${capital:,.0f} | Baseline: 1.00% risk per config')
    print(f'  Each cell shows: Avg Annual% / Max DD% / Worst Year%')
    print('=' * 110)

    # PHASE 1: Uniform risk (same % for all configs)
    print(f'\n  PHASE 1: UNIFORM RISK (same % all configs)')
    print(f'  {"Risk%":>7}  {"Avg/Y":>7}  {"MaxDD":>7}  {"WrstY":>7}  {"StdY":>6}  '
          f'{"NegY":>4}  {"WrstMo":>10}  {"Final$":>12}  {"Verdict":>12}')
    print('-' * 110)

    for risk in risk_levels:
        risk_map = {name: risk for name in configs}
        r = simulate_portfolio(all_trades, risk_map, capital)
        # Verdict
        if r['avg_annual'] >= 12 and r['avg_annual'] <= 20 and r['max_dd'] <= 10:
            verdict = 'TARGET'
        elif r['avg_annual'] >= 10 and r['max_dd'] <= 15:
            verdict = 'acceptable'
        elif r['max_dd'] > 20:
            verdict = 'TOO RISKY'
        else:
            verdict = ''
        print(f'  {risk * 100:>6.2f}%  {r["avg_annual"]:>6.1f}%  {r["max_dd"]:>6.1f}%  '
              f'{r["worst_year"]:>6.1f}%  {r["std_annual"]:>5.1f}%  {r["negative_years"]:>3}   '
              f'${r["worst_month_pnl"]:>9,.0f}  ${r["final_equity"]:>11,.0f}  {verdict:>12}')

    # PHASE 2: Differentiated risk (reduce NI225, keep GDAXI/NDAXI)
    print(f'\n  PHASE 2: DIFFERENTIATED RISK (NI225 reduced, GDAXI/NDAXI equal)')
    print(f'  {"NI225%":>7} {"GD/ND%":>7}  {"Avg/Y":>7}  {"MaxDD":>7}  {"WrstY":>7}  {"StdY":>6}  '
          f'{"NegY":>4}  {"WrstMo":>10}  {"Final$":>12}  {"Verdict":>12}')
    print('-' * 110)

    ni225_levels = [0.10, 0.15, 0.20, 0.25, 0.30]
    other_levels = [0.20, 0.25, 0.30, 0.35, 0.40, 0.50]

    for ni_risk in ni225_levels:
        for other_risk in other_levels:
            risk_map = {
                'NI225_VEGA': ni_risk,
                'GDAXI_VEGA': other_risk,
                'NDAXI_VEGA': other_risk,
            }
            r = simulate_portfolio(all_trades, risk_map, capital)
            if r['avg_annual'] >= 12 and r['avg_annual'] <= 20 and r['max_dd'] <= 10:
                verdict = '** TARGET **'
            elif r['avg_annual'] >= 10 and r['max_dd'] <= 15:
                verdict = 'acceptable'
            elif r['max_dd'] > 20:
                verdict = 'TOO RISKY'
            elif r['avg_annual'] < 8:
                verdict = 'too low'
            else:
                verdict = ''
            # Only print interesting ones
            if r['avg_annual'] >= 8 and r['max_dd'] <= 20:
                print(f'  {ni_risk * 100:>6.2f} {other_risk * 100:>6.2f}%  {r["avg_annual"]:>6.1f}%  '
                      f'{r["max_dd"]:>6.1f}%  {r["worst_year"]:>6.1f}%  {r["std_annual"]:>5.1f}%  '
                      f'{r["negative_years"]:>3}   ${r["worst_month_pnl"]:>9,.0f}  '
                      f'${r["final_equity"]:>11,.0f}  {verdict:>12}')

    # PHASE 3: Fully independent (all three different)
    print(f'\n  PHASE 3: BEST CANDIDATES (fine-tuned)')
    print(f'  {"NI225%":>7} {"GDAXI%":>7} {"NDAXI%":>7}  {"Avg/Y":>7}  {"MaxDD":>7}  {"WrstY":>7}  '
          f'{"StdY":>6}  {"NegY":>4}  {"Final$":>12}  {"Verdict":>12}')
    print('-' * 110)

    # Test fine-grained combos around the sweet spot
    fine = [0.15, 0.20, 0.25, 0.30, 0.35]
    best_score = -999
    best_combo = None

    for ni in fine:
        for gd in fine:
            for nd in fine:
                risk_map = {
                    'NI225_VEGA': ni,
                    'GDAXI_VEGA': gd,
                    'NDAXI_VEGA': nd,
                }
                r = simulate_portfolio(all_trades, risk_map, capital)
                # Score: maximize return while penalizing DD and variance
                # Target: 15% annual, 10% DD
                dd_penalty = max(0, r['max_dd'] - 10) * 3
                low_ret_penalty = max(0, 12 - r['avg_annual']) * 2
                neg_year_penalty = r['negative_years'] * 5
                score = r['avg_annual'] - dd_penalty - low_ret_penalty - neg_year_penalty - r['std_annual'] * 0.3

                if score > best_score:
                    best_score = score
                    best_combo = (ni, gd, nd, r, score)

                # Print good candidates
                if r['avg_annual'] >= 10 and r['max_dd'] <= 12 and r['negative_years'] == 0:
                    if r['avg_annual'] >= 12 and r['max_dd'] <= 10:
                        verdict = '** TARGET **'
                    else:
                        verdict = 'close'
                    print(f'  {ni * 100:>6.2f} {gd * 100:>6.2f}% {nd * 100:>6.2f}%  '
                          f'{r["avg_annual"]:>6.1f}%  {r["max_dd"]:>6.1f}%  {r["worst_year"]:>6.1f}%  '
                          f'{r["std_annual"]:>5.1f}%  {r["negative_years"]:>3}   '
                          f'${r["final_equity"]:>11,.0f}  {verdict:>12}')

    if best_combo:
        ni, gd, nd, r, score = best_combo
        print(f'\n  BEST OVERALL (score={score:.1f}):')
        print(f'    NI225={ni*100:.2f}%  GDAXI={gd*100:.2f}%  NDAXI={nd*100:.2f}%')
        print(f'    Avg/Y={r["avg_annual"]:.1f}%  MaxDD={r["max_dd"]:.1f}%  '
              f'WrstY={r["worst_year"]:.1f}%  StdY={r["std_annual"]:.1f}%  '
              f'NegYears={r["negative_years"]}  Final=${r["final_equity"]:,.0f}')

        # Show yearly breakdown for best combo
        print(f'\n    Yearly breakdown:')
        for year, ret in zip(r['years'], r['annual_rets']):
            bar = '+' * int(ret) if ret >= 0 else '-' * int(abs(ret))
            print(f'      {year}: {ret:>+6.1f}%  {bar}')


# =============================================================================
# AUTO-DETECT LOGS
# =============================================================================

def find_latest_vega_logs(n=3):
    """Find the N most recent VEGA trade logs (from the same portfolio run)."""
    import glob
    pattern = os.path.join(LOG_DIR, 'VEGA_trades_*.txt')
    files = glob.glob(pattern)
    if not files:
        print(f'No VEGA trade logs found in {LOG_DIR}')
        sys.exit(1)

    # Sort by modification time (newest first)
    files.sort(key=os.path.getmtime, reverse=True)

    # Take the N most recent (from the same run)
    return files[:n]


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description='VEGA Monthly Performance Analyzer')
    parser.add_argument('--logs', nargs='+', help='Specific log files to analyze')
    parser.add_argument('--capital', type=float, default=50_000, help='Starting capital (default: 50000)')
    parser.add_argument('--monthly', '-m', action='store_true', help='Show full monthly tables per config')
    parser.add_argument('--yearly', '-y', action='store_true', help='Show yearly summary per config')
    parser.add_argument('--heatmap', action='store_true', help='Show monthly return heatmap')
    parser.add_argument('--all', '-a', action='store_true', help='Show all tables')
    parser.add_argument('--simulate', '-s', action='store_true', help='Run risk allocation simulation grid')
    args = parser.parse_args()

    if args.all:
        args.monthly = True
        args.yearly = True
        args.heatmap = True

    # Default: show comparison + risk summary + heatmap (unless simulate mode)
    show_default = not (args.monthly or args.yearly or args.heatmap or args.simulate)
    if show_default:
        args.heatmap = True

    capital = args.capital

    # Find logs
    if args.logs:
        log_files = []
        for lf in args.logs:
            if os.path.isabs(lf):
                log_files.append(lf)
            else:
                log_files.append(os.path.join(LOG_DIR, lf))
    else:
        log_files = find_latest_vega_logs(n=3)

    print(f'\n{"=" * 70}')
    print(f'  VEGA MONTHLY PERFORMANCE ANALYSIS')
    print(f'  {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print(f'  Capital: ${capital:,.0f}')
    print(f'  Logs: {len(log_files)}')
    print('=' * 70)

    # Parse all logs
    all_trades = {}
    all_monthly = {}
    all_yearly = {}

    for lf in log_files:
        trades, dz, day_filter, atr_filter = parse_vega_log(lf)
        name = identify_config(dz, day_filter, atr_filter, len(trades))
        print(f'  {name}: {len(trades)} trades (DZ={dz})')
        all_trades[name] = trades

        monthly = compute_monthly(trades, capital)
        yearly = compute_yearly_from_monthly(monthly)
        all_monthly[name] = monthly
        all_yearly[name] = yearly

    # Per-config tables
    if args.monthly:
        for name in all_monthly:
            print_monthly_table(name, all_monthly[name], capital)

    if args.yearly:
        for name in all_yearly:
            print_yearly_summary(name, all_yearly[name], capital)

    # Portfolio combined
    portfolio_monthly = combine_portfolio(all_trades, capital)

    # Always show comparison and risk summary
    print_config_comparison(all_yearly, capital)
    print_risk_summary(all_monthly, portfolio_monthly, capital)

    if args.heatmap:
        print_portfolio_monthly_heatmap(portfolio_monthly, capital)

    # Risk simulation
    if args.simulate:
        run_simulation_grid(all_trades, capital)

    print()


if __name__ == '__main__':
    main()
