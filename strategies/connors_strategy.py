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

Validated on SP500 Daily 15Y (2010-2024):
  Score 4.17, 118 trades, WR 78.8%, 80% positive years.

Reference: tools/connors_rsi2_definitive.py
"""

from collections import defaultdict
from datetime import datetime

import backtrader as bt
import numpy as np

from lib.position_sizing import calculate_position_size


class CONNORSStrategy(bt.Strategy):

    params = dict(
        # --- Connors RSI(2) published parameters (DO NOT OPTIMIZE) ---
        rsi_period=2,
        sma_trend_period=200,
        sma_exit_period=5,
        rsi_threshold=10,
        max_hold_days=20,

        # --- Asset / Risk (auto-injected by run_backtest.py) ---
        risk_percent=0.01,
        pip_value=1.0,
        lot_size=1,
        jpy_rate=1.0,
        is_jpy_pair=False,
        is_etf=True,
        margin_pct=5.0,

        # --- Sizing mode ---
        # 'risk' = ATR-based virtual stop for position sizing
        # 'fixed' = fixed number of contracts
        sizing_mode='fixed',
        fixed_contracts=1,
        atr_period=14,
        atr_sl_multiplier=2.0,

        # --- Output ---
        print_signals=False,
        export_reports=True,
    )

    def __init__(self):
        self.rsi = bt.ind.RSI(self.data.close, period=self.p.rsi_period,
                              safediv=True)
        self.sma_trend = bt.ind.SMA(self.data.close, period=self.p.sma_trend_period)
        self.sma_exit = bt.ind.SMA(self.data.close, period=self.p.sma_exit_period)

        if self.p.sizing_mode == 'risk':
            self.atr = bt.ind.ATR(self.data, period=self.p.atr_period)

        # Order tracking
        self.order = None
        self.entry_bar = 0
        self.entry_price = 0.0

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

    def start(self):
        self._starting_cash = self.broker.get_value()

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
                size = self._calc_size()
                if size > 0:
                    self.order = self.buy(size=size)
                    self.entry_bar = len(self)
                    if self.p.print_signals:
                        print(f"  [ENTRY] {dt} | RSI={self.rsi[0]:.1f} "
                              f"| Close={self.data.close[0]:.2f} "
                              f"| Size={size}")
        else:
            # --- EXIT LOGIC ---
            bars_held = len(self) - self.entry_bar
            reason = None

            if self.data.close[0] > self.sma_exit[0]:
                reason = 'SMA_EXIT'
            elif bars_held >= self.p.max_hold_days:
                reason = 'TIMEOUT'

            if reason:
                self.order = self.close()
                if self.p.print_signals:
                    print(f"  [EXIT]  {dt} | Reason={reason} "
                          f"| Bars={bars_held} "
                          f"| Close={self.data.close[0]:.2f}")

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

        self._trade_pnls.append({
            'date': dt,
            'year': dt.year,
            'pnl': pnl,
            'is_winner': pnl > 0,
        })

    # -----------------------------------------------------------------
    # Position sizing
    # -----------------------------------------------------------------

    def _calc_size(self):
        if self.p.sizing_mode == 'fixed':
            return self.p.fixed_contracts

        # Risk-based sizing using virtual ATR stop
        entry = self.data.close[0]
        virtual_stop = entry - self.p.atr_sl_multiplier * self.atr[0]

        if self.p.is_etf:
            pair_type = 'ETF'
        elif self.p.is_jpy_pair:
            pair_type = 'JPY'
        else:
            pair_type = 'STANDARD'

        return calculate_position_size(
            entry_price=entry,
            stop_loss=virtual_stop,
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
        print("  Sizing: %s" % self.p.sizing_mode)
        if self.p.sizing_mode == 'fixed':
            print("  Fixed Contracts: %d" % self.p.fixed_contracts)
        else:
            print("  Risk: %.2f%%" % (self.p.risk_percent * 100))
            print("  ATR SL Mult: %.1f" % self.p.atr_sl_multiplier)
        print("=" * 70)
