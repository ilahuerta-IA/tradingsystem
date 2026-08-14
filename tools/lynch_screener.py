r"""
PETER LYNCH SCREENER

PowerShell examples (run from the TradingSystem directory):

    One ticker, terminal only (no CSV):
        python .\tools\lynch_screener.py --ticker AIR.PA

    NYSE, one batch:
        python .\tools\lynch_screener.py --file .\data\nyse_full_tickers.json --start 0 --end 50

    One European market:
        python .\tools\lynch_screener.py --file .\data\euronext_AEX_Amsterdam.json --start 0 --end 50

    All Euronext JSON files, deduplicated:
        python .\tools\lynch_screener.py --files ".\data\euronext_*.json" --start 0 --end 500 --output-name euronext

    Several explicit files:
        python .\tools\lynch_screener.py --files .\data\euronext_AEX_Amsterdam.json .\data\euronext_IBEX_35_Madrid.json --output-name aex_ibex
"""

import argparse
import glob
import json
import logging
import pandas as pd
import yfinance as yf
from pathlib import Path

logging.getLogger("yfinance").setLevel(logging.CRITICAL)

MIN_ROIC = 15
MIN_EPS_GROWTH = 15
MAX_EPS_GROWTH = 40
RESULT_COLUMNS = [
    "Ticker",
    "Nombre",
    "Fuente",
    "Sector",
    "Precio ($)",
    "MarketCap ($M)",
    "PER",
    "PEG",
    "ROIC 5a (%)",
    "Deuda/Eq (%)",
    "EPS 5a (%)",
    "Beta",
    "Filtro Lynch",
]

# ==========================================
# 1. LEYENDA Y CRITERIOS DE FILTRADO (PETER LYNCH)
# ==========================================
def print_screener_legend():
    """Muestra la leyenda explicativa de los filtros aplicados."""
    print("\n" + "="*70)
    print("LEYENDA DE FILTRADO Y CRITERIOS (ESTILO PETER LYNCH)")
    print("="*70)
    print(" - PEG Ratio      : Ideal <= 1.0 (Crecimiento a un precio razonable).")
    print(" - PER (P/E)      : Ideal <= 25.0 (Evita sobrevaloracion extrema).")
    print(" - Deuda / Capital: Ideal < 40% (Bajo apalancamiento financiero).")
    print(f" - ROIC 5 anos    : Ideal >= {MIN_ROIC}%.")
    print(f" - EPS 5 anos     : Crecimiento entre {MIN_EPS_GROWTH}% y {MAX_EPS_GROWTH}%.")
    print(" - MarketCap      : Tamano de mercado en Millones de USD ($M).")
    print(" - Beta           : Volatilidad relativa frente al mercado.")
    print("="*70 + "\n")

# ==========================================
# 2. CARGA Y NORMALIZACION DE DATOS
# ==========================================
def resolve_input_files(patterns: list[str]) -> list[Path]:
    """Expande rutas y patrones glob, conservando cada archivo una sola vez."""
    resolved = []
    seen = set()
    for pattern in patterns:
        matches = [Path(match) for match in glob.glob(pattern)]
        if not matches and Path(pattern).is_file():
            matches = [Path(pattern)]
        if not matches:
            print(f"[WARN] No se encontraron archivos para: {pattern}")
        for path in sorted(matches):
            normalized = str(path.resolve()).lower()
            if normalized not in seen:
                seen.add(normalized)
                resolved.append(path)
    return resolved


def load_universe(file_paths: list[Path], ticker_key: str = "symbol") -> list[dict]:
    """Normaliza varios JSON y combina simbolos duplicados con sus fuentes."""
    companies = {}
    for path in file_paths:
        try:
            with path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError) as error:
            print(f"[ERROR] No se pudo leer {path}: {error}")
            continue

        if not isinstance(data, list):
            print(f"[ERROR] El JSON debe contener una lista: {path}")
            continue

        source = path.stem
        for item in data:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get(ticker_key, "")).strip().upper()
            if not symbol:
                continue
            name = item.get("name")
            name = name.strip() if isinstance(name, str) and name.strip() not in {"N/A", "N/D"} else None
            if symbol not in companies:
                companies[symbol] = {"symbol": symbol, "name": name, "sources": [source]}
            else:
                if not companies[symbol]["name"] and name:
                    companies[symbol]["name"] = name
                if source not in companies[symbol]["sources"]:
                    companies[symbol]["sources"].append(source)

    return list(companies.values())


def load_tickers_from_json(file_path: str, ticker_key: str = "symbol") -> list[str]:
    """Mantiene compatibilidad con la carga de un unico JSON."""
    files = resolve_input_files([file_path])
    return [company["symbol"] for company in load_universe(files, ticker_key)]

# ==========================================
# 3. EVALUACION Y EXTRACCION DE METRICAS
# ==========================================
def get_statement_row(statement: pd.DataFrame, *names: str) -> pd.Series:
    """Obtiene una partida financiera aceptando los nombres usados por yfinance."""
    for name in names:
        if name in statement.index:
            return pd.to_numeric(statement.loc[name], errors="coerce")
    return pd.Series(dtype=float)


