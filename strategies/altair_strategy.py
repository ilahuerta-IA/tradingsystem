"""
ALTAIR Strategy - Trend-Following Momentum on NDX Stocks

CONCEPT:
Dual-timeframe momentum strategy inspired by Robert Miner's
"High Probability Trading Strategies" (Figures 2.5-2.6).

LAYER 1 -- D1 REGIME (Selector, reviewed quincenal/monthly):
    Close_D1 > SMA(252)          -> Mom12M bullish
    ATR_D1(14) / SMA(ATR, 252) < 1.0  -> CALM volatility
    Close_D1 > Close_D1[63]      -> Mom63d positive
    All three = CALM_UP regime -> trading enabled.

LAYER 2 -- H1 SIGNAL (Trader, automated):
    DT Oscillator (DTOSC) = double-smoothed stochastic:
        raw_k  = Stoch(period=8)
        sk     = SMA(raw_k, smooth_k=5)
        sd     = SMA(sk, smooth_d=3)     <- "fast line"
        signal = SMA(sd, signal=3)       <- "slow line"
    Entry: fast crosses above slow from below oversold (25%).
    One-bar binary signal. LONG only.

LAYER 3 -- EXECUTION:
    SL = entry - sl_atr_mult * ATR(H1, 14)
    TP = entry + tp_atr_mult * ATR(H1, 14)
    Time exit after max_holding_bars.
    Risk-based sizing: size = risk_amount / sl_distance.

DATA FEEDS:
    datas[0] = Stock H1 bars (primary, traded)
    datas[1] = Stock D1 bars (resampled by runner, for regime)
"""
from __future__ import annotations
import math
import datetime as _dt
from pathlib import Path
from datetime import datetime
from collections import defaultdict

import backtrader as bt
import numpy as np

from lib.filters import check_time_filter, check_day_filter


# =============================================================================
# CUSTOM INDICATOR: DT OSCILLATOR (double-smoothed stochastic)
# =============================================================================

class DTOscillator(bt.Indicator):
    """
    DT Oscillator from Robert Miner.

    Computation:
        raw_k  = 100 * (close - lowest(low, period)) / (highest(high, period) - lowest(low, period))
        sk     = SMA(raw_k, smooth_k)
        sd     = SMA(sk, smooth_d)      -> fast line
        signal = SMA(sd, signal_period)  -> slow line

    Lines:
        fast   = sd (double-smoothed %K)
        slow   = signal (triple-smoothed)
        ob     = overbought level
        os_lvl = oversold level
    """
    lines = ('fast', 'slow', 'ob', 'os_lvl')

    params = dict(
        period=8,
        smooth_k=5,
        smooth_d=3,
        signal=3,
        overbought=75,
        oversold=25,
    )

    plotinfo = dict(
        subplot=True,
        plotname='DT Oscillator',
        plotlinelabels=True,
    )
    plotlines = dict(
        fast=dict(color='blue', linewidth=1.5, _name='DTOSC Fast'),
        slow=dict(color='red', linewidth=1.0, _name='DTOSC Slow'),
        ob=dict(color='gray', linestyle='--', linewidth=0.5),
        os_lvl=dict(color='gray', linestyle='--', linewidth=0.5),
    )

    def __init__(self):
        # Raw Stochastic %K
        highest = bt.ind.Highest(self.data.high, period=self.p.period)
        lowest = bt.ind.Lowest(self.data.low, period=self.p.period)
        raw_k = 100.0 * (self.data.close - lowest) / (highest - lowest + 1e-10)

        # Double smoothing
        sk = bt.ind.SMA(raw_k, period=self.p.smooth_k)
        sd = bt.ind.SMA(sk, period=self.p.smooth_d)

        # Fast and slow lines
        self.lines.fast = sd
        self.lines.slow = bt.ind.SMA(sd, period=self.p.signal)

    def next(self):
        self.lines.ob[0] = self.p.overbought
        self.lines.os_lvl[0] = self.p.oversold


# =============================================================================
# ENTRY/EXIT PLOT LINES
# =============================================================================

class ALTAIREntryExitLines(bt.Indicator):
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


# =============================================================================
# ALTAIR STRATEGY
# =============================================================================

