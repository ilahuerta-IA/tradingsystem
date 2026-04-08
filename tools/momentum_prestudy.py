"""
Momentum Regime Pre-Study -- Quantitative validation before strategy coding.

Tests 4 layers of the Momentum Regime hypothesis:
  4.1  TREND:      Does 12M momentum filter improve forward H4 returns?
  4.2  VOLATILITY: Does high ATR regime improve edge & lower Spread/ATR?
  4.3  TIMING:     Which H4 hour slot has the best edge?
  4.4  HOLDING:    Does edge grow (trend) or decay (mean-reversion)?

Axiom 12: pre-study BEFORE writing strategy code.
See context/MOMENTUM_PRESTUDY.md for full design.

Usage:
  python tools/momentum_prestudy.py                    # Full study, all assets
  python tools/momentum_prestudy.py --asset GDAXI      # Single asset
  python tools/momentum_prestudy.py --test trend        # Single test
  python tools/momentum_prestudy.py --test volatility
  python tools/momentum_prestudy.py --test timing
  python tools/momentum_prestudy.py --test holding
  python tools/momentum_prestudy.py --save              # Save CSV to analysis/
"""

import os
import argparse

import pandas as pd
import numpy as np


# ====================================================================
# CONFIG
# ====================================================================

ASSET_FILES = {
    'GDAXI':  ('data/GDAXI_5m_15Yea.csv',  'data/GDAXI_5m_5Yea.csv'),
    'XAUUSD': ('data/XAUUSD_5m_5Yea.csv',),
    'NDX':    ('data/NDX_5m_15Yea.csv',    'data/NDX_5m_5Yea.csv'),
    'UK100':  ('data/UK100_5m_15Yea.csv',  'data/UK100_5m_5Yea.csv'),
    'SP500':  ('data/SP500_5m_15Yea.csv',  'data/SP500_5m_5Yea.csv'),
    'NI225':  ('data/NI225_5m_15Yea.csv',  'data/NI225_5m_5Yea.csv'),
}

# Broker spreads in points
SPREADS = {
    'GDAXI': 2.0, 'XAUUSD': 0.35, 'NDX': 1.8, 'UK100': 1.0,
    'SP500': 0.8, 'NI225': 12.0,
}

# Momentum lookback in trading days
MOM_DAYS = 252

# ATR period for H4
ATR_PERIOD = 24

# Forward bars to test
FORWARD_BARS = [1, 2, 3, 6, 12]

# H4 hours to test (UTC start of each 4h bar)
H4_HOURS = [0, 4, 8, 12, 16, 20]


# ====================================================================
# DATA LOADING
# ====================================================================

def find_data_file(symbol):
    """Find best available data file (prefer longer history)."""
    paths = ASSET_FILES.get(symbol, ())
    for p in paths:
        if os.path.exists(p):
            return p
    return None


def load_data(symbol):
    """Load 5m CSV, resample to H4 and Daily. Returns (h4_df, daily_df)."""
    path = find_data_file(symbol)
    if path is None:
        return None, None

    df = pd.read_csv(path)
    df['datetime'] = pd.to_datetime(
        df['Date'].astype(str) + ' ' + df['Time'])
    df.set_index('datetime', inplace=True)

    # H4 OHLC
    h4 = df.resample('240min').agg({
        'Open': 'first', 'High': 'max',
        'Low': 'min', 'Close': 'last',
    }).dropna()

    # Daily OHLC
    daily = df.resample('D').agg({
        'Open': 'first', 'High': 'max',
        'Low': 'min', 'Close': 'last',
    }).dropna()

    return h4, daily


def compute_atr(ohlc, period=ATR_PERIOD):
    """Compute ATR series."""
    prev_c = ohlc['Close'].shift(1)
    tr = np.maximum(
        ohlc['High'] - ohlc['Low'],
        np.maximum(
            abs(ohlc['High'] - prev_c),
            abs(ohlc['Low'] - prev_c)))
    return tr.rolling(period).mean()


def compute_momentum_12m(daily):
    """Compute 12-month absolute momentum: price_today / price_252d_ago - 1."""
    return daily['Close'] / daily['Close'].shift(MOM_DAYS) - 1


