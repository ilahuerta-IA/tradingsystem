"""
Cross-Asset Divergence Study -- Generic tool for ANY asset pair.

Extends divergence_study.py to support cross-asset-class combinations:
indices, gold, bonds, FX. Adds hedged convergence analysis (long B + short A).

Computes:
  1. Z-score spread statistics per session (same as divergence_study.py)
  2. Mean-reversion edge: does traded asset B revert after divergence?
  3. Hedged convergence edge: long B + short A simultaneously
  4. Yearly stability analysis (per-year breakdown)
  5. Bootstrap confidence intervals for Sharpe
  6. Score = edge * sqrt(N) ranking
  7. Spread/ATR cost viability check (Axiom 8)

Usage:
  # Full scan of predefined cross-asset pairs:
  python tools/cross_asset_study.py

  # Specific pair:
  python tools/cross_asset_study.py --ref SP500 --traded XAUUSD

  # Specific pair + session:
  python tools/cross_asset_study.py --ref SP500 --traded XAUUSD --session London

  # Custom timeframe (H1 instead of default H4):
  python tools/cross_asset_study.py --tf H1

  # Only show pairs with Score > threshold:
  python tools/cross_asset_study.py --min-score 1.5

  # Include hedged convergence analysis:
  python tools/cross_asset_study.py --hedge

  # Save results to analysis/ folder:
  python tools/cross_asset_study.py --save
"""

import os
import sys
import argparse
from itertools import product
from collections import defaultdict

import pandas as pd
import numpy as np


# ====================================================================
# ASSET REGISTRY -- add new assets here
# ====================================================================

ASSET_FILES = {
    # CFD Indices (15Y if available, else 5Y)
    'NI225':  ('data/NI225_5m_15Yea.csv',  'data/NI225_5m_5Yea.csv'),
    'GDAXI':  ('data/GDAXI_5m_15Yea.csv',  'data/GDAXI_5m_5Yea.csv'),
    'SP500':  ('data/SP500_5m_15Yea.csv',  'data/SP500_5m_5Yea.csv'),
    'UK100':  ('data/UK100_5m_15Yea.csv',  'data/UK100_5m_5Yea.csv'),
    'NDX':    ('data/NDX_5m_15Yea.csv',    'data/NDX_5m_5Yea.csv'),
    'EUR50':  ('data/EUR50_5m_5Yea.csv',),
    'AUS200': ('data/AUS200_5m_5Yea.csv',),
    # Commodities
    'XAUUSD': ('data/XAUUSD_5m_5Yea.csv',),
    'SLV':    ('data/SLV_5m_5Yea.csv',),
    # Bonds / Fixed Income
    'TLT':    ('data/TLT_5m_5Yea.csv',),
    # FX Majors
    'EURUSD': ('data/EURUSD_5m_5Yea.csv',),
    'USDJPY': ('data/USDJPY_5m_5Yea.csv',),
    'USDCHF': ('data/USDCHF_5m_5Yea.csv',),
    'AUDUSD': ('data/AUDUSD_5m_5Yea.csv',),
    'NZDUSD': ('data/NZDUSD_5m_5Yea.csv',),
    # ETFs
    'GLD':    ('data/GLD_5m_5Yea.csv',),
    'DIA':    ('data/DIA_5m_5Yea.csv',),
    'XLE':    ('data/XLE_5m_5Yea.csv',),
    'EWZ':    ('data/EWZ_5m_5Yea.csv',),
    'XLU':    ('data/XLU_5m_5Yea.csv',),
}

