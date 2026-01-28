"""
SEDNA Strategy Checker for Live Trading.

Implements the 3-phase state machine:
1. SCANNING - Looking for HTF trend (ER >= threshold + Close > KAMA)
2. PULLBACK_DETECTED - Monitoring pullback (N bars without new HH, respects KAMA)
3. WAITING_BREAKOUT - Monitoring for breakout above pullback HH

Key differences from KOI:
- KAMA on HL2 instead of 5 EMAs ascending
- Efficiency Ratio (HTF filter) as main trigger instead of Bullish Engulfing
- Pullback detection for trend continuation
- ATR filter uses average ATR over N periods
- Day filter (weekday filtering)

Uses lib/filters.py for all filtering logic consistent with backtesting.
"""

import logging
import math
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum

import pandas as pd
import numpy as np

from .base_checker import BaseChecker, Signal, SignalDirection
from lib.filters import (
    check_time_filter,
    check_day_filter,
    check_sl_pips_filter,
    check_atr_filter,
    check_efficiency_ratio_filter,
    calculate_efficiency_ratio,
    calculate_kama,
    detect_pullback,
    check_pullback_breakout,
)
from live.timezone import broker_to_utc


class SEDNAState(Enum):
    """SEDNA state machine states."""
    SCANNING = "SCANNING"
    PULLBACK_DETECTED = "PULLBACK_DETECTED"
    WAITING_BREAKOUT = "WAITING_BREAKOUT"


