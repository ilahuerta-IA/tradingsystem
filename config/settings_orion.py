"""ORION GUI asset configuration (single source of truth).

Defines the assets shown in the ORION GEX GUI ticker selector. Each entry
maps a yfinance symbol (the GEX / options-chain source) to the broker's
MT5 symbol name (live spot + order routing). Toggle ``active`` to add or
remove an asset from the GUI without touching any code.

Lot sizing is identical across US equities at the broker, so only the
names differ between yfinance and MT5; that is all this table encodes.

Fields:
    yf:     yfinance ticker (options chain + reference price source).
    mt5:    MT5 broker symbol name (live spot + order routing).
    role:   'core'    -> tradeable underlying (listed first in selector).
            'context' -> macro overlay / index proxy (regime read only).
    ratio:  price ratio that converts the MT5 quote into the yfinance
            underlying coordinate system. 1.0 for cash equities (MT5
            quotes the share directly). Use a fraction when the broker
            quotes a different instrument (e.g. an index CFD):
              SPY = SPX500 / 10     (exact, US convention)
              QQQ ~ NAS100 / 41.1   (approx, drifts ~0.5%/yr)
    active: include in the GUI selector when True.

ASCII-only (project axiom 4). MT5 names verified against the broker's
symbol list (2026-06-02).
"""

ORION_ASSETS = [
    # --- Core tradeable equities (ratio 1.0: MT5 quotes the share) -----
    {"yf": "AAPL",  "mt5": "Apple",                         "role": "core",    "ratio": 1.0,        "active": True},
    {"yf": "TSLA",  "mt5": "Tesla Motors",                  "role": "core",    "ratio": 1.0,        "active": True},
    {"yf": "JPM",   "mt5": "J.P. Morgan",                   "role": "core",    "ratio": 1.0,        "active": True},
    {"yf": "META",  "mt5": "Meta Platforms Inc",            "role": "core",    "ratio": 1.0,        "active": True},
    {"yf": "NVDA",  "mt5": "Nvidia",                        "role": "core",    "ratio": 1.0,        "active": True},
    {"yf": "MU",    "mt5": "Micron",                        "role": "core",    "ratio": 1.0,        "active": True},
    {"yf": "AMD",   "mt5": "Advanced Micro Devices",        "role": "core",    "ratio": 1.0,        "active": True},
    {"yf": "AMZN",  "mt5": "Amazon",                        "role": "core",    "ratio": 1.0,        "active": True},
    {"yf": "INTC",  "mt5": "Intel",                         "role": "core",    "ratio": 1.0,        "active": True},
    {"yf": "GOOGL", "mt5": "Alphabet Inc A",                "role": "core",    "ratio": 1.0,        "active": True},
    {"yf": "NFLX",  "mt5": "Netflix",                       "role": "core",    "ratio": 1.0,        "active": True},
    {"yf": "MSFT",  "mt5": "Microsoft",                     "role": "core",    "ratio": 1.0,        "active": True},
    {"yf": "PLTR",  "mt5": "Palantir Tech Inc A",           "role": "core",    "ratio": 1.0,        "active": True},

    # --- Context overlays / index proxies (not direct trades) ----------
    {"yf": "XLK",   "mt5": "Technology Select Sector SPDR", "role": "context", "ratio": 1.0,        "active": True},
    {"yf": "SPY",   "mt5": "SPX500",                        "role": "context", "ratio": 1.0 / 10.0, "active": True},
    {"yf": "QQQ",   "mt5": "NAS100",                        "role": "context", "ratio": 1.0 / 41.1, "active": True},
]


def active_assets():
    """Return active asset entries, preserving declaration order."""
    return [a for a in ORION_ASSETS if a.get("active", True)]


def core_tickers():
    """Active yfinance tickers with role 'core' (tradeable)."""
    return [a["yf"] for a in active_assets() if a.get("role") == "core"]


def context_tickers():
    """Active yfinance tickers with role 'context' (overlay)."""
    return [a["yf"] for a in active_assets() if a.get("role") == "context"]


def all_tickers():
    """Active core tickers followed by active context tickers."""
    return core_tickers() + context_tickers()


def ticker_to_mt5():
    """Map yfinance ticker -> MT5 symbol for active assets."""
    return {a["yf"]: a["mt5"] for a in active_assets()}


def fixed_ratios():
    """Map yfinance ticker -> ratio for active entries where ratio != 1.0."""
    return {
        a["yf"]: a["ratio"]
        for a in active_assets()
        if a.get("ratio", 1.0) != 1.0
    }
