try:
    import MetaTrader5 as mt5 # type: ignore
except ImportError:
    mt5 = None

# Diccionario con el ticker de TradingView y el nombre real exacto extraído de tu PDF
TARGET_COMPANIES = {
    "AAPL": "Apple",
    "NVDA": "NVIDIA",
    "GOOGL": "Alphabet",
    "GOOG": "Alphabet",
    "MSFT": "Microsoft",
    "AMZN": "Amazon",
    "AVGO": "Broadcom",
    "META": "Meta Platforms",
    "TSLA": "Tesla",
    "LLY": "Eli Lilly",
    "BRK.B": "Berkshire Hathaway",
    "MU": "Micron",
    "JPM": "JPMorgan",
    "WMT": "Walmart",
    "AMD": "Advanced Micro Devices",
    "V": "Visa",
    "XOM": "ExxonMobil",
    "JNJ": "Johnson & Johnson",
    "MA": "Mastercard",
    "INTC": "Intel",
    "ABBV": "AbbVie",
    "CSCO": "Cisco",
    "BAC": "Bank of America",
    "COST": "Costco",
    "AMAT": "Applied Materials",
    "CVX": "Chevron",
    "UNH": "UnitedHealth",
    "KO": "Coca-Cola",
    "CAT": "Caterpillar",
    "GE": "GE Aerospace",
    "PG": "Procter & Gamble",
    "LRCX": "Lam Research",
    "ORCL": "Oracle",
    "HD": "Home Depot",
    "MS": "Morgan Stanley",
    "MRK": "Merck",
    "NFLX": "Netflix",
    "GS": "Goldman Sachs",
    "PM": "Philip Morris",
    "PLTR": "Palantir",
    "RTX": "RTX Corporation",
    "PANW": "Palo Alto Networks",
    "DELL": "Dell Technologies",
    "GEV": "GE Vernova",
    "WFC": "Wells Fargo",
    "TXN": "Texas Instruments",
    "KLAC": "KLA Corporation",
    "LIN": "Linde",
    "AXP": "American Express",
    "C": "Citigroup",
    "ANET": "Arista Networks",
    "TMO": "Thermo Fisher",
    "AMGN": "Amgen",
    "IBM": "International Business Machines",
    "APH": "Amphenol",
    "VZ": "Verizon",
    "PEP": "PepsiCo",
    "STX": "Seagate",
    "MCD": "McDonald's",
    "SNDK": "Sandisk",
    "CRWD": "CrowdStrike",
    "TMUS": "T-Mobile",
    "WDC": "Western Digital",
    "NEE": "NextEra Energy",
    "ABT": "Abbott",
    "SCHW": "Charles Schwab",
    "ADI": "Analog Devices",
    "BLK": "BlackRock",
    "TJX": "TJX Companies",
    "BA": "Boeing",
    "UNP": "Union Pacific",
    "WELL": "Welltower",
    "DIS": "Walt Disney",
    "GILD": "Gilead",
    "DE": "Deere",
    "MRVL": "Marvell",
    "BX": "Blackstone",
    "QCOM": "QUALCOMM",
    "T": "AT&T",
    "IBKR": "Interactive Brokers",
    "ETN": "Eaton",
    "BKNG": "Booking",
    "CRM": "Salesforce",
    "COP": "ConocoPhillips",
    "UBER": "Uber",
    "PFE": "Pfizer",
    "PLD": "Prologis",
    "DHR": "Danaher",
    "APP": "AppLovin",
    "CB": "Chubb",
    "CVS": "CVS Health",
    "SYK": "Stryker",
    "LMT": "Lockheed Martin",
    "BMY": "Bristol-Myers",
    "COF": "Capital One",
    "ISRG": "Intuitive Surgical",
    "PGR": "Progressive",
    "SPGI": "S&P Global",
    "VRTX": "Vertex",
    "PH": "Parker-Hannifin"
}

def diagnostico_simbolos():
    if not mt5.initialize():
        print("Error: Asegúrate de que MT5 esté abierto.")
        return

    all_symbols = mt5.symbols_get()
    print(f"--- ANALIZANDO {len(all_symbols)} ACTIVOS DEL BRÓKER EN MODO LECTURA ---\n")

    encontrados = []
    dudosos = []
    no_encontrados = []

    for ticker, keyword in TARGET_COMPANIES.items():
        keyword_upper = keyword.upper()
        matches = []

        # Recorremos los símbolos del bróker buscando coincidencia en la descripción
        for sym in all_symbols:
            desc_upper = sym.description.upper()
            name_upper = sym.name.upper()

            # Búsqueda estricta de la palabra clave completa
            if keyword_upper in desc_upper or keyword_upper in name_upper:
                matches.append((sym.name, sym.description, sym.path))

        if len(matches) == 1:
            m = matches[0]
            encontrados.append((ticker, keyword, m[0], m[1]))
            print(f"✓ [OK] {ticker} ({keyword}) -> MT5 Symbol: '{m[0]}' | Desc: '{m[1]}'")
        elif len(matches) > 1:
            dudosos.append((ticker, keyword, matches))
            print(f"⚠ [VARIAS COINCIDENCIAS] {ticker} ({keyword}):")
            for m in matches:
                print(f"    └─ Candidate: '{m[0]}' | Desc: '{m[1]}' | Ruta: {m[2]}")
        else:
            no_encontrados.append((ticker, keyword))
            print(f"✗ [NO ENCONTRADO] {ticker} ({keyword})")

    print("\n" + "="*50)
    print(f"RESUMEN DIAGNÓSTICO:")
    print(f" - Coincidencias exactas/únicas: {len(encontrados)}")
    print(f" - Múltiples candidatos a revisar: {len(dudosos)}")
    print(f" - No localizados en este bróker: {len(no_encontrados)}")
    print("="*50)

    mt5.shutdown()

if __name__ == "__main__":
    diagnostico_simbolos()