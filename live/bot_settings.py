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
    # Sunset Ogle strategy (Forex)
    "EURUSD_PRO": True,
    "EURJPY_PRO": True,
    "USDCAD_PRO": False,  # Disabled: high spread/slippage destroys edge
    "USDCHF_PRO": True,
    "USDJPY_PRO": True,
    
    # KOI strategy (Forex)
    "EURUSD_KOI": True,
    "USDCAD_KOI": False,  # Disabled: high spread/slippage destroys edge
    "USDCHF_KOI": True,
    "USDJPY_KOI": True,
    "EURJPY_KOI": True,
    
    # SEDNA strategy (Forex - JPY pairs)
    "USDJPY_SEDNA": True,
    "EURJPY_SEDNA": True,
    
    # GEMINI strategy (correlation divergence EURUSD/USDCHF)
    "EURUSD_GEMINI": True,
    "USDCHF_GEMINI": True,
    
    # KOI strategy (ETFs) - disabled until broker availability confirmed
    "DIA_KOI": False,
    "TLT_KOI": False,
    
    # SEDNA strategy (ETFs) - disabled until broker availability confirmed
    "DIA_SEDNA": False,
}

# Strategy type mapping (which checker class to use)
STRATEGY_TYPES = {
    # SunsetOgle
    "EURUSD_PRO": "SunsetOgle",
    "EURJPY_PRO": "SunsetOgle",
    "USDCAD_PRO": "SunsetOgle",
    "USDCHF_PRO": "SunsetOgle",
    "USDJPY_PRO": "SunsetOgle",
    # KOI
    "EURUSD_KOI": "KOI",
    "USDCAD_KOI": "KOI",
    "USDCHF_KOI": "KOI",
    "USDJPY_KOI": "KOI",
    "EURJPY_KOI": "KOI",
    "DIA_KOI": "KOI",
    "TLT_KOI": "KOI",
    # SEDNA
    "USDJPY_SEDNA": "SEDNA",
    "EURJPY_SEDNA": "SEDNA",
    "DIA_SEDNA": "SEDNA",
    # GEMINI
    "EURUSD_GEMINI": "GEMINI",
    "USDCHF_GEMINI": "GEMINI",
}


# =============================================================================
# BROKER TIMEZONE
# =============================================================================
# 
# UTC ARCHITECTURE — READ THIS BEFORE TOUCHING ANY TIME/DAY FILTER
#
# Data flow:
#   1. MT5 copy_rates_from_pos() → timestamps in BROKER TIME (UTC+2 winter / UTC+3 summer)
#   2. data_provider.get_bars() → DataFrame with "time" column = broker time, index = int (0..N)
#   3. Checkers: broker_time = df["time"].iloc[-1]  (⚠️ NEVER use df.index[-1], it's an integer!)
#   4. broker_to_utc(broker_time) → subtracts BROKER_UTC_OFFSET hours → UTC
#   5. Filters allowed_hours/allowed_days are applied on UTC (optimized on Dukascopy CSV data which is UTC)
#
# Rules:
#   - allowed_hours in settings.py = UTC HOURS (optimized on Dukascopy UTC data)
#   - allowed_days in settings.py = UTC DAYS (weekday() on UTC datetime)
#   - Checkers MUST use df["time"].iloc[-1], NEVER df.index[-1]
#   - broker_to_utc() uses BROKER_UTC_OFFSET below + automatic DST
#   - Logs show "Broker: HH:MM, UTC: HH:MM" for verification
#   - On first candle, multi_monitor logs UTC VALIDATION with real timestamps
#
# Historical bug (2026-02-15):
#   gemini_checker.py used df.index[-1] (integer 199) instead of df["time"].iloc[-1]
#   This produced broker_time = pd.Timestamp(199) = 1970-01-01 00:00:00
#   And utc_time.hour = 22 always, regardless of actual time.
#   Did not affect trades because use_time_filter=False in v0.5.2 for GEMINI.
#   Fixed in v0.5.3.
#

# Current broker UTC offset (hours)
# - FOREX.comGLOBAL: UTC+2 (winter) / UTC+3 (summer)
# - OANDA: UTC+0
BROKER_UTC_OFFSET = 2

# Does broker follow EET daylight saving time?
# If True: March last Sunday → October last Sunday = UTC+3 (summer)
#          Rest of year = UTC+2 (winter)  
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