# ====================================================================
# TEST 4.1: TREND -- Does 12M momentum filter improve H4 returns?
# ====================================================================

def test_trend(h4, daily, symbol):
    """
    Test if Momentum 12M > 0 filter improves forward H4 returns.
    Returns dict with results.
    """
    mom = compute_momentum_12m(daily)
    atr_h4 = compute_atr(h4)

    # Map daily momentum to H4 bars (use previous day's momentum)
    mom_daily = mom.shift(1)  # avoid look-ahead: use yesterday's mom
    h4_dates = h4.index.date
    mom_map = mom_daily.to_dict()

    h4_mom = pd.Series(index=h4.index, dtype=float)
    for i, idx in enumerate(h4.index):
        d = idx.date()
        # Find the most recent daily momentum value
        if pd.Timestamp(d) in mom_daily.index:
            h4_mom.iloc[i] = mom_daily.loc[pd.Timestamp(d)]

    # Forward fill missing
    h4_mom = h4_mom.ffill()

    # Forward returns (ATR-normalized)
    results = []
    for fwd in FORWARD_BARS:
        fwd_ret = (h4['Close'].shift(-fwd) - h4['Close']) / atr_h4

        # All bars (baseline)
        all_ret = fwd_ret.dropna()
        n_all = len(all_ret)
        edge_all = all_ret.mean() if n_all > 50 else np.nan
        wr_all = (all_ret > 0).mean() * 100 if n_all > 50 else np.nan

        # LONG regime only (mom > 0) -- long trades only
        long_mask = h4_mom > 0
        long_ret = fwd_ret[long_mask].dropna()
        n_long = len(long_ret)
        edge_long = long_ret.mean() if n_long > 50 else np.nan
        wr_long = (long_ret > 0).mean() * 100 if n_long > 50 else np.nan

        # SHORT regime only (mom < 0) -- short trades only (invert return)
        short_mask = h4_mom < 0
        short_ret = -fwd_ret[short_mask].dropna()
        n_short = len(short_ret)
        edge_short = short_ret.mean() if n_short > 50 else np.nan
        wr_short = (short_ret > 0).mean() * 100 if n_short > 50 else np.nan

        # Combined: long in LONG regime + short in SHORT regime
        combined = pd.concat([
            fwd_ret[long_mask],
            -fwd_ret[short_mask]
        ]).dropna()
        n_comb = len(combined)
        edge_comb = combined.mean() if n_comb > 50 else np.nan
        wr_comb = (combined > 0).mean() * 100 if n_comb > 50 else np.nan

        results.append({
            'symbol': symbol, 'fwd': fwd,
            'n_all': n_all, 'edge_all': edge_all, 'wr_all': wr_all,
            'n_long': n_long, 'edge_long': edge_long, 'wr_long': wr_long,
            'n_short': n_short, 'edge_short': edge_short, 'wr_short': wr_short,
            'n_combined': n_comb, 'edge_combined': edge_comb, 'wr_combined': wr_comb,
            'pct_long': long_mask.sum() / len(h4_mom.dropna()) * 100,
            'pct_short': short_mask.sum() / len(h4_mom.dropna()) * 100,
        })

    # Yearly breakdown (fwd=1, combined)
    combined_series = pd.concat([
        fwd_ret[long_mask].rename('ret'),
        (-fwd_ret[short_mask]).rename('ret')
    ])
    fwd1 = (h4['Close'].shift(-1) - h4['Close']) / atr_h4
    yearly = {}
    for yr in sorted(set(h4.index.year)):
        yr_mask_long = long_mask & (h4.index.year == yr)
        yr_mask_short = short_mask & (h4.index.year == yr)
        yr_ret = pd.concat([
            fwd1[yr_mask_long], -fwd1[yr_mask_short]
        ]).dropna()
        if len(yr_ret) >= 10:
            yearly[yr] = {
                'n': len(yr_ret),
                'edge': yr_ret.mean(),
                'wr': (yr_ret > 0).mean() * 100,
            }

    return results, yearly


