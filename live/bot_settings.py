"""
Live Bot Settings - Pure Configuration Values
=============================================

Only values here, no code. Functions go in separate modules.
"""

# =============================================================================
# ENABLED STRATEGIES AND SYMBOLS
# =============================================================================
# Use this to enable/disable strategies and symbols for testing.
# Key = config name from config/settings.py
# Value = True (enabled) or False (disabled)

ENABLED_CONFIGS = {
    # Sunset Ogle strategy
    "EURUSD_PRO": True,
    "EURJPY_PRO": False,
    "USDCAD_PRO": False,
    "USDCHF_PRO": False,
    "USDJPY_PRO": False,
    
    # KOI strategy
    "EURUSD_KOI": True,
    "DIA_KOI": False,
    "TLT_KOI": False,
}

# Strategy type mapping (which checker class to use)
STRATEGY_TYPES = {
    "EURUSD_PRO": "SunsetOgle",
    "EURJPY_PRO": "SunsetOgle",
    "USDCAD_PRO": "SunsetOgle",
    "USDCHF_PRO": "SunsetOgle",
    "USDJPY_PRO": "SunsetOgle",
    "EURUSD_KOI": "KOI",
    "DIA_KOI": "KOI",
    "TLT_KOI": "KOI",
}


# =============================================================================
# BROKER TIMEZONE
# =============================================================================

# Current broker UTC offset (hours)
# - Darwinex/ICMarkets: UTC+2 (winter) / UTC+3 (summer)
# - OANDA: UTC+0
BROKER_UTC_OFFSET = 3

# Does broker follow EET daylight saving time?
BROKER_FOLLOWS_DST = True


# =============================================================================
# CONNECTION
# =============================================================================

# MT5 initialization timeout (milliseconds) - 2 minutes to allow manual login
MT5_INIT_TIMEOUT_MS = 120000

# MT5 login timeout (milliseconds)
MT5_LOGIN_TIMEOUT_MS = 60000

MAX_RECONNECT_ATTEMPTS = 5
RECONNECT_DELAY_SECONDS = 30
HEALTH_CHECK_INTERVAL = 60


# =============================================================================
# TRADING LOOP
# =============================================================================

CANDLE_CLOSE_BUFFER_SECONDS = 2
MIN_TRADE_INTERVAL_SECONDS = 300


# =============================================================================
# LOGGING
# =============================================================================

LOG_LEVEL = "INFO"
LOG_SIGNAL_DETAILS = True
LOG_STATE_TRANSITIONS = True
LOG_MAX_SIZE_MB = 10
LOG_BACKUP_COUNT = 5


# =============================================================================
# SAFETY
# =============================================================================

DEMO_ONLY = True
MAX_POSITION_SIZE_LOTS = 1.0
MAX_DAILY_TRADES = 0
EMERGENCY_STOP = False
