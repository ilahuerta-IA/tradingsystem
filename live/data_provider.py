"""
MT5 Market Data Provider.

Single Responsibility: Fetch OHLCV data from MT5.
Does NOT analyze signals or execute trades.

Features:
- Fetches historical bars (configurable count)
- Waits for candle close before returning
- Returns pandas DataFrame compatible with backtest strategies
- Connection health monitoring

Usage:
    provider = DataProvider(connector)
    df = provider.get_bars('EURUSD', timeframe='M5', count=150)
"""

import time
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

import pandas as pd
import numpy as np

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    mt5 = None

from .connector import MT5Connector


class Timeframe(Enum):
    """Supported timeframes."""
    M1 = (mt5.TIMEFRAME_M1 if MT5_AVAILABLE else 1, 1)
    M5 = (mt5.TIMEFRAME_M5 if MT5_AVAILABLE else 5, 5)
    M15 = (mt5.TIMEFRAME_M15 if MT5_AVAILABLE else 15, 15)
    M30 = (mt5.TIMEFRAME_M30 if MT5_AVAILABLE else 30, 30)
    H1 = (mt5.TIMEFRAME_H1 if MT5_AVAILABLE else 60, 60)
    H4 = (mt5.TIMEFRAME_H4 if MT5_AVAILABLE else 240, 240)
    D1 = (mt5.TIMEFRAME_D1 if MT5_AVAILABLE else 1440, 1440)
    
    @property
    def mt5_value(self) -> int:
        """Get MT5 timeframe constant."""
        return self.value[0]
    
    @property
    def minutes(self) -> int:
        """Get timeframe in minutes."""
        return self.value[1]


@dataclass
class BarData:
    """Single bar data structure."""
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'time': self.time,
            'open': self.open,
            'high': self.high,
            'low': self.low,
            'close': self.close,
            'volume': self.volume
        }


