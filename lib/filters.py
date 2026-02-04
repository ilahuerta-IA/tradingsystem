"""
Reusable trade filters for all strategies.

Simple pure functions that can be shared across:
- Backtrader strategies (backtest)
- MT5 live trading bot
- Future strategies (Koi, etc.)

Usage:
    from lib.filters import check_time_filter, check_atr_filter
    
    if not check_time_filter(dt, allowed_hours):
        return False
"""

import math
from datetime import datetime
from typing import List, Optional


# =============================================================================
# TIME FILTERS
# =============================================================================

def check_time_filter(dt: datetime, allowed_hours: List[int], enabled: bool = True) -> bool:
    """
    Check if datetime hour is in allowed hours list.
    
    Args:
        dt: Current datetime
        allowed_hours: List of allowed hours (0-23), e.g., [5,6,7,8,9,10,11,12,13,14,15,16,17,18]
        enabled: If False, always returns True (filter disabled)
    
    Returns:
        True if hour is allowed or filter disabled
    
    Example:
        check_time_filter(dt, [5,6,7,8,9,10,11,12,13,14,15,16,17,18])  # 5:00-18:00 UTC
    """
    if not enabled:
        return True
    if not allowed_hours:
        return True  # Empty list = no restriction
    return dt.hour in allowed_hours


def check_day_filter(dt: datetime, allowed_days: List[int], enabled: bool = True) -> bool:
    """
    Check if datetime day of week is in allowed days list.
    
    Args:
        dt: Current datetime
        allowed_days: List of allowed weekdays (0=Monday, 6=Sunday)
                      e.g., [0,1,2,3,4] for Monday-Friday
        enabled: If False, always returns True (filter disabled)
    
    Returns:
        True if day is allowed or filter disabled
    
    Example:
        check_day_filter(dt, [0,1,2,4])  # Monday, Tuesday, Wednesday, Friday (skip Thursday)
    """
    if not enabled:
        return True
    if not allowed_days:
        return True  # Empty list = no restriction
    return dt.weekday() in allowed_days


# =============================================================================
# ATR FILTERS
# =============================================================================

def check_atr_filter(atr: float, min_atr: float, max_atr: float, enabled: bool = True) -> bool:
    """
    Check if ATR is within valid range.
    
    Args:
        atr: Current ATR value
        min_atr: Minimum ATR threshold
        max_atr: Maximum ATR threshold
        enabled: If False, always returns True
    
    Returns:
        True if ATR within range or filter disabled
    
    Example:
        check_atr_filter(0.05, 0.03, 0.09)  # True - within 0.030-0.090
    """
    if not enabled:
        return True
    return min_atr <= atr <= max_atr


# =============================================================================
# ANGLE FILTERS
# =============================================================================

def check_angle_filter(angle: float, min_angle: float, max_angle: float, enabled: bool = True) -> bool:
    """
    Check if angle is within valid range.
    
    Args:
        angle: Current angle in degrees
        min_angle: Minimum angle threshold
        max_angle: Maximum angle threshold
        enabled: If False, always returns True
    
    Returns:
        True if angle within range or filter disabled
    
    Example:
        check_angle_filter(75.5, 45.0, 95.0)  # True - within 45-95 degrees
    """
    if not enabled:
        return True
    return min_angle <= angle <= max_angle


# =============================================================================
# SL PIPS FILTERS
# =============================================================================

def check_sl_pips_filter(sl_pips: float, min_pips: float, max_pips: float, enabled: bool = True) -> bool:
    """
    Check if Stop Loss pips is within valid range.
    
    Args:
        sl_pips: Stop loss size in pips
        min_pips: Minimum SL pips threshold
        max_pips: Maximum SL pips threshold
        enabled: If False, always returns True
    
    Returns:
        True if SL pips within range or filter disabled
    
    Example:
        check_sl_pips_filter(25.5, 20.0, 50.0)  # True - within 20-50 pips
    """
    if not enabled:
        return True
    return min_pips <= sl_pips <= max_pips


# =============================================================================
# EFFICIENCY RATIO (HTF) FILTERS
# =============================================================================

