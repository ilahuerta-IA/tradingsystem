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
