"""
Cointegration Test: AUDUSD vs NZDUSD (1H timeframe)
Rolling window: 200 periods (configurable)
Tests: Engle-Granger, Johansen, Rolling stability, Half-life (O-U)
"""
import pandas as pd
import numpy as np
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

DATA_DIR = Path(__file__).parent.parent / 'data'
AUDUSD_FILE = DATA_DIR / 'AUDUSD_5m_5Yea.csv'
NZDUSD_FILE = DATA_DIR / 'NZDUSD_5m_5Yea.csv'

ROLLING_WINDOW = 200  # periods in 1H bars


def load_data(filepath):
    df = pd.read_csv(filepath)
    df['datetime'] = pd.to_datetime(
        df['Date'].astype(str) + ' ' + df['Time'],
        format='%Y%m%d %H:%M:%S'
    )
    df.set_index('datetime', inplace=True)
    return df['Close']


def resample_1h(series):
    """Resample 5min to 1H close."""
    return series.resample('1h').last().dropna()


def resample_daily(series):
    """Resample 5min to daily close."""
    return series.resample('1D').last().dropna()


def engle_granger_test(y, x, label=''):
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
    print(f'ENGLE-GRANGER COINTEGRATION TEST {label}')
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


def johansen_test(y, x, label=''):
    """Johansen cointegration test."""
    from statsmodels.tsa.vector_ar.vecm import coint_johansen

    data = pd.concat([y, x], axis=1).dropna()
    result = coint_johansen(data, det_order=0, k_ar_diff=1)

    print('=' * 70)
    print(f'JOHANSEN COINTEGRATION TEST {label}')
    print('=' * 70)
    print(f'{"Hypothesis":<20} {"Trace Stat":<15} {"5% Critical":<15} {"Result"}')
    print('-' * 65)
    for i in range(2):
        trace = result.lr1[i]
        crit = result.cvt[i, 1]
        status = 'REJECT H0 -> COINTEGRATED' if trace > crit else 'FAIL to reject'
        print(f'r <= {i:<16} {trace:<15.4f} {crit:<15.4f} {status}')

    print(f'\n{"Hypothesis":<20} {"Max-Eig Stat":<15} {"5% Critical":<15} {"Result"}')
    print('-' * 65)
    for i in range(2):
        eig = result.lr2[i]
        crit = result.cvm[i, 1]
        status = 'REJECT H0 -> COINTEGRATED' if eig > crit else 'FAIL to reject'
        print(f'r <= {i:<16} {eig:<15.4f} {crit:<15.4f} {status}')
    print()

    return result


