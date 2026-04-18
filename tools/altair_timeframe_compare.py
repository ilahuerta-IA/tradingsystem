"""
ALTAIR Timeframe Comparison -- H1 vs 30m vs 15m

Compares ALTAIR strategy performance across timeframes for the same tickers.
Uses cerebro.resampledata() to build proper 30m/15m bars from 5m CSV data.
Reuses run_bt()/extract() pattern from altair_sp500_ab_test.py.

The strategy code is IDENTICAL across timeframes -- only bars_per_day and
the CSV source change. bars_per_day scales the D1 regime indicators.
DTOSC(8,5,3,3) stays fixed (Miner pre-study: zone coverage OK at all TFs).

Timeframe mapping (US stocks, 14:30-21:00 UTC):
    H1  = 7 bars/day   (data: *_1h_8Yea.csv, native)
    30m = 13 bars/day   (data: *_5m_8Yea.csv, resampledata 30min)
    15m = 26 bars/day   (data: *_5m_8Yea.csv, resampledata 15min)

Usage:
    python tools/altair_timeframe_compare.py                     # all 5 tickers
    python tools/altair_timeframe_compare.py --ticker JPM V      # specific
    python tools/altair_timeframe_compare.py --tf H1 30m         # only H1 vs 30m
"""
import sys
import os
import io
import math
import contextlib
import warnings
import argparse
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
    ALTAIR_STRATEGIES_CONFIG, ALTAIR_BROKER_CONFIG, _make_config,
)

STARTING_CASH = 100_000.0

# Tickers with 5m data available for comparison
TICKERS_5M = [
    # Original 7
    'JPM', 'V', 'NVDA', 'MSFT', 'GOOGL', 'ALB', 'WDC',
    # Top-20 expansion (13 new)
    'TYL', 'SBAC', 'AWK', 'TTWO', 'PWR', 'KEYS', 'HCA',
    'MCO', 'NSC', 'RMD', 'LHX', 'AXON', 'WST', 'TDY', 'MPWR',
]

# Timeframe definitions: label -> (csv_suffix, bars_per_day, resample_minutes)
# resample_minutes=0 means native (no resampling needed).
TIMEFRAMES = {
    'H1':  ('_1h_8Yea.csv', 7,  0),
    '30m': ('_5m_8Yea.csv', 13, 30),
    '15m': ('_5m_8Yea.csv', 26, 15),
}

# Best config per ticker (from Phase 1 screening / settings_altair.py)
BEST_CONFIG = {
    # Original 7
    'JPM':   {'max_sl_atr_mult': 4.0, 'dtosc_os': 20},    # Config B
    'V':     {'max_sl_atr_mult': 4.0, 'dtosc_os': 20},    # Config B
    'NVDA':  {'max_sl_atr_mult': 2.0, 'dtosc_os': 25},    # Config A
    'MSFT':  {'max_sl_atr_mult': 2.0, 'dtosc_os': 25},    # Config A
    'GOOGL': {'max_sl_atr_mult': 2.0, 'dtosc_os': 25},    # Config A
    'ALB':   {'max_sl_atr_mult': 4.0, 'dtosc_os': 20},    # Config B
    'WDC':   {'max_sl_atr_mult': 4.0, 'dtosc_os': 20},    # Config B
    # Top-20 expansion (from altair_sp500_screening_results.txt)
    'TYL':   {'max_sl_atr_mult': 4.0, 'dtosc_os': 20},    # Config B: PF 2.23
    'SBAC':  {'max_sl_atr_mult': 4.0, 'dtosc_os': 20},    # Config B: PF 1.75
    'AWK':   {'max_sl_atr_mult': 4.0, 'dtosc_os': 20},    # Config B: PF 1.65
    'TTWO':  {'max_sl_atr_mult': 2.0, 'dtosc_os': 25},    # Config A: PF 2.10
    'PWR':   {'max_sl_atr_mult': 4.0, 'dtosc_os': 20},    # Config B: PF 1.85
    'KEYS':  {'max_sl_atr_mult': 4.0, 'dtosc_os': 20},    # Config B: PF 1.73
    'HCA':   {'max_sl_atr_mult': 4.0, 'dtosc_os': 20},    # Config B: PF 1.74
    'MCO':   {'max_sl_atr_mult': 2.0, 'dtosc_os': 25},    # Config A: PF 1.90
    'NSC':   {'max_sl_atr_mult': 4.0, 'dtosc_os': 20},    # Config B
    'RMD':   {'max_sl_atr_mult': 2.0, 'dtosc_os': 25},    # Config A: PF 1.71
    'LHX':   {'max_sl_atr_mult': 2.0, 'dtosc_os': 25},    # Config A: PF 1.54
    'AXON':  {'max_sl_atr_mult': 2.0, 'dtosc_os': 25},    # Config A: PF 2.42
    'WST':   {'max_sl_atr_mult': 2.0, 'dtosc_os': 25},    # Config A: PF 1.94
    'TDY':   {'max_sl_atr_mult': 2.0, 'dtosc_os': 25},    # Config A: PF 1.79
    'MPWR':  {'max_sl_atr_mult': 2.0, 'dtosc_os': 25},    # Config A: PF 1.54
}


