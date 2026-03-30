"""
VEGA Fase 0: Cross-Index Z-Score Divergence Study.

Analyzes the statistical properties of the normalized spread between
two equity indices and its predictive value for a target FX pair.

Pairs studied:
  - SP500 vs NI225 -> USDJPY  (primary)
  - SP500 vs AUS200 -> AUDUSD (validation)

Usage:
  python tools/study_vega_zscore.py
  python tools/study_vega_zscore.py --save-only
"""
import sys
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

SAVE_ONLY = '--save-only' in sys.argv
if SAVE_ONLY:
    matplotlib.use('Agg')

OUT_DIR = Path('analysis')
OUT_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SMA_PERIOD = 24       # H1 bars = 1 trading day
ATR_PERIOD = 24       # same window for ATR
RESAMPLE_TF = '1h'    # resample M5 -> H1

PAIRS = [
    {
        'name': 'SP500_NI225_USDJPY',
        'index_a': 'SP500',
        'index_b': 'NI225',
        'fx': 'USDJPY',
        'label_a': 'SP500',
        'label_b': 'NI225',
        'label_fx': 'USDJPY',
    },
    {
        'name': 'SP500_AUS200_AUDUSD',
        'index_a': 'SP500',
        'index_b': 'AUS200',
        'fx': 'AUDUSD',
        'label_a': 'SP500',
        'label_b': 'AUS200',
        'label_fx': 'AUDUSD',
    },
]

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_m5(symbol):
    """Load Dukascopy M5 CSV and return OHLCV DataFrame with datetime index."""
    path = Path(f'data/{symbol}_5m_5Yea.csv')
    if not path.exists():
        print(f'  ERROR: file not found: {path}')
        sys.exit(1)
    df = pd.read_csv(path)
    df['datetime'] = pd.to_datetime(
        df['Date'].astype(str) + ' ' + df['Time'],
        format='%Y%m%d %H:%M:%S',
    )
    df.set_index('datetime', inplace=True)
    df.columns = [c.lower() for c in df.columns]
    return df[['open', 'high', 'low', 'close', 'volume']]


def resample_to_h1(df):
    """Resample M5 OHLCV to H1."""
    return df.resample(RESAMPLE_TF).agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum',
    }).dropna()


