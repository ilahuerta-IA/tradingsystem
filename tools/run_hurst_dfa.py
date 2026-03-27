"""Quick DFA Hurst regime analysis for SP500/DIA and GLD/SLV."""
import numpy as np
import pandas as pd
from pathlib import Path
from statsmodels.tsa.stattools import adfuller
from statsmodels.regression.linear_model import OLS
from statsmodels.tools import add_constant
from tools.hurst_regime_detector import load_data, resample_1h


def hurst_dfa(series):
    ts = np.asarray(series, dtype=np.float64)
    N = len(ts)
    if N < 50:
        return np.nan
    Y = np.cumsum(ts - np.mean(ts))
    min_n, max_n = 10, N // 4
    if max_n < min_n:
        return np.nan
    sizes = np.unique(np.logspace(np.log10(min_n), np.log10(max_n), 20).astype(int))
    sizes = sizes[sizes >= min_n]
    fluct, valid_sizes = [], []
    for n in sizes:
        n_seg = N // n
        if n_seg < 2:
            continue
        rms_list = []
        for seg in range(n_seg):
            segment = Y[seg * n:(seg + 1) * n]
            x = np.arange(n, dtype=np.float64)
            trend = np.polyval(np.polyfit(x, segment, 1), x)
            rms_list.append(np.sqrt(np.mean((segment - trend) ** 2)))
        fluct.append(np.mean(rms_list))
        valid_sizes.append(n)
    if len(valid_sizes) < 4:
        return np.nan
    H = np.polyfit(np.log(np.array(valid_sizes, dtype=float)),
                   np.log(np.array(fluct, dtype=float)), 1)[0]
    return np.clip(H, 0.0, 2.0)


def estimate_ou(spread):
    X = spread[:-1]
    dX = np.diff(spread)
    X_c = add_constant(X)
    try:
        m = OLS(dX, X_c).fit()
        a, b = m.params
    except Exception:
        return 0, np.nan, np.std(np.diff(spread)), np.inf
    if b >= 0:
        return 0, np.nan, np.std(dX), np.inf
    theta = -b
    mu = -a / b
    sigma = np.std(m.resid)
    hl = np.log(2) / theta
    return theta, mu, sigma, hl


DATA_DIR = Path('data')
PAIRS = [
    ('SP500', 'DIA', 'SP500_5m_5Yea.csv', 'DIA_5m_5Yea.csv'),
    ('GLD', 'SLV', 'GLD_5m_5Yea.csv', 'SLV_5m_5Yea.csv'),
]

HURST_WINDOW = 200
OLS_WINDOW = 500
STEP = 25

