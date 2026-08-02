import os
import sys
import re

try:
    import MetaTrader5 as mt5
except ImportError:
    print("Error: MetaTrader5 no está instalado. Instálalo con: pip install MetaTrader5")
    sys.exit(1)

try:
    import yfinance as yf
except ImportError:
    print("Error: yfinance no está instalado. Instálalo con: pip install yfinance")
    sys.exit(1)

OUTPUT_DIR = r"C:\Iván\Yosoybuendesarrollador\Python\Portafolio\TradingSystem\results"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "etfs_disponibles.html")

# Mapeo exhaustivo ampliado para nombres descriptivos de MT5
MAPEO_EXPLICITO = {
    # Sectoriales SPDR
    "TECHNOLOGY SELECT SECTOR SPDR": "XLK",
    "FINANCIAL SELECT SECTOR SPDR": "XLF",
    "ENERGY SELECT SECTOR SPDR": "XLE",
    "HEALTH CARE SELECT SECTOR SPDR": "XLV",
    "CONSUMER DISCRETIONARY SELECT SECTOR SPDR": "XLY",
    "CONSUMER STAPLES SELECT SECTOR SPDR": "XLP",
    "INDUSTRIAL SELECT SECTOR SPDR": "XLI",
    "MATERIALS SELECT SECTOR SPDR": "XLB",
    "UTILITIES SELECT SECTOR SPDR": "XLU",
    "REAL ESTATE SELECT SECTOR SPDR": "XLRE",
    "COMMUNICATION SERVICES SELECT SECTOR SPDR": "XLC",

    # Direxion & ProShares & iShares (Capturas anteriores)
    "DIREXION DLY FIN BEAR 3XSHS": "FAZ",
    "DIREXION DLY GDM IDX BULL 2X": "NUGT",
    "DIREXION DLY JR GLD BULL 2X": "JNUG",
    "INVESCO QQQ TRUST SERIES 1": "QQQ",
    "ISHARES DOW JONES US REAL ESTAT": "IYR",
    "ISHARES MSCI EMERG MARKETS": "EEM",
    "ISHARES MSCI SOUTH KOREA": "EWY",
    "ISHARES RUSSELL 1000 GROWTH": "IWF",
    "ISHARES S&P 500 GROWTH": "IVW",
    "ISHARES SILVER TRUST": "SLV",
    "PROSHARES ULTRA SHRT RUSL 2000": "TWM",
    "PROSHARES ULTRA VIX ST": "UVXY",
    "PROSHARES ULTRAPRO DOW30": "UDOW",
    "PROSHARES VIX SHORT TERM": "VIXY",
    "PROSHARES VIX ST": "VIXY",
    "SPDR GOLD TRUST": "GLD",
    "SPDR GOLD TRUST (US)": "GLD",
    "ULTRA QQQ PROSHARES": "QLD",
    "VANECK VECTORS GOLD MINERS": "GDX",
    "VANECK VECTORS JR GOLD MINERS": "GDXJ",
    "VANECK VECTORS JUNIOR GOLD MINERS": "GDXJ",
    "REALITY SHARES NSDQ NEXTGEN ECO": "QQQJ",
    "ISHARES RUSSELL 2000": "IWM",
    "GLOBAL X LITHIUM": "LIT",
    "GLOBAL X SILVER MINERS": "SIL",
    "ISHARES MSCI CHINA": "MCHI",
    "ISHARES FTSE XINHUA CHINA 25": "FXI",
    "SPDR S&P 500": "SPY",
    "SPDR SP BIOTECH": "XBI"
}

def es_etf(sym):
    name = sym.name.upper()
    desc = sym.description.upper()
    path = sym.path.upper()

    keywords = ["ETF", "ISHARES", "SPDR", "GLOBAL X", "VANGUARD", "LYXOR", "INVESCO", "PROSHARES", "VANECK", "DIREXION", "SELECT SECTOR"]
    
    if "NETFLIX" in desc or name == "NFLX":
        return False

    return any(kw in name or kw in desc or kw in path for kw in keywords)

def inferir_ticker_yf(name, desc):
    name_clean = name.strip()
    desc_clean = desc.strip()
    full_str_upper = f"{name_clean} {desc_clean}".upper()

    # 1. Búsqueda por mapa explícito
    for key, ticker in MAPEO_EXPLICITO.items():
        if key in full_str_upper:
            return ticker

    # 2. Extracción mediante Regex (Busca patrones tipo "(QQQ)", "- SLV", o palabras de 3-4 letras mayúsculas)
    match = re.search(r'\b([A-Z]{3,5})\b', name_clean)
    if match and match.group(1) not in ["DLY", "BULL", "BEAR", "SHS", "SERIES", "INDEX", "TRUST"]:
        return match.group(1)

    # 3. Si el nombre de MT5 ya es un ticker estándar corto
    if 2 <= len(name_clean) <= 5 and name_clean.isalpha():
        return name_clean.upper()

    return name_clean

