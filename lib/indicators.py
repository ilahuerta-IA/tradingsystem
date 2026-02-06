"""
Technical indicators for trading strategies.
All indicators follow Backtrader conventions.

Note: Angle calculation is done inline in strategy using EMA confirm (period 1).
This matches the original sunrise_ogle_eurjpy_pro.py implementation.
"""
import backtrader as bt


class EfficiencyRatio(bt.Indicator):
    """
    Efficiency Ratio (ER) indicator.
    
    Measures trend strength as the ratio of directional movement to total movement.
    Used in Kaufman's Adaptive Moving Average (KAMA) calculation.
    
    ER = |Change over N periods| / Sum of |Individual changes|
    
    Values:
    - ER close to 1.0 = Strong trend (price moving efficiently in one direction)
    - ER close to 0.0 = Choppy/ranging market (price moving back and forth)
    
    Usage:
        er = EfficiencyRatio(data.close, period=10)
        if er[0] > 0.35:  # Trending market
            allow_entry = True
    """
    lines = ('er',)
    params = (
        ('period', 10),
    )
    
    plotinfo = dict(
        subplot=True,
        plotname='Efficiency Ratio',
        plotlinelabels=True,
    )
    plotlines = dict(
        er=dict(color='orange', linewidth=1.2),
    )
    
    def __init__(self):
        pass
    
    def next(self):
        if len(self.data) < self.p.period + 1:
            self.lines.er[0] = 0.0
            return
        
        # Directional change over period
        change = abs(self.data[0] - self.data[-self.p.period])
        
        # Sum of absolute individual changes (volatility)
        volatility = sum(
            abs(self.data[-i] - self.data[-i - 1])
            for i in range(self.p.period)
        )
        
        if volatility > 0:
            self.lines.er[0] = change / volatility
        else:
            self.lines.er[0] = 0.0


class KAMA(bt.Indicator):
    """
    Kaufman's Adaptive Moving Average (KAMA).
    
    Adapts smoothing based on market efficiency:
    - High efficiency (trending) → faster response
    - Low efficiency (choppy) → slower response
    
    Formula:
        ER = |Change| / Volatility
        SC = (ER * (fast_sc - slow_sc) + slow_sc)^2
        KAMA = KAMA[-1] + SC * (Price - KAMA[-1])
    
    Usage:
        kama = KAMA(data.close, period=10, fast=2, slow=30)
    """
    lines = ('kama',)
    params = (
        ('period', 10),      # Efficiency ratio period
        ('fast', 2),         # Fast smoothing constant period
        ('slow', 30),        # Slow smoothing constant period
    )
    
    plotinfo = dict(
        subplot=False,
        plotlinelabels=True,
    )
    plotlines = dict(
        kama=dict(color='purple', linewidth=1.5),
    )
    
    def __init__(self):
        self.fast_sc = 2.0 / (self.p.fast + 1.0)
        self.slow_sc = 2.0 / (self.p.slow + 1.0)
        # Set minimum period needed
        self.addminperiod(self.p.period + 1)
    
    def nextstart(self):
        self.lines.kama[0] = sum(self.data.get(size=self.p.period)) / self.p.period
    
    def next(self):
        change = abs(self.data[0] - self.data[-self.p.period])
        volatility = sum(abs(self.data[-i] - self.data[-i-1]) for i in range(self.p.period))
        
        if volatility != 0:
            er = change / volatility
        else:
            er = 0
        
        sc = (er * (self.fast_sc - self.slow_sc) + self.slow_sc) ** 2
        self.lines.kama[0] = self.lines.kama[-1] + sc * (self.data[0] - self.lines.kama[-1])


class ROC(bt.Indicator):
    """
    Rate of Change (ROC) indicator.
    
    Measures the percentage change in price over N periods.
    
    Formula:
        ROC = (close - close[-period]) / close[-period]
    
    Values:
    - Positive: Price increased over period
    - Negative: Price decreased over period
    - Magnitude indicates strength of move
    
    Usage:
        roc = ROC(data.close, period=12)
        if roc[0] > 0.001:  # Price up >0.1%
            # Bullish momentum
    """
    lines = ('roc',)
    params = (
        ('period', 12),  # Lookback period for ROC calculation
    )
    
    plotinfo = dict(
        subplot=True,
        plotname='Rate of Change',
        plotlinelabels=True,
    )
    plotlines = dict(
        roc=dict(color='blue', linewidth=1.2),
    )
    
    def __init__(self):
        self.addminperiod(self.p.period + 1)
    
    def next(self):
        old_price = self.data[-self.p.period]
        if old_price != 0:
            self.lines.roc[0] = (self.data[0] - old_price) / old_price
        else:
            self.lines.roc[0] = 0.0


def calculate_roc(current_price: float, old_price: float) -> float:
    """
    Calculate Rate of Change (helper function for non-backtrader use).
    
    Args:
        current_price: Current price
        old_price: Price N periods ago
    
    Returns:
        ROC as decimal (0.01 = 1% change)
    
    Usage:
        # With price history list
        roc = calculate_roc(prices[-1], prices[-period-1])
    """
    if old_price == 0:
        return 0.0
    return (current_price - old_price) / old_price


def calculate_roc_from_history(prices: list, period: int) -> float:
    """
    Calculate ROC from price history list.
    
    Args:
        prices: List of prices (most recent at end)
        period: Lookback period
    
    Returns:
        ROC as decimal, or 0.0 if insufficient data
    """
    if len(prices) < period + 1:
        return 0.0
    return calculate_roc(prices[-1], prices[-period - 1])


