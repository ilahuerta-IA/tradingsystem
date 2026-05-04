"""Pyqtgraph chart widget for ORION GEX GUI.

Displays a dark, time-less chart with horizontal lines for each GEX
level. Y axis is price (right-hand side, MT5-like); X axis is hidden.
Left-click drag on the price axis scales the price range.

Visual style is intentionally minimal and matches MT5:
  - Lines are 1 px thin; the exact price is read from the right axis.
  - Each line carries a small "tag" label anchored to the right edge
    showing "NAME price (delta)".
  - No grid, no x axis, dark background.

Public API:
    GexChartWidget(parent=None)
        update_levels(levels: dict, top_strikes: list[(strike, net_gex)],
                      asym: float, gamma_flip: float or None,
                      deltas: dict, expiry_changed: bool)
        update_spot(spot: float)
        clear_levels()
"""

from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QPen
import pyqtgraph as pg


# Visual configuration ------------------------------------------------

BG_COLOR = "#0d0d0d"
FG_COLOR = "#d0d0d0"

ASYM_FONT_SIZE = 12
LABEL_FONT_SIZE = 8
LINE_WIDTH = 1
STRIKE_LINE_WIDTH = 1

# Color per level (line + label tag).
LEVEL_STYLES = {
    "SPOT":       {"color": "#3aa0ff", "style": Qt.PenStyle.SolidLine},
    "BID":        {"color": "#2266aa", "style": Qt.PenStyle.SolidLine},
    "ASK":        {"color": "#66bbff", "style": Qt.PenStyle.SolidLine},
    "CALL_WALL":  {"color": "#22dd55", "style": Qt.PenStyle.SolidLine},
    "PUT_WALL":   {"color": "#ee3344", "style": Qt.PenStyle.SolidLine},
    "GAMMA_FLIP": {"color": "#ffcc33", "style": Qt.PenStyle.DashLine},
    "MAX_GEX":    {"color": "#33ddee", "style": Qt.PenStyle.DotLine},
}


# Custom Y axis with left-drag scale (MT5-like) -----------------------

