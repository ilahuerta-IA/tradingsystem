"""
ALTAIR Timeframe Pre-Study -- Miner's Checklist Before Lowering Timeframe

Validates three prerequisites before running ALTAIR at 30m/15m:

  1. DTOSC Zone Coverage: Does DTOSC(8,5,3,3) reach OS (<25) and OB (>75)
     zones on pullbacks? Miner: "the oscillator must reach OS/OB on most
     swings, with reversals within 1-2 bars of the price extreme."

  2. Spread/ATR Viability (Axiom 8): Is ATR large enough relative to
     spread? Rule: spread must be < 20% of expected profit.
     Proxy: spread/(ATR * tp_mult) < 0.20.

  3. Signal Quality: How many DTOSC crossovers from OS occur per TF?
     Are there excessive whipsaw crosses?

Method: Pure pandas analysis on resampled OHLC (no backtrader).

Usage:
    python tools/altair_tf_prestudy.py                    # all 5 tickers
    python tools/altair_tf_prestudy.py --ticker MSFT JPM  # specific
"""
import sys
import os
import argparse

import numpy as np
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')

TICKERS = ['JPM', 'V', 'NVDA', 'MSFT', 'GOOGL']

# DTOSC params (Miner: 8,5,3,3 for intraday)
DTOSC_PERIOD = 8
DTOSC_SMOOTH_K = 5
DTOSC_SMOOTH_D = 3
DTOSC_SIGNAL = 3
DTOSC_OB = 75
DTOSC_OS_A = 25   # Config A
DTOSC_OS_B = 20   # Config B

# Config per ticker (same as timeframe_compare)
BEST_CONFIG = {
    'JPM':   {'os': DTOSC_OS_B},
    'V':     {'os': DTOSC_OS_B},
    'NVDA':  {'os': DTOSC_OS_A},
    'MSFT':  {'os': DTOSC_OS_A},
    'GOOGL': {'os': DTOSC_OS_A},
}

# Typical bid-ask spread per ticker (USD, conservative estimates for US stocks)
# Source: average quoted spreads for liquid SPX/NDX components
SPREADS = {
    'JPM':   0.01,
    'V':     0.01,
    'NVDA':  0.02,
    'MSFT':  0.01,
    'GOOGL': 0.02,
}

# Timeframes to analyze: label -> resample_rule (pandas offset alias)
# H1 uses dedicated 1h CSV; 30m/15m resample from 5m
TIMEFRAMES = ['H1', '30m', '15m']

# ALTAIR TP multiplier (for spread viability check)
TP_ATR_MULT = 4.0
ATR_PERIOD_H1 = 14  # standard ATR lookback at H1


# ── Data Loading ─────────────────────────────────────────────────────────────

def load_csv(filepath):
    """Load a Date/Time OHLCV CSV into a DatetimeIndex DataFrame."""
    df = pd.read_csv(filepath)
    df['datetime'] = pd.to_datetime(
        df['Date'].astype(str) + ' ' + df['Time'],
        format='%Y%m%d %H:%M:%S',
    )
    df.set_index('datetime', inplace=True)
    df = df[['Open', 'High', 'Low', 'Close', 'Volume']].astype(float)
    return df


def resample_ohlcv(df_5m, rule):
    """Resample 5m OHLCV to a coarser timeframe (e.g. '30min', '15min')."""
    agg = {
        'Open': 'first',
        'High': 'max',
        'Low': 'min',
        'Close': 'last',
        'Volume': 'sum',
    }
    resampled = df_5m.resample(rule).agg(agg).dropna(subset=['Open'])
    return resampled


# ── DTOSC Computation ────────────────────────────────────────────────────────