class SpectralEntropy(bt.Indicator):
    """
    Spectral Entropy (SE) indicator.
    
    Measures the "randomness" or "structure" of price movements using FFT
    (Fast Fourier Transform) to analyze frequency components.
    
    Spectral Entropy Theory:
    - Low SE (~0.0-0.5): Dominant frequency exists = structured trend/cycle
    - High SE (~0.7-1.0): Energy spread across frequencies = random/noisy
    
    For HTF analysis, use resampledata() to create HTF datafeed and apply
    SE indicator on that feed. This ensures proper calculation and plotting.
    
    Usage:
        # On same timeframe
        se = SpectralEntropy(data.close, period=30)
        
        # On HTF (use resampledata first)
        data_60m = cerebro.resampledata(data, timeframe=bt.TimeFrame.Minutes, compression=60)
        se_htf = SpectralEntropy(data_60m.close, period=30)
    """
    lines = ('se',)
    params = (
        ('period', 30),  # FFT window period
    )
    
    plotinfo = dict(
        subplot=True,
        plotname='Spectral Entropy',
        plotlinelabels=True,
    )
    plotlines = dict(
        se=dict(color='cyan', linewidth=1.2),
    )
    
    def __init__(self):
        import numpy as np
        self.np = np
        self.addminperiod(self.p.period + 1)
    
    def next(self):
        if len(self.data) < self.p.period + 1:
            self.lines.se[0] = 1.0
            return
        
        # Get prices - use self.data.get() for efficiency
        prices = self.np.array(self.data.get(size=self.p.period + 1))
        
        # Calculate SE
        se_value = self._calculate_se(prices)
        self.lines.se[0] = se_value
    
    def _calculate_se(self, prices):
        """Calculate Spectral Entropy from price array using periodogram."""
        if len(prices) < 4:
            return 1.0
        
        try:
            # Use periodogram for cleaner spectral estimation
            from scipy.signal import periodogram
            _, psd = periodogram(prices)
            
            # Normalize to probability distribution
            total_power = self.np.sum(psd)
            if total_power <= 0:
                return 1.0
            
            psd_norm = psd / total_power
            
            # Shannon entropy (avoid log(0))
            psd_norm = psd_norm[psd_norm > 0]
            if len(psd_norm) == 0:
                return 1.0
            
            entropy = -self.np.sum(psd_norm * self.np.log2(psd_norm + 1e-12))
            
            # Normalize to [0, 1]
            max_entropy = self.np.log2(len(psd_norm))
            if max_entropy <= 0:
                return 1.0
            
            return float(min(max(entropy / max_entropy, 0.0), 1.0))
        except:
            return 1.0


class SEStdDev(bt.Indicator):
    """
    SE Stability Indicator - Standard Deviation of Spectral Entropy.
    
    Measures the stability/consistency of SE over N periods.
    
    Low StdDev = SE is stable = market in consistent regime = good for entry
    High StdDev = SE is volatile = market changing regime = avoid
    
    Usage:
        se = SpectralEntropy(data, period=20, htf_mult=6)
        se_std = SEStdDev(se, period=5)
        if se_std[0] < 0.03:  # Stable SE
            allow_entry = True
    """
    lines = ('stddev',)
    params = (
        ('period', 5),  # Lookback for StdDev calculation
    )
    
    plotinfo = dict(
        subplot=True,
        plotname='SE StdDev',
        plotlinelabels=True,
    )
    plotlines = dict(
        stddev=dict(color='yellow', linewidth=1.2),
    )
    
    def __init__(self):
        import numpy as np
        self.np = np
        self.addminperiod(self.p.period)
    
    def next(self):
        if len(self.data) < self.p.period:
            self.lines.stddev[0] = 0.0
            return
        
        # Get recent SE values
        se_values = [self.data[-i] for i in range(self.p.period)]
        self.lines.stddev[0] = float(self.np.std(se_values))


class HTFIndicatorSync(bt.Indicator):
    """
    Syncs an HTF indicator line to the base timeframe for plotting.
    
    Problem: When you calculate an indicator on HTF data (e.g., 60m), it has
    fewer data points than the base TF (e.g., 5m). Backtrader cannot plot
    arrays of different lengths on the same chart.
    
    Solution: This indicator runs on the BASE data and uses coupling ()
    to read values from an HTF indicator line.
    
    Usage:
        # In strategy __init__:
        self.htf_se_raw = SpectralEntropy(self.datas[1].close, period=30)
        self.htf_se_raw.plotinfo.plot = False  # Hide raw HTF
        
        # Sync to base TF for plotting - pass the LINE directly
        self.htf_se = HTFIndicatorSync(self.data0, htf_line=self.htf_se_raw.lines.se)
        self.htf_se.plotinfo.plotname = 'SE(60m)'
    """
    lines = ('value',)
    params = (
        ('htf_line', None),  # The HTF indicator LINE (not indicator) to sync
    )
    
    plotinfo = dict(
        subplot=True,
        plotname='HTF Synced',
        plotlinelabels=True,
    )
    plotlines = dict(
        value=dict(color='cyan', linewidth=1.2),
    )
    
    def __init__(self):
        # Use Backtrader's coupling mechanism - THIS IS THE KEY
        # By using the htf_line in an operation, Backtrader will auto-sync
        if self.p.htf_line is not None:
            # Direct coupling - Backtrader handles the sync automatically
            self.lines.value = self.p.htf_line()


# =============================================================================
# DEPRECATED - Use SpectralEntropy with htf_mult parameter instead
# =============================================================================
# class SpectralEntropyHTF was an earlier attempt that didn't work correctly.
# The SpectralEntropy class now has built-in HTF aggregation via htf_mult param.
# Keeping this commented for reference only.
# =============================================================================