"""
Multi-Strategy Trading Monitor.

Orchestrates multiple strategies and symbols using the checkers module.
Each enabled configuration gets its own checker instance.
"""

import logging
import json
import time
import signal
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

# Add project root
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import STRATEGIES_CONFIG
from .bot_settings import (
    ENABLED_CONFIGS,
    STRATEGY_TYPES,
    MAX_RECONNECT_ATTEMPTS,
    RECONNECT_DELAY_SECONDS,
    CANDLE_CLOSE_BUFFER_SECONDS,
)
from .connector import MT5Connector
from .data_provider import DataProvider, Timeframe
from .executor import OrderExecutor
from .checkers import get_checker, BaseChecker, Signal, SignalDirection
from .timezone import utc_to_broker


class BrokerTimeFormatter(logging.Formatter):
    """Custom formatter that uses broker time (UTC+3) instead of local time."""
    
    def formatTime(self, record, datefmt=None):
        """Override to use broker time."""
        from .timezone import get_broker_utc_offset
        from datetime import timezone, timedelta
        
        # Get record time and convert to broker time
        ct = datetime.fromtimestamp(record.created)
        # Local to UTC (assuming system is UTC+1 Spain)
        # Then UTC to broker
        broker_offset = get_broker_utc_offset()
        # Simple approach: add (broker_offset - local_offset) hours
        # For now, assume we want broker time = UTC + broker_offset
        utc_time = datetime.utcfromtimestamp(record.created)
        broker_time = utc_time + timedelta(hours=broker_offset)
        
        if datefmt:
            return broker_time.strftime(datefmt)
        return broker_time.strftime("%Y-%m-%d %H:%M:%S") + f",{int(record.msecs):03d}"


class MonitorState(Enum):
    """Monitor operational states."""
    INITIALIZING = "INITIALIZING"
    RUNNING = "RUNNING"
    WAITING_CANDLE = "WAITING_CANDLE"
    CHECKING_SIGNALS = "CHECKING_SIGNALS"
    EXECUTING = "EXECUTING"
    ERROR = "ERROR"
    STOPPED = "STOPPED"


