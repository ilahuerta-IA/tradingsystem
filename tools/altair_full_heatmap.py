"""
ALTAIR Full Heatmap -- Unified Yearly PnL + PF + Sharpe for ALL tickers

Runs ALL ALTAIR tickers (active, disabled, pending) with their best config
and outputs a unified yearly PnL heatmap with PF and Sharpe columns.

Sources:
  - Active/Disabled: from settings_altair.py (uses stored config)
  - Pending (best config): from screening results, applies Config A or B

Usage:
    python tools/altair_full_heatmap.py               # run all
    python tools/altair_full_heatmap.py --source ndx   # only NDX tickers
    python tools/altair_full_heatmap.py --source dj30  # only DJ30
    python tools/altair_full_heatmap.py --source sp500  # only SP500 pending
    python tools/altair_full_heatmap.py --ticker NVDA SBAC MCO  # specific tickers
    python tools/altair_full_heatmap.py --skip-disabled  # exclude failed tickers
"""
import sys
import os
import io
import re
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
ANALYSIS_DIR = Path(PROJECT_ROOT) / "analysis"
SCREENING_FILE = ANALYSIS_DIR / "altair_sp500_screening_results.txt"

CONFIG_A = {'max_sl_atr_mult': 2.0, 'dtosc_os': 25}
CONFIG_B = {'max_sl_atr_mult': 4.0, 'dtosc_os': 20}

# Sector mapping for display
SECTORS = {
    'NVDA': 'Semicon', 'AMAT': 'Semicon', 'AMD': 'Semicon',
    'AVGO': 'Semicon', 'KLAC': 'Semicon', 'LRCX': 'Semicon',
    'MU': 'Semicon', 'ASML': 'Semicon', 'MPWR': 'Semicon',
    'GOOGL': 'Tech', 'MSFT': 'Tech', 'NOW': 'Tech',
    'IT': 'Tech', 'KEYS': 'ElecTest', 'ZBRA': 'Tech',
    'TYL': 'Tech', 'NFLX': 'Stream',
    'CAT': 'Indust', 'FIX': 'Indust', 'EME': 'Indust',
    'PWR': 'Indust', 'WAB': 'Indust', 'LII': 'HVAC',
    'TT': 'HVAC', 'ETN': 'Elect',
    'V': 'Payments', 'AXP': 'Finance', 'JPM': 'Banking',
    'GS': 'InvBank', 'APO': 'AltFin', 'MCO': 'Ratings',
    'CBOE': 'Exchange', 'MSCI': 'FinData', 'EFX': 'DataAnl',
    'NSC': 'Railroad', 'CAH': 'HlthDist', 'FDX': 'Logist',
    'VLO': 'EnRefin', 'MPC': 'EnRefin', 'PGR': 'Insur',
    'HD': 'Retail', 'UNH': 'Health', 'LLY': 'Pharma',
    'LMT': 'Defense', 'PH': 'Indust', 'STZ': 'ConStap',
    'AMP': 'FinSvc', 'DELL': 'Hardware',
    'HCA': 'HlthProv', 'RMD': 'MedDev', 'WST': 'MedDev',
    'AXON': 'Safety', 'LHX': 'AeroDef', 'TDY': 'AeroDef',
    'LITE': 'Optic', 'COHR': 'Optic',
    'TTWO': 'Gaming', 'GNRC': 'PowerGen', 'GE': 'Conglom',
    'WDC': 'Storage', 'STX': 'Storage', 'GRMN': 'NavTech',
    'AWK': 'WaterUtil', 'SBAC': 'TowerREIT', 'EXR': 'StorREIT',
    'HWM': 'AeroMat', 'PKG': 'Packag', 'STLD': 'Steel',
    'ALB': 'Chem', 'AVY': 'Material', 'HSY': 'ConStap',
    'MSI': 'CommEquip', 'RCL': 'Cruise', 'LYV': 'LiveEnt',
    'POOL': 'PoolSupp', 'TPL': 'LandRoy', 'TRGP': 'Midstrm',
    'FIX': 'Indust', 'BR': 'FinTech', 'HLT': 'Hotels',
    'DPZ': 'RestFood', 'HII': 'ShipDef', 'ARES': 'AltFin',
    'TDG': 'AeroPart', 'COR': 'HlthDist',
    'ALGN': 'MedDev', 'FOXA': 'Media', 'EPAM': 'ITServ',
    'FICO': 'CrdScore', 'GPN': 'Payments', 'NOC': 'Defense',
    'CASY': 'ConvStor', 'TER': 'SemiEqup', 'URI': 'EquipRnt',
    'CVNA': 'AutoDlr', 'ATO': 'GasUtil', 'XYZ': 'Fintech',
    'AJG': 'InsBrok',
    'NFLX': 'Stream', 'LLY': 'Pharma', 'LMT': 'Defense',
}


# ── Run backtest ─────────────────────────────────────────────────────────────

def run_bt(asset_name, asset_cfg, override_params=None):
    """Run one ALTAIR BT. Returns dict with yearly PnL, PF, Sharpe, DD."""
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
    pv = list(strat._portfolio_values) if strat._portfolio_values else [STARTING_CASH]
    peak = pv[0]
    for v in pv:
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

    # Yearly PnL
    yearly_raw = defaultdict(lambda: {'trades': 0, 'wins': 0, 'pnl': 0.0,
                                       'gp': 0.0, 'gl': 0.0})
    for tp in strat._trade_pnls:
        y = tp['year']
        yearly_raw[y]['trades'] += 1
        yearly_raw[y]['pnl'] += tp['pnl']
        if tp['is_winner']:
            yearly_raw[y]['wins'] += 1
            yearly_raw[y]['gp'] += tp['pnl']
        else:
            yearly_raw[y]['gl'] += abs(tp['pnl'])

    yearly = {}
    pos_years = 0
    for y in sorted(yearly_raw.keys()):
        s = yearly_raw[y]
        y_pf = (s['gp'] / s['gl']) if s['gl'] > 0 else (
            float('inf') if s['gp'] > 0 else 0)
        yearly[y] = {'trades': s['trades'], 'pnl': s['pnl'], 'pf': y_pf}
        if s['pnl'] > 0:
            pos_years += 1

    return {
        'trades': t, 'wr': wr, 'pf': pf, 'net_pnl': pnl,
        'max_dd': dd, 'sharpe': sharpe,
        'yearly': yearly,
        'pos_years': pos_years, 'total_years': len(yearly),
    }


# ── Config loading ───────────────────────────────────────────────────────────

def _detect_from_date(csv_path):
    with open(csv_path, 'r') as f:
        f.readline()
        first = f.readline().strip()
    if first:
        ds = first.split(',')[0]
        return datetime(int(ds[:4]), int(ds[4:6]), int(ds[6:8]))
    return datetime(2017, 1, 1)


def _parse_best_config():
    """Parse screening results to get best config (A/B) per pending ticker."""
    best = {}
    if not SCREENING_FILE.exists():
        return best
    text = SCREENING_FILE.read_text(encoding='utf-8')
    # Parse comparison table: "AJG    |  1.26 ... | A" or "| -"
    for line in text.splitlines():
        m = re.match(r'^(\w+)\s+\|.*\|\s+([AB\-])\s*$', line)
        if m:
            cfg = m.group(2)
            best[m.group(1)] = cfg if cfg in ('A', 'B') else 'A'
    return best


