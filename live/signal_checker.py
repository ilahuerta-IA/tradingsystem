"""
Signal Checker for Live Trading.

Single Responsibility: Detect trading signals using lib/filters.
Does NOT execute trades - only determines if signal conditions are met.

Reuses the SAME filters from backtesting:
- lib/filters.py (ATR, angle, time, SL pips)
- Strategy parameters from config/settings.py

This ensures live trading uses IDENTICAL logic to backtesting.

Usage:
    checker = SignalChecker(config_name='EURUSD_PRO')
    signal = checker.check_signal(df)
    
    if signal.valid:
        print(f"Signal: {signal.direction} at {signal.entry_price}")
"""

import math
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

import pandas as pd
import numpy as np

# Import SAME filters used in backtesting
import sys
from pathlib import Path

# Add project root to path for lib imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from lib.filters import (
    check_time_filter,
    check_atr_filter,
    check_angle_filter,
    check_sl_pips_filter,
    check_ema_price_filter,
)
from config.settings import STRATEGIES_CONFIG


class SignalDirection(Enum):
    """Signal direction."""
    LONG = "LONG"
    SHORT = "SHORT"
    NONE = "NONE"


class EntryState(Enum):
    """State machine states (matching backtest)."""
    SCANNING = "SCANNING"
    ARMED_LONG = "ARMED_LONG"
    ARMED_SHORT = "ARMED_SHORT"
    WINDOW_OPEN = "WINDOW_OPEN"


@dataclass
class Signal:
    """Trading signal container."""
    valid: bool
    direction: SignalDirection
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    atr: Optional[float] = None
    angle: Optional[float] = None
    reason: str = ""
    timestamp: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            'valid': self.valid,
            'direction': self.direction.value,
            'entry_price': self.entry_price,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'atr': self.atr,
            'angle': self.angle,
            'reason': self.reason,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }


class SignalChecker:
    """
    Checks for trading signals using backtest-identical logic.
    
    Implements the 4-phase state machine:
    1. SCANNING - Looking for EMA crossover
    2. ARMED_LONG - Waiting for pullback (bearish candles)
    3. WINDOW_OPEN - Monitoring for breakout
    4. Signal generated on successful breakout
    
    All filter logic is imported from lib/filters.py to ensure
    live trading behaves EXACTLY like backtesting.
    
    Example:
        checker = SignalChecker('EURUSD_PRO')
        
        # On each M5 candle close:
        signal = checker.check_signal(df)
        
        if signal.valid:
            # Execute trade
            pass
    """
    
    def __init__(
        self,
        config_name: str,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize signal checker.
        
        Args:
            config_name: Configuration key from STRATEGIES_CONFIG
            logger: Optional logger instance
        """
        self.config_name = config_name
        self.logger = logger or logging.getLogger(__name__)
        
        # Load configuration
        if config_name not in STRATEGIES_CONFIG:
            raise ValueError(f"Configuration not found: {config_name}")
        
        self.config = STRATEGIES_CONFIG[config_name]
        self.params = self.config['params']
        
        # State machine
        self.state = EntryState.SCANNING
        self.pullback_count = 0
        self.pullback_high: Optional[float] = None
        self.pullback_low: Optional[float] = None
        self.window_top: Optional[float] = None
        self.window_bottom: Optional[float] = None
        self.window_expiry_bar: Optional[int] = None
        self.current_bar_index = 0
        
        # Signal tracking
        self.signal_atr: Optional[float] = None
        
        self.logger.info(f"SignalChecker initialized for {config_name}")
    
    def reset_state(self) -> None:
        """Reset state machine to SCANNING."""
        self.state = EntryState.SCANNING
        self.pullback_count = 0
        self.pullback_high = None
        self.pullback_low = None
        self.window_top = None
        self.window_bottom = None
        self.window_expiry_bar = None
        self.signal_atr = None
    
    def _calculate_emas(self, df: pd.DataFrame) -> Dict[str, pd.Series]:
        """
        Calculate EMAs from DataFrame.
        
        Args:
            df: DataFrame with 'close' column
            
        Returns:
            Dictionary of EMA series
        """
        close = df['close']
        
        return {
            'fast': close.ewm(span=self.params['ema_fast_length'], adjust=False).mean(),
            'medium': close.ewm(span=self.params['ema_medium_length'], adjust=False).mean(),
            'slow': close.ewm(span=self.params['ema_slow_length'], adjust=False).mean(),
            'confirm': close.ewm(span=self.params['ema_confirm_length'], adjust=False).mean(),
            'filter': close.ewm(span=self.params['ema_filter_price_length'], adjust=False).mean(),
        }
    
    def _calculate_atr(self, df: pd.DataFrame) -> pd.Series:
        """
        Calculate ATR from DataFrame.
        
        Args:
            df: DataFrame with high, low, close columns
            
        Returns:
            ATR series
        """
        high = df['high']
        low = df['low']
        close = df['close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=self.params['atr_length']).mean()
        
        return atr
    
    def _calculate_angle(self, ema_confirm: pd.Series) -> float:
        """
        Calculate EMA angle in degrees (matching backtest).
        
        Args:
            ema_confirm: Confirmation EMA series
            
        Returns:
            Angle in degrees
        """
        try:
            current = float(ema_confirm.iloc[-1])
            previous = float(ema_confirm.iloc[-2])
            scale = self.params.get('angle_scale', 100.0)
            
            rise = (current - previous) * scale
            return math.degrees(math.atan(rise))
        except (IndexError, ValueError):
            return 0.0
    
    def _check_crossover(self, emas: Dict[str, pd.Series]) -> bool:
        """
        Check for bullish EMA crossover.
        
        Confirm EMA crosses above any of fast/medium/slow.
        
        Args:
            emas: Dictionary of EMA series
            
        Returns:
            True if crossover detected
        """
        confirm = emas['confirm']
        
        # Need at least 2 bars
        if len(confirm) < 2:
            return False
        
        for ema_name in ['fast', 'medium', 'slow']:
            other = emas[ema_name]
            
            # Crossover: current above, previous below or equal
            curr_above = float(confirm.iloc[-1]) > float(other.iloc[-1])
            prev_below = float(confirm.iloc[-2]) <= float(other.iloc[-2])
            
            if curr_above and prev_below:
                return True
        
        return False
    
    def _check_bearish_candle(self, df: pd.DataFrame) -> bool:
        """Check if last candle is bearish (for pullback)."""
        return float(df['close'].iloc[-1]) < float(df['open'].iloc[-1])
    
    def check_signal(self, df: pd.DataFrame) -> Signal:
        """
        Check for trading signal using 4-phase state machine.
        
        Args:
            df: DataFrame with OHLCV data (at least 150 bars)
            
        Returns:
            Signal object (valid=True if signal detected)
        """
        self.current_bar_index += 1
        now = datetime.now()
        
        # Validate data
        if df is None or len(df) < self.params.get('ema_filter_price_length', 70):
            return Signal(
                valid=False,
                direction=SignalDirection.NONE,
                reason="Insufficient data",
                timestamp=now
            )
        
        # Calculate indicators
        emas = self._calculate_emas(df)
        atr_series = self._calculate_atr(df)
        
        current_atr = float(atr_series.iloc[-1])
        current_close = float(df['close'].iloc[-1])
        current_high = float(df['high'].iloc[-1])
        current_low = float(df['low'].iloc[-1])
        current_angle = self._calculate_angle(emas['confirm'])
        ema_filter_value = float(emas['filter'].iloc[-1])
        
        # Get current time from data or system
        if 'time' in df.columns:
            current_dt = df['time'].iloc[-1]
            if isinstance(current_dt, pd.Timestamp):
                current_dt = current_dt.to_pydatetime()
        else:
            current_dt = now
        
        # ========================================
        # STATE MACHINE (identical to backtest)
        # ========================================
        
        # --- SCANNING STATE ---
        if self.state == EntryState.SCANNING:
            
            # Check for EMA crossover
            if not self._check_crossover(emas):
                return Signal(
                    valid=False,
                    direction=SignalDirection.NONE,
                    reason="No crossover",
                    timestamp=now
                )
            
            # Check price filter: close > EMA filter
            if not check_ema_price_filter(current_close, ema_filter_value):
                return Signal(
                    valid=False,
                    direction=SignalDirection.NONE,
                    reason=f"Price filter failed: {current_close:.5f} <= EMA({ema_filter_value:.5f})",
                    timestamp=now
                )
            
            # Check ATR filter
            if not check_atr_filter(
                current_atr,
                self.params['atr_min'],
                self.params['atr_max']
            ):
                return Signal(
                    valid=False,
                    direction=SignalDirection.NONE,
                    reason=f"ATR filter failed: {current_atr:.6f} not in [{self.params['atr_min']}-{self.params['atr_max']}]",
                    timestamp=now
                )
            
            # Check angle filter (if enabled)
            if self.params.get('use_angle_filter', False):
                if not check_angle_filter(
                    current_angle,
                    self.params['angle_min'],
                    self.params['angle_max']
                ):
                    return Signal(
                        valid=False,
                        direction=SignalDirection.NONE,
                        reason=f"Angle filter failed: {current_angle:.1f} not in [{self.params['angle_min']}-{self.params['angle_max']}]",
                        timestamp=now
                    )
            
            # All filters passed - transition to ARMED
            self.state = EntryState.ARMED_LONG
            self.pullback_count = 0
            self.signal_atr = current_atr
            
            self.logger.info(f"SCANNING -> ARMED_LONG | ATR: {current_atr:.6f}, Angle: {current_angle:.1f}")
            
            return Signal(
                valid=False,
                direction=SignalDirection.NONE,
                reason="Armed - waiting for pullback",
                timestamp=now
            )
        
        # --- ARMED_LONG STATE ---
        elif self.state == EntryState.ARMED_LONG:
            
            # Check for bearish pullback candle
            if self._check_bearish_candle(df):
                self.pullback_count += 1
                
                # Check if pullback complete
                if self.pullback_count >= self.params['pullback_candles']:
                    # Store pullback levels
                    self.pullback_high = current_high
                    self.pullback_low = current_low
                    
                    # Calculate window levels
                    candle_range = self.pullback_high - self.pullback_low
                    offset = candle_range * self.params.get('price_offset_mult', 0.01)
                    
                    self.window_top = self.pullback_high + offset
                    self.window_bottom = self.pullback_low - offset
                    self.window_expiry_bar = self.current_bar_index + self.params['window_periods']
                    
                    # Transition to WINDOW_OPEN
                    self.state = EntryState.WINDOW_OPEN
                    
                    self.logger.info(
                        f"ARMED -> WINDOW_OPEN | "
                        f"Pullbacks: {self.pullback_count}, "
                        f"Breakout level: {self.window_top:.5f}"
                    )
                
                return Signal(
                    valid=False,
                    direction=SignalDirection.NONE,
                    reason=f"Pullback {self.pullback_count}/{self.params['pullback_candles']}",
                    timestamp=now
                )
            else:
                # Non-pullback candle invalidates
                self.reset_state()
                return Signal(
                    valid=False,
                    direction=SignalDirection.NONE,
                    reason="Pullback invalidated (bullish candle)",
                    timestamp=now
                )
        
        # --- WINDOW_OPEN STATE ---
        elif self.state == EntryState.WINDOW_OPEN:
            
            # Check window expiry
            if self.current_bar_index > self.window_expiry_bar:
                self.logger.info("Window expired - back to ARMED")
                self.state = EntryState.ARMED_LONG
                self.pullback_count = 0
                return Signal(
                    valid=False,
                    direction=SignalDirection.NONE,
                    reason="Window expired",
                    timestamp=now
                )
            
            # Check for downside failure (instability)
            if current_low <= self.window_bottom:
                self.logger.info("Window broken downside - back to ARMED")
                self.state = EntryState.ARMED_LONG
                self.pullback_count = 0
                return Signal(
                    valid=False,
                    direction=SignalDirection.NONE,
                    reason="Window broken downside",
                    timestamp=now
                )
            
            # Check for upside breakout (SUCCESS!)
            if current_high >= self.window_top:
                
                # Time filter at entry (if enabled)
                if self.params.get('use_time_filter', False):
                    allowed_hours = self.params.get('allowed_hours', [])
                    if not check_time_filter(current_dt, allowed_hours, True):
                        self.logger.info(f"Time filter blocked: hour {current_dt.hour} not in {allowed_hours}")
                        return Signal(
                            valid=False,
                            direction=SignalDirection.NONE,
                            reason=f"Time filter: {current_dt.hour}h not allowed",
                            timestamp=now
                        )
                
                # Calculate SL/TP
                entry_price = self.window_top
                entry_bar_low = current_low
                entry_bar_high = current_high
                
                stop_loss = entry_bar_low - (current_atr * self.params['sl_mult'])
                take_profit = entry_bar_high + (current_atr * self.params['tp_mult'])
                
                # Create valid signal
                signal = Signal(
                    valid=True,
                    direction=SignalDirection.LONG,
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    atr=current_atr,
                    angle=current_angle,
                    reason="Breakout confirmed",
                    timestamp=now
                )
                
                self.logger.info(
                    f"SIGNAL LONG | Entry: {entry_price:.5f}, "
                    f"SL: {stop_loss:.5f}, TP: {take_profit:.5f}"
                )
                
                # Reset state after signal
                self.reset_state()
                
                return signal
            
            # Still in window, no breakout yet
            return Signal(
                valid=False,
                direction=SignalDirection.NONE,
                reason=f"Waiting for breakout above {self.window_top:.5f}",
                timestamp=now
            )
        
        # Fallback
        return Signal(
            valid=False,
            direction=SignalDirection.NONE,
            reason="Unknown state",
            timestamp=now
        )
    
    def get_state_info(self) -> Dict[str, Any]:
        """Get current state machine info for logging."""
        return {
            'state': self.state.value,
            'pullback_count': self.pullback_count,
            'window_top': self.window_top,
            'window_bottom': self.window_bottom,
            'current_bar': self.current_bar_index,
            'window_expiry': self.window_expiry_bar,
        }


# Test function
def test_signal_checker():
    """Test signal checker with mock data."""
    logging.basicConfig(level=logging.INFO)
    
    # Create mock data
    np.random.seed(42)
    n = 150
    
    # Simulate uptrending price
    base_price = 1.1000
    trend = np.linspace(0, 0.01, n)
    noise = np.random.normal(0, 0.0005, n)
    
    close = base_price + trend + noise
    high = close + np.random.uniform(0.0002, 0.001, n)
    low = close - np.random.uniform(0.0002, 0.001, n)
    open_price = np.roll(close, 1)
    open_price[0] = base_price
    
    df = pd.DataFrame({
        'time': pd.date_range(start='2025-01-10 00:00', periods=n, freq='5T'),
        'open': open_price,
        'high': high,
        'low': low,
        'close': close,
        'volume': np.random.randint(100, 1000, n)
    })
    
    # Test checker
    checker = SignalChecker('EURUSD_PRO')
    
    print("\nTesting SignalChecker with mock data...")
    print(f"Data range: {df['time'].iloc[0]} to {df['time'].iloc[-1]}")
    
    # Check signal
    signal = checker.check_signal(df)
    
    print(f"\nSignal result:")
    print(f"  Valid: {signal.valid}")
    print(f"  Direction: {signal.direction.value}")
    print(f"  Reason: {signal.reason}")
    print(f"  State: {checker.state.value}")
    
    return True


if __name__ == "__main__":
    test_signal_checker()