class ALTAIRStrategy(bt.Strategy):
    """
    ALTAIR -- Trend-Following Momentum on NDX Stocks.

    LONG only. D1 regime filter + H1 DTOSC entry.
    Trades datas[0] (H1 stock bars), reads datas[1] (D1 for regime).
    """

    params = dict(
        # === DTOSC CORE ===
        dtosc_period=8,
        dtosc_smooth_k=5,
        dtosc_smooth_d=3,
        dtosc_signal=3,
        dtosc_ob=75,
        dtosc_os=25,

        # === D1 REGIME (periods in DAYS, scaled by bars_per_day internally) ===
        regime_enabled=True,
        regime_sma_period=252,
        regime_atr_period=252,
        regime_atr_current_period=14,
        regime_atr_threshold=1.0,
        momentum_63d_period=63,
        bars_per_day=7,             # H1 bars per trading day (US stocks)

        # === RISK / EXIT ===
        atr_period=14,
        sl_atr_mult=2.0,
        tp_atr_mult=3.0,
        max_holding_bars=120,
        max_entries_per_day=1,

        # === SESSION ===
        use_time_filter=True,
        allowed_hours=[14, 15, 16, 17, 18, 19],
        use_day_filter=True,
        allowed_days=[0, 1, 2, 3, 4],

        # === SIZING ===
        risk_percent=0.01,
        capital_alloc_pct=0.20,
        max_position_pct=0.30,

        # === ASSET CONFIG (auto-injected by run_backtest.py) ===
        pip_value=0.01,
        is_jpy_pair=False,
        is_etf=True,
        margin_pct=20.0,

        # === DEBUG & REPORTING ===
        print_signals=False,
        export_reports=True,

        # === PLOT ===
        plot_entry_exit_lines=True,
    )

    def __init__(self):
        # Single data feed: H1 stock bars
        self.data_h1 = self.datas[0]

        asset_name = self.data_h1._name
        print(f'[ALTAIR] Asset: {asset_name}')
        print(f'[ALTAIR] Single H1 feed, regime computed with '
              f'bars_per_day={self.p.bars_per_day}')

        # Scale factor for converting day-based periods to H1 bars
        bpd = self.p.bars_per_day

        # --- H1 Indicators ---
        self.atr_h1 = bt.ind.ATR(self.data_h1, period=self.p.atr_period)
        self.dtosc = DTOscillator(
            self.data_h1,
            period=self.p.dtosc_period,
            smooth_k=self.p.dtosc_smooth_k,
            smooth_d=self.p.dtosc_smooth_d,
            signal=self.p.dtosc_signal,
            overbought=self.p.dtosc_ob,
            oversold=self.p.dtosc_os,
        )

        # --- Regime indicators (on H1, with day-scaled periods) ---
        # Mom12M: SMA of 252 trading days
        self.regime_sma = bt.ind.SMA(
            self.data_h1.close,
            period=self.p.regime_sma_period * bpd)
        # ATR for current volatility (14d)
        self.regime_atr = bt.ind.ATR(
            self.data_h1,
            period=self.p.regime_atr_current_period * bpd)
        # Long-term average ATR (252d)
        self.regime_sma_atr = bt.ind.SMA(
            self.regime_atr,
            period=self.p.regime_atr_period * bpd)

        # Hide regime indicators from main plot
        self.regime_sma.plotinfo.plot = False
        self.regime_atr.plotinfo.plot = False
        self.regime_sma_atr.plotinfo.plot = False

        # Entry/exit lines on price chart
        if self.p.plot_entry_exit_lines:
            self.entry_exit_lines = ALTAIREntryExitLines(self.data_h1)
        else:
            self.entry_exit_lines = None

        # Orders
        self.order = None

        # Position state
        self.state = "SCANNING"
        self.entry_bar = None
        self.entry_datetime = None
        self.entry_price = None
        self.stop_loss_level = None
        self.take_profit_level = None
        self.last_exit_reason = None
        self.trades_today = 0
        self.last_trade_date = None

        # Regime cache (updated per H1 bar from D1 data)
        self._regime_state = 'UNKNOWN'
        self._regime_mom12m = 0.0
        self._regime_mom63d = 0.0
        self._regime_atr_ratio = 0.0

        # Statistics
        self.total_trades = 0
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
        try:
            dt_date = self.data_h1.datetime.date(offset)
            dt_time = self.data_h1.datetime.time(offset)
            return datetime.combine(dt_date, dt_time)
        except Exception:
            return self.data_h1.datetime.datetime(offset)

    # =========================================================================
    # REGIME COMPUTATION (D1)
    # =========================================================================

    def _update_regime(self):
        """Compute regime from H1 indicators (day-scaled periods).

        CALM_UP requires all three:
          1. Close > SMA(252d)           -> Mom12M bullish
          2. ATR / SMA(ATR, 252d) < 1.0  -> CALM volatility
          3. Close > Close[-63d]         -> Mom63d positive
        """
        if not self.p.regime_enabled:
            self._regime_state = 'DISABLED'
            return

        # Check if indicators are ready
        try:
            close_val = float(self.data_h1.close[0])
            sma_val = float(self.regime_sma[0])
            atr_val = float(self.regime_atr[0])
            sma_atr_val = float(self.regime_sma_atr[0])
        except (IndexError, ValueError):
            self._regime_state = 'WARMING'
            return

        if (math.isnan(sma_val) or math.isnan(atr_val) or
                math.isnan(sma_atr_val) or sma_atr_val <= 0):
            self._regime_state = 'WARMING'
            return

        # Mom12M: close > SMA(252d)
        mom12m_ok = close_val > sma_val
        self._regime_mom12m = ((close_val / sma_val) - 1.0) * 100

        # ATR ratio: current ATR / long-term average ATR
        atr_ratio = atr_val / sma_atr_val
        self._regime_atr_ratio = atr_ratio
        calm_ok = atr_ratio < self.p.regime_atr_threshold

        # Mom63d: close > close[63 days ago] (in H1 bars)
        mom63d_ok = False
        self._regime_mom63d = 0.0
        lookback = self.p.momentum_63d_period * self.p.bars_per_day
        try:
            close_ago = float(self.data_h1.close[-lookback])
            if not math.isnan(close_ago) and close_ago > 0:
                self._regime_mom63d = ((close_val / close_ago) - 1.0) * 100
                mom63d_ok = close_val > close_ago
        except (IndexError, ValueError):
            pass

        if mom12m_ok and calm_ok and mom63d_ok:
            self._regime_state = 'CALM_UP'
        elif mom12m_ok and not calm_ok:
            self._regime_state = 'VOLATILE_UP'
        elif not mom12m_ok and calm_ok:
            self._regime_state = 'CALM_DOWN'
        else:
            self._regime_state = 'VOLATILE_DOWN'

    # =========================================================================
    # DTOSC SIGNAL (H1)
    # =========================================================================

    def _check_dtosc_signal(self):
        """Check for DTOSC bullish reversal from oversold zone.

        Signal fires when:
          1. fast crosses above slow (fast[0] > slow[0] and fast[-1] <= slow[-1])
          2. Cross comes from oversold zone (fast[-1] < dtosc_os or slow[-1] < dtosc_os)
        """
        try:
            fast_now = float(self.dtosc.fast[0])
            fast_prev = float(self.dtosc.fast[-1])
            slow_now = float(self.dtosc.slow[0])
            slow_prev = float(self.dtosc.slow[-1])
        except (IndexError, ValueError):
            return False

        if math.isnan(fast_now) or math.isnan(slow_now):
            return False
        if math.isnan(fast_prev) or math.isnan(slow_prev):
            return False

        # Bullish cross: fast crosses above slow
        cross_up = (fast_now > slow_now) and (fast_prev <= slow_prev)
        if not cross_up:
            return False

        # Must come from oversold zone
        from_oversold = (fast_prev < self.p.dtosc_os or
                         slow_prev < self.p.dtosc_os)
        return from_oversold

    # =========================================================================
    # TRADE REPORTING
    # =========================================================================

    def _init_trade_reporting(self):
        if not self.p.export_reports:
            return
        try:
            report_dir = Path("logs")
            report_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            asset = self.data_h1._name
            report_path = report_dir / f"ALTAIR_{asset}_trades_{timestamp}.txt"
            self.trade_report_file = open(report_path, 'w', encoding='utf-8')

            f = self.trade_report_file
            f.write("=== ALTAIR STRATEGY TRADE REPORT ===\n")
            f.write(f"Generated: {datetime.now()}\n")
            f.write(f"Asset: {asset}\n\n")
            f.write("=== CONFIGURATION ===\n")
            f.write(
                f"DTOSC: period={self.p.dtosc_period}, "
                f"smooth_k={self.p.dtosc_smooth_k}, "
                f"smooth_d={self.p.dtosc_smooth_d}, "
                f"signal={self.p.dtosc_signal}\n")
            f.write(
                f"Oversold/Overbought: {self.p.dtosc_os} / {self.p.dtosc_ob}\n")
            if self.p.regime_enabled:
                f.write(
                    f"Regime: Mom12M({self.p.regime_sma_period}) + "
                    f"ATR_ratio(<{self.p.regime_atr_threshold}) + "
                    f"Mom63d({self.p.momentum_63d_period})\n")
            else:
                f.write("Regime: DISABLED\n")
            if self.p.use_time_filter:
                hours = list(self.p.allowed_hours)
                f.write(f"Session: {min(hours):02d}:00-{max(hours):02d}:00 UTC\n")
            if self.p.use_day_filter:
                day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
                days = [day_names[d] for d in self.p.allowed_days if d < 7]
                f.write(f"Allowed Days: {days}\n")
            f.write(
                f"SL: {self.p.sl_atr_mult}x ATR | "
                f"TP: {self.p.tp_atr_mult}x ATR\n")
            f.write(
                f"Max Holding: {self.p.max_holding_bars} bars | "
                f"Max Entries/Day: {self.p.max_entries_per_day}\n")
            f.write(f"Risk: {self.p.risk_percent * 100:.1f}%\n")
            f.write("\n")
            print(f"[ALTAIR] Trade report: {report_path}")
        except Exception as e:
            print(f"[ALTAIR] Trade reporting init failed: {e}")

    def _record_trade_entry(self, dt, entry_price, size, atr_h1,
                            dtosc_fast, dtosc_slow):
        if not self.trade_report_file:
            return
        try:
            entry = {
                'entry_time': dt,
                'entry_price': entry_price,
                'size': size,
                'direction': 'LONG',
                'atr_h1': atr_h1,
                'dtosc_fast': dtosc_fast,
                'dtosc_slow': dtosc_slow,
                'regime': self._regime_state,
                'regime_mom12m': self._regime_mom12m,
                'regime_mom63d': self._regime_mom63d,
                'regime_atr_ratio': self._regime_atr_ratio,
                'stop_loss': self.stop_loss_level,
                'take_profit': self.take_profit_level,
            }
            self.trade_reports.append(entry)

            f = self.trade_report_file
            n = len(self.trade_reports)
            f.write(f"ENTRY #{n}\n")
            f.write(f"Time: {dt.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Direction: LONG\n")
            f.write(f"Asset: {self.data_h1._name}\n")
            f.write(f"Entry Price: {entry_price:.2f}\n")
            f.write(f"Size: {size} shares\n")
            f.write(f"ATR(H1): {atr_h1:.2f}\n")
            f.write(f"DTOSC Fast: {dtosc_fast:.1f}\n")
            f.write(f"DTOSC Slow: {dtosc_slow:.1f}\n")
            f.write(
                f"Regime: {self._regime_state} "
                f"(Mom12M={self._regime_mom12m:+.1f}%, "
                f"Mom63d={self._regime_mom63d:+.1f}%, "
                f"ATR_ratio={self._regime_atr_ratio:.2f})\n")
            f.write(f"Stop Loss: {self.stop_loss_level:.2f}\n")
            f.write(f"Take Profit: {self.take_profit_level:.2f}\n")
            f.write("-" * 50 + "\n\n")
            f.flush()
        except Exception:
            pass

    def _record_trade_exit(self, dt, pnl, reason, bars_held):
        if not self.trade_report_file or not self.trade_reports:
            return
        try:
            self.trade_reports[-1]['pnl'] = pnl
            self.trade_reports[-1]['exit_reason'] = reason
            self.trade_reports[-1]['exit_time'] = dt
            self.trade_reports[-1]['bars_held'] = bars_held

            f = self.trade_report_file
            n = len(self.trade_reports)
            f.write(f"EXIT #{n}\n")
            f.write(f"Time: {dt.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Exit Reason: {reason}\n")
            f.write(f"P&L: ${pnl:.2f}\n")
            f.write(f"Bars Held: {bars_held}\n")
            f.write("=" * 80 + "\n\n")
            f.flush()
        except Exception:
            pass

    # =========================================================================
    # PLOT LINES
    # =========================================================================

    def _update_plot_lines(self, entry=None, sl=None, tp=None):
        if not self.entry_exit_lines:
            return
        nan = float('nan')
        self.entry_exit_lines.lines.entry[0] = entry if entry else nan
        self.entry_exit_lines.lines.stop_loss[0] = sl if sl else nan
        self.entry_exit_lines.lines.take_profit[0] = tp if tp else nan

    # =========================================================================
    # ENTRY EXECUTION
    # =========================================================================

    def _execute_entry(self, dt):
        entry_price = float(self.data_h1.close[0])
        atr_val = float(self.atr_h1[0])

        if atr_val <= 0 or math.isnan(atr_val):
            return

        # SL / TP levels
        sl_dist = atr_val * self.p.sl_atr_mult
        tp_dist = atr_val * self.p.tp_atr_mult
        self.stop_loss_level = entry_price - sl_dist
        self.take_profit_level = entry_price + tp_dist

        # Risk-based sizing: size = risk_amount / sl_distance
        equity = self.broker.get_value()
        risk_amount = equity * self.p.risk_percent
        if sl_dist <= 0:
            return
        size = int(risk_amount / sl_dist)
        if size < 1:
            return

        # Cap by capital allocation (margin)
        margin_per_share = entry_price * (self.p.margin_pct / 100.0)
        if margin_per_share > 0:
            max_by_alloc = int(
                (equity * self.p.capital_alloc_pct) / margin_per_share)
            size = min(size, max(1, max_by_alloc))

        # Absolute max position cap
        if margin_per_share > 0:
            abs_max = int(
                (equity * self.p.max_position_pct) / margin_per_share)
            size = min(size, max(1, abs_max))

        # Execute
        self.order = self.buy(data=self.data_h1, size=size)

        # State
        self.state = "IN_POSITION"
        self.entry_bar = len(self.data_h1)
        self.entry_datetime = dt
        self.entry_price = entry_price

        # Plot
        self._update_plot_lines(entry_price, self.stop_loss_level,
                                self.take_profit_level)

        # Record
        dtosc_fast = float(self.dtosc.fast[0])
        dtosc_slow = float(self.dtosc.slow[0])
        self._record_trade_entry(
            dt, entry_price, size, atr_val, dtosc_fast, dtosc_slow)

        if self.p.print_signals:
            print(
                f"[ALTAIR] {dt} ENTRY LONG {size}x "
                f"@ {entry_price:.2f} | "
                f"SL={self.stop_loss_level:.2f} "
                f"TP={self.take_profit_level:.2f} | "
                f"DTOSC={dtosc_fast:.1f}/{dtosc_slow:.1f} | "
                f"Regime={self._regime_state}")

    # =========================================================================
    # EXIT LOGIC
    # =========================================================================

    def _check_stop_loss(self):
        if self.stop_loss_level is None:
            return False
        return float(self.data_h1.low[0]) <= self.stop_loss_level

    def _check_take_profit(self):
        if self.take_profit_level is None or self.p.tp_atr_mult <= 0:
            return False
        return float(self.data_h1.high[0]) >= self.take_profit_level

    def _execute_exit(self, dt, reason):
        self.last_exit_reason = reason
        self.close(data=self.data_h1)

        # Clear plot
        self._update_plot_lines()

        # Reset
        self.state = "SCANNING"
        self.entry_bar = None
        self.entry_datetime = None
        self.entry_price = None
        self.stop_loss_level = None
        self.take_profit_level = None

        if self.p.print_signals:
            print(f"[ALTAIR] {dt} EXIT ({reason}) "
                  f"@ {self.data_h1.close[0]:.2f}")

    # =========================================================================
    # ORDER / TRADE NOTIFICATIONS
    # =========================================================================

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status in [order.Canceled, order.Margin, order.Rejected]:
            if self.p.print_signals:
                status_names = {
                    order.Canceled: 'Canceled',
                    order.Margin: 'Margin',
                    order.Rejected: 'Rejected',
                }
                print(f'[ALTAIR] Order {status_names.get(order.status, "?")}')
            if self.state != "IN_POSITION":
                self.state = "SCANNING"

        if order.data == self.data_h1:
            self.order = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            return

        dt = self._get_datetime()
        pnl = trade.pnl
        bars_held = 0
        if self.entry_bar is not None:
            bars_held = len(self.data_h1) - self.entry_bar

        self.total_trades += 1
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
        self._record_trade_exit(dt, pnl, reason, bars_held)

        if self.p.print_signals:
            print(f"[ALTAIR] {dt} TRADE CLOSED ({reason}) | "
                  f"P&L: ${pnl:.2f} | Bars: {bars_held}")

        self.last_exit_reason = None

    # =========================================================================
    # MAIN LOOP
    # =========================================================================

    def next(self):
        # Track portfolio
        self._portfolio_values.append(self.broker.get_value())

        dt = self._get_datetime()
        if self._first_bar_dt is None:
            self._first_bar_dt = dt
        self._last_bar_dt = dt

        # Update D1 regime (reads latest D1 bar)
        self._update_regime()

        # Skip if order pending
        if self.order:
            return

        # === STATE MACHINE ===

        if self.state == "IN_POSITION":
            # Check stop loss
            if self._check_stop_loss():
                self._execute_exit(dt, 'PROT_STOP')
                return

            # Check take profit
            if self._check_take_profit():
                self._execute_exit(dt, 'TP_EXIT')
                return

            # Check max holding
            bars_held = len(self.data_h1) - self.entry_bar
            if bars_held >= self.p.max_holding_bars:
                self._execute_exit(dt, 'TIME_EXIT')
                return

            # Update plot while in position
            self._update_plot_lines(
                self.entry_price, self.stop_loss_level,
                self.take_profit_level)

        elif self.state == "SCANNING":
            # Time filter
            if self.p.use_time_filter:
                if not check_time_filter(
                        dt, list(self.p.allowed_hours), True):
                    return

            # Day filter
            if self.p.use_day_filter:
                if not check_day_filter(
                        dt, list(self.p.allowed_days), True):
                    return

            # Max entries per day
            if self.p.max_entries_per_day > 0:
                current_date = dt.date()
                if self.last_trade_date != current_date:
                    self.last_trade_date = current_date
                    self.trades_today = 0
                if self.trades_today >= self.p.max_entries_per_day:
                    return

            # D1 Regime filter
            if self.p.regime_enabled:
                if self._regime_state != 'CALM_UP':
                    return

            # DTOSC signal
            if not self._check_dtosc_signal():
                return

            # All conditions met -> ENTER
            self.trades_today += 1
            self._execute_entry(dt)

    # =========================================================================
    # STOP -- FINAL REPORT
    # =========================================================================

    def stop(self):
        total_trades = self.total_trades
        win_rate = (
            (self.wins / total_trades * 100) if total_trades > 0 else 0)
        profit_factor = (
            (self.gross_profit / self.gross_loss)
            if self.gross_loss > 0 else float('inf'))
        total_pnl = self.gross_profit - self.gross_loss
        final_value = self.broker.get_value()

        # Periods per year (data-driven)
        if self._first_bar_dt and self._last_bar_dt:
            data_days = (self._last_bar_dt - self._first_bar_dt).days
            data_years = max(data_days / 365.25, 0.1)
            periods_per_year = len(self._portfolio_values) / data_years
        else:
            periods_per_year = 252 * 7  # H1 bars fallback (~7/day)

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
        print('=== ALTAIR STRATEGY SUMMARY ===')
        print('=' * 70)

        print(f'Asset: {self.data_h1._name}')
        print(f'DTOSC: period={self.p.dtosc_period}, '
              f'smooth_k={self.p.dtosc_smooth_k}, '
              f'smooth_d={self.p.dtosc_smooth_d}, '
              f'signal={self.p.dtosc_signal}')
        print(f'Oversold/Overbought: {self.p.dtosc_os}/{self.p.dtosc_ob}')
        print(f'Regime: {"ON" if self.p.regime_enabled else "OFF"}')
        print(f'SL: {self.p.sl_atr_mult}x ATR | '
              f'TP: {self.p.tp_atr_mult}x ATR | '
              f'Max Hold: {self.p.max_holding_bars} bars')

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

        # Commission summary
        from lib.commission import ETFCommission
        actual_total_comm = ETFCommission.total_commission
        actual_total_contracts = ETFCommission.total_contracts
        avg_commission = (
            actual_total_comm / total_trades if total_trades > 0 else 0)

        print(f"\n{'=' * 70}")
        print('COMMISSION SUMMARY (Stock/ETF)')
        print(f"{'=' * 70}")
        print(f'Total Shares Traded:          {actual_total_contracts:,.0f}')
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
                f = self.trade_report_file
                f.write("\n=== SUMMARY ===\n")
                f.write(f"Total Trades: {total_trades}\n")
                f.write(f"Wins: {self.wins} | Losses: {self.losses}\n")
                f.write(f"Win Rate: {win_rate:.1f}%\n")
                f.write(f"Profit Factor: {profit_factor:.2f}\n")
                f.write(f"Net P&L: ${total_pnl:,.2f}\n")
                f.write(f"Sharpe: {sharpe_ratio:.2f}\n")
                f.write(f"Max DD: {max_drawdown_pct:.2f}%\n")
                f.write(f"CAGR: {cagr:.2f}%\n")
                self.trade_report_file.close()
            except Exception:
                pass