def check_efficiency_ratio_filter(
    er_value: float, 
    threshold: float, 
    enabled: bool = True
) -> bool:
    """
    Check if market is trending using Efficiency Ratio.
    
    Efficiency Ratio (ER) measures trend strength:
    - ER close to 1.0 = Strong trend (directional movement)
    - ER close to 0.0 = Choppy/sideways (no clear direction)
    
    Filters out entries when market is too choppy.
    
    Args:
        er_value: Current Efficiency Ratio value (0.0 to 1.0)
        threshold: Minimum ER required to allow entry (e.g., 0.35)
        enabled: If False, always returns True
    
    Returns:
        True if ER >= threshold or filter disabled
    
    Example:
        check_efficiency_ratio_filter(0.42, 0.35)  # True - trending
        check_efficiency_ratio_filter(0.20, 0.35)  # False - choppy
    """
    if not enabled:
        return True
    return er_value >= threshold


def calculate_efficiency_ratio(prices: list, period: int = 10) -> float:
    """
    Calculate Efficiency Ratio from price list.
    
    Pure function for use in any context (backtest, live, analysis).
    
    ER = |Price change over N periods| / Sum(|Individual price changes|)
    
    Args:
        prices: List of prices (most recent last), needs period + 1 values
        period: Lookback period for calculation
    
    Returns:
        Efficiency Ratio value (0.0 to 1.0)
    
    Example:
        prices = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110]
        er = calculate_efficiency_ratio(prices, period=10)  # ~1.0 (strong trend)
    """
    if len(prices) < period + 1:
        return 0.0
    
    # Directional change
    change = abs(prices[-1] - prices[-period - 1])
    
    # Sum of individual absolute changes
    volatility = sum(
        abs(prices[-i] - prices[-i - 1])
        for i in range(1, period + 1)
    )
    
    if volatility > 0:
        return change / volatility
    return 0.0


# =============================================================================
# SPECTRAL ENTROPY (HTF) FILTERS - HELIX STRATEGY
# =============================================================================

def calculate_spectral_entropy(prices: list, period: int = 20) -> float:
    """
    Calculate Spectral Entropy from price returns.
    
    Spectral Entropy measures the "randomness" or "structure" of price movements
    using FFT (Fast Fourier Transform) to analyze frequency components.
    
    Theory:
    - Low SE (~0.0-0.5): Dominant frequency = structured trend/cycle
    - High SE (~0.7-1.0): Spread across frequencies = random/noisy
    
    For HELIX strategy (LONG only):
    - SE < threshold indicates structured movement → potential trend
    - Combined with KAMA bullish bias for direction confirmation
    
    Args:
        prices: List of prices (most recent last), needs period + 1 values
        period: Lookback period for FFT calculation (power of 2 recommended but not required)
    
    Returns:
        Spectral Entropy value (0.0 to 1.0, normalized)
    
    Example:
        prices = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110]
        se = calculate_spectral_entropy(prices, period=10)
    """
    import numpy as np
    
    if len(prices) < period + 1:
        return 1.0  # Return max entropy (uncertain) if insufficient data
    
    # Calculate returns over period
    recent_prices = prices[-(period + 1):]
    returns = np.diff(recent_prices) / np.array(recent_prices[:-1])
    
    # Remove any NaN/Inf
    returns = returns[np.isfinite(returns)]
    if len(returns) < 4:  # Need at least 4 samples for meaningful FFT
        return 1.0
    
    # Apply FFT
    fft_result = np.fft.fft(returns)
    power_spectrum = np.abs(fft_result) ** 2
    
    # Only use positive frequencies (first half, excluding DC component)
    n_freqs = len(power_spectrum) // 2
    if n_freqs < 2:
        return 1.0
    
    power_spectrum = power_spectrum[1:n_freqs + 1]
    
    # Normalize to get probability distribution
    total_power = np.sum(power_spectrum)
    if total_power <= 0:
        return 1.0
    
    prob = power_spectrum / total_power
    
    # Remove zeros for log calculation
    prob = prob[prob > 0]
    if len(prob) == 0:
        return 1.0
    
    # Calculate Shannon entropy
    entropy = -np.sum(prob * np.log2(prob))
    
    # Normalize by maximum possible entropy (log2 of number of frequencies)
    max_entropy = np.log2(len(prob))
    if max_entropy <= 0:
        return 1.0
    
    normalized_entropy = entropy / max_entropy
    
    return float(min(max(normalized_entropy, 0.0), 1.0))


