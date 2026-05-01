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
    QApplication, QComboBox, QHBoxLayout, QLabel, QMainWindow,
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
from .spot_provider import SpotProvider  # noqa: E402


# ---------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------

CORE_TICKERS = gex.CORE_TICKERS
CONTEXT_TICKERS = gex.CONTEXT_TICKERS
ALL_TICKERS = gex.ALL_TICKERS
TOP_STRIKES_N = 5
SPOT_REFRESH_MS = 1000

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

        # Cache of last (levels, expiry, snapshot_dict) per ticker, used
        # to compute deltas to display on the chart.
        self._last_snapshots: Dict[str, dict] = {}

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
        self._ticker_combo.setMinimumWidth(120)
        top.addWidget(self._ticker_combo)

        self._scan_btn = QPushButton("SCAN")
        self._compare_btn = QPushButton("COMPARE")
        self._export_btn = QPushButton("EXPORT LOG")
        for b in (self._scan_btn, self._compare_btn, self._export_btn):
            b.setMinimumWidth(110)
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
        outer.addWidget(splitter, 1)

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
        self._export_btn.clicked.connect(self._on_export)

    def _start_spot_timer(self) -> None:
        self._spot_timer = QTimer(self)
        self._spot_timer.setInterval(SPOT_REFRESH_MS)
        self._spot_timer.timeout.connect(self._refresh_spot)
        self._spot_timer.start()

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

    def _refresh_spot(self) -> None:
        ticker = self._current_ticker()
        if not ticker:
            return
        spot = self._spot.get_spot(ticker)
        if spot is None:
            self._spot_label.setText(f"SPOT: -- ({ticker})")
            self._spot_label.setStyleSheet("color: #888888;")
            return
        self._spot_label.setText(f"SPOT: {spot:.2f} ({ticker})")
        self._spot_label.setStyleSheet("color: #3aa0ff;")
        self._chart.update_spot(spot)

    # ---- chart wiring -----------------------------------------------

    def _render_chart(
        self,
        ticker: str,
        latest: dict,
        prev: Optional[dict],
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
        self._chart.update_levels(
            levels=levels,
            top_strikes=top_strikes,
            asym=asym,
            gamma_flip=gamma_flip,
            deltas=deltas,
            expiry_changed=expiry_changed,
        )

        # Overlay the current live spot if we have one.
        spot = self._spot.get_spot(ticker)
        if spot is None:
            spot = meta.get("spot")
        self._chart.update_spot(spot)

    @staticmethod
    def _extract_levels(meta: dict) -> Dict[str, float]:
        return {
            "CALL_WALL": meta.get("call_wall"),
            "PUT_WALL": meta.get("put_wall"),
            "GAMMA_FLIP": meta.get("gamma_flip"),
            "MAX_GEX": meta.get("max_gex_strike"),
        }

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
