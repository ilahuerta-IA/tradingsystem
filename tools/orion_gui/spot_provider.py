"""Live spot provider backed by MetaTrader 5.

Attaches to a running MT5 terminal (no login required if the terminal
is already authenticated). Resolves broker-specific symbol names by
scanning the available symbol set and matching common patterns.

If MT5 is unavailable or the ticker is not found in the broker's
symbol set, get_spot() returns None and status() reports it. The GUI
will then fall back to displaying the last SCAN spot without live
updates.

Public API:
    SpotProvider().connect() -> bool
    SpotProvider().resolve(ticker) -> str or None
    SpotProvider().get_spot(ticker) -> float or None
    SpotProvider().status() -> str
    SpotProvider().shutdown() -> None
"""

from typing import Dict, Optional


# Manual ticker -> MT5 symbol map (broker-specific).
# Edit this table when adding tickers if the broker uses
# descriptive names instead of standard tickers.
TICKER_TO_MT5 = {
    "GOOGL": "Alphabet Inc A",
    "MSFT":  "Microsoft",
    "NVDA":  "Nvidia",
    "SPY":   "SPX500",
    "QQQ":   "NAS100",
    "JPM":   "J.P. Morgan",
    "V":     "Visa",
    "ALB":   "Albermarle",
    "WDC":   "Western Digital",
    "GS":    "Goldman Sachs",
    "TSLA":  "Tesla Motors",
    "AMZN":  "Amazon",
    "META":  "Meta Platforms Inc",
    "DAX":   "GER40",
}


class SpotProvider:
    """Thin wrapper over MetaTrader5 module for live spot retrieval."""

    def __init__(self):
        self._mt5 = None
        self._connected = False
        self._symbol_map: Dict[str, str] = {}
        self._status_msg = "Not connected"

    # ---- lifecycle ----------------------------------------------------

    def connect(self) -> bool:
        """Initialize MT5 module. Returns True on success."""
        try:
            import MetaTrader5 as mt5
        except ImportError:
            self._status_msg = "MetaTrader5 module not installed"
            return False
        self._mt5 = mt5
        if not mt5.initialize():
            err = mt5.last_error()
            self._status_msg = f"MT5 init failed: {err}"
            self._mt5 = None
            return False
        info = mt5.terminal_info()
        if info is None:
            self._status_msg = "MT5 terminal_info unavailable"
            self._mt5 = None
            return False
        self._connected = True
        self._status_msg = "MT5 connected"
        return True

    def shutdown(self) -> None:
        if self._mt5 is not None:
            try:
                self._mt5.shutdown()
            except Exception:
                pass
        self._mt5 = None
        self._connected = False

    # ---- symbol resolution -------------------------------------------

    def resolve(self, ticker: str) -> Optional[str]:
        """Find the broker symbol matching a generic ticker.

        Resolution order:
          1. Manual override table TICKER_TO_MT5.
          2. Exact match against broker symbol set.
          3. Common suffix patterns (.US, .NAS, ...).
          4. Prefix scan over broker symbols.
        Result is cached so repeated lookups are cheap.
        """
        if not self._connected or self._mt5 is None:
            return None
        ticker = ticker.upper().strip()
        if ticker in self._symbol_map:
            return self._symbol_map[ticker]

        all_symbols = self._mt5.symbols_get()
        if all_symbols is None:
            return None
        names = {s.name for s in all_symbols}

        chosen = None

        # 1. Manual override.
        manual = TICKER_TO_MT5.get(ticker)
        if manual is not None and manual in names:
            chosen = manual

        # 2/3. Exact + suffixes.
        if chosen is None:
            candidates = [ticker]
            candidates += [f"{ticker}{sfx}" for sfx in
                           (".US", ".NAS", ".NYS", "_US", "_NAS", "us")]
            for cand in candidates:
                if cand in names:
                    chosen = cand
                    break

        # 4. Prefix scan.
        if chosen is None:
            for name in sorted(names):
                up = name.upper()
                if up.startswith(ticker + ".") or up.startswith(ticker + "_"):
                    chosen = name
                    break

        if chosen is None:
            return None

        # Ensure symbol is selected (visible in Market Watch).
        try:
            self._mt5.symbol_select(chosen, True)
        except Exception:
            pass
        self._symbol_map[ticker] = chosen
        return chosen

    # ---- queries -----------------------------------------------------

    def get_spot(self, ticker: str) -> Optional[float]:
        """Return mid price for ticker, or None if unavailable."""
        ba = self.get_bid_ask(ticker)
        if ba is None:
            return None
        bid, ask = ba
        return (bid + ask) / 2.0

    def get_bid_ask(self, ticker: str) -> Optional[tuple]:
        """Return (bid, ask) tuple for ticker, or None if unavailable."""
        if not self._connected or self._mt5 is None:
            return None
        symbol = self.resolve(ticker)
        if symbol is None:
            return None
        tick = self._mt5.symbol_info_tick(symbol)
        if tick is None:
            return None
        if tick.bid and tick.ask:
            return (float(tick.bid), float(tick.ask))
        if tick.last and tick.last > 0:
            v = float(tick.last)
            return (v, v)
        return None

    def status(self) -> str:
        return self._status_msg
