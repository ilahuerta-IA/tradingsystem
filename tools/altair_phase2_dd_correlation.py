"""
ALTAIR Phase 2 -- Drawdown Correlation Analysis

Runs BT for 20 Phase-1 candidates, extracts daily equity curves, and computes:
  1. Correlation matrix of daily returns between tickers
  2. Drawdown clusters: which tickers fall together, when, how deep
  3. Worst combined months (aggregated portfolio DD)
  4. Pair-wise loss overlap flags

Usage:
    python tools/altair_phase2_dd_correlation.py                # all 20 candidates
    python tools/altair_phase2_dd_correlation.py --ticker NVDA JPM SBAC
    python tools/altair_phase2_dd_correlation.py --csv           # export daily equity to CSV
"""
import sys
import os
import io
import re
import math
import contextlib
import warnings
import argparse
from datetime import datetime, date
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
ANALYSIS_DIR = Path(PROJECT_ROOT) / "analysis"
SCREENING_FILE = ANALYSIS_DIR / "altair_sp500_screening_results.txt"

CONFIG_A = {'max_sl_atr_mult': 2.0, 'dtosc_os': 25}
CONFIG_B = {'max_sl_atr_mult': 4.0, 'dtosc_os': 20}

# Phase 1 combined candidate list (20 tickers)
PHASE1_CANDIDATES = [
    # 8 common (scoring + visual)
    'TYL', 'SBAC', 'AWK', 'TTWO', 'PWR', 'KEYS', 'HCA', 'MCO',
    # 4 solo visuals (NDX/DJ30 actives)
    'NVDA', 'JPM', 'NSC', 'V',
    # 8 solo scoring
    'ALB', 'RMD', 'LHX', 'AXON', 'WDC', 'WST', 'TDY', 'MPWR',
]

SECTORS = {
    'TYL': 'Tech/Gov', 'SBAC': 'TowerREIT', 'AWK': 'WaterUtil',
    'TTWO': 'Gaming', 'PWR': 'Industrial', 'KEYS': 'ElecTest',
    'HCA': 'HealthProv', 'MCO': 'Ratings', 'NVDA': 'Semicon',
    'JPM': 'Banking', 'NSC': 'Railroad', 'V': 'Payments',
    'ALB': 'Chemical', 'RMD': 'MedDevice', 'LHX': 'Defense',
    'AXON': 'SecTech', 'WDC': 'Storage', 'WST': 'PharmaPkg',
    'TDY': 'DefInstr', 'MPWR': 'Semicon',
}


# ===========================================================================
# BT Analyzer -- capture (date, portfolio_value) each bar
# ===========================================================================

class DailyEquityCurve(bt.Analyzer):
    """Records end-of-day portfolio value for each trading day."""

    def start(self):
        self._day_vals = {}  # date -> last portfolio value that day

    def next(self):
        dt = self.strategy.data.datetime.date(0)
        val = self.strategy.broker.get_value()
        self._day_vals[dt] = val

    def get_analysis(self):
        return self._day_vals


# ===========================================================================
# Run single BT with daily equity extraction
# ===========================================================================

def run_bt(asset_name, asset_cfg, override_params=None):
    """Run ALTAIR BT and return daily equity curve + summary stats."""
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
        cerebro.addanalyzer(DailyEquityCurve, _name='daily_eq')

        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            results = cerebro.run()

        strat = results[0]
        daily_eq = strat.analyzers.daily_eq.get_analysis()

        # Summary stats
        fv = cerebro.broker.getvalue()
        pnl = fv - STARTING_CASH
        t = strat.total_trades
        w = strat.wins
        gp = strat.gross_profit
        gl = strat.gross_loss
        pf = (gp / gl) if gl > 0 else (float('inf') if gp > 0 else 0)

        # Max DD from portfolio values
        dd = 0.0
        pv = list(strat._portfolio_values) if strat._portfolio_values else []
        if pv:
            peak = pv[0]
            for v in pv:
                if v > peak:
                    peak = v
                d = (peak - v) / peak * 100.0
                if d > dd:
                    dd = d

        return {
            'daily_eq': daily_eq,  # {date: portfolio_value}
            'trades': t, 'pf': min(pf, 99.0), 'net_pnl': pnl, 'max_dd': dd,
        }
    except Exception as e:
        return {'error': str(e)}


# ===========================================================================
# Config loading (reuse from heatmap tool)
# ===========================================================================