# Asset class metadata: spread in points and typical ATR for cost ratio
# Axiom 8: Spread/ATR(H4) < 2% to trade. Reference assets have no limit.
ASSET_CLASS = {
    # CFD Indices -- spread/ATR from VEGA study
    'NI225':  {'class': 'index',   'spread_atr_pct': 1.73},
    'GDAXI':  {'class': 'index',   'spread_atr_pct': 0.96},
    'SP500':  {'class': 'index',   'spread_atr_pct': 2.10},
    'UK100':  {'class': 'index',   'spread_atr_pct': 2.40},
    'NDX':    {'class': 'index',   'spread_atr_pct': 0.41},
    'EUR50':  {'class': 'index',   'spread_atr_pct': 2.50},
    'AUS200': {'class': 'index',   'spread_atr_pct': 3.00},
    # Gold -- spread ~0.35 pts, ATR(H4) ~25 pts -> ~1.4%
    'XAUUSD': {'class': 'commodity', 'spread_atr_pct': 1.40},
    'SLV':    {'class': 'etf',      'spread_atr_pct': 3.00},
    # Bonds
    'TLT':    {'class': 'etf',      'spread_atr_pct': 2.50},
    # FX -- spread/ATR too high for H4 VEGA-style (>2.4%)
    'EURUSD': {'class': 'fx',       'spread_atr_pct': 3.48},
    'USDJPY': {'class': 'fx',       'spread_atr_pct': 2.41},
    'USDCHF': {'class': 'fx',       'spread_atr_pct': 3.00},
    'AUDUSD': {'class': 'fx',       'spread_atr_pct': 7.54},
    'NZDUSD': {'class': 'fx',       'spread_atr_pct': 5.00},
    # ETFs
    'GLD':    {'class': 'etf',      'spread_atr_pct': 1.80},
    'DIA':    {'class': 'etf',      'spread_atr_pct': 1.50},
    'XLE':    {'class': 'etf',      'spread_atr_pct': 2.00},
    'EWZ':    {'class': 'etf',      'spread_atr_pct': 3.00},
    'XLU':    {'class': 'etf',      'spread_atr_pct': 2.50},
}

# Sessions (UTC winter -- DST shifts -1h in summer)
SESSIONS = {
    'Tokyo':      (0, 5),
    'London':     (7, 12),
    'NY':         (14, 18),
    'LDN_NY':     (13, 16),
    'LBMA_AM':    (10, 12),   # London gold fix AM
    'LBMA_PM':    (14, 16),   # London gold fix PM
}

# Default cross-asset pairs to study (ref -> traded)
# Focus: cross-asset divergence where repricing lag exists
DEFAULT_PAIRS = [
    # Gold vs equity (risk-on / risk-off divergence)
    ('SP500',  'XAUUSD'),
    ('NDX',    'XAUUSD'),
    ('GDAXI',  'XAUUSD'),
    # Gold vs bonds (safe haven divergence)
    ('TLT',    'XAUUSD'),
    ('XAUUSD', 'TLT'),
    # Equity vs bonds (risk-on / risk-off)
    ('SP500',  'TLT'),
    ('TLT',    'SP500'),
    ('NDX',    'TLT'),
    # Index cross (extending VEGA -- reversed pairs not yet tested)
    ('NI225',  'GDAXI'),
    ('UK100',  'NI225'),
    ('EUR50',  'GDAXI'),
    # Gold vs FX (gold/dollar inverse)
    ('XAUUSD', 'USDJPY'),
    ('XAUUSD', 'EURUSD'),
    # Equity vs FX (risk proxy)
    ('SP500',  'USDJPY'),
    ('SP500',  'AUDUSD'),
]

# Z-score params (same as VEGA strategy -- DO NOT OPTIMIZE)
SMA_PERIOD = 24
ATR_PERIOD = 24

# Dead zone thresholds
DZ_THRESHOLDS = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5]

# Forward bars to measure mean-reversion
FORWARD_BARS = [1, 2, 3]

# Minimum data overlap
MIN_OVERLAP_BARS = 300

# Bootstrap config
N_BOOTSTRAP = 1000


# ====================================================================
# DATA LOADING
# ====================================================================

def find_data_file(symbol):
    """Find best available data file for symbol (prefer longer history)."""
    paths = ASSET_FILES.get(symbol)
    if not paths:
        return None
    for p in paths:
        if os.path.exists(p):
            return p
    return None


def load_and_resample(symbol, path, tf_minutes):
    """Load 5m CSV and resample to target timeframe OHLC."""
    df = pd.read_csv(path)
    df['datetime'] = pd.to_datetime(
        df['Date'].astype(str) + ' ' + df['Time'])
    df.set_index('datetime', inplace=True)

    rule = 'D' if tf_minutes >= 1440 else f'{tf_minutes}min'
    resampled = df.resample(rule).agg({
        'Open': 'first',
        'High': 'max',
        'Low': 'min',
        'Close': 'last',
    }).dropna()

    return resampled


