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


class SpectralEntropy(bt.Indicator):
    """
    Spectral Entropy (SE) indicator with optional internal HTF aggregation.
    
    Measures the "randomness" or "structure" of price movements using FFT
    (Fast Fourier Transform) to analyze frequency components of returns.
    
    Spectral Entropy Theory:
    - Low SE (~0.0-0.5): Dominant frequency exists = structured trend/cycle
    - High SE (~0.7-1.0): Energy spread across frequencies = random/noisy
    
    Key difference from Efficiency Ratio (ER):
    - ER measures directional efficiency (trending vs choppy)
    - SE measures frequency structure (dominant pattern vs noise)
    
    Internal HTF Aggregation:
    - When htf_mult > 1, indicator aggregates base TF bars internally
    - E.g., htf_mult=6 on 5m data = 30m aggregated bars
    - This gives TRUE HTF frequency analysis without external resampling
    
    Usage:
        # Standard (same timeframe)
        se = SpectralEntropy(data.close, period=20)
        
        # HTF (6x aggregation = 30m on 5m data)
        se_htf = SpectralEntropy(data, period=20, htf_mult=6)
    """
    lines = ('se',)
    params = (
        ('period', 20),    # FFT window period (in HTF bars if htf_mult > 1)
        ('htf_mult', 1),   # HTF multiplier (1=same TF, 6=30m from 5m, etc.)
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
        # Buffer for HTF aggregation
        self._htf_closes = []
        self._bar_count = 0
        self._last_se_value = 1.0
        
        # Minimum bars needed for calculation
        # For HTF, we need period * htf_mult base bars to get 'period' HTF bars
        min_bars = self.p.period * self.p.htf_mult + 2
        self.addminperiod(min_bars)
    
    def next(self):
        self._bar_count += 1
        
        # If using HTF aggregation
        if self.p.htf_mult > 1:
            # Store close for aggregation
            self._htf_closes.append(float(self.data.close[0]))
            
            # Only calculate when we have a complete HTF bar
            if self._bar_count % self.p.htf_mult != 0:
                # Keep previous SE value (smooth)
                self.lines.se[0] = self._last_se_value
                return
            
            # Calculate HTF closes (last close of each htf_mult group)
            required_base_bars = (self.p.period + 1) * self.p.htf_mult
            if len(self._htf_closes) < required_base_bars:
                self.lines.se[0] = 1.0
                self._last_se_value = 1.0
                return
            
            # Extract HTF closes (take last bar of each group)
            recent_closes = self._htf_closes[-required_base_bars:]
            htf_closes = [
                recent_closes[i * self.p.htf_mult + self.p.htf_mult - 1]
                for i in range(self.p.period + 1)
            ]
            prices = htf_closes
            
            # Cleanup old data
            max_buffer = required_base_bars + self.p.htf_mult * 2
            if len(self._htf_closes) > max_buffer:
                self._htf_closes = self._htf_closes[-max_buffer:]
        else:
            # Standard calculation on same timeframe
            if len(self.data) < self.p.period + 1:
                self.lines.se[0] = 1.0
                self._last_se_value = 1.0
                return
            prices = [self.data.close[-i] for i in range(self.p.period, -1, -1)]
        
        # Calculate SE from prices
        se_value = self._calculate_se(prices)
        self.lines.se[0] = se_value
        self._last_se_value = se_value
    
    def _calculate_se(self, prices):
        """Calculate Spectral Entropy from price array."""
        prices = self.np.array(prices)
        
        # Calculate returns
        returns = self.np.diff(prices) / prices[:-1]
        returns = returns[self.np.isfinite(returns)]
        
        if len(returns) < 4:
            return 1.0
        
        # FFT and power spectrum
        fft_result = self.np.fft.fft(returns)
        power_spectrum = self.np.abs(fft_result) ** 2
        
        # Positive frequencies only
        n_freqs = len(power_spectrum) // 2
        if n_freqs < 2:
            return 1.0
        
        power_spectrum = power_spectrum[1:n_freqs + 1]
        
        # Normalize to probability
        total_power = self.np.sum(power_spectrum)
        if total_power <= 0:
            return 1.0
        
        prob = power_spectrum / total_power
        prob = prob[prob > 0]
        
        if len(prob) == 0:
            return 1.0
        
        # Shannon entropy (normalized)
        entropy = -self.np.sum(prob * self.np.log2(prob))
        max_entropy = self.np.log2(len(prob))
        
        if max_entropy <= 0:
            return 1.0
        
        return float(min(max(entropy / max_entropy, 0.0), 1.0))


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


# =============================================================================
# DEPRECATED - Use SpectralEntropy with htf_mult parameter instead
# =============================================================================
# class SpectralEntropyHTF was an earlier attempt that didn't work correctly.
# The SpectralEntropy class now has built-in HTF aggregation via htf_mult param.
# Keeping this commented for reference only.
# =============================================================================