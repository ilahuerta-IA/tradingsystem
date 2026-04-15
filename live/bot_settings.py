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
    "EURUSD_PRO": False,  # PAUSED 2026-04-05: M5 phase closed, transitioning to H4
    "EURJPY_PRO": False,  # PAUSED 2026-04-05: M5 phase closed, transitioning to H4
    "USDCAD_PRO": False,  # Disabled: high spread/slippage destroys edge
    "USDCHF_PRO": False,  # PAUSED 2026-04-05: M5 phase closed, transitioning to H4
    "USDJPY_PRO": False,  # PAUSED 2026-02-28: 1/11 WR in OOS (p=1.6%). Re-evaluate Jun 2026
    
    # KOI strategy (Forex)
    "EURUSD_KOI": False,  # PAUSED 2026-04-05: M5 phase closed, transitioning to H4
    "USDCAD_KOI": False,  # Disabled: high spread/slippage destroys edge
    "USDCHF_KOI": False,  # PAUSED 2026-04-05: M5 phase closed, transitioning to H4
    "USDJPY_KOI": False,  # PAUSED 2026-04-05: M5 phase closed, transitioning to H4
    "EURJPY_KOI": False,  # PAUSED 2026-04-05: M5 phase closed, transitioning to H4
    
    # SEDNA strategy (Forex - JPY pairs)
    "USDJPY_SEDNA": False,  # PAUSED 2026-04-05: M5 phase closed, transitioning to H4
    "EURJPY_SEDNA": False,  # PAUSED 2026-04-05: M5 phase closed, transitioning to H4
    
    # GEMINI strategy (correlation divergence EURUSD/USDCHF)
    "EURUSD_GEMINI": False,  # PAUSED 2026-04-05: M5 phase closed, transitioning to H4
    "USDCHF_GEMINI": False,  # PAUSED 2026-04-05: M5 phase closed, transitioning to H4
    
    # KOI strategy (ETFs) - disabled until broker availability confirmed
    "DIA_KOI": False,
    "TLT_KOI": False,
    
    # SEDNA strategy (ETFs) - disabled until broker availability confirmed
    "DIA_SEDNA": False,

    # VEGA strategy (Cross-Index Z-Score Divergence, H4)
    # Deployed 2026-04-05: transitioning from M5 to H4 structural approach
    "NI225_VEGA": True,   # SP500→JPN225, London session, LONG only
    "GDAXI_VEGA": False,  # DISABLED 2026-04-11: 73% overlap with NDAXI, worse PF(1.28 vs 1.31)/DD(15% vs 14%)
    "NDAXI_VEGA": True,   # NAS100→GER40, London session, LONG+SHORT
    # ALTAIR strategy (Trend-Following Momentum, Miner DTOSC, CFD stocks)
    # Deployed 2026-04-15: live demo, ENABLED=False until integration tested
    # TF Live per ticker: 15m (NVDA, GOOGL), 30m (JPM), H1 (V, ALB, WDC)
    "JPM_ALTAIR":   False,  # 30m, Config B (os=20, max_sl=4.0), PF 1.57
    "NVDA_ALTAIR":  False,  # 15m, Config A (os=25, max_sl=2.0), PF 1.97
    "GOOGL_ALTAIR": False,  # 15m, Config A (os=25, max_sl=2.0), PF 1.58
    "V_ALTAIR":     False,  # H1,  Config B (os=20, max_sl=4.0), PF 1.84
    "ALB_ALTAIR":   False,  # H1,  Config B (os=20, max_sl=4.0), PF 2.15
    "WDC_ALTAIR":   False,  # H1,  Config B (os=20, max_sl=4.0), PF 1.17
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
    # VEGA
    "NI225_VEGA": "VEGA",
    "GDAXI_VEGA": "VEGA",
    "NDAXI_VEGA": "VEGA",
    # ALTAIR (CFD stocks, single-feed, LONG only)
    "JPM_ALTAIR":   "ALTAIR",
    "NVDA_ALTAIR":  "ALTAIR",
    "GOOGL_ALTAIR": "ALTAIR",
    "V_ALTAIR":     "ALTAIR",
    "ALB_ALTAIR":   "ALTAIR",
    "WDC_ALTAIR":   "ALTAIR",
}


# =============================================================================
# SYMBOL MAPPING (BT name → broker name)
# =============================================================================
# CFD index symbol names differ between BT data (Dukascopy) and broker (FOREX.comGLOBAL).
# Forex pairs (EURUSD, etc.) are identical and don't need mapping.

SYMBOL_MAP = {
    "SP500": "SPX500",
    "GDAXI": "GER40",
    "NI225": "JPN225",
    "NDX": "NAS100",
}

# VEGA configs trade the reference_symbol, not asset_name.
# This set identifies configs where the executor uses reference_symbol for orders.
VEGA_CONFIGS = {"NI225_VEGA", "GDAXI_VEGA", "NDAXI_VEGA"}

