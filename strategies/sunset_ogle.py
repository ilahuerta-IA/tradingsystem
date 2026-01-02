"""
Sunset Ogle Strategy - Volatility Expansion Channel Entry System
================================================================
EXACT replica of sunrise_ogle_eurjpy_pro.py for TradingSystem.

4-Phase State Machine:
1. SCANNING - Monitor for EMA crossover signals
2. ARMED_LONG - Wait for pullback candles (bearish)
3. WINDOW_OPEN - Monitor breakout level
4. Entry executed with ATR-based SL/TP

Active Filters (EURJPY):
- Price Filter EMA: close > EMA(70)
- Angle Filter: 45-95 degrees, scale 100
- ATR Filter: 0.030-0.090
- Time Filter: 5:00-18:00 UTC

Supports multiple instruments via params.
"""
from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path

import backtrader as bt


class SunsetOgleStrategy(bt.Strategy):
    """
    Volatility Expansion Channel Strategy - Long-only.
    
    Implements 4-phase state machine for entry detection with
    EMA crossover signals, pullback confirmation, and breakout execution.
    """
    
    params = dict(
        # EMA settings
        ema_fast_length=18,
        ema_medium_length=18,
        ema_slow_length=24,
        ema_confirm_length=1,
        ema_filter_price_length=70,
        
        # ATR settings
        atr_length=10,
        atr_min=0.030,
        atr_max=0.090,
        
        # Angle settings
        angle_min=45.0,
        angle_max=95.0,
        angle_scale=100.0,
        
        # SL/TP multipliers
        sl_mult=3.5,
        tp_mult=15.0,
        
        # Pullback settings
        pullback_candles=2,
        window_periods=2,
        price_offset_mult=0.01,
        
        # Time filter
        time_start_hour=5,
        time_start_minute=0,
        time_end_hour=18,
        time_end_minute=0,
        
        # Risk management
        risk_percent=0.003,
        
        # JPY pair settings
        is_jpy=True,
        jpy_rate=150.0,
        lot_size=100000,
        pip_value=0.01,
        
        # Debug and reporting
        print_signals=True,
        export_report=True,
    )
    
    def __init__(self):
        """Initialize indicators and state variables."""
        d = self.data
        
        # Technical indicators
        self.ema_fast = bt.ind.EMA(d.close, period=self.p.ema_fast_length)
        self.ema_medium = bt.ind.EMA(d.close, period=self.p.ema_medium_length)
        self.ema_slow = bt.ind.EMA(d.close, period=self.p.ema_slow_length)
        self.ema_confirm = bt.ind.EMA(d.close, period=self.p.ema_confirm_length)
        self.ema_filter = bt.ind.EMA(d.close, period=self.p.ema_filter_price_length)
        self.atr = bt.ind.ATR(d, period=self.p.atr_length)
        
        # Order tracking
        self.order = None
        self.stop_order = None
        self.limit_order = None
        
        # Price levels
        self.stop_level = None
        self.take_level = None
        self.last_entry_price = None
        
        # State machine variables
        self.entry_state = "SCANNING"
        self.pullback_count = 0
        self.pullback_high = None
        self.pullback_low = None
        self.window_top = None
        self.window_bottom = None
        self.window_expiry = None
        self.window_start = None
        
        # Signal tracking for ATR increment calculation
        self.signal_atr = None
        self.entry_atr_increment = None
        
        # Timing tracking
        self.last_entry_bar = None
        self.entry_window_start = None
        
        # Statistics (same as original)
        self.trades = 0
        self.wins = 0
        self.losses = 0
        self.gross_profit = 0.0
        self.gross_loss = 0.0
        
        # Trade tracking for yearly stats
        self._trade_pnls = []
        self._initial_cash = None
        
        # Detailed trade reports
        self.trade_reports = []
        self.trade_report_file = None
        
        # Exit reason tracking
        self.last_exit_reason = "UNKNOWN"
        
        # Initialize trade reporting
        self._init_trade_reporting()
    
    def _init_trade_reporting(self):
        """Initialize trade report file."""
        if not self.p.export_report:
            return
            
        try:
            reports_dir = Path('temp_reports')
            reports_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            asset_name = getattr(self.data, '_name', 'UNKNOWN')
            filename = f'{asset_name}_trades_{timestamp}.txt'
            filepath = reports_dir / filename
            
            self.trade_report_file = open(filepath, 'w')
            
            # Write header (same format as original)
            self.trade_report_file.write("=== SUNRISE STRATEGY TRADE REPORT ===\n")
            self.trade_report_file.write(f"Asset: {asset_name}\n")
            self.trade_report_file.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            self.trade_report_file.write(f"Data File: EURJPY_5m_5Yea.csv\n")
            self.trade_report_file.write("Trading Direction: LONG\n\n")
            
            # Configuration parameters
            self.trade_report_file.write("CONFIGURATION PARAMETERS:\n")
            self.trade_report_file.write("-" * 30 + "\n")
            self.trade_report_file.write("LONG Configuration:\n")
            self.trade_report_file.write(f"  ATR Range: {self.p.atr_min:.6f} - {self.p.atr_max:.6f}\n")
            self.trade_report_file.write(f"  Angle Range: {self.p.angle_min:.2f} to {self.p.angle_max:.2f} deg\n")
            self.trade_report_file.write("  Candle Direction Filter: DISABLED\n")
            self.trade_report_file.write("  Pullback Mode: True\n\n")
            
            self.trade_report_file.write("Common Parameters:\n")
            self.trade_report_file.write(f"  Risk Percent: {self.p.risk_percent*100:.1f}%\n")
            self.trade_report_file.write(f"  Trading Hours: {self.p.time_start_hour:02d}:00 - {self.p.time_end_hour:02d}:00 UTC\n")
            self.trade_report_file.write("  Window Time Offset: DISABLED (Immediate window opening)\n")
            self.trade_report_file.write(f"  LONG Stop Loss ATR Multiplier: {self.p.sl_mult}\n")
            self.trade_report_file.write(f"  LONG Take Profit ATR Multiplier: {self.p.tp_mult}\n\n")
            
            self.trade_report_file.write("=" * 80 + "\n")
            self.trade_report_file.write("TRADE DETAILS\n")
            self.trade_report_file.write("=" * 80 + "\n\n")
            self.trade_report_file.flush()
            
        except Exception as e:
            print(f"Trade reporting init error: {e}")
            self.trade_report_file = None
    
    def _cross_above(self, a, b):
        """Check if line a crosses above line b."""
        try:
            return (float(a[0]) > float(b[0])) and (float(a[-1]) <= float(b[-1]))
        except (IndexError, ValueError, TypeError):
            return False
    
    def _cross_below(self, a, b):
        """Check if line a crosses below line b."""
        try:
            return (float(a[0]) < float(b[0])) and (float(a[-1]) >= float(b[-1]))
        except (IndexError, ValueError, TypeError):
            return False
    
    def _angle(self):
        """Calculate EMA angle in degrees."""
        try:
            rise = (float(self.ema_confirm[0]) - float(self.ema_confirm[-1])) * self.p.angle_scale
            return math.degrees(math.atan(rise))
        except (IndexError, ValueError, TypeError, ZeroDivisionError):
            return float('nan')
    
    def _in_time_range(self, dt):
        """Check if current time is within trading hours."""
        current = dt.hour * 60 + dt.minute
        start = self.p.time_start_hour * 60 + self.p.time_start_minute
        end = self.p.time_end_hour * 60 + self.p.time_end_minute
        return start <= current <= end
    
    def _reset_state(self):
        """Reset entry state machine to SCANNING."""
        self.entry_state = "SCANNING"
        self.pullback_count = 0
        self.pullback_high = None
        self.pullback_low = None
        self.window_top = None
        self.window_bottom = None
        self.window_expiry = None
        self.window_start = None
        self.entry_window_start = None
    
    def _check_signal(self):
        """PHASE 1: Check for valid EMA crossover signal with all filters."""
        # EMA crossover (confirm crosses above ANY of fast/medium/slow)
        cross_any = (
            self._cross_above(self.ema_confirm, self.ema_fast) or
            self._cross_above(self.ema_confirm, self.ema_medium) or
            self._cross_above(self.ema_confirm, self.ema_slow)
        )
        
        if not cross_any:
            return False
        
        # Price filter: close > EMA(70)
        if self.data.close[0] <= self.ema_filter[0]:
            return False
        
        # Angle filter: 45-95 degrees
        angle = self._angle()
        if not (self.p.angle_min <= angle <= self.p.angle_max):
            return False
        
        # ATR filter: 0.030-0.090
        atr = float(self.atr[0]) if not math.isnan(float(self.atr[0])) else 0.0
        if atr < self.p.atr_min or atr > self.p.atr_max:
            return False
        
        # Store ATR at signal detection for increment calculation
        self.signal_atr = atr
        self.entry_window_start = len(self)
        return True
    
    def _check_pullback(self):
        """PHASE 2: Count bearish pullback candles."""
        is_bearish = self.data.close[0] < self.data.open[0]
        
        if is_bearish:
            self.pullback_count += 1
            if self.pullback_count >= self.p.pullback_candles:
                self.pullback_high = float(self.data.high[0])
                self.pullback_low = float(self.data.low[0])
                return True
        else:
            # Non-pullback candle invalidates sequence
            self._reset_state()
        
        return False
    
    def _open_window(self):
        """PHASE 3: Open breakout window after pullback confirmation."""
        current_bar = len(self)
        self.window_start = current_bar
        self.window_expiry = current_bar + self.p.window_periods
        
        # Calculate channel with dynamic price offset
        candle_range = self.pullback_high - self.pullback_low
        offset = candle_range * self.p.price_offset_mult
        
        self.window_top = self.pullback_high + offset
        self.window_bottom = self.pullback_low - offset
        
        self.entry_state = "WINDOW_OPEN"
        
        if self.p.print_signals:
            dt = self.datas[0].datetime.datetime(0)
            print(f'{dt} [{self.data._name}] Phase: ARMED -> BREAKOUT. Level: {self.window_top:.3f} (Offset Dynamic: {offset:.5f})')
    
    def _monitor_window(self):
        """PHASE 4: Monitor for breakout within window."""
        current_bar = len(self)
        
        # Timeout: return to ARMED state (allows re-pullback)
        if current_bar > self.window_expiry:
            self.entry_state = "ARMED_LONG"
            self.pullback_count = 0
            self.window_top = None
            self.window_bottom = None
            self.window_expiry = None
            return None
        
        # Success: high breaks above top level
        if self.data.high[0] >= self.window_top:
            return 'SUCCESS'
        
        # Failure: low breaks below bottom (instability)
        if self.data.low[0] <= self.window_bottom:
            self.entry_state = "ARMED_LONG"
            self.pullback_count = 0
            self.window_top = None
            self.window_bottom = None
            self.window_expiry = None
        
        return None
    
    def _validate_entry(self):
        """Validate all filters at breakout execution time."""
        # Price filter
        if self.data.close[0] <= self.ema_filter[0]:
            return False
        
        # Angle filter
        angle = self._angle()
        if not (self.p.angle_min <= angle <= self.p.angle_max):
            return False
        
        return True
    
    def _calculate_position_size(self, entry_price, stop_loss):
        """Calculate position size based on risk parameters (JPY corrected)."""
        raw_risk = entry_price - stop_loss
        if raw_risk <= 0:
            return 0
        
        pip_risk = raw_risk / self.p.pip_value
        pip_value_jpy = self.p.lot_size * self.p.pip_value
        value_per_pip = pip_value_jpy / entry_price
        
        equity = self.broker.get_value()
        risk_amount = equity * self.p.risk_percent
        
        if pip_risk > 0 and value_per_pip > 0:
            optimal_lots = risk_amount / (pip_risk * value_per_pip)
        else:
            return 0
        
        optimal_lots = max(0.01, round(optimal_lots, 2))
        real_contracts = int(optimal_lots * self.p.lot_size)
        bt_size = int(real_contracts / self.p.jpy_rate)
        
        return max(100, bt_size)
    
    def _record_trade_entry(self, dt, entry_price, atr, angle):
        """Record trade entry for detailed reporting."""
        if not self.trade_report_file:
            return
        
        try:
            # Calculate bars to entry
            current_bar = len(self)
            bars_to_entry = current_bar - self.entry_window_start if self.entry_window_start else 1
            bars_to_entry = max(1, min(bars_to_entry, 50))
            
            # Calculate ATR increment
            atr_increment = 0.0
            if self.signal_atr is not None:
                atr_increment = atr - self.signal_atr
            self.entry_atr_increment = atr_increment
            
            # Store trade data
            trade_entry = {
                'entry_time': dt,
                'direction': 'LONG',
                'entry_price': entry_price,
                'stop_level': self.stop_level,
                'take_level': self.take_level,
                'current_atr': atr,
                'atr_increment': atr_increment,
                'current_angle': angle,
                'bars_to_entry': bars_to_entry,
            }
            self.trade_reports.append(trade_entry)
            
            # Write to file (same format as original)
            trade_num = len(self.trade_reports)
            self.trade_report_file.write(f"ENTRY #{trade_num}\n")
            self.trade_report_file.write(f"Time: {dt.strftime('%Y-%m-%d %H:%M:%S')}\n")
            self.trade_report_file.write("Direction: LONG\n")
            self.trade_report_file.write(f"ATR Current: {atr:.6f}\n")
            
            # ATR increment/decrement display
            if atr_increment >= 0:
                self.trade_report_file.write(f"ATR Increment: {atr_increment:+.6f} (No Filter)\n")
            else:
                self.trade_report_file.write(f"ATR Change: {atr_increment:+.6f} (Decrement Filter OFF)\n")
            
            self.trade_report_file.write(f"Angle Current: {angle:.2f} deg\n")
            self.trade_report_file.write(f"Angle Filter: ENABLED | Range: {self.p.angle_min:.1f}-{self.p.angle_max:.1f} deg | Valid: True\n")
            self.trade_report_file.write(f"Bars to Entry: {bars_to_entry}\n")
            self.trade_report_file.write("-" * 50 + "\n\n")
            self.trade_report_file.flush()
            
        except Exception as e:
            print(f"Trade entry recording error: {e}")
    
    def _record_trade_exit(self, dt, exit_price, pnl, exit_reason):
        """Record trade exit for detailed reporting."""
        if not self.trade_report_file or not self.trade_reports:
            return
        
        try:
            last_trade = self.trade_reports[-1]
            
            # Calculate duration
            entry_time = last_trade.get('entry_time')
            if entry_time:
                duration = dt - entry_time
                duration_minutes = int(duration.total_seconds() / 60)
                duration_bars = int(duration_minutes / 5)
            else:
                duration_minutes = 0
                duration_bars = 0
            
            # Calculate pips
            entry_price = last_trade.get('entry_price', 0)
            pips = (exit_price - entry_price) / self.p.pip_value if entry_price > 0 else 0
            
            # Update trade record
            last_trade.update({
                'exit_time': dt,
                'exit_price': exit_price,
                'pnl': pnl,
                'pips': pips,
                'exit_reason': exit_reason,
                'duration_bars': duration_bars,
                'duration_minutes': duration_minutes,
            })
            
            # Write to file
            trade_num = len(self.trade_reports)
            self.trade_report_file.write(f"EXIT #{trade_num}\n")
            self.trade_report_file.write(f"Time: {dt.strftime('%Y-%m-%d %H:%M:%S')}\n")
            self.trade_report_file.write(f"Exit Reason: {exit_reason}\n")
            self.trade_report_file.write(f"P&L: {pnl:.2f}\n")
            self.trade_report_file.write(f"Pips: {pips:.1f}\n")
            self.trade_report_file.write(f"Duration: {duration_bars} bars ({duration_minutes} min)\n")
            self.trade_report_file.write("=" * 80 + "\n\n")
            self.trade_report_file.flush()
            
        except Exception as e:
            print(f"Trade exit recording error: {e}")
    
    def _close_trade_reporting(self):
        """Close trade report file and write summary."""
        if not self.trade_report_file:
            return
        
        try:
            total_trades = len(self.trade_reports)
            winning_trades = [t for t in self.trade_reports if t.get('pnl', 0) > 0]
            losing_trades = [t for t in self.trade_reports if t.get('pnl', 0) <= 0]
            
            total_pnl = sum(t.get('pnl', 0) for t in self.trade_reports)
            win_rate = (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0
            
            avg_win = sum(t.get('pnl', 0) for t in winning_trades) / len(winning_trades) if winning_trades else 0
            avg_loss = sum(t.get('pnl', 0) for t in losing_trades) / len(losing_trades) if losing_trades else 0
            
            self.trade_report_file.write("\n" + "=" * 80 + "\n")
            self.trade_report_file.write("SUMMARY\n")
            self.trade_report_file.write("=" * 80 + "\n")
            self.trade_report_file.write(f"Total Trades: {total_trades}\n")
            self.trade_report_file.write(f"Winning Trades: {len(winning_trades)}\n")
            self.trade_report_file.write(f"Losing Trades: {len(losing_trades)}\n")
            self.trade_report_file.write(f"Win Rate: {win_rate:.2f}%\n")
            self.trade_report_file.write(f"Total P&L: {total_pnl:.2f}\n")
            self.trade_report_file.write(f"Average Win: {avg_win:.2f}\n")
            self.trade_report_file.write(f"Average Loss: {avg_loss:.2f}\n")
            self.trade_report_file.write("=" * 80 + "\n")
            
            self.trade_report_file.close()
            self.trade_report_file = None
            
        except Exception as e:
            print(f"Trade reporting close error: {e}")
    
    def _execute_entry(self, dt):
        """Execute entry order with position sizing and protective orders."""
        atr = float(self.atr[0]) if not math.isnan(float(self.atr[0])) else 0.0
        if atr <= 0:
            self._reset_state()
            return
        
        entry_price = float(self.data.close[0])
        bar_low = float(self.data.low[0])
        bar_high = float(self.data.high[0])
        
        # Calculate SL/TP levels
        self.stop_level = bar_low - atr * self.p.sl_mult
        self.take_level = bar_high + atr * self.p.tp_mult
        
        # Calculate position size
        bt_size = self._calculate_position_size(entry_price, self.stop_level)
        if bt_size <= 0:
            self._reset_state()
            return
        
        # Log entry
        self.trades += 1
        angle = self._angle()
        
        print('')
        print(f'{dt} [{self.data._name}] ENTRY #{self.trades}')
        print(f'{dt} [{self.data._name}] Time: {dt}')
        print(f'{dt} [{self.data._name}] Direction: LONG')
        print(f'{dt} [{self.data._name}] Price: {entry_price:.3f} | SL: {self.stop_level:.3f} | TP: {self.take_level:.3f}')
        print(f'{dt} [{self.data._name}] ATR: {atr:.5f} | Angle: {angle:.1f}')
        print('-' * 40)
        
        # Record entry for reporting
        self._record_trade_entry(dt, entry_price, atr, angle)
        
        # Place order
        self.order = self.buy(size=bt_size)
        self.last_entry_price = entry_price
        self.last_entry_bar = len(self)
        
        # Reset state machine
        self._reset_state()
        self.signal_atr = None
    
    def next(self):
        """Main strategy logic - 4-phase state machine."""
        # Capture initial cash on first bar
        if self._initial_cash is None:
            self._initial_cash = self.broker.get_value()
        
        dt = self.datas[0].datetime.datetime(0)
        
        # Cancel phantom orders when no position
        if not self.position:
            if self.order:
                try:
                    self.cancel(self.order)
                except Exception:
                    pass
                self.order = None
            if self.stop_order:
                try:
                    self.cancel(self.stop_order)
                except Exception:
                    pass
                self.stop_order = None
            if self.limit_order:
                try:
                    self.cancel(self.limit_order)
                except Exception:
                    pass
                self.limit_order = None
        
        # Wait for pending entry orders
        if self.order:
            return
        
        # Skip entry logic if in position
        if self.position:
            return
        
        # GLOBAL INVALIDATION: Reset only if opposing crossover WITH bearish previous candle
        if self.entry_state == "ARMED_LONG":
            try:
                prev_bear = self.data.close[-1] < self.data.open[-1]
                cross_any = (self._cross_below(self.ema_confirm, self.ema_fast) or
                            self._cross_below(self.ema_confirm, self.ema_medium) or
                            self._cross_below(self.ema_confirm, self.ema_slow))
                if prev_bear and cross_any:
                    self._reset_state()
            except IndexError:
                pass
        
        # STATE MACHINE ROUTER
        if self.entry_state == "SCANNING":
            if self._check_signal():
                self.entry_state = "ARMED_LONG"
                self.pullback_count = 0
                if self.p.print_signals:
                    print(f'{dt} [{self.data._name}] Phase: SCANNING -> ARMED (Angle: {self._angle():.1f})')
        
        elif self.entry_state == "ARMED_LONG":
            if self._check_pullback():
                self._open_window()
        
        elif self.entry_state == "WINDOW_OPEN":
            result = self._monitor_window()
            
            if result == 'SUCCESS':
                # Time filter check
                if not self._in_time_range(dt):
                    self._reset_state()
                    return
                
                # Validate filters at breakout
                if not self._validate_entry():
                    self._reset_state()
                    return
                
                self._execute_entry(dt)
    
    def notify_order(self, order):
        """Handle order notifications."""
        if order.status in [order.Submitted, order.Accepted]:
            return
        
        if order.status == order.Completed:
            dt = self.datas[0].datetime.datetime(0)
            
            if order == self.order:
                if order.isbuy():
                    print(f'{dt} [{self.data._name}] === BUY EXEC @ {order.executed.price:.5f} | Comm: {order.executed.comm:.2f} ===')
                    
                    # Place protective orders
                    if self.stop_level and self.take_level:
                        self.stop_order = self.sell(
                            size=order.executed.size,
                            exectype=bt.Order.Stop,
                            price=self.stop_level,
                        )
                        self.limit_order = self.sell(
                            size=order.executed.size,
                            exectype=bt.Order.Limit,
                            price=self.take_level,
                        )
                
                self.order = None
            
            else:
                # Exit order completed
                print(f'{dt} [{self.data._name}] === SELL EXEC @ {order.executed.price:.5f} | Comm: {order.executed.comm:.2f} ===')
                
                # Determine exit reason
                if order == self.stop_order:
                    self.last_exit_reason = "STOP_LOSS"
                elif order == self.limit_order:
                    self.last_exit_reason = "TAKE_PROFIT"
                else:
                    self.last_exit_reason = "UNKNOWN"
                
                # Cancel remaining protective order
                if order == self.stop_order and self.limit_order:
                    try:
                        self.cancel(self.limit_order)
                    except Exception:
                        pass
                elif order == self.limit_order and self.stop_order:
                    try:
                        self.cancel(self.stop_order)
                    except Exception:
                        pass
                
                self.stop_order = None
                self.limit_order = None
        
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            if order == self.order:
                self.order = None
            if order == self.stop_order:
                self.stop_order = None
            if order == self.limit_order:
                self.limit_order = None
    
    def notify_trade(self, trade):
        """Handle trade notifications - track statistics."""
        if not trade.isclosed:
            return
        
        dt = bt.num2date(self.data.datetime[0])
        pnl = trade.pnlcomm
        
        # Update statistics
        if pnl > 0:
            self.wins += 1
            self.gross_profit += pnl
        else:
            self.losses += 1
            self.gross_loss += abs(pnl)
        
        # Store for yearly stats
        self._trade_pnls.append({
            'date': dt,
            'year': dt.year,
            'pnl': pnl,
            'is_winner': pnl > 0,
        })
        
        # Calculate exit price
        entry_price = self.last_entry_price if self.last_entry_price else trade.price
        if entry_price > 0 and trade.size != 0:
            exit_price = entry_price + (pnl / trade.size)
        else:
            exit_price = float(self.data.close[0])
        
        print(f'{dt} [{self.data._name}] === TRADE CLOSED | Net P&L: {pnl:.2f} ===')
        
        # Record exit
        self._record_trade_exit(dt, exit_price, pnl, self.last_exit_reason)
        
        # Reset levels
        self.stop_level = None
        self.take_level = None
        self.last_entry_price = None
    
    def stop(self):
        """Strategy end - print summary and close reporting."""
        # Close any open positions
        if self.position:
            self.close()
            if self.stop_order:
                self.cancel(self.stop_order)
            if self.limit_order:
                self.cancel(self.limit_order)
        
        # Calculate metrics
        total_trades = self.wins + self.losses
        win_rate = (self.wins / total_trades * 100) if total_trades > 0 else 0
        profit_factor = (self.gross_profit / self.gross_loss) if self.gross_loss > 0 else float('inf')
        
        final_value = self.broker.get_value()
        initial_cash = self._initial_cash if self._initial_cash else 100000.0
        total_pnl = final_value - initial_cash
        
        # Print summary (same format as original)
        print('\n' + '=' * 60)
        print('STRATEGY SUMMARY')
        print('=' * 60)
        print(f'Total Trades: {total_trades}')
        print(f'Wins: {self.wins} | Losses: {self.losses}')
        print(f'Win Rate: {win_rate:.1f}%')
        print(f'Profit Factor: {profit_factor:.2f}')
        print(f'Gross Profit: ${self.gross_profit:,.2f}')
        print(f'Gross Loss: ${self.gross_loss:,.2f}')
        print(f'Total P&L: ${total_pnl:,.2f}')
        print(f'Final Value: ${final_value:,.2f}')
        print('=' * 60)
        
        # Close trade reporting
        self._close_trade_reporting()
