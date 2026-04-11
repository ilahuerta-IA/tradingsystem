"""
ALTAIR Portfolio Robustness Check

Runs deep analysis on all active ALTAIR assets with their config params.
Applies the 10-criteria checklist from compare_robustness.py adapted to
individual stock backtests (no log comparison needed -- single-period mode).

Metrics per stock:
  PF, WR%, MaxDD, Sharpe, Sortino, Calmar, CAGR, MC95/MC99, Trades/Year,
  Dominant Year %, Negative Years, Yearly PnL breakdown.

Quality gates (from CONTEXT.md checklist + portfolio specs 2026-04-11):
  PASS:    PF >= 1.30 AND Sharpe >= 0.30 AND DD < 15% AND MC95 < 20%
           AND dominant < 50% AND neg_years <= 1
           AND sector diversifies (not redundant with existing portfolio)
  DISCARD: PF < 1.0 OR Sharpe < 0.30 OR DD > 25% OR neg_years >= 4
  NOTE:    OOS = live demo only (too few trades for statistical OOS split)

Optional: --exclude NVDA,NSC to test portfolio resilience without top performers.

Usage:
    python tools/altair_robustness_check.py
    python tools/altair_robustness_check.py --exclude NVDA,NSC
"""
import sys
import os
import io
import math
import random
import contextlib
import warnings
from datetime import datetime
from collections import defaultdict

import numpy as np
import backtrader as bt
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

warnings.filterwarnings('ignore')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
sys.path.insert(0, PROJECT_ROOT)

from pathlib import Path
from strategies.altair_strategy import ALTAIRStrategy
from lib.commission import ETFCommission, ETFCSVData
from config.settings_altair import (
    ALTAIR_STRATEGIES_CONFIG, ALTAIR_BROKER_CONFIG,
)

STARTING_CASH = 100_000.0
MC_SIMULATIONS = 10_000
RISK_FREE_RATE = 0.0

# Quality gates for ALTAIR IS (no WF optimization done yet)
# Post-OOS thresholds (PF>1.5, Sharpe>1.0) NOT applicable here.
# IS minimum from CONTEXT.md: PF >= 1.30
# Priority: yearly consistency (all years positive) > raw PF/Sharpe
# Portfolio specs (2026-04-11):
#   - Sharpe >= 0.30 minimum (below = unstable equity curve)
#   - Must diversify: redundant sector concentration = reject
#   - OOS = live demo only (too few IS trades for statistical split)
CHECK_PF_MIN = 1.30
CHECK_SHARPE_MIN = 0.30
CHECK_DD_MAX = 15.0
CHECK_MC95_MAX = 20.0
CHECK_DOMINANT_YEAR_MAX = 50.0  # relaxed: fewer years = higher natural dominance
CHECK_NEGATIVE_YEARS_MAX = 1   # sweet spot: prefer ALL years positive

# Immediate discard thresholds
DISCARD_PF = 1.0
DISCARD_SHARPE = 0.30  # hard floor: below this = noise, not edge
DISCARD_DD = 25.0
DISCARD_NEG_YEARS = 4  # with 6-8yr history, 3 neg is borderline

# Sector mapping (for display)
SECTORS = {
    'NVDA': 'Semiconductors', 'AMAT': 'Semiconductors', 'AMD': 'Semiconductors',
    'AVGO': 'Semiconductors', 'GOOGL': 'Tech/Search', 'MSFT': 'Tech/Software',
    'NFLX': 'Streaming', 'CAT': 'Industrial', 'V': 'Payments',
    'JPM': 'Banking', 'AXP': 'Finance', 'GS': 'Inv. Banking',
    'NSC': 'Railroad', 'CAH': 'Healthcare Dist', 'FDX': 'Logistics',
    'VLO': 'Energy/Refining', 'EFX': 'Data/Analytics', 'MPC': 'Energy/Refining',
    'PGR': 'Insurance',
}


