"""
Order Executor for Live Trading.

Single Responsibility: Execute orders on MT5.
Does NOT detect signals - only executes when told to.

Features:
- Market orders with SL/TP (bracket order)
- Position tracking per strategy
- OCA behavior (one position per strategy)
- Uses lib/position_sizing.py for lot calculation

Usage:
    executor = OrderExecutor(connector, config_name='EURUSD_PRO')
    
    result = executor.execute_long(
        symbol='EURUSD',
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1100
    )
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    mt5 = None

import sys
from pathlib import Path

# Add project root for lib imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from lib.position_sizing import calculate_position_size
from config.settings import STRATEGIES_CONFIG
from .connector import MT5Connector
from .bot_settings import RISK_OVERRIDES


class OrderType(Enum):
    """Order types."""
    BUY = "BUY"
    SELL = "SELL"


class OrderResult(Enum):
    """Order execution result."""
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    POSITION_EXISTS = "POSITION_EXISTS"
    NO_CONNECTION = "NO_CONNECTION"


@dataclass
class ExecutionResult:
    """Order execution result container."""
    success: bool
    result: OrderResult
    order_ticket: Optional[int] = None
    position_ticket: Optional[int] = None
    executed_price: Optional[float] = None
    executed_volume: float = 0.0
    message: str = ""
    timestamp: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            'success': self.success,
            'result': self.result.value,
            'order_ticket': self.order_ticket,
            'position_ticket': self.position_ticket,
            'executed_price': self.executed_price,
            'executed_volume': self.executed_volume,
            'message': self.message,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }


class OrderExecutor:
    """
    Executes orders on MT5.
    
    Features:
    - One position per strategy (OCA behavior)
    - Market orders with immediate SL/TP
    - Position sizing using lib/position_sizing.py
    - Trade logging for analysis
    
    Example:
        connector = MT5Connector()
        connector.connect()
        
        executor = OrderExecutor(connector, 'EURUSD_PRO')
        
        # Check if we can trade
        if executor.can_open_position('EURUSD'):
            result = executor.execute_long(
                symbol='EURUSD',
                entry_price=1.1000,
                stop_loss=1.0950,
                take_profit=1.1100
            )
            
            if result.success:
                print(f"Order filled at {result.executed_price}")
    """
    
    # Magic number base for order identification
    MAGIC_NUMBER_BASE = 20260110  # YYYYMMDD format
    
    def __init__(
        self,
        connector: MT5Connector,
        config_name: str,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize executor.
        
        Args:
            connector: MT5Connector instance (must be connected)
            config_name: Configuration key from STRATEGIES_CONFIG
            logger: Optional logger instance
        """
        self.connector = connector
        self.config_name = config_name
        self.logger = logger or logging.getLogger(__name__)
        
        # Load configuration
        if config_name not in STRATEGIES_CONFIG:
            raise ValueError(f"Configuration not found: {config_name}")
        
        self.config = STRATEGIES_CONFIG[config_name]
        self.params = self.config['params']
        
        # Generate unique magic number for this strategy
        # This allows tracking positions per strategy
        self.magic_number = self._generate_magic_number(config_name)
        
        # Trade history (for logging)
        self.trade_history: List[Dict] = []
        
        self.logger.info(f"OrderExecutor initialized for {config_name}, magic: {self.magic_number}")
    
    def _generate_magic_number(self, config_name: str) -> int:
        """
        Generate unique magic number for strategy identification.
        
        Uses Python's hash with better collision resistance than simple ASCII sum.
        """
        # Use full hash to avoid collisions between similar names
        # e.g., EURJPY_PRO vs USDJPY_PRO had same ASCII sum
        import hashlib
        hash_bytes = hashlib.md5(config_name.encode()).hexdigest()[:8]
        name_hash = int(hash_bytes, 16) % 100000  # 5 digits for more uniqueness
        return self.MAGIC_NUMBER_BASE + name_hash
    
    def _get_filling_mode(self, symbol: str) -> int:
        """
        Detect broker-supported filling mode for symbol.
        
        Error 10030 (INVALID_FILL) occurs when using unsupported filling mode.
        filling_mode flags: 1=FOK, 2=IOC, 4=RETURN (can be combined)
        
        Args:
            symbol: Trading symbol
            
        Returns:
            MT5 filling mode constant
        """
        try:
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                self.logger.warning(f"Cannot get symbol info for {symbol}, defaulting to FOK")
                return mt5.ORDER_FILLING_FOK
            
            filling_mode = symbol_info.filling_mode
            
            # Priority: IOC > FOK > RETURN
            if filling_mode & 2:  # IOC supported
                selected = mt5.ORDER_FILLING_IOC
                self.logger.debug(f"{symbol}: Using IOC filling (broker supports: {filling_mode})")
            elif filling_mode & 1:  # FOK supported
                selected = mt5.ORDER_FILLING_FOK
                self.logger.debug(f"{symbol}: Using FOK filling (broker supports: {filling_mode})")
            elif filling_mode & 4:  # RETURN supported
                selected = mt5.ORDER_FILLING_RETURN
                self.logger.debug(f"{symbol}: Using RETURN filling (broker supports: {filling_mode})")
            else:
                # Fallback to FOK
                selected = mt5.ORDER_FILLING_FOK
                self.logger.warning(f"{symbol}: Unknown filling mode {filling_mode}, defaulting to FOK")
            
            return selected
            
        except Exception as e:
            self.logger.error(f"Error detecting filling mode for {symbol}: {e}")
            return mt5.ORDER_FILLING_FOK
    
    def get_positions(self, symbol: Optional[str] = None) -> List[Dict]:
        """
        Get open positions for this strategy.
        
        Args:
            symbol: Optional symbol filter
            
        Returns:
            List of position dictionaries
        """
        if not self.connector.is_connected():
            return []
        
        try:
            if symbol:
                positions = mt5.positions_get(symbol=symbol)
            else:
                positions = mt5.positions_get()
            
            if positions is None:
                return []
            
            # Filter by magic number (our strategy's positions only)
            our_positions = [
                {
                    'ticket': p.ticket,
                    'symbol': p.symbol,
                    'type': 'BUY' if p.type == mt5.ORDER_TYPE_BUY else 'SELL',
                    'volume': p.volume,
                    'price_open': p.price_open,
                    'sl': p.sl,
                    'tp': p.tp,
                    'profit': p.profit,
                    'magic': p.magic,
                    'time': datetime.fromtimestamp(p.time),
                }
                for p in positions
                if p.magic == self.magic_number
            ]
            
            return our_positions
            
        except Exception as e:
            self.logger.error(f"Error getting positions: {e}")
            return []
    
    def can_open_position(self, symbol: str) -> bool:
        """
        Check if we can open a new position.
        
        Implements OCA: only one position per strategy per symbol.
        
        Args:
            symbol: Symbol to check
            
        Returns:
            True if no existing position for this strategy/symbol
        """
        positions = self.get_positions(symbol)
        
        if len(positions) > 0:
            self.logger.debug(f"Position already exists for {symbol}: {positions[0]['ticket']}")
            return False
        
        return True
    
    def _calculate_lot_size(
        self,
        symbol: str,
        entry_price: float,
        stop_loss: float
    ) -> float:
        """
        Calculate lot size using BROKER-SPECIFIC values (tick_value, tick_size, point).
        
        This is the CORRECT formula for live trading with MT5:
        lot_size = risk_amount / (sl_distance_in_points x value_per_point)
        
        Args:
            symbol: Trading symbol
            entry_price: Entry price
            stop_loss: Stop loss price
            
        Returns:
            Lot size (volume)
        """
        if not self.connector.is_connected():
            self.logger.warning("Not connected, using minimum lot size")
            return 0.01  # Minimum
        
        # Get account equity
        account = self.connector.account
        if account is None:
            self.logger.warning("No account info, using minimum lot size")
            return 0.01
        
        equity = account.equity

        # Risk override: bot_settings.RISK_OVERRIDES > settings.py params
        if self.config_name in RISK_OVERRIDES:
            risk_percent = RISK_OVERRIDES[self.config_name]
        else:
            risk_percent = self.params.get('risk_percent', 0.01)
        
        # Get symbol info from broker (critical for correct calculation)
        symbol_info = self.connector.get_symbol_info(symbol)
        if symbol_info is None:
            self.logger.error(f"Cannot get symbol info for {symbol}, using minimum")
            return 0.01
        
        # Extract broker-specific values
        point = symbol_info['point']  # Minimum price unit (e.g., 0.00001 for EURUSD, 0.001 for USDJPY)
        tick_size = symbol_info['tick_size']  # Minimum price change (usually == point)
        tick_value = symbol_info['tick_value']  # Value per tick in account currency
        min_lot = symbol_info['volume_min']
        max_lot = symbol_info['volume_max']
        lot_step = symbol_info['volume_step']
        
        # Calculate risk amount
        risk_amount = equity * risk_percent
        
        # Calculate SL distance in price
        sl_distance = abs(entry_price - stop_loss)
        
        if sl_distance <= 0:
            self.logger.error(f"Invalid SL distance: {sl_distance}")
            return min_lot
        
        # Calculate value per point from broker data
        # tick_value = value change per tick in account currency
        # point / tick_size handles cases where they differ
        if tick_size > 0 and point > 0:
            value_per_point = tick_value * (point / tick_size)
        else:
            self.logger.warning(f"Invalid tick data for {symbol}, tick_size={tick_size}, point={point}")
            value_per_point = tick_value if tick_value > 0 else 1.0
        
        # Calculate SL distance in points
        sl_distance_in_points = sl_distance / point
        
        # Calculate lot size using broker-specific formula
        # Formula: lot_size = risk_amount / (sl_distance_in_points x value_per_point)
        if value_per_point > 0 and sl_distance_in_points > 0:
            calculated_lots = risk_amount / (sl_distance_in_points * value_per_point)
        else:
            self.logger.error(
                f"Invalid calculation: value_per_point={value_per_point}, "
                f"sl_points={sl_distance_in_points}"
            )
            return min_lot
        
        # Round to lot step
        calculated_lots = round(calculated_lots / lot_step) * lot_step
        
        # Clamp to broker limits
        calculated_lots = max(min_lot, min(calculated_lots, max_lot))
        
        # Log detailed position sizing info
        self.logger.info(
            f"=== POSITION SIZING for {symbol} ===\n"
            f"   Equity: ${equity:,.2f}\n"
            f"   Risk: {risk_percent*100:.1f}% = ${risk_amount:.2f}\n"
            f"   Entry: {entry_price:.5f}, SL: {stop_loss:.5f}\n"
            f"   SL Distance: {sl_distance:.5f} = {sl_distance_in_points:.1f} points\n"
            f"   Broker Values: point={point}, tick_value=${tick_value:.4f}\n"
            f"   Value per Point: ${value_per_point:.5f}\n"
            f"   Lot Calculation: ${risk_amount:.2f} / ({sl_distance_in_points:.1f} x ${value_per_point:.5f})\n"
            f"   Result: {calculated_lots:.2f} lots"
        )
        
        # Risk verification
        actual_risk = calculated_lots * sl_distance_in_points * value_per_point
        if abs(actual_risk - risk_amount) > risk_amount * 0.05:  # > 5% difference
            self.logger.warning(
                f"Risk mismatch! Expected ${risk_amount:.2f}, actual ${actual_risk:.2f}"
            )
        
        return calculated_lots
    
    def execute_long(
        self,
        symbol: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        comment: str = ""
    ) -> ExecutionResult:
        """
        Execute a LONG (BUY) order with SL/TP.
        
        Args:
            symbol: Trading symbol
            entry_price: Expected entry price (for sizing, actual uses market)
            stop_loss: Stop loss price
            take_profit: Take profit price
            comment: Optional order comment
            
        Returns:
            ExecutionResult with details
        """
        now = datetime.now()
        
        # Check connection
        if not self.connector.is_connected():
            return ExecutionResult(
                success=False,
                result=OrderResult.NO_CONNECTION,
                message="Not connected to MT5",
                timestamp=now
            )
        
        # Check if position already exists (OCA)
        if not self.can_open_position(symbol):
            return ExecutionResult(
                success=False,
                result=OrderResult.POSITION_EXISTS,
                message=f"Position already exists for {symbol}",
                timestamp=now
            )
        
        try:
            # Get current price
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return ExecutionResult(
                    success=False,
                    result=OrderResult.FAILED,
                    message=f"Could not get tick for {symbol}",
                    timestamp=now
                )
            
            # Calculate lot size
            volume = self._calculate_lot_size(symbol, entry_price, stop_loss)
            
            # Get symbol info for proper price formatting
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                return ExecutionResult(
                    success=False,
                    result=OrderResult.FAILED,
                    message=f"Symbol not found: {symbol}",
                    timestamp=now
                )
            
            # Round prices to symbol digits
            digits = symbol_info.digits
            stop_loss = round(stop_loss, digits)
            take_profit = round(take_profit, digits)
            
            # Detect broker-supported filling mode (fixes error 10030)
            filling_mode = self._get_filling_mode(symbol)
            
            # Prepare order request
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": volume,
                "type": mt5.ORDER_TYPE_BUY,
                "price": tick.ask,  # Market buy at ask
                "sl": stop_loss,
                "tp": take_profit,
                "deviation": 20,  # Max slippage points
                "magic": self.magic_number,
                "comment": comment or f"TradingSystem {self.config_name}",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": filling_mode,
            }
            
            self.logger.info(
                f"Sending BUY order: {symbol} "
                f"vol={volume:.2f}, SL={stop_loss:.5f}, TP={take_profit:.5f}"
            )
            
            # Send order
            result = mt5.order_send(request)
            
            if result is None:
                error = mt5.last_error()
                return ExecutionResult(
                    success=False,
                    result=OrderResult.FAILED,
                    message=f"Order send failed: {error}",
                    timestamp=now
                )
            
            # Check result
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                return ExecutionResult(
                    success=False,
                    result=OrderResult.REJECTED,
                    message=f"Order rejected: {result.retcode} - {result.comment}",
                    timestamp=now
                )
            
            # Success!
            execution = ExecutionResult(
                success=True,
                result=OrderResult.SUCCESS,
                order_ticket=result.order,
                position_ticket=result.order,  # For market orders, same as order
                executed_price=result.price,
                executed_volume=result.volume,
                message="Order executed successfully",
                timestamp=now
            )
            
            # Log trade
            trade_log = {
                'timestamp': now,
                'symbol': symbol,
                'type': 'BUY',
                'volume': result.volume,
                'price': result.price,
                'sl': stop_loss,
                'tp': take_profit,
                'ticket': result.order,
                'config': self.config_name,
            }
            self.trade_history.append(trade_log)
            
            self.logger.info(
                f"[OK] BUY executed: {symbol} @ {result.price:.5f}, "
                f"vol={result.volume:.2f}, ticket={result.order}"
            )
            
            return execution
            
        except Exception as e:
            self.logger.error(f"Order execution error: {e}")
            return ExecutionResult(
                success=False,
                result=OrderResult.FAILED,
                message=f"Exception: {str(e)}",
                timestamp=now
            )
    
    def get_trade_history(self) -> List[Dict]:
        """Get trade history for this session."""
        return self.trade_history.copy()
    
    def close_position(self, ticket: int) -> ExecutionResult:
        """
        Close an open position.
        
        Args:
            ticket: Position ticket to close
            
        Returns:
            ExecutionResult with details
        """
        now = datetime.now()
        
        if not self.connector.is_connected():
            return ExecutionResult(
                success=False,
                result=OrderResult.NO_CONNECTION,
                message="Not connected",
                timestamp=now
            )
        
        try:
            # Get position info
            position = mt5.positions_get(ticket=ticket)
            if not position:
                return ExecutionResult(
                    success=False,
                    result=OrderResult.FAILED,
                    message=f"Position not found: {ticket}",
                    timestamp=now
                )
            
            pos = position[0]
            
            # Determine close order type
            close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
            
            # Get current price
            tick = mt5.symbol_info_tick(pos.symbol)
            price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
            
            # Detect broker-supported filling mode
            filling_mode = self._get_filling_mode(pos.symbol)
            
            # Prepare close request
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": pos.symbol,
                "volume": pos.volume,
                "type": close_type,
                "position": ticket,
                "price": price,
                "deviation": 20,
                "magic": self.magic_number,
                "comment": "Close position",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": filling_mode,
            }
            
            result = mt5.order_send(request)
            
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                return ExecutionResult(
                    success=False,
                    result=OrderResult.REJECTED,
                    message=f"Close rejected: {result.retcode}",
                    timestamp=now
                )
            
            return ExecutionResult(
                success=True,
                result=OrderResult.SUCCESS,
                executed_price=result.price,
                executed_volume=result.volume,
                message="Position closed",
                timestamp=now
            )
            
        except Exception as e:
            return ExecutionResult(
                success=False,
                result=OrderResult.FAILED,
                message=f"Close error: {e}",
                timestamp=now
            )


