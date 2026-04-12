"""
LYRA Strategy - Short-Selling on Index CFDs During VOLATILE_UP Regime

CONCEPT:
Bear-market complement to ALTAIR.  Same dual-timeframe framework
(D1 regime + H1 DTOSC timing) but **inverted for SHORT entries**.

LAYER 1 -- D1 REGIME (from ALTAIR):
    CALM_UP  / VOLATILE_UP / CALM_DOWN / VOLATILE_DOWN
    Lyra trades ONLY during VOLATILE_UP regime.
    (Prestudy showed it's the only regime with positive short edge.)

LAYER 2 -- H1 SIGNAL (inverted DTOSC):
    Entry: fast crosses BELOW slow from ABOVE overbought (75%).
    One-bar binary signal.  SHORT only.

LAYER 3 -- EXECUTION:
    Entry: Trailing One-Bar LOW (Tr-1BL) sell stop confirmation.
           After DTOSC cross-down, sell stop at low-tick each bar.
           Cancel if DTOSC loses alignment or timeout.
    SL = swing_high + tick (structural stop at rally high).
    TP = entry - tp_atr_mult * ATR(H1, 14).
    Max SL filter: skip if SL > max_sl_atr_mult * ATR.
    Time exit after max_holding_bars.
    Regime exit: close if regime returns to CALM_UP.
    Risk-based sizing: size = risk_amount / sl_distance.

STATE MACHINE:
    SCANNING -> [DTOSC cross from OB + VOLATILE_UP] -> TRIGGERED
    TRIGGERED -> [low < sell_stop] -> IN_POSITION
    TRIGGERED -> [DTOSC alignment lost / timeout] -> SCANNING
    IN_POSITION -> [SL/TP/TIME/REGIME] -> SCANNING

DATA FEEDS:
    datas[0] = Index H1 bars (primary, traded)
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
# CUSTOM INDICATOR: DT OSCILLATOR (reused from ALTAIR)
# =============================================================================

class DTOscillator(bt.Indicator):
    """DT Oscillator from Robert Miner (double-smoothed stochastic)."""
    lines = ('fast', 'slow', 'ob', 'os_lvl')

    params = dict(
        period=8,
        smooth_k=5,
        smooth_d=3,
        signal=3,
        overbought=75,
        oversold=25,
    )

    plotinfo = dict(subplot=True, plotname='DT Oscillator')
    plotlines = dict(
        fast=dict(color='blue', linewidth=1.5, _name='DTOSC Fast'),
        slow=dict(color='red', linewidth=1.0, _name='DTOSC Slow'),
        ob=dict(color='gray', linestyle='--', linewidth=0.5),
        os_lvl=dict(color='gray', linestyle='--', linewidth=0.5),
    )

    def __init__(self):
        highest = bt.ind.Highest(self.data.high, period=self.p.period)
        lowest = bt.ind.Lowest(self.data.low, period=self.p.period)
        raw_k = 100.0 * (self.data.close - lowest) / (highest - lowest + 1e-10)
        sk = bt.ind.SMA(raw_k, period=self.p.smooth_k)
        sd = bt.ind.SMA(sk, period=self.p.smooth_d)
        self.lines.fast = sd
        self.lines.slow = bt.ind.SMA(sd, period=self.p.signal)

    def next(self):
        self.lines.ob[0] = self.p.overbought
        self.lines.os_lvl[0] = self.p.oversold


# =============================================================================
# LYRA STRATEGY
# =============================================================================

class LYRAStrategy(bt.Strategy):
    """
    LYRA -- Short-Selling on Index CFDs during VOLATILE_UP regime.

    SHORT only.  Inverted ALTAIR logic:
      - Regime: VOLATILE_UP (not CALM_UP)
      - DTOSC: bearish cross from overbought
      - Entry: sell (Tr-1BL confirmation)
      - SL: above swing high
      - TP: below entry
      - Regime exit: close short if CALM_UP returns
    """

    params = dict(
        # === DTOSC CORE ===
        dtosc_period=8,
        dtosc_smooth_k=5,
        dtosc_smooth_d=3,
        dtosc_signal=3,
        dtosc_ob=75,
        dtosc_os=25,

        # === D1 REGIME ===
        regime_enabled=True,
        regime_sma_period=252,
        regime_atr_period=252,
        regime_atr_current_period=14,
        regime_atr_threshold=1.0,
        momentum_63d_period=63,
        bars_per_day=7,

        # === ALLOWED REGIMES FOR ENTRY ===
        # 1=VOLATILE_UP, 2=CALM_DOWN, 3=VOLATILE_DOWN
        allowed_regimes=(1,),       # Default: VOLATILE_UP only

        # === RISK / EXIT ===
        atr_period=14,
        sl_atr_mult=2.0,           # Fallback SL if swing high not available
        tp_atr_mult=3.0,           # TP = entry - X * ATR
        max_sl_atr_mult=3.0,       # Max SL width in ATR mult

        # === ENTRY CONFIRMATION ===
        use_tr1bl=True,             # Trailing One-Bar Low (short version of Tr-1BH)
        tr1bl_timeout=5,            # Max bars in TRIGGERED state
        tr1bl_tick=0.01,            # Tick offset below bar low
        use_swing_high_sl=True,     # SL at swing high (structural)

        max_holding_bars=35,        # ~5 trading days at bpd=7
        max_entries_per_day=1,

        # === ATR ENTRY FILTER ===
        min_atr_entry=0.0,          # 0 = disabled
        max_atr_entry=0.0,          # 0 = disabled

        # === REGIME EXIT ===
        exit_on_calm_up=True,       # Close short if regime returns to CALM_UP

        # === SESSION ===
        use_time_filter=True,
        allowed_hours=[14, 15, 16, 17, 18, 19],
        use_day_filter=True,
        allowed_days=[0, 1, 2, 3, 4],

        # === SIZING ===
        risk_percent=0.01,
        capital_alloc_pct=0.20,
        max_position_pct=0.30,

        # === ASSET CONFIG ===
        pip_value=0.01,
        is_jpy_pair=False,
        is_etf=True,
        margin_pct=5.0,

        # === DEBUG ===
        print_signals=False,
        export_reports=True,
        plot_entry_exit_lines=False,
    )

    # Regime code map (same as ALTAIR)
    REGIME_CODES = {
        'CALM_UP': 0, 'VOLATILE_UP': 1,
        'CALM_DOWN': 2, 'VOLATILE_DOWN': 3,
    }

    def __init__(self):
        self.data_h1 = self.datas[0]
        asset_name = self.data_h1._name
        bpd = self.p.bars_per_day
        print(f'[LYRA] Asset: {asset_name} (SHORT strategy)')
        print(f'[LYRA] bpd={bpd}, allowed_regimes={self.p.allowed_regimes}')

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

        # --- Regime indicators (H1-scaled) ---
        self.regime_sma = bt.ind.SMA(
            self.data_h1.close, period=self.p.regime_sma_period * bpd)
        self.regime_atr = bt.ind.ATR(
            self.data_h1, period=self.p.regime_atr_current_period * bpd)
        self.regime_sma_atr = bt.ind.SMA(
            self.regime_atr, period=self.p.regime_atr_period * bpd)

        # Hide from plot
        self.regime_sma.plotinfo.plot = False
        self.regime_atr.plotinfo.plot = False
        self.regime_sma_atr.plotinfo.plot = False

        # Orders
        self.order = None

        # State machine
        self.state = "SCANNING"
        self.entry_bar = None
        self.entry_datetime = None
        self.entry_price = None
        self.stop_loss_level = None
        self.take_profit_level = None
        self.last_exit_reason = None
        self.trades_today = 0
        self.last_trade_date = None

        # Tr-1BL state (inverted Tr-1BH)
        self._triggered_bar_count = 0
        self._triggered_sell_stop = 0.0
        self._frozen_swing_high = None
        self._triggered_cancels = 0

        # Swing HIGH tracking (inverted from swing low)
        self._swing_high = 0.0
        self._tracking_overbought = False

        # Regime cache
        self._regime_state = 'UNKNOWN'
        self._regime_code = -1
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
    # REGIME COMPUTATION (identical to ALTAIR)
    # =========================================================================

    def _update_regime(self):
        if not self.p.regime_enabled:
            self._regime_state = 'DISABLED'
            self._regime_code = -1
            return

        try:
            close_val = float(self.data_h1.close[0])
            sma_val = float(self.regime_sma[0])
            atr_val = float(self.regime_atr[0])
            sma_atr_val = float(self.regime_sma_atr[0])
        except (IndexError, ValueError):
            self._regime_state = 'WARMING'
            self._regime_code = -1
            return

        if (math.isnan(sma_val) or math.isnan(atr_val) or
                math.isnan(sma_atr_val) or sma_atr_val <= 0):
            self._regime_state = 'WARMING'
            self._regime_code = -1
            return

        mom12m_ok = close_val > sma_val
        self._regime_mom12m = ((close_val / sma_val) - 1.0) * 100

        atr_ratio = atr_val / sma_atr_val
        self._regime_atr_ratio = atr_ratio
        calm_ok = atr_ratio < self.p.regime_atr_threshold

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
            self._regime_code = 0
        elif mom12m_ok and not calm_ok:
            self._regime_state = 'VOLATILE_UP'
            self._regime_code = 1
        elif not mom12m_ok and calm_ok:
            self._regime_state = 'CALM_DOWN'
            self._regime_code = 2
        else:
            self._regime_state = 'VOLATILE_DOWN'
            self._regime_code = 3

    # =========================================================================
    # DTOSC BEARISH SIGNAL (inverted from ALTAIR's bullish)
    # =========================================================================

    def _check_dtosc_short_signal(self):
        """Check for DTOSC bearish reversal from overbought zone.

        Signal fires when:
          1. fast crosses BELOW slow (fast[0] < slow[0] and fast[-1] >= slow[-1])
          2. Cross comes from overbought zone (fast[-1] > dtosc_ob or slow[-1] > dtosc_ob)
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

        # Bearish cross: fast crosses below slow
        cross_down = (fast_now < slow_now) and (fast_prev >= slow_prev)
        if not cross_down:
            return False

        # Must come from overbought zone
        from_overbought = (fast_prev > self.p.dtosc_ob or
                           slow_prev > self.p.dtosc_ob)
        return from_overbought

    # =========================================================================
    # SWING HIGH TRACKING (inverted from ALTAIR swing low)
    # =========================================================================

    def _track_swing_high(self):
        """Track highest high while DTOSC is in overbought zone."""
        try:
            fast_val = float(self.dtosc.fast[0])
        except (IndexError, ValueError):
            return
        if math.isnan(fast_val):
            return

        high_val = float(self.data_h1.high[0])

        if fast_val > self.p.dtosc_ob:
            if not self._tracking_overbought:
                self._tracking_overbought = True
                self._swing_high = high_val
            else:
                self._swing_high = max(self._swing_high, high_val)
        else:
            self._tracking_overbought = False

    # =========================================================================
    # TRIGGERED STATE (Trailing One-Bar LOW)
    # =========================================================================

    def _handle_triggered(self, dt):
        """Handle TRIGGERED state: Trailing One-Bar LOW (sell stop)."""
        self._triggered_bar_count += 1

        try:
            fast_now = float(self.dtosc.fast[0])
            slow_now = float(self.dtosc.slow[0])
        except (IndexError, ValueError):
            self.state = "SCANNING"
            self._triggered_cancels += 1
            return

        # DTOSC must stay bearish (fast below slow)
        if fast_now > slow_now:
            if self.p.print_signals:
                print(f'[LYRA] {dt} TRIGGERED->SCANNING: DTOSC lost alignment')
            self.state = "SCANNING"
            self._triggered_cancels += 1
            return

        # Timeout
        if self._triggered_bar_count >= self.p.tr1bl_timeout:
            if self.p.print_signals:
                print(f'[LYRA] {dt} TRIGGERED->SCANNING: Timeout')
            self.state = "SCANNING"
            self._triggered_cancels += 1
            return

        # Check if price broke sell stop (low went below)
        bar_low = float(self.data_h1.low[0])
        if bar_low <= self._triggered_sell_stop:
            entry_price = float(self.data_h1.close[0])
            atr_val = float(self.atr_h1[0])

            # Max SL check
            if (self.p.use_swing_high_sl
                    and self._frozen_swing_high is not None
                    and self.p.max_sl_atr_mult > 0
                    and not math.isnan(atr_val) and atr_val > 0):
                sl_level = self._frozen_swing_high + self.p.tr1bl_tick
                sl_dist = sl_level - entry_price
                if sl_dist > self.p.max_sl_atr_mult * atr_val:
                    if self.p.print_signals:
                        print(f'[LYRA] {dt} TRIGGERED->SCANNING: '
                              f'SL too wide ({sl_dist:.2f} > '
                              f'{self.p.max_sl_atr_mult}x ATR)')
                    self.state = "SCANNING"
                    self._triggered_cancels += 1
                    return

            self.trades_today += 1
            self._execute_entry(dt)
            self._triggered_bar_count = 0
        else:
            # Trail sell stop to current bar's low
            self._triggered_sell_stop = bar_low - self.p.tr1bl_tick

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
            report_path = report_dir / f"LYRA_{asset}_trades_{timestamp}.txt"
            self.trade_report_file = open(report_path, 'w', encoding='utf-8')
            f = self.trade_report_file
            f.write("=== LYRA STRATEGY TRADE REPORT ===\n")
            f.write(f"Generated: {datetime.now()}\n")
            f.write(f"Asset: {asset}\n")
            f.write(f"Direction: SHORT ONLY\n")
            f.write(f"Allowed Regimes: {self.p.allowed_regimes}\n")
            f.write(f"DTOSC OB: {self.p.dtosc_ob}\n")
            f.write(f"SL: {self.p.sl_atr_mult}x ATR (max {self.p.max_sl_atr_mult}x)\n")
            f.write(f"TP: {self.p.tp_atr_mult}x ATR\n")
            f.write(f"Max Holding: {self.p.max_holding_bars} bars\n")
            f.write(f"Tr-1BL: {'ON' if self.p.use_tr1bl else 'OFF'}"
                    f" (timeout={self.p.tr1bl_timeout})\n")
            f.write(f"Use Swing High SL: {self.p.use_swing_high_sl}\n")
            f.write(f"Risk: {self.p.risk_percent * 100:.1f}%\n")
            f.write(f"Time Filter: {list(self.p.allowed_hours)}\n")
            f.write(f"Day Filter: {list(self.p.allowed_days)}\n")
            f.write(f"Min ATR Entry: {self.p.min_atr_entry}\n")
            f.write(f"Max ATR Entry: {self.p.max_atr_entry}\n")
            f.write("\n")
            print(f"[LYRA] Trade report: {report_path}")
        except Exception as e:
            print(f"[LYRA] Trade reporting init failed: {e}")

    def _record_trade_entry(self, dt, entry_price, size, atr_h1,
                            dtosc_fast, dtosc_slow):
        try:
            entry = {
                'entry_time': dt,
                'entry_price': entry_price,
                'size': size,
                'direction': 'SHORT',
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

            if not self.trade_report_file:
                return
            f = self.trade_report_file
            n = len(self.trade_reports)
            f.write(f"ENTRY #{n}\n")
            f.write(f"Time: {dt.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Direction: SHORT\n")
            f.write(f"Entry Price: {entry_price:.2f}\n")
            f.write(f"Size: {size}\n")
            f.write(f"ATR(H1): {atr_h1:.2f}\n")
            f.write(f"DTOSC: {dtosc_fast:.1f}/{dtosc_slow:.1f}\n")
            f.write(f"Regime: {self._regime_state}\n")
            f.write(f"SL: {self.stop_loss_level:.2f}\n")
            f.write(f"TP: {self.take_profit_level:.2f}\n")
            f.write("-" * 50 + "\n\n")
            f.flush()
        except Exception:
            pass

    def _record_trade_exit(self, dt, pnl, reason, bars_held):
        if not self.trade_reports:
            return
        try:
            self.trade_reports[-1]['pnl'] = pnl
            self.trade_reports[-1]['exit_reason'] = reason
            self.trade_reports[-1]['exit_time'] = dt
            self.trade_reports[-1]['bars_held'] = bars_held

            if not self.trade_report_file:
                return
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
    # ENTRY EXECUTION (SHORT)
    # =========================================================================

    def _execute_entry(self, dt):
        entry_price = float(self.data_h1.close[0])
        atr_val = float(self.atr_h1[0])

        if atr_val <= 0 or math.isnan(atr_val):
            self.state = "SCANNING"
            return

        # SL: above swing high (inverted from ALTAIR)
        if (self.p.use_swing_high_sl
                and self._frozen_swing_high is not None):
            self.stop_loss_level = self._frozen_swing_high + self.p.tr1bl_tick
            sl_dist = self.stop_loss_level - entry_price
            if sl_dist <= 0:
                if self.p.print_signals:
                    print(f'[LYRA] {dt} SKIP: swing_high below entry')
                self.state = "SCANNING"
                return
        else:
            sl_dist = atr_val * self.p.sl_atr_mult
            self.stop_loss_level = entry_price + sl_dist

        # TP: below entry (inverted)
        if self.p.tp_atr_mult > 0:
            tp_dist = atr_val * self.p.tp_atr_mult
            self.take_profit_level = entry_price - tp_dist
        else:
            self.take_profit_level = None

        # Risk-based sizing
        equity = self.broker.get_value()
        risk_amount = equity * self.p.risk_percent
        if sl_dist <= 0:
            return
        size = int(risk_amount / sl_dist)
        if size < 1:
            return

        # Cap by capital allocation
        margin_per_unit = entry_price * (self.p.margin_pct / 100.0)
        if margin_per_unit > 0:
            max_by_alloc = int(
                (equity * self.p.capital_alloc_pct) / margin_per_unit)
            size = min(size, max(1, max_by_alloc))
            abs_max = int(
                (equity * self.p.max_position_pct) / margin_per_unit)
            size = min(size, max(1, abs_max))

        # SELL (short)
        self.order = self.sell(data=self.data_h1, size=size)

        self.state = "IN_POSITION"
        self.entry_bar = len(self.data_h1)
        self.entry_datetime = dt
        self.entry_price = entry_price

        dtosc_fast = float(self.dtosc.fast[0])
        dtosc_slow = float(self.dtosc.slow[0])
        self._record_trade_entry(
            dt, entry_price, size, atr_val, dtosc_fast, dtosc_slow)

        if self.p.print_signals:
            print(f"[LYRA] {dt} ENTRY SHORT {size}x "
                  f"@ {entry_price:.2f} | "
                  f"SL={self.stop_loss_level:.2f} "
                  f"TP={self.take_profit_level} | "
                  f"Regime={self._regime_state}")

    # =========================================================================
    # EXIT LOGIC (SHORT)
    # =========================================================================

    def _check_stop_loss(self):
        """SL for short: price goes UP above stop."""
        if self.stop_loss_level is None:
            return False
        return float(self.data_h1.high[0]) >= self.stop_loss_level

    def _check_take_profit(self):
        """TP for short: price goes DOWN below target."""
        if self.take_profit_level is None or self.p.tp_atr_mult <= 0:
            return False
        return float(self.data_h1.low[0]) <= self.take_profit_level

    def _check_regime_exit(self):
        """Exit if regime returns to CALM_UP."""
        if not self.p.exit_on_calm_up:
            return False
        return self._regime_code == 0  # CALM_UP

    def _execute_exit(self, dt, reason):
        self.last_exit_reason = reason
        self.close(data=self.data_h1)
        self.state = "SCANNING"
        self.entry_bar = None
        self.entry_datetime = None
        self.entry_price = None
        self.stop_loss_level = None
        self.take_profit_level = None
        if self.p.print_signals:
            print(f"[LYRA] {dt} EXIT ({reason}) "
                  f"@ {self.data_h1.close[0]:.2f}")

    # =========================================================================
    # ORDER / TRADE NOTIFICATIONS
    # =========================================================================

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status in [order.Canceled, order.Margin, order.Rejected]:
            if self.p.print_signals:
                print(f'[LYRA] Order {order.status}')
            if self.state not in ("IN_POSITION", "TRIGGERED"):
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
            print(f"[LYRA] {dt} TRADE CLOSED ({reason}) | "
                  f"P&L: ${pnl:.2f} | Bars: {bars_held}")
        self.last_exit_reason = None

    # =========================================================================
    # MAIN LOOP
    # =========================================================================

    def next(self):
        self._portfolio_values.append(self.broker.get_value())

        dt = self._get_datetime()
        if self._first_bar_dt is None:
            self._first_bar_dt = dt
        self._last_bar_dt = dt

        # Regime
        self._update_regime()

        # Track swing high during overbought phase
        if self.p.use_swing_high_sl:
            self._track_swing_high()

        if self.order:
            return

        # === STATE MACHINE ===

        if self.state == "IN_POSITION":
            # 1. Regime exit (highest priority for shorts)
            if self._check_regime_exit():
                self._execute_exit(dt, 'REGIME_EXIT')
                return

            # 2. Stop loss
            if self._check_stop_loss():
                self._execute_exit(dt, 'PROT_STOP')
                return

            # 3. Take profit
            if self._check_take_profit():
                self._execute_exit(dt, 'TP_EXIT')
                return

            # 4. Max holding
            bars_held = len(self.data_h1) - self.entry_bar
            if bars_held >= self.p.max_holding_bars:
                self._execute_exit(dt, 'TIME_EXIT')
                return

        elif self.state == "TRIGGERED":
            self._handle_triggered(dt)

        elif self.state == "SCANNING":
            # Time filter
            if self.p.use_time_filter:
                if not check_time_filter(dt, list(self.p.allowed_hours), True):
                    return

            # Day filter
            if self.p.use_day_filter:
                if not check_day_filter(dt, list(self.p.allowed_days), True):
                    return

            # Max entries per day
            if self.p.max_entries_per_day > 0:
                current_date = dt.date()
                if self.last_trade_date != current_date:
                    self.last_trade_date = current_date
                    self.trades_today = 0
                if self.trades_today >= self.p.max_entries_per_day:
                    return

            # Regime filter: only trade during allowed regimes
            if self.p.regime_enabled:
                if self._regime_code not in self.p.allowed_regimes:
                    return

            # ATR entry filter
            try:
                atr_now = float(self.atr_h1[0])
                if not math.isnan(atr_now) and atr_now > 0:
                    if (self.p.min_atr_entry > 0
                            and atr_now < self.p.min_atr_entry):
                        return
                    if (self.p.max_atr_entry > 0
                            and atr_now > self.p.max_atr_entry):
                        return
            except (IndexError, ValueError):
                pass

            # DTOSC bearish signal
            if not self._check_dtosc_short_signal():
                return

            # All conditions met
            if self.p.use_tr1bl:
                self.state = "TRIGGERED"
                self._triggered_bar_count = 0
                self._triggered_sell_stop = (
                    float(self.data_h1.low[0]) - self.p.tr1bl_tick)
                self._frozen_swing_high = (
                    self._swing_high
                    if self._swing_high > 0 else None)
                if self.p.print_signals:
                    sw = (f'{self._frozen_swing_high:.2f}'
                          if self._frozen_swing_high else 'N/A')
                    print(f'[LYRA] {dt} TRIGGERED: '
                          f'sell_stop={self._triggered_sell_stop:.2f} '
                          f'swing_high={sw}')
            else:
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

        if self._first_bar_dt and self._last_bar_dt:
            data_days = (self._last_bar_dt - self._first_bar_dt).days
            data_years = max(data_days / 365.25, 0.1)
            periods_per_year = len(self._portfolio_values) / data_years
        else:
            periods_per_year = 252 * 7

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
                std = np.std(arr)
                if std > 0:
                    sharpe_ratio = (
                        np.mean(arr) * periods_per_year
                    ) / (std * np.sqrt(periods_per_year))

        max_dd = 0.0
        if self._portfolio_values:
            peak = self._portfolio_values[0]
            for v in self._portfolio_values:
                if v > peak:
                    peak = v
                dd = (peak - v) / peak * 100.0
                if dd > max_dd:
                    max_dd = dd

        print(f'\n{"="*70}')
        print(f'LYRA STRATEGY RESULTS -- {self.data_h1._name}')
        print(f'{"="*70}')
        print(f'Direction:       SHORT ONLY')
        print(f'Total Trades:    {total_trades}')
        print(f'Win Rate:        {win_rate:.1f}%')
        pf_str = f'{profit_factor:.2f}' if profit_factor < 100 else 'INF'
        print(f'Profit Factor:   {pf_str}')
        print(f'Net P&L:         ${total_pnl:,.2f}')
        print(f'Final Value:     ${final_value:,.2f}')
        print(f'Max Drawdown:    {max_dd:.2f}%')
        print(f'Sharpe Ratio:    {sharpe_ratio:.4f}')
        print(f'Triggered Cancels: {self._triggered_cancels}')
        print(f'{"="*70}\n')

        if self.trade_report_file:
            try:
                f = self.trade_report_file
                f.write(f"\n{'='*70}\n")
                f.write(f"SUMMARY\n")
                f.write(f"Total Trades: {total_trades}\n")
                f.write(f"Win Rate: {win_rate:.1f}%\n")
                f.write(f"Profit Factor: {pf_str}\n")
                f.write(f"Net P&L: ${total_pnl:,.2f}\n")
                f.write(f"Max Drawdown: {max_dd:.2f}%\n")
                f.write(f"Sharpe: {sharpe_ratio:.4f}\n")
                f.close()
            except Exception:
                pass