def run_bt(asset_name, asset_cfg):
    """Run one ALTAIR BT using the asset's own config params."""
    try:
        cerebro = bt.Cerebro(stdstats=False)
        data_path = Path(PROJECT_ROOT) / asset_cfg['data_path']
        data = ETFCSVData(
            dataname=str(data_path),
            dtformat='%Y%m%d', tmformat='%H:%M:%S',
            datetime=0, time=1, open=2, high=3, low=4, close=5,
            volume=6, openinterest=-1,
            fromdate=asset_cfg['from_date'], todate=asset_cfg['to_date'],
        )
        cerebro.adddata(data, name=asset_name)
        cerebro.broker.setcash(STARTING_CASH)

        broker_cfg = ALTAIR_BROKER_CONFIG.get('darwinex_zero_stock', {})
        ETFCommission.total_commission = 0.0
        ETFCommission.total_contracts = 0.0
        ETFCommission.commission_calls = 0
        commission = ETFCommission(
            commission=broker_cfg.get('commission_per_contract', 0.02),
            margin_pct=broker_cfg.get('margin_percent', 20.0),
        )
        cerebro.broker.addcommissioninfo(commission)

        params = dict(asset_cfg['params'])
        params['export_reports'] = False
        params['print_signals'] = False
        cerebro.addstrategy(ALTAIRStrategy, **params)

        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            results = cerebro.run()

        strat = results[0]
        return extract(strat, cerebro)
    except Exception as e:
        return {'error': str(e)}


def extract(strat, cerebro):
    fv = cerebro.broker.getvalue()
    pnl = fv - STARTING_CASH
    t = strat.total_trades
    w = strat.wins
    gp = strat.gross_profit
    gl = strat.gross_loss
    wr = (w / t * 100) if t > 0 else 0
    pf = (gp / gl) if gl > 0 else (float('inf') if gp > 0 else 0)

    # Portfolio values for DD, Sharpe, Sortino
    pv = list(strat._portfolio_values) if strat._portfolio_values else [STARTING_CASH]

    # Max DD
    dd = 0.0
    peak = pv[0]
    for v in pv:
        if v > peak:
            peak = v
        d = (peak - v) / peak * 100.0
        if d > dd:
            dd = d

    # Date range
    first_dt = strat._first_bar_dt
    last_dt = strat._last_bar_dt
    if first_dt and last_dt:
        days = (last_dt - first_dt).days
        years = max(days / 365.25, 0.5)
    else:
        years = 1.0

    # CAGR
    final_value = STARTING_CASH + pnl
    cagr = (final_value / STARTING_CASH) ** (1.0 / years) - 1.0

    # Returns from trade PnLs
    trade_pnls = [tp['pnl'] for tp in strat._trade_pnls]
    returns = [p / STARTING_CASH for p in trade_pnls]

    # Sharpe (annualized from trade returns)
    sharpe = 0.0
    if len(returns) > 1:
        avg_r = np.mean(returns)
        std_r = np.std(returns, ddof=1)
        tpy = t / years
        if std_r > 0:
            sharpe = (avg_r / std_r) * math.sqrt(tpy)

    # Sortino (downside deviation only)
    sortino = 0.0
    downside = [r for r in returns if r < 0]
    if downside and len(downside) > 1:
        avg_r = np.mean(returns)
        dd_dev = math.sqrt(sum(r**2 for r in downside) / len(downside))
        tpy = t / years
        if dd_dev > 0:
            sortino = (avg_r / dd_dev) * math.sqrt(tpy)

    # Calmar = CAGR / MaxDD
    calmar = (cagr * 100) / dd if dd > 0 else 0

    # Monte Carlo DD (10k sims, shuffle trade PnLs)
    mc_dds = []
    random.seed(42)
    for _ in range(MC_SIMULATIONS):
        shuffled = random.sample(trade_pnls, len(trade_pnls))
        eq = STARTING_CASH
        pk = eq
        sim_dd = 0.0
        for p in shuffled:
            eq += p
            pk = max(pk, eq)
            d = (pk - eq) / pk * 100 if pk > 0 else 0
            sim_dd = max(sim_dd, d)
        mc_dds.append(sim_dd)
    mc_dds.sort()
    mc95 = mc_dds[int(0.95 * len(mc_dds))] if mc_dds else 0
    mc99 = mc_dds[int(0.99 * len(mc_dds))] if mc_dds else 0

    # Yearly PnL
    yearly = defaultdict(lambda: {'trades': 0, 'wins': 0, 'pnl': 0.0,
                                   'gp': 0.0, 'gl': 0.0, 'trade_pnls': []})
    for tp in strat._trade_pnls:
        y = tp['year']
        yearly[y]['trades'] += 1
        yearly[y]['pnl'] += tp['pnl']
        yearly[y]['trade_pnls'].append(tp['pnl'])
        if tp['is_winner']:
            yearly[y]['wins'] += 1
            yearly[y]['gp'] += tp['pnl']
        else:
            yearly[y]['gl'] += abs(tp['pnl'])

    yearly_dict = {}
    neg_years = 0
    pos_years = 0
    for y in sorted(yearly.keys()):
        s = yearly[y]
        y_pf = (s['gp'] / s['gl']) if s['gl'] > 0 else (
            float('inf') if s['gp'] > 0 else 0)
        y_wr = (s['wins'] / s['trades'] * 100) if s['trades'] > 0 else 0

        # Per-year Sharpe from trade returns
        y_sharpe = 0.0
        y_rets = [p / STARTING_CASH for p in s['trade_pnls']]
        if len(y_rets) > 1:
            avg = np.mean(y_rets)
            std = np.std(y_rets, ddof=1)
            if std > 0:
                y_sharpe = (avg / std) * math.sqrt(len(y_rets))

        # Per-year MaxDD from trade-by-trade equity
        y_dd = 0.0
        eq = STARTING_CASH
        pk = eq
        for p in s['trade_pnls']:
            eq += p
            pk = max(pk, eq)
            d = (pk - eq) / pk * 100 if pk > 0 else 0
            y_dd = max(y_dd, d)

        # Per-year Sortino (downside deviation)
        y_sortino = 0.0
        y_down = [r for r in y_rets if r < 0]
        if y_down and len(y_down) > 1:
            avg = np.mean(y_rets)
            dd_dev = math.sqrt(sum(r**2 for r in y_down) / len(y_down))
            if dd_dev > 0:
                y_sortino = (avg / dd_dev) * math.sqrt(len(y_rets))

        yearly_dict[y] = {
            'trades': s['trades'], 'wins': s['wins'], 'wr': y_wr,
            'pnl': s['pnl'], 'pf': y_pf, 'gp': s['gp'], 'gl': s['gl'],
            'sharpe': y_sharpe, 'sortino': y_sortino, 'dd': y_dd,
        }
        if s['pnl'] < 0:
            neg_years += 1
        else:
            pos_years += 1

    # Dominant year %
    if pnl > 0:
        max_year_pnl = max((yd['pnl'] for yd in yearly_dict.values()), default=0)
        dominant_pct = max_year_pnl / pnl * 100 if pnl > 0 else 0
    else:
        dominant_pct = 0

    return {
        'trades': t, 'wins': w, 'wr': wr, 'pf': pf,
        'net_pnl': pnl, 'max_dd': dd,
        'sharpe': sharpe, 'sortino': sortino, 'calmar': calmar,
        'cagr': cagr * 100,
        'mc95': mc95, 'mc99': mc99,
        'mc_ratio': mc95 / dd if dd > 0 else 0,
        'years': years, 'trades_per_year': t / years,
        'yearly': yearly_dict,
        'neg_years': neg_years, 'pos_years': pos_years,
        'total_years': len(yearly_dict),
        'dominant_pct': dominant_pct,
        'trade_pnls_raw': [(tp['date'], tp['pnl']) for tp in strat._trade_pnls],
        'commission': ETFCommission.total_commission,
    }


