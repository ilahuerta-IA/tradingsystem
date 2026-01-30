"""
GLIESE Strategy v2 - Mean Reversion for Ranging Markets

Trades oversold bounces when market is NOT trending (ADXR < threshold).
Complement to trend-following strategies (SEDNA, KOI, SunsetOgle).

CURRENT LOGIC (v2 Simplified):
  1. Wait for ADXR < threshold (ranging market)
  2. Price (close) goes BELOW lower band (KAMA - ATR*mult) for min_bars
  3. Price (close) returns ABOVE lower band → IMMEDIATE ENTRY
  4. SL: Extension low - buffer
  5. TP: Entry + ATR * multiplier

Key Parameters:
  - extension_min_bars: Minimum bars below band (8-10 optimal)
  - band_atr_mult: Band distance from KAMA (1.0 = tight)
  - adxr_max_threshold: Max ADXR to allow entry (20-25 = ranging)
  - atr_tp_multiplier: TP distance in ATR units

Analysis Findings (USDCHF 5 years):
  - Extension 10+ bars: PF 2.30+
  - Wednesday/Friday best days
  - Hours 7-8am (UTC) best entry
  - SL 15-20 pips optimal
  - Duration <1h = 71% WR

Author: Ivan
Version: 2.1.0
"""
import backtrader as bt
import numpy as np
from datetime import datetime, timedelta
from enum import Enum, auto
from collections import defaultdict
from typing import Optional, Tuple, Dict, List
import os

from lib.indicators import KAMA
from lib.filters import calculate_adxr, check_adxr_filter


class GLIESEState(Enum):
    """Simplified state machine for GLIESE v2."""
    IDLE = auto()
    IN_EXTENSION = auto()        # A: Below lower band
    CONFIRMING = auto()          # B: Confirming reversal (delay before entry)
    REVERSAL_DETECTED = auto()   # C: Returned above band (legacy, not used with confirmation)
    WAITING_BREAKOUT = auto()    # D: In pullback, waiting for breakout
    IN_POSITION = auto()


class EntryExitLines(bt.Indicator):
    """
    Indicator to plot entry/exit price levels as horizontal dashed lines.
    Shows Entry (green), Stop Loss (red), Take Profit (blue).
    """
    lines = ('entry', 'stop_loss', 'take_profit', 'lower_band')
    
    plotinfo = dict(subplot=False, plotlinelabels=True)
    plotlines = dict(
        entry=dict(color='green', linestyle='--', linewidth=1.0),
        stop_loss=dict(color='red', linestyle='--', linewidth=1.0),
        take_profit=dict(color='blue', linestyle='--', linewidth=1.0),
        lower_band=dict(color='orange', linestyle='-', linewidth=0.8),
    )
    
    def __init__(self):
        pass
    
    def next(self):
        pass