def check_spectral_entropy_filter(
    se_value: float,
    threshold: float,
    enabled: bool = True
) -> bool:
    """
    Check if market has structure using Spectral Entropy.
    
    Spectral Entropy (SE) measures market randomness:
    - SE close to 0.0 = Structured/trending (dominant frequency)
    - SE close to 1.0 = Random/noisy (no clear pattern)
    
    For trend-following (HELIX), we want LOWER entropy = more structure.
    This is OPPOSITE to ER: ER high = trending, SE low = trending.
    
    Args:
        se_value: Current Spectral Entropy value (0.0 to 1.0)
        threshold: Maximum SE allowed for entry (e.g., 0.7)
        enabled: If False, always returns True
    
    Returns:
        True if SE <= threshold or filter disabled
    
    Example:
        check_spectral_entropy_filter(0.45, 0.7)  # True - structured
        check_spectral_entropy_filter(0.85, 0.7)  # False - too noisy
    """
    if not enabled:
        return True
    return se_value <= threshold


# =============================================================================
# PULLBACK DETECTION (Reusable for any strategy)
# =============================================================================

def detect_pullback(
    highs: list,
    lows: list,
    closes: list,
    kama_values: list,
    min_bars: int = 2,
    max_bars: int = 5,
    enabled: bool = True
) -> dict:
    """
    Detect pullback pattern for trend continuation entries.
    
    Pullback definition:
    1. Price made a Higher High (HH) in lookback period
    2. N consecutive bars without new HH (consolidation)
    3. Price respects support level (stays above KAMA)
    
    This is a REUSABLE function for any strategy needing pullback detection.
    
    Args:
        highs: List of high prices (most recent last), needs max_bars + 2 values
        lows: List of low prices (most recent last)
        closes: List of close prices (most recent last)
        kama_values: List of KAMA/MA values (most recent last)
        min_bars: Minimum bars without new HH to confirm pullback
        max_bars: Maximum bars to wait (timeout if exceeded)
        enabled: If False, returns invalid pullback
    
    Returns:
        dict with:
            'valid': bool - True if pullback detected
            'bars_since_hh': int - Bars since last HH
            'hh_price': float - The Higher High price
            'pullback_low': float - Lowest low during pullback
            'breakout_level': float - HH price (for breakout detection)
            'respects_support': bool - Price stayed above KAMA
    
    Example:
        result = detect_pullback(highs, lows, closes, kama_values, min_bars=2, max_bars=5)
        if result['valid']:
            breakout_level = result['breakout_level']
    """
    if not enabled:
        return {'valid': False, 'bars_since_hh': 0, 'hh_price': 0, 
                'pullback_low': 0, 'breakout_level': 0, 'respects_support': False}
    
    # Need enough data
    required_len = max_bars + 2
    if len(highs) < required_len or len(lows) < required_len:
        return {'valid': False, 'bars_since_hh': 0, 'hh_price': 0,
                'pullback_low': 0, 'breakout_level': 0, 'respects_support': False}
    
    # Find the Higher High in lookback
    # We look back max_bars+1 to find the HH, then count bars since
    lookback_highs = highs[-(max_bars + 2):-1]  # Exclude current bar
    hh_price = max(lookback_highs)
    hh_index = len(lookback_highs) - 1 - lookback_highs[::-1].index(hh_price)
    
    # Bars since HH (how many bars ago was the HH?)
    bars_since_hh = len(lookback_highs) - 1 - hh_index
    
    # Current bar high
    current_high = highs[-1]
    
    # If current bar makes new HH, no pullback yet
    if current_high >= hh_price:
        return {'valid': False, 'bars_since_hh': 0, 'hh_price': hh_price,
                'pullback_low': 0, 'breakout_level': 0, 'respects_support': False}
    
    # Check if we have min_bars without new HH
    if bars_since_hh < min_bars:
        return {'valid': False, 'bars_since_hh': bars_since_hh, 'hh_price': hh_price,
                'pullback_low': 0, 'breakout_level': 0, 'respects_support': False}
    
    # Check if exceeded max_bars (timeout)
    if bars_since_hh > max_bars:
        return {'valid': False, 'bars_since_hh': bars_since_hh, 'hh_price': hh_price,
                'pullback_low': 0, 'breakout_level': 0, 'respects_support': False}
    
    # Calculate pullback low (lowest low since HH)
    pullback_lows = lows[-(bars_since_hh + 1):]
    pullback_low = min(pullback_lows)
    
    # Check if price respects KAMA (all closes above KAMA during pullback)
    pullback_closes = closes[-(bars_since_hh + 1):]
    pullback_kamas = kama_values[-(bars_since_hh + 1):]
    respects_support = all(c > k for c, k in zip(pullback_closes, pullback_kamas))
    
    # Valid pullback: min_bars <= bars_since_hh <= max_bars AND respects support
    valid = respects_support
    
    return {
        'valid': valid,
        'bars_since_hh': bars_since_hh,
        'hh_price': hh_price,
        'pullback_low': pullback_low,
        'breakout_level': hh_price,  # Breakout = break above HH
        'respects_support': respects_support
    }


