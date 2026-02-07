"""
GEMINI Strategy - Correlation Divergence Momentum (Harmony Score)

CONCEPT:
EURUSD and USDCHF are inversely correlated (~-0.90) via USD.
We measure MOMENTUM (Rate of Change) of each pair, not price levels.

Harmony Score = ROC_EURUSD × (-ROC_USDCHF) × scale
(Product captures symmetric divergence: both ROCs moving apart from zero)

When harmony > threshold AND ROC_primary > 0 sustained for N bars -> LONG EURUSD

This captures SYMMETRIC divergence scenarios:
- EURUSD rising (+), USDCHF falling (-) -> harmony positive (ideal scenario)
- Higher value = stronger AND more symmetric movement
- Negative harmony = both ROCs same direction (no divergence)

ENTRY SYSTEM:
1. HARMONY: ROC_primary × (-ROC_reference) × scale > threshold
2. DIRECTION: ROC_primary > 0 (ensures LONG direction makes sense)
3. SUSTAINED: Harmony positive for N consecutive bars
4. TREND: Price > KAMA (optional)

EXIT SYSTEM:
- Stop Loss: Entry - (ATR x SL multiplier)
- Take Profit: Entry + (ATR x TP multiplier)

TARGET PAIRS: 
- EURUSD_GEMINI (primary=EURUSD, reference=USDCHF)
"""
from __future__ import annotations
import math
from pathlib import Path
from datetime import datetime
from collections import defaultdict

import backtrader as bt
import numpy as np

from lib.filters import (
    check_time_filter,
    check_day_filter,
    check_atr_filter,
    check_sl_pips_filter,
)
from lib.indicators import KAMA, calculate_roc_from_history
from lib.position_sizing import calculate_position_size


class EntryExitLines(bt.Indicator):
    """Indicator to plot entry/exit price levels as horizontal dashed lines."""
    lines = ('entry', 'stop_loss', 'take_profit')
    
    plotinfo = dict(subplot=False, plotlinelabels=True)
    plotlines = dict(
        entry=dict(color='green', linestyle='--', linewidth=1.0),
        stop_loss=dict(color='red', linestyle='--', linewidth=1.0),
        take_profit=dict(color='blue', linestyle='--', linewidth=1.0),
    )
    
    def __init__(self):
        pass
    
    def next(self):
        pass


class ROCDualIndicator(bt.Indicator):
    """Indicator to plot ROC of primary/reference and Harmony Score."""
    lines = ('roc_primary', 'roc_reference', 'harmony', 'zero')
    
    plotinfo = dict(
        subplot=True,
        plotname='ROC & Harmony',
        plotlinelabels=True,
        plotheight=2.0,     # Double height for better visibility
    )
    plotlines = dict(
        roc_primary=dict(color='blue', linewidth=1.2, _name='ROC Primary'),
        roc_reference=dict(color='red', linewidth=1.2, _name='ROC Reference'),
        harmony=dict(color='purple', linewidth=2.0, _name='Harmony'),
        zero=dict(color='gray', linestyle='--', linewidth=0.8),
    )
    
    def __init__(self):
        pass
    
    def next(self):
        # Zero line constant
        self.lines.zero[0] = 0.0


class AngleIndicator(bt.Indicator):
    """Indicator to plot slope angles of ROC and Harmony."""
    lines = ('roc_angle', 'harmony_angle', 'zero')
    
    plotinfo = dict(
        subplot=True,
        plotname='Slope Angles (degrees)',
        plotlinelabels=True,
        plotheight=1.5,
    )
    plotlines = dict(
        roc_angle=dict(color='blue', linewidth=1.2, _name='ROC Angle'),
        harmony_angle=dict(color='purple', linewidth=1.2, _name='Harmony Angle'),
        zero=dict(color='gray', linestyle='--', linewidth=0.8),
    )
    
    def __init__(self):
        pass
    
    def next(self):
        self.lines.zero[0] = 0.0


