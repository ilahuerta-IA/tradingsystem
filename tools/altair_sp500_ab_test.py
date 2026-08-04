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

# Mass 15m mode: years are aligned Aug-Jul (label = start year; 2020 =
# Aug2020-Jul2021). IS = 4 aligned years (Aug2020-Jul2024); the ONE-SHOT
# holdout Aug2024-Jul2026 (2 aligned years) is never touched by this mode.
# Cutoff decided 2026-08-03 BEFORE any look at holdout data.
IS_TO_DATE = datetime(2024, 7, 31)
RESULTS_DIR = os.path.join(PROJECT_ROOT, 'results', 'mass15m')


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

    # Yearly PnL (aligned Aug-Jul fiscal years, label = start year)
    yearly = defaultdict(lambda: {'trades': 0, 'wins': 0, 'pnl': 0.0,
                                   'gp': 0.0, 'gl': 0.0})
    for tp in strat._trade_pnls:
        d = tp['date']
        y = d.year if d.month >= 8 else d.year - 1
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
            'gp': s['gp'], 'gl': s['gl'],
        }
        if s['pnl'] > 0:
            pos_years += 1

    total_years = len(yearly_dict)

    # Pseudo-daily Sharpe: equity sampled every 26 bars (15m regular session)
    sharpe = 0.0
    eq = strat._portfolio_values
    if eq and len(eq) > 52:
        daily = np.asarray(eq[::26], dtype=float)
        rets = np.diff(daily) / daily[:-1]
        sd = rets.std()
        if sd > 0:
            sharpe = rets.mean() / sd * np.sqrt(252)

    return {
        'trades': t, 'wr': wr, 'pf': pf, 'net_pnl': pnl,
        'max_dd': dd, 'yearly': yearly_dict, 'sharpe': sharpe,
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


def _cap_pf(pf):
    return min(pf, 999.0)


def _universe15m_configs():
    """One config per data/*_15m_8Yea.csv archive (bars_per_day=26,
    to_date=IS_TO_DATE so the holdout stays untouched)."""
    configs = {}
    for p in sorted(Path(PROJECT_ROOT, 'data').glob('*_15m_8Yea.csv')):
        ticker = p.name.split('_')[0]
        cfg = _make_config(ticker, p.name, _detect_from_date(p),
                           active=True, universe='mass15m', bars_per_day=26)
        cfg['to_date'] = IS_TO_DATE
        configs[ticker] = cfg
    return configs


def run_universe15m():
    """Mass IS backtest over all 15m archives. Appends per ticker to CSVs
    (resumable: already-summarized tickers are skipped). Token-lean output."""
    import csv as _csv
    os.makedirs(RESULTS_DIR, exist_ok=True)
    sum_path = os.path.join(RESULTS_DIR, 'mass15m_summary.csv')
    yr_path = os.path.join(RESULTS_DIR, 'mass15m_yearly.csv')

    done = set()
    if os.path.exists(sum_path):
        with open(sum_path, 'r') as f:
            for row in _csv.DictReader(f):
                done.add(row['ticker'])
    new_sum = not os.path.exists(sum_path)
    new_yr = not os.path.exists(yr_path)

    configs = _universe15m_configs()
    todo = [t for t in sorted(configs) if t not in done]
    print('Universe15m: %d archives, %d done, %d to run. IS ends %s.'
          % (len(configs), len(done), len(todo), IS_TO_DATE.date()))

    fs = open(sum_path, 'a', newline='')
    fy = open(yr_path, 'a', newline='')
    ws = _csv.writer(fs)
    wy = _csv.writer(fy)
    if new_sum:
        ws.writerow(['ticker', 'config', 'trades', 'wr', 'pf', 'max_dd',
                     'net_pnl', 'sharpe', 'pos_years', 'total_years'])
    if new_yr:
        wy.writerow(['ticker', 'config', 'year', 'trades', 'pnl', 'pf'])

    for i, name in enumerate(todo, 1):
        line = '[%3d/%d] %-6s' % (i, len(todo), name)
        rows_s, rows_y = [], []
        for label, override in (('A', CONFIG_A), ('B', CONFIG_B)):
            m = run_bt(name, configs[name], override)
            if 'error' in m:
                line += '  %s: ERROR %s' % (label, m['error'][:40])
                rows_s.append([name, label, 0, 0, 0, 0, 0, 0, 0, 0])
                continue
            rows_s.append([name, label, m['trades'], round(m['wr'], 1),
                           round(_cap_pf(m['pf']), 3), round(m['max_dd'], 2),
                           round(m['net_pnl'], 0), round(m['sharpe'], 2),
                           m['pos_years'], m['total_years']])
            for y, yd in sorted(m['yearly'].items()):
                rows_y.append([name, label, y, yd['trades'],
                               round(yd['pnl'], 0),
                               round(_cap_pf(yd['pf']), 3)])
            line += '  %s: T=%3d PF=%5.2f DD=%4.1f Y+=%d/%d' % (
                label, m['trades'], _cap_pf(m['pf']), m['max_dd'],
                m['pos_years'], m['total_years'])
        ws.writerows(rows_s)
        wy.writerows(rows_y)
        fs.flush()
        fy.flush()
        print(line)
    fs.close()
    fy.close()
    print('Done. Summary: %s' % sum_path)


OOS_TO_DATE = datetime(2026, 7, 31)
OOS_YEARS = (2024, 2025)


def _is_candidates(min_pf=1.5, min_trades=30):
    """Tickers passing IS PF gates (finalists + vigilar), best preset."""
    import csv as _csv
    by_ticker = {}
    with open(os.path.join(RESULTS_DIR, 'mass15m_summary.csv')) as f:
        for r in _csv.DictReader(f):
            by_ticker.setdefault(r['ticker'], {})[r['config']] = r
    out = {}
    for t, cfgs in by_ticker.items():
        if 'A' not in cfgs or 'B' not in cfgs:
            continue
        pa, pb = float(cfgs['A']['pf']), float(cfgs['B']['pf'])
        if pa <= 1.0 or pb <= 1.0:
            continue
        best = 'A' if pa >= pb else 'B'
        m = cfgs[best]
        if float(m['pf']) < min_pf or int(m['trades']) < min_trades:
            continue
        out[t] = (best, float(m['pf']))
    return out


def run_oos():
    """One-shot OOS (fiscal 2024+2025 = Aug-2024..Jul-2026) on IS candidates.
    Full history run so SMA200 etc. are warm; only OOS-year trades count.
    Resumable; writes results/mass15m/oos_summary.csv."""
    import csv as _csv
    cands = _is_candidates()
    oos_path = os.path.join(RESULTS_DIR, 'oos_summary.csv')
    done = set()
    if os.path.exists(oos_path):
        with open(oos_path) as f:
            for r in _csv.DictReader(f):
                done.add(r['ticker'])
    configs = _universe15m_configs()
    todo = [t for t in sorted(cands) if t not in done and t in configs]
    print('OOS: %d candidates, %d done, %d to run. Fiscal years %s.'
          % (len(cands), len(done), len(todo), (OOS_YEARS,)))
    new = not os.path.exists(oos_path)
    fo = open(oos_path, 'a', newline='')
    w = _csv.writer(fo)
    if new:
        w.writerow(['ticker', 'config', 'is_pf', 'oos_trades', 'oos_pnl',
                    'oos_pf', 'y24_t', 'y24_pf', 'y25_t', 'y25_pf'])
    for i, t in enumerate(todo, 1):
        best, is_pf = cands[t]
        cfg = dict(configs[t])
        cfg['to_date'] = OOS_TO_DATE
        m = run_bt(t, cfg, CONFIG_A if best == 'A' else CONFIG_B)
        if 'error' in m:
            print('[%2d/%d] %-6s ERROR %s' % (i, len(todo), t,
                                              m['error'][:40]))
            continue
        tr, pnl, gp, gl = 0, 0.0, 0.0, 0.0
        ycols = []
        for y in OOS_YEARS:
            yd = m['yearly'].get(y)
            if yd:
                tr += yd['trades']
                pnl += yd['pnl']
                gp += yd['gp']
                gl += yd['gl']
                ycols += [yd['trades'], round(_cap_pf(yd['pf']), 2)]
            else:
                ycols += [0, 0]
        opf = _cap_pf(gp / gl if gl > 0 else (999.0 if gp > 0 else 0))
        w.writerow([t, best, is_pf, tr, round(pnl, 0), round(opf, 3)] + ycols)
        fo.flush()
        print('[%2d/%d] %-6s %s IS_PF=%.2f OOS: T=%3d PF=%5.2f PnL=%7.0f'
              ' | 24:%3d/%-5.2f 25:%3d/%-5.2f'
              % (i, len(todo), t, best, is_pf, tr, opf, pnl,
                 ycols[0], ycols[1], ycols[2], ycols[3]))
    fo.close()
    print('Done. OOS summary: %s' % oos_path)


def print_finalists(min_pf=1.5, min_pos_years=3, min_pos_ratio=0.8,
                    min_trades=30, max_year_share=0.6):
    """Finalists from mass15m_summary.csv. Full finalist: profitable in BOTH
    presets, best PF >= min_pf, >= min_pos_years positive aligned years,
    pos ratio >= min_pos_ratio, no single year > max_year_share of PnL.
    VIGILAR: passes PF/trades but fails a consistency check."""
    import csv as _csv
    sum_path = os.path.join(RESULTS_DIR, 'mass15m_summary.csv')
    yr_path = os.path.join(RESULTS_DIR, 'mass15m_yearly.csv')
    by_ticker = {}
    with open(sum_path, 'r') as f:
        for r in _csv.DictReader(f):
            by_ticker.setdefault(r['ticker'], {})[r['config']] = r
    yearly = defaultdict(dict)
    with open(yr_path, 'r') as f:
        for r in _csv.DictReader(f):
            yearly[(r['ticker'], r['config'])][int(r['year'])] = r

    finalists = []
    vigilar = []
    for t, cfgs in by_ticker.items():
        if 'A' not in cfgs or 'B' not in cfgs:
            continue
        pa, pb = float(cfgs['A']['pf']), float(cfgs['B']['pf'])
        if pa <= 1.0 or pb <= 1.0:
            continue
        best = 'A' if pa >= pb else 'B'
        m = cfgs[best]
        if float(m['pf']) < min_pf or int(m['trades']) < min_trades:
            continue
        ty = int(m['total_years']) or 1
        ydata = yearly.get((t, best), {})
        total_pnl = sum(float(y['pnl']) for y in ydata.values())
        max_share = (max((float(y['pnl']) for y in ydata.values()),
                         default=0) / total_pnl) if total_pnl > 0 else 1.0
        consistent = (int(m['pos_years']) >= min_pos_years
                      and int(m['pos_years']) / ty >= min_pos_ratio
                      and max_share <= max_year_share)
        (finalists if consistent else vigilar).append(
            (float(m['pf']), t, best, m, max_share))

    years = sorted({y for k in yearly for y in yearly[k]})

    def _table(rows, label):
        rows.sort(reverse=True)
        hdr = ('%-6s Cfg %4s %6s %6s %6s %8s %4s %5s' %
               ('TICKER', 'T', 'PF', 'DD%', 'Sharpe', 'PnL$', 'Y+', 'Conc'))
        hdr += ''.join('  %s(n/PF)' % y for y in years)
        print('\n%s: %d' % (label, len(rows)))
        print(hdr)
        for pf, t, best, m, share in rows:
            sh = float(m['sharpe'])
            row = '%-6s  %s  %4s %6.2f %6.1f %5.2f%s %8.0f %s/%s %4.0f%%' % (
                t, best, m['trades'], pf, float(m['max_dd']),
                sh, '!' if sh < 0.7 else ' ', float(m['net_pnl']),
                m['pos_years'], m['total_years'], share * 100)
            for y in years:
                yd = yearly.get((t, best), {}).get(y)
                row += ('  %3s/%-5.2f' % (yd['trades'], float(yd['pf']))
                        if yd else '      --  ')
            print(row)

    print('Criteria: both presets PF>1.0, best PF>=%.2f, T>=%d; consistency:'
          ' Y+>=%d, ratio>=%d%%, max year <=%d%% of PnL. Years = Aug-Jul.'
          ' Sharpe<0.7 = red flag "!" only (Ivan 2026-08-03, review with OOS).'
          % (min_pf, min_trades, min_pos_years, min_pos_ratio * 100,
             max_year_share * 100))
    _table(finalists, 'FINALISTS')
    _table(vigilar, 'VIGILAR (PF ok, consistency failed)')


def main():
    parser = argparse.ArgumentParser(description='ALTAIR A/B Config Test')
    parser.add_argument('--pending', action='store_true',
                        help='Test pending tickers from pending_tickers.txt')
    parser.add_argument('--ticker', nargs='+',
                        help='Only test specific tickers (with --pending)')
    parser.add_argument('--universe15m', action='store_true',
                        help='Mass IS backtest over all data/*_15m_8Yea.csv '
                             '(resumable, writes results/mass15m/*.csv)')
    parser.add_argument('--finalists', action='store_true',
                        help='Print finalists table from mass15m results')
    parser.add_argument('--oos', action='store_true',
                        help='One-shot OOS (fiscal 2024+2025) on candidates')
    args = parser.parse_args()

    if args.universe15m:
        run_universe15m()
        return
    if args.finalists:
        print_finalists()
        return
    if args.oos:
        run_oos()
        return
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