# ── BT runner (from altair_sp500_ab_test.py) ─────────────────────────────────

def run_bt(asset_name, asset_cfg, override_params=None):
    """Run one ALTAIR BT with optional param overrides."""
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
            data_resampled._name = asset_name
        else:
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

        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            results = cerebro.run()

        strat = results[0]
        return extract(strat, cerebro)
    except Exception as e:
        return {'error': str(e)}


def extract(strat, cerebro):
    """Extract summary stats from completed BT (same as ab_test.py)."""
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

    # Time span
    first_dt = strat._first_bar_dt
    last_dt = strat._last_bar_dt
    years = max((last_dt - first_dt).days / 365.25, 0.5) if first_dt and last_dt else 1.0

    # Sharpe from trade returns (annualized)
    trade_pnls = [tp['pnl'] for tp in strat._trade_pnls]
    returns = [p / STARTING_CASH for p in trade_pnls]
    sharpe = 0.0
    if len(returns) > 1:
        avg_r = np.mean(returns)
        std_r = np.std(returns, ddof=1)
        tpy = t / years
        if std_r > 0:
            sharpe = (avg_r / std_r) * math.sqrt(tpy)

    # Yearly PnL + PF + Sharpe
    yearly_raw = defaultdict(lambda: {'trades': 0, 'pnl': 0.0,
                                       'gp': 0.0, 'gl': 0.0, 'rets': []})
    for tp in strat._trade_pnls:
        y = tp['year']
        yearly_raw[y]['trades'] += 1
        yearly_raw[y]['pnl'] += tp['pnl']
        yearly_raw[y]['rets'].append(tp['pnl'] / STARTING_CASH)
        if tp['is_winner']:
            yearly_raw[y]['gp'] += tp['pnl']
        else:
            yearly_raw[y]['gl'] += abs(tp['pnl'])

    yearly = {}
    pos_years = 0
    for y in sorted(yearly_raw.keys()):
        s = yearly_raw[y]
        ypf = (s['gp'] / s['gl']) if s['gl'] > 0 else (
            float('inf') if s['gp'] > 0 else 0)
        yshrp = 0.0
        if len(s['rets']) > 1:
            avg_r = np.mean(s['rets'])
            std_r = np.std(s['rets'], ddof=1)
            if std_r > 0:
                yshrp = (avg_r / std_r) * math.sqrt(len(s['rets']))
        yearly[y] = {'trades': s['trades'], 'pnl': s['pnl'],
                      'pf': ypf, 'sharpe': yshrp}
        if s['pnl'] > 0:
            pos_years += 1

    return {
        'trades': t, 'wr': wr, 'pf': pf, 'net_pnl': pnl,
        'max_dd': dd, 'sharpe': sharpe, 'years': years,
        'yearly': yearly,
        'pos_years': pos_years, 'total_years': len(yearly),
        'trades_per_month': t / (years * 12) if years > 0 else 0,
    }


# ── Config builder ────────────────────────────────────────────────────────────

def _detect_from_date(csv_path):
    """Read first data line to detect start date."""
    with open(csv_path, 'r') as f:
        f.readline()  # header
        first = f.readline().strip()
    if first:
        ds = first.split(',')[0]
        return datetime(int(ds[:4]), int(ds[4:6]), int(ds[6:8]))
    return datetime(2017, 1, 1)