# ====================================================================
# TEST 4.2: VOLATILITY -- Does high ATR improve edge?
# ====================================================================

def test_volatility(h4, daily, symbol):
    """
    Test if high ATR regime improves edge and lowers Spread/ATR.
    """
    atr_h4 = compute_atr(h4)
    mom = compute_momentum_12m(daily)

    # ATR ratio: current ATR vs rolling 250-bar mean
    atr_mean_rolling = atr_h4.rolling(250).mean()
    atr_ratio = atr_h4 / atr_mean_rolling

    # Map momentum to H4
    mom_daily = mom.shift(1)
    h4_mom = pd.Series(index=h4.index, dtype=float)
    for idx in h4.index:
        d = pd.Timestamp(idx.date())
        if d in mom_daily.index:
            h4_mom.loc[idx] = mom_daily.loc[d]
    h4_mom = h4_mom.ffill()

    # Regime masks
    long_mask = h4_mom > 0
    short_mask = h4_mom < 0

    # Spread/ATR dynamic
    spread = SPREADS.get(symbol, 0)
    sprd_atr = spread / atr_h4 * 100

    # Forward return (fwd=1, ATR-normalized)
    fwd1 = (h4['Close'].shift(-1) - h4['Close']) / atr_h4

    # Combined directional return
    dir_ret = fwd1.copy()
    dir_ret[short_mask] = -fwd1[short_mask]
    dir_ret[~(long_mask | short_mask)] = np.nan

    vol_thresholds = [0.8, 1.0, 1.2, 1.5, 2.0]
    results = []

    for vt in vol_thresholds:
        high_vol = atr_ratio > vt
        mask = high_vol & (long_mask | short_mask)
        ret = dir_ret[mask].dropna()

        sa = sprd_atr[high_vol].dropna()

        n = len(ret)
        results.append({
            'symbol': symbol,
            'atr_threshold': vt,
            'n_bars': n,
            'pct_time': high_vol.sum() / len(atr_ratio.dropna()) * 100,
            'edge': ret.mean() if n > 50 else np.nan,
            'wr': (ret > 0).mean() * 100 if n > 50 else np.nan,
            'sprd_atr_mean': sa.mean() if len(sa) > 0 else np.nan,
            'sprd_atr_p50': sa.median() if len(sa) > 0 else np.nan,
        })

    return results


# ====================================================================
# TEST 4.3: TIMING -- Which H4 hour is best?
# ====================================================================

def test_timing(h4, daily, symbol):
    """
    Test which H4 hour slot has the best forward edge.
    Filtered by momentum regime (Capa 1).
    """
    atr_h4 = compute_atr(h4)
    mom = compute_momentum_12m(daily)

    # Map momentum to H4
    mom_daily = mom.shift(1)
    h4_mom = pd.Series(index=h4.index, dtype=float)
    for idx in h4.index:
        d = pd.Timestamp(idx.date())
        if d in mom_daily.index:
            h4_mom.loc[idx] = mom_daily.loc[d]
    h4_mom = h4_mom.ffill()

    long_mask = h4_mom > 0
    short_mask = h4_mom < 0

    fwd1 = (h4['Close'].shift(-1) - h4['Close']) / atr_h4

    # Directional return
    dir_ret = fwd1.copy()
    dir_ret[short_mask] = -fwd1[short_mask]
    dir_ret[~(long_mask | short_mask)] = np.nan

    results = []
    for hour in H4_HOURS:
        hour_mask = h4.index.hour == hour
        mask = hour_mask & (long_mask | short_mask)
        ret = dir_ret[mask].dropna()
        n = len(ret)

        # Yearly consistency
        positive_years = 0
        total_years = 0
        for yr in sorted(set(h4.index.year)):
            yr_mask = mask & (h4.index.year == yr)
            yr_ret = dir_ret[yr_mask].dropna()
            if len(yr_ret) >= 5:
                total_years += 1
                if yr_ret.mean() > 0:
                    positive_years += 1

        results.append({
            'symbol': symbol,
            'hour_utc': hour,
            'n': n,
            'edge': ret.mean() if n > 30 else np.nan,
            'wr': (ret > 0).mean() * 100 if n > 30 else np.nan,
            'score': ret.mean() * np.sqrt(n) if n > 30 else np.nan,
            'years_pos': positive_years,
            'years_total': total_years,
        })

    return results


