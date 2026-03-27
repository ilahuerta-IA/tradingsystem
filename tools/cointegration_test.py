"""
Cointegration Test: EURUSD vs USDCHF
Statistical validation BEFORE writing any strategy code.
Tests: Engle-Granger, Johansen, Rolling stability, Half-life (O-U)
"""
import pandas as pd
import numpy as np
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / 'data'
EURUSD_FILE = DATA_DIR / 'EURUSD_5m_5Yea.csv'
USDCHF_FILE = DATA_DIR / 'USDCHF_5m_5Yea.csv'


def load_data(filepath):
    df = pd.read_csv(
        filepath,
        parse_dates={'datetime': ['Date', 'Time']},
        date_format='%Y%m%d %H:%M:%S',
    )
    df.set_index('datetime', inplace=True)
    return df['Close']


def resample_daily(series):
    """Resample 5min to daily close for cointegration tests."""
    return series.resample('1D').last().dropna()


def engle_granger_test(y, x):
    """Engle-Granger 2-step cointegration test."""
    from statsmodels.regression.linear_model import OLS
    from statsmodels.tsa.stattools import adfuller
    from statsmodels.tools import add_constant

    x_const = add_constant(x)
    result = OLS(y, x_const).fit()
    residuals = result.resid
    hedge_ratio = result.params.iloc[1]

    adf_stat, adf_pvalue, _, _, crit_values, _ = adfuller(residuals, maxlag=20)

    print('=' * 70)
    print('ENGLE-GRANGER COINTEGRATION TEST')
    print('=' * 70)
    print(f'Hedge Ratio (beta): {hedge_ratio:.6f}')
    print(f'R-squared:          {result.rsquared:.4f}')
    print(f'ADF Statistic:      {adf_stat:.4f}')
    print(f'ADF p-value:        {adf_pvalue:.6f}')
    print(f'Critical values:    1%={crit_values["1%"]:.4f}  '
          f'5%={crit_values["5%"]:.4f}  '
          f'10%={crit_values["10%"]:.4f}')
    if adf_pvalue < 0.01:
        print('RESULT: *** COINTEGRATED at 1% level ***')
    elif adf_pvalue < 0.05:
        print('RESULT: ** COINTEGRATED at 5% level **')
    elif adf_pvalue < 0.10:
        print('RESULT: * COINTEGRATED at 10% level *')
    else:
        print('RESULT: NOT COINTEGRATED (p > 0.10)')
    print()

    return residuals, hedge_ratio, adf_pvalue


def johansen_test(y, x):
    """Johansen cointegration test (confirms Engle-Granger)."""
    from statsmodels.tsa.vector_ar.vecm import coint_johansen

    data = pd.concat([y, x], axis=1).dropna()
    result = coint_johansen(data, det_order=0, k_ar_diff=1)

    print('=' * 70)
    print('JOHANSEN COINTEGRATION TEST')
    print('=' * 70)
    print(f'{"Hypothesis":<20} {"Trace Stat":<15} {"5% Critical":<15} {"Result"}')
    print('-' * 65)
    for i in range(2):
        trace = result.lr1[i]
        crit = result.cvt[i, 1]  # 5% critical value
        status = 'REJECT H0 (cointegrated)' if trace > crit else 'FAIL to reject'
        print(f'r <= {i:<16} {trace:<15.4f} {crit:<15.4f} {status}')

    print(f'\n{"Hypothesis":<20} {"Max-Eig Stat":<15} {"5% Critical":<15} {"Result"}')
    print('-' * 65)
    for i in range(2):
        eig = result.lr2[i]
        crit = result.cvm[i, 1]
        status = 'REJECT H0 (cointegrated)' if eig > crit else 'FAIL to reject'
        print(f'r <= {i:<16} {eig:<15.4f} {crit:<15.4f} {status}')
    print()

    return result