class GLIESEStrategy(bt.Strategy):
    """
    GLIESE v2 - Simplified Mean Reversion Strategy
    
    Entry Logic:
        1. HL2_EMA(10) goes below LowerBand for min_extension_bars
        2. HL2_EMA(10) returns above LowerBand (reversal)
        3. Price pulls back without breaking extension low
        4. Price breaks above pullback high → LONG ENTRY
    
    Exit:
        - Take Profit: Price reaches KAMA (center)
        - Stop Loss: Extension low - buffer
    """
    
    params = dict(
        # === KAMA Settings ===
        kama_period=10,
        kama_fast=2,
        kama_slow=30,
        
        # === HL2 EMA for stability ===
        hl2_ema_period=10,
        
        # === Band Settings ===
        band_atr_period=14,
        band_atr_mult=2.0,  # LowerBand = KAMA - mult * ATR
        
        # === Extension Detection ===
        extension_min_bars=3,
        extension_max_bars=15,
        
        # === Pullback Settings ===
        pullback_max_bars=5,
        breakout_buffer_pips=2.0,
        
        # === SL/TP ===
        sl_buffer_pips=5.0,
        use_kama_tp=True,  # TP at KAMA
        atr_sl_multiplier=2.0,  # SL = entry - atr_sl_mult * ATR
        atr_tp_multiplier=3.0,  # TP = entry + atr_tp_mult * ATR (if use_kama_tp=False)
        
        # === FILTERS (same as SEDNA) ===
        use_time_filter=False,
        allowed_hours=[],
        
        use_day_filter=False,
        allowed_days=[0, 1, 2, 3, 4],
        
        use_sl_pips_filter=False,
        sl_pips_min=5.0,
        sl_pips_max=30.0,
        
        use_atr_filter=False,
        atr_min=0.0003,
        atr_max=0.0010,
        atr_avg_period=20,
        
        # === ADXR Filter (ranging market) ===
        use_adxr_filter=False,
        adxr_period=14,
        adxr_lookback=14,
        adxr_max_threshold=25.0,  # ADXR < 25 = ranging (good for mean reversion)
        
        # === Time-Based Exit ===
        use_time_exit=False,
        time_exit_bars=12,  # Exit if no TP/SL hit after X bars (12 bars = 1h on 5min TF)
        
        # === Confirmation Delay (filter fakeouts) ===
        use_confirmation_delay=False,
        confirmation_bars=3,  # Wait X bars above band before entry (3 bars = 15min on 5min TF)
        
        # === Asset Config ===
        pip_value=0.0001,
        lot_size=100000,
        jpy_rate=1.0,
        is_etf=False,
        is_jpy_pair=False,
        margin_pct=3.33,
        
        # === Risk ===
        risk_percent=0.01,
        
        # === Debug ===
        print_signals=False,
        export_reports=True,
        
        # === Plot ===
        plot_bands=True,
        plot_entry_exit_lines=True,  # Show entry/SL/TP on chart
    )
    
    def __init__(self):
        """Initialize indicators and state."""
        d = self.data
        
        # HL2 = (High + Low) / 2 - same approach as SEDNA
        self.hl2 = (d.high + d.low) / 2.0
        
        # KAMA on close (custom implementation like SEDNA)
        self.kama = KAMA(
            d.close,
            period=self.p.kama_period,
            fast=self.p.kama_fast,
            slow=self.p.kama_slow
        )
        
        # EMA on HL2 for stability (period=1 = raw HL2)
        self.hl2_ema = bt.ind.EMA(self.hl2, period=self.p.hl2_ema_period)
        
        # ATR for bands
        self.atr = bt.ind.ATR(d, period=self.p.band_atr_period)
        
        # Entry/Exit lines for plotting
        if self.p.plot_entry_exit_lines:
            self.entry_exit_lines = EntryExitLines(d)
        else:
            self.entry_exit_lines = None
        
        # State
        self.state = GLIESEState.IDLE
        
        # Extension tracking
        self.extension_bar_count = 0
        self.extension_low = None
        self.extension_start_bar = None
        
        # Pullback tracking
        self.pullback_high = None
        self.pullback_bar_count = 0
        self.breakout_level = None
        
        # Pattern ATR (for SL calculation)
        self.pattern_atr = None
        
        # Orders
        self.order = None
        self.stop_order = None
        self.limit_order = None
        self.stop_level = None
        self.take_level = None
        
        # Trade tracking
        self._starting_cash = None
        self.trades = 0
        self.wins = 0
        self.losses = 0
        self.gross_profit = 0.0
        self.gross_loss = 0.0
        self._portfolio_values = []
        self._trade_pnls = []
        self.last_exit_reason = None
        
        # ATR history for averaging
        self.atr_history = []
        
        # Time-based exit tracking
        self.entry_bar = None
        
        # Confirmation delay tracking
        self.confirmation_bar_count = 0
        
        # Trade report
        self.trade_report_file = None
        
    def start(self):
        """Called at strategy start."""
        self._starting_cash = self.broker.get_cash()
        
        # Open trade report file
        if self.p.export_reports:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
            os.makedirs(log_dir, exist_ok=True)
            filepath = os.path.join(log_dir, f'GLIESE_trades_{timestamp}.txt')
            self.trade_report_file = open(filepath, 'w', encoding='utf-8')
            self.trade_report_file.write("=== GLIESE v2 STRATEGY TRADE REPORT ===\n")
            self.trade_report_file.write(f"Generated: {datetime.now()}\n")
            self.trade_report_file.write(f"KAMA: period={self.p.kama_period}, fast={self.p.kama_fast}, slow={self.p.kama_slow}\n")
            self.trade_report_file.write(f"Band: KAMA - {self.p.band_atr_mult} x ATR\n")
            self.trade_report_file.write(f"Extension: {self.p.extension_min_bars}-{self.p.extension_max_bars} bars\n")
            self.trade_report_file.write(f"HL2_EMA period: {self.p.hl2_ema_period}\n\n")
    
    def prenext(self):
        """Called before minimum period is reached."""
        pass
    
    def next(self):
        """Main strategy logic - called on each bar."""
        # Track portfolio value
        self._portfolio_values.append(self.broker.get_value())
        
        # Track ATR history
        if len(self.atr) > 0 and not np.isnan(self.atr[0]):
            self.atr_history.append(float(self.atr[0]))
            if len(self.atr_history) > self.p.atr_avg_period:
                self.atr_history.pop(0)
        
        # Update plot lines
        self._update_plot_lines()
        
        # Skip if order pending
        if self.order:
            return
        
        # Check time-based exit if in position
        if self.position:
            self._check_time_exit()
            return
        
        # Get current values
        dt = self.data.datetime.datetime(0)
        current_bar = len(self)
        
        # Apply filters
        if not self._check_filters(dt):
            return
        
        # State machine
        signal = self._process_state_machine(dt, current_bar)
        
        if signal:
            self._execute_entry(dt)
    
    def _check_filters(self, dt: datetime) -> bool:
        """Check all filters. Returns True if all pass."""
        # Time filter
        if self.p.use_time_filter and self.p.allowed_hours:
            if dt.hour not in self.p.allowed_hours:
                return False
        
        # Day filter
        if self.p.use_day_filter and self.p.allowed_days:
            if dt.weekday() not in self.p.allowed_days:
                return False
        
        # ATR filter
        if self.p.use_atr_filter and len(self.atr_history) >= self.p.atr_avg_period:
            avg_atr = np.mean(self.atr_history)
            if not (self.p.atr_min <= avg_atr <= self.p.atr_max):
                return False
        
        # ADXR filter - ranging market (ADXR < threshold)
        if self.p.use_adxr_filter:
            required_bars = (self.p.adxr_period * 2) + self.p.adxr_lookback + 5
            if len(self.data) >= required_bars:
                highs = [float(self.data.high[-i]) for i in range(required_bars)]
                lows = [float(self.data.low[-i]) for i in range(required_bars)]
                closes = [float(self.data.close[-i]) for i in range(required_bars)]
                highs.reverse()
                lows.reverse()
                closes.reverse()
                
                adxr_value = calculate_adxr(
                    highs, lows, closes,
                    self.p.adxr_period, self.p.adxr_lookback
                )
                
                if not check_adxr_filter(adxr_value, self.p.adxr_max_threshold, True):
                    return False
        
        return True
    
    def _update_plot_lines(self):
        """Update the entry/exit lines indicator for visualization."""
        if not self.entry_exit_lines:
            return
        
        # Always show lower band
        lower_band = self._get_lower_band()
        self.entry_exit_lines.lines.lower_band[0] = lower_band
        
        # Show entry/SL/TP only when in position
        if self.position and self.stop_level and self.take_level:
            entry_price = self.position.price
            self.entry_exit_lines.lines.entry[0] = entry_price
            self.entry_exit_lines.lines.stop_loss[0] = self.stop_level
            self.entry_exit_lines.lines.take_profit[0] = self.take_level
        else:
            # Clear lines when not in position
            self.entry_exit_lines.lines.entry[0] = float('nan')
            self.entry_exit_lines.lines.stop_loss[0] = float('nan')
            self.entry_exit_lines.lines.take_profit[0] = float('nan')
    
    def _check_time_exit(self):
        """Check if trade should be closed due to time limit."""
        if not self.p.use_time_exit or self.entry_bar is None:
            return
        
        current_bar = len(self)
        bars_in_trade = current_bar - self.entry_bar
        
        if bars_in_trade >= self.p.time_exit_bars:
            # Time limit reached - close position at market
            if self.p.print_signals:
                dt = self.data.datetime.datetime(0)
                print(f"[{dt:%Y-%m-%d %H:%M}] GLIESE: TIME EXIT after {bars_in_trade} bars")
            
            # Cancel pending SL/TP orders
            if self.stop_order:
                self.cancel(self.stop_order)
            if self.limit_order:
                self.cancel(self.limit_order)
            
            # Close position at market
            self.order = self.close()
            self.last_exit_reason = "TIME_EXIT"
    
    def _get_lower_band(self) -> float:
        """Calculate lower band: KAMA - mult * ATR."""
        kama_val = float(self.kama[0])
        atr_val = float(self.atr[0])
        return kama_val - self.p.band_atr_mult * atr_val
    
    def _get_avg_atr(self) -> float:
        """Get average ATR."""
        if len(self.atr_history) >= 5:
            return np.mean(self.atr_history[-20:])
        return float(self.atr[0])
    
    def _process_state_machine(self, dt: datetime, current_bar: int) -> bool:
        """
        Process state machine for pattern detection.
        Returns True if entry signal generated.
        """
        current_close = float(self.data.close[0])
        lower_band = self._get_lower_band()
        current_low = float(self.data.low[0])
        current_high = float(self.data.high[0])
        
        # =====================================================================
        # STATE: IDLE - Looking for extension below band
        # =====================================================================
        if self.state == GLIESEState.IDLE:
            if current_close < lower_band:
                # Start extension
                self.state = GLIESEState.IN_EXTENSION
                self.extension_bar_count = 1
                self.extension_low = current_low
                self.extension_start_bar = current_bar
                
                if self.p.print_signals:
                    print(f"[{dt:%Y-%m-%d %H:%M}] GLIESE: EXTENSION START | "
                          f"Close={current_close:.5f} < Band={lower_band:.5f}")
            
            return False
        
        # =====================================================================
        # STATE: IN_EXTENSION - Tracking extension, waiting for return
        # =====================================================================
        elif self.state == GLIESEState.IN_EXTENSION:
            # Update extension low
            self.extension_low = min(self.extension_low, current_low)
            
            if current_close < lower_band:
                # Still in extension
                self.extension_bar_count += 1
                
                # Timeout check
                if self.extension_bar_count > self.p.extension_max_bars:
                    if self.p.print_signals:
                        print(f"[{dt:%Y-%m-%d %H:%M}] GLIESE: Extension timeout ({self.extension_bar_count} bars)")
                    self._reset_state()
                    return False
            else:
                # Close returned above band - check if extension was long enough
                if self.extension_bar_count >= self.p.extension_min_bars:
                    self.pattern_atr = self._get_avg_atr()
                    
                    # Check if confirmation delay is enabled
                    if self.p.use_confirmation_delay:
                        # Enter CONFIRMING state
                        self.state = GLIESEState.CONFIRMING
                        self.confirmation_bar_count = 1
                        
                        if self.p.print_signals:
                            print(f"[{dt:%Y-%m-%d %H:%M}] GLIESE: CONFIRMING START | "
                                  f"ExtBars={self.extension_bar_count}, waiting {self.p.confirmation_bars} bars")
                        return False
                    else:
                        # No confirmation - ENTRY SIGNAL IMMEDIATELY
                        if self.p.print_signals:
                            print(f"[{dt:%Y-%m-%d %H:%M}] GLIESE: REVERSAL - ENTRY | "
                                  f"ExtBars={self.extension_bar_count}, ExtLow={self.extension_low:.5f}")
                        return True
                else:
                    # Extension too short
                    if self.p.print_signals:
                        print(f"[{dt:%Y-%m-%d %H:%M}] GLIESE: Extension too short ({self.extension_bar_count} bars)")
                    self._reset_state()
            
            return False
        
        # =====================================================================
        # STATE: CONFIRMING - Pure delay (wait X bars then entry, no conditions)
        # =====================================================================
        elif self.state == GLIESEState.CONFIRMING:
            # Pure delay - just count bars, no conditions checked
            self.confirmation_bar_count += 1
            
            if self.confirmation_bar_count >= self.p.confirmation_bars:
                # Delay complete - ENTRY SIGNAL (no matter what)
                if self.p.print_signals:
                    print(f"[{dt:%Y-%m-%d %H:%M}] GLIESE: DELAY COMPLETE - ENTRY | "
                          f"DelayBars={self.confirmation_bar_count}")
                return True
            
            return False
        
        return False
    
    def _reset_state(self):
        """Reset state machine to IDLE."""
        self.state = GLIESEState.IDLE
        self.extension_bar_count = 0
        self.extension_low = None
        self.extension_start_bar = None
        self.pullback_high = None
        self.pullback_bar_count = 0
        self.breakout_level = None
        self.pattern_atr = None
        self.confirmation_bar_count = 0  # Reset confirmation counter
    
    def _execute_entry(self, dt: datetime):
        """Execute entry order."""
        # Calculate SL/TP
        sl_buffer = self.p.sl_buffer_pips * self.p.pip_value
        self.stop_level = self.extension_low - sl_buffer
        
        if self.p.use_kama_tp:
            self.take_level = float(self.kama[0])
        else:
            self.take_level = float(self.data.close[0]) + self.pattern_atr * self.p.atr_tp_multiplier
        
        # Calculate position size
        entry_price = float(self.data.close[0])
        sl_distance = entry_price - self.stop_level
        sl_pips = sl_distance / self.p.pip_value
        
        # SL pips filter
        if self.p.use_sl_pips_filter:
            if not (self.p.sl_pips_min <= sl_pips <= self.p.sl_pips_max):
                if self.p.print_signals:
                    print(f"[{dt:%Y-%m-%d %H:%M}] GLIESE: SL pips filter failed ({sl_pips:.1f})")
                self._reset_state()
                return
        
        # Position sizing
        account_value = self.broker.get_value()
        risk_amount = account_value * self.p.risk_percent
        
        if self.p.is_etf:
            position_value = risk_amount / (sl_distance / entry_price)
            size = int(position_value / entry_price)
        else:
            pip_value_per_lot = self.p.lot_size * self.p.pip_value
            if self.p.pip_value == 0.01:  # JPY pair
                pip_value_per_lot = self.p.lot_size / self.p.jpy_rate
            size_lots = risk_amount / (sl_pips * pip_value_per_lot)
            size = int(size_lots * self.p.lot_size)
        
        if size <= 0:
            self._reset_state()
            return
        
        # Execute market order
        self.order = self.buy(size=size)
        
        # Track entry bar for time-based exit
        self.entry_bar = len(self)
        
        # Log entry
        if self.trade_report_file:
            self.trade_report_file.write(f"ENTRY #{self.trades + 1}\n")
            self.trade_report_file.write(f"Time: {dt}\n")
            self.trade_report_file.write(f"Entry Price: {entry_price:.5f}\n")
            self.trade_report_file.write(f"Stop Loss: {self.stop_level:.5f}\n")
            self.trade_report_file.write(f"Take Profit: {self.take_level:.5f}\n")
            self.trade_report_file.write(f"SL Pips: {sl_pips:.1f}\n")
            self.trade_report_file.write(f"ATR (avg): {self.pattern_atr:.6f}\n")
            self.trade_report_file.write(f"Extension Bars: {self.extension_bar_count}\n")
            self.trade_report_file.write(f"Extension Low: {self.extension_low:.5f}\n")
            self.trade_report_file.write("-" * 50 + "\n\n")
        
        self.state = GLIESEState.IN_POSITION
    
    def notify_order(self, order):
        """Handle order notifications."""
        if order.status in [order.Submitted, order.Accepted]:
            return
        
        if order.status == order.Completed:
            if order.isbuy():
                # Entry completed - place SL and TP orders
                self.stop_order = self.sell(
                    size=order.executed.size,
                    exectype=bt.Order.Stop,
                    price=self.stop_level
                )
                self.limit_order = self.sell(
                    size=order.executed.size,
                    exectype=bt.Order.Limit,
                    price=self.take_level,
                    oco=self.stop_order
                )
                
                if self.p.print_signals:
                    print(f"[OK] GLIESE BUY at {order.executed.price:.5f} size={order.executed.size}")
                
                self.order = None
            
            elif order.issell():
                # Exit completed
                if order == self.stop_order:
                    self.last_exit_reason = "STOP_LOSS"
                elif order == self.limit_order:
                    self.last_exit_reason = "TAKE_PROFIT"
                else:
                    self.last_exit_reason = "UNKNOWN"
                
                if self.p.print_signals:
                    print(f"[EXIT] at {order.executed.price:.5f} reason={self.last_exit_reason}")
                
                self.stop_order = None
                self.limit_order = None
                self.order = None
                self.stop_level = None
                self.take_level = None
                self.entry_bar = None  # Reset entry bar tracking
        
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            # Handle OCA cancellations silently
            is_expected_cancel = (self.stop_order and self.limit_order)
            if not is_expected_cancel and self.p.print_signals:
                print(f"Order {order.getstatusname()}: {order.ref}")
            
            if self.order and order.ref == self.order.ref:
                self.order = None
            if self.stop_order and order.ref == self.stop_order.ref:
                self.stop_order = None
            if self.limit_order and order.ref == self.limit_order.ref:
                self.limit_order = None
    
    def notify_trade(self, trade):
        """Handle trade notifications."""
        if not trade.isclosed:
            return
        
        self.trades += 1
        # Use pnlcomm to include commission in P&L calculation
        pnl = trade.pnlcomm  # Net P&L after commission
        
        if pnl > 0:
            self.wins += 1
            self.gross_profit += pnl
        else:
            self.losses += 1
            self.gross_loss += abs(pnl)
        
        # Store for yearly stats
        dt = self.data.datetime.datetime(0)
        self._trade_pnls.append({
            'date': dt,
            'year': dt.year,
            'pnl': pnl,
            'is_winner': pnl > 0
        })
        
        # Log exit
        if self.trade_report_file:
            self.trade_report_file.write(f"EXIT #{self.trades}\n")
            self.trade_report_file.write(f"Time: {dt}\n")
            self.trade_report_file.write(f"Exit Reason: {self.last_exit_reason}\n")
            self.trade_report_file.write(f"P&L: ${pnl:,.2f}\n")
            self.trade_report_file.write("=" * 80 + "\n\n")
        
        # Reset state
        self._reset_state()
    
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
            if total_return > 0 and len(self._trade_pnls) > 0:
                first_date = self._trade_pnls[0]['date']
                last_date = self._trade_pnls[-1]['date']
                days = (last_date - first_date).days
                years = max(days / 365.25, 0.1)
                cagr = (pow(total_return, 1.0 / years) - 1.0) * 100.0
        
        # Calmar Ratio
        calmar_ratio = cagr / max_drawdown_pct if max_drawdown_pct > 0 else 0
        
        # Monte Carlo Simulation
        monte_carlo_dd_95 = 0.0
        monte_carlo_dd_99 = 0.0
        if len(self._trade_pnls) >= 20:
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
        print("=== GLIESE v2 STRATEGY SUMMARY ===")
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
        
        # Strategy Configuration
        print(f"\n{'='*70}")
        print("STRATEGY CONFIGURATION")
        print(f"{'='*70}")
        print(f"  KAMA: period={self.p.kama_period}, fast={self.p.kama_fast}, slow={self.p.kama_slow}")
        print(f"  Band: KAMA - {self.p.band_atr_mult} x ATR")
        print(f"  HL2_EMA period: {self.p.hl2_ema_period}")
        print(f"  Extension: {self.p.extension_min_bars}-{self.p.extension_max_bars} bars")
        print(f"  Pullback max: {self.p.pullback_max_bars} bars")
        print(f"  TP: {'KAMA' if self.p.use_kama_tp else f'{self.p.atr_tp_multiplier}x ATR'}")
        print(f"  SL buffer: {self.p.sl_buffer_pips} pips")
        if self.p.use_time_filter:
            print(f"  Time Filter: hours {list(self.p.allowed_hours)}")
        if self.p.use_day_filter:
            print(f"  Day Filter: days {list(self.p.allowed_days)}")
        if self.p.use_sl_pips_filter:
            print(f"  SL Pips Filter: {self.p.sl_pips_min}-{self.p.sl_pips_max}")
        print("=" * 70)
        
        # Close trade report file
        if self.trade_report_file:
            try:
                self.trade_report_file.write("\n=== FINAL SUMMARY ===\n")
                self.trade_report_file.write(f"Total Trades: {self.trades}\n")
                self.trade_report_file.write(f"Wins: {self.wins} | Losses: {self.losses}\n")
                self.trade_report_file.write(f"Win Rate: {win_rate:.1f}%\n")
                self.trade_report_file.write(f"Profit Factor: {profit_factor:.2f}\n")
                self.trade_report_file.write(f"Sharpe Ratio: {sharpe_ratio:.2f}\n")
                self.trade_report_file.write(f"Max Drawdown: {max_drawdown_pct:.2f}%\n")
                self.trade_report_file.write(f"Net P&L: ${total_pnl:.2f}\n")
                self.trade_report_file.close()
                print(f"\nTrade report saved.")
            except:
                pass