def check_quality(m):
    """Apply quality gates for ALTAIR IS.

    Priority order:
      1. Yearly consistency (all years positive = sweet spot)
      2. PF >= 1.30 (IS minimum)
      3. DD manageable
      4. Monte Carlo stable
    """
    fails = []

    # Immediate discard
    if m['pf'] < DISCARD_PF:
        return 'DISCARD', ['PF < 1.0']
    if m['sharpe'] < DISCARD_SHARPE:
        return 'DISCARD', ['Sharpe < 0.30']
    if m['max_dd'] > DISCARD_DD:
        return 'DISCARD', ['DD > 25%']
    if m['neg_years'] >= DISCARD_NEG_YEARS:
        return 'DISCARD', ['neg_years >= 4']

    # Quality checks (IS level)
    if m['pf'] < CHECK_PF_MIN:
        fails.append('PF < 1.30')
    if m['sharpe'] < CHECK_SHARPE_MIN:
        fails.append('Sharpe < 0.30')
    if m['max_dd'] > CHECK_DD_MAX:
        fails.append('DD > 15%')
    if m['mc95'] > CHECK_MC95_MAX:
        fails.append('MC95 > 20%')
    if m['dominant_pct'] > CHECK_DOMINANT_YEAR_MAX:
        fails.append('DomYear > 50%')
    if m['neg_years'] > CHECK_NEGATIVE_YEARS_MAX:
        fails.append('NegYrs > 1')

    # Consistency bonus: if ALL years positive, relax PF threshold slightly
    all_positive = m['neg_years'] == 0 and m['total_years'] >= 4

    if not fails:
        return 'PASS', []
    elif all_positive and len(fails) == 1 and 'PF < 1.30' in fails:
        return 'REVIEW', fails + ['but ALL years positive']
    elif len(fails) <= 2:
        return 'REVIEW', fails
    else:
        return 'FAIL', fails


