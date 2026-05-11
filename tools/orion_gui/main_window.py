"""ORION GEX GUI main window.

Single-window app: top control bar, terminal-like log on the left,
GEX chart on the right. SCAN refreshes a snapshot for the selected
ticker, COMPARE shows diff between the two most recent snapshots,
EXPORT dumps the log to a text file.
"""

import contextlib
import datetime as dt
import io
import os
import sys
import traceback
from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPalette, QTextCursor
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QPlainTextEdit, QPushButton, QSplitter, QStatusBar, QVBoxLayout,
    QWidget,
)

# Add project root and tools/ to sys.path so we can import sibling modules.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_TOOLS_DIR = os.path.dirname(_THIS_DIR)
_ROOT_DIR = os.path.dirname(_TOOLS_DIR)
for _p in (_ROOT_DIR, _TOOLS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import orion_gex as gex  # noqa: E402

from .chart_widget import GexChartWidget  # noqa: E402
from .order_executor import (  # noqa: E402
    OrionOrderError, OrionOrderExecutor,
)
from .spot_provider import SpotProvider  # noqa: E402


# ---------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------

CORE_TICKERS = gex.CORE_TICKERS
CONTEXT_TICKERS = gex.CONTEXT_TICKERS
ALL_TICKERS = gex.ALL_TICKERS
TOP_STRIKES_N = 5
SPOT_REFRESH_MS = 2000
AUTO_POLL_MS = 10_000  # 10s; conservative wrt yfinance rate-limit

# Order presets: (label, sl_pct). TP is always = SL (1:1 R:R).
ORDER_PRESETS = [
    ("0.5% SL/TP", 0.005),
    ("1.0% SL/TP", 0.010),
]
ORDER_RISK_PCT = 0.01  # 1% of equity at SL

# Fixed price ratios for tickers where MT5 quotes a different
# instrument than the GEX source (yfinance). The ratio converts the
# MT5 quote into the underlying ETF coordinate system used by the
# options chain.
#   SPY = SPX500 / 10   (official US convention, exact)
#   QQQ ~ NAS100 / 41.1 (approximate, drifts ~0.5% over time)
# Stocks (NVDA, V, MSFT, ...) are not listed -> ratio 1.0 (MT5 raw,
# full precision).
FIXED_RATIOS = {
    "SPY": 1.0 / 10.0,
    "QQQ": 1.0 / 41.1,
}

LOG_BG = "#0d0d0d"
LOG_FG = "#d0d0d0"
WINDOW_BG = "#181818"


# ---------------------------------------------------------------------
# Utility: capture stdout from a callable into a string.
# ---------------------------------------------------------------------

def _capture_stdout(func, *args, **kwargs) -> Tuple[str, object]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            result = func(*args, **kwargs)
        except Exception:
            traceback.print_exc()
            result = None
    return buf.getvalue(), result


# ---------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------

class OrionGuiMainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ORION GEX -- Manual Observation Tool")
        self.resize(1500, 900)

        self._spot = SpotProvider()
        self._spot.connect()  # silently fall back to "no live" if it fails

        # Order executor (DEMO-only by design). Logs to logs/orion/orders.jsonl.
        _orders_dir = os.path.join(_ROOT_DIR, "logs", "orion")
        self._executor = OrionOrderExecutor(self._spot, _orders_dir)

        # Cache of last (levels, expiry, snapshot_dict) per ticker, used
        # to compute deltas to display on the chart.
        self._last_snapshots: Dict[str, dict] = {}

        # Per-ticker price-scale ratio (snapshot_spot / mt5_spot).
        # Needed because GEX chains use the underlying ETF/stock
        # (e.g. QQQ ~ 667), while the broker quotes the corresponding
        # CFD/index (e.g. NAS100 ~ 27438). The ratio is recomputed on
        # every SCAN so live MT5 ticks are mapped into the same
        # coordinate system as the snapshot levels.
        self._price_ratio: Dict[str, float] = {}

        self._build_ui()
        self._apply_dark_palette()
        self._wire_signals()
        self._start_spot_timer()

        self._append_log(
            f"=== ORION GEX GUI started {dt.datetime.now():%Y-%m-%d %H:%M:%S}\n"
            f"=== Spot source: {self._spot.status()}\n"
        )

    # ---- UI construction --------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(4)

        # Top bar
        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(QLabel("Ticker:"))
        self._ticker_combo = QComboBox()
        for t in CORE_TICKERS:
            self._ticker_combo.addItem(t)
        self._ticker_combo.insertSeparator(len(CORE_TICKERS))
        for t in CONTEXT_TICKERS:
            self._ticker_combo.addItem(t)
        self._ticker_combo.setMinimumWidth(80)
        top.addWidget(self._ticker_combo)

        self._scan_btn = QPushButton("SCAN")
        self._compare_btn = QPushButton("COMPARE")
        self._auto_btn = QPushButton("AUTO")
        self._auto_btn.setCheckable(True)
        self._auto_btn.setStyleSheet(
            "QPushButton:checked { background: #2a6c2a; color: #ffffff; }"
        )
        self._export_btn = QPushButton("EXPORT LOG")
        for b in (self._scan_btn, self._compare_btn, self._auto_btn,
                  self._export_btn):
            b.setMinimumWidth(60)
            top.addWidget(b)

        # Order controls (BUY / SELL with fixed risk %, dropdown for SL%).
        top.addSpacing(20)
        top.addWidget(QLabel("Risk:"))
        self._risk_combo = QComboBox()
        for label, _pct in ORDER_PRESETS:
            self._risk_combo.addItem(label)
        self._risk_combo.setMinimumWidth(70)
        top.addWidget(self._risk_combo)

        self._buy_btn = QPushButton("BUY")
        self._buy_btn.setStyleSheet(
            "QPushButton { background: #1e5a1e; color: #ffffff; "
            "font-weight: bold; }"
            "QPushButton:disabled { background: #333; color: #666; }"
        )
        self._sell_btn = QPushButton("SELL")
        self._sell_btn.setStyleSheet(
            "QPushButton { background: #6c1e1e; color: #ffffff; "
            "font-weight: bold; }"
            "QPushButton:disabled { background: #333; color: #666; }"
        )
        for b in (self._buy_btn, self._sell_btn):
            b.setMinimumWidth(50)
            top.addWidget(b)

        top.addStretch(1)

        self._mt5_label = QLabel(self._spot.status())
        self._mt5_label.setStyleSheet("color: #aaaaaa;")
        top.addWidget(self._mt5_label)

        self._spot_label = QLabel("SPOT: --")
        f = QFont()
        f.setBold(True)
        f.setPointSize(11)
        self._spot_label.setFont(f)
        self._spot_label.setStyleSheet("color: #3aa0ff;")
        top.addWidget(self._spot_label)

        outer.addLayout(top)

        # Splitter: log left, chart right
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(4)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPointSize(9)
        self._log.setFont(mono)
        self._log.setStyleSheet(
            f"QPlainTextEdit {{ background: {LOG_BG}; color: {LOG_FG}; "
            f"border: 1px solid #333333; }}"
        )
        splitter.addWidget(self._log)

        self._chart = GexChartWidget()
        splitter.addWidget(self._chart)

        splitter.setStretchFactor(0, 35)
        splitter.setStretchFactor(1, 65)
        splitter.setSizes([520, 980])
        splitter.setChildrenCollapsible(True)
        outer.addWidget(splitter, 1)

        # Allow window to shrink aggressively (so it can dock side-by-side
        # with another app). Top bar wraps via horizontal scroll if needed.
        self.setMinimumSize(400, 300)

        self.setStatusBar(QStatusBar())

    def _apply_dark_palette(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        pal = QPalette()
        pal.setColor(QPalette.ColorRole.Window, QColor(WINDOW_BG))
        pal.setColor(QPalette.ColorRole.WindowText, QColor(LOG_FG))
        pal.setColor(QPalette.ColorRole.Base, QColor(LOG_BG))
        pal.setColor(QPalette.ColorRole.Text, QColor(LOG_FG))
        pal.setColor(QPalette.ColorRole.Button, QColor("#252525"))
        pal.setColor(QPalette.ColorRole.ButtonText, QColor(LOG_FG))
        app.setPalette(pal)

    def _wire_signals(self) -> None:
        self._scan_btn.clicked.connect(self._on_scan)
        self._compare_btn.clicked.connect(self._on_compare)
        self._auto_btn.toggled.connect(self._on_auto_toggled)
        self._export_btn.clicked.connect(self._on_export)
        self._buy_btn.clicked.connect(lambda: self._on_order("BUY"))
        self._sell_btn.clicked.connect(lambda: self._on_order("SELL"))
        self._ticker_combo.currentIndexChanged.connect(
            self._on_ticker_changed
        )

    def _start_spot_timer(self) -> None:
        self._spot_timer = QTimer(self)
        self._spot_timer.setInterval(SPOT_REFRESH_MS)
        self._spot_timer.timeout.connect(self._refresh_spot)
        self._spot_timer.start()

        # Polling timer used by AUTO mode (created stopped).
        self._auto_timer = QTimer(self)
        self._auto_timer.setInterval(AUTO_POLL_MS)
        self._auto_timer.timeout.connect(self._auto_tick)

        # In-memory snapshot used by AUTO so we can compute deltas without
        # touching disk. Reset every time AUTO starts.
        self._auto_prev_snapshot: Dict[str, dict] = {}
        # Per-ticker AUTO state (cleared on AUTO ON):
        # _auto_prev_hash: detect "no refresh" of yfinance chain.
        # _auto_prev_imp:  previous GEX impulse (B) for delta.
        # _auto_run:       run length of spot delta in ticks.
        self._auto_prev_hash: Dict[str, str] = {}
        self._auto_prev_imp: Dict[str, float] = {}
        self._auto_run: Dict[str, int] = {}
        # SPY/QQQ prior close cache (fetched once per AUTO session).
        self._auto_index_prev_close: Dict[str, float] = {}

    # ---- handlers ----------------------------------------------------

    def _current_ticker(self) -> str:
        return self._ticker_combo.currentText().strip().upper()

    def _on_scan(self) -> None:
        ticker = self._current_ticker()
        if not ticker:
            return
        self._scan_btn.setEnabled(False)
        try:
            self._scan_ticker(ticker)
        finally:
            self._scan_btn.setEnabled(True)

    def _scan_ticker(self, ticker: str) -> None:
        # Capture orion_gex output into the log.
        text, _ = _capture_stdout(
            gex.process_ticker, ticker,
            expiry=None, do_plot=False, persist=True,
        )
        self._append_log(text + "\n")

        # Load the freshly written snapshot to feed the chart.
        snaps = gex._list_snapshots(ticker)
        if not snaps:
            self._append_log(f"  [WARN] No snapshot persisted for {ticker}.\n")
            return
        latest = gex._load_snapshot(snaps[0][0])
        prev = gex._load_snapshot(snaps[1][0]) if len(snaps) >= 2 else None

        # Write CSV mirrors next to the existing analysis/ files.
        self._write_csv_mirrors(ticker, latest)

        self._render_chart(ticker, latest, prev)
        self._last_snapshots[ticker] = latest

    def _on_compare(self) -> None:
        ticker = self._current_ticker()
        if not ticker:
            return
        text, _ = _capture_stdout(gex.cmd_compare, ticker)
        self._append_log(text + "\n")

        snaps = gex._list_snapshots(ticker)
        if len(snaps) < 2:
            return
        latest = gex._load_snapshot(snaps[0][0])
        prev = gex._load_snapshot(snaps[1][0])
        self._render_chart(ticker, latest, prev)

    def _on_export(self) -> None:
        logs_dir = os.path.join(_ROOT_DIR, "logs", "orion")
        os.makedirs(logs_dir, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(logs_dir, f"gui_session_{stamp}.txt")
        with open(path, "w", encoding="ascii", errors="replace") as f:
            f.write(self._log.toPlainText())
        self._append_log(f"\n=== Exported log to {path}\n")

    # ---- order handlers ---------------------------------------------

    def _on_order(self, side: str) -> None:
        ticker = self._current_ticker()
        if not ticker:
            return

        # Hard guard: DEMO only.
        is_demo, msg = self._executor.is_demo_account()
        if not is_demo:
            QMessageBox.critical(
                self, "ORION order blocked",
                f"Order refused.\n\n{msg}",
            )
            self._append_log(f"  [ORDER] BLOCKED: {msg}\n")
            return

        sl_pct = ORDER_PRESETS[self._risk_combo.currentIndex()][1]
        try:
            plan = self._executor.compute_plan(
                ticker=ticker, side=side,
                sl_pct=sl_pct, risk_pct=ORDER_RISK_PCT,
            )
        except OrionOrderError as exc:
            QMessageBox.warning(
                self, "ORION order rejected",
                f"Cannot prepare order:\n\n{exc}",
            )
            self._append_log(f"  [ORDER] REJECTED ({side} {ticker}): {exc}\n")
            return

        # Confirmation modal with full plan.
        money_at_risk = plan.lots * plan.contract_size * abs(
            plan.entry_price - plan.sl_price
        )
        text = (
            f"{plan.side}  {plan.symbol}  ({plan.ticker})\n"
            f"\n"
            f"Lots:           {plan.lots:g}\n"
            f"Entry (mkt):    {plan.entry_price:.4f}\n"
            f"SL:             {plan.sl_price:.4f}  "
            f"({plan.sl_pct*100:.2f}%)\n"
            f"TP:             {plan.tp_price:.4f}  "
            f"({plan.sl_pct*100:.2f}%, 1:1)\n"
            f"\n"
            f"Equity:         {plan.equity:.2f}\n"
            f"Risk budget:    {plan.risk_money:.2f}  "
            f"({plan.risk_pct*100:.2f}%)\n"
            f"Actual loss@SL: {money_at_risk:.2f}\n"
            f"\n"
            f"Spread:         {plan.spread_price:.4f}  "
            f"({plan.spread_fraction*100:.1f}% of SL distance)\n"
            f"\n"
            f"{plan.notes}"
        )
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(f"Confirm {plan.side} {plan.ticker}")
        box.setText(text)
        box.setStandardButtons(
            QMessageBox.StandardButton.Ok
            | QMessageBox.StandardButton.Cancel
        )
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if box.exec() != QMessageBox.StandardButton.Ok:
            self._append_log(
                f"  [ORDER] cancelled by user ({side} {ticker})\n"
            )
            return

        try:
            result = self._executor.execute(plan, comment=f"ORION_{side}")
        except OrionOrderError as exc:
            QMessageBox.critical(
                self, "ORION order failed",
                f"Order send failed:\n\n{exc}",
            )
            self._append_log(f"  [ORDER] FAILED ({side} {ticker}): {exc}\n")
            return

        status = result.get("status")
        if status == "ok":
            self._append_log(
                f"  [ORDER OK] {side} {plan.symbol} "
                f"vol={result.get('volume')} @ {result.get('price')} "
                f"deal={result.get('deal')}\n"
            )
        else:
            self._append_log(
                f"  [ORDER {status.upper()}] retcode={result.get('retcode')} "
                f"comment={result.get('comment')}\n"
            )

    def _refresh_spot(self) -> None:
        ticker = self._current_ticker()
        if not ticker:
            return
        mt5_sym = self._spot.resolve(ticker)
        ba = self._spot.get_bid_ask(ticker)
        sym_disp = mt5_sym if mt5_sym else ticker
        if ba is None:
            self._spot_label.setText(f"BID/ASK: -- [{sym_disp}]")
            self._spot_label.setStyleSheet("color: #888888;")
            return
        bid_raw, ask_raw = ba
        ratio = self._price_ratio.get(ticker, 1.0)
        bid = bid_raw * ratio
        ask = ask_raw * ratio
        spread = ask - bid
        if abs(ratio - 1.0) < 1e-6:
            self._spot_label.setText(
                f"BID {bid:.2f} / ASK {ask:.2f} (sp {spread:.2f}) [{sym_disp}]"
            )
        else:
            self._spot_label.setText(
                f"BID {bid:.2f} / ASK {ask:.2f} "
                f"(MT5 {bid_raw:.2f}/{ask_raw:.2f} x{ratio:.4f}) [{sym_disp}]"
            )
        self._spot_label.setStyleSheet("color: #3aa0ff;")
        self._chart.update_spot_bidask(bid, ask)

    # ---- chart wiring -----------------------------------------------

    def _render_chart(
        self,
        ticker: str,
        latest: dict,
        prev: Optional[dict],
        preserve_range: bool = False,
    ) -> None:
        meta = latest.get("meta", {})
        levels = self._extract_levels(meta)
        gamma_flip = meta.get("gamma_flip")
        asym = meta.get("asym")

        deltas: Dict[str, Optional[float]] = {}
        expiry_changed = False
        if prev is not None:
            prev_meta = prev.get("meta", {})
            prev_levels = self._extract_levels(prev_meta)
            for k, v in levels.items():
                pv = prev_levels.get(k)
                if v is None or pv is None:
                    deltas[k] = None
                else:
                    deltas[k] = v - pv
            expiry_changed = (
                meta.get("expiry") is not None
                and prev_meta.get("expiry") is not None
                and meta.get("expiry") != prev_meta.get("expiry")
            )

        top_strikes = self._top_strikes_from_snapshot(latest, TOP_STRIKES_N)
        net_gex_map = self._build_net_gex_map(
            latest, prev, levels, top_strikes,
        )
        self._chart.update_levels(
            levels=levels,
            top_strikes=top_strikes,
            asym=asym,
            gamma_flip=gamma_flip,
            deltas=deltas,
            expiry_changed=expiry_changed,
            net_gex_map=net_gex_map,
            preserve_range=preserve_range,
        )

        # Apply fixed ratio if defined for this ticker; otherwise 1.0.
        ratio = FIXED_RATIOS.get(ticker, 1.0)
        prev_ratio = self._price_ratio.get(ticker)
        self._price_ratio[ticker] = ratio
        # Log only on change (avoids spam in AUTO mode).
        if ratio != 1.0 and prev_ratio != ratio:
            self._append_log(
                f"  [ratio] {ticker}: fixed ratio {ratio:.4f} "
                f"(MT5 quote * ratio -> underlying coordinate)\n"
            )

        ba = self._spot.get_bid_ask(ticker)
        snap_spot = meta.get("spot")
        if ba is not None:
            self._chart.update_spot_bidask(ba[0] * ratio, ba[1] * ratio)
        elif snap_spot is not None:
            self._chart.update_spot(snap_spot)

    @staticmethod
    def _extract_levels(meta: dict) -> Dict[str, float]:
        return {
            "CALL_WALL": meta.get("call_wall"),
            "PUT_WALL": meta.get("put_wall"),
            "GAMMA_FLIP": meta.get("gamma_flip"),
            "MAX_GEX": meta.get("max_gex_strike"),
        }

    @staticmethod
    def _profile_net_by_strike(snapshot: dict) -> Dict[float, float]:
        out: Dict[float, float] = {}
        for r in (snapshot.get("gex_profile", []) or []):
            try:
                out[float(r.get("strike"))] = float(r.get("net_gex", 0.0))
            except (TypeError, ValueError):
                continue
        return out

    @classmethod
    def _build_net_gex_map(
        cls,
        latest: dict,
        prev: Optional[dict],
        levels: Dict[str, float],
        top_strikes: List[Tuple[float, float]],
    ) -> Dict[float, Tuple[float, Optional[float]]]:
        """For every strike rendered on the chart, return (current, delta).

        Named levels (CALL_WALL / PUT_WALL / ...) are mapped to the closest
        strike present in the gex_profile (tolerance 0.01). Unnamed top
        strikes use exact match.
        """
        cur_by_strike = cls._profile_net_by_strike(latest)
        prev_by_strike = (
            cls._profile_net_by_strike(prev) if prev is not None else {}
        )
        all_strikes = sorted(cur_by_strike.keys())

        def nearest(price: float) -> Optional[float]:
            if not all_strikes:
                return None
            best = min(all_strikes, key=lambda s: abs(s - price))
            return best if abs(best - price) <= 0.01 else None

        out: Dict[float, Tuple[float, Optional[float]]] = {}

        for name in ("CALL_WALL", "PUT_WALL", "GAMMA_FLIP", "MAX_GEX"):
            price = levels.get(name)
            if price is None:
                continue
            s = nearest(price)
            if s is None:
                continue
            cur = cur_by_strike.get(s)
            if cur is None:
                continue
            pv = prev_by_strike.get(s)
            delta = (cur - pv) if pv is not None else None
            out[price] = (cur, delta)

        for strike, _net in top_strikes:
            cur = cur_by_strike.get(strike)
            if cur is None:
                continue
            pv = prev_by_strike.get(strike)
            delta = (cur - pv) if pv is not None else None
            out[strike] = (cur, delta)

        return out

    @staticmethod
    def _top_strikes_from_snapshot(
        snapshot: dict, n: int
    ) -> List[Tuple[float, float]]:
        profile = snapshot.get("gex_profile", []) or []
        rows = []
        for r in profile:
            try:
                strike = float(r.get("strike"))
                net = float(r.get("net_gex", 0.0))
            except (TypeError, ValueError):
                continue
            rows.append((strike, net))
        rows.sort(key=lambda x: abs(x[1]), reverse=True)
        return rows[:n]

    # ---- CSV mirrors -------------------------------------------------

    def _write_csv_mirrors(self, ticker: str, snapshot: dict) -> None:
        """Write GEX levels + profile CSVs into analysis/ alongside legacy files."""
        analysis_dir = os.path.join(_ROOT_DIR, "analysis")
        os.makedirs(analysis_dir, exist_ok=True)
        meta = snapshot.get("meta", {})
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M")
        date_str = meta.get("date", dt.date.today().isoformat())
        spot = meta.get("spot", 0.0)
        expiry = meta.get("expiry", "")

        # Levels CSV
        lev_path = os.path.join(
            analysis_dir, f"gex_levels_{ticker}_{stamp}.csv"
        )
        with open(lev_path, "w", encoding="ascii") as f:
            f.write("ticker,level,price,spot,expiry,date\n")
            mapping = (
                ("PUT_WALL", "put_wall"),
                ("CALL_WALL", "call_wall"),
                ("GAMMA_FLIP", "gamma_flip"),
                ("MAX_GEX", "max_gex_strike"),
                ("MAX_CALL_OI", "max_call_oi"),
                ("MAX_PUT_OI", "max_put_oi"),
            )
            for label, key in mapping:
                val = meta.get(key)
                if val is None:
                    continue
                f.write(f"{ticker},{label},{val},{spot},{expiry},{date_str}\n")

        # Profile CSV
        prof_path = os.path.join(
            analysis_dir, f"gex_profile_{ticker}_{stamp}.csv"
        )
        with open(prof_path, "w", encoding="ascii") as f:
            f.write(
                "strike,call_oi,put_oi,call_gamma,put_gamma,"
                "call_gex,put_gex,net_gex\n"
            )
            for r in snapshot.get("gex_profile", []) or []:
                f.write(
                    f"{r.get('strike', '')},"
                    f"{r.get('call_oi', '')},"
                    f"{r.get('put_oi', '')},"
                    f"{r.get('call_gamma', '')},"
                    f"{r.get('put_gamma', '')},"
                    f"{r.get('call_gex', '')},"
                    f"{r.get('put_gex', '')},"
                    f"{r.get('net_gex', '')}\n"
                )

    # ---- AUTO mode ---------------------------------------------------

    def _on_auto_toggled(self, checked: bool) -> None:
        if checked:
            ticker = self._current_ticker()
            if not ticker:
                self._auto_btn.setChecked(False)
                return
            self._scan_btn.setEnabled(False)
            self._compare_btn.setEnabled(False)
            self._auto_btn.setText("AUTO ON")
            self._auto_prev_snapshot.clear()
            self._auto_prev_hash.clear()
            self._auto_prev_imp.clear()
            self._auto_run.clear()
            self._auto_index_prev_close.clear()
            self._append_log(
                f"=== AUTO ON [{ticker}] polling every "
                f"{AUTO_POLL_MS // 1000}s, no disk writes\n"
            )
            # Fire one tick immediately, then start the timer.
            self._auto_tick()
            self._auto_timer.start()
        else:
            self._auto_timer.stop()
            self._scan_btn.setEnabled(True)
            self._compare_btn.setEnabled(True)
            self._auto_btn.setText("AUTO")
            self._append_log("=== AUTO OFF\n")

    def _on_ticker_changed(self, *_args) -> None:
        # Cancel AUTO when the ticker changes to avoid scanning a
        # different symbol than what the user just selected.
        if self._auto_btn.isChecked():
            self._auto_btn.setChecked(False)

    def _auto_tick(self) -> None:
        ticker = self._current_ticker()
        if not ticker:
            return
        try:
            snapshot = self._build_snapshot_in_memory(ticker)
        except Exception as exc:
            self._append_log(f"  [AUTO] {ticker} fetch error: {exc}\n")
            return
        if snapshot is None:
            self._append_log(f"  [AUTO] {ticker} skipped (empty chain)\n")
            return
        prev = self._auto_prev_snapshot.get(ticker)
        # First tick auto-ranges; subsequent ticks preserve the user's
        # manual zoom/scroll on the price axis.
        preserve = ticker in self._auto_prev_snapshot
        self._render_chart(ticker, snapshot, prev, preserve_range=preserve)

        # Fixed-width single-line log entry. Columns align vertically so
        # consecutive ticks are easy to scan.
        line = self._format_auto_line(ticker, snapshot, prev)
        self._append_log(line + "\n")
        self._auto_prev_snapshot[ticker] = snapshot

    # ---- AUTO log formatting / helpers -------------------------------

    @staticmethod
    def _snapshot_hash(snapshot: Optional[dict]) -> str:
        """Cheap fingerprint to detect whether yfinance refreshed.

        Combines spot (4 dp) + sum of all OI in the gex_profile. If two
        consecutive snapshots share the same hash, yfinance has not
        served new data and we render '(__)' instead of '(d+0.00)'.
        """
        if snapshot is None:
            return ""
        meta = snapshot.get("meta") or {}
        spot = round(float(meta.get("spot") or 0.0), 4)
        oi_sum = 0.0
        for r in (snapshot.get("gex_profile") or []):
            try:
                oi_sum += float(r.get("call_oi", 0) or 0)
                oi_sum += float(r.get("put_oi", 0) or 0)
            except (TypeError, ValueError):
                pass
        return f"{spot}|{oi_sum:.0f}"

    @classmethod
    def _gex_total(cls, snapshot: Optional[dict]) -> Optional[float]:
        """Total net_gex of the snapshot in raw units."""
        if snapshot is None:
            return None
        prof = cls._profile_net_by_strike(snapshot)
        if not prof:
            return None
        return sum(prof.values())

    @classmethod
    def _gex_impulse(cls, snapshot: Optional[dict]) -> Optional[float]:
        """Sum of net_gex (raw units) for strikes in (spot, call_wall].

        BUY-bias indicator: positive means dealers are accumulating
        gamma above the spot, between the current price and the next
        major resistance. Growing -> resistance acting as magnet.
        """
        if snapshot is None:
            return None
        meta = snapshot.get("meta") or {}
        spot = meta.get("spot")
        cw = meta.get("call_wall")
        if spot is None or cw is None or cw <= spot:
            return None
        prof = cls._profile_net_by_strike(snapshot)
        if not prof:
            return None
        return sum(v for k, v in prof.items() if spot < k <= cw)

    def _index_pct(self, ticker: str) -> Optional[float]:
        """Pct change vs prior close for SPY/QQQ via MT5 spot.

        Prior close is fetched once per AUTO session via yfinance
        (cached). Current price uses the broker BID/ASK with the
        FIXED_RATIO so it matches the underlying ETF coordinate.
        Returns None if MT5 not connected or yfinance lookup failed.
        """
        prev_close = self._auto_index_prev_close.get(ticker)
        if prev_close is None:
            try:
                import yfinance as yf
                hist = yf.Ticker(ticker).history(period="2d", interval="1d")
                if not hist.empty and "Close" in hist.columns:
                    prev_close = float(hist["Close"].iloc[-1])
                    self._auto_index_prev_close[ticker] = prev_close
            except Exception:
                return None
        if prev_close is None or prev_close <= 0:
            return None
        ba = self._spot.get_bid_ask(ticker)
        if ba is None:
            return None
        ratio = FIXED_RATIOS.get(ticker, 1.0)
        mid = (ba[0] + ba[1]) / 2.0 * ratio
        return (mid - prev_close) / prev_close * 100.0

    @staticmethod
    def _scale_gex(val: Optional[float]) -> str:
        """Auto-scale GEX magnitude to B / M / K / raw.

        Signed, 2 decimals, fixed 8-char field so columns stay aligned.
        Examples: '+2.10B  ', '+450.32M', '+12.40K ', '   +832 '.
        """
        if val is None:
            return "   --   "
        a = abs(val)
        if a >= 1e9:
            body = f"{val / 1e9:+.2f}B"
        elif a >= 1e6:
            body = f"{val / 1e6:+.2f}M"
        elif a >= 1e3:
            body = f"{val / 1e3:+.2f}K"
        else:
            body = f"{val:+.0f}"
        return body.rjust(8)

    @classmethod
    def _scale_gex_delta(cls, val: Optional[float]) -> str:
        """'(d+450.32M)' / '(d__     )' fixed 11-char body."""
        if val is None:
            return "(d__     )"
        body = "d" + cls._scale_gex(val).strip()
        return "(" + body.ljust(8) + ")"

    @staticmethod
    def _fmt_delta(val: Optional[float], unit: str, width: int) -> str:
        """'(d+0.30)' / '(__   )' rendered to a fixed width."""
        if val is None:
            return ("(" + "__".ljust(width - 3) + ")").rjust(width + 1)
        if unit == "%":
            body = f"d{val:+.2f}%"
        else:
            body = f"d{val:+.2f}"
        return ("(" + body + ")").rjust(width + 2)

    @staticmethod
    def _fmt_pct(val: Optional[float], width: int = 8) -> str:
        if val is None:
            return "  --    ".rjust(width)
        return f"{val:+.3f}%".rjust(width)

    def _update_run(self, ticker: str, dspot_pct: Optional[float]) -> int:
        """Update consecutive-direction counter for spot delta.

        Threshold: 0.02% of spot. Below threshold (incl. None) resets
        run to 0 only if it actually breaks direction; if the snapshot
        did not refresh (dspot_pct is None) we keep the previous run.
        """
        prev_run = self._auto_run.get(ticker, 0)
        if dspot_pct is None:
            return prev_run  # no refresh -> keep
        thr = 0.02
        if dspot_pct >= thr:
            new_run = prev_run + 1 if prev_run >= 0 else 1
        elif dspot_pct <= -thr:
            new_run = prev_run - 1 if prev_run <= 0 else -1
        else:
            new_run = 0
        self._auto_run[ticker] = new_run
        return new_run

    def _format_auto_line(
        self, ticker: str, snapshot: dict, prev: Optional[dict],
    ) -> str:
        import datetime as _dt
        ts = _dt.datetime.now().strftime("%H:%M:%S")
        meta = snapshot.get("meta") or {}
        spot = meta.get("spot")
        prev_meta = (prev or {}).get("meta") or {}
        prev_spot = prev_meta.get("spot")

        # Detect whether yfinance refreshed.
        cur_hash = self._snapshot_hash(snapshot)
        prev_hash = self._auto_prev_hash.get(ticker, "")
        refreshed = (cur_hash != prev_hash) and bool(prev_hash)
        first_tick = not bool(prev_hash)
        self._auto_prev_hash[ticker] = cur_hash

        # Spot + delta (only meaningful when refreshed).
        if spot is None:
            spot_str = "  --  "
        else:
            spot_str = f"{spot:>7.2f}"
        if refreshed and spot is not None and prev_spot is not None:
            dspot = spot - prev_spot
            dspot_pct = dspot / prev_spot * 100.0 if prev_spot else None
            d_spot_str = self._fmt_delta(dspot, "", 6)
        else:
            dspot_pct = None
            d_spot_str = self._fmt_delta(None, "", 6)

        # NetGEX total + delta (auto-scaled to B/M/K/raw).
        gex_v = self._gex_total(snapshot)
        gex_v_prev = self._gex_total(prev) if refreshed else None
        gex_str = self._scale_gex(gex_v)
        if gex_v is not None and gex_v_prev is not None:
            d_gex_str = self._scale_gex_delta(gex_v - gex_v_prev)
        else:
            d_gex_str = self._scale_gex_delta(None)

        # GEX impulse (spot, call_wall], auto-scaled.
        imp = self._gex_impulse(snapshot)
        imp_str = self._scale_gex(imp)
        if imp is None:
            d_imp_str = self._scale_gex_delta(None)
        else:
            if refreshed:
                imp_prev = self._auto_prev_imp.get(ticker)
                d_imp_str = (
                    self._scale_gex_delta(imp - imp_prev)
                    if imp_prev is not None
                    else self._scale_gex_delta(None)
                )
                self._auto_prev_imp[ticker] = imp
            else:
                d_imp_str = self._scale_gex_delta(None)
                if first_tick:
                    self._auto_prev_imp[ticker] = imp

        # SPY / QQQ context (% vs prior close, MT5 spot).
        spy_pct = self._index_pct("SPY")
        qqq_pct = self._index_pct("QQQ")
        spy_str = self._fmt_pct(spy_pct)
        qqq_str = self._fmt_pct(qqq_pct)

        # Run length of spot delta.
        run = self._update_run(ticker, dspot_pct)
        run_str = f"r{run:+d}" if run != 0 else "r 0"

        return (
            f"  [{ts}] {ticker:<5s} {spot_str} {d_spot_str} "
            f"GEX {gex_str} {d_gex_str} "
            f"IMP {imp_str} {d_imp_str} "
            f"SPY {spy_str} QQQ {qqq_str} {run_str}"
        )

    def _build_snapshot_in_memory(self, ticker: str) -> Optional[dict]:
        """Replicate process_ticker + append_history but RAM-only.

        Returns a dict shaped like the on-disk snapshot
        ({"meta": {...}, "gex_profile": [...]}) so it can feed
        _render_chart unchanged. No file I/O.
        """
        try:
            calls, puts, spot, chosen_exp, _ = gex.fetch_options_data(
                ticker, None,
            )
        except Exception:
            raise
        import datetime as _dt
        exp_date = _dt.datetime.strptime(chosen_exp, "%Y-%m-%d").date()
        T = max((exp_date - _dt.date.today()).days, 1) / 365.0
        gex_df = gex.calc_gex_per_strike(calls, puts, spot, T)
        levels = gex.identify_levels(gex_df, spot)
        analysis = gex.analyze_levels(gex_df, spot, levels)

        total_oi = (
            gex._safe_int(calls["openInterest"].sum())
            + gex._safe_int(puts["openInterest"].sum())
        )
        if total_oi == 0:
            # Empty chain (market closed). Skip silently in AUTO.
            return None

        meta = {
            "date": _dt.date.today().isoformat(),
            "ticker": ticker,
            "spot": round(spot, 4),
            "expiry": chosen_exp,
            "call_wall": levels.get("CALL_WALL"),
            "put_wall": levels.get("PUT_WALL"),
            "gamma_flip": levels.get("GAMMA_FLIP"),
            "max_gex_strike": levels.get("MAX_GEX"),
            "max_call_oi": levels.get("MAX_CALL_OI"),
            "max_put_oi": levels.get("MAX_PUT_OI"),
            "asym": analysis.get("asym"),
        }
        return {
            "meta": meta,
            "timestamp": _dt.datetime.now().isoformat(timespec="seconds"),
            "gex_profile": gex_df.to_dict(orient="records"),
        }

    # ---- log helpers -------------------------------------------------

    def _append_log(self, text: str) -> None:
        self._log.moveCursor(QTextCursor.MoveOperation.End)
        self._log.insertPlainText(text)
        self._log.moveCursor(QTextCursor.MoveOperation.End)

    # ---- close -------------------------------------------------------

    def closeEvent(self, event):  # noqa: N802 (Qt API)
        try:
            self._spot.shutdown()
        except Exception:
            pass
        super().closeEvent(event)
