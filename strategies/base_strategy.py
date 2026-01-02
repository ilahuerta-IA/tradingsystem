"""
Base strategy class with common functionality.
All strategies should inherit from this class.
"""
import backtrader as bt
from abc import abstractmethod
import os

class BaseStrategy(bt.Strategy):
    """
    Abstract base class for all trading strategies.
    
    Provides common functionality:
    - Position sizing with JPY correction
    - Time filtering
    - ATR-based stop loss and take profit calculation
    - Trade logging
    """
    params = (
        # Risk management
        ('risk_pct', 0.003),            # Risk per trade (0.3%)
        
        # JPY pair settings
        ('is_jpy', False),              # JPY pair flag
        ('jpy_rate', 150.0),            # JPY/USD rate for size correction
        
        # Forex settings
        ('lot_size', 100000),           # Standard lot size
        ('pip_value', 0.01),            # 0.01 for JPY, 0.0001 for standard
        
        # Time filter
        ('allowed_hours', None),        # List of allowed trading hours
        
        # ATR settings
        ('atr_period', 14),
        ('atr_min', 0.030),
        ('atr_max', 0.090),
        
        # SL/TP multipliers
        ('sl_mult', 3.5),
        ('tp_mult', 15.0),
        
        # Debug
        ('debug_mode', False),
    )
    
    def __init__(self):
        self.order = None
        self.sl_order = None
        self.tp_order = None
        self.trade_count = 0
        self.trade_log = []
        
        # ATR indicator
        self.atr = bt.indicators.ATR(self.data, period=self.p.atr_period)
    
    def log(self, txt, dt=None):
        """Log message with timestamp."""
        dt = dt or self.datas[0].datetime.datetime(0)
        msg = f'{dt.isoformat()} {txt}'
        if self.p.log_file:
            with open(self.p.log_file, 'a') as f: f.write(msg + "\n")
        if type == 'CRITICAL' or self.p.debug:
            print(msg)

    def debug(self, txt):
        """Debug message (only if debug_mode enabled)."""
        if self.p.debug_mode:
            self.log(f'[DEBUG] {txt}')
    
    def is_valid_hour(self):
        """Check if current hour is in allowed trading hours."""
        if self.p.allowed_hours is None:
            return True
        current_hour = self.datas[0].datetime.datetime(0).hour
        return current_hour in self.p.allowed_hours
    
    def is_atr_valid(self):
        """Check if ATR is within valid range."""
        current_atr = self.atr[0]
        return self.p.atr_min <= current_atr <= self.p.atr_max
    
    def calculate_position_size(self, entry_price, stop_loss):
        """
        Calculate position size based on risk percentage.
        
        Includes JPY pair correction for accurate lot sizing.
        Returns size in Backtrader units (adjusted for JPY if needed).
        """
        account_value = self.broker.getvalue()
        risk_amount = account_value * self.p.risk_pct
        
        stop_distance = abs(entry_price - stop_loss)
        if stop_distance <= 0:
            return 0
        
        stop_distance_pips = stop_distance / self.p.pip_value
        
        if self.p.is_jpy:
            # JPY pairs: pip value in JPY, convert to USD
            pip_value_jpy = self.p.lot_size * self.p.pip_value  # 1000 JPY per pip per lot
            pip_value_usd = pip_value_jpy / entry_price  # Convert to USD
            
            # Calculate optimal lots
            optimal_lots = risk_amount / (stop_distance_pips * pip_value_usd)
            
            # Convert to Backtrader size (adjusted by jpy_rate for commission calc)
            real_contracts = optimal_lots * self.p.lot_size
            bt_size = int(real_contracts / self.p.jpy_rate)
        else:
            # Standard pairs: direct calculation
            pip_value_usd = 10.0  # $10 per pip per standard lot
            optimal_lots = risk_amount / (stop_distance_pips * pip_value_usd)
            bt_size = int(optimal_lots * self.p.lot_size)
        
        return max(1, bt_size)
    
    def calculate_sl_tp(self, entry_price, entry_bar_low, entry_bar_high, direction='long'):
        """
        Calculate stop loss and take profit based on ATR.
        
        Uses entry bar high/low as reference points (not entry price).
        """
        atr_value = self.atr[0]
        
        if direction == 'long':
            sl = entry_bar_low - (atr_value * self.p.sl_mult)
            tp = entry_bar_high + (atr_value * self.p.tp_mult)
        else:
            sl = entry_bar_high + (atr_value * self.p.sl_mult)
            tp = entry_bar_low - (atr_value * self.p.tp_mult)
        
        return sl, tp
    
    def notify_order(self, order):
        """Handle order notifications."""
        if order.status in [order.Submitted, order.Accepted]:
            return
        
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f'BUY EXECUTED @ {order.executed.price:.5f} | Comm: {order.executed.comm:.2f}')
            else:
                self.log(f'SELL EXECUTED @ {order.executed.price:.5f} | Comm: {order.executed.comm:.2f}')
        
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log(f'Order Canceled/Margin/Rejected: {order.status}')
        
        self.order = None
    
    def notify_trade(self, trade):
        """Handle trade notifications."""
        if not trade.isclosed:
            return
        
        self.log(f'TRADE CLOSED | Gross: {trade.pnl:.2f} | Net: {trade.pnlcomm:.2f}')
        
        self.trade_log.append({
            'entry_time': bt.num2date(trade.dtopen),
            'exit_time': bt.num2date(trade.dtclose),
            'pnl': trade.pnlcomm,
            'size': trade.size,
        })
    
    @abstractmethod
    def next(self):
        """Main strategy logic - must be implemented by subclasses."""
        pass