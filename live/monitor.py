"""
Live Trading Monitor - Main Orchestrator.

Single Responsibility: Coordinate all components in the trading loop.

This is the "brain" that ties everything together:
- Waits for candle close (data_provider)
- Checks for signals (signal_checker)  
- Executes orders (executor)
- Logs everything (JSON format for analysis)

Architecture:
    +---------------+
    |    Monitor    |  <-- YOU ARE HERE
    +-------+-------+
            |
    +-------+-------+
    |               |
    v               v
+----------+  +--------------+
| Connector|  | DataProvider |
+----+-----+  +------+-------+
     |               |
     v               v
+----------+  +--------------+
| Executor |  |SignalChecker |
+----------+  +--------------+

Usage:
    monitor = LiveTradingMonitor(
        config_name='EURUSD_PRO',
        demo_only=True
    )
    monitor.run()  # Runs until interrupted
"""

import logging
import json
import time
import signal
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

# Add project root
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import STRATEGIES_CONFIG
from .connector import MT5Connector
from .data_provider import DataProvider, Timeframe
from .signal_checker import SignalChecker, SignalDirection
from .executor import OrderExecutor, ExecutionResult


class MonitorState(Enum):
    """Monitor operational states."""
    INITIALIZING = "INITIALIZING"
    RUNNING = "RUNNING"
    WAITING_CANDLE = "WAITING_CANDLE"
    CHECKING_SIGNAL = "CHECKING_SIGNAL"
    EXECUTING = "EXECUTING"
    ERROR = "ERROR"
    STOPPED = "STOPPED"