def _detect_from_date(csv_path):
    with open(csv_path, 'r') as f:
        f.readline()
        first = f.readline().strip()
    if first:
        ds = first.split(',')[0]
        return datetime(int(ds[:4]), int(ds[4:6]), int(ds[6:8]))
    return datetime(2017, 1, 1)


def _parse_best_config():
    best = {}
    if not SCREENING_FILE.exists():
        return best
    text = SCREENING_FILE.read_text(encoding='utf-8')
    for line in text.splitlines():
        m = re.match(r'^(\w+)\s+\|.*\|\s+([AB\-])\s*$', line)
        if m:
            cfg = m.group(2)
            best[m.group(1)] = cfg if cfg in ('A', 'B') else 'A'
    return best


def load_configs(only_tickers=None):
    """Load configs for Phase 1 candidates only."""
    target = set(only_tickers) if only_tickers else set(PHASE1_CANDIDATES)
    all_cfgs = {}

    # 1. From settings_altair.py (active + disabled)
    for key, cfg in ALTAIR_STRATEGIES_CONFIG.items():
        name = cfg['asset_name']
        if name in target:
            all_cfgs[name] = cfg

    # 2. Pending tickers (with best config from screening)
    missing = target - set(all_cfgs.keys())
    if missing:
        best_map = _parse_best_config()
        for ticker in missing:
            csv_name = '%s_1h_8Yea.csv' % ticker
            csv_path = os.path.join(PROJECT_ROOT, 'data', csv_name)
            if not os.path.exists(csv_path):
                continue
            from_date = _detect_from_date(csv_path)
            best = best_map.get(ticker, 'A')
            override = CONFIG_B if best == 'B' else CONFIG_A
            cfg = _make_config(ticker, csv_name, from_date,
                               active=True, universe='sp500_pending',
                               **override)
            cfg['to_date'] = datetime(2026, 12, 31)
            all_cfgs[ticker] = cfg

    return all_cfgs


# ===========================================================================
# Build aligned daily return matrix
# ===========================================================================

def build_return_matrix(equity_curves):
    """
    Build aligned daily return matrix from per-ticker equity curves.

    Returns:
        dates: sorted list of dates
        tickers: list of ticker names (column order)
        ret_matrix: np.array shape (n_days, n_tickers) of daily returns
        eq_matrix:  np.array shape (n_days, n_tickers) of equity values
    """
    # Find common date range
    all_dates = set()
    for eq in equity_curves.values():
        all_dates.update(eq.keys())
    dates = sorted(all_dates)

    tickers = sorted(equity_curves.keys())
    n = len(dates)
    m = len(tickers)

    eq_matrix = np.full((n, m), np.nan)
    for j, tk in enumerate(tickers):
        eq = equity_curves[tk]
        for i, d in enumerate(dates):
            if d in eq:
                eq_matrix[i, j] = eq[d]

    # Forward-fill NaN (ticker not trading on some days = flat equity)
    for j in range(m):
        last_valid = STARTING_CASH
        for i in range(n):
            if np.isnan(eq_matrix[i, j]):
                eq_matrix[i, j] = last_valid
            else:
                last_valid = eq_matrix[i, j]

    # Daily returns
    ret_matrix = np.zeros((n, m))
    for i in range(1, n):
        for j in range(m):
            prev = eq_matrix[i - 1, j]
            if prev > 0:
                ret_matrix[i, j] = (eq_matrix[i, j] - prev) / prev

    return dates, tickers, ret_matrix, eq_matrix


# ===========================================================================
# Analysis functions
# ===========================================================================

def correlation_matrix(ret_matrix, tickers):
    """Compute pairwise correlation of daily returns."""
    n_tickers = len(tickers)
    corr = np.corrcoef(ret_matrix.T)
    # Handle NaN from zero-variance columns
    corr = np.nan_to_num(corr, nan=0.0)
    return corr


def monthly_pnl_matrix(dates, eq_matrix, tickers):
    """Compute monthly PnL (absolute $) per ticker."""
    monthly = defaultdict(lambda: defaultdict(float))
    for i in range(1, len(dates)):
        ym = (dates[i].year, dates[i].month)
        for j in range(len(tickers)):
            monthly[ym][tickers[j]] += eq_matrix[i, j] - eq_matrix[i - 1, j]
    return monthly


