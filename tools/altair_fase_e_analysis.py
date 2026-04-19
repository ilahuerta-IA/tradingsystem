"""
ALTAIR Fase E -- Combined Multi-TF Portfolio Analysis (H1 + 15m)

Runs the same 5-task deep analysis as altair_deep_analysis.py but for the
full combined portfolio: 8 H1 tickers + 10 x 15m tickers = 18 total.

Reuses:
  - altair_timeframe_compare.py: build_config(), extract(), STARTING_CASH
  - altair_deep_analysis.py: all 5 task functions
  - altair_phase2_dd_correlation.py: run_bt() for H1 tickers, load_configs()

Usage:
    python tools/altair_fase_e_analysis.py                  # all 5 tasks
    python tools/altair_fase_e_analysis.py --task 1 3 5     # specific tasks
    python tools/altair_fase_e_analysis.py --mc-runs 5000   # more MC iterations
"""
import sys
import os
import io
import contextlib
import warnings
import argparse

warnings.filterwarnings('ignore')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
sys.path.insert(0, PROJECT_ROOT)

from pathlib import Path
import backtrader as bt

from strategies.altair_strategy import ALTAIRStrategy
from lib.commission import ETFCommission, ETFCSVData
from config.settings_altair import ALTAIR_BROKER_CONFIG

from tools.altair_timeframe_compare import (
    build_config as _tf_build_config,
    extract as tf_extract,
    STARTING_CASH,
)
from tools.altair_phase2_dd_correlation import (
    load_configs as _h1_load_configs,
)
from tools.altair_deep_analysis import (
    task1_dd_clusters,
    task2_entry_coincidence,
    task3_yearly_robustness,
    task4_statistical_weight,
    task5_monte_carlo,
    SECTORS as SECTORS_15M,
)


# ── Portfolio definition ─────────────────────────────────────────────────────

# H1 KEEP: 40+ trades, PF > 1.50, robust yearly
H1_TICKERS = ['HCA', 'V', 'JPM', 'TDY', 'KEYS', 'AWK', 'NSC', 'PWR']

# 15m KEEP: Fase C TF-robust (2) + Fase D expansion (8)
TICKERS_15M = [
    # Fase C TF-robust
    'MCO', 'GOOGL',
    # Fase D expansion (Ivan's 8 picks)
    'TDG', 'PGR', 'NOC', 'MPC', 'HII', 'GS', 'GRMN', 'ETN',
]

ALL_TICKERS = H1_TICKERS + TICKERS_15M

SECTORS = {
    # H1
    'HCA': 'HealthProv', 'V': 'Payments', 'JPM': 'Banking',
    'TDY': 'DefInstr', 'KEYS': 'ElecTest', 'AWK': 'WaterUtil',
    'NSC': 'Railroad', 'PWR': 'Industrial',
    # 15m Fase C
    'MCO': 'Ratings', 'GOOGL': 'Tech',
    # 15m Fase D
    'TDG': 'Aerospace', 'PGR': 'Insurance', 'NOC': 'Defense',
    'MPC': 'Energy', 'HII': 'Defense', 'GS': 'Financials',
    'GRMN': 'ConsElec', 'ETN': 'Industrials',
}


# ── BT runners ───────────────────────────────────────────────────────────────

def run_bt_15m(ticker, asset_cfg):
    """Run 15m BT with export_reports=True (same as altair_deep_analysis)."""
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
        resample_min = asset_cfg.get('resample_minutes', 0)
        if resample_min > 0:
            data_resampled = cerebro.resampledata(
                data,
                timeframe=bt.TimeFrame.Minutes,
                compression=resample_min,
            )
            data_resampled._name = ticker
        else:
            cerebro.adddata(data, name=ticker)
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
        params['export_reports'] = True
        params['print_signals'] = False
        cerebro.addstrategy(ALTAIRStrategy, **params)

        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            results = cerebro.run()

        strat = results[0]
        summary = tf_extract(strat, cerebro)
        return summary, list(strat.trade_reports), list(strat._trade_pnls)
    except Exception as e:
        return {'error': str(e)}, [], []


