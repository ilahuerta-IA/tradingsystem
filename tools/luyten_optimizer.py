"""
LUYTEN Strategy Optimizer - Grid Search with Yearly Breakdown

Runs parameter grid search over LUYTEN ORB strategy for ETFs/CFD indices.
Shows per-year stats (PF, Trades, DD, Sharpe, CAGR) for each combo.

Usage:
    python tools/luyten_optimizer.py              # default asset (TLT)
    python tools/luyten_optimizer.py AUS200       # select AUS200

Configure:
    1. Add/edit ASSET_PROFILES for each asset
    2. Set OPTIMIZE_* = True/False to enable/disable each parameter
    3. Set range + step for each parameter in the profile
"""
import sys
import os
import json
import math
import warnings
import itertools
from datetime import datetime
from pathlib import Path
from collections import defaultdict

import numpy as np
import backtrader as bt

warnings.filterwarnings('ignore')

# Add project root to path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
sys.path.insert(0, PROJECT_ROOT)

from strategies.luyten_strategy import LUYTENStrategy
from lib.commission import ETFCommission, CFDIndexCommission, ETFCSVData
from config.settings import BROKER_CONFIG


# =============================================================================
# ASSET PROFILES
# =============================================================================

ASSET_PROFILES = {
    'TLT': {
        'data_path': 'data/TLT_5m_5Yea.csv',
        'broker_config_key': 'darwinex_zero_etf',
        'from_date': datetime(2020, 1, 1),
        'to_date': datetime(2023, 12, 31),
        'ranges': {
            'consolidation_bars_min': (10, 18, 2),
            'consolidation_bars_max': (14, 22, 2),
            'bk_above_min_pips': (2.0, 8.0, 2.0),
            'bk_body_min_pips': (0.0, 15.0, 5.0),
            'atr_tp_multiplier': (2.0, 3.5, 0.5),
            'atr_sl_multiplier': (1.5, 2.0, 0.5),
        },
        'base_params': {
            'session_start_hour': None,
            'session_start_minute': 0,
            'consolidation_bars_min': 12,
            'consolidation_bars_max': 18,
            'bk_above_min_pips': 2.0,
            'bk_body_min_pips': 10.0,
            'atr_length': 14,
            'atr_avg_period': 20,
            'atr_sl_multiplier': 1.5,
            'atr_tp_multiplier': 3.0,
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
        },
    },
    'AUS200': {
        'data_path': 'data/AUS200_5m_5Yea.csv',
        'broker_config_key': 'darwinex_zero_cfd_index',
        'from_date': datetime(2020, 1, 1),
        'to_date': datetime(2023, 12, 31),
        'ranges': {
            'consolidation_bars_min': (13, 19, 2),
            'consolidation_bars_max': (17, 23, 2),
            'bk_above_min_pips': (3.0, 7.0, 2.0),
            'bk_body_min_pips': (0.0, 10.0, 5.0),
            'atr_tp_multiplier': (2.0, 3.5, 0.5),
            'atr_sl_multiplier': (1.5, 2.0, 0.5),
        },
        'base_params': {
            'session_start_hour': 8,
            'session_start_minute': 0,
            'dst_mode': 'london_uk',
            'consolidation_bars_min': 15,
            'consolidation_bars_max': 21,
            'bk_above_min_pips': 5.0,
            'bk_body_min_pips': 0.0,
            'atr_length': 14,
            'atr_avg_period': 20,
            'atr_sl_multiplier': 1.5,
            'atr_tp_multiplier': 3.0,
            'sl_buffer_pips': 0.0,
            'use_eod_close': True,
            'eod_close_hour': 20,
            'eod_close_minute': 50,
            'use_time_filter': False,
            'allowed_hours': [],
            'use_day_filter': False,
            'allowed_days': [0, 1, 2, 3, 4],
            'use_sl_pips_filter': False,
            'sl_pips_min': 8.0,
            'sl_pips_max': 80.0,
            'risk_percent': 0.01,
            'pip_value': 1.0,
            'lot_size': 1,
            'jpy_rate': 1.0,
            'is_jpy_pair': False,
            'is_etf': True,
            'margin_pct': 5.0,
            'print_signals': False,
            'export_reports': False,
        },
    },
}

# =============================================================================
# ACTIVE CONFIGURATION (resolved from CLI arg or default)
# =============================================================================

