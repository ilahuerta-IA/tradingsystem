"""
CERES Strategy - Opening Range + Simple Pullback + Breakout (Intraday ETF)

Native ETF intraday strategy designed from scratch.
Core thesis: the first N bars after market open (Opening Range) predict
the direction of the day. Entry on pullback below OR_HH then breakout above.

ENTRY SYSTEM (3 STATES):
    IDLE -> WINDOW_FORMING -> ARMED -> Entry

1. IDLE: Wait for market open
2. WINDOW_FORMING: Collect OR bars -> OR_HH, OR_LL, OR_HEIGHT
3. Quality Filters (all optional): ER_OR, ER_HTF, OR_Height, PB_Angle, etc.
4. ARMED: Wait for close < OR_HH (pullback), then close > OR_HH (breakout)

EXIT SYSTEM:
    - Stop Loss: configurable mode (or_low / fixed_pips / atr_mult) + buffer
    - Take Profit: configurable mode (none / or_height_mult / fixed_pips / atr_mult)
    - EOD Close: forced close before session end

DIRECTION: LONG only
ASSETS: ETFs (GLD, DIA, XLE, XLU, TLT, ...)

Design docs: docs/ceres_strategy.md

v0.9.0: Simplified pullback -- removed Ogle mechanics (bearish candle counting,
         breakout channel, re-arms). Now: close < OR_HH then close > OR_HH.
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
# REUSABLE: Opening Range quality assessment
# =========================================================================

def calculate_or_efficiency(or_opens, or_closes, or_highs, or_lows):
    """
    Calculate Efficiency Ratio of the Opening Range.

    ER = |net move| / sum(|individual moves|)
    High ER = directional OR (trending), low ER = choppy OR.

    Args:
        or_opens: List of open prices during OR
        or_closes: List of close prices during OR
        or_highs: List of high prices during OR (unused, reserved)
        or_lows: List of low prices during OR (unused, reserved)

    Returns:
        ER value 0.0 to 1.0
    """
    if len(or_closes) < 2:
        return 0.0
    # Net directional change
    change = abs(or_closes[-1] - or_opens[0])
    # Sum of individual bar ranges (close-to-close)
    volatility = sum(
        abs(or_closes[i] - or_closes[i - 1])
        for i in range(1, len(or_closes))
    )
    if volatility > 0:
        return change / volatility
    return 0.0


def calculate_pullback_angle(closes_since_or, num_bars):
    """
    Calculate angle of the pullback phase (from OR end to just before entry).

    Measures how price behaved during the consolidation/pullback:
    - Flat angle (~0) = sideways consolidation (healthy)
    - Negative angle = price fell during pullback (deeper retracement)
    - Positive angle = price drifted up during pullback (shallow)

    Uses close prices from OR completion to the bar before entry.

    Args:
        closes_since_or: List of close prices during ARMED phase
        num_bars: Number of bars in pullback

    Returns:
        Angle in degrees
    """
    if num_bars <= 0 or len(closes_since_or) < 2:
        return 0.0
    first_close = closes_since_or[0]
    last_close = closes_since_or[-1]
    if first_close <= 0:
        return 0.0
    pct_change = (last_close - first_close) / first_close
    angle_rad = math.atan2(pct_change * 10000, num_bars)
    return math.degrees(angle_rad)


# check_or_pullback_ready removed in v0.8 — replaced by Ogle pullback mechanics


# =========================================================================
# PLOT HELPER
# =========================================================================

class CeresEntryExitLines(bt.Indicator):
    """Plot entry/SL/TP lines on chart."""
    lines = ('entry', 'stop_loss', 'take_profit', 'or_hh', 'or_ll')
    plotinfo = dict(subplot=False, plotlinelabels=True)
    plotlines = dict(
        entry=dict(color='green', linestyle='--', linewidth=1.0),
        stop_loss=dict(color='red', linestyle='--', linewidth=1.0),
        take_profit=dict(color='blue', linestyle='--', linewidth=1.0),
        or_hh=dict(color='orange', linestyle=':', linewidth=0.8),
        or_ll=dict(color='orange', linestyle=':', linewidth=0.8),
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
    CERES: Opening Range + Pullback + Breakout intraday strategy for ETFs.

    State machine: IDLE -> WINDOW_FORMING -> ARMED -> Entry
    """

    params = dict(
        # --- Opening Range ---
        delay_bars=0,              # Bars to skip after first bar of day before OR
        or_candles=8,              # Bars to form OR (8 x 15min = 2h)

        # --- Quality Filters (all optional, independent) ---
        use_pb_angle_filter=False,
        pb_angle_min=-90.0,
        pb_angle_max=90.0,

        use_pb_depth_filter=False,  # PB Depth as % of OR Height
        pb_depth_min=0.0,
        pb_depth_max=100.0,

        allowed_pb_bars=[],         # List of allowed PB bar counts (empty=all)

        use_or_height_filter=False, # OR height in pips (min/max)
        or_height_min=0.0,
        or_height_max=9999.0,

        use_er_or_filter=False,    # ER of the OR itself (min/max range)
        er_or_min=0.0,
        er_or_max=1.0,

        use_er_htf_filter=False,   # ER in higher timeframe (macro context)
        er_htf_threshold=0.3,
        er_htf_period=10,
        er_htf_timeframe_minutes=60,

        # --- Pullback (simple: close < OR_HH then close > OR_HH) ---
        pullback_max_bars=20,      # Max bars after OR to wait for pullback+breakout

        # --- Stop Loss ---
        sl_mode='or_low',          # 'or_low' | 'fixed_pips' | 'atr_mult'
        sl_buffer_pips=5.0,
        sl_fixed_pips=30.0,
        sl_atr_mult=1.5,

        # --- Take Profit ---
        tp_mode='none',            # 'none' | 'or_height_mult' | 'fixed_pips' | 'atr_mult'
        tp_or_mult=1.5,
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

        # HTF ER (optional, scales period by timeframe ratio)
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
        self.or_bar_count = 0
        self.or_highs = []
        self.or_lows = []
        self.or_opens = []
        self.or_closes = []
        self.or_atr_values = []

        # OR computed values
        self.or_hh = None
        self.or_ll = None
        self.or_height = None
        self.or_er = None
        self.or_atr_avg = None
        self.or_end_bar = None

        # Day-start detection (DST-agnostic)
        self._day_first_bar_seen = False
        self._delay_bars_remaining = 0

        # ARMED state tracking
        self.highs_since_or = []
        self.closes_since_or = []
        self.lows_since_or = []
        self.armed_bar_count = 0

        # Simple pullback state
        self._pullback_seen = False    # True once close < OR_HH observed

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

            f.write("=== CERES STRATEGY TRADE REPORT ===\n")
            f.write("Generated: %s\n" % datetime.now())
            f.write("\n")

            # Opening Range config
            f.write("Opening Range: %d candles, delay=%d bars after open\n" % (
                self.p.or_candles, self.p.delay_bars))

            # Quality filters
            if self.p.use_or_height_filter:
                f.write("OR Height Filter: ENABLED | Range: %.1f-%.1f pips\n" % (
                    self.p.or_height_min, self.p.or_height_max))
            else:
                f.write("OR Height Filter: DISABLED\n")

            if self.p.use_pb_angle_filter:
                f.write("PB Angle Filter: ENABLED | Range: %.1f-%.1f deg\n" % (
                    self.p.pb_angle_min, self.p.pb_angle_max))
            else:
                f.write("PB Angle Filter: DISABLED\n")

            if self.p.use_pb_depth_filter:
                f.write("PB Depth Filter: ENABLED | Range: %.1f-%.1f%%\n" % (
                    self.p.pb_depth_min, self.p.pb_depth_max))
            else:
                f.write("PB Depth Filter: DISABLED\n")

            if self.p.allowed_pb_bars:
                f.write("Allowed PB Bars: %s\n" % list(self.p.allowed_pb_bars))
            else:
                f.write("Allowed PB Bars: ALL\n")

            if self.p.use_er_or_filter:
                f.write("ER OR Filter: ENABLED | Range: %.2f-%.2f\n"
                        % (self.p.er_or_min, self.p.er_or_max))
            else:
                f.write("ER OR Filter: DISABLED\n")

            if self.p.use_er_htf_filter:
                f.write("ER HTF Filter: ENABLED | Threshold: %.2f, Period: %d, TF: %dm\n" % (
                    self.p.er_htf_threshold, self.p.er_htf_period,
                    self.p.er_htf_timeframe_minutes))
            else:
                f.write("ER HTF Filter: DISABLED\n")

            # Pullback (simple)
            f.write("Pullback: simple (close<HH then close>HH), max_bars=%d\n" % (
                self.p.pullback_max_bars,))

            # SL / TP
            f.write("SL Mode: %s | Buffer: %.1f pips" % (
                self.p.sl_mode, self.p.sl_buffer_pips))
            if self.p.sl_mode == 'fixed_pips':
                f.write(" | Fixed: %.1f pips" % self.p.sl_fixed_pips)
            elif self.p.sl_mode == 'atr_mult':
                f.write(" | ATR Mult: %.1f" % self.p.sl_atr_mult)
            f.write("\n")

            f.write("TP Mode: %s" % self.p.tp_mode)
            if self.p.tp_mode == 'or_height_mult':
                f.write(" | OR Mult: %.1f" % self.p.tp_or_mult)
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
                            or_hh, or_ll, or_height, or_er, or_atr_avg,
                            pb_bars=0, pb_angle=0.0, pb_depth_pct=0.0,
                            rearm_count=0):
        """Record entry details to log and trade_reports list."""
        entry = {
            'entry_time': dt,
            'entry_price': entry_price,
            'size': size,
            'atr_avg': atr_avg,
            'sl_pips': sl_pips,
            'stop_level': self.stop_level,
            'take_level': self.take_level,
            'or_hh': or_hh,
            'or_ll': or_ll,
            'or_height': or_height,
            'or_er': or_er,
            'or_atr_avg': or_atr_avg,
            'sl_mode': self.p.sl_mode,
            'tp_mode': self.p.tp_mode,
            'pb_bars': pb_bars,
            'pb_angle': pb_angle,
            'pb_depth_pct': pb_depth_pct,
            'rearm_count': rearm_count,
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
            f.write("OR HH: %.5f\n" % or_hh)
            f.write("OR LL: %.5f\n" % or_ll)
            f.write("OR Height: %.5f\n" % or_height)
            f.write("OR ER: %.4f\n" % or_er)
            f.write("OR ATR Avg: %.6f\n" % or_atr_avg)
            f.write("SL Mode: %s\n" % self.p.sl_mode)
            f.write("TP Mode: %s\n" % self.p.tp_mode)
            f.write("PB Bars: %d\n" % pb_bars)
            f.write("PB Angle: %.2f\n" % pb_angle)
            f.write("PB Depth: %.1f%%\n" % pb_depth_pct)
            f.write("Rearm Count: %d\n" % rearm_count)
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
        self.entry_exit_lines.lines.or_hh[0] = hh if hh else nan
        self.entry_exit_lines.lines.or_ll[0] = ll if ll else nan

    def _is_or_start_ready(self):
        """Check if we should start forming the OR (first bar of day + delay).

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
        """Reset to IDLE state, clearing all OR and ARMED data."""
        self.state = "IDLE"
        self.or_bar_count = 0
        self.or_highs = []
        self.or_lows = []
        self.or_opens = []
        self.or_closes = []
        self.or_atr_values = []
        self.or_hh = None
        self.or_ll = None
        self.or_height = None
        self.or_er = None
        self.or_atr_avg = None
        self.or_end_bar = None
        self.highs_since_or = []
        self.closes_since_or = []
        self.lows_since_or = []
        self.armed_bar_count = 0
        self._pullback_seen = False

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

    def _check_or_quality(self):
        """
        Check all optional quality filters on the completed Opening Range.
        Returns True if OR passes all active filters (or all are disabled).
        """
        # OR Height filter (in pips)
        if self.p.use_or_height_filter:
            if self.or_height is None:
                return False
            height_pips = self.or_height / self.p.pip_value
            if not (self.p.or_height_min <= height_pips <= self.p.or_height_max):
                if self.p.print_signals:
                    dt = self._get_datetime()
                    print('%s [%s] OR REJECTED: height=%.1f pips (need %.1f-%.1f)'
                          % (dt, self.data._name, height_pips,
                             self.p.or_height_min, self.p.or_height_max))
                return False

        # ER of the OR itself (min/max range)
        if self.p.use_er_or_filter:
            if self.or_er is None:
                return False
            if not (self.p.er_or_min <= self.or_er <= self.p.er_or_max):
                if self.p.print_signals:
                    dt = self._get_datetime()
                    print('%s [%s] OR REJECTED: er=%.4f (need %.2f-%.2f)'
                          % (dt, self.data._name, self.or_er,
                             self.p.er_or_min, self.p.er_or_max))
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
                        print('%s [%s] OR REJECTED: er_htf=%.4f (need >= %.2f)'
                              % (dt, self.data._name, er_val,
                                 self.p.er_htf_threshold))
                    return False

        return True

    # =====================================================================
    # SL / TP CALCULATION
    # =====================================================================

    def _calculate_sl(self, entry_price, atr_avg):
        """Calculate stop loss price based on configured mode."""
        if self.p.sl_mode == 'or_low':
            base = self.or_ll
        elif self.p.sl_mode == 'fixed_pips':
            base = entry_price - (self.p.sl_fixed_pips * self.p.pip_value)
        elif self.p.sl_mode == 'atr_mult':
            base = entry_price - (atr_avg * self.p.sl_atr_mult)
        else:
            base = self.or_ll  # Default fallback

        # Apply buffer
        sl_price = base - (self.p.sl_buffer_pips * self.p.pip_value)
        return sl_price

    def _calculate_tp(self, entry_price, atr_avg):
        """Calculate take profit price based on configured mode. None = no TP."""
        if self.p.tp_mode == 'none':
            return None
        elif self.p.tp_mode == 'or_height_mult':
            return entry_price + (self.or_height * self.p.tp_or_mult)
        elif self.p.tp_mode == 'fixed_pips':
            return entry_price + (self.p.tp_fixed_pips * self.p.pip_value)
        elif self.p.tp_mode == 'atr_mult':
            return entry_price + (atr_avg * self.p.tp_atr_mult)
        return None

    # =====================================================================
    # ENTRY EXECUTION
    # =====================================================================

    def _execute_entry(self, dt, atr_avg):
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

        # Compute pullback metrics (before buy, so filter can reject)
        pb_bars = self.armed_bar_count
        pb_angle = calculate_pullback_angle(
            self.closes_since_or, pb_bars
        )
        # Pullback depth: how far below OR_HH the lowest low went
        if self.lows_since_or and self.or_hh and self.or_height and self.or_height > 0:
            pb_min_low = min(self.lows_since_or)
            pb_depth_pct = (self.or_hh - pb_min_low) / self.or_height * 100
        else:
            pb_depth_pct = 0.0

        # PB Angle filter
        if self.p.use_pb_angle_filter:
            if pb_angle < self.p.pb_angle_min or pb_angle > self.p.pb_angle_max:
                if self.p.print_signals:
                    print('%s [%s] ENTRY SKIPPED: pb_angle=%.2f (need %.1f-%.1f)'
                          % (dt, self.data._name, pb_angle,
                             self.p.pb_angle_min, self.p.pb_angle_max))
                return

        # PB Depth filter (% of OR Height)
        if self.p.use_pb_depth_filter:
            if pb_depth_pct < self.p.pb_depth_min or pb_depth_pct > self.p.pb_depth_max:
                if self.p.print_signals:
                    print('%s [%s] ENTRY SKIPPED: pb_depth=%.1f%% (need %.1f-%.1f%%)'
                          % (dt, self.data._name, pb_depth_pct,
                             self.p.pb_depth_min, self.p.pb_depth_max))
                return

        # Allowed PB Bars filter
        if self.p.allowed_pb_bars:
            if pb_bars not in self.p.allowed_pb_bars:
                if self.p.print_signals:
                    print('%s [%s] ENTRY SKIPPED: pb_bars=%d not in %s'
                          % (dt, self.data._name, pb_bars,
                             list(self.p.allowed_pb_bars)))
                return

        # Send buy order
        self.order = self.buy(size=bt_size)
        self._traded_today = True

        # Record
        self._record_trade_entry(
            dt, entry_price, bt_size, atr_avg, sl_pips,
            self.or_hh, self.or_ll, self.or_height,
            self.or_er if self.or_er else 0.0,
            self.or_atr_avg if self.or_atr_avg else 0.0,
            pb_bars, pb_angle, pb_depth_pct,
        )

        if self.p.print_signals:
            print(
                '%s [%s] ENTRY LONG @ %.5f | SL=%.5f (%s) | TP=%s | '
                'OR_HH=%.5f OR_LL=%.5f Height=%.5f'
                % (dt, self.data._name, entry_price, self.stop_level,
                   self.p.sl_mode,
                   ('%.5f' % self.take_level) if self.take_level else 'EOD',
                   self.or_hh, self.or_ll, self.or_height)
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

            # If we just submitted a close order, wait for it
            # (reset daily vars AFTER this guard so _traded_today isn't
            #  prematurely False while a day-change close is still pending)
            if self.order:
                self._today_date = today
                return

            self._today_date = today
            self._traded_today = False
            self._day_first_bar_seen = True
            self._delay_bars_remaining = self.p.delay_bars
            # If day changes while in WINDOW_FORMING or ARMED, reset
            if self.state in ("WINDOW_FORMING", "ARMED"):
                self._reset_state()

        # Pending order? Wait.
        if self.order:
            return

        # --- POSITION OPEN: manage exits ---
        if self.position:
            # EOD close (skip on entry bar to avoid immediate close)
            if len(self) != self._entry_fill_bar and self._check_eod_close(dt):
                return

            # Reset state machine if still armed
            if self.state != "IDLE":
                self._reset_state()

            # Update plot lines
            self._update_plot_lines(
                self.last_entry_price, self.stop_level, self.take_level,
                self.or_hh, self.or_ll
            )
            return

        # --- NO POSITION: run state machine ---

        # Already traded today? Wait for tomorrow.
        if self._traded_today:
            return

        atr_avg = self._get_average_atr()
        if atr_avg <= 0:
            return

        # ---- STATE: IDLE ----
        if self.state == "IDLE":
            if self._is_or_start_ready():
                self._day_first_bar_seen = False  # consumed
                self.state = "WINDOW_FORMING"
                self.or_bar_count = 0
                self.or_highs = []
                self.or_lows = []
                self.or_opens = []
                self.or_closes = []
                self.or_atr_values = []

                if self.p.print_signals:
                    print('%s [%s] OR FORMING: collecting %d bars'
                          % (dt, self.data._name, self.p.or_candles))

                # Include this bar as first OR bar
                self._collect_or_bar()

        # ---- STATE: WINDOW_FORMING ----
        elif self.state == "WINDOW_FORMING":
            self._collect_or_bar()

            if self.or_bar_count >= self.p.or_candles:
                # OR complete -> compute values
                self.or_hh = max(self.or_highs)
                self.or_ll = min(self.or_lows)
                self.or_height = self.or_hh - self.or_ll
                self.or_end_bar = len(self)

                # Compute quality metrics (always, for logging)
                self.or_er = calculate_or_efficiency(
                    self.or_opens, self.or_closes,
                    self.or_highs, self.or_lows,
                )
                if self.or_atr_values:
                    self.or_atr_avg = sum(self.or_atr_values) / len(self.or_atr_values)
                else:
                    self.or_atr_avg = atr_avg

                if self.p.print_signals:
                    print(
                        '%s [%s] OR COMPLETE: HH=%.5f LL=%.5f '
                        'Height=%.5f ER=%.4f ATR=%.6f'
                        % (dt, self.data._name, self.or_hh, self.or_ll,
                           self.or_height, self.or_er,
                           self.or_atr_avg)
                    )

                # Quality check
                if self._check_or_quality():
                    self.state = "ARMED"
                    self.highs_since_or = []
                    self.closes_since_or = []
                    self.lows_since_or = []
                    self.armed_bar_count = 0
                    if self.p.print_signals:
                        print('%s [%s] ARMED: waiting pullback+breakout > %.5f'
                              % (dt, self.data._name, self.or_hh))
                else:
                    self._reset_state()  # OR rejected, wait tomorrow

        # ---- STATE: ARMED (simple pullback: close<HH then close>HH) ----
        elif self.state == "ARMED":
            self.armed_bar_count += 1

            # Update plot: show OR levels while armed
            self._update_plot_lines(hh=self.or_hh, ll=self.or_ll)

            # Track bar data for pullback metrics
            self.highs_since_or.append(float(self.data.high[0]))
            self.closes_since_or.append(float(self.data.close[0]))
            self.lows_since_or.append(float(self.data.low[0]))

            current_close = float(self.data.close[0])

            if not self._pullback_seen:
                # Phase 1: wait for close below OR_HH (pullback)
                if current_close < self.or_hh:
                    self._pullback_seen = True
                    if self.p.print_signals:
                        print('%s [%s] PULLBACK SEEN: close=%.5f < OR_HH=%.5f'
                              % (dt, self.data._name, current_close,
                                 self.or_hh))
            else:
                # Phase 2: wait for close above OR_HH (breakout)
                if current_close > self.or_hh:
                    if self.p.print_signals:
                        print('%s [%s] BREAKOUT: close=%.5f > OR_HH=%.5f'
                              % (dt, self.data._name, current_close,
                                 self.or_hh))
                    self._execute_entry(dt, atr_avg)
                    self._reset_state()
                    return

            # Timeout
            if self.armed_bar_count > self.p.pullback_max_bars:
                if self.p.print_signals:
                    print('%s [%s] ARMED TIMEOUT after %d bars'
                          % (dt, self.data._name, self.armed_bar_count))
                self._reset_state()

    def _collect_or_bar(self):
        """Collect current bar data into OR arrays."""
        self.or_highs.append(float(self.data.high[0]))
        self.or_lows.append(float(self.data.low[0]))
        self.or_opens.append(float(self.data.open[0]))
        self.or_closes.append(float(self.data.close[0]))
        current_atr = float(self.atr[0]) if not math.isnan(float(self.atr[0])) else 0
        if current_atr > 0:
            self.or_atr_values.append(current_atr)
        self.or_bar_count += 1

    # =====================================================================
    # ORDER / TRADE NOTIFICATIONS
    # =====================================================================

    def notify_order(self, order):
        """Handle order status changes."""
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status == order.Completed:
            if order == self.order and order.isbuy():
                # Entry fill (must be a BUY -- day-change close also uses
                # self.order but is a SELL, must go to the else branch)
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
        print("=== CERES STRATEGY SUMMARY ===")
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
        print("  OR: %d candles, delay=%d bars after day open"
              % (self.p.or_candles, self.p.delay_bars))
        print("  Pullback: simple (close<HH then close>HH), max_bars=%d"
              % self.p.pullback_max_bars)
        print("  SL Mode: %s | Buffer: %.1f pips"
              % (self.p.sl_mode, self.p.sl_buffer_pips))
        print("  TP Mode: %s" % self.p.tp_mode)
        if self.p.use_or_height_filter:
            print("  OR Height Filter: %.1f-%.1f pips"
                  % (self.p.or_height_min, self.p.or_height_max))
        if self.p.use_pb_angle_filter:
            print("  PB Angle Filter: %.1f-%.1f deg"
                  % (self.p.pb_angle_min, self.p.pb_angle_max))
        if self.p.use_pb_depth_filter:
            print("  PB Depth Filter: %.1f-%.1f%%"
                  % (self.p.pb_depth_min, self.p.pb_depth_max))
        if self.p.allowed_pb_bars:
            print("  Allowed PB Bars: %s" % list(self.p.allowed_pb_bars))
        if self.p.use_er_or_filter:
            print("  ER OR Filter: %.2f-%.2f"
                  % (self.p.er_or_min, self.p.er_or_max))
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
