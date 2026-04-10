"""
ALTAIR Deep Compare -- Yearly breakdown for top parameter candidates.

Runs selected combos across all 7 assets, shows per-year PnL, WR, PF
per asset, plus aggregated yearly metrics and consistency scores.

Usage:
    python tools/altair_deep_compare.py
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

from strategies.altair_strategy import ALTAIRStrategy
from lib.commission import ETFCommission, ETFCSVData
from config.settings_altair import (
    ALTAIR_STRATEGIES_CONFIG, ALTAIR_BROKER_CONFIG, _DEFAULT_PARAMS,
)


# =============================================================================
# CANDIDATES TO COMPARE
# =============================================================================

CANDIDATES = {
    'A: tp3.0 os25 t10 (current)': {
        'max_sl_atr_mult': 2.0,
        'tp_atr_mult': 3.0,
        'dtosc_os': 25,
        'tr1bh_timeout': 10,
    },
    'B: tp3.0 os25 t5': {
        'max_sl_atr_mult': 2.0,
        'tp_atr_mult': 3.0,
        'dtosc_os': 25,
        'tr1bh_timeout': 5,
    },
    'C: tp4.0 os25 t10': {
        'max_sl_atr_mult': 2.0,
        'tp_atr_mult': 4.0,
        'dtosc_os': 25,
        'tr1bh_timeout': 10,
    },
    'D: tp4.0 os25 t5': {
        'max_sl_atr_mult': 2.0,
        'tp_atr_mult': 4.0,
        'dtosc_os': 25,
        'tr1bh_timeout': 5,
    },
    'E: tp3.0 os20 t5': {
        'max_sl_atr_mult': 2.0,
        'tp_atr_mult': 3.0,
        'dtosc_os': 20,
        'tr1bh_timeout': 5,
    },
    'F: tp4.0 os20 t5': {
        'max_sl_atr_mult': 2.0,
        'tp_atr_mult': 4.0,
        'dtosc_os': 20,
        'tr1bh_timeout': 5,
    },
    'G: tp5.0 os25 t10': {
        'max_sl_atr_mult': 2.0,
        'tp_atr_mult': 5.0,
        'dtosc_os': 25,
        'tr1bh_timeout': 10,
    },
    'H: tp3.5 os25 t10': {
        'max_sl_atr_mult': 2.0,
        'tp_atr_mult': 3.5,
        'dtosc_os': 25,
        'tr1bh_timeout': 10,
    },
}


# =============================================================================
# ASSETS
# =============================================================================

ASSETS = {}
for key, cfg in ALTAIR_STRATEGIES_CONFIG.items():
    if cfg.get('active', True):
        ASSETS[cfg['asset_name']] = {
            'data_path': cfg['data_path'],
            'from_date': cfg['from_date'],
            'to_date': cfg['to_date'],
        }

STARTING_CASH = 100_000.0
ASSET_NAMES = sorted(ASSETS.keys())


# =============================================================================
# BACKTEST + METRICS
# =============================================================================

def run_bt(asset_name, asset_cfg, overrides):
    try:
        cerebro = bt.Cerebro(stdstats=False)
        from pathlib import Path
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
        params.update(overrides)
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

    # Sortino
    sortino = 0.0
    if len(strat._portfolio_values) > 10:
        pv = strat._portfolio_values
        rets = np.array([(pv[i] - pv[i-1]) / pv[i-1]
                         for i in range(1, len(pv))])
        neg = rets[rets < 0]
        if len(neg) > 0:
            dd_std = np.std(neg)
            if strat._first_bar_dt and strat._last_bar_dt:
                days = (strat._last_bar_dt - strat._first_bar_dt).days
                yrs = max(days / 365.25, 0.1)
                ppy = len(pv) / yrs
            else:
                ppy = 252 * 7
            if dd_std > 0:
                sortino = (np.mean(rets) * ppy) / (dd_std * np.sqrt(ppy))

    # Yearly
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
            'trades': s['trades'], 'wr': y_wr, 'pf': y_pf, 'pnl': s['pnl']}

    return {
        'trades': t, 'wr': wr, 'pf': pf, 'net_pnl': pnl,
        'max_dd': dd, 'sharpe': sharpe, 'sortino': sortino,
        'yearly': yearly_dict,
    }


def fmt_pf(pf):
    return '%.2f' % pf if pf < 100 else 'INF'


# =============================================================================
# MAIN
# =============================================================================

def main():
    total_bt = len(CANDIDATES) * len(ASSET_NAMES)
    print('=' * 100)
    print('ALTAIR DEEP COMPARE -- Yearly Breakdown')
    print('=' * 100)
    print('Candidates: %d | Assets: %d | Total BT: %d'
          % (len(CANDIDATES), len(ASSET_NAMES), total_bt))
    print('=' * 100)

    # Collect all years across all data
    all_years = set()

    # Run all
    results = {}  # {candidate_name: {asset: metrics}}
    for cname, overrides in CANDIDATES.items():
        print('\n>>> %s' % cname)
        results[cname] = {}
        for asset in ASSET_NAMES:
            m = run_bt(asset, ASSETS[asset], overrides)
            results[cname][asset] = m
            if 'error' not in m:
                all_years.update(m['yearly'].keys())
                print('  %-6s T=%2d PF=%5s WR=%4.1f%% DD=%5.2f%% '
                      'Sh=%5.2f So=%5.2f PnL=$%8.0f'
                      % (asset, m['trades'], fmt_pf(m['pf']), m['wr'],
                         m['max_dd'], m['sharpe'], m['sortino'],
                         m['net_pnl']))

    years = sorted(all_years)

    # =================================================================
    # YEARLY PNL HEATMAP PER CANDIDATE
    # =================================================================
    for cname in CANDIDATES:
        print('\n' + '=' * 100)
        print('YEARLY PnL: %s' % cname)
        print('=' * 100)

        # Header
        hdr = '%-7s' % 'Asset'
        for y in years:
            hdr += ' %8d' % y
        hdr += ' %10s %6s %6s' % ('TOTAL', 'Sh', 'So')
        print(hdr)
        print('-' * len(hdr))

        yearly_totals = {y: 0.0 for y in years}
        yearly_positive_count = {y: 0 for y in years}
        total_positive_years_per_asset = {}

        for asset in ASSET_NAMES:
            m = results[cname][asset]
            if 'error' in m:
                print('%-7s ERROR' % asset)
                continue

            row = '%-7s' % asset
            pos_years = 0
            for y in years:
                yd = m['yearly'].get(y, {})
                pnl = yd.get('pnl', 0.0)
                yearly_totals[y] += pnl
                if pnl > 0:
                    yearly_positive_count[y] += 1
                    pos_years += 1
                elif pnl == 0 and yd.get('trades', 0) == 0:
                    pos_years += 0  # neutral
                # Color hint: + or - prefix
                if yd.get('trades', 0) == 0:
                    row += '      -- '
                elif pnl >= 0:
                    row += ' %+7.0f ' % pnl
                else:
                    row += ' %+7.0f ' % pnl
            row += ' %+9.0f' % m['net_pnl']
            row += ' %6.2f' % m['sharpe']
            row += ' %6.2f' % m['sortino']
            total_positive_years_per_asset[asset] = pos_years
            print(row)

        # Totals row
        print('-' * len(hdr))
        row = '%-7s' % 'TOTAL'
        for y in years:
            row += ' %+7.0f ' % yearly_totals[y]
        total_all = sum(yearly_totals.values())
        row += ' %+9.0f' % total_all
        print(row)

        # Positive count row
        row = '%-7s' % '+count'
        for y in years:
            row += '    %d/%d  ' % (yearly_positive_count[y],
                                     len(ASSET_NAMES))
        print(row)

    # =================================================================
    # SUMMARY COMPARISON TABLE
    # =================================================================
    print('\n' + '=' * 100)
    print('SUMMARY COMPARISON')
    print('=' * 100)
    print('%-30s %5s %5s %5s %6s %6s %6s %5s %10s %5s'
          % ('Candidate', 'medPF', 'mWR%', 'Prof',
             'wDD%', 'mSh', 'mSo', '+Yrs', 'TotalPnL', 'Score'))
    print('-' * 100)

    ranked = []
    for cname in CANDIDATES:
        pfs, wrs, sharpes, sortinos = [], [], [], []
        profitable = 0
        worst_dd = 0.0
        total_pnl = 0.0
        total_positive_asset_years = 0
        total_asset_years = 0

        for asset in ASSET_NAMES:
            m = results[cname][asset]
            if 'error' in m:
                continue
            p = m['pf'] if m['pf'] < 100 else 99.0
            pfs.append(p)
            wrs.append(m['wr'])
            sharpes.append(m['sharpe'])
            sortinos.append(m['sortino'])
            total_pnl += m['net_pnl']
            if m['net_pnl'] > 0:
                profitable += 1
            if m['max_dd'] > worst_dd:
                worst_dd = m['max_dd']
            # Count positive years per asset
            for y in years:
                yd = m['yearly'].get(y, {})
                if yd.get('trades', 0) > 0:
                    total_asset_years += 1
                    if yd.get('pnl', 0) > 0:
                        total_positive_asset_years += 1

        if not pfs:
            continue

        med_pf = float(np.median(pfs))
        m_wr = float(np.mean(wrs))
        m_sh = float(np.mean(sharpes))
        m_so = float(np.mean(sortinos))

        # Consistency score: positive asset-years / total asset-years
        consistency = (total_positive_asset_years / total_asset_years * 100
                       if total_asset_years > 0 else 0)

        # Score: emphasize consistency + profitability
        score = med_pf * (1 + profitable * 0.1) * (1 + consistency / 200.0)

        ranked.append((cname, med_pf, m_wr, profitable, worst_dd,
                        m_sh, m_so, total_positive_asset_years,
                        total_asset_years, total_pnl, score))

        pos_str = '%d/%d' % (total_positive_asset_years, total_asset_years)
        print('%-30s %5s %4.1f%% %3d/7 %5.1f%% %6.2f %6.2f %5s %+9.0f %6.3f'
              % (cname, fmt_pf(med_pf), m_wr, profitable, worst_dd,
                 m_sh, m_so, pos_str, total_pnl, score))

    # Sort by score
    ranked.sort(key=lambda x: x[-1], reverse=True)
    print('\n--- RANKING BY SCORE ---')
    for i, r in enumerate(ranked, 1):
        print('%d. %s (score=%.3f)' % (i, r[0], r[-1]))


if __name__ == '__main__':
    main()
