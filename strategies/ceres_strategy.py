"""
CERES Strategy v1.0 - Moving Window Consolidation + Breakout (Intraday ETF)

Native ETF intraday strategy. Detects consolidation zones (tight price ranges)
that form at any point during the session, then enters on upward breakout.

The window is "mobile" -- it adapts when price breaks containment bounds.
A break below updates window_low, a break above updates window_high,
and the consolidation counter resets. Once N consecutive bars stay within
the window, the consolidation is confirmed and the strategy arms for breakout.

ENTRY SYSTEM (3 STATES):
    IDLE -> SCANNING -> ARMED -> Entry

1. IDLE: Wait for market open (new trading day)
2. SCANNING: Look for N consecutive contained bars (moving consolidation)
   - If bar breaks below: window_low = bar_low, reset counter
   - If bar breaks above: window_high = bar_high, reset counter
   - If N bars contained: window confirmed -> ARMED
3. ARMED: Wait for close > window_high (breakout)
   - Optional: breakout candle min height filter (breakout_offset_mult)
   - If close < window_low: pattern broken -> back to SCANNING

EXIT SYSTEM:
    - Stop Loss: configurable mode (window_low / fixed_pips / atr_mult) + buffer
    - Take Profit: configurable mode (none / window_height_mult / fixed_pips / atr_mult)
    - EOD Close: forced close before session end

DIRECTION: LONG only
ASSETS: ETFs (GLD, DIA, XLE, XLU, TLT, ...)

Design docs: docs/ceres_strategy.md

v0.9.0: Simplified pullback (close < OR_HH then close > OR_HH).
v1.0.0: Mobile consolidation window. Replaces fixed OR + pullback.
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
    check_sl_pips_filter,
    check_efficiency_ratio_filter,
)
from lib.indicators import EfficiencyRatio
from lib.position_sizing import calculate_position_size


# =========================================================================
# REUSABLE: Window efficiency ratio
# =========================================================================

def calculate_window_efficiency(opens, closes):
    """
    Calculate Efficiency Ratio of a consolidation window.

    ER = |net move| / sum(|individual moves|)
    Low ER = sideways/choppy (good consolidation).
    High ER = directional (poor consolidation).

    Args:
        opens: List of open prices during window
        closes: List of close prices during window

    Returns:
        ER value 0.0 to 1.0
    """
    if len(closes) < 2:
        return 0.0
    change = abs(closes[-1] - opens[0])
    volatility = sum(
        abs(closes[i] - closes[i - 1])
        for i in range(1, len(closes))
    )
    if volatility > 0:
        return change / volatility
    return 0.0


# =========================================================================
# PLOT HELPER
# =========================================================================

class CeresEntryExitLines(bt.Indicator):
    """Plot entry/SL/TP lines on chart."""
    lines = ('entry', 'stop_loss', 'take_profit', 'window_high_line', 'window_low_line')
    plotinfo = dict(subplot=False, plotlinelabels=True)
    plotlines = dict(
        entry=dict(color='green', linestyle='--', linewidth=1.0),
        stop_loss=dict(color='red', linestyle='--', linewidth=1.0),
        take_profit=dict(color='blue', linestyle='--', linewidth=1.0),
        window_high_line=dict(color='orange', linestyle=':', linewidth=0.8),
        window_low_line=dict(color='orange', linestyle=':', linewidth=0.8),
    )
    def __init__(self):
        pass
    def next(self):
        pass


# =========================================================================
# CERES STRATEGY
# =========================================================================

class CERESStrategy(bt.Strategy):
    """
    CERES: Moving Window Consolidation + Breakout for ETFs.

    State machine: IDLE -> SCANNING -> ARMED -> Entry
    """

    params = dict(
        # --- Consolidation Window ---
        delay_bars=0,               # Bars to skip after first bar of day
        consolidation_bars=8,       # N consecutive contained bars to confirm

        # --- Window Quality Filters ---
        use_window_height_filter=False,
        window_height_min=0.0,      # Min window height in pips
        window_height_max=9999.0,   # Max window height in pips

        use_window_er_filter=False,  # ER of the consolidation window
        window_er_min=0.0,
        window_er_max=1.0,

        use_er_htf_filter=False,    # ER in higher timeframe (macro context)
        er_htf_threshold=0.3,
        er_htf_period=10,
        er_htf_timeframe_minutes=60,

        # --- Scan / Armed limits ---
        use_max_scan_bars=False,    # Limit how long the consolidation can last
        max_scan_bars=50,           # Max bars in SCANNING before reset
        use_max_armed_bars=False,   # Limit how long to wait for breakout
        max_armed_bars=30,          # Max bars in ARMED before reset

        # --- Breakout ---
        use_body_breakout=False,    # Require candle body (not wick) above window_high
        breakout_offset_mult=0.0,   # Min candle range / window height (0=disabled)

        # --- Stop Loss ---
        sl_mode='window_low',       # 'window_low' | 'fixed_pips' | 'atr_mult'
        sl_buffer_pips=5.0,
        sl_fixed_pips=30.0,
        sl_atr_mult=1.5,

        # --- Take Profit ---
        tp_mode='none',             # 'none' | 'window_height_mult' | 'fixed_pips' | 'atr_mult'
        tp_window_mult=1.5,
        tp_fixed_pips=50.0,
        tp_atr_mult=2.0,

        # --- EOD Close ---
        use_eod_close=True,
        eod_close_hour=20,
        eod_close_minute=45,

        # --- Standard Filters ---
        use_time_filter=False,
        allowed_hours=[],
        use_day_filter=True,
        allowed_days=[0, 1, 2, 3, 4],

        use_sl_pips_filter=False,
        sl_pips_min=5.0,
        sl_pips_max=200.0,

        # --- ATR ---
        atr_length=14,
        atr_avg_period=20,

        # --- Risk / Asset ---
        risk_percent=0.0075,
        pip_value=0.01,
        is_jpy_pair=False,
        jpy_rate=1.0,
        lot_size=1,
        is_etf=True,
        margin_pct=20.0,

        # --- Debug ---
        print_signals=False,
        export_reports=True,
        plot_entry_exit_lines=True,
    )

    # =====================================================================
    # INIT
    # =====================================================================

    def __init__(self):
        self.atr = bt.ind.ATR(self.data, period=self.p.atr_length)

        # HTF ER (optional)
        self.htf_er = None
        if self.p.use_er_htf_filter:
            base_tf_minutes = 5
            htf_mult = self.p.er_htf_timeframe_minutes // base_tf_minutes
            scaled_period = self.p.er_htf_period * htf_mult
            self.htf_er = EfficiencyRatio(self.data.close, period=scaled_period)
            self.htf_er.plotinfo.plotname = (
                'ER(%dm equiv)' % self.p.er_htf_timeframe_minutes
            )

        # Plot lines
        if self.p.plot_entry_exit_lines:
            self.entry_exit_lines = CeresEntryExitLines(self.data)
        else:
            self.entry_exit_lines = None

        # State machine
        self.state = "IDLE"

        # Window tracking
        self.window_high = None
        self.window_low = None
        self.window_height = None
        self.window_er = None
        self.window_atr_avg = None
        self.consol_count = 0
        self.scan_bar_count = 0
        self.window_closes = []
        self.window_opens = []

        # Day-start detection (DST-agnostic)
        self._day_first_bar_seen = False
        self._delay_bars_remaining = 0

        # ARMED state tracking
        self.armed_bar_count = 0

        # Order management
        self.order = None
        self.stop_order = None
        self.limit_order = None
        self.stop_level = None
        self.take_level = None
        self.last_entry_price = None
        self.last_entry_bar = None
        self.last_exit_reason = None
        self._entry_fill_bar = -1

        # Day tracking (max 1 trade per day)
        self._today_date = None
        self._traded_today = False

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
        self._first_bar_dt = None
        self._last_bar_dt = None
        self.trade_reports = []
        self.trade_report_file = None
        self._current_trade_idx = None

        self._init_trade_reporting()

    # =====================================================================
    # TRADE REPORTING
    # =====================================================================

    def _init_trade_reporting(self):
        """Initialize trade report file with full configuration header."""
        if not self.p.export_reports:
            return
        try:
            report_dir = Path("logs")
            report_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_path = report_dir / ("CERES_trades_%s.txt" % timestamp)
            self.trade_report_file = open(report_path, 'w', encoding='utf-8')
            f = self.trade_report_file

            f.write("=== CERES STRATEGY TRADE REPORT (v1.0) ===\n")
            f.write("Generated: %s\n" % datetime.now())
            f.write("\n")

            # Consolidation Window config
            f.write("Consolidation: %d bars, delay=%d bars after open\n" % (
                self.p.consolidation_bars, self.p.delay_bars))

            # Quality filters
            if self.p.use_window_height_filter:
                f.write("Window Height Filter: ENABLED | Range: %.1f-%.1f pips\n" % (
                    self.p.window_height_min, self.p.window_height_max))
            else:
                f.write("Window Height Filter: DISABLED\n")

            if self.p.use_window_er_filter:
                f.write("Window ER Filter: ENABLED | Range: %.2f-%.2f\n"
                        % (self.p.window_er_min, self.p.window_er_max))
            else:
                f.write("Window ER Filter: DISABLED\n")

            if self.p.use_er_htf_filter:
                f.write("ER HTF Filter: ENABLED | Threshold: %.2f, Period: %d, TF: %dm\n" % (
                    self.p.er_htf_threshold, self.p.er_htf_period,
                    self.p.er_htf_timeframe_minutes))
            else:
                f.write("ER HTF Filter: DISABLED\n")

            # Scan / Armed limits
            if self.p.use_max_scan_bars:
                f.write("Max Scan Bars: ENABLED | Max: %d\n" % self.p.max_scan_bars)
            else:
                f.write("Max Scan Bars: DISABLED\n")
            if self.p.use_max_armed_bars:
                f.write("Max Armed Bars: ENABLED | Max: %d\n" % self.p.max_armed_bars)
            else:
                f.write("Max Armed Bars: DISABLED\n")

            # Breakout
            f.write("Body Breakout: %s\n" % ("ENABLED" if self.p.use_body_breakout else "DISABLED"))
            if self.p.breakout_offset_mult > 0:
                f.write("Breakout Offset: %.2f (min candle/window_height)\n"
                        % self.p.breakout_offset_mult)
            else:
                f.write("Breakout Offset: DISABLED (any close > window_high)\n")

            # SL / TP
            f.write("SL Mode: %s | Buffer: %.1f pips" % (
                self.p.sl_mode, self.p.sl_buffer_pips))
            if self.p.sl_mode == 'fixed_pips':
                f.write(" | Fixed: %.1f pips" % self.p.sl_fixed_pips)
            elif self.p.sl_mode == 'atr_mult':
                f.write(" | ATR Mult: %.1f" % self.p.sl_atr_mult)
            f.write("\n")

            f.write("TP Mode: %s" % self.p.tp_mode)
            if self.p.tp_mode == 'window_height_mult':
                f.write(" | Window Mult: %.1f" % self.p.tp_window_mult)
            elif self.p.tp_mode == 'fixed_pips':
                f.write(" | Fixed: %.1f pips" % self.p.tp_fixed_pips)
            elif self.p.tp_mode == 'atr_mult':
                f.write(" | ATR Mult: %.1f" % self.p.tp_atr_mult)
            f.write("\n")

            # EOD
            if self.p.use_eod_close:
                f.write("EOD Close: %d:%02d UTC\n" % (
                    self.p.eod_close_hour, self.p.eod_close_minute))
            else:
                f.write("EOD Close: DISABLED\n")

            # Standard filters
            if self.p.use_sl_pips_filter:
                f.write("SL Pips Filter: ENABLED | Range: %.1f-%.1f\n" % (
                    self.p.sl_pips_min, self.p.sl_pips_max))
            else:
                f.write("SL Pips Filter: DISABLED\n")

            if self.p.use_time_filter:
                f.write("Time Filter: %s\n" % list(self.p.allowed_hours))
            else:
                f.write("Time Filter: DISABLED\n")

            if self.p.use_day_filter:
                f.write("Day Filter: %s\n" % list(self.p.allowed_days))
            else:
                f.write("Day Filter: DISABLED\n")

            # Risk
            f.write("Pip Value: %s\n" % self.p.pip_value)
            f.write("Risk: %.2f%%\n" % (self.p.risk_percent * 100))
            f.write("ATR: length=%d, avg_period=%d\n" % (
                self.p.atr_length, self.p.atr_avg_period))

            f.write("=" * 80 + "\n\n")
            f.flush()
            print("Trade report: %s" % report_path)
        except Exception as e:
            print("Trade reporting init failed: %s" % e)

    def _record_trade_entry(self, dt, entry_price, size, atr_avg, sl_pips,
                            window_high, window_low, window_height,
                            window_er, window_atr_avg,
                            consol_bars, scan_bars, armed_bars,
                            breakout_candle_height):
        """Record entry details to log and trade_reports list."""
        entry = {
            'entry_time': dt,
            'entry_price': entry_price,
            'size': size,
            'atr_avg': atr_avg,
            'sl_pips': sl_pips,
            'stop_level': self.stop_level,
            'take_level': self.take_level,
            'window_high': window_high,
            'window_low': window_low,
            'window_height': window_height,
            'window_er': window_er,
            'window_atr_avg': window_atr_avg,
            'sl_mode': self.p.sl_mode,
            'tp_mode': self.p.tp_mode,
            'consol_bars': consol_bars,
            'scan_bars': scan_bars,
            'armed_bars': armed_bars,
            'breakout_candle_height': breakout_candle_height,
        }
        self.trade_reports.append(entry)
        self._current_trade_idx = len(self.trade_reports) - 1

        if not self.trade_report_file:
            return
        try:
            f = self.trade_report_file
            f.write("ENTRY #%d\n" % len(self.trade_reports))
            f.write("Time: %s\n" % dt.strftime('%Y-%m-%d %H:%M:%S'))
            f.write("Entry Price: %.5f\n" % entry_price)
            f.write("Stop Loss: %.5f\n" % self.stop_level)
            if self.take_level:
                f.write("Take Profit: %.5f\n" % self.take_level)
            else:
                f.write("Take Profit: NONE (EOD)\n")
            f.write("SL Pips: %.1f\n" % sl_pips)
            f.write("ATR (avg): %.6f\n" % atr_avg)
            f.write("Window High: %.5f\n" % window_high)
            f.write("Window Low: %.5f\n" % window_low)
            f.write("Window Height: %.5f\n" % window_height)
            f.write("Window ER: %.4f\n" % window_er)
            f.write("Window ATR Avg: %.6f\n" % window_atr_avg)
            f.write("SL Mode: %s\n" % self.p.sl_mode)
            f.write("TP Mode: %s\n" % self.p.tp_mode)
            f.write("Consolidation Bars: %d\n" % consol_bars)
            f.write("Scan Bars: %d\n" % scan_bars)
            f.write("Armed Bars: %d\n" % armed_bars)
            f.write("Breakout Candle: %.5f\n" % breakout_candle_height)
            f.write("-" * 50 + "\n\n")
            f.flush()
        except Exception:
            pass

    def _record_trade_exit(self, dt, pnl, reason):
        """Record exit details to log and trade_reports list."""
        if self._current_trade_idx is None:
            return
        if self._current_trade_idx < len(self.trade_reports):
            last_trade = self.trade_reports[self._current_trade_idx]
            last_trade['pnl'] = pnl
            last_trade['exit_reason'] = reason
            last_trade['exit_time'] = dt

        if not self.trade_report_file:
            self._current_trade_idx = None
            return
        try:
            f = self.trade_report_file
            f.write("EXIT #%d\n" % (self._current_trade_idx + 1))
            f.write("Time: %s\n" % dt.strftime('%Y-%m-%d %H:%M:%S'))
            f.write("Exit Reason: %s\n" % reason)
            f.write("P&L: $%.2f\n" % pnl)
            f.write("=" * 80 + "\n\n")
            f.flush()
        except Exception:
            pass
        self._current_trade_idx = None

    # =====================================================================
    # HELPERS
    # =====================================================================

    def _get_datetime(self, offset=0):
        """Get current bar datetime."""
        try:
            dt_date = self.data.datetime.date(offset)
            dt_time = self.data.datetime.time(offset)
            return datetime.combine(dt_date, dt_time)
        except Exception:
            return self.data.datetime.datetime(offset)

    def _get_average_atr(self):
        """Get average ATR over configured period."""
        if len(self.atr_history) < self.p.atr_avg_period:
            val = float(self.atr[0])
            return val if not math.isnan(val) else 0
        recent = self.atr_history[-self.p.atr_avg_period:]
        return sum(recent) / len(recent)

    def _update_plot_lines(self, entry=None, sl=None, tp=None, hh=None, ll=None):
        """Update plot overlay lines."""
        if not self.entry_exit_lines:
            return
        nan = float('nan')
        self.entry_exit_lines.lines.entry[0] = entry if entry else nan
        self.entry_exit_lines.lines.stop_loss[0] = sl if sl else nan
        self.entry_exit_lines.lines.take_profit[0] = tp if tp else nan
        self.entry_exit_lines.lines.window_high_line[0] = hh if hh else nan
        self.entry_exit_lines.lines.window_low_line[0] = ll if ll else nan

    def _is_day_scan_ready(self):
        """Check if we should start scanning (first bar of day + delay).

        DST-agnostic: detects day change from data, not from clock.
        Uses delay_bars param to skip N bars after first bar of day.
        """
        if not self._day_first_bar_seen:
            return False
        if self._delay_bars_remaining > 0:
            self._delay_bars_remaining -= 1
            return False
        return True

    def _reset_state(self):
        """Full reset to IDLE -- end of day or after entry."""
        self.state = "IDLE"
        self.window_high = None
        self.window_low = None
        self.window_height = None
        self.window_er = None
        self.window_atr_avg = None
        self.consol_count = 0
        self.scan_bar_count = 0
        self.window_closes = []
        self.window_opens = []
        self.armed_bar_count = 0

    def _soft_reset_window(self):
        """Reset window bounds while staying in SCANNING state."""
        self.window_high = None
        self.window_low = None
        self.window_height = None
        self.window_er = None
        self.consol_count = 0
        self.window_closes = []
        self.window_opens = []

    def _init_window_from_bar(self):
        """Initialize consolidation window from current bar.

        Returns True if window was initialized, False if rejected (too wide).
        """
        bar_high = float(self.data.high[0])
        bar_low = float(self.data.low[0])
        bar_close = float(self.data.close[0])
        bar_open = float(self.data.open[0])

        self.window_high = bar_high
        self.window_low = bar_low
        self.window_height = bar_high - bar_low
        self.consol_count = 1
        self.window_closes = [bar_close]
        self.window_opens = [bar_open]

        # Early rejection: single bar wider than max
        if self.p.use_window_height_filter and self.window_height > 0:
            height_pips = self.window_height / self.p.pip_value
            if height_pips > self.p.window_height_max:
                self._soft_reset_window()
                return False
        return True

    # =====================================================================
    # EOD CLOSE
    # =====================================================================

    def _check_eod_close(self, dt):
        """Check and execute EOD forced close."""
        if not self.p.use_eod_close:
            return False
        if self.p.eod_close_hour is None or self.p.eod_close_minute is None:
            return False

        current_minutes = dt.hour * 60 + dt.minute
        eod_minutes = self.p.eod_close_hour * 60 + self.p.eod_close_minute

        if current_minutes >= eod_minutes:
            self.last_exit_reason = "EOD_CLOSE"
            if self.stop_order:
                self.cancel(self.stop_order)
                self.stop_order = None
            if self.limit_order:
                self.cancel(self.limit_order)
                self.limit_order = None
            self.close()

            if self.p.print_signals:
                print(
                    '%s [%s] === EOD CLOSE @ %.2f (forced %d:%02d UTC) ==='
                    % (dt, self.data._name, self.data.close[0],
                       self.p.eod_close_hour, self.p.eod_close_minute)
                )
            return True
        return False

    # =====================================================================
    # QUALITY FILTERS
    # =====================================================================

    def _check_window_quality(self):
        """
        Check all optional quality filters on the confirmed consolidation window.
        Returns True if window passes all active filters (or all are disabled).
        """
        # Window Height filter (in pips)
        if self.p.use_window_height_filter:
            if self.window_height is None:
                return False
            height_pips = self.window_height / self.p.pip_value
            if not (self.p.window_height_min <= height_pips <= self.p.window_height_max):
                if self.p.print_signals:
                    dt = self._get_datetime()
                    print('%s [%s] WINDOW REJECTED: height=%.1f pips (need %.1f-%.1f)'
                          % (dt, self.data._name, height_pips,
                             self.p.window_height_min, self.p.window_height_max))
                return False

        # ER of the consolidation window
        if self.p.use_window_er_filter:
            if self.window_er is None:
                return False
            if not (self.p.window_er_min <= self.window_er <= self.p.window_er_max):
                if self.p.print_signals:
                    dt = self._get_datetime()
                    print('%s [%s] WINDOW REJECTED: er=%.4f (need %.2f-%.2f)'
                          % (dt, self.data._name, self.window_er,
                             self.p.window_er_min, self.p.window_er_max))
                return False

        # ER in higher timeframe
        if self.p.use_er_htf_filter:
            if self.htf_er is not None:
                er_val = float(self.htf_er[0])
                if not check_efficiency_ratio_filter(
                    er_val, self.p.er_htf_threshold, True
                ):
                    if self.p.print_signals:
                        dt = self._get_datetime()
                        print('%s [%s] WINDOW REJECTED: er_htf=%.4f (need >= %.2f)'
                              % (dt, self.data._name, er_val,
                                 self.p.er_htf_threshold))
                    return False

        return True

    # =====================================================================
    # SL / TP CALCULATION
    # =====================================================================

    def _calculate_sl(self, entry_price, atr_avg):
        """Calculate stop loss price based on configured mode."""
        if self.p.sl_mode in ('window_low', 'or_low'):
            base = self.window_low
        elif self.p.sl_mode == 'fixed_pips':
            base = entry_price - (self.p.sl_fixed_pips * self.p.pip_value)
        elif self.p.sl_mode == 'atr_mult':
            base = entry_price - (atr_avg * self.p.sl_atr_mult)
        else:
            base = self.window_low  # Default fallback

        # Apply buffer
        sl_price = base - (self.p.sl_buffer_pips * self.p.pip_value)
        return sl_price

    def _calculate_tp(self, entry_price, atr_avg):
        """Calculate take profit price based on configured mode. None = no TP."""
        if self.p.tp_mode == 'none':
            return None
        elif self.p.tp_mode in ('window_height_mult', 'or_height_mult'):
            return entry_price + (self.window_height * self.p.tp_window_mult)
        elif self.p.tp_mode == 'fixed_pips':
            return entry_price + (self.p.tp_fixed_pips * self.p.pip_value)
        elif self.p.tp_mode == 'atr_mult':
            return entry_price + (atr_avg * self.p.tp_atr_mult)
        return None

    # =====================================================================
    # ENTRY EXECUTION
    # =====================================================================

    def _execute_entry(self, dt, atr_avg, breakout_candle_height):
        """Validate filters, size position, and send buy order."""

        # Day/Time filter (applied at entry, not globally)
        if not check_day_filter(dt, self.p.allowed_days, self.p.use_day_filter):
            if self.p.print_signals:
                print('%s [%s] ENTRY SKIPPED: day %s not in allowed_days'
                      % (dt, self.data._name, dt.strftime('%A')))
            return
        if not check_time_filter(dt, self.p.allowed_hours, self.p.use_time_filter):
            if self.p.print_signals:
                print('%s [%s] ENTRY SKIPPED: hour %d not in allowed_hours'
                      % (dt, self.data._name, dt.hour))
            return

        entry_price = float(self.data.close[0])

        # Calculate SL/TP
        self.stop_level = self._calculate_sl(entry_price, atr_avg)
        self.take_level = self._calculate_tp(entry_price, atr_avg)

        # SL sanity: must be below entry
        if self.stop_level >= entry_price:
            if self.p.print_signals:
                print('%s [%s] ENTRY SKIPPED: SL %.5f >= entry %.5f'
                      % (dt, self.data._name, self.stop_level, entry_price))
            return

        # SL pips filter
        sl_pips = abs(entry_price - self.stop_level) / self.p.pip_value
        if not check_sl_pips_filter(
            sl_pips, self.p.sl_pips_min, self.p.sl_pips_max,
            self.p.use_sl_pips_filter
        ):
            if self.p.print_signals:
                print('%s [%s] ENTRY SKIPPED: sl_pips=%.1f out of range'
                      % (dt, self.data._name, sl_pips))
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

        # Send buy order
        self.order = self.buy(size=bt_size)
        self._traded_today = True

        # Record
        self._record_trade_entry(
            dt, entry_price, bt_size, atr_avg, sl_pips,
            self.window_high, self.window_low, self.window_height,
            self.window_er if self.window_er else 0.0,
            self.window_atr_avg if self.window_atr_avg else 0.0,
            self.consol_count, self.scan_bar_count,
            self.armed_bar_count, breakout_candle_height,
        )

        if self.p.print_signals:
            print(
                '%s [%s] ENTRY LONG @ %.5f | SL=%.5f (%s) | TP=%s | '
                'Window H=%.5f L=%.5f Height=%.5f'
                % (dt, self.data._name, entry_price, self.stop_level,
                   self.p.sl_mode,
                   ('%.5f' % self.take_level) if self.take_level else 'EOD',
                   self.window_high, self.window_low, self.window_height)
            )

    # =====================================================================
    # MAIN LOOP
    # =====================================================================

    def next(self):
        self._portfolio_values.append(self.broker.get_value())

        # Track ATR
        current_atr = float(self.atr[0]) if not math.isnan(float(self.atr[0])) else 0
        if current_atr > 0:
            self.atr_history.append(current_atr)

        dt = self._get_datetime()
        if self._first_bar_dt is None:
            self._first_bar_dt = dt
        self._last_bar_dt = dt

        # Day change detection -> reset daily tracking
        today = dt.date()
        if today != self._today_date:
            # Force-close any overnight position (DST-safe EOD)
            if self.position and self.p.use_eod_close:
                self.last_exit_reason = "EOD_CLOSE"
                if self.stop_order:
                    self.cancel(self.stop_order)
                    self.stop_order = None
                if self.limit_order:
                    self.cancel(self.limit_order)
                    self.limit_order = None
                self.order = self.close()
                if self.p.print_signals:
                    print('%s [%s] === EOD CLOSE (day change) @ %.2f ==='
                          % (dt, self.data._name, self.data.close[0]))

            if self.order:
                self._today_date = today
                return

            self._today_date = today
            self._traded_today = False
            self._day_first_bar_seen = True
            self._delay_bars_remaining = self.p.delay_bars
            # If day changes while in SCANNING or ARMED, reset
            if self.state in ("SCANNING", "ARMED"):
                self._reset_state()

        # Pending order? Wait.
        if self.order:
            return

        # --- POSITION OPEN: manage exits ---
        if self.position:
            # EOD close (skip on entry bar to avoid immediate close)
            if len(self) != self._entry_fill_bar and self._check_eod_close(dt):
                return

            # Reset state machine if still scanning/armed
            if self.state != "IDLE":
                self._reset_state()

            # Update plot lines
            self._update_plot_lines(
                self.last_entry_price, self.stop_level, self.take_level,
                self.window_high, self.window_low
            )
            return

        # --- NO POSITION: run state machine ---

        # Already traded today? Wait for tomorrow.
        if self._traded_today:
            return

        atr_avg = self._get_average_atr()
        if atr_avg <= 0:
            return

        # Stop scanning at EOD time (no point entering right before close)
        if self.state in ("SCANNING", "ARMED"):
            if self.p.use_eod_close:
                current_minutes = dt.hour * 60 + dt.minute
                eod_minutes = self.p.eod_close_hour * 60 + self.p.eod_close_minute
                if current_minutes >= eod_minutes:
                    self._reset_state()
                    return

        # ---- STATE: IDLE ----
        if self.state == "IDLE":
            if self._is_day_scan_ready():
                self._day_first_bar_seen = False  # consumed
                self.state = "SCANNING"
                self.scan_bar_count = 1

                # Initialize window from first bar
                if not self._init_window_from_bar():
                    # Bar too wide, window reset. Next bar will re-init.
                    pass

                if self.p.print_signals:
                    print('%s [%s] SCANNING: looking for %d-bar consolidation'
                          % (dt, self.data._name, self.p.consolidation_bars))

        # ---- STATE: SCANNING ----
        elif self.state == "SCANNING":
            self.scan_bar_count += 1

            bar_high = float(self.data.high[0])
            bar_low = float(self.data.low[0])
            bar_close = float(self.data.close[0])
            bar_open = float(self.data.open[0])

            # Re-init after soft reset (window_high is None)
            if self.window_high is None:
                self._init_window_from_bar()
                return

            # Update plot: show window levels while scanning
            self._update_plot_lines(hh=self.window_high, ll=self.window_low)

            # Check containment: bar must stay within window bounds
            break_above = bar_high > self.window_high
            break_below = bar_low < self.window_low

            if break_above or break_below:
                # Window broken -- adapt bounds, reset counter
                if break_above:
                    self.window_high = bar_high
                if break_below:
                    self.window_low = bar_low
                self.window_height = self.window_high - self.window_low
                self.consol_count = 1
                self.window_closes = [bar_close]
                self.window_opens = [bar_open]

                # Early rejection: window too wide after break
                if self.p.use_window_height_filter:
                    height_pips = self.window_height / self.p.pip_value
                    if height_pips > self.p.window_height_max:
                        self._soft_reset_window()

                if self.p.print_signals and self.window_high is not None:
                    print('%s [%s] WINDOW BREAK: H=%.5f L=%.5f Height=%.1f pips'
                          % (dt, self.data._name, self.window_high,
                             self.window_low,
                             self.window_height / self.p.pip_value))
            else:
                # Bar contained -- increment counter
                self.consol_count += 1
                self.window_closes.append(bar_close)
                self.window_opens.append(bar_open)

                if self.consol_count >= self.p.consolidation_bars:
                    # Consolidation confirmed!
                    self.window_height = self.window_high - self.window_low

                    # Compute ER of the window
                    if len(self.window_closes) >= 2:
                        self.window_er = calculate_window_efficiency(
                            self.window_opens, self.window_closes,
                        )
                    else:
                        self.window_er = 0.0

                    # Store ATR average at window completion
                    self.window_atr_avg = atr_avg

                    if self.p.print_signals:
                        print(
                            '%s [%s] CONSOLIDATION CONFIRMED: H=%.5f L=%.5f '
                            'Height=%.1f pips ER=%.4f (%d bars, scan=%d)'
                            % (dt, self.data._name, self.window_high,
                               self.window_low,
                               self.window_height / self.p.pip_value,
                               self.window_er, self.consol_count,
                               self.scan_bar_count))

                    # Quality check
                    if self._check_window_quality():
                        self.state = "ARMED"
                        self.armed_bar_count = 0
                        if self.p.print_signals:
                            print('%s [%s] ARMED: waiting breakout > %.5f'
                                  % (dt, self.data._name, self.window_high))
                    else:
                        # Window rejected by quality filter -- start fresh
                        self._soft_reset_window()

            # Max scan bars limit: if consolidation takes too long, reset
            if (self.state == "SCANNING" and self.p.use_max_scan_bars
                    and self.scan_bar_count > self.p.max_scan_bars):
                if self.p.print_signals:
                    print('%s [%s] SCAN TIMEOUT: %d bars > max %d'
                          % (dt, self.data._name, self.scan_bar_count,
                             self.p.max_scan_bars))
                self._soft_reset_window()

        # ---- STATE: ARMED (waiting breakout above window high) ----
        elif self.state == "ARMED":
            self.armed_bar_count += 1

            # Update plot: show window levels while armed
            self._update_plot_lines(hh=self.window_high, ll=self.window_low)

            bar_high = float(self.data.high[0])
            bar_low = float(self.data.low[0])
            bar_close = float(self.data.close[0])

            # Check breakout above window high
            # Body breakout: require min(open, close) above window_high
            bar_open = float(self.data.open[0])
            body_low = min(bar_open, bar_close)

            if self.p.use_body_breakout:
                breakout_ok = body_low > self.window_high
            else:
                breakout_ok = bar_close > self.window_high

            if breakout_ok:
                # Breakout detected! Check candle size filter
                candle_height = bar_high - bar_low
                min_candle = self.p.breakout_offset_mult * self.window_height

                if self.p.breakout_offset_mult <= 0 or candle_height >= min_candle:
                    if self.p.print_signals:
                        print('%s [%s] BREAKOUT: close=%.5f > window=%.5f, '
                              'candle=%.1f pips (min=%.1f)'
                              % (dt, self.data._name, bar_close,
                                 self.window_high,
                                 candle_height / self.p.pip_value,
                                 min_candle / self.p.pip_value))
                    self._execute_entry(dt, atr_avg, candle_height)
                    self._reset_state()
                    return
                else:
                    if self.p.print_signals:
                        print('%s [%s] BREAKOUT REJECTED: candle=%.1f pips '
                              '< min=%.1f pips'
                              % (dt, self.data._name,
                                 candle_height / self.p.pip_value,
                                 min_candle / self.p.pip_value))

            # Max armed bars limit: waited too long for breakout, reset
            if (self.p.use_max_armed_bars
                    and self.armed_bar_count > self.p.max_armed_bars):
                if self.p.print_signals:
                    print('%s [%s] ARMED TIMEOUT: %d bars > max %d'
                          % (dt, self.data._name, self.armed_bar_count,
                             self.p.max_armed_bars))
                self.state = "SCANNING"
                self._soft_reset_window()
                self.armed_bar_count = 0
                return

            # Check if pattern broken (close below window low)
            if bar_close < self.window_low:
                if self.p.print_signals:
                    print('%s [%s] PATTERN BROKEN: close=%.5f < window_low=%.5f'
                          % (dt, self.data._name, bar_close, self.window_low))
                self.state = "SCANNING"
                self._soft_reset_window()
                self.armed_bar_count = 0

    # =====================================================================
    # ORDER / TRADE NOTIFICATIONS
    # =====================================================================

    def notify_order(self, order):
        """Handle order status changes."""
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status == order.Completed:
            if order == self.order and order.isbuy():
                # Entry fill
                self.last_entry_price = order.executed.price
                self.last_entry_bar = len(self)
                self._entry_fill_bar = len(self)

                # Place SL (and TP if configured)
                if self.take_level:
                    self.limit_order = self.sell(
                        size=order.executed.size,
                        exectype=bt.Order.Limit,
                        price=self.take_level,
                    )
                    self.stop_order = self.sell(
                        size=order.executed.size,
                        exectype=bt.Order.Stop,
                        price=self.stop_level,
                        oco=self.limit_order,
                    )
                else:
                    # SL only, no TP
                    self.stop_order = self.sell(
                        size=order.executed.size,
                        exectype=bt.Order.Stop,
                        price=self.stop_level,
                    )

                self.order = None

                if self.p.print_signals:
                    dt = self._get_datetime()
                    print(
                        '%s [%s] ORDER FILLED @ %.5f | SL=%.5f TP=%s'
                        % (dt, self.data._name, order.executed.price,
                           self.stop_level,
                           ('%.5f' % self.take_level) if self.take_level else 'EOD')
                    )

            else:
                # Exit fill
                exec_price = order.executed.price
                exit_reason = self.last_exit_reason

                if exit_reason is None:
                    if self.last_entry_price is not None:
                        delta = exec_price - self.last_entry_price
                        if delta > 0:
                            exit_reason = "TAKE_PROFIT"
                        elif delta < 0:
                            exit_reason = "STOP_LOSS"
                        else:
                            exit_reason = "BREAKEVEN"
                    elif order.exectype == bt.Order.Market:
                        exit_reason = "EOD_CLOSE"

                if self.last_exit_reason is None:
                    self.last_exit_reason = exit_reason

                if self.p.print_signals:
                    dt = self._get_datetime()
                    print('%s [%s] EXIT @ %.5f reason=%s'
                          % (dt, self.data._name, exec_price, exit_reason))

                # Clear
                self._update_plot_lines()
                self.stop_order = None
                self.limit_order = None
                self.order = None
                self.stop_level = None
                self.take_level = None

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            is_expected_cancel = (self.stop_order and self.limit_order)
            if not is_expected_cancel and self.p.print_signals:
                print("Order %s: ref=%d" % (order.getstatusname(), order.ref))

            if self.order and order.ref == self.order.ref:
                # Entry rejected -> allow re-entry today
                self._traded_today = False
                # Entry rejected -> write orphan exit
                if self._current_trade_idx is not None and self.trade_report_file:
                    f = self.trade_report_file
                    f.write("EXIT #%d\n" % (self._current_trade_idx + 1))
                    f.write("Time: N/A\n")
                    f.write("Exit Reason: %s\n" % order.getstatusname())
                    f.write("P&L: $0.00\n")
                    f.write("=" * 80 + "\n\n")
                    f.flush()
                self._current_trade_idx = None
                self.order = None

            if self.stop_order and order.ref == self.stop_order.ref:
                self.stop_order = None
            if self.limit_order and order.ref == self.limit_order.ref:
                self.limit_order = None

    def notify_trade(self, trade):
        """Handle trade close -> stats + logging."""
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
            'is_winner': pnl > 0,
        })

        # Determine exit reason
        last_reason = getattr(self, 'last_exit_reason', None)
        if last_reason and last_reason in ('EOD_CLOSE',):
            reason = last_reason
        elif pnl > 0:
            reason = "TAKE_PROFIT"
        else:
            reason = "STOP_LOSS"

        self._record_trade_exit(dt, pnl, reason)
        self.last_exit_reason = None

    # =====================================================================
    # STATISTICS (stop)
    # =====================================================================

    def stop(self):
        """Strategy end -- print summary with advanced metrics."""
        final_value = self.broker.get_value()
        total_pnl = final_value - self._starting_cash
        win_rate = (self.wins / self.trades * 100) if self.trades > 0 else 0
        profit_factor = (
            (self.gross_profit / self.gross_loss)
            if self.gross_loss > 0 else float('inf')
        )

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

        # Data-driven periods_per_year
        if self._first_bar_dt and self._last_bar_dt:
            data_days = (self._last_bar_dt - self._first_bar_dt).days
            data_years = max(data_days / 365.25, 0.1)
            periods_per_year = len(self._portfolio_values) / data_years
        else:
            periods_per_year = 252 * 24 * 12

        # Sharpe Ratio
        sharpe_ratio = 0.0
        if len(self._portfolio_values) > 10:
            returns = []
            for i in range(1, len(self._portfolio_values)):
                ret = (
                    (self._portfolio_values[i] - self._portfolio_values[i - 1])
                    / self._portfolio_values[i - 1]
                )
                returns.append(ret)
            if returns:
                arr = np.array(returns)
                mean_r = np.mean(arr)
                std_r = np.std(arr)
                if std_r > 0:
                    sharpe_ratio = (
                        (mean_r * periods_per_year)
                        / (std_r * np.sqrt(periods_per_year))
                    )

        # Sortino Ratio
        sortino_ratio = 0.0
        if len(self._portfolio_values) > 10:
            returns = []
            for i in range(1, len(self._portfolio_values)):
                ret = (
                    (self._portfolio_values[i] - self._portfolio_values[i - 1])
                    / self._portfolio_values[i - 1]
                )
                returns.append(ret)
            if returns:
                arr = np.array(returns)
                mean_r = np.mean(arr)
                neg = arr[arr < 0]
                if len(neg) > 0:
                    dd_dev = np.std(neg)
                    if dd_dev > 0:
                        sortino_ratio = (
                            (mean_r * periods_per_year)
                            / (dd_dev * np.sqrt(periods_per_year))
                        )

        # CAGR
        cagr = 0.0
        if self._portfolio_values and self._trade_pnls and self._starting_cash > 0:
            total_return = final_value / self._starting_cash
            if total_return > 0:
                first_d = self._trade_pnls[0]['date']
                last_d = self._trade_pnls[-1]['date']
                days = (last_d - first_d).days
                years = max(days / 365.25, 0.1)
                cagr = (pow(total_return, 1.0 / years) - 1.0) * 100.0

        calmar_ratio = cagr / max_drawdown_pct if max_drawdown_pct > 0 else 0

        # Monte Carlo Simulation
        monte_carlo_dd_95 = 0.0
        monte_carlo_dd_99 = 0.0
        if len(self._trade_pnls) >= 20:
            n_sims = 10000
            pnl_list = [t['pnl'] for t in self._trade_pnls]
            mc_dds = []
            for _ in range(n_sims):
                shuffled = np.random.permutation(pnl_list)
                equity = self._starting_cash
                peak = equity
                max_dd = 0.0
                for p in shuffled:
                    equity += p
                    if equity > peak:
                        peak = equity
                    dd = (peak - equity) / peak * 100.0 if peak > 0 else 0.0
                    if dd > max_dd:
                        max_dd = dd
                mc_dds.append(max_dd)
            mc_arr = np.array(mc_dds)
            monte_carlo_dd_95 = np.percentile(mc_arr, 95)
            monte_carlo_dd_99 = np.percentile(mc_arr, 99)

        # Yearly Statistics
        yearly_stats = defaultdict(lambda: {
            'trades': 0, 'wins': 0, 'pnl': 0.0,
            'gross_profit': 0.0, 'gross_loss': 0.0,
        })
        for trade in self._trade_pnls:
            y = trade['year']
            yearly_stats[y]['trades'] += 1
            yearly_stats[y]['pnl'] += trade['pnl']
            if trade['is_winner']:
                yearly_stats[y]['wins'] += 1
                yearly_stats[y]['gross_profit'] += trade['pnl']
            else:
                yearly_stats[y]['gross_loss'] += abs(trade['pnl'])

        # --- Print Summary ---
        print("\n" + "=" * 70)
        print("=== CERES STRATEGY SUMMARY (v1.0 Mobile Window) ===")
        print("=" * 70)

        print("Total Trades: %d" % self.trades)
        print("Wins: %d | Losses: %d" % (self.wins, self.losses))
        print("Win Rate: %.1f%%" % win_rate)
        print("Profit Factor: %.2f" % profit_factor)
        print("Gross Profit: $%s" % format(self.gross_profit, ',.2f'))
        print("Gross Loss: $%s" % format(self.gross_loss, ',.2f'))
        print("Net P&L: $%s" % format(total_pnl, ',.0f'))
        print("Final Value: $%s" % format(final_value, ',.0f'))

        print("\n" + "=" * 70)
        print("ADVANCED RISK METRICS")
        print("=" * 70)
        print("Sharpe Ratio:        %8.2f" % sharpe_ratio)
        print("Sortino Ratio:       %8.2f" % sortino_ratio)
        print("CAGR:                %7.2f%%" % cagr)
        print("Max Drawdown:        %7.2f%%" % max_drawdown_pct)
        print("Calmar Ratio:        %8.2f" % calmar_ratio)

        if monte_carlo_dd_95 > 0:
            mc_ratio = (
                monte_carlo_dd_95 / max_drawdown_pct
                if max_drawdown_pct > 0 else 0
            )
            mc_status = (
                "Good" if mc_ratio < 1.5
                else "Caution" if mc_ratio < 2.0
                else "Warning"
            )
            print("\nMonte Carlo Analysis (10,000 simulations):")
            print("  95th Percentile DD: %6.2f%%  [%s]"
                  % (monte_carlo_dd_95, mc_status))
            print("  99th Percentile DD: %6.2f%%" % monte_carlo_dd_99)
            print("  Historical vs MC95: %.2fx" % mc_ratio)
        print("=" * 70)

        # Yearly table
        print("\n" + "=" * 70)
        print("YEARLY STATISTICS")
        print("=" * 70)
        print("%-6s %7s %7s %7s %12s" % ('Year', 'Trades', 'WR%', 'PF', 'PnL'))
        print("-" * 45)

        for year in sorted(yearly_stats.keys()):
            s = yearly_stats[year]
            wr = (s['wins'] / s['trades'] * 100) if s['trades'] > 0 else 0
            pf = (
                (s['gross_profit'] / s['gross_loss'])
                if s['gross_loss'] > 0 else float('inf')
            )
            print("%-6d %7d %6.1f%% %7.2f $%10s"
                  % (year, s['trades'], wr, pf, format(s['pnl'], ',.0f')))

        print("=" * 70)

        # Config summary
        print("\n" + "=" * 70)
        print("STRATEGY CONFIGURATION")
        print("=" * 70)
        print("  Consolidation: %d bars, delay=%d bars after open"
              % (self.p.consolidation_bars, self.p.delay_bars))
        print("  Body Breakout: %s" % ("ENABLED" if self.p.use_body_breakout else "DISABLED"))
        if self.p.breakout_offset_mult > 0:
            print("  Breakout Offset: %.2f (min candle/window_height)"
                  % self.p.breakout_offset_mult)
        else:
            print("  Breakout Offset: DISABLED (any close > window_high)")
        print("  SL Mode: %s | Buffer: %.1f pips"
              % (self.p.sl_mode, self.p.sl_buffer_pips))
        print("  TP Mode: %s" % self.p.tp_mode)
        if self.p.use_window_height_filter:
            print("  Window Height Filter: %.1f-%.1f pips"
                  % (self.p.window_height_min, self.p.window_height_max))
        if self.p.use_window_er_filter:
            print("  Window ER Filter: %.2f-%.2f"
                  % (self.p.window_er_min, self.p.window_er_max))
        if self.p.use_er_htf_filter:
            print("  ER HTF Filter: >= %.2f (period=%d, tf=%dm)"
                  % (self.p.er_htf_threshold, self.p.er_htf_period,
                     self.p.er_htf_timeframe_minutes))
        if self.p.use_sl_pips_filter:
            print("  SL Pips Filter: %.1f-%.1f"
                  % (self.p.sl_pips_min, self.p.sl_pips_max))
        if self.p.use_eod_close:
            print("  EOD Close: %d:%02d UTC"
                  % (self.p.eod_close_hour, self.p.eod_close_minute))
        if self.p.use_day_filter:
            print("  Day Filter: %s" % list(self.p.allowed_days))
        print("  Risk: %.2f%%" % (self.p.risk_percent * 100))
        print("=" * 70)

        # Close report file
        if self.trade_report_file:
            self.trade_report_file.close()
            print("\nTrade report saved.")
