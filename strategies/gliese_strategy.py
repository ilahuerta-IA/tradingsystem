"""
GLIESE Strategy - HTF Range Detection + Mean Reversion + Pullback Entry

Complementary to SEDNA for assets where trend-following doesn't work well:
- USDCHF, USDCAD, EURUSD

DESIGN PHILOSOPHY:
- While SEDNA looks for TRENDING markets (high ER), GLIESE looks for RANGING markets
- Entry on bounce from range extremes back to fair value (KAMA)

ENTRY SYSTEM (4 PHASES):
1. RANGE DETECTION (HTF 15m):
   - ER < threshold (low directional momentum)
   - ADXR < threshold (no trend strength)
   - KAMA slope < k * ATR (flat center line)

2. EXTENSION BELOW:
   - Price crosses below lower band (KAMA - band_mult * ATR)
   - Must stay below for minimum bars (filter false touches)

3. REVERSAL CONFIRMED:
   - Price crosses back ABOVE lower band
   - Confirms range held and extension is reversing

4. PULLBACK + BREAKOUT:
   - Wait for pullback consolidation
   - Enter on breakout above micro-swing high

EXIT SYSTEM:
- Stop Loss: Entry - (ATR * SL multiplier)
- Take Profit: Entry + (ATR * TP multiplier)
"""
from __future__ import annotations
import math
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from enum import Enum

import backtrader as bt
import numpy as np