def calculate_eps_growth(income_stmt: pd.DataFrame) -> float | None:
    """Calcula el CAGR del EPS con hasta cinco ejercicios anuales disponibles."""
    eps = get_statement_row(income_stmt, "Diluted EPS", "Basic EPS").dropna()
    if len(eps) < 2:
        return None

    eps = eps.iloc[:5]
    newest_eps = eps.iloc[0]
    oldest_eps = eps.iloc[-1]
    years = len(eps) - 1
    if newest_eps <= 0 or oldest_eps <= 0:
        return None

    return ((newest_eps / oldest_eps) ** (1 / years) - 1) * 100


def calculate_roic(income_stmt: pd.DataFrame, balance_sheet: pd.DataFrame) -> float | None:
    """Calcula el ROIC medio usando hasta cinco ejercicios anuales disponibles."""
    ebit = get_statement_row(income_stmt, "EBIT", "Operating Income")
    tax_rate = get_statement_row(income_stmt, "Tax Rate For Calcs")
    tax_provision = get_statement_row(income_stmt, "Tax Provision")
    pretax_income = get_statement_row(income_stmt, "Pretax Income")
    debt = get_statement_row(balance_sheet, "Total Debt")
    equity = get_statement_row(
        balance_sheet,
        "Stockholders Equity",
        "Total Stockholder Equity",
    )
    cash = get_statement_row(
        balance_sheet,
        "Cash Cash Equivalents And Short Term Investments",
        "Cash And Cash Equivalents",
    )

    roic_values = []
    for date in balance_sheet.columns[:5]:
        if date not in ebit.index or date not in debt.index or date not in equity.index:
            continue

        effective_tax_rate = tax_rate.get(date)
        if pd.isna(effective_tax_rate):
            pretax = pretax_income.get(date)
            taxes = tax_provision.get(date)
            effective_tax_rate = taxes / pretax if pd.notna(pretax) and pretax > 0 else 0
        effective_tax_rate = min(max(effective_tax_rate, 0), 1)

        invested_capital = debt.get(date) + equity.get(date) - cash.get(date, 0)
        if pd.notna(invested_capital) and invested_capital > 0 and pd.notna(ebit.get(date)):
            roic_values.append(ebit.get(date) * (1 - effective_tax_rate) / invested_capital * 100)

    return sum(roic_values) / len(roic_values) if roic_values else None


def evaluate_lynch_criteria(
    peg: float,
    debt_to_equity: float,
    pe: float,
    roic_5y: float,
    eps_growth_5y: float,
) -> bool:
    """Aplica la logica de filtrado basica de Peter Lynch."""
    try:
        # Si faltan datos criticos, descartamos el filtro positivo
        metrics = [peg, debt_to_equity, pe, roic_5y, eps_growth_5y]
        if any(pd.isna(metric) for metric in metrics):
            return False
        return (
            (0 < peg <= 1.0)
            and (debt_to_equity < 40)
            and (0 < pe <= 25)
            and (roic_5y >= MIN_ROIC)
            and (MIN_EPS_GROWTH <= eps_growth_5y <= MAX_EPS_GROWTH)
        )
    except (TypeError, ValueError):
        return False

def fetch_and_filter_data(companies: list[dict]) -> tuple:
    """Descarga metricas fundamentales ampliadas para cada ticker."""
    if not companies:
        return pd.DataFrame(columns=RESULT_COLUMNS), []

    print(f"[INFO] Descargando datos fundamentales y metricas para {len(companies)} tickers...")
    
    valid_data = []
    missing_tickers = []

    for company in companies:
        if isinstance(company, str):
            company = {"symbol": company, "name": None, "sources": []}
        ticker = company["symbol"]
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            # Verificacion de existencia de datos basicos
            if 'currentPrice' not in info and 'regularMarketPrice' not in info:
                missing_tickers.append(ticker)
                continue

            # Extraccion de campos clave
            sector = info.get('sector', 'N/D')
            price = info.get('currentPrice') or info.get('regularMarketPrice')
            market_cap = info.get('marketCap', 0)
            market_cap_m = round(market_cap / 1_000_000, 2) if market_cap else None
            
            pe_ratio = info.get('trailingPE') or info.get('forwardPE', None)
            peg_ratio = info.get('pegRatio', None)
            
            # yfinance entrega debtToEquity en porcentaje (ej: 34.12)
            debt_equity = info.get('debtToEquity', None) 
            beta = info.get('beta', None)
            income_stmt = stock.income_stmt
            balance_sheet = stock.balance_sheet
            eps_growth_5y = calculate_eps_growth(income_stmt)
            roic_5y = calculate_roic(income_stmt, balance_sheet)

            # Evaluacion de filtros
            lynch_pass = evaluate_lynch_criteria(
                peg_ratio,
                debt_equity,
                pe_ratio,
                roic_5y,
                eps_growth_5y,
            )

            valid_data.append({
                "Ticker": ticker,
                "Nombre": company["name"] or info.get("longName") or info.get("shortName"),
                "Fuente": ",".join(company["sources"]),
                "Sector": sector,
                "Precio ($)": round(price, 2) if price else None,
                "MarketCap ($M)": market_cap_m,
                "PER": round(pe_ratio, 2) if pe_ratio else 99.90,
                "PEG": round(peg_ratio, 2) if peg_ratio else 99.90,
                "ROIC 5a (%)": round(roic_5y, 2) if roic_5y is not None else None,
                "Deuda/Eq (%)": round(debt_equity, 2) if debt_equity else None,
                "EPS 5a (%)": round(eps_growth_5y, 2) if eps_growth_5y is not None else None,
                "Beta": round(beta, 2) if beta else None,
                "Filtro Lynch": "PASA" if lynch_pass else "NO"
            })
            
        except Exception:
            missing_tickers.append(ticker)
            
    return pd.DataFrame(valid_data, columns=RESULT_COLUMNS), missing_tickers