def drawdown_series(eq_matrix, tickers):
    """Compute daily DD% series for each ticker."""
    n, m = eq_matrix.shape
    dd_matrix = np.zeros((n, m))
    for j in range(m):
        peak = eq_matrix[0, j]
        for i in range(n):
            if eq_matrix[i, j] > peak:
                peak = eq_matrix[i, j]
            dd_matrix[i, j] = (peak - eq_matrix[i, j]) / peak * 100.0
    return dd_matrix


def portfolio_equity(eq_matrix, tickers):
    """
    Compute equal-weight portfolio equity.
    Each ticker starts at $100K. Portfolio = sum of all.
    """
    port_eq = np.sum(eq_matrix, axis=1)
    return port_eq


def find_worst_months(dates, eq_matrix, tickers, top_n=10):
    """Find worst months by combined portfolio change."""
    monthly = monthly_pnl_matrix(dates, eq_matrix, tickers)
    month_totals = []
    for ym, ticker_pnls in monthly.items():
        total = sum(ticker_pnls.values())
        month_totals.append((ym, total, ticker_pnls))
    month_totals.sort(key=lambda x: x[1])
    return month_totals[:top_n]


def find_dd_clusters(dates, dd_matrix, tickers, threshold=3.0):
    """
    Find days where multiple tickers are simultaneously in DD > threshold%.
    Returns list of (date, n_tickers_in_dd, avg_dd, tickers_in_dd).
    """
    clusters = []
    for i in range(len(dates)):
        in_dd = []
        for j in range(len(tickers)):
            if dd_matrix[i, j] > threshold:
                in_dd.append((tickers[j], dd_matrix[i, j]))
        if len(in_dd) >= 3:  # cluster = 3+ tickers in DD simultaneously
            avg_dd = np.mean([d for _, d in in_dd])
            clusters.append((dates[i], len(in_dd), avg_dd, in_dd))
    return clusters


def loss_overlap_pairs(dates, ret_matrix, tickers):
    """
    For each pair, count how many negative-return days overlap.
    High overlap = bad diversification.
    """
    n, m = ret_matrix.shape
    overlaps = {}
    for j1 in range(m):
        neg1 = ret_matrix[:, j1] < -0.001  # meaningful loss threshold
        for j2 in range(j1 + 1, m):
            neg2 = ret_matrix[:, j2] < -0.001
            both = np.sum(neg1 & neg2)
            total_neg = max(np.sum(neg1), np.sum(neg2), 1)
            overlap_pct = both / total_neg * 100
            overlaps[(tickers[j1], tickers[j2])] = {
                'both_neg': int(both),
                'overlap_pct': overlap_pct,
            }
    return overlaps


# ===========================================================================
# Display functions
# ===========================================================================

def display_correlation(corr, tickers):
    """Print correlation matrix."""
    print()
    print("=" * 80)
    print("DAILY RETURN CORRELATION MATRIX")
    print("=" * 80)
    print()

    # Header
    hdr = '%-6s' % ''
    for tk in tickers:
        hdr += '%7s' % tk[:5]
    print(hdr)
    print('-' * (6 + 7 * len(tickers)))

    for i, tk in enumerate(tickers):
        row = '%-6s' % tk
        for j in range(len(tickers)):
            val = corr[i, j]
            if i == j:
                row += '     --'
            elif abs(val) >= 0.30:
                row += '  %+.2f' % val  # highlight high corr
            else:
                row += '   %.2f' % val
            
        print(row)
    print()


def display_worst_months(worst_months, tickers):
    """Print worst months with per-ticker breakdown."""
    print()
    print("=" * 80)
    print("WORST COMBINED MONTHS (top 10)")
    print("=" * 80)
    print()

    hdr = '%-10s %+10s  ' % ('Month', 'PortfPnL')
    for tk in tickers:
        hdr += '%+8s' % tk[:6]
    print(hdr)
    print('-' * (22 + 8 * len(tickers)))

    for ym, total, ticker_pnls in worst_months:
        row = '%4d-%02d    %+10.0f  ' % (ym[0], ym[1], total)
        for tk in tickers:
            pnl = ticker_pnls.get(tk, 0)
            if pnl == 0:
                row += '%8s' % '--'
            elif pnl < -500:
                row += '%+8.0f' % pnl  # loss
            else:
                row += '%+8.0f' % pnl
        print(row)
    print()


