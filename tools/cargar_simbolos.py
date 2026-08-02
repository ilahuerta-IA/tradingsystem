import MetaTrader5 as mt5

# ==============================================================================
# 1. LISTA DE ACCIONES (S&P 500)
# ==============================================================================
ACCIONES_SP500 = [
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
    {"yf": "PFE",   "mt5": "Pfizer",                        "role": "core", "ratio": 1.0, "active": True}
]

# ==============================================================================
# 2. LISTA DE ETFs (SPOT / SIN APALANCAR)
# ==============================================================================
ETFS_SPOT = [
    {"yf": "SPY",   "mt5": "SPDR S&P 500 ETF",                  "role": "core", "ratio": 1.0, "active": True},
    {"yf": "QQQ",   "mt5": "Invesco QQQ Trust Series 1",        "role": "core", "ratio": 1.0, "active": True},
    {"yf": "IWM",   "mt5": "iShares Russell 2000 ETF",          "role": "core", "ratio": 1.0, "active": True},
    {"yf": "IWF",   "mt5": "iShares Russell 1000 Growth",       "role": "core", "ratio": 1.0, "active": True},
    {"yf": "IVW",   "mt5": "iShares S&P 500 Growth Index",      "role": "core", "ratio": 1.0, "active": True},
    {"yf": "QQQJ",  "mt5": "Reality Shares Nsdq NextGen Eco",   "role": "core", "ratio": 1.0, "active": True},
    {"yf": "XLK",   "mt5": "Technology Select Sector SPDR",     "role": "core", "ratio": 1.0, "active": True},
    {"yf": "XBI",   "mt5": "SPDR SP Biotech ETF",               "role": "core", "ratio": 1.0, "active": True},
    {"yf": "IYR",   "mt5": "iShares Dow Jones US Real Estat",   "role": "core", "ratio": 1.0, "active": True},
    {"yf": "LIT",   "mt5": "Global X Lithium ETF",              "role": "core", "ratio": 1.0, "active": True},
    {"yf": "SIL",   "mt5": "Global X Silver Miners ETF",        "role": "core", "ratio": 1.0, "active": True},
    {"yf": "GDX",   "mt5": "VanEck Vectors Gold Miners",        "role": "core", "ratio": 1.0, "active": True},
    {"yf": "GDXJ",  "mt5": "VanEck Vectors Jr Gold Miners",     "role": "core", "ratio": 1.0, "active": True},
    {"yf": "GLD",   "mt5": "SPDR Gold Trust (US)",              "role": "core", "ratio": 1.0, "active": True},
    {"yf": "SLV",   "mt5": "iShares Silver Trust",              "role": "core", "ratio": 1.0, "active": True},
    {"yf": "EEM",   "mt5": "iShares MSCI Emerg Markets",        "role": "core", "ratio": 1.0, "active": True},
    {"yf": "FXI",   "mt5": "iShares FTSE Xinhua China 25",      "role": "core", "ratio": 1.0, "active": True},
    {"yf": "MCHI",  "mt5": "iShares MSCI China ETF",            "role": "core", "ratio": 1.0, "active": True},
    {"yf": "EWY",   "mt5": "iShares MSCI South Korea ETF",      "role": "core", "ratio": 1.0, "active": True}
]

# ==============================================================================
# 3. CONTROL DE SELECCIÓN (Descomenta solo 1 de las 3 opciones)
# ==============================================================================

# OPCIÓN 1: Cargar SOLO ETFs
assets = ETFS_SPOT

# OPCIÓN 2: Cargar SOLO Acciones
# assets = ACCIONES_SP500

# OPCIÓN 3: Cargar AMBOS (Acciones + ETFs)
# assets = ETFS_SPOT + ACCIONES_SP500


# ==============================================================================
# 4. SCRIPT DE LIMPIEZA Y CARGA
# ==============================================================================
def limpiar_y_cargar():
    if not mt5.initialize():
        print("Error: Conecta con MT5 antes de ejecutar.")
        return

    # ---------------------------------------------------------
    # PASO A: Limpiar el Market Watch (ocultar lo que esté visible)
    # ---------------------------------------------------------
    símbolos_visibles = mt5.symbols_get(selected=True)
    if símbolos_visibles:
        print(f"Limpiando {len(símbolos_visibles)} símbolos visibles del Market Watch...")
        for sym in símbolos_visibles:
            mt5.symbol_select(sym.name, False)

    # ---------------------------------------------------------
    # PASO B: Cargar la lista seleccionada en 'assets'
    # ---------------------------------------------------------
    print(f"\nCargando {len(assets)} símbolos de la lista seleccionada...")
    exitos = 0
    for item in assets:
        simbolo = item["mt5"]
        if mt5.symbol_select(simbolo, True):
            exitos += 1
            print(f"✓ [{item['yf']}] Cargado -> '{simbolo}'")
        else:
            print(f"✗ Error al cargar -> '{simbolo}'")

    print(f"\n¡Completado! {exitos} de {len(assets)} activos desplegados en la Observación del Mercado.")
    mt5.shutdown()

if __name__ == "__main__":
    limpiar_y_cargar()