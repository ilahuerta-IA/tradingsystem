"""
VEGA Divergence Study -- Axiom 12 compliance.

Purpose: Before implementing any new VEGA config, study the actual
z-score divergence between index pairs across sessions.

Computes:
  1. Z-score spread (z_A - z_B) statistics per session
  2. Mean absolute divergence by session window
  3. Frequency of | spread | > dead_zone thresholds
  4. Mean-reversion predictability: after |spread| > DZ,
     does traded asset (B) move in predicted direction?
  5. Theoretical edge: avg return per signal bar

Usage:
  python tools/divergence_study.py
"""

import pandas as pd
import numpy as np
import os
import sys
from itertools import product


# ====================================================================
# CONFIG
# ====================================================================

# Index files: {symbol: path}
INDEX_FILES = {
    'NI225':  'data/NI225_5m_15Yea.csv',
    'GDAXI':  'data/GDAXI_5m_15Yea.csv',
    'SP500':  'data/SP500_5m_15Yea.csv',
    'UK100':  'data/UK100_5m_15Yea.csv',
    'NDX':    'data/NDX_5m_15Yea.csv',
    'EUR50':  'data/EUR50_5m_5Yea.csv',
    'AUS200': 'data/AUS200_5m_5Yea.csv',
}

# Spread/ATR for traded assets (only trade assets with < 2%)
SPREAD_ATR = {
    'NDX':   0.41,   # Best
    'GDAXI': 0.96,
    'NI225': 1.73,   # Marginal
}

# Sessions (UTC winter hours -- DST shifts -1h in summer)
SESSIONS = {
    'Tokyo':   (0, 5),     # NI225 main session
    'London':  (7, 12),    # GDAXI/UK100/EUR50 main session
    'NY':      (14, 18),   # NDX/SP500 main session
    'LDN_NY':  (13, 16),   # Overlap London afternoon + NY open
}

# Z-score params (same as strategy)
SMA_PERIOD = 24
ATR_PERIOD = 24

# Dead zone thresholds to test
DZ_THRESHOLDS = [1.5, 2.0, 2.5, 3.0, 3.5]

# Forward bars to measure mean-reversion (H4 bars)
FORWARD_BARS = [1, 2, 3]

# Minimum data overlap (H4 bars)
MIN_OVERLAP_BARS = 500


# ====================================================================
# DATA LOADING
# ====================================================================

def load_h4(symbol, path):
    """Load CSV and resample to H4 OHLC."""
    if not os.path.exists(path):
        print(f"  WARNING: {path} not found, skipping {symbol}")
        return None
    df = pd.read_csv(path)
    df['datetime'] = pd.to_datetime(
        df['Date'].astype(str) + ' ' + df['Time'])
    df.set_index('datetime', inplace=True)
    h4 = df.resample('4h').agg({
        'Open': 'first', 'High': 'max',
        'Low': 'min', 'Close': 'last'
    }).dropna()
    return h4


def compute_zscore(h4):
    """Compute z-score series: (Close - SMA) / ATR on H4."""
    sma = h4['Close'].rolling(SMA_PERIOD).mean()
    # True Range for ATR
    prev_close = h4['Close'].shift(1)
    tr = np.maximum(
        h4['High'] - h4['Low'],
        np.maximum(
            abs(h4['High'] - prev_close),
            abs(h4['Low'] - prev_close)
        )
    )
    atr = tr.rolling(ATR_PERIOD).mean()
    z = (h4['Close'] - sma) / atr
    z = z.replace([np.inf, -np.inf], np.nan)
    return z, atr, h4['Close']


# ====================================================================
# STUDY FUNCTIONS
# ====================================================================

def session_mask(idx, start_h, end_h):
    """Boolean mask for UTC hours in [start_h, end_h)."""
    hours = idx.hour
    if start_h <= end_h:
        return (hours >= start_h) & (hours < end_h)
    else:  # Wrap around midnight
        return (hours >= start_h) | (hours < end_h)


