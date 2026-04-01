"""
VEGA Strategy - Cross-Index Z-Score Divergence (London Repricing)

CONCEPT:
Regional indices (NI225, GDAXI, UK100) share macro exposure with SP500.
Overnight moves in SP500 create temporary divergence vs. regional indices.
During London session (07:00-12:00 UTC), repricing corrects this divergence.

Z-score normalizes each index relative to its own 24h SMA and ATR:
    z = (Close - SMA(24)) / ATR(24)

Spread = z_SP500 - z_TARGET measures relative divergence.

Negative predictive correlation: when spread > 0 (SP500 relatively high,
target relatively low), target return is negative -- and vice versa.

SIGNAL (Index B standalone mode):
    forecast = clip(spread / dead_zone * 20, -20, +20)
    direction = -sign(forecast)
    -> spread > dead_zone  -> SHORT target index
    -> spread < -dead_zone -> LONG target index
    -> size proportional to |forecast| / 20

SESSION: London (07:00-12:00 UTC) -- confirmed across 4 indices.
EXIT: Time-based (holding_hours), with wide protective stop as safety net.

VALIDATED CONFIGURATIONS (Fase 0c):
    SP500/NI225 London: Sharpe 2.36, PF 1.26, 7/7 years, perm p=0.000
    SP500/GDAXI London: Sharpe 2.72, PF 1.31, 6/7 years, perm p=0.000
    SP500/UK100 London: Sharpe 1.19, PF 1.12, 7/7 years, perm p=0.009
    SP500/EUR50 London: Sharpe 1.70, PF 1.19, perm p=0.000

DATA FEEDS:
    datas[0] = Index A (SP500, reference/leader) -- H1 resampled
    datas[1] = Index B (NI225/GDAXI, trading target) -- H1 resampled
"""
from __future__ import annotations
import math
from pathlib import Path
from datetime import datetime
from collections import defaultdict

import backtrader as bt
import numpy as np

from lib.filters import check_time_filter, check_day_filter


# =============================================================================
# CUSTOM INDICATORS FOR PLOT
# =============================================================================

class SpreadIndicator(bt.Indicator):
    """Plot z-score spread and normalized forecast as subplot.

    Both lines share the same scale:
    - spread: raw z-score difference (zA - zB)
    - forecast_norm: forecast / max_forecast * dead_zone
      maps [-20,+20] -> [-dz, +dz] so it overlays cleanly on spread
    - dead_zone lines at +/- dead_zone
    """
    lines = ('spread', 'forecast_norm', 'dead_zone_upper', 'dead_zone_lower',
             'zero')

    plotinfo = dict(
        subplot=True,
        plotname='VEGA Spread & Forecast',
        plotlinelabels=True,
        plotheight=2.0,
    )
    plotlines = dict(
        spread=dict(color='blue', linewidth=1.5,
                    _name='Spread (zA - zB)'),
        forecast_norm=dict(color='purple', linewidth=2.0, linestyle='-',
                           _name='Forecast (norm)'),
        dead_zone_upper=dict(color='gray', linestyle='--', linewidth=0.8),
        dead_zone_lower=dict(color='gray', linestyle='--', linewidth=0.8),
        zero=dict(color='gray', linestyle='-', linewidth=0.5),
    )

    def __init__(self):
        pass

    def next(self):
        self.lines.zero[0] = 0.0


class EntryExitLines(bt.Indicator):
    """Horizontal lines for entry, stop, hold-end levels."""
    lines = ('entry', 'stop_loss')

    plotinfo = dict(subplot=False, plotlinelabels=True)
    plotlines = dict(
        entry=dict(color='green', linestyle='--', linewidth=1.0),
        stop_loss=dict(color='red', linestyle='--', linewidth=1.0),
    )

    def __init__(self):
        pass

    def next(self):
        pass


# =============================================================================
# VEGA STRATEGY
# =============================================================================

class VEGAStrategy(bt.Strategy):
    """
    VEGA -- Cross-Index Z-Score Divergence.

    Trades the lagging index (datas[1]) based on z-score spread
    with the leading index (datas[0], typically SP500).
    Bidirectional: LONG or SHORT target index depending on spread sign.
    """

    params = dict(
        # === Z-SCORE SETTINGS ===
        sma_period=24,              # SMA period in H1 bars (24 = 24 hours)
        atr_period=24,              # ATR period in H1 bars

        # === SIGNAL ===
        dead_zone=1.0,              # Minimum spread to generate signal
        max_forecast=20,            # Forecast range [-20, +20]
        min_forecast_entry=1,       # Minimum |forecast| to enter

        # === DIRECTION FILTER ===
        allow_long=True,            # Allow LONG entries on target index
        allow_short=True,           # Allow SHORT entries on target index

        # === SESSION ===
        session_start_hour=7,       # London session start (UTC)
        session_end_hour=12,        # London session end (UTC)
        holding_hours=6,            # Hours to hold position
        max_trades_per_day=0,       # Max entries per day (0=unlimited)

        # === FILTERS ===
        use_time_filter=True,
        allowed_hours=[7, 8, 9, 10, 11, 12],
        use_day_filter=True,
        allowed_days=[0, 1, 2, 3, 4],

        # === PROTECTIVE STOP / TAKE PROFIT ===
        use_protective_stop=True,
        protective_atr_mult=5.0,    # Wide stop as safety net (rarely hit)
        tp_atr_mult=0.0,            # Take profit in ATR multiples (0=disabled)

        # === POSITION SIZING ===
        risk_percent=0.01,          # Risk per trade as fraction of equity
        max_position_pct=0.10,      # Max equity fraction in margin
        capital_alloc_pct=0.10,     # Max margin allocation at full forecast
        max_loss_per_trade_pct=0.05,  # Max loss if protective stop hit (% equity)

        # === ASSET CONFIG (auto-injected by run_backtest.py) ===
        pip_value=1.0,              # CFD index: 1 point = $1
        is_jpy_pair=False,
        is_etf=True,                # CFD indices use ETF-style margin
        margin_pct=5.0,             # Margin requirement
        lot_size=1,                 # CFD index: 1 contract = 1 unit
        jpy_rate=1.0,

        # === DEBUG & REPORTING ===
        print_signals=False,
        export_reports=True,

        # === PLOT ===
        plot_reference=False,       # Show Index A chart
        plot_entry_exit_lines=True,
    )

    def __init__(self):
        # Data feeds (both H1, resampled by runner)
        self.data_a = self.datas[0]     # Index A (SP500, reference)
        self.data_b = self.datas[1]     # Index B (NI225/GDAXI, traded)

        print(f'[VEGA] Index A (reference): {self.data_a._name}')
        print(f'[VEGA] Index B (traded):    {self.data_b._name}')

        # Hide reference chart if not needed
        if not self.p.plot_reference:
            self.data_a.plotinfo.plot = False

        # Technical indicators on H1 data
        self.sma_a = bt.ind.SMA(self.data_a.close, period=self.p.sma_period)
        self.atr_a = bt.ind.ATR(self.data_a, period=self.p.atr_period)
        self.sma_b = bt.ind.SMA(self.data_b.close, period=self.p.sma_period)
        self.atr_b = bt.ind.ATR(self.data_b, period=self.p.atr_period)

        # Hide indicators on reference
        self.sma_a.plotinfo.plot = False
        self.atr_a.plotinfo.plot = False

        # Spread subplot
        self.spread_ind = SpreadIndicator(self.data_b)

        # Entry/exit lines on price chart
        if self.p.plot_entry_exit_lines:
            self.entry_exit_lines = EntryExitLines(self.data_b)
        else:
            self.entry_exit_lines = None

        # Orders
        self.order_b = None

        # Position state
        self.state = "SCANNING"
        self.entry_bar = None
        self.entry_datetime = None
        self.entry_price_b = None
        self.entry_forecast = None
        self.direction = 0              # +1 = long B, -1 = short B
        self.protective_stop_b = None
        self.last_exit_reason = None
        self.trades_today = 0
        self.last_trade_date = None

        # Statistics
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

        # Trade reporting
        self.trade_reports = []
        self.trade_report_file = None
        self._init_trade_reporting()

    # =========================================================================
    # DATETIME HELPER
    # =========================================================================

    def _get_datetime(self, offset=0):
        """Get correct datetime combining date and time."""
        try:
            dt_date = self.data_b.datetime.date(offset)
            dt_time = self.data_b.datetime.time(offset)
            return datetime.combine(dt_date, dt_time)
        except Exception:
            return self.data_b.datetime.datetime(offset)

    # =========================================================================
    # Z-SCORE AND SIGNAL
    # =========================================================================

    def _compute_zscore(self, data_close, sma, atr):
        """Compute z-score: (close - SMA) / ATR."""
        close_val = float(data_close[0])
        sma_val = float(sma[0])
        atr_val = float(atr[0])
        if atr_val <= 0 or math.isnan(atr_val) or math.isnan(sma_val):
            return 0.0
        return (close_val - sma_val) / atr_val

    def _compute_spread(self):
        """Compute spread = z_A - z_B."""
        z_a = self._compute_zscore(self.data_a.close, self.sma_a, self.atr_a)
        z_b = self._compute_zscore(self.data_b.close, self.sma_b, self.atr_b)
        return z_a - z_b, z_a, z_b

    def _compute_forecast(self, spread):
        """
        Continuous forecast in [-max_forecast, +max_forecast].
        forecast > 0 when spread > 0 (A high, B low).
        """
        raw = spread / self.p.dead_zone * self.p.max_forecast
        return max(-self.p.max_forecast, min(self.p.max_forecast, raw))

    # =========================================================================
    # TRADE REPORTING (same pattern as GEMINI)
    # =========================================================================

    def _init_trade_reporting(self):
        """Initialize trade report file."""
        if not self.p.export_reports:
            return
        try:
            report_dir = Path("logs")
            report_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_path = report_dir / f"VEGA_trades_{timestamp}.txt"
            self.trade_report_file = open(report_path, 'w', encoding='utf-8')
            self.trade_report_file.write("=== VEGA STRATEGY TRADE REPORT ===\n")
            self.trade_report_file.write(f"Generated: {datetime.now()}\n\n")
            self.trade_report_file.write("=== CONFIGURATION ===\n")
            self.trade_report_file.write(
                f"Z-score: SMA={self.p.sma_period}, ATR={self.p.atr_period}\n")
            self.trade_report_file.write(
                f"Dead Zone: {self.p.dead_zone}\n")
            self.trade_report_file.write(
                f"Holding: {self.p.holding_hours}h\n")
            self.trade_report_file.write(
                f"Session: {self.p.session_start_hour:02d}:00-"
                f"{self.p.session_end_hour:02d}:00 UTC\n")
            self.trade_report_file.write(
                f"Protective Stop: "
                f"{'ON (' + str(self.p.protective_atr_mult) + 'x ATR)' if self.p.use_protective_stop else 'OFF'}\n")
            self.trade_report_file.write(
                f"Risk: {self.p.risk_percent * 100:.1f}%\n")
            if self.p.use_time_filter:
                self.trade_report_file.write(
                    f"Time Filter: {list(self.p.allowed_hours)}\n")
            if self.p.use_day_filter:
                day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
                days = [day_names[d] for d in self.p.allowed_days if d < 7]
                self.trade_report_file.write(f"Day Filter: {days}\n")
            self.trade_report_file.write("\n")
            print(f"[VEGA] Trade report: {report_path}")
        except Exception as e:
            print(f"[VEGA] Trade reporting init failed: {e}")

    def _record_trade_entry(self, dt, entry_price, size, direction,
                            spread, forecast, atr_b):
        """Record entry to trade report file."""
        if not self.trade_report_file:
            return
        try:
            entry = {
                'entry_time': dt,
                'entry_price': entry_price,
                'size': size,
                'direction': 'LONG' if direction > 0 else 'SHORT',
                'spread': spread,
                'forecast': forecast,
                'atr_b': atr_b,
                'stop_level': self.protective_stop_b,
            }
            self.trade_reports.append(entry)
            self.trade_report_file.write(f"ENTRY #{len(self.trade_reports)}\n")
            self.trade_report_file.write(
                f"Time: {dt.strftime('%Y-%m-%d %H:%M:%S')}\n")
            self.trade_report_file.write(
                f"Direction: {entry['direction']}\n")
            self.trade_report_file.write(
                f"Entry Price: {entry_price:.2f}\n")
            self.trade_report_file.write(
                f"Size: {size} contracts\n")
            self.trade_report_file.write(
                f"Spread: {spread:.4f}\n")
            self.trade_report_file.write(
                f"Forecast: {forecast:.1f}\n")
            self.trade_report_file.write(
                f"ATR(B): {atr_b:.2f}\n")
            if self.protective_stop_b is not None:
                self.trade_report_file.write(
                    f"Protective Stop: {self.protective_stop_b:.2f}\n")
            self.trade_report_file.write("-" * 50 + "\n\n")
            self.trade_report_file.flush()
        except Exception:
            pass

    def _record_trade_exit(self, dt, pnl, reason):
        """Record exit to trade report file."""
        if not self.trade_report_file or not self.trade_reports:
            return
        try:
            self.trade_reports[-1]['pnl'] = pnl
            self.trade_reports[-1]['exit_reason'] = reason
            self.trade_reports[-1]['exit_time'] = dt
            self.trade_report_file.write(
                f"EXIT #{len(self.trade_reports)}\n")
            self.trade_report_file.write(
                f"Time: {dt.strftime('%Y-%m-%d %H:%M:%S')}\n")
            self.trade_report_file.write(
                f"Exit Reason: {reason}\n")
            self.trade_report_file.write(
                f"P&L: ${pnl:.2f}\n")
            self.trade_report_file.write("=" * 80 + "\n\n")
            self.trade_report_file.flush()
        except Exception:
            pass

    # =========================================================================
    # PLOT LINES UPDATE
    # =========================================================================

    def _update_plot_lines(self, entry_price=None, stop_level=None):
        """Update entry/exit plot lines on chart."""
        if not self.entry_exit_lines:
            return
        nan = float('nan')
        self.entry_exit_lines.lines.entry[0] = (
            entry_price if entry_price else nan)
        self.entry_exit_lines.lines.stop_loss[0] = (
            stop_level if stop_level else nan)

    # =========================================================================
    # ENTRY EXECUTION
    # =========================================================================

    def _execute_entry(self, dt, spread, forecast):
        """Execute market entry based on forecast direction."""
        entry_price_b = float(self.data_b.close[0])
        atr_b_val = float(self.atr_b[0])

        if atr_b_val <= 0 or math.isnan(atr_b_val):
            return

        # Direction: OPPOSITE of forecast sign (negative correlation)
        # forecast > 0 (spread > 0, A high, B low) -> SHORT B
        # forecast < 0 (spread < 0, A low, B high) -> LONG B
        if forecast > 0:
            self.direction = -1     # SHORT B
        else:
            self.direction = +1     # LONG B

        # Direction filter: skip if direction is disabled
        if self.direction == 1 and not self.p.allow_long:
            return
        if self.direction == -1 and not self.p.allow_short:
            return

        position_fraction = abs(forecast) / self.p.max_forecast

        # Position sizing: margin-allocation proportional to forecast.
        # VEGA exits by TIME (99.5% of trades), not by stop loss.
        # The protective stop is a safety net, so risk_percent-based sizing
        # is too conservative. Instead, allocate margin proportional to
        # forecast strength: stronger signal -> more contracts.
        #
        # At max forecast: allocate capital_alloc_pct of equity as margin.
        # At partial forecast: scale linearly.
        # This matches the study's fractional sizing approach.
        equity = self.broker.get_value()
        margin_per_contract = entry_price_b * (self.p.margin_pct / 100.0)

        # JPY-denominated indices: margin is in JPY, convert to USD
        if self.p.is_jpy_pair and self.p.jpy_rate > 1:
            margin_per_contract = margin_per_contract / self.p.jpy_rate

        if margin_per_contract <= 0:
            return

        max_margin = equity * self.p.capital_alloc_pct * position_fraction
        contracts = int(max_margin / margin_per_contract)

        if contracts < 1:
            return  # Signal too weak for even 1 contract

        # Cap at absolute max
        abs_max = int(
            (equity * self.p.max_position_pct) / margin_per_contract)
        contracts = min(contracts, max(1, abs_max))

        # DD cap: if protective stop hit, max loss <= max_loss_per_trade_pct
        if self.p.use_protective_stop and atr_b_val > 0:
            stop_dist = atr_b_val * self.p.protective_atr_mult
            loss_per_contract = stop_dist
            if self.p.is_jpy_pair and self.p.jpy_rate > 1:
                loss_per_contract = loss_per_contract / self.p.jpy_rate
            max_loss = equity * self.p.max_loss_per_trade_pct
            if loss_per_contract > 0:
                dd_cap = int(max_loss / loss_per_contract)
                if dd_cap < contracts:
                    contracts = max(1, dd_cap)

        # Execute order
        if self.direction == 1:
            self.order_b = self.buy(data=self.data_b, size=contracts)
        else:
            self.order_b = self.sell(data=self.data_b, size=contracts)

        # Update state
        self.state = "IN_POSITION"
        self.entry_bar = len(self.data_b)
        self.entry_datetime = dt
        self.entry_price_b = entry_price_b
        self.entry_forecast = forecast

        # Protective stop
        if self.p.use_protective_stop:
            stop_dist = atr_b_val * self.p.protective_atr_mult
            if self.direction == 1:
                self.protective_stop_b = entry_price_b - stop_dist
            else:
                self.protective_stop_b = entry_price_b + stop_dist

        # Update plot
        self._update_plot_lines(entry_price_b, self.protective_stop_b)

        # Record
        self._record_trade_entry(
            dt, entry_price_b, contracts, self.direction,
            spread, forecast, atr_b_val)

        if self.p.print_signals:
            dir_str = 'LONG' if self.direction > 0 else 'SHORT'
            print(
                f"[VEGA] {dt} ENTRY {dir_str} {contracts}x "
                f"@ {entry_price_b:.2f} | "
                f"spread={spread:.3f} forecast={forecast:.1f} | "
                f"stop={self.protective_stop_b:.2f}")

    # =========================================================================
    # EXIT LOGIC
    # =========================================================================

    def _check_protective_stop(self):
        """Check if wide protective stop was hit."""
        if not self.p.use_protective_stop or self.protective_stop_b is None:
            return False

        if self.direction == 1:     # Long B
            if float(self.data_b.low[0]) <= self.protective_stop_b:
                return True
        else:                       # Short B
            if float(self.data_b.high[0]) >= self.protective_stop_b:
                return True
        return False

    def _check_take_profit(self):
        """Check if take profit level reached based on ATR multiple."""
        if self.p.tp_atr_mult <= 0 or self.entry_price_b is None:
            return False

        atr_b_val = float(self.atr_b[0])
        if atr_b_val <= 0 or math.isnan(atr_b_val):
            return False

        tp_dist = atr_b_val * self.p.tp_atr_mult
        current_price = float(self.data_b.close[0])

        if self.direction == 1:     # Long B
            return current_price >= self.entry_price_b + tp_dist
        else:                       # Short B
            return current_price <= self.entry_price_b - tp_dist

    def _execute_exit(self, dt, reason):
        """Close position on Index B."""
        self.last_exit_reason = reason
        self.close(data=self.data_b)

        # Clear plot lines
        self._update_plot_lines()

        # Reset state
        self.state = "SCANNING"
        self.entry_bar = None
        self.entry_datetime = None
        self.entry_price_b = None
        self.entry_forecast = None
        self.protective_stop_b = None
        self.direction = 0

        if self.p.print_signals:
            print(f"[VEGA] {dt} EXIT ({reason}) "
                  f"@ {self.data_b.close[0]:.2f}")

    # =========================================================================
    # ORDER / TRADE NOTIFICATIONS
    # =========================================================================

    def notify_order(self, order):
        """Handle order notifications."""
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status in [order.Canceled, order.Margin, order.Rejected]:
            if self.p.print_signals:
                status_names = {
                    order.Canceled: 'Canceled',
                    order.Margin: 'Margin',
                    order.Rejected: 'Rejected',
                }
                print(f'[VEGA] Order {status_names.get(order.status, "?")}')
            if self.state != "IN_POSITION":
                self.state = "SCANNING"

        if order.data == self.data_b:
            self.order_b = None

    def notify_trade(self, trade):
        """Handle trade close -- calculate real P&L from Backtrader."""
        if not trade.isclosed:
            return

        dt = self._get_datetime()
        pnl = trade.pnl

        self.trades += 1
        self._trade_pnls.append({
            'date': dt,
            'year': dt.year,
            'pnl': pnl,
            'is_winner': pnl > 0,
        })

        if pnl > 0:
            self.wins += 1
            self.gross_profit += pnl
        else:
            self.losses += 1
            self.gross_loss += abs(pnl)

        reason = self.last_exit_reason or "UNKNOWN"
        self._record_trade_exit(dt, pnl, reason)

        if self.p.print_signals:
            print(f"[VEGA] {dt} TRADE CLOSED ({reason}) | "
                  f"P&L: ${pnl:.2f}")

        self.last_exit_reason = None

    # =========================================================================
    # MAIN LOOP
    # =========================================================================

    def next(self):
        """Main strategy loop -- called each H1 bar."""

        # Compute spread every bar (for plotting)
        spread, z_a, z_b = self._compute_spread()
        forecast = self._compute_forecast(spread)

        # Update spread subplot (forecast normalized to spread scale)
        self.spread_ind.lines.spread[0] = spread
        dz = self.p.dead_zone if self.p.dead_zone > 0 else 1.0
        self.spread_ind.lines.forecast_norm[0] = (
            forecast / self.p.max_forecast * dz)
        self.spread_ind.lines.dead_zone_upper[0] = dz
        self.spread_ind.lines.dead_zone_lower[0] = -dz

        # Track portfolio value
        self._portfolio_values.append(self.broker.get_value())

        dt = self._get_datetime()
        if self._first_bar_dt is None:
            self._first_bar_dt = dt
        self._last_bar_dt = dt

        # Skip if order pending
        if self.order_b:
            return

        # === STATE MACHINE ===

        if self.state == "IN_POSITION":
            # Check protective stop first (safety net)
            if self._check_protective_stop():
                self._execute_exit(dt, 'PROT_STOP')
                return

            # Check take profit
            if self._check_take_profit():
                self._execute_exit(dt, 'TP_EXIT')
                return

            # Check holding period
            bars_held = len(self.data_b) - self.entry_bar
            if bars_held >= self.p.holding_hours:
                self._execute_exit(dt, 'TIME_EXIT')
                return

            # Update plot lines while in position
            self._update_plot_lines(
                self.entry_price_b, self.protective_stop_b)

        elif self.state == "SCANNING":
            # Time filter
            if self.p.use_time_filter:
                if not check_time_filter(
                        dt, self.p.allowed_hours, True):
                    return

            # Day filter
            if self.p.use_day_filter:
                if not check_day_filter(
                        dt, self.p.allowed_days, True):
                    return

            # Check that enough time remains to hold
            latest_entry_hour = (
                self.p.session_end_hour + self.p.holding_hours)
            # No explicit block needed; allowed_hours handles entry window

            # Max trades per day filter
            if self.p.max_trades_per_day > 0:
                current_date = dt.date()
                if self.last_trade_date != current_date:
                    self.last_trade_date = current_date
                    self.trades_today = 0
                if self.trades_today >= self.p.max_trades_per_day:
                    return

            # Dead zone / forecast threshold
            if abs(forecast) < self.p.min_forecast_entry:
                return

            # Enter
            self.trades_today += 1
            self._execute_entry(dt, spread, forecast)

    # =========================================================================
    # STOP -- FINAL REPORT (same structure as GEMINI)
    # =========================================================================

    def stop(self):
        """Generate final report with advanced metrics."""
        total_trades = self.trades
        win_rate = (
            (self.wins / total_trades * 100) if total_trades > 0 else 0)
        profit_factor = (
            (self.gross_profit / self.gross_loss)
            if self.gross_loss > 0 else float('inf'))
        total_pnl = self.gross_profit - self.gross_loss
        final_value = self.broker.get_value()

        # Data-driven periods_per_year
        if self._first_bar_dt and self._last_bar_dt:
            data_days = (self._last_bar_dt - self._first_bar_dt).days
            data_years = max(data_days / 365.25, 0.1)
            periods_per_year = len(self._portfolio_values) / data_years
        else:
            periods_per_year = 252 * 24  # Fallback: H1 bars

        # Sharpe Ratio
        sharpe_ratio = 0.0
        if len(self._portfolio_values) > 10:
            returns = []
            for i in range(1, len(self._portfolio_values)):
                prev = self._portfolio_values[i - 1]
                if prev > 0:
                    returns.append(
                        (self._portfolio_values[i] - prev) / prev)
            if returns:
                arr = np.array(returns)
                mean_r = np.mean(arr)
                std_r = np.std(arr)
                if std_r > 0:
                    sharpe_ratio = (
                        (mean_r * periods_per_year)
                        / (std_r * np.sqrt(periods_per_year)))

        # Max Drawdown
        max_drawdown_pct = 0.0
        if self._portfolio_values:
            peak = self._portfolio_values[0]
            for val in self._portfolio_values:
                if val > peak:
                    peak = val
                dd = (peak - val) / peak * 100 if peak > 0 else 0
                if dd > max_drawdown_pct:
                    max_drawdown_pct = dd

        # CAGR
        cagr = 0.0
        if self._starting_cash > 0 and final_value > 0:
            total_return = final_value / self._starting_cash
            if self.trade_reports:
                first_t = (self.trade_reports[0].get('exit_time')
                           or self.trade_reports[0].get('entry_time'))
                last_t = (self.trade_reports[-1].get('exit_time')
                          or self.trade_reports[-1].get('entry_time'))
                if first_t and last_t:
                    years = max((last_t - first_t).days / 365.25, 0.1)
                else:
                    years = max(
                        len(self._portfolio_values) / periods_per_year,
                        0.1)
            else:
                years = max(
                    len(self._portfolio_values) / periods_per_year, 0.1)
            if total_return > 0:
                cagr = (pow(total_return, 1.0 / years) - 1.0) * 100.0

        # Sortino Ratio
        sortino_ratio = 0.0
        if len(self._portfolio_values) > 10:
            returns = []
            for i in range(1, len(self._portfolio_values)):
                prev = self._portfolio_values[i - 1]
                if prev > 0:
                    returns.append(
                        (self._portfolio_values[i] - prev) / prev)
            if returns:
                arr = np.array(returns)
                mean_r = np.mean(arr)
                neg = arr[arr < 0]
                if len(neg) > 0:
                    dd_std = np.std(neg)
                    if dd_std > 0:
                        sortino_ratio = (
                            (mean_r * periods_per_year)
                            / (dd_std * np.sqrt(periods_per_year)))

        # Calmar Ratio
        calmar_ratio = (
            cagr / max_drawdown_pct if max_drawdown_pct > 0 else 0)

        # Monte Carlo (10,000 sims)
        mc_dd_95 = 0.0
        mc_dd_99 = 0.0
        if len(self._trade_pnls) >= 30:
            pnl_vals = np.array([t['pnl'] for t in self._trade_pnls])
            mc_dds = []
            for _ in range(10000):
                shuffled = np.random.choice(
                    pnl_vals, size=len(pnl_vals), replace=True)
                cumsum = np.cumsum(shuffled)
                running_max = np.maximum.accumulate(
                    cumsum + self._starting_cash)
                drawdowns = (
                    (running_max - (cumsum + self._starting_cash))
                    / running_max * 100)
                mc_dds.append(np.max(drawdowns))
            mc_dd_95 = np.percentile(mc_dds, 95)
            mc_dd_99 = np.percentile(mc_dds, 99)

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

        # Yearly Sharpe / Sortino
        for year in yearly_stats:
            pnls = yearly_stats[year]['pnls']
            if len(pnls) > 1:
                pnl_arr = np.array(pnls)
                mean_p = np.mean(pnl_arr)
                std_p = np.std(pnl_arr)
                yearly_stats[year]['sharpe'] = (
                    (mean_p / std_p) * np.sqrt(len(pnls))
                    if std_p > 0 else 0.0)
                neg_p = pnl_arr[pnl_arr < 0]
                if len(neg_p) > 0:
                    dd_s = np.std(neg_p)
                    yearly_stats[year]['sortino'] = (
                        (mean_p / dd_s) * np.sqrt(len(pnls))
                        if dd_s > 0 else 0.0)
                else:
                    yearly_stats[year]['sortino'] = (
                        float('inf') if mean_p > 0 else 0.0)
            else:
                yearly_stats[year]['sharpe'] = 0.0
                yearly_stats[year]['sortino'] = 0.0

        # Exit reason breakdown
        exit_reasons = defaultdict(int)
        for t in self.trade_reports:
            exit_reasons[t.get('exit_reason', 'UNKNOWN')] += 1

        # =================================================================
        # PRINT SUMMARY
        # =================================================================
        print('\n' + '=' * 70)
        print('=== VEGA STRATEGY SUMMARY ===')
        print('=' * 70)

        print(f'Index A: {self.data_a._name} (reference)')
        print(f'Index B: {self.data_b._name} (traded)')
        print(f'Z-score: SMA={self.p.sma_period}, '
              f'ATR={self.p.atr_period}')
        print(f'Dead Zone: {self.p.dead_zone} | '
              f'Holding: {self.p.holding_hours}h')

        print(f'\nTotal Trades: {total_trades}')
        print(f'Wins: {self.wins} | Losses: {self.losses}')
        print(f'Win Rate: {win_rate:.1f}%')
        print(f'Profit Factor: {profit_factor:.2f}')
        print(f'Gross Profit: ${self.gross_profit:,.2f}')
        print(f'Gross Loss: ${self.gross_loss:,.2f}')
        print(f'Net P&L: ${total_pnl:,.2f}')
        print(f'Final Value: ${final_value:,.2f}')

        # Exit reasons
        if exit_reasons:
            print(f'\nExit Reasons:')
            for reason, count in sorted(exit_reasons.items()):
                pct = count / total_trades * 100 if total_trades > 0 else 0
                print(f'  {reason}: {count} ({pct:.1f}%)')

        # Advanced Metrics
        print(f"\n{'=' * 70}")
        print('ADVANCED RISK METRICS')
        print(f"{'=' * 70}")

        sh_status = ("Poor" if sharpe_ratio < 0.5
                     else "Marginal" if sharpe_ratio < 1.0
                     else "Good" if sharpe_ratio < 2.0
                     else "Excellent")
        print(f'Sharpe Ratio:    {sharpe_ratio:>8.2f}  [{sh_status}]')

        so_status = ("Poor" if sortino_ratio < 0.5
                     else "Marginal" if sortino_ratio < 1.0
                     else "Good" if sortino_ratio < 2.0
                     else "Excellent")
        print(f'Sortino Ratio:   {sortino_ratio:>8.2f}  [{so_status}]')

        cagr_status = ("Below Market" if cagr < 8
                       else "Market-level" if cagr < 12
                       else "Good" if cagr < 20
                       else "Exceptional")
        print(f'CAGR:            {cagr:>7.2f}%  [{cagr_status}]')

        dd_status = ("Excellent" if max_drawdown_pct < 10
                     else "Acceptable" if max_drawdown_pct < 20
                     else "High" if max_drawdown_pct < 30
                     else "Dangerous")
        print(f'Max Drawdown:    {max_drawdown_pct:>7.2f}%  [{dd_status}]')

        cal_status = ("Poor" if calmar_ratio < 0.5
                      else "Acceptable" if calmar_ratio < 1.0
                      else "Good" if calmar_ratio < 2.0
                      else "Excellent")
        print(f'Calmar Ratio:    {calmar_ratio:>8.2f}  [{cal_status}]')

        if mc_dd_95 > 0:
            mc_ratio = (mc_dd_95 / max_drawdown_pct
                        if max_drawdown_pct > 0 else 0)
            mc_status = ("Good" if mc_ratio < 1.5
                         else "Caution" if mc_ratio < 2.0
                         else "Warning")
            print(f'\nMonte Carlo Analysis (10,000 simulations):')
            print(f'  95th Pctile DD: {mc_dd_95:>6.2f}%  [{mc_status}]')
            print(f'  99th Pctile DD: {mc_dd_99:>6.2f}%')
            print(f'  Historical vs MC95: {mc_ratio:.2f}x')

        print(f"{'=' * 70}")

        # Yearly Statistics
        if yearly_stats:
            print(f"\n{'=' * 70}")
            print('YEARLY STATISTICS')
            print(f"{'=' * 70}")
            print(f"{'Year':<6} {'Trades':>7} {'WR%':>7} "
                  f"{'PF':>7} {'PnL':>12} "
                  f"{'Sharpe':>8} {'Sortino':>8}")
            print(f"{'-' * 70}")

            for year in sorted(yearly_stats.keys()):
                s = yearly_stats[year]
                wr = (s['wins'] / s['trades'] * 100
                      if s['trades'] > 0 else 0)
                pf = (s['gross_profit'] / s['gross_loss']
                      if s['gross_loss'] > 0 else float('inf'))
                y_sh = s.get('sharpe', 0.0)
                y_so = s.get('sortino', 0.0)
                pf_str = (f"{pf:>7.2f}"
                          if pf != float('inf') else "    inf")
                so_str = (f"{y_so:>7.2f}"
                          if y_so != float('inf') else "    inf")
                print(f"{year:<6} {s['trades']:>7} {wr:>6.1f}% "
                      f"{pf_str} ${s['pnl']:>10,.0f} "
                      f"{y_sh:>8.2f} {so_str}")

            print(f"{'=' * 70}")

        # Commission summary — read actual commission from broker's CommInfo
        total_contracts = sum(
            t.get('size', 0) for t in self.trade_reports if 'size' in t)

        # Use actual accumulated commission from CFDIndexCommission class
        from lib.commission import CFDIndexCommission
        actual_total_comm = CFDIndexCommission.total_commission
        actual_total_contracts = CFDIndexCommission.total_contracts
        avg_commission = (
            actual_total_comm / total_trades if total_trades > 0 else 0)

        print(f"\n{'=' * 70}")
        print('COMMISSION SUMMARY (CFD Index)')
        print(f"{'=' * 70}")
        print(f'Total Contract-Units Traded:  {actual_total_contracts:,.0f}')
        print(f'Total Commission Paid:        ${actual_total_comm:,.2f}')
        print(f'Avg Comm per Trade:           ${avg_commission:,.2f}')
        print(f"{'=' * 70}")

        # Final summary
        total_return = (
            ((final_value - self._starting_cash) / self._starting_cash * 100)
            if self._starting_cash > 0 else 0)
        print(f'\nFinal Value: ${final_value:,.2f}')
        print(f'Return: {total_return:.2f}%')

        # Close trade report file
        if self.trade_report_file:
            try:
                self.trade_report_file.write("\n=== SUMMARY ===\n")
                self.trade_report_file.write(
                    f"Total Trades: {total_trades}\n")
                self.trade_report_file.write(
                    f"Wins: {self.wins} | Losses: {self.losses}\n")
                self.trade_report_file.write(
                    f"Win Rate: {win_rate:.1f}%\n")
                self.trade_report_file.write(
                    f"Profit Factor: {profit_factor:.2f}\n")
                self.trade_report_file.write(
                    f"Sharpe Ratio: {sharpe_ratio:.2f}\n")
                self.trade_report_file.write(
                    f"Max Drawdown: {max_drawdown_pct:.2f}%\n")
                self.trade_report_file.write(
                    f"CAGR: {cagr:.2f}%\n")
                self.trade_report_file.write(
                    f"Net P&L: ${total_pnl:,.2f}\n")
                self.trade_report_file.write(
                    f"Total Return: {total_return:.2f}%\n")
                self.trade_report_file.close()
            except Exception:
                pass
