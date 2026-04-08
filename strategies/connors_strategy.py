"""
Connors RSI(2) Mean-Reversion Strategy
=======================================

Published system by Larry Connors — ZERO optimizable parameters.
All values taken directly from Connors' research:

  - Filter:  Close > SMA(200)  (only trade uptrends)
  - Entry:   RSI(2) < threshold (default 10)
  - Exit:    Close > SMA(5)
  - Timeout: max_hold_days (default 20)
  - Direction: LONG only

Optional (off by default):
  - Protective SL: atr_sl_multiplier x ATR below entry
  - Take Profit:   atr_tp_multiplier x ATR above entry
  - Dynamic sizing: risk_percent based on SL distance

Validated on SP500 Daily 15Y (2010-2024):
  Score 4.17, 118 trades, WR 78.8%, 80% positive years.

Reference: tools/connors_rsi2_definitive.py
"""

import os
from collections import defaultdict
from datetime import datetime

import backtrader as bt
import numpy as np

from lib.position_sizing import calculate_position_size
from lib.filters import check_time_filter, check_day_filter


class CONNORSStrategy(bt.Strategy):

    params = dict(
        # --- Connors RSI(2) published parameters (DO NOT OPTIMIZE) ---
        rsi_period=2,
        sma_trend_period=200,
        sma_exit_period=5,
        rsi_threshold=10,
        max_hold_days=20,

        # --- Optional SL/TP by ATR (off by default = Connors original) ---
        atr_period=14,
        use_protective_stop=False,
        atr_sl_multiplier=2.0,
        sl_buffer_pips=0.0,
        use_take_profit=False,
        atr_tp_multiplier=3.0,

        # --- Entry filters (all off by default = no filtering) ---
        use_time_filter=False,
        allowed_hours=[],           # e.g. [7,8,9,10,11,12] = only enter 07-12 UTC
        use_day_filter=False,
        allowed_days=[],            # e.g. [0,1,2,3] = Mon-Thu (skip Fri)
        min_atr_entry=0.0,          # Min ATR to enter (0=disabled)
        max_atr_entry=0.0,          # Max ATR to enter (0=disabled)

        # --- Asset / Risk (auto-injected by run_backtest.py) ---
        risk_percent=0.01,
        pip_value=1.0,
        lot_size=1,
        jpy_rate=1.0,
        is_jpy_pair=False,
        is_etf=True,
        margin_pct=5.0,

        # --- Sizing mode ---
        # 'risk' = dynamic sizing based on SL distance (requires use_protective_stop)
        # 'fixed' = fixed number of BT units
        sizing_mode='fixed',
        fixed_contracts=10,

        # --- Output ---
        print_signals=False,
        export_reports=True,
    )

    def __init__(self):
        self.rsi = bt.ind.RSI(self.data.close, period=self.p.rsi_period,
                              safediv=True)
        self.sma_trend = bt.ind.SMA(self.data.close, period=self.p.sma_trend_period)
        self.sma_exit = bt.ind.SMA(self.data.close, period=self.p.sma_exit_period)
        self.atr = bt.ind.ATR(self.data, period=self.p.atr_period)

        # Order tracking
        self.order = None
        self.stop_order = None
        self.limit_order = None
        self.entry_bar = 0
        self.entry_price = 0.0
        self.stop_level = 0.0
        self.take_level = 0.0
        self._entry_size = 0
        self.last_exit_reason = None

        # Statistics
        self.trades = 0
        self.wins = 0
        self.losses = 0
        self.gross_profit = 0.0
        self.gross_loss = 0.0
        self._trade_pnls = []
        self._portfolio_values = []
        self._starting_cash = 0.0
        self._first_bar_dt = None
        self._last_bar_dt = None

        # Trade reports (used by run_backtest.py for commission summary)
        self.trade_reports = []
        self._current_trade_idx = None

        # Trade log file
        self.trade_report_file = None

    def start(self):
        self._starting_cash = self.broker.get_value()
        self._init_trade_reporting()

    def _init_trade_reporting(self):
        """Initialize trade log file in logs/."""
        if not self.p.export_reports:
            return
        logs_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
        os.makedirs(logs_dir, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'CONNORS_trades_{timestamp}.txt'
        filepath = os.path.join(logs_dir, filename)
        self.trade_report_file = open(filepath, 'w', encoding='utf-8')
        f = self.trade_report_file
        f.write("=" * 80 + "\n")
        f.write("CONNORS RSI(2) TRADE LOG\n")
        f.write("=" * 80 + "\n")
        f.write(f"RSI: period={self.p.rsi_period}, threshold=<{self.p.rsi_threshold}\n")
        f.write(f"SMA Trend: {self.p.sma_trend_period}, SMA Exit: {self.p.sma_exit_period}\n")
        f.write(f"Max Hold: {self.p.max_hold_days} days\n")
        f.write(f"ATR: period={self.p.atr_period}\n")
        if self.p.use_protective_stop:
            f.write(f"Protective Stop: ON ({self.p.atr_sl_multiplier}x ATR)\n")
        else:
            f.write("Protective Stop: OFF\n")
        if self.p.use_take_profit:
            f.write(f"Take Profit: ON ({self.p.atr_tp_multiplier}x ATR)\n")
        else:
            f.write("Take Profit: OFF\n")
        f.write(f"Sizing: {self.p.sizing_mode}")
        if self.p.sizing_mode == 'fixed':
            f.write(f" ({self.p.fixed_contracts} units)\n")
        else:
            f.write(f" (risk={self.p.risk_percent*100:.2f}%)\n")
        # Filters
        if self.p.use_time_filter:
            f.write(f"Hour Filter: {self.p.allowed_hours}\n")
        if self.p.use_day_filter:
            f.write(f"Day Filter: {self.p.allowed_days}\n")
        if self.p.min_atr_entry > 0 or self.p.max_atr_entry > 0:
            f.write(f"ATR Filter: [{self.p.min_atr_entry}, {self.p.max_atr_entry}]\n")
        f.write("=" * 80 + "\n\n")
        f.flush()

    def prenext(self):
        self._track_portfolio()

    def nextstart(self):
        self._track_portfolio()
        self.next()

    def next(self):
        self._track_portfolio()

        # Guard: pending order
        if self.order:
            return

        dt = self.data.datetime.datetime(0)

        if not self.position:
            # --- ENTRY LOGIC ---
            if (self.data.close[0] > self.sma_trend[0]
                    and self.rsi[0] < self.p.rsi_threshold):

                # --- Entry filters ---
                if not check_time_filter(dt, self.p.allowed_hours,
                                         self.p.use_time_filter):
                    return
                if not check_day_filter(dt, self.p.allowed_days,
                                        self.p.use_day_filter):
                    return
                atr_now = float(self.atr[0])
                if self.p.min_atr_entry > 0 and atr_now < self.p.min_atr_entry:
                    return
                if self.p.max_atr_entry > 0 and atr_now > self.p.max_atr_entry:
                    return

                self._execute_entry(dt)
        else:
            # --- EXIT LOGIC (only if no bracket orders active) ---
            bars_held = len(self) - self.entry_bar
            reason = None

            # Check protective stop (manual check per bar)
            if (self.p.use_protective_stop and self.stop_level > 0
                    and self.data.low[0] <= self.stop_level):
                reason = 'STOP_LOSS'
            # Check take profit (manual check per bar)
            elif (self.p.use_take_profit and self.take_level > 0
                    and self.data.high[0] >= self.take_level):
                reason = 'TAKE_PROFIT'
            elif self.data.close[0] > self.sma_exit[0]:
                reason = 'SMA_EXIT'
            elif bars_held >= self.p.max_hold_days:
                reason = 'TIMEOUT'

            if reason:
                self.last_exit_reason = reason
                self.order = self.close()
                if self.p.print_signals:
                    print(f"  [EXIT]  {dt} | Reason={reason} "
                          f"| Bars={bars_held} "
                          f"| Close={self.data.close[0]:.2f}")

    # -----------------------------------------------------------------
    # Entry execution
    # -----------------------------------------------------------------

    def _execute_entry(self, dt):
        """Execute entry with position sizing and optional SL/TP levels."""
        entry_price = self.data.close[0]
        atr_val = self.atr[0]

        if atr_val <= 0:
            return

        # Calculate SL/TP levels
        sl_buffer = self.p.sl_buffer_pips * self.p.pip_value
        self.stop_level = entry_price - (atr_val * self.p.atr_sl_multiplier) - sl_buffer
        self.take_level = entry_price + (atr_val * self.p.atr_tp_multiplier)

        # Position sizing
        size = self._calc_size(entry_price)
        if size <= 0:
            return

        self._entry_size = size
        self.order = self.buy(size=size)
        self.entry_bar = len(self)

        # Record entry in trade report
        trade_idx = len(self.trade_reports)
        self.trade_reports.append({
            'entry_time': dt,
            'entry_price': entry_price,
            'size': size,
            'rsi': self.rsi[0],
            'atr': atr_val,
            'sl': self.stop_level if self.p.use_protective_stop else None,
            'tp': self.take_level if self.p.use_take_profit else None,
            'pnl': 0.0,
            'exit_reason': None,
            'exit_time': None,
        })
        self._current_trade_idx = trade_idx

        # Write to log file
        if self.trade_report_file:
            f = self.trade_report_file
            f.write("ENTRY #%d\n" % (trade_idx + 1))
            f.write("Time: %s\n" % dt.strftime('%Y-%m-%d %H:%M:%S'))
            f.write("Entry Price: %.2f\n" % entry_price)
            f.write("Size: %d contracts\n" % size)
            f.write("RSI(2): %.1f\n" % self.rsi[0])
            f.write("ATR: %.2f\n" % atr_val)
            if self.p.use_protective_stop:
                f.write("Protective Stop: %.2f\n" % self.stop_level)
            if self.p.use_take_profit:
                f.write("Take Profit: %.2f\n" % self.take_level)
            f.write("\n")
            f.flush()

        if self.p.print_signals:
            sl_str = f" SL={self.stop_level:.2f}" if self.p.use_protective_stop else ""
            tp_str = f" TP={self.take_level:.2f}" if self.p.use_take_profit else ""
            print(f"  [ENTRY] {dt} | RSI={self.rsi[0]:.1f} "
                  f"| Close={entry_price:.2f} | Size={size}{sl_str}{tp_str}")

    # -----------------------------------------------------------------
    # Order / Trade notifications
    # -----------------------------------------------------------------

    def notify_order(self, order):
        if order.status in [order.Completed]:
            if order.isbuy():
                self.entry_price = order.executed.price
            self.order = None
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.order = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            return

        dt = self.data.datetime.datetime(0)
        pnl = trade.pnlcomm

        self.trades += 1
        if pnl > 0:
            self.wins += 1
            self.gross_profit += pnl
        else:
            self.losses += 1
            self.gross_loss += abs(pnl)

        # Determine exit reason
        reason = self.last_exit_reason or ('WIN' if pnl > 0 else 'LOSS')
        self.last_exit_reason = None

        self._trade_pnls.append({
            'date': dt,
            'year': dt.year,
            'pnl': pnl,
            'is_winner': pnl > 0,
            'exit_reason': reason,
            'bars_held': len(self) - self.entry_bar,
        })

        # Update trade report
        self._record_trade_exit(dt, pnl, reason)

    def _record_trade_exit(self, dt, pnl, reason):
        """Record exit details to log and trade_reports list."""
        if self._current_trade_idx is None:
            return
        if self._current_trade_idx < len(self.trade_reports):
            report = self.trade_reports[self._current_trade_idx]
            report['pnl'] = pnl
            report['exit_reason'] = reason
            report['exit_time'] = dt

        if self.trade_report_file:
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

    # -----------------------------------------------------------------
    # Position sizing
    # -----------------------------------------------------------------

    def _calc_size(self, entry_price):
        if self.p.sizing_mode == 'fixed':
            return self.p.fixed_contracts

        # Risk-based sizing: need a real SL distance
        if not self.p.use_protective_stop or self.stop_level <= 0:
            return self.p.fixed_contracts

        if self.p.is_etf:
            pair_type = 'ETF'
        elif self.p.is_jpy_pair:
            pair_type = 'JPY'
        else:
            pair_type = 'STANDARD'

        return calculate_position_size(
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

    # -----------------------------------------------------------------
    # Portfolio tracking
    # -----------------------------------------------------------------

    def _track_portfolio(self):
        dt = self.data.datetime.datetime(0)
        if self._first_bar_dt is None:
            self._first_bar_dt = dt
        self._last_bar_dt = dt
        self._portfolio_values.append(self.broker.get_value())

    # -----------------------------------------------------------------
    # Statistics (stop)
    # -----------------------------------------------------------------

    def stop(self):
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
            periods_per_year = 252

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
                peak_eq = equity
                max_dd = 0.0
                for p in shuffled:
                    equity += p
                    if equity > peak_eq:
                        peak_eq = equity
                    dd = (peak_eq - equity) / peak_eq * 100.0 if peak_eq > 0 else 0.0
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
        print("=== CONNORS RSI(2) STRATEGY SUMMARY ===")
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
        print("CONNORS RSI(2) CONFIGURATION")
        print("=" * 70)
        print("  RSI Period: %d" % self.p.rsi_period)
        print("  SMA Trend: %d" % self.p.sma_trend_period)
        print("  SMA Exit: %d" % self.p.sma_exit_period)
        print("  RSI Threshold: < %d" % self.p.rsi_threshold)
        print("  Max Hold: %d days" % self.p.max_hold_days)
        if self.p.use_protective_stop:
            print("  Protective Stop: %.1fx ATR" % self.p.atr_sl_multiplier)
        else:
            print("  Protective Stop: OFF")
        if self.p.use_take_profit:
            print("  Take Profit: %.1fx ATR" % self.p.atr_tp_multiplier)
        else:
            print("  Take Profit: OFF")
        print("  Sizing: %s" % self.p.sizing_mode)
        if self.p.sizing_mode == 'fixed':
            print("  Fixed Contracts: %d BT units" % self.p.fixed_contracts)
        else:
            print("  Risk: %.2f%%" % (self.p.risk_percent * 100))
        # Filters
        if self.p.use_time_filter:
            print("  Hour Filter: %s" % self.p.allowed_hours)
        else:
            print("  Hour Filter: OFF")
        if self.p.use_day_filter:
            print("  Day Filter: %s" % self.p.allowed_days)
        else:
            print("  Day Filter: OFF")
        if self.p.min_atr_entry > 0 or self.p.max_atr_entry > 0:
            lo = self.p.min_atr_entry if self.p.min_atr_entry > 0 else '-'
            hi = self.p.max_atr_entry if self.p.max_atr_entry > 0 else '-'
            print("  ATR Filter: [%s, %s]" % (lo, hi))
        else:
            print("  ATR Filter: OFF")
        print("=" * 70)

        # Close report file
        if self.trade_report_file:
            self.trade_report_file.close()
            print("\nTrade report saved.")
