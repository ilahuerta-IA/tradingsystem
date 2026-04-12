"""
LYRA Optimizer -- Multi-Index Grid Search for Short Strategy

Runs parameter combinations across index CFDs simultaneously.
Each combo is tested on every active index, then aggregated.
Adapted from altair_optimizer.py for the LYRA short strategy.

Scores by: median PF across all indices.
Secondary: count profitable, mean WR, worst MaxDD.

Usage:
    python tools/lyra_optimizer.py                    # default: SL phase
    python tools/lyra_optimizer.py --phase sl
    python tools/lyra_optimizer.py --phase tp
    python tools/lyra_optimizer.py --phase entry
    python tools/lyra_optimizer.py --phase holding
    python tools/lyra_optimizer.py --index NDX        # single index only

Output: logs/LYRA_optimizer_<phase>_<timestamp>.json
"""
import sys
import os
import io
import json
import math
import contextlib
import warnings
import itertools
from datetime import datetime
from pathlib import Path
from collections import defaultdict

import numpy as np
import backtrader as bt

warnings.filterwarnings('ignore')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
sys.path.insert(0, PROJECT_ROOT)

from strategies.lyra_strategy import LYRAStrategy
from lib.commission import CFDIndexCommission, ETFCSVData
from config.settings_lyra import (
    LYRA_STRATEGIES_CONFIG, LYRA_BROKER_CONFIG,
)


# =============================================================================
# ASSETS
# =============================================================================

def _load_assets(index_filter=None):
    """Load LYRA index configs, optionally filtered to a single index."""
    assets = {}
    for key, cfg in LYRA_STRATEGIES_CONFIG.items():
        if not cfg.get('active', True):
            continue
        if index_filter and cfg['asset_name'] != index_filter:
            continue
        assets[cfg['asset_name']] = {
            'data_path': cfg['data_path'],
            'from_date': cfg['from_date'],
            'to_date': cfg['to_date'],
            'broker_config_key': cfg.get('broker_config_key',
                                         'darwinex_zero_cfd_sp500'),
            'params': cfg.get('params', {}),
        }
    return assets

STARTING_CASH = 100_000.0


# =============================================================================
# PHASE DEFINITIONS
# =============================================================================

PHASES = {
    'sl': {
        'description': 'Stop Loss parameters',
        'grid': {
            'max_sl_atr_mult': [1.5, 2.0, 3.0, 4.0, 5.0],
            'sl_atr_mult': [1.5, 2.0, 2.5, 3.0],
        },
        'fixed': {},
    },
    'tp': {
        'description': 'Take Profit parameters',
        'grid': {
            'tp_atr_mult': [0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0],
        },
        'fixed': {},
    },
    'entry': {
        'description': 'Entry / DTOSC parameters',
        'grid': {
            'tr1bl_timeout': [3, 5, 8, 10],
            'dtosc_ob': [70, 75, 80],
        },
        'fixed': {},
    },
    'holding': {
        'description': 'Holding period parameters',
        'grid': {
            'max_holding_bars': [20, 35, 50, 70, 100],
        },
        'fixed': {},
    },
    'regime': {
        'description': 'Regime filter variants',
        'grid': {
            'allowed_regimes': [
                (1,),           # VOLATILE_UP only
                (1, 2),         # VOLATILE_UP + CALM_DOWN
                (1, 3),         # VOLATILE_UP + VOLATILE_DOWN
                (1, 2, 3),      # all non-CALM_UP
            ],
        },
        'fixed': {},
    },
    'confirmation': {
        'description': 'Tr-1BL on/off',
        'grid': {
            'use_tr1bl': [True, False],
        },
        'fixed': {},
    },
}


# =============================================================================
# GRID GENERATION
# =============================================================================

def build_param_grid(phase_name):
    phase = PHASES[phase_name]
    grid_def = phase['grid']
    keys = sorted(grid_def.keys())
    combos = list(itertools.product(*(grid_def[k] for k in keys)))
    grid = []
    for combo in combos:
        overrides = dict(zip(keys, combo))
        overrides.update(phase.get('fixed', {}))
        grid.append(overrides)
    return grid, keys


