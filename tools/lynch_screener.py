import argparse
import json
import pandas as pd
import yfinance as yf
from pathlib import Path

MIN_ROIC = 15
MIN_EPS_GROWTH = 15
MAX_EPS_GROWTH = 40
RESULT_COLUMNS = [
    "Ticker",
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
# 2. CARGA DE DATOS
# ==========================================
def load_tickers_from_json(file_path: str, ticker_key: str = "symbol") -> list:
    """Lee el archivo JSON y extrae la lista de tickers."""
    path = Path(file_path)
    if not path.exists():
        print(f"[ERROR] No se encontro el archivo en {file_path}")
        return []
    
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    return [item.get(ticker_key) for item in data if item.get(ticker_key)]

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

def fetch_and_filter_data(tickers: list) -> tuple:
    """Descarga metricas fundamentales ampliadas para cada ticker."""
    if not tickers:
        return pd.DataFrame(), []

    print(f"[INFO] Descargando datos fundamentales y metricas para {len(tickers)} tickers...")
    
    valid_data = []
    missing_tickers = []

    for ticker in tickers:
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
def save_results(df: pd.DataFrame, start: int, end: int):
    """Guarda en CSV todos los resultados descargados."""
    output_dir = Path("results")
    output_dir.mkdir(exist_ok=True)
    
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
    parser.add_argument("--file", type=str, default="DATA/nyse_full_tickers.json", help="Ruta al JSON")
    args = parser.parse_args()

    print("\n" + "="*70)
    print("LYNCH SCREENER AVANZADO - INICIALIZANDO")
    print("="*70)

    # Mostrar la leyenda informativa obligatoria
    print_screener_legend()

    all_tickers = load_tickers_from_json(args.file)
    if not all_tickers:
        return
    
    total = len(all_tickers)
    end_idx = min(args.end, total) 
    start_idx = max(0, args.start)
    batch_tickers = all_tickers[start_idx:end_idx]
    
    print(f"[OK] Archivo cargado. Total de empresas en base de datos: {total}")
    print(f"[INFO] Procesando paquete actual: del registro {start_idx} al {end_idx} ({len(batch_tickers)} empresas)\n")

    # Obtener y filtrar datos con metricas completas
    df_valid, missing = fetch_and_filter_data(batch_tickers)

    # Reporte en Terminal
    print("\n" + "="*70)
    print("RESULTADOS DEL ANALISIS Y FILTRADO")
    print("="*70)
    
    if not df_valid.empty:
        print(df_valid.to_markdown(index=False, tablefmt="github"))
    else:
        print("[WARN] No se encontraron datos validos para este paquete.")
    save_results(df_valid, start_idx, end_idx)

    # Reporte de errores / tickers no encontrados
    if missing:
        print("\n" + "-"*70)
        print(f"[ERROR] TICKERS NO ENCONTRADOS / SIN FUNDAMENTALES ({len(missing)}):")
        print("-" *70)
        print(", ".join(missing))

if __name__ == "__main__":
    main()