def compute_zscore(ohlc, sma_period=SMA_PERIOD, atr_period=ATR_PERIOD):
    """Compute z-score: (Close - SMA) / ATR. Returns z, atr, close."""
    sma = ohlc['Close'].rolling(sma_period).mean()
    prev_close = ohlc['Close'].shift(1)
    tr = np.maximum(
        ohlc['High'] - ohlc['Low'],
        np.maximum(
            abs(ohlc['High'] - prev_close),
            abs(ohlc['Low'] - prev_close)
        )
    )
    atr = tr.rolling(atr_period).mean()
    z = (ohlc['Close'] - sma) / atr
    z = z.replace([np.inf, -np.inf], np.nan)
    return z, atr, ohlc['Close']


# ====================================================================
# SESSION FILTER
# ====================================================================

def session_mask(idx, start_h, end_h):
    """Boolean mask for UTC hours in [start_h, end_h)."""
    hours = idx.hour
    if start_h <= end_h:
        return (hours >= start_h) & (hours < end_h)
    else:
        return (hours >= start_h) | (hours < end_h)


# ====================================================================
# CORE STUDY: SINGLE PAIR + SESSION
# ====================================================================

def study_pair(z_a, z_b, close_a, close_b, atr_a, atr_b,
               sym_a, sym_b, session_name, start_h, end_h,
               include_hedge=False):
    """
    Study divergence and mean-reversion for one pair in one session.

    Modes:
      - Standalone (B only): trade B in direction opposite to spread sign
      - Hedged (B-A): long B + short A simultaneously (convergence)

    Returns dict with all metrics, or None if insufficient data.
    """
    common = z_a.dropna().index.intersection(z_b.dropna().index)
    if len(common) < MIN_OVERLAP_BARS:
        return None

    spread = z_a.loc[common] - z_b.loc[common]
    cl_a = close_a.loc[common]
    cl_b = close_b.loc[common]
    at_a = atr_a.loc[common]
    at_b = atr_b.loc[common]

    mask = session_mask(common, start_h, end_h)
    spread_sess = spread[mask]

    if len(spread_sess) < 50:
        return None

    result = {
        'ref': sym_a,
        'traded': sym_b,
        'session': session_name,
        'bars': len(spread_sess),
        'spread_mean': spread_sess.mean(),
        'spread_std': spread_sess.std(),
        'abs_spread_mean': spread_sess.abs().mean(),
        'abs_spread_median': spread_sess.abs().median(),
        'abs_spread_p75': spread_sess.abs().quantile(0.75),
        'abs_spread_p90': spread_sess.abs().quantile(0.90),
    }

    # Frequency above dead zone
    for dz in DZ_THRESHOLDS:
        count = (spread_sess.abs() > dz).sum()
        result[f'freq_dz{dz}'] = count / len(spread_sess) * 100

    # Forward returns (B standalone)
    fwd_ret_b = {}
    for fwd in FORWARD_BARS:
        fwd_ret_b[fwd] = (cl_b.shift(-fwd) - cl_b) / at_b

    # Forward returns (hedged: long B + short A, ATR-normalized)
    fwd_ret_hedge = {}
    if include_hedge:
        for fwd in FORWARD_BARS:
            ret_b = (cl_b.shift(-fwd) - cl_b) / at_b
            ret_a = (cl_a.shift(-fwd) - cl_a) / at_a
            # Hedge: long B + short A -> ret_b - ret_a
            fwd_ret_hedge[fwd] = ret_b - ret_a

    # Edge computation for each DZ x FWD combination
    for dz in DZ_THRESHOLDS:
        long_mask = mask & (spread < -dz)
        short_mask = mask & (spread > dz)

        for fwd in FORWARD_BARS:
            # --- Standalone B ---
            long_ret = fwd_ret_b[fwd][long_mask]
            short_ret = -fwd_ret_b[fwd][short_mask]
            all_ret = pd.concat([long_ret, short_ret]).dropna()
            n = len(all_ret)
            suffix = f'dz{dz}_f{fwd}'

            if n >= 15:
                result[f'edge_{suffix}'] = all_ret.mean()
                result[f'wr_{suffix}'] = (all_ret > 0).mean() * 100
                result[f'n_{suffix}'] = n
            else:
                result[f'edge_{suffix}'] = np.nan
                result[f'wr_{suffix}'] = np.nan
                result[f'n_{suffix}'] = n

            # --- Hedged convergence (B-A) ---
            if include_hedge:
                # Long B + short A when spread > dz (A high, B low)
                # Short B + long A when spread < -dz (A low, B high)
                hedge_long = fwd_ret_hedge[fwd][short_mask]  # spread>0: long B, short A
                hedge_short = -fwd_ret_hedge[fwd][long_mask]  # spread<0: short B, long A
                hedge_all = pd.concat([hedge_long, hedge_short]).dropna()
                hn = len(hedge_all)

                if hn >= 15:
                    result[f'hedge_edge_{suffix}'] = hedge_all.mean()
                    result[f'hedge_wr_{suffix}'] = (hedge_all > 0).mean() * 100
                    result[f'hedge_n_{suffix}'] = hn
                else:
                    result[f'hedge_edge_{suffix}'] = np.nan
                    result[f'hedge_wr_{suffix}'] = np.nan
                    result[f'hedge_n_{suffix}'] = hn

    # Yearly stability (for best DZ/fwd combo -- computed later in ranking)
    return result


