"""
VEGA Fase 0c: Direct Index Trading via Z-Score Divergence.

Pivot from Fase 0b: instead of trading FX, trade the LAGGING index directly.
When SP500 leads NI225 (z_SP500 > z_NI225), long NI225 expecting convergence.

Study structure:
  1. Predictive power: spread(t) vs index_B return(t+h)
  2. Quintile analysis: conditional returns of lagging index
  3. Naive PnL: forecast-proportional sizing on the index
  4. Both directions: long lagging + short leading (and each alone)
  5. FX as optional confirmation filter
  6. Session filtering (carry over insight from 0b)
  7. Bootstrap CI + permutation tests
  8. Yearly stability
  9. Multi-pair: SP500/NI225, SP500/AUS200

Usage:
  python tools/study_vega_index.py
  python tools/study_vega_index.py --save-only
"""
import sys
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

SAVE_ONLY = '--save-only' in sys.argv
if SAVE_ONLY:
    matplotlib.use('Agg')

OUT_DIR = Path('analysis')
OUT_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SMA_PERIOD = 24
ATR_PERIOD = 24

SESSIONS = {
    'Tokyo':    (0, 5),
    'London':   (7, 12),
    'NY_Close': (17, 20),
    'All':      (0, 23),
}

INDEX_PAIRS = [
    {
        'name': 'SP500_vs_NI225',
        'index_a': 'SP500', 'index_b': 'NI225',
        'fx': 'USDJPY',
        'label': 'SP500 leads -> long NI225',
    },
    {
        'name': 'SP500_vs_AUS200',
        'index_a': 'SP500', 'index_b': 'AUS200',
        'fx': 'AUDUSD',
        'label': 'SP500 leads -> long AUS200',
    },
]

HORIZONS = [1, 2, 3, 6, 12, 24]
N_BOOTSTRAP = 1000
N_PERMUTATIONS = 2000


# ---------------------------------------------------------------------------
# Data loading (shared with Fase 0/0b)
# ---------------------------------------------------------------------------

def load_m5(symbol):
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
    return df.resample('1h').agg({
        'open': 'first', 'high': 'max', 'low': 'min',
        'close': 'last', 'volume': 'sum',
    }).dropna()


