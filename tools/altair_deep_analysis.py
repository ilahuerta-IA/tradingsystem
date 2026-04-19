"""
ALTAIR Deep Analysis -- 8 x 15m Expansion Picks

Runs backtests for the 8 user-selected 15m tickers and performs:
  1. DD Cluster Analysis (worst months across portfolio)
  2. Entry Coincidence / Diversification (signal clustering)
  3. Year-by-Year Robustness (cross-ticker regime stability)
  4. Statistical Weight (confidence intervals on PF)
  5. Monte Carlo Simulation (P(ruin), expected max DD)

Reuses build_config/extract/STARTING_CASH from altair_timeframe_compare.py.
Only adds a thin run_bt_full() wrapper that also returns trade_reports + _trade_pnls.

Usage:
    python tools/altair_deep_analysis.py                  # all 5 analyses
    python tools/altair_deep_analysis.py --task 1 3 5     # specific tasks
    python tools/altair_deep_analysis.py --mc-runs 5000   # more MC iterations
"""
import sys
import os
import io
import contextlib
import warnings
import argparse
from collections import defaultdict

import numpy as np

warnings.filterwarnings('ignore')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
sys.path.insert(0, PROJECT_ROOT)

from pathlib import Path
import backtrader as bt

from strategies.altair_strategy import ALTAIRStrategy
from lib.commission import ETFCommission, ETFCSVData
from config.settings_altair import ALTAIR_BROKER_CONFIG

# Reuse infrastructure from existing tool
from tools.altair_timeframe_compare import (
    build_config as _tf_build_config,
    extract as tf_extract,
    STARTING_CASH,
)

# User's 8 picks from Fase D 15m expansion
TICKERS_15M = ['TDG', 'PGR', 'NOC', 'MPC', 'HII', 'GS', 'GRMN', 'ETN']

SECTORS = {
    'TDG': 'Aerospace', 'PGR': 'Insurance', 'NOC': 'Defense',
    'MPC': 'Energy/Refiner', 'HII': 'Defense', 'GS': 'Financials',
    'GRMN': 'Consumer Elec', 'ETN': 'Industrials',
}


# ── BT runner (thin wrapper over timeframe_compare infra) ────────────────────

def build_config(ticker):
    """Build ALTAIR 15m config via existing tool."""
    return _tf_build_config(ticker, '15m')


def run_bt_full(ticker, asset_cfg):
    """Run BT with export_reports=True, return (summary, trade_reports, _trade_pnls).

    Uses same cerebro setup as altair_timeframe_compare.run_bt() but enables
    trade_reports and returns raw strategy data for deep analysis.
    """
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
        params['export_reports'] = True   # key difference: populate trade_reports
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


# ── TASK 1: DD Cluster Analysis ──────────────────────────────────────────────

