"""
ALTAIR Entries-Per-Day Diversification Study

Runs option-D params with max_entries_per_day = 1, 2, 3 across all 7 assets.
For each setting, shows:
  - Per-asset summary (trades, PF, DD, PnL)
  - Monthly PnL heatmap (portfolio aggregate) to spot worst DD months
  - Worst 5 months by drawdown contribution
  - Trade clustering analysis: entries within N days across assets

Philosophy: check if allowing more entries/day creates dangerous
clustering (correlated drawdowns when multiple positions open together).

Usage:
    python tools/altair_entries_study.py
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

from strategies.altair_strategy import ALTAIRStrategy
from lib.commission import ETFCommission, ETFCSVData
from config.settings_altair import (
    ALTAIR_STRATEGIES_CONFIG, ALTAIR_BROKER_CONFIG, _DEFAULT_PARAMS,
)
from pathlib import Path


# =============================================================================
# OPTION D PARAMS (fixed from deep compare)
# =============================================================================
OPTION_D = {
    'max_sl_atr_mult': 2.0,
    'tp_atr_mult': 4.0,
    'dtosc_os': 25,
    'tr1bh_timeout': 5,
}

ENTRIES_TO_TEST = [1, 2, 3]

STARTING_CASH = 100_000.0

ASSETS = {}
for key, cfg in ALTAIR_STRATEGIES_CONFIG.items():
    if cfg.get('active', True):
        ASSETS[cfg['asset_name']] = {
            'data_path': cfg['data_path'],
            'from_date': cfg['from_date'],
            'to_date': cfg['to_date'],
        }

ASSET_NAMES = sorted(ASSETS.keys())


# =============================================================================
# BACKTEST ENGINE
# =============================================================================

def run_bt(asset_name, asset_cfg, max_entries):
    """Run single BT returning metrics + trade list with dates."""
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

        params = dict(_DEFAULT_PARAMS)
        params.update(OPTION_D)
        params['max_entries_per_day'] = max_entries
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

    # Trade list with dates for clustering analysis
    trades = []
    for tp in strat._trade_pnls:
        trades.append({
            'date': tp['date'],
            'year': tp['year'],
            'month': tp['date'].month,
            'pnl': tp['pnl'],
            'is_winner': tp['is_winner'],
        })

    # Monthly PnL
    monthly = defaultdict(float)
    monthly_trades = defaultdict(int)
    for tp in trades:
        key = (tp['year'], tp['month'])
        monthly[key] += tp['pnl']
        monthly_trades[key] += 1

    return {
        'trades': t, 'wr': wr, 'pf': pf, 'net_pnl': pnl,
        'max_dd': dd, 'sharpe': sharpe,
        'trade_list': trades,
        'monthly_pnl': dict(monthly),
        'monthly_trades': dict(monthly_trades),
    }


# =============================================================================
# ANALYSIS FUNCTIONS
# =============================================================================

def aggregate_monthly(all_results):
    """Aggregate monthly PnL across all assets."""
    agg = defaultdict(lambda: {'pnl': 0.0, 'trades': 0, 'assets': 0})
    for asset, m in all_results.items():
        if 'error' in m:
            continue
        for (y, mo), pnl in m['monthly_pnl'].items():
            agg[(y, mo)]['pnl'] += pnl
            agg[(y, mo)]['trades'] += m['monthly_trades'].get((y, mo), 0)
        for (y, mo) in m['monthly_pnl']:
            agg[(y, mo)]['assets'] += 1
    return agg


def find_worst_months(agg_monthly, n=10):
    """Return worst N months by portfolio PnL."""
    items = [(k, v) for k, v in agg_monthly.items()]
    items.sort(key=lambda x: x[1]['pnl'])
    return items[:n]


def cluster_analysis(all_results):
    """Analyze trade entry clustering across assets within same week."""
    all_dates = []
    for asset, m in all_results.items():
        if 'error' in m:
            continue
        for t in m['trade_list']:
            all_dates.append({
                'asset': asset,
                'date': t['date'],
                'pnl': t['pnl'],
            })

    all_dates.sort(key=lambda x: x['date'])

    # Find clusters: trades within 3 calendar days across different assets
    clusters = []
    i = 0
    while i < len(all_dates):
        cluster = [all_dates[i]]
        j = i + 1
        while j < len(all_dates):
            delta = (all_dates[j]['date'] - all_dates[i]['date']).days
            if delta <= 3:
                cluster.append(all_dates[j])
                j += 1
            else:
                break
        if len(cluster) >= 3:
            unique_assets = len(set(t['asset'] for t in cluster))
            if unique_assets >= 2:
                total_pnl = sum(t['pnl'] for t in cluster)
                clusters.append({
                    'start': cluster[0]['date'],
                    'end': cluster[-1]['date'],
                    'n_trades': len(cluster),
                    'n_assets': unique_assets,
                    'pnl': total_pnl,
                    'assets': [t['asset'] for t in cluster],
                })
        i = j if j > i + 1 else i + 1

    return clusters


def fmt_pf(pf):
    return '%.2f' % pf if pf < 100 else 'INF'


MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


# =============================================================================
# MAIN
# =============================================================================

def main():
    total_bt = len(ENTRIES_TO_TEST) * len(ASSET_NAMES)
    print('=' * 100)
    print('ALTAIR ENTRIES-PER-DAY DIVERSIFICATION STUDY')
    print('=' * 100)
    print('Option D params: tp=4.0, os=25, timeout=5, max_sl=2.0')
    print('Testing max_entries_per_day = %s' % ENTRIES_TO_TEST)
    print('Assets: %d | Total BT: %d' % (len(ASSET_NAMES), total_bt))
    print('=' * 100)

    all_data = {}  # {entries: {asset: metrics}}

    for entries in ENTRIES_TO_TEST:
        print('\n' + '=' * 80)
        print('MAX ENTRIES PER DAY = %d' % entries)
        print('=' * 80)

        all_data[entries] = {}
        for asset in ASSET_NAMES:
            m = run_bt(asset, ASSETS[asset], entries)
            all_data[entries][asset] = m
            if 'error' not in m:
                print('  %-6s T=%3d PF=%5s WR=%4.1f%% DD=%5.2f%% '
                      'Sh=%5.2f PnL=$%8.0f'
                      % (asset, m['trades'], fmt_pf(m['pf']), m['wr'],
                         m['max_dd'], m['sharpe'], m['net_pnl']))
            else:
                print('  %-6s ERROR: %s' % (asset, m['error']))

        # Aggregates
        results = all_data[entries]
        valid = {k: v for k, v in results.items() if 'error' not in v}
        if not valid:
            continue

        total_trades = sum(v['trades'] for v in valid.values())
        total_pnl = sum(v['net_pnl'] for v in valid.values())
        med_pf = np.median([v['pf'] for v in valid.values()])
        worst_dd = max(v['max_dd'] for v in valid.values())
        mean_sh = np.mean([v['sharpe'] for v in valid.values()])
        prof = sum(1 for v in valid.values() if v['net_pnl'] > 0)

        print('\n  AGGREGATE: T=%d medPF=%.2f Prof=%d/%d wDD=%.1f%% '
              'mSh=%.2f PnL=$%.0f'
              % (total_trades, med_pf, prof, len(valid), worst_dd,
                 mean_sh, total_pnl))

        # Monthly heatmap (portfolio)
        agg = aggregate_monthly(results)
        years = sorted(set(y for (y, _) in agg.keys()))

        print('\n  MONTHLY PnL HEATMAP (portfolio aggregate):')
        header = '  Year  ' + ''.join('%7s' % m for m in MONTHS) + '   TOTAL'
        print(header)
        print('  ' + '-' * (len(header) - 2))
        for yr in years:
            row = '  %d  ' % yr
            yr_total = 0
            for mo in range(1, 13):
                if (yr, mo) in agg:
                    val = agg[(yr, mo)]['pnl']
                    yr_total += val
                    if val >= 0:
                        row += '%+7.0f' % val
                    else:
                        row += '%+7.0f' % val
                else:
                    row += '     --'
            row += '  %+8.0f' % yr_total
            print(row)

        # Worst months
        worst = find_worst_months(agg, n=10)
        print('\n  WORST 10 MONTHS (portfolio):')
        print('  %-10s %8s %6s %6s' % ('Month', 'PnL', 'Trades', 'Assets'))
        print('  ' + '-' * 34)
        for (y, mo), info in worst:
            print('  %d-%02d    %+8.0f %6d %6d'
                  % (y, mo, info['pnl'], info['trades'], info['assets']))

        # Cluster analysis
        clusters = cluster_analysis(results)
        losing_clusters = [c for c in clusters if c['pnl'] < 0]
        losing_clusters.sort(key=lambda x: x['pnl'])

        print('\n  TRADE CLUSTERING (>= 3 trades within 3 days, >= 2 assets):')
        print('  Total clusters: %d | Losing clusters: %d'
              % (len(clusters), len(losing_clusters)))
        if losing_clusters:
            print('\n  WORST 10 LOSING CLUSTERS:')
            print('  %-12s %-12s %5s %5s %9s  Assets'
                  % ('Start', 'End', 'Trds', 'Ast', 'PnL'))
            print('  ' + '-' * 65)
            for c in losing_clusters[:10]:
                assets_str = ','.join(sorted(set(c['assets'])))
                print('  %s  %s  %3d   %3d  %+8.0f  %s'
                      % (c['start'].strftime('%Y-%m-%d'),
                         c['end'].strftime('%Y-%m-%d'),
                         c['n_trades'], c['n_assets'], c['pnl'],
                         assets_str))

    # =================================================================
    # COMPARISON TABLE
    # =================================================================
    print('\n' + '=' * 100)
    print('COMPARISON: max_entries_per_day = 1 vs 2 vs 3')
    print('=' * 100)
    print('%-8s %5s %6s %4s %6s %6s %9s %8s %8s'
          % ('Entries', 'medPF', 'mWR%', 'Prof', 'wDD%', 'mSh', 'TotalPnL',
             'Trades', 'Clusters'))
    print('-' * 72)
    for entries in ENTRIES_TO_TEST:
        results = all_data[entries]
        valid = {k: v for k, v in results.items() if 'error' not in v}
        if not valid:
            continue
        total_trades = sum(v['trades'] for v in valid.values())
        total_pnl = sum(v['net_pnl'] for v in valid.values())
        med_pf = np.median([v['pf'] for v in valid.values()])
        worst_dd = max(v['max_dd'] for v in valid.values())
        mean_sh = np.mean([v['sharpe'] for v in valid.values()])
        mean_wr = np.mean([v['wr'] for v in valid.values()])
        prof = sum(1 for v in valid.values() if v['net_pnl'] > 0)

        clusters = cluster_analysis(results)
        losing_cl = sum(1 for c in clusters if c['pnl'] < 0)

        print('%-8d %5.2f %5.1f%% %3d/7 %5.1f%% %5.2f %+9.0f %8d %8d'
              % (entries, med_pf, mean_wr, prof, worst_dd, mean_sh,
                 total_pnl, total_trades, losing_cl))

    # Delta analysis
    print('\n--- DELTA vs entries=1 ---')
    if 1 in all_data:
        base = all_data[1]
        base_valid = {k: v for k, v in base.items() if 'error' not in v}
        base_pnl = sum(v['net_pnl'] for v in base_valid.values())
        base_trades = sum(v['trades'] for v in base_valid.values())
        base_dd = max(v['max_dd'] for v in base_valid.values())
        for entries in [2, 3]:
            if entries not in all_data:
                continue
            r = all_data[entries]
            v = {k: vv for k, vv in r.items() if 'error' not in vv}
            t_pnl = sum(vv['net_pnl'] for vv in v.values())
            t_trades = sum(vv['trades'] for vv in v.values())
            t_dd = max(vv['max_dd'] for vv in v.values())
            print('  entries=%d: dPnL=%+.0f  dTrades=%+d  dDD=%+.1f%%'
                  % (entries, t_pnl - base_pnl, t_trades - base_trades,
                     t_dd - base_dd))

    print('\nDone.')


if __name__ == '__main__':
    main()