# ====================================================================
# TEST 4.4: HOLDING -- Does edge grow or decay?
# ====================================================================

def test_holding(h4, daily, symbol):
    """
    Test forward returns at 1,2,3,6,12 bars to determine holding profile.
    """
    atr_h4 = compute_atr(h4)
    mom = compute_momentum_12m(daily)

    # Map momentum to H4
    mom_daily = mom.shift(1)
    h4_mom = pd.Series(index=h4.index, dtype=float)
    for idx in h4.index:
        d = pd.Timestamp(idx.date())
        if d in mom_daily.index:
            h4_mom.loc[idx] = mom_daily.loc[d]
    h4_mom = h4_mom.ffill()

    long_mask = h4_mom > 0
    short_mask = h4_mom < 0

    results = []
    for fwd in FORWARD_BARS:
        fwd_ret = (h4['Close'].shift(-fwd) - h4['Close']) / atr_h4

        # Combined directional
        dir_ret = fwd_ret.copy()
        dir_ret[short_mask] = -fwd_ret[short_mask]
        dir_ret[~(long_mask | short_mask)] = np.nan

        ret = dir_ret.dropna()
        n = len(ret)

        results.append({
            'symbol': symbol,
            'fwd_bars': fwd,
            'fwd_hours': fwd * 4,
            'n': n,
            'edge': ret.mean() if n > 50 else np.nan,
            'wr': (ret > 0).mean() * 100 if n > 50 else np.nan,
            'edge_per_bar': (ret.mean() / fwd) if n > 50 else np.nan,
        })

    return results


# ====================================================================
# REPORTS
# ====================================================================

def print_trend_report(all_results, all_yearly):
    """Print Test 4.1 report."""
    print()
    print("=" * 90)
    print("TEST 4.1: TREND -- Does 12M Momentum filter improve H4 forward returns?")
    print("=" * 90)
    print()

    for symbol in sorted(set(r['symbol'] for r in all_results)):
        sym_res = [r for r in all_results if r['symbol'] == symbol]
        r1 = sym_res[0]
        print(f"  {symbol}  (mom>0: {r1['pct_long']:.1f}% of time | "
              f"mom<0: {r1['pct_short']:.1f}%)")

        print(f"  {'fwd':>4} | {'--- Baseline ---':^20} | "
              f"{'---- LONG regime ---':^22} | "
              f"{'--- SHORT regime ---':^22} | "
              f"{'--- COMBINED ---':^20}")
        print(f"  {'bars':>4} | {'N':>6} {'Edge':>7} {'WR%':>6} | "
              f"{'N':>6} {'Edge':>7} {'WR%':>6} {'vs base':>8} | "
              f"{'N':>6} {'Edge':>7} {'WR%':>6} {'vs base':>8} | "
              f"{'N':>6} {'Edge':>7} {'WR%':>6}")
        print(f"  {'-'*86}")

        for r in sym_res:
            def fmt(v):
                return f"{v:>7.4f}" if not np.isnan(v) else "    N/A"
            def fmtp(v):
                return f"{v:>5.1f}%" if not np.isnan(v) else "   N/A"

            # Improvement vs baseline
            imp_l = ""
            if not np.isnan(r['edge_long']) and not np.isnan(r['edge_all']):
                if r['edge_all'] != 0:
                    imp_l = f"{(r['edge_long']/r['edge_all']-1)*100:>+6.0f}%"
                else:
                    imp_l = f"  {'INF':>5}"
            imp_s = ""
            if not np.isnan(r['edge_short']) and not np.isnan(r['edge_all']):
                if r['edge_all'] != 0:
                    imp_s = f"{(r['edge_short']/abs(r['edge_all'])):>+6.1f}x"

            print(f"  {r['fwd']:>4} | {r['n_all']:>6} {fmt(r['edge_all'])} "
                  f"{fmtp(r['wr_all'])} | "
                  f"{r['n_long']:>6} {fmt(r['edge_long'])} "
                  f"{fmtp(r['wr_long'])} {imp_l:>8} | "
                  f"{r['n_short']:>6} {fmt(r['edge_short'])} "
                  f"{fmtp(r['wr_short'])} {'':<8} | "
                  f"{r['n_combined']:>6} {fmt(r['edge_combined'])} "
                  f"{fmtp(r['wr_combined'])}")

        # Yearly
        if symbol in all_yearly:
            yearly = all_yearly[symbol]
            if yearly:
                pos = sum(1 for y in yearly.values() if y['edge'] > 0)
                print(f"\n  Yearly (fwd=1, combined): "
                      f"{pos}/{len(yearly)} positive years")
                print(f"  {'Year':<6} {'N':>5} {'Edge':>8} {'WR%':>6}")
                for yr in sorted(yearly.keys()):
                    y = yearly[yr]
                    m = '+' if y['edge'] > 0 else '-'
                    print(f"  {yr:<6} {y['n']:>5} {y['edge']:>8.4f} "
                          f"{y['wr']:>5.1f}% {m}")
        print()