def display_dd_clusters(clusters, top_n=15):
    """Print worst DD cluster events."""
    print()
    print("=" * 80)
    print("DRAWDOWN CLUSTERS (3+ tickers simultaneously in DD > 3%%)")
    print("=" * 80)
    print()

    if not clusters:
        print("  No significant clusters found.")
        return

    # Group by month and take worst day per month
    monthly_worst = {}
    for d, n_tk, avg_dd, tickers_in_dd in clusters:
        ym = (d.year, d.month)
        if ym not in monthly_worst or avg_dd > monthly_worst[ym][2]:
            monthly_worst[ym] = (d, n_tk, avg_dd, tickers_in_dd)

    ranked = sorted(monthly_worst.values(), key=lambda x: -x[2])[:top_n]
    for d, n_tk, avg_dd, in_dd in ranked:
        tks = sorted(in_dd, key=lambda x: -x[1])
        tk_str = ', '.join('%s(%.1f%%)' % (t, dd) for t, dd in tks[:8])
        if len(tks) > 8:
            tk_str += ' +%d more' % (len(tks) - 8)
        print('  %s  %2d tickers  avgDD=%.1f%%  %s' % (
            d.strftime('%Y-%m-%d'), n_tk, avg_dd, tk_str))
    print()


def display_loss_overlap(overlaps, tickers, top_n=20):
    """Print pairs with highest loss overlap."""
    print()
    print("=" * 80)
    print("LOSS DAY OVERLAP (pairs losing on same days)")
    print("=" * 80)
    print()

    ranked = sorted(overlaps.items(), key=lambda x: -x[1]['overlap_pct'])
    print('  %-6s %-6s  %s  %s' % ('Tk1', 'Tk2', 'BothNeg', 'Overlap%'))
    print('  ' + '-' * 40)
    for (t1, t2), info in ranked[:top_n]:
        flag = ' !! WARN' if info['overlap_pct'] > 40 else ''
        print('  %-6s %-6s  %5d    %5.1f%%%s' % (
            t1, t2, info['both_neg'], info['overlap_pct'], flag))
    print()


def display_portfolio_summary(dates, eq_matrix, tickers):
    """Print combined portfolio stats."""
    print()
    print("=" * 80)
    print("COMBINED PORTFOLIO (equal-weight, $100K per ticker)")
    print("=" * 80)
    print()

    port_eq = portfolio_equity(eq_matrix, tickers)
    total_start = STARTING_CASH * len(tickers)
    total_end = port_eq[-1]
    total_pnl = total_end - total_start

    # Portfolio DD
    peak = port_eq[0]
    max_dd = 0.0
    max_dd_date = dates[0]
    for i in range(len(port_eq)):
        if port_eq[i] > peak:
            peak = port_eq[i]
        d = (peak - port_eq[i]) / peak * 100.0
        if d > max_dd:
            max_dd = d
            max_dd_date = dates[i]

    # Annualized return
    years = (dates[-1] - dates[0]).days / 365.25
    ann_ret = (total_pnl / total_start) / years * 100 if years > 0 else 0.0

    # Portfolio Sharpe (daily returns -> annualized)
    port_returns = np.diff(port_eq) / port_eq[:-1]
    port_returns = port_returns[~np.isnan(port_returns)]
    if len(port_returns) > 1 and np.std(port_returns) > 0:
        # Approx 252 trading days/year
        sharpe = (np.mean(port_returns) / np.std(port_returns)) * math.sqrt(252)
    else:
        sharpe = 0.0

    # Yearly PnL
    yearly_pnl = defaultdict(float)
    for i in range(1, len(dates)):
        y = dates[i].year
        yearly_pnl[y] += port_eq[i] - port_eq[i - 1]

    print('  Tickers:        %d' % len(tickers))
    print('  Capital:        $%.0f per ticker ($%.0f total)' % (
        STARTING_CASH, total_start))
    print('  Period:         %s to %s (%.1f years)' % (
        dates[0], dates[-1], years))
    print('  Total PnL:      $%+.0f' % total_pnl)
    print('  Annual Return:  %.1f%%' % ann_ret)
    print('  Sharpe (daily): %.2f' % sharpe)
    print('  Max DD:         %.1f%% (near %s)' % (max_dd, max_dd_date))
    print()

    # Yearly
    print('  Yearly PnL:')
    for y in sorted(yearly_pnl.keys()):
        pnl = yearly_pnl[y]
        pct = pnl / total_start * 100
        bar = '+' * min(int(abs(pct) * 2), 40) if pnl > 0 else '-' * min(
            int(abs(pct) * 2), 40)
        sign = '+' if pnl > 0 else ('-' if pnl < 0 else '')
        print('    %d  $%s%.0f  (%s%.1f%%)  %s' % (
            y, sign, abs(pnl), sign, pct, bar))
    print()