class PriceAxisItem(pg.AxisItem):
    """Y axis that scales price range when dragged with left button."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._last_y = None

    def mouseDragEvent(self, ev):
        ev.accept()
        if ev.button() != Qt.MouseButton.LeftButton:
            self._last_y = None
            return
        if ev.isStart():
            self._last_y = ev.pos().y()
            return
        if ev.isFinish():
            self._last_y = None
            return
        if self._last_y is None:
            return
        dy = ev.pos().y() - self._last_y
        self._last_y = ev.pos().y()
        factor = 1.0 + dy * 0.005
        factor = max(0.2, min(5.0, factor))
        vb = self.linkedView()
        if vb is not None:
            vb.scaleBy(y=factor, x=1.0)


# Helper: build an InfiniteLine with an embedded right-anchored label.

def _make_line(price: float, color: str, style, width: int,
               text: str) -> pg.InfiniteLine:
    pen = QPen(QColor(color))
    pen.setWidth(width)
    pen.setStyle(style)
    pen.setCosmetic(True)
    label_opts = {
        "position": 1.0,                 # right-edge "tag"
        "color": color,
        "movable": False,
        "fill": (13, 13, 13, 200),       # dark fill so text is readable
        "border": pg.mkPen(color, width=1),
        "anchors": [(1, 0.5), (1, 0.5)],
    }
    line = pg.InfiniteLine(
        pos=price,
        angle=0,
        pen=pen,
        label=text,
        labelOpts=label_opts,
    )
    if line.label is not None:
        f = QFont()
        f.setPointSize(LABEL_FONT_SIZE)
        f.setBold(True)
        line.label.textItem.setFont(f)
    return line


# Main chart widget ----------------------------------------------------

class GexChartWidget(pg.PlotWidget):

    def __init__(self, parent=None):
        right_axis = PriceAxisItem(orientation="right")
        super().__init__(parent=parent, axisItems={"right": right_axis})

        self.setBackground(BG_COLOR)
        self.showAxis("left", False)
        self.showAxis("right", True)
        self.showAxis("bottom", False)
        self.getAxis("right").setPen(pg.mkPen(FG_COLOR))
        self.getAxis("right").setTextPen(pg.mkPen(FG_COLOR))

        self.setMouseEnabled(x=False, y=True)
        self.hideButtons()
        self.showGrid(x=False, y=False)
        self.getPlotItem().getViewBox().setDefaultPadding(0.02)

        self._items: List[pg.GraphicsObject] = []
        self._spot_line: Optional[pg.InfiniteLine] = None
        self._bid_line: Optional[pg.InfiniteLine] = None
        self._ask_line: Optional[pg.InfiniteLine] = None
        self._spread_region: Optional[pg.LinearRegionItem] = None

        # Overlay labels (asymmetry top-right, expiry-changed top-left).
        self._asym_label = pg.TextItem("ASYM --", anchor=(1, 0))
        f = QFont()
        f.setPointSize(ASYM_FONT_SIZE)
        f.setBold(True)
        self._asym_label.setFont(f)
        self.addItem(self._asym_label, ignoreBounds=True)

        self._expiry_label = pg.TextItem("", anchor=(0, 0))
        self._expiry_label.setColor(QColor("#ee3344"))
        ef = QFont()
        ef.setPointSize(ASYM_FONT_SIZE)
        ef.setBold(True)
        self._expiry_label.setFont(ef)
        self.addItem(self._expiry_label, ignoreBounds=True)

        vb = self.getViewBox()
        if vb is not None:
            vb.sigRangeChanged.connect(self._reposition_overlay_labels)

    # ---- public API --------------------------------------------------

    def clear_levels(self) -> None:
        for item in self._items:
            try:
                self.removeItem(item)
            except Exception:
                pass
        self._items = []
        for attr in ("_spot_line", "_bid_line", "_ask_line", "_spread_region"):
            obj = getattr(self, attr, None)
            if obj is not None:
                try:
                    self.removeItem(obj)
                except Exception:
                    pass
                setattr(self, attr, None)

    def update_levels(
        self,
        levels: Dict[str, float],
        top_strikes: List[Tuple[float, float]],
        asym: Optional[float],
        gamma_flip: Optional[float],
        deltas: Dict[str, Optional[float]],
        expiry_changed: bool,
        net_gex_map: Optional[Dict[float, Tuple[float, Optional[float]]]] = None,
        preserve_range: bool = False,
    ) -> None:
        """Render levels.

        net_gex_map: optional {strike -> (current_net_gex, delta_or_None)}.
        When provided, each line tag is prefixed with the net GEX value
        and the change vs the previous snapshot.
        preserve_range: when True, do NOT auto-range the Y axis. Used by
        AUTO mode so the user's manual zoom/scroll survives polling.
        """
        self.clear_levels()
        nmap = net_gex_map or {}

        for name in ("CALL_WALL", "PUT_WALL", "GAMMA_FLIP", "MAX_GEX"):
            price = levels.get(name)
            if price is None:
                continue
            self._add_named_level(
                name, price, deltas.get(name), nmap.get(price),
            )

        named_prices = {levels.get(n) for n in
                        ("CALL_WALL", "PUT_WALL", "GAMMA_FLIP", "MAX_GEX")}
        for strike, _net in top_strikes:
            if strike in named_prices:
                continue
            self._add_strike_line(strike, gamma_flip, nmap.get(strike))

        if asym is None:
            self._asym_label.setText("ASYM --")
            self._asym_label.setColor(QColor("#888888"))
        else:
            color = "#888888"
            if asym >= 1.5:
                color = "#22dd55"
            elif asym <= 0.67:
                color = "#ee3344"
            elif asym >= 1.0:
                color = "#88dd88"
            else:
                color = "#dd8888"
            self._asym_label.setText(f"ASYM {asym:.2f}")
            self._asym_label.setColor(QColor(color))

        self._expiry_label.setText("EXPIRY CHANGED" if expiry_changed else "")

        if not preserve_range:
            self._auto_range(levels, top_strikes)
        self._reposition_overlay_labels()

    def update_spot(self, spot: Optional[float]) -> None:
        """Update the single mid SPOT line (used when bid/ask unavailable)."""
        if spot is None:
            return
        text = f"SPOT {spot:.2f}"
        style = LEVEL_STYLES["SPOT"]
        if self._spot_line is None:
            self._spot_line = _make_line(
                spot, style["color"], style["style"],
                LINE_WIDTH, text,
            )
            self.addItem(self._spot_line)
        else:
            self._spot_line.setValue(spot)
            if self._spot_line.label is not None:
                self._spot_line.label.setText(text)

    def update_spot_bidask(
        self, bid: Optional[float], ask: Optional[float]
    ) -> None:
        """Render bid + ask as two thin lines with a shaded spread region."""
        if bid is None or ask is None:
            return
        if bid > ask:
            bid, ask = ask, bid
        spread = ask - bid

        bid_text = f"BID {bid:.2f}"
        ask_text = f"ASK {ask:.2f} (sp {spread:.2f})"
        bs = LEVEL_STYLES["BID"]
        as_ = LEVEL_STYLES["ASK"]

        # Drop a single SPOT line if it was created earlier.
        if self._spot_line is not None:
            try:
                self.removeItem(self._spot_line)
            except Exception:
                pass
            self._spot_line = None

        if self._bid_line is None:
            self._bid_line = _make_line(
                bid, bs["color"], bs["style"], LINE_WIDTH, bid_text,
            )
            self.addItem(self._bid_line)
        else:
            self._bid_line.setValue(bid)
            if self._bid_line.label is not None:
                self._bid_line.label.setText(bid_text)

        if self._ask_line is None:
            self._ask_line = _make_line(
                ask, as_["color"], as_["style"], LINE_WIDTH, ask_text,
            )
            self.addItem(self._ask_line)
        else:
            self._ask_line.setValue(ask)
            if self._ask_line.label is not None:
                self._ask_line.label.setText(ask_text)

        # Shaded horizontal band between bid and ask.
        brush = pg.mkBrush(58, 160, 255, 40)
        if self._spread_region is None:
            self._spread_region = pg.LinearRegionItem(
                values=(bid, ask),
                orientation="horizontal",
                brush=brush,
                movable=False,
            )
            self._spread_region.setZValue(-10)
            self.addItem(self._spread_region)
        else:
            self._spread_region.setRegion((bid, ask))

    # ---- internal helpers --------------------------------------------

    def _add_named_level(
        self, name: str, price: float, delta: Optional[float],
        net_gex_pair: Optional[Tuple[float, Optional[float]]] = None,
    ) -> None:
        style = LEVEL_STYLES[name]
        delta_str = self._fmt_delta(delta)
        prefix = self._fmt_net_gex_prefix(net_gex_pair)
        text = f"{prefix}{name} {price:.2f} {delta_str}".rstrip()
        line = _make_line(
            price, style["color"], style["style"], LINE_WIDTH, text,
        )
        self.addItem(line)
        self._items.append(line)

    def _add_strike_line(
        self, strike: float, gamma_flip: Optional[float],
        net_gex_pair: Optional[Tuple[float, Optional[float]]] = None,
    ) -> None:
        if gamma_flip is None:
            color = "#888888"
        elif strike >= gamma_flip:
            color = "#226633"
        else:
            color = "#662233"
        prefix = self._fmt_net_gex_prefix(net_gex_pair)
        text = f"{prefix}{strike:.2f}"
        line = _make_line(
            strike, color, Qt.PenStyle.DashLine,
            STRIKE_LINE_WIDTH, text,
        )
        self.addItem(line)
        self._items.append(line)

    @staticmethod
    def _fmt_delta(delta: Optional[float]) -> str:
        if delta is None:
            return ""
        if abs(delta) < 1e-9:
            return "(==)"
        sign = "+" if delta > 0 else ""
        return f"({sign}{delta:.2f})"

    @staticmethod
    def _fmt_net_gex_prefix(
        pair: Optional[Tuple[float, Optional[float]]]
    ) -> str:
        """Format the leading '[GEX (delta)] ' chunk for the line tag."""
        if pair is None:
            return ""
        cur, delta = pair
        if cur is None:
            return ""
        cur_s = GexChartWidget._fmt_si(cur)
        if delta is None:
            return f"[{cur_s}] "
        if abs(delta) < 1e-9:
            return f"[{cur_s} (==)] "
        return f"[{cur_s} ({GexChartWidget._fmt_si(delta)})] "

    @staticmethod
    def _fmt_si(x: float) -> str:
        """Compact +/- value with SI suffix (K/M/B)."""
        ax = abs(x)
        sign = "+" if x >= 0 else "-"
        if ax < 1_000:
            return f"{sign}{ax:.0f}"
        if ax < 1_000_000:
            return f"{sign}{ax/1_000:.2f}K"
        if ax < 1_000_000_000:
            return f"{sign}{ax/1_000_000:.2f}M"
        return f"{sign}{ax/1_000_000_000:.2f}B"

    def _reposition_overlay_labels(self, *_args, **_kw) -> None:
        vb = self.getViewBox()
        if vb is None:
            return
        (xmin, xmax), (ymin, ymax) = vb.viewRange()
        xpad = (xmax - xmin) * 0.01
        ypad = (ymax - ymin) * 0.01
        self._asym_label.setPos(xmax - xpad, ymax - ypad)
        self._expiry_label.setPos(xmin + xpad, ymax - ypad)

    def _auto_range(
        self,
        levels: Dict[str, float],
        top_strikes: List[Tuple[float, float]],
    ) -> None:
        prices = [v for v in levels.values() if v is not None]
        prices += [s for s, _ in top_strikes]
        if not prices:
            return
        lo, hi = min(prices), max(prices)
        if hi == lo:
            pad = max(1.0, hi * 0.02)
        else:
            pad = (hi - lo) * 0.10
        vb = self.getViewBox()
        if vb is not None:
            vb.setYRange(lo - pad, hi + pad, padding=0)
            vb.setXRange(0, 1, padding=0)
