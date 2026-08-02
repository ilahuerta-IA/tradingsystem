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
    {"yf": "AAPL",  "mt5": "Apple",                         "role": "core", "ratio": 1.0, "active": True},
    {"yf": "NVDA",  "mt5": "Nvidia",                        "role": "core", "ratio": 1.0, "active": True},
    {"yf": "GOOGL", "mt5": "Alphabet Inc A",                "role": "core", "ratio": 1.0, "active": True},
    {"yf": "MSFT",  "mt5": "Microsoft",                     "role": "core", "ratio": 1.0, "active": True},
    {"yf": "AMZN",  "mt5": "Amazon",                        "role": "core", "ratio": 1.0, "active": True},
    {"yf": "AVGO",  "mt5": "Broadcom Ltd",                  "role": "core", "ratio": 1.0, "active": True},
    {"yf": "META",  "mt5": "Meta Platforms Inc",            "role": "core", "ratio": 1.0, "active": True},
    {"yf": "TSLA",  "mt5": "Tesla Motors",                  "role": "core", "ratio": 1.0, "active": True},
    {"yf": "LLY",   "mt5": "Eli Lilly",                     "role": "core", "ratio": 1.0, "active": True},
    {"yf": "BRK.B", "mt5": "Berkshire Hathaway - Class B",  "role": "core", "ratio": 1.0, "active": True},
    {"yf": "MU",    "mt5": "Micron",                        "role": "core", "ratio": 1.0, "active": True},
    {"yf": "WMT",   "mt5": "Walmart",                       "role": "core", "ratio": 1.0, "active": True},
    {"yf": "AMD",   "mt5": "Advanced Micro Devices",        "role": "core", "ratio": 1.0, "active": True},
    {"yf": "V",     "mt5": "Visa",                          "role": "core", "ratio": 1.0, "active": True},
    {"yf": "JNJ",   "mt5": "Johnson & Johnson",             "role": "core", "ratio": 1.0, "active": True},
    {"yf": "MA",    "mt5": "Mastercard",                    "role": "core", "ratio": 1.0, "active": True},
    {"yf": "INTC",  "mt5": "Intel",                         "role": "core", "ratio": 1.0, "active": True},
    {"yf": "CSCO",  "mt5": "Cisco Systems",                 "role": "core", "ratio": 1.0, "active": True},
    {"yf": "BAC",   "mt5": "Bank Of America",               "role": "core", "ratio": 1.0, "active": True},
    {"yf": "COST",  "mt5": "Costco",                        "role": "core", "ratio": 1.0, "active": True},
    {"yf": "AMAT",  "mt5": "Applied Materials",             "role": "core", "ratio": 1.0, "active": True},
    {"yf": "CVX",   "mt5": "Chevron Corp",                  "role": "core", "ratio": 1.0, "active": True},
    {"yf": "CAT",   "mt5": "Caterpillar",                   "role": "core", "ratio": 1.0, "active": True},
    {"yf": "LRCX",  "mt5": "Lam Research Corp",             "role": "core", "ratio": 1.0, "active": True},
    {"yf": "ORCL",  "mt5": "Oracle",                        "role": "core", "ratio": 1.0, "active": True},
    {"yf": "HD",    "mt5": "Home Depot",                    "role": "core", "ratio": 1.0, "active": True},
    {"yf": "MS",    "mt5": "Morgan Stanley",                "role": "core", "ratio": 1.0, "active": True},
    {"yf": "MRK",   "mt5": "Merck and Co",                  "role": "core", "ratio": 1.0, "active": True},
    {"yf": "NFLX",  "mt5": "Netflix",                       "role": "core", "ratio": 1.0, "active": True},
    {"yf": "GS",    "mt5": "Goldman Sachs",                 "role": "core", "ratio": 1.0, "active": True},
    {"yf": "PLTR",  "mt5": "Palantir Tech Inc A",           "role": "core", "ratio": 1.0, "active": True},
    {"yf": "PANW",  "mt5": "Palo Alto Networks",            "role": "core", "ratio": 1.0, "active": True},
    {"yf": "DELL",  "mt5": "Dell Technologies",             "role": "core", "ratio": 1.0, "active": True},
    {"yf": "WFC",   "mt5": "Wells Fargo and Co",            "role": "core", "ratio": 1.0, "active": True},
    {"yf": "TXN",   "mt5": "Texas Instruments",             "role": "core", "ratio": 1.0, "active": True},
    {"yf": "LIN",   "mt5": "Linde Plc",                     "role": "core", "ratio": 1.0, "active": True},
    {"yf": "AXP",   "mt5": "American Express",              "role": "core", "ratio": 1.0, "active": True},
    {"yf": "C",     "mt5": "Citigroup",                     "role": "core", "ratio": 1.0, "active": True},
    {"yf": "ANET",  "mt5": "Arista Networks Inc",           "role": "core", "ratio": 1.0, "active": True},
    {"yf": "AMGN",  "mt5": "Amgen",                         "role": "core", "ratio": 1.0, "active": True},
    {"yf": "IBM",   "mt5": "IBM",                           "role": "core", "ratio": 1.0, "active": True},
    {"yf": "PEP",   "mt5": "PepsiCo",                       "role": "core", "ratio": 1.0, "active": True},
    {"yf": "MCD",   "mt5": "McDonald's",                    "role": "core", "ratio": 1.0, "active": True},
    {"yf": "TMUS",  "mt5": "T-Mobile US",                   "role": "core", "ratio": 1.0, "active": True},
    {"yf": "WDC",   "mt5": "Western Digital",               "role": "core", "ratio": 1.0, "active": True},
    {"yf": "ADI",   "mt5": "Analog Devices",                "role": "core", "ratio": 1.0, "active": True},
    {"yf": "TJX",   "mt5": "TJX Companies",                 "role": "core", "ratio": 1.0, "active": True},
    {"yf": "BA",    "mt5": "Boeing Co",                     "role": "core", "ratio": 1.0, "active": True},
    {"yf": "UNP",   "mt5": "Union Pacific",                 "role": "core", "ratio": 1.0, "active": True},
    {"yf": "DIS",   "mt5": "Walt Disney",                   "role": "core", "ratio": 1.0, "active": True},
    {"yf": "GILD",  "mt5": "Gilead Sciences",               "role": "core", "ratio": 1.0, "active": True},
    {"yf": "QCOM",  "mt5": "Qualcomm",                      "role": "core", "ratio": 1.0, "active": True},
    {"yf": "T",     "mt5": "AT&T",                          "role": "core", "ratio": 1.0, "active": True},
    {"yf": "IBKR",  "mt5": "Interactive Brokers Inc",       "role": "core", "ratio": 1.0, "active": True},
    {"yf": "BKNG",  "mt5": "Booking Holdings Inc",          "role": "core", "ratio": 1.0, "active": True},
    {"yf": "CRM",   "mt5": "Salesforce Inc",                "role": "core", "ratio": 1.0, "active": True},
    {"yf": "COP",   "mt5": "ConocoPhillips",                "role": "core", "ratio": 1.0, "active": True},
    {"yf": "UBER",  "mt5": "Uber Inc",                      "role": "core", "ratio": 1.0, "active": True},
    {"yf": "PFE",   "mt5": "Pfizer",                        "role": "core", "ratio": 1.0, "active": True},

    {"yf": "SPY",   "mt5": "SPDR S&P 500 ETF",                  "role": "core", "ratio": 1.0, "active": True},
    {"yf": "QQQ",   "mt5": "Invesco QQQ Trust Series 1",        "role": "core", "ratio": 1.0, "active": True},
    {"yf": "IWM",   "mt5": "iShares Russell 2000 ETF",          "role": "core", "ratio": 1.0, "active": True},
    {"yf": "IWF",   "mt5": "iShares Russell 1000 Growth",       "role": "core", "ratio": 1.0, "active": True},
    {"yf": "IVW",   "mt5": "iShares S&P 500 Growth Index",      "role": "core", "ratio": 1.0, "active": True},
    {"yf": "XLK",   "mt5": "Technology Select Sector SPDR",     "role": "core", "ratio": 1.0, "active": True},
    {"yf": "XBI",   "mt5": "SPDR SP Biotech ETF",               "role": "core", "ratio": 1.0, "active": True},
    {"yf": "LIT",   "mt5": "Global X Lithium ETF",              "role": "core", "ratio": 1.0, "active": False},  # edge 2.6x < 5x spread (2026-08-02)
    {"yf": "SIL",   "mt5": "Global X Silver Miners ETF",        "role": "core", "ratio": 1.0, "active": False},  # edge 3.9x < 5x spread; re-check open-market (2026-08-02)
    {"yf": "GDX",   "mt5": "VanEck Vectors Gold Miners",        "role": "core", "ratio": 1.0, "active": True},
    {"yf": "GDXJ",  "mt5": "VanEck Vectors Jr Gold Miners",     "role": "core", "ratio": 1.0, "active": True},
    {"yf": "GLD",   "mt5": "SPDR Gold Trust (US)",              "role": "core", "ratio": 1.0, "active": True},
    {"yf": "SLV",   "mt5": "iShares Silver Trust",              "role": "core", "ratio": 1.0, "active": True},
    {"yf": "EEM",   "mt5": "iShares MSCI Emerg Markets",        "role": "core", "ratio": 1.0, "active": True},
    {"yf": "FXI",   "mt5": "iShares FTSE Xinhua China 25",      "role": "core", "ratio": 1.0, "active": True},
    {"yf": "MCHI",  "mt5": "iShares MSCI China ETF",            "role": "core", "ratio": 1.0, "active": True},
    {"yf": "EWY",   "mt5": "iShares MSCI South Korea ETF",      "role": "core", "ratio": 1.0, "active": True},
  
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
