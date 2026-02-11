"""
Signal checkers for live trading strategies.
"""

import logging
from typing import Optional

from .base_checker import BaseChecker, Signal, SignalDirection
from .sunset_ogle_checker import SunsetOgleChecker
from .koi_checker import KOIChecker
from .sedna_checker import SEDNAChecker
from .gliese_checker import GLIESEChecker
from .gemini_checker import GEMINIChecker

# Registry for dynamic instantiation
CHECKER_REGISTRY = {
    "SunsetOgle": SunsetOgleChecker,
    "KOI": KOIChecker,
    "SEDNA": SEDNAChecker,
    "GLIESE": GLIESEChecker,
    "GEMINI": GEMINIChecker,
    # "HELIX": HELIXChecker,  # In development - not ready for live
}


def get_checker(
    strategy_name: str,
    config_name: str,
    params: dict,
    logger: Optional[logging.Logger] = None,
) -> BaseChecker:
    """
    Factory function to get a checker instance.
    
    Args:
        strategy_name: Name of strategy ("SunsetOgle", "KOI", "SEDNA", "GLIESE")
        config_name: Configuration name (e.g., "EURUSD_H1")
        params: Strategy parameters dict
        logger: Optional logger instance
        
    Returns:
        Checker instance
        
    Raises:
        ValueError: If strategy_name not in registry
    """
    checker_class = CHECKER_REGISTRY.get(strategy_name)
    if checker_class is None:
        raise ValueError(
            f"Unknown strategy: {strategy_name}. "
            f"Available: {list(CHECKER_REGISTRY.keys())}"
        )
    return checker_class(config_name, params, logger)


__all__ = [
    "BaseChecker",
    "Signal", 
    "SignalDirection",
    "SunsetOgleChecker",
    "KOIChecker",
    "SEDNAChecker",
    "GLIESEChecker",
    "CHECKER_REGISTRY",
    "get_checker",
]
