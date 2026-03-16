"""
LUYTEN OOS Runner — Test specific parameter combos on out-of-sample period.

Runs the top N candidates from Phase 2 IS optimization on OOS dates (2024-2025).
Exports results in the same JSON format as the optimizer for comparison.

Usage:
    python tools/luyten_oos_runner.py
"""
import sys
import os
import json
import io
import contextlib
import warnings
from datetime import datetime
from pathlib import Path
from collections import defaultdict

import numpy as np
import backtrader as bt

warnings.filterwarnings('ignore')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
sys.path.insert(0, PROJECT_ROOT)

from strategies.luyten_strategy import LUYTENStrategy
from lib.commission import ETFCommission, ETFCSVData
from config.settings import BROKER_CONFIG


# =============================================================================
# OOS CONFIGURATION
# =============================================================================

DATA_PATH = 'data/TLT_5m_5Yea.csv'
ASSET_NAME = 'TLT'
FROM_DATE = datetime(2024, 1, 1)
TO_DATE = datetime(2025, 12, 31)
STARTING_CASH = 100000.0

# Base params (non-optimized values)
BASE_PARAMS = {
    'atr_length': 14,
    'atr_avg_period': 20,
    'sl_buffer_pips': 0.0,
    'use_eod_close': True,
    'eod_close_hour': 20,
    'eod_close_minute': 50,
    'use_time_filter': False,
    'allowed_hours': [],
    'use_day_filter': False,
    'allowed_days': [0, 1, 2, 3, 4],
    'use_sl_pips_filter': False,
    'sl_pips_min': 0.0,
    'sl_pips_max': 9999.0,
    'risk_percent': 0.01,
    'pip_value': 0.01,
    'lot_size': 1,
    'jpy_rate': 1.0,
    'is_jpy_pair': False,
    'is_etf': True,
    'margin_pct': 20.0,
    'print_signals': False,
    'export_reports': False,
}

# Top 10 candidates from Phase 2 IS optimization
# Format: (SL, TP, BkAbv, BkBdy, CBars)
OOS_CANDIDATES = [
    {'atr_sl_multiplier': 1.5, 'atr_tp_multiplier': 2.5, 'bk_above_min_pips': 2.0,  'bk_body_min_pips': 10.0, 'consolidation_bars': 19},
    {'atr_sl_multiplier': 1.5, 'atr_tp_multiplier': 2.5, 'bk_above_min_pips': 6.0,  'bk_body_min_pips': 0.0,  'consolidation_bars': 19},
    {'atr_sl_multiplier': 1.5, 'atr_tp_multiplier': 2.5, 'bk_above_min_pips': 6.0,  'bk_body_min_pips': 5.0,  'consolidation_bars': 19},
    {'atr_sl_multiplier': 1.5, 'atr_tp_multiplier': 2.5, 'bk_above_min_pips': 6.0,  'bk_body_min_pips': 10.0, 'consolidation_bars': 19},
    {'atr_sl_multiplier': 1.5, 'atr_tp_multiplier': 3.0, 'bk_above_min_pips': 6.0,  'bk_body_min_pips': 5.0,  'consolidation_bars': 19},
    {'atr_sl_multiplier': 1.5, 'atr_tp_multiplier': 2.0, 'bk_above_min_pips': 8.0,  'bk_body_min_pips': 5.0,  'consolidation_bars': 21},
    {'atr_sl_multiplier': 1.5, 'atr_tp_multiplier': 3.0, 'bk_above_min_pips': 6.0,  'bk_body_min_pips': 0.0,  'consolidation_bars': 19},
    {'atr_sl_multiplier': 1.5, 'atr_tp_multiplier': 2.5, 'bk_above_min_pips': 4.0,  'bk_body_min_pips': 10.0, 'consolidation_bars': 19},
    {'atr_sl_multiplier': 1.5, 'atr_tp_multiplier': 2.0, 'bk_above_min_pips': 8.0,  'bk_body_min_pips': 0.0,  'consolidation_bars': 21},
    {'atr_sl_multiplier': 1.5, 'atr_tp_multiplier': 2.0, 'bk_above_min_pips': 6.0,  'bk_body_min_pips': 5.0,  'consolidation_bars': 19},
]

SWEEP_KEYS = ['atr_sl_multiplier', 'atr_tp_multiplier', 'bk_above_min_pips',
              'bk_body_min_pips', 'consolidation_bars']


