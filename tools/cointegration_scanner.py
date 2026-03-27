"""
Cointegration Scanner: Test ALL possible pairs from available data.
Finds which pairs have real, stable cointegration relationships.
"""
import pandas as pd
import numpy as np
from pathlib import Path
from itertools import combinations
import warnings
warnings.filterwarnings('ignore')

DATA_DIR = Path(__file__).parent.parent / 'data'


def load_data(filepath):
    df = pd.read_csv(filepath)
    df['datetime'] = pd.to_datetime(
        df['Date'].astype(str) + ' ' + df['Time'],
        format='%Y%m%d %H:%M:%S'
    )
    df.set_index('datetime', inplace=True)
    return df['Close']


def resample_daily(series):
    return series.resample('1D').last().dropna()


def test_cointegration(y, x):
    """Run Engle-Granger test. Returns dict with results."""
    from statsmodels.regression.linear_model import OLS
    from statsmodels.tsa.stattools import adfuller
    from statsmodels.tools import add_constant

    log_y = np.log(y)
    log_x = np.log(x)

    x_const = add_constant(log_x)
    result = OLS(log_y, x_const).fit()
    residuals = result.resid
    hedge_ratio = result.params.iloc[1]

    adf_stat, adf_pvalue, *_ = adfuller(residuals, maxlag=20)

    # Half-life
    spread_lag = residuals.shift(1).dropna()
    spread_diff = residuals.diff().dropna()
    spread_lag = spread_lag.iloc[1:]
    spread_diff = spread_diff.iloc[1:]
    X = add_constant(spread_lag)
    ou_result = OLS(spread_diff, X).fit()
    theta = ou_result.params.iloc[1]
    half_life = -np.log(2) / theta if theta < 0 else 9999

    # Rolling stability (252-day windows)
    coint_pct = 0.0
    window = 252
    if len(log_y) > window + 50:
        coint_count = 0
        total = 0
        for i in range(window, len(log_y), 20):  # step 20 for speed
            yw = log_y.iloc[i - window:i]
            xw = log_x.iloc[i - window:i]
            xc = add_constant(xw)
            try:
                reg = OLS(yw, xc).fit()
                _, pv, *_ = adfuller(reg.resid, maxlag=10)
                if pv < 0.05:
                    coint_count += 1
            except Exception:
                pass
            total += 1
        coint_pct = 100 * coint_count / total if total > 0 else 0

    # Z-Score trade frequency
    z = (residuals - residuals.mean()) / residuals.std()
    entries_2 = ((z.shift(1) < 2) & (z >= 2)).sum()
    entries_2 += ((z.shift(1) > -2) & (z <= -2)).sum()
    years = len(y) / 252
    trades_per_year = entries_2 / years if years > 0 else 0

    # Correlation
    corr = y.corr(x)

    return {
        'eg_pvalue': adf_pvalue,
        'adf_stat': adf_stat,
        'hedge_ratio': hedge_ratio,
        'r_squared': result.rsquared,
        'half_life': half_life,
        'rolling_coint_pct': coint_pct,
        'correlation': corr,
        'z_range_min': z.min(),
        'z_range_max': z.max(),
        'trades_per_year_z2': trades_per_year,
        'n_days': len(y),
    }