def print_volatility_report(all_results):
    """Print Test 4.2 report."""
    print()
    print("=" * 90)
    print("TEST 4.2: VOLATILITY -- Does high ATR regime improve edge?")
    print("  atr_ratio = ATR_24 / ATR_24_rolling_250  (>1 = above-average vol)")
    print("=" * 90)

    for symbol in sorted(set(r['symbol'] for r in all_results)):
        sym_res = [r for r in all_results if r['symbol'] == symbol]
        print(f"\n  {symbol}  (spread = {SPREADS.get(symbol, 0)} pts)")
        print(f"  {'ATR>':>6} {'%time':>6} {'N':>7} {'Edge':>8} "
              f"{'WR%':>6} {'S/A mean':>9} {'S/A med':>9}")
        print(f"  {'-'*60}")

        for r in sym_res:
            def fmt(v):
                return f"{v:>8.4f}" if pd.notna(v) else "     N/A"
            def fmtp(v):
                return f"{v:>5.1f}%" if pd.notna(v) else "   N/A"
            def fmtsa(v):
                return f"{v:>7.2f}%" if pd.notna(v) else "     N/A"

            print(f"  {r['atr_threshold']:>5.1f}x {r['pct_time']:>5.1f}% "
                  f"{r['n_bars']:>7} {fmt(r['edge'])} {fmtp(r['wr'])} "
                  f" {fmtsa(r['sprd_atr_mean'])} {fmtsa(r['sprd_atr_p50'])}")
    print()


def print_timing_report(all_results):
    """Print Test 4.3 report."""
    print()
    print("=" * 90)
    print("TEST 4.3: TIMING -- Which H4 hour slot is best? (filtered by Mom12 regime)")
    print("=" * 90)

    for symbol in sorted(set(r['symbol'] for r in all_results)):
        sym_res = sorted(
            [r for r in all_results if r['symbol'] == symbol],
            key=lambda x: -(x['score'] if pd.notna(x.get('score')) else -999))
        print(f"\n  {symbol}")
        print(f"  {'Hour':>6} {'N':>6} {'Edge':>8} {'WR%':>6} "
              f"{'Score':>8} {'Yr+/Tot':>8}")
        print(f"  {'-'*50}")

        for r in sym_res:
            def fmt(v):
                return f"{v:>8.4f}" if pd.notna(v) else "     N/A"
            def fmtp(v):
                return f"{v:>5.1f}%" if pd.notna(v) else "   N/A"

            yr_str = (f"{r['years_pos']}/{r['years_total']}"
                      if r['years_total'] > 0 else "N/A")
            score_str = (f"{r['score']:>8.2f}"
                         if pd.notna(r.get('score')) else "     N/A")
            print(f"  {r['hour_utc']:>4}:00 {r['n']:>6} {fmt(r['edge'])} "
                  f"{fmtp(r['wr'])} {score_str} {yr_str:>8}")
    print()