def task1_dd_clusters(all_trades):
    """Identify calendar months where multiple tickers draw down simultaneously."""
    print()
    print('=' * 100)
    print('TASK 1: DD CLUSTER ANALYSIS -- Monthly PnL Heatmap')
    print('=' * 100)

    # Aggregate monthly PnL per ticker
    monthly = defaultdict(lambda: defaultdict(float))
    for ticker, trades in all_trades.items():
        for t in trades:
            if 'exit_time' not in t:
                continue
            dt = t['exit_time']
            ym = (dt.year, dt.month)
            monthly[ticker][ym] += t['pnl']

    # Collect all year-months
    all_ym = set()
    for ticker_months in monthly.values():
        all_ym.update(ticker_months.keys())
    all_ym = sorted(all_ym)

    tickers = sorted(all_trades.keys())

    # Heatmap header
    print()
    print('Monthly PnL by ticker (negative months highlighted with *):')
    print()
    hdr = '%-7s' % 'YM'
    for tk in tickers:
        hdr += ' %7s' % tk
    hdr += '  %8s %4s' % ('TOTAL', 'NEG')
    print(hdr)
    print('-' * len(hdr))

    worst_months = []
    for ym in all_ym:
        row = '%4d-%02d' % ym
        total = 0.0
        neg_count = 0
        for tk in tickers:
            pnl = monthly[tk].get(ym, 0.0)
            total += pnl
            if pnl < -1.0:
                row += ' %+6.0f*' % pnl
                neg_count += 1
            elif abs(pnl) < 1.0:
                row += '       -'
            else:
                row += ' %+7.0f' % pnl
            total += 0  # already added
        row += '  %+8.0f %4d' % (total, neg_count)
        print(row)
        if neg_count >= 3:
            worst_months.append((ym, neg_count, total))

    # Systemic risk summary
    print()
    print('SYSTEMIC RISK MONTHS (3+ tickers negative simultaneously):')
    if worst_months:
        print('  %-7s  %4s  %8s' % ('Month', 'Neg', 'PortPnL'))
        print('  ' + '-' * 25)
        for ym, nc, tot in sorted(worst_months, key=lambda x: x[1], reverse=True):
            print('  %4d-%02d  %4d  %+8.0f' % (ym[0], ym[1], nc, tot))
    else:
        print('  None found -- good diversification!')

    # Worst single months per ticker
    print()
    print('WORST MONTH per ticker:')
    for tk in tickers:
        if not monthly[tk]:
            continue
        worst_ym = min(monthly[tk], key=monthly[tk].get)
        worst_pnl = monthly[tk][worst_ym]
        print('  %-6s  %4d-%02d  %+8.0f' % (tk, worst_ym[0], worst_ym[1], worst_pnl))

    # Correlation of monthly returns
    print()
    print('MONTHLY PnL CORRELATION MATRIX:')
    print()
    # Build matrix
    ym_list = all_ym
    mat = np.zeros((len(tickers), len(ym_list)))
    for i, tk in enumerate(tickers):
        for j, ym in enumerate(ym_list):
            mat[i, j] = monthly[tk].get(ym, 0.0)

    # Only compute if enough months
    if len(ym_list) >= 6:
        corr = np.corrcoef(mat)
        hdr2 = '       '
        for tk in tickers:
            hdr2 += ' %6s' % tk
        print(hdr2)
        for i, tk in enumerate(tickers):
            row = '%-6s ' % tk
            for j in range(len(tickers)):
                if i == j:
                    row += '  1.00 '
                else:
                    row += ' %+5.2f ' % corr[i, j]
            print(row)
    print()


# ── TASK 2: Entry Coincidence / Diversification ─────────────────────────────

def task2_entry_coincidence(all_trades):
    """Check if multiple tickers fire signals on same days/weeks."""
    print()
    print('=' * 100)
    print('TASK 2: ENTRY COINCIDENCE / DIVERSIFICATION')
    print('=' * 100)

    tickers = sorted(all_trades.keys())

    # Entries per calendar week: (year, week_number) -> set of tickers
    weekly_entries = defaultdict(set)
    daily_entries = defaultdict(set)
    ticker_entry_dates = {}

    for ticker, trades in all_trades.items():
        dates = []
        for t in trades:
            dt = t['entry_time']
            daily_entries[dt.date()].add(ticker)
            iso = dt.isocalendar()
            weekly_entries[(iso[0], iso[1])].add(ticker)
            dates.append(dt.date())
        ticker_entry_dates[ticker] = dates

    # Same-day coincidences
    print()
    print('SAME-DAY ENTRIES (2+ tickers entering same day):')
    same_day = {d: tks for d, tks in daily_entries.items() if len(tks) >= 2}
    if same_day:
        counts = defaultdict(int)
        for d, tks in sorted(same_day.items()):
            n = len(tks)
            counts[n] += 1
        for n in sorted(counts.keys()):
            print('  %d tickers same day: %d occurrences' % (n, counts[n]))
        total_days = len(daily_entries)
        overlap_days = len(same_day)
        print('  Overlap ratio: %d / %d trading days = %.1f%%' % (
            overlap_days, total_days, overlap_days / total_days * 100 if total_days else 0))
    else:
        print('  No same-day entries found')

    # Same-week coincidences
    print()
    print('SAME-WEEK ENTRIES (3+ tickers entering same week):')
    hot_weeks = {w: tks for w, tks in weekly_entries.items() if len(tks) >= 3}
    if hot_weeks:
        top_weeks = sorted(hot_weeks.items(), key=lambda x: len(x[1]), reverse=True)[:15]
        print('  %-12s  %4s  %s' % ('Week', 'Count', 'Tickers'))
        for (y, w), tks in top_weeks:
            print('  %4d-W%02d     %4d  %s' % (y, w, len(tks), ', '.join(sorted(tks))))
        # Distribution
        dist = defaultdict(int)
        for w, tks in weekly_entries.items():
            dist[len(tks)] += 1
        print()
        print('  Weekly entry distribution:')
        for n in sorted(dist.keys()):
            bar = '#' * dist[n]
            print('    %d tickers: %3d weeks  %s' % (n, dist[n], bar[:50]))
    else:
        print('  No weeks with 3+ simultaneous entries')

    # Entry calendar distribution: are entries evenly spread across months?
    print()
    print('ENTRY DISTRIBUTION BY MONTH (all tickers):')
    month_dist = defaultdict(int)
    for ticker, dates in ticker_entry_dates.items():
        for d in dates:
            month_dist[d.month] += 1
    months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
              'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    total_entries = sum(month_dist.values())
    expected = total_entries / 12 if total_entries else 1
    for m in range(1, 13):
        cnt = month_dist.get(m, 0)
        ratio = cnt / expected if expected > 0 else 0
        bar = '#' * int(ratio * 20)
        flag = ' <-- CLUSTERED' if ratio > 1.5 else (' <-- SPARSE' if ratio < 0.5 else '')
        print('  %s: %4d entries (%.1fx avg)  %s%s' % (
            months[m - 1], cnt, ratio, bar, flag))
    print()