# =============================================================================
# BACKTEST ENGINE (identical to optimizer)
# =============================================================================

def run_single_backtest(params):
    try:
        cerebro = bt.Cerebro(stdstats=False)

        data_path = Path(PROJECT_ROOT) / DATA_PATH
        data = ETFCSVData(
            dataname=str(data_path),
            dtformat='%Y%m%d',
            tmformat='%H:%M:%S',
            datetime=0, time=1, open=2, high=3, low=4, close=5,
            volume=6, openinterest=-1,
            fromdate=FROM_DATE, todate=TO_DATE,
        )
        cerebro.adddata(data, name=ASSET_NAME)
        cerebro.broker.setcash(STARTING_CASH)

        broker_cfg = BROKER_CONFIG.get('darwinex_zero_etf',
                                       BROKER_CONFIG['darwinex_zero'])
        ETFCommission.total_commission = 0.0
        ETFCommission.total_contracts = 0.0
        ETFCommission.commission_calls = 0
        commission = ETFCommission(
            commission=broker_cfg.get('commission_per_contract', 0.02),
            margin_pct=broker_cfg.get('margin_percent', 20.0),
        )
        cerebro.broker.addcommissioninfo(commission)

        cerebro.addstrategy(LUYTENStrategy, **params)

        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            results = cerebro.run()

        strat = results[0]
        return _extract_metrics(strat, cerebro)

    except Exception as e:
        return {'error': str(e)}


def _extract_metrics(strat, cerebro):
    final_value = cerebro.broker.getvalue()
    total_pnl = final_value - STARTING_CASH

    trades = strat.trades
    wins = strat.wins
    losses = strat.losses
    gross_profit = strat.gross_profit
    gross_loss = strat.gross_loss

    wr = (wins / trades * 100) if trades > 0 else 0
    pf = (gross_profit / gross_loss) if gross_loss > 0 else (
        float('inf') if gross_profit > 0 else 0)

    max_dd = 0.0
    if strat._portfolio_values:
        peak = strat._portfolio_values[0]
        for v in strat._portfolio_values:
            if v > peak:
                peak = v
            dd = (peak - v) / peak * 100.0
            if dd > max_dd:
                max_dd = dd

    sharpe = 0.0
    if len(strat._portfolio_values) > 10:
        pv = strat._portfolio_values
        rets = np.array([(pv[i] - pv[i-1]) / pv[i-1]
                         for i in range(1, len(pv))])
        if strat._first_bar_dt and strat._last_bar_dt:
            d = (strat._last_bar_dt - strat._first_bar_dt).days
            yrs = max(d / 365.25, 0.1)
            ppy = len(pv) / yrs
        else:
            ppy = 252 * 24 * 12
        std = np.std(rets)
        if std > 0:
            sharpe = (np.mean(rets) * ppy) / (std * np.sqrt(ppy))

    cagr = 0.0
    if strat._trade_pnls and STARTING_CASH > 0:
        total_ret = final_value / STARTING_CASH
        if total_ret > 0:
            first_d = strat._trade_pnls[0]['date']
            last_d = strat._trade_pnls[-1]['date']
            years = max((last_d - first_d).days / 365.25, 0.1)
            cagr = (pow(total_ret, 1.0 / years) - 1.0) * 100.0

    yearly = defaultdict(lambda: {
        'trades': 0, 'wins': 0, 'pnl': 0.0,
        'gross_profit': 0.0, 'gross_loss': 0.0,
    })
    for t in strat._trade_pnls:
        y = t['year']
        yearly[y]['trades'] += 1
        yearly[y]['pnl'] += t['pnl']
        if t['is_winner']:
            yearly[y]['wins'] += 1
            yearly[y]['gross_profit'] += t['pnl']
        else:
            yearly[y]['gross_loss'] += abs(t['pnl'])

    yearly_list = {}
    for y in sorted(yearly.keys()):
        s = yearly[y]
        y_wr = (s['wins'] / s['trades'] * 100) if s['trades'] > 0 else 0
        y_pf = (s['gross_profit'] / s['gross_loss']) if s['gross_loss'] > 0 else (
            float('inf') if s['gross_profit'] > 0 else 0)
        yearly_list[y] = {
            'trades': s['trades'], 'wr': y_wr, 'pf': y_pf, 'pnl': s['pnl'],
        }

    return {
        'trades': trades, 'wins': wins, 'losses': losses,
        'wr': wr, 'pf': pf,
        'gross_profit': gross_profit, 'gross_loss': gross_loss,
        'net_pnl': total_pnl, 'final_value': final_value,
        'max_dd': max_dd, 'sharpe': sharpe, 'cagr': cagr,
        'yearly': yearly_list,
    }