def fmt_pf(pf):
    return '%.2f' % pf if pf < 100 else 'INF'


def main():
    # Parse --exclude argument
    exclude = set()
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == '--exclude' and i + 1 < len(args):
            exclude = set(args[i + 1].upper().split(','))

    # Load all active assets
    assets = {}
    for key, cfg in ALTAIR_STRATEGIES_CONFIG.items():
        if not cfg.get('active', True):
            continue
        name = cfg['asset_name']
        if name in exclude:
            continue
        assets[name] = {
            'data_path': cfg['data_path'],
            'from_date': cfg['from_date'],
            'to_date': cfg['to_date'],
            'universe': cfg.get('universe', 'ndx'),
            'params': cfg.get('params', {}),
        }

    names = sorted(assets.keys())

    print('=' * 110)
    print('ALTAIR PORTFOLIO ROBUSTNESS CHECK')
    print('=' * 110)
    if exclude:
        print('EXCLUDED: %s' % ', '.join(sorted(exclude)))
    print('Active assets (%d): %s' % (len(names), ', '.join(names)))
    print('Quality gates (IS): PF>=1.30 DD<15%% MC95<20%% DomYr<50%% NegYr<=1')
    print('Discard: PF<1.0 OR DD>25%% OR NegYr>=4')
    print('PRIORITY: yearly consistency (all years+) > raw PF/Sharpe')
    print('=' * 110)

    # Run all BTs
    results = {}
    for name in names:
        cfg = assets[name]
        univ = cfg['universe'].upper()
        m = run_bt(name, cfg)
        results[name] = m
        if 'error' in m:
            print('  %-6s [%s] -> ERROR: %s' % (name, univ, m['error']))
        else:
            print('  %-6s [%-4s] T=%2d PF=%5s WR=%4.1f%% DD=%5.2f%% Sh=%5.2f So=%5.2f'
                  % (name, univ, m['trades'], fmt_pf(m['pf']), m['wr'],
                     m['max_dd'], m['sharpe'], m['sortino']))

    # Collect all years
    all_years = set()
    for m in results.values():
        if 'error' not in m:
            all_years.update(m['yearly'].keys())
    years = sorted(all_years)

    # Rank all stocks by PF (used across all sections)
    ranked = sorted(
        [(n, results[n]) for n in names if 'error' not in results[n]],
        key=lambda x: -x[1]['pf'] if x[1]['pf'] < 100 else -99
    )

    # =========================================================================
    # 0. DATA OVERVIEW -- periods, active years, trades/year detail
    # =========================================================================
    print('\n' + '=' * 130)
    print('0. DATA OVERVIEW (period, active years, trades/year)')
    print('=' * 130)
    hdr0 = '%-6s %-5s %-16s %-7s %-10s  %4s  %4s  %4s  %4s' % (
        'Stock', 'Univ', 'Sector', 'Config', 'Data Period', 'DataY', 'ActY', 'Trd', 'T/Y')
    for y in years:
        hdr0 += ' %4d' % y
    print(hdr0)
    print('-' * len(hdr0))

    for name, m in ranked:
        univ = assets[name]['universe'].upper()
        sector = SECTORS.get(name, '?')
        from_d = assets[name]['from_date']
        to_d = assets[name]['to_date']
        period_str = '%s-%s' % (from_d.strftime('%Y'), to_d.strftime('%Y'))
        data_years = (to_d - from_d).days / 365.25

        # Config label
        p = assets[name]['params']
        if p.get('max_sl_atr_mult', 2.0) == 4.0:
            cfg_label = 'B(DJ30)'
        else:
            cfg_label = 'A(NDX)'

        active_yrs = len([y for y in m['yearly'] if m['yearly'][y]['trades'] > 0])

        row = '%-6s %-5s %-16s %-7s %-10s  %4.1f  %4d  %4d  %4.1f' % (
            name, univ, sector[:16], cfg_label, period_str,
            data_years, active_yrs, m['trades'], m['trades_per_year'])
        for y in years:
            yd = m['yearly'].get(y, {})
            t_y = yd.get('trades', 0)
            if t_y == 0:
                row += '   --'
            else:
                row += ' %4d' % t_y
        print(row)

    # Summary
    total_trades = sum(results[n]['trades'] for n in names if 'error' not in results[n])
    print('-' * len(hdr0))
    row = '%-6s %-5s %-16s %-7s %-10s  %4s  %4s  %4d  %4.1f' % (
        'TOTAL', '', '', '', '', '', '',
        total_trades, total_trades / max(len(years), 1))
    for y in years:
        y_t = sum(results[n]['yearly'].get(y, {}).get('trades', 0)
                  for n in names if 'error' not in results[n])
        row += ' %4d' % y_t
    print(row)

    # =========================================================================
    # 1. DEEP METRICS TABLE (all stocks ranked by PF)
    # =========================================================================
    print('\n' + '=' * 130)
    print('1. DEEP METRICS (ranked by PF)')
    print('=' * 130)
    hdr = '%-6s %-5s %-16s %3s %5s %4s %5s %5s %5s %5s %5s %5s %5s %4s %4s %3s  %s' % (
        'Stock', 'Univ', 'Sector', 'Trd', 'PF', 'WR%', 'DD%',
        'Shrp', 'Sort', 'Calm', 'CAGR', 'MC95', 'MC99', 'T/Y', 'Dom%', 'NY', 'VERDICT')
    print(hdr)
    print('-' * len(hdr))

    for name, m in ranked:
        univ = assets[name]['universe'].upper()
        sector = SECTORS.get(name, '?')
        verdict, fails = check_quality(m)

        verdict_str = verdict
        if fails:
            verdict_str += ' (%s)' % ', '.join(fails)

        print('%-6s %-5s %-16s %3d %5s %4.1f %5.2f %5.2f %5.2f %5.2f %5.1f %5.1f %5.1f %4.1f %4.0f %3d  %s'
              % (name, univ, sector[:16], m['trades'], fmt_pf(m['pf']),
                 m['wr'], m['max_dd'], m['sharpe'], m['sortino'],
                 m['calmar'], m['cagr'], m['mc95'], m['mc99'],
                 m['trades_per_year'], m['dominant_pct'], m['neg_years'],
                 verdict_str))

    # Compute total_pnl and yearly_totals for use below
    total_pnl = sum(m['net_pnl'] for _, m in ranked)
    yearly_totals = {}
    for y in years:
        yearly_totals[y] = sum(
            results[n]['yearly'].get(y, {}).get('pnl', 0)
            for n in names if 'error' not in results[n])

    # =========================================================================
    # 2. UNIFIED YEARLY TABLE + HEATMAP IMAGE + EQUITY CURVES
    # =========================================================================
    metrics_list = ['PnL', 'Trd', 'WR%', 'PF', 'Shrp', 'Sort', 'DD%']
    yr_cols = ['%d' % y for y in years]

    # --- 2a. Console unified table ---
    print('\n' + '=' * (10 + 9 * len(years) + 12))
    print('2. UNIFIED YEARLY TABLE (all metrics per stock)')
    print('=' * (10 + 9 * len(years) + 12))

    hdr_line = '%-6s %-5s' % ('Stock', 'Metr')
    for y in years:
        hdr_line += ' %8d' % y
    hdr_line += ' %10s' % 'TOTAL'
    print(hdr_line)
    sep = '-' * len(hdr_line)

    for name, m in ranked:
        print(sep)
        for mi, metric in enumerate(metrics_list):
            label = name if mi == 0 else ''
            row = '%-6s %-5s' % (label, metric)
            for y in years:
                yd = m['yearly'].get(y, {})
                t_y = yd.get('trades', 0)
                if t_y == 0:
                    row += '       --'
                else:
                    if metric == 'PnL':
                        row += ' %+8.0f' % yd.get('pnl', 0)
                    elif metric == 'Trd':
                        row += ' %8d' % t_y
                    elif metric == 'WR%':
                        row += ' %7.1f%%' % yd.get('wr', 0)
                    elif metric == 'PF':
                        row += ' %8s' % fmt_pf(yd.get('pf', 0))
                    elif metric == 'Shrp':
                        row += ' %8.2f' % yd.get('sharpe', 0)
                    elif metric == 'Sort':
                        row += ' %8.2f' % yd.get('sortino', 0)
                    elif metric == 'DD%':
                        row += ' %7.2f%%' % yd.get('dd', 0)
            # TOTAL column
            if metric == 'PnL':
                row += ' %+10.0f' % m['net_pnl']
            elif metric == 'Trd':
                row += ' %10d' % m['trades']
            elif metric == 'WR%':
                row += ' %9.1f%%' % m['wr']
            elif metric == 'PF':
                row += ' %10s' % fmt_pf(m['pf'])
            elif metric == 'Shrp':
                row += ' %10.2f' % m['sharpe']
            elif metric == 'Sort':
                row += ' %10.2f' % m['sortino']
            elif metric == 'DD%':
                row += ' %9.2f%%' % m['max_dd']
            print(row)

    # Portfolio totals
    print(sep)
    t_trades = sum(m['trades'] for _, m in ranked)
    for mi, metric in enumerate(metrics_list):
        label = 'PORT' if mi == 0 else ''
        row = '%-6s %-5s' % (label, metric)
        for y in years:
            y_trd = sum(results[n]['yearly'].get(y, {}).get('trades', 0)
                        for n in names if 'error' not in results[n])
            if metric == 'PnL':
                row += ' %+8.0f' % yearly_totals[y]
            elif metric == 'Trd':
                row += ' %8d' % y_trd
            else:
                # Average of active stocks that year
                vals = []
                for n, m2 in ranked:
                    yd = m2['yearly'].get(y, {})
                    if yd.get('trades', 0) > 0:
                        if metric == 'WR%':
                            vals.append(yd.get('wr', 0))
                        elif metric == 'PF':
                            pf_v = yd.get('pf', 0)
                            vals.append(min(pf_v, 50))
                        elif metric == 'Shrp':
                            vals.append(yd.get('sharpe', 0))
                        elif metric == 'Sort':
                            vals.append(yd.get('sortino', 0))
                        elif metric == 'DD%':
                            vals.append(yd.get('dd', 0))
                if vals:
                    avg = np.mean(vals)
                    if metric == 'WR%':
                        row += ' %7.1f%%' % avg
                    elif metric == 'PF':
                        row += ' %8s' % fmt_pf(avg)
                    elif metric in ('Shrp', 'Sort'):
                        row += ' %8.2f' % avg
                    elif metric == 'DD%':
                        row += ' %7.2f%%' % avg
                else:
                    row += '       --'
        # TOTAL column
        if metric == 'PnL':
            row += ' %+10.0f' % total_pnl
        elif metric == 'Trd':
            row += ' %10d' % t_trades
        elif metric == 'WR%':
            row += ' %9.1f%%' % float(np.mean([m['wr'] for _, m in ranked]))
        elif metric == 'PF':
            row += ' %10s' % fmt_pf(float(np.median([min(m['pf'], 99) for _, m in ranked])))
        elif metric == 'Shrp':
            row += ' %10.2f' % float(np.mean([m['sharpe'] for _, m in ranked]))
        elif metric == 'Sort':
            row += ' %10.2f' % float(np.mean([m['sortino'] for _, m in ranked]))
        elif metric == 'DD%':
            row += ' %9.2f%%' % max(m['max_dd'] for _, m in ranked)
        print(row)
    print(sep)

    # Commission summary
    total_comm = sum(results[n].get('commission', 0) for n in names if 'error' not in results[n])
    total_gross = total_pnl + total_comm
    print('\n  COMISIONES: Total=$%.0f | PnL bruto=$%+.0f | PnL neto=$%+.0f | Impacto=%.1f%%'
          % (total_comm, total_gross, total_pnl,
             total_comm / total_gross * 100 if total_gross != 0 else 0))
    for name, m in ranked:
        comm = m.get('commission', 0)
        gross = m['net_pnl'] + comm
        print('    %-6s: Comis=$%.0f  Bruto=$%+.0f  Neto=$%+.0f'
              % (name, comm, gross, m['net_pnl']))

    # --- 2b. PnL Heatmap image ---
    out_dir = Path(PROJECT_ROOT) / 'images' / 'altair_robustness'
    out_dir.mkdir(parents=True, exist_ok=True)

    stock_names = [n for n, _ in ranked]
    n_stocks = len(stock_names)
    n_years = len(years)

    pnl_matrix = np.zeros((n_stocks, n_years))
    for i, (name, m) in enumerate(ranked):
        for j, y in enumerate(years):
            yd = m['yearly'].get(y, {})
            if yd.get('trades', 0) > 0:
                pnl_matrix[i, j] = yd.get('pnl', 0)
            else:
                pnl_matrix[i, j] = np.nan

    fig, ax = plt.subplots(figsize=(max(14, n_years * 1.8), max(8, n_stocks * 0.6)))
    vmax = max(abs(np.nanmin(pnl_matrix)), abs(np.nanmax(pnl_matrix)))
    im = ax.imshow(pnl_matrix, cmap='RdYlGn', aspect='auto',
                   vmin=-vmax, vmax=vmax)

    ax.set_xticks(range(n_years))
    ax.set_xticklabels(yr_cols, fontsize=11, fontweight='bold')
    ax.set_yticks(range(n_stocks))
    ylabels = []
    for name, m in ranked:
        verdict, _ = check_quality(m)
        ylabels.append('%s (PF %s)' % (name, fmt_pf(m['pf'])))
    ax.set_yticklabels(ylabels, fontsize=10)

    # Annotate cells with PnL + Trades
    for i, (name, m) in enumerate(ranked):
        for j, y in enumerate(years):
            yd = m['yearly'].get(y, {})
            t_y = yd.get('trades', 0)
            if t_y == 0:
                ax.text(j, i, '--', ha='center', va='center',
                        fontsize=8, color='gray')
            else:
                pnl_v = yd.get('pnl', 0)
                color = 'white' if abs(pnl_v) > vmax * 0.5 else 'black'
                ax.text(j, i, '%+.0f\n(%d t)' % (pnl_v, t_y),
                        ha='center', va='center', fontsize=7.5,
                        fontweight='bold', color=color)

    # Yearly totals at bottom
    for j, y in enumerate(years):
        ax.text(j, n_stocks - 0.3, '%+.0fK' % (yearly_totals[y] / 1000),
                ha='center', va='top', fontsize=8, fontweight='bold',
                color='navy', style='italic')

    plt.colorbar(im, ax=ax, label='PnL ($)', shrink=0.8)
    ax.set_title('ALTAIR Portfolio — PnL Heatmap by Stock & Year (net of commissions)',
                 fontsize=13, fontweight='bold', pad=12)
    fig.tight_layout()
    heatmap_path = out_dir / 'pnl_heatmap.png'
    fig.savefig(str(heatmap_path), dpi=150, bbox_inches='tight')
    plt.close(fig)
    print('\n  Heatmap guardado: %s' % heatmap_path)

    # --- 2c. Equity curves (cumulative PnL per stock) ---
    fig2, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 12),
                                     gridspec_kw={'height_ratios': [3, 1]})

    # Top: individual equity curves
    colors = plt.cm.tab20(np.linspace(0, 1, n_stocks))
    portfolio_trades = []  # (date, pnl) across all stocks
    for i, (name, m) in enumerate(ranked):
        tpnls = m.get('trade_pnls_raw', [])
        if not tpnls:
            continue
        sorted_trades = sorted(tpnls, key=lambda x: x[0])
        dates = [t[0] for t in sorted_trades]
        cum_pnl = np.cumsum([t[1] for t in sorted_trades])
        ax1.plot(dates, cum_pnl, label='%s (%+.0fK)' % (name, m['net_pnl'] / 1000),
                 color=colors[i], linewidth=1.3, alpha=0.85)
        portfolio_trades.extend(sorted_trades)

    ax1.axhline(y=0, color='black', linewidth=0.5, linestyle='--')
    ax1.set_title('ALTAIR — Cumulative PnL per Stock (net of $%.0f commissions)'
                  % total_comm, fontsize=13, fontweight='bold')
    ax1.set_ylabel('Cumulative PnL ($)', fontsize=11)
    ax1.legend(loc='upper left', fontsize=7.5, ncol=3, framealpha=0.9)
    ax1.grid(True, alpha=0.3)
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(
        lambda x, p: '${:,.0f}'.format(x)))

    # Bottom: portfolio aggregate equity curve
    if portfolio_trades:
        portfolio_trades.sort(key=lambda x: x[0])
        p_dates = [t[0] for t in portfolio_trades]
        p_cum = np.cumsum([t[1] for t in portfolio_trades])
        ax2.fill_between(p_dates, 0, p_cum, alpha=0.3, color='green',
                         where=[v >= 0 for v in p_cum])
        ax2.fill_between(p_dates, 0, p_cum, alpha=0.3, color='red',
                         where=[v < 0 for v in p_cum])
        ax2.plot(p_dates, p_cum, color='darkgreen', linewidth=1.5)
        ax2.axhline(y=0, color='black', linewidth=0.5, linestyle='--')
        ax2.set_title('Portfolio Aggregate (%d stocks, %d trades, $%+.0f)'
                      % (n_stocks, t_trades, total_pnl),
                      fontsize=11, fontweight='bold')
        ax2.set_ylabel('Portfolio PnL ($)', fontsize=10)
        ax2.grid(True, alpha=0.3)
        ax2.yaxis.set_major_formatter(mticker.FuncFormatter(
            lambda x, p: '${:,.0f}'.format(x)))

    fig2.tight_layout()
    equity_path = out_dir / 'equity_curves.png'
    fig2.savefig(str(equity_path), dpi=150, bbox_inches='tight')
    plt.close(fig2)
    print('  Equity curves guardado: %s' % equity_path)

    # =========================================================================
    # 3. OFFSET ANALYSIS: who profits when portfolio loses?
    # =========================================================================
    print('\n' + '=' * 110)
    print('3. OFFSET ANALYSIS: Profitable when portfolio year is negative')
    print('=' * 110)

    neg_portfolio_years = [y for y in years if yearly_totals.get(y, 0) < 0]
    if neg_portfolio_years:
        print('Negative portfolio years: %s' % neg_portfolio_years)
        hdr3 = '%-6s' % 'Stock'
        for y in neg_portfolio_years:
            hdr3 += ' %8d' % y
        hdr3 += '  Offsets?'
        print(hdr3)
        print('-' * len(hdr3))

        for name, m in ranked:
            row = '%-6s' % name
            offsets = 0
            for y in neg_portfolio_years:
                yd = m['yearly'].get(y, {})
                p = yd.get('pnl', 0)
                row += ' %+7.0f ' % p
                if p > 0:
                    offsets += 1
            row += '  %s' % ('YES (%d/%d)' % (offsets, len(neg_portfolio_years))
                             if offsets > 0 else 'NO')
            print(row)
    else:
        print('No negative portfolio years -- all years positive!')

    # =========================================================================
    # 4. PORTFOLIO AGGREGATE (with and without top performers)
    # =========================================================================
    print('\n' + '=' * 110)
    print('4. PORTFOLIO AGGREGATE')
    print('=' * 110)

    # Build groups
    all_stocks = [n for n, _ in ranked]
    top_performers = set()
    # Identify top performers by PnL contribution
    pnl_sorted = sorted(ranked, key=lambda x: -x[1]['net_pnl'])
    if len(pnl_sorted) >= 4:
        # Top 2 by PnL are "potential dominators"
        top_performers = {pnl_sorted[0][0], pnl_sorted[1][0]}

    groups = [
        ('ALL (%d)' % len(all_stocks), all_stocks),
    ]
    if top_performers:
        without = [n for n in all_stocks if n not in top_performers]
        groups.append(
            ('WITHOUT %s (%d)' % ('+'.join(sorted(top_performers)), len(without)),
             without)
        )

    for group_name, group_stocks in groups:
        print('\n--- %s ---' % group_name)

        pfs = []
        total_pnl_g = 0
        total_trades_g = 0
        worst_dd = 0
        sharpes = []
        sortinos = []

        for name in group_stocks:
            m = results[name]
            pfs.append(min(m['pf'], 99))
            total_pnl_g += m['net_pnl']
            total_trades_g += m['trades']
            sharpes.append(m['sharpe'])
            sortinos.append(m['sortino'])
            if m['max_dd'] > worst_dd:
                worst_dd = m['max_dd']

        # Yearly aggregates
        g_yearly = {}
        for y in years:
            y_pnl = sum(results[n]['yearly'].get(y, {}).get('pnl', 0) for n in group_stocks)
            g_yearly[y] = y_pnl

        g_pos_years = sum(1 for p in g_yearly.values() if p > 0)
        g_neg_years = sum(1 for p in g_yearly.values() if p < 0)

        print('  Assets: %d | Trades: %d | medPF: %s | mSharpe: %.2f | mSortino: %.2f'
              % (len(group_stocks), total_trades_g, fmt_pf(float(np.median(pfs))),
                 float(np.mean(sharpes)), float(np.mean(sortinos))))
        print('  TotalPnL: $%+.0f | worstDD: %.1f%% | Years+: %d/%d'
              % (total_pnl_g, worst_dd, g_pos_years, len(years)))

        # Yearly row
        row = '  Yearly: '
        for y in years:
            row += '%d:%+.0f  ' % (y, g_yearly[y])
        print(row)

    # =========================================================================
    # 5. VERDICT SUMMARY
    # =========================================================================
    print('\n' + '=' * 110)
    print('5. VERDICT SUMMARY')
    print('=' * 110)

    pass_count = 0
    review_count = 0
    fail_count = 0

    for name, m in ranked:
        verdict, fails = check_quality(m)
        sector = SECTORS.get(name, '?')
        status = {
            'PASS': 'PASS  ',
            'REVIEW': 'REVIEW',
            'FAIL': 'FAIL  ',
            'DISCARD': 'DISCARD',
        }.get(verdict, verdict)

        if verdict == 'PASS':
            pass_count += 1
        elif verdict == 'REVIEW':
            review_count += 1
        else:
            fail_count += 1

        detail = ', '.join(fails) if fails else 'All criteria met'
        print('  %-6s %-16s  %s  %s' % (name, sector, status, detail))

    print('\nPASS: %d | REVIEW: %d | FAIL/DISCARD: %d' % (pass_count, review_count, fail_count))
    print('=' * 110)


if __name__ == '__main__':
    main()