def build_config(ticker, tf_label):
    """Build ALTAIR config for a given ticker and timeframe.

    Uses cerebro.resampledata() to build proper 30m/15m OHLC bars.
    All indicator params stay at H1 defaults -- the resampled bars
    ensure DTOSC(8) = 8 bars of 30m = 4h, consistent with H1 behavior.
    Only bars_per_day changes (for D1 regime scaling).
    """
    csv_suffix, bpd, resample_min = TIMEFRAMES[tf_label]
    csv_name = '%s%s' % (ticker, csv_suffix)
    csv_path = os.path.join(PROJECT_ROOT, 'data', csv_name)
    if not os.path.exists(csv_path):
        return None
    from_date = _detect_from_date(csv_path)
    overrides = dict(BEST_CONFIG.get(ticker, {}))
    overrides['bars_per_day'] = bpd

    cfg = _make_config(ticker, csv_name, from_date,
                       active=True, universe='tf_compare', **overrides)
    cfg['to_date'] = datetime(2026, 12, 31)
    cfg['resample_minutes'] = resample_min
    return cfg


# ── Display ───────────────────────────────────────────────────────────────────

def display_comparison(all_results, tf_labels):
    """Print side-by-side comparison table."""
    print()
    print('=' * 100)
    print('ALTAIR TIMEFRAME COMPARISON -- %s' % ' vs '.join(tf_labels))
    print('=' * 100)
    print()

    # Per-ticker comparison
    tickers = sorted(set(tk for tk, _ in all_results.keys()))

    hdr = '%-6s %-4s  %4s %5s %5s %5s %6s %7s %5s' % (
        'Ticker', 'TF', 'T', 'T/mo', 'PF', 'Shrp', 'DD%', 'PnL', 'Y+')
    print(hdr)
    print('-' * 72)

    for ticker in tickers:
        for tf in tf_labels:
            key = (ticker, tf)
            if key not in all_results:
                print('%-6s %-4s  %s' % (ticker, tf, '-- no data --'))
                continue
            r = all_results[key]
            if 'error' in r:
                print('%-6s %-4s  ERROR: %s' % (ticker, tf, r['error']))
                continue
            pf_str = '%5.2f' % r['pf'] if r['pf'] < 99 else '  INF'
            print('%-6s %-4s  %4d %5.2f %s %5.2f %5.1f%% %+7.0f %d/%d' % (
                ticker, tf, r['trades'], r['trades_per_month'],
                pf_str, r['sharpe'], r['max_dd'],
                r['net_pnl'], r['pos_years'], r['total_years']))
        print()

    # Aggregate summary per TF
    print('-' * 72)
    print()
    print('AGGREGATE BY TIMEFRAME:')
    print()
    print('%-4s  %5s %6s %6s %6s %6s %9s' % (
        'TF', 'T/mo', 'medPF', 'mShrp', 'medDD', 'mDD%', 'totPnL'))
    print('-' * 55)

    for tf in tf_labels:
        tf_results = [all_results[(tk, tf)] for tk in tickers
                      if (tk, tf) in all_results and 'error' not in all_results[(tk, tf)]]
        if not tf_results:
            continue
        trades_mo = [r['trades_per_month'] for r in tf_results]
        pfs = [min(r['pf'], 99) for r in tf_results]
        sharpes = [r['sharpe'] for r in tf_results]
        dds = [r['max_dd'] for r in tf_results]
        total_pnl = sum(r['net_pnl'] for r in tf_results)
        print('%-4s  %5.2f %6.2f %6.2f %5.1f%% %5.1f%% %+9.0f' % (
            tf,
            np.mean(trades_mo), np.median(pfs), np.median(sharpes),
            np.median(dds), np.mean(dds), total_pnl))
    print()

    # Yearly heatmap per TF
    all_years = set()
    for r in all_results.values():
        if 'error' not in r:
            all_years.update(r['yearly'].keys())
    years = sorted(all_years)

    if years:
        print('YEARLY TRADES (all tickers combined):')
        yr_hdr = '%-4s  ' + ''.join('%6d' % y for y in years) + '  TOTAL'
        print(yr_hdr)
        print('-' * (6 + 6 * len(years) + 8))
        for tf in tf_labels:
            tf_results = [(tk, all_results[(tk, tf)])
                          for tk in tickers
                          if (tk, tf) in all_results and 'error' not in all_results[(tk, tf)]]
            row = '%-4s  ' % tf
            total_t = 0
            for y in years:
                yt = sum(r['yearly'].get(y, {}).get('trades', 0) for _, r in tf_results)
                total_t += yt
                row += '%6d' % yt
            row += '  %5d' % total_t
            print(row)
        print()


