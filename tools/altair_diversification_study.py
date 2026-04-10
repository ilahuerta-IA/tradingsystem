"""
ALTAIR Diversification Study -- NDX vs NDX+DJ30

Runs all active ALTAIR assets with their config params (NDX Option D
for NDX stocks, DJ30 Phase 1-3 for DJ30 stocks) and compares:
  1. NDX-7 only: yearly PnL, DD, PF
  2. DJ30-5 only: yearly PnL, DD, PF
  3. Combined NDX+DJ30: yearly PnL, DD, PF
  4. Diversification benefit: combined DD vs NDX-only DD
  5. Year-by-year correlation

Uses the same BT engine as altair_deep_compare.py / altair_optimizer.py.

Usage:
    python tools/altair_diversification_study.py
"""
import sys
import os
import io
import math
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
    ALTAIR_STRATEGIES_CONFIG, ALTAIR_BROKER_CONFIG, _DEFAULT_PARAMS,
)


STARTING_CASH = 100_000.0


# =============================================================================
# LOAD ASSETS WITH THEIR CONFIG PARAMS
# =============================================================================

def load_assets():
    """Load active assets grouped by universe, with per-stock params."""
    assets = {}
    for key, cfg in ALTAIR_STRATEGIES_CONFIG.items():
        if not cfg.get('active', True):
            continue
        name = cfg['asset_name']
        assets[name] = {
            'data_path': cfg['data_path'],
            'from_date': cfg['from_date'],
            'to_date': cfg['to_date'],
            'universe': cfg.get('universe', 'ndx'),
            'params': cfg.get('params', {}),
        }
    return assets


# =============================================================================
# BACKTEST
# =============================================================================

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

        # Use the asset's own params from settings_altair.py
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

    # Max DD
    dd = 0.0
    if strat._portfolio_values:
        peak = strat._portfolio_values[0]
        for v in strat._portfolio_values:
            if v > peak:
                peak = v
            d = (peak - v) / peak * 100.0
            if d > dd:
                dd = d

    # Sharpe
    sharpe = 0.0
    if len(strat._portfolio_values) > 10:
        pv = strat._portfolio_values
        rets = np.array([(pv[i] - pv[i-1]) / pv[i-1]
                         for i in range(1, len(pv))])
        if strat._first_bar_dt and strat._last_bar_dt:
            days = (strat._last_bar_dt - strat._first_bar_dt).days
            yrs = max(days / 365.25, 0.1)
            ppy = len(pv) / yrs
        else:
            ppy = 252 * 7
        std = np.std(rets)
        if std > 0:
            sharpe = (np.mean(rets) * ppy) / (std * np.sqrt(ppy))

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
    for y in sorted(yearly.keys()):
        s = yearly[y]
        y_wr = (s['wins'] / s['trades'] * 100) if s['trades'] > 0 else 0
        y_pf = (s['gp'] / s['gl']) if s['gl'] > 0 else (
            float('inf') if s['gp'] > 0 else 0)
        yearly_dict[y] = {
            'trades': s['trades'], 'wr': y_wr, 'pf': y_pf, 'pnl': s['pnl'],
        }

    # Portfolio values for combined equity curve
    portfolio_values = list(strat._portfolio_values)

    return {
        'trades': t, 'wr': wr, 'pf': pf, 'net_pnl': pnl,
        'max_dd': dd, 'sharpe': sharpe,
        'yearly': yearly_dict,
        'portfolio_values': portfolio_values,
    }


def fmt_pf(pf):
    return '%.2f' % pf if pf < 100 else 'INF'


# =============================================================================
# MAIN
# =============================================================================

def main():
    assets = load_assets()
    ndx_names = sorted(n for n, a in assets.items() if a['universe'] == 'ndx')
    dj30_names = sorted(n for n, a in assets.items() if a['universe'] == 'dj30')
    all_names = sorted(assets.keys())

    total_bt = len(all_names)
    print('=' * 100)
    print('ALTAIR DIVERSIFICATION STUDY -- NDX vs NDX+DJ30')
    print('=' * 100)
    print('NDX assets (%d):  %s' % (len(ndx_names), ', '.join(ndx_names)))
    print('DJ30 assets (%d): %s' % (len(dj30_names), ', '.join(dj30_names)))
    print('Total backtests: %d' % total_bt)
    print('Each asset uses its own config params from settings_altair.py')
    print('=' * 100)

    # Run all BTs
    results = {}
    for name in all_names:
        cfg = assets[name]
        univ = cfg['universe'].upper()
        m = run_bt(name, cfg)
        results[name] = m
        if 'error' in m:
            print('  %-6s [%s] -> ERROR: %s' % (name, univ, m['error']))
        else:
            print('  %-6s [%-4s] T=%2d PF=%5s WR=%4.1f%% DD=%5.2f%% '
                  'Sh=%5.2f PnL=$%8.0f'
                  % (name, univ, m['trades'], fmt_pf(m['pf']), m['wr'],
                     m['max_dd'], m['sharpe'], m['net_pnl']))

    # Collect all years
    all_years = set()
    for m in results.values():
        if 'error' not in m:
            all_years.update(m['yearly'].keys())
    years = sorted(all_years)

    # =========================================================================
    # 1. YEARLY PNL HEATMAP (all assets)
    # =========================================================================
    print('\n' + '=' * 100)
    print('1. YEARLY PnL HEATMAP (all 12 assets)')
    print('=' * 100)

    hdr = '%-7s %-5s' % ('Asset', 'Univ')
    for y in years:
        hdr += ' %8d' % y
    hdr += ' %10s %6s' % ('TOTAL', 'PF')
    print(hdr)
    print('-' * len(hdr))

    for name in all_names:
        m = results[name]
        if 'error' in m:
            print('%-7s %-5s ERROR' % (name, assets[name]['universe'].upper()))
            continue
        univ = assets[name]['universe'].upper()
        row = '%-7s %-5s' % (name, univ)
        for y in years:
            yd = m['yearly'].get(y, {})
            if yd.get('trades', 0) == 0:
                row += '      -- '
            else:
                row += ' %+7.0f ' % yd.get('pnl', 0)
        row += ' %+9.0f' % m['net_pnl']
        row += ' %6s' % fmt_pf(m['pf'])
        print(row)

    # =========================================================================
    # 2. GROUP AGGREGATES: NDX-only, DJ30-only, Combined
    # =========================================================================
    groups = {
        'NDX-7':     ndx_names,
        'DJ30-5':    dj30_names,
        'Combined':  all_names,
    }

    print('\n' + '=' * 100)
    print('2. YEARLY AGGREGATE BY GROUP')
    print('=' * 100)

    for group_name, group_assets in groups.items():
        print('\n--- %s ---' % group_name)
        hdr2 = '%-8s' % 'Year'
        hdr2 += ' %7s %5s %5s %8s %8s %6s' % (
            'Trades', 'Wins', 'WR%', 'Gross+', 'Gross-', 'PF')
        hdr2 += ' %10s %5s' % ('PnL', '+/?')
        print(hdr2)
        print('-' * len(hdr2))

        total_trades = 0
        total_wins = 0
        total_gp = 0.0
        total_gl = 0.0
        total_pnl = 0.0
        positive_years = 0

        for y in years:
            y_trades = 0
            y_wins = 0
            y_gp = 0.0
            y_gl = 0.0
            y_pnl = 0.0
            assets_active = 0
            assets_positive = 0

            for name in group_assets:
                m = results.get(name)
                if not m or 'error' in m:
                    continue
                yd = m['yearly'].get(y, {})
                if yd.get('trades', 0) == 0:
                    continue
                assets_active += 1
                y_trades += yd['trades']
                y_wins += yd.get('wins', 0) if 'wins' in yd else 0
                # Reconstruct wins from WR
                if 'wins' not in yd and yd.get('wr', 0) > 0:
                    y_wins += int(yd['trades'] * yd['wr'] / 100)
                y_pnl += yd['pnl']
                if yd['pnl'] > 0:
                    assets_positive += 1
                # gp/gl from yearly data
                y_pf_raw = yd.get('pf', 0)
                if y_pf_raw > 0 and yd['pnl'] > 0 and y_pf_raw < 100:
                    # PF = gp/gl, pnl = gp - gl => gp = pnl * pf/(pf-1)
                    if y_pf_raw > 1:
                        gp_est = yd['pnl'] * y_pf_raw / (y_pf_raw - 1)
                        gl_est = gp_est - yd['pnl']
                        y_gp += gp_est
                        y_gl += gl_est
                    else:
                        y_gp += max(yd['pnl'], 0)
                        y_gl += max(-yd['pnl'], 0)
                elif yd['pnl'] >= 0:
                    y_gp += yd['pnl']
                else:
                    y_gl += abs(yd['pnl'])

            total_trades += y_trades
            total_wins += y_wins
            total_gp += y_gp
            total_gl += y_gl
            total_pnl += y_pnl

            if y_trades == 0:
                continue

            y_wr = y_wins / y_trades * 100 if y_trades > 0 else 0
            y_pf = y_gp / y_gl if y_gl > 0 else (
                float('inf') if y_gp > 0 else 0)
            pos_label = '%d/%d' % (assets_positive, assets_active)
            if y_pnl > 0:
                positive_years += 1

            print('%-8d %7d %5d %4.1f%% %+7.0f  %+7.0f  %6s %+9.0f %5s'
                  % (y, y_trades, y_wins, y_wr,
                     y_gp, -y_gl, fmt_pf(y_pf), y_pnl, pos_label))

        # Total row
        print('-' * len(hdr2))
        total_wr = total_wins / total_trades * 100 if total_trades > 0 else 0
        total_pf = total_gp / total_gl if total_gl > 0 else 0
        print('%-8s %7d %5d %4.1f%% %+7.0f  %+7.0f  %6s %+9.0f  %d/%d yrs+'
              % ('TOTAL', total_trades, total_wins, total_wr,
                 total_gp, -total_gl, fmt_pf(total_pf), total_pnl,
                 positive_years, len(years)))

    # =========================================================================
    # 3. COMPARATIVE SUMMARY TABLE
    # =========================================================================
    print('\n' + '=' * 100)
    print('3. DIVERSIFICATION COMPARISON')
    print('=' * 100)

    print('%-12s %6s %5s %6s %6s %6s %8s %10s'
          % ('Group', 'Assets', 'Trd', 'medPF', 'mWR%', 'wDD%', 'mSharpe', 'TotalPnL'))
    print('-' * 80)

    for group_name, group_assets in groups.items():
        pfs = []
        wrs = []
        sharpes = []
        worst_dd = 0.0
        total_pnl = 0.0
        total_trades = 0

        for name in group_assets:
            m = results.get(name)
            if not m or 'error' in m:
                continue
            p = m['pf'] if m['pf'] < 100 else 99.0
            pfs.append(p)
            wrs.append(m['wr'])
            sharpes.append(m['sharpe'])
            total_pnl += m['net_pnl']
            total_trades += m['trades']
            if m['max_dd'] > worst_dd:
                worst_dd = m['max_dd']

        if not pfs:
            continue

        print('%-12s %6d %5d %6s %5.1f%% %5.1f%% %8.2f %+9.0f'
              % (group_name, len(pfs), total_trades,
                 fmt_pf(float(np.median(pfs))),
                 float(np.mean(wrs)),
                 worst_dd,
                 float(np.mean(sharpes)),
                 total_pnl))

    # =========================================================================
    # 4. YEAR-BY-YEAR NDX vs DJ30 PnL COMPARISON
    # =========================================================================
    print('\n' + '=' * 100)
    print('4. YEAR-BY-YEAR: NDX vs DJ30 vs COMBINED')
    print('=' * 100)
    print('%-6s %12s %12s %12s %8s'
          % ('Year', 'NDX PnL', 'DJ30 PnL', 'Combined', 'DJ30 help?'))
    print('-' * 60)

    ndx_yearly = []
    dj30_yearly = []

    for y in years:
        ndx_pnl = 0.0
        dj30_pnl = 0.0
        for name in ndx_names:
            m = results.get(name)
            if m and 'error' not in m:
                ndx_pnl += m['yearly'].get(y, {}).get('pnl', 0)
        for name in dj30_names:
            m = results.get(name)
            if m and 'error' not in m:
                dj30_pnl += m['yearly'].get(y, {}).get('pnl', 0)

        combined = ndx_pnl + dj30_pnl
        ndx_yearly.append(ndx_pnl)
        dj30_yearly.append(dj30_pnl)

        # Did DJ30 help? (offsetting NDX weakness or amplifying)
        if ndx_pnl < 0 and dj30_pnl > 0:
            help_label = 'OFFSET'
        elif ndx_pnl < 0 and dj30_pnl < 0:
            help_label = 'BOTH-'
        elif ndx_pnl > 0 and dj30_pnl > 0:
            help_label = 'BOTH+'
        elif ndx_pnl > 0 and dj30_pnl < 0:
            help_label = 'DRAG'
        else:
            help_label = '--'

        print('%-6d %+11.0f  %+11.0f  %+11.0f  %s'
              % (y, ndx_pnl, dj30_pnl, combined, help_label))

    print('-' * 60)
    total_ndx = sum(ndx_yearly)
    total_dj30 = sum(dj30_yearly)
    print('%-6s %+11.0f  %+11.0f  %+11.0f'
          % ('TOTAL', total_ndx, total_dj30, total_ndx + total_dj30))

    # Correlation between NDX and DJ30 yearly PnLs
    if len(ndx_yearly) >= 3 and len(dj30_yearly) >= 3:
        corr = np.corrcoef(ndx_yearly, dj30_yearly)[0, 1]
        print('\nNDX-DJ30 yearly PnL correlation: %.3f' % corr)
        if corr < 0.3:
            print('=> LOW correlation: good diversification')
        elif corr < 0.6:
            print('=> MODERATE correlation: partial diversification')
        else:
            print('=> HIGH correlation: limited diversification benefit')

    # =========================================================================
    # 5. PER-ASSET SUMMARY (sorted by PF)
    # =========================================================================
    print('\n' + '=' * 100)
    print('5. ALL ASSETS RANKED BY PF')
    print('=' * 100)
    print('%-7s %-5s %5s %5s %6s %6s %6s %10s %5s'
          % ('Asset', 'Univ', 'Trd', 'WR%', 'PF', 'DD%', 'Sharpe',
             'TotalPnL', '+Yrs'))
    print('-' * 70)

    ranked = []
    for name in all_names:
        m = results.get(name)
        if not m or 'error' in m:
            continue
        pos_years = sum(1 for y in years
                        if m['yearly'].get(y, {}).get('pnl', 0) > 0)
        total_years = sum(1 for y in years
                         if m['yearly'].get(y, {}).get('trades', 0) > 0)
        ranked.append((name, m, pos_years, total_years))

    ranked.sort(key=lambda x: x[1]['pf'] if x[1]['pf'] < 100 else 99, reverse=True)

    for name, m, pos_y, tot_y in ranked:
        univ = assets[name]['universe'].upper()
        print('%-7s %-5s %5d %4.1f%% %6s %5.1f%% %6.2f %+9.0f %2d/%d'
              % (name, univ, m['trades'], m['wr'], fmt_pf(m['pf']),
                 m['max_dd'], m['sharpe'], m['net_pnl'], pos_y, tot_y))

    print('\n' + '=' * 100)
    print('STUDY COMPLETE')
    print('=' * 100)


if __name__ == '__main__':
    main()
