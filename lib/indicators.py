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
    Spectral Entropy (SE) indicator.
    
    Measures the "randomness" or "structure" of price movements using FFT
    (Fast Fourier Transform) to analyze frequency components of returns.
    
    Spectral Entropy Theory:
    - Low SE (~0.0-0.5): Dominant frequency exists = structured trend/cycle
    - High SE (~0.7-1.0): Energy spread across frequencies = random/noisy
    
    Key difference from Efficiency Ratio (ER):
    - ER measures directional efficiency (trending vs choppy)
    - SE measures frequency structure (dominant pattern vs noise)
    
    For HELIX strategy:
    - SE < threshold indicates structured movement → potential trend
    - Works on pairs where ER fails to detect structure fast enough
    
    Usage:
        se = SpectralEntropy(data.close, period=20)
        if se[0] < 0.7:  # Structured market
            allow_entry = True
    """
    lines = ('se',)
    params = (
        ('period', 20),  # FFT window period
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
    
    def next(self):
        if len(self.data) < self.p.period + 1:
            self.lines.se[0] = 1.0  # Max entropy when insufficient data
            return
        
        # Gather price data
        prices = [self.data[-i] for i in range(self.p.period, -1, -1)]
        
        # Calculate returns
        returns = self.np.diff(prices) / self.np.array(prices[:-1])
        returns = returns[self.np.isfinite(returns)]
        
        if len(returns) < 4:
            self.lines.se[0] = 1.0
            return
        
        # FFT and power spectrum
        fft_result = self.np.fft.fft(returns)
        power_spectrum = self.np.abs(fft_result) ** 2
        
        # Positive frequencies only
        n_freqs = len(power_spectrum) // 2
        if n_freqs < 2:
            self.lines.se[0] = 1.0
            return
        
        power_spectrum = power_spectrum[1:n_freqs + 1]
        
        # Normalize to probability
        total_power = self.np.sum(power_spectrum)
        if total_power <= 0:
            self.lines.se[0] = 1.0
            return
        
        prob = power_spectrum / total_power
        prob = prob[prob > 0]
        
        if len(prob) == 0:
            self.lines.se[0] = 1.0
            return
        
        # Shannon entropy (normalized)
        entropy = -self.np.sum(prob * self.np.log2(prob))
        max_entropy = self.np.log2(len(prob))
        
        if max_entropy <= 0:
            self.lines.se[0] = 1.0
            return
        
        self.lines.se[0] = float(min(max(entropy / max_entropy, 0.0), 1.0))