class DataProvider:
    """
    Provides market data from MT5.
    
    Features:
    - Fetches N bars of historical data
    - Configurable timeframe (default M5)
    - Returns pandas DataFrame (compatible with backtest)
    - Waits for candle close synchronization
    - Handles connection issues gracefully
    
    Example:
        connector = MT5Connector()
        connector.connect()
        
        provider = DataProvider(connector)
        
        # Get last 150 closed M5 bars for EURUSD
        df = provider.get_bars('EURUSD', count=150)
        
        # Wait for next M5 candle to close
        provider.wait_for_candle_close('EURUSD')
    """
    
    # Minimum bars needed for indicators (EMA 120 + buffer)
    MIN_BARS_FOR_INDICATORS = 150
    
    # Default timeframe
    DEFAULT_TIMEFRAME = Timeframe.M5
    
    def __init__(
        self,
        connector: MT5Connector,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize data provider.
        
        Args:
            connector: MT5Connector instance (must be connected)
            logger: Optional logger instance
        """
        self.connector = connector
        self.logger = logger or logging.getLogger(__name__)
        
        # Cache for symbol info
        self._symbol_cache: Dict[str, Dict] = {}
    
    def get_bars(
        self,
        symbol: str,
        timeframe: Timeframe = None,
        count: int = None,
        include_current: bool = False
    ) -> Optional[pd.DataFrame]:
        """
        Get historical bars from MT5.
        
        Args:
            symbol: Symbol name (e.g., 'EURUSD')
            timeframe: Timeframe enum (default M5)
            count: Number of bars to fetch (default MIN_BARS_FOR_INDICATORS)
            include_current: If False, exclude the forming (incomplete) bar
            
        Returns:
            DataFrame with columns: time, open, high, low, close, volume
            Returns None on error
        """
        if not self.connector.is_connected():
            self.logger.error("Not connected to MT5")
            return None
        
        if not MT5_AVAILABLE:
            self.logger.error("MT5 library not available")
            return None
        
        timeframe = timeframe or self.DEFAULT_TIMEFRAME
        count = count or self.MIN_BARS_FOR_INDICATORS
        
        try:
            # Request extra bar if we're excluding current
            fetch_count = count + 1 if not include_current else count
            
            # Fetch bars from MT5
            rates = mt5.copy_rates_from_pos(
                symbol,
                timeframe.mt5_value,
                0,  # Start from current bar
                fetch_count
            )
            
            if rates is None or len(rates) == 0:
                error = mt5.last_error()
                self.logger.error(f"Failed to get bars for {symbol}: {error}")
                return None
            
            # Convert to DataFrame
            df = pd.DataFrame(rates)
            
            # Convert time from timestamp to datetime
            df['time'] = pd.to_datetime(df['time'], unit='s')
            
            # Rename columns to match backtest format
            df = df.rename(columns={
                'tick_volume': 'volume'
            })
            
            # Select only needed columns
            df = df[['time', 'open', 'high', 'low', 'close', 'volume']]
            
            # Exclude current (incomplete) bar if requested
            if not include_current and len(df) > count:
                df = df.iloc[:-1]
            
            # Ensure we have exactly the requested count
            df = df.tail(count)
            
            # Reset index
            df = df.reset_index(drop=True)
            
            self.logger.debug(
                f"Fetched {len(df)} bars for {symbol} {timeframe.name}, "
                f"from {df['time'].iloc[0]} to {df['time'].iloc[-1]}"
            )
            
            return df
            
        except Exception as e:
            self.logger.error(f"Error fetching bars for {symbol}: {e}")
            return None
    
    def get_current_bar(
        self,
        symbol: str,
        timeframe: Timeframe = None
    ) -> Optional[BarData]:
        """
        Get the current (forming) bar.
        
        Args:
            symbol: Symbol name
            timeframe: Timeframe (default M5)
            
        Returns:
            BarData for current bar or None on error
        """
        if not self.connector.is_connected():
            return None
        
        timeframe = timeframe or self.DEFAULT_TIMEFRAME
        
        try:
            rates = mt5.copy_rates_from_pos(
                symbol,
                timeframe.mt5_value,
                0,  # Current bar
                1
            )
            
            if rates is None or len(rates) == 0:
                return None
            
            bar = rates[0]
            return BarData(
                time=datetime.fromtimestamp(bar['time']),
                open=float(bar['open']),
                high=float(bar['high']),
                low=float(bar['low']),
                close=float(bar['close']),
                volume=int(bar['tick_volume'])
            )
            
        except Exception as e:
            self.logger.error(f"Error getting current bar: {e}")
            return None
    
    def get_tick(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get current tick (bid/ask) for symbol.
        
        Args:
            symbol: Symbol name
            
        Returns:
            Dictionary with bid, ask, time or None on error
        """
        if not self.connector.is_connected():
            return None
        
        try:
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return None
            
            return {
                'bid': tick.bid,
                'ask': tick.ask,
                'time': datetime.fromtimestamp(tick.time),
                'volume': tick.volume
            }
            
        except Exception as e:
            self.logger.error(f"Error getting tick for {symbol}: {e}")
            return None
    
    def wait_for_candle_close(
        self,
        symbol: str,
        timeframe: Timeframe = None,
        timeout_seconds: int = 400,
        check_interval: float = 1.0
    ) -> bool:
        """
        Wait for current candle to close.
        
        Blocks until the current candle closes and a new one starts.
        This ensures we analyze complete bars only.
        
        Args:
            symbol: Symbol to monitor
            timeframe: Timeframe (default M5)
            timeout_seconds: Maximum wait time (default ~6.5 min for M5)
            check_interval: Seconds between checks
            
        Returns:
            True if candle closed, False on timeout or error
        """
        timeframe = timeframe or self.DEFAULT_TIMEFRAME
        
        # Get current bar time
        current_bar = self.get_current_bar(symbol, timeframe)
        if current_bar is None:
            self.logger.error("Could not get current bar for wait")
            return False
        
        start_bar_time = current_bar.time
        start_wait = time.time()
        
        self.logger.info(
            f"Waiting for {symbol} {timeframe.name} candle to close "
            f"(current bar: {start_bar_time.strftime('%H:%M')})"
        )
        
        while True:
            # Check timeout
            elapsed = time.time() - start_wait
            if elapsed > timeout_seconds:
                self.logger.warning(f"Timeout waiting for candle close after {elapsed:.0f}s")
                return False
            
            # Check connection
            if not self.connector.is_connected():
                self.logger.error("Connection lost while waiting for candle")
                return False
            
            # Check if new bar started
            new_bar = self.get_current_bar(symbol, timeframe)
            if new_bar is None:
                self.logger.warning("Could not get bar, retrying...")
                time.sleep(check_interval)
                continue
            
            if new_bar.time > start_bar_time:
                self.logger.info(
                    f"[OK] New candle opened: {new_bar.time.strftime('%H:%M')} "
                    f"(waited {elapsed:.1f}s)"
                )
                return True
            
            # Still same candle, wait
            time.sleep(check_interval)
    
    def get_seconds_until_candle_close(
        self,
        timeframe: Timeframe = None
    ) -> int:
        """
        Calculate seconds remaining until current candle closes.
        
        Args:
            timeframe: Timeframe (default M5)
            
        Returns:
            Seconds until candle close
        """
        timeframe = timeframe or self.DEFAULT_TIMEFRAME
        
        now = datetime.now()
        minutes_in_candle = now.minute % timeframe.minutes
        seconds_in_candle = minutes_in_candle * 60 + now.second
        total_seconds = timeframe.minutes * 60
        
        return total_seconds - seconds_in_candle
    
    def get_symbol_digits(self, symbol: str) -> int:
        """
        Get decimal digits for symbol (for price formatting).
        
        Args:
            symbol: Symbol name
            
        Returns:
            Number of decimal places (e.g., 5 for EURUSD)
        """
        if symbol in self._symbol_cache:
            return self._symbol_cache[symbol].get('digits', 5)
        
        info = self.connector.get_symbol_info(symbol)
        if info:
            self._symbol_cache[symbol] = info
            return info['digits']
        
        # Default for forex
        return 5 if not symbol.endswith('JPY') else 3


# Convenience function for testing
def test_data_provider() -> bool:
    """Test data provider functionality."""
    from .connector import MT5Connector
    
    logging.basicConfig(level=logging.INFO)
    
    with MT5Connector(demo_only=True) as conn:
        if not conn.is_connected():
            print("[FAIL] Could not connect to MT5")
            return False
        
        provider = DataProvider(conn)
        
        # Test get_bars
        print("\nTesting get_bars...")
        df = provider.get_bars('EURUSD', count=10)
        
        if df is not None and len(df) > 0:
            print(f"[OK] Got {len(df)} bars")
            print(df.tail(3))
        else:
            print("[FAIL] Failed to get bars")
            return False
        
        # Test get_tick
        print("\nTesting get_tick...")
        tick = provider.get_tick('EURUSD')
        
        if tick:
            print(f"[OK] EURUSD Bid: {tick['bid']}, Ask: {tick['ask']}")
        else:
            print("[FAIL] Failed to get tick")
            return False
        
        # Test seconds until close
        seconds = provider.get_seconds_until_candle_close()
        print(f"\nSeconds until M5 close: {seconds}")
        
        return True


if __name__ == "__main__":
    test_data_provider()
