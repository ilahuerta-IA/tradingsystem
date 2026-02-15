"""
Timezone utilities for live trading.

Handles broker timezone conversions to align with UTC-based backtesting data.

ARCHITECTURE:
  - Dukascopy CSV data (backtest): timestamps in UTC
  - MT5 copy_rates_from_pos (live): timestamps in BROKER TIME (UTC+2/+3)
  - allowed_hours/allowed_days in settings.py: optimized on UTC data
  - Live checkers: convert broker_time → UTC before applying filters

USAGE IN CHECKERS:
  broker_time = df["time"].iloc[-1]    # ⚠️ NEVER df.index[-1] (it's an integer!)
  utc_time = broker_to_utc(broker_time) # Subtracts offset
  # Apply filters on utc_time.hour / utc_time.weekday()
"""

from datetime import datetime, timedelta

from .bot_settings import BROKER_UTC_OFFSET, BROKER_FOLLOWS_DST


def get_broker_utc_offset() -> int:
    """
    Get current broker UTC offset, accounting for DST if configured.
    
    Returns:
        UTC offset in hours (e.g., 3 for UTC+3)
    """
    if not BROKER_FOLLOWS_DST:
        return BROKER_UTC_OFFSET
    
    now = datetime.now()
    
    # Last Sunday of March (start of summer time)
    march_last = datetime(now.year, 3, 31)
    while march_last.weekday() != 6:
        march_last -= timedelta(days=1)
    
    # Last Sunday of October (end of summer time)
    october_last = datetime(now.year, 10, 31)
    while october_last.weekday() != 6:
        october_last -= timedelta(days=1)
    
    if march_last <= now.replace(tzinfo=None) < october_last:
        return 3  # Summer: UTC+3
    else:
        return 2  # Winter: UTC+2


def broker_to_utc(broker_dt: datetime) -> datetime:
    """
    Convert broker datetime to UTC.
    
    Args:
        broker_dt: Datetime in broker timezone
        
    Returns:
        Datetime in UTC
    """
    offset = get_broker_utc_offset()
    return broker_dt - timedelta(hours=offset)


def utc_to_broker(utc_dt: datetime) -> datetime:
    """
    Convert UTC datetime to broker time.
    
    Args:
        utc_dt: Datetime in UTC
        
    Returns:
        Datetime in broker timezone
    """
    offset = get_broker_utc_offset()
    return utc_dt + timedelta(hours=offset)