# Test function
def test_executor():
    """Test executor functionality (requires MT5 connection)."""
    from .connector import MT5Connector
    
    logging.basicConfig(level=logging.INFO)
    
    with MT5Connector(demo_only=True) as conn:
        if not conn.is_connected():
            print("[FAIL] Could not connect to MT5")
            return False
        
        executor = OrderExecutor(conn, 'EURUSD_PRO')
        
        print(f"\nExecutor magic number: {executor.magic_number}")
        
        # Check existing positions
        positions = executor.get_positions('EURUSD')
        print(f"Existing positions: {len(positions)}")
        
        # Check if can open
        can_open = executor.can_open_position('EURUSD')
        print(f"Can open position: {can_open}")
        
        # Note: Don't actually execute unless testing!
        print("\n[WARNING] Order execution test skipped (safety)")
        print("Uncomment the execute_long call to test real order")
        
        # UNCOMMENT TO TEST REAL ORDER:
        # if can_open:
        #     result = executor.execute_long(
        #         symbol='EURUSD',
        #         entry_price=1.1000,
        #         stop_loss=1.0950,
        #         take_profit=1.1150,
        #         comment="Test order"
        #     )
        #     print(f"Execution result: {result.to_dict()}")
        
        return True


if __name__ == "__main__":
    test_executor()