# ── TASK 3: Year-by-Year Robustness ─────────────────────────────────────────

def task3_yearly_robustness(all_trades, all_summaries, all_trade_pnls):
    """Year-by-year cross-ticker analysis."""
    print()
    print('=' * 100)
    print('TASK 3: YEAR-BY-YEAR ROBUSTNESS')
    print('=' * 100)

    tickers = sorted(all_trades.keys())

    # Yearly PnL per ticker from _trade_pnls
    yearly = defaultdict(lambda: defaultdict(lambda: {'pnl': 0.0, 'trades': 0,
                                                       'gp': 0.0, 'gl': 0.0}))
    for ticker in tickers:
        for tp in all_trade_pnls[ticker]:
            y = tp['year']
            yearly[ticker][y]['pnl'] += tp['pnl']
            yearly[ticker][y]['trades'] += 1
            if tp['is_winner']:
                yearly[ticker][y]['gp'] += tp['pnl']
            else:
                yearly[ticker][y]['gl'] += abs(tp['pnl'])

    all_years = set()
    for tk_years in yearly.values():
        all_years.update(tk_years.keys())
    years = sorted(all_years)

    # Header
    print()
    hdr = '%-6s' % 'Year'
    for tk in tickers:
        hdr += '  %7s' % tk
    hdr += '  %8s %3s %4s' % ('PortPnL', 'N+', '%Pos')
    print(hdr)
    print('-' * len(hdr))

    year_summary = []
    for y in years:
        row = '%-6d' % y
        port_pnl = 0.0
        pos_count = 0
        active_count = 0
        for tk in tickers:
            yd = yearly[tk].get(y)
            if yd and yd['trades'] > 0:
                pnl = yd['pnl']
                row += '  %+7.0f' % pnl
                port_pnl += pnl
                active_count += 1
                if pnl > 0:
                    pos_count += 1
            else:
                row += '       --'
        pct_pos = (pos_count / active_count * 100) if active_count > 0 else 0
        flag = '  *** WEAK' if pct_pos < 50 else ''
        row += '  %+8.0f %3d %4.0f%%%s' % (port_pnl, pos_count, pct_pos, flag)
        print(row)
        year_summary.append((y, port_pnl, pos_count, active_count, pct_pos))

    # Stability metrics
    print()
    print('STABILITY METRICS per ticker:')
    print('  %-6s %6s %7s %7s %6s %6s' % (
        'Ticker', 'AvgPnL', 'StdPnL', 'CV', 'MinY', 'MaxY'))
    print('  ' + '-' * 50)
    for tk in tickers:
        yr_pnls = [yearly[tk][y]['pnl'] for y in years
                   if yearly[tk].get(y) and yearly[tk][y]['trades'] > 0]
        if len(yr_pnls) >= 2:
            avg = np.mean(yr_pnls)
            std = np.std(yr_pnls, ddof=1)
            cv = (std / abs(avg)) if abs(avg) > 0 else float('inf')
            print('  %-6s %+6.0f %7.0f %7.2f %+6.0f %+6.0f' % (
                tk, avg, std, cv, min(yr_pnls), max(yr_pnls)))

    # Yearly PF per ticker
    print()
    print('YEARLY PF per ticker:')
    hdr2 = '%-6s' % 'Year'
    for tk in tickers:
        hdr2 += '  %6s' % tk
    print(hdr2)
    print('-' * len(hdr2))
    for y in years:
        row = '%-6d' % y
        for tk in tickers:
            yd = yearly[tk].get(y)
            if yd and yd['trades'] > 0:
                pf = (yd['gp'] / yd['gl']) if yd['gl'] > 0 else (
                    99.0 if yd['gp'] > 0 else 0)
                pf_s = '%5.2f' % min(pf, 99)
                row += '  %s ' % pf_s
            else:
                row += '     -- '
        print(row)

    # Portfolio aggregate
    print()
    port_pnls = [ps[1] for ps in year_summary]
    neg_years = sum(1 for p in port_pnls if p <= 0)
    print('PORTFOLIO SUMMARY:')
    print('  Total years: %d' % len(years))
    print('  Positive portfolio years: %d / %d' % (
        len(years) - neg_years, len(years)))
    if neg_years > 0:
        print('  *** WARNING: %d year(s) with negative portfolio PnL' % neg_years)
    weak = [ys for ys in year_summary if ys[4] < 50]
    if weak:
        print('  WEAK YEARS (< 50%% positive):')
        for y, pnl, pos, act, pct in weak:
            print('    %d: %d/%d positive (%+.0f portfolio PnL)' % (
                y, pos, act, pnl))
    print()