def display_yearly_detail(all_results, tf_labels):
    """Print year-by-year PF / Sharpe / PnL per ticker, side by side."""
    tickers = sorted(set(tk for tk, _ in all_results.keys()))
    all_years = set()
    for r in all_results.values():
        if 'error' not in r:
            all_years.update(r['yearly'].keys())
    years = sorted(all_years)

    print()
    print('=' * 100)
    print('YEARLY DETAIL: %s' % ' vs '.join(tf_labels))
    print('=' * 100)

    for ticker in tickers:
        res = {}
        for tf in tf_labels:
            key = (ticker, tf)
            if key in all_results and 'error' not in all_results[key]:
                res[tf] = all_results[key]
        if not res:
            continue

        # Ticker header with overall stats
        parts = []
        for tf in tf_labels:
            if tf in res:
                r = res[tf]
                pf = min(r['pf'], 99)
                parts.append('%s: T=%d PF=%.2f Shrp=%.2f PnL=%+.0f' % (
                    tf, r['trades'], pf, r['sharpe'], r['net_pnl']))
        print()
        print('%-6s  (%s)' % (ticker, '  |  '.join(parts)))

        # Column headers per TF
        col = '      '
        for tf in tf_labels:
            col += '| %3s:  T    PF   Shrp      PnL  ' % tf
        print(col)
        print('-' * len(col))

        for y in years:
            row = '%4d  ' % y
            for tf in tf_labels:
                if tf in res:
                    yd = res[tf]['yearly'].get(y)
                    if yd and yd['trades'] > 0:
                        pf_s = '%5.2f' % min(yd['pf'], 99)
                        row += '|      %3d %s %+5.2f %+9.0f  ' % (
                            yd['trades'], pf_s, yd['sharpe'], yd['pnl'])
                    else:
                        row += '|       --    --    --       --  '
                else:
                    row += '|       --    --    --       --  '
            print(row)

        # Total row
        row = ' ALL  '
        for tf in tf_labels:
            if tf in res:
                r = res[tf]
                pf_s = '%5.2f' % min(r['pf'], 99)
                row += '|      %3d %s %+5.2f %+9.0f  ' % (
                    r['trades'], pf_s, r['sharpe'], r['net_pnl'])
            else:
                row += '|       --    --    --       --  '
        print('-' * len(col))
        print(row)

    print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='ALTAIR timeframe comparison -- H1 vs 30m vs 15m')
    parser.add_argument('--ticker', nargs='+',
                        help='Specific tickers (default: %s)' % ', '.join(TICKERS_5M))
    parser.add_argument('--tf', nargs='+', choices=list(TIMEFRAMES.keys()),
                        help='Timeframes to compare (default: all)')
    parser.add_argument('--yearly', action='store_true',
                        help='Show year-by-year detail per ticker')
    args = parser.parse_args()

    tickers = [t.upper() for t in args.ticker] if args.ticker else TICKERS_5M
    tf_labels = args.tf if args.tf else list(TIMEFRAMES.keys())

    print()
    print('ALTAIR Timeframe Comparison')
    print('  Tickers: %s' % ', '.join(tickers))
    print('  Timeframes: %s' % ', '.join(tf_labels))
    print()

    all_results = {}
    total_runs = len(tickers) * len(tf_labels)
    run_n = 0

    for ticker in tickers:
        for tf in tf_labels:
            run_n += 1
            sys.stdout.write('  [%d/%d] %-6s %3s ...' % (
                run_n, total_runs, ticker, tf))
            sys.stdout.flush()
            cfg = build_config(ticker, tf)
            if cfg is None:
                print(' SKIP (no CSV)')
                continue
            r = run_bt(ticker, cfg)
            all_results[(ticker, tf)] = r
            if 'error' in r:
                print(' ERROR: %s' % r['error'])
            else:
                print(' T=%3d  T/mo=%.2f  PF=%.2f  Shrp=%.2f  DD=%.1f%%' % (
                    r['trades'], r['trades_per_month'],
                    min(r['pf'], 99), r['sharpe'], r['max_dd']))

    display_comparison(all_results, tf_labels)

    if args.yearly:
        display_yearly_detail(all_results, tf_labels)


if __name__ == '__main__':
    main()