from lib.filters import (
    check_time_filter,
    check_day_filter,
    check_atr_filter,
    check_sl_pips_filter,
    calculate_efficiency_ratio,
    calculate_adxr,
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
from lib.indicators import EfficiencyRatio
from lib.position_sizing import calculate_position_size


class GLIESEState(Enum):
    """GLIESE state machine states."""
    SCANNING = "SCANNING"
    RANGE_DETECTED = "RANGE_DETECTED"
    EXTENSION_BELOW = "EXTENSION_BELOW"
    REVERSAL_DETECTED = "REVERSAL_DETECTED"
    WAITING_PULLBACK = "WAITING_PULLBACK"
    WAITING_BREAKOUT = "WAITING_BREAKOUT"


class KAMA(bt.Indicator):
    """
    Kaufman's Adaptive Moving Average (KAMA).
    
    Uses efficiency ratio to adapt between fast and slow smoothing constants.
    """
    lines = ('kama',)
    params = (
        ('period', 10),
        ('fast', 2),
        ('slow', 30),
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


class BandLines(bt.Indicator):
    """
    Upper and Lower bands around center line (KAMA).
    
    Bands = KAMA +/- (band_mult * ATR)
    """
    lines = ('upper', 'lower')
    params = (
        ('band_mult', 1.5),
    )
    
    plotinfo = dict(
        subplot=False,
        plotlinelabels=True,
    )
    plotlines = dict(
        upper=dict(color='gray', linestyle='--', linewidth=1.0),
        lower=dict(color='gray', linestyle='--', linewidth=1.0),
    )
    
    def __init__(self):
        self.kama = self.data0  # KAMA values
        self.atr = self.data1   # ATR values
    
    def next(self):
        kama_val = float(self.kama[0])
        atr_val = float(self.atr[0])
        band_dist = self.p.band_mult * atr_val
        self.lines.upper[0] = kama_val + band_dist
        self.lines.lower[0] = kama_val - band_dist


class EntryExitLines(bt.Indicator):
    """
    Indicator to plot entry/exit price levels as horizontal dashed lines.
    """
    lines = ('entry', 'stop_loss', 'take_profit')
    
    plotinfo = dict(
        subplot=False,
        plotlinelabels=True,
    )
    plotlines = dict(
        entry=dict(color='green', linestyle='--', linewidth=1.0),
        stop_loss=dict(color='red', linestyle='--', linewidth=1.0),
        take_profit=dict(color='blue', linestyle='--', linewidth=1.0),
    )
    
    def __init__(self):
        pass
    
    def next(self):
        pass


class GLIESEStrategy(bt.Strategy):
    """
    GLIESE Strategy - Mean Reversion in Ranging Markets.
    
    Complementary to SEDNA:
    - SEDNA: Trend-following (ER HIGH = good)
    - GLIESE: Mean-reversion (ER LOW = good)
    """
    
    params = dict(
        # KAMA settings (center line)
        kama_period=10,
        kama_fast=2,
        kama_slow=30,
        
        # Band settings
        band_atr_period=14,
        band_atr_mult=1.5,
        
        # ATR for SL/TP
        atr_length=14,
        atr_sl_multiplier=2.0,
        atr_tp_multiplier=3.0,
        
        # Breakout Window (after pullback)
        use_breakout_window=True,
        breakout_window_candles=5,
        breakout_level_offset_pips=2.0,
        
        # === RANGE DETECTION (HTF 15m) ===
        
        # Efficiency Ratio - LOW for ranging
        use_htf_range_filter=True,
        htf_timeframe_minutes=15,
        htf_er_period=10,
        htf_er_max_threshold=0.30,  # ER < 0.30 = ranging (inverted vs SEDNA)
        
        # ADXR - LOW for ranging
        use_adxr_filter=True,
        adxr_period=14,
        adxr_lookback=14,
        adxr_max_threshold=25.0,  # ADXR < 25 = no trend
        
        # KAMA Slope - FLAT for ranging
        use_kama_slope_filter=True,
        kama_slope_lookback=5,
        kama_slope_atr_mult=0.3,  # slope < 0.3 * ATR = flat
        
        # === EXTENSION DETECTION ===
        extension_min_bars=2,  # Min bars below band to validate
        extension_max_bars=20,  # Max bars (cancel if exceeded)
        
        # Z-Score filter (optional)
        use_zscore_filter=False,
        zscore_min_depth=-2.0,  # Min Z-Score to validate entry
        
        # === PULLBACK DETECTION ===
        use_pullback_filter=True,
        pullback_min_bars=1,
        pullback_max_bars=4,
        
        # === CANCELLATION ===
        er_cancel_threshold=0.50,  # Cancel if ER exceeds (trend starting)
        
        # === STANDARD FILTERS ===
        
        # Time Filter
        use_time_filter=False,
        allowed_hours=[],
        
        # Day Filter (0=Monday, 6=Sunday)
        use_day_filter=False,
        allowed_days=[0, 1, 2, 3, 4],
        
        # SL Pips Filter
        use_sl_pips_filter=False,
        sl_pips_min=5.0,
        sl_pips_max=20.0,
        
        # ATR Filter
        use_atr_filter=False,
        atr_min=0.0,
        atr_max=1.0,
        atr_avg_period=20,
        
        # === ASSET CONFIG ===
        pip_value=0.0001,
        is_jpy_pair=False,
        jpy_rate=150.0,
        lot_size=100000,
        is_etf=False,
        margin_pct=3.33,
        
        # Risk
        risk_percent=0.01,
        
        # Debug & Reporting
        print_signals=False,
        export_reports=True,
        
        # Plot options
        plot_entry_exit_lines=True,
        plot_bands=True,
    )

    def __init__(self):
        d = self.data
        
        # HL2 = (High + Low) / 2
        self.hl2 = (d.high + d.low) / 2.0
        
        # KAMA on HL2 (center line)
        self.kama = KAMA(
            self.hl2,
            period=self.p.kama_period,
            fast=self.p.kama_fast,
            slow=self.p.kama_slow
        )
        
        # ATR
        self.atr = bt.ind.ATR(d, period=self.p.atr_length)
        
        # Bands (KAMA +/- band_mult * ATR)
        if self.p.plot_bands:
            self.bands = BandLines(self.kama, self.atr, band_mult=self.p.band_atr_mult)
        
        # HTF Efficiency Ratio (scaled period to simulate higher timeframe)
        self.htf_er = None
        if self.p.use_htf_range_filter:
            base_tf_minutes = 5
            htf_multiplier = self.p.htf_timeframe_minutes // base_tf_minutes
            self.scaled_er_period = self.p.htf_er_period * htf_multiplier
            self.htf_er = EfficiencyRatio(d.close, period=self.scaled_er_period)
            self.htf_er.plotinfo.plotname = f'ER({self.p.htf_timeframe_minutes}m equiv)'
        else:
            self.scaled_er_period = self.p.htf_er_period * 3
        
        # Entry/Exit plot lines
        if self.p.plot_entry_exit_lines:
            self.entry_exit_lines = EntryExitLines(d)
        else:
            self.entry_exit_lines = None
        
        # Orders
        self.order = None
        self.stop_order = None
        self.limit_order = None
        
        # Levels
        self.stop_level = None
        self.take_level = None
        self.last_entry_price = None
        self.last_entry_bar = None
        self.last_exit_reason = None
        
        # State machine
        self.state = GLIESEState.SCANNING
        self.pattern_detected_bar = None
        self.breakout_level = None
        self.pattern_atr = None
        
        # Extension tracking
        self.extension_bar_count = 0
        self.extension_start_bar = None
        self.extension_min_price = float('inf')
        
        # Price history
        self.price_history = {
            'highs': [],
            'lows': [],
            'closes': [],
            'kama': []
        }
        self.kama_history = []
        self.atr_history = []
        self.pullback_data = None
        
        # Stats
        self.trades = 0
        self.wins = 0
        self.losses = 0
        self.gross_profit = 0.0
        self.gross_loss = 0.0
        self._portfolio_values = []
        self._trade_pnls = []
        self._starting_cash = self.broker.get_cash()
        
        # Trade reporting
        self.trade_reports = []
        self.trade_report_file = None
        self._init_trade_reporting()

    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _get_datetime(self, offset=0) -> datetime:
        """Get correct datetime combining date and time."""
        try:
            dt_date = self.data.datetime.date(offset)
            dt_time = self.data.datetime.time(offset)
            return datetime.combine(dt_date, dt_time)
        except Exception:
            return self.data.datetime.datetime(offset)
    
    def _get_average_atr(self) -> float:
        """Get average ATR over the specified period."""
        if len(self.atr_history) < self.p.atr_avg_period:
            return float(self.atr[0]) if not math.isnan(float(self.atr[0])) else 0
        
        recent_atr = self.atr_history[-self.p.atr_avg_period:]
        return sum(recent_atr) / len(recent_atr)
    
    def _calculate_bands(self) -> tuple:
        """Calculate upper and lower bands."""
        kama_val = float(self.kama[0])
        atr_val = float(self.atr[0])
        return calculate_bands(kama_val, atr_val, self.p.band_atr_mult)
    
    def _calculate_zscore(self) -> float:
        """Calculate current Z-Score (distance from KAMA in ATR units)."""
        try:
            close = float(self.data.close[0])
            kama_val = float(self.kama[0])
            atr_val = float(self.atr[0])
            
            if atr_val > 0:
                return (close - kama_val) / atr_val
            return 0.0
        except:
            return 0.0

    # =========================================================================
    # RANGE DETECTION CONDITIONS (HTF)
    # =========================================================================
    
    def _check_range_conditions(self) -> tuple:
        """
        Check if market is in ranging state (all three conditions).
        
        Returns: (passed: bool, details: dict, reason: str)
        """
        details = {}
        
        # 1. Efficiency Ratio LOW (no directional momentum)
        if self.p.use_htf_range_filter:
            close_prices = [float(self.data.close[-i]) for i in range(self.scaled_er_period + 1)]
            close_prices.reverse()
            er_value = calculate_efficiency_ratio(close_prices, self.scaled_er_period)
            details['er'] = er_value
            
            if not check_efficiency_ratio_range_filter(
                er_value, self.p.htf_er_max_threshold, True
            ):
                return False, details, f"ER {er_value:.3f} >= {self.p.htf_er_max_threshold} (trending)"
        
        # 2. ADXR LOW (no trend strength)
        if self.p.use_adxr_filter:
            required_bars = (self.p.adxr_period * 2) + self.p.adxr_lookback + 5
            if len(self.data) >= required_bars:
                highs = [float(self.data.high[-i]) for i in range(required_bars)]
                lows = [float(self.data.low[-i]) for i in range(required_bars)]
                closes = [float(self.data.close[-i]) for i in range(required_bars)]
                highs.reverse()
                lows.reverse()
                closes.reverse()
                
                adxr_value = calculate_adxr(
                    highs, lows, closes,
                    self.p.adxr_period, self.p.adxr_lookback
                )
                details['adxr'] = adxr_value
                
                if not check_adxr_filter(adxr_value, self.p.adxr_max_threshold, True):
                    return False, details, f"ADXR {adxr_value:.2f} >= {self.p.adxr_max_threshold} (trending)"
        
        # 3. KAMA Slope FLAT (relative to ATR)
        if self.p.use_kama_slope_filter:
            if len(self.kama_history) >= self.p.kama_slope_lookback + 1:
                kama_slope = calculate_kama_slope(
                    self.kama_history, self.p.kama_slope_lookback
                )
                atr_val = float(self.atr[0])
                details['kama_slope'] = kama_slope
                details['slope_threshold'] = self.p.kama_slope_atr_mult * atr_val
                
                if not check_kama_slope_filter(
                    kama_slope, atr_val, self.p.kama_slope_atr_mult, True
                ):
                    return False, details, f"KAMA slope {kama_slope:.6f} >= threshold (trending)"
        
        return True, details, "Range confirmed"
    
    def _check_er_cancel(self) -> bool:
        """Check if ER has risen above cancel threshold (trend starting)."""
        if not self.p.use_htf_range_filter:
            return False
        
        try:
            close_prices = [float(self.data.close[-i]) for i in range(self.scaled_er_period + 1)]
            close_prices.reverse()
            er_value = calculate_efficiency_ratio(close_prices, self.scaled_er_period)
            
            return er_value > self.p.er_cancel_threshold
        except:
            return False

    # =========================================================================
    # EXTENSION AND REVERSAL DETECTION
    # =========================================================================
    
    def _check_extension_below(self) -> bool:
        """Check if price is below lower band."""
        try:
            current_close = float(self.data.close[0])
            _, lower_band = self._calculate_bands()
            return check_extension_below_band(current_close, lower_band)
        except:
            return False
    
    def _check_reversal_above(self) -> bool:
        """Check if price has reversed back above lower band."""
        try:
            current_close = float(self.data.close[0])
            _, lower_band = self._calculate_bands()
            return check_reversal_above_band(current_close, lower_band)
        except:
            return False
    
    def _check_zscore_depth(self) -> bool:
        """Check if Z-Score reached minimum depth (optional filter)."""
        if not self.p.use_zscore_filter:
            return True
        
        zscore = self._calculate_zscore()
        return zscore <= self.p.zscore_min_depth

    # =========================================================================
    # PULLBACK DETECTION
    # =========================================================================
    
    def _check_pullback_condition(self) -> bool:
        """Check pullback condition using standard reusable filter."""
        if not self.p.use_pullback_filter:
            return True
        
        required_len = self.p.pullback_max_bars + 2
        if len(self.price_history['highs']) < required_len:
            return False
        
        result = detect_pullback(
            highs=self.price_history['highs'],
            lows=self.price_history['lows'],
            closes=self.price_history['closes'],
            kama_values=self.price_history['kama'],
            min_bars=self.p.pullback_min_bars,
            max_bars=self.p.pullback_max_bars,
            enabled=True
        )
        
        if result['valid']:
            self.pullback_data = result
            return True
        
        return False

    # =========================================================================
    # STATE MACHINE
    # =========================================================================
    
    def _reset_state(self):
        """Reset state machine to SCANNING."""
        self.state = GLIESEState.SCANNING
        self.pattern_detected_bar = None
        self.breakout_level = None
        self.pattern_atr = None
        self.extension_bar_count = 0
        self.extension_start_bar = None
        self.extension_min_price = float('inf')
        self.pullback_data = None
    
    def _update_price_history(self):
        """Update price history for pullback detection."""
        try:
            current_high = float(self.data.high[0])
            current_low = float(self.data.low[0])
            current_close = float(self.data.close[0])
            current_kama = float(self.kama[0])
            current_atr = float(self.atr[0])
            
            self.price_history['highs'].append(current_high)
            self.price_history['lows'].append(current_low)
            self.price_history['closes'].append(current_close)
            self.price_history['kama'].append(current_kama)
            
            self.kama_history.append(current_kama)
            self.atr_history.append(current_atr)
            
            # Keep only what we need
            max_len = max(self.p.pullback_max_bars + 10, self.p.kama_slope_lookback + 5)
            for key in self.price_history:
                if len(self.price_history[key]) > max_len:
                    self.price_history[key] = self.price_history[key][-max_len:]
            
            if len(self.kama_history) > max_len:
                self.kama_history = self.kama_history[-max_len:]
            if len(self.atr_history) > self.p.atr_avg_period + 5:
                self.atr_history = self.atr_history[-(self.p.atr_avg_period + 5):]
        except:
            pass
    
    def _process_state_machine(self, dt: datetime) -> bool:
        """
        Process the 4-phase state machine.
        
        Returns True if entry signal generated.
        """
        current_bar = len(self)
        current_high = float(self.data.high[0])
        current_low = float(self.data.low[0])
        
        # =====================================================================
        # STATE: SCANNING - Looking for range conditions
        # =====================================================================
        if self.state == GLIESEState.SCANNING:
            range_ok, details, reason = self._check_range_conditions()
            
            if range_ok:
                self.state = GLIESEState.RANGE_DETECTED
                if self.p.print_signals:
                    print(f"[{dt:%Y-%m-%d %H:%M}] GLIESE: RANGE DETECTED | {details}")
            
            return False
        
        # =====================================================================
        # STATE: RANGE_DETECTED - Looking for extension below band
        # =====================================================================
        elif self.state == GLIESEState.RANGE_DETECTED:
            # Check if range still valid
            if self._check_er_cancel():
                if self.p.print_signals:
                    print(f"[{dt:%Y-%m-%d %H:%M}] GLIESE: Range cancelled (ER surge)")
                self._reset_state()
                return False
            
            # Check for extension below lower band
            if self._check_extension_below():
                self.state = GLIESEState.EXTENSION_BELOW
                self.extension_start_bar = current_bar
                self.extension_bar_count = 1
                self.extension_min_price = current_low
                if self.p.print_signals:
                    _, lower = self._calculate_bands()
                    print(f"[{dt:%Y-%m-%d %H:%M}] GLIESE: EXTENSION BELOW | "
                          f"Close={float(self.data.close[0]):.5f} < LowerBand={lower:.5f}")
            
            return False
        
        # =====================================================================
        # STATE: EXTENSION_BELOW - Tracking extension, waiting for reversal
        # =====================================================================
        elif self.state == GLIESEState.EXTENSION_BELOW:
            # Check for cancellation
            if self._check_er_cancel():
                if self.p.print_signals:
                    print(f"[{dt:%Y-%m-%d %H:%M}] GLIESE: Extension cancelled (ER surge)")
                self._reset_state()
                return False
            
            # Track extension
            self.extension_bar_count += 1
            self.extension_min_price = min(self.extension_min_price, current_low)
            
            # Check for timeout (extension took too long = breakdown)
            if self.extension_bar_count > self.p.extension_max_bars:
                if self.p.print_signals:
                    print(f"[{dt:%Y-%m-%d %H:%M}] GLIESE: Extension timeout ({self.extension_bar_count} bars)")
                self._reset_state()
                return False
            
            # Check for reversal back above lower band
            if self._check_reversal_above():
                # Must have been extended for minimum bars
                if self.extension_bar_count >= self.p.extension_min_bars:
                    self.state = GLIESEState.REVERSAL_DETECTED
                    if self.p.print_signals:
                        print(f"[{dt:%Y-%m-%d %H:%M}] GLIESE: REVERSAL DETECTED | "
                              f"ExtBars={self.extension_bar_count}, MinPrice={self.extension_min_price:.5f}")
            
            return False
        
        # =====================================================================
        # STATE: REVERSAL_DETECTED - Waiting for pullback
        # =====================================================================
        elif self.state == GLIESEState.REVERSAL_DETECTED:
            # Check for cancellation
            if self._check_er_cancel():
                if self.p.print_signals:
                    print(f"[{dt:%Y-%m-%d %H:%M}] GLIESE: Reversal cancelled (ER surge)")
                self._reset_state()
                return False
            
            # Check for pullback
            if self._check_pullback_condition():
                self.state = GLIESEState.WAITING_PULLBACK
                self.pattern_detected_bar = current_bar
                self.pattern_atr = self._get_average_atr()
                
                # Set breakout level from pullback data
                if self.pullback_data:
                    offset = self.p.breakout_level_offset_pips * self.p.pip_value
                    self.breakout_level = self.pullback_data['breakout_level'] + offset
                else:
                    self.breakout_level = current_high + (self.p.breakout_level_offset_pips * self.p.pip_value)
                
                if self.p.print_signals:
                    print(f"[{dt:%Y-%m-%d %H:%M}] GLIESE: PULLBACK DETECTED | "
                          f"BreakoutLevel={self.breakout_level:.5f}")
                
                self.state = GLIESEState.WAITING_BREAKOUT
            
            return False
        
        # =====================================================================
        # STATE: WAITING_BREAKOUT - Monitoring for breakout entry
        # =====================================================================
        elif self.state == GLIESEState.WAITING_BREAKOUT:
            bars_since_pattern = current_bar - self.pattern_detected_bar
            
            # Check for timeout
            if bars_since_pattern > self.p.breakout_window_candles:
                if self.p.print_signals:
                    print(f"[{dt:%Y-%m-%d %H:%M}] GLIESE: Breakout window expired")
                self._reset_state()
                return False
            
            # Check for cancellation
            if self._check_er_cancel():
                if self.p.print_signals:
                    print(f"[{dt:%Y-%m-%d %H:%M}] GLIESE: Breakout cancelled (ER surge)")
                self._reset_state()
                return False
            
            # Check for breakout
            if check_pullback_breakout(
                current_high=current_high,
                breakout_level=self.breakout_level,
                buffer_pips=0,
                pip_value=self.p.pip_value
            ):
                # ENTRY SIGNAL
                if self.p.print_signals:
                    print(f"[{dt:%Y-%m-%d %H:%M}] GLIESE: BREAKOUT - ENTRY SIGNAL | "
                          f"High={current_high:.5f} > Level={self.breakout_level:.5f}")
                return True
            
            return False
        
        return False

    # =========================================================================
    # STANDARD FILTERS
    # =========================================================================
    
    def _check_standard_filters(self, dt: datetime, atr_avg: float, sl_pips: float) -> bool:
        """Check standard filters (time, day, ATR, SL pips)."""
        if not check_time_filter(dt, self.p.allowed_hours, self.p.use_time_filter):
            return False
        
        if not check_day_filter(dt, self.p.allowed_days, self.p.use_day_filter):
            return False
        
        if not check_atr_filter(atr_avg, self.p.atr_min, self.p.atr_max, self.p.use_atr_filter):
            return False
        
        if not check_sl_pips_filter(sl_pips, self.p.sl_pips_min, self.p.sl_pips_max, self.p.use_sl_pips_filter):
            return False
        
        return True

    # =========================================================================
    # ENTRY EXECUTION
    # =========================================================================
    
    def _execute_entry(self, dt: datetime, atr_avg: float):
        """Execute entry with SL/TP orders."""
        entry_price = self.breakout_level
        
        # Calculate SL/TP
        self.stop_level = entry_price - (atr_avg * self.p.atr_sl_multiplier)
        self.take_level = entry_price + (atr_avg * self.p.atr_tp_multiplier)
        
        sl_pips = abs(entry_price - self.stop_level) / self.p.pip_value
        
        # Check standard filters
        if not self._check_standard_filters(dt, atr_avg, sl_pips):
            self._reset_state()
            return
        
        # Calculate position size
        # Determine pair type
        pair_type = 'STANDARD'
        if self.p.is_etf:
            pair_type = 'ETF'
        elif self.p.pip_value == 0.01:  # JPY pairs
            pair_type = 'JPY'
        
        size = calculate_position_size(
            entry_price=entry_price,
            stop_loss=self.stop_level,
            equity=self.broker.get_value(),
            risk_percent=self.p.risk_percent,
            pair_type=pair_type,
            lot_size=self.p.lot_size,
            jpy_rate=self.p.jpy_rate,
            pip_value=self.p.pip_value,
            margin_pct=self.p.margin_pct,
        )
        
        if size <= 0:
            self._reset_state()
            return
        
        # Execute entry
        self.order = self.buy(size=size, exectype=bt.Order.Stop, price=entry_price)
        
        self.last_entry_price = entry_price
        self.last_entry_bar = len(self)
        self.pattern_atr = atr_avg
        
        # Record trade entry
        self._record_trade_entry(dt, entry_price, size, atr_avg, sl_pips)
        
        if self.p.print_signals:
            print(f">>> GLIESE ENTRY {dt:%Y-%m-%d %H:%M} | Entry={entry_price:.5f} | "
                  f"SL={self.stop_level:.5f} | TP={self.take_level:.5f} | Size={size}")

    # =========================================================================
    # MAIN LOOP
    # =========================================================================
    
    def _print_diagnostics(self, dt: datetime):
        """Print diagnostic info every N bars for debugging."""
        bar_num = len(self)
        
        # Print every 500 bars (about 1.7 days of 5m data)
        if bar_num % 500 != 0:
            return
        
        # Calculate all indicator values
        close = float(self.data.close[0])
        kama_val = float(self.kama[0])
        atr_val = float(self.atr[0])
        upper_band, lower_band = self._calculate_bands()
        
        # ER calculation
        er_value = None
        if self.p.use_htf_range_filter and len(self.data) >= self.scaled_er_period + 1:
            close_prices = [float(self.data.close[-i]) for i in range(self.scaled_er_period + 1)]
            close_prices.reverse()
            er_value = calculate_efficiency_ratio(close_prices, self.scaled_er_period)
        
        # ADXR calculation
        adxr_value = None
        if self.p.use_adxr_filter:
            required_bars = (self.p.adxr_period * 2) + self.p.adxr_lookback + 5
            if len(self.data) >= required_bars:
                highs = [float(self.data.high[-i]) for i in range(required_bars)]
                lows = [float(self.data.low[-i]) for i in range(required_bars)]
                closes = [float(self.data.close[-i]) for i in range(required_bars)]
                highs.reverse()
                lows.reverse()
                closes.reverse()
                adxr_value = calculate_adxr(
                    highs, lows, closes,
                    self.p.adxr_period, self.p.adxr_lookback
                )
        
        # KAMA Slope calculation
        kama_slope = None
        slope_threshold = None
        if self.p.use_kama_slope_filter and len(self.kama_history) >= self.p.kama_slope_lookback + 1:
            kama_slope = calculate_kama_slope(self.kama_history, self.p.kama_slope_lookback)
            slope_threshold = self.p.kama_slope_atr_mult * atr_val
        
        # Print diagnostic
        print(f"\n{'='*80}")
        print(f"[BAR {bar_num}] {dt:%Y-%m-%d %H:%M} | STATE: {self.state.name}")
        print(f"{'='*80}")
        print(f"  PRICE:  Close={close:.5f} | KAMA={kama_val:.5f} | ATR={atr_val:.6f}")
        print(f"  BANDS:  Upper={upper_band:.5f} | Lower={lower_band:.5f}")
        print(f"  DISTANCE: Close-Lower={(close - lower_band):.6f} | Close-KAMA={(close - kama_val):.6f}")
        print(f"  --- RANGE FILTERS ---")
        if er_value is not None:
            er_pass = "PASS" if er_value < self.p.htf_er_max_threshold else "FAIL"
            print(f"  ER:     {er_value:.4f} < {self.p.htf_er_max_threshold:.2f} ? {er_pass}")
        if adxr_value is not None:
            adxr_pass = "PASS" if adxr_value < self.p.adxr_max_threshold else "FAIL"
            print(f"  ADXR:   {adxr_value:.2f} < {self.p.adxr_max_threshold:.1f} ? {adxr_pass}")
        if kama_slope is not None:
            slope_pass = "PASS" if kama_slope < slope_threshold else "FAIL"
            print(f"  SLOPE:  {kama_slope:.8f} < {slope_threshold:.8f} ? {slope_pass}")
        
        # Check if all conditions pass
        range_ok, details, reason = self._check_range_conditions()
        print(f"  RANGE RESULT: {'ALL PASS' if range_ok else reason}")
        print(f"{'='*80}\n")
    
    def next(self):
        """Main strategy logic executed on each bar."""
        # Track portfolio value
        self._portfolio_values.append(self.broker.get_value())
        
        # Update price history
        self._update_price_history()
        
        # Get current datetime
        dt = self._get_datetime()
        
        # Skip if warmup period
        min_bars = max(
            self.p.kama_period + 10,
            self.scaled_er_period + 5,
            (self.p.adxr_period * 2) + self.p.adxr_lookback + 5
        )
        if len(self) < min_bars:
            return
        
        # Print diagnostics if enabled
        if self.p.print_signals:
            self._print_diagnostics(dt)
        
        # Update plot lines if in position
        if self.position and self.entry_exit_lines:
            self._update_plot_lines(
                self.last_entry_price,
                self.stop_level,
                self.take_level
            )
        elif self.entry_exit_lines:
            self._update_plot_lines(None, None, None)
        
        # Skip if pending order or in position
        if self.order or self.position:
            return
        
        # Process state machine
        entry_signal = self._process_state_machine(dt)
        
        if entry_signal:
            atr_avg = self._get_average_atr()
            self._execute_entry(dt, atr_avg)

    # =========================================================================
    # ORDER AND TRADE NOTIFICATIONS
    # =========================================================================
    
    def notify_order(self, order):
        """Handle order notifications."""
        if order.status in [order.Submitted, order.Accepted]:
            return
        
        if order.status == order.Completed:
            if order.isbuy():
                # Entry filled - place SL/TP
                self.stop_order = self.sell(
                    size=order.executed.size,
                    exectype=bt.Order.Stop,
                    price=self.stop_level
                )
                self.limit_order = self.sell(
                    size=order.executed.size,
                    exectype=bt.Order.Limit,
                    price=self.take_level
                )
                
                # Update plot lines
                if self.entry_exit_lines:
                    self._update_plot_lines(
                        order.executed.price,
                        self.stop_level,
                        self.take_level
                    )
                
                self._reset_state()
            
            elif order.issell():
                # Exit - cancel other order
                if order == self.stop_order and self.limit_order:
                    self.cancel(self.limit_order)
                    self.last_exit_reason = "STOP_LOSS"
                elif order == self.limit_order and self.stop_order:
                    self.cancel(self.stop_order)
                    self.last_exit_reason = "TAKE_PROFIT"
                
                # Clear plot lines
                if self.entry_exit_lines:
                    self._update_plot_lines(None, None, None)
                
                self.stop_order = None
                self.limit_order = None
        
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            if order == self.order:
                self._reset_state()
        
        if order == self.order:
            self.order = None
    
    def notify_trade(self, trade):
        """Handle trade notifications."""
        if not trade.isclosed:
            return
        
        pnl = trade.pnl
        self.trades += 1
        self._trade_pnls.append(pnl)
        
        if pnl > 0:
            self.wins += 1
            self.gross_profit += pnl
        else:
            self.losses += 1
            self.gross_loss += abs(pnl)
        
        dt = self._get_datetime()
        reason = self.last_exit_reason or "UNKNOWN"
        self._record_trade_exit(dt, pnl, reason)
        
        if self.p.print_signals:
            print(f"<<< GLIESE EXIT {dt:%Y-%m-%d %H:%M} | PnL=${pnl:.2f} | {reason}")

    # =========================================================================
    # PLOT HELPERS
    # =========================================================================
    
    def _update_plot_lines(self, entry_price=None, stop_level=None, take_level=None):
        """Update entry/exit plot lines on chart."""
        if not self.entry_exit_lines:
            return
        
        nan = float('nan')
        self.entry_exit_lines.lines.entry[0] = entry_price if entry_price else nan
        self.entry_exit_lines.lines.stop_loss[0] = stop_level if stop_level else nan
        self.entry_exit_lines.lines.take_profit[0] = take_level if take_level else nan

    # =========================================================================
    # TRADE REPORTING
    # =========================================================================
    
    def _init_trade_reporting(self):
        """Initialize trade report file."""
        if not self.p.export_reports:
            return
        try:
            report_dir = Path("logs")
            report_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_path = report_dir / f"GLIESE_trades_{timestamp}.txt"
            self.trade_report_file = open(report_path, 'w', encoding='utf-8')
            self.trade_report_file.write("=== GLIESE STRATEGY TRADE REPORT ===\n")
            self.trade_report_file.write(f"Generated: {datetime.now()}\n")
            self.trade_report_file.write(f"KAMA: period={self.p.kama_period}, fast={self.p.kama_fast}, slow={self.p.kama_slow}\n")
            self.trade_report_file.write(f"Bands: KAMA +/- {self.p.band_atr_mult} x ATR\n")
            self.trade_report_file.write(f"Range Detection: ER<{self.p.htf_er_max_threshold}, ADXR<{self.p.adxr_max_threshold}\n")
            self.trade_report_file.write(f"SL: {self.p.atr_sl_multiplier}x ATR | TP: {self.p.atr_tp_multiplier}x ATR\n")
            self.trade_report_file.write("\n")
            print(f"Trade report: {report_path}")
        except Exception as e:
            print(f"Trade reporting init failed: {e}")
    
    def _record_trade_entry(self, dt, entry_price, size, atr, sl_pips):
        """Record entry to trade report file."""
        if not self.trade_report_file:
            return
        try:
            entry = {
                'entry_time': dt,
                'entry_price': entry_price,
                'size': size,
                'atr': atr,
                'sl_pips': sl_pips,
                'stop_level': self.stop_level,
                'take_level': self.take_level,
            }
            self.trade_reports.append(entry)
            self.trade_report_file.write(f"ENTRY #{len(self.trade_reports)}\n")
            self.trade_report_file.write(f"Time: {dt.strftime('%Y-%m-%d %H:%M:%S')}\n")
            self.trade_report_file.write(f"Entry Price: {entry_price:.5f}\n")
            self.trade_report_file.write(f"Stop Loss: {self.stop_level:.5f}\n")
            self.trade_report_file.write(f"Take Profit: {self.take_level:.5f}\n")
            self.trade_report_file.write(f"SL Pips: {sl_pips:.1f}\n")
            self.trade_report_file.write(f"ATR (avg): {atr:.6f}\n")
            self.trade_report_file.write(f"State: Extension={self.extension_bar_count} bars\n")
            self.trade_report_file.write("-" * 50 + "\n\n")
            self.trade_report_file.flush()
        except Exception as e:
            pass
    
    def _record_trade_exit(self, dt, pnl, reason):
        """Record exit to trade report file."""
        if not self.trade_report_file or not self.trade_reports:
            return
        try:
            self.trade_reports[-1]['pnl'] = pnl
            self.trade_reports[-1]['exit_reason'] = reason
            self.trade_reports[-1]['exit_time'] = dt
            self.trade_report_file.write(f"EXIT #{len(self.trade_reports)}\n")
            self.trade_report_file.write(f"Time: {dt.strftime('%Y-%m-%d %H:%M:%S')}\n")
            self.trade_report_file.write(f"Exit Reason: {reason}\n")
            self.trade_report_file.write(f"P&L: ${pnl:.2f}\n")
            self.trade_report_file.write("=" * 80 + "\n\n")
            self.trade_report_file.flush()
        except:
            pass
    
    def stop(self):
        """Cleanup on strategy stop."""
        if self.trade_report_file:
            try:
                self.trade_report_file.write("\n=== SUMMARY ===\n")
                self.trade_report_file.write(f"Total Trades: {self.trades}\n")
                self.trade_report_file.write(f"Wins: {self.wins} | Losses: {self.losses}\n")
                if self.trades > 0:
                    win_rate = (self.wins / self.trades) * 100
                    self.trade_report_file.write(f"Win Rate: {win_rate:.1f}%\n")
                self.trade_report_file.write(f"Gross Profit: ${self.gross_profit:.2f}\n")
                self.trade_report_file.write(f"Gross Loss: ${self.gross_loss:.2f}\n")
                self.trade_report_file.write(f"Net P&L: ${self.gross_profit - self.gross_loss:.2f}\n")
                self.trade_report_file.close()
            except:
                pass