def yearly_stability(z_a, z_b, close_b, atr_b, mask_func,
                     dz, fwd):
    """Compute per-year edge for a specific pair/session/DZ/fwd."""
    common = z_a.dropna().index.intersection(z_b.dropna().index)
    spread = z_a.loc[common] - z_b.loc[common]
    cl_b = close_b.loc[common]
    at_b = atr_b.loc[common]
    mask = mask_func(common)
    fwd_ret = (cl_b.shift(-fwd) - cl_b) / at_b

    years = sorted(set(common.year))
    yearly = {}
    for yr in years:
        yr_mask = mask & (common.year == yr)
        long_mask = yr_mask & (spread < -dz)
        short_mask = yr_mask & (spread > dz)

        long_ret = fwd_ret[long_mask]
        short_ret = -fwd_ret[short_mask]
        all_ret = pd.concat([long_ret, short_ret]).dropna()

        if len(all_ret) >= 5:
            yearly[yr] = {
                'n': len(all_ret),
                'edge': all_ret.mean(),
                'wr': (all_ret > 0).mean() * 100,
            }
    return yearly


def bootstrap_sharpe_ci(returns, n_boot=N_BOOTSTRAP):
    """Bootstrap 95% CI for Sharpe-like metric (mean/std)."""
    if len(returns) < 20:
        return (np.nan, np.nan)
    returns = returns.dropna().values
    sharpes = []
    for _ in range(n_boot):
        sample = np.random.choice(returns, size=len(returns), replace=True)
        s = np.std(sample)
        if s > 0:
            sharpes.append(np.mean(sample) / s * np.sqrt(len(sample)))
    if not sharpes:
        return (np.nan, np.nan)
    return (np.percentile(sharpes, 2.5), np.percentile(sharpes, 97.5))


# ====================================================================
# MAIN
# ====================================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description='Cross-Asset Divergence Study (generic)')
    parser.add_argument('--ref', type=str, default=None,
                        help='Reference asset (e.g. SP500)')
    parser.add_argument('--traded', type=str, default=None,
                        help='Traded asset (e.g. XAUUSD)')
    parser.add_argument('--session', type=str, default=None,
                        help='Specific session (e.g. London)')
    parser.add_argument('--tf', type=str, default='H4',
                        choices=['H1', 'H4', 'D1'],
                        help='Timeframe (default: H4, D1=Daily)')
    parser.add_argument('--min-score', type=float, default=0.0,
                        help='Minimum Score to display (default: 0)')
    parser.add_argument('--hedge', action='store_true',
                        help='Include hedged convergence analysis')
    parser.add_argument('--yearly', action='store_true',
                        help='Show yearly stability for top candidates')
    parser.add_argument('--save', action='store_true',
                        help='Save results to analysis/ folder')
    parser.add_argument('--dz', type=float, default=None,
                        help='Single dead zone to test (default: all)')
    parser.add_argument('--top', type=int, default=20,
                        help='Number of top candidates to show (default: 20)')
    return parser.parse_args()


