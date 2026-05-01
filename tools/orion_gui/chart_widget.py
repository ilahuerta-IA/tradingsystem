"""Pyqtgraph chart widget for ORION GEX GUI.

Displays a dark, time-less chart with horizontal lines for each GEX
level. Y axis is price; X axis is hidden. Left-click drag on the
price (Y) axis scales the price range (MT5-like behavior).

Public API:
    GexChartWidget(parent=None)
        update_levels(levels: dict, top_strikes: list[(strike, net_gex)],
                      asym: float, gamma_flip: float or None,
                      deltas: dict, expiry_changed: bool)
        update_spot(spot: float)
        clear_levels()

Levels rendered (key -> color, style):
    SPOT       blue solid 2
    CALL_WALL  green solid 3
    PUT_WALL   red solid 3
    GAMMA_FLIP yellow dashed 2
    MAX_GEX    cyan dotted 2
    Top strikes: green dashed thin (above flip), red dashed thin (below)
"""

from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QPen
import pyqtgraph as pg


# Visual configuration ------------------------------------------------

BG_COLOR = "#0d0d0d"
FG_COLOR = "#d0d0d0"
ASYM_FONT_SIZE = 14
LABEL_FONT_SIZE = 9

LEVEL_STYLES = {
    "SPOT":       {"color": "#3aa0ff", "width": 2, "style": Qt.PenStyle.SolidLine},
    "CALL_WALL":  {"color": "#22dd55", "width": 3, "style": Qt.PenStyle.SolidLine},
    "PUT_WALL":   {"color": "#ee3344", "width": 3, "style": Qt.PenStyle.SolidLine},
    "GAMMA_FLIP": {"color": "#ffcc33", "width": 2, "style": Qt.PenStyle.DashLine},
    "MAX_GEX":    {"color": "#33ddee", "width": 2, "style": Qt.PenStyle.DotLine},
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
        # Drag down (dy > 0) -> compress price (zoom out, factor > 1).
        # Drag up   (dy < 0) -> expand price  (zoom in,  factor < 1).
        factor = 1.0 + dy * 0.005
        factor = max(0.2, min(5.0, factor))
        vb = self.linkedView()
        if vb is not None:
            vb.scaleBy(y=factor, x=1.0)


# Main chart widget ----------------------------------------------------

class GexChartWidget(pg.PlotWidget):

    def __init__(self, parent=None):
        # Custom Y axis on the right (where MT5 keeps it).
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
        self.showGrid(x=False, y=True, alpha=0.15)

        self._items: List[pg.GraphicsObject] = []
        self._spot_line: Optional[pg.InfiniteLine] = None
        self._spot_label: Optional[pg.TextItem] = None
        self._asym_label: pg.TextItem = pg.TextItem("ASYM --", anchor=(1, 0))
        font = QFont()
        font.setPointSize(ASYM_FONT_SIZE)
        font.setBold(True)
        self._asym_label.setFont(font)
        self.addItem(self._asym_label)
        self._expiry_label: pg.TextItem = pg.TextItem("", anchor=(0, 0))
        self._expiry_label.setColor(QColor("#ee3344"))
        ef = QFont()
        ef.setPointSize(ASYM_FONT_SIZE)
        ef.setBold(True)
        self._expiry_label.setFont(ef)
        self.addItem(self._expiry_label)

    # ---- public API --------------------------------------------------

    def clear_levels(self) -> None:
        for item in self._items:
            try:
                self.removeItem(item)
            except Exception:
                pass
        self._items = []
        if self._spot_line is not None:
            self.removeItem(self._spot_line)
            self._spot_line = None
        if self._spot_label is not None:
            self.removeItem(self._spot_label)
            self._spot_label = None

    def update_levels(
        self,
        levels: Dict[str, float],
        top_strikes: List[Tuple[float, float]],
        asym: Optional[float],
        gamma_flip: Optional[float],
        deltas: Dict[str, Optional[float]],
        expiry_changed: bool,
    ) -> None:
        """Redraw all GEX level lines + asymmetry label."""
        self.clear_levels()

        for name in ("CALL_WALL", "PUT_WALL", "GAMMA_FLIP", "MAX_GEX"):
            price = levels.get(name)
            if price is None:
                continue
            self._add_level_line(name, price, deltas.get(name))

        # Top strikes (excluding the named ones already drawn).
        named_prices = {levels.get(n) for n in
                        ("CALL_WALL", "PUT_WALL", "GAMMA_FLIP", "MAX_GEX")}
        for strike, _net in top_strikes:
            if strike in named_prices:
                continue
            self._add_strike_line(strike, gamma_flip)

        # Asymmetry label (top-right).
        if asym is None:
            self._asym_label.setText("ASYM --")
            self._asym_label.setColor(QColor("#888888"))
        else:
            txt = f"ASYM {asym:.2f}"
            color = "#888888"
            if asym >= 1.5:
                color = "#22dd55"
            elif asym <= 0.67:
                color = "#ee3344"
            elif asym >= 1.0:
                color = "#88dd88"
            else:
                color = "#dd8888"
            self._asym_label.setText(txt)
            self._asym_label.setColor(QColor(color))

        if expiry_changed:
            self._expiry_label.setText("EXPIRY CHANGED")
        else:
            self._expiry_label.setText("")

        self._reposition_overlay_labels()
        self._auto_range(levels, top_strikes)

    def update_spot(self, spot: Optional[float]) -> None:
        """Update or create the live spot line + label."""
        if spot is None:
            return
        style = LEVEL_STYLES["SPOT"]
        pen = QPen(QColor(style["color"]))
        pen.setWidth(style["width"])
        pen.setStyle(style["style"])
        if self._spot_line is None:
            self._spot_line = pg.InfiniteLine(pos=spot, angle=0, pen=pen)
            self.addItem(self._spot_line)
        else:
            self._spot_line.setValue(spot)

        label_txt = f"SPOT {spot:.2f}"
        if self._spot_label is None:
            self._spot_label = pg.TextItem(label_txt, anchor=(0, 1))
            self._spot_label.setColor(QColor(style["color"]))
            f = QFont()
            f.setPointSize(LABEL_FONT_SIZE)
            f.setBold(True)
            self._spot_label.setFont(f)
            self.addItem(self._spot_label)
        else:
            self._spot_label.setText(label_txt)
        vb = self.getViewBox()
        if vb is not None:
            xrange = vb.viewRange()[0]
            self._spot_label.setPos(xrange[0], spot)

    # ---- internal helpers --------------------------------------------

    def _add_level_line(
        self, name: str, price: float, delta: Optional[float]
    ) -> None:
        style = LEVEL_STYLES[name]
        pen = QPen(QColor(style["color"]))
        pen.setWidth(style["width"])
        pen.setStyle(style["style"])
        line = pg.InfiniteLine(pos=price, angle=0, pen=pen)
        self.addItem(line)
        self._items.append(line)

        delta_str = self._fmt_delta(delta)
        text = f"{name} {price:.2f} {delta_str}"
        label = pg.TextItem(text, anchor=(0, 1))
        label.setColor(QColor(style["color"]))
        f = QFont()
        f.setPointSize(LABEL_FONT_SIZE)
        f.setBold(True)
        label.setFont(f)
        label.setPos(0, price)
        self.addItem(label)
        self._items.append(label)

    def _add_strike_line(
        self, strike: float, gamma_flip: Optional[float]
    ) -> None:
        if gamma_flip is None:
            color = "#888888"
        elif strike >= gamma_flip:
            color = "#226633"
        else:
            color = "#662233"
        pen = QPen(QColor(color))
        pen.setWidth(1)
        pen.setStyle(Qt.PenStyle.DashLine)
        line = pg.InfiniteLine(pos=strike, angle=0, pen=pen)
        self.addItem(line)
        self._items.append(line)

        label = pg.TextItem(f"{strike:.2f}", anchor=(0, 1))
        label.setColor(QColor(color))
        f = QFont()
        f.setPointSize(LABEL_FONT_SIZE - 1)
        label.setFont(f)
        label.setPos(0, strike)
        self.addItem(label)
        self._items.append(label)

    def _fmt_delta(self, delta: Optional[float]) -> str:
        if delta is None:
            return ""
        if abs(delta) < 1e-9:
            return "(==)"
        sign = "+" if delta > 0 else ""
        return f"({sign}{delta:.2f})"

    def _reposition_overlay_labels(self) -> None:
        vb = self.getViewBox()
        if vb is None:
            return
        (xmin, xmax), (ymin, ymax) = vb.viewRange()
        self._asym_label.setPos(xmax, ymax)
        self._expiry_label.setPos(xmin, ymax)

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
