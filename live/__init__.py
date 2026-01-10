"""
Live Trading Module for TradingSystem.

This module provides MT5 live trading capabilities while reusing
the existing lib/ filters and position sizing logic from backtesting.

Architecture (SOLID):
- connector.py: MT5 connection management (Single Responsibility)
- data_provider.py: Market data fetching (Single Responsibility)
- signal_checker.py: Signal detection using lib/filters (Open/Closed)
- executor.py: Order execution (Single Responsibility)
- monitor.py: Main orchestrator (Dependency Injection)

Usage:
    python run_live.py --config EURUSD_PRO
"""

__version__ = "0.1.0"

# Expose main classes for easy imports
from .connector import MT5Connector, AccountInfo, AccountType
from .data_provider import DataProvider, Timeframe, BarData
from .signal_checker import SignalChecker, Signal, SignalDirection, EntryState
from .executor import OrderExecutor, ExecutionResult, OrderResult
from .monitor import LiveTradingMonitor, MonitorState

__all__ = [
    # Connector
    'MT5Connector',
    'AccountInfo', 
    'AccountType',
    # Data Provider
    'DataProvider',
    'Timeframe',
    'BarData',
    # Signal Checker
    'SignalChecker',
    'Signal',
    'SignalDirection',
    'EntryState',
    # Executor
    'OrderExecutor',
    'ExecutionResult',
    'OrderResult',
    # Monitor
    'LiveTradingMonitor',
    'MonitorState',
]