def main():
    args = parse_args()
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    tf_minutes = {'H1': 60, 'H4': 240, 'D1': 1440}[args.tf]
    tf_label = args.tf

    print("=" * 80)
    print(f"CROSS-ASSET DIVERGENCE STUDY ({tf_label})")
    print("=" * 80)
    print(f"Z-score: SMA={SMA_PERIOD}, ATR={ATR_PERIOD}")
    print(f"Timeframe: {tf_label} ({tf_minutes}m bars)")
    print(f"Sessions: {list(SESSIONS.keys())}")
    print(f"Dead Zones: {DZ_THRESHOLDS}")
    print(f"Hedge mode: {'ON' if args.hedge else 'OFF'}")
    print()

    # Build pairs list
    if args.ref and args.traded:
        pairs = [(args.ref.upper(), args.traded.upper())]
    elif args.ref:
        # All pairs with this reference
        pairs = [(args.ref.upper(), t)
                 for t in ASSET_FILES if t != args.ref.upper()]
    elif args.traded:
        # All references for this traded asset
        pairs = [(r, args.traded.upper())
                 for r in ASSET_FILES if r != args.traded.upper()]
    else:
        pairs = DEFAULT_PAIRS

    # Filter sessions
    # D1 bars have no intraday hour => use AllDay (full 0-24h mask)
    if tf_minutes >= 1440:
        sessions = {'AllDay': (0, 24)}
    elif args.session:
        sessions = {args.session: SESSIONS[args.session]}
    else:
        sessions = SESSIONS

    # Filter dead zones
    dz_list = [args.dz] if args.dz is not None else list(DZ_THRESHOLDS)

    # Load data
    print("Loading data...")
    cache = {}
    needed_syms = set()
    for ref, traded in pairs:
        needed_syms.add(ref)
        needed_syms.add(traded)

    for sym in sorted(needed_syms):
        path = find_data_file(sym)
        if path is None:
            print(f"  WARNING: no data file for {sym}, skipping")
            continue
        ohlc = load_and_resample(sym, path, tf_minutes)
        z, atr, close = compute_zscore(ohlc)
        cache[sym] = {'z': z, 'atr': atr, 'close': close, 'ohlc': ohlc}
        print(f"  {sym}: {len(ohlc):,} {tf_label} bars "
              f"({ohlc.index[0].date()} to {ohlc.index[-1].date()})")
    print()

    # Run study
    results = []
    valid_pairs = [(r, t) for r, t in pairs
                   if r in cache and t in cache]

    print(f"Pairs to study: {len(valid_pairs)}")
    for ref, traded in valid_pairs:
        sa = ASSET_CLASS.get(traded, {}).get('spread_atr_pct', 99)
        print(f"  {ref} -> {traded} (spread/ATR={sa:.2f}%)")
    print()

    for (ref, traded), (sess_name, (sh, eh)) in product(
            valid_pairs, sessions.items()):
        r = study_pair(
            cache[ref]['z'], cache[traded]['z'],
            cache[ref]['close'], cache[traded]['close'],
            cache[ref]['atr'], cache[traded]['atr'],
            ref, traded, sess_name, sh, eh,
            include_hedge=args.hedge)
        if r:
            results.append(r)

    if not results:
        print("No results! Check data availability.")
        return

    df = pd.DataFrame(results)

    # ================================================================
    # REPORT 1: Divergence amplitude
    # ================================================================
    print()
    print("=" * 80)
    print("REPORT 1: DIVERGENCE AMPLITUDE (|z_A - z_B|) BY PAIR x SESSION")
    print("=" * 80)
    print(f"{'Ref':>7} -> {'Traded':<7} {'Session':<10} "
          f"{'Bars':>6} {'|Sprd|':>7} {'Med':>7} {'P75':>7} {'P90':>7} "
          f"{'%>2.0':>6} {'%>3.0':>6}")
    print("-" * 80)
    for _, row in df.sort_values(
            ['traded', 'abs_spread_mean'], ascending=[True, False]).iterrows():
        print(f"{row['ref']:>7} -> {row['traded']:<7} "
              f"{row['session']:<10} "
              f"{row['bars']:>6} {row['abs_spread_mean']:>7.3f} "
              f"{row['abs_spread_median']:>7.3f} "
              f"{row['abs_spread_p75']:>7.3f} "
              f"{row['abs_spread_p90']:>7.3f} "
              f"{row.get('freq_dz2.0', 0):>5.1f}% "
              f"{row.get('freq_dz3.0', 0):>5.1f}%")

    # ================================================================
    # REPORT 2: Edge by DZ (detail)
    # ================================================================
    print()
    print("=" * 80)
    print("REPORT 2: MEAN-REVERSION EDGE (B standalone, ATR-normalized)")
    print("  Positive edge = signal profitable on average")
    print("=" * 80)

    for dz in [2.0, 3.0]:
        col_n = f'n_dz{dz}_f1'
        if col_n not in df.columns:
            continue
        print(f"\n--- Dead Zone = {dz} ---")
        print(f"{'Ref':>7} -> {'Traded':<7} {'Session':<10} "
              f"{'N':>5} "
              f"{'Edge1':>7} {'WR1%':>5} "
              f"{'Edge2':>7} {'WR2%':>5} "
              f"{'Edge3':>7} {'WR3%':>5}")
        print("-" * 80)

        sub = df[df[col_n] >= 15].sort_values(
            f'edge_dz{dz}_f1', ascending=False)
        for _, row in sub.iterrows():
            vals = []
            for fwd in FORWARD_BARS:
                e = row.get(f'edge_dz{dz}_f{fwd}', np.nan)
                w = row.get(f'wr_dz{dz}_f{fwd}', np.nan)
                vals.extend([e, w])
            print(f"{row['ref']:>7} -> {row['traded']:<7} "
                  f"{row['session']:<10} "
                  f"{row[col_n]:>5.0f} "
                  f"{vals[0]:>7.4f} {vals[1]:>4.1f}% "
                  f"{vals[2]:>7.4f} {vals[3]:>4.1f}% "
                  f"{vals[4]:>7.4f} {vals[5]:>4.1f}%")

    # ================================================================
    # REPORT 3: TOP candidates by Score
    # ================================================================
    for dz in [3.0, 2.0]:
        col_e = f'edge_dz{dz}_f1'
        col_n = f'n_dz{dz}_f1'
        col_w = f'wr_dz{dz}_f1'
        if col_e not in df.columns:
            continue

        print()
        print("=" * 80)
        print(f"REPORT 3: TOP CANDIDATES (Score = edge * sqrt(N), "
              f"DZ={dz}, fwd=1)")
        print("=" * 80)

        ranked = df[df[col_n] >= 15].copy()
        if len(ranked) == 0:
            print("  No candidates with N >= 15")
            continue

        ranked['score'] = ranked[col_e] * np.sqrt(ranked[col_n])
        ranked = ranked[ranked['score'] > args.min_score]
        ranked = ranked.sort_values('score', ascending=False)

        print(f"{'#':>3} {'Ref':>7} -> {'Traded':<7} {'Session':<10} "
              f"{'N':>5} {'Edge':>7} {'WR%':>5} {'Score':>8} "
              f"{'Sprd/ATR':>8}")
        print("-" * 85)

        for i, (_, row) in enumerate(ranked.head(args.top).iterrows()):
            sa = ASSET_CLASS.get(row['traded'], {}).get(
                'spread_atr_pct', 99)
            viable = 'OK' if sa < 2.0 else 'HIGH' if sa < 3.0 else 'FAIL'
            print(f"{i+1:>3} {row['ref']:>7} -> {row['traded']:<7} "
                  f"{row['session']:<10} "
                  f"{row[col_n]:>5.0f} {row[col_e]:>7.4f} "
                  f"{row[col_w]:>4.1f}% {row['score']:>8.2f} "
                  f"{sa:>6.2f}% [{viable}]")

    # ================================================================
    # REPORT 4: Hedged convergence (if --hedge)
    # ================================================================
    if args.hedge:
        for dz in [3.0, 2.0]:
            col_he = f'hedge_edge_dz{dz}_f1'
            col_hn = f'hedge_n_dz{dz}_f1'
            col_hw = f'hedge_wr_dz{dz}_f1'
            if col_he not in df.columns:
                continue

            print()
            print("=" * 80)
            print(f"REPORT 4: HEDGED CONVERGENCE (long B + short A, "
                  f"DZ={dz}, fwd=1)")
            print("  Positive edge = convergence trade profitable")
            print("=" * 80)

            ranked_h = df[df[col_hn] >= 15].copy()
            if len(ranked_h) == 0:
                print("  No candidates with N >= 15")
                continue

            ranked_h['hedge_score'] = (
                ranked_h[col_he] * np.sqrt(ranked_h[col_hn]))
            ranked_h = ranked_h[ranked_h['hedge_score'] > args.min_score]
            ranked_h = ranked_h.sort_values('hedge_score', ascending=False)

            print(f"{'#':>3} {'Ref':>7} -> {'Traded':<7} {'Session':<10} "
                  f"{'N':>5} {'HEdge':>7} {'HWR%':>5} {'HScore':>8} "
                  f"{'vs Solo':>8}")
            print("-" * 85)

            for i, (_, row) in enumerate(ranked_h.head(args.top).iterrows()):
                solo_e = row.get(f'edge_dz{dz}_f1', 0)
                hedge_e = row[col_he]
                comparison = (f"+{(hedge_e/solo_e-1)*100:.0f}%"
                              if solo_e > 0 and hedge_e > 0
                              else "N/A")
                print(f"{i+1:>3} {row['ref']:>7} -> {row['traded']:<7} "
                      f"{row['session']:<10} "
                      f"{row[col_hn]:>5.0f} {hedge_e:>7.4f} "
                      f"{row[col_hw]:>4.1f}% "
                      f"{row['hedge_score']:>8.2f} "
                      f"{comparison:>8}")

    # ================================================================
    # YEARLY STABILITY (if --yearly, for top 5 candidates)
    # ================================================================
    if args.yearly:
        print()
        print("=" * 80)
        print("YEARLY STABILITY (top 5 candidates, DZ=3.0, fwd=1)")
        print("=" * 80)

        dz = 3.0
        col_e = f'edge_dz{dz}_f1'
        col_n = f'n_dz{dz}_f1'

        ranked_y = df[df[col_n] >= 15].copy()
        if len(ranked_y) > 0:
            ranked_y['score'] = ranked_y[col_e] * np.sqrt(ranked_y[col_n])
            ranked_y = ranked_y.sort_values('score', ascending=False)

            for _, row in ranked_y.head(5).iterrows():
                ref_sym = row['ref']
                trd_sym = row['traded']
                sess = row['session']
                sh, eh = SESSIONS.get(sess, (0, 24)) if sess != 'AllDay' else (0, 24)

                def make_mask(idx, _sh=sh, _eh=eh):
                    return session_mask(idx, _sh, _eh)

                ys = yearly_stability(
                    cache[ref_sym]['z'], cache[trd_sym]['z'],
                    cache[trd_sym]['close'], cache[trd_sym]['atr'],
                    make_mask, dz, 1)

                print(f"\n  {ref_sym} -> {trd_sym} ({sess}) "
                      f"Score={row['score']:.2f}")
                positive_years = sum(
                    1 for y in ys.values() if y['edge'] > 0)
                print(f"  Years: {len(ys)} | "
                      f"Positive: {positive_years}/{len(ys)}")
                print(f"  {'Year':<6} {'N':>5} {'Edge':>8} {'WR%':>6}")
                for yr in sorted(ys.keys()):
                    y = ys[yr]
                    marker = '+' if y['edge'] > 0 else '-'
                    print(f"  {yr:<6} {y['n']:>5} "
                          f"{y['edge']:>8.4f} {y['wr']:>5.1f}% {marker}")

    # ================================================================
    # SAVE (if --save)
    # ================================================================
    if args.save:
        out_dir = 'analysis'
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(
            out_dir, f'cross_asset_study_{tf_label}.csv')
        df.to_csv(out_path, index=False, float_format='%.6f')
        print(f"\nResults saved to {out_path}")

    # ================================================================
    # SUMMARY
    # ================================================================
    print()
    print("=" * 80)
    print("INTERPRETATION GUIDE")
    print("=" * 80)
    print("- Edge > 0.05:  viable after costs (if Spread/ATR < 2%)")
    print("- WR% > 53%:    statistically meaningful")
    print("- Score > 2.0:  strong candidate (VEGA empirical: >= 2.0 = pass)")
    print("- Score < 2.0:  weak -- 0/4 passed BT in VEGA history")
    print("- Spread/ATR:   OK (<2%), HIGH (2-3%), FAIL (>3%)")
    print("- Hedge mode:   reduces DD but may reduce edge too")
    print("- Next step:    Score >= 2.0 + Spread/ATR OK -> implement in BT")
    print("=" * 80)
    print()
    print("AXIOM 12 REMINDER: Do NOT implement strategy without Score >= 2.0")
    print("AXIOM 8 REMINDER:  Do NOT trade assets with Spread/ATR > 2%")


if __name__ == '__main__':
    main()