def generar_html(etfs_data):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    rows_html = ""
    for item in etfs_data:
        badge_opciones = (
            '<span class="badge bg-success">✓ Sí</span>' 
            if item['has_options'] 
            else '<span class="badge bg-secondary">✗ No</span>'
        )
        
        rows_html += f"""
        <tr>
            <td><span class="badge bg-primary text-wrap fs-6">{item['ticker']}</span></td>
            <td><strong>{item['name']}</strong></td>
            <td>{item['description']}</td>
            <td>{item['num_expirations']}</td>
            <td class="text-center">{badge_opciones}</td>
        </tr>
        """

    html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ETFs Disponibles - Bróker MT5</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.datatables.net/1.13.6/css/dataTables.bootstrap5.min.css">
    <style>
        body {{ background-color: #0f172a; color: #f8fafc; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }}
        .card {{ background-color: #1e293b; border: 1px solid #334155; border-radius: 12px; }}
        
        .table {{ color: #e2e8f0; --bs-table-bg: transparent; }}
        .table-striped>tbody>tr:nth-of-type(odd)>* {{ 
            background-color: #182232 !important; 
            color: #cbd5e1 !important; 
        }}
        .table-striped>tbody>tr:nth-of-type(even)>* {{ 
            background-color: #243144 !important; 
            color: #ffffff !important; 
        }}
        .table-hover>tbody>tr:hover>* {{ 
            background-color: #3b82f6 !important; 
            color: #ffffff !important; 
        }}
        
        .badge {{ font-size: 0.85em; padding: 0.5em 0.75em; }}
        .dataTables_wrapper .dataTables_length, .dataTables_wrapper .dataTables_filter, 
        .dataTables_wrapper .dataTables_info, .dataTables_wrapper .dataTables_paginate {{ color: #94a3b8 !important; }}
        .form-control, .form-select {{ background-color: #0f172a; border-color: #334155; color: #f8fafc; }}
        .form-control:focus, .form-select:focus {{ background-color: #1e293b; color: #ffffff; border-color: #3b82f6; box-shadow: none; }}
    </style>
</head>
<body class="py-4">
    <div class="container-fluid px-4">
        <div class="d-flex justify-content-between align-items-center mb-4">
            <div>
                <h2 class="fw-bold text-primary mb-1">Catálogo de ETFs - Bróker MT5</h2>
                <p class="text-muted mb-0">Total detectados: <strong>{len(etfs_data)}</strong></p>
            </div>
            <button onclick="location.reload()" class="btn btn-outline-primary btn-sm">Actualizar Vista</button>
        </div>

        <div class="card p-4 shadow-lg">
            <div class="table-responsive">
                <table id="etfTable" class="table table-striped table-hover align-middle">
                    <thead>
                        <tr>
                            <th>Ticker (YF)</th>
                            <th>Nombre MT5</th>
                            <th>Descripción Activo</th>
                            <th>Vencimientos Opciones</th>
                            <th class="text-center">Tiene Opciones</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html}
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <script src="https://code.jquery.com/jquery-3.7.0.min.js"></script>
    <script src="https://cdn.datatables.net/1.13.6/js/jquery.dataTables.min.js"></script>
    <script src="https://cdn.datatables.net/1.13.6/js/dataTables.bootstrap5.min.js"></script>
    <script>
        $(document).ready(function() {{
            $('#etfTable').DataTable({{
                "language": {{
                    "url": "//cdn.datatables.net/plug-ins/1.13.6/i18n/es-ES.json"
                }},
                "pageLength": 25,
                "order": [[4, "desc"], [0, "asc"]]
            }});
        }});
    </script>
</body>
</html>
"""

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"\n✓ Informe HTML actualizado guardado en:\n{OUTPUT_FILE}")

def main():
    if not mt5.initialize():
        print("Error: Asegúrate de tener MT5 abierto.")
        return

    all_symbols = mt5.symbols_get()
    print(f"Buscando ETFs sobre {len(all_symbols)} activos en MT5...")

    etfs_encontrados = [sym for sym in all_symbols if es_etf(sym)]
    print(f"Se identificaron {len(etfs_encontrados)} ETFs. Consultando opciones...\n")

    resultados = []
    for sym in etfs_encontrados:
        ticker = inferir_ticker_yf(sym.name, sym.description)
        
        has_options = False
        num_expirations = 0

        try:
            tk = yf.Ticker(ticker)
            opts = tk.options
            if opts and len(opts) > 0:
                has_options = True
                num_expirations = len(opts)
        except Exception:
            pass

        resultados.append({
            "ticker": ticker,
            "name": sym.name,
            "description": sym.description,
            "has_options": has_options,
            "num_expirations": num_expirations
        })

        status_str = f"✓ Opciones ({num_expirations} vto)" if has_options else "✗ Sin opciones"
        print(f"  -> Ticker: [{ticker}] | MT5: {sym.name} | {status_str}")

    generar_html(resultados)
    mt5.shutdown()

if __name__ == "__main__":
    main()