def run_bt_h1(ticker, asset_cfg):
    """Run H1 BT with export_reports=True."""
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
        cerebro.adddata(data, name=ticker)
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
        params['export_reports'] = True
        params['print_signals'] = False
        cerebro.addstrategy(ALTAIRStrategy, **params)

        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            results = cerebro.run()

        strat = results[0]
        summary = tf_extract(strat, cerebro)
        return summary, list(strat.trade_reports), list(strat._trade_pnls)
    except Exception as e:
        return {'error': str(e)}, [], []


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='ALTAIR Fase E -- Combined Multi-TF Portfolio Analysis')
    parser.add_argument('--task', nargs='+', type=int, choices=[1, 2, 3, 4, 5],
                        help='Specific tasks (default: all)')
    parser.add_argument('--mc-runs', type=int, default=2000,
                        help='Monte Carlo iterations (default: 2000)')
    args = parser.parse_args()

    tasks = args.task if args.task else [1, 2, 3, 4, 5]

    print()
    print('#' * 100)
    print('#  ALTAIR FASE E -- COMBINED MULTI-TF PORTFOLIO ANALYSIS')
    print('#  H1 tickers (%d): %s' % (len(H1_TICKERS), ', '.join(H1_TICKERS)))
    print('#  15m tickers (%d): %s' % (len(TICKERS_15M), ', '.join(TICKERS_15M)))
    print('#  Total: %d tickers' % len(ALL_TICKERS))
    print('#  Tasks: %s' % ', '.join(str(t) for t in tasks))
    print('#' * 100)

    # Load H1 configs
    h1_cfgs = _h1_load_configs(only_tickers=H1_TICKERS)

    all_summaries = {}
    all_trades = {}
    all_trade_pnls = {}

    # Run H1 backtests
    print()
    print('Running H1 backtests (%d tickers)...' % len(H1_TICKERS))
    for i, tk in enumerate(H1_TICKERS, 1):
        sys.stdout.write('  [%d/%d] %-6s (H1) ...' % (i, len(H1_TICKERS), tk))
        sys.stdout.flush()
        if tk not in h1_cfgs:
            print(' SKIP (no config)')
            continue
        summary, trades, trade_pnls = run_bt_h1(tk, h1_cfgs[tk])
        if isinstance(summary, dict) and 'error' in summary:
            print(' ERROR: %s' % summary['error'])
            continue
        all_summaries[tk] = summary
        all_trades[tk] = trades
        all_trade_pnls[tk] = trade_pnls
        print(' T=%3d  PF=%.2f  Shrp=%.2f  DD=%.1f%%  PnL=%+.0f' % (
            summary['trades'], min(summary['pf'], 99), summary['sharpe'],
            summary['max_dd'], summary['net_pnl']))

    # Run 15m backtests
    print()
    print('Running 15m backtests (%d tickers)...' % len(TICKERS_15M))
    for i, tk in enumerate(TICKERS_15M, 1):
        sys.stdout.write('  [%d/%d] %-6s (15m) ...' % (i, len(TICKERS_15M), tk))
        sys.stdout.flush()
        cfg = _tf_build_config(tk, '15m')
        if cfg is None:
            print(' SKIP (no CSV)')
            continue
        summary, trades, trade_pnls = run_bt_15m(tk, cfg)
        if isinstance(summary, dict) and 'error' in summary:
            print(' ERROR: %s' % summary['error'])
            continue
        all_summaries[tk] = summary
        all_trades[tk] = trades
        all_trade_pnls[tk] = trade_pnls
        print(' T=%3d  PF=%.2f  Shrp=%.2f  DD=%.1f%%  PnL=%+.0f' % (
            summary['trades'], min(summary['pf'], 99), summary['sharpe'],
            summary['max_dd'], summary['net_pnl']))

    # Summary table
    print()
    print('BACKTEST SUMMARY (all %d tickers):' % len(all_summaries))
    print('  %-6s %3s %4s %5s %5s %5s %8s  %-12s %s' % (
        'Ticker', 'TF', 'T', 'PF', 'Shrp', 'DD%', 'PnL', 'Sector', 'Cfg'))
    print('  ' + '-' * 70)
    for tk in ALL_TICKERS:
        if tk not in all_summaries:
            continue
        s = all_summaries[tk]
        tf = 'H1' if tk in H1_TICKERS else '15m'
        print('  %-6s %3s %4d %5.2f %5.2f %4.1f%% %+8.0f  %-12s' % (
            tk, tf, s['trades'], min(s['pf'], 99), s['sharpe'],
            s['max_dd'], s['net_pnl'], SECTORS.get(tk, '')))

    # Aggregate stats
    total_trades = sum(s['trades'] for s in all_summaries.values())
    total_pnl = sum(s['net_pnl'] for s in all_summaries.values())
    h1_trades = sum(all_summaries[tk]['trades'] for tk in H1_TICKERS
                    if tk in all_summaries)
    m15_trades = sum(all_summaries[tk]['trades'] for tk in TICKERS_15M
                     if tk in all_summaries)
    print()
    print('  AGGREGATE: %d total trades (H1: %d, 15m: %d), total PnL: $%+.0f' % (
        total_trades, h1_trades, m15_trades, total_pnl))

    # Run requested tasks (reusing from altair_deep_analysis.py)
    if 1 in tasks:
        task1_dd_clusters(all_trades)
    if 2 in tasks:
        task2_entry_coincidence(all_trades)
    if 3 in tasks:
        task3_yearly_robustness(all_trades, all_summaries, all_trade_pnls)
    if 4 in tasks:
        task4_statistical_weight(all_trades, all_summaries)
    if 5 in tasks:
        task5_monte_carlo(all_trades, n_runs=args.mc_runs)


if __name__ == '__main__':
    main()
