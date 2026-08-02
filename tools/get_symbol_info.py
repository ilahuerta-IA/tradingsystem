import sys

try:
    import MetaTrader5 as mt5
except ImportError:
    print("Error: MetaTrader5 no está instalado. Instálalo con: pip install MetaTrader5")
    sys.exit(1)

# Lista de activos proporcionada
ETFS_ASSETS = [
    {"yf": "SPY",   "mt5": "SPDR S&P 500 ETF",                  "role": "core", "ratio": 1.0, "active": True},
    {"yf": "QQQ",   "mt5": "Invesco QQQ Trust Series 1",        "role": "core", "ratio": 1.0, "active": True},
    {"yf": "IWM",   "mt5": "iShares Russell 2000 ETF",          "role": "core", "ratio": 1.0, "active": True},
    {"yf": "IWF",   "mt5": "iShares Russell 1000 Growth",       "role": "core", "ratio": 1.0, "active": True},
    {"yf": "IVW",   "mt5": "iShares S&P 500 Growth Index",      "role": "core", "ratio": 1.0, "active": True},
    {"yf": "XLK",   "mt5": "Technology Select Sector SPDR",     "role": "core", "ratio": 1.0, "active": True},
    {"yf": "XBI",   "mt5": "SPDR SP Biotech ETF",               "role": "core", "ratio": 1.0, "active": True},
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

def obtener_info_activos():
    if not mt5.initialize():
        print("Error: Asegúrate de tener MT5 abierto.")
        return

    print("=" * 105)
    print(f"{'YF':<6} | {'SIMBOLO MT5':<32} | {'DIG':<4} | {'TICK SIZE':<10} | {'TICK VAL':<9} | {'VOL MIN':<8} | {'VOL STEP':<8} | {'SPREAD':<6}")
    print("=" * 105)

    resultados = {}

    for item in ETFS_ASSETS:
        simbolo = item["mt5"]
        
        # Aseguramos que el símbolo esté disponible/seleccionado para consultar sus datos
        mt5.symbol_select(simbolo, True)
        info = mt5.symbol_info(simbolo)

        if info is None:
            print(f"✗ No se pudo obtener información para: {simbolo}")
            continue

        # Extracción de campos exactos para el cálculo de lotes
        digits = info.digits                  # Número de decimales
        trade_contract_size = info.trade_contract_size # Tamaño del contrato
        tick_size = info.trade_tick_size      # Tamaño del tick (ej. 0.001)
        tick_value = info.trade_tick_value    # Valor del tick en la divisa de la cuenta
        volume_min = info.volume_min          # Volumen mínimo permitido
        volume_step = info.volume_step        # Paso/Incremento de volumen
        spread = info.spread                  # Spread actual en puntos

        # Almacenamos en un diccionario por si se quiere exportar
        resultados[item["yf"]] = {
            "mt5_name": simbolo,
            "digits": digits,
            "contract_size": trade_contract_size,
            "tick_size": tick_size,
            "tick_value": tick_value,
            "volume_min": volume_min,
            "volume_step": volume_step,
            "spread": spread
        }

        print(f"{item['yf']:<6} | {simbolo:<32} | {digits:<4} | {tick_size:<10} | {tick_value:<9} | {volume_min:<8} | {volume_step:<8} | {spread:<6}")

    print("=" * 105)
    mt5.shutdown()
    return resultados

if __name__ == "__main__":
    obtener_info_activos()