# ── TASK 4: Statistical Weight (CI on PF) ────────────────────────────────────

def task4_statistical_weight(all_trades, all_summaries):
    """Bootstrap confidence intervals on Profit Factor."""
    print()
    print('=' * 100)
    print('TASK 4: STATISTICAL WEIGHT -- Confidence Intervals on PF')
    print('=' * 100)

    tickers = sorted(all_trades.keys())
    n_boot = 10_000
    rng = np.random.default_rng(42)

    print()
    print('Bootstrap CI on PF (%d iterations):' % n_boot)
    print()
    print('  %-6s %4s  %6s  %12s  %12s  %12s  %s' % (
        'Ticker', 'T', 'PF_obs', '90% CI', '95% CI', '99% CI', 'Verdict'))
    print('  ' + '-' * 80)

    for tk in tickers:
        trades = all_trades[tk]
        pnls = np.array([t['pnl'] for t in trades if 'pnl' in t])
        n = len(pnls)
        if n < 10:
            print('  %-6s %4d  -- too few trades --' % (tk, n))
            continue

        # Observed PF
        gp = pnls[pnls > 0].sum()
        gl = abs(pnls[pnls < 0].sum())
        pf_obs = (gp / gl) if gl > 0 else float('inf')

        # Bootstrap
        boot_pfs = []
        for _ in range(n_boot):
            sample = rng.choice(pnls, size=n, replace=True)
            b_gp = sample[sample > 0].sum()
            b_gl = abs(sample[sample < 0].sum())
            b_pf = (b_gp / b_gl) if b_gl > 0 else 99.0
            boot_pfs.append(min(b_pf, 99.0))
        boot_pfs = np.array(boot_pfs)

        ci90 = (np.percentile(boot_pfs, 5), np.percentile(boot_pfs, 95))
        ci95 = (np.percentile(boot_pfs, 2.5), np.percentile(boot_pfs, 97.5))
        ci99 = (np.percentile(boot_pfs, 0.5), np.percentile(boot_pfs, 99.5))

        # Verdict: lower bound of 95% CI > 1.0 means statistically profitable
        if ci95[0] > 1.20:
            verdict = 'STRONG (PF>1.2 at 95%)'
        elif ci95[0] > 1.00:
            verdict = 'VIABLE (PF>1.0 at 95%)'
        elif ci90[0] > 1.00:
            verdict = 'MARGINAL (PF>1.0 at 90%)'
        else:
            verdict = 'WEAK (PF<1.0 possible)'

        print('  %-6s %4d  %5.2f  [%4.2f, %4.2f]  [%4.2f, %4.2f]  [%4.2f, %4.2f]  %s' % (
            tk, n, pf_obs,
            ci90[0], ci90[1], ci95[0], ci95[1], ci99[0], ci99[1],
            verdict))

    # Win rate CI
    print()
    print('Bootstrap CI on Win Rate (%d iterations):' % n_boot)
    print()
    print('  %-6s %4s  %6s  %12s  %s' % (
        'Ticker', 'T', 'WR_obs', '95% CI', 'Notes'))
    print('  ' + '-' * 55)
    for tk in tickers:
        trades = all_trades[tk]
        pnls = np.array([t['pnl'] for t in trades if 'pnl' in t])
        n = len(pnls)
        if n < 10:
            continue
        wr_obs = (pnls > 0).sum() / n * 100

        boot_wrs = []
        for _ in range(n_boot):
            sample = rng.choice(pnls, size=n, replace=True)
            boot_wrs.append((sample > 0).sum() / n * 100)
        boot_wrs = np.array(boot_wrs)
        ci95 = (np.percentile(boot_wrs, 2.5), np.percentile(boot_wrs, 97.5))
        note = 'OK' if ci95[0] > 50 else 'WR<50% possible'
        print('  %-6s %4d  %5.1f%%  [%4.1f%%, %4.1f%%]  %s' % (
            tk, n, wr_obs, ci95[0], ci95[1], note))
    print()


# ── TASK 5: Monte Carlo Simulation ──────────────────────────────────────────

def task5_monte_carlo(all_trades, n_runs=2000):
    """Reshuffle trade returns, simulate equity curves, measure tail risk."""
    print()
    print('=' * 100)
    print('TASK 5: MONTE CARLO SIMULATION (%d iterations per ticker)' % n_runs)
    print('=' * 100)
    print()
    print('NOTE: Terminal PnL = sum(trades) = constant regardless of order.')
    print('      MC measures: MaxDD distribution, P(ruin), equity path risk.')

    tickers = sorted(all_trades.keys())
    rng = np.random.default_rng(123)

    print()
    print('  %-6s %4s  %8s  %7s  %7s  %7s  %7s  %7s' % (
        'Ticker', 'T', 'Net PnL', 'ObsDD%', 'MC mDD', 'MC P75', 'MC P95', 'P(ruin)'))
    print('  ' + '-' * 75)

    for tk in tickers:
        trades = all_trades[tk]
        pnls = np.array([t['pnl'] for t in trades if 'pnl' in t])
        n = len(pnls)
        if n < 10:
            print('  %-6s %4d  -- too few trades --' % (tk, n))
            continue

        obs_pnl = pnls.sum()

        # Observed max DD from trade sequence
        cum = np.cumsum(pnls) + STARTING_CASH
        peak = np.maximum.accumulate(cum)
        obs_dd = ((peak - cum) / peak * 100).max()

        # MC simulation: shuffle trade order
        mc_max_dds = []
        mc_ruin = 0

        for _ in range(n_runs):
            shuffled = rng.permutation(pnls)
            equity = np.cumsum(shuffled) + STARTING_CASH
            mc_peak = np.maximum.accumulate(equity)
            mc_dd = ((mc_peak - equity) / mc_peak * 100).max()
            mc_max_dds.append(mc_dd)
            if equity.min() <= STARTING_CASH * 0.5:  # 50% ruin threshold
                mc_ruin += 1

        mc_max_dds = np.array(mc_max_dds)
        p_ruin = mc_ruin / n_runs * 100

        print('  %-6s %4d  %+8.0f  %6.1f%%  %6.1f%%  %6.1f%%  %6.1f%%  %5.1f%%' % (
            tk, n, obs_pnl, obs_dd,
            np.median(mc_max_dds),
            np.percentile(mc_max_dds, 75),
            np.percentile(mc_max_dds, 95),
            p_ruin))

    # PORTFOLIO Monte Carlo: combine all 8 tickers
    print()
    print('PORTFOLIO MONTE CARLO (all %d tickers combined):' % len(tickers))
    print()

    # Collect all trades with dates for portfolio simulation
    all_portfolio_trades = []
    for tk in tickers:
        for t in all_trades[tk]:
            if 'pnl' in t and 'exit_time' in t:
                all_portfolio_trades.append({
                    'ticker': tk, 'pnl': t['pnl'],
                    'exit_time': t['exit_time'],
                })

    # Sort by exit date for observed curve
    all_portfolio_trades.sort(key=lambda x: x['exit_time'])
    port_pnls = np.array([t['pnl'] for t in all_portfolio_trades])
    n_port = len(port_pnls)

    if n_port < 20:
        print('  Too few portfolio trades for MC')
        return

    obs_port_pnl = port_pnls.sum()
    cum = np.cumsum(port_pnls) + STARTING_CASH
    peak = np.maximum.accumulate(cum)
    obs_port_dd = ((peak - cum) / peak * 100).max()

    mc_finals = []
    mc_dds = []
    mc_ruin = 0
    for _ in range(n_runs):
        shuffled = rng.permutation(port_pnls)
        equity = np.cumsum(shuffled) + STARTING_CASH
        mc_peak = np.maximum.accumulate(equity)
        mc_dd = ((mc_peak - equity) / mc_peak * 100).max()
        mc_dds.append(mc_dd)
        mc_finals.append(equity[-1] - STARTING_CASH)
        if equity.min() <= STARTING_CASH * 0.5:
            mc_ruin += 1

    mc_finals = np.array(mc_finals)
    mc_dds = np.array(mc_dds)

    print('  Portfolio trades: %d' % n_port)
    print('  Observed PnL:     %+.0f' % obs_port_pnl)
    print('  Observed MaxDD:   %.1f%%' % obs_port_dd)
    print()
    print('  MC Terminal PnL distribution:')
    print('    Median:  %+.0f' % np.median(mc_finals))
    print('    P5:      %+.0f' % np.percentile(mc_finals, 5))
    print('    P25:     %+.0f' % np.percentile(mc_finals, 25))
    print('    P75:     %+.0f' % np.percentile(mc_finals, 75))
    print('    P95:     %+.0f' % np.percentile(mc_finals, 95))
    print()
    print('  MC Max Drawdown distribution:')
    print('    Median:  %.1f%%' % np.median(mc_dds))
    print('    P75:     %.1f%%' % np.percentile(mc_dds, 75))
    print('    P95:     %.1f%%  <-- expect this DD in worst scenarios' % np.percentile(mc_dds, 95))
    print('    P99:     %.1f%%' % np.percentile(mc_dds, 99))
    print()
    print('  P(ruin 50%%): %.1f%%' % (mc_ruin / n_runs * 100))

    # Skill vs Luck: is observed PnL above MC median?
    rank = (mc_finals < obs_port_pnl).sum() / n_runs * 100
    print()
    print('  SKILL vs LUCK:')
    print('    Observed PnL rank in MC: %.0fth percentile' % rank)
    if rank > 60:
        print('    --> Favorable trade ordering (potential momentum persistence)')
    elif rank < 40:
        print('    --> Unfavorable ordering (observed was below typical)')
    else:
        print('    --> Consistent with random ordering (no sequence bias)')
    print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='ALTAIR Deep Analysis -- 8 x 15m expansion picks')
    parser.add_argument('--task', nargs='+', type=int, choices=[1, 2, 3, 4, 5],
                        help='Specific tasks (default: all)')
    parser.add_argument('--mc-runs', type=int, default=2000,
                        help='Monte Carlo iterations (default: 2000)')
    args = parser.parse_args()

    tasks = args.task if args.task else [1, 2, 3, 4, 5]

    print()
    print('#' * 100)
    print('#  ALTAIR DEEP ANALYSIS -- 8 x 15m EXPANSION PICKS')
    print('#  Tickers: %s' % ', '.join(TICKERS_15M))
    print('#  Tasks: %s' % ', '.join(str(t) for t in tasks))
    print('#' * 100)

    # Step 1: Run all 8 backtests
    print()
    print('Running backtests...')
    all_summaries = {}
    all_trades = {}      # ticker -> trade_reports
    all_trade_pnls = {}  # ticker -> _trade_pnls

    for i, tk in enumerate(TICKERS_15M, 1):
        sys.stdout.write('  [%d/%d] %-6s ...' % (i, len(TICKERS_15M), tk))
        sys.stdout.flush()
        cfg = build_config(tk)
        if cfg is None:
            print(' SKIP (no CSV)')
            continue
        summary, trades, trade_pnls = run_bt_full(tk, cfg)
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
    print('BACKTEST SUMMARY:')
    print('  %-6s %4s %5s %5s %5s %8s  %s' % (
        'Ticker', 'T', 'PF', 'Shrp', 'DD%', 'PnL', 'Sector'))
    print('  ' + '-' * 55)
    for tk in TICKERS_15M:
        if tk not in all_summaries:
            continue
        s = all_summaries[tk]
        print('  %-6s %4d %5.2f %5.2f %4.1f%% %+8.0f  %s' % (
            tk, s['trades'], min(s['pf'], 99), s['sharpe'],
            s['max_dd'], s['net_pnl'], SECTORS.get(tk, '')))

    # Run requested tasks
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