def rolling_cointegration(y, x, window=252):
    """Rolling Engle-Granger test to check stability over time."""
    from statsmodels.regression.linear_model import OLS
    from statsmodels.tsa.stattools import adfuller
    from statsmodels.tools import add_constant

    results = []
    dates = []

    for i in range(window, len(y)):
        y_window = y.iloc[i - window:i]
        x_window = x.iloc[i - window:i]

        x_const = add_constant(x_window)
        reg = OLS(y_window, x_const).fit()
        residuals = reg.resid
        hedge_ratio = reg.params.iloc[1]

        try:
            adf_stat, adf_pvalue, *_ = adfuller(residuals, maxlag=10)
        except Exception:
            adf_pvalue = 1.0
            adf_stat = 0.0

        results.append({
            'date': y.index[i],
            'hedge_ratio': hedge_ratio,
            'adf_pvalue': adf_pvalue,
            'adf_stat': adf_stat,
            'cointegrated_5pct': adf_pvalue < 0.05,
        })

    df_results = pd.DataFrame(results)

    print('=' * 70)
    print(f'ROLLING COINTEGRATION (window={window} days)')
    print('=' * 70)

    total = len(df_results)
    coint_count = df_results['cointegrated_5pct'].sum()
    pct = 100 * coint_count / total

    print(f'Total windows:          {total}')
    print(f'Cointegrated (p<0.05):  {coint_count} ({pct:.1f}%)')
    print(f'NOT cointegrated:       {total - coint_count} ({100 - pct:.1f}%)')
    print(f'Hedge Ratio range:      [{df_results["hedge_ratio"].min():.4f}, '
          f'{df_results["hedge_ratio"].max():.4f}]')
    print(f'Hedge Ratio mean:       {df_results["hedge_ratio"].mean():.4f}')
    print(f'Hedge Ratio std:        {df_results["hedge_ratio"].std():.4f}')

    # Yearly breakdown
    df_results['year'] = df_results['date'].dt.year
    print(f'\nYearly breakdown:')
    print(f'{"Year":<8} {"Windows":<10} {"Coint%":<10} {"Hedge Mean":<12} {"Hedge Std"}')
    print('-' * 55)
    for year, group in df_results.groupby('year'):
        n = len(group)
        c = group['cointegrated_5pct'].sum()
        print(f'{year:<8} {n:<10} {100*c/n:<10.1f} '
              f'{group["hedge_ratio"].mean():<12.4f} '
              f'{group["hedge_ratio"].std():.4f}')

    # Longest break
    not_coint = ~df_results['cointegrated_5pct']
    if not_coint.any():
        streaks = not_coint.astype(int).groupby(
            (~not_coint).cumsum()
        ).sum()
        max_break = streaks.max()
        print(f'\nLongest non-cointegrated streak: {max_break} consecutive days')
    print()

    return df_results


def half_life_ou(spread):
    """Ornstein-Uhlenbeck half-life of mean reversion."""
    from statsmodels.regression.linear_model import OLS

    spread_lag = spread.shift(1).dropna()
    spread_diff = spread.diff().dropna()

    # Align
    spread_lag = spread_lag.iloc[1:]
    spread_diff = spread_diff.iloc[1:]

    # OLS: delta_spread = theta * (spread_lag - mu) + epsilon
    # Simplified: delta_spread = a + b * spread_lag
    from statsmodels.tools import add_constant
    X = add_constant(spread_lag)
    result = OLS(spread_diff, X).fit()

    theta = result.params.iloc[1]

    if theta >= 0:
        print('=' * 70)
        print('HALF-LIFE (Ornstein-Uhlenbeck)')
        print('=' * 70)
        print(f'Theta: {theta:.6f} (positive = NO mean reversion)')
        print('RESULT: Spread does NOT mean-revert. FAIL.')
        print()
        return None

    half_life = -np.log(2) / theta

    print('=' * 70)
    print('HALF-LIFE (Ornstein-Uhlenbeck)')
    print('=' * 70)
    print(f'Theta:     {theta:.6f}')
    print(f'Half-life: {half_life:.1f} days')
    if half_life < 5:
        print('RESULT: Very fast reversion (< 5 days) - may be noise')
    elif half_life < 30:
        print(f'RESULT: Good half-life for trading ({half_life:.0f} days)')
    elif half_life < 90:
        print(f'RESULT: Slow reversion ({half_life:.0f} days) - longer holds needed')
    else:
        print(f'RESULT: Very slow ({half_life:.0f} days) - may not be tradeable intraday')
    print()

    return half_life