_asset_arg = sys.argv[1] if len(sys.argv) > 1 else 'TLT'
if _asset_arg not in ASSET_PROFILES:
    print("ERROR: Unknown asset '%s'. Available: %s"
          % (_asset_arg, ', '.join(sorted(ASSET_PROFILES.keys()))))
    sys.exit(1)

_profile = ASSET_PROFILES[_asset_arg]
ASSET_NAME = _asset_arg
DATA_PATH = _profile['data_path']
BROKER_CONFIG_KEY = _profile['broker_config_key']
FROM_DATE = _profile['from_date']
TO_DATE = _profile['to_date']
STARTING_CASH = 100000.0
BASE_PARAMS = dict(_profile['base_params'])

# --- Parameter toggles: True = sweep this param, False = use base value ---
OPTIMIZE_CONSOLIDATION_BARS_MIN = True
OPTIMIZE_CONSOLIDATION_BARS_MAX = True
OPTIMIZE_BK_ABOVE_MIN_PIPS = True
OPTIMIZE_BK_BODY_MIN_PIPS = True
OPTIMIZE_ATR_TP_MULTIPLIER = True
OPTIMIZE_ATR_SL_MULTIPLIER = True

# --- Sweep ranges from profile ---
RANGE_CONSOLIDATION_BARS_MIN = _profile['ranges']['consolidation_bars_min']
RANGE_CONSOLIDATION_BARS_MAX = _profile['ranges']['consolidation_bars_max']
RANGE_BK_ABOVE_MIN_PIPS = _profile['ranges']['bk_above_min_pips']
RANGE_BK_BODY_MIN_PIPS = _profile['ranges']['bk_body_min_pips']
RANGE_ATR_TP_MULTIPLIER = _profile['ranges']['atr_tp_multiplier']
RANGE_ATR_SL_MULTIPLIER = _profile['ranges']['atr_sl_multiplier']


# =============================================================================
# GRID GENERATION
# =============================================================================

def _frange(start, stop, step):
    """Float range inclusive of stop."""
    values = []
    current = start
    while current <= stop + step * 0.001:
        values.append(round(current, 6))
        current += step
    return values


def build_param_grid():
    """Build list of param dicts to test."""
    sweep = {}

    if OPTIMIZE_CONSOLIDATION_BARS_MIN:
        s, e, st = RANGE_CONSOLIDATION_BARS_MIN
        sweep['consolidation_bars_min'] = list(range(int(s), int(e) + 1, int(st)))
    if OPTIMIZE_CONSOLIDATION_BARS_MAX:
        s, e, st = RANGE_CONSOLIDATION_BARS_MAX
        sweep['consolidation_bars_max'] = list(range(int(s), int(e) + 1, int(st)))
    if OPTIMIZE_BK_ABOVE_MIN_PIPS:
        sweep['bk_above_min_pips'] = _frange(*RANGE_BK_ABOVE_MIN_PIPS)
    if OPTIMIZE_BK_BODY_MIN_PIPS:
        sweep['bk_body_min_pips'] = _frange(*RANGE_BK_BODY_MIN_PIPS)
    if OPTIMIZE_ATR_TP_MULTIPLIER:
        sweep['atr_tp_multiplier'] = _frange(*RANGE_ATR_TP_MULTIPLIER)
    if OPTIMIZE_ATR_SL_MULTIPLIER:
        sweep['atr_sl_multiplier'] = _frange(*RANGE_ATR_SL_MULTIPLIER)

    if not sweep:
        print("ERROR: No parameter enabled for optimization.")
        print("Set at least one OPTIMIZE_* = True")
        sys.exit(1)

    keys = sorted(sweep.keys())
    combos = list(itertools.product(*(sweep[k] for k in keys)))

    grid = []
    for combo in combos:
        params = dict(BASE_PARAMS)
        for k, v in zip(keys, combo):
            params[k] = v
        # Skip invalid combos where min > max
        cb_min = params.get('consolidation_bars_min', 0)
        cb_max = params.get('consolidation_bars_max', 9999)
        if cb_min > cb_max:
            continue
        grid.append(params)

    return grid, keys


# =============================================================================
# SINGLE BACKTEST
# =============================================================================

