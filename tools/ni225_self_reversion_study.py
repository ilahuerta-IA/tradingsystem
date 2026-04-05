"""
NI225 Self-Reversion Study -- Pre-implementation analysis.

Focused study on NI225 self-reversion (own z-score) in the NY
session (14-18 UTC), which showed Score=2.34 in the NOVA study.

Breaks down the signal by:
  1. Long vs Short direction
  2. Dead Zone sweep (2.0, 2.5, 3.0, 3.5)
  3. Forward bars (1, 2, 3)
  4. Hour within session (14, 15, 16, 17)
  5. Day of week
  6. Yearly stability
  7. Cost viability (spread/ATR = 1.73%)

Usage:
  python tools/ni225_self_reversion_study.py
"""

import os
import sys
import numpy as np
import pandas as pd
from math import sqrt as msqrt

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')

# Z-score params (VEGA identical)
SMA_PERIOD = 24
ATR_PERIOD = 24

# Session (UTC winter)
SESSION_START = 14
SESSION_END = 18

# Spread/ATR for NI225
SPREAD_ATR_PCT = 1.73

DZ_LIST = [2.0, 2.5, 3.0, 3.5]
FWD_BARS = [1, 2, 3]
DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']

SEP = "=" * 80
SUBSEP = "-" * 80


# ====================================================================
# DATA
# ====================================================================

def load_5m(path):
    """Load Dukascopy 5m CSV."""
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


def resample_h4(df_5m):
    """Resample to H4."""
    return df_5m.resample('4h').agg({
        'open': 'first', 'high': 'max', 'low': 'min',
        'close': 'last', 'volume': 'sum'
    }).dropna(subset=['open'])


def compute_zscore(h4):
    """Z-score = (Close - SMA) / ATR."""
    c = h4['close']
    sma = c.rolling(SMA_PERIOD).mean()
    prev = c.shift(1)
    tr = pd.concat([
        h4['high'] - h4['low'],
        (h4['high'] - prev).abs(),
        (h4['low'] - prev).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(ATR_PERIOD).mean()
    z = (c - sma) / atr
    z = z.replace([np.inf, -np.inf], np.nan)
    return z, atr, c


# ====================================================================
# SIGNAL EXTRACTION
# ====================================================================

def extract_signals(z, atr, close, dz):
    """
    Extract self-reversion signals from NI225 z-score.

    Long signal:  z < -dz  (price below mean -> expect reversion UP)
    Short signal: z > +dz  (price above mean -> expect reversion DOWN)

    Returns DataFrame with columns:
      datetime, direction, z_value, close, atr,
      fwd_ret_1..3 (ATR-normalized, aligned with direction)
      hour, dow, year
    """
    mask_session = (z.index.hour >= SESSION_START) & \
                   (z.index.hour < SESSION_END)
    z_sess = z[mask_session].dropna()
    close_sess = close.reindex(z_sess.index)
    atr_sess = atr.reindex(z_sess.index)

    rows = []
    for fwd in FWD_BARS:
        fwd_ret = close.shift(-fwd) - close
        fwd_ret_atr = (fwd_ret / atr).reindex(z_sess.index)

        # Long signals: z < -dz
        long_mask = z_sess < -dz
        for dt in z_sess[long_mask].index:
            ret = fwd_ret_atr.get(dt, np.nan)
            if fwd == 1 and not np.isnan(ret):
                rows.append({
                    'datetime': dt,
                    'direction': 'long',
                    'z_value': z_sess[dt],
                    'close': close_sess[dt],
                    'atr': atr_sess[dt],
                    'hour': dt.hour,
                    'dow': dt.dayofweek,
                    'year': dt.year,
                })
            if len(rows) > 0 and rows[-1]['datetime'] == dt:
                rows[-1][f'fwd_ret_{fwd}'] = ret  # Aligned (long)

        # Short signals: z > +dz
        short_mask = z_sess > dz
        for dt in z_sess[short_mask].index:
            ret = fwd_ret_atr.get(dt, np.nan)
            if fwd == 1 and not np.isnan(ret):
                rows.append({
                    'datetime': dt,
                    'direction': 'short',
                    'z_value': z_sess[dt],
                    'close': close_sess[dt],
                    'atr': atr_sess[dt],
                    'hour': dt.hour,
                    'dow': dt.dayofweek,
                    'year': dt.year,
                })
            if len(rows) > 0 and rows[-1]['datetime'] == dt:
                rows[-1][f'fwd_ret_{fwd}'] = -ret  # Negate for short

    return pd.DataFrame(rows)


def extract_signals_fast(z, atr, close, dz):
    """
    Vectorized signal extraction -- much faster than row-by-row.
    """
    mask_session = (z.index.hour >= SESSION_START) & \
                   (z.index.hour < SESSION_END)
    z_sess = z[mask_session].dropna()

    # Forward returns in ATR units
    fwd_rets = {}
    for fwd in FWD_BARS:
        fr = (close.shift(-fwd) - close) / atr
        fwd_rets[fwd] = fr.reindex(z_sess.index)

    # Long: z < -dz
    long_mask = z_sess < -dz
    # Short: z > +dz
    short_mask = z_sess > dz

    records = []

    for mask, direction, sign in [(long_mask, 'long', 1.0),
                                   (short_mask, 'short', -1.0)]:
        idx = z_sess[mask].index
        if len(idx) == 0:
            continue
        for dt in idx:
            r = {
                'datetime': dt,
                'direction': direction,
                'z_value': z_sess[dt],
                'hour': dt.hour,
                'dow': dt.dayofweek,
                'year': dt.year,
            }
            for fwd in FWD_BARS:
                val = fwd_rets[fwd].get(dt, np.nan)
                r[f'fwd_ret_{fwd}'] = val * sign
            records.append(r)

    df = pd.DataFrame(records)
    if len(df) > 0:
        df = df.sort_values('datetime').reset_index(drop=True)
    return df


# ====================================================================
# REPORTING
# ====================================================================

def score(edge, n):
    """Score = edge * sqrt(N)."""
    if n < 1 or np.isnan(edge):
        return 0.0
    return edge * msqrt(n)


def report_edge(df, col, label):
    """Print edge stats for a DataFrame slice."""
    vals = df[col].dropna()
    n = len(vals)
    if n < 5:
        print(f"  {label:<25} N={n:>4}  (insufficient)")
        return n, np.nan, np.nan, 0.0
    edge = vals.mean()
    wr = (vals > 0).mean() * 100
    sc = score(edge, n)
    flag = " ***" if sc >= 2.0 else " *" if sc >= 1.5 else ""
    print(f"  {label:<25} N={n:>4}  Edge={edge:>+.4f}  "
          f"WR={wr:>5.1f}%  Score={sc:>5.2f}{flag}")
    return n, edge, wr, sc


def main():
    os.chdir(BASE_DIR)

    # Find NI225 data
    for fname in ['NI225_5m_15Yea.csv', 'NI225_5m_5Yea.csv']:
        path = os.path.join(DATA_DIR, fname)
        if os.path.exists(path):
            break
    else:
        print("ERROR: NI225 data not found")
        sys.exit(1)

    print(SEP)
    print("NI225 SELF-REVERSION STUDY -- NY SESSION (14-18 UTC)")
    print(SEP)
    print(f"Z-score: SMA={SMA_PERIOD}, ATR={ATR_PERIOD}")
    print(f"Session: {SESSION_START}-{SESSION_END} UTC")
    print(f"DZ thresholds: {DZ_LIST}")
    print(f"Forward bars: {FWD_BARS}")
    print(f"Spread/ATR: {SPREAD_ATR_PCT}%")
    print()

    print("Loading NI225 data...")
    df_5m = load_5m(path)
    h4 = resample_h4(df_5m)
    z, atr, close = compute_zscore(h4)
    print(f"  H4 bars: {len(h4)} ({h4.index[0].date()} to "
          f"{h4.index[-1].date()})")
    print()

    # ==================================================================
    # REPORT 1: EDGE BY DZ AND FORWARD BARS (ALL, LONG, SHORT)
    # ==================================================================
    print(SEP)
    print("REPORT 1: EDGE BY DEAD ZONE x FORWARD BARS x DIRECTION")
    print(SEP)

    best_records = []

    for dz in DZ_LIST:
        signals = extract_signals_fast(z, atr, close, dz)
        if len(signals) == 0:
            print(f"\n--- DZ={dz} --- No signals")
            continue

        print(f"\n--- DZ={dz} ---")
        for fwd in FWD_BARS:
            col = f'fwd_ret_{fwd}'
            if col not in signals.columns:
                continue
            print(f"\n  Forward = {fwd} bar(s):")
            n_all, e_all, wr_all, sc_all = report_edge(
                signals, col, "ALL")
            n_l, e_l, wr_l, sc_l = report_edge(
                signals[signals['direction'] == 'long'], col, "LONG only")
            n_s, e_s, wr_s, sc_s = report_edge(
                signals[signals['direction'] == 'short'], col, "SHORT only")

            best_records.append({
                'dz': dz, 'fwd': fwd,
                'n_all': n_all, 'edge_all': e_all, 'wr_all': wr_all,
                'score_all': sc_all,
                'n_long': n_l, 'edge_long': e_l, 'score_long': sc_l,
                'n_short': n_s, 'edge_short': e_s, 'score_short': sc_s,
            })

    # ==================================================================
    # REPORT 2: HOUR BREAKDOWN (within NY session)
    # ==================================================================
    print()
    print(SEP)
    print("REPORT 2: EDGE BY HOUR (DZ=3.0, fwd=1)")
    print(SEP)

    dz_focus = 3.0
    signals = extract_signals_fast(z, atr, close, dz_focus)
    col = 'fwd_ret_1'

    if len(signals) > 0 and col in signals.columns:
        for hour in range(SESSION_START, SESSION_END):
            mask_h = signals['hour'] == hour
            sub = signals[mask_h]
            report_edge(sub, col, f"HOUR {hour}:00 UTC")

        # Also check DZ=2.0
        print(f"\n  --- Same breakdown for DZ=2.0 ---")
        signals_dz2 = extract_signals_fast(z, atr, close, 2.0)
        if len(signals_dz2) > 0 and col in signals_dz2.columns:
            for hour in range(SESSION_START, SESSION_END):
                mask_h = signals_dz2['hour'] == hour
                sub = signals_dz2[mask_h]
                report_edge(sub, col, f"HOUR {hour}:00 UTC")

    # ==================================================================
    # REPORT 3: DAY-OF-WEEK BREAKDOWN
    # ==================================================================
    print()
    print(SEP)
    print("REPORT 3: EDGE BY DAY OF WEEK (DZ=3.0, fwd=1)")
    print(SEP)

    if len(signals) > 0 and col in signals.columns:
        for dow in range(5):
            mask_d = signals['dow'] == dow
            sub = signals[mask_d]
            report_edge(sub, col, DAY_NAMES[dow])

        print(f"\n  --- Same breakdown for DZ=2.0 ---")
        if len(signals_dz2) > 0 and col in signals_dz2.columns:
            for dow in range(5):
                mask_d = signals_dz2['dow'] == dow
                sub = signals_dz2[mask_d]
                report_edge(sub, col, DAY_NAMES[dow])

    # ==================================================================
    # REPORT 4: YEARLY STABILITY
    # ==================================================================
    print()
    print(SEP)
    print("REPORT 4: YEARLY STABILITY")
    print(SEP)

    for dz in [3.0, 2.5, 2.0]:
        sigs = extract_signals_fast(z, atr, close, dz)
        if len(sigs) == 0:
            continue
        print(f"\n--- DZ={dz}, fwd=1, ALL ---")
        col = 'fwd_ret_1'
        years = sorted(sigs['year'].unique())
        pos_years = 0
        total_years = 0
        print(f"  {'Year':<6} {'N':>5} {'Edge':>8} {'WR%':>6} "
              f"{'Score':>7}  {'Long':>5} {'Short':>5}")
        print(f"  {SUBSEP}")
        for yr in years:
            sub = sigs[sigs['year'] == yr]
            vals = sub[col].dropna()
            n = len(vals)
            if n < 3:
                continue
            total_years += 1
            edge = vals.mean()
            wr = (vals > 0).mean() * 100
            sc = score(edge, n)
            n_l = (sub['direction'] == 'long').sum()
            n_s = (sub['direction'] == 'short').sum()
            tag = "+" if edge > 0 else "-"
            if edge > 0:
                pos_years += 1
            print(f"  {yr:<6} {n:>5} {edge:>+8.4f} {wr:>5.1f}% "
                  f"{sc:>+7.2f}  L={n_l:>3} S={n_s:>3}  {tag}")
        print(f"\n  Positive years: {pos_years}/{total_years} "
              f"({pos_years/total_years*100:.0f}%)" if total_years > 0
              else "")

        # Long only
        print(f"\n--- DZ={dz}, fwd=1, LONG ONLY ---")
        long_sigs = sigs[sigs['direction'] == 'long']
        pos_years = 0
        total_years = 0
        print(f"  {'Year':<6} {'N':>5} {'Edge':>8} {'WR%':>6} "
              f"{'Score':>7}")
        print(f"  {SUBSEP}")
        for yr in years:
            sub = long_sigs[long_sigs['year'] == yr]
            vals = sub[col].dropna()
            n = len(vals)
            if n < 2:
                continue
            total_years += 1
            edge = vals.mean()
            wr = (vals > 0).mean() * 100
            sc = score(edge, n)
            tag = "+" if edge > 0 else "-"
            if edge > 0:
                pos_years += 1
            print(f"  {yr:<6} {n:>5} {edge:>+8.4f} {wr:>5.1f}% "
                  f"{sc:>+7.2f}  {tag}")
        print(f"\n  Positive years: {pos_years}/{total_years} "
              f"({pos_years/total_years*100:.0f}%)" if total_years > 0
              else "")

        # Short only
        print(f"\n--- DZ={dz}, fwd=1, SHORT ONLY ---")
        short_sigs = sigs[sigs['direction'] == 'short']
        pos_years = 0
        total_years = 0
        print(f"  {'Year':<6} {'N':>5} {'Edge':>8} {'WR%':>6} "
              f"{'Score':>7}")
        print(f"  {SUBSEP}")
        for yr in years:
            sub = short_sigs[short_sigs['year'] == yr]
            vals = sub[col].dropna()
            n = len(vals)
            if n < 2:
                continue
            total_years += 1
            edge = vals.mean()
            wr = (vals > 0).mean() * 100
            sc = score(edge, n)
            tag = "+" if edge > 0 else "-"
            if edge > 0:
                pos_years += 1
            print(f"  {yr:<6} {n:>5} {edge:>+8.4f} {wr:>5.1f}% "
                  f"{sc:>+7.2f}  {tag}")
        print(f"\n  Positive years: {pos_years}/{total_years} "
              f"({pos_years/total_years*100:.0f}%)" if total_years > 0
              else "")

    # ==================================================================
    # REPORT 5: COST VIABILITY
    # ==================================================================
    print()
    print(SEP)
    print("REPORT 5: COST VIABILITY")
    print(SEP)
    print(f"  Spread/ATR = {SPREAD_ATR_PCT}%")
    print(f"  1 ATR unit cost ~= {SPREAD_ATR_PCT/100:.4f} ATR")
    print()

    for dz in [3.0, 2.5, 2.0]:
        sigs = extract_signals_fast(z, atr, close, dz)
        if len(sigs) == 0:
            continue
        for fwd in FWD_BARS:
            col = f'fwd_ret_{fwd}'
            vals = sigs[col].dropna()
            if len(vals) < 20:
                continue
            gross_edge = vals.mean()
            cost = SPREAD_ATR_PCT / 100
            net_edge = gross_edge - cost
            net_score = score(net_edge, len(vals))
            flag = " OK" if net_edge > 0 else " FAIL"
            print(f"  DZ={dz} fwd={fwd}: Gross={gross_edge:>+.4f}  "
                  f"Cost={cost:.4f}  Net={net_edge:>+.4f}  "
                  f"NetScore={net_score:>+.2f}{flag}")

    # ==================================================================
    # SUMMARY
    # ==================================================================
    print()
    print(SEP)
    print("INTERPRETATION GUIDE")
    print(SEP)
    print("- Score >= 2.0: implement candidate (Axiom 12)")
    print("- If LONG >> SHORT: configure allow_long=True, "
          "allow_short=False")
    print("- If specific hours dominate: narrow session window")
    print("- If specific days are negative: add day filter")
    print("- Net edge > 0 after spread/ATR: cost-viable")
    print("- Positive years >= 70%: stable edge")
    print()
    print("IMPLEMENTATION NOTE:")
    print("  NI225 self-reversion is NOT cross-asset (VEGA).")
    print("  It uses the asset's OWN z-score as signal.")
    print("  Strategy code needs: z_NI225 vs DZ, no reference pair.")
    print(SEP)


if __name__ == '__main__':
    main()