def check_pullback_breakout(
    current_high: float,
    breakout_level: float,
    buffer_pips: float = 0.0,
    pip_value: float = 0.01
) -> bool:
    """
    Check if price breaks above pullback high (breakout confirmation).
    
    Args:
        current_high: Current bar high price
        breakout_level: The HH price to break
        buffer_pips: Additional buffer in pips above breakout level
        pip_value: Value of 1 pip for this asset
    
    Returns:
        True if high > breakout_level + buffer
    
    Example:
        if check_pullback_breakout(150.25, 150.10, buffer_pips=5, pip_value=0.01):
            # Breakout confirmed, enter trade
    """
    buffer = buffer_pips * pip_value
    return current_high > (breakout_level + buffer)


# =============================================================================
# CONFIRMATION HOLD (Reusable for mean reversion strategies)
# =============================================================================

def check_confirmation_hold(
    current_low: float,
    invalidation_level: float,
    bars_waiting: int,
    required_bars: int,
    offset_pips: float = 0.0,
    pip_value: float = 0.0001,
    enabled: bool = True
) -> dict:
    """
    Check if price holds above invalidation level during confirmation period.
    
    Used for mean reversion strategies to filter fakeouts:
    - After reversal signal, wait N bars before entry
    - Cancel if price breaks below invalidation level - offset (fakeout detected)
    
    This is a REUSABLE function for any strategy needing confirmation delay.
    
    Args:
        current_low: Current bar low price
        invalidation_level: Price level that would cancel the signal (e.g., extension low)
        bars_waiting: How many bars have passed since confirmation started
        required_bars: Total bars needed to confirm
        offset_pips: Buffer below invalidation level (flexibility for noise)
        pip_value: Value of 1 pip for this asset
        enabled: If False, returns immediate confirmation
    
    Returns:
        dict with:
            'status': str - 'WAITING', 'CONFIRMED', 'CANCELLED'
            'bars_remaining': int - Bars left to confirm
            'invalidated': bool - True if price broke invalidation level
            'effective_level': float - Actual invalidation level used (with offset)
    
    Example:
        # In strategy loop after reversal detected:
        result = check_confirmation_hold(
            current_low=current_bar_low,
            invalidation_level=extension_low,
            bars_waiting=3,
            required_bars=5,
            offset_pips=3.0,
            pip_value=0.0001
        )
        if result['status'] == 'CONFIRMED':
            execute_entry()
        elif result['status'] == 'CANCELLED':
            reset_state()
    """
    if not enabled:
        return {
            'status': 'CONFIRMED',
            'bars_remaining': 0,
            'invalidated': False,
            'effective_level': invalidation_level
        }
    
    # Calculate effective invalidation level (with offset for flexibility)
    offset = offset_pips * pip_value
    effective_level = invalidation_level - offset
    
    # Check for invalidation (price broke below effective level)
    if current_low < effective_level:
        return {
            'status': 'CANCELLED',
            'bars_remaining': required_bars - bars_waiting,
            'invalidated': True,
            'effective_level': effective_level
        }
    
    # Check if enough bars have passed
    if bars_waiting >= required_bars:
        return {
            'status': 'CONFIRMED',
            'bars_remaining': 0,
            'invalidated': False,
            'effective_level': effective_level
        }
    
    # Still waiting
    return {
        'status': 'WAITING',
        'bars_remaining': required_bars - bars_waiting,
        'invalidated': False,
        'effective_level': effective_level
    }


