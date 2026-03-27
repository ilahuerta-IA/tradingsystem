"""
Hurst Exponent + Ornstein-Uhlenbeck Regime Detector
====================================================
Camino B: Replace static cointegration tests with dynamic regime detection.

Key question: Can the Hurst exponent identify mean-reverting windows in real-time,
acting as an ON/OFF switch for a stat-arb bot?

Tests:
1. Rolling Hurst Exponent (Rescaled Range method) on spread
2. Rolling OU parameter estimation (theta, mu, sigma)
3. Cross-reference: When H < 0.45, does ADF also confirm stationarity?
4. Predictive power: Does Hurst LEAD cointegration state changes?

Usage:
    python tools/hurst_regime_detector.py
"""

import numpy as np
import pandas as pd
from pathlib import Path
from statsmodels.tsa.stattools import adfuller
from statsmodels.regression.linear_model import OLS
from statsmodels.tools import add_constant

# ── Config ──────────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).resolve().parent.parent / 'data'
ASSET_A_FILE = DATA_DIR / 'SP500_5m_5Yea.csv'
ASSET_B_FILE = DATA_DIR / 'DIA_5m_5Yea.csv'
ASSET_A_NAME = 'SP500'
ASSET_B_NAME = 'DIA'

HURST_WINDOW = 200       # bars for rolling Hurst
ADF_WINDOW = 200          # bars for rolling ADF (same window for comparison)
OLS_WINDOW = 500          # bars for rolling hedge ratio (longer for stability)
OU_WINDOW = 200           # bars for OU parameter estimation
STEP = 50                 # step between rolling evaluations (1H bars)

HURST_THRESHOLD = 0.45    # Below this = mean-reverting regime
ADF_THRESHOLD = 0.05      # Below this = cointegrated


# ── Data Loading ────────────────────────────────────────────────────────
def load_data(filepath):
    """Load 5min CSV and return close prices as Series."""
    df = pd.read_csv(filepath, header=0)
    df.columns = [c.strip() for c in df.columns]
    df['Datetime'] = pd.to_datetime(
        df['Date'].astype(str) + ' ' + df['Time'].astype(str),
        format='%Y%m%d %H:%M:%S'
    )
    df.set_index('Datetime', inplace=True)
    return df['Close']


def resample_1h(series):
    """Resample 5min close to 1H using last price."""
    return series.resample('1h').last().dropna()


# ── Hurst Exponent (Rescaled Range) ────────────────────────────────────
def hurst_rs(series):
    """
    Calculate Hurst exponent using the Rescaled Range (R/S) method.

    H < 0.5: Mean-reverting (anti-persistent)
    H = 0.5: Random walk
    H > 0.5: Trending (persistent)

    Uses multiple sub-series lengths for robust estimation.
    """
    ts = np.asarray(series, dtype=np.float64)
    N = len(ts)
    if N < 20:
        return np.nan

    # Use logarithmically spaced chunk sizes from 10 to N/2
    max_k = N // 2
    min_k = 10
    if max_k < min_k:
        return np.nan

    # Generate ~12 log-spaced sizes
    sizes = np.unique(np.logspace(
        np.log10(min_k), np.log10(max_k), num=15
    ).astype(int))
    sizes = sizes[sizes >= min_k]

    if len(sizes) < 4:
        return np.nan

    rs_means = []
    valid_sizes = []

    for n in sizes:
        num_chunks = N // n
        if num_chunks < 1:
            continue

        rs_values = []
        for i in range(num_chunks):
            chunk = ts[i * n:(i + 1) * n]
            mean_chunk = np.mean(chunk)
            deviations = np.cumsum(chunk - mean_chunk)
            R = np.max(deviations) - np.min(deviations)
            S = np.std(chunk, ddof=1)
            if S > 1e-12:
                rs_values.append(R / S)

        if len(rs_values) > 0:
            rs_means.append(np.mean(rs_values))
            valid_sizes.append(n)

    if len(valid_sizes) < 4:
        return np.nan

    # Linear regression: log(R/S) = H * log(n) + c
    log_sizes = np.log(np.array(valid_sizes, dtype=np.float64))
    log_rs = np.log(np.array(rs_means, dtype=np.float64))

    # Simple least squares
    coeffs = np.polyfit(log_sizes, log_rs, 1)
    H = coeffs[0]

    # Clamp to reasonable range
    return np.clip(H, 0.0, 1.0)


