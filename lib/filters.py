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