def compute_dtosc(df, period=8, smooth_k=5, smooth_d=3, signal=3):
    """
    Compute DT Oscillator (Miner) on OHLC DataFrame.

    Returns DataFrame with columns: raw_k, sk (fast), sd (slow=signal).
    """
    high_max = df['High'].rolling(period).max()
    low_min = df['Low'].rolling(period).min()
    denom = high_max - low_min
    denom = denom.replace(0, np.nan)

    raw_k = 100.0 * (df['Close'] - low_min) / denom
    sk = raw_k.rolling(smooth_k).mean()   # first smoothing -> fast line
    sd = sk.rolling(smooth_d).mean()       # second smoothing
    sig = sd.rolling(signal).mean()        # signal line -> slow line

    return pd.DataFrame({
        'raw_k': raw_k,
        'fast': sd,     # Miner: sd is the "fast" line
        'slow': sig,    # signal is the "slow" line
    }, index=df.index)


# ── ATR Computation ──────────────────────────────────────────────────────────

def compute_atr(df, period):
    """Compute Average True Range over `period` bars."""
    h = df['High']
    l = df['Low']
    c = df['Close'].shift(1)
    tr = pd.concat([h - l, (h - c).abs(), (l - c).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()


# ── Analysis per Ticker x Timeframe ─────────────────────────────────────────

def analyze(ticker, tf_label, df_ohlc, dtosc_os):
    """
    Run Miner's pre-study checklist on one ticker at one timeframe.

    Returns dict with all diagnostic metrics.
    """
    n_bars = len(df_ohlc)

    # ── 1. DTOSC zone coverage ──
    dtosc = compute_dtosc(df_ohlc, DTOSC_PERIOD, DTOSC_SMOOTH_K,
                          DTOSC_SMOOTH_D, DTOSC_SIGNAL)
    valid = dtosc.dropna()
    n_valid = len(valid)

    # Percentage of bars where fast line is in OS / OB zones
    pct_os = (valid['fast'] < dtosc_os).mean() * 100
    pct_ob = (valid['fast'] > DTOSC_OB).mean() * 100

    # Count distinct OS visits (transitions into OS zone)
    in_os = (valid['fast'] < dtosc_os).astype(int)
    os_entries = ((in_os == 1) & (in_os.shift(1) == 0)).sum()

    # Count bullish crossovers from OS (ALTAIR signal)
    fast = valid['fast']
    slow = valid['slow']
    cross_up = (fast > slow) & (fast.shift(1) <= slow.shift(1))
    from_os = (fast.shift(1) < dtosc_os) | (slow.shift(1) < dtosc_os)
    signals = (cross_up & from_os).sum()

    # Signals per month
    if n_valid > 0:
        date_range = (valid.index[-1] - valid.index[0]).days
        months = max(date_range / 30.44, 1)
        signals_per_month = signals / months
    else:
        months = 0
        signals_per_month = 0

    # ── 2. Spread / ATR viability ──
    # Scale ATR period proportionally: at 30m there are more bars per day
    bpd_map = {'H1': 7, '30m': 13, '15m': 26}
    bpd = bpd_map[tf_label]
    atr_period = round(ATR_PERIOD_H1 * bpd / 7)
    atr = compute_atr(df_ohlc, atr_period)
    median_atr = atr.median()
    mean_atr = atr.mean()

    spread = SPREADS.get(ticker, 0.01)
    # Expected profit per trade = ATR * TP multiplier
    expected_profit = median_atr * TP_ATR_MULT
    spread_ratio = (spread / expected_profit * 100) if expected_profit > 0 else 999

    # ATR as % of median close (to compare across price scales)
    median_close = df_ohlc['Close'].median()
    atr_pct = (median_atr / median_close * 100) if median_close > 0 else 0

    # ── 3. Signal quality: whipsaw ratio ──
    # Total cross-ups (regardless of zone) vs signal cross-ups
    total_cross_ups = cross_up.sum()
    whipsaw_ratio = ((total_cross_ups - signals) / total_cross_ups * 100
                     if total_cross_ups > 0 else 0)

    return {
        'ticker': ticker,
        'tf': tf_label,
        'n_bars': n_bars,
        'n_valid': n_valid,
        'dtosc_os': dtosc_os,
        # Zone coverage
        'pct_os': pct_os,
        'pct_ob': pct_ob,
        'os_entries': os_entries,
        'signals': signals,
        'sig_per_mo': signals_per_month,
        # Spread / ATR
        'atr_period': atr_period,
        'med_atr': median_atr,
        'atr_pct': atr_pct,
        'spread': spread,
        'sprd_ratio': spread_ratio,
        # Quality
        'total_xup': total_cross_ups,
        'whipsaw_pct': whipsaw_ratio,
    }


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='ALTAIR Timeframe Pre-Study (Miner Checklist)')
    parser.add_argument('--ticker', nargs='+', default=TICKERS,
                        help='Tickers to analyze (default: all 5)')
    args = parser.parse_args()
    tickers = [t.upper() for t in args.ticker]

    print()
    print('=' * 100)
    print('ALTAIR TIMEFRAME PRE-STUDY -- Miner Checklist')
    print('=' * 100)
    print()
    print('DTOSC params: (%d, %d, %d, %d)  OB=%d' % (
        DTOSC_PERIOD, DTOSC_SMOOTH_K, DTOSC_SMOOTH_D, DTOSC_SIGNAL, DTOSC_OB))
    print('Spread source: hardcoded conservative estimates')
    print('TP multiplier: %.1f x ATR (for spread viability)' % TP_ATR_MULT)
    print()

    all_results = []

    for ticker in tickers:
        dtosc_os = BEST_CONFIG.get(ticker, {}).get('os', DTOSC_OS_A)

        # Load H1 from dedicated CSV
        h1_path = os.path.join(DATA_DIR, '%s_1h_8Yea.csv' % ticker)
        m5_path = os.path.join(DATA_DIR, '%s_5m_8Yea.csv' % ticker)

        if not os.path.exists(h1_path):
            print('  [SKIP] %s: no H1 CSV' % ticker)
            continue
        if not os.path.exists(m5_path):
            print('  [SKIP] %s: no 5m CSV' % ticker)
            continue

        print('  Loading %s ...' % ticker, end=' ', flush=True)
        df_h1 = load_csv(h1_path)
        df_5m = load_csv(m5_path)
        print('H1=%d bars, 5m=%d bars' % (len(df_h1), len(df_5m)))

        # Resample 5m -> 30m, 15m
        df_30m = resample_ohlcv(df_5m, '30min')
        df_15m = resample_ohlcv(df_5m, '15min')

        tf_data = {
            'H1':  df_h1,
            '30m': df_30m,
            '15m': df_15m,
        }

        for tf in TIMEFRAMES:
            result = analyze(ticker, tf, tf_data[tf], dtosc_os)
            all_results.append(result)

    # ── Print Report ─────────────────────────────────────────────────────
    print()
    print('-' * 100)
    print('SECTION 1: DTOSC ZONE COVERAGE')
    print('  Miner: oscillator must reach OS/OB on most swings.')
    print('  pct_OS/OB = %% of bars in zone. os_entries = distinct visits.')
    print('  signals = bullish crossovers from OS. sig/mo = monthly rate.')
    print('-' * 100)
    fmt = '%-6s %-4s  OS=%-2d  bars=%7d  pctOS=%5.1f%%  pctOB=%5.1f%%  ' \
          'os_vis=%4d  sigs=%4d  sig/mo=%5.2f'
    for r in all_results:
        print(fmt % (
            r['ticker'], r['tf'], r['dtosc_os'], r['n_valid'],
            r['pct_os'], r['pct_ob'], r['os_entries'],
            r['signals'], r['sig_per_mo'],
        ))

    print()
    print('-' * 100)
    print('SECTION 2: SPREAD / ATR VIABILITY (Axiom 8)')
    print('  sprd_ratio = spread / (median_ATR * TP_mult) * 100')
    print('  VIABLE if sprd_ratio < 20%%. MARGINAL 20-40%%. UNVIABLE > 40%%.')
    print('-' * 100)
    fmt2 = '%-6s %-4s  ATR(%2d)=$%7.2f  ATR%%=%5.2f%%  spread=$%.2f  ' \
           'sprd_ratio=%5.2f%%  %s'
    for r in all_results:
        if r['sprd_ratio'] < 20:
            verdict = 'VIABLE'
        elif r['sprd_ratio'] < 40:
            verdict = 'MARGINAL'
        else:
            verdict = '** UNVIABLE **'
        print(fmt2 % (
            r['ticker'], r['tf'], r['atr_period'], r['med_atr'],
            r['atr_pct'], r['spread'], r['sprd_ratio'], verdict,
        ))

    print()
    print('-' * 100)
    print('SECTION 3: SIGNAL QUALITY')
    print('  total_xup = all fast>slow crossovers.')
    print('  signals = crossovers from OS zone only (ALTAIR entries).')
    print('  whipsaw%% = crossovers NOT from OS / total (noise ratio).')
    print('-' * 100)
    fmt3 = '%-6s %-4s  total_xup=%5d  signals=%4d  whipsaw=%5.1f%%'
    for r in all_results:
        print(fmt3 % (
            r['ticker'], r['tf'], r['total_xup'],
            r['signals'], r['whipsaw_pct'],
        ))

    # ── Summary Comparison ───────────────────────────────────────────────
    print()
    print('=' * 100)
    print('SUMMARY: H1 vs 30m vs 15m')
    print('=' * 100)
    header = '%-6s %-4s  sig/mo  pctOS  pctOB  sprd%%   whip%%   ATR($)'
    print(header % ('Ticker', 'TF'))
    print('-' * 70)
    fmt_s = '%-6s %-4s  %5.2f  %5.1f  %5.1f  %5.2f   %5.1f   %7.2f'
    for r in all_results:
        print(fmt_s % (
            r['ticker'], r['tf'], r['sig_per_mo'],
            r['pct_os'], r['pct_ob'], r['sprd_ratio'],
            r['whipsaw_pct'], r['med_atr'],
        ))

    # ── Miner Diagnostic Flags ───────────────────────────────────────────
    print()
    print('=' * 100)
    print('DIAGNOSTIC FLAGS')
    print('=' * 100)
    flags = []
    for r in all_results:
        prefix = '%s %s' % (r['ticker'], r['tf'])
        if r['pct_os'] < 5.0:
            flags.append('%s: LOW OS coverage (%.1f%%) -- DTOSC rarely reaches '
                         'oversold. Consider shorter period.' % (prefix, r['pct_os']))
        if r['pct_ob'] < 5.0:
            flags.append('%s: LOW OB coverage (%.1f%%) -- DTOSC rarely reaches '
                         'overbought.' % (prefix, r['pct_ob']))
        if r['sprd_ratio'] >= 20:
            flags.append('%s: SPREAD WARNING (%.1f%%) -- spread eats >20%% of '
                         'expected profit.' % (prefix, r['sprd_ratio']))
        if r['whipsaw_pct'] > 80:
            flags.append('%s: HIGH WHIPSAW (%.1f%%) -- most crossovers are '
                         'noise, not from OS zone.' % (prefix, r['whipsaw_pct']))
        if r['sig_per_mo'] < 0.5 and r['tf'] in ('30m', '15m'):
            flags.append('%s: LOW FREQUENCY (%.2f sig/mo) -- not enough signals '
                         'to justify lower TF.' % (prefix, r['sig_per_mo']))

    if flags:
        for f in flags:
            print('  [!] %s' % f)
    else:
        print('  No flags raised. All checks passed.')

    print()


if __name__ == '__main__':
    main()