# =============================================================================
# EMA PRICE FILTERS
# =============================================================================

def check_ema_price_filter(close: float, ema_value: float, direction: str = "LONG", enabled: bool = True) -> bool:
    """
    Check if price is on correct side of EMA for trend filter.
    
    Args:
        close: Current close price
        ema_value: EMA indicator value
        direction: "LONG" (close > EMA) or "SHORT" (close < EMA)
        enabled: If False, always returns True
    
    Returns:
        True if price passes EMA filter or filter disabled
    
    Example:
        check_ema_price_filter(162.50, 162.00, "LONG")  # True - close > EMA
    """
    if not enabled:
        return True
    if direction == "LONG":
        return close > ema_value
    elif direction == "SHORT":
        return close < ema_value
    return True


# =============================================================================
# HELPER: Format filter status for logging
# =============================================================================

def format_filter_status(name: str, enabled: bool, passed: bool, details: str = "") -> str:
    """
    Format filter result for trade logs.
    
    Args:
        name: Filter name (e.g., "Time Filter")
        enabled: Whether filter is enabled
        passed: Whether filter passed
        details: Optional details string
    
    Returns:
        Formatted string for logging
    
    Example:
        format_filter_status("ATR Filter", True, True, "0.05 in [0.03-0.09]")
        # Returns: "ATR Filter: ENABLED | 0.05 in [0.03-0.09] | PASS"
    """
    if not enabled:
        return f"{name}: DISABLED"
    
    status = "PASS" if passed else "FAIL"
    if details:
        return f"{name}: ENABLED | {details} | {status}"
    return f"{name}: {status}"


# =============================================================================
# KAMA (Kaufman Adaptive Moving Average) - For SEDNA Strategy
# =============================================================================

def calculate_kama(
    prices: list,
    period: int = 10,
    fast: int = 2,
    slow: int = 30
) -> list:
    """
    Calculate Kaufman Adaptive Moving Average (KAMA).
    
    KAMA adapts to market conditions using Efficiency Ratio:
    - In trending markets (high ER): KAMA responds quickly
    - In choppy markets (low ER): KAMA responds slowly
    
    Pure function for use in any context (backtest, live, analysis).
    
    Args:
        prices: List of prices (most recent last)
        period: Efficiency ratio period
        fast: Fast smoothing constant period
        slow: Slow smoothing constant period
    
    Returns:
        List of KAMA values (same length as prices, NaN for warmup)
    
    Example:
        hl2_prices = [(h + l) / 2 for h, l in zip(highs, lows)]
        kama = calculate_kama(hl2_prices, period=10, fast=2, slow=30)
    """
    if len(prices) < period + 1:
        return [float('nan')] * len(prices)
    
    # Smoothing constants
    fast_sc = 2.0 / (fast + 1.0)
    slow_sc = 2.0 / (slow + 1.0)
    
    kama_values = [float('nan')] * len(prices)
    
    # Initialize with SMA
    kama_values[period] = sum(prices[:period + 1]) / (period + 1)
    
    # Calculate KAMA for remaining values
    for i in range(period + 1, len(prices)):
        # Efficiency Ratio
        change = abs(prices[i] - prices[i - period])
        volatility = sum(abs(prices[i - j] - prices[i - j - 1]) for j in range(period))
        
        if volatility > 0:
            er = change / volatility
        else:
            er = 0.0
        
        # Smoothing constant based on ER
        sc = (er * (fast_sc - slow_sc) + slow_sc) ** 2
        
        # KAMA calculation
        kama_values[i] = kama_values[i - 1] + sc * (prices[i] - kama_values[i - 1])
    
    return kama_values