def run_single_backtest(params):
    """
    Run one LUYTEN backtest silently and return metrics dict.
    Returns None if backtest fails.
    """
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

        broker_cfg = BROKER_CONFIG.get(BROKER_CONFIG_KEY,
                                       BROKER_CONFIG['darwinex_zero'])
        if 'cfd_index' in BROKER_CONFIG_KEY:
            CFDIndexCommission.total_commission = 0.0
            CFDIndexCommission.total_contracts = 0.0
            CFDIndexCommission.commission_calls = 0
            commission = CFDIndexCommission(
                commission=broker_cfg.get('commission_per_contract', 0.275),
                margin_pct=broker_cfg.get('margin_percent', 5.0),
            )
        else:
            ETFCommission.total_commission = 0.0
            ETFCommission.total_contracts = 0.0
            ETFCommission.commission_calls = 0
            commission = ETFCommission(
                commission=broker_cfg.get('commission_per_contract', 0.02),
                margin_pct=broker_cfg.get('margin_percent', 20.0),
            )
        cerebro.broker.addcommissioninfo(commission)

        cerebro.addstrategy(LUYTENStrategy, **params)

        # Suppress all print output from strategy
        import io
        import contextlib
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            results = cerebro.run()

        strat = results[0]
        return _extract_metrics(strat, cerebro)

    except Exception as e:
        return {'error': str(e)}


def _extract_metrics(strat, cerebro):
    """Extract all metrics from a completed strategy run."""
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

    # Max Drawdown
    max_dd = 0.0
    if strat._portfolio_values:
        peak = strat._portfolio_values[0]
        for v in strat._portfolio_values:
            if v > peak:
                peak = v
            dd = (peak - v) / peak * 100.0
            if dd > max_dd:
                max_dd = dd

    # Sharpe
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

    # CAGR
    cagr = 0.0
    if strat._trade_pnls and STARTING_CASH > 0:
        total_ret = final_value / STARTING_CASH
        if total_ret > 0:
            first_d = strat._trade_pnls[0]['date']
            last_d = strat._trade_pnls[-1]['date']
            years = max((last_d - first_d).days / 365.25, 0.1)
            cagr = (pow(total_ret, 1.0 / years) - 1.0) * 100.0

    # Yearly breakdown
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


# =============================================================================
# DISPLAY
# =============================================================================

def fmt_pf(pf):
    return '%.2f' % pf if pf < 100 else 'INF'


def print_results(all_results, sweep_keys):
    """Print formatted results table with yearly breakdown."""
    if not all_results:
        print("No results to display.")
        return

    # Collect all years
    all_years = set()
    for _, metrics in all_results:
        if 'yearly' in metrics:
            all_years.update(metrics['yearly'].keys())
    years = sorted(all_years)

    # Header
    print('\n' + '=' * 120)
    print('LUYTEN OPTIMIZER RESULTS')
    print('Data: %s | Period: %s to %s | Cash: $%s'
          % (ASSET_NAME, FROM_DATE.strftime('%Y-%m-%d'),
             TO_DATE.strftime('%Y-%m-%d'), format(STARTING_CASH, ',.0f')))
    print('Parameters swept: %s' % ', '.join(sweep_keys))
    print('=' * 120)

    # Build param columns
    param_headers = []
    for k in sweep_keys:
        short = k.replace('consolidation_bars_min', 'CBMin') \
                 .replace('consolidation_bars_max', 'CBMax') \
                 .replace('bk_above_min_pips', 'BkAbv') \
                 .replace('bk_body_min_pips', 'BkBdy') \
                 .replace('atr_tp_multiplier', 'TP_M') \
                 .replace('atr_sl_multiplier', 'SL_M')
        param_headers.append(short)

    # Overall header
    hdr_params = '  '.join('%-6s' % h for h in param_headers)
    hdr_overall = '%6s %5s %6s %6s %6s %6s %10s' % (
        'Trds', 'WR%', 'PF', 'DD%', 'Shrpe', 'CAGR%', 'Net PnL')

    # Year headers
    hdr_years = ''
    for y in years:
        hdr_years += '  | %4d: %4s %5s %6s' % (y, 'Trds', 'PF', 'PnL')

    print('\n%s  %s%s' % (hdr_params, hdr_overall, hdr_years))
    print('-' * (len(hdr_params) + 2 + 55 + len(hdr_years)))

    # Sort by PF descending
    sorted_results = sorted(all_results,
                            key=lambda r: r[1].get('pf', 0)
                            if r[1].get('pf', 0) < 100 else 99.99,
                            reverse=True)

    for params, metrics in sorted_results:
        if 'error' in metrics:
            vals = '  '.join('%-6s' % str(params.get(k, '?')) for k in sweep_keys)
            print('%s  ERROR: %s' % (vals, metrics['error']))
            continue

        # Param values
        vals = '  '.join('%-6s' % str(params.get(k, '?')) for k in sweep_keys)

        # Overall metrics
        row = '%6d %4.1f%% %6s %5.1f%% %+5.2f %+5.1f%% %+10s' % (
            metrics['trades'], metrics['wr'], fmt_pf(metrics['pf']),
            metrics['max_dd'], metrics['sharpe'], metrics['cagr'],
            format(metrics['net_pnl'], ',.0f'))

        # Yearly
        yr_str = ''
        for y in years:
            yd = metrics.get('yearly', {}).get(y)
            if yd:
                yr_str += '  | %4d: %4d %5s %+6s' % (
                    y, yd['trades'], fmt_pf(yd['pf']),
                    format(yd['pnl'], ',.0f'))
            else:
                yr_str += '  | %4d: %4s %5s %6s' % (y, '-', '-', '-')

        print('%s  %s%s' % (vals, row, yr_str))

    # Best combo
    valid = [(p, m) for p, m in sorted_results
             if 'error' not in m and m['trades'] >= 10]
    if valid:
        best = valid[0]
        print('\n' + '=' * 80)
        best_vals = ', '.join('%s=%s' % (k, best[0].get(k)) for k in sweep_keys)
        print('BEST: %s -> PF=%s, Trades=%d, DD=%.1f%%, Sharpe=%.2f, CAGR=%.1f%%'
              % (best_vals, fmt_pf(best[1]['pf']), best[1]['trades'],
                 best[1]['max_dd'], best[1]['sharpe'], best[1]['cagr']))
        print('=' * 80)


