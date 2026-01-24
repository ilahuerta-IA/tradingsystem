"""
SEDNA Strategy - Bullish Engulfing + KAMA + CCI (optional) + Breakout Window

Based on KOI with these key differences:
1. KAMA on HL2 instead of 5 EMAs ascending
2. CCI calculated on HL2 (with flag to disable completely)
3. ATR filter uses average ATR over N periods

ENTRY SYSTEM (4 PHASES):
1. PATTERN: Bullish engulfing candle detected
2. TREND: EMA(HL2) > KAMA(HL2) - configurable EMA period (default 1 = raw HL2)
3. MOMENTUM: CCI(HL2) > threshold (optional, can be disabled)
4. BREAKOUT: Price breaks pattern HIGH + offset within N candles

EXIT SYSTEM:
- Stop Loss: Entry - (ATR x SL multiplier)
- Take Profit: Entry + (ATR x TP multiplier)
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
    check_atr_filter,
    check_sl_pips_filter,
    check_efficiency_ratio_filter,
)
from lib.indicators import EfficiencyRatio
from lib.position_sizing import calculate_position_size


class KAMA(bt.Indicator):
    """
    Kaufman's Adaptive Moving Average (KAMA).
    
    Uses efficiency ratio to adapt between fast and slow smoothing constants.
    """
    lines = ('kama',)
    params = (
        ('period', 12),      # Efficiency ratio period
        ('fast', 2),         # Fast smoothing constant period
        ('slow', 30),        # Slow smoothing constant period
    )
    
    # Plot on main chart with price (not separate panel)
    plotinfo = dict(
        subplot=False,       # Same panel as price
        plotlinelabels=True,
    )
    plotlines = dict(
        kama=dict(color='purple', linewidth=1.5),
    )
    
    def __init__(self):
        # Calculate smoothing constants
        self.fast_sc = 2.0 / (self.p.fast + 1.0)
        self.slow_sc = 2.0 / (self.p.slow + 1.0)
    
    def nextstart(self):
        # Initialize with SMA
        self.lines.kama[0] = sum(self.data.get(size=self.p.period)) / self.p.period
    
    def next(self):
        # Efficiency Ratio = Change / Volatility
        change = abs(self.data[0] - self.data[-self.p.period])
        volatility = sum(abs(self.data[-i] - self.data[-i-1]) for i in range(self.p.period))
        
        if volatility != 0:
            er = change / volatility
        else:
            er = 0
        
        # Smoothing constant
        sc = (er * (self.fast_sc - self.slow_sc) + self.slow_sc) ** 2
        
        # KAMA
        self.lines.kama[0] = self.lines.kama[-1] + sc * (self.data[0] - self.lines.kama[-1])


class EntryExitLines(bt.Indicator):
    """
    Indicator to plot entry/exit price levels as horizontal dashed lines.
    
    Shows:
    - Entry price (green dashed)
    - Stop Loss level (red dashed)
    - Take Profit level (blue dashed)
    
    Lines persist until position is closed.
    """
    lines = ('entry', 'stop_loss', 'take_profit')
    
    plotinfo = dict(
        subplot=False,  # Plot on price chart
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
        # Values are set externally by the strategy
        pass


class SEDNAStrategy(bt.Strategy):
    """
    SEDNA Strategy implementation.
    
    Based on KOI with:
    - KAMA on HL2 instead of 5 EMAs
    - CCI on HL2 (optional)
    - ATR filter with average ATR
    """
    
    params = dict(
        # KAMA settings (replaces 5 EMAs)
        kama_period=12,
        kama_fast=2,
        kama_slow=30,
        
        # HL2 EMA for KAMA comparison (period=1 means raw HL2)
        hl2_ema_period=1,
        
        # CCI settings
        use_cci_filter=True,  # Flag to enable/disable CCI completely
        cci_period=20,
        cci_threshold=100,
        cci_max_threshold=999,
        
        # ATR for SL/TP
        atr_length=10,
        atr_sl_multiplier=2.0,
        atr_tp_multiplier=10.0,
        
        # Breakout Window
        use_breakout_window=True,
        breakout_window_candles=3,
        breakout_level_offset_pips=5.0,
        
        # === FILTERS ===
        
        # Time Filter
        use_time_filter=False,
        allowed_hours=[],
        
        # SL Pips Filter
        use_sl_pips_filter=False,
        sl_pips_min=5.0,
        sl_pips_max=50.0,
        
        # ATR Filter (uses average ATR)
        use_atr_filter=False,
        atr_min=0.0,
        atr_max=1.0,
        atr_avg_period=20,  # Period for ATR averaging
        
        # === HTF FILTER (Higher Timeframe Trend Detection) ===
        # Uses Efficiency Ratio to filter choppy markets
        # ER close to 1.0 = trending, ER close to 0.0 = choppy
        use_htf_filter=False,
        htf_timeframe_minutes=15,  # Target HTF (used to scale ER period)
        htf_er_period=10,  # ER period on HTF equivalent
        htf_er_threshold=0.35,  # Min ER to allow entry
        
        # === EXIT CONDITIONS ===
        
        # KAMA Exit: Close position when KAMA > EMA (trend reversal)
        use_kama_exit=False,
        
        # === ASSET CONFIG ===
        pip_value=0.01,
        is_jpy_pair=False,
        jpy_rate=150.0,
        lot_size=1,
        is_etf=True,
        margin_pct=20.0,
        
        # Risk
        risk_percent=0.005,
        
        # Debug & Reporting
        print_signals=False,
        export_reports=True,
        
        # Plot options
        plot_entry_exit_lines=True,  # Show entry/SL/TP dashed lines on chart
    )

    def __init__(self):
        d = self.data
        
        # HL2 = (High + Low) / 2
        self.hl2 = (d.high + d.low) / 2.0
        
        # KAMA on HL2 (replaces 5 EMAs)
        self.kama = KAMA(
            self.hl2,
            period=self.p.kama_period,
            fast=self.p.kama_fast,
            slow=self.p.kama_slow
        )
        
        # EMA on HL2 for KAMA comparison (period=1 = raw HL2)
        self.hl2_ema = bt.ind.EMA(self.hl2, period=self.p.hl2_ema_period)
        self.hl2_ema.plotinfo.subplot = False  # Plot on price chart
        self.hl2_ema.plotinfo.plotname = 'HL2 EMA'
        
        # CCI on HL2 (instead of HLC3)
        # CCI = (HL2 - SMA(HL2)) / (0.015 * Mean Deviation)
        self.cci_sma = bt.ind.SMA(self.hl2, period=self.p.cci_period)
        self.cci_sma.plotinfo.plot = False  # Hide from plot (internal use)
        self.cci = bt.ind.CCI(d, period=self.p.cci_period)  # We'll override calculation
        
        # ATR
        self.atr = bt.ind.ATR(d, period=self.p.atr_length)
        
        # HTF Efficiency Ratio (scaled period to simulate higher timeframe)
        # Example: 5m data, HTF=15m -> multiplier=3, ER period=10*3=30 bars
        self.htf_er = None
        if self.p.use_htf_filter:
            base_tf_minutes = 5  # Data timeframe
            htf_multiplier = self.p.htf_timeframe_minutes // base_tf_minutes
            scaled_er_period = self.p.htf_er_period * htf_multiplier
            self.htf_er = EfficiencyRatio(d.close, period=scaled_er_period)
            self.htf_er.plotinfo.plotname = f'ER({self.p.htf_timeframe_minutes}m equiv)'
        
        # Entry/Exit plot lines (dashed lines on chart)
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
        
        # Breakout state machine
        self.state = "SCANNING"
        self.pattern_detected_bar = None
        self.breakout_level = None
        self.pattern_atr = None
        self.pattern_cci = None
        
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
    # CCI ON HL2 CALCULATION
    # =========================================================================
    
    def _calculate_cci_hl2(self) -> float:
        """Calculate CCI using HL2 instead of typical price (HLC3)."""
        try:
            # Get HL2 values for period
            hl2_values = []
            for i in range(self.p.cci_period):
                h = float(self.data.high[-i])
                l = float(self.data.low[-i])
                hl2_values.append((h + l) / 2.0)
            
            # Current HL2
            current_hl2 = (float(self.data.high[0]) + float(self.data.low[0])) / 2.0
            
            # SMA of HL2
            sma_hl2 = sum(hl2_values) / len(hl2_values)
            
            # Mean deviation
            mean_dev = sum(abs(v - sma_hl2) for v in hl2_values) / len(hl2_values)
            
            if mean_dev == 0:
                return 0.0
            
            # CCI
            cci = (current_hl2 - sma_hl2) / (0.015 * mean_dev)
            return cci
        except:
            return 0.0
    
    def _get_average_atr(self) -> float:
        """Get average ATR over the specified period."""
        if len(self.atr_history) < self.p.atr_avg_period:
            return float(self.atr[0]) if not math.isnan(float(self.atr[0])) else 0
        
        recent_atr = self.atr_history[-self.p.atr_avg_period:]
        return sum(recent_atr) / len(recent_atr)

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
            report_path = report_dir / f"SEDNA_trades_{timestamp}.txt"
            self.trade_report_file = open(report_path, 'w', encoding='utf-8')
            self.trade_report_file.write("=== SEDNA STRATEGY TRADE REPORT ===\n")
            self.trade_report_file.write(f"Generated: {datetime.now()}\n")
            self.trade_report_file.write(f"KAMA: period={self.p.kama_period}, fast={self.p.kama_fast}, slow={self.p.kama_slow}\n")
            if self.p.use_cci_filter:
                self.trade_report_file.write(f"CCI (HL2): {self.p.cci_period}/{self.p.cci_threshold}\n")
            else:
                self.trade_report_file.write("CCI: DISABLED\n")
            self.trade_report_file.write(f"Breakout: {self.p.breakout_level_offset_pips}pips, {self.p.breakout_window_candles}bars\n")
            self.trade_report_file.write(f"SL: {self.p.atr_sl_multiplier}x ATR | TP: {self.p.atr_tp_multiplier}x ATR\n")
            if self.p.use_sl_pips_filter:
                self.trade_report_file.write(f"SL Filter: {self.p.sl_pips_min}-{self.p.sl_pips_max} pips\n")
            if self.p.use_atr_filter:
                self.trade_report_file.write(f"ATR Filter: {self.p.atr_min}-{self.p.atr_max} (avg {self.p.atr_avg_period})\n")
            if self.p.use_time_filter:
                self.trade_report_file.write(f"Time Filter: {list(self.p.allowed_hours)}\n")
            if self.p.use_htf_filter:
                self.trade_report_file.write(f"HTF Filter: ER(period={self.p.htf_er_period}, TF={self.p.htf_timeframe_minutes}m) >= {self.p.htf_er_threshold}\n")
            self.trade_report_file.write("\n")
            print(f"Trade report: {report_path}")
        except Exception as e:
            print(f"Trade reporting init failed: {e}")

    def _record_trade_entry(self, dt, entry_price, size, atr, cci, sl_pips):
        """Record entry to trade report file."""
        if not self.trade_report_file:
            return
        try:
            entry = {
                'entry_time': dt,
                'entry_price': entry_price,
                'size': size,
                'atr': atr,
                'cci': cci,
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
            if self.p.use_cci_filter:
                self.trade_report_file.write(f"CCI (HL2): {cci:.2f}\n")
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
        """
        Update entry/exit plot lines on chart.
        
        Args:
            entry_price: Entry price level (or None to clear)
            stop_level: Stop loss level (or None to clear)
            take_level: Take profit level (or None to clear)
        """
        if not self.entry_exit_lines:
            return
        
        # Use NaN to hide line when no position
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
            dt_date = self.data.datetime.date(offset)
            dt_time = self.data.datetime.time(offset)
            return datetime.combine(dt_date, dt_time)
        except Exception:
            return self.data.datetime.datetime(offset)

    # =========================================================================
    # PATTERN DETECTION
    # =========================================================================
    
    def _check_bullish_engulfing(self) -> bool:
        """Check for bullish engulfing pattern (same as KOI)."""
        try:
            prev_open = float(self.data.open[-1])
            prev_close = float(self.data.close[-1])
            if prev_close >= prev_open:
                return False
            
            curr_open = float(self.data.open[0])
            curr_close = float(self.data.close[0])
            if curr_close <= curr_open:
                return False
            
            if curr_open > prev_close or curr_close < prev_open:
                return False
            
            return True
        except:
            return False

    def _check_kama_condition(self) -> bool:
        """Check if EMA(HL2) is above KAMA (replaces 5 EMAs ascending)."""
        try:
            hl2_ema_value = float(self.hl2_ema[0])
            kama_value = float(self.kama[0])
            return hl2_ema_value > kama_value
        except:
            return False

    def _check_kama_exit_condition(self) -> bool:
        """
        Check if KAMA > EMA (trend reversal = exit signal).
        
        This is the INVERSE of entry condition:
        - Entry: EMA > KAMA (bullish)
        - Exit: KAMA > EMA (bearish / trend lost)
        """
        try:
            hl2_ema_value = float(self.hl2_ema[0])
            kama_value = float(self.kama[0])
            return kama_value > hl2_ema_value
        except:
            return False

    def _check_cci_condition(self) -> bool:
        """Check if CCI(HL2) > threshold and < max_threshold."""
        if not self.p.use_cci_filter:
            return True  # CCI disabled, always pass
        
        try:
            cci_val = self._calculate_cci_hl2()
            if cci_val <= self.p.cci_threshold:
                return False
            if cci_val >= self.p.cci_max_threshold:
                return False
            return True
        except:
            return False

    def _check_htf_filter(self) -> bool:
        """
        Check Higher Timeframe Efficiency Ratio filter.
        
        Filters entries when market is too choppy on HTF.
        ER >= threshold = trending market, allow entry.
        ER < threshold = choppy market, block entry.
        """
        if not self.p.use_htf_filter or self.htf_er is None:
            return True
        
        try:
            er_value = float(self.htf_er[0])
            return check_efficiency_ratio_filter(
                er_value=er_value,
                threshold=self.p.htf_er_threshold,
                enabled=True
            )
        except:
            return True  # On error, allow entry

    def _check_entry_conditions(self, dt: datetime) -> bool:
        """Check all entry conditions."""
        if self.position or self.order:
            return False
        
        if not check_time_filter(dt, self.p.allowed_hours, self.p.use_time_filter):
            return False
        
        # HTF filter (Efficiency Ratio on higher timeframe)
        if not self._check_htf_filter():
            return False
        
        if not self._check_bullish_engulfing():
            return False
        
        # KAMA condition (replaces 5 EMAs)
        if not self._check_kama_condition():
            return False
        
        # CCI condition (optional)
        if not self._check_cci_condition():
            return False
        
        return True

    # =========================================================================
    # BREAKOUT STATE MACHINE
    # =========================================================================
    
    def _reset_breakout_state(self):
        """Reset breakout window state."""
        self.state = "SCANNING"
        self.pattern_detected_bar = None
        self.breakout_level = None
        self.pattern_atr = None
        self.pattern_cci = None

    # =========================================================================
    # EXIT EXECUTION
    # =========================================================================
    
    def _execute_kama_exit(self, dt: datetime):
        """
        Execute exit when KAMA crosses above EMA (trend reversal).
        
        Steps:
        1. Cancel pending SL/TP orders (OCA)
        2. Close position at market
        3. Set exit reason for tracking
        """
        # Cancel pending OCA orders
        if self.stop_order:
            self.cancel(self.stop_order)
        if self.limit_order:
            self.cancel(self.limit_order)
        
        # Set exit reason BEFORE closing (for notify_trade)
        self.last_exit_reason = "KAMA_REVERSAL"
        
        # Close position at market
        self.close()
        
        if self.p.print_signals:
            kama_val = float(self.kama[0])
            ema_val = float(self.hl2_ema[0])
            print(f">>> SEDNA KAMA EXIT {dt:%Y-%m-%d %H:%M} "
                  f"KAMA={kama_val:.5f} > EMA={ema_val:.5f}")

    # =========================================================================
    # ENTRY EXECUTION
    # =========================================================================
    
    def _execute_entry(self, dt: datetime, atr_avg: float, cci_now: float):
        """Execute entry with all filters applied."""
        # ATR filter (uses average ATR)
        if not check_atr_filter(atr_avg, self.p.atr_min, self.p.atr_max, self.p.use_atr_filter):
            return
        
        entry_price = float(self.data.close[0])
        self.stop_level = entry_price - (atr_avg * self.p.atr_sl_multiplier)
        self.take_level = entry_price + (atr_avg * self.p.atr_tp_multiplier)
        
        sl_pips = abs(entry_price - self.stop_level) / self.p.pip_value
        
        # SL pips filter
        if not check_sl_pips_filter(sl_pips, self.p.sl_pips_min, self.p.sl_pips_max, self.p.use_sl_pips_filter):
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
        
        self.order = self.buy(size=bt_size)
        
        if self.p.print_signals:
            cci_str = f"CCI={cci_now:.0f}" if self.p.use_cci_filter else "CCI=OFF"
            print(f">>> SEDNA BUY {dt:%Y-%m-%d %H:%M} price={entry_price:.5f} "
                  f"SL={self.stop_level:.5f} TP={self.take_level:.5f} {cci_str} SL_pips={sl_pips:.1f}")
        
        self._record_trade_entry(dt, entry_price, bt_size, atr_avg, cci_now, sl_pips)

    # =========================================================================
    # MAIN LOOP
    # =========================================================================
    
    def next(self):
        """Main loop with breakout window state machine."""
        self._portfolio_values.append(self.broker.get_value())
        
        # Track ATR history for averaging
        current_atr = float(self.atr[0]) if not math.isnan(float(self.atr[0])) else 0
        if current_atr > 0:
            self.atr_history.append(current_atr)
        
        dt = self._get_datetime()
        current_bar = len(self)
        
        if self.order:
            return
        
        if self.position:
            if self.state != "SCANNING":
                self._reset_breakout_state()
            
            # Update plot lines while position is open
            self._update_plot_lines(
                entry_price=self.last_entry_price,
                stop_level=self.stop_level,
                take_level=self.take_level
            )
            
            # Check KAMA exit condition (if enabled)
            if self.p.use_kama_exit and self._check_kama_exit_condition():
                self._execute_kama_exit(dt)
            return
        
        # Get average ATR for this bar
        atr_avg = self._get_average_atr()
        if atr_avg <= 0:
            return
        
        # State machine for breakout window
        if self.p.use_breakout_window:
            if self.state == "SCANNING":
                if self._check_entry_conditions(dt):
                    cci_now = self._calculate_cci_hl2() if self.p.use_cci_filter else 0
                    
                    self.pattern_detected_bar = current_bar
                    offset = self.p.breakout_level_offset_pips * self.p.pip_value
                    self.breakout_level = float(self.data.high[0]) + offset
                    self.pattern_atr = atr_avg  # Use average ATR
                    self.pattern_cci = cci_now
                    self.state = "WAITING_BREAKOUT"
                    return
            
            elif self.state == "WAITING_BREAKOUT":
                bars_since = current_bar - self.pattern_detected_bar
                
                if bars_since > self.p.breakout_window_candles:
                    self._reset_breakout_state()
                    return
                
                if float(self.data.high[0]) > self.breakout_level:
                    self._execute_entry(dt, self.pattern_atr, self.pattern_cci)
                    self._reset_breakout_state()
                    return
        else:
            if self._check_entry_conditions(dt):
                cci_now = self._calculate_cci_hl2() if self.p.use_cci_filter else 0
                self._execute_entry(dt, atr_avg, cci_now)

    # =========================================================================
    # ORDER NOTIFICATIONS
    # =========================================================================
    
    def notify_order(self, order):
        """Order notification with OCA for SL/TP."""
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status == order.Completed:
            if order == self.order:  # Entry order
                self.last_entry_price = order.executed.price
                self.last_entry_bar = len(self)
                
                if self.p.print_signals:
                    print(f"[OK] SEDNA BUY EXECUTED at {order.executed.price:.5f} size={order.executed.size}")

                # Place protective OCA orders
                if self.stop_level and self.take_level:
                    self.stop_order = self.sell(
                        size=order.executed.size,
                        exectype=bt.Order.Stop,
                        price=self.stop_level,
                        oco=self.limit_order
                    )
                    self.limit_order = self.sell(
                        size=order.executed.size,
                        exectype=bt.Order.Limit,
                        price=self.take_level,
                        oco=self.stop_order
                    )
                
                self.order = None

            else:  # Exit order (SL/TP or KAMA exit)
                exit_reason = "UNKNOWN"
                if order.exectype == bt.Order.Stop:
                    exit_reason = "STOP_LOSS"
                elif order.exectype == bt.Order.Limit:
                    exit_reason = "TAKE_PROFIT"
                elif order.exectype == bt.Order.Market:
                    # Market order from self.close() = KAMA exit
                    exit_reason = self.last_exit_reason or "KAMA_REVERSAL"
                
                # Only update if not already set by _execute_kama_exit
                if self.last_exit_reason is None:
                    self.last_exit_reason = exit_reason
                
                if self.p.print_signals:
                    print(f"[EXIT] at {order.executed.price:.5f} reason={exit_reason}")

                # Clear plot lines when position closes
                self._update_plot_lines(None, None, None)
                
                self.stop_order = None
                self.limit_order = None
                self.order = None
                self.stop_level = None
                self.take_level = None

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            is_expected_cancel = (self.stop_order and self.limit_order)
            if not is_expected_cancel and self.p.print_signals:
                print(f"Order {order.getstatusname()}: {order.ref}")
            
            if self.order and order.ref == self.order.ref: self.order = None
            if self.stop_order and order.ref == self.stop_order.ref: self.stop_order = None
            if self.limit_order and order.ref == self.limit_order.ref: self.limit_order = None

    def notify_trade(self, trade):
        """Handle trade close notifications."""
        if not trade.isclosed:
            return
        
        dt = self._get_datetime()
        pnl = trade.pnlcomm
        
        self.trades += 1
        if pnl > 0:
            self.wins += 1
            self.gross_profit += pnl
        else:
            self.losses += 1
            self.gross_loss += abs(pnl)
        
        self._trade_pnls.append({
            'date': dt,
            'year': dt.year,
            'pnl': pnl,
            'is_winner': pnl > 0
        })
        
        reason = getattr(self, 'last_exit_reason', 'UNKNOWN')
        self._record_trade_exit(dt, pnl, reason)

    # =========================================================================
    # STATISTICS
    # =========================================================================
    
    def stop(self):
        """Strategy end - print summary with advanced metrics."""
        final_value = self.broker.get_value()
        total_pnl = final_value - self._starting_cash
        win_rate = (self.wins / self.trades * 100) if self.trades > 0 else 0
        profit_factor = (self.gross_profit / self.gross_loss) if self.gross_loss > 0 else float('inf')
        
        # Max Drawdown
        max_drawdown_pct = 0.0
        if self._portfolio_values:
            peak = self._portfolio_values[0]
            for value in self._portfolio_values:
                if value > peak:
                    peak = value
                drawdown = (peak - value) / peak * 100.0
                if drawdown > max_drawdown_pct:
                    max_drawdown_pct = drawdown
        
        # Sharpe Ratio
        sharpe_ratio = 0.0
        if len(self._portfolio_values) > 10:
            returns = []
            for i in range(1, len(self._portfolio_values)):
                ret = (self._portfolio_values[i] - self._portfolio_values[i-1]) / self._portfolio_values[i-1]
                returns.append(ret)
            
            if len(returns) > 0:
                returns_array = np.array(returns)
                mean_return = np.mean(returns_array)
                std_return = np.std(returns_array)
                periods_per_year = 252 * 24 * 12
                if std_return > 0:
                    sharpe_ratio = (mean_return * periods_per_year) / (std_return * np.sqrt(periods_per_year))
        
        # Sortino Ratio
        sortino_ratio = 0.0
        if len(self._portfolio_values) > 10:
            returns = []
            for i in range(1, len(self._portfolio_values)):
                ret = (self._portfolio_values[i] - self._portfolio_values[i-1]) / self._portfolio_values[i-1]
                returns.append(ret)
            
            if len(returns) > 0:
                returns_array = np.array(returns)
                mean_return = np.mean(returns_array)
                negative_returns = returns_array[returns_array < 0]
                if len(negative_returns) > 0:
                    downside_dev = np.std(negative_returns)
                    periods_per_year = 252 * 24 * 12
                    if downside_dev > 0:
                        sortino_ratio = (mean_return * periods_per_year) / (downside_dev * np.sqrt(periods_per_year))
        
        # CAGR
        cagr = 0.0
        if self._portfolio_values and self._trade_pnls and self._starting_cash > 0:
            total_return = final_value / self._starting_cash
            if total_return > 0:
                first_date = self._trade_pnls[0]['date']
                last_date = self._trade_pnls[-1]['date']
                days = (last_date - first_date).days
                years = max(days / 365.25, 0.1)
                cagr = (pow(total_return, 1.0 / years) - 1.0) * 100.0
        
        # Calmar Ratio
        calmar_ratio = cagr / max_drawdown_pct if max_drawdown_pct > 0 else 0
        
        # Yearly Statistics
        yearly_stats = defaultdict(lambda: {
            'trades': 0, 'wins': 0, 'pnl': 0.0,
            'gross_profit': 0.0, 'gross_loss': 0.0
        })
        
        for trade in self._trade_pnls:
            year = trade['year']
            yearly_stats[year]['trades'] += 1
            yearly_stats[year]['pnl'] += trade['pnl']
            if trade['is_winner']:
                yearly_stats[year]['wins'] += 1
                yearly_stats[year]['gross_profit'] += trade['pnl']
            else:
                yearly_stats[year]['gross_loss'] += abs(trade['pnl'])
        
        # Print Summary
        print("\n" + "=" * 70)
        print("=== SEDNA STRATEGY SUMMARY ===")
        print("=" * 70)
        
        print(f"Total Trades: {self.trades}")
        print(f"Wins: {self.wins} | Losses: {self.losses}")
        print(f"Win Rate: {win_rate:.1f}%")
        print(f"Profit Factor: {profit_factor:.2f}")
        print(f"Gross Profit: ${self.gross_profit:,.2f}")
        print(f"Gross Loss: ${self.gross_loss:,.2f}")
        print(f"Net P&L: ${total_pnl:,.0f}")
        print(f"Final Value: ${final_value:,.0f}")
        
        print(f"\n{'='*70}")
        print("ADVANCED RISK METRICS")
        print(f"{'='*70}")
        print(f"Sharpe Ratio:        {sharpe_ratio:>8.2f}")
        print(f"Sortino Ratio:       {sortino_ratio:>8.2f}")
        print(f"CAGR:                {cagr:>7.2f}%")
        print(f"Max Drawdown:        {max_drawdown_pct:>7.2f}%")
        print(f"Calmar Ratio:        {calmar_ratio:>8.2f}")
        print(f"{'='*70}")
        
        # Yearly Statistics
        print(f"\n{'='*70}")
        print("YEARLY STATISTICS")
        print(f"{'='*70}")
        print(f"{'Year':<6} {'Trades':>7} {'WR%':>7} {'PF':>7} {'PnL':>12}")
        print(f"{'-'*45}")
        
        for year in sorted(yearly_stats.keys()):
            stats = yearly_stats[year]
            wr = (stats['wins'] / stats['trades'] * 100) if stats['trades'] > 0 else 0
            year_pf = (stats['gross_profit'] / stats['gross_loss']) if stats['gross_loss'] > 0 else float('inf')
            print(f"{year:<6} {stats['trades']:>7} {wr:>6.1f}% {year_pf:>7.2f} ${stats['pnl']:>10,.0f}")
        
        print(f"{'='*70}")
        
        # Active filters
        print(f"\n{'='*70}")
        print("STRATEGY CONFIGURATION")
        print(f"{'='*70}")
        print(f"  KAMA: period={self.p.kama_period}, fast={self.p.kama_fast}, slow={self.p.kama_slow}")
        if self.p.use_cci_filter:
            print(f"  CCI (HL2): {self.p.cci_threshold}-{self.p.cci_max_threshold}")
        else:
            print("  CCI: DISABLED")
        if self.p.use_time_filter:
            print(f"  Time Filter: hours {list(self.p.allowed_hours)}")
        if self.p.use_sl_pips_filter:
            print(f"  SL Pips Filter: {self.p.sl_pips_min}-{self.p.sl_pips_max}")
        if self.p.use_atr_filter:
            print(f"  ATR Filter: {self.p.atr_min}-{self.p.atr_max} (avg {self.p.atr_avg_period})")
        print("=" * 70)
        
        # Close report file
        if self.trade_report_file:
            self.trade_report_file.close()
            print(f"\nTrade report saved.")
