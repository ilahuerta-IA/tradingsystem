"""
Momentum-Quality Divergence Study (NOVA Fase 0)

Tests whether Clenow momentum quality (annualized slope * R^2)
amplifies H4 mean-reversion edge.

Two study modes:
  A) Self-reversion: asset z-score dip below own H4 mean.
     Does reversion edge increase when daily momentum is high?
  B) VEGA-filtered: cross-asset spread (validated VEGA pairs).
     Does traded asset momentum improve VEGA signal quality?

Parameters from literature (NOT optimized):
  - Z-score: SMA=24, ATR=24 (VEGA identical, = 1 trading day H4)
  - Momentum: slope*R^2, lookback=90d (Clenow, Stocks on the Move)
  - Dead Zones: 2.0, 3.0 (VEGA validated range)

Usage:
  # Full study (tradeable assets + VEGA pairs):
  python tools/nova_momentum_study.py

  # Specific asset:
  python tools/nova_momentum_study.py --asset GDAXI

  # Specific session:
  python tools/nova_momentum_study.py --session London

  # Include yearly stability + save CSV:
  python tools/nova_momentum_study.py --yearly --save

  # Only self-reversion or only VEGA:
  python tools/nova_momentum_study.py --self-only
  python tools/nova_momentum_study.py --vega-only
"""

import os
import sys
import argparse
from math import erfc, sqrt as msqrt
from collections import defaultdict

import numpy as np
import pandas as pd


# ====================================================================
# CONFIGURATION
# ====================================================================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')

ASSET_FILES = {
    'NI225':  ('NI225_5m_15Yea.csv', 'NI225_5m_5Yea.csv'),
    'GDAXI':  ('GDAXI_5m_15Yea.csv', 'GDAXI_5m_5Yea.csv'),
    'SP500':  ('SP500_5m_15Yea.csv', 'SP500_5m_5Yea.csv'),
    'UK100':  ('UK100_5m_15Yea.csv', 'UK100_5m_5Yea.csv'),
    'NDX':    ('NDX_5m_15Yea.csv',   'NDX_5m_5Yea.csv'),
    'EUR50':  ('EUR50_5m_5Yea.csv',),
    'XAUUSD': ('XAUUSD_5m_5Yea.csv',),
    'TLT':    ('TLT_5m_5Yea.csv',),
    'EURUSD': ('EURUSD_5m_5Yea.csv',),
    'USDJPY': ('USDJPY_5m_5Yea.csv',),
    'AUDUSD': ('AUDUSD_5m_5Yea.csv',),
}

SPREAD_ATR_PCT = {
    'GDAXI': 0.96, 'NDX': 0.41, 'NI225': 1.73, 'XAUUSD': 1.40,
    'SP500': 2.10, 'UK100': 2.40, 'EUR50': 2.50, 'TLT': 2.50,
    'EURUSD': 3.48, 'USDJPY': 2.41, 'AUDUSD': 7.54,
}

# Only assets with Spread/ATR < 2% (Axiom 8)
TRADEABLE = ['GDAXI', 'NDX', 'NI225', 'XAUUSD']

SESSIONS = {
    'Tokyo':  (0, 5),
    'London': (7, 12),
    'NY':     (14, 18),
}

# Fixed from VEGA (not optimized)
SMA_PERIOD = 24
ATR_PERIOD = 24

# Fixed from Clenow literature (not optimized)
MOM_LOOKBACK = 90

DZ_THRESHOLDS = [2.0, 3.0]

# Validated VEGA pairs (reference -> traded)
VEGA_PAIRS = [
    ('SP500', 'GDAXI'),
    ('SP500', 'NI225'),
    ('NDX',   'GDAXI'),
    ('NDX',   'NI225'),
]


# ====================================================================
# DATA LOADING
# ====================================================================

def find_data_file(sym):
    """Find longest available data file for symbol."""
    for fname in ASSET_FILES.get(sym, []):
        path = os.path.join(DATA_DIR, fname)
        if os.path.exists(path):
            return path
    return None


def load_5m(path):
    """Load Dukascopy 5m CSV (Date,Time,Open,High,Low,Close,Volume)."""
    df = pd.read_csv(path)
    df['datetime'] = pd.to_datetime(
        df['Date'].astype(str) + ' ' + df['Time'])
    df = df.set_index('datetime').sort_index()
    df = df.rename(columns={
        'Open': 'open', 'High': 'high', 'Low': 'low',
        'Close': 'close', 'Volume': 'volume'
    })
    df = df[df.index.dayofweek < 5]
    return df[['open', 'high', 'low', 'close', 'volume']]


def resample_ohlc(df_5m, rule):
    """Resample 5m to target timeframe (e.g. '4h', '1D')."""
    return df_5m.resample(rule).agg({
        'open': 'first', 'high': 'max', 'low': 'min',
        'close': 'last', 'volume': 'sum'
    }).dropna(subset=['open'])


# ====================================================================
# INDICATORS
# ====================================================================

def compute_zscore(ohlc):
    """Z-score = (Close - SMA) / ATR. Same formula as VEGA."""
    c = ohlc['close']
    sma = c.rolling(SMA_PERIOD).mean()
    prev = c.shift(1)
    tr = pd.concat([
        ohlc['high'] - ohlc['low'],
        (ohlc['high'] - prev).abs(),
        (ohlc['low'] - prev).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(ATR_PERIOD).mean()
    z = (c - sma) / atr
    return z, atr, c


def compute_clenow_momentum(daily_close, lookback=MOM_LOOKBACK):
    """
    Rolling Clenow momentum: annualized regression slope * R^2.

    Regression of log(close) over `lookback` trading days.
    Annualize: exp(slope * 252) - 1.
    Score = annualized_return * R^2  (penalizes noisy trends).
    """
    n = len(daily_close)
    scores = np.full(n, np.nan)
    log_p = np.log(daily_close.values.astype(float))

    x = np.arange(lookback, dtype=float)
    xm = x.mean()
    ss_xx = ((x - xm) ** 2).sum()

    for i in range(lookback, n):
        y = log_p[i - lookback:i]
        if np.any(np.isnan(y)):
            continue
        ym = y.mean()
        ss_xy = ((x - xm) * (y - ym)).sum()
        ss_yy = ((y - ym) ** 2).sum()
        if ss_yy == 0:
            continue
        slope = ss_xy / ss_xx
        r_sq = (ss_xy ** 2) / (ss_xx * ss_yy)
        scores[i] = (np.exp(slope * 252) - 1) * r_sq

    return pd.Series(scores, index=daily_close.index)


def align_daily_to_h4(daily_series, h4_index):
    """Map PREVIOUS day's momentum to each H4 bar (no lookahead)."""
    return daily_series.shift(1).reindex(h4_index, method='ffill')


# ====================================================================
# STUDY FUNCTIONS
# ====================================================================

def study_reversion(z_sig, close, atr, mom,
                    label, sess, sh, eh, dz, fwd=1):
    """
    Generic mean-reversion study split by momentum tercile.

    z_sig: signal series (own z-score or cross-asset spread).
           z < -dz -> BUY (expect up), z > dz -> SELL (expect down).
    close/atr: traded asset close & ATR for forward return.
    mom: Clenow momentum aligned to H4 bars.

    Returns (list_of_result_dicts, raw_returns_per_tercile).
    """
    hour = z_sig.index.hour
    mask = ((hour >= sh) & (hour <= eh) &
            z_sig.notna() & mom.notna() & atr.notna())

    fwd_ret = (close.shift(-fwd) - close) / atr

    # Direction-aligned returns
    aligned = pd.Series(np.nan, index=z_sig.index)
    long_m = mask & (z_sig < -dz)
    short_m = mask & (z_sig > dz)
    aligned[long_m] = fwd_ret[long_m]
    aligned[short_m] = -fwd_ret[short_m]

    idx = aligned.dropna().index
    if len(idx) < 30:
        return [], {}

    m = mom.loc[idx].values
    r = aligned.loc[idx].values
    ok = ~(np.isnan(m) | np.isnan(r))
    m, r = m[ok], r[ok]
    if len(m) < 30:
        return [], {}

    t33 = np.percentile(m, 33)
    t67 = np.percentile(m, 67)
    splits = {
        'ALL':  np.ones(len(m), dtype=bool),
        'Low':  m <= t33,
        'Mid':  (m > t33) & (m <= t67),
        'High': m > t67,
    }

    results = []
    raw = {}
    for tname, tmask in splits.items():
        nt = int(tmask.sum())
        if nt < 10:
            continue
        rv = r[tmask]
        raw[tname] = rv
        results.append({
            'label': label, 'session': sess, 'dz': dz, 'fwd': fwd,
            'tercile': tname, 'n': nt,
            'edge': float(rv.mean()), 'wr': float((rv > 0).mean()),
            'score': float(rv.mean() * np.sqrt(nt)),
            'mom_avg': float(m[tmask].mean()),
        })

    return results, raw


def welch_lift(high_ret, low_ret):
    """Welch t-test for High - Low tercile edge difference."""
    if len(high_ret) < 10 or len(low_ret) < 10:
        return np.nan, np.nan, np.nan
    lift = high_ret.mean() - low_ret.mean()
    n1, n2 = len(high_ret), len(low_ret)
    v1 = high_ret.var(ddof=1)
    v2 = low_ret.var(ddof=1)
    se = np.sqrt(v1 / n1 + v2 / n2)
    if se == 0:
        return lift, 0.0, 1.0
    t_stat = lift / se
    p_val = erfc(abs(t_stat) / msqrt(2))  # normal approx for large N
    return float(lift), float(t_stat), float(p_val)


def yearly_breakdown(z_sig, close, atr, mom, sh, eh, dz, fwd=1):
    """Per-year edge for ALL signals (unsplit baseline)."""
    hour = z_sig.index.hour
    mask = ((hour >= sh) & (hour <= eh) &
            z_sig.notna() & mom.notna() & atr.notna())
    fwd_ret = (close.shift(-fwd) - close) / atr
    aligned = pd.Series(np.nan, index=z_sig.index)
    aligned[mask & (z_sig < -dz)] = fwd_ret[mask & (z_sig < -dz)]
    aligned[mask & (z_sig > dz)] = -fwd_ret[mask & (z_sig > dz)]
    data = aligned.dropna()
    if len(data) < 10:
        return []
    years = data.index.year
    rows = []
    for yr in sorted(years.unique()):
        yd = data[years == yr]
        if len(yd) < 5:
            continue
        rows.append({
            'year': yr, 'n': len(yd),
            'edge': float(yd.mean()),
            'wr': float((yd > 0).mean()),
        })
    return rows


# ====================================================================
# MAIN
# ====================================================================

def main():
    p = argparse.ArgumentParser(
        description='NOVA Momentum-Quality Divergence Study (Fase 0)')
    p.add_argument('--asset', help='Specific traded asset (e.g. GDAXI)')
    p.add_argument('--session', help='Specific session (Tokyo/London/NY)')
    p.add_argument('--dz', type=float, help='Specific dead zone')
    p.add_argument('--fwd', type=int, default=1, help='Forward bars (default 1)')
    p.add_argument('--yearly', action='store_true', help='Per-year breakdown')
    p.add_argument('--save', action='store_true', help='Save CSV to analysis/')
    p.add_argument('--self-only', action='store_true',
                   help='Only self-reversion study (skip VEGA)')
    p.add_argument('--vega-only', action='store_true',
                   help='Only VEGA+momentum study (skip self)')
    args = p.parse_args()

    print("=" * 80)
    print("NOVA MOMENTUM-QUALITY DIVERGENCE STUDY (Fase 0)")
    print("=" * 80)
    print(f"Hypothesis: Clenow momentum amplifies H4 mean-reversion")
    print(f"Z-score: SMA={SMA_PERIOD}, ATR={ATR_PERIOD} (VEGA identical)")
    print(f"Momentum: slope*R^2, lookback={MOM_LOOKBACK}d (Clenow)")
    print(f"Dead Zones: {DZ_THRESHOLDS}")
    print(f"Forward: {args.fwd} bar(s)")
    print()

    # Determine assets
    if args.asset:
        assets = [args.asset.upper()]
    else:
        assets = list(TRADEABLE)

    sessions = ({args.session: SESSIONS[args.session]}
                if args.session else SESSIONS)
    dz_list = [args.dz] if args.dz is not None else list(DZ_THRESHOLDS)

    # All symbols needed
    needed = set(assets)
    if not args.self_only:
        for ref, traded in VEGA_PAIRS:
            if args.asset and traded != args.asset.upper():
                continue
            needed.add(ref)
            needed.add(traded)

    # Load data
    print("Loading data...")
    cache = {}
    for sym in sorted(needed):
        path = find_data_file(sym)
        if not path:
            print(f"  WARNING: no data for {sym}")
            continue
        df = load_5m(path)
        h4 = resample_ohlc(df, '4h')
        daily = resample_ohlc(df, '1D')
        z, atr, cl = compute_zscore(h4)
        mom = compute_clenow_momentum(daily['close'])
        h4_mom = align_daily_to_h4(mom, h4.index)
        cache[sym] = {
            'z': z, 'atr': atr, 'close': cl, 'mom': h4_mom,
            'daily_mom': mom,
        }
        vm = mom.dropna()
        print(f"  {sym}: {len(h4):,} H4 bars, {len(daily):,} daily, "
              f"mom range [{vm.min():.2f}, {vm.max():.2f}]")
    print()

    all_res = []
    all_raw = {}  # (label, session, dz) -> {tercile: returns_array}

    # ================================================================
    # STUDY A: Self mean-reversion by momentum quality
    # ================================================================
    if not args.vega_only:
        for asset in assets:
            if asset not in cache:
                continue
            c = cache[asset]
            sa = SPREAD_ATR_PCT.get(asset, 99)
            for sn, (sh, eh) in sessions.items():
                for dz in dz_list:
                    lbl = asset + "(self)"
                    res, raw = study_reversion(
                        c['z'], c['close'], c['atr'], c['mom'],
                        lbl, sn, sh, eh, dz, args.fwd)
                    for r in res:
                        r['spread_atr'] = sa
                        r['mode'] = 'self'
                    all_res.extend(res)
                    if raw:
                        all_raw[(lbl, sn, dz)] = raw

    # ================================================================
    # STUDY B: VEGA signals filtered by traded asset momentum
    # ================================================================
    if not args.self_only:
        pairs = VEGA_PAIRS
        if args.asset:
            pairs = [(r, t) for r, t in pairs
                     if t == args.asset.upper()]
        for ref, traded in pairs:
            if ref not in cache or traded not in cache:
                continue
            cr, ct = cache[ref], cache[traded]
            # Cross z-score: traded_z - ref_z
            # When traded_z - ref_z < -dz -> traded relatively low -> BUY
            cross_z = ct['z'] - cr['z']
            sa = SPREAD_ATR_PCT.get(traded, 99)
            for sn, (sh, eh) in sessions.items():
                for dz in dz_list:
                    lbl = ref + "->" + traded
                    res, raw = study_reversion(
                        cross_z, ct['close'], ct['atr'], ct['mom'],
                        lbl, sn, sh, eh, dz, args.fwd)
                    for r in res:
                        r['spread_atr'] = sa
                        r['mode'] = 'vega'
                    all_res.extend(res)
                    if raw:
                        all_raw[(lbl, sn, dz)] = raw

    if not all_res:
        print("No results. Check data availability.")
        return

    # ================================================================
    # REPORT 1: Mean-reversion by tercile
    # ================================================================
    for mode, title in [('self', 'SELF MEAN-REVERSION'),
                        ('vega', 'VEGA + MOMENTUM FILTER')]:
        subset = [r for r in all_res if r.get('mode') == mode]
        if not subset:
            continue
        for dz in dz_list:
            dz_sub = [r for r in subset if r['dz'] == dz]
            if not dz_sub:
                continue
            print()
            print("=" * 80)
            print(f"REPORT: {title} (DZ={dz}, fwd={args.fwd})")
            print("=" * 80)
            hdr = (f"{'Label':>18} {'Sess':<7} {'Terc':<5} {'N':>5} "
                   f"{'Edge':>7} {'WR%':>6} {'Score':>7} {'MomAvg':>8}")
            print(hdr)
            print("-" * len(hdr))

            groups = defaultdict(list)
            for r in dz_sub:
                groups[(r['label'], r['session'])].append(r)

            order = {'ALL': 0, 'Low': 1, 'Mid': 2, 'High': 3}
            for (lbl, sn), rows in sorted(groups.items()):
                for r in sorted(rows, key=lambda x: order.get(x['tercile'], 9)):
                    marker = ''
                    if r['tercile'] == 'High' and r['edge'] > 0.03:
                        marker = ' <-'
                    print(f"{r['label']:>18} {r['session']:<7} "
                          f"{r['tercile']:<5} {r['n']:>5} "
                          f"{r['edge']:>7.4f} {r['wr']*100:>5.1f}% "
                          f"{r['score']:>7.2f} {r['mom_avg']:>8.3f}"
                          f"{marker}")
                print()

    # ================================================================
    # REPORT 2: Momentum lift (High - Low)
    # ================================================================
    print()
    print("=" * 80)
    print("MOMENTUM LIFT: High tercile edge - Low tercile edge")
    print("=" * 80)
    hdr = (f"{'Label':>18} {'Sess':<7} {'DZ':>4} "
           f"{'Lift':>7} {'t-stat':>7} {'p-val':>7} {'Sig?':>5}")
    print(hdr)
    print("-" * len(hdr))

    sig_count = 0
    for (lbl, sn, dz), raw in sorted(all_raw.items()):
        if 'High' not in raw or 'Low' not in raw:
            continue
        lift, t, pv = welch_lift(raw['High'], raw['Low'])
        if np.isnan(lift):
            continue
        sig = 'YES' if pv < 0.05 else 'no'
        if pv < 0.05:
            sig_count += 1
        print(f"{lbl:>18} {sn:<7} {dz:>4.1f} "
              f"{lift:>7.4f} {t:>7.2f} {pv:>7.4f} {sig:>5}")

    total_tests = sum(1 for k, v in all_raw.items()
                      if 'High' in v and 'Low' in v)
    print(f"\nSignificant (p<0.05): {sig_count}/{total_tests}")
    if total_tests > 0:
        pct = sig_count / total_tests * 100
        print(f"By chance alone expect ~5% = {total_tests * 0.05:.1f} "
              f"significant. Got {sig_count} ({pct:.0f}%).")

    # ================================================================
    # REPORT 3: Top candidates by Score
    # ================================================================
    print()
    print("=" * 80)
    print(f"TOP CANDIDATES BY SCORE (fwd={args.fwd})")
    print("=" * 80)

    for tfilt in ['High', 'ALL']:
        top = sorted([r for r in all_res if r['tercile'] == tfilt],
                     key=lambda x: -x['score'])[:15]
        if not top:
            continue
        print(f"\n  --- Tercile: {tfilt} ---")
        print(f"  {'#':>3} {'Label':>18} {'Sess':<7} {'DZ':>4} {'N':>5} "
              f"{'Edge':>7} {'WR%':>6} {'Score':>7} {'Sprd/ATR':>8}")
        print("  " + "-" * 70)
        for i, r in enumerate(top, 1):
            sa = r.get('spread_atr', 99)
            tag = 'OK' if sa < 2 else 'HIGH' if sa < 3 else 'FAIL'
            print(f"  {i:>3} {r['label']:>18} {r['session']:<7} "
                  f"{r['dz']:>4.1f} {r['n']:>5} {r['edge']:>7.4f} "
                  f"{r['wr']*100:>5.1f}% {r['score']:>7.2f} "
                  f"{sa:>5.2f}% [{tag}]")

    # ================================================================
    # YEARLY STABILITY (optional)
    # ================================================================
    if args.yearly:
        print()
        print("=" * 80)
        print("YEARLY STABILITY (top 5 by ALL Score)")
        print("=" * 80)

        all_top = sorted([r for r in all_res if r['tercile'] == 'ALL'],
                         key=lambda x: -x['score'])
        seen = set()
        top_keys = []
        for r in all_top:
            key = (r['label'], r['session'], r['dz'])
            if key not in seen:
                seen.add(key)
                top_keys.append(r)
            if len(top_keys) >= 5:
                break

        for r in top_keys:
            lbl, sn, dz = r['label'], r['session'], r['dz']
            # Determine z_sig source
            if '(self)' in lbl:
                asset = lbl.replace('(self)', '')
                if asset not in cache:
                    continue
                c = cache[asset]
                z_sig = c['z']
                cl, at, mo = c['close'], c['atr'], c['mom']
            elif '->' in lbl:
                ref, traded = lbl.split('->')
                if ref not in cache or traded not in cache:
                    continue
                z_sig = cache[traded]['z'] - cache[ref]['z']
                cl = cache[traded]['close']
                at = cache[traded]['atr']
                mo = cache[traded]['mom']
            else:
                continue

            sh, eh = SESSIONS.get(sn, (0, 23))
            yrs = yearly_breakdown(z_sig, cl, at, mo, sh, eh, dz, args.fwd)
            if not yrs:
                continue
            pos = sum(1 for y in yrs if y['edge'] > 0)
            print(f"\n  {lbl} ({sn}) DZ={dz} Score={r['score']:.2f}")
            print(f"  Years: {len(yrs)} | Positive: {pos}/{len(yrs)}")
            print(f"  {'Year':>6} {'N':>5} {'Edge':>8} {'WR%':>6}")
            for y in yrs:
                sign = '+' if y['edge'] > 0 else '-'
                print(f"  {y['year']:>6} {y['n']:>5} {y['edge']:>8.4f} "
                      f"{y['wr']*100:>5.1f}% {sign}")

    # ================================================================
    # SAVE
    # ================================================================
    if args.save:
        outdir = os.path.join(BASE_DIR, 'analysis')
        os.makedirs(outdir, exist_ok=True)
        df = pd.DataFrame(all_res)
        outpath = os.path.join(outdir, 'nova_momentum_study_H4.csv')
        df.to_csv(outpath, index=False)
        print(f"\nResults saved to {outpath}")

    # ================================================================
    # INTERPRETATION
    # ================================================================
    print()
    print("=" * 80)
    print("INTERPRETATION GUIDE")
    print("=" * 80)
    print("- High tercile Edge >> Low tercile: momentum quality matters")
    print("- Lift p<0.05: statistically significant difference")
    print("- If NO lift anywhere: NOVA hypothesis FAILS -> close investigation")
    print("- If lift exists + Score >= 2.0: design strategy around it")
    print("- Edge > 0.05 + Spread/ATR OK: viable after costs")
    print("- Score > 2.0: strong candidate (VEGA empirical threshold)")
    print("=" * 80)
    print()
    print("AXIOM 12: Do NOT implement strategy without Score >= 2.0")


if __name__ == '__main__':
    main()