# =============================================================================
# JSON EXPORT
# =============================================================================

def save_results_json(all_results, sweep_keys):
    """Save optimizer results to JSON in logs/."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_dir = Path(PROJECT_ROOT) / 'logs'
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / ('LUYTEN_optimizer_%s.json' % timestamp)

    # Sort by PF descending
    sorted_results = sorted(
        all_results,
        key=lambda r: r[1].get('pf', 0) if r[1].get('pf', 0) < 100 else 99.99,
        reverse=True,
    )

    data = {
        'optimizer': 'LUYTEN',
        'timestamp': datetime.now().isoformat(),
        'asset': ASSET_NAME,
        'period': {'from': FROM_DATE.strftime('%Y-%m-%d'),
                   'to': TO_DATE.strftime('%Y-%m-%d')},
        'starting_cash': STARTING_CASH,
        'sweep_keys': sweep_keys,
        'total_combinations': len(all_results),
        'results': [],
    }

    for params, metrics in sorted_results:
        entry = {
            'params': {k: params[k] for k in sweep_keys},
        }
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

    # Best combo
    valid = [r for r in data['results'] if 'error' not in r and r['overall']['trades'] >= 10]
    if valid:
        data['best'] = valid[0]

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print('\nResults saved to: %s' % out_path)
    return out_path


# =============================================================================
# MAIN
# =============================================================================

def main():
    grid, sweep_keys = build_param_grid()
    total = len(grid)

    print('=' * 70)
    print('LUYTEN OPTIMIZER')
    print('=' * 70)
    print('Asset: %s' % ASSET_NAME)
    print('Period: %s to %s' % (FROM_DATE.strftime('%Y-%m-%d'),
                                 TO_DATE.strftime('%Y-%m-%d')))
    print('Starting cash: $%s' % format(STARTING_CASH, ',.0f'))
    print('\nParameters to optimize:')
    for k in sweep_keys:
        vals = sorted(set(p[k] for p in grid))
        print('  %s: %s' % (k, vals))
    print('\nTotal combinations: %d' % total)
    print('-' * 70)

    all_results = []
    for i, params in enumerate(grid):
        label = ', '.join('%s=%s' % (k, params[k]) for k in sweep_keys)
        print('[%d/%d] Running: %s ...' % (i + 1, total, label), end='', flush=True)

        metrics = run_single_backtest(params)
        all_results.append((params, metrics))

        if metrics and 'error' not in metrics:
            print(' -> Trades=%d, PF=%s, DD=%.1f%%, Sharpe=%.2f'
                  % (metrics['trades'], fmt_pf(metrics['pf']),
                     metrics['max_dd'], metrics['sharpe']))
        else:
            print(' -> ERROR: %s' % metrics.get('error', 'unknown'))

    print_results(all_results, sweep_keys)
    save_results_json(all_results, sweep_keys)


if __name__ == '__main__':
    main()