@dataclass
class MonitorStats:
    """Runtime statistics."""
    start_time: datetime
    candles_processed: int = 0
    signals_detected: int = 0
    trades_executed: int = 0
    errors_count: int = 0
    last_candle_time: Optional[datetime] = None
    last_signal_time: Optional[datetime] = None
    last_trade_time: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for logging."""
        return {
            'start_time': self.start_time.isoformat(),
            'runtime_minutes': (datetime.now() - self.start_time).total_seconds() / 60,
            'candles_processed': self.candles_processed,
            'signals_detected': self.signals_detected,
            'trades_executed': self.trades_executed,
            'errors_count': self.errors_count,
            'last_candle_time': self.last_candle_time.isoformat() if self.last_candle_time else None,
        }


class LiveTradingMonitor:
    """
    Main trading loop orchestrator.
    
    Coordinates:
    - MT5 connection health
    - Candle close synchronization
    - Signal detection
    - Order execution
    - Comprehensive logging
    
    Example:
        monitor = LiveTradingMonitor(
            config_name='EURUSD_PRO',
            demo_only=True,
            log_dir=Path('./logs')
        )
        
        try:
            monitor.run()  # Blocking
        except KeyboardInterrupt:
            monitor.stop()
    """
    
    # Timeframe for M5 candles
    CANDLE_SECONDS = 300  # 5 minutes
    
    # Maximum reconnection attempts
    MAX_RECONNECT_ATTEMPTS = 5
    RECONNECT_DELAY_SECONDS = 30
    
    def __init__(
        self,
        config_name: str,
        demo_only: bool = True,
        log_dir: Optional[Path] = None,
        credentials_path: Optional[Path] = None
    ):
        """
        Initialize trading monitor.
        
        Args:
            config_name: Strategy configuration key (e.g., 'EURUSD_PRO')
            demo_only: Only allow demo accounts (safety)
            log_dir: Directory for JSON logs
            credentials_path: Path to MT5 credentials JSON
        """
        self.config_name = config_name
        self.demo_only = demo_only
        self.log_dir = log_dir or PROJECT_ROOT / 'logs'
        self.credentials_path = credentials_path
        
        # Ensure log directory exists
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Setup logging
        self._setup_logging()
        
        # State
        self.state = MonitorState.INITIALIZING
        self.running = False
        self.stats = MonitorStats(start_time=datetime.now())
        
        # Components (initialized in start())
        self.connector: Optional[MT5Connector] = None
        self.data_provider: Optional[DataProvider] = None
        self.signal_checker: Optional[SignalChecker] = None
        self.executor: Optional[OrderExecutor] = None
        
        # Load configuration
        if config_name not in STRATEGIES_CONFIG:
            raise ValueError(f"Configuration not found: {config_name}")
        
        self.config = STRATEGIES_CONFIG[config_name]
        self.symbol = self.config.get('asset_name') or self.config.get('symbol')
        
        # Trade log file (JSON lines format)
        self.trade_log_path = self.log_dir / f"trades_{config_name}_{datetime.now().strftime('%Y%m%d')}.jsonl"
        
        self.logger.info(f"Monitor initialized for {config_name} ({self.symbol})")
    
    def _setup_logging(self):
        """Configure logging with file and console handlers."""
        self.logger = logging.getLogger(f"Monitor.{self.config_name}")
        self.logger.setLevel(logging.DEBUG)
        
        # Avoid duplicate handlers
        if self.logger.handlers:
            return
        
        # Console handler
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        console.setFormatter(logging.Formatter(
            '%(asctime)s | %(levelname)-7s | %(message)s',
            datefmt='%H:%M:%S'
        ))
        self.logger.addHandler(console)
        
        # File handler (detailed)
        log_file = self.log_dir / f"monitor_{self.config_name}_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s | %(levelname)-7s | %(name)s | %(message)s'
        ))
        self.logger.addHandler(file_handler)
    
    def _log_event(self, event_type: str, data: Dict[str, Any]):
        """
        Log event in JSON format for analysis.
        
        Args:
            event_type: Type of event (SIGNAL, TRADE, ERROR, etc.)
            data: Event data
        """
        event = {
            'timestamp': datetime.now().isoformat(),
            'event_type': event_type,
            'config': self.config_name,
            'symbol': self.symbol,
            **data
        }
        
        with open(self.trade_log_path, 'a') as f:
            f.write(json.dumps(event) + '\n')
    
    def _initialize_components(self) -> bool:
        """
        Initialize all trading components.
        
        Returns:
            True if successful
        """
        try:
            # 1. Connector
            self.logger.info("Initializing MT5 connector...")
            self.connector = MT5Connector(
                credentials_path=self.credentials_path,
                demo_only=self.demo_only
            )
            
            if not self.connector.connect():
                self.logger.error("Failed to connect to MT5")
                return False
            
            # 2. Data Provider
            self.logger.info("Initializing data provider...")
            self.data_provider = DataProvider(
                connector=self.connector
            )
            
            # 3. Signal Checker
            self.logger.info("Initializing signal checker...")
            self.signal_checker = SignalChecker(
                config_name=self.config_name,
                logger=self.logger
            )
            
            # 4. Executor
            self.logger.info("Initializing executor...")
            self.executor = OrderExecutor(
                connector=self.connector,
                config_name=self.config_name,
                logger=self.logger
            )
            
            self.logger.info("[OK] All components initialized")
            return True
            
        except Exception as e:
            self.logger.error(f"Component initialization failed: {e}")
            self._log_event('ERROR', {'error': str(e), 'phase': 'initialization'})
            return False
    
    def _check_connection(self) -> bool:
        """Check and repair MT5 connection if needed."""
        if self.connector is None:
            return False
        
        if self.connector.is_connected():
            return True
        
        # Attempt reconnection
        self.logger.warning("Connection lost, attempting reconnect...")
        self._log_event('CONNECTION', {'status': 'lost'})
        
        for attempt in range(self.MAX_RECONNECT_ATTEMPTS):
            if self.connector.connect():
                self.logger.info(f"Reconnected on attempt {attempt + 1}")
                self._log_event('CONNECTION', {'status': 'reconnected', 'attempt': attempt + 1})
                return True
            
            self.logger.warning(f"Reconnect attempt {attempt + 1} failed")
            time.sleep(self.RECONNECT_DELAY_SECONDS)
        
        self.logger.error("Failed to reconnect after max attempts")
        self._log_event('ERROR', {'error': 'reconnection_failed'})
        return False
    
    def _wait_for_candle_close(self) -> bool:
        """
        Wait until next candle close.
        
        Returns:
            True if candle closed, False if interrupted
        """
        now = datetime.now()
        
        # Calculate seconds until next candle close
        seconds_in_candle = (now.minute % 5) * 60 + now.second
        seconds_to_wait = self.CANDLE_SECONDS - seconds_in_candle
        
        if seconds_to_wait <= 0:
            seconds_to_wait = self.CANDLE_SECONDS
        
        # Add small buffer (2 seconds) for data availability
        seconds_to_wait += 2
        
        next_candle_time = now + timedelta(seconds=seconds_to_wait)
        
        self.logger.info(
            f"Waiting {seconds_to_wait}s until candle close "
            f"(~{next_candle_time.strftime('%H:%M:%S')})"
        )
        
        self.state = MonitorState.WAITING_CANDLE
        
        # Wait in chunks for responsiveness
        while seconds_to_wait > 0 and self.running:
            sleep_time = min(seconds_to_wait, 10)  # Check every 10s
            time.sleep(sleep_time)
            seconds_to_wait -= sleep_time
            
            # Periodic connection check
            if not self._check_connection():
                return False
        
        return self.running
    
    def _process_candle(self):
        """
        Process the closed candle: check signal, execute if needed.
        """
        self.state = MonitorState.CHECKING_SIGNAL
        
        try:
            # 1. Fetch latest data
            bars = self.data_provider.get_bars(
                symbol=self.symbol,
                timeframe=Timeframe.M5,
                count=200  # Extra for indicators
            )
            
            if bars.empty:
                self.logger.warning("No bar data received")
                return
            
            self.stats.candles_processed += 1
            self.stats.last_candle_time = datetime.now()
            
            # Get latest complete candle (index -1 might be forming)
            # So we use -2 for the just-closed candle
            if len(bars) < 2:
                return
            
            # 2. Check for signal
            signal = self.signal_checker.check_signal(bars)
            
            if signal is None or not signal.valid:
                self.logger.debug(f"No signal: {signal.reason if signal else 'None'}")
                return
            
            # 3. Signal detected!
            self.stats.signals_detected += 1
            self.stats.last_signal_time = datetime.now()
            
            entry_str = f"{signal.entry_price:.5f}" if signal.entry_price else "N/A"
            self.logger.info(
                f"SIGNAL: {signal.direction.value} @ {entry_str}"
            )
            
            self._log_event('SIGNAL', signal.to_dict())
            
            # 4. Check if we can execute
            if not self.executor.can_open_position(self.symbol):
                self.logger.info("Position already open, skipping signal")
                return
            
            # 5. Execute (only LONG for now - Sunset_ogle)
            if signal.direction != SignalDirection.LONG:
                self.logger.debug("Non-LONG signal ignored (strategy is long-only)")
                return
            
            self.state = MonitorState.EXECUTING
            
            result = self.executor.execute_long(
                symbol=self.symbol,
                entry_price=signal.entry_price,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                comment=f"{self.config_name}"
            )
            
            if result.success:
                self.stats.trades_executed += 1
                self.stats.last_trade_time = datetime.now()
                
                self._log_event('TRADE', {
                    'direction': 'LONG',
                    'entry': result.executed_price,
                    'volume': result.executed_volume,
                    'sl': signal.stop_loss,
                    'tp': signal.take_profit,
                    'ticket': result.order_ticket,
                })
            else:
                self.logger.warning(f"Execution failed: {result.message}")
                self._log_event('EXECUTION_FAILED', {
                    'reason': result.message,
                    'signal': signal.to_dict()
                })
            
        except Exception as e:
            self.stats.errors_count += 1
            self.logger.error(f"Error processing candle: {e}")
            self._log_event('ERROR', {'error': str(e), 'phase': 'process_candle'})
    
    def start(self) -> bool:
        """
        Start the monitor (initialize components).
        
        Returns:
            True if started successfully
        """
        self.logger.info("=" * 50)
        self.logger.info(f"Starting Live Trading Monitor")
        self.logger.info(f"Config: {self.config_name}")
        self.logger.info(f"Symbol: {self.symbol}")
        self.logger.info(f"Demo Only: {self.demo_only}")
        self.logger.info("=" * 50)
        
        if not self._initialize_components():
            self.state = MonitorState.ERROR
            return False
        
        self.running = True
        self.state = MonitorState.RUNNING
        
        # Log start event
        self._log_event('MONITOR_START', {
            'demo_only': self.demo_only,
            'account': self.connector.account.login if self.connector.account else None
        })
        
        return True
    
    def stop(self):
        """Stop the monitor gracefully."""
        self.logger.info("Stopping monitor...")
        self.running = False
        self.state = MonitorState.STOPPED
        
        # Log stats
        self._log_event('MONITOR_STOP', self.stats.to_dict())
        
        # Disconnect
        if self.connector:
            self.connector.disconnect()
        
        self.logger.info("Monitor stopped")
        self.logger.info(f"Stats: {self.stats.to_dict()}")
    
    def run(self):
        """
        Main trading loop. Runs until interrupted.
        
        Call start() before run().
        """
        if not self.running:
            if not self.start():
                return
        
        self.logger.info("Entering main trading loop")
        
        try:
            while self.running:
                # Wait for next candle close
                if not self._wait_for_candle_close():
                    break
                
                # Process the closed candle
                self._process_candle()
                
                # Brief pause before next cycle
                time.sleep(1)
                
        except KeyboardInterrupt:
            self.logger.info("Keyboard interrupt received")
        except Exception as e:
            self.logger.error(f"Fatal error in main loop: {e}")
            self._log_event('FATAL_ERROR', {'error': str(e)})
        finally:
            self.stop()
    
    def run_single_iteration(self):
        """
        Run a single iteration (for testing).
        
        Does not wait for candle close.
        """
        if not self.running:
            if not self.start():
                return
        
        self.logger.info("Running single iteration...")
        self._process_candle()


def setup_signal_handlers(monitor: LiveTradingMonitor):
    """Setup graceful shutdown handlers."""
    def signal_handler(sig, frame):
        print("\n\n[STOP] Shutdown signal received...")
        monitor.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


# Entry point for direct execution
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Live Trading Monitor')
    parser.add_argument('--config', default='EURUSD_PRO', help='Strategy config name')
    parser.add_argument('--demo-only', action='store_true', default=True, help='Demo only mode')
    parser.add_argument('--single', action='store_true', help='Run single iteration')
    
    args = parser.parse_args()
    
    monitor = LiveTradingMonitor(
        config_name=args.config,
        demo_only=args.demo_only
    )
    
    setup_signal_handlers(monitor)
    
    if args.single:
        monitor.run_single_iteration()
    else:
        monitor.run()