def main():
    # Find all CSV files
    csv_files = sorted(DATA_DIR.glob('*_5m_*.csv'))
    print(f'Found {len(csv_files)} data files\n')

    # Load and resample all
    assets = {}
    for f in csv_files:
        name = f.stem.split('_5m')[0]
        try:
            raw = load_data(f)
            daily = resample_daily(raw)
            assets[name] = daily
            print(f'  {name}: {len(daily)} daily bars '
                  f'({daily.index[0].date()} to {daily.index[-1].date()})')
        except Exception as e:
            print(f'  {name}: FAILED ({e})')

    print(f'\nLoaded {len(assets)} assets. Testing all {len(assets)*(len(assets)-1)//2} pairs...\n')

    # Test all combinations
    results = []
    asset_names = sorted(assets.keys())

    for a, b in combinations(asset_names, 2):
        # Align dates
        common = assets[a].index.intersection(assets[b].index)
        if len(common) < 500:
            continue

        y = assets[a].loc[common]
        x = assets[b].loc[common]

        try:
            r = test_cointegration(y, x)
            r['pair'] = f'{a}/{b}'
            r['asset_a'] = a
            r['asset_b'] = b
            results.append(r)
        except Exception as e:
            print(f'  {a}/{b}: ERROR ({e})')

    # Sort by Engle-Granger p-value (best first)
    results.sort(key=lambda x: x['eg_pvalue'])

    # Print results
    print('=' * 110)
    print('COINTEGRATION SCAN RESULTS (sorted by Engle-Granger p-value)')
    print('=' * 110)
    print(f'{"Pair":<20} {"EG p-val":<10} {"Coint%":<8} {"HalfLife":<10} '
          f'{"Hedge":<10} {"Corr":<8} {"Tr/yr":<7} {"Verdict"}')
    print('-' * 110)

    for r in results:
        hl = f'{r["half_life"]:.0f}d' if r['half_life'] < 9999 else 'INF'

        # Verdict
        eg_ok = r['eg_pvalue'] < 0.05
        roll_ok = r['rolling_coint_pct'] > 50
        hl_ok = 5 < r['half_life'] < 90
        trades_ok = r['trades_per_year_z2'] >= 3

        if eg_ok and roll_ok and hl_ok:
            verdict = '*** STRONG ***'
        elif eg_ok and (roll_ok or hl_ok):
            verdict = '** MODERATE **'
        elif eg_ok:
            verdict = '* WEAK *'
        else:
            verdict = 'FAIL'

        print(f'{r["pair"]:<20} {r["eg_pvalue"]:<10.4f} '
              f'{r["rolling_coint_pct"]:<8.1f} {hl:<10} '
              f'{r["hedge_ratio"]:<10.4f} {r["correlation"]:<8.4f} '
              f'{r["trades_per_year_z2"]:<7.1f} {verdict}')

    # Detail on top candidates
    top = [r for r in results if r['eg_pvalue'] < 0.10]
    if top:
        print(f'\n{"=" * 110}')
        print(f'TOP CANDIDATES (EG p-value < 0.10): {len(top)}')
        print(f'{"=" * 110}')
        for r in top:
            hl = f'{r["half_life"]:.1f}' if r['half_life'] < 9999 else 'INF'
            print(f'\n  {r["pair"]}:')
            print(f'    Engle-Granger p = {r["eg_pvalue"]:.6f}')
            print(f'    Rolling cointegration = {r["rolling_coint_pct"]:.1f}%')
            print(f'    Half-life = {hl} days')
            print(f'    Hedge ratio = {r["hedge_ratio"]:.4f}')
            print(f'    Correlation = {r["correlation"]:.4f}')
            print(f'    Z-Score range = [{r["z_range_min"]:.2f}, {r["z_range_max"]:.2f}]')
            print(f'    Trades/year (|Z|>2) = {r["trades_per_year_z2"]:.1f}')
            print(f'    Data: {r["n_days"]} trading days')
    else:
        print('\nNO candidates with EG p-value < 0.10 found.')

    # Summary
    print(f'\n{"=" * 110}')
    print('SUMMARY')
    print(f'{"=" * 110}')
    strong = [r for r in results if r['eg_pvalue'] < 0.05
              and r['rolling_coint_pct'] > 50
              and 5 < r['half_life'] < 90]
    moderate = [r for r in results if r['eg_pvalue'] < 0.05
                and (r['rolling_coint_pct'] > 50 or 5 < r['half_life'] < 90)
                and r not in strong]
    weak = [r for r in results if r['eg_pvalue'] < 0.05
            and r not in strong and r not in moderate]

    print(f'  STRONG cointegration:   {len(strong)}')
    for r in strong:
        print(f'    -> {r["pair"]}')
    print(f'  MODERATE cointegration: {len(moderate)}')
    for r in moderate:
        print(f'    -> {r["pair"]}')
    print(f'  WEAK cointegration:     {len(weak)}')
    for r in weak:
        print(f'    -> {r["pair"]}')
    print(f'  FAIL:                   {len(results) - len(strong) - len(moderate) - len(weak)}')

    if not strong and not moderate:
        print('\n  CONCLUSION: No viable cointegration pairs found in this dataset.')
        print('  Consider: different timeframes, synthetic pairs, or non-cointegration approaches.')


if __name__ == '__main__':
    main()