for name_a, name_b, file_a, file_b in PAIRS:
    print('=' * 70)
    print(f'HURST DFA REGIME ANALYSIS: {name_a} vs {name_b}')
    print('=' * 70)

    a_5m = load_data(DATA_DIR / file_a)
    b_5m = load_data(DATA_DIR / file_b)
    a_1h = resample_1h(a_5m)
    b_1h = resample_1h(b_5m)
    common = a_1h.index.intersection(b_1h.index)
    a = np.log(a_1h.loc[common]).values
    b = np.log(b_1h.loc[common]).values
    idx = a_1h.loc[common].index
    N = len(a)
    print(f'1H bars: {N} ({idx[0]} to {idx[-1]})')

    beta_full = OLS(a, add_constant(b)).fit().params[1]
    spread_full = a - beta_full * b
    spread_ret_full = np.diff(spread_full)

    print(f'Full-sample hedge ratio: {beta_full:.4f}')
    print(f'Spread (level) DFA H: {hurst_dfa(spread_full):.4f}  (stationary if <1.0)')
    print(f'Spread returns DFA H: {hurst_dfa(spread_ret_full):.4f}  (anti-persistent if <0.5)')

    results = []
    for i in range(max(OLS_WINDOW, HURST_WINDOW), N, STEP):
        w_a = a[i - OLS_WINDOW:i]
        w_b = b[i - OLS_WINDOW:i]
        beta = OLS(w_a, add_constant(w_b)).fit().params[1]

        sp = a[i - HURST_WINDOW:i] - beta * b[i - HURST_WINDOW:i]
        sp_ret = np.diff(sp)

        h_ret = hurst_dfa(sp_ret)
        h_level = hurst_dfa(sp)

        try:
            _, adf_p, _, _, _, _ = adfuller(sp, maxlag=int(len(sp) ** 0.25))
        except Exception:
            adf_p = 1.0

        theta, mu, sigma, hl = estimate_ou(sp)

        results.append({
            'datetime': idx[i],
            'beta': beta,
            'h_returns': h_ret,
            'h_level': h_level,
            'adf_p': adf_p,
            'adf_coint': adf_p < 0.05,
            'theta': theta,
            'half_life': hl,
        })

    df = pd.DataFrame(results).set_index('datetime')
    print(f'Rolling windows: {len(df)} (step={STEP})')

    # Hurst Returns Distribution
    print(f'\n--- HURST ON SPREAD RETURNS (anti-persistence detector) ---')
    h = df['h_returns']
    print(f'  Mean: {h.mean():.4f}  Median: {h.median():.4f}  Std: {h.std():.4f}')
    print(f'  Min: {h.min():.4f}  Max: {h.max():.4f}')
    for thresh in [0.30, 0.35, 0.40, 0.45, 0.50]:
        n_below = (h < thresh).sum()
        print(f'  H < {thresh}: {n_below:4d} ({n_below / len(h) * 100:5.1f}%)')

    # Cross-reference
    print(f'\n--- CROSS-REFERENCE: Hurst(returns)<0.45 vs ADF<0.05 ---')
    hurst_mr = h < 0.45
    adf_mr = df['adf_coint']
    both = (hurst_mr & adf_mr).sum()
    h_only = (hurst_mr & ~adf_mr).sum()
    a_only = (~hurst_mr & adf_mr).sum()
    neither = (~hurst_mr & ~adf_mr).sum()

    print(f'  Total: {len(df)}')
    print(f'  Hurst<0.45: {hurst_mr.sum()} ({hurst_mr.mean() * 100:.1f}%)')
    print(f'  ADF<0.05:   {adf_mr.sum()} ({adf_mr.mean() * 100:.1f}%)')
    print(f'  Both agree MR:     {both}')
    print(f'  Hurst only:        {h_only}')
    print(f'  ADF only:          {a_only}')
    print(f'  Both agree NO:     {neither}')
    if hurst_mr.sum() > 0:
        print(f'  Precision (Hurst MR -> ADF agrees): {both / hurst_mr.sum() * 100:.1f}%')
    if adf_mr.sum() > 0:
        print(f'  Recall (ADF MR -> Hurst caught): {both / adf_mr.sum() * 100:.1f}%')

    # OU params by regime
    mr_mask = hurst_mr & (df['theta'] > 0)
    non_mr_mask = ~hurst_mr & (df['theta'] > 0)

    print(f'\n--- OU PARAMETERS BY HURST REGIME ---')
    if mr_mask.sum() > 0:
        mr = df[mr_mask]
        print(f'  MR regime (H<0.45, N={len(mr)}):')
        print(f'    Theta median: {mr["theta"].median():.6f}')
        print(f'    Half-life median: {mr["half_life"].median():.1f}h = {mr["half_life"].median() / 24:.1f}d')
        print(f'    Hedge ratio std: {mr["beta"].std():.4f}')
    if non_mr_mask.sum() > 0:
        nmr = df[non_mr_mask]
        print(f'  Non-MR regime (H>=0.45, N={len(nmr)}):')
        print(f'    Theta median: {nmr["theta"].median():.6f}')
        print(f'    Half-life median: {nmr["half_life"].median():.1f}h = {nmr["half_life"].median() / 24:.1f}d')
        print(f'    Hedge ratio std: {nmr["beta"].std():.4f}')

    if mr_mask.sum() > 0 and non_mr_mask.sum() > 0:
        theta_r = mr["theta"].median() / nmr["theta"].median() if nmr["theta"].median() > 0 else float('inf')
        print(f'  Theta ratio (MR/non-MR): {theta_r:.2f}x faster')

    # Yearly breakdown
    print(f'\n--- YEARLY REGIME BREAKDOWN ---')
    print(f'{"Year":<6}{"N":<6}{"H<0.45":<12}{"ADF<0.05":<12}{"Both":<8}{"H_med":<10}')
    print('-' * 54)
    df['year'] = df.index.year
    for yr, g in df.groupby('year'):
        n = len(g)
        hmr = (g['h_returns'] < 0.45).sum()
        amr = g['adf_coint'].sum()
        b2 = ((g['h_returns'] < 0.45) & g['adf_coint']).sum()
        hmed = g['h_returns'].median()
        print(f'{yr:<6}{n:<6}{hmr:>3} ({hmr / n * 100:4.1f}%)  {amr:>3} ({amr / n * 100:4.1f}%)  {b2:>3}     {hmed:.4f}')

    print()