class GEMINIStrategy(bt.Strategy):
    """
    GEMINI Strategy - Correlation Divergence Momentum.
    
    Trades EURUSD (or USDCHF) based on divergence from correlated pair.
    Long when spread expands positive = primary pair has intrinsic strength.
    """
    
    params = dict(
        # === ROC DIVERGENCE SETTINGS ===
        roc_period_primary=12,          # ROC period for primary (12 = 1 hour on 5m)
        roc_period_reference=12,        # ROC period for reference (can be different)
        
        # === HARMONY SCORE ===
        harmony_scale=10000,            # Multiplier for visualization (raw values ~0.000001)
        
        # === ENTRY SYSTEM: KAMA Cross + Angle Confirmation ===
        # Step 1: TRIGGER - HL2_EMA crosses above KAMA
        # Step 2: CONFIRMATION - Within N bars, check angles
        cross_window_bars=5,            # Window after cross to look for entry (N bars)
        entry_roc_angle_min=10.0,       # Min ROC angle during window (degrees)
        entry_harmony_angle_min=10.0,   # Min Harmony angle during window (degrees)
        # Angle scales (for plot-scaled values)
        roc_angle_scale=1.0,            # Scale for ROC angle calculation
        harmony_angle_scale=1.0,        # Scale for Harmony angle calculation
        
        # === KAMA SETTINGS ===
        kama_period=10,
        kama_fast=2,
        kama_slow=30,
        
        # HL2 EMA for KAMA comparison
        hl2_ema_period=1,
        
        # === ATR for SL/TP ===
        atr_length=14,
        atr_sl_multiplier=3.0,
        atr_tp_multiplier=8.0,
        
        # === FILTERS ===
        # Time Filter
        use_time_filter=False,
        allowed_hours=[],
        
        # Day Filter (0=Monday, 6=Sunday)
        use_day_filter=False,
        allowed_days=[0, 1, 2, 3, 4],
        
        # SL Pips Filter
        use_sl_pips_filter=False,
        sl_pips_min=5.0,
        sl_pips_max=50.0,
        
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
        plot_reference_chart=False,    # Show USDCHF chart in plot
        plot_roc_multiplier=10000,     # Scale ROC values for visibility (raw ~0.0001)
        plot_harmony_multiplier=1.0,   # Additional scale for harmony (already scaled by harmony_scale)
    )

    def __init__(self):
        # Primary data (EURUSD)
        self.primary_data = self.datas[0]
        
        # Reference data (USDCHF)
        if len(self.datas) > 1:
            self.reference_data = self.datas[1]
            print(f'[GEMINI] Reference data: {self.reference_data._name}')
            
            # Hide reference chart from plot if not needed
            if not self.p.plot_reference_chart:
                self.reference_data.plotinfo.plot = False
        else:
            raise ValueError('[GEMINI] ERROR: Reference data required (datas[1])')
        
        # HL2 for primary
        self.hl2 = (self.primary_data.high + self.primary_data.low) / 2.0
        
        # KAMA on primary HL2
        self.kama = KAMA(
            self.hl2,
            period=self.p.kama_period,
            fast=self.p.kama_fast,
            slow=self.p.kama_slow
        )
        
        # EMA on HL2 for KAMA comparison
        self.hl2_ema = bt.ind.EMA(self.hl2, period=self.p.hl2_ema_period)
        self.hl2_ema.plotinfo.subplot = False
        self.hl2_ema.plotinfo.plotname = 'HL2 EMA'
        
        # ATR on primary
        self.atr = bt.ind.ATR(self.primary_data, period=self.p.atr_length)
        
        # Entry/Exit plot lines
        if self.p.plot_entry_exit_lines:
            self.entry_exit_lines = EntryExitLines(self.primary_data)
        else:
            self.entry_exit_lines = None
        
        # ROC indicator for subplot (shows both ROC lines)
        self.roc_indicator = ROCDualIndicator(self.primary_data)
        
        # Angle indicator for subplot (shows slope angles)
        self.angle_indicator = AngleIndicator(self.primary_data)
        
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
        self.state = "SCANNING"
        
        # Cross detection state
        self.cross_detected_bar = None      # Bar number when cross detected
        self.in_cross_window = False        # Currently in entry window
        self.prev_hl2_above_kama = False    # Previous bar HL2 > KAMA state
        
        # History for ROC calculation
        self.primary_close_history = []
        self.reference_close_history = []
        self.harmony_history = []
        
        # History for slope/angle calculation
        self.roc_primary_history = []    # Store ROC values for slope
        self.harmony_value_history = []  # Store harmony for slope
        
        # ATR history for averaging
        self.atr_history = []
        
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
    # SLOPE/ANGLE CALCULATION (inspired by Ogle)
    # =========================================================================
    
    def _calculate_angle(self, current_val: float, previous_val: float, scale: float) -> float:
        """
        Calculate angle of slope in degrees (same formula as Ogle).
        
        angle = atan((current - previous) * scale) -> degrees
        
        Positive angle = rising, negative = falling
        45 degrees = moderate rise, 80+ = strong rise
        """
        try:
            rise = (current_val - previous_val) * scale
            return math.degrees(math.atan(rise))
        except (ValueError, ZeroDivisionError):
            return 0.0

    # =========================================================================
    # HARMONY CALCULATION (ROC-based)
    # =========================================================================
    
    def _calculate_harmony(self) -> tuple:
        """
        Calculate Harmony Score from ROC of both pairs.
        
        Harmony = ROC_primary × (-ROC_reference) × scale
        
        High harmony = both ROCs diverging from zero proportionally
        (primary rising, reference falling = harmonic divergence)
        
        Returns: (harmony_scaled, roc_primary, roc_reference, roc_angle, harmony_angle)
        """
        try:
            # Get current close prices
            primary_close = float(self.primary_data.close[0])
            reference_close = float(self.reference_data.close[0])
            
            # Store history
            self.primary_close_history.append(primary_close)
            self.reference_close_history.append(reference_close)
            
            # Need enough data for ROC (use max of both periods)
            max_period = max(self.p.roc_period_primary, self.p.roc_period_reference)
            required_len = max_period + 1
            if len(self.primary_close_history) < required_len:
                return 0.0, 0.0, 0.0, 0.0, 0.0
            
            # Keep only needed history
            max_history = max_period + 10
            if len(self.primary_close_history) > max_history:
                self.primary_close_history = self.primary_close_history[-max_history:]
                self.reference_close_history = self.reference_close_history[-max_history:]
            
            # Calculate ROC using lib function (each with its own period)
            roc_primary = calculate_roc_from_history(self.primary_close_history, self.p.roc_period_primary)
            roc_reference = calculate_roc_from_history(self.reference_close_history, self.p.roc_period_reference)
            
            # Harmony = ROC_primary × (-ROC_reference) × scale
            # Positive when: primary up AND reference down (harmonic divergence)
            harmony_raw = roc_primary * (-roc_reference)
            harmony_scaled = harmony_raw * self.p.harmony_scale
            
            # Store values history for slope calculation
            self.roc_primary_history.append(roc_primary)
            self.harmony_value_history.append(harmony_scaled)
            
            # Keep limited history (2 values enough for slope)
            if len(self.roc_primary_history) > 5:
                self.roc_primary_history = self.roc_primary_history[-5:]
            if len(self.harmony_value_history) > 5:
                self.harmony_value_history = self.harmony_value_history[-5:]
            
            # Calculate angles using PLOT-SCALED values (same as what's visible in subplot)
            roc_angle = 0.0
            harmony_angle = 0.0
            
            if len(self.roc_primary_history) >= 2 and len(self.harmony_value_history) >= 2:
                roc_plot_current = self.roc_primary_history[-1] * self.p.plot_roc_multiplier
                roc_plot_previous = self.roc_primary_history[-2] * self.p.plot_roc_multiplier
                harmony_plot_current = self.harmony_value_history[-1] * self.p.plot_harmony_multiplier
                harmony_plot_previous = self.harmony_value_history[-2] * self.p.plot_harmony_multiplier
                
                roc_angle = self._calculate_angle(
                    roc_plot_current, 
                    roc_plot_previous,
                    self.p.roc_angle_scale
                )
                harmony_angle = self._calculate_angle(
                    harmony_plot_current,
                    harmony_plot_previous,
                    self.p.harmony_angle_scale
                )
            
            return harmony_scaled, roc_primary, roc_reference, roc_angle, harmony_angle
            
        except Exception as e:
            return 0.0, 0.0, 0.0, 0.0, 0.0

    # =========================================================================
    # TRADE REPORTING (same format as HELIX)
    # =========================================================================
    
    def _init_trade_reporting(self):
        """Initialize trade report file."""
        if not self.p.export_reports:
            return
        try:
            report_dir = Path("logs")
            report_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_path = report_dir / f"GEMINI_trades_{timestamp}.txt"
            self.trade_report_file = open(report_path, 'w', encoding='utf-8')
            self.trade_report_file.write("=== GEMINI STRATEGY TRADE REPORT ===\n")
            self.trade_report_file.write(f"Generated: {datetime.now()}\n")
            self.trade_report_file.write("\n")
            # Configuration header
            self.trade_report_file.write("=== CONFIGURATION ===\n")
            self.trade_report_file.write(f"KAMA: period={self.p.kama_period}, fast={self.p.kama_fast}, slow={self.p.kama_slow}\n")
            self.trade_report_file.write(f"Entry System: KAMA Cross + Angle Confirmation\n")
            self.trade_report_file.write(f"Cross Window: {self.p.cross_window_bars} bars\n")
            self.trade_report_file.write(f"ROC: primary_period={self.p.roc_period_primary}, reference_period={self.p.roc_period_reference}\n")
            self.trade_report_file.write(f"Harmony Scale: {self.p.harmony_scale}\n")
            self.trade_report_file.write(f"Entry Angles: ROC >= {self.p.entry_roc_angle_min}°, Harmony >= {self.p.entry_harmony_angle_min}°\n")
            self.trade_report_file.write(f"ATR: length={self.p.atr_length}, avg_period={self.p.atr_avg_period}\n")
            self.trade_report_file.write(f"SL: {self.p.atr_sl_multiplier}x ATR | TP: {self.p.atr_tp_multiplier}x ATR\n")
            self.trade_report_file.write(f"Pip Value: {self.p.pip_value}\n")
            self.trade_report_file.write(f"Risk: {self.p.risk_percent * 100:.1f}%\n")
            # Filters
            self.trade_report_file.write("\n=== FILTERS ===\n")
            if self.p.use_sl_pips_filter:
                self.trade_report_file.write(f"SL Pips Filter: {self.p.sl_pips_min}-{self.p.sl_pips_max} pips\n")
            else:
                self.trade_report_file.write("SL Pips Filter: DISABLED\n")
            if self.p.use_atr_filter:
                self.trade_report_file.write(f"ATR Filter: {self.p.atr_min}-{self.p.atr_max}\n")
            else:
                self.trade_report_file.write("ATR Filter: DISABLED\n")
            if self.p.use_time_filter:
                self.trade_report_file.write(f"Time Filter: {list(self.p.allowed_hours)}\n")
            else:
                self.trade_report_file.write("Time Filter: DISABLED\n")
            if self.p.use_day_filter:
                day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
                days = [day_names[d] for d in self.p.allowed_days if d < 7]
                self.trade_report_file.write(f"Day Filter: {days}\n")
            else:
                self.trade_report_file.write("Day Filter: DISABLED\n")
            self.trade_report_file.write("\n")
            print(f"[GEMINI] Trade report: {report_path}")
        except Exception as e:
            print(f"[GEMINI] Trade reporting init failed: {e}")

    def _record_trade_entry(self, dt, entry_price, size, atr, sl_pips, harmony_value, roc_angle, harmony_angle):
        """Record entry to trade report file."""
        if not self.trade_report_file:
            return
        try:
            entry = {
                'entry_time': dt,
                'entry_price': entry_price,
                'size': size,
                'atr': atr,
                'harmony': harmony_value,
                'roc_angle': roc_angle,
                'harmony_angle': harmony_angle,
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
            self.trade_report_file.write(f"ROC Angle: {roc_angle:.1f}°\n")
            self.trade_report_file.write(f"Harmony Angle: {harmony_angle:.1f}°\n")
            self.trade_report_file.write(f"Harmony Score: {harmony_value:.4f}\n")
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

    # =========================================================================
    # PLOT LINES UPDATE
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
    # DATETIME HELPER
    # =========================================================================
    
    def _get_datetime(self, offset=0) -> datetime:
        """Get correct datetime combining date and time."""
        try:
            dt_date = self.primary_data.datetime.date(offset)
            dt_time = self.primary_data.datetime.time(offset)
            return datetime.combine(dt_date, dt_time)
        except Exception:
            return self.primary_data.datetime.datetime(offset)

    def _get_average_atr(self) -> float:
        """Get average ATR over the specified period."""
        if len(self.atr_history) < self.p.atr_avg_period:
            return float(self.atr[0]) if not math.isnan(float(self.atr[0])) else 0
        
        recent_atr = self.atr_history[-self.p.atr_avg_period:]
        return sum(recent_atr) / len(recent_atr)

    # =========================================================================
    # CONDITION CHECKS
    # =========================================================================
    
    def _check_kama_condition(self) -> bool:
        """Check if EMA(HL2) is above KAMA. Always checks (KAMA cross is the trigger)."""
        try:
            hl2_ema_value = float(self.hl2_ema[0])
            kama_value = float(self.kama[0])
            return hl2_ema_value > kama_value
        except:
            return False

    def _detect_kama_cross(self) -> bool:
        """
        Detect if HL2_EMA just crossed above KAMA (bullish cross).
        
        Returns: True if cross detected THIS bar
        """
        try:
            hl2_ema_now = float(self.hl2_ema[0])
            kama_now = float(self.kama[0])
            
            # Current state
            hl2_above_kama_now = hl2_ema_now > kama_now
            
            # Cross detected: was below/equal, now above
            cross = hl2_above_kama_now and not self.prev_hl2_above_kama
            
            # Update state for next bar
            self.prev_hl2_above_kama = hl2_above_kama_now
            
            return cross
        except:
            return False
    
    def _check_cross_window(self) -> bool:
        """
        Check if we're still within the entry window after a cross.
        
        Returns: True if within window
        """
        if self.cross_detected_bar is None:
            return False
        
        current_bar = len(self.primary_data)
        bars_since_cross = current_bar - self.cross_detected_bar
        
        return bars_since_cross <= self.p.cross_window_bars
    
    def _check_angle_conditions(self, roc_angle: float, harmony_angle: float) -> bool:
        """
        Check if both angles meet minimum requirements.
        
        Returns: True if both angles >= minimum
        """
        roc_ok = roc_angle >= self.p.entry_roc_angle_min
        harmony_ok = harmony_angle >= self.p.entry_harmony_angle_min
        return roc_ok and harmony_ok
    
    def _check_final_filters(self, dt: datetime) -> bool:
        """
        Check final filters before entry (time, day, ATR, SL pips).
        Applied AFTER angle confirmation.
        
        Returns: True if all filters pass
        """
        # Time filter
        if self.p.use_time_filter:
            if not check_time_filter(dt, self.p.allowed_hours, True):
                return False
        
        # Day filter
        if self.p.use_day_filter:
            if not check_day_filter(dt, self.p.allowed_days, True):
                return False
        
        return True

    # =========================================================================
    # ENTRY EXECUTION
    # =========================================================================
    
    def _execute_entry(self, dt: datetime, harmony_value: float, roc_angle: float, harmony_angle: float):
        """Execute market entry after KAMA cross + angle confirmation."""
        
        entry_price = float(self.primary_data.close[0])
        avg_atr = self._get_average_atr()
        
        # ATR Filter
        if self.p.use_atr_filter:
            if not check_atr_filter(avg_atr, self.p.atr_min, self.p.atr_max, True):
                return
        
        # Calculate SL/TP
        self.stop_level = entry_price - (avg_atr * self.p.atr_sl_multiplier)
        self.take_level = entry_price + (avg_atr * self.p.atr_tp_multiplier)
        
        # SL Pips Filter
        sl_pips = abs(entry_price - self.stop_level) / self.p.pip_value
        if self.p.use_sl_pips_filter:
            if not check_sl_pips_filter(sl_pips, self.p.sl_pips_min, self.p.sl_pips_max, True):
                return
        
        # Position sizing
        if self.p.is_etf:
            pair_type = 'ETF'
        elif self.p.is_jpy_pair:
            pair_type = 'JPY'
        else:
            pair_type = 'STANDARD'
        
        bt_size = calculate_position_size(
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
        
        if bt_size <= 0:
            return
        
        # Execute order
        self.order = self.buy(size=bt_size, exectype=bt.Order.Market)
        self.last_entry_price = entry_price
        self.last_entry_bar = len(self.primary_data)
        self.state = "IN_POSITION"
        
        # Record entry
        self._record_trade_entry(
            dt, entry_price, bt_size, avg_atr, sl_pips, harmony_value, roc_angle, harmony_angle
        )
        
        # Update plot lines
        self._update_plot_lines(entry_price, self.stop_level, self.take_level)
        
        if self.p.print_signals:
            print(f"[GEMINI] {dt} ENTRY @ {entry_price:.5f} | ROC_angle={roc_angle:.1f}° | Harm_angle={harmony_angle:.1f}° | SL={self.stop_level:.5f}")

    # =========================================================================
    # EXIT LOGIC
    # =========================================================================
    
    def _check_exit_conditions(self) -> str:
        """Check exit conditions. Returns exit reason or empty string."""
        low = float(self.primary_data.low[0])
        high = float(self.primary_data.high[0])
        
        # Stop Loss hit
        if low <= self.stop_level:
            return 'SL'
        
        # Take Profit hit
        if high >= self.take_level:
            return 'TP'
        
        return ''
    
    def _execute_exit(self, dt: datetime, reason: str):
        """Execute exit order. Stats updated in notify_trade."""
        self.last_exit_reason = reason
        self.order = self.close()
        
        # Update plot lines (clear)
        self._update_plot_lines()
        
        # Reset state (stats updated in notify_trade)
        self.state = "SCANNING"
        self.stop_level = None
        self.take_level = None
        self.last_entry_price = None
        self.last_entry_bar = None

    # =========================================================================
    # ORDER NOTIFICATION
    # =========================================================================
    
    def notify_order(self, order):
        """Handle order notifications."""
        if order.status in [order.Submitted, order.Accepted]:
            return
        
        if order.status in [order.Canceled, order.Margin, order.Rejected]:
            if self.p.print_signals:
                print(f'[GEMINI] Order failed: {order.status}')
            self.state = "SCANNING"
        
        self.order = None

    def notify_trade(self, trade):
        """Handle trade close notifications - calculate real P&L from Backtrader."""
        if not trade.isclosed:
            return
        
        dt = self._get_datetime()
        pnl = trade.pnl  # Real P&L from Backtrader
        
        self.trades += 1
        self._trade_pnls.append(pnl)
        
        if pnl > 0:
            self.wins += 1
            self.gross_profit += pnl
        else:
            self.losses += 1
            self.gross_loss += abs(pnl)
        
        reason = self.last_exit_reason or "UNKNOWN"
        self._record_trade_exit(dt, pnl, reason)
        
        if self.p.print_signals:
            print(f"[GEMINI] {dt} EXIT ({reason}) | P&L: ${pnl:.2f}")
        
        self.last_exit_reason = None

    # =========================================================================
    # MAIN LOOP
    # =========================================================================
    
    def next(self):
        """Main strategy loop."""
        # Update ATR history
        atr_val = float(self.atr[0])
        if not math.isnan(atr_val):
            self.atr_history.append(atr_val)
            if len(self.atr_history) > self.p.atr_avg_period * 2:
                self.atr_history = self.atr_history[-self.p.atr_avg_period * 2:]
        
        # Calculate harmony every bar (for plotting)
        harmony_value, roc_primary, roc_reference, roc_angle, harmony_angle = self._calculate_harmony()
        
        # Update ROC indicator for subplot (both lines + harmony)
        # Apply plot multipliers for visibility (doesn't affect calculations)
        self.roc_indicator.lines.roc_primary[0] = roc_primary * self.p.plot_roc_multiplier
        self.roc_indicator.lines.roc_reference[0] = roc_reference * self.p.plot_roc_multiplier
        self.roc_indicator.lines.harmony[0] = harmony_value * self.p.plot_harmony_multiplier
        
        # Update Angle indicator for subplot
        self.angle_indicator.lines.roc_angle[0] = roc_angle
        self.angle_indicator.lines.harmony_angle[0] = harmony_angle
        
        # Track portfolio value
        self._portfolio_values.append(self.broker.get_value())
        
        # Skip if order pending
        if self.order:
            return
        
        # Get current datetime
        dt = self._get_datetime()
        
        # State machine
        if self.state == "IN_POSITION":
            # Check exit conditions
            exit_reason = self._check_exit_conditions()
            if exit_reason:
                self._execute_exit(dt, exit_reason)
                
            # Update plot lines while in position
            else:
                self._update_plot_lines(
                    self.last_entry_price, 
                    self.stop_level, 
                    self.take_level
                )
        
        elif self.state == "SCANNING":
            # === NEW ENTRY SYSTEM ===
            # Step 1: TRIGGER - Detect KAMA cross
            if self._detect_kama_cross():
                self.cross_detected_bar = len(self.primary_data)
                self.in_cross_window = True
                if self.p.print_signals:
                    print(f"[GEMINI] {dt} KAMA CROSS detected - window open for {self.p.cross_window_bars} bars")
            
            # Step 2: Check if still in window
            if self.in_cross_window:
                if not self._check_cross_window():
                    # Window expired
                    self.in_cross_window = False
                    self.cross_detected_bar = None
                    if self.p.print_signals:
                        print(f"[GEMINI] {dt} Window expired - no entry")
                else:
                    # Step 3: CONFIRMATION - Check angles
                    if self._check_angle_conditions(roc_angle, harmony_angle):
                        # Step 4: FILTERS - Final checks before entry
                        if self._check_final_filters(dt):
                            self._execute_entry(dt, harmony_value, roc_angle, harmony_angle)
                            # Reset window after entry
                            self.in_cross_window = False
                            self.cross_detected_bar = None

    # =========================================================================
    # STOP - FINAL REPORT (same structure as HELIX)
    # =========================================================================
    
    def stop(self):
        """Generate final report."""
        total_trades = self.trades
        win_rate = (self.wins / total_trades * 100) if total_trades > 0 else 0
        profit_factor = (self.gross_profit / self.gross_loss) if self.gross_loss > 0 else float('inf')
        total_pnl = self.gross_profit - self.gross_loss
        final_value = self.broker.get_value()
        
        # Calculate advanced metrics
        sharpe_ratio = 0.0
        sortino_ratio = 0.0
        if len(self._trade_pnls) > 1:
            pnl_array = np.array(self._trade_pnls)
            mean_pnl = np.mean(pnl_array)
            std_pnl = np.std(pnl_array)
            
            if std_pnl > 0:
                sharpe_ratio = (mean_pnl / std_pnl) * np.sqrt(len(pnl_array))
            
            negative_pnls = pnl_array[pnl_array < 0]
            if len(negative_pnls) > 0:
                downside_std = np.std(negative_pnls)
                if downside_std > 0:
                    sortino_ratio = (mean_pnl / downside_std) * np.sqrt(len(pnl_array))
        
        # Max Drawdown
        max_drawdown_pct = 0.0
        if len(self._portfolio_values) > 0:
            peak = self._portfolio_values[0]
            for val in self._portfolio_values:
                if val > peak:
                    peak = val
                dd = (peak - val) / peak * 100
                if dd > max_drawdown_pct:
                    max_drawdown_pct = dd
        
        # CAGR
        cagr = 0.0
        if len(self._portfolio_values) > 252:  # ~1 year of trading days
            years = len(self._portfolio_values) / 252
            if self._starting_cash > 0 and final_value > 0:
                cagr = ((final_value / self._starting_cash) ** (1 / years) - 1) * 100
        
        # Calmar Ratio
        calmar_ratio = cagr / max_drawdown_pct if max_drawdown_pct > 0 else 0
        
        # Monte Carlo simulation
        monte_carlo_dd_95 = 0.0
        monte_carlo_dd_99 = 0.0
        if len(self._trade_pnls) >= 30:
            monte_carlo_dds = []
            for _ in range(10000):
                shuffled_pnls = np.random.choice(self._trade_pnls, size=len(self._trade_pnls), replace=True)
                cumsum = np.cumsum(shuffled_pnls)
                running_max = np.maximum.accumulate(cumsum + self._starting_cash)
                drawdowns = (running_max - (cumsum + self._starting_cash)) / running_max * 100
                monte_carlo_dds.append(np.max(drawdowns))
            
            monte_carlo_dd_95 = np.percentile(monte_carlo_dds, 95)
            monte_carlo_dd_99 = np.percentile(monte_carlo_dds, 99)
        
        # Yearly Statistics
        yearly_stats = defaultdict(lambda: {
            'trades': 0, 'wins': 0, 'losses': 0,
            'gross_profit': 0.0, 'gross_loss': 0.0, 'pnl': 0.0,
            'pnls': []
        })
        
        for trade in self.trade_reports:
            if 'exit_time' in trade and 'pnl' in trade:
                year = trade['exit_time'].year
                pnl = trade['pnl']
                yearly_stats[year]['trades'] += 1
                yearly_stats[year]['pnl'] += pnl
                yearly_stats[year]['pnls'].append(pnl)
                if pnl > 0:
                    yearly_stats[year]['wins'] += 1
                    yearly_stats[year]['gross_profit'] += pnl
                else:
                    yearly_stats[year]['losses'] += 1
                    yearly_stats[year]['gross_loss'] += abs(pnl)
        
        # Calculate yearly Sharpe
        for year in yearly_stats:
            pnls = yearly_stats[year]['pnls']
            if len(pnls) > 1:
                pnl_array = np.array(pnls)
                mean_pnl = np.mean(pnl_array)
                std_pnl = np.std(pnl_array)
                if std_pnl > 0:
                    yearly_stats[year]['sharpe'] = (mean_pnl / std_pnl) * np.sqrt(len(pnls))
                else:
                    yearly_stats[year]['sharpe'] = 0.0
                
                neg_pnls = pnl_array[pnl_array < 0]
                if len(neg_pnls) > 0:
                    downside_std = np.std(neg_pnls)
                    if downside_std > 0:
                        yearly_stats[year]['sortino'] = (mean_pnl / downside_std) * np.sqrt(len(pnls))
                    else:
                        yearly_stats[year]['sortino'] = 0.0
                else:
                    yearly_stats[year]['sortino'] = float('inf') if mean_pnl > 0 else 0.0
            else:
                yearly_stats[year]['sharpe'] = 0.0
                yearly_stats[year]['sortino'] = 0.0
        
        # =================================================================
        # PRINT SUMMARY
        # =================================================================
        print('\n' + '=' * 70)
        print('=== GEMINI STRATEGY SUMMARY ===')
        print('=' * 70)
        
        print(f'Total Trades: {total_trades}')
        print(f'Wins: {self.wins} | Losses: {self.losses}')
        print(f'Win Rate: {win_rate:.1f}%')
        print(f'Profit Factor: {profit_factor:.2f}')
        print(f'Gross Profit: ${self.gross_profit:,.2f}')
        print(f'Gross Loss: ${self.gross_loss:,.2f}')
        print(f'Net P&L: ${total_pnl:,.2f}')
        print(f'Final Value: ${final_value:,.2f}')
        
        # Advanced Metrics
        print(f"\n{'='*70}")
        print('ADVANCED RISK METRICS')
        print(f"{'='*70}")
        
        sharpe_status = "Poor" if sharpe_ratio < 0.5 else "Marginal" if sharpe_ratio < 1.0 else "Good" if sharpe_ratio < 2.0 else "Excellent"
        print(f'Sharpe Ratio:    {sharpe_ratio:>8.2f}  [{sharpe_status}]')
        
        sortino_status = "Poor" if sortino_ratio < 0.5 else "Marginal" if sortino_ratio < 1.0 else "Good" if sortino_ratio < 2.0 else "Excellent"
        print(f'Sortino Ratio:   {sortino_ratio:>8.2f}  [{sortino_status}]')
        
        cagr_status = "Below Market" if cagr < 8 else "Market-level" if cagr < 12 else "Good" if cagr < 20 else "Exceptional"
        print(f'CAGR:            {cagr:>7.2f}%  [{cagr_status}]')
        
        dd_status = "Excellent" if max_drawdown_pct < 10 else "Acceptable" if max_drawdown_pct < 20 else "High" if max_drawdown_pct < 30 else "Dangerous"
        print(f'Max Drawdown:    {max_drawdown_pct:>7.2f}%  [{dd_status}]')
        
        calmar_status = "Poor" if calmar_ratio < 0.5 else "Acceptable" if calmar_ratio < 1.0 else "Good" if calmar_ratio < 2.0 else "Excellent"
        print(f'Calmar Ratio:    {calmar_ratio:>8.2f}  [{calmar_status}]')
        
        if monte_carlo_dd_95 > 0:
            mc_ratio = monte_carlo_dd_95 / max_drawdown_pct if max_drawdown_pct > 0 else 0
            mc_status = "Good" if mc_ratio < 1.5 else "Caution" if mc_ratio < 2.0 else "Warning"
            print(f'\nMonte Carlo Analysis (10,000 simulations):')
            print(f'  95th Percentile DD: {monte_carlo_dd_95:>6.2f}%  [{mc_status}]')
            print(f'  99th Percentile DD: {monte_carlo_dd_99:>6.2f}%')
            print(f'  Historical vs MC95: {mc_ratio:.2f}x')
        
        print(f"{'='*70}")
        
        # Yearly Statistics
        if yearly_stats:
            print(f"\n{'='*70}")
            print('YEARLY STATISTICS')
            print(f"{'='*70}")
            print(f"{'Year':<6} {'Trades':>7} {'WR%':>7} {'PF':>7} {'PnL':>12} {'Sharpe':>8} {'Sortino':>8}")
            print(f"{'-'*70}")
            
            for year in sorted(yearly_stats.keys()):
                stats = yearly_stats[year]
                wr = (stats['wins'] / stats['trades'] * 100) if stats['trades'] > 0 else 0
                year_pf = (stats['gross_profit'] / stats['gross_loss']) if stats['gross_loss'] > 0 else float('inf')
                year_sharpe = stats.get('sharpe', 0.0)
                year_sortino = stats.get('sortino', 0.0)
                
                pf_str = f"{year_pf:>7.2f}" if year_pf != float('inf') else "    inf"
                sortino_str = f"{year_sortino:>7.2f}" if year_sortino != float('inf') else "    inf"
                
                print(f"{year:<6} {stats['trades']:>7} {wr:>6.1f}% {pf_str} ${stats['pnl']:>10,.0f} {year_sharpe:>8.2f} {sortino_str}")
            
            print(f"{'='*70}")
        
        # Commission Summary (calculated from trade_reports)
        total_lots = sum(t.get('size', 0) / self.p.lot_size for t in self.trade_reports if 'size' in t)
        total_commission = total_lots * 2 * 2.5  # Round-trip * $2.5 per lot (typical forex)
        avg_commission = total_commission / total_trades if total_trades > 0 else 0
        avg_lots = total_lots / total_trades if total_trades > 0 else 0
        
        print(f"\n{'='*70}")
        print('COMMISSION SUMMARY')
        print(f"{'='*70}")
        print(f'Total Commission Paid:    ${total_commission:,.2f}')
        print(f'Total Lots Traded:        {total_lots:,.2f}')
        print(f'Avg Commission per Trade: ${avg_commission:,.2f}')
        print(f'Avg Lots per Trade:       {avg_lots:,.2f}')
        print(f"{'='*70}")
        
        # Final summary
        total_return = ((final_value - self._starting_cash) / self._starting_cash) * 100 if self._starting_cash > 0 else 0
        print(f'\nFinal Value: ${final_value:,.2f}')
        print(f'Return: {total_return:.2f}%')
        
        # Close trade report file
        if self.trade_report_file:
            try:
                self.trade_report_file.write("\n=== SUMMARY ===\n")
                self.trade_report_file.write(f"Total Trades: {total_trades}\n")
                self.trade_report_file.write(f"Wins: {self.wins} | Losses: {self.losses}\n")
                self.trade_report_file.write(f"Win Rate: {win_rate:.1f}%\n")
                self.trade_report_file.write(f"Profit Factor: {profit_factor:.2f}\n")
                self.trade_report_file.write(f"Sharpe Ratio: {sharpe_ratio:.2f}\n")
                self.trade_report_file.write(f"Sortino Ratio: {sortino_ratio:.2f}\n")
                self.trade_report_file.write(f"Max Drawdown: {max_drawdown_pct:.2f}%\n")
                self.trade_report_file.write(f"CAGR: {cagr:.2f}%\n")
                self.trade_report_file.write(f"Net P&L: ${total_pnl:,.2f}\n")
                self.trade_report_file.write(f"Total Commission: ${total_commission:,.2f}\n")
                self.trade_report_file.write(f"Total Return: {total_return:.2f}%\n")
                self.trade_report_file.close()
            except:
                pass
