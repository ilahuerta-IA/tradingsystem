"""
Sunset Ogle Strategy Checker for Live Trading.

Implements the 4-phase state machine:
1. SCANNING - Looking for EMA crossover
2. ARMED_LONG - Waiting for pullback (bearish candles)
3. WINDOW_OPEN - Monitoring for breakout
4. Signal generated on successful breakout

Uses lib/filters.py for consistent behavior with backtesting.
"""

import math
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum

import pandas as pd

from .base_checker import BaseChecker, Signal, SignalDirection
from lib.filters import (
    check_time_filter,
    check_atr_filter,
    check_angle_filter,
    check_ema_price_filter,
)
from live.timezone import broker_to_utc


class SunsetOgleState(Enum):
    """State machine states."""
    SCANNING = "SCANNING"
    ARMED_LONG = "ARMED_LONG"
    WINDOW_OPEN = "WINDOW_OPEN"


class SunsetOgleChecker(BaseChecker):
    """
    Sunset Ogle strategy signal checker.
    
    4-Phase State Machine:
    - SCANNING: Monitor for EMA crossover + filters
    - ARMED_LONG: Wait for pullback candles
    - WINDOW_OPEN: Monitor breakout level
    """
    
    @property
    def strategy_name(self) -> str:
        return "SunsetOgle"
    
    def __init__(
        self,
        config_name: str,
        params: Dict[str, Any],
        logger: Optional[logging.Logger] = None
    ):
        super().__init__(config_name, params, logger)
        
        # State machine
        self.state = SunsetOgleState.SCANNING
        self.pullback_count = 0
        self.pullback_high: Optional[float] = None
        self.pullback_low: Optional[float] = None
        self.window_top: Optional[float] = None
        self.window_bottom: Optional[float] = None
        self.window_expiry_bar: Optional[int] = None
        self.signal_atr: Optional[float] = None
        
        self.logger.info(f"[{self.strategy_name}] Checker initialized for {config_name}")
    
    def reset_state(self) -> None:
        """Reset state machine to SCANNING."""
        self.state = SunsetOgleState.SCANNING
        self.pullback_count = 0
        self.pullback_high = None
        self.pullback_low = None
        self.window_top = None
        self.window_bottom = None
        self.window_expiry_bar = None
        self.signal_atr = None
    
    def get_state_info(self) -> Dict[str, Any]:
        """Get current state machine info for logging."""
        return {
            "strategy": self.strategy_name,
            "state": self.state.value,
            "pullback_count": self.pullback_count,
            "window_top": self.window_top,
            "window_bottom": self.window_bottom,
            "current_bar": self.current_bar_index,
            "window_expiry": self.window_expiry_bar,
        }
    
    def _calculate_emas(self, df: pd.DataFrame) -> Dict[str, pd.Series]:
        """Calculate EMAs from DataFrame."""
        close = df["close"]
        return {
            "fast": close.ewm(span=self.params["ema_fast_length"], adjust=False).mean(),
            "medium": close.ewm(span=self.params["ema_medium_length"], adjust=False).mean(),
            "slow": close.ewm(span=self.params["ema_slow_length"], adjust=False).mean(),
            "confirm": close.ewm(span=self.params["ema_confirm_length"], adjust=False).mean(),
            "filter": close.ewm(span=self.params["ema_filter_price_length"], adjust=False).mean(),
        }
    
    def _calculate_atr(self, df: pd.DataFrame) -> pd.Series:
        """Calculate ATR from DataFrame."""
        high = df["high"]
        low = df["low"]
        close = df["close"]
        
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(window=self.params["atr_length"]).mean()
    
    def _calculate_angle(self, ema_confirm: pd.Series) -> float:
        """Calculate EMA angle in degrees."""
        try:
            current = float(ema_confirm.iloc[-1])
            previous = float(ema_confirm.iloc[-2])
            scale = self.params.get("angle_scale", 100.0)
            rise = (current - previous) * scale
            return math.degrees(math.atan(rise))
        except (IndexError, ValueError):
            return 0.0
    
    def _check_crossover(self, emas: Dict[str, pd.Series]) -> bool:
        """Check for bullish EMA crossover."""
        confirm = emas["confirm"]
        
        if len(confirm) < 2:
            return False
        
        for ema_name in ["fast", "medium", "slow"]:
            other = emas[ema_name]
            curr_above = float(confirm.iloc[-1]) > float(other.iloc[-1])
            prev_below = float(confirm.iloc[-2]) <= float(other.iloc[-2])
            if curr_above and prev_below:
                return True
        
        return False
    
    def _check_bearish_candle(self, df: pd.DataFrame) -> bool:
        """Check if last candle is bearish."""
        return float(df["close"].iloc[-1]) < float(df["open"].iloc[-1])
    
    def check_signal(self, df: pd.DataFrame) -> Signal:
        """
        Check for trading signal using 4-phase state machine.
        """
        self.current_bar_index += 1
        now = datetime.now()
        
        # Validate data
        min_bars = self.params.get("ema_filter_price_length", 70)
        if df is None or len(df) < min_bars:
            return self._create_no_signal("Insufficient data")
        
        # Calculate indicators
        emas = self._calculate_emas(df)
        atr_series = self._calculate_atr(df)
        
        current_atr = float(atr_series.iloc[-1])
        current_close = float(df["close"].iloc[-1])
        current_high = float(df["high"].iloc[-1])
        current_low = float(df["low"].iloc[-1])
        current_angle = self._calculate_angle(emas["confirm"])
        ema_filter_value = float(emas["filter"].iloc[-1])
        
        # Get current time from data
        if "time" in df.columns:
            current_dt = df["time"].iloc[-1]
            if isinstance(current_dt, pd.Timestamp):
                current_dt = current_dt.to_pydatetime()
        else:
            current_dt = now
        
        # ========================================
        # STATE MACHINE
        # ========================================
        
        # --- SCANNING STATE ---
        if self.state == SunsetOgleState.SCANNING:
            
            if not self._check_crossover(emas):
                self._log_signal_check("No crossover")
                return self._create_no_signal("No crossover")
            
            if not check_ema_price_filter(current_close, ema_filter_value):
                reason = f"Price filter: {current_close:.5f} <= EMA({ema_filter_value:.5f})"
                self._log_signal_check(reason)
                return self._create_no_signal(reason)
            
            if not check_atr_filter(current_atr, self.params["atr_min"], self.params["atr_max"]):
                reason = f"ATR filter: {current_atr:.6f} not in [{self.params['atr_min']}-{self.params['atr_max']}]"
                self._log_signal_check(reason)
                return self._create_no_signal(reason)
            
            if self.params.get("use_angle_filter", False):
                if not check_angle_filter(current_angle, self.params["angle_min"], self.params["angle_max"]):
                    reason = f"Angle filter: {current_angle:.1f} not in [{self.params['angle_min']}-{self.params['angle_max']}]"
                    self._log_signal_check(reason)
                    return self._create_no_signal(reason)
            
            # All filters passed - transition to ARMED
            self.state = SunsetOgleState.ARMED_LONG
            self.pullback_count = 0
            self.signal_atr = current_atr
            
            self._log_state_transition(
                "SCANNING", "ARMED_LONG",
                f"ATR: {current_atr:.6f}, Angle: {current_angle:.1f}"
            )
            
            return self._create_no_signal("Armed - waiting for pullback")
        
        # --- ARMED_LONG STATE ---
        elif self.state == SunsetOgleState.ARMED_LONG:
            
            if self._check_bearish_candle(df):
                self.pullback_count += 1
                
                if self.pullback_count >= self.params["pullback_candles"]:
                    self.pullback_high = current_high
                    self.pullback_low = current_low
                    
                    candle_range = self.pullback_high - self.pullback_low
                    offset = candle_range * self.params.get("price_offset_mult", 0.01)
                    
                    self.window_top = self.pullback_high + offset
                    self.window_bottom = self.pullback_low - offset
                    self.window_expiry_bar = self.current_bar_index + self.params["window_periods"]
                    
                    self.state = SunsetOgleState.WINDOW_OPEN
                    
                    self._log_state_transition(
                        "ARMED_LONG", "WINDOW_OPEN",
                        f"Pullbacks: {self.pullback_count}, Breakout: {self.window_top:.5f}"
                    )
                
                return self._create_no_signal(f"Pullback {self.pullback_count}/{self.params['pullback_candles']}")
            else:
                self.reset_state()
                return self._create_no_signal("Pullback invalidated (bullish candle)")
        
        # --- WINDOW_OPEN STATE ---
        elif self.state == SunsetOgleState.WINDOW_OPEN:
            
            if self.current_bar_index > self.window_expiry_bar:
                self._log_state_transition("WINDOW_OPEN", "ARMED_LONG", "Window expired")
                self.state = SunsetOgleState.ARMED_LONG
                self.pullback_count = 0
                return self._create_no_signal("Window expired")
            
            if current_low <= self.window_bottom:
                self._log_state_transition("WINDOW_OPEN", "ARMED_LONG", "Window broken downside")
                self.state = SunsetOgleState.ARMED_LONG
                self.pullback_count = 0
                return self._create_no_signal("Window broken downside")
            
            # Check for upside breakout
            if current_high >= self.window_top:
                
                # Time filter
                if self.params.get("use_time_filter", False):
                    allowed_hours = self.params.get("allowed_hours", [])
                    current_dt_utc = broker_to_utc(current_dt)
                    if not check_time_filter(current_dt_utc, allowed_hours, True):
                        reason = f"Time filter: UTC {current_dt_utc.hour}h not in {allowed_hours}"
                        self.logger.info(f"[{self.strategy_name}] {reason}")
                        return self._create_no_signal(reason)
                
                # Calculate SL/TP
                entry_price = self.window_top
                stop_loss = current_low - (current_atr * self.params["sl_mult"])
                take_profit = current_high + (current_atr * self.params["tp_mult"])
                
                # Calculate SL pips for logging
                pip_value = self.params.get("pip_value", 0.0001)
                sl_pips = abs(entry_price - stop_loss) / pip_value
                
                self.logger.info(
                    f"[{self.strategy_name}] SIGNAL LONG | "
                    f"Entry: {entry_price:.5f}, SL: {stop_loss:.5f}, TP: {take_profit:.5f}, "
                    f"ATR: {current_atr:.5f}, SL_pips: {sl_pips:.1f}"
                )
                
                signal = self._create_signal(
                    direction=SignalDirection.LONG,
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    atr=current_atr,
                    reason="Breakout confirmed"
                )
                
                self.reset_state()
                return signal
            
            return self._create_no_signal(f"Waiting for breakout above {self.window_top:.5f}")
        
        return self._create_no_signal("Unknown state")
