"""
Base Signal Checker - Abstract interface for all strategy checkers.

All strategy checkers must inherit from this class and implement:
- check_signal(df) -> Signal
- reset_state()
- get_state_info() -> dict

This ensures consistent interface across strategies for the monitor.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

import pandas as pd


class SignalDirection(Enum):
    """Signal direction."""
    LONG = "LONG"
    SHORT = "SHORT"
    NONE = "NONE"


@dataclass
class Signal:
    """Trading signal container."""
    valid: bool
    direction: SignalDirection
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    atr: Optional[float] = None
    reason: str = ""
    timestamp: Optional[datetime] = None
    strategy_name: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "valid": self.valid,
            "direction": self.direction.value,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "atr": self.atr,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "strategy_name": self.strategy_name,
        }


class BaseChecker(ABC):
    """
    Abstract base class for strategy signal checkers.
    
    Each strategy implements its own checker that:
    1. Maintains internal state machine
    2. Processes OHLCV data to detect signals
    3. Returns Signal objects with entry/SL/TP levels
    
    All checkers share:
    - Same Signal output format
    - Same logging interface
    - Same state inspection methods
    """
    
    def __init__(
        self,
        config_name: str,
        params: Dict[str, Any],
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize checker.
        
        Args:
            config_name: Configuration key (e.g., 'EURUSD_PRO')
            params: Strategy parameters from config/settings.py
            logger: Optional logger instance
        """
        self.config_name = config_name
        self.params = params
        self.logger = logger or logging.getLogger(f"Checker.{config_name}")
        self.current_bar_index = 0
        
    @property
    @abstractmethod
    def strategy_name(self) -> str:
        """Return strategy name for logging."""
        pass
    
    @abstractmethod
    def check_signal(self, df: pd.DataFrame) -> Signal:
        """
        Check for trading signal.
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            Signal object (valid=True if signal detected)
        """
        pass
    
    @abstractmethod
    def reset_state(self) -> None:
        """Reset state machine to initial state."""
        pass
    
    @abstractmethod
    def get_state_info(self) -> Dict[str, Any]:
        """Get current state machine info for logging."""
        pass
    
    def _log_state_transition(self, from_state: str, to_state: str, reason: str = ""):
        """Log state machine transition."""
        msg = f"[{self.config_name}] {from_state} -> {to_state}"
        if reason:
            msg += f" | {reason}"
        self.logger.info(msg)
    
    def _log_signal_check(self, reason: str):
        """Log signal check result (debug level)."""
        self.logger.debug(f"[{self.config_name}] No signal: {reason}")
    
    def _create_no_signal(self, reason: str) -> Signal:
        """Helper to create a no-signal response."""
        return Signal(
            valid=False,
            direction=SignalDirection.NONE,
            reason=reason,
            timestamp=datetime.now(),
            strategy_name=self.strategy_name,
        )
    
    def _create_signal(
        self,
        direction: SignalDirection,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        atr: float,
        reason: str = "Signal confirmed"
    ) -> Signal:
        """Helper to create a valid signal."""
        return Signal(
            valid=True,
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            atr=atr,
            reason=reason,
            timestamp=datetime.now(),
            strategy_name=self.strategy_name,
        )