# ==========================================
# 4. GUARDADO DE RESULTADOS
# ==========================================
def save_results(df: pd.DataFrame, start: int, end: int, output_name: str | None = None):
    """Guarda en CSV todos los resultados descargados."""
    output_dir = Path("results")
    output_dir.mkdir(exist_ok=True)

    if output_name:
        safe_name = "".join(character if character.isalnum() or character in "-_" else "_" for character in output_name)
        filename = output_dir / f"lynch_report_{safe_name}_{start}_to_{end}.csv"
    else:
        filename = output_dir / f"lynch_report_{start}_to_{end}.csv"
    df.to_csv(filename, index=False, sep=";")
    print(f"\n[OK] Reporte detallado guardado con exito en: {filename}")

# ==========================================
# 5. EJECUCION PRINCIPAL Y CLI
# ==========================================
def main():
    parser = argparse.ArgumentParser(description="Screener Avanzado tipo Peter Lynch")
    parser.add_argument("--start", type=int, default=0, help="Indice inicial del paquete")
    parser.add_argument("--end", type=int, default=50, help="Indice final del paquete")
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument("--ticker", help="Simbolo de yfinance para analizar en terminal sin crear CSV")
    input_group.add_argument("--file", help="Ruta a un JSON (compatible con el uso anterior)")
    input_group.add_argument("--files", nargs="+", help="Rutas o patrones glob de varios JSON")
    parser.add_argument("--output-name", help="Nombre del universo para el archivo CSV")
    args = parser.parse_args()

    print("\n" + "="*70)
    print("LYNCH SCREENER AVANZADO - INICIALIZANDO")
    print("="*70)

    # Mostrar la leyenda informativa obligatoria
    print_screener_legend()

    if args.ticker:
        ticker = args.ticker.strip().upper()
        if not ticker:
            parser.error("--ticker requiere un simbolo valido")
        batch_companies = [{"symbol": ticker, "name": None, "sources": ["yfinance"]}]
        start_idx = 0
        end_idx = 1
        output_name = None
        print(f"[INFO] Analizando activo individual: {ticker}\n")
    else:
        input_patterns = args.files or [args.file or "data/nyse_full_tickers.json"]
        input_files = resolve_input_files(input_patterns)
        if not input_files:
            return

        all_companies = load_universe(input_files)
        if not all_companies:
            print("[ERROR] No se encontraron simbolos validos en los archivos.")
            return

        total = len(all_companies)
        end_idx = min(args.end, total)
        start_idx = max(0, args.start)
        batch_companies = all_companies[start_idx:end_idx]
        default_output_name = input_files[0].stem if len(input_files) == 1 else "combined"
        output_name = args.output_name or default_output_name

        print(f"[OK] Archivos cargados: {len(input_files)}. Empresas unicas: {total}")
        print(f"[INFO] Procesando paquete actual: del registro {start_idx} al {end_idx} ({len(batch_companies)} empresas)\n")

    # Obtener y filtrar datos con metricas completas
    df_valid, missing = fetch_and_filter_data(batch_companies)

    # Reporte en Terminal
    print("\n" + "="*70)
    print("RESULTADOS DEL ANALISIS Y FILTRADO")
    print("="*70)
    
    if not df_valid.empty:
        print(df_valid.to_markdown(index=False, tablefmt="github"))
    else:
        print("[WARN] No se encontraron datos validos para este paquete.")
    if not args.ticker:
        save_results(df_valid, start_idx, end_idx, output_name)

    # Reporte de errores / tickers no encontrados
    if missing:
        print("\n" + "-"*70)
        print(f"[ERROR] TICKERS NO ENCONTRADOS / SIN FUNDAMENTALES ({len(missing)}):")
        print("-" *70)
        print(", ".join(missing))

if __name__ == "__main__":
    main()