def study_pair(z_a, z_b, close_b, atr_b, sym_a, sym_b, session_name,
               start_h, end_h):
    """
    Study divergence and mean-reversion for one pair in one session.

    z_a: reference z-score, z_b: traded z-score
    Signal: spread = z_a - z_b
    Trade direction on B: spread > 0 -> SHORT B, spread < 0 -> LONG B
    Mean-reversion: after spread > DZ, does B move DOWN (short profitable)?
                    after spread < -DZ, does B move UP (long profitable)?
    """
    # Align on common index
    common = z_a.dropna().index.intersection(z_b.dropna().index)
    if len(common) < MIN_OVERLAP_BARS:
        return None

    spread = z_a.loc[common] - z_b.loc[common]
    close = close_b.loc[common]
    atr = atr_b.loc[common]

    # Filter to session hours
    mask = session_mask(common, start_h, end_h)
    spread_sess = spread[mask]
    close_sess = close[mask]
    atr_sess = atr[mask]

    if len(spread_sess) < 100:
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

    # Frequency above dead zone thresholds
    for dz in DZ_THRESHOLDS:
        count = (spread_sess.abs() > dz).sum()
        result[f'freq_dz{dz}'] = count / len(spread_sess) * 100

    # Mean-reversion study: for bars where |spread| > DZ,
    # measure forward return of B in ATR units
    for dz in DZ_THRESHOLDS:
        for fwd in FORWARD_BARS:
            # Forward return in points
            fwd_ret = close.shift(-fwd) - close
            fwd_ret_atr = fwd_ret / atr  # Normalize by ATR

            # Signal: spread > dz -> expect B down (short) -> fwd_ret < 0
            #         spread < -dz -> expect B up (long) -> fwd_ret > 0
            # We define "edge" as the signed return ALIGNED with signal:
            #   signal_sign = -sign(spread)  [trade direction]
            #   aligned_return = signal_sign * fwd_ret

            long_mask = mask & (spread < -dz)
            short_mask = mask & (spread > dz)

            long_ret = fwd_ret_atr[long_mask]
            short_ret = -fwd_ret_atr[short_mask]  # Negate for short

            all_ret = pd.concat([long_ret, short_ret])
            n_signals = len(all_ret.dropna())

            if n_signals >= 20:
                edge = all_ret.dropna().mean()
                win_rate = (all_ret.dropna() > 0).mean() * 100
                result[f'edge_dz{dz}_f{fwd}'] = edge
                result[f'wr_dz{dz}_f{fwd}'] = win_rate
                result[f'n_dz{dz}_f{fwd}'] = n_signals
            else:
                result[f'edge_dz{dz}_f{fwd}'] = np.nan
                result[f'wr_dz{dz}_f{fwd}'] = np.nan
                result[f'n_dz{dz}_f{fwd}'] = n_signals

    return result


# ====================================================================
# MAIN
# ====================================================================

def main():
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    print("=" * 80)
    print("VEGA DIVERGENCE STUDY -- Axiom 12 compliance")
    print("=" * 80)
    print(f"Z-score: SMA={SMA_PERIOD}, ATR={ATR_PERIOD}")
    print(f"Sessions: {list(SESSIONS.keys())}")
    print(f"Dead Zones: {DZ_THRESHOLDS}")
    print(f"Forward bars: {FORWARD_BARS}")
    print()

    # Load all data
    print("Loading data...")
    h4_data = {}
    z_data = {}
    atr_data = {}
    close_data = {}
    for sym, path in INDEX_FILES.items():
        h4 = load_h4(sym, path)
        if h4 is not None:
            z, atr, close = compute_zscore(h4)
            h4_data[sym] = h4
            z_data[sym] = z
            atr_data[sym] = atr
            close_data[sym] = close
            print(f"  {sym}: {len(h4)} H4 bars "
                  f"({h4.index[0].date()} to {h4.index[-1].date()})")
    print()

    # Define pairs: (reference, traded) where traded has good spread/ATR
    tradeable = list(SPREAD_ATR.keys())
    all_syms = list(z_data.keys())

    pairs = []
    for traded in tradeable:
        for ref in all_syms:
            if ref != traded:
                pairs.append((ref, traded))

    print(f"Pairs to study: {len(pairs)}")
    for ref, traded in pairs:
        print(f"  {ref} -> {traded} (trade {traded}, "
              f"spread/ATR={SPREAD_ATR[traded]:.2f}%)")
    print()

    # Run study
    results = []
    for (ref, traded), (sess_name, (sh, eh)) in product(
            pairs, SESSIONS.items()):
        if ref not in z_data or traded not in z_data:
            continue
        r = study_pair(
            z_data[ref], z_data[traded],
            close_data[traded], atr_data[traded],
            ref, traded, sess_name, sh, eh)
        if r:
            results.append(r)

    if not results:
        print("No results! Check data.")
        return

    df = pd.DataFrame(results)

    # ================================================================
    # REPORT 1: Divergence amplitude by pair x session
    # ================================================================
    print()
    print("=" * 80)
    print("REPORT 1: DIVERGENCE AMPLITUDE (|z_A - z_B|) BY PAIR x SESSION")
    print("=" * 80)
    print(f"{'Ref':>7} -> {'Traded':<7} {'Session':<8} "
          f"{'Bars':>6} {'|Sprd|':>7} {'Median':>7} {'P75':>7} {'P90':>7} "
          f"{'%>2.0':>6} {'%>3.0':>6}")
    print("-" * 80)
    for _, row in df.sort_values(
            ['traded', 'abs_spread_mean'], ascending=[True, False]).iterrows():
        print(f"{row['ref']:>7} -> {row['traded']:<7} {row['session']:<8} "
              f"{row['bars']:>6} {row['abs_spread_mean']:>7.3f} "
              f"{row['abs_spread_median']:>7.3f} "
              f"{row['abs_spread_p75']:>7.3f} "
              f"{row['abs_spread_p90']:>7.3f} "
              f"{row.get('freq_dz2.0', 0):>5.1f}% "
              f"{row.get('freq_dz3.0', 0):>5.1f}%")

    # ================================================================
    # REPORT 2: Mean-reversion edge (DZ=2.0, 3.0; fwd=1,2,3)
    # ================================================================
    print()
    print("=" * 80)
    print("REPORT 2: MEAN-REVERSION EDGE (avg ATR-normalized return)")
    print("  Positive edge = mean-reversion works (profitable)")
    print("  WR% = win rate of aligned return")
    print("=" * 80)

    for dz in [2.0, 3.0]:
        print(f"\n--- Dead Zone = {dz} ---")
        print(f"{'Ref':>7} -> {'Traded':<7} {'Session':<8} "
              f"{'N':>5} "
              f"{'Edge1':>7} {'WR1%':>5} "
              f"{'Edge2':>7} {'WR2%':>5} "
              f"{'Edge3':>7} {'WR3%':>5}")
        print("-" * 80)

        sub = df[df[f'n_dz{dz}_f1'] >= 20].sort_values(
            f'edge_dz{dz}_f1', ascending=False)
        for _, row in sub.iterrows():
            n = row[f'n_dz{dz}_f1']
            e1 = row.get(f'edge_dz{dz}_f1', np.nan)
            w1 = row.get(f'wr_dz{dz}_f1', np.nan)
            e2 = row.get(f'edge_dz{dz}_f2', np.nan)
            w2 = row.get(f'wr_dz{dz}_f2', np.nan)
            e3 = row.get(f'edge_dz{dz}_f3', np.nan)
            w3 = row.get(f'wr_dz{dz}_f3', np.nan)
            print(f"{row['ref']:>7} -> {row['traded']:<7} "
                  f"{row['session']:<8} {n:>5} "
                  f"{e1:>7.4f} {w1:>4.1f}% "
                  f"{e2:>7.4f} {w2:>4.1f}% "
                  f"{e3:>7.4f} {w3:>4.1f}%")

    # ================================================================
    # REPORT 3: TOP candidates -- ranked by edge * sqrt(N)
    # ================================================================
    print()
    print("=" * 80)
    print("REPORT 3: TOP CANDIDATES (ranked by edge * sqrt(N) at DZ=3.0, fwd=1)")
    print("  Score = edge_per_bar * sqrt(N_signals) -- proxy for risk-adjusted return")
    print("=" * 80)

    dz = 3.0
    fwd = 1
    col_e = f'edge_dz{dz}_f{fwd}'
    col_n = f'n_dz{dz}_f{fwd}'
    col_w = f'wr_dz{dz}_f{fwd}'

    ranked = df[df[col_n] >= 20].copy()
    if len(ranked) > 0:
        ranked['score'] = ranked[col_e] * np.sqrt(ranked[col_n])
        ranked = ranked.sort_values('score', ascending=False)

        print(f"{'#':>3} {'Ref':>7} -> {'Traded':<7} {'Session':<8} "
              f"{'N':>5} {'Edge':>7} {'WR%':>5} {'Score':>8} "
              f"{'Sprd/ATR':>8}")
        print("-" * 80)
        for i, (_, row) in enumerate(ranked.head(20).iterrows()):
            sa = SPREAD_ATR.get(row['traded'], 99)
            print(f"{i+1:>3} {row['ref']:>7} -> {row['traded']:<7} "
                  f"{row['session']:<8} "
                  f"{row[col_n]:>5.0f} {row[col_e]:>7.4f} "
                  f"{row[col_w]:>4.1f}% {row['score']:>8.2f} "
                  f"{sa:>7.2f}%")

    # ================================================================
    # REPORT 4: Also show DZ=2.0 ranking
    # ================================================================
    print()
    print("=" * 80)
    print("REPORT 4: TOP CANDIDATES (ranked by edge * sqrt(N) at DZ=2.0, fwd=1)")
    print("=" * 80)

    dz = 2.0
    col_e = f'edge_dz{dz}_f{fwd}'
    col_n = f'n_dz{dz}_f{fwd}'
    col_w = f'wr_dz{dz}_f{fwd}'

    ranked2 = df[df[col_n] >= 30].copy()
    if len(ranked2) > 0:
        ranked2['score'] = ranked2[col_e] * np.sqrt(ranked2[col_n])
        ranked2 = ranked2.sort_values('score', ascending=False)

        print(f"{'#':>3} {'Ref':>7} -> {'Traded':<7} {'Session':<8} "
              f"{'N':>5} {'Edge':>7} {'WR%':>5} {'Score':>8} "
              f"{'Sprd/ATR':>8}")
        print("-" * 80)
        for i, (_, row) in enumerate(ranked2.head(20).iterrows()):
            sa = SPREAD_ATR.get(row['traded'], 99)
            print(f"{i+1:>3} {row['ref']:>7} -> {row['traded']:<7} "
                  f"{row['session']:<8} "
                  f"{row[col_n]:>5.0f} {row[col_e]:>7.4f} "
                  f"{row[col_w]:>4.1f}% {row['score']:>8.2f} "
                  f"{sa:>7.2f}%")

    # ================================================================
    # SUMMARY
    # ================================================================
    print()
    print("=" * 80)
    print("SUMMARY / INTERPRETATION GUIDE")
    print("=" * 80)
    print("- Edge > 0: mean-reversion signal is profitable on average")
    print("- Edge > 0.05: suggests viable after costs")
    print("- WR% > 52%: statistically meaningful win rate")
    print("- Score > 1.0: strong risk-adjusted candidate")
    print("- N > 100: sufficient sample for confidence")
    print()
    print("KEY HYPOTHESIS:")
    print("  Best divergence = reference OPEN, traded CLOSED/opening")
    print("  -> Tokyo session: NI225(ref) open, NDX(traded) closed")
    print("  -> London session: GDAXI/UK100(ref) open, NDX(traded) pre-market")
    print("  -> NY session: both open -> LESS divergence (simultaneous pricing)")
    print("=" * 80)


if __name__ == '__main__':
    main()
