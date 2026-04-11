"""
ALTAIR SP500 Tier 1-HIGH -- Config A vs Config B Comparison

Runs all SP500 stocks from settings_altair.py with:
  Config A (NDX defaults): max_sl_atr_mult=2.0, dtosc_os=25
  Config B (DJ30 override): max_sl_atr_mult=4.0, dtosc_os=20

Compares per-stock PF, WR%, MaxDD%, net PnL and recommends best config.

Usage:
    python tools/altair_sp500_ab_test.py
"""
import sys
import os
import io
import contextlib
import warnings
from datetime import datetime
from collections import defaultdict

import numpy as np
import backtrader as bt

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

CONFIG_A = {'max_sl_atr_mult': 2.0, 'dtosc_os': 25}  # NDX defaults
CONFIG_B = {'max_sl_atr_mult': 4.0, 'dtosc_os': 20}  # DJ30 override


def run_bt(asset_name, asset_cfg, override_params=None):
    """Run one ALTAIR BT with optional param overrides."""
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
        if override_params:
            params.update(override_params)
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

    dd = 0.0
    if strat._portfolio_values:
        peak = strat._portfolio_values[0]
        for v in strat._portfolio_values:
            if v > peak:
                peak = v
            d = (peak - v) / peak * 100.0
            if d > dd:
                dd = d

    # Yearly PnL
    yearly = defaultdict(lambda: {'trades': 0, 'wins': 0, 'pnl': 0.0,
                                   'gp': 0.0, 'gl': 0.0})
    for tp in strat._trade_pnls:
        y = tp['year']
        yearly[y]['trades'] += 1
        yearly[y]['pnl'] += tp['pnl']
        if tp['is_winner']:
            yearly[y]['wins'] += 1
            yearly[y]['gp'] += tp['pnl']
        else:
            yearly[y]['gl'] += abs(tp['pnl'])

    yearly_dict = {}
    pos_years = 0
    for y in sorted(yearly.keys()):
        s = yearly[y]
        y_pf = (s['gp'] / s['gl']) if s['gl'] > 0 else (
            float('inf') if s['gp'] > 0 else 0)
        yearly_dict[y] = {
            'trades': s['trades'], 'pnl': s['pnl'], 'pf': y_pf,
        }
        if s['pnl'] > 0:
            pos_years += 1

    total_years = len(yearly_dict)

    return {
        'trades': t, 'wr': wr, 'pf': pf, 'net_pnl': pnl,
        'max_dd': dd, 'yearly': yearly_dict,
        'pos_years': pos_years, 'total_years': total_years,
    }


def fmt_pf(pf):
    return '%.2f' % pf if pf < 100 else 'INF'


