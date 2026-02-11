"""
GEMINI Strategy Checker for Live Trading.

Implements correlation divergence momentum using Harmony Score.
Requires TWO data feeds: primary (e.g., EURUSD) and reference (e.g., USDCHF).

Entry System (2-phase):
1. TRIGGER: HL2_EMA crosses above KAMA (bullish cross)
2. CONFIRM: Within allowed_cross_bars window, ROC and Harmony angles in range

Harmony Score = ROC_primary × (-ROC_reference) × scale
- Positive when primary rises AND reference falls (harmonic divergence)
- Used to confirm genuine momentum, not just noise

Uses lib/filters.py for filtering consistent with backtesting.
"""

import math
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from enum import Enum

import pandas as pd
import numpy as np

from .base_checker import BaseChecker, Signal, SignalDirection
from lib.filters import check_time_filter, check_day_filter, check_sl_pips_filter, check_atr_filter
from live.timezone import broker_to_utc


class GEMINIState(Enum):
    """GEMINI state machine states."""
    SCANNING = "SCANNING"
    CROSS_WINDOW = "CROSS_WINDOW"


class GEMINIChecker(BaseChecker):
    """
    GEMINI strategy signal checker.
    
    2-Phase State Machine:
    - SCANNING: Monitor for HL2_EMA crossing above KAMA
    - CROSS_WINDOW: Within N bars of cross, check angle confirmations
    
    Requires reference_df parameter in check_signal() for dual-feed calculation.
    """
    
    @property
    def strategy_name(self) -> str:
        return "GEMINI"
    
    def __init__(
        self,
        config_name: str,
        params: Dict[str, Any],
        logger: Optional[logging.Logger] = None
    ):
        super().__init__(config_name, params, logger)
        
        # State machine
        self.state = GEMINIState.SCANNING
        self.cross_detected_bar: Optional[int] = None
        self.prev_hl2_above_kama: bool = False
        
        # History for calculations
        self.primary_close_history = []
        self.reference_close_history = []
        self.roc_primary_history = []
        self.harmony_history = []
        self.atr_history = []
        
        # KAMA parameters
        self.kama_period = params.get("kama_period", 10)
        self.kama_fast = params.get("kama_fast", 2)
        self.kama_slow = params.get("kama_slow", 30)
        self.hl2_ema_period = params.get("hl2_ema_period", 1)
        
        # ROC parameters
        self.roc_period_primary = params.get("roc_period_primary", 5)
        self.roc_period_reference = params.get("roc_period_reference", 5)
        self.harmony_scale = params.get("harmony_scale", 10000)
        
        # Entry parameters
        self.allowed_cross_bars = params.get("allowed_cross_bars", [])
        self.entry_roc_angle_min = params.get("entry_roc_angle_min", 10.0)
        self.entry_roc_angle_max = params.get("entry_roc_angle_max", 40.0)
        self.entry_harmony_angle_min = params.get("entry_harmony_angle_min", 10.0)
        self.entry_harmony_angle_max = params.get("entry_harmony_angle_max", 25.0)
        self.roc_angle_scale = params.get("roc_angle_scale", 1.0)
        self.harmony_angle_scale = params.get("harmony_angle_scale", 1.0)
        
        # Plot multipliers (used for angle calculation)
        self.plot_roc_multiplier = params.get("plot_roc_multiplier", 500)
        self.plot_harmony_multiplier = params.get("plot_harmony_multiplier", 15.0)
        
        # ATR parameters
        self.atr_length = params.get("atr_length", 10)
        self.atr_avg_period = params.get("atr_avg_period", 20)
        self.atr_sl_mult = params.get("atr_sl_multiplier", 5.0)
        self.atr_tp_mult = params.get("atr_tp_multiplier", 10.0)
        
        # Pip value
        self.pip_value = params.get("pip_value", 0.0001)
        
        self.logger.info(
            f"[{self.config_name}] GEMINI Checker initialized | "
            f"KAMA({self.kama_period},{self.kama_fast},{self.kama_slow}) | "
            f"ROC periods: {self.roc_period_primary}/{self.roc_period_reference}"
        )
    
    def reset_state(self) -> None:
        """Reset state machine to SCANNING."""
        self.state = GEMINIState.SCANNING
        self.cross_detected_bar = None
        self.prev_hl2_above_kama = False
        self.primary_close_history = []
        self.reference_close_history = []
        self.roc_primary_history = []
        self.harmony_history = []
        self.atr_history = []
    
    def get_state_info(self) -> Dict[str, Any]:
        """Get current state machine info for logging."""
        return {
            "strategy": self.strategy_name,
            "state": self.state.value,
            "cross_detected_bar": self.cross_detected_bar,
            "current_bar": self.current_bar_index,
            "bars_since_cross": (
                self.current_bar_index - self.cross_detected_bar 
                if self.cross_detected_bar else None
            ),
        }
    
    # =========================================================================
    # CALCULATIONS
    # =========================================================================
    
    def _calculate_kama(self, prices: list) -> float:
        """Calculate KAMA value from price history."""
        if len(prices) < self.kama_period + 1:
            return prices[-1] if prices else 0.0
        
        # Efficiency Ratio
        change = abs(prices[-1] - prices[-self.kama_period])
        volatility = sum(
            abs(prices[-i] - prices[-i - 1])
            for i in range(1, self.kama_period + 1)
        )
        
        if volatility > 0:
            er = change / volatility
        else:
            er = 0.0
        
        # Smoothing constants
        fast_sc = 2 / (self.kama_fast + 1)
        slow_sc = 2 / (self.kama_slow + 1)
        sc = (er * (fast_sc - slow_sc) + slow_sc) ** 2
        
        # KAMA calculation (simplified - initialize with SMA)
        if not hasattr(self, '_kama_value') or self._kama_value is None:
            self._kama_value = sum(prices[-self.kama_period:]) / self.kama_period
        
        self._kama_value = self._kama_value + sc * (prices[-1] - self._kama_value)
        return self._kama_value
    
    def _calculate_ema(self, prices: list, period: int) -> float:
        """Calculate EMA from price history."""
        if len(prices) < period:
            return prices[-1] if prices else 0.0
        
        multiplier = 2 / (period + 1)
        ema = prices[-period]
        for price in prices[-period + 1:]:
            ema = (price - ema) * multiplier + ema
        return ema
    
    def _calculate_atr(self, df: pd.DataFrame) -> float:
        """Calculate ATR from DataFrame."""
        high = df["high"].values
        low = df["low"].values
        close = df["close"].values
        
        if len(close) < 2:
            return 0.0
        
        # True Range
        tr_values = []
        for i in range(1, min(len(close), self.atr_length + 1)):
            tr = max(
                high[-i] - low[-i],
                abs(high[-i] - close[-i - 1]),
                abs(low[-i] - close[-i - 1])
            )
            tr_values.append(tr)
        
        if not tr_values:
            return 0.0
        
        return sum(tr_values) / len(tr_values)
    
    def _calculate_roc(self, prices: list, period: int) -> float:
        """Calculate Rate of Change."""
        if len(prices) < period + 1:
            return 0.0
        return (prices[-1] - prices[-period - 1]) / prices[-period - 1]
    
    def _calculate_angle(self, current_val: float, previous_val: float, scale: float) -> float:
        """Calculate angle of slope in degrees."""
        try:
            rise = (current_val - previous_val) * scale
            return math.degrees(math.atan(rise))
        except (ValueError, ZeroDivisionError):
            return 0.0
    
    def _calculate_harmony(
        self, 
        primary_closes: list, 
        reference_closes: list
    ) -> Tuple[float, float, float, float, float]:
        """
        Calculate Harmony Score from ROC of both pairs.
        
        Returns: (harmony_scaled, roc_primary, roc_reference, roc_angle, harmony_angle)
        """
        max_period = max(self.roc_period_primary, self.roc_period_reference)
        if len(primary_closes) < max_period + 1 or len(reference_closes) < max_period + 1:
            return 0.0, 0.0, 0.0, 0.0, 0.0
        
        # Calculate ROCs
        roc_primary = self._calculate_roc(primary_closes, self.roc_period_primary)
        roc_reference = self._calculate_roc(reference_closes, self.roc_period_reference)
        
        # Harmony = ROC_primary × (-ROC_reference) × scale
        harmony_raw = roc_primary * (-roc_reference)
        harmony_scaled = harmony_raw * self.harmony_scale
        
        # Store for angle calculation
        self.roc_primary_history.append(roc_primary)
        self.harmony_history.append(harmony_scaled)
        
        # Keep limited history
        if len(self.roc_primary_history) > 5:
            self.roc_primary_history = self.roc_primary_history[-5:]
        if len(self.harmony_history) > 5:
            self.harmony_history = self.harmony_history[-5:]
        
        # Calculate angles using PLOT-SCALED values
        roc_angle = 0.0
        harmony_angle = 0.0
        
        if len(self.roc_primary_history) >= 2 and len(self.harmony_history) >= 2:
            roc_plot_current = self.roc_primary_history[-1] * self.plot_roc_multiplier
            roc_plot_previous = self.roc_primary_history[-2] * self.plot_roc_multiplier
            harmony_plot_current = self.harmony_history[-1] * self.plot_harmony_multiplier
            harmony_plot_previous = self.harmony_history[-2] * self.plot_harmony_multiplier
            
            roc_angle = self._calculate_angle(
                roc_plot_current, roc_plot_previous, self.roc_angle_scale
            )
            harmony_angle = self._calculate_angle(
                harmony_plot_current, harmony_plot_previous, self.harmony_angle_scale
            )
        
        return harmony_scaled, roc_primary, roc_reference, roc_angle, harmony_angle
    
    def _get_average_atr(self) -> float:
        """Get average ATR over configured period."""
        if not self.atr_history:
            return 0.0
        
        recent = self.atr_history[-self.atr_avg_period:] if len(self.atr_history) >= self.atr_avg_period else self.atr_history
        return sum(recent) / len(recent)
    
    # =========================================================================
    # SIGNAL CHECK
    # =========================================================================
    
    def check_signal(
        self, 
        df: pd.DataFrame, 
        reference_df: Optional[pd.DataFrame] = None
    ) -> Signal:
        """
        Check for trading signal.
        
        Args:
            df: Primary pair DataFrame with OHLCV data
            reference_df: Reference pair DataFrame (required for GEMINI)
            
        Returns:
            Signal object (valid=True if signal detected)
        """
        self.current_bar_index += 1
        
        # Require reference data
        if reference_df is None or reference_df.empty:
            return self._create_no_signal("No reference data available")
        
        if len(df) < 50 or len(reference_df) < 50:
            return self._create_no_signal("Insufficient data")
        
        # Get timestamps for analysis
        broker_time = df.index[-1] if hasattr(df.index[-1], 'hour') else pd.Timestamp(df.index[-1])
        utc_time = broker_to_utc(broker_time)
        
        # Get current values
        close = df["close"].iloc[-1]
        high = df["high"].iloc[-1]
        low = df["low"].iloc[-1]
        hl2 = (high + low) / 2
        
        # Update history
        self.primary_close_history.append(close)
        self.reference_close_history.append(reference_df["close"].iloc[-1])
        
        # Keep limited history
        max_history = 150
        if len(self.primary_close_history) > max_history:
            self.primary_close_history = self.primary_close_history[-max_history:]
            self.reference_close_history = self.reference_close_history[-max_history:]
        
        # Calculate ATR and store
        current_atr = self._calculate_atr(df)
        self.atr_history.append(current_atr)
        if len(self.atr_history) > 50:
            self.atr_history = self.atr_history[-50:]
        
        # Build HL2 history for KAMA/EMA
        hl2_history = []
        for i in range(min(len(df), 50)):
            h = df["high"].iloc[-(i+1)]
            l = df["low"].iloc[-(i+1)]
            hl2_history.insert(0, (h + l) / 2)
        
        # Calculate KAMA and HL2 EMA
        kama_value = self._calculate_kama(hl2_history)
        hl2_ema_value = self._calculate_ema(hl2_history, self.hl2_ema_period)
        
        # Current state check
        hl2_above_kama = hl2_ema_value > kama_value
        
        # Detect KAMA cross
        cross_detected = hl2_above_kama and not self.prev_hl2_above_kama
        self.prev_hl2_above_kama = hl2_above_kama
        
        # Calculate Harmony and angles
        harmony, roc_primary, roc_reference, roc_angle, harmony_angle = self._calculate_harmony(
            self.primary_close_history,
            self.reference_close_history
        )
        
        # State machine
        if self.state == GEMINIState.SCANNING:
            if cross_detected:
                self.cross_detected_bar = self.current_bar_index
                self.state = GEMINIState.CROSS_WINDOW
                self._log_state_transition(
                    "SCANNING", "CROSS_WINDOW",
                    f"Broker: {broker_time.strftime('%H:%M')}, UTC: {utc_time.strftime('%H:%M')} | "
                    f"HL2_EMA: {hl2_ema_value:.5f}, KAMA: {kama_value:.5f}"
                )
            else:
                return self._create_no_signal("No KAMA cross detected")
        
        # In CROSS_WINDOW state
        if self.state == GEMINIState.CROSS_WINDOW:
            bars_since_cross = self.current_bar_index - self.cross_detected_bar
            
            # Check if window expired
            max_window = max(self.allowed_cross_bars) if self.allowed_cross_bars else 20
            if bars_since_cross > max_window:
                self.state = GEMINIState.SCANNING
                self.cross_detected_bar = None
                return self._create_no_signal(f"Cross window expired after {bars_since_cross} bars")
            
            # Check if still above KAMA
            if not hl2_above_kama:
                self.state = GEMINIState.SCANNING
                self.cross_detected_bar = None
                return self._create_no_signal("HL2_EMA dropped below KAMA - cross invalidated")
            
            # Check if this bar is in allowed_cross_bars
            if self.allowed_cross_bars and bars_since_cross not in self.allowed_cross_bars:
                return self._create_no_signal(f"Bar {bars_since_cross} not in allowed_cross_bars {self.allowed_cross_bars}")
            
            # Check angle conditions
            roc_ok = self.entry_roc_angle_min <= abs(roc_angle) <= self.entry_roc_angle_max
            harmony_ok = self.entry_harmony_angle_min <= abs(harmony_angle) <= self.entry_harmony_angle_max
            
            if not roc_ok:
                return self._create_no_signal(
                    f"ROC angle {roc_angle:.1f} not in [{self.entry_roc_angle_min}-{self.entry_roc_angle_max}]"
                )
            
            if not harmony_ok:
                return self._create_no_signal(
                    f"Harmony angle {harmony_angle:.1f} not in [{self.entry_harmony_angle_min}-{self.entry_harmony_angle_max}]"
                )
            
            # Check direction (ROC primary should be positive for LONG)
            if roc_primary <= 0:
                return self._create_no_signal(f"ROC primary negative: {roc_primary:.6f}")
            
            # Day filter
            if self.params.get("use_day_filter"):
                allowed_days = self.params.get("allowed_days", [])
                day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
                current_day = utc_time.weekday()
                if current_day not in allowed_days:
                    return self._create_no_signal(
                        f"Day filter: {day_names[current_day]} not in {[day_names[d] for d in allowed_days]}"
                    )
            
            # Time filter
            if self.params.get("use_time_filter"):
                allowed_hours = self.params.get("allowed_hours", [])
                if allowed_hours and utc_time.hour not in allowed_hours:
                    return self._create_no_signal(
                        f"Time filter: UTC {utc_time.hour}h not in {allowed_hours}"
                    )
            
            # Calculate entry/SL/TP
            entry_price = close
            avg_atr = self._get_average_atr()
            
            if avg_atr <= 0:
                return self._create_no_signal("ATR is zero or negative")
            
            # ATR filter
            if self.params.get("use_atr_filter"):
                atr_min = self.params.get("atr_min", 0)
                atr_max = self.params.get("atr_max", 1)
                if not (atr_min <= avg_atr <= atr_max):
                    return self._create_no_signal(
                        f"ATR filter: {avg_atr:.6f} not in [{atr_min}-{atr_max}]"
                    )
            
            stop_loss = entry_price - (avg_atr * self.atr_sl_mult)
            take_profit = entry_price + (avg_atr * self.atr_tp_mult)
            
            # SL pips filter
            sl_pips = abs(entry_price - stop_loss) / self.pip_value
            if self.params.get("use_sl_pips_filter"):
                sl_min = self.params.get("sl_pips_min", 5)
                sl_max = self.params.get("sl_pips_max", 50)
                if not (sl_min <= sl_pips <= sl_max):
                    return self._create_no_signal(
                        f"SL pips filter: {sl_pips:.1f} not in [{sl_min}-{sl_max}]"
                    )
            
            # All conditions met - generate signal
            self.state = GEMINIState.SCANNING
            self.cross_detected_bar = None
            
            # Log entry details for analysis
            self.logger.info(
                f"[{self.config_name}] ENTRY SIGNAL | "
                f"cross_bars={bars_since_cross} | "
                f"roc_angle={roc_angle:.1f} | "
                f"harmony_angle={harmony_angle:.1f} | "
                f"harmony={harmony:.2f} | "
                f"roc_primary={roc_primary:.6f} | "
                f"roc_reference={roc_reference:.6f} | "
                f"atr={avg_atr:.6f} | "
                f"sl_pips={sl_pips:.1f}"
            )
            
            return self._create_signal(
                direction=SignalDirection.LONG,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                atr=avg_atr,
                reason=f"KAMA cross confirmed | cross_bars={bars_since_cross} | roc_angle={roc_angle:.1f} | harmony_angle={harmony_angle:.1f}"
            )
        
        return self._create_no_signal("Unknown state")