def export_daily_csv(dates, eq_matrix, tickers, filepath):
    """Export daily equity curves to CSV for external analysis."""
    with open(filepath, 'w') as f:
        f.write('date,' + ','.join(tickers) + '\n')
        for i, d in enumerate(dates):
            vals = ','.join('%.2f' % eq_matrix[i, j] for j in range(len(tickers)))
            f.write('%s,%s\n' % (d.strftime('%Y-%m-%d'), vals))
    print('  Daily equity exported to: %s' % filepath)


# ===========================================================================
# Main
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(
        description="ALTAIR Phase 2 -- DD Correlation Analysis")
    parser.add_argument('--ticker', nargs='+',
                        help='Run specific tickers (default: 20 Phase-1 candidates)')
    parser.add_argument('--csv', action='store_true',
                        help='Export daily equity curves to CSV')
    args = parser.parse_args()

    tickers_to_run = [t.upper() for t in args.ticker] if args.ticker else None
    all_cfgs = load_configs(only_tickers=tickers_to_run)

    found = sorted(all_cfgs.keys())
    missing = set(tickers_to_run or PHASE1_CANDIDATES) - set(found)
    print()
    print("Phase 2 -- DD Correlation Analysis")
    print("  Candidates: %d loaded" % len(found))
    if missing:
        print("  WARNING: missing data for: %s" % ', '.join(sorted(missing)))
    print()

    # Run all BTs
    equity_curves = {}
    summaries = {}
    for i, name in enumerate(found, 1):
        cfg = all_cfgs[name]
        sector = SECTORS.get(name, '?')
        sys.stdout.write('  [%d/%d] %-6s (%s) ...' % (i, len(found), name, sector))
        sys.stdout.flush()
        r = run_bt(name, cfg)
        if 'error' in r:
            print(' ERROR: %s' % r['error'])
        else:
            equity_curves[name] = r['daily_eq']
            summaries[name] = r
            print(' T=%d PF=%.2f DD=%.1f%% PnL=$%+.0f' % (
                r['trades'], r['pf'], r['max_dd'], r['net_pnl']))

    if len(equity_curves) < 2:
        print("ERROR: need at least 2 tickers for correlation analysis.")
        return

    # Build aligned matrices
    print()
    print("Building aligned daily return matrix...")
    dates, tickers, ret_matrix, eq_matrix = build_return_matrix(equity_curves)
    print("  %d trading days x %d tickers" % (len(dates), len(tickers)))

    # Export CSV if requested
    if args.csv:
        csv_path = ANALYSIS_DIR / 'altair_phase2_daily_equity.csv'
        export_daily_csv(dates, eq_matrix, tickers, str(csv_path))

    # Analyses
    corr = correlation_matrix(ret_matrix, tickers)
    dd_matrix = drawdown_series(eq_matrix, tickers)
    overlaps = loss_overlap_pairs(dates, ret_matrix, tickers)
    worst = find_worst_months(dates, eq_matrix, tickers)
    clusters = find_dd_clusters(dates, dd_matrix, tickers)

    # Display all
    display_correlation(corr, tickers)
    display_worst_months(worst, tickers)
    display_dd_clusters(clusters)
    display_loss_overlap(overlaps, tickers)
    display_portfolio_summary(dates, eq_matrix, tickers)

    # Summary table: individual ticker stats sorted by PF
    print()
    print("=" * 80)
    print("INDIVIDUAL TICKER SUMMARY (Phase 2 candidates)")
    print("=" * 80)
    print()
    print('  %-6s %-10s %3s %5s %5s %6s' % (
        'Ticker', 'Sector', 'T', 'PF', 'DD%', 'PnL'))
    print('  ' + '-' * 45)
    ranked = sorted(summaries.items(), key=lambda x: -x[1]['pf'])
    for name, s in ranked:
        sector = SECTORS.get(name, '?')
        print('  %-6s %-10s %3d %5.2f %5.1f %+9.0f' % (
            name, sector, s['trades'], s['pf'], s['max_dd'], s['net_pnl']))
    print()


if __name__ == '__main__':
    main()
