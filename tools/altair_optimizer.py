"""
ALTAIR Optimizer -- Multi-Asset Grid Search (Standard Params)

Runs parameter combinations across ALL 7 NDX stocks simultaneously.
Each combo is tested on every asset, then aggregated to find the
best UNIVERSAL parameters (not per-asset optimization).

Scores by: median PF across all assets (robust to outliers like NVDA).
Secondary: count of profitable assets, mean WR, worst MaxDD.

Usage:
    python tools/altair_optimizer.py              # default: SL battery
    python tools/altair_optimizer.py --phase sl   # SL parameters
    python tools/altair_optimizer.py --phase tp   # TP parameters
    python tools/altair_optimizer.py --phase entry # Entry parameters

Output: logs/ALTAIR_optimizer_<phase>_<timestamp>.json
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

from strategies.altair_strategy import ALTAIRStrategy
from lib.commission import ETFCommission, ETFCSVData
from config.settings_altair import (
    ALTAIR_STRATEGIES_CONFIG, ALTAIR_BROKER_CONFIG, _DEFAULT_PARAMS,
)


# =============================================================================
# ASSETS TO TEST (all 7 NDX stocks)
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


# =============================================================================
# PHASE DEFINITIONS (which params to sweep per phase)
# =============================================================================

PHASES = {
    'sl': {
        'description': 'Stop Loss parameters',
        'grid': {
            'max_sl_atr_mult': [2.0, 3.0, 4.0, 5.0, 6.0],
            'sl_atr_mult': [1.5, 2.0, 2.5],
        },
        'fixed': {},
    },
    'tp': {
        'description': 'Take Profit parameters',
        'grid': {
            'tp_atr_mult': [2.0, 2.5, 3.0, 3.5, 4.0, 5.0],
        },
        'fixed': {},
    },
    'entry': {
        'description': 'Entry confirmation parameters',
        'grid': {
            'tr1bh_timeout': [5, 8, 10, 15],
            'dtosc_os': [20, 25, 30],
        },
        'fixed': {},
    },
    'holding': {
        'description': 'Holding period parameters',
        'grid': {
            'max_holding_bars': [60, 90, 120, 180],
            'tp_atr_mult': [2.5, 3.0, 4.0],
        },
        'fixed': {},
    },
}


# =============================================================================
# GRID GENERATION
# =============================================================================

def _frange(start, stop, step):
    values = []
    current = start
    while current <= stop + step * 0.001:
        values.append(round(current, 6))
        current += step
    return values


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
# SINGLE ASSET BACKTEST
# =============================================================================

def run_single_backtest(asset_name, asset_cfg, param_overrides):
    """Run one ALTAIR backtest silently. Returns metrics dict or error."""
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
        cerebro.adddata(data, name=asset_name)
        cerebro.broker.setcash(STARTING_CASH)

        # Commission (stock CFD)
        broker_cfg = ALTAIR_BROKER_CONFIG.get('darwinex_zero_stock', {})
        ETFCommission.total_commission = 0.0
        ETFCommission.total_contracts = 0.0
        ETFCommission.commission_calls = 0
        commission = ETFCommission(
            commission=broker_cfg.get('commission_per_contract', 0.02),
            margin_pct=broker_cfg.get('margin_percent', 20.0),
        )
        cerebro.broker.addcommissioninfo(commission)

        # Build strategy params: defaults + overrides
        strat_params = dict(_DEFAULT_PARAMS)
        strat_params.update(param_overrides)
        # Disable file I/O for speed
        strat_params['export_reports'] = False
        strat_params['print_signals'] = False

        cerebro.addstrategy(ALTAIRStrategy, **strat_params)

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

    # Triggered cancels
    cancels = getattr(strat, '_triggered_cancels', 0)

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
        'cancels': cancels,
        'exit_reasons': dict(exit_reasons),
        'yearly': yearly_dict,
    }


# =============================================================================
# MULTI-ASSET SCORING
# =============================================================================

def score_combo(asset_results):
    """Score a param combo across all assets.

    Primary: median PF (robust to NVDA outlier).
    Tiebreaker: count profitable, mean WR.
    """
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

    # Composite score: median_pf * bonus for more profitable assets
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
    # Parse CLI
    phase_name = 'sl'
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == '--phase' and i < len(sys.argv) - 1:
            phase_name = sys.argv[i + 1]

    if phase_name not in PHASES:
        print("ERROR: Unknown phase '%s'. Available: %s"
              % (phase_name, ', '.join(sorted(PHASES.keys()))))
        sys.exit(1)

    phase = PHASES[phase_name]
    grid, sweep_keys = build_param_grid(phase_name)
    asset_names = sorted(ASSETS.keys())
    total_bt = len(grid) * len(asset_names)

    print('=' * 80)
    print('ALTAIR OPTIMIZER -- Multi-Asset Grid Search')
    print('=' * 80)
    print('Phase: %s (%s)' % (phase_name.upper(), phase['description']))
    print('Assets: %s' % ', '.join(asset_names))
    print('Sweep: %s' % ', '.join(sweep_keys))
    print('Combinations: %d x %d assets = %d backtests'
          % (len(grid), len(asset_names), total_bt))
    print('Starting cash: $%s per asset' % format(STARTING_CASH, ',.0f'))
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
                print('  %-6s -> ERROR: %s' % (asset_name, m['error']))
            else:
                exits = m.get('exit_reasons', {})
                prot = exits.get('PROT_STOP', 0)
                tp = exits.get('TP_EXIT', 0)
                print('  %-6s -> T=%2d PF=%5s WR=%4.1f%% DD=%5.2f%% '
                      'PnL=$%8.0f  SL=%d TP=%d'
                      % (asset_name, m['trades'], fmt_pf(m['pf']),
                         m['wr'], m['max_dd'], m['net_pnl'],
                         prot, tp))

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
    print('%-4s %-35s %7s %7s %6s %5s %7s'
          % ('#', 'Params', 'medPF', 'meanWR', 'Prof', 'wDD%', 'Score'))
    print('-' * 80)

    for rank, combo in enumerate(all_combos, 1):
        s = combo['summary']
        if not s:
            continue
        label = ', '.join('%s=%s' % (k, combo['overrides'][k])
                          for k in sweep_keys)
        print('%-4d %-35s %7s %6.1f%% %4d/%-1d %5.1f%% %7.3f'
              % (rank, label[:35],
                 fmt_pf(s['median_pf']),
                 s['mean_wr'],
                 s['profitable_count'], s['total_assets'],
                 s['worst_dd'],
                 combo['score']))

    # Save JSON
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_dir = Path(PROJECT_ROOT) / 'logs'
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / ('ALTAIR_optimizer_%s_%s.json'
                          % (phase_name, timestamp))

    def _safe_val(v):
        if isinstance(v, float) and (math.isinf(v) or math.isnan(v)):
            return None
        return v

    json_data = {
        'optimizer': 'ALTAIR_grid',
        'phase': phase_name,
        'timestamp': datetime.now().isoformat(),
        'assets': asset_names,
        'sweep_keys': sweep_keys,
        'total_combinations': len(grid),
        'total_backtests': total_bt,
        'results': [],
    }

    for combo in all_combos:
        entry = {
            'params': {k: combo['overrides'][k] for k in sweep_keys},
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
    print('Best: %s (score=%.3f, medPF=%s)'
          % (', '.join('%s=%s' % (k, all_combos[0]['overrides'][k])
                       for k in sweep_keys),
             all_combos[0]['score'],
             fmt_pf(all_combos[0]['summary']['median_pf'])))

    return out_path


if __name__ == '__main__':
    main()
