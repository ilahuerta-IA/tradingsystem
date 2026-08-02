try:
    import yfinance as yf # type: ignore
except ImportError as e:
    print(f"Error: yfinance is not installed. Install it using: pip install yfinance")
    print(f"Details: {e}")
    exit(1)

# Lista limpia previa (tickers de Yahoo Finance / TradingView)
assets_to_check = [
    {"yf": "AAPL",  "mt5": "Apple"},
    {"yf": "NVDA",  "mt5": "Nvidia"},
    {"yf": "GOOGL", "mt5": "Alphabet Inc A"},
    {"yf": "MSFT",  "mt5": "Microsoft"},
    {"yf": "AMZN",  "mt5": "Amazon"},
    {"yf": "AVGO",  "mt5": "Broadcom Ltd"},
    {"yf": "META",  "mt5": "Meta Platforms Inc"},
    {"yf": "TSLA",  "mt5": "Tesla Motors"},
    {"yf": "LLY",   "mt5": "Eli Lilly"},
    {"yf": "BRK-B", "mt5": "Berkshire Hathaway - Class B"}, # Formato Yahoo Finance usa guion '-'
    {"yf": "MU",    "mt5": "Micron"},
    {"yf": "WMT",   "mt5": "Walmart"},
    {"yf": "AMD",   "mt5": "Advanced Micro Devices"},
    {"yf": "V",     "mt5": "Visa"},
    {"yf": "JNJ",   "mt5": "Johnson & Johnson"},
    {"yf": "MA",    "mt5": "Mastercard"},
    {"yf": "INTC",  "mt5": "Intel"},
    {"yf": "CSCO",  "mt5": "Cisco Systems"},
    {"yf": "BAC",   "mt5": "Bank Of America"},
    {"yf": "COST",  "mt5": "Costco"},
    {"yf": "AMAT",  "mt5": "Applied Materials"},
    {"yf": "CVX",   "mt5": "Chevron Corp"},
    {"yf": "CAT",   "mt5": "Caterpillar"},
    {"yf": "LRCX",  "mt5": "Lam Research Corp"},
    {"yf": "ORCL",  "mt5": "Oracle"},
    {"yf": "HD",    "mt5": "Home Depot"},
    {"yf": "MS",    "mt5": "Morgan Stanley"},
    {"yf": "MRK",   "mt5": "Merck and Co"},
    {"yf": "NFLX",  "mt5": "Netflix"},
    {"yf": "GS",    "mt5": "Goldman Sachs"},
    {"yf": "PLTR",  "mt5": "Palantir Tech Inc A"},
    {"yf": "PANW",  "mt5": "Palo Alto Networks"},
    {"yf": "DELL",  "mt5": "Dell Technologies"},
    {"yf": "WFC",   "mt5": "Wells Fargo and Co"},
    {"yf": "TXN",   "mt5": "Texas Instruments"},
    {"yf": "LIN",   "mt5": "Linde Plc"},
    {"yf": "AXP",   "mt5": "American Express"},
    {"yf": "C",     "mt5": "Citigroup"},
    {"yf": "ANET",  "mt5": "Arista Networks Inc"},
    {"yf": "AMGN",  "mt5": "Amgen"},
    {"yf": "IBM",   "mt5": "IBM"},
    {"yf": "PEP",   "mt5": "PepsiCo"},
    {"yf": "MCD",   "mt5": "McDonald's"},
    {"yf": "TMUS",  "mt5": "T-Mobile US"},
    {"yf": "WDC",   "mt5": "Western Digital"},
    {"yf": "ADI",   "mt5": "Analog Devices"},
    {"yf": "TJX",   "mt5": "TJX Companies"},
    {"yf": "BA",    "mt5": "Boeing Co"},
    {"yf": "UNP",   "mt5": "Union Pacific"},
    {"yf": "DIS",   "mt5": "Walt Disney"},
    {"yf": "GILD",  "mt5": "Gilead Sciences"},
    {"yf": "QCOM",  "mt5": "Qualcomm"},
    {"yf": "T",     "mt5": "AT&T"},
    {"yf": "IBKR",  "mt5": "Interactive Brokers Inc"},
    {"yf": "BKNG",  "mt5": "Booking Holdings Inc"},
    {"yf": "CRM",   "mt5": "Salesforce Inc"},
    {"yf": "COP",   "mt5": "ConocoPhillips"},
    {"yf": "UBER",  "mt5": "Uber Inc"},
    {"yf": "PFE",   "mt5": "Pfizer"}
]

def filtrar_con_opciones():
    con_opciones = []
    sin_opciones = []

    print(f"Comprobando disponibilidad de opciones en Yahoo Finance para {len(assets_to_check)} activos...\n")

    for item in assets_to_check:
        ticker_yf = item["yf"]
        try:
            tk = yf.Ticker(ticker_yf)
            options_dates = tk.options

            if len(options_dates) > 0:
                con_opciones.append(item)
                print(f"✓ [TIENE OPCIONES] {ticker_yf} ({len(options_dates)} vencimientos disponibles)")
            else:
                sin_opciones.append(item)
                print(f"✗ [SIN OPCIONES] {ticker_yf}")
        except Exception as e:
            sin_opciones.append(item)
            print(f" Error consultando {ticker_yf}: {e}")

    print("\n" + "="*50)
    print(f"RESUMEN FINAL:")
    print(f" - Activos válidos (con mercado de opciones): {len(con_opciones)}")
    print(f" - Activos descartados (sin opciones): {len(sin_opciones)}")
    print("="*50)

    # Imprimir en formato de código la lista filtrada lista para usar
    print("\n### LISTA REFINADA CON OPCIONES ###\n")
    print("assets_con_opciones = [")
    for elem in con_opciones:
        # Volvemos a colocar BRK.B con punto si lo prefieres para tu estructura
        yf_symbol = elem['yf'].replace("-", ".")
        print(f'    {{"yf": "{yf_symbol}", "mt5": "{elem["mt5"]}", "role": "core", "ratio": 1.0, "active": True}},')
    print("]")

if __name__ == "__main__":
    filtrar_con_opciones()