def get_kama_value(
    prices: list,
    period: int = 10,
    fast: int = 2,
    slow: int = 30
) -> float:
    """
    Get current KAMA value (last value only).
    
    Convenience function for live trading when you only need the latest value.
    
    Args:
        prices: List of prices (most recent last), needs period + 1 values minimum
        period: Efficiency ratio period
        fast: Fast smoothing constant period
        slow: Slow smoothing constant period
    
    Returns:
        Current KAMA value, or NaN if insufficient data
    """
    kama_values = calculate_kama(prices, period, fast, slow)
    return kama_values[-1] if kama_values else float('nan')


# =============================================================================
# ADX / ADXR (Average Directional Index) - For GLIESE Strategy
# =============================================================================

def calculate_adx(
    highs: list,
    lows: list,
    closes: list,
    period: int = 14
) -> list:
    """
    Calculate Average Directional Index (ADX).
    
    ADX measures trend strength regardless of direction:
    - ADX < 20: No trend (ranging market)
    - ADX 20-25: Weak trend / transition
    - ADX 25-50: Strong trend
    - ADX > 50: Very strong trend
    
    Pure function for use in any context (backtest, live, analysis).
    
    Args:
        highs: List of high prices (most recent last)
        lows: List of low prices (most recent last)
        closes: List of close prices (most recent last)
        period: Smoothing period for ADX calculation
    
    Returns:
        List of ADX values (same length as input, NaN for warmup)
    
    Example:
        adx = calculate_adx(highs, lows, closes, period=14)
        if adx[-1] < 25:
            # Market is ranging - good for mean reversion
    """
    n = len(highs)
    min_required = period * 2 + 1
    if n < min_required:
        return [float('nan')] * n
    
    # Initialize output
    adx_values = [float('nan')] * n
    
    # Calculate True Range, +DM, -DM for each bar
    tr_list = [0.0]  # First element placeholder
    plus_dm_list = [0.0]
    minus_dm_list = [0.0]
    
    for i in range(1, n):
        high = highs[i]
        low = lows[i]
        prev_high = highs[i - 1]
        prev_low = lows[i - 1]
        prev_close = closes[i - 1]
        
        # True Range
        tr1 = high - low
        tr2 = abs(high - prev_close)
        tr3 = abs(low - prev_close)
        tr = max(tr1, tr2, tr3)
        tr_list.append(tr)
        
        # Directional Movement
        up_move = high - prev_high
        down_move = prev_low - low
        
        plus_dm = up_move if up_move > down_move and up_move > 0 else 0.0
        minus_dm = down_move if down_move > up_move and down_move > 0 else 0.0
        
        plus_dm_list.append(plus_dm)
        minus_dm_list.append(minus_dm)
    
    # Smoothed values using Wilder's method
    smoothed_tr = [0.0] * n
    smoothed_plus_dm = [0.0] * n
    smoothed_minus_dm = [0.0] * n
    
    # First smoothed value is sum of first period values
    smoothed_tr[period] = sum(tr_list[1:period + 1])
    smoothed_plus_dm[period] = sum(plus_dm_list[1:period + 1])
    smoothed_minus_dm[period] = sum(minus_dm_list[1:period + 1])
    
    # Subsequent smoothed values using Wilder's smoothing
    for i in range(period + 1, n):
        smoothed_tr[i] = smoothed_tr[i-1] - (smoothed_tr[i-1] / period) + tr_list[i]
        smoothed_plus_dm[i] = smoothed_plus_dm[i-1] - (smoothed_plus_dm[i-1] / period) + plus_dm_list[i]
        smoothed_minus_dm[i] = smoothed_minus_dm[i-1] - (smoothed_minus_dm[i-1] / period) + minus_dm_list[i]
    
    # Calculate DX values
    dx_list = [float('nan')] * n
    
    for i in range(period, n):
        if smoothed_tr[i] > 0:
            plus_di = 100.0 * smoothed_plus_dm[i] / smoothed_tr[i]
            minus_di = 100.0 * smoothed_minus_dm[i] / smoothed_tr[i]
            di_sum = plus_di + minus_di
            if di_sum > 0:
                dx_list[i] = 100.0 * abs(plus_di - minus_di) / di_sum
    
    # Calculate ADX using Wilder's smoothing of DX
    # First ADX value is average of first 'period' DX values
    adx_start = period * 2 - 1
    
    if adx_start < n:
        first_dx_values = [dx_list[i] for i in range(period, adx_start + 1) if not math.isnan(dx_list[i])]
        if first_dx_values:
            adx_values[adx_start] = sum(first_dx_values) / len(first_dx_values)
            
            # Subsequent ADX values use Wilder's smoothing
            for i in range(adx_start + 1, n):
                prev_adx = adx_values[i - 1]
                curr_dx = dx_list[i]
                
                if not math.isnan(prev_adx):
                    if not math.isnan(curr_dx):
                        adx_values[i] = (prev_adx * (period - 1) + curr_dx) / period
                    else:
                        adx_values[i] = prev_adx
    
    return adx_values


def calculate_adxr(
    highs: list,
    lows: list,
    closes: list,
    period: int = 14,
    lookback: int = 14
) -> float:
    """
    Calculate Average Directional Index Rating (ADXR).
    
    ADXR = (ADX[0] + ADX[lookback]) / 2
    
    Smoother version of ADX, reduces whipsaws and provides more stable
    trend strength measurement.
    
    Args:
        highs: List of high prices (most recent last)
        lows: List of low prices (most recent last)
        closes: List of close prices (most recent last)
        period: ADX smoothing period
        lookback: Periods back to average with current ADX
    
    Returns:
        Current ADXR value, or NaN if insufficient data
    
    Example:
        adxr = calculate_adxr(highs, lows, closes, period=14, lookback=14)
        if adxr < 25:
            # Market is ranging - suitable for mean reversion
    """
    adx_values = calculate_adx(highs, lows, closes, period)
    
    if len(adx_values) < lookback + 1:
        return float('nan')
    
    current_adx = adx_values[-1]
    past_adx = adx_values[-lookback - 1]
    
    if math.isnan(current_adx) or math.isnan(past_adx):
        return float('nan')
    
    return (current_adx + past_adx) / 2.0


def check_adxr_filter(
    adxr_value: float,
    max_threshold: float,
    enabled: bool = True
) -> bool:
    """
    Check if market is ranging using ADXR (for mean reversion).
    
    ADXR < threshold indicates ranging/non-trending market,
    suitable for mean reversion strategies.
    
    Note: This is INVERTED from typical ADX usage.
    - SEDNA: ADX HIGH = good (trending)
    - GLIESE: ADXR LOW = good (ranging)
    
    Args:
        adxr_value: Current ADXR value
        max_threshold: Maximum ADXR to allow entry (e.g., 25)
        enabled: If False, always returns True
    
    Returns:
        True if ADXR < threshold or filter disabled
    
    Example:
        check_adxr_filter(18.5, 25.0)  # True - ranging market
        check_adxr_filter(32.0, 25.0)  # False - trending market
    """
    if not enabled:
        return True
    if math.isnan(adxr_value):
        return False
    return adxr_value < max_threshold


# =============================================================================
# KAMA SLOPE (For range detection) - For GLIESE Strategy
# =============================================================================

def calculate_kama_slope(
    kama_values: list,
    lookback: int = 5
) -> float:
    """
    Calculate KAMA slope over lookback period.
    
    Measures how much KAMA has moved, useful for detecting flat/ranging periods.
    
    Args:
        kama_values: List of KAMA values (most recent last)
        lookback: Number of bars to measure slope
    
    Returns:
        Absolute slope value (always positive), or NaN if insufficient data
    
    Example:
        slope = calculate_kama_slope(kama_values, lookback=5)
    """
    if len(kama_values) < lookback + 1:
        return float('nan')
    
    current_kama = kama_values[-1]
    past_kama = kama_values[-lookback - 1]
    
    if math.isnan(current_kama) or math.isnan(past_kama):
        return float('nan')
    
    return abs(current_kama - past_kama)


def check_kama_slope_filter(
    kama_slope: float,
    atr_value: float,
    max_atr_mult: float,
    enabled: bool = True
) -> bool:
    """
    Check if KAMA slope is flat (for range detection).
    
    Slope is considered flat if: slope < max_atr_mult * ATR
    This normalizes the threshold across different assets.
    
    Args:
        kama_slope: Absolute KAMA slope value
        atr_value: Current ATR for normalization
        max_atr_mult: Maximum slope as multiple of ATR (e.g., 0.3)
        enabled: If False, always returns True
    
    Returns:
        True if slope is flat (ranging) or filter disabled
    
    Example:
        check_kama_slope_filter(0.0002, 0.0010, 0.3)  # True: 0.0002 < 0.3*0.001
        check_kama_slope_filter(0.0005, 0.0010, 0.3)  # False: 0.0005 > 0.0003
    """
    if not enabled:
        return True
    if math.isnan(kama_slope) or math.isnan(atr_value) or atr_value <= 0:
        return False
    
    threshold = max_atr_mult * atr_value
    return kama_slope < threshold


# =============================================================================
# EFFICIENCY RATIO RANGE FILTER (Inverted for GLIESE)
# =============================================================================

def check_efficiency_ratio_range_filter(
    er_value: float,
    max_threshold: float,
    enabled: bool = True
) -> bool:
    """
    Check if market is ranging using Efficiency Ratio (for mean reversion).
    
    ER < threshold indicates choppy/ranging market,
    suitable for mean reversion strategies.
    
    Note: This is INVERTED from SEDNA's ER filter.
    - SEDNA: ER >= threshold (trending)
    - GLIESE: ER < threshold (ranging)
    
    Args:
        er_value: Current Efficiency Ratio value (0.0 to 1.0)
        max_threshold: Maximum ER to allow entry (e.g., 0.30)
        enabled: If False, always returns True
    
    Returns:
        True if ER < threshold or filter disabled
    
    Example:
        check_efficiency_ratio_range_filter(0.20, 0.30)  # True - ranging
        check_efficiency_ratio_range_filter(0.45, 0.30)  # False - trending
    """
    if not enabled:
        return True
    return er_value < max_threshold


# =============================================================================
# BAND CALCULATIONS (For GLIESE Mean Reversion)
# =============================================================================

def calculate_bands(
    center_value: float,
    atr_value: float,
    band_mult: float = 1.5
) -> tuple:
    """
    Calculate upper and lower bands around center value.
    
    Bands = Center +/- (band_mult * ATR)
    
    Args:
        center_value: Center line value (e.g., KAMA)
        atr_value: Current ATR for band width
        band_mult: Multiplier for band distance (e.g., 1.5)
    
    Returns:
        Tuple of (upper_band, lower_band)
    
    Example:
        upper, lower = calculate_bands(1.0850, 0.0010, 1.5)
        # upper = 1.0865, lower = 1.0835
    """
    band_distance = band_mult * atr_value
    upper_band = center_value + band_distance
    lower_band = center_value - band_distance
    return upper_band, lower_band


def check_extension_below_band(
    current_close: float,
    lower_band: float
) -> bool:
    """
    Check if price has extended below lower band.
    
    Args:
        current_close: Current close price
        lower_band: Lower band value
    
    Returns:
        True if close < lower_band (extended below)
    
    Example:
        if check_extension_below_band(1.0830, 1.0835):
            # Price is below lower band - potential mean reversion setup
    """
    return current_close < lower_band


def check_reversal_above_band(
    current_close: float,
    lower_band: float
) -> bool:
    """
    Check if price has reversed back above lower band.
    
    Used after extension detection to confirm reversal.
    
    Args:
        current_close: Current close price
        lower_band: Lower band value
    
    Returns:
        True if close >= lower_band (reversed above)
    
    Example:
        if check_reversal_above_band(1.0840, 1.0835):
            # Price reversed back above band - reversal confirmed
    """
    return current_close >= lower_band