# ── Ornstein-Uhlenbeck Parameter Estimation ────────────────────────────
def estimate_ou_params(spread, dt=1.0):
    """
    Estimate OU parameters from discrete observations.
    dX = theta*(mu - X)*dt + sigma*dW

    Returns: (theta, mu, sigma, half_life)
    Using OLS on: X_{t+1} - X_t = a + b*X_t + epsilon
    where theta = -b/dt, mu = -a/b, sigma = std(epsilon)/sqrt(dt)
    """
    spread = np.asarray(spread, dtype=np.float64)
    if len(spread) < 10:
        return np.nan, np.nan, np.nan, np.nan

    X = spread[:-1]
    dX = np.diff(spread)

    X_const = add_constant(X)
    try:
        model = OLS(dX, X_const).fit()
        a, b = model.params
    except Exception:
        return np.nan, np.nan, np.nan, np.nan

    if b >= 0:  # No mean reversion
        return 0.0, np.nan, np.std(dX), np.inf

    theta = -b / dt
    mu = -a / b
    sigma = np.std(model.resid) / np.sqrt(dt)
    half_life = np.log(2) / theta if theta > 0 else np.inf

    return theta, mu, sigma, half_life


# ── Optimal Z-Score Entry (OU-based) ───────────────────────────────────
def optimal_zscore_entry(theta, sigma, transaction_cost_pct=0.001):
    """
    Calculate optimal Z-score entry level based on OU parameters and costs.
    Based on: z_opt = sqrt(2 * cost / (sigma^2 / (2*theta)))
    Simplified: entry where expected profit > transaction cost.
    """
    if theta <= 0 or sigma <= 0:
        return np.nan
    variance_rate = sigma**2 / (2 * theta)
    if variance_rate <= 0:
        return np.nan
    z_opt = np.sqrt(2 * transaction_cost_pct / variance_rate)
    # Practical floor/ceiling
    return np.clip(z_opt, 0.5, 4.0)