class SEDNAChecker(BaseChecker):
    """
    SEDNA strategy signal checker.
    
    3-Phase State Machine:
    - SCANNING: Monitor for HTF trend (ER >= threshold AND Close > KAMA)
    - PULLBACK_DETECTED: Monitor for pullback (N bars without HH, respects KAMA)
    - WAITING_BREAKOUT: Monitor breakout level above pullback HH
    """
    
    @property
    def strategy_name(self) -> str:
        return "SEDNA"
    
    def __init__(
        self,
        config_name: str,
        params: Dict[str, Any],
        logger: Optional[logging.Logger] = None
    ):
        super().__init__(config_name, params, logger)
        
        # State machine
        self.state = SEDNAState.SCANNING
        self.pattern_bar: Optional[int] = None
        self.breakout_level: Optional[float] = None
        self.pattern_atr: Optional[float] = None
        self.pullback_data: Optional[Dict] = None
        
        # KAMA parameters
        self.kama_period = params.get("kama_period", 10)
        self.kama_fast = params.get("kama_fast", 2)
        self.kama_slow = params.get("kama_slow", 30)
        self.hl2_ema_period = params.get("hl2_ema_period", 1)
        
        # HTF Efficiency Ratio parameters
        self.htf_er_period = params.get("htf_er_period", 10)
        self.htf_timeframe_minutes = params.get("htf_timeframe_minutes", 15)
        # Scale ER period for 5m data to simulate HTF
        base_tf_minutes = 5
        self.scaled_er_period = self.htf_er_period * (self.htf_timeframe_minutes // base_tf_minutes)
        
        # ATR averaging
        self.atr_avg_period = params.get("atr_avg_period", 20)
        
        # Price history for pullback detection
        self.price_history: Dict[str, List[float]] = {
            'highs': [],
            'lows': [],
            'closes': [],
            'kama': []
        }
        
        self.logger.info(
            f"[{self.config_name}] SEDNA Checker initialized | "
            f"KAMA({self.kama_period},{self.kama_fast},{self.kama_slow}) | "
            f"HTF ER period={self.scaled_er_period} ({self.htf_timeframe_minutes}m equiv)"
        )
    
    def reset_state(self) -> None:
        """Reset state machine to SCANNING."""
        self.state = SEDNAState.SCANNING
        self.pattern_bar = None
        self.breakout_level = None
        self.pattern_atr = None
        self.pullback_data = None
    
    def get_state_info(self) -> Dict[str, Any]:
        """Get current state machine info for logging."""
        return {
            "strategy": self.strategy_name,
            "state": self.state.value,
            "pattern_bar": self.pattern_bar,
            "breakout_level": self.breakout_level,
            "current_bar": self.current_bar_index,
            "pullback_data": self.pullback_data,
        }
    
    # =========================================================================
    # INDICATOR CALCULATIONS
    # =========================================================================
    
    def _calculate_hl2(self, df: pd.DataFrame) -> pd.Series:
        """Calculate HL2 = (High + Low) / 2."""
        return (df["high"] + df["low"]) / 2.0
    
    def _calculate_hl2_ema(self, hl2: pd.Series) -> pd.Series:
        """Calculate EMA of HL2 for KAMA comparison."""
        if self.hl2_ema_period <= 1:
            return hl2  # Raw HL2 if period is 1
        return hl2.ewm(span=self.hl2_ema_period, adjust=False).mean()
    
    def _calculate_kama(self, hl2: pd.Series) -> pd.Series:
        """Calculate KAMA from HL2 series."""
        hl2_list = hl2.tolist()
        kama_values = calculate_kama(
            hl2_list,
            period=self.kama_period,
            fast=self.kama_fast,
            slow=self.kama_slow
        )
        return pd.Series(kama_values, index=hl2.index)
    
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
    
    def _calculate_average_atr(self, atr_series: pd.Series) -> float:
        """Calculate average ATR over specified period."""
        if len(atr_series) < self.atr_avg_period:
            return float(atr_series.iloc[-1]) if len(atr_series) > 0 else 0.0
        
        recent_atr = atr_series.iloc[-self.atr_avg_period:]
        return float(recent_atr.mean())
    
    def _calculate_efficiency_ratio(self, df: pd.DataFrame) -> float:
        """Calculate Efficiency Ratio for HTF filter."""
        if len(df) < self.scaled_er_period + 1:
            return 0.0
        
        close_prices = df["close"].tolist()
        return calculate_efficiency_ratio(close_prices, period=self.scaled_er_period)
    
    # =========================================================================
    # CONDITION CHECKS
    # =========================================================================
    
    def _check_htf_filter(self, df: pd.DataFrame, kama_value: float) -> tuple:
        """
        Check Higher Timeframe trend filter (MAIN TRIGGER).
        
        Two conditions:
        1. ER >= threshold (market is trending)
        2. Close > KAMA (bullish direction)
        
        Returns: (passed: bool, er_value: float, reason: str)
        """
        use_htf_filter = self.params.get("use_htf_filter", False)
        if not use_htf_filter:
            return True, 0.0, "HTF filter disabled"
        
        # Calculate ER
        er_value = self._calculate_efficiency_ratio(df)
        er_threshold = self.params.get("htf_er_threshold", 0.35)
        
        # Check ER condition
        if not check_efficiency_ratio_filter(er_value, er_threshold, True):
            return False, er_value, f"ER {er_value:.3f} < threshold {er_threshold}"
        
        # Check Close > KAMA
        current_close = float(df["close"].iloc[-1])
        if current_close <= kama_value:
            return False, er_value, f"Close {current_close:.5f} <= KAMA {kama_value:.5f}"
        
        return True, er_value, f"ER={er_value:.3f}, Close > KAMA"
    
    def _check_kama_condition(self, hl2_ema_value: float, kama_value: float) -> tuple:
        """
        Check if EMA(HL2) > KAMA (trend confirmation).
        
        Returns: (passed: bool, reason: str)
        """
        if hl2_ema_value > kama_value:
            return True, f"HL2_EMA {hl2_ema_value:.5f} > KAMA {kama_value:.5f}"
        return False, f"HL2_EMA {hl2_ema_value:.5f} <= KAMA {kama_value:.5f}"
    
    def _check_pullback(self, df: pd.DataFrame, kama_series: pd.Series) -> tuple:
        """
        Check pullback condition using standard filter.
        
        Returns: (valid: bool, pullback_data: dict, reason: str)
        """
        use_pullback_filter = self.params.get("use_pullback_filter", False)
        if not use_pullback_filter:
            # No pullback filter - return current high as breakout level
            current_high = float(df["high"].iloc[-1])
            return True, {'breakout_level': current_high, 'bars_since_hh': 0}, "Pullback filter disabled"
        
        min_bars = self.params.get("pullback_min_bars", 2)
        max_bars = self.params.get("pullback_max_bars", 5)
        
        # Build price history lists
        required_len = max_bars + 5
        if len(df) < required_len:
            return False, None, f"Insufficient data for pullback ({len(df)} < {required_len})"
        
        highs = df["high"].iloc[-required_len:].tolist()
        lows = df["low"].iloc[-required_len:].tolist()
        closes = df["close"].iloc[-required_len:].tolist()
        kama_values = kama_series.iloc[-required_len:].tolist()
        
        # Use standard pullback detection
        result = detect_pullback(
            highs=highs,
            lows=lows,
            closes=closes,
            kama_values=kama_values,
            min_bars=min_bars,
            max_bars=max_bars,
            enabled=True
        )
        
        if result['valid']:
            return True, result, f"Pullback detected: {result['bars_since_hh']} bars since HH @ {result['hh_price']:.5f}"
        
        return False, result, f"No valid pullback (bars_since_hh={result['bars_since_hh']}, respects_support={result['respects_support']})"
    
    # =========================================================================
    # MAIN SIGNAL CHECK
    # =========================================================================
    
    def check_signal(self, df: pd.DataFrame) -> Signal:
        """
        Check for trading signal using 3-phase state machine.
        """
        self.current_bar_index += 1
        now = datetime.now()
        
        # Validate data
        min_bars = max(self.scaled_er_period, self.kama_period, self.atr_avg_period) + 20
        if df is None or len(df) < min_bars:
            return self._create_no_signal(f"Insufficient data ({len(df) if df is not None else 0} < {min_bars})")
        
        # Calculate indicators
        hl2 = self._calculate_hl2(df)
        hl2_ema = self._calculate_hl2_ema(hl2)
        kama_series = self._calculate_kama(hl2)
        atr_series = self._calculate_atr(df)
        
        current_kama = float(kama_series.iloc[-1])
        current_hl2_ema = float(hl2_ema.iloc[-1])
        current_atr = float(atr_series.iloc[-1])
        avg_atr = self._calculate_average_atr(atr_series)
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
        
        # Convert to UTC for time filter
        current_dt_utc = broker_to_utc(current_dt)
        
        # ========================================
        # STATE MACHINE
        # ========================================
        
        # --- SCANNING STATE ---
        if self.state == SEDNAState.SCANNING:
            
            # Time filter
            if self.params.get("use_time_filter", False):
                allowed_hours = self.params.get("allowed_hours", [])
                if not check_time_filter(current_dt_utc, allowed_hours, True):
                    reason = f"Time filter: UTC {current_dt_utc.hour}h not in {allowed_hours}"
                    return self._create_no_signal(reason)
            
            # Day filter
            if self.params.get("use_day_filter", False):
                allowed_days = self.params.get("allowed_days", [0, 1, 2, 3, 4])
                if not check_day_filter(current_dt_utc, allowed_days, True):
                    day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
                    reason = f"Day filter: {day_names[current_dt_utc.weekday()]} not in {[day_names[d] for d in allowed_days]}"
                    return self._create_no_signal(reason)
            
            # Phase 1: HTF Filter (ER >= threshold AND Close > KAMA)
            htf_passed, er_value, htf_reason = self._check_htf_filter(df, current_kama)
            if not htf_passed:
                return self._create_no_signal(f"HTF filter: {htf_reason}")
            
            # Phase 2: KAMA condition (HL2_EMA > KAMA)
            kama_passed, kama_reason = self._check_kama_condition(current_hl2_ema, current_kama)
            if not kama_passed:
                return self._create_no_signal(f"KAMA condition: {kama_reason}")
            
            # Phase 3: Pullback detection
            pullback_passed, pullback_data, pullback_reason = self._check_pullback(df, kama_series)
            if not pullback_passed:
                return self._create_no_signal(f"Pullback: {pullback_reason}")
            
            # All conditions met - setup breakout window
            use_breakout_window = self.params.get("use_breakout_window", True)
            
            if use_breakout_window:
                pip_value = self.params.get("pip_value", 0.01)
                offset_pips = self.params.get("breakout_level_offset_pips", 1.0)
                
                self.pattern_bar = self.current_bar_index
                self.pullback_data = pullback_data
                self.breakout_level = pullback_data['breakout_level'] + (offset_pips * pip_value)
                self.pattern_atr = avg_atr  # Use average ATR
                
                self.state = SEDNAState.WAITING_BREAKOUT
                
                self._log_state_transition(
                    "SCANNING", "WAITING_BREAKOUT",
                    f"Broker: {current_dt:%H:%M}, UTC: {current_dt_utc:%H:%M} | "
                    f"ER={er_value:.3f}, KAMA={current_kama:.5f}, HL2_EMA={current_hl2_ema:.5f} | "
                    f"Pullback HH={pullback_data['hh_price']:.5f}, Breakout={self.breakout_level:.5f}, "
                    f"Avg ATR={avg_atr:.6f}"
                )
                
                return self._create_no_signal("Waiting for breakout confirmation")
            
            else:
                # Immediate entry (no breakout confirmation)
                return self._execute_immediate_entry(
                    df, current_dt, current_dt_utc, current_close, avg_atr,
                    er_value, current_kama, current_hl2_ema
                )
        
        # --- WAITING_BREAKOUT STATE ---
        elif self.state == SEDNAState.WAITING_BREAKOUT:
            
            # Check timeout
            bars_since = self.current_bar_index - self.pattern_bar
            breakout_window = self.params.get("breakout_window_candles", 5)
            
            if bars_since > breakout_window:
                self._log_state_transition(
                    "WAITING_BREAKOUT", "SCANNING",
                    f"Timeout after {bars_since} bars (window={breakout_window})"
                )
                self.reset_state()
                return self._create_no_signal("Breakout window expired")
            
            # Check for breakout
            pip_value = self.params.get("pip_value", 0.01)
            if check_pullback_breakout(current_high, self.breakout_level, buffer_pips=0, pip_value=pip_value):
                return self._execute_breakout_entry(
                    df, current_dt, current_dt_utc, bars_since,
                    current_kama, current_hl2_ema
                )
            
            return self._create_no_signal(
                f"Waiting for breakout above {self.breakout_level:.5f} ({bars_since}/{breakout_window} bars)"
            )
        
        return self._create_no_signal("Unknown state")
    
    # =========================================================================
    # ENTRY EXECUTION HELPERS
    # =========================================================================
    
    def _execute_immediate_entry(
        self, df: pd.DataFrame, current_dt: datetime, current_dt_utc: datetime,
        entry_price: float, avg_atr: float, er_value: float,
        kama_value: float, hl2_ema_value: float
    ) -> Signal:
        """Execute immediate entry (no breakout window)."""
        
        # ATR Filter (using average ATR)
        use_atr_filter = self.params.get("use_atr_filter", False)
        atr_min = self.params.get("atr_min", 0)
        atr_max = self.params.get("atr_max", 999)
        
        if not check_atr_filter(avg_atr, atr_min, atr_max, use_atr_filter):
            reason = f"ATR filter: avg {avg_atr:.6f} not in [{atr_min}-{atr_max}]"
            self.logger.info(f"[{self.config_name}] {reason} - Signal rejected")
            return self._create_no_signal(reason)
        
        stop_loss = entry_price - (avg_atr * self.params.get("atr_sl_multiplier", 3.0))
        take_profit = entry_price + (avg_atr * self.params.get("atr_tp_multiplier", 8.0))
        
        # SL Pips Filter
        pip_value = self.params.get("pip_value", 0.01)
        sl_pips = abs(entry_price - stop_loss) / pip_value
        
        use_sl_pips_filter = self.params.get("use_sl_pips_filter", False)
        sl_pips_min = self.params.get("sl_pips_min", 0)
        sl_pips_max = self.params.get("sl_pips_max", 999)
        
        if not check_sl_pips_filter(sl_pips, sl_pips_min, sl_pips_max, use_sl_pips_filter):
            reason = f"SL pips filter: {sl_pips:.1f} not in [{sl_pips_min}-{sl_pips_max}]"
            self.logger.info(f"[{self.config_name}] {reason} - Signal rejected")
            return self._create_no_signal(reason)
        
        self.logger.info(
            f"[{self.config_name}] SIGNAL LONG (immediate) | "
            f"Broker: {current_dt:%H:%M}, UTC: {current_dt_utc:%H:%M} | "
            f"Entry: {entry_price:.5f}, SL: {stop_loss:.5f}, TP: {take_profit:.5f} | "
            f"ER={er_value:.3f}, KAMA={kama_value:.5f}, HL2_EMA={hl2_ema_value:.5f}, "
            f"Avg ATR={avg_atr:.6f}, SL pips={sl_pips:.1f}"
        )
        
        return self._create_signal(
            direction=SignalDirection.LONG,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            atr=avg_atr,
            reason=f"HTF trend + KAMA bullish + ER={er_value:.3f}"
        )
    
    def _execute_breakout_entry(
        self, df: pd.DataFrame, current_dt: datetime, current_dt_utc: datetime,
        bars_since: int, kama_value: float, hl2_ema_value: float
    ) -> Signal:
        """Execute entry after breakout confirmation."""
        
        entry_price = self.breakout_level
        atr_for_sl = self.pattern_atr if self.pattern_atr else 0.0
        
        if atr_for_sl <= 0:
            self.reset_state()
            return self._create_no_signal("Invalid ATR for entry")
        
        # ATR Filter (using average ATR from pattern)
        use_atr_filter = self.params.get("use_atr_filter", False)
        atr_min = self.params.get("atr_min", 0)
        atr_max = self.params.get("atr_max", 999)
        
        if not check_atr_filter(atr_for_sl, atr_min, atr_max, use_atr_filter):
            reason = f"ATR filter: avg {atr_for_sl:.6f} not in [{atr_min}-{atr_max}]"
            self.logger.info(f"[{self.config_name}] {reason} - Signal rejected")
            self.reset_state()
            return self._create_no_signal(reason)
        
        stop_loss = entry_price - (atr_for_sl * self.params.get("atr_sl_multiplier", 3.0))
        take_profit = entry_price + (atr_for_sl * self.params.get("atr_tp_multiplier", 8.0))
        
        # SL Pips Filter
        pip_value = self.params.get("pip_value", 0.01)
        sl_pips = abs(entry_price - stop_loss) / pip_value
        
        use_sl_pips_filter = self.params.get("use_sl_pips_filter", False)
        sl_pips_min = self.params.get("sl_pips_min", 0)
        sl_pips_max = self.params.get("sl_pips_max", 999)
        
        if not check_sl_pips_filter(sl_pips, sl_pips_min, sl_pips_max, use_sl_pips_filter):
            reason = f"SL pips filter: {sl_pips:.1f} not in [{sl_pips_min}-{sl_pips_max}]"
            self.logger.info(f"[{self.config_name}] {reason} - Signal rejected")
            self.reset_state()
            return self._create_no_signal(reason)
        
        # Calculate ER for logging
        er_value = self._calculate_efficiency_ratio(df)
        
        # Log pullback info if available
        pullback_info = ""
        if self.pullback_data:
            pullback_info = f"Pullback HH={self.pullback_data['hh_price']:.5f}, bars_since_HH={self.pullback_data['bars_since_hh']}, "
        
        self.logger.info(
            f"[{self.config_name}] SIGNAL LONG (breakout) | "
            f"Broker: {current_dt:%H:%M}, UTC: {current_dt_utc:%H:%M} | "
            f"Entry: {entry_price:.5f}, SL: {stop_loss:.5f}, TP: {take_profit:.5f} | "
            f"{pullback_info}"
            f"Bars waited: {bars_since}, ER={er_value:.3f}, KAMA={kama_value:.5f}, "
            f"Avg ATR={atr_for_sl:.6f}, SL pips={sl_pips:.1f}"
        )
        
        signal = self._create_signal(
            direction=SignalDirection.LONG,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            atr=atr_for_sl,
            reason=f"Breakout confirmed after {bars_since} bars, ER={er_value:.3f}"
        )
        
        self.reset_state()
        return signal