def main():
    # Load only SP500 stocks
    sp500_configs = {}
    for key, cfg in ALTAIR_STRATEGIES_CONFIG.items():
        if cfg.get('universe') == 'sp500' and cfg.get('active', True):
            name = cfg['asset_name']
            sp500_configs[name] = cfg

    if not sp500_configs:
        print('No active SP500 stocks found in settings_altair.py')
        return

    names = sorted(sp500_configs.keys())
    print('=' * 90)
    print('ALTAIR SP500 TIER 1-HIGH -- CONFIG A vs CONFIG B')
    print('=' * 90)
    print('Config A (NDX):  max_sl_atr_mult=2.0, dtosc_os=25')
    print('Config B (DJ30): max_sl_atr_mult=4.0, dtosc_os=20')
    print('Stocks (%d): %s' % (len(names), ', '.join(names)))
    print('=' * 90)

    results_a = {}
    results_b = {}

    # Run Config A
    print('\n--- Running Config A (NDX defaults) ---')
    for name in names:
        cfg = sp500_configs[name]
        m = run_bt(name, cfg, CONFIG_A)
        results_a[name] = m
        if 'error' in m:
            print('  %-6s -> ERROR: %s' % (name, m['error']))
        else:
            print('  %-6s T=%2d PF=%5s WR=%4.1f%% DD=%5.2f%% PnL=$%+8.0f  Y+=%d/%d'
                  % (name, m['trades'], fmt_pf(m['pf']), m['wr'],
                     m['max_dd'], m['net_pnl'],
                     m['pos_years'], m['total_years']))

    # Run Config B
    print('\n--- Running Config B (DJ30 override) ---')
    for name in names:
        cfg = sp500_configs[name]
        m = run_bt(name, cfg, CONFIG_B)
        results_b[name] = m
        if 'error' in m:
            print('  %-6s -> ERROR: %s' % (name, m['error']))
        else:
            print('  %-6s T=%2d PF=%5s WR=%4.1f%% DD=%5.2f%% PnL=$%+8.0f  Y+=%d/%d'
                  % (name, m['trades'], fmt_pf(m['pf']), m['wr'],
                     m['max_dd'], m['net_pnl'],
                     m['pos_years'], m['total_years']))

    # Comparison table
    print('\n' + '=' * 90)
    print('COMPARISON: Config A vs Config B')
    print('=' * 90)
    hdr = '%-6s | %5s %4s %5s %+8s %3s | %5s %4s %5s %+8s %3s | %s' % (
        'Stock',
        'PF_A', 'WR%', 'DD%', 'PnL_A', 'Y+',
        'PF_B', 'WR%', 'DD%', 'PnL_B', 'Y+',
        'BEST')
    print(hdr)
    print('-' * len(hdr))

    a_wins = 0
    b_wins = 0
    both_profitable = 0
    neither = 0

    for name in names:
        ma = results_a.get(name, {})
        mb = results_b.get(name, {})
        if 'error' in ma or 'error' in mb:
            print('%-6s | ERROR' % name)
            continue

        # Decide best: primary = PF, secondary = net_pnl
        pf_a = ma['pf']
        pf_b = mb['pf']
        profitable_a = pf_a > 1.0
        profitable_b = pf_b > 1.0

        if profitable_a and profitable_b:
            both_profitable += 1
            best = 'A' if pf_a >= pf_b else 'B'
        elif profitable_a:
            best = 'A'
        elif profitable_b:
            best = 'B'
        else:
            best = '-'
            neither += 1

        if best == 'A':
            a_wins += 1
        elif best == 'B':
            b_wins += 1

        best_mark = '<-- %s' % best if best != '-' else 'NEITHER'

        ya = '%d/%d' % (ma['pos_years'], ma['total_years'])
        yb = '%d/%d' % (mb['pos_years'], mb['total_years'])

        print('%-6s | %5s %4.1f %5.2f %+8.0f %3s | %5s %4.1f %5.2f %+8.0f %3s | %s'
              % (name,
                 fmt_pf(pf_a), ma['wr'], ma['max_dd'], ma['net_pnl'], ya,
                 fmt_pf(pf_b), mb['wr'], mb['max_dd'], mb['net_pnl'], yb,
                 best_mark))

    print('-' * len(hdr))
    print('Config A wins: %d | Config B wins: %d | Neither: %d | Both profitable: %d'
          % (a_wins, b_wins, neither, both_profitable))

    # Yearly heatmap for best config per stock
    print('\n' + '=' * 90)
    print('YEARLY PnL HEATMAP (best config per stock)')
    print('=' * 90)

    all_years = set()
    for name in names:
        for r in [results_a, results_b]:
            m = r.get(name, {})
            if 'error' not in m:
                all_years.update(m['yearly'].keys())
    years = sorted(all_years)

    hdr2 = '%-6s Cfg' + ''.join(' %7d' % y for y in years) + ' %+9s %5s' % ('TOTAL', 'PF')
    print(hdr2)
    print('-' * len(hdr2))

    for name in names:
        ma = results_a.get(name, {})
        mb = results_b.get(name, {})
        if 'error' in ma and 'error' in mb:
            continue

        # Pick best
        pf_a = ma.get('pf', 0) if 'error' not in ma else 0
        pf_b = mb.get('pf', 0) if 'error' not in mb else 0
        if pf_a >= 1.0 and pf_a >= pf_b:
            best_m, cfg_label = ma, 'A'
        elif pf_b >= 1.0:
            best_m, cfg_label = mb, 'B'
        else:
            best_m = ma if pf_a >= pf_b else mb
            cfg_label = 'A' if pf_a >= pf_b else 'B'

        row = '%-6s  %s ' % (name, cfg_label)
        for y in years:
            yd = best_m['yearly'].get(y, {})
            if yd.get('trades', 0) == 0:
                row += '     -- '
            else:
                row += ' %+6.0f ' % yd.get('pnl', 0)
        row += ' %+8.0f' % best_m['net_pnl']
        row += ' %5s' % fmt_pf(best_m['pf'])
        print(row)


if __name__ == '__main__':
    main()