def calc_atr(df, period):
    tr = pd.concat([
        df['high'] - df['low'],
        (df['high'] - df['close'].shift(1)).abs(),
        (df['low'] - df['close'].shift(1)).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def calc_zscore(df, sma_period, atr_period):
    sma = df['close'].rolling(sma_period).mean()
    atr = calc_atr(df, atr_period)
    atr = atr.replace(0, np.nan)
    return (df['close'] - sma) / atr


def load_and_prepare(pair_cfg):
    """Load indices + FX, compute z-scores and index returns."""
    print(f'  Loading {pair_cfg["index_a"]}...')
    a_h1 = resample_to_h1(load_m5(pair_cfg['index_a']))

    print(f'  Loading {pair_cfg["index_b"]}...')
    b_h1 = resample_to_h1(load_m5(pair_cfg['index_b']))

    print(f'  Loading {pair_cfg["fx"]} (for filter)...')
    fx_h1 = resample_to_h1(load_m5(pair_cfg['fx']))

    # Align all three
    common = a_h1.index.intersection(b_h1.index).intersection(fx_h1.index)
    a_h1 = a_h1.loc[common]
    b_h1 = b_h1.loc[common]
    fx_h1 = fx_h1.loc[common]

    z_a = calc_zscore(a_h1, SMA_PERIOD, ATR_PERIOD)
    z_b = calc_zscore(b_h1, SMA_PERIOD, ATR_PERIOD)
    spread = (z_a - z_b).dropna()

    # Compute returns for BOTH indices (the target is the lagging one = index_b)
    data = pd.DataFrame({
        'spread': spread,
        'z_a': z_a,
        'z_b': z_b,
        'a_close': a_h1['close'],
        'b_close': b_h1['close'],
        'b_atr': calc_atr(b_h1, ATR_PERIOD),
        'a_atr': calc_atr(a_h1, ATR_PERIOD),
        'fx_close': fx_h1['close'],
        'fx_zscore': calc_zscore(fx_h1, SMA_PERIOD, ATR_PERIOD),
    })

    # Index B returns at multiple horizons (this is what we want to predict)
    for h in HORIZONS:
        data[f'b_ret_{h}h'] = b_h1['close'].pct_change(h).shift(-h)
        data[f'a_ret_{h}h'] = a_h1['close'].pct_change(h).shift(-h)
        # Convergence return: long B, short A
        data[f'conv_ret_{h}h'] = data[f'b_ret_{h}h'] - data[f'a_ret_{h}h']

    data['hour'] = data.index.hour
    data['year'] = data.index.year
    data = data.dropna(subset=['spread', 'b_close', 'b_atr'])

    print(f'  Common H1: {len(common)} ({common[0].date()} to {common[-1].date()})')
    print(f'  Analysis rows: {len(data)}')
    return data


# ---------------------------------------------------------------------------
# Analysis functions
# ---------------------------------------------------------------------------

def filter_session(data, session_name):
    h_start, h_end = SESSIONS[session_name]
    if session_name == 'All':
        return data.copy()
    return data[(data['hour'] >= h_start) & (data['hour'] <= h_end)].copy()


def predictive_corr(data, target_prefix='b_ret', horizons=HORIZONS):
    results = {}
    for h in horizons:
        col = f'{target_prefix}_{h}h'
        mask = data[col].notna()
        if mask.sum() < 50:
            results[h] = (np.nan, np.nan, 0)
            continue
        r, p = stats.pearsonr(data.loc[mask, 'spread'], data.loc[mask, col])
        results[h] = (r, p, mask.sum())
    return results


def quintile_analysis(data, target_col, horizon_label=''):
    valid = data.dropna(subset=[target_col])
    if len(valid) < 100:
        return None
    valid = valid.copy()
    valid['quintile'] = pd.qcut(valid['spread'], 5, labels=False, duplicates='drop')
    if valid['quintile'].nunique() < 5:
        return None

    result = valid.groupby('quintile').agg(
        mean_spread=('spread', 'mean'),
        mean_ret=pd.NamedAgg(column=target_col, aggfunc='mean'),
        std_ret=pd.NamedAgg(column=target_col, aggfunc='std'),
        count=('spread', 'count'),
        win_rate=pd.NamedAgg(column=target_col, aggfunc=lambda x: (x > 0).mean()),
    )
    result['mean_ret_bps'] = result['mean_ret'] * 10000
    result['t_stat'] = result['mean_ret'] / (result['std_ret'] / np.sqrt(result['count']))
    return result


def naive_pnl(data, target_col, horizon, dead_zone=1.0, mode='convergence'):
    """
    Simulate PnL.
    
    mode='convergence': short spread = long B when spread > 0 (expect B to catch up)
    mode='long_b':      only long B when spread > 0
    mode='short_a':     only short A when spread > 0
    """
    valid = data.dropna(subset=[target_col]).copy()
    if len(valid) < 100:
        return None

    forecast = (valid['spread'] / dead_zone * 20).clip(-20, 20)
    position = forecast / 20.0  # [-1, +1]

    if mode == 'long_b':
        # Long B when spread > 0 (A leads, B lags behind)
        # position > 0 means spread > 0 means we want long B
        # But we need to REVERSE because high spread means B should go UP
        pnl_per_bar = -position * valid[target_col]
    elif mode == 'short_a':
        pnl_per_bar = -position * valid[target_col]
    else:  # convergence: long B short A
        pnl_per_bar = -position * valid[target_col]

    pnl_sampled = pnl_per_bar.iloc[::horizon]

    if pnl_sampled.std() == 0:
        return None

    neg_sum = abs(pnl_sampled[pnl_sampled < 0].sum())
    return {
        'n_trades': len(pnl_sampled[pnl_sampled != 0]),
        'total_ret': pnl_sampled.sum(),
        'mean_ret': pnl_sampled.mean(),
        'sharpe': pnl_sampled.mean() / pnl_sampled.std() * np.sqrt(252 * 24 / horizon),
        'win_rate': (pnl_sampled > 0).mean(),
        'pf': pnl_sampled[pnl_sampled > 0].sum() / neg_sum if neg_sum > 0 else np.inf,
        'max_dd': (pnl_sampled.cumsum() - pnl_sampled.cumsum().cummax()).min(),
        'pnl_series': pnl_sampled,
        'cumulative': pnl_sampled.cumsum(),
    }


def bootstrap_sharpe(pnl_series, n_bootstrap=N_BOOTSTRAP, annualize_factor=1.0):
    arr = pnl_series.dropna().values
    if len(arr) < 30:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(42)
    sharpes = []
    for _ in range(n_bootstrap):
        sample = rng.choice(arr, size=len(arr), replace=True)
        s = sample.mean() / sample.std() * np.sqrt(annualize_factor) if sample.std() > 0 else 0
        sharpes.append(s)
    sharpes = np.array(sharpes)
    return np.percentile(sharpes, 2.5), np.median(sharpes), np.percentile(sharpes, 97.5)


def permutation_test(data, target_col, n_perms=N_PERMUTATIONS):
    valid = data.dropna(subset=[target_col])
    if len(valid) < 100:
        return np.nan, np.nan
    real_r, _ = stats.pearsonr(valid['spread'], valid[target_col])
    rng = np.random.default_rng(42)
    count = 0
    for _ in range(n_perms):
        shuffled = rng.permutation(valid['spread'].values)
        perm_r, _ = stats.pearsonr(shuffled, valid[target_col])
        if abs(perm_r) >= abs(real_r):
            count += 1
    return real_r, count / n_perms


def yearly_stability(data, target_col, horizon=6, dead_zone=1.0):
    years = sorted(data['year'].unique())
    rows = []
    for year in years:
        sub = data[data['year'] == year]
        sim = naive_pnl(sub, target_col, horizon, dead_zone)
        if sim is None:
            continue
        rows.append({
            'year': year,
            'n_trades': sim['n_trades'],
            'total_ret_bps': sim['total_ret'] * 10000,
            'sharpe': sim['sharpe'],
            'win_rate': sim['win_rate'],
            'pf': sim['pf'],
            'max_dd_bps': sim['max_dd'] * 10000,
        })
    return pd.DataFrame(rows)


def dead_zone_sweep(data, target_col, horizons=[3, 6, 12]):
    dead_zones = [0.3, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0]
    results = []
    for dz in dead_zones:
        for h in horizons:
            sim = naive_pnl(data, target_col, h, dz)
            if sim is None:
                continue
            sh_lo, _, sh_hi = bootstrap_sharpe(
                sim['pnl_series'], annualize_factor=252 * 24 / h
            )
            results.append({
                'dead_zone': dz, 'horizon': h,
                'sharpe': sim['sharpe'], 'sharpe_lo': sh_lo, 'sharpe_hi': sh_hi,
                'pf': sim['pf'], 'win_rate': sim['win_rate'],
                'n_trades': sim['n_trades'],
                'total_ret_bps': sim['total_ret'] * 10000,
            })
    return pd.DataFrame(results) if results else None


def fx_filter_analysis(data, target_col, horizon=6, dead_zone=1.0):
    """
    Compare PnL with and without FX confirmation filter.
    Filter: only trade when FX z-score confirms direction.
    When spread > 0 (A leads B), we expect B to catch up.
    If FX also diverges in confirming direction, enter. Otherwise skip.
    """
    valid = data.dropna(subset=[target_col, 'fx_zscore']).copy()
    if len(valid) < 200:
        return None

    forecast = (valid['spread'] / dead_zone * 20).clip(-20, 20)

    # FX filter: when spread > 0 and fx_zscore > 0 (or spread < 0 and fx < 0)
    # i.e. sign(spread) == sign(fx_zscore) -> confirmed
    fx_confirms = (valid['spread'] * valid['fx_zscore']) > 0

    # Unfiltered
    pos_raw = forecast / 20.0
    pnl_raw = (-pos_raw * valid[target_col]).iloc[::horizon]

    # Filtered: zero out trades where FX doesn't confirm
    pos_filtered = (forecast * fx_confirms.astype(float)) / 20.0
    pnl_filtered = (-pos_filtered * valid[target_col]).iloc[::horizon]

    # Also try FX-CONTRAY filter: only when FX does NOT confirm (contrarian)
    pos_contrary = (forecast * (~fx_confirms).astype(float)) / 20.0
    pnl_contrary = (-pos_contrary * valid[target_col]).iloc[::horizon]

    def _metrics(pnl):
        if pnl.std() == 0 or len(pnl) < 30:
            return None
        neg = abs(pnl[pnl < 0].sum())
        return {
            'sharpe': pnl.mean() / pnl.std() * np.sqrt(252 * 24 / horizon),
            'pf': pnl[pnl > 0].sum() / neg if neg > 0 else np.inf,
            'win_rate': (pnl > 0).mean(),
            'n_trades': (pnl != 0).sum(),
            'total_bps': pnl.sum() * 10000,
        }

    return {
        'no_filter': _metrics(pnl_raw),
        'fx_confirm': _metrics(pnl_filtered),
        'fx_contrary': _metrics(pnl_contrary),
    }


# ---------------------------------------------------------------------------
# Per-pair, per-session analysis
# ---------------------------------------------------------------------------

def analyze_session(data, pair_cfg, session_name):
    sdata = filter_session(data, session_name)
    h_start, h_end = SESSIONS[session_name]
    n = len(sdata)
    if n < 200:
        return None

    print(f'\n  --- {session_name} ({h_start:02d}-{h_end:02d} UTC) | N={n:,} ---')

    # === 1. Predictive correlations: spread vs index_B return ===
    print(f'\n    [A] Spread -> Index B return:')
    pred_b = predictive_corr(sdata, 'b_ret')
    print(f'    {"Horizon":>8s}  {"Corr":>8s}  {"p-val":>10s}  {"N":>6s}')
    for h in HORIZONS:
        r, p, cnt = pred_b[h]
        sig = '***' if p < 0.001 else '**' if p < 0.01 else '*' if p < 0.05 else ''
        if not np.isnan(r):
            print(f'    {h:>6d}h  {r:>8.4f}  {p:>10.2e}  {cnt:>6d} {sig}')

    # === 2. Predictive correlations: spread vs convergence return ===
    print(f'\n    [B] Spread -> Convergence return (B - A):')
    pred_conv = predictive_corr(sdata, 'conv_ret')
    for h in HORIZONS:
        r, p, cnt = pred_conv[h]
        sig = '***' if p < 0.001 else '**' if p < 0.01 else '*' if p < 0.05 else ''
        if not np.isnan(r):
            print(f'    {h:>6d}h  {r:>8.4f}  {p:>10.2e}  {cnt:>6d} {sig}')

    # === 3. Quintile: index B return at 6h ===
    quint_b = quintile_analysis(sdata, 'b_ret_6h')
    quint_conv = quintile_analysis(sdata, 'conv_ret_6h')
    qlabels = ['Q1 (low)', 'Q2', 'Q3', 'Q4', 'Q5 (high)']
    if quint_b is not None:
        print(f'\n    Quintile -> Index B (6h):')
        print(f'    {"Q":>12s}  {"Spread":>8s}  {"Ret bps":>8s}  {"t-stat":>7s}  {"N":>5s}')
        for i, row in quint_b.iterrows():
            sig = '*' if abs(row['t_stat']) > 1.96 else ''
            print(f'    {qlabels[i]:>12s}  {row["mean_spread"]:>8.3f}  '
                  f'{row["mean_ret_bps"]:>8.2f}  {row["t_stat"]:>7.2f}{sig} {row["count"]:>5.0f}')
        edge = quint_b.loc[4, 'mean_ret_bps'] - quint_b.loc[0, 'mean_ret_bps']
        print(f'    Q5-Q1 edge (B): {edge:.2f} bps')

    if quint_conv is not None:
        print(f'\n    Quintile -> Convergence B-A (6h):')
        print(f'    {"Q":>12s}  {"Spread":>8s}  {"Ret bps":>8s}  {"t-stat":>7s}  {"N":>5s}')
        for i, row in quint_conv.iterrows():
            sig = '*' if abs(row['t_stat']) > 1.96 else ''
            print(f'    {qlabels[i]:>12s}  {row["mean_spread"]:>8.3f}  '
                  f'{row["mean_ret_bps"]:>8.2f}  {row["t_stat"]:>7.2f}{sig} {row["count"]:>5.0f}')
        edge = quint_conv.loc[4, 'mean_ret_bps'] - quint_conv.loc[0, 'mean_ret_bps']
        print(f'    Q5-Q1 edge (conv): {edge:.2f} bps')

    # === 4. Naive PnL (index B, dz=1.0, 6h) ===
    sim_b = naive_pnl(sdata, 'b_ret_6h', 6, 1.0)
    sim_conv = naive_pnl(sdata, 'conv_ret_6h', 6, 1.0)

    for label, sim in [('Index B', sim_b), ('Convergence B-A', sim_conv)]:
        if sim is None:
            continue
        sh_lo, sh_med, sh_hi = bootstrap_sharpe(
            sim['pnl_series'], annualize_factor=252 * 24 / 6
        )
        print(f'\n    PnL [{label}] (dz=1.0, 6h):')
        print(f'      Trades:    {sim["n_trades"]:,}')
        print(f'      Total:     {sim["total_ret"]*10000:.1f} bps')
        print(f'      Sharpe:    {sim["sharpe"]:.3f}')
        print(f'      PF:        {sim["pf"]:.3f}')
        print(f'      Win rate:  {sim["win_rate"]:.1%}')
        print(f'      Max DD:    {sim["max_dd"]*10000:.1f} bps')
        print(f'      Bootstrap: [{sh_lo:.3f}, {sh_med:.3f}, {sh_hi:.3f}]')

    # === 5. Yearly stability ===
    ystab_b = yearly_stability(sdata, 'b_ret_6h', 6, 1.0)
    ystab_conv = yearly_stability(sdata, 'conv_ret_6h', 6, 1.0)

    for label, ystab in [('Index B', ystab_b), ('Conv B-A', ystab_conv)]:
        if len(ystab) == 0:
            continue
        print(f'\n    Yearly [{label}] (dz=1.0, 6h):')
        print(f'    {"Year":>4s}  {"N":>5s}  {"RetBps":>8s}  {"Sharpe":>7s}  {"WR":>6s}  {"PF":>6s}')
        for _, row in ystab.iterrows():
            print(f'    {row["year"]:>4.0f}  {row["n_trades"]:>5.0f}  '
                  f'{row["total_ret_bps"]:>8.1f}  {row["sharpe"]:>7.3f}  '
                  f'{row["win_rate"]:>6.1%}  {row["pf"]:>6.3f}')
        pos = (ystab['total_ret_bps'] > 0).sum()
        print(f'    Positive: {pos}/{len(ystab)}')

    # === 6. FX filter comparison ===
    fx_res = fx_filter_analysis(sdata, 'b_ret_6h', 6, 1.0)
    if fx_res:
        print(f'\n    FX Filter comparison (Index B, dz=1.0, 6h):')
        for mode, metrics in fx_res.items():
            if metrics is None:
                continue
            print(f'      {mode:>12s}: Sharpe={metrics["sharpe"]:.3f}, PF={metrics["pf"]:.3f}, '
                  f'WR={metrics["win_rate"]:.1%}, N={metrics["n_trades"]}, '
                  f'Total={metrics["total_bps"]:.0f}bps')

    return {
        'session': session_name, 'n': n,
        'pred_b': pred_b, 'pred_conv': pred_conv,
        'quint_b': quint_b, 'quint_conv': quint_conv,
        'sim_b': sim_b, 'sim_conv': sim_conv,
        'ystab_b': ystab_b, 'ystab_conv': ystab_conv,
        'fx_res': fx_res,
    }


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def plot_pair(data, pair_cfg, results):
    fig, axes = plt.subplots(3, 3, figsize=(20, 16))
    fig.suptitle(f'VEGA Fase 0c: {pair_cfg["label"]}', fontsize=14, fontweight='bold')

    # -- 1. Predictive corr: Index B vs Convergence, by session (6h) --
    ax = axes[0, 0]
    sessions = [s for s in ['Tokyo', 'London', 'NY_Close', 'All']
                if results.get(s) and results[s] is not None]
    width = 0.35
    x = np.arange(len(sessions))
    corrs_b = []
    corrs_c = []
    for s in sessions:
        rb, pb, _ = results[s]['pred_b'].get(6, (np.nan, np.nan, 0))
        rc, pc, _ = results[s]['pred_conv'].get(6, (np.nan, np.nan, 0))
        corrs_b.append(rb if not np.isnan(rb) else 0)
        corrs_c.append(rc if not np.isnan(rc) else 0)
    ax.bar(x - width/2, corrs_b, width, label='Index B', alpha=0.7, color='steelblue')
    ax.bar(x + width/2, corrs_c, width, label='Conv B-A', alpha=0.7, color='darkorange')
    ax.set_xticks(x)
    ax.set_xticklabels(sessions)
    ax.axhline(0, color='black', linewidth=0.8)
    ax.set_title('Predictive Corr (6h) by Session')
    ax.set_ylabel('Pearson r')
    ax.legend(fontsize=8)

    # -- 2. Quintile: Index B across key sessions --
    ax = axes[0, 1]
    for s in ['Tokyo', 'NY_Close', 'All']:
        if not results.get(s) or results[s] is None:
            continue
        q = results[s].get('quint_b')
        if q is None:
            continue
        ax.plot(q['mean_spread'], q['mean_ret_bps'], 'o-', label=s, markersize=5)
    ax.axhline(0, color='black', linewidth=0.5)
    ax.axvline(0, color='black', linewidth=0.5)
    ax.set_title('Quintile: Spread vs Index B Ret (bps, 6h)')
    ax.set_xlabel('Mean Spread')
    ax.set_ylabel('Mean Index B Return (bps)')
    ax.legend(fontsize=8)

    # -- 3. Quintile: Convergence B-A --
    ax = axes[0, 2]
    for s in ['Tokyo', 'NY_Close', 'All']:
        if not results.get(s) or results[s] is None:
            continue
        q = results[s].get('quint_conv')
        if q is None:
            continue
        ax.plot(q['mean_spread'], q['mean_ret_bps'], 'o-', label=s, markersize=5)
    ax.axhline(0, color='black', linewidth=0.5)
    ax.axvline(0, color='black', linewidth=0.5)
    ax.set_title('Quintile: Spread vs Conv B-A (bps, 6h)')
    ax.set_xlabel('Mean Spread')
    ax.set_ylabel('Convergence Return (bps)')
    ax.legend(fontsize=8)

    # -- 4. Dead zone sweep (best session or All) --
    ax = axes[1, 0]
    best_sess = 'All'
    for s in ['Tokyo', 'London', 'NY_Close']:
        r = results.get(s)
        if r and r.get('sim_conv') and r['sim_conv']['sharpe'] > (results.get(best_sess, {}) or {}).get('sim_conv', {}).get('sharpe', -99):
            best_sess = s
    sdata = filter_session(data, best_sess)
    sweep = dead_zone_sweep(sdata, 'conv_ret_6h', [3, 6, 12])
    if sweep is not None and len(sweep) > 0:
        for h in [3, 6, 12]:
            sub = sweep[sweep['horizon'] == h]
            if len(sub) > 0:
                ax.plot(sub['dead_zone'], sub['sharpe'], 'o-', label=f'{h}h', markersize=4)
                ax.fill_between(sub['dead_zone'], sub['sharpe_lo'], sub['sharpe_hi'], alpha=0.1)
        ax.axhline(0, color='red', linestyle='--', alpha=0.5)
        ax.set_title(f'{best_sess}: Sharpe by Dead Zone (Conv)')
        ax.set_xlabel('Dead Zone')
        ax.set_ylabel('Sharpe')
        ax.legend(fontsize=8)

    # -- 5. Equity curves: Index B vs Convergence (All session) --
    ax = axes[1, 1]
    for s_name in ['All']:
        r = results.get(s_name)
        if not r:
            continue
        if r.get('sim_b'):
            cum = r['sim_b']['cumulative'] * 10000
            ax.plot(cum.index, cum.values, label=f'{s_name} Index B', linewidth=0.5)
        if r.get('sim_conv'):
            cum = r['sim_conv']['cumulative'] * 10000
            ax.plot(cum.index, cum.values, label=f'{s_name} Conv B-A', linewidth=0.5)
    ax.axhline(0, color='black', linewidth=0.5)
    ax.set_title('Equity Curve (dz=1.0, 6h)')
    ax.set_ylabel('Cumulative PnL (bps)')
    ax.legend(fontsize=8)

    # -- 6. FX filter comparison bar chart --
    ax = axes[1, 2]
    fx_sess = 'All'
    fx_r = results.get(fx_sess, {})
    fx_res = fx_r.get('fx_res') if fx_r else None
    if fx_res:
        modes = [m for m in ['no_filter', 'fx_confirm', 'fx_contrary'] if fx_res.get(m)]
        sharpes_fx = [fx_res[m]['sharpe'] for m in modes]
        colors = ['steelblue', 'green', 'red']
        ax.bar(modes, sharpes_fx, color=colors[:len(modes)], alpha=0.7)
        ax.axhline(0, color='black', linewidth=0.8)
        ax.set_title(f'{fx_sess}: FX Filter Effect on Sharpe')
        ax.set_ylabel('Sharpe')
        for i, (m, s) in enumerate(zip(modes, sharpes_fx)):
            pf = fx_res[m]['pf']
            ax.text(i, s + 0.05 * np.sign(s), f'PF={pf:.2f}', ha='center', fontsize=8)

    # -- 7. Yearly stability (best signal) --
    ax = axes[2, 0]
    for target_label, ystab_key in [('Conv B-A', 'ystab_conv'), ('Index B', 'ystab_b')]:
        r = results.get('All')
        if not r:
            continue
        ystab = r.get(ystab_key)
        if ystab is None or len(ystab) == 0:
            continue
        colors_yr = ['green' if s > 0 else 'red' for s in ystab['sharpe']]
        ax.bar(ystab['year'].astype(str), ystab['sharpe'], color=colors_yr, alpha=0.7)
        ax.axhline(0, color='black', linewidth=0.8)
        ax.set_title(f'All: Yearly Sharpe — {target_label}')
        ax.set_ylabel('Sharpe')
        ax.tick_params(axis='x', rotation=45)
        break  # only plot first available

    # -- 8. Hourly heatmap: predictive corr spread vs conv_ret_6h --
    ax = axes[2, 1]
    corr_by_hour = []
    for hr in range(24):
        sub = data[data['hour'] == hr].dropna(subset=['conv_ret_6h'])
        if len(sub) > 50:
            r, p = stats.pearsonr(sub['spread'], sub['conv_ret_6h'])
            corr_by_hour.append({'hour': hr, 'corr': r, 'pval': p})
        else:
            corr_by_hour.append({'hour': hr, 'corr': 0, 'pval': 1})
    hdf = pd.DataFrame(corr_by_hour)
    colors_h = ['green' if p < 0.05 else 'lightgray' for p in hdf['pval']]
    ax.bar(hdf['hour'], hdf['corr'], color=colors_h, alpha=0.7)
    ax.axhline(0, color='black', linewidth=0.8)
    ax.axvspan(-0.5, 5.5, alpha=0.05, color='blue', label='Tokyo')
    ax.axvspan(16.5, 20.5, alpha=0.05, color='red', label='NY Close')
    ax.set_title('Predictive Corr: Spread vs Conv B-A (6h)')
    ax.set_xlabel('Hour (UTC)')
    ax.set_ylabel('Pearson r')
    ax.set_xticks(range(0, 24, 2))
    ax.legend(fontsize=7)

    # -- 9. Predictive corr by horizon (All) --
    ax = axes[2, 2]
    r_all = results.get('All')
    if r_all:
        for label, pred in [('Index B', r_all['pred_b']), ('Conv B-A', r_all['pred_conv'])]:
            hs = [h for h in HORIZONS if not np.isnan(pred[h][0])]
            rs = [pred[h][0] for h in hs]
            ax.plot([str(h) for h in hs], rs, 'o-', label=label, markersize=5)
        ax.axhline(0, color='black', linewidth=0.8)
        ax.set_title('All: Corr by Horizon')
        ax.set_xlabel('Horizon (hours)')
        ax.set_ylabel('Pearson r')
        ax.legend(fontsize=8)

    plt.tight_layout()
    out = OUT_DIR / f'vega_fase0c_{pair_cfg["name"]}.png'
    plt.savefig(out, dpi=150, bbox_inches='tight')
    print(f'\n  Chart saved: {out}')
    if not SAVE_ONLY:
        plt.show()
    plt.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print('=' * 80)
    print(' VEGA FASE 0c: DIRECT INDEX TRADING VIA Z-SCORE DIVERGENCE')
    print(f' SMA={SMA_PERIOD}h, ATR={ATR_PERIOD}h')
    print(f' Sessions: {list(SESSIONS.keys())}')
    print(f' Bootstrap: {N_BOOTSTRAP}, Permutations: {N_PERMUTATIONS}')
    print('=' * 80)

    all_verdicts = []

    for pair_cfg in INDEX_PAIRS:
        print(f'\n{"="*80}')
        print(f' PAIR: {pair_cfg["label"]}')
        print(f'{"="*80}')

        data = load_and_prepare(pair_cfg)

        results = {}
        for session_name in SESSIONS:
            res = analyze_session(data, pair_cfg, session_name)
            results[session_name] = res

        # Dead zone sweep for All and best session
        print(f'\n  === DEAD ZONE SWEEP ===')
        for sess in ['Tokyo', 'London', 'NY_Close', 'All']:
            sdata = filter_session(data, sess)
            if len(sdata) < 200:
                continue
            sweep_b = dead_zone_sweep(sdata, 'b_ret_6h', [3, 6, 12])
            sweep_conv = dead_zone_sweep(sdata, 'conv_ret_6h', [3, 6, 12])
            for label, sweep in [('Index B', sweep_b), ('Conv B-A', sweep_conv)]:
                if sweep is not None and len(sweep) > 0:
                    best = sweep.loc[sweep['sharpe'].idxmax()]
                    print(f'    {sess} [{label}]: Best dz={best["dead_zone"]:.1f}, '
                          f'h={best["horizon"]:.0f}h, Sharpe={best["sharpe"]:.3f} '
                          f'[{best["sharpe_lo"]:.3f},{best["sharpe_hi"]:.3f}], '
                          f'PF={best["pf"]:.3f}')

        # Permutation tests
        print(f'\n  === PERMUTATION TESTS ({N_PERMUTATIONS} perms) ===')
        for sess in ['Tokyo', 'London', 'NY_Close', 'All']:
            sdata = filter_session(data, sess)
            if len(sdata) < 200:
                continue
            for label, col in [('B_6h', 'b_ret_6h'), ('Conv_6h', 'conv_ret_6h')]:
                r, pval = permutation_test(sdata, col)
                if not np.isnan(r):
                    sig = '***' if pval < 0.001 else '**' if pval < 0.01 else '*' if pval < 0.05 else 'NS'
                    print(f'    {sess} [{label}]: r={r:.4f}, perm_p={pval:.4f} {sig}')

        # Plot
        plot_pair(data, pair_cfg, results)

        # Collect verdicts
        for sess in SESSIONS:
            r = results.get(sess)
            if not r:
                continue
            rb, pb, nb = r['pred_b'].get(6, (np.nan, np.nan, 0))
            rc, pc, nc = r['pred_conv'].get(6, (np.nan, np.nan, 0))
            sh_b = r['sim_b']['sharpe'] if r.get('sim_b') else np.nan
            pf_b = r['sim_b']['pf'] if r.get('sim_b') else np.nan
            sh_c = r['sim_conv']['sharpe'] if r.get('sim_conv') else np.nan
            pf_c = r['sim_conv']['pf'] if r.get('sim_conv') else np.nan
            all_verdicts.append({
                'pair': pair_cfg['name'], 'session': sess, 'n': r['n'],
                'corr_b_6h': rb, 'pval_b_6h': pb,
                'corr_conv_6h': rc, 'pval_conv_6h': pc,
                'sharpe_b': sh_b, 'pf_b': pf_b,
                'sharpe_conv': sh_c, 'pf_conv': pf_c,
            })

    # -----------------------------------------------------------------------
    # FINAL VERDICT
    # -----------------------------------------------------------------------
    print(f'\n{"="*80}')
    print(f' FINAL VERDICT TABLE')
    print(f'{"="*80}')
    vdf = pd.DataFrame(all_verdicts)
    print(f'\n  {"Pair":>20s}  {"Sess":>10s}  {"N":>6s}  '
          f'{"rB":>7s}  {"pB":>9s}  {"ShB":>7s}  {"PFb":>6s}  '
          f'{"rC":>7s}  {"pC":>9s}  {"ShC":>7s}  {"PFc":>6s}  {"Verdict":>10s}')
    for _, row in vdf.iterrows():
        # verdict based on convergence (the real trade)
        if row['sharpe_conv'] > 0.5 and row['pf_conv'] > 1.15:
            verdict = 'PROMISING'
        elif row['sharpe_conv'] > 0.2 and row['pf_conv'] > 1.05:
            verdict = 'MARGINAL'
        elif np.isnan(row['sharpe_conv']):
            verdict = 'N/A'
        else:
            verdict = 'NO EDGE'

        sigb = '***' if row['pval_b_6h'] < 0.001 else '**' if row['pval_b_6h'] < 0.01 else '*' if row['pval_b_6h'] < 0.05 else ''
        sigc = '***' if row['pval_conv_6h'] < 0.001 else '**' if row['pval_conv_6h'] < 0.01 else '*' if row['pval_conv_6h'] < 0.05 else ''
        print(f'  {row["pair"]:>20s}  {row["session"]:>10s}  {row["n"]:>6.0f}  '
              f'{row["corr_b_6h"]:>7.4f}  {row["pval_b_6h"]:>7.1e}{sigb:>2s}  '
              f'{row["sharpe_b"]:>7.3f}  {row["pf_b"]:>6.3f}  '
              f'{row["corr_conv_6h"]:>7.4f}  {row["pval_conv_6h"]:>7.1e}{sigc:>2s}  '
              f'{row["sharpe_conv"]:>7.3f}  {row["pf_conv"]:>6.3f}  {verdict:>10s}')

    print(f'\n  Key:')
    print(f'  - rB/ShB/PFb = Index B standalone return metrics')
    print(f'  - rC/ShC/PFc = Convergence (long B, short A) metrics')
    print(f'  - PROMISING: Sharpe > 0.5 AND PF > 1.15 (convergence)')
    print(f'  - MARGINAL: Sharpe > 0.2 AND PF > 1.05')
    print(f'  - All pre-costs. Index CFD spread ~1-2 pts (SP500), ~10-20 pts (NI225)')


if __name__ == '__main__':
    main()
