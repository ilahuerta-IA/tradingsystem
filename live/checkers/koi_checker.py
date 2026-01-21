"""
KOI Strategy Checker for Live Trading.

Implements the 2-phase state machine:
1. SCANNING - Looking for Bullish Engulfing + 5 EMAs ascending + CCI filter
2. WAITING_BREAKOUT - Monitoring for breakout above pattern high

Uses lib/filters.py for time filtering consistent with backtesting.
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum

import pandas as pd

from .base_checker import BaseChecker, Signal, SignalDirection
from lib.filters import check_time_filter, check_sl_pips_filter
from live.timezone import broker_to_utc


class KOIState(Enum):
    """KOI state machine states."""
    SCANNING = "SCANNING"
    WAITING_BREAKOUT = "WAITING_BREAKOUT"


class KOIChecker(BaseChecker):
    """
    KOI strategy signal checker.
    
    2-Phase State Machine:
    - SCANNING: Monitor for Bullish Engulfing + 5 EMAs ascending + CCI
    - WAITING_BREAKOUT: Monitor breakout level
    """
    
    @property
    def strategy_name(self) -> str:
        return "KOI"
    
    def __init__(
        self,
        config_name: str,
        params: Dict[str, Any],
        logger: Optional[logging.Logger] = None
    ):
        super().__init__(config_name, params, logger)
        
        # State machine
        self.state = KOIState.SCANNING
        self.pattern_bar: Optional[int] = None
        self.breakout_level: Optional[float] = None
        self.pattern_atr: Optional[float] = None
        self.pattern_cci: Optional[float] = None
        
        # EMA periods for KOI
        self.ema_periods = [
            params.get("ema_period_1", 10),
            params.get("ema_period_2", 20),
            params.get("ema_period_3", 40),
            params.get("ema_period_4", 80),
            params.get("ema_period_5", 120),
        ]
        
        self.logger.info(f"[{self.strategy_name}] Checker initialized for {config_name}")
    
    def reset_state(self) -> None:
        """Reset state machine to SCANNING."""
        self.state = KOIState.SCANNING
        self.pattern_bar = None
        self.breakout_level = None
        self.pattern_atr = None
        self.pattern_cci = None
    
    def get_state_info(self) -> Dict[str, Any]:
        """Get current state machine info for logging."""
        return {
            "strategy": self.strategy_name,
            "state": self.state.value,
            "pattern_bar": self.pattern_bar,
            "breakout_level": self.breakout_level,
            "current_bar": self.current_bar_index,
        }
    
    def _calculate_emas(self, df: pd.DataFrame) -> Dict[str, pd.Series]:
        """Calculate all 5 EMAs."""
        close = df["close"]
        result = {}
        for i, period in enumerate(self.ema_periods, 1):
            result[f"ema_{i}"] = close.ewm(span=period, adjust=False).mean()
        return result
    
    def _calculate_atr(self, df: pd.DataFrame) -> pd.Series:
        """Calculate ATR from DataFrame."""
        high = df["high"]
        low = df["low"]
        close = df["close"]
        
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr_period = self.params.get("atr_length", 14)
        return tr.rolling(window=atr_period).mean()
    
    def _calculate_cci(self, df: pd.DataFrame) -> pd.Series:
        """Calculate CCI (Commodity Channel Index)."""
        high = df["high"]
        low = df["low"]
        close = df["close"]
        
        typical_price = (high + low + close) / 3
        cci_period = self.params.get("cci_period", 20)
        
        sma_tp = typical_price.rolling(window=cci_period).mean()
        mean_dev = typical_price.rolling(window=cci_period).apply(
            lambda x: abs(x - x.mean()).mean(), raw=True
        )
        
        cci = (typical_price - sma_tp) / (0.015 * mean_dev)
        return cci
    
    def _check_bullish_engulfing(self, df: pd.DataFrame) -> bool:
        """
        Check for bullish engulfing pattern.
        
        Requirements:
        - Previous candle: bearish (close < open)
        - Current candle: bullish (close > open)
        - Current body engulfs previous body
        """
        if len(df) < 2:
            return False
        
        prev_open = float(df["open"].iloc[-2])
        prev_close = float(df["close"].iloc[-2])
        curr_open = float(df["open"].iloc[-1])
        curr_close = float(df["close"].iloc[-1])
        
        # Previous must be bearish
        if prev_close >= prev_open:
            return False
        
        # Current must be bullish
        if curr_close <= curr_open:
            return False
        
        # Current body must engulf previous body
        # Body bottom (curr_open) <= prev_close (body top of bearish)
        # Body top (curr_close) >= prev_open (body bottom of bearish)
        if curr_open > prev_close:
            return False
        if curr_close < prev_open:
            return False
        
        return True
    
    def _check_emas_ascending(self, emas: Dict[str, pd.Series]) -> tuple:
        """
        Check if all 5 EMAs are individually ascending.
        
        Each EMA's current value must be > its previous value.
        Returns: (is_valid, failed_ema_index or None)
        """
        for i in range(1, 6):
            ema_key = f"ema_{i}"
            ema = emas.get(ema_key)
            if ema is None or len(ema) < 2:
                return False, i
            
            current = float(ema.iloc[-1])
            previous = float(ema.iloc[-2])
            
            if current <= previous:
                return False, i
        
        return True, None
    
    def _check_cci_condition(self, cci: float) -> bool:
        """Check CCI momentum filter."""
        cci_threshold = self.params.get("cci_threshold", 110)
        cci_max = self.params.get("cci_max_threshold", 999)
        
        if cci <= cci_threshold:
            return False
        if cci >= cci_max:
            return False
        
        return True
    
    def check_signal(self, df: pd.DataFrame) -> Signal:
        """
        Check for trading signal using 2-phase state machine.
        """
        self.current_bar_index += 1
        now = datetime.now()
        
        # Validate data
        min_bars = max(self.ema_periods) + 10
        if df is None or len(df) < min_bars:
            return self._create_no_signal("Insufficient data")
        
        # Calculate indicators
        emas = self._calculate_emas(df)
        atr_series = self._calculate_atr(df)
        cci_series = self._calculate_cci(df)
        
        current_atr = float(atr_series.iloc[-1])
        current_cci = float(cci_series.iloc[-1])
        current_close = float(df["close"].iloc[-1])
        current_high = float(df["high"].iloc[-1])
        current_low = float(df["low"].iloc[-1])
        
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
        if self.state == KOIState.SCANNING:
            
            # Time filter (optional)
            if self.params.get("use_time_filter", False):
                allowed_hours = self.params.get("allowed_hours", [])
                current_dt_utc = broker_to_utc(current_dt)
                if not check_time_filter(current_dt_utc, allowed_hours, True):
                    reason = f"Time filter: UTC {current_dt_utc.hour}h not in {allowed_hours}"
                    self._log_signal_check(reason)
                    return self._create_no_signal(reason)
            
            # Check Bullish Engulfing
            if not self._check_bullish_engulfing(df):
                self._log_signal_check("No bullish engulfing")
                return self._create_no_signal("No bullish engulfing")
            
            # Check 5 EMAs ascending
            emas_valid, failed_ema = self._check_emas_ascending(emas)
            if not emas_valid:
                ema_period = self.ema_periods[failed_ema - 1] if failed_ema else '?'
                reason = f"EMAs not all ascending (EMA{failed_ema}={ema_period} failed)"
                self._log_signal_check(reason)
                return self._create_no_signal(reason)
            
            # Check CCI
            if not self._check_cci_condition(current_cci):
                reason = f"CCI filter: {current_cci:.1f} not in ({self.params.get('cci_threshold', 110)}, {self.params.get('cci_max_threshold', 999)})"
                self._log_signal_check(reason)
                return self._create_no_signal(reason)
            
            # All conditions met - check if breakout window is enabled
            use_breakout_window = self.params.get("use_breakout_window", True)
            
            if use_breakout_window:
                # Setup breakout window
                pip_value = self.params.get("pip_value", 0.0001)
                offset_pips = self.params.get("breakout_level_offset_pips", 3)
                
                self.pattern_bar = self.current_bar_index
                self.breakout_level = current_high + (offset_pips * pip_value)
                self.pattern_atr = current_atr
                self.pattern_cci = current_cci
                
                self.state = KOIState.WAITING_BREAKOUT
                
                self._log_state_transition(
                    "SCANNING", "WAITING_BREAKOUT",
                    f"Pattern high: {current_high:.5f}, Breakout: {self.breakout_level:.5f}, CCI: {current_cci:.1f}, ATR: {current_atr:.5f}"
                )
                
                return self._create_no_signal("Waiting for breakout confirmation")
            
            else:
                # Immediate entry (no breakout confirmation)
                entry_price = current_close
                stop_loss = entry_price - (current_atr * self.params.get("atr_sl_multiplier", 2.0))
                take_profit = entry_price + (current_atr * self.params.get("atr_tp_multiplier", 6.0))
                
                # SL Pips Filter (matching backtest behavior)
                pip_value = self.params.get("pip_value", 0.0001)
                sl_pips = abs(entry_price - stop_loss) / pip_value
                
                use_sl_pips_filter = self.params.get("use_sl_pips_filter", False)
                sl_pips_min = self.params.get("sl_pips_min", 0)
                sl_pips_max = self.params.get("sl_pips_max", 999)
                
                if not check_sl_pips_filter(sl_pips, sl_pips_min, sl_pips_max, use_sl_pips_filter):
                    reason = f"SL pips filter: {sl_pips:.1f} not in [{sl_pips_min}-{sl_pips_max}]"
                    self.logger.info(f"[{self.strategy_name}] {reason} - Signal rejected")
                    return self._create_no_signal(reason)
                
                self.logger.info(
                    f"[{self.strategy_name}] SIGNAL LONG (immediate) | "
                    f"Entry: {entry_price:.5f}, SL: {stop_loss:.5f}, TP: {take_profit:.5f}, "
                    f"CCI: {current_cci:.1f}, SL pips: {sl_pips:.1f}"
                )
                
                return self._create_signal(
                    direction=SignalDirection.LONG,
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    atr=current_atr,
                    reason=f"Bullish engulfing + EMAs ascending + CCI {current_cci:.1f}"
                )
        
        # --- WAITING_BREAKOUT STATE ---
        elif self.state == KOIState.WAITING_BREAKOUT:
            
            # Check timeout
            bars_since = self.current_bar_index - self.pattern_bar
            breakout_window = self.params.get("breakout_window_candles", 3)
            
            if bars_since > breakout_window:
                self._log_state_transition(
                    "WAITING_BREAKOUT", "SCANNING",
                    f"Timeout after {bars_since} bars"
                )
                self.reset_state()
                return self._create_no_signal("Breakout window expired")
            
            # Check for breakout
            if current_high > self.breakout_level:
                # Breakout confirmed - generate signal
                entry_price = self.breakout_level
                atr_for_sl = self.pattern_atr if self.pattern_atr else current_atr
                
                stop_loss = entry_price - (atr_for_sl * self.params.get("atr_sl_multiplier", 2.0))
                take_profit = entry_price + (atr_for_sl * self.params.get("atr_tp_multiplier", 6.0))
                
                # SL Pips Filter (matching backtest behavior)
                pip_value = self.params.get("pip_value", 0.0001)
                sl_pips = abs(entry_price - stop_loss) / pip_value
                
                use_sl_pips_filter = self.params.get("use_sl_pips_filter", False)
                sl_pips_min = self.params.get("sl_pips_min", 0)
                sl_pips_max = self.params.get("sl_pips_max", 999)
                
                if not check_sl_pips_filter(sl_pips, sl_pips_min, sl_pips_max, use_sl_pips_filter):
                    reason = f"SL pips filter: {sl_pips:.1f} not in [{sl_pips_min}-{sl_pips_max}]"
                    self.logger.info(f"[{self.strategy_name}] {reason} - Signal rejected")
                    self.reset_state()
                    return self._create_no_signal(reason)
                
                self.logger.info(
                    f"[{self.strategy_name}] SIGNAL LONG (breakout) | "
                    f"Entry: {entry_price:.5f}, SL: {stop_loss:.5f}, TP: {take_profit:.5f}, "
                    f"Bars waited: {bars_since}, SL pips: {sl_pips:.1f}"
                )
                
                signal = self._create_signal(
                    direction=SignalDirection.LONG,
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    atr=atr_for_sl,
                    reason=f"Breakout confirmed after {bars_since} bars"
                )
                
                self.reset_state()
                return signal
            
            return self._create_no_signal(
                f"Waiting for breakout above {self.breakout_level:.5f} ({bars_since}/{breakout_window} bars)"
            )
        
        return self._create_no_signal("Unknown state")