# ALTAIR configs: single-feed CFD stocks with per-ticker TF.
# The checker reads params from config/settings_altair.py (ALTAIR_STRATEGIES_CONFIG).
ALTAIR_CONFIGS = {"JPM_ALTAIR", "NVDA_ALTAIR", "GOOGL_ALTAIR", "V_ALTAIR", "ALB_ALTAIR", "WDC_ALTAIR"}

# ALTAIR per-ticker live timeframe (minutes) and bars_per_day scaling.
# M5 base loop resamples to these TFs. bars_per_day scales D1 regime periods.
# H1=7 bpd (6.5h session / 1h), 30m=13 bpd, 15m=26 bpd.
ALTAIR_LIVE_TF = {
    "JPM_ALTAIR":   {"timeframe_minutes": 30, "bars_per_day": 13},   # 30m
    "NVDA_ALTAIR":  {"timeframe_minutes": 15, "bars_per_day": 26},   # 15m
    "GOOGL_ALTAIR": {"timeframe_minutes": 15, "bars_per_day": 26},   # 15m
    "V_ALTAIR":     {"timeframe_minutes": 60, "bars_per_day": 7},    # H1
    "ALB_ALTAIR":   {"timeframe_minutes": 60, "bars_per_day": 7},    # H1
    "WDC_ALTAIR":   {"timeframe_minutes": 60, "bars_per_day": 7},    # H1
}


# =============================================================================
# BROKER TIMEZONE
# =============================================================================
# 
# UTC ARCHITECTURE -- READ THIS BEFORE TOUCHING ANY TIME/DAY FILTER
#
# Data flow:
#   1. MT5 copy_rates_from_pos() -> timestamps in BROKER TIME (UTC+2 winter / UTC+3 summer)
#   2. data_provider.get_bars() -> DataFrame with "time" column = broker time, index = int (0..N)
#   3. Checkers: broker_time = df["time"].iloc[-1]  (WARNING: NEVER use df.index[-1], it's an integer!)
#   4. broker_to_utc(broker_time) -> subtracts BROKER_UTC_OFFSET hours -> UTC
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

# Broker UTC offset -- WINTER BASE only.
# Actual offset is computed automatically by get_broker_utc_offset() in timezone.py:
#   BROKER_FOLLOWS_DST=True -> March-October = base+1 (summer), rest = base (winter).
# Do NOT change this value seasonally; DST is automatic.
# - FOREX.comGLOBAL: base=2 (winter UTC+2, summer UTC+3)
# - OANDA: base=0
BROKER_UTC_OFFSET = 2

# Does broker follow EET daylight saving time?
# If True: March last Sunday -> October last Sunday = UTC+3 (summer)
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
# RISK OVERRIDES (live position sizing)
# =============================================================================
# Tiered risk_percent per config for live trading.
# Overrides the 1% default in config/settings.py.
# Executor reads from here first; falls back to settings.py params if missing.
#
# Tiers (from portfolio walk-forward validation):
#   A = 1.50%  (best risk-adjusted returns)
#   B = 1.00%  (strong performers)
#   C = 0.75%  (solid but moderate)
#   D = 0.50%  (weaker edge, conservative)

RISK_OVERRIDES = {
    # VEGA -- 0.35% uniform (margin-allocation sizing, not SL-based)
    # Note: VEGA checker uses its own sizing (capital_alloc_pct), not executor's SL formula.
    # These are here for documentation; actual sizing is in VEGAChecker.calculate_vega_lots().
    "NI225_VEGA":    0.0035,
    "GDAXI_VEGA":    0.0035,
    "NDAXI_VEGA":    0.0035,
    # Tier A -- 1.50%
    "USDCHF_PRO":    0.015,
    "USDCHF_GEMINI": 0.015,
    # Tier B -- 1.00%
    "EURUSD_PRO":    0.010,
    "USDCHF_KOI":    0.010,
    "EURJPY_PRO":    0.010,
    # Tier C -- 0.75%
    "EURUSD_KOI":    0.0075,
    "EURJPY_KOI":    0.0075,
    "USDJPY_KOI":    0.0075,
    "USDJPY_SEDNA":  0.0075,
    "USDJPY_PRO":    0.0075,
    "EURUSD_GEMINI": 0.0075,
    # Tier D -- 0.50%
    "EURJPY_SEDNA":  0.005,
}


# =============================================================================
# SAFETY
# =============================================================================

DEMO_ONLY = True

# TODO: These safety caps are DEFINED but NOT YET enforced in executor.py.
# Currently the lot calculation and trade frequency are self-limiting
# (low signal volume ~3-4 trades/week, risk_percent controls lot size).
# Wire these into executor.py before switching to real money:
#   - MAX_POSITION_SIZE_LOTS: clamp calculated lots to this maximum
#   - MAX_DAILY_TRADES: reject new trades if daily count reached (0 = unlimited)
MAX_POSITION_SIZE_LOTS = 1.0
MAX_DAILY_TRADES = 0
EMERGENCY_STOP = False