def print_holding_report(all_results):
    """Print Test 4.4 report."""
    print()
    print("=" * 90)
    print("TEST 4.4: HOLDING -- Does edge grow (trend) or decay (mean-reversion)?")
    print("  Filtered by Mom12 regime. Edge = ATR-normalized directional return.")
    print("=" * 90)

    for symbol in sorted(set(r['symbol'] for r in all_results)):
        sym_res = [r for r in all_results if r['symbol'] == symbol]
        print(f"\n  {symbol}")
        print(f"  {'fwd':>4} {'hours':>6} {'N':>7} {'Edge':>8} "
              f"{'WR%':>6} {'Edge/bar':>9} {'Profile':>10}")
        print(f"  {'-'*55}")

        edges = [(r['fwd_bars'], r.get('edge', np.nan)) for r in sym_res]
        for r in sym_res:
            def fmt(v):
                return f"{v:>8.4f}" if pd.notna(v) else "     N/A"
            def fmtp(v):
                return f"{v:>5.1f}%" if pd.notna(v) else "   N/A"

            # Determine profile
            profile = ""
            if r['fwd_bars'] == max(FORWARD_BARS) and pd.notna(r.get('edge')):
                e1 = next(
                    (x[1] for x in edges if x[0] == 1), np.nan)
                e_last = r['edge']
                if pd.notna(e1) and pd.notna(e_last):
                    if e_last > e1 * 1.5:
                        profile = "TREND ↗"
                    elif e_last < e1 * 0.5:
                        profile = "DECAY ↘"
                    else:
                        profile = "FLAT →"

            print(f"  {r['fwd_bars']:>4} {r['fwd_hours']:>5}h {r['n']:>7} "
                  f"{fmt(r['edge'])} {fmtp(r['wr'])} "
                  f"{fmt(r['edge_per_bar'])} {profile:>10}")
    print()


def print_summary(trend_res, vol_res, timing_res, holding_res):
    """Print global pass/fail summary."""
    print()
    print("=" * 90)
    print("GLOBAL SUMMARY -- Pass/Fail by Asset")
    print("=" * 90)
    print()

    symbols = sorted(set(r['symbol'] for r in trend_res))
    print(f"  {'Asset':<8} {'Trend':^12} {'Volatility':^12} "
          f"{'Timing':^12} {'Holding':^12} {'OVERALL':^10}")
    print(f"  {'-'*70}")

    for sym in symbols:
        # Trend: combined edge_fwd1 > 0.01
        t_res = [r for r in trend_res
                 if r['symbol'] == sym and r['fwd'] == 1]
        t_edge = t_res[0]['edge_combined'] if t_res else np.nan
        t_pass = pd.notna(t_edge) and t_edge > 0.01

        # Volatility: best threshold with edge > 0.01 and S/A < 2%
        v_res = [r for r in vol_res if r['symbol'] == sym]
        v_pass = any(
            pd.notna(r['edge']) and r['edge'] > 0.01
            and pd.notna(r['sprd_atr_mean']) and r['sprd_atr_mean'] < 2.0
            for r in v_res)

        # Timing: best hour Score > 1.0 and >=60% years positive
        ti_res = [r for r in timing_res if r['symbol'] == sym]
        ti_pass = any(
            pd.notna(r.get('score')) and r['score'] > 1.0
            and r['years_total'] > 0
            and r['years_pos'] / r['years_total'] >= 0.6
            for r in ti_res)

        # Holding: edge grows or stays (not decay)
        h_res = [r for r in holding_res if r['symbol'] == sym]
        e1 = next((r['edge'] for r in h_res if r['fwd_bars'] == 1), np.nan)
        e12 = next(
            (r['edge'] for r in h_res
             if r['fwd_bars'] == max(FORWARD_BARS)), np.nan)
        h_pass = (pd.notna(e1) and pd.notna(e12)
                  and e12 >= e1 * 0.5 and e1 > 0)

        overall = t_pass and v_pass and ti_pass and h_pass

        def mark(v):
            return "✅ PASS" if v else "❌ FAIL"

        print(f"  {sym:<8} {mark(t_pass):^12} {mark(v_pass):^12} "
              f"{mark(ti_pass):^12} {mark(h_pass):^12} "
              f"{'✅ GO' if overall else '❌ NO':^10}")

    print()
    print("  Criteria:")
    print("    Trend:      Combined edge (fwd=1) > 0.01 ATR")
    print("    Volatility: Edge > 0.01 with S/A < 2% at some ATR threshold")
    print("    Timing:     Best hour Score > 1.0 and >=60% years positive")
    print("    Holding:    Edge doesn't decay >50% from fwd=1 to fwd=max")
    print()
    print("  AXIOM 12: Only proceed to strategy if asset passes ALL 4 tests")
    print("=" * 90)