def spread_statistics(residuals, hedge_ratio):
    """Basic spread statistics and Z-Score analysis."""
    z_score = (residuals - residuals.mean()) / residuals.std()

    print('=' * 70)
    print('SPREAD & Z-SCORE STATISTICS')
    print('=' * 70)
    print(f'Spread mean:        {residuals.mean():.6f}')
    print(f'Spread std:         {residuals.std():.6f}')
    print(f'Z-Score range:      [{z_score.min():.2f}, {z_score.max():.2f}]')

    # Count Z-Score crossings (potential trades)
    for threshold in [1.5, 2.0, 2.5, 3.0]:
        entries = ((z_score.shift(1) < threshold) & (z_score >= threshold)).sum()
        entries += ((z_score.shift(1) > -threshold) & (z_score <= -threshold)).sum()
        per_year = entries / (len(z_score) / 252)
        print(f'Z-Score crossings |{threshold}|: {entries} total, '
              f'~{per_year:.0f}/year')

    print()


def correlation_analysis(y, x):
    """Simple correlation check."""
    corr = y.corr(x)
    log_corr = np.log(y).corr(np.log(x))

    print('=' * 70)
    print('CORRELATION ANALYSIS')
    print('=' * 70)
    print(f'Price correlation:     {corr:.4f}')
    print(f'Log-price correlation: {log_corr:.4f}')

    # Rolling correlation (252-day)
    rolling_corr = y.rolling(252).corr(x)
    print(f'Rolling 252d corr:     [{rolling_corr.min():.4f}, {rolling_corr.max():.4f}]')
    print(f'Rolling 252d mean:     {rolling_corr.mean():.4f}')
    print()


def main():
    print('Loading EURUSD and USDCHF 5-minute data...')
    eurusd_5m = load_data(EURUSD_FILE)
    usdchf_5m = load_data(USDCHF_FILE)
    print(f'EURUSD: {len(eurusd_5m)} bars ({eurusd_5m.index[0]} to {eurusd_5m.index[-1]})')
    print(f'USDCHF: {len(usdchf_5m)} bars ({usdchf_5m.index[0]} to {usdchf_5m.index[-1]})')

    # Resample to daily for cointegration tests
    eurusd = resample_daily(eurusd_5m)
    usdchf = resample_daily(usdchf_5m)

    # Align dates
    common = eurusd.index.intersection(usdchf.index)
    eurusd = eurusd.loc[common]
    usdchf = usdchf.loc[common]
    print(f'\nDaily aligned: {len(eurusd)} trading days '
          f'({eurusd.index[0].date()} to {eurusd.index[-1].date()})')
    print()

    # 1. Correlation
    correlation_analysis(eurusd, usdchf)

    # 2. Engle-Granger
    residuals, hedge_ratio, eg_pvalue = engle_granger_test(
        np.log(eurusd), np.log(usdchf)
    )

    # 3. Johansen
    johansen_test(np.log(eurusd), np.log(usdchf))

    # 4. Rolling cointegration stability
    rolling_results = rolling_cointegration(
        np.log(eurusd), np.log(usdchf), window=252
    )

    # 5. Half-life
    half_life = half_life_ou(residuals)

    # 6. Spread statistics
    spread_statistics(residuals, hedge_ratio)

    # Final verdict
    print('=' * 70)
    print('FINAL VERDICT')
    print('=' * 70)
    coint_pct = 100 * rolling_results['cointegrated_5pct'].mean()
    if eg_pvalue < 0.05 and coint_pct > 70 and half_life and half_life < 90:
        print('PASS: EURUSD/USDCHF are cointegrated.')
        print(f'  - Engle-Granger p={eg_pvalue:.6f} (< 0.05)')
        print(f'  - Rolling stability: {coint_pct:.1f}% of windows cointegrated')
        print(f'  - Half-life: {half_life:.1f} days')
        print('  -> PROCEED to strategy development (Fase 1)')
    else:
        print('FAIL or MARGINAL:')
        print(f'  - Engle-Granger p={eg_pvalue:.6f} '
              f'({"PASS" if eg_pvalue < 0.05 else "FAIL"})')
        print(f'  - Rolling stability: {coint_pct:.1f}% '
              f'({"PASS" if coint_pct > 70 else "FAIL"})')
        if half_life:
            print(f'  - Half-life: {half_life:.1f} days '
                  f'({"PASS" if half_life < 90 else "FAIL"})')
        else:
            print('  - Half-life: NO mean reversion (FAIL)')
        print('  -> EVALUATE carefully before proceeding')


if __name__ == '__main__':
    main()