def calc_atr(df, period):
    """Calculate ATR on OHLCV dataframe."""
    tr = pd.concat([
        df['high'] - df['low'],
        (df['high'] - df['close'].shift(1)).abs(),
        (df['low'] - df['close'].shift(1)).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def calc_zscore(df, sma_period, atr_period):
    """z = (close - SMA) / ATR. Returns Series."""
    sma = df['close'].rolling(sma_period).mean()
    atr = calc_atr(df, atr_period)
    z = (df['close'] - sma) / atr
    return z


# ---------------------------------------------------------------------------
# Analysis functions
# ---------------------------------------------------------------------------

def analyze_pair(pair_cfg):
    """Full analysis for one index pair -> FX target."""
    name = pair_cfg['name']
    print(f'\n{"="*70}')
    print(f' PAIR: {pair_cfg["label_a"]} vs {pair_cfg["label_b"]} -> {pair_cfg["label_fx"]}')
    print(f'{"="*70}')

    # Load and resample
    print(f'  Loading {pair_cfg["index_a"]}...')
    a_m5 = load_m5(pair_cfg['index_a'])
    a_h1 = resample_to_h1(a_m5)
    print(f'    M5: {len(a_m5)} bars, H1: {len(a_h1)} bars')

    print(f'  Loading {pair_cfg["index_b"]}...')
    b_m5 = load_m5(pair_cfg['index_b'])
    b_h1 = resample_to_h1(b_m5)
    print(f'    M5: {len(b_m5)} bars, H1: {len(b_h1)} bars')

    print(f'  Loading {pair_cfg["fx"]}...')
    fx_m5 = load_m5(pair_cfg['fx'])
    fx_h1 = resample_to_h1(fx_m5)
    print(f'    M5: {len(fx_m5)} bars, H1: {len(fx_h1)} bars')

    # Align on common index
    common = a_h1.index.intersection(b_h1.index).intersection(fx_h1.index)
    print(f'  Common H1 bars: {len(common)} ({common[0].date()} to {common[-1].date()})')

    a_h1 = a_h1.loc[common]
    b_h1 = b_h1.loc[common]
    fx_h1 = fx_h1.loc[common]

    # Z-scores
    z_a = calc_zscore(a_h1, SMA_PERIOD, ATR_PERIOD)
    z_b = calc_zscore(b_h1, SMA_PERIOD, ATR_PERIOD)
    spread = (z_a - z_b).dropna()
    spread.name = 'spread'

    # FX returns at various horizons
    fx_ret = {}
    for h in [1, 2, 3, 6, 12, 24]:
        fx_ret[h] = fx_h1['close'].pct_change(h).shift(-h)

    # Combine
    data = pd.DataFrame({
        'spread': spread,
        'z_a': z_a,
        'z_b': z_b,
        'fx_close': fx_h1['close'],
    })
    for h, ret in fx_ret.items():
        data[f'fx_ret_{h}h'] = ret
    data = data.dropna()
    data['hour'] = data.index.hour
    data['year'] = data.index.year

    print(f'  Analysis rows: {len(data)}')

    # --- 1. Spread distribution ---
    print(f'\n  --- Spread Statistics ---')
    print(f'  Mean:   {data["spread"].mean():.4f}')
    print(f'  Std:    {data["spread"].std():.4f}')
    print(f'  Skew:   {data["spread"].skew():.4f}')
    print(f'  Kurt:   {data["spread"].kurtosis():.4f}')
    print(f'  Min:    {data["spread"].min():.4f}')
    print(f'  Max:    {data["spread"].max():.4f}')
    q = data['spread'].quantile([0.01, 0.05, 0.10, 0.25, 0.75, 0.90, 0.95, 0.99])
    print(f'  Q1%:    {q.iloc[0]:.4f}')
    print(f'  Q5%:    {q.iloc[1]:.4f}')
    print(f'  Q95%:   {q.iloc[5]:.4f}')
    print(f'  Q99%:   {q.iloc[6]:.4f}')

    # --- 2. Autocorrelation ---
    print(f'\n  --- Autocorrelation of Spread ---')
    max_lag = 48
    acf = [data['spread'].autocorr(lag=i) for i in range(1, max_lag + 1)]
    print(f'  Lag  1h: {acf[0]:.4f}')
    print(f'  Lag  2h: {acf[1]:.4f}')
    print(f'  Lag  6h: {acf[5]:.4f}')
    print(f'  Lag 12h: {acf[11]:.4f}')
    print(f'  Lag 24h: {acf[23]:.4f}')
    print(f'  Lag 48h: {acf[47]:.4f}')
    mean_reversion = acf[0] > 0.5
    momentum = acf[0] > 0.9
    if momentum:
        print(f'  >> HIGH persistence (acf1={acf[0]:.3f}): spread has MOMENTUM')
    elif mean_reversion:
        print(f'  >> MODERATE persistence (acf1={acf[0]:.3f}): partial reversion')
    else:
        print(f'  >> LOW persistence (acf1={acf[0]:.3f}): fast mean-reversion')

    # --- 3. Predictive value ---
    print(f'\n  --- Predictive Value: spread_t vs FX_return_{"{"}h{"}"} ---')
    print(f'  {"Horizon":>8s}  {"Corr":>8s}  {"p-value":>10s}  {"Direction":>10s}')
    from scipy import stats
    pred_results = {}
    for h in [1, 2, 3, 6, 12, 24]:
        col = f'fx_ret_{h}h'
        mask = data[col].notna()
        r, p = stats.pearsonr(data.loc[mask, 'spread'], data.loc[mask, col])
        direction = 'LONG' if r > 0 else 'SHORT'
        sig = '***' if p < 0.001 else '**' if p < 0.01 else '*' if p < 0.05 else ''
        print(f'  {h:>6d}h  {r:>8.4f}  {p:>10.2e}  {direction:>6s} {sig}')
        pred_results[h] = (r, p)

    # --- 4. Heatmap by hour ---
    print(f'\n  --- Mean Spread by Hour (UTC) ---')
    hourly = data.groupby('hour').agg(
        mean_spread=('spread', 'mean'),
        std_spread=('spread', 'std'),
        count=('spread', 'count'),
    )
    # Predictive power by hour: corr(spread, fx_ret_6h) per hour
    hourly_pred = []
    for hr in range(24):
        mask = data['hour'] == hr
        sub = data.loc[mask].dropna(subset=['fx_ret_6h'])
        if len(sub) > 50:
            r, p = stats.pearsonr(sub['spread'], sub['fx_ret_6h'])
            hourly_pred.append({'hour': hr, 'corr_6h': r, 'pval': p, 'n': len(sub)})
        else:
            hourly_pred.append({'hour': hr, 'corr_6h': np.nan, 'pval': np.nan, 'n': len(sub)})
    hourly_pred = pd.DataFrame(hourly_pred).set_index('hour')

    print(f'  {"Hour":>4s}  {"Mean":>7s}  {"Std":>7s}  {"Corr6h":>7s}  {"pval":>10s}  {"N":>6s}')
    for hr in range(24):
        if hr in hourly.index:
            row = hourly.loc[hr]
            pr = hourly_pred.loc[hr]
            sig = '*' if pr['pval'] < 0.05 else ''
            print(f'  {hr:>4d}  {row["mean_spread"]:>7.3f}  {row["std_spread"]:>7.3f}'
                  f'  {pr["corr_6h"]:>7.4f}  {pr["pval"]:>10.2e}  {pr["n"]:>6.0f} {sig}')

    # --- 5. Regime stability by year ---
    print(f'\n  --- Regime Stability: Spread Stats by Year ---')
    yearly = data.groupby('year').agg(
        mean=('spread', 'mean'),
        std=('spread', 'std'),
        skew=('spread', lambda x: x.skew()),
        count=('spread', 'count'),
    )
    print(f'  {"Year":>4s}  {"Mean":>7s}  {"Std":>6s}  {"Skew":>6s}  {"N":>6s}')
    for year, row in yearly.iterrows():
        print(f'  {year:>4d}  {row["mean"]:>7.3f}  {row["std"]:>6.3f}'
              f'  {row["skew"]:>6.3f}  {row["count"]:>6.0f}')

    # --- 6. Yearly predictive corr ---
    print(f'\n  --- Yearly Predictive Corr: spread vs fx_ret_6h ---')
    print(f'  {"Year":>4s}  {"Corr":>8s}  {"pval":>10s}  {"N":>6s}')
    for year in sorted(data['year'].unique()):
        sub = data[data['year'] == year].dropna(subset=['fx_ret_6h'])
        if len(sub) > 50:
            r, p = stats.pearsonr(sub['spread'], sub['fx_ret_6h'])
            sig = '*' if p < 0.05 else ''
            print(f'  {year:>4d}  {r:>8.4f}  {p:>10.2e}  {len(sub):>6d} {sig}')

    # ---------------------------------------------------------------------------
    # PLOTS
    # ---------------------------------------------------------------------------
    fig, axes = plt.subplots(3, 2, figsize=(16, 14))
    fig.suptitle(f'VEGA Fase 0: {pair_cfg["label_a"]} vs {pair_cfg["label_b"]}'
                 f' -> {pair_cfg["label_fx"]}', fontsize=14, fontweight='bold')

    # Plot 1: Spread distribution
    ax = axes[0, 0]
    ax.hist(data['spread'], bins=200, density=True, alpha=0.7, color='steelblue')
    ax.axvline(0, color='black', linewidth=0.8)
    ax.axvline(data['spread'].quantile(0.05), color='red', linestyle='--', label='5%/95%')
    ax.axvline(data['spread'].quantile(0.95), color='red', linestyle='--')
    ax.set_title('Spread Distribution')
    ax.set_xlabel('z_A - z_B')
    ax.legend()

    # Plot 2: Autocorrelation
    ax = axes[0, 1]
    ax.bar(range(1, max_lag + 1), acf, color='steelblue', alpha=0.7)
    ax.axhline(0, color='black', linewidth=0.8)
    ax.axhline(1.96 / np.sqrt(len(data)), color='red', linestyle='--', alpha=0.5)
    ax.axhline(-1.96 / np.sqrt(len(data)), color='red', linestyle='--', alpha=0.5)
    ax.set_title('Spread Autocorrelation')
    ax.set_xlabel('Lag (hours)')
    ax.set_ylabel('ACF')

    # Plot 3: Predictive correlation by horizon
    ax = axes[1, 0]
    horizons = [1, 2, 3, 6, 12, 24]
    corrs = [pred_results[h][0] for h in horizons]
    pvals = [pred_results[h][1] for h in horizons]
    colors = ['green' if p < 0.05 else 'gray' for p in pvals]
    ax.bar([str(h) for h in horizons], corrs, color=colors, alpha=0.7)
    ax.axhline(0, color='black', linewidth=0.8)
    ax.set_title(f'Predictive Corr: spread_t vs {pair_cfg["label_fx"]}_ret')
    ax.set_xlabel('Horizon (hours)')
    ax.set_ylabel('Pearson r')

    # Plot 4: Hourly predictive heatmap
    ax = axes[1, 1]
    hrs = hourly_pred.index.values
    corr_vals = hourly_pred['corr_6h'].values
    colors_hr = ['green' if hourly_pred.loc[h, 'pval'] < 0.05 else 'gray'
                 for h in hrs]
    ax.bar(hrs, corr_vals, color=colors_hr, alpha=0.7)
    ax.axhline(0, color='black', linewidth=0.8)
    ax.set_title('Predictive Corr by Hour UTC (6h horizon)')
    ax.set_xlabel('Hour (UTC)')
    ax.set_ylabel('Pearson r')
    ax.set_xticks(range(0, 24, 2))

    # Plot 5: Spread time series (last 2 years)
    ax = axes[2, 0]
    recent = data[data.index >= '2024-01-01']
    ax.plot(recent.index, recent['spread'], linewidth=0.3, color='steelblue')
    ax.axhline(0, color='black', linewidth=0.8)
    q5 = data['spread'].quantile(0.05)
    q95 = data['spread'].quantile(0.95)
    ax.axhline(q95, color='red', linestyle='--', alpha=0.5, label=f'Q95={q95:.2f}')
    ax.axhline(q5, color='red', linestyle='--', alpha=0.5, label=f'Q5={q5:.2f}')
    ax.set_title('Spread Time Series (2024-2026)')
    ax.set_ylabel('z_A - z_B')
    ax.legend()

    # Plot 6: Scatter spread vs fx_ret_6h
    ax = axes[2, 1]
    # subsample for readability
    sample = data.dropna(subset=['fx_ret_6h']).sample(min(5000, len(data)), random_state=42)
    ax.scatter(sample['spread'], sample['fx_ret_6h'] * 100, alpha=0.1, s=1, color='steelblue')
    ax.axhline(0, color='black', linewidth=0.5)
    ax.axvline(0, color='black', linewidth=0.5)
    # add binned means
    bins = pd.cut(data['spread'], bins=20)
    binned = data.groupby(bins, observed=True)['fx_ret_6h'].mean() * 100
    bin_centers = [(b.left + b.right) / 2 for b in binned.index]
    ax.plot(bin_centers, binned.values, 'ro-', linewidth=2, markersize=4, label='Binned mean')
    ax.set_title(f'Spread vs {pair_cfg["label_fx"]} Return 6h')
    ax.set_xlabel('spread (z_A - z_B)')
    ax.set_ylabel(f'{pair_cfg["label_fx"]} return 6h (%)')
    ax.legend()

    plt.tight_layout()
    out_path = OUT_DIR / f'vega_fase0_{name}.png'
    plt.savefig(out_path, dpi=150, bbox_inches='tight')
    print(f'\n  Chart saved: {out_path}')
    if not SAVE_ONLY:
        plt.show()
    plt.close()

    return data, pred_results, acf


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print('=' * 70)
    print(' VEGA FASE 0: CROSS-INDEX Z-SCORE DIVERGENCE STUDY')
    print(f' SMA={SMA_PERIOD}h, ATR={ATR_PERIOD}h, resample={RESAMPLE_TF}')
    print('=' * 70)

    results = {}
    for pair in PAIRS:
        data, pred, acf = analyze_pair(pair)
        results[pair['name']] = {
            'data': data,
            'pred': pred,
            'acf': acf,
        }

    # ---------------------------------------------------------------------------
    # Summary comparison
    # ---------------------------------------------------------------------------
    print(f'\n{"="*70}')
    print(f' SUMMARY COMPARISON')
    print(f'{"="*70}')
    print(f'  {"Pair":>30s}  {"ACF(1h)":>8s}  {"ACF(24h)":>8s}'
          f'  {"Corr6h":>8s}  {"pval6h":>10s}')
    for pair in PAIRS:
        r = results[pair['name']]
        acf1 = r['acf'][0]
        acf24 = r['acf'][23]
        corr6, pval6 = r['pred'][6]
        sig = '***' if pval6 < 0.001 else '**' if pval6 < 0.01 else '*' if pval6 < 0.05 else ''
        print(f'  {pair["name"]:>30s}  {acf1:>8.4f}  {acf24:>8.4f}'
              f'  {corr6:>8.4f}  {pval6:>10.2e} {sig}')

    print(f'\n  Interpretation:')
    print(f'  - ACF(1h) > 0.9: spread is persistent (momentum property)')
    print(f'  - ACF(1h) < 0.5: spread reverts quickly')
    print(f'  - Corr6h > 0 with p<0.05: spread predicts LONG {PAIRS[0]["label_fx"]}')
    print(f'  - Corr6h < 0 with p<0.05: spread predicts SHORT {PAIRS[0]["label_fx"]}')
    print(f'  - Green bars in plots = statistically significant (p<0.05)')


if __name__ == '__main__':
    main()
