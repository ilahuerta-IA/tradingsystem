"""
VEGA Fase 0b: Session-Filtered Z-Score Divergence Deep Study.

Builds on Fase 0 findings: global correlation is weak (r=-0.017) but
the hourly heatmap showed structural differences by session.
Tokyo (0-5 UTC) shows POSITIVE correlation, NY close (17-20 UTC) shows
NEGATIVE. This study isolates each window rigorously.

Study structure:
  1. Per-window predictive analysis (Tokyo, London, NY, NY-close)
  2. Quintile spread analysis (conditional returns)
  3. Naive PnL simulation with forecast-proportional sizing
  4. Bootstrap confidence intervals for Sharpe and PF
  5. Yearly stability within each window
  6. Multi-pair comparison (SP500/NI225->USDJPY, SP500/AUS200->AUDUSD)
  7. Direct index spread: long NI225 / short SP500 (or vice versa)
  8. Summary verdict table

Usage:
  python tools/study_vega_session.py
  python tools/study_vega_session.py --save-only
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
SMA_PERIOD = 24       # H1 bars = 1 trading day
ATR_PERIOD = 24       # same window for ATR

SESSIONS = {
    'Tokyo':    (0, 5),    # 00:00-05:59 UTC, NI225 cash
    'London':   (7, 12),   # 07:00-12:59 UTC
    'NY':       (13, 17),  # 13:00-17:59 UTC, SP500 cash
    'NY_Close': (17, 20),  # 17:00-20:59 UTC, late NY
    'All':      (0, 23),   # all hours
}

# FX pair configurations
FX_PAIRS = [
    {
        'name': 'SP500_NI225_USDJPY',
        'index_a': 'SP500', 'index_b': 'NI225', 'fx': 'USDJPY',
        'label': 'SP500 vs NI225 -> USDJPY',
    },
    {
        'name': 'SP500_AUS200_AUDUSD',
        'index_a': 'SP500', 'index_b': 'AUS200', 'fx': 'AUDUSD',
        'label': 'SP500 vs AUS200 -> AUDUSD',
    },
]

FX_HORIZONS = [1, 2, 3, 6, 12, 24]
N_BOOTSTRAP = 1000
QUINTILE_LABELS = ['Q1 (low)', 'Q2', 'Q3', 'Q4', 'Q5 (high)']


# ---------------------------------------------------------------------------
# Data loading (reuse from Fase 0)
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
    # Avoid division by zero
    atr = atr.replace(0, np.nan)
    z = (df['close'] - sma) / atr
    return z


def load_and_prepare(pair_cfg):
    """Load all three instruments, resample, align, compute z-scores."""
    print(f'  Loading {pair_cfg["index_a"]}...')
    a_h1 = resample_to_h1(load_m5(pair_cfg['index_a']))
    print(f'    H1: {len(a_h1)} bars')

    print(f'  Loading {pair_cfg["index_b"]}...')
    b_h1 = resample_to_h1(load_m5(pair_cfg['index_b']))
    print(f'    H1: {len(b_h1)} bars')

    print(f'  Loading {pair_cfg["fx"]}...')
    fx_h1 = resample_to_h1(load_m5(pair_cfg['fx']))
    print(f'    H1: {len(fx_h1)} bars')

    # Align
    common = a_h1.index.intersection(b_h1.index).intersection(fx_h1.index)
    a_h1 = a_h1.loc[common]
    b_h1 = b_h1.loc[common]
    fx_h1 = fx_h1.loc[common]

    # Z-scores
    z_a = calc_zscore(a_h1, SMA_PERIOD, ATR_PERIOD)
    z_b = calc_zscore(b_h1, SMA_PERIOD, ATR_PERIOD)
    spread = (z_a - z_b).dropna()

    # Build master dataframe
    data = pd.DataFrame({
        'spread': spread,
        'z_a': z_a,
        'z_b': z_b,
        'fx_close': fx_h1['close'],
        'fx_atr': calc_atr(fx_h1, ATR_PERIOD),
    })
    for h in FX_HORIZONS:
        data[f'fx_ret_{h}h'] = fx_h1['close'].pct_change(h).shift(-h)
    data['hour'] = data.index.hour
    data['year'] = data.index.year
    data['weekday'] = data.index.weekday  # 0=Mon
    data = data.dropna(subset=['spread', 'fx_close', 'fx_atr'])

    print(f'  Common H1 bars: {len(common)} ({common[0].date()} to {common[-1].date()})')
    print(f'  Analysis rows: {len(data)}')
    return data


# ---------------------------------------------------------------------------
# Analysis functions
# ---------------------------------------------------------------------------

def filter_session(data, session_name):
    """Filter data to only include rows within a session window."""
    h_start, h_end = SESSIONS[session_name]
    if session_name == 'All':
        return data.copy()
    return data[(data['hour'] >= h_start) & (data['hour'] <= h_end)].copy()


def predictive_corr(data, horizons=FX_HORIZONS):
    """Pearson correlation of spread vs fx_ret at multiple horizons."""
    results = {}
    for h in horizons:
        col = f'fx_ret_{h}h'
        mask = data[col].notna()
        if mask.sum() < 50:
            results[h] = (np.nan, np.nan, 0)
            continue
        r, p = stats.pearsonr(data.loc[mask, 'spread'], data.loc[mask, col])
        results[h] = (r, p, mask.sum())
    return results


def quintile_analysis(data, horizon=6):
    """Split spread into quintiles and compute conditional FX returns."""
    col = f'fx_ret_{horizon}h'
    valid = data.dropna(subset=[col])
    if len(valid) < 100:
        return None
    valid = valid.copy()
    valid['quintile'] = pd.qcut(valid['spread'], 5, labels=False, duplicates='drop')
    if valid['quintile'].nunique() < 5:
        return None

    result = valid.groupby('quintile').agg(
        mean_spread=('spread', 'mean'),
        mean_ret=pd.NamedAgg(column=col, aggfunc='mean'),
        std_ret=pd.NamedAgg(column=col, aggfunc='std'),
        count=('spread', 'count'),
        win_rate=pd.NamedAgg(column=col, aggfunc=lambda x: (x > 0).mean()),
    )
    result['mean_ret_bps'] = result['mean_ret'] * 10000
    result['t_stat'] = result['mean_ret'] / (result['std_ret'] / np.sqrt(result['count']))
    return result


def naive_pnl_simulation(data, horizon=6, dead_zone=1.0, direction='both'):
    """
    Simulate naive PnL using forecast-proportional sizing.
    
    Forecast = clip(spread / dead_zone * 20, -20, +20)
    Position size proportional to |forecast|/20.
    PnL = position_sign * fx_return * |forecast|/20
    
    direction: 'both', 'long', 'short'
    """
    col = f'fx_ret_{horizon}h'
    valid = data.dropna(subset=[col]).copy()
    if len(valid) < 100:
        return None

    # Forecast: continuous
    forecast = (valid['spread'] / dead_zone * 20).clip(-20, 20)

    if direction == 'long':
        forecast = forecast.clip(lower=0)
    elif direction == 'short':
        forecast = forecast.clip(upper=0)

    # Normalized position [-1, +1]
    position = forecast / 20.0

    # PnL proportional to position (negative spread -> short FX -> negative position)
    # When spread > 0 (index_a > index_b), we expect FX to go DOWN (from Fase 0)
    # So our PnL = -position * fx_return (we SHORT when spread is positive)
    pnl_per_bar = -position * valid[col]

    # Avoid overlapping trades: only count every 'horizon' bars
    pnl_sampled = pnl_per_bar.iloc[::horizon]
    
    result = {
        'n_signals': (forecast.abs() > 0).sum(),
        'n_trades_approx': len(pnl_sampled[pnl_sampled != 0]),
        'total_ret': pnl_sampled.sum(),
        'mean_ret': pnl_sampled.mean(),
        'std_ret': pnl_sampled.std(),
        'sharpe': pnl_sampled.mean() / pnl_sampled.std() * np.sqrt(252 * 24 / horizon) if pnl_sampled.std() > 0 else 0,
        'win_rate': (pnl_sampled > 0).mean(),
        'pnl_series': pnl_sampled,
        'cumulative': pnl_sampled.cumsum(),
        'max_dd': (pnl_sampled.cumsum() - pnl_sampled.cumsum().cummax()).min(),
        'pf': pnl_sampled[pnl_sampled > 0].sum() / abs(pnl_sampled[pnl_sampled < 0].sum()) if (pnl_sampled < 0).sum() > 0 else np.inf,
        'forecast': forecast,
    }
    return result


def bootstrap_sharpe(pnl_series, n_bootstrap=N_BOOTSTRAP, annualize_factor=1.0):
    """Bootstrap confidence interval for Sharpe ratio."""
    arr = pnl_series.dropna().values
    if len(arr) < 30:
        return np.nan, np.nan, np.nan
    sharpes = []
    rng = np.random.default_rng(42)
    for _ in range(n_bootstrap):
        sample = rng.choice(arr, size=len(arr), replace=True)
        s = sample.mean() / sample.std() * np.sqrt(annualize_factor) if sample.std() > 0 else 0
        sharpes.append(s)
    sharpes = np.array(sharpes)
    return np.percentile(sharpes, 2.5), np.median(sharpes), np.percentile(sharpes, 97.5)


def yearly_stability(data, horizon=6, dead_zone=1.0):
    """Run naive PnL simulation per year to check stability."""
    years = sorted(data['year'].unique())
    rows = []
    for year in years:
        sub = data[data['year'] == year]
        sim = naive_pnl_simulation(sub, horizon=horizon, dead_zone=dead_zone)
        if sim is None:
            continue
        rows.append({
            'year': year,
            'n_trades': sim['n_trades_approx'],
            'total_ret_bps': sim['total_ret'] * 10000,
            'sharpe': sim['sharpe'],
            'win_rate': sim['win_rate'],
            'pf': sim['pf'],
            'max_dd_bps': sim['max_dd'] * 10000,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Main analysis per pair + session
# ---------------------------------------------------------------------------

def analyze_pair_session(data, pair_cfg, session_name):
    """Full analysis for one pair in one session window."""
    sdata = filter_session(data, session_name)
    h_start, h_end = SESSIONS[session_name]
    n = len(sdata)
    if n < 200:
        return None

    print(f'\n  --- {session_name} ({h_start:02d}-{h_end:02d} UTC) | N={n:,} ---')

    # 1. Predictive correlations
    pred = predictive_corr(sdata)
    print(f'    Predictive correlations:')
    print(f'    {"Horizon":>8s}  {"Corr":>8s}  {"p-val":>10s}  {"N":>6s}  {"Sig":>4s}')
    for h in FX_HORIZONS:
        r, p, count = pred[h]
        sig = '***' if p < 0.001 else '**' if p < 0.01 else '*' if p < 0.05 else ''
        if not np.isnan(r):
            print(f'    {h:>6d}h  {r:>8.4f}  {p:>10.2e}  {count:>6d}  {sig:>4s}')

    # 2. Quintile analysis (6h horizon)
    quint = quintile_analysis(sdata, horizon=6)
    if quint is not None:
        print(f'\n    Quintile analysis (6h horizon):')
        print(f'    {"Q":>4s}  {"Spread":>8s}  {"Ret bps":>8s}  {"WinRate":>8s}  {"t-stat":>7s}  {"N":>6s}')
        for i, row in quint.iterrows():
            sig = '*' if abs(row['t_stat']) > 1.96 else ''
            print(f'    {QUINTILE_LABELS[i]:>12s}  {row["mean_spread"]:>8.3f}  '
                  f'{row["mean_ret_bps"]:>8.2f}  {row["win_rate"]:>8.1%}  '
                  f'{row["t_stat"]:>7.2f}{sig} {row["count"]:>5.0f}')
        # Edge: Q5 - Q1
        edge = quint.loc[4, 'mean_ret_bps'] - quint.loc[0, 'mean_ret_bps']
        print(f'    Q5-Q1 edge: {edge:.2f} bps')

    # 3. Naive PnL simulation
    for dz in [0.5, 1.0, 1.5, 2.0]:
        sim = naive_pnl_simulation(sdata, horizon=6, dead_zone=dz)
        if sim is None:
            continue
        sh_lo, sh_med, sh_hi = bootstrap_sharpe(
            sim['pnl_series'],
            annualize_factor=252 * 24 / 6
        )
        if dz == 1.0:
            print(f'\n    Naive PnL simulation (dead_zone={dz}):')
            print(f'      Trades:    {sim["n_trades_approx"]:,}')
            print(f'      Total ret: {sim["total_ret"]*10000:.1f} bps')
            print(f'      Sharpe:    {sim["sharpe"]:.3f}')
            print(f'      Win rate:  {sim["win_rate"]:.1%}')
            print(f'      PF:        {sim["pf"]:.3f}')
            print(f'      Max DD:    {sim["max_dd"]*10000:.1f} bps')
            print(f'      Bootstrap Sharpe 95% CI: [{sh_lo:.3f}, {sh_med:.3f}, {sh_hi:.3f}]')

    # 4. Yearly stability (dead_zone=1.0)
    ystab = yearly_stability(sdata, horizon=6, dead_zone=1.0)
    if len(ystab) > 0:
        print(f'\n    Yearly stability (dz=1.0):')
        print(f'    {"Year":>4s}  {"Trades":>6s}  {"RetBps":>8s}  {"Sharpe":>7s}  {"WinR":>6s}  {"PF":>6s}')
        for _, row in ystab.iterrows():
            print(f'    {row["year"]:>4.0f}  {row["n_trades"]:>6.0f}  '
                  f'{row["total_ret_bps"]:>8.1f}  {row["sharpe"]:>7.3f}  '
                  f'{row["win_rate"]:>6.1%}  {row["pf"]:>6.3f}')
        pos_years = (ystab['total_ret_bps'] > 0).sum()
        print(f'    Positive years: {pos_years}/{len(ystab)}')

    return {
        'session': session_name,
        'n': n,
        'pred': pred,
        'quint': quint,
    }


# ---------------------------------------------------------------------------
# Dead zone sweep: find best dead_zone per session
# ---------------------------------------------------------------------------

def dead_zone_sweep(data, session_name, horizons=[3, 6, 12]):
    """Sweep dead_zone values and horizons to find optimal config."""
    sdata = filter_session(data, session_name)
    if len(sdata) < 200:
        return None

    dead_zones = [0.3, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0]
    results = []
    for dz in dead_zones:
        for h in horizons:
            sim = naive_pnl_simulation(sdata, horizon=h, dead_zone=dz)
            if sim is None:
                continue
            sh_lo, _, sh_hi = bootstrap_sharpe(
                sim['pnl_series'],
                annualize_factor=252 * 24 / h
            )
            results.append({
                'dead_zone': dz,
                'horizon': h,
                'sharpe': sim['sharpe'],
                'sharpe_lo': sh_lo,
                'sharpe_hi': sh_hi,
                'pf': sim['pf'],
                'win_rate': sim['win_rate'],
                'n_trades': sim['n_trades_approx'],
                'total_ret_bps': sim['total_ret'] * 10000,
                'max_dd_bps': sim['max_dd'] * 10000,
            })
    return pd.DataFrame(results)


# ---------------------------------------------------------------------------
# Direction comparison: long-only, short-only, both
# ---------------------------------------------------------------------------

def direction_comparison(data, session_name, dead_zone=1.0, horizon=6):
    """Compare long-only, short-only, and both-direction trading."""
    sdata = filter_session(data, session_name)
    if len(sdata) < 200:
        return None

    results = {}
    for direction in ['both', 'long', 'short']:
        sim = naive_pnl_simulation(sdata, horizon=horizon, dead_zone=dead_zone,
                                   direction=direction)
        if sim is None:
            continue
        sh_lo, _, sh_hi = bootstrap_sharpe(
            sim['pnl_series'],
            annualize_factor=252 * 24 / horizon
        )
        results[direction] = {
            'sharpe': sim['sharpe'],
            'sharpe_ci': (sh_lo, sh_hi),
            'pf': sim['pf'],
            'win_rate': sim['win_rate'],
            'total_ret_bps': sim['total_ret'] * 10000,
            'n_trades': sim['n_trades_approx'],
            'cumulative': sim['cumulative'],
        }
    return results


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def plot_pair_results(data, pair_cfg, session_results, dz_sweeps, dir_results):
    """Create comprehensive plot for one pair."""
    fig, axes = plt.subplots(3, 3, figsize=(20, 16))
    fig.suptitle(f'VEGA Fase 0b: {pair_cfg["label"]}', fontsize=14, fontweight='bold')

    # -- Row 1: Session comparison --

    # 1a. Predictive corr by session (6h horizon)
    ax = axes[0, 0]
    sessions = [s for s in ['Tokyo', 'London', 'NY', 'NY_Close', 'All']
                if s in session_results and session_results[s] is not None]
    corrs = []
    pvals = []
    for s in sessions:
        r, p, _ = session_results[s]['pred'][6]
        corrs.append(r if not np.isnan(r) else 0)
        pvals.append(p if not np.isnan(p) else 1)
    colors = ['green' if p < 0.05 else 'gray' for p in pvals]
    ax.bar(sessions, corrs, color=colors, alpha=0.7)
    ax.axhline(0, color='black', linewidth=0.8)
    ax.set_title('Predictive Corr by Session (6h)')
    ax.set_ylabel('Pearson r')
    for i, (c, p) in enumerate(zip(corrs, pvals)):
        sig = '***' if p < 0.001 else '**' if p < 0.01 else '*' if p < 0.05 else ''
        ax.text(i, c + 0.001 * np.sign(c), f'{c:.4f}{sig}', ha='center', va='bottom' if c > 0 else 'top', fontsize=8)

    # 1b. Quintile spread Q1 vs Q5 returns
    ax = axes[0, 1]
    for s in ['Tokyo', 'NY_Close', 'All']:
        if s not in session_results or session_results[s] is None:
            continue
        q = session_results[s].get('quint')
        if q is None:
            continue
        x = q['mean_spread']
        y = q['mean_ret_bps']
        ax.plot(x, y, 'o-', label=s, markersize=5)
    ax.axhline(0, color='black', linewidth=0.5)
    ax.axvline(0, color='black', linewidth=0.5)
    ax.set_title('Quintile: Mean Spread vs Mean Ret (bps)')
    ax.set_xlabel('Mean Spread in Quintile')
    ax.set_ylabel('Mean FX Return 6h (bps)')
    ax.legend(fontsize=8)

    # 1c. Predictive corr by horizon for best session
    ax = axes[0, 2]
    best_session = 'NY_Close' if 'NY_Close' in session_results and session_results['NY_Close'] else 'All'
    if best_session in session_results and session_results[best_session]:
        pred = session_results[best_session]['pred']
        horizons = [h for h in FX_HORIZONS if not np.isnan(pred[h][0])]
        rs = [pred[h][0] for h in horizons]
        ps_ = [pred[h][1] for h in horizons]
        cols = ['green' if p < 0.05 else 'gray' for p in ps_]
        ax.bar([str(h) for h in horizons], rs, color=cols, alpha=0.7)
        ax.axhline(0, color='black', linewidth=0.8)
        ax.set_title(f'{best_session}: Corr by Horizon')
        ax.set_xlabel('Horizon (hours)')
        ax.set_ylabel('Pearson r')

    # -- Row 2: Dead zone sweep and PnL --

    # 2a. Dead zone sweep heatmap for NY_Close (or best session)
    ax = axes[1, 0]
    sweep_key = 'NY_Close' if 'NY_Close' in dz_sweeps and dz_sweeps['NY_Close'] is not None else list(dz_sweeps.keys())[0]
    if dz_sweeps.get(sweep_key) is not None:
        sweep = dz_sweeps[sweep_key]
        for h in [3, 6, 12]:
            sub = sweep[sweep['horizon'] == h]
            if len(sub) > 0:
                ax.plot(sub['dead_zone'], sub['sharpe'], 'o-', label=f'{h}h', markersize=4)
                # shade CI
                ax.fill_between(sub['dead_zone'], sub['sharpe_lo'], sub['sharpe_hi'], alpha=0.1)
        ax.axhline(0, color='red', linestyle='--', alpha=0.5)
        ax.set_title(f'{sweep_key}: Sharpe by Dead Zone')
        ax.set_xlabel('Dead Zone (z-score units)')
        ax.set_ylabel('Sharpe (annualized)')
        ax.legend(fontsize=8)

    # 2b. Direction comparison equity curves
    ax = axes[1, 1]
    dir_key = 'NY_Close' if 'NY_Close' in dir_results and dir_results['NY_Close'] else list(dir_results.keys())[0]
    if dir_results.get(dir_key):
        for direction, res in dir_results[dir_key].items():
            cum = res['cumulative'] * 10000
            ax.plot(cum.index, cum.values, label=f'{direction} (Sh={res["sharpe"]:.2f})',
                    linewidth=0.7)
        ax.axhline(0, color='black', linewidth=0.5)
        ax.set_title(f'{dir_key}: Cumulative PnL by Direction')
        ax.set_ylabel('Cumulative (bps)')
        ax.legend(fontsize=8)

    # 2c. Dead zone sweep: PF
    ax = axes[1, 2]
    if dz_sweeps.get(sweep_key) is not None:
        sweep = dz_sweeps[sweep_key]
        for h in [3, 6, 12]:
            sub = sweep[sweep['horizon'] == h]
            if len(sub) > 0:
                ax.plot(sub['dead_zone'], sub['pf'], 'o-', label=f'{h}h', markersize=4)
        ax.axhline(1.0, color='red', linestyle='--', alpha=0.5)
        ax.set_title(f'{sweep_key}: PF by Dead Zone')
        ax.set_xlabel('Dead Zone')
        ax.set_ylabel('Profit Factor')
        ax.legend(fontsize=8)

    # -- Row 3: Yearly stability, equity curve, spread heatmap --

    # 3a. Yearly Sharpe for best session
    ax = axes[2, 0]
    best_sess = 'NY_Close'
    sdata = filter_session(data, best_sess)
    ystab = yearly_stability(sdata, horizon=6, dead_zone=1.0)
    if len(ystab) > 0:
        colors_yr = ['green' if s > 0 else 'red' for s in ystab['sharpe']]
        ax.bar(ystab['year'].astype(str), ystab['sharpe'], color=colors_yr, alpha=0.7)
        ax.axhline(0, color='black', linewidth=0.8)
        ax.set_title(f'{best_sess}: Yearly Sharpe (dz=1.0, 6h)')
        ax.set_ylabel('Sharpe')
        ax.tick_params(axis='x', rotation=45)

    # 3b. Overall equity curve for best config
    ax = axes[2, 1]
    sim = naive_pnl_simulation(sdata, horizon=6, dead_zone=1.0)
    if sim:
        cum = sim['cumulative'] * 10000
        ax.plot(cum.index, cum.values, color='steelblue', linewidth=0.5)
        ax.axhline(0, color='black', linewidth=0.5)
        ax.fill_between(cum.index, cum.values, 0, where=cum.values > 0,
                        color='green', alpha=0.1)
        ax.fill_between(cum.index, cum.values, 0, where=cum.values < 0,
                        color='red', alpha=0.1)
        ax.set_title(f'{best_sess}: Equity Curve (dz=1.0, 6h)')
        ax.set_ylabel('Cumulative PnL (bps)')

    # 3c. Hourly heatmap (all hours, multi-horizon)
    ax = axes[2, 2]
    corr_by_hour = []
    for hr in range(24):
        sub = data[data['hour'] == hr].dropna(subset=['fx_ret_6h'])
        if len(sub) > 50:
            r, p = stats.pearsonr(sub['spread'], sub['fx_ret_6h'])
            corr_by_hour.append({'hour': hr, 'corr': r, 'pval': p})
        else:
            corr_by_hour.append({'hour': hr, 'corr': 0, 'pval': 1})
    hdf = pd.DataFrame(corr_by_hour)
    colors_h = ['green' if p < 0.05 else 'lightgray' for p in hdf['pval']]
    ax.bar(hdf['hour'], hdf['corr'], color=colors_h, alpha=0.7)
    ax.axhline(0, color='black', linewidth=0.8)
    # Shade session windows
    ax.axvspan(-0.5, 5.5, alpha=0.05, color='blue', label='Tokyo')
    ax.axvspan(16.5, 20.5, alpha=0.05, color='red', label='NY Close')
    ax.set_title('Predictive Corr by Hour UTC (6h)')
    ax.set_xlabel('Hour (UTC)')
    ax.set_ylabel('Pearson r')
    ax.set_xticks(range(0, 24, 2))
    ax.legend(fontsize=7)

    plt.tight_layout()
    out_path = OUT_DIR / f'vega_fase0b_{pair_cfg["name"]}.png'
    plt.savefig(out_path, dpi=150, bbox_inches='tight')
    print(f'\n  Chart saved: {out_path}')
    if not SAVE_ONLY:
        plt.show()
    plt.close()


# ---------------------------------------------------------------------------
# Permutation test
# ---------------------------------------------------------------------------

def permutation_test(data, session_name, horizon=6, n_perms=2000):
    """
    Shuffle spread labels and re-compute correlation to get null distribution.
    Returns how many permutations exceed the real correlation.
    """
    sdata = filter_session(data, session_name)
    col = f'fx_ret_{horizon}h'
    valid = sdata.dropna(subset=[col])
    if len(valid) < 100:
        return np.nan, np.nan

    real_r, _ = stats.pearsonr(valid['spread'], valid[col])
    rng = np.random.default_rng(42)
    count_exceed = 0
    for _ in range(n_perms):
        shuffled = rng.permutation(valid['spread'].values)
        perm_r, _ = stats.pearsonr(shuffled, valid[col])
        if abs(perm_r) >= abs(real_r):
            count_exceed += 1
    perm_pval = count_exceed / n_perms
    return real_r, perm_pval


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print('=' * 80)
    print(' VEGA FASE 0b: SESSION-FILTERED Z-SCORE DIVERGENCE DEEP STUDY')
    print(f' SMA={SMA_PERIOD}h, ATR={ATR_PERIOD}h')
    print(f' Sessions: {list(SESSIONS.keys())}')
    print(f' Bootstrap: {N_BOOTSTRAP} samples')
    print('=' * 80)

    all_verdicts = []

    for pair_cfg in FX_PAIRS:
        print(f'\n{"="*80}')
        print(f' PAIR: {pair_cfg["label"]}')
        print(f'{"="*80}')

        data = load_and_prepare(pair_cfg)

        # --- Per-session analysis ---
        session_results = {}
        for session_name in SESSIONS:
            res = analyze_pair_session(data, pair_cfg, session_name)
            session_results[session_name] = res

        # --- Dead zone sweeps for key sessions ---
        print(f'\n  === DEAD ZONE SWEEP ===')
        dz_sweeps = {}
        for sess in ['Tokyo', 'NY_Close', 'All']:
            print(f'\n    {sess}:')
            sweep = dead_zone_sweep(data, sess)
            dz_sweeps[sess] = sweep
            if sweep is not None and len(sweep) > 0:
                best = sweep.loc[sweep['sharpe'].idxmax()]
                print(f'      Best: dz={best["dead_zone"]:.1f}, h={best["horizon"]:.0f}h, '
                      f'Sharpe={best["sharpe"]:.3f} [{best["sharpe_lo"]:.3f}, {best["sharpe_hi"]:.3f}], '
                      f'PF={best["pf"]:.3f}, N={best["n_trades"]:.0f}')

        # --- Direction comparison ---
        print(f'\n  === DIRECTION COMPARISON (dz=1.0, 6h) ===')
        dir_results = {}
        for sess in ['Tokyo', 'NY_Close', 'All']:
            print(f'\n    {sess}:')
            dr = direction_comparison(data, sess)
            dir_results[sess] = dr
            if dr:
                for d, r in dr.items():
                    lo, hi = r['sharpe_ci']
                    print(f'      {d:>6s}: Sharpe={r["sharpe"]:.3f} [{lo:.3f},{hi:.3f}], '
                          f'PF={r["pf"]:.3f}, WR={r["win_rate"]:.1%}')

        # --- Permutation tests for key sessions ---
        print(f'\n  === PERMUTATION TESTS (2000 permutations) ===')
        for sess in ['Tokyo', 'NY_Close']:
            real_r, perm_p = permutation_test(data, sess, horizon=6)
            if not np.isnan(real_r):
                sig = '***' if perm_p < 0.001 else '**' if perm_p < 0.01 else '*' if perm_p < 0.05 else 'NOT SIG'
                print(f'    {sess}: r={real_r:.4f}, perm_pval={perm_p:.4f} {sig}')

        # --- Plots ---
        plot_pair_results(data, pair_cfg, session_results, dz_sweeps, dir_results)

        # --- Collect verdict ---
        for sess in ['Tokyo', 'NY_Close', 'All']:
            if session_results.get(sess) and session_results[sess] is not None:
                pred = session_results[sess]['pred']
                r6, p6, n6 = pred.get(6, (np.nan, np.nan, 0))
                best_dz = None
                best_sharpe = np.nan
                best_pf = np.nan
                if dz_sweeps.get(sess) is not None and len(dz_sweeps[sess]) > 0:
                    best_row = dz_sweeps[sess].loc[dz_sweeps[sess]['sharpe'].idxmax()]
                    best_dz = best_row['dead_zone']
                    best_sharpe = best_row['sharpe']
                    best_pf = best_row['pf']
                all_verdicts.append({
                    'pair': pair_cfg['name'],
                    'session': sess,
                    'n': session_results[sess]['n'],
                    'corr_6h': r6,
                    'pval_6h': p6,
                    'best_dz': best_dz,
                    'best_sharpe': best_sharpe,
                    'best_pf': best_pf,
                })

    # ---------------------------------------------------------------------------
    # FINAL VERDICT TABLE
    # ---------------------------------------------------------------------------
    print(f'\n{"="*80}')
    print(f' FINAL VERDICT TABLE')
    print(f'{"="*80}')
    vdf = pd.DataFrame(all_verdicts)
    print(f'\n  {"Pair":>28s}  {"Session":>10s}  {"N":>6s}  {"Corr6h":>8s}  {"pval":>10s}  '
          f'{"BestDZ":>6s}  {"Sharpe":>7s}  {"PF":>6s}  {"Verdict":>10s}')
    for _, row in vdf.iterrows():
        sig = '***' if row['pval_6h'] < 0.001 else '**' if row['pval_6h'] < 0.01 else '*' if row['pval_6h'] < 0.05 else ''
        if row['best_sharpe'] > 0.3 and row['best_pf'] > 1.1:
            verdict = 'PROMISING'
        elif row['best_sharpe'] > 0.1:
            verdict = 'MARGINAL'
        else:
            verdict = 'NO EDGE'
        print(f'  {row["pair"]:>28s}  {row["session"]:>10s}  {row["n"]:>6.0f}  '
              f'{row["corr_6h"]:>8.4f}  {row["pval_6h"]:>10.2e}{sig:>3s}  '
              f'{row["best_dz"]:>6.1f}  {row["best_sharpe"]:>7.3f}  '
              f'{row["best_pf"]:>6.3f}  {verdict:>10s}')

    print(f'\n  Interpretation:')
    print(f'  - PROMISING: Sharpe > 0.3 AND PF > 1.1 in best dead-zone config')
    print(f'  - MARGINAL: Sharpe > 0.1 but below 0.3, or PF < 1.1')
    print(f'  - NO EDGE: Sharpe < 0.1 or PF < 1.0')
    print(f'  - All Sharpe values are BEFORE costs (spread + swap)')
    print(f'  - Bootstrap 95% CI must not cross zero for confidence')
    print(f'  - Must be stable across years (no single year driving result)')


if __name__ == '__main__':
    main()
