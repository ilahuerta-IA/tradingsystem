"""
GLIESE Strategy Checker for Live Trading.

Implements the 4-phase state machine for mean reversion:
1. SCANNING - Looking for ranging market (ER low + ADXR low + KAMA flat)
2. RANGE_DETECTED - Monitoring for extension below lower band
3. EXTENSION_BELOW - Tracking extension, waiting for reversal
4. REVERSAL_DETECTED - Waiting for pullback
5. WAITING_BREAKOUT - Monitoring for breakout above micro-swing

Key differences from SEDNA:
- SEDNA: Trend-following (ER HIGH = good)
- GLIESE: Mean-reversion (ER LOW = good)
- Uses ADXR filter for trend strength
- Uses KAMA slope filter for flat detection
- Trades bounce from range extremes back to fair value

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
    calculate_efficiency_ratio,
    calculate_adxr,
    calculate_kama,
    calculate_kama_slope,
    check_efficiency_ratio_range_filter,
    check_adxr_filter,
    check_kama_slope_filter,
    calculate_bands,
    check_extension_below_band,
    check_reversal_above_band,
    detect_pullback,
    check_pullback_breakout,
)
from live.timezone import broker_to_utc


class GLIESEState(Enum):
    """GLIESE state machine states."""
    SCANNING = "SCANNING"
    RANGE_DETECTED = "RANGE_DETECTED"
    EXTENSION_BELOW = "EXTENSION_BELOW"
    REVERSAL_DETECTED = "REVERSAL_DETECTED"
    WAITING_BREAKOUT = "WAITING_BREAKOUT"


class GLIESEChecker(BaseChecker):
    """
    GLIESE strategy signal checker for mean reversion.
    
    4-Phase State Machine:
    - SCANNING: Monitor for ranging market (ER low + ADXR low + KAMA flat)
    - RANGE_DETECTED: Monitor for extension below lower band
    - EXTENSION_BELOW: Track extension, wait for reversal back above band
    - REVERSAL_DETECTED: Wait for pullback pattern
    - WAITING_BREAKOUT: Monitor breakout level for entry
    """
    
    @property
    def strategy_name(self) -> str:
        return "GLIESE"
    
    def __init__(
        self,
        config_name: str,
        params: Dict[str, Any],
        logger: Optional[logging.Logger] = None
    ):
        super().__init__(config_name, params, logger)
        
        # State machine
        self.state = GLIESEState.SCANNING
        self.pattern_bar: Optional[int] = None
        self.breakout_level: Optional[float] = None
        self.pattern_atr: Optional[float] = None
        self.pullback_data: Optional[Dict] = None
        
        # Extension tracking
        self.extension_bar_count = 0
        self.extension_start_bar: Optional[int] = None
        self.extension_min_price = float('inf')
        
        # KAMA parameters
        self.kama_period = params.get("kama_period", 10)
        self.kama_fast = params.get("kama_fast", 2)
        self.kama_slow = params.get("kama_slow", 30)
        
        # Band parameters
        self.band_atr_mult = params.get("band_atr_mult", 1.5)
        
        # HTF parameters (for range detection)
        self.htf_er_period = params.get("htf_er_period", 10)
        self.htf_timeframe_minutes = params.get("htf_timeframe_minutes", 15)
        base_tf_minutes = 5
        self.scaled_er_period = self.htf_er_period * (self.htf_timeframe_minutes // base_tf_minutes)
        
        # ADXR parameters
        self.adxr_period = params.get("adxr_period", 14)
        self.adxr_lookback = params.get("adxr_lookback", 14)
        
        # KAMA slope parameters
        self.kama_slope_lookback = params.get("kama_slope_lookback", 5)
        
        # ATR averaging
        self.atr_avg_period = params.get("atr_avg_period", 20)
        
        # Price history for indicators
        self.price_history: Dict[str, List[float]] = {
            'highs': [],
            'lows': [],
            'closes': [],
            'kama': []
        }
        self.kama_history: List[float] = []
        
        self.logger.info(
            f"[{self.config_name}] GLIESE Checker initialized | "
            f"KAMA({self.kama_period},{self.kama_fast},{self.kama_slow}) | "
            f"Bands: KAMA +/- {self.band_atr_mult}xATR | "
            f"ER period={self.scaled_er_period} ({self.htf_timeframe_minutes}m equiv)"
        )
    
    def reset_state(self) -> None:
        """Reset state machine to SCANNING."""
        self.state = GLIESEState.SCANNING
        self.pattern_bar = None
        self.breakout_level = None
        self.pattern_atr = None
        self.pullback_data = None
        self.extension_bar_count = 0
        self.extension_start_bar = None
        self.extension_min_price = float('inf')
    
    def get_state_info(self) -> Dict[str, Any]:
        """Get current state machine info for logging."""
        return {
            "strategy": self.strategy_name,
            "state": self.state.value,
            "pattern_bar": self.pattern_bar,
            "breakout_level": self.breakout_level,
            "extension_bars": self.extension_bar_count,
            "current_bar": self.current_bar_index,
            "pullback_data": self.pullback_data,
        }
    
    # =========================================================================
    # INDICATOR CALCULATIONS
    # =========================================================================
    
    def _calculate_hl2(self, df: pd.DataFrame) -> pd.Series:
        """Calculate HL2 = (High + Low) / 2."""
        return (df["high"] + df["low"]) / 2.0
    
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
        """Calculate Efficiency Ratio for range filter."""
        if len(df) < self.scaled_er_period + 1:
            return 1.0  # Return high ER (trending) if insufficient data
        
        close_prices = df["close"].tolist()
        return calculate_efficiency_ratio(close_prices, period=self.scaled_er_period)
    
    def _calculate_bands(self, kama_value: float, atr_value: float) -> tuple:
        """Calculate upper and lower bands."""
        return calculate_bands(kama_value, atr_value, self.band_atr_mult)
    
    # =========================================================================
    # RANGE DETECTION CONDITIONS
    # =========================================================================
    
    def _check_range_conditions(self, df: pd.DataFrame, kama_value: float, atr_value: float) -> tuple:
        """
        Check if market is in ranging state (all conditions).
        
        Returns: (passed: bool, details: dict, reason: str)
        """
        details = {}
        
        # 1. Efficiency Ratio LOW
        use_htf_range_filter = self.params.get("use_htf_range_filter", True)
        if use_htf_range_filter:
            er_value = self._calculate_efficiency_ratio(df)
            er_max_threshold = self.params.get("htf_er_max_threshold", 0.30)
            details['er'] = er_value
            
            if not check_efficiency_ratio_range_filter(er_value, er_max_threshold, True):
                return False, details, f"ER {er_value:.3f} >= {er_max_threshold} (trending)"
        
        # 2. ADXR LOW
        use_adxr_filter = self.params.get("use_adxr_filter", True)
        if use_adxr_filter:
            required_bars = (self.adxr_period * 2) + self.adxr_lookback + 5
            if len(df) >= required_bars:
                highs = df["high"].tolist()
                lows = df["low"].tolist()
                closes = df["close"].tolist()
                
                adxr_value = calculate_adxr(
                    highs, lows, closes,
                    self.adxr_period, self.adxr_lookback
                )
                adxr_max_threshold = self.params.get("adxr_max_threshold", 25.0)
                details['adxr'] = adxr_value
                
                if not math.isnan(adxr_value):
                    if not check_adxr_filter(adxr_value, adxr_max_threshold, True):
                        return False, details, f"ADXR {adxr_value:.2f} >= {adxr_max_threshold} (trending)"
        
        # 3. KAMA Slope FLAT
        use_kama_slope_filter = self.params.get("use_kama_slope_filter", True)
        if use_kama_slope_filter:
            if len(self.kama_history) >= self.kama_slope_lookback + 1:
                kama_slope = calculate_kama_slope(self.kama_history, self.kama_slope_lookback)
                kama_slope_atr_mult = self.params.get("kama_slope_atr_mult", 0.3)
                details['kama_slope'] = kama_slope
                details['slope_threshold'] = kama_slope_atr_mult * atr_value
                
                if not math.isnan(kama_slope):
                    if not check_kama_slope_filter(kama_slope, atr_value, kama_slope_atr_mult, True):
                        return False, details, f"KAMA slope {kama_slope:.6f} >= threshold (trending)"
        
        return True, details, "Range confirmed"
    
    def _check_er_cancel(self, df: pd.DataFrame) -> bool:
        """Check if ER has risen above cancel threshold (trend starting)."""
        use_htf_range_filter = self.params.get("use_htf_range_filter", True)
        if not use_htf_range_filter:
            return False
        
        try:
            er_value = self._calculate_efficiency_ratio(df)
            er_cancel_threshold = self.params.get("er_cancel_threshold", 0.50)
            return er_value > er_cancel_threshold
        except:
            return False
    
    # =========================================================================
    # EXTENSION AND REVERSAL DETECTION
    # =========================================================================
    
    def _check_extension_below(self, current_close: float, lower_band: float) -> bool:
        """Check if price is below lower band."""
        return check_extension_below_band(current_close, lower_band)
    
    def _check_reversal_above(self, current_close: float, lower_band: float) -> bool:
        """Check if price has reversed back above lower band."""
        return check_reversal_above_band(current_close, lower_band)
    
    # =========================================================================
    # PULLBACK DETECTION
    # =========================================================================
    
    def _check_pullback(self, df: pd.DataFrame, kama_series: pd.Series) -> tuple:
        """
        Check pullback condition using standard filter.
        
        Returns: (valid: bool, pullback_data: dict, reason: str)
        """
        use_pullback_filter = self.params.get("use_pullback_filter", True)
        if not use_pullback_filter:
            current_high = float(df["high"].iloc[-1])
            return True, {'breakout_level': current_high, 'bars_since_hh': 0}, "Pullback filter disabled"
        
        min_bars = self.params.get("pullback_min_bars", 1)
        max_bars = self.params.get("pullback_max_bars", 4)
        
        required_len = max_bars + 5
        if len(df) < required_len:
            return False, None, f"Insufficient data for pullback ({len(df)} < {required_len})"
        
        highs = df["high"].iloc[-required_len:].tolist()
        lows = df["low"].iloc[-required_len:].tolist()
        closes = df["close"].iloc[-required_len:].tolist()
        kama_values = kama_series.iloc[-required_len:].tolist()
        
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
            return True, result, f"Pullback detected: {result['bars_since_hh']} bars since HH"
        
        return False, result, f"No valid pullback (bars_since_hh={result['bars_since_hh']})"
    
    # =========================================================================
    # PRICE HISTORY MANAGEMENT
    # =========================================================================
    
    def _update_price_history(self, df: pd.DataFrame, kama_series: pd.Series):
        """Update price history for pullback detection."""
        try:
            current_high = float(df["high"].iloc[-1])
            current_low = float(df["low"].iloc[-1])
            current_close = float(df["close"].iloc[-1])
            current_kama = float(kama_series.iloc[-1])
            
            self.price_history['highs'].append(current_high)
            self.price_history['lows'].append(current_low)
            self.price_history['closes'].append(current_close)
            self.price_history['kama'].append(current_kama)
            self.kama_history.append(current_kama)
            
            # Keep only what we need
            max_len = max(
                self.params.get("pullback_max_bars", 4) + 10,
                self.kama_slope_lookback + 5
            )
            for key in self.price_history:
                if len(self.price_history[key]) > max_len:
                    self.price_history[key] = self.price_history[key][-max_len:]
            
            if len(self.kama_history) > max_len:
                self.kama_history = self.kama_history[-max_len:]
        except:
            pass
    
    # =========================================================================
    # MAIN SIGNAL CHECK
    # =========================================================================
    
    def check_signal(self, df: pd.DataFrame) -> Signal:
        """
        Check for trading signal using 4-phase state machine.
        """
        self.current_bar_index += 1
        now = datetime.now()
        
        # Validate data
        min_bars = max(
            self.scaled_er_period,
            self.kama_period,
            (self.adxr_period * 2) + self.adxr_lookback,
            self.atr_avg_period
        ) + 20
        
        if df is None or len(df) < min_bars:
            return self._create_no_signal(f"Insufficient data ({len(df) if df is not None else 0} < {min_bars})")
        
        # Calculate indicators
        hl2 = self._calculate_hl2(df)
        kama_series = self._calculate_kama(hl2)
        atr_series = self._calculate_atr(df)
        
        current_kama = float(kama_series.iloc[-1])
        current_atr = float(atr_series.iloc[-1])
        avg_atr = self._calculate_average_atr(atr_series)
        current_close = float(df["close"].iloc[-1])
        current_high = float(df["high"].iloc[-1])
        current_low = float(df["low"].iloc[-1])
        
        # Calculate bands
        upper_band, lower_band = self._calculate_bands(current_kama, current_atr)
        
        # Update price history
        self._update_price_history(df, kama_series)
        
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
        if self.state == GLIESEState.SCANNING:
            
            # Time filter
            if self.params.get("use_time_filter", False):
                allowed_hours = self.params.get("allowed_hours", [])
                if not check_time_filter(current_dt_utc, allowed_hours, True):
                    return self._create_no_signal(f"Time filter: UTC {current_dt_utc.hour}h not in allowed")
            
            # Day filter
            if self.params.get("use_day_filter", False):
                allowed_days = self.params.get("allowed_days", [0, 1, 2, 3, 4])
                if not check_day_filter(current_dt_utc, allowed_days, True):
                    return self._create_no_signal(f"Day filter: weekday not in allowed")
            
            # Phase 1: Range detection
            range_ok, details, reason = self._check_range_conditions(df, current_kama, current_atr)
            
            if range_ok:
                self.state = GLIESEState.RANGE_DETECTED
                er_str = f"ER={details.get('er', 0):.3f}" if 'er' in details else ""
                adxr_str = f"ADXR={details.get('adxr', 0):.2f}" if 'adxr' in details else ""
                self._log_state_transition(
                    "SCANNING", "RANGE_DETECTED",
                    f"Broker: {current_dt:%H:%M}, UTC: {current_dt_utc:%H:%M} | "
                    f"{er_str}, {adxr_str}, KAMA={current_kama:.5f}"
                )
            
            return self._create_no_signal(f"Scanning: {reason}")
        
        # --- RANGE_DETECTED STATE ---
        elif self.state == GLIESEState.RANGE_DETECTED:
            
            # Check if range still valid
            if self._check_er_cancel(df):
                self._log_state_transition("RANGE_DETECTED", "SCANNING", "ER surge - range cancelled")
                self.reset_state()
                return self._create_no_signal("Range cancelled (ER surge)")
            
            # Check for extension below lower band
            if self._check_extension_below(current_close, lower_band):
                self.state = GLIESEState.EXTENSION_BELOW
                self.extension_start_bar = self.current_bar_index
                self.extension_bar_count = 1
                self.extension_min_price = current_low
                
                self._log_state_transition(
                    "RANGE_DETECTED", "EXTENSION_BELOW",
                    f"Close={current_close:.5f} < LowerBand={lower_band:.5f}"
                )
            
            return self._create_no_signal(f"Range detected, waiting for extension below {lower_band:.5f}")
        
        # --- EXTENSION_BELOW STATE ---
        elif self.state == GLIESEState.EXTENSION_BELOW:
            
            # Check for cancellation
            if self._check_er_cancel(df):
                self._log_state_transition("EXTENSION_BELOW", "SCANNING", "ER surge - extension cancelled")
                self.reset_state()
                return self._create_no_signal("Extension cancelled (ER surge)")
            
            # Track extension
            self.extension_bar_count += 1
            self.extension_min_price = min(self.extension_min_price, current_low)
            
            # Check for timeout
            extension_max_bars = self.params.get("extension_max_bars", 20)
            if self.extension_bar_count > extension_max_bars:
                self._log_state_transition(
                    "EXTENSION_BELOW", "SCANNING",
                    f"Extension timeout ({self.extension_bar_count} bars)"
                )
                self.reset_state()
                return self._create_no_signal("Extension timeout - possible breakdown")
            
            # Check for reversal back above lower band
            extension_min_bars = self.params.get("extension_min_bars", 2)
            if self._check_reversal_above(current_close, lower_band):
                if self.extension_bar_count >= extension_min_bars:
                    self.state = GLIESEState.REVERSAL_DETECTED
                    self._log_state_transition(
                        "EXTENSION_BELOW", "REVERSAL_DETECTED",
                        f"ExtBars={self.extension_bar_count}, MinPrice={self.extension_min_price:.5f}"
                    )
            
            return self._create_no_signal(
                f"Extension: {self.extension_bar_count}/{extension_max_bars} bars, min={self.extension_min_price:.5f}"
            )
        
        # --- REVERSAL_DETECTED STATE ---
        elif self.state == GLIESEState.REVERSAL_DETECTED:
            
            # Check for cancellation
            if self._check_er_cancel(df):
                self._log_state_transition("REVERSAL_DETECTED", "SCANNING", "ER surge - reversal cancelled")
                self.reset_state()
                return self._create_no_signal("Reversal cancelled (ER surge)")
            
            # Check for pullback
            pullback_ok, pullback_data, pullback_reason = self._check_pullback(df, kama_series)
            
            if pullback_ok:
                self.pattern_bar = self.current_bar_index
                self.pattern_atr = avg_atr
                self.pullback_data = pullback_data
                
                # Set breakout level
                pip_value = self.params.get("pip_value", 0.0001)
                offset_pips = self.params.get("breakout_level_offset_pips", 2.0)
                self.breakout_level = pullback_data['breakout_level'] + (offset_pips * pip_value)
                
                self.state = GLIESEState.WAITING_BREAKOUT
                self._log_state_transition(
                    "REVERSAL_DETECTED", "WAITING_BREAKOUT",
                    f"Pullback HH={pullback_data['breakout_level']:.5f}, BreakoutLevel={self.breakout_level:.5f}"
                )
            
            return self._create_no_signal(f"Reversal detected, waiting for pullback: {pullback_reason}")
        
        # --- WAITING_BREAKOUT STATE ---
        elif self.state == GLIESEState.WAITING_BREAKOUT:
            
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
            
            # Check for cancellation
            if self._check_er_cancel(df):
                self._log_state_transition("WAITING_BREAKOUT", "SCANNING", "ER surge - breakout cancelled")
                self.reset_state()
                return self._create_no_signal("Breakout cancelled (ER surge)")
            
            # Check for breakout
            pip_value = self.params.get("pip_value", 0.0001)
            if check_pullback_breakout(current_high, self.breakout_level, buffer_pips=0, pip_value=pip_value):
                return self._execute_breakout_entry(
                    df, current_dt, current_dt_utc, bars_since, current_kama, avg_atr
                )
            
            return self._create_no_signal(
                f"Waiting for breakout above {self.breakout_level:.5f} ({bars_since}/{breakout_window} bars)"
            )
        
        return self._create_no_signal("Unknown state")
    
    # =========================================================================
    # ENTRY EXECUTION
    # =========================================================================
    
    def _execute_breakout_entry(
        self, df: pd.DataFrame, current_dt: datetime, current_dt_utc: datetime,
        bars_since: int, kama_value: float, avg_atr: float
    ) -> Signal:
        """Execute entry after breakout confirmation."""
        
        entry_price = self.breakout_level
        atr_for_sl = self.pattern_atr if self.pattern_atr else avg_atr
        
        if atr_for_sl <= 0:
            self.reset_state()
            return self._create_no_signal("Invalid ATR for entry")
        
        # ATR Filter
        use_atr_filter = self.params.get("use_atr_filter", False)
        atr_min = self.params.get("atr_min", 0)
        atr_max = self.params.get("atr_max", 999)
        
        if not check_atr_filter(atr_for_sl, atr_min, atr_max, use_atr_filter):
            reason = f"ATR filter: avg {atr_for_sl:.6f} not in [{atr_min}-{atr_max}]"
            self.logger.info(f"[{self.config_name}] {reason} - Signal rejected")
            self.reset_state()
            return self._create_no_signal(reason)
        
        # Calculate SL/TP
        stop_loss = entry_price - (atr_for_sl * self.params.get("atr_sl_multiplier", 2.0))
        take_profit = entry_price + (atr_for_sl * self.params.get("atr_tp_multiplier", 3.0))
        
        # SL Pips Filter
        pip_value = self.params.get("pip_value", 0.0001)
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
        
        # Log entry details
        extension_info = f"ExtBars={self.extension_bar_count}, ExtMin={self.extension_min_price:.5f}"
        pullback_info = ""
        if self.pullback_data:
            pullback_info = f", PB_HH={self.pullback_data['breakout_level']:.5f}"
        
        self.logger.info(
            f"[{self.config_name}] SIGNAL LONG (mean-reversion breakout) | "
            f"Broker: {current_dt:%H:%M}, UTC: {current_dt_utc:%H:%M} | "
            f"Entry: {entry_price:.5f}, SL: {stop_loss:.5f}, TP: {take_profit:.5f} | "
            f"{extension_info}{pullback_info}, "
            f"Bars waited: {bars_since}, ER={er_value:.3f}, KAMA={kama_value:.5f}, "
            f"Avg ATR={atr_for_sl:.6f}, SL pips={sl_pips:.1f}"
        )
        
        signal = self._create_signal(
            direction=SignalDirection.LONG,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            atr=atr_for_sl,
            reason=f"Mean-reversion breakout after {self.extension_bar_count} ext bars, ER={er_value:.3f}"
        )
        
        self.reset_state()
        return signal