def fmt_pf(pf):
    return '%.2f' % pf if pf < 100 else 'INF'


# =============================================================================
# MAIN
# =============================================================================

def main():
    total = len(OOS_CANDIDATES)

    print('=' * 70)
    print('LUYTEN OOS VALIDATION')
    print('=' * 70)
    print('Asset: %s' % ASSET_NAME)
    print('OOS Period: %s to %s' % (FROM_DATE.strftime('%Y-%m-%d'),
                                     TO_DATE.strftime('%Y-%m-%d')))
    print('Starting cash: $%s' % format(STARTING_CASH, ',.0f'))
    print('Candidates: %d' % total)
    print('-' * 70)

    all_results = []
    for i, candidate in enumerate(OOS_CANDIDATES):
        params = dict(BASE_PARAMS)
        params.update(candidate)

        label = ', '.join('%s=%s' % (k, candidate[k]) for k in SWEEP_KEYS)
        print('[%d/%d] %s ...' % (i + 1, total, label), end='', flush=True)

        metrics = run_single_backtest(params)
        all_results.append((params, metrics))

        if metrics and 'error' not in metrics:
            print(' → Trades=%d, PF=%s, DD=%.1f%%, Sharpe=%.2f'
                  % (metrics['trades'], fmt_pf(metrics['pf']),
                     metrics['max_dd'], metrics['sharpe']))
        else:
            print(' → ERROR: %s' % metrics.get('error', 'unknown'))

    # Save JSON
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_dir = Path(PROJECT_ROOT) / 'logs'
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / ('LUYTEN_OOS_%s.json' % timestamp)

    sorted_results = sorted(
        all_results,
        key=lambda r: r[1].get('pf', 0) if r[1].get('pf', 0) < 100 else 99.99,
        reverse=True,
    )

    data = {
        'optimizer': 'LUYTEN_OOS',
        'timestamp': datetime.now().isoformat(),
        'asset': ASSET_NAME,
        'period': {'from': FROM_DATE.strftime('%Y-%m-%d'),
                   'to': TO_DATE.strftime('%Y-%m-%d')},
        'starting_cash': STARTING_CASH,
        'sweep_keys': SWEEP_KEYS,
        'total_combinations': total,
        'results': [],
    }

    for params, metrics in sorted_results:
        entry = {'params': {k: params[k] for k in SWEEP_KEYS}}
        if 'error' in metrics:
            entry['error'] = metrics['error']
        else:
            entry['overall'] = {
                'trades': metrics['trades'],
                'wins': metrics['wins'],
                'losses': metrics['losses'],
                'wr': round(metrics['wr'], 2),
                'pf': round(metrics['pf'], 4) if metrics['pf'] < 100 else None,
                'gross_profit': round(metrics['gross_profit'], 2),
                'gross_loss': round(metrics['gross_loss'], 2),
                'net_pnl': round(metrics['net_pnl'], 2),
                'max_dd_pct': round(metrics['max_dd'], 2),
                'sharpe': round(metrics['sharpe'], 4),
                'cagr_pct': round(metrics['cagr'], 2),
            }
            entry['yearly'] = {}
            for y, yd in sorted(metrics.get('yearly', {}).items()):
                entry['yearly'][str(y)] = {
                    'trades': yd['trades'],
                    'wr': round(yd['wr'], 2),
                    'pf': round(yd['pf'], 4) if yd['pf'] < 100 else None,
                    'pnl': round(yd['pnl'], 2),
                }
        data['results'].append(entry)

    valid = [r for r in data['results'] if 'error' not in r and r['overall']['trades'] >= 1]
    if valid:
        data['best'] = valid[0]

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print('\n' + '=' * 70)
    print('OOS Results saved to: %s' % out_path)
    print('=' * 70)
    print('\nNext: compare IS vs OOS with:')
    print('  python tools/analyze_optimizer.py logs/LUYTEN_optimizer_20260316_075318.json --compare %s --top 10' % out_path.name)

    return out_path


if __name__ == '__main__':
    main()
