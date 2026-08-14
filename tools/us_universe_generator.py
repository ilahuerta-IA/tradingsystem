r"""
GENERADOR DE UNIVERSOS USA PARA LYNCH SCREENER

Fuentes:
  - NASDAQ: directorio oficial Nasdaq Trader.
  - Russell 2000: posiciones actuales del ETF IWM de iShares. IWM es un proxy
    publico del indice; la composicion oficial de FTSE Russell es licenciada.

PowerShell examples (run from the TradingSystem directory):

  Generate both universes:
    python .\tools\us_universe_generator.py --universe all

  Generate NASDAQ only:
    python .\tools\us_universe_generator.py --universe nasdaq

  Generate Russell 2000 proxy only:
    python .\tools\us_universe_generator.py --universe russell2000

Generated files:
  data\nasdaq_listed.json
  data\russell_2000_iwm.json

Analyze generated files:
  python .\tools\lynch_screener.py --file .\data\nasdaq_listed.json --start 0 --end 50
  python .\tools\lynch_screener.py --file .\data\russell_2000_iwm.json --start 0 --end 50
"""

import argparse
import csv
import io
import json
import re
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

NASDAQ_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
RUSSELL_2000_URL = (
    "https://www.ishares.com/us/products/239710/"
    "ishares-russell-2000-etf/latest-holdings.csv"
)
USER_AGENT = "TradingSystem universe generator/1.0"

NON_EQUITY_NAME_MARKERS = (
    " - Warrant",
    " - Warrants",
    " - Unit",
    " - Units",
    " - Right",
    " - Rights",
    "Preferred Stock",
    "Preference Share",
    "Senior Notes",
    "Subordinated Notes",
    "Debentures",
    "Closed End Fund",
)
SPAC_NAME_MARKERS = (
    "Acquisition Corp",
    "Acquisition Company",
    "Blank Check",
)


def create_session() -> requests.Session:
    """Crea una sesion HTTP con reintentos para errores transitorios."""
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def download_text(session: requests.Session, url: str) -> str:
    """Descarga texto y rechaza respuestas HTML o vacias."""
    response = session.get(url, timeout=45)
    response.raise_for_status()
    text = response.content.decode("utf-8-sig", errors="strict")
    beginning = text.lstrip()[:200].lower()
    if not text.strip() or beginning.startswith("<!doctype html") or beginning.startswith("<html"):
        raise ValueError(f"La fuente no devolvio datos tabulares: {url}")
    return text


def normalize_yahoo_symbol(symbol: str) -> str:
    """Convierte la notacion de clases con punto al formato usado por Yahoo."""
    return symbol.strip().upper().replace(".", "-")


def normalize_security_name(name: str) -> str:
    """Reduce un nombre para comparar la misma accion entre proveedores."""
    normalized = name.upper().replace("&", " AND ")
    for marker in ("COMMON STOCK", "COMMON SHARES", "ORDINARY SHARES", "(DE)"):
        normalized = normalized.replace(marker, " ")
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", normalized).split())


def find_header_line(text: str, required_columns: set[str], delimiter: str) -> int:
    """Localiza una cabecera por sus columnas para tolerar preambulos variables."""
    for index, line in enumerate(text.splitlines()):
        columns = {column.strip().strip('"') for column in line.split(delimiter)}
        if required_columns.issubset(columns):
            return index
    raise ValueError(f"No se encontro la cabecera esperada: {sorted(required_columns)}")


def is_operating_equity(name: str) -> bool:
    """Descarta instrumentos no accionarios y SPAC sin negocio operativo."""
    return not any(marker.lower() in name.lower() for marker in NON_EQUITY_NAME_MARKERS + SPAC_NAME_MARKERS)


def build_symbol_resolver(nasdaq_text: str, other_listed_text: str) -> tuple[set[str], dict[str, str]]:
    """Crea indices de simbolos oficiales y nombres unicos para resolver clases."""
    official_records = []

    nasdaq_header = find_header_line(nasdaq_text, {"Symbol", "Security Name", "Test Issue", "ETF"}, "|")
    nasdaq_reader = csv.DictReader(
        io.StringIO("\n".join(nasdaq_text.splitlines()[nasdaq_header:])),
        delimiter="|",
    )
    for row in nasdaq_reader:
        if row.get("Test Issue") == "N" and row.get("ETF") == "N":
            official_records.append((row.get("Symbol", ""), row.get("Security Name", "")))

    other_header = find_header_line(
        other_listed_text,
        {"ACT Symbol", "Security Name", "Test Issue", "ETF"},
        "|",
    )
    other_reader = csv.DictReader(
        io.StringIO("\n".join(other_listed_text.splitlines()[other_header:])),
        delimiter="|",
    )
    for row in other_reader:
        if row.get("Test Issue") == "N" and row.get("ETF") == "N":
            official_records.append((row.get("ACT Symbol", ""), row.get("Security Name", "")))

    official_symbols = set()
    symbols_by_name = {}
    ambiguous_names = set()
    for source_symbol, name in official_records:
        if not source_symbol or not name:
            continue
        symbol = normalize_yahoo_symbol(source_symbol)
        official_symbols.add(symbol)
        name_key = normalize_security_name(name)
        if name_key in symbols_by_name and symbols_by_name[name_key] != symbol:
            ambiguous_names.add(name_key)
        else:
            symbols_by_name[name_key] = symbol

    for name_key in ambiguous_names:
        symbols_by_name.pop(name_key, None)
    return official_symbols, symbols_by_name