# =============================================================================
# SINGLE INDEX BACKTEST
# =============================================================================

def run_single_backtest(asset_name, asset_cfg, param_overrides):
    """Run one LYRA backtest silently.  Returns metrics dict or error."""
    try:
        cerebro = bt.Cerebro(stdstats=False)

        data_path = Path(PROJECT_ROOT) / asset_cfg['data_path']
        data = ETFCSVData(
            dataname=str(data_path),
            dtformat='%Y%m%d',
            tmformat='%H:%M:%S',
            datetime=0, time=1, open=2, high=3, low=4, close=5,
            volume=6, openinterest=-1,
            fromdate=asset_cfg['from_date'],
            todate=asset_cfg['to_date'],
        )

        # Resample 5m -> H1 (index data is 5-minute bars)
        data_h1 = cerebro.resampledata(
            data,
            timeframe=bt.TimeFrame.Minutes,
            compression=60,
        )
        data_h1._name = asset_name

        cerebro.broker.setcash(STARTING_CASH)
        cerebro.broker.set_coc(True)

        # Commission (CFD index)
        broker_key = asset_cfg.get('broker_config_key',
                                   'darwinex_zero_cfd_sp500')
        broker_cfg = LYRA_BROKER_CONFIG.get(broker_key, {})
        CFDIndexCommission.total_commission = 0.0
        CFDIndexCommission.total_contracts = 0.0
        CFDIndexCommission.commission_calls = 0
        commission = CFDIndexCommission(
            commission=broker_cfg.get('commission_per_contract', 0.275),
            margin_pct=broker_cfg.get('margin_percent', 5.0),
            is_jpy_index=broker_cfg.get('is_jpy_index', False),
            jpy_rate=broker_cfg.get('jpy_rate', 150.0),
        )
        cerebro.broker.addcommissioninfo(commission)

        # Build strategy params: asset defaults + overrides
        strat_params = dict(asset_cfg.get('params', {}))
        strat_params.update(param_overrides)
        strat_params['export_reports'] = False
        strat_params['print_signals'] = False

        cerebro.addstrategy(LYRAStrategy, **strat_params)

        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            results = cerebro.run()

        strat = results[0]
        return _extract_metrics(strat, cerebro)

    except Exception as e:
        return {'error': str(e)}


def _extract_metrics(strat, cerebro):
    """Extract trades, PF, WR, DD, Sharpe, exit reasons from backtest result."""
    final_value = cerebro.broker.getvalue()
    total_pnl = final_value - STARTING_CASH

    trades = strat.total_trades
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
        rets = np.array([(pv[i] - pv[i - 1]) / pv[i - 1]
                         for i in range(1, len(pv))])
        if strat._first_bar_dt and strat._last_bar_dt:
            d = (strat._last_bar_dt - strat._first_bar_dt).days
            yrs = max(d / 365.25, 0.1)
            ppy = len(pv) / yrs
        else:
            ppy = 252 * 7
        std = np.std(rets)
        if std > 0:
            sharpe = (np.mean(rets) * ppy) / (std * np.sqrt(ppy))

    # Exit reasons
    exit_reasons = defaultdict(int)
    for t in strat.trade_reports:
        exit_reasons[t.get('exit_reason', 'UNKNOWN')] += 1

    # Yearly PnL
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

    yearly_dict = {}
    for y in sorted(yearly.keys()):
        s = yearly[y]
        y_wr = (s['wins'] / s['trades'] * 100) if s['trades'] > 0 else 0
        y_pf = (s['gross_profit'] / s['gross_loss']) if s['gross_loss'] > 0 else (
            float('inf') if s['gross_profit'] > 0 else 0)
        yearly_dict[y] = {
            'trades': s['trades'], 'wr': y_wr, 'pf': y_pf, 'pnl': s['pnl'],
        }

    return {
        'trades': trades, 'wins': wins, 'losses': losses,
        'wr': wr, 'pf': pf,
        'gross_profit': gross_profit, 'gross_loss': gross_loss,
        'net_pnl': total_pnl, 'final_value': final_value,
        'max_dd': max_dd, 'sharpe': sharpe,
        'cancels': getattr(strat, '_triggered_cancels', 0),
        'exit_reasons': dict(exit_reasons),
        'yearly': yearly_dict,
    }


