"""
Timezone utilities for live trading.

Handles broker timezone conversions to align with UTC-based backtesting data.
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