# ====================================================================
# MAIN
# ====================================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description='Momentum Regime Pre-Study (Axiom 12)')
    parser.add_argument('--asset', type=str, default=None,
                        help='Specific asset (default: all candidates)')
    parser.add_argument('--test', type=str, default=None,
                        choices=['trend', 'volatility', 'timing', 'holding'],
                        help='Run specific test only')
    parser.add_argument('--save', action='store_true',
                        help='Save results to analysis/')
    return parser.parse_args()


def main():
    args = parse_args()
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # Select assets
    if args.asset:
        assets = [args.asset.upper()]
    else:
        assets = list(ASSET_FILES.keys())

    tests = (['trend', 'volatility', 'timing', 'holding']
             if args.test is None else [args.test])

    print("=" * 90)
    print("MOMENTUM REGIME PRE-STUDY")
    print("=" * 90)
    print(f"Assets: {', '.join(assets)}")
    print(f"Tests:  {', '.join(tests)}")
    print(f"Mom lookback: {MOM_DAYS} trading days")
    print(f"ATR period: {ATR_PERIOD} bars")
    print(f"Forward bars: {FORWARD_BARS}")
    print()

    # Load data
    print("Loading data...")
    cache = {}
    for sym in assets:
        h4, daily = load_data(sym)
        if h4 is not None:
            cache[sym] = {'h4': h4, 'daily': daily}
            print(f"  {sym}: {len(h4):,} H4 bars, {len(daily):,} daily bars "
                  f"({daily.index[0].date()} to {daily.index[-1].date()})")
        else:
            print(f"  {sym}: NO DATA -- skipping")
    print()

    valid_assets = [a for a in assets if a in cache]
    if not valid_assets:
        print("No data available!")
        return

    # Run tests
    all_trend, all_yearly = [], {}
    all_vol, all_timing, all_holding = [], [], []

    for sym in valid_assets:
        h4 = cache[sym]['h4']
        daily = cache[sym]['daily']

        if 'trend' in tests:
            res, yearly = test_trend(h4, daily, sym)
            all_trend.extend(res)
            all_yearly[sym] = yearly

        if 'volatility' in tests:
            all_vol.extend(test_volatility(h4, daily, sym))

        if 'timing' in tests:
            all_timing.extend(test_timing(h4, daily, sym))

        if 'holding' in tests:
            all_holding.extend(test_holding(h4, daily, sym))

    # Print reports
    if all_trend:
        print_trend_report(all_trend, all_yearly)
    if all_vol:
        print_volatility_report(all_vol)
    if all_timing:
        print_timing_report(all_timing)
    if all_holding:
        print_holding_report(all_holding)

    # Global summary (only if all tests ran)
    if all_trend and all_vol and all_timing and all_holding:
        print_summary(all_trend, all_vol, all_timing, all_holding)

    # Save
    if args.save:
        out_dir = 'analysis'
        os.makedirs(out_dir, exist_ok=True)
        if all_trend:
            pd.DataFrame(all_trend).to_csv(
                f'{out_dir}/momentum_trend.csv', index=False)
        if all_vol:
            pd.DataFrame(all_vol).to_csv(
                f'{out_dir}/momentum_volatility.csv', index=False)
        if all_timing:
            pd.DataFrame(all_timing).to_csv(
                f'{out_dir}/momentum_timing.csv', index=False)
        if all_holding:
            pd.DataFrame(all_holding).to_csv(
                f'{out_dir}/momentum_holding.csv', index=False)
        print(f"\nResults saved to {out_dir}/momentum_*.csv")


if __name__ == '__main__':
    main()
