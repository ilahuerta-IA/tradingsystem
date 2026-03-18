"""
LUYTEN Strategy v1.0 - Opening Range Breakout (Simplified ORB) for ETFs

Observes the first N bars of each trading day to establish a consolidation
high (highest HIGH). After the consolidation phase, waits for a bullish
candle whose body crosses above that level, then enters LONG on the next
bar's open.

STATE MACHINE (3 STATES):
    IDLE -> CONSOLIDATION -> WAITING_BREAKOUT -> Entry

1. IDLE: Wait for new trading day
2. CONSOLIDATION: Record highest HIGH of the first N bars (consolidation_bars)
3. WAITING_BREAKOUT: Wait for green candle with:
   - open < consolidation_high AND close > consolidation_high
   - close - consolidation_high >= bk_above_min_pips (how far above)
   - close - open >= bk_body_min_pips (minimum candle body)
   Entry on open of NEXT candle (signal bar confirmed, enter next bar)

EXIT SYSTEM:
    - Stop Loss: entry - ATR(14) * atr_sl_multiplier
    - Take Profit: entry + ATR(14) * atr_tp_multiplier
    - EOD Close: forced close before session end

DIRECTION: LONG only
MAX ENTRIES PER DAY: 1
ASSETS: ETFs (TLT primary target)
"""
from __future__ import annotations
import math
from pathlib import Path
from datetime import datetime, time as dt_time
from collections import defaultdict

import backtrader as bt
import numpy as np

from lib.filters import (
    check_time_filter,
    check_day_filter,
    check_sl_pips_filter,
)
from lib.position_sizing import calculate_position_size