def load_all_configs(skip_disabled=False, source_filter=None, only_tickers=None):
    """Load all ALTAIR configs: active + disabled + pending."""
    all_cfgs = {}
    sources = {}

    # 1. Active + Disabled from settings_altair.py
    for key, cfg in ALTAIR_STRATEGIES_CONFIG.items():
        name = cfg['asset_name']
        is_active = cfg.get('active', True)
        if skip_disabled and not is_active:
            continue

        universe = cfg.get('universe', 'ndx')
        src = 'active' if is_active else 'disabled'
        tag = '%s/%s' % (universe.upper(), src)

        if source_filter:
            if source_filter == 'ndx' and universe != 'ndx':
                continue
            if source_filter == 'dj30' and universe != 'dj30':
                continue

        all_cfgs[name] = cfg
        sources[name] = tag

    # 2. Pending tickers from file (with best config from screening)
    if source_filter not in ('ndx', 'dj30'):
        best_map = _parse_best_config()
        pending_path = os.path.join(SCRIPT_DIR, 'pending_tickers.txt')
        tickers = []
        if os.path.exists(pending_path):
            with open(pending_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    tickers.append(line)
            if 'HWM' not in tickers:
                tickers.append('HWM')

        for ticker in sorted(tickers):
            if ticker in all_cfgs:
                continue  # already loaded from settings
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
            sources[ticker] = 'SP500/%s' % best

    # 3. Filter by --ticker
    if only_tickers:
        upper = {t.upper() for t in only_tickers}
        all_cfgs = {k: v for k, v in all_cfgs.items() if k in upper}
        sources = {k: v for k, v in sources.items() if k in upper}

    return all_cfgs, sources


# ── Run all ──────────────────────────────────────────────────────────────────

def run_all(all_cfgs, sources):
    """Run BT for each ticker and collect results."""
    results = {}
    names = sorted(all_cfgs.keys())
    total = len(names)
    for i, name in enumerate(names, 1):
        cfg = all_cfgs[name]
        src = sources.get(name, '?')
        sys.stdout.write('  [%d/%d] %-6s (%s) ...' % (i, total, name, src))
        sys.stdout.flush()
        r = run_bt(name, cfg)
        if 'error' in r:
            print(' ERROR: %s' % r['error'])
        else:
            print(
                ' T=%d PF=%5.2f Shrp=%5.2f DD=%5.2f%% PnL=$%+9.0f Y+=%d/%d'
                % (r['trades'], min(r['pf'], 99), r['sharpe'], r['max_dd'],
                   r['net_pnl'], r['pos_years'], r['total_years'])
            )
            results[name] = r
    return results


# ── Display heatmap ──────────────────────────────────────────────────────────

def display(results, sources):
    """Print unified yearly PnL heatmap with PF + Sharpe columns."""
    if not results:
        print("No results.")
        return

    # Collect all years across all tickers
    all_years = set()
    for r in results.values():
        all_years.update(r['yearly'].keys())
    years = sorted(all_years)

    sep = "=" * (60 + len(years) * 8)
    print()
    print(sep)
    print("ALTAIR FULL HEATMAP -- Yearly PnL + PF + Sharpe (all tickers)")
    print(sep)
    print()

    # Sort by PF descending
    ranked = sorted(results.items(), key=lambda x: x[1]['pf'], reverse=True)

    # Header
    yr_hdr = ''.join('%8d' % y for y in years)
    print(
        '%-6s %-10s %3s  %s %9s  %5s %5s %5s %3s' %
        ('Ticker', 'Source', 'T', yr_hdr, 'TOTAL', 'PF', 'Shrp', 'DD%', 'Y+')
    )
    print('-' * (60 + len(years) * 8))

    for name, r in ranked:
        src = sources.get(name, '?')
        sector = SECTORS.get(name, '')
        # Show config letter for pending
        if '/A' in src or '/B' in src:
            cfg_letter = src.split('/')[1]
            label = '%s %s' % (cfg_letter, sector)
        elif 'active' in src:
            label = sector
        elif 'disabled' in src:
            label = 'OFF/%s' % sector
        else:
            label = sector if sector else src
        if len(label) > 10:
            label = label[:10]
        cols = []
        for y in years:
            yd = r['yearly'].get(y)
            if yd is None:
                cols.append('%8s' % '--')
            else:
                cols.append('%+8.0f' % yd['pnl'])
        yr_str = ''.join(cols)

        pf_str = '%5.2f' % r['pf'] if r['pf'] < 99 else '  INF'
        print(
            '%-6s %-10s %3d  %s %+9.0f  %s %5.2f %5.1f %d/%d' %
            (name, label, r['trades'], yr_str, r['net_pnl'],
             pf_str, r['sharpe'], r['max_dd'],
             r['pos_years'], r['total_years'])
        )

    print('-' * (60 + len(years) * 8))
    print('  %d tickers | Sorted by PF desc' % len(results))

    # Quick stats
    pfs = [r['pf'] for r in results.values() if r['pf'] < 99]
    sharpes = [r['sharpe'] for r in results.values()]
    dds = [r['max_dd'] for r in results.values()]
    profitable = sum(1 for r in results.values() if r['net_pnl'] > 0)
    print()
    print('  Profitable: %d/%d' % (profitable, len(results)))
    print('  PF    median=%.2f  mean=%.2f' % (np.median(pfs), np.mean(pfs)))
    print('  Sharpe median=%.2f  mean=%.2f' % (np.median(sharpes), np.mean(sharpes)))
    print('  DD%%   median=%.1f%%  mean=%.1f%%' % (np.median(dds), np.mean(dds)))
    print()


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="ALTAIR full heatmap -- all tickers, yearly PnL + PF + Sharpe")
    parser.add_argument('--source', choices=['ndx', 'dj30', 'sp500'],
                        help='Filter by source universe')
    parser.add_argument('--ticker', nargs='+',
                        help='Run only specific tickers')
    parser.add_argument('--skip-disabled', action='store_true',
                        help='Skip disabled configs (PF<1 failures)')
    args = parser.parse_args()

    print()
    print("Loading configs...")
    all_cfgs, sources = load_all_configs(
        skip_disabled=args.skip_disabled,
        source_filter=args.source,
        only_tickers=args.ticker,
    )
    print("  %d tickers loaded" % len(all_cfgs))
    print()
    print("Running backtests...")

    results = run_all(all_cfgs, sources)
    display(results, sources)


if __name__ == '__main__':
    main()