def parse_nasdaq(text: str) -> list[dict]:
    """Extrae acciones operativas del directorio oficial de Nasdaq."""
    header_line = find_header_line(
        text,
        {"Symbol", "Security Name", "Test Issue", "Financial Status", "ETF"},
        "|",
    )
    reader = csv.DictReader(io.StringIO("\n".join(text.splitlines()[header_line:])), delimiter="|")
    records = []
    seen = set()
    for row in reader:
        source_symbol = (row.get("Symbol") or "").strip()
        name = (row.get("Security Name") or "").strip()
        if not source_symbol or source_symbol == "File Creation Time":
            continue
        if row.get("Test Issue") != "N" or row.get("ETF") != "N":
            continue
        if row.get("Financial Status") != "N" or not is_operating_equity(name):
            continue
        symbol = normalize_yahoo_symbol(source_symbol)
        if symbol in seen:
            continue
        seen.add(symbol)
        records.append(
            {
                "symbol": symbol,
                "name": name,
                "sector": "N/A",
                "exchange": "NASDAQ",
                "source": "Nasdaq Trader Symbol Directory",
                "source_symbol": source_symbol,
            }
        )
    return records


def parse_russell_2000(
    text: str,
    official_symbols: set[str] | None = None,
    symbols_by_name: dict[str, str] | None = None,
) -> list[dict]:
    """Extrae posiciones de renta variable del ETF IWM."""
    header_line = find_header_line(
        text,
        {"Ticker", "Name", "Sector", "Asset Class", "Exchange", "Currency"},
        ",",
    )
    reader = csv.DictReader(io.StringIO("\n".join(text.splitlines()[header_line:])))
    records = []
    seen = set()
    for row in reader:
        source_symbol = (row.get("Ticker") or "").strip()
        name = (row.get("Name") or "").strip()
        if not source_symbol or source_symbol == "-" or row.get("Asset Class") != "Equity":
            continue
        if not is_operating_equity(name):
            continue
        symbol = normalize_yahoo_symbol(source_symbol)
        resolution = "source"
        if official_symbols is not None and symbol not in official_symbols and symbols_by_name is not None:
            resolved_symbol = symbols_by_name.get(normalize_security_name(name))
            if resolved_symbol:
                symbol = resolved_symbol
                resolution = "official_name_match"
        if symbol in seen:
            continue
        seen.add(symbol)
        records.append(
            {
                "symbol": symbol,
                "name": name,
                "sector": (row.get("Sector") or "N/A").strip() or "N/A",
                "exchange": (row.get("Exchange") or "N/A").strip() or "N/A",
                "currency": (row.get("Currency") or "N/A").strip() or "N/A",
                "weight": (row.get("Weight (%)") or "N/A").strip() or "N/A",
                "source": "iShares Russell 2000 ETF (IWM) holdings",
                "source_symbol": source_symbol,
                "symbol_resolution": resolution,
            }
        )
    return records


def save_json(records: list[dict], output_path: Path) -> None:
    """Guarda un universo compatible con lynch_screener.py."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(records, file, ensure_ascii=False, indent=4)
        file.write("\n")
    print(f"[OK] {len(records)} activos guardados en: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera universos NASDAQ y Russell 2000 para Lynch Screener")
    parser.add_argument(
        "--universe",
        choices=("nasdaq", "russell2000", "all"),
        default="all",
        help="Universo que se descargara (por defecto: all)",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("data"), help="Directorio de salida JSON")
    args = parser.parse_args()

    session = create_session()
    nasdaq_text = None
    if args.universe in {"nasdaq", "all"}:
        print("[INFO] Descargando directorio oficial NASDAQ...")
        nasdaq_text = download_text(session, NASDAQ_URL)
        nasdaq = parse_nasdaq(nasdaq_text)
        if not nasdaq:
            raise RuntimeError("La fuente NASDAQ no produjo ningun activo")
        save_json(nasdaq, args.output_dir / "nasdaq_listed.json")

    if args.universe in {"russell2000", "all"}:
        print("[INFO] Descargando posiciones de IWM (proxy Russell 2000)...")
        if nasdaq_text is None:
            nasdaq_text = download_text(session, NASDAQ_URL)
        other_listed_text = download_text(session, OTHER_LISTED_URL)
        official_symbols, symbols_by_name = build_symbol_resolver(nasdaq_text, other_listed_text)
        russell = parse_russell_2000(
            download_text(session, RUSSELL_2000_URL),
            official_symbols,
            symbols_by_name,
        )
        if not russell:
            raise RuntimeError("La fuente IWM no produjo ningun activo")
        save_json(russell, args.output_dir / "russell_2000_iwm.json")


if __name__ == "__main__":
    main()