@dataclass
class MonitorStats:
    """Runtime statistics."""
    start_time: datetime = field(default_factory=datetime.now)
    candles_processed: int = 0
    signals_detected: int = 0
    trades_executed: int = 0
    errors_count: int = 0
    last_candle_time: Optional[datetime] = None
    signals_by_strategy: Dict[str, int] = field(default_factory=dict)
    trades_by_strategy: Dict[str, int] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for logging."""
        return {
            "start_time": self.start_time.isoformat(),
            "runtime_minutes": (datetime.now() - self.start_time).total_seconds() / 60,
            "candles_processed": self.candles_processed,
            "signals_detected": self.signals_detected,
            "trades_executed": self.trades_executed,
            "errors_count": self.errors_count,
            "last_candle_time": self.last_candle_time.isoformat() if self.last_candle_time else None,
            "signals_by_strategy": self.signals_by_strategy,
            "trades_by_strategy": self.trades_by_strategy,
        }


class MultiStrategyMonitor:
    """
    Multi-strategy trading monitor.
    
    Manages multiple checkers, one per enabled configuration.
    Each checker is independent and maintains its own state.
    
    Example:
        monitor = MultiStrategyMonitor(demo_only=True)
        monitor.run()
    """
    
    # Timeframe for M5 candles
    CANDLE_SECONDS = 300  # 5 minutes
    
    def __init__(
        self,
        demo_only: bool = True,
        log_dir: Optional[Path] = None,
        credentials_path: Optional[Path] = None
    ):
        """
        Initialize multi-strategy monitor.
        
        Args:
            demo_only: Only allow demo accounts (safety)
            log_dir: Directory for JSON logs
            credentials_path: Path to MT5 credentials JSON
        """
        self.demo_only = demo_only
        self.log_dir = log_dir or PROJECT_ROOT / "logs"
        self.credentials_path = credentials_path
        
        # Ensure log directory exists
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Setup logging
        self._setup_logging()
        
        # State
        self.state = MonitorState.INITIALIZING
        self.running = False
        self.stats = MonitorStats()
        
        # Components (initialized in start())
        self.connector: Optional[MT5Connector] = None
        self.data_provider: Optional[DataProvider] = None
        
        # Executors by config name (one per config for correct magic numbers)
        self.executors: Dict[str, OrderExecutor] = {}
        
        # Checkers by config name
        self.checkers: Dict[str, BaseChecker] = {}
        
        # Symbols to fetch data for
        self.active_symbols: Dict[str, List[str]] = {}  # symbol -> [config_names]
        
        # Trade log file (JSON lines format)
        self.trade_log_path = self.log_dir / f"trades_multi_{datetime.now().strftime('%Y%m%d')}.jsonl"
    
    def _setup_logging(self):
        """Configure logging with file and console handlers using broker time."""
        self.logger = logging.getLogger("MultiMonitor")
        self.logger.setLevel(logging.DEBUG)
        
        # Avoid duplicate handlers
        if self.logger.handlers:
            return
        
        # Console handler (broker time)
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        console.setFormatter(BrokerTimeFormatter(
            "%(asctime)s | %(levelname)-7s | %(message)s",
            datefmt="%H:%M:%S"
        ))
        self.logger.addHandler(console)
        
        # File handler (detailed, broker time)
        log_file = self.log_dir / f"monitor_multi_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(BrokerTimeFormatter(
            "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
        ))
        self.logger.addHandler(file_handler)
    
    def _log_event(self, event_type: str, data: Dict[str, Any]):
        """Log event in JSON format for analysis."""
        event = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            **data
        }
        
        with open(self.trade_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
    
    def _initialize_checkers(self) -> bool:
        """
        Initialize checker instances for enabled configs.
        
        Returns:
            True if at least one checker initialized
        """
        enabled_count = 0
        
        for config_name, enabled in ENABLED_CONFIGS.items():
            if not enabled:
                self.logger.debug(f"[{config_name}] Disabled, skipping")
                continue
            
            if config_name not in STRATEGIES_CONFIG:
                self.logger.warning(f"[{config_name}] Config not found in STRATEGIES_CONFIG")
                continue
            
            if config_name not in STRATEGY_TYPES:
                self.logger.warning(f"[{config_name}] No STRATEGY_TYPES mapping")
                continue
            
            strategy_type = STRATEGY_TYPES[config_name]
            config = STRATEGIES_CONFIG[config_name]
            
            # Get symbol
            symbol = config.get("asset_name") or config.get("symbol")
            if not symbol:
                self.logger.warning(f"[{config_name}] No symbol defined")
                continue
            
            # Get params (merge config params with EMA period mappings for KOI)
            params = config.get("params", {})
            if strategy_type == "KOI":
                # Map EMA period names for KOI checker
                params = {
                    **params,
                    "ema_period_1": params.get("ema_1_period", 10),
                    "ema_period_2": params.get("ema_2_period", 20),
                    "ema_period_3": params.get("ema_3_period", 40),
                    "ema_period_4": params.get("ema_4_period", 80),
                    "ema_period_5": params.get("ema_5_period", 120),
                }
            
            try:
                # Create checker
                checker = get_checker(
                    strategy_name=strategy_type,
                    config_name=config_name,
                    params=params,
                    logger=self.logger
                )
                self.checkers[config_name] = checker
                
                # Create executor for this config
                executor = OrderExecutor(
                    connector=self.connector,
                    config_name=config_name,
                    logger=self.logger
                )
                self.executors[config_name] = executor
                
                # Track symbols
                if symbol not in self.active_symbols:
                    self.active_symbols[symbol] = []
                self.active_symbols[symbol].append(config_name)
                
                enabled_count += 1
                self.logger.info(
                    f"[OK] {config_name}: {strategy_type} on {symbol}"
                )
                
            except Exception as e:
                self.logger.error(f"[{config_name}] Failed to create checker/executor: {e}")
        
        if enabled_count == 0:
            self.logger.error("No checkers initialized!")
            return False
        
        self.logger.info(f"Initialized {enabled_count} checkers")
        self.logger.info(f"Active symbols: {list(self.active_symbols.keys())}")
        
        return True
    
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
            self.data_provider = DataProvider(connector=self.connector)
            
            # 3. Checkers and Executors (one executor per config)
            self.logger.info("Initializing checkers and executors...")
            if not self._initialize_checkers():
                return False
            
            self.logger.info("[OK] All components initialized")
            return True
            
        except Exception as e:
            self.logger.error(f"Component initialization failed: {e}")
            self._log_event("ERROR", {"error": str(e), "phase": "initialization"})
            return False
    
    def _check_connection(self) -> bool:
        """Check and repair MT5 connection if needed."""
        if self.connector is None:
            return False
        
        if self.connector.is_connected():
            return True
        
        # Attempt reconnection
        self.logger.warning("Connection lost, attempting reconnect...")
        self._log_event("CONNECTION", {"status": "lost"})
        
        for attempt in range(MAX_RECONNECT_ATTEMPTS):
            if self.connector.connect():
                self.logger.info(f"Reconnected on attempt {attempt + 1}")
                self._log_event("CONNECTION", {"status": "reconnected", "attempt": attempt + 1})
                return True
            
            self.logger.warning(f"Reconnect attempt {attempt + 1} failed")
            time.sleep(RECONNECT_DELAY_SECONDS)
        
        self.logger.error("Failed to reconnect after max attempts")
        self._log_event("ERROR", {"error": "reconnection_failed"})
        return False
    
    def _wait_for_candle_close(self) -> bool:
        """
        Wait until next candle close.
        
        Returns:
            True if candle closed, False if interrupted or connection lost
        """
        from .timezone import get_broker_utc_offset
        
        now = datetime.now()
        
        # Calculate seconds until next candle close
        seconds_in_candle = (now.minute % 5) * 60 + now.second
        seconds_to_wait = self.CANDLE_SECONDS - seconds_in_candle
        
        if seconds_to_wait <= 0:
            seconds_to_wait = self.CANDLE_SECONDS
        
        # Add buffer for data availability
        seconds_to_wait += CANDLE_CLOSE_BUFFER_SECONDS
        
        # Calculate next candle time in broker timezone for display
        next_candle_local = now + timedelta(seconds=seconds_to_wait)
        broker_offset = get_broker_utc_offset()
        # Local to UTC to Broker: UTC = local - local_offset, Broker = UTC + broker_offset
        next_candle_utc = datetime.utcnow() + timedelta(seconds=seconds_to_wait)
        next_candle_broker = next_candle_utc + timedelta(hours=broker_offset)
        
        self.logger.info(
            f"Waiting {seconds_to_wait}s until candle close "
            f"(~{next_candle_broker.strftime('%H:%M:%S')})"
        )
        
        self.state = MonitorState.WAITING_CANDLE
        
        # Wait in chunks for responsiveness
        try:
            while seconds_to_wait > 0 and self.running:
                sleep_time = min(seconds_to_wait, 10)  # Check every 10s
                time.sleep(sleep_time)
                seconds_to_wait -= sleep_time
                
                # Periodic connection check
                if not self._check_connection():
                    self.logger.warning("Connection lost during wait")
                    return False
        except Exception as e:
            self.logger.error(f"Error during candle wait: {e}")
            return False
        
        return self.running
    
    def _process_candle(self):
        """
        Process the closed candle for all active checkers.
        """
        self.state = MonitorState.CHECKING_SIGNALS
        
        # Fetch data for each symbol once
        symbol_data: Dict[str, Any] = {}
        
        for symbol in self.active_symbols:
            try:
                bars = self.data_provider.get_bars(
                    symbol=symbol,
                    timeframe=Timeframe.M5,
                    count=200  # Extra for indicators
                )
                
                if bars.empty:
                    self.logger.warning(f"No data for {symbol}")
                    continue
                
                symbol_data[symbol] = bars
                
            except Exception as e:
                self.logger.error(f"Failed to fetch data for {symbol}: {e}")
        
        if not symbol_data:
            self.logger.warning("No data fetched for any symbol")
            return
        
        self.stats.candles_processed += 1
        self.stats.last_candle_time = datetime.now()
        
        # Check each checker
        for config_name, checker in self.checkers.items():
            config = STRATEGIES_CONFIG.get(config_name, {})
            symbol = config.get("asset_name") or config.get("symbol")
            
            if symbol not in symbol_data:
                continue
            
            bars = symbol_data[symbol]
            
            try:
                self._check_and_execute(config_name, checker, symbol, bars)
            except Exception as e:
                self.stats.errors_count += 1
                self.logger.error(f"[{config_name}] Error: {e}")
                self._log_event("ERROR", {
                    "config": config_name,
                    "error": str(e),
                    "phase": "check_and_execute"
                })
    
    def _check_and_execute(
        self,
        config_name: str,
        checker: BaseChecker,
        symbol: str,
        bars: Any
    ):
        """
        Check signal and execute if valid.
        
        Args:
            config_name: Configuration name
            checker: Strategy checker instance
            symbol: Trading symbol
            bars: OHLCV DataFrame
        """
        # Check for signal
        signal = checker.check_signal(bars)
        
        if not signal.valid:
            self.logger.debug(f"[{config_name}] No signal: {signal.reason}")
            return
        
        # Signal detected!
        self.stats.signals_detected += 1
        self.stats.signals_by_strategy[config_name] = (
            self.stats.signals_by_strategy.get(config_name, 0) + 1
        )
        
        entry_str = f"{signal.entry_price:.5f}" if signal.entry_price else "N/A"
        self.logger.info(
            f"[{config_name}] SIGNAL: {signal.direction.value} @ {entry_str}"
        )
        
        self._log_event("SIGNAL", {
            "config": config_name,
            "symbol": symbol,
            "strategy": checker.strategy_name,
            **signal.to_dict()
        })
        
        # Get executor for this config
        executor = self.executors.get(config_name)
        if executor is None:
            self.logger.error(f"[{config_name}] No executor found")
            return
        
        # Check if we can execute
        if not executor.can_open_position(symbol):
            self.logger.info(f"[{config_name}] Position already open on {symbol}")
            return
        
        # Only LONG for now (both strategies are long-only)
        if signal.direction != SignalDirection.LONG:
            self.logger.debug(f"[{config_name}] Non-LONG signal ignored")
            return
        
        # Execute
        self.state = MonitorState.EXECUTING
        
        result = executor.execute_long(
            symbol=symbol,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            comment=config_name
        )
        
        if result.success:
            self.stats.trades_executed += 1
            self.stats.trades_by_strategy[config_name] = (
                self.stats.trades_by_strategy.get(config_name, 0) + 1
            )
            
            self.logger.info(
                f"[{config_name}] EXECUTED: {symbol} @ {result.executed_price:.5f}"
            )
            
            self._log_event("TRADE", {
                "config": config_name,
                "symbol": symbol,
                "strategy": checker.strategy_name,
                "direction": "LONG",
                "entry": result.executed_price,
                "volume": result.executed_volume,
                "sl": signal.stop_loss,
                "tp": signal.take_profit,
                "ticket": result.order_ticket,
            })
        else:
            self.logger.warning(f"[{config_name}] Execution failed: {result.message}")
            self._log_event("EXECUTION_FAILED", {
                "config": config_name,
                "reason": result.message,
                "signal": signal.to_dict()
            })
    
    def start(self) -> bool:
        """
        Start the monitor.
        
        Returns:
            True if started successfully
        """
        self.logger.info("=" * 60)
        self.logger.info("Starting Multi-Strategy Trading Monitor")
        self.logger.info(f"Demo Only: {self.demo_only}")
        self.logger.info("=" * 60)
        
        # Show enabled configs
        enabled = [k for k, v in ENABLED_CONFIGS.items() if v]
        self.logger.info(f"Enabled configs: {enabled}")
        
        # Retry initialization with backoff
        for attempt in range(MAX_RECONNECT_ATTEMPTS):
            if self._initialize_components():
                self.running = True
                self.state = MonitorState.RUNNING
                
                # Log start event
                self._log_event("MONITOR_START", {
                    "demo_only": self.demo_only,
                    "account": self.connector.account.login if self.connector.account else None,
                    "enabled_configs": enabled,
                })
                
                return True
            
            if attempt < MAX_RECONNECT_ATTEMPTS - 1:
                wait_time = RECONNECT_DELAY_SECONDS * (attempt + 1)
                self.logger.warning(
                    f"Initialization failed (attempt {attempt + 1}/{MAX_RECONNECT_ATTEMPTS}), "
                    f"retrying in {wait_time}s..."
                )
                time.sleep(wait_time)
        
        self.logger.error(f"Failed to initialize after {MAX_RECONNECT_ATTEMPTS} attempts")
        self.state = MonitorState.ERROR
        return False
    
    def stop(self):
        """Stop the monitor gracefully."""
        self.logger.info("Stopping monitor...")
        self.running = False
        self.state = MonitorState.STOPPED
        
        # Log stats
        self._log_event("MONITOR_STOP", self.stats.to_dict())
        
        # Disconnect
        if self.connector:
            self.connector.disconnect()
        
        self.logger.info("Monitor stopped")
        self.logger.info(f"Stats: {json.dumps(self.stats.to_dict(), indent=2)}")
    
    def run(self):
        """
        Main trading loop. Runs until interrupted.
        
        Implements robust error handling with automatic recovery:
        - Connection loss triggers reconnection attempts
        - Individual iteration failures don't crash the bot
        - All errors are logged for debugging
        """
        if not self.running:
            if not self.start():
                return
        
        self.logger.info("Entering main trading loop")
        
        consecutive_errors = 0
        max_consecutive_errors = 5
        
        try:
            while self.running:
                try:
                    # Check connection before each cycle
                    if not self._check_connection():
                        self.logger.error("Connection check failed, will retry next cycle")
                        consecutive_errors += 1
                        if consecutive_errors >= max_consecutive_errors:
                            self.logger.error(f"Too many consecutive errors ({consecutive_errors}), stopping")
                            break
                        time.sleep(RECONNECT_DELAY_SECONDS)
                        continue
                    
                    # Wait for next candle close
                    if not self._wait_for_candle_close():
                        if not self.running:
                            break
                        # Connection lost during wait
                        self.logger.warning("Candle wait interrupted, checking connection...")
                        consecutive_errors += 1
                        continue
                    
                    # Process the closed candle
                    self._process_candle()
                    
                    # Reset error counter on success
                    consecutive_errors = 0
                    
                    # Brief pause before next cycle
                    time.sleep(1)
                    
                except Exception as e:
                    consecutive_errors += 1
                    self.logger.error(f"Error in main loop iteration: {e}")
                    self._log_event("ITERATION_ERROR", {
                        "error": str(e),
                        "consecutive_errors": consecutive_errors
                    })
                    
                    if consecutive_errors >= max_consecutive_errors:
                        self.logger.error(f"Too many consecutive errors ({consecutive_errors}), stopping")
                        break
                    
                    # Wait before retry
                    time.sleep(RECONNECT_DELAY_SECONDS)
                
        except KeyboardInterrupt:
            self.logger.info("Keyboard interrupt received")
        except Exception as e:
            self.logger.error(f"Fatal error in main loop: {e}")
            self._log_event("FATAL_ERROR", {"error": str(e)})
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


def setup_signal_handlers(monitor: MultiStrategyMonitor):
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
    
    parser = argparse.ArgumentParser(description="Multi-Strategy Trading Monitor")
    parser.add_argument("--demo-only", action="store_true", default=True, help="Demo only mode")
    parser.add_argument("--single", action="store_true", help="Run single iteration")
    
    args = parser.parse_args()
    
    monitor = MultiStrategyMonitor(demo_only=args.demo_only)
    
    setup_signal_handlers(monitor)
    
    if args.single:
        monitor.run_single_iteration()
    else:
        monitor.run()