# =============================================================================
# SCORING
# =============================================================================

def score_combo(asset_results):
    pfs = []
    wrs = []
    profitable = 0
    worst_dd = 0.0
    total_trades = 0

    for asset, m in asset_results.items():
        if 'error' in m:
            continue
        p = m['pf']
        if p == float('inf'):
            p = 99.0
        pfs.append(p)
        wrs.append(m['wr'])
        total_trades += m['trades']
        if m['net_pnl'] > 0:
            profitable += 1
        if m['max_dd'] > worst_dd:
            worst_dd = m['max_dd']

    if not pfs:
        return -999.0, {}

    median_pf = float(np.median(pfs))
    mean_wr = float(np.mean(wrs))
    score = median_pf * (1 + profitable * 0.1) * (1 + mean_wr / 200.0)

    summary = {
        'median_pf': round(median_pf, 4),
        'mean_pf': round(float(np.mean(pfs)), 4),
        'mean_wr': round(mean_wr, 2),
        'profitable_count': profitable,
        'total_assets': len(pfs),
        'worst_dd': round(worst_dd, 2),
        'total_trades': total_trades,
    }
    return score, summary


def fmt_pf(pf):
    return '%.2f' % pf if pf < 100 else 'INF'


# =============================================================================
# MAIN
# =============================================================================

def main():
    phase_name = 'sl'
    index_filter = None
    cli_fixed = {}

    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == '--phase' and i + 1 < len(sys.argv):
            phase_name = sys.argv[i + 1]
            i += 2
        elif arg == '--index' and i + 1 < len(sys.argv):
            index_filter = sys.argv[i + 1].upper()
            i += 2
        elif arg == '--fixed' and i + 1 < len(sys.argv):
            for pair in sys.argv[i + 1].split(','):
                k, v = pair.split('=')
                cli_fixed[k.strip()] = float(v.strip())
            i += 2
        else:
            i += 1

    if phase_name not in PHASES:
        print("ERROR: Unknown phase '%s'. Available: %s"
              % (phase_name, ', '.join(sorted(PHASES.keys()))))
        sys.exit(1)

    ASSETS = _load_assets(index_filter)
    if not ASSETS:
        print("ERROR: No active indices (filter: %s)" % index_filter)
        sys.exit(1)

    phase = PHASES[phase_name]
    grid, sweep_keys = build_param_grid(phase_name)

    if cli_fixed:
        for entry in grid:
            entry.update(cli_fixed)

    asset_names = sorted(ASSETS.keys())
    total_bt = len(grid) * len(asset_names)

    print('=' * 80)
    print('LYRA OPTIMIZER -- Multi-Index Grid Search (SHORT)')
    print('=' * 80)
    print('Indices: %s' % ', '.join(asset_names))
    print('Phase: %s (%s)' % (phase_name.upper(), phase['description']))
    if cli_fixed:
        print('Fixed overrides: %s' % ', '.join(
            '%s=%s' % (k, v) for k, v in cli_fixed.items()))
    print('Sweep: %s' % ', '.join(sweep_keys))
    print('Combinations: %d x %d indices = %d backtests'
          % (len(grid), len(asset_names), total_bt))
    print('-' * 80)

    all_combos = []
    bt_count = 0

    for i, overrides in enumerate(grid):
        label = ', '.join('%s=%s' % (k, overrides[k]) for k in sweep_keys)
        print('\n[Combo %d/%d] %s' % (i + 1, len(grid), label))

        asset_results = {}
        for asset_name in asset_names:
            bt_count += 1
            asset_cfg = ASSETS[asset_name]

            m = run_single_backtest(asset_name, asset_cfg, overrides)
            asset_results[asset_name] = m

            if 'error' in m:
                print('  %-8s -> ERROR: %s' % (asset_name, m['error']))
            else:
                exits = m.get('exit_reasons', {})
                regime = exits.get('REGIME_EXIT', 0)
                sl = exits.get('PROT_STOP', 0)
                tp = exits.get('TP_EXIT', 0)
                time = exits.get('TIME_EXIT', 0)
                print('  %-8s -> T=%3d PF=%5s WR=%4.1f%% DD=%5.2f%% '
                      'PnL=$%8.0f  SL=%d TP=%d RG=%d TM=%d'
                      % (asset_name, m['trades'], fmt_pf(m['pf']),
                         m['wr'], m['max_dd'], m['net_pnl'],
                         sl, tp, regime, time))

        score, summary = score_combo(asset_results)
        all_combos.append({
            'overrides': overrides,
            'asset_results': asset_results,
            'score': score,
            'summary': summary,
        })

        if summary:
            print('  --- SCORE=%.3f | medPF=%s | profitable=%d/%d | '
                  'meanWR=%.1f%% | worstDD=%.1f%%'
                  % (score, fmt_pf(summary['median_pf']),
                     summary['profitable_count'],
                     summary['total_assets'],
                     summary['mean_wr'],
                     summary['worst_dd']))

    # Sort by score descending
    all_combos.sort(key=lambda x: x['score'], reverse=True)

    # Print ranking
    print('\n' + '=' * 80)
    print('RANKING (by composite score)')
    print('=' * 80)
    print('%-4s %-40s %7s %7s %6s %5s %7s'
          % ('#', 'Params', 'medPF', 'meanWR', 'Prof', 'wDD%', 'Score'))
    print('-' * 80)

    for rank, combo in enumerate(all_combos, 1):
        s = combo['summary']
        if not s:
            continue
        label = ', '.join('%s=%s' % (k, combo['overrides'][k])
                          for k in sweep_keys)
        print('%-4d %-40s %7s %6.1f%% %4d/%-1d %5.1f%% %7.3f'
              % (rank, label[:40],
                 fmt_pf(s['median_pf']),
                 s['mean_wr'],
                 s['profitable_count'], s['total_assets'],
                 s['worst_dd'],
                 combo['score']))

    # Save JSON
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_dir = Path(PROJECT_ROOT) / 'logs'
    out_dir.mkdir(exist_ok=True)
    idx_tag = index_filter.lower() if index_filter else 'all'
    out_path = out_dir / ('LYRA_optimizer_%s_%s_%s.json'
                          % (idx_tag, phase_name, timestamp))

    def _safe_val(v):
        if isinstance(v, tuple):
            return list(v)
        if isinstance(v, float) and (math.isinf(v) or math.isnan(v)):
            return None
        return v

    json_data = {
        'optimizer': 'LYRA_grid',
        'phase': phase_name,
        'indices': asset_names,
        'timestamp': datetime.now().isoformat(),
        'sweep_keys': sweep_keys,
        'total_combinations': len(grid),
        'total_backtests': total_bt,
        'results': [],
    }

    for combo in all_combos:
        # Serialize overrides (handle tuple values)
        params_ser = {}
        for k in sweep_keys:
            v = combo['overrides'][k]
            params_ser[k] = list(v) if isinstance(v, tuple) else v

        entry = {
            'params': params_ser,
            'score': round(combo['score'], 4),
            'summary': combo['summary'],
            'per_asset': {},
        }
        for asset, m in combo['asset_results'].items():
            if 'error' in m:
                entry['per_asset'][asset] = {'error': m['error']}
            else:
                entry['per_asset'][asset] = {
                    'trades': m['trades'],
                    'wr': round(m['wr'], 2),
                    'pf': round(_safe_val(m['pf']) or 0, 4),
                    'net_pnl': round(m['net_pnl'], 2),
                    'max_dd': round(m['max_dd'], 2),
                    'sharpe': round(m['sharpe'], 4),
                    'cancels': m['cancels'],
                    'exit_reasons': m.get('exit_reasons', {}),
                }
        json_data['results'].append(entry)

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)

    print('\nResults saved: %s' % out_path)
    if all_combos and all_combos[0]['summary']:
        print('Best: %s (score=%.3f, medPF=%s)'
              % (', '.join('%s=%s' % (k, all_combos[0]['overrides'][k])
                           for k in sweep_keys),
                 all_combos[0]['score'],
                 fmt_pf(all_combos[0]['summary']['median_pf'])))

    return out_path


if __name__ == '__main__':
    main()