# ── Main Analysis ──────────────────────────────────────────────────────
def main():
    print('=' * 70)
    print(f'HURST + OU REGIME DETECTOR: {ASSET_A_NAME} vs {ASSET_B_NAME}')
    print('=' * 70)

    # Load and align
    a_5m = load_data(ASSET_A_FILE)
    b_5m = load_data(ASSET_B_FILE)
    a_1h = resample_1h(a_5m)
    b_1h = resample_1h(b_5m)

    common = a_1h.index.intersection(b_1h.index)
    a = a_1h.loc[common]
    b = b_1h.loc[common]
    print(f'1H aligned: {len(a)} bars ({a.index[0]} to {a.index[-1]})')

    log_a = np.log(a)
    log_b = np.log(b)

    # ── Compute spread with rolling hedge ratio ─────────────────────
    print(f'\nComputing spread (OLS rolling window={OLS_WINDOW})...')

    n = len(log_a)
    indices = list(range(OLS_WINDOW, n, STEP))
    results = []

    for i in indices:
        idx = log_a.index[i]

        # Rolling OLS for hedge ratio
        window_a = log_a.values[i - OLS_WINDOW:i]
        window_b = log_b.values[i - OLS_WINDOW:i]
        model = OLS(window_a, add_constant(window_b)).fit()
        hedge_ratio = model.params[1]

        # Current spread using this hedge ratio
        # Use spread over HURST_WINDOW bars ending at i
        start_h = max(0, i - HURST_WINDOW)
        spread_window = log_a.values[start_h:i] - hedge_ratio * log_b.values[start_h:i]

        if len(spread_window) < HURST_WINDOW * 0.8:
            continue

        # Hurst exponent on spread
        H = hurst_rs(spread_window)

        # ADF on spread (same window)
        try:
            adf_stat, adf_p, _, _, _, _ = adfuller(spread_window, maxlag=int(len(spread_window)**0.25))
        except Exception:
            adf_p = 1.0

        # OU parameters on spread
        theta, mu, sigma_ou, half_life = estimate_ou_params(spread_window)

        # Z-Score of current spread value
        spread_mean = np.mean(spread_window)
        spread_std = np.std(spread_window)
        zscore = (spread_window[-1] - spread_mean) / spread_std if spread_std > 1e-10 else 0

        results.append({
            'datetime': idx,
            'hedge_ratio': hedge_ratio,
            'hurst': H,
            'adf_p': adf_p,
            'adf_cointegrated': adf_p < ADF_THRESHOLD,
            'hurst_meanrev': H < HURST_THRESHOLD if not np.isnan(H) else False,
            'theta': theta,
            'mu': mu,
            'sigma_ou': sigma_ou,
            'half_life_hours': half_life,
            'zscore': zscore,
            'spread_std': spread_std,
        })

    df = pd.DataFrame(results)
    df.set_index('datetime', inplace=True)
    print(f'Computed {len(df)} rolling windows (step={STEP} bars)')

    # ── Analysis 1: Hurst Distribution ──────────────────────────────
    print('\n' + '=' * 70)
    print('1. HURST EXPONENT DISTRIBUTION')
    print('=' * 70)
    print(f'  Mean:   {df["hurst"].mean():.4f}')
    print(f'  Median: {df["hurst"].median():.4f}')
    print(f'  Std:    {df["hurst"].std():.4f}')
    print(f'  Min:    {df["hurst"].min():.4f}')
    print(f'  Max:    {df["hurst"].max():.4f}')
    print(f'\n  H < 0.40 (strong MR):   {(df["hurst"] < 0.40).sum():4d} ({(df["hurst"] < 0.40).mean()*100:.1f}%)')
    print(f'  H < 0.45 (mean-rev):    {(df["hurst"] < 0.45).sum():4d} ({(df["hurst"] < 0.45).mean()*100:.1f}%)')
    print(f'  0.45 <= H <= 0.55 (RW): {((df["hurst"] >= 0.45) & (df["hurst"] <= 0.55)).sum():4d} ({((df["hurst"] >= 0.45) & (df["hurst"] <= 0.55)).mean()*100:.1f}%)')
    print(f'  H > 0.55 (trending):    {(df["hurst"] > 0.55).sum():4d} ({(df["hurst"] > 0.55).mean()*100:.1f}%)')

    # ── Analysis 2: Cross-reference Hurst vs ADF ────────────────────
    print('\n' + '=' * 70)
    print('2. CROSS-REFERENCE: HURST vs ADF (THE KEY QUESTION)')
    print('=' * 70)

    total = len(df)
    adf_yes = df['adf_cointegrated'].sum()
    hurst_yes = df['hurst_meanrev'].sum()
    both = (df['adf_cointegrated'] & df['hurst_meanrev']).sum()
    neither = (~df['adf_cointegrated'] & ~df['hurst_meanrev']).sum()
    hurst_only = (df['hurst_meanrev'] & ~df['adf_cointegrated']).sum()
    adf_only = (df['adf_cointegrated'] & ~df['hurst_meanrev']).sum()

    print(f'\n  Total windows: {total}')
    print(f'  ADF says cointegrated (p<0.05):  {adf_yes:4d} ({adf_yes/total*100:.1f}%)')
    print(f'  Hurst says mean-reverting (<0.45): {hurst_yes:4d} ({hurst_yes/total*100:.1f}%)')
    print(f'\n  Confusion matrix:')
    print(f'                         ADF: YES    ADF: NO')
    print(f'    Hurst < 0.45 (MR):  {both:5d}      {hurst_only:5d}')
    print(f'    Hurst >= 0.45:      {adf_only:5d}      {neither:5d}')

    # Precision and recall (treating ADF as "ground truth")
    if hurst_yes > 0:
        precision = both / hurst_yes
        print(f'\n  Precision (when Hurst says MR, ADF agrees): {precision*100:.1f}%')
    if adf_yes > 0:
        recall = both / adf_yes
        print(f'  Recall (of ADF-confirmed windows, Hurst caught): {recall*100:.1f}%')

    # Agreement rate
    agreement = (both + neither) / total
    print(f'  Overall agreement: {agreement*100:.1f}%')

    # ── Analysis 3: Hurst as PREDICTIVE filter ──────────────────────
    print('\n' + '=' * 70)
    print('3. PREDICTIVE POWER: Does Hurst LEAD regime changes?')
    print('=' * 70)

    # Check: when Hurst drops below 0.45, does ADF confirm within next 1-3 steps?
    hurst_signal = df['hurst'] < HURST_THRESHOLD
    adf_signal = df['adf_cointegrated']

    # Forward-looking: after Hurst goes below threshold, does ADF confirm within N steps?
    for lookahead in [1, 2, 3]:
        adf_forward = adf_signal.rolling(lookahead, min_periods=1).max().shift(-lookahead).fillna(0).astype(bool)
        hurst_then_adf = (hurst_signal & adf_forward).sum()
        if hurst_signal.sum() > 0:
            hit_rate = hurst_then_adf / hurst_signal.sum()
            print(f'  Hurst<0.45 → ADF confirms within {lookahead} step(s): {hurst_then_adf}/{hurst_signal.sum()} ({hit_rate*100:.1f}%)')

    # Reverse: does Hurst drop BEFORE ADF confirms?
    print(f'\n  Checking lead/lag...')
    hurst_entries = df.index[hurst_signal & ~hurst_signal.shift(1).fillna(False)]
    lead_count = 0
    lag_count = 0
    simultaneous = 0
    for entry_time in hurst_entries:
        pos = df.index.get_loc(entry_time)
        # Look ±5 steps for nearest ADF confirmation
        for offset in range(0, 6):
            if pos + offset < len(df) and df['adf_cointegrated'].iloc[pos + offset]:
                if offset == 0:
                    simultaneous += 1
                else:
                    lead_count += 1
                break
            if pos - offset >= 0 and offset > 0 and df['adf_cointegrated'].iloc[pos - offset]:
                lag_count += 1
                break

    print(f'  Hurst entry events: {len(hurst_entries)}')
    print(f'  Hurst LEADS ADF:    {lead_count} (Hurst drops first, ADF confirms later)')
    print(f'  Simultaneous:       {simultaneous}')
    print(f'  Hurst LAGS ADF:     {lag_count} (ADF already confirmed)')

    # ── Analysis 4: OU Parameters in Mean-Reverting Regimes ─────────
    print('\n' + '=' * 70)
    print('4. ORNSTEIN-UHLENBECK PARAMS BY REGIME')
    print('=' * 70)

    mr = df[df['hurst_meanrev'] & (df['theta'] > 0)]
    non_mr = df[~df['hurst_meanrev'] & (df['theta'] > 0)]

    if len(mr) > 0:
        print(f'\n  MEAN-REVERTING regime (H<0.45, N={len(mr)}):')
        print(f'    Theta (speed):     mean={mr["theta"].mean():.6f}  median={mr["theta"].median():.6f}')
        print(f'    Half-life (hours): mean={mr["half_life_hours"].mean():.1f}  median={mr["half_life_hours"].median():.1f}')
        print(f'    Sigma (vol):       mean={mr["sigma_ou"].mean():.6f}')
        hl_days = mr["half_life_hours"].median() / 24
        print(f'    Half-life (days):  median={hl_days:.1f}')
    else:
        print('\n  NO mean-reverting windows found!')

    if len(non_mr) > 0:
        print(f'\n  NON-REVERTING regime (H>=0.45, N={len(non_mr)}):')
        print(f'    Theta (speed):     mean={non_mr["theta"].mean():.6f}  median={non_mr["theta"].median():.6f}')
        print(f'    Half-life (hours): mean={non_mr["half_life_hours"].mean():.1f}  median={non_mr["half_life_hours"].median():.1f}')
        print(f'    Sigma (vol):       mean={non_mr["sigma_ou"].mean():.6f}')

    if len(mr) > 0 and len(non_mr) > 0:
        theta_ratio = mr["theta"].median() / non_mr["theta"].median() if non_mr["theta"].median() > 0 else np.inf
        print(f'\n  Theta ratio (MR/non-MR): {theta_ratio:.2f}x faster reversion in MR regime')

    # ── Analysis 5: Yearly Hurst Regime Breakdown ───────────────────
    print('\n' + '=' * 70)
    print('5. YEARLY REGIME BREAKDOWN')
    print('=' * 70)
    print(f'{"Year":<6} {"Windows":<9} {"H<0.40":<9} {"H<0.45":<9} {"0.45-0.55":<10} {"H>0.55":<9} {"ADF<0.05":<9} {"Both":<6}')
    print('-' * 67)

    df['year'] = df.index.year
    for year, grp in df.groupby('year'):
        n = len(grp)
        h40 = (grp['hurst'] < 0.40).sum()
        h45 = (grp['hurst'] < 0.45).sum()
        rw = ((grp['hurst'] >= 0.45) & (grp['hurst'] <= 0.55)).sum()
        tr = (grp['hurst'] > 0.55).sum()
        adf = grp['adf_cointegrated'].sum()
        both_yr = (grp['adf_cointegrated'] & grp['hurst_meanrev']).sum()
        print(f'{year:<6} {n:<9} {h40:>3} ({h40/n*100:4.1f}%) {h45:>3} ({h45/n*100:4.1f}%) {rw:>3} ({rw/n*100:4.1f}%)  {tr:>3} ({tr/n*100:4.1f}%) {adf:>3} ({adf/n*100:4.1f}%) {both_yr:>3}')

    # ── Analysis 6: Actionable Summary ──────────────────────────────
    print('\n' + '=' * 70)
    print('6. ACTIONABLE SUMMARY')
    print('=' * 70)

    mr_pct = df['hurst_meanrev'].mean() * 100
    if mr_pct > 30:
        print(f'  ✓ Mean-reverting regime detected {mr_pct:.0f}% of the time → VIABLE for stat-arb')
    elif mr_pct > 15:
        print(f'  ~ Mean-reverting regime detected {mr_pct:.0f}% of the time → MARGINAL')
    else:
        print(f'  ✗ Mean-reverting regime detected {mr_pct:.0f}% of the time → INSUFFICIENT')

    if len(mr) > 0:
        median_hl = mr["half_life_hours"].median()
        if median_hl < 48:
            print(f'  ✓ Median half-life in MR regime: {median_hl:.0f}h → FAST enough for intraday/swing')
        elif median_hl < 240:
            print(f'  ~ Median half-life in MR regime: {median_hl:.0f}h → Swing only')
        else:
            print(f'  ✗ Median half-life in MR regime: {median_hl:.0f}h → TOO SLOW')

    if hurst_yes > 0:
        if precision > 0.4:
            print(f'  ✓ Hurst precision (agreement with ADF): {precision*100:.0f}% → RELIABLE filter')
        elif precision > 0.2:
            print(f'  ~ Hurst precision (agreement with ADF): {precision*100:.0f}% → PARTIAL filter')
        else:
            print(f'  ✗ Hurst precision (agreement with ADF): {precision*100:.0f}% → POOR filter')


if __name__ == '__main__':
    main()