def rolling_cointegration(y, x, window=200, label=''):
    """Rolling Engle-Granger test to check stability."""
    from statsmodels.regression.linear_model import OLS
    from statsmodels.tsa.stattools import adfuller
    from statsmodels.tools import add_constant

    results = []

    step = max(1, window // 20)  # ~20 samples per window
    for i in range(window, len(y), step):
        y_window = y.iloc[i - window:i]
        x_window = x.iloc[i - window:i]

        x_const = add_constant(x_window)
        try:
            reg = OLS(y_window, x_const).fit()
            residuals = reg.resid
            hedge_ratio = reg.params.iloc[1]
            adf_stat, adf_pvalue, *_ = adfuller(residuals, maxlag=10)
        except Exception:
            continue

        results.append({
            'date': y.index[i],
            'hedge_ratio': hedge_ratio,
            'adf_pvalue': adf_pvalue,
            'adf_stat': adf_stat,
            'cointegrated_5pct': adf_pvalue < 0.05,
            'cointegrated_1pct': adf_pvalue < 0.01,
        })

    df_results = pd.DataFrame(results)

    print('=' * 70)
    print(f'ROLLING COINTEGRATION (window={window}) {label}')
    print('=' * 70)

    total = len(df_results)
    coint5 = df_results['cointegrated_5pct'].sum()
    coint1 = df_results['cointegrated_1pct'].sum()

    print(f'Total windows:            {total}')
    print(f'Cointegrated (p<0.05):    {coint5} ({100*coint5/total:.1f}%)')
    print(f'Cointegrated (p<0.01):    {coint1} ({100*coint1/total:.1f}%)')
    print(f'NOT cointegrated:         {total - coint5} ({100*(total-coint5)/total:.1f}%)')
    print(f'Hedge Ratio range:        [{df_results["hedge_ratio"].min():.4f}, '
          f'{df_results["hedge_ratio"].max():.4f}]')
    print(f'Hedge Ratio mean:         {df_results["hedge_ratio"].mean():.4f}')
    print(f'Hedge Ratio std:          {df_results["hedge_ratio"].std():.4f}')

    # Yearly breakdown
    df_results['year'] = df_results['date'].dt.year
    print(f'\nYearly breakdown:')
    print(f'{"Year":<8} {"Windows":<10} {"Coint5%":<10} {"Coint1%":<10} '
          f'{"Hedge Mean":<12} {"Hedge Std"}')
    print('-' * 65)
    for year, group in df_results.groupby('year'):
        n = len(group)
        c5 = group['cointegrated_5pct'].sum()
        c1 = group['cointegrated_1pct'].sum()
        print(f'{year:<8} {n:<10} {100*c5/n:<10.1f} {100*c1/n:<10.1f} '
              f'{group["hedge_ratio"].mean():<12.4f} '
              f'{group["hedge_ratio"].std():.4f}')

    # Longest break
    not_coint = ~df_results['cointegrated_5pct']
    if not_coint.any():
        groups = (not_coint != not_coint.shift()).cumsum()
        streaks = not_coint.groupby(groups).sum()
        max_break = int(streaks.max()) if len(streaks) > 0 else 0
        # Convert to approximate days
        approx_days = max_break * step / 24  # 1H bars -> days
        print(f'\nLongest non-cointegrated streak: ~{max_break} samples '
              f'(~{approx_days:.0f} trading days)')
    print()

    return df_results


def half_life_ou(spread, label=''):
    """Ornstein-Uhlenbeck half-life of mean reversion."""
    from statsmodels.regression.linear_model import OLS
    from statsmodels.tools import add_constant

    spread_lag = spread.shift(1).dropna()
    spread_diff = spread.diff().dropna()

    spread_lag = spread_lag.iloc[1:]
    spread_diff = spread_diff.iloc[1:]

    X = add_constant(spread_lag)
    result = OLS(spread_diff, X).fit()
    theta = result.params.iloc[1]

    print('=' * 70)
    print(f'HALF-LIFE (Ornstein-Uhlenbeck) {label}')
    print('=' * 70)

    if theta >= 0:
        print(f'Theta: {theta:.6f} (positive = NO mean reversion)')
        print('RESULT: Spread does NOT mean-revert. FAIL.')
        print()
        return None

    half_life = -np.log(2) / theta

    print(f'Theta:        {theta:.6f}')
    print(f'Half-life:    {half_life:.1f} bars')

    # Convert to approx days/hours depending on timeframe
    print(f'  = {half_life:.1f} hours (1H bars)')
    print(f'  = {half_life/24:.1f} days')

    if half_life < 5:
        print('RESULT: Very fast reversion (< 5 bars) -- may be noise')
    elif half_life < 48:
        print(f'RESULT: EXCELLENT for intraday/swing ({half_life:.0f}h = {half_life/24:.1f}d)')
    elif half_life < 200:
        print(f'RESULT: Good for swing trading ({half_life/24:.1f} days)')
    elif half_life < 500:
        print(f'RESULT: Slow reversion ({half_life/24:.1f} days) -- longer holds')
    else:
        print(f'RESULT: Very slow ({half_life/24:.1f} days) -- may not be tradeable')
    print()

    return half_life


def spread_statistics(residuals, label=''):
    """Spread Z-Score analysis."""
    z = (residuals - residuals.mean()) / residuals.std()

    print('=' * 70)
    print(f'SPREAD & Z-SCORE STATISTICS {label}')
    print('=' * 70)
    print(f'Spread mean:        {residuals.mean():.6f}')
    print(f'Spread std:         {residuals.std():.6f}')
    print(f'Z-Score range:      [{z.min():.2f}, {z.max():.2f}]')

    years = (residuals.index[-1] - residuals.index[0]).days / 365.25

    for threshold in [1.0, 1.5, 2.0, 2.5, 3.0]:
        entries = ((z.shift(1) < threshold) & (z >= threshold)).sum()
        entries += ((z.shift(1) > -threshold) & (z <= -threshold)).sum()
        per_year = entries / years if years > 0 else 0
        print(f'Z-Score crossings |{threshold}|: {entries:>4} total, '
              f'~{per_year:.0f}/year')

    print()


def correlation_analysis(y, x, label=''):
    """Correlation check."""
    corr = y.corr(x)
    log_corr = np.log(y).corr(np.log(x))

    rolling_corr = y.rolling(200).corr(x)

    print('=' * 70)
    print(f'CORRELATION ANALYSIS {label}')
    print('=' * 70)
    print(f'Price correlation:     {corr:.4f}')
    print(f'Log-price correlation: {log_corr:.4f}')
    print(f'Rolling 200-bar corr:  [{rolling_corr.min():.4f}, {rolling_corr.max():.4f}]')
    print(f'Rolling 200-bar mean:  {rolling_corr.mean():.4f}')
    print()


def main():
    print('Loading AUDUSD and NZDUSD 5-minute data...')
    audusd_5m = load_data(AUDUSD_FILE)
    nzdusd_5m = load_data(NZDUSD_FILE)
    print(f'AUDUSD: {len(audusd_5m)} bars '
          f'({audusd_5m.index[0]} to {audusd_5m.index[-1]})')
    print(f'NZDUSD: {len(nzdusd_5m)} bars '
          f'({nzdusd_5m.index[0]} to {nzdusd_5m.index[-1]})')

    # =====================================================================
    # 1H TIMEFRAME (primary analysis)
    # =====================================================================
    print('\n' + '#' * 70)
    print('#  1H TIMEFRAME ANALYSIS')
    print('#' * 70)

    audusd_1h = resample_1h(audusd_5m)
    nzdusd_1h = resample_1h(nzdusd_5m)

    common_1h = audusd_1h.index.intersection(nzdusd_1h.index)
    audusd_1h = audusd_1h.loc[common_1h]
    nzdusd_1h = nzdusd_1h.loc[common_1h]
    print(f'\n1H aligned: {len(audusd_1h)} bars '
          f'({audusd_1h.index[0]} to {audusd_1h.index[-1]})')
    print()

    correlation_analysis(audusd_1h, nzdusd_1h, label='(1H)')

    residuals_1h, hedge_1h, eg_pvalue_1h = engle_granger_test(
        np.log(audusd_1h), np.log(nzdusd_1h), label='(1H)'
    )

    johansen_test(np.log(audusd_1h), np.log(nzdusd_1h), label='(1H)')

    rolling_1h = rolling_cointegration(
        np.log(audusd_1h), np.log(nzdusd_1h),
        window=ROLLING_WINDOW, label='(1H, window=200)'
    )

    half_life_1h = half_life_ou(residuals_1h, label='(1H)')

    spread_statistics(residuals_1h, label='(1H)')

    # =====================================================================
    # DAILY TIMEFRAME (for comparison with scanner)
    # =====================================================================
    print('#' * 70)
    print('#  DAILY TIMEFRAME (comparison)')
    print('#' * 70)

    audusd_d = resample_daily(audusd_5m)
    nzdusd_d = resample_daily(nzdusd_5m)

    common_d = audusd_d.index.intersection(nzdusd_d.index)
    audusd_d = audusd_d.loc[common_d]
    nzdusd_d = nzdusd_d.loc[common_d]
    print(f'\nDaily aligned: {len(audusd_d)} bars '
          f'({audusd_d.index[0].date()} to {audusd_d.index[-1].date()})')
    print()

    residuals_d, hedge_d, eg_pvalue_d = engle_granger_test(
        np.log(audusd_d), np.log(nzdusd_d), label='(Daily)'
    )

    johansen_test(np.log(audusd_d), np.log(nzdusd_d), label='(Daily)')

    rolling_d = rolling_cointegration(
        np.log(audusd_d), np.log(nzdusd_d),
        window=252, label='(Daily, window=252)'
    )

    half_life_d = half_life_ou(residuals_d, label='(Daily)')

    spread_statistics(residuals_d, label='(Daily)')

    # =====================================================================
    # FINAL VERDICT
    # =====================================================================
    print('=' * 70)
    print('FINAL VERDICT: AUDUSD / NZDUSD')
    print('=' * 70)

    for label, pv, roll_df, hl in [
        ('1H', eg_pvalue_1h, rolling_1h, half_life_1h),
        ('Daily', eg_pvalue_d, rolling_d, half_life_d),
    ]:
        coint_pct = 100 * roll_df['cointegrated_5pct'].mean()
        hl_val = hl if hl else 9999
        eg_ok = pv < 0.05
        roll_ok = coint_pct > 50
        hl_ok = hl is not None and hl < 500

        if eg_ok and roll_ok and hl_ok:
            verdict = '*** STRONG - PROCEED ***'
        elif eg_ok and (roll_ok or hl_ok):
            verdict = '** MODERATE - PROMISING **'
        elif eg_ok:
            verdict = '* WEAK *'
        else:
            verdict = 'FAIL'

        print(f'\n  [{label}]:')
        print(f'    Engle-Granger p = {pv:.6f} '
              f'({"PASS" if eg_ok else "FAIL"})')
        print(f'    Rolling stability = {coint_pct:.1f}% '
              f'({"PASS" if roll_ok else "FAIL - need >50%"})')
        if hl:
            hl_str = f'{hl:.1f}h = {hl/24:.1f}d' if label == '1H' else f'{hl:.1f}d'
            print(f'    Half-life = {hl_str} '
                  f'({"PASS" if hl_ok else "FAIL"})')
        else:
            print(f'    Half-life = NO REVERSION (FAIL)')
        print(f'    -> {verdict}')


if __name__ == '__main__':
    main()
