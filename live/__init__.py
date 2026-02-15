"""
Live Trading Module for TradingSystem.

This module provides MT5 live trading capabilities while reusing
the existing lib/ filters and position sizing logic from backtesting.

Architecture (SOLID):
- connector.py: MT5 connection management
- data_provider.py: Market data fetching
- checkers/: Strategy-specific signal detection (BaseChecker pattern)
- executor.py: Order execution
- monitor.py: Single-strategy orchestrator
- multi_monitor.py: Multi-strategy orchestrator

Usage:
    # Single strategy (legacy)
    python run_live.py --config EURUSD_PRO
    
    # Multi-strategy (new)
    python -m live.multi_monitor
"""

__version__ = "0.5.3"

# Expose main classes for easy imports
from .connector import MT5Connector, AccountInfo, AccountType
from .data_provider import DataProvider, Timeframe, BarData
from .signal_checker import SignalChecker, Signal, SignalDirection, EntryState
from .executor import OrderExecutor, ExecutionResult, OrderResult
from .monitor import LiveTradingMonitor, MonitorState
from .multi_monitor import MultiStrategyMonitor

# Checkers
from .checkers import (
    BaseChecker,
    Signal as CheckerSignal,
    SignalDirection as CheckerSignalDirection,
    SunsetOgleChecker,
    KOIChecker,
    SEDNAChecker,
    CHECKER_REGISTRY,
)

__all__ = [
    # Connector
    "MT5Connector",
    "AccountInfo", 
    "AccountType",
    # Data Provider
    "DataProvider",
    "Timeframe",
    "BarData",
    # Signal Checker (legacy single-strategy)
    "SignalChecker",
    "Signal",
    "SignalDirection",
    "EntryState",
    # Executor
    "OrderExecutor",
    "ExecutionResult",
    "OrderResult",
    # Monitor (legacy single-strategy)
    "LiveTradingMonitor",
    "MonitorState",
    # Multi-Strategy Monitor (new)
    "MultiStrategyMonitor",
    # Checkers (new)
    "BaseChecker",
    "SunsetOgleChecker",
    "KOIChecker",
    "SEDNAChecker",
    "CHECKER_REGISTRY",
]
