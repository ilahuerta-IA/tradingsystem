"""
ALTAIR SP500 Tier 1-HIGH -- Config A vs Config B Comparison

Runs all SP500 stocks from settings_altair.py with:
  Config A (NDX defaults): max_sl_atr_mult=2.0, dtosc_os=25
  Config B (DJ30 override): max_sl_atr_mult=4.0, dtosc_os=20

Compares per-stock PF, WR%, MaxDD%, net PnL and recommends best config.

Usage:
    python tools/altair_sp500_ab_test.py              # existing SP500 configs only
    python tools/altair_sp500_ab_test.py --pending     # pending tickers from file
    python tools/altair_sp500_ab_test.py --pending --ticker CVNA AXON  # specific tickers
"""
import sys
import os
import io
import contextlib
import warnings
import argparse
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
    ALTAIR_STRATEGIES_CONFIG, ALTAIR_BROKER_CONFIG, _make_config,
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


def _detect_from_date(csv_path):
    """Read first data line of CSV to get earliest date."""
    with open(csv_path, 'r') as f:
        f.readline()  # skip header
        first = f.readline().strip()
    if first:
        date_str = first.split(',')[0]  # e.g. '20170103'
        return datetime(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))
    return datetime(2017, 1, 1)


def _load_pending_tickers(only_tickers=None):
    """Load tickers from pending_tickers.txt and create temp configs via _make_config."""
    pending_path = os.path.join(SCRIPT_DIR, 'pending_tickers.txt')
    tickers = []
    with open(pending_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            tickers.append(line)

    # Also add HWM (noted in file as already downloaded separately)
    if 'HWM' not in tickers:
        tickers.append('HWM')

    if only_tickers:
        only_upper = {t.upper() for t in only_tickers}
        tickers = [t for t in tickers if t in only_upper]

    configs = {}
    skipped = []
    for ticker in sorted(tickers):
        csv_name = '%s_1h_8Yea.csv' % ticker
        csv_path = os.path.join(PROJECT_ROOT, 'data', csv_name)
        if not os.path.exists(csv_path):
            skipped.append(ticker)
            continue
        from_date = _detect_from_date(csv_path)
        cfg = _make_config(ticker, csv_name, from_date,
                           active=True, universe='sp500_pending')
        # Override to_date to use all available data
        cfg['to_date'] = datetime(2026, 12, 31)
        configs[ticker] = cfg

    if skipped:
        print('  Skipped (no CSV): %s' % ', '.join(skipped))

    return configs


def _run_ab_comparison(stock_configs, title):
    """Run Config A vs B for a dict of {name: cfg}. Shared logic."""
    names = sorted(stock_configs.keys())
    if not names:
        print('No stocks to test.')
        return

    print('=' * 90)
    print(title)
    print('=' * 90)
    print('Config A (NDX):  max_sl_atr_mult=2.0, dtosc_os=25')
    print('Config B (DJ30): max_sl_atr_mult=4.0, dtosc_os=20')
    print('Stocks (%d): %s' % (len(names), ', '.join(names)))
    print('=' * 90)

    results_a = {}
    results_b = {}

    # Run Config A
    print('\n--- Running Config A (NDX defaults) ---')
    for i, name in enumerate(names, 1):
        cfg = stock_configs[name]
        m = run_bt(name, cfg, CONFIG_A)
        results_a[name] = m
        if 'error' in m:
            print('  [%2d/%d] %-6s -> ERROR: %s' % (i, len(names), name, m['error']))
        else:
            print('  [%2d/%d] %-6s T=%2d PF=%5s WR=%4.1f%% DD=%5.2f%% PnL=$%+8.0f  Y+=%d/%d'
                  % (i, len(names), name, m['trades'], fmt_pf(m['pf']), m['wr'],
                     m['max_dd'], m['net_pnl'],
                     m['pos_years'], m['total_years']))

    # Run Config B
    print('\n--- Running Config B (DJ30 override) ---')
    for i, name in enumerate(names, 1):
        cfg = stock_configs[name]
        m = run_bt(name, cfg, CONFIG_B)
        results_b[name] = m
        if 'error' in m:
            print('  [%2d/%d] %-6s -> ERROR: %s' % (i, len(names), name, m['error']))
        else:
            print('  [%2d/%d] %-6s T=%2d PF=%5s WR=%4.1f%% DD=%5.2f%% PnL=$%+8.0f  Y+=%d/%d'
                  % (i, len(names), name, m['trades'], fmt_pf(m['pf']), m['wr'],
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
    tier1 = []  # PF >= 1.30 best config
    tier2 = []  # 1.0 < PF < 1.30
    tier3 = []  # PF <= 1.0

    for name in names:
        ma = results_a.get(name, {})
        mb = results_b.get(name, {})
        if 'error' in ma or 'error' in mb:
            err_a = ma.get('error', '')
            err_b = mb.get('error', '')
            print('%-6s | ERROR: A=%s B=%s' % (name, err_a, err_b))
            tier3.append((name, '-', 0, 0))
            continue

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
        best_m = ma if best == 'A' else (mb if best == 'B' else ma)
        best_pf = best_m['pf']

        ya = '%d/%d' % (ma['pos_years'], ma['total_years'])
        yb = '%d/%d' % (mb['pos_years'], mb['total_years'])

        print('%-6s | %5s %4.1f %5.2f %+8.0f %3s | %5s %4.1f %5.2f %+8.0f %3s | %s'
              % (name,
                 fmt_pf(pf_a), ma['wr'], ma['max_dd'], ma['net_pnl'], ya,
                 fmt_pf(pf_b), mb['wr'], mb['max_dd'], mb['net_pnl'], yb,
                 best_mark))

        if best_pf >= 1.30:
            tier1.append((name, best, best_pf, best_m['net_pnl']))
        elif best_pf > 1.0:
            tier2.append((name, best, best_pf, best_m['net_pnl']))
        else:
            tier3.append((name, best, best_pf, best_m['net_pnl']))

    print('-' * len(hdr))
    print('Config A wins: %d | Config B wins: %d | Neither: %d | Both profitable: %d'
          % (a_wins, b_wins, neither, both_profitable))

    # Classification summary
    print('\n' + '=' * 90)
    print('CLASSIFICATION')
    print('=' * 90)
    print('\nTIER 1 -- PF >= 1.30 (%d stocks):' % len(tier1))
    for name, cfg, pf, pnl in sorted(tier1, key=lambda x: -x[2]):
        print('  %-6s Config %s  PF=%5s  PnL=$%+8.0f' % (name, cfg, fmt_pf(pf), pnl))
    print('\nTIER 2 -- 1.0 < PF < 1.30 (%d stocks):' % len(tier2))
    for name, cfg, pf, pnl in sorted(tier2, key=lambda x: -x[2]):
        print('  %-6s Config %s  PF=%5s  PnL=$%+8.0f' % (name, cfg, fmt_pf(pf), pnl))
    print('\nTIER 3 -- PF <= 1.0 / ERROR (%d stocks) -> DISCARD:' % len(tier3))
    for name, cfg, pf, pnl in sorted(tier3, key=lambda x: -x[2]):
        print('  %-6s Config %s  PF=%5s  PnL=$%+8.0f' % (name, cfg, fmt_pf(pf), pnl))

    # Yearly heatmap for best config per stock (Tier 1+2 only)
    show_names = [t[0] for t in sorted(tier1 + tier2, key=lambda x: -x[2])]
    if show_names:
        print('\n' + '=' * 90)
        print('YEARLY PnL HEATMAP (Tier 1+2, best config)')
        print('=' * 90)

        all_years = set()
        for name in show_names:
            for r in [results_a, results_b]:
                m = r.get(name, {})
                if 'error' not in m:
                    all_years.update(m['yearly'].keys())
        years = sorted(all_years)

        hdr2 = '%-6s Cfg' + ''.join(' %7d' % y for y in years) + ' %+9s %5s' % ('TOTAL', 'PF')
        print(hdr2)
        print('-' * len(hdr2))

        for name in show_names:
            ma = results_a.get(name, {})
            mb = results_b.get(name, {})
            if 'error' in ma and 'error' in mb:
                continue

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


def main():
    parser = argparse.ArgumentParser(description='ALTAIR A/B Config Test')
    parser.add_argument('--pending', action='store_true',
                        help='Test pending tickers from pending_tickers.txt')
    parser.add_argument('--ticker', nargs='+',
                        help='Only test specific tickers (with --pending)')
    args = parser.parse_args()

    if args.pending:
        print('Loading pending tickers...')
        configs = _load_pending_tickers(args.ticker)
        _run_ab_comparison(configs, 'ALTAIR PENDING TICKERS -- CONFIG A vs CONFIG B')
    else:
        # Original mode: existing SP500 configs
        sp500_configs = {}
        for key, cfg in ALTAIR_STRATEGIES_CONFIG.items():
            if cfg.get('universe') == 'sp500' and cfg.get('active', True):
                name = cfg['asset_name']
                sp500_configs[name] = cfg
        _run_ab_comparison(sp500_configs,
                           'ALTAIR SP500 TIER 1-HIGH -- CONFIG A vs CONFIG B')


if __name__ == '__main__':
    main()