class LUYTENStrategy(bt.Strategy):
    """Opening Range Breakout (simplified) for slow ETFs like TLT."""

    params = dict(
        # --- Consolidation ---
        consolidation_bars=6,       # N first bars to observe
        session_start_hour=None,    # UTC hour to begin consolidation (None = first bar of day)
        session_start_minute=0,     # UTC minute to begin consolidation

        # --- Breakout Filters ---
        bk_above_min_pips=0.0,      # min distance close - consolidation_high
        bk_body_min_pips=0.0,       # min green candle body (close - open)

        # --- ATR ---
        atr_length=14,
        atr_avg_period=20,

        # --- Stop Loss / Take Profit (ATR-based) ---
        atr_sl_multiplier=2.0,
        atr_tp_multiplier=4.0,
        sl_buffer_pips=0.0,         # extra buffer below SL

        # --- EOD Close ---
        use_eod_close=True,
        eod_close_hour=20,
        eod_close_minute=50,

        # --- Standard Filters ---
        use_time_filter=False,
        allowed_hours=[],
        use_day_filter=False,
        allowed_days=[0, 1, 2, 3, 4],

        use_sl_pips_filter=False,
        sl_pips_min=0.0,
        sl_pips_max=9999.0,

        # --- ATR Range Filter ---
        use_atr_range_filter=False,
        atr_range_min=0.0,
        atr_range_max=9999.0,

        # --- Asset / Risk ---
        risk_percent=0.01,
        pip_value=0.01,
        lot_size=1,
        jpy_rate=1.0,
        is_jpy_pair=False,
        is_etf=True,
        margin_pct=20.0,

        # --- Debug ---
        print_signals=False,
        export_reports=True,
    )

    # =====================================================================
    # INIT
    # =====================================================================

    def __init__(self):
        self.atr = bt.ind.ATR(self.data, period=self.p.atr_length)

        # State machine
        self.state = "IDLE"

        # Consolidation tracking
        self.consolidation_high = None
        self.consol_count = 0

        # Signal bar flag: breakout confirmed, enter on NEXT bar
        self._signal_pending = False
        self._signal_atr_avg = 0.0
        self._signal_bk_above_pips = 0.0
        self._signal_bk_body_pips = 0.0

        # Day-start detection
        self._day_first_bar_seen = False

        # Order management
        self.order = None
        self.stop_order = None
        self.limit_order = None
        self.stop_level = None
        self.take_level = None
        self.last_entry_price = None
        self.last_exit_reason = None
        self._entry_fill_bar = -1

        # Day tracking (max 1 trade per day)
        self._today_date = None
        self._traded_today = False
        self._today_eod_minutes = None
        self._today_session_start_minutes = None

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
        """Initialize trade report file with configuration header."""
        if not self.p.export_reports:
            return
        try:
            report_dir = Path("logs")
            report_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_path = report_dir / ("LUYTEN_trades_%s.txt" % timestamp)
            self.trade_report_file = open(report_path, 'w', encoding='utf-8')
            f = self.trade_report_file

            f.write("=== LUYTEN STRATEGY TRADE REPORT (v1.0) ===\n")
            f.write("Generated: %s\n" % datetime.now())
            f.write("\n")
            if self.p.session_start_hour is not None:
                f.write("Session Start: %d:%02d UTC (DST-adjusted)\n"
                        % (self.p.session_start_hour,
                           self.p.session_start_minute))
            f.write("Consolidation: %d bars (first N bars of day)\n"
                    % self.p.consolidation_bars)
            f.write("BK Above Min: %.1f pips | BK Body Min: %.1f pips\n"
                    % (self.p.bk_above_min_pips, self.p.bk_body_min_pips))
            f.write("ATR SL Mult: %.1f | ATR TP Mult: %.1f | SL Buffer: %.1f pips\n"
                    % (self.p.atr_sl_multiplier, self.p.atr_tp_multiplier,
                       self.p.sl_buffer_pips))

            if self.p.use_eod_close:
                f.write("EOD Close: %d:%02d UTC\n"
                        % (self.p.eod_close_hour, self.p.eod_close_minute))
            else:
                f.write("EOD Close: DISABLED\n")

            if self.p.use_sl_pips_filter:
                f.write("SL Pips Filter: %.1f-%.1f\n"
                        % (self.p.sl_pips_min, self.p.sl_pips_max))
            else:
                f.write("SL Pips Filter: DISABLED\n")

            if self.p.use_atr_range_filter:
                f.write("ATR Range Filter: %.4f-%.4f\n"
                        % (self.p.atr_range_min, self.p.atr_range_max))
            else:
                f.write("ATR Range Filter: DISABLED\n")

            if self.p.use_time_filter:
                f.write("Time Filter: %s\n" % list(self.p.allowed_hours))
            else:
                f.write("Time Filter: DISABLED\n")

            if self.p.use_day_filter:
                f.write("Day Filter: %s\n" % list(self.p.allowed_days))
            else:
                f.write("Day Filter: DISABLED\n")

            f.write("Risk: %.2f%%\n" % (self.p.risk_percent * 100))
            f.write("ATR: length=%d, avg_period=%d\n"
                    % (self.p.atr_length, self.p.atr_avg_period))
            f.write("=" * 80 + "\n\n")
            f.flush()
            print("Trade report: %s" % report_path)
        except Exception as e:
            print("Trade reporting init failed: %s" % e)

    def _record_trade_entry(self, dt, entry_price, size, atr_avg, sl_pips,
                            consolidation_high, consol_bars,
                            bk_above_pips, bk_body_pips):
        """Record entry details to log and trade_reports list."""
        entry = {
            'entry_time': dt,
            'entry_price': entry_price,
            'size': size,
            'atr_avg': atr_avg,
            'sl_pips': sl_pips,
            'stop_level': self.stop_level,
            'take_level': self.take_level,
            'consolidation_high': consolidation_high,
            'consol_bars': consol_bars,
            'bk_above_pips': bk_above_pips,
            'bk_body_pips': bk_body_pips,
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
            f.write("Consolidation High: %.5f\n" % consolidation_high)
            f.write("Consolidation Bars: %d\n" % consol_bars)
            f.write("BK Above Pips: %.1f\n" % bk_above_pips)
            f.write("BK Body Pips: %.1f\n" % bk_body_pips)
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
            dt_time_val = self.data.datetime.time(offset)
            return datetime.combine(dt_date, dt_time_val)
        except Exception:
            return self.data.datetime.datetime(offset)

    def _get_average_atr(self):
        """Get average ATR over configured period."""
        if len(self.atr_history) < self.p.atr_avg_period:
            val = float(self.atr[0])
            return val if not math.isnan(val) else 0
        recent = self.atr_history[-self.p.atr_avg_period:]
        return sum(recent) / len(recent)

    def _reset_state(self):
        """Full reset to IDLE."""
        self.state = "IDLE"
        self.consolidation_high = None
        self.consol_count = 0
        self._signal_pending = False
        self._signal_atr_avg = 0.0
        self._signal_bk_above_pips = 0.0
        self._signal_bk_body_pips = 0.0

    # =====================================================================
    # EOD CLOSE
    # =====================================================================

    def _check_eod_close(self, dt):
        """Check and execute EOD forced close."""
        if not self.p.use_eod_close:
            return False
        if self._today_eod_minutes is None:
            return False

        current_minutes = dt.hour * 60 + dt.minute

        if current_minutes >= self._today_eod_minutes:
            self.last_exit_reason = "EOD_CLOSE"
            # Explicit cancel bracket orders, then close position
            if self.stop_order:
                self.cancel(self.stop_order)
                self.stop_order = None
            if self.limit_order:
                self.cancel(self.limit_order)
                self.limit_order = None
            self.order = self.close()

            if self.p.print_signals:
                print(
                    '%s [%s] === EOD CLOSE @ %.2f (forced %d:%02d UTC) ==='
                    % (dt, self.data._name, self.data.close[0],
                       self._today_eod_minutes // 60,
                       self._today_eod_minutes % 60)
                )
            return True
        return False

    # =====================================================================
    # ENTRY EXECUTION
    # =====================================================================

    def _execute_entry(self, dt, atr_avg, bk_above_pips, bk_body_pips):
        """Validate filters, size position, and send buy order."""

        # Day/Time filter
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

        entry_price = float(self.data.open[0])

        # Calculate SL/TP
        sl_buffer = self.p.sl_buffer_pips * self.p.pip_value
        self.stop_level = entry_price - (atr_avg * self.p.atr_sl_multiplier) - sl_buffer
        self.take_level = entry_price + (atr_avg * self.p.atr_tp_multiplier)

        # SL sanity: must be below entry
        if self.stop_level >= entry_price:
            if self.p.print_signals:
                print('%s [%s] ENTRY SKIPPED: SL %.5f >= entry %.5f'
                      % (dt, self.data._name, self.stop_level, entry_price))
            return

        # ATR range filter
        if self.p.use_atr_range_filter:
            if atr_avg < self.p.atr_range_min or atr_avg > self.p.atr_range_max:
                if self.p.print_signals:
                    print('%s [%s] ENTRY SKIPPED: atr_avg=%.4f out of range [%.4f-%.4f]'
                          % (dt, self.data._name, atr_avg,
                             self.p.atr_range_min, self.p.atr_range_max))
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
            self.consolidation_high, self.consol_count,
            bk_above_pips, bk_body_pips,
        )

        if self.p.print_signals:
            print(
                '%s [%s] ENTRY LONG @ %.5f | SL=%.5f | TP=%.5f | '
                'Consol High=%.5f'
                % (dt, self.data._name, entry_price, self.stop_level,
                   self.take_level, self.consolidation_high)
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

        # Day change detection
        today = dt.date()
        if today != self._today_date:
            # Compute DST-aware EOD for this trading day
            if self.p.use_eod_close and self.p.eod_close_hour is not None:
                base_eod = self.p.eod_close_hour * 60 + self.p.eod_close_minute
                if dt.hour < 14:
                    self._today_eod_minutes = base_eod - 60
                else:
                    self._today_eod_minutes = base_eod

            # Compute DST-aware session start (same DST heuristic as EOD)
            if self.p.session_start_hour is not None:
                base_start = (self.p.session_start_hour * 60
                              + self.p.session_start_minute)
                if dt.hour < 14:
                    self._today_session_start_minutes = base_start - 60
                else:
                    self._today_session_start_minutes = base_start
            else:
                self._today_session_start_minutes = None

            # Force-close any overnight position
            if self.position and self.p.use_eod_close:
                self.last_exit_reason = "EOD_CLOSE"
                oco_ref = self.stop_order or self.limit_order
                if oco_ref:
                    self.order = self.close(oco=oco_ref)
                else:
                    self.order = self.close()
                self.stop_order = None
                self.limit_order = None
                if self.p.print_signals:
                    print('%s [%s] === EOD CLOSE (day change) @ %.2f ==='
                          % (dt, self.data._name, self.data.close[0]))

            if self.order:
                self._today_date = today
                return

            self._today_date = today
            self._traded_today = False
            self._day_first_bar_seen = True
            self._signal_pending = False
            self._signal_atr_avg = 0.0
            self._signal_bk_above_pips = 0.0
            self._signal_bk_body_pips = 0.0

            # New day always starts in IDLE -> begin consolidation
            self._reset_state()

        # Pending order? Wait.
        if self.order:
            return

        # --- POSITION OPEN: manage exits ---
        if self.position:
            # EOD close (skip on entry bar)
            if len(self) != self._entry_fill_bar and self._check_eod_close(dt):
                return
            # Nothing else to manage (SL/TP are bracket orders)
            return

        # --- NO POSITION: run state machine ---

        # Already traded today? Wait for tomorrow.
        if self._traded_today:
            return

        atr_avg = self._get_average_atr()
        if atr_avg <= 0:
            return

        # Stop scanning at EOD time
        if self.state != "IDLE":
            if self.p.use_eod_close and self._today_eod_minutes is not None:
                current_minutes = dt.hour * 60 + dt.minute
                if current_minutes >= self._today_eod_minutes:
                    self._reset_state()
                    return

        # ---- STATE: IDLE ----
        if self.state == "IDLE":
            if self._day_first_bar_seen:
                # If session_start_hour is set, wait until that time (DST-adjusted)
                if self._today_session_start_minutes is not None:
                    current_minutes = dt.hour * 60 + dt.minute
                    if current_minutes < self._today_session_start_minutes:
                        return

                self._day_first_bar_seen = False
                self.state = "CONSOLIDATION"
                self.consolidation_high = float(self.data.high[0])
                self.consol_count = 1

                if self.p.print_signals:
                    print('%s [%s] CONSOLIDATION START: bar 1/%d, high=%.5f'
                          % (dt, self.data._name, self.p.consolidation_bars,
                             self.consolidation_high))

        # ---- STATE: CONSOLIDATION ----
        elif self.state == "CONSOLIDATION":
            bar_high = float(self.data.high[0])

            # Track highest HIGH
            if bar_high > self.consolidation_high:
                self.consolidation_high = bar_high

            self.consol_count += 1

            if self.p.print_signals:
                print('%s [%s] CONSOLIDATION: bar %d/%d, high=%.5f'
                      % (dt, self.data._name, self.consol_count,
                         self.p.consolidation_bars, self.consolidation_high))

            if self.consol_count >= self.p.consolidation_bars:
                # Consolidation complete -> wait for breakout
                self.state = "WAITING_BREAKOUT"

                if self.p.print_signals:
                    print('%s [%s] WAITING BREAKOUT > %.5f'
                          % (dt, self.data._name, self.consolidation_high))

        # ---- STATE: WAITING_BREAKOUT ----
        elif self.state == "WAITING_BREAKOUT":
            bar_open = float(self.data.open[0])
            bar_close = float(self.data.close[0])

            # Green candle that closes above consolidation_high
            # Accepts both cross-breakout (open below) and gap-breakout (open above)
            is_green = bar_close > bar_open
            close_above = bar_close > self.consolidation_high

            if is_green and close_above:
                # Check breakout filters
                above_dist = (bar_close - self.consolidation_high) / self.p.pip_value
                body_size = (bar_close - bar_open) / self.p.pip_value

                above_ok = above_dist >= self.p.bk_above_min_pips
                body_ok = body_size >= self.p.bk_body_min_pips

                if above_ok and body_ok:
                    # Breakout confirmed! Place buy now, fills at next bar's open
                    if self.p.print_signals:
                        print(
                            '%s [%s] BREAKOUT SIGNAL: close=%.5f > consol=%.5f, '
                            'above=%.1f pips, body=%.1f pips'
                            % (dt, self.data._name, bar_close,
                               self.consolidation_high, above_dist, body_size)
                        )
                    self._execute_entry(dt, atr_avg, above_dist, body_size)
                    self._reset_state()
                    return
                else:
                    if self.p.print_signals:
                        print(
                            '%s [%s] BREAKOUT REJECTED: above=%.1f (min=%.1f), '
                            'body=%.1f (min=%.1f)'
                            % (dt, self.data._name, above_dist,
                               self.p.bk_above_min_pips, body_size,
                               self.p.bk_body_min_pips)
                        )

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
                self._entry_fill_bar = len(self)

                # Bracket orders expire at EOD
                eod_valid = None
                if (self.p.use_eod_close
                        and self._today_eod_minutes is not None):
                    fill_dt = self._get_datetime()
                    eod_h, eod_m = divmod(self._today_eod_minutes, 60)
                    eod_valid = datetime.combine(
                        fill_dt.date(),
                        dt_time(eod_h, eod_m),
                    )

                # Place SL + TP bracket
                self.limit_order = self.sell(
                    size=order.executed.size,
                    exectype=bt.Order.Limit,
                    price=self.take_level,
                    valid=eod_valid,
                )
                self.stop_order = self.sell(
                    size=order.executed.size,
                    exectype=bt.Order.Stop,
                    price=self.stop_level,
                    oco=self.limit_order,
                    valid=eod_valid,
                )

                self.order = None

                if self.p.print_signals:
                    dt = self._get_datetime()
                    print(
                        '%s [%s] ORDER FILLED @ %.5f | SL=%.5f TP=%.5f'
                        % (dt, self.data._name, order.executed.price,
                           self.stop_level, self.take_level)
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
                self._traded_today = False
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
        print("=== LUYTEN STRATEGY SUMMARY (v1.0 ORB) ===")
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
        print("  Consolidation: %d bars (first N bars of day)"
              % self.p.consolidation_bars)
        print("  BK Above Min: %.1f pips" % self.p.bk_above_min_pips)
        print("  BK Body Min: %.1f pips" % self.p.bk_body_min_pips)
        print("  ATR SL Mult: %.1f | ATR TP Mult: %.1f"
              % (self.p.atr_sl_multiplier, self.p.atr_tp_multiplier))
        print("  SL Buffer: %.1f pips" % self.p.sl_buffer_pips)
        if self.p.use_sl_pips_filter:
            print("  SL Pips Filter: %.1f-%.1f"
                  % (self.p.sl_pips_min, self.p.sl_pips_max))
        if self.p.use_atr_range_filter:
            print("  ATR Range Filter: %.4f-%.4f"
                  % (self.p.atr_range_min, self.p.atr_range_max))
        if self.p.use_eod_close:
            print("  EOD Close: %d:%02d UTC"
                  % (self.p.eod_close_hour, self.p.eod_close_minute))
        if self.p.use_time_filter:
            print("  Time Filter: %s" % list(self.p.allowed_hours))
        if self.p.use_day_filter:
            print("  Day Filter: %s" % list(self.p.allowed_days))
        print("  Risk: %.2f%%" % (self.p.risk_percent * 100))
        print("=" * 70)

        # Close report file
        if self.trade_report_file:
            self.trade_report_file.close()
            print("\nTrade report saved.")
