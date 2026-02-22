"""
KOI Strategy - Bullish Engulfing + 5 EMA + CCI + Breakout Window

ENTRY SYSTEM (4 PHASES):
1. PATTERN: Bullish engulfing candle detected
2. TREND: All 5 EMAs ascending (EMA[0] > EMA[-1])
3. MOMENTUM: CCI > threshold
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
    check_day_filter,
    check_atr_filter,
    check_sl_pips_filter,
)
from lib.position_sizing import calculate_position_size


class KOIStrategy(bt.Strategy):
    """
    KOI Strategy implementation.
    Uses lib/filters.py and lib/position_sizing.py for consistency.
    """
    
    params = dict(
        # 5 EMAs
        ema_1_period=10,
        ema_2_period=20,
        ema_3_period=40,
        ema_4_period=80,
        ema_5_period=120,
        
        # CCI
        cci_period=20,
        cci_threshold=110,
        cci_max_threshold=999,  # Max CCI (999 = disabled)
        
        # ATR for SL/TP
        atr_length=10,
        atr_sl_multiplier=2.0,
        atr_tp_multiplier=6.0,
        
        # Breakout Window
        use_breakout_window=True,
        breakout_window_candles=3,
        breakout_level_offset_pips=2.0,
        
        # === FILTERS (all with use_xxx flag) ===
        
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
        
        # === ASSET CONFIG ===
        pip_value=0.0001,
        is_jpy_pair=False,
        jpy_rate=150.0,
        lot_size=100000,
        is_etf=False,
        margin_pct=3.33,
        
        # EOD Close (ETFs only) - force close before market close
        eod_close_hour=None,
        eod_close_minute=None,
        
        # Risk
        risk_percent=0.005,
        
        # Debug & Reporting
        print_signals=False,
        export_reports=True,
    )

    def __init__(self):
        d = self.data
        
        # Indicators
        self.ema_1 = bt.ind.EMA(d.close, period=self.p.ema_1_period)
        self.ema_2 = bt.ind.EMA(d.close, period=self.p.ema_2_period)
        self.ema_3 = bt.ind.EMA(d.close, period=self.p.ema_3_period)
        self.ema_4 = bt.ind.EMA(d.close, period=self.p.ema_4_period)
        self.ema_5 = bt.ind.EMA(d.close, period=self.p.ema_5_period)
        self.cci = bt.ind.CCI(d, period=self.p.cci_period)
        self.atr = bt.ind.ATR(d, period=self.p.atr_length)
        
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
        
        # Trade reporting (KOI generates its own log like original)
        self.trade_reports = []
        self.trade_report_file = None
        self._current_trade_idx = None  # Index of active trade in trade_reports
        self._entry_fill_bar = -1  # Bar where buy filled (skip EOD close on same bar)
        self._init_trade_reporting()

    # =========================================================================
    # TRADE REPORTING (same as original koi_eurusd_pro.py)
    # =========================================================================
    
    def _init_trade_reporting(self):
        """Initialize trade report file."""
        if not self.p.export_reports:
            return
        try:
            report_dir = Path("logs")
            report_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_path = report_dir / f"KOI_trades_{timestamp}.txt"
            self.trade_report_file = open(report_path, 'w', encoding='utf-8')
            self.trade_report_file.write("=== KOI STRATEGY TRADE REPORT ===\n")
            self.trade_report_file.write(f"Generated: {datetime.now()}\n")
            self.trade_report_file.write(f"EMAs: {self.p.ema_1_period}, {self.p.ema_2_period}, "
                                        f"{self.p.ema_3_period}, {self.p.ema_4_period}, {self.p.ema_5_period}\n")
            self.trade_report_file.write(f"CCI: {self.p.cci_period}/{self.p.cci_threshold}\n")
            self.trade_report_file.write(f"Breakout: {self.p.breakout_level_offset_pips}pips, {self.p.breakout_window_candles}bars\n")
            self.trade_report_file.write(f"SL: {self.p.atr_sl_multiplier}x ATR | TP: {self.p.atr_tp_multiplier}x ATR\n")
            if self.p.use_sl_pips_filter:
                self.trade_report_file.write(f"SL Filter: {self.p.sl_pips_min}-{self.p.sl_pips_max} pips\n")
            if self.p.use_atr_filter:
                self.trade_report_file.write(f"ATR Filter: {self.p.atr_min}-{self.p.atr_max}\n")
            if self.p.use_time_filter:
                self.trade_report_file.write(f"Time Filter: {list(self.p.allowed_hours)}\n")
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
            self._current_trade_idx = len(self.trade_reports) - 1
            self.trade_report_file.write(f"ENTRY #{len(self.trade_reports)}\n")
            self.trade_report_file.write(f"Time: {dt.strftime('%Y-%m-%d %H:%M:%S')}\n")
            self.trade_report_file.write(f"Entry Price: {entry_price:.5f}\n")
            self.trade_report_file.write(f"Stop Loss: {self.stop_level:.5f}\n")
            self.trade_report_file.write(f"Take Profit: {self.take_level:.5f}\n")
            self.trade_report_file.write(f"SL Pips: {sl_pips:.1f}\n")
            self.trade_report_file.write(f"ATR: {atr:.6f}\n")
            self.trade_report_file.write(f"CCI: {cci:.2f}\n")
            self.trade_report_file.write("-" * 50 + "\n\n")
            self.trade_report_file.flush()
        except Exception as e:
            pass

    def _record_trade_exit(self, dt, pnl, reason):
        """Record exit to trade report file."""
        if not self.trade_report_file or not self.trade_reports:
            return
        # Skip recording for phantom trades (e.g. accidental shorts)
        if self._current_trade_idx is None:
            return
        try:
            last_trade = self.trade_reports[self._current_trade_idx]
            last_trade['pnl'] = pnl
            last_trade['exit_reason'] = reason
            last_trade['exit_time'] = dt
            self.trade_report_file.write(f"EXIT #{len(self.trade_reports)}\n")
            self.trade_report_file.write(f"Time: {dt.strftime('%Y-%m-%d %H:%M:%S')}\n")
            self.trade_report_file.write(f"Exit Reason: {reason}\n")
            self.trade_report_file.write(f"P&L: ${pnl:.2f}\n")
            self.trade_report_file.write("=" * 80 + "\n\n")
            self.trade_report_file.flush()
            self._current_trade_idx = None
        except:
            pass

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
    # PATTERN DETECTION (EXACT from original koi_eurusd_pro.py)
    # =========================================================================
    
    def _check_bullish_engulfing(self) -> bool:
        """Check for bullish engulfing pattern."""
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

    def _check_emas_ascending(self) -> bool:
        """Check if ALL 5 EMAs are individually ascending."""
        try:
            emas = [self.ema_1, self.ema_2, self.ema_3, self.ema_4, self.ema_5]
            for ema in emas:
                if float(ema[0]) <= float(ema[-1]):
                    return False
            return True
        except:
            return False

    def _check_cci_condition(self) -> bool:
        """Check if CCI > threshold and < max_threshold."""
        try:
            cci_val = float(self.cci[0])
            if cci_val <= self.p.cci_threshold:
                return False
            if cci_val >= self.p.cci_max_threshold:
                return False
            return True
        except:
            return False

    def _check_eod_close(self, dt):
        """
        Check if position should be force-closed at end of day (ETFs only).
        
        Returns True if position was closed, False otherwise.
        """
        if self.p.eod_close_hour is None or self.p.eod_close_minute is None:
            return False
        
        current_minutes = dt.hour * 60 + dt.minute
        eod_minutes = self.p.eod_close_hour * 60 + self.p.eod_close_minute
        
        if current_minutes >= eod_minutes:
            # Set exit reason before close so notify_order picks it up
            self.last_exit_reason = "EOD_CLOSE"
            
            # Cancel protective orders
            if self.stop_order:
                self.cancel(self.stop_order)
                self.stop_order = None
            if self.limit_order:
                self.cancel(self.limit_order)
                self.limit_order = None
            
            # Force close at market
            self.close()
            
            if self.p.print_signals:
                print(
                    f'{dt} [{self.data._name}] === EOD CLOSE @ '
                    f'{self.data.close[0]:.2f} (forced {self.p.eod_close_hour}:'
                    f'{self.p.eod_close_minute:02d} UTC) ==='
                )
            
            return True
        
        return False

    def _check_entry_conditions(self, dt: datetime) -> bool:
        """Check all entry conditions."""
        if self.position or self.order:
            return False
        
        if not check_time_filter(dt, self.p.allowed_hours, self.p.use_time_filter):
            return False
        
        if not check_day_filter(dt, self.p.allowed_days, self.p.use_day_filter):
            return False
        
        if not self._check_bullish_engulfing():
            return False
        
        if not self._check_emas_ascending():
            return False
        
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
    # ENTRY EXECUTION
    # =========================================================================
    
    def _execute_entry(self, dt: datetime, atr_now: float, cci_now: float):
        """Execute entry with all filters applied."""
        # ATR filter
        if not check_atr_filter(atr_now, self.p.atr_min, self.p.atr_max, self.p.use_atr_filter):
            return
        
        entry_price = float(self.data.close[0])
        self.stop_level = entry_price - (atr_now * self.p.atr_sl_multiplier)
        self.take_level = entry_price + (atr_now * self.p.atr_tp_multiplier)
        
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
            print(f">>> KOI BUY {dt:%Y-%m-%d %H:%M} price={entry_price:.5f} "
                  f"SL={self.stop_level:.5f} TP={self.take_level:.5f} CCI={cci_now:.0f} SL_pips={sl_pips:.1f}")
        
        self._record_trade_entry(dt, entry_price, bt_size, atr_now, cci_now, sl_pips)

    # =========================================================================
    # MAIN LOOP
    # =========================================================================
    
    def next(self):
        """Main loop with breakout window state machine."""
        self._portfolio_values.append(self.broker.get_value())
        
        dt = self._get_datetime()
        
        # Track date range for data-driven annualization
        if self._first_bar_dt is None:
            self._first_bar_dt = dt
        self._last_bar_dt = dt
        current_bar = len(self)
        
        if self.order:
            return
        
        if self.position:
            # Skip EOD close on bar where buy just filled (prevents cancel race condition)
            if len(self) != self._entry_fill_bar and self._check_eod_close(dt):
                return
            if self.state != "SCANNING":
                self._reset_breakout_state()
            return
        
        # State machine for breakout window
        if self.p.use_breakout_window:
            if self.state == "SCANNING":
                if self._check_entry_conditions(dt):
                    atr_now = float(self.atr[0]) if not math.isnan(float(self.atr[0])) else 0
                    cci_now = float(self.cci[0])
                    if atr_now <= 0:
                        return
                    
                    self.pattern_detected_bar = current_bar
                    offset = self.p.breakout_level_offset_pips * self.p.pip_value
                    self.breakout_level = float(self.data.high[0]) + offset
                    self.pattern_atr = atr_now
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
                atr_now = float(self.atr[0]) if not math.isnan(float(self.atr[0])) else 0
                cci_now = float(self.cci[0])
                if atr_now > 0:
                    self._execute_entry(dt, atr_now, cci_now)

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
                self._entry_fill_bar = len(self)  # Track fill bar for EOD close race prevention
                
                if self.p.print_signals:
                    print(f"[OK] KOI BUY EXECUTED at {order.executed.price:.5f} size={order.executed.size}")

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

            else:  # Exit order (SL/TP)
                exit_reason = "UNKNOWN"
                if order.exectype == bt.Order.Stop:
                    exit_reason = "STOP_LOSS"
                elif order.exectype == bt.Order.Limit:
                    exit_reason = "TAKE_PROFIT"
                
                # Preserve EOD_CLOSE reason if already set by _check_eod_close
                if self.last_exit_reason != "EOD_CLOSE":
                    self.last_exit_reason = exit_reason
                
                if self.p.print_signals:
                    print(f"[EXIT] at {order.executed.price:.5f} reason={exit_reason}")

                self.stop_order = None
                self.limit_order = None
                self.order = None
                self.stop_level = None
                self.take_level = None

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            is_expected_cancel = (self.stop_order and self.limit_order)
            if not is_expected_cancel and self.p.print_signals:
                print(f"Order {order.getstatusname()}: {order.ref}")
            
            if self.order and order.ref == self.order.ref:
                # Buy order rejected/margin — write N/A exit for orphan entry
                if self._current_trade_idx is not None and self.trade_report_file:
                    self.trade_report_file.write(f"EXIT #{self._current_trade_idx + 1}\n")
                    self.trade_report_file.write("Time: N/A\n")
                    self.trade_report_file.write(f"Exit Reason: {order.getstatusname()}\n")
                    self.trade_report_file.write("P&L: $0.00\n")
                    self.trade_report_file.write("=" * 80 + "\n\n")
                    self.trade_report_file.flush()
                self._current_trade_idx = None
                self.order = None
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
    # STATISTICS (same as original)
    # =========================================================================
    
    def stop(self):
        """Strategy end - print summary with advanced metrics."""
        final_value = self.broker.get_value()
        total_pnl = final_value - self._starting_cash
        win_rate = (self.wins / self.trades * 100) if self.trades > 0 else 0
        profit_factor = (self.gross_profit / self.gross_loss) if self.gross_loss > 0 else float('inf')
        
        # =================================================================
        # ADVANCED METRICS: Drawdown, Sharpe, Sortino, CAGR, Calmar
        # =================================================================
        max_drawdown_pct = 0.0
        sharpe_ratio = 0.0
        sortino_ratio = 0.0
        cagr = 0.0
        calmar_ratio = 0.0
        monte_carlo_dd_95 = 0.0
        monte_carlo_dd_99 = 0.0
        
        # Max Drawdown
        if self._portfolio_values:
            peak = self._portfolio_values[0]
            for value in self._portfolio_values:
                if value > peak:
                    peak = value
                drawdown = (peak - value) / peak * 100.0
                if drawdown > max_drawdown_pct:
                    max_drawdown_pct = drawdown
        
        # Daily returns for Sharpe/Sortino
        daily_returns = []
        if self._trade_pnls:
            daily_pnl = defaultdict(float)
            for trade in self._trade_pnls:
                date_key = trade['date'].date()
                daily_pnl[date_key] += trade['pnl']
            
            equity = self._starting_cash
            sorted_dates = sorted(daily_pnl.keys())
            for date in sorted_dates:
                pnl = daily_pnl[date]
                if equity > 0:
                    daily_ret = pnl / equity
                    daily_returns.append(daily_ret)
                    equity += pnl
        
        # Compute data-driven periods_per_year from actual bar dates
        if self._first_bar_dt and self._last_bar_dt:
            data_days = (self._last_bar_dt - self._first_bar_dt).days
            data_years = max(data_days / 365.25, 0.1)
            periods_per_year = len(self._portfolio_values) / data_years
        else:
            periods_per_year = 252 * 24 * 12  # Fallback: forex 5-min
        
        # SHARPE RATIO (same calculation as original sunrise_ogle)
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
                if std_return > 0:
                    sharpe_ratio = (mean_return * periods_per_year) / (std_return * np.sqrt(periods_per_year))
        
        # SORTINO RATIO (same calculation as original sunrise_ogle)
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
                    if downside_dev > 0:
                        sortino_ratio = (mean_return * periods_per_year) / (downside_dev * np.sqrt(periods_per_year))
        
        # CAGR
        if self._portfolio_values and self._trade_pnls and self._starting_cash > 0:
            total_return = final_value / self._starting_cash
            if total_return > 0:
                first_date = self._trade_pnls[0]['date']
                last_date = self._trade_pnls[-1]['date']
                days = (last_date - first_date).days
                years = max(days / 365.25, 0.1)
                cagr = (pow(total_return, 1.0 / years) - 1.0) * 100.0
        
        # Calmar Ratio
        if max_drawdown_pct > 0:
            calmar_ratio = cagr / max_drawdown_pct
        
        # =================================================================
        # MONTE CARLO SIMULATION
        # =================================================================
        if self._trade_pnls and len(self._trade_pnls) >= 20:
            n_simulations = 10000
            pnl_list = [t['pnl'] for t in self._trade_pnls]
            mc_max_drawdowns = []
            
            for _ in range(n_simulations):
                shuffled_pnl = np.random.permutation(pnl_list)
                equity = self._starting_cash
                peak = equity
                max_dd = 0.0
                
                for pnl in shuffled_pnl:
                    equity += pnl
                    if equity > peak:
                        peak = equity
                    dd = (peak - equity) / peak * 100.0 if peak > 0 else 0.0
                    if dd > max_dd:
                        max_dd = dd
                
                mc_max_drawdowns.append(max_dd)
            
            mc_max_drawdowns = np.array(mc_max_drawdowns)
            monte_carlo_dd_95 = np.percentile(mc_max_drawdowns, 95)
            monte_carlo_dd_99 = np.percentile(mc_max_drawdowns, 99)
        
        # =================================================================
        # YEARLY STATISTICS
        # =================================================================
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
        
        # =================================================================
        # PRINT SUMMARY
        # =================================================================
        print("\n" + "=" * 70)
        print("=== KOI STRATEGY SUMMARY ===")
        print("=" * 70)
        
        print(f"Total Trades: {self.trades}")
        print(f"Wins: {self.wins} | Losses: {self.losses}")
        print(f"Win Rate: {win_rate:.1f}%")
        print(f"Profit Factor: {profit_factor:.2f}")
        print(f"Gross Profit: ${self.gross_profit:,.2f}")
        print(f"Gross Loss: ${self.gross_loss:,.2f}")
        print(f"Net P&L: ${total_pnl:,.0f}")
        print(f"Final Value: ${final_value:,.0f}")
        
        # Advanced Metrics with quality indicators
        print(f"\n{'='*70}")
        print("ADVANCED RISK METRICS")
        print(f"{'='*70}")
        
        sharpe_status = "Poor" if sharpe_ratio < 0.5 else "Marginal" if sharpe_ratio < 1.0 else "Good" if sharpe_ratio < 2.0 else "Excellent"
        print(f"Sharpe Ratio:        {sharpe_ratio:>8.2f}  [{sharpe_status}]")
        
        sortino_status = "Poor" if sortino_ratio < 0.5 else "Marginal" if sortino_ratio < 1.0 else "Good" if sortino_ratio < 2.0 else "Excellent"
        print(f"Sortino Ratio:       {sortino_ratio:>8.2f}  [{sortino_status}]")
        
        cagr_status = "Below Market" if cagr < 8 else "Market-level" if cagr < 12 else "Good" if cagr < 20 else "Exceptional"
        print(f"CAGR:                {cagr:>7.2f}%  [{cagr_status}]")
        
        dd_status = "Excellent" if max_drawdown_pct < 10 else "Acceptable" if max_drawdown_pct < 20 else "High" if max_drawdown_pct < 30 else "Dangerous"
        print(f"Max Drawdown:        {max_drawdown_pct:>7.2f}%  [{dd_status}]")
        
        calmar_status = "Poor" if calmar_ratio < 0.5 else "Acceptable" if calmar_ratio < 1.0 else "Good" if calmar_ratio < 2.0 else "Excellent"
        print(f"Calmar Ratio:        {calmar_ratio:>8.2f}  [{calmar_status}]")
        
        # Monte Carlo Analysis
        if monte_carlo_dd_95 > 0:
            mc_ratio = monte_carlo_dd_95 / max_drawdown_pct if max_drawdown_pct > 0 else 0
            mc_status = "Good" if mc_ratio < 1.5 else "Caution" if mc_ratio < 2.0 else "Warning"
            print(f"\nMonte Carlo Analysis (10,000 simulations):")
            print(f"  95th Percentile DD: {monte_carlo_dd_95:>6.2f}%  [{mc_status}]")
            print(f"  99th Percentile DD: {monte_carlo_dd_99:>6.2f}%")
            print(f"  Historical vs MC95: {mc_ratio:.2f}x")
        
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
        print("ACTIVE FILTERS")
        print(f"{'='*70}")
        if self.p.use_time_filter:
            print(f"  Time Filter: hours {list(self.p.allowed_hours)}")
        if self.p.use_day_filter:
            print(f"  Day Filter: days {list(self.p.allowed_days)}")
        if self.p.use_sl_pips_filter:
            print(f"  SL Pips Filter: {self.p.sl_pips_min}-{self.p.sl_pips_max}")
        if self.p.use_atr_filter:
            print(f"  ATR Filter: {self.p.atr_min}-{self.p.atr_max}")
        if not any([self.p.use_time_filter, self.p.use_day_filter, self.p.use_sl_pips_filter, self.p.use_atr_filter]):
            print("  No filters active")
        print("=" * 70)
        
        # Close report file
        if self.trade_report_file:
            self.trade_report_file.close()
            print(f"\nTrade report saved.")