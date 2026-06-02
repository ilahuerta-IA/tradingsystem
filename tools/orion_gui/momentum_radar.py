"""Momentum Confluence Radar widget for the ORION GUI.

A separate, resizable floating window that renders the four per-tick
deltas produced by main_window._auto_tick as a radar (spider) polygon.
Confluence -- all axes pushing outward in the same (bullish) direction --
becomes readable at a glance. LONG-only by design.

Axes (clockwise from top):
    N  dPrice    price change vs previous tick
    E  dNET_GEX  GEX impulse change (sum net_gex in (spot, call_wall])
    S  SPY%      SPY tick-to-tick percent change
    O  QQQ%      QQQ tick-to-tick percent change

All inputs are normalized RELATIVE to the instrument (percent of spot,
percent of the GEX base) so a single scaling generalizes across tickers
of very different price and open-interest magnitude (verified on AAPL,
AMD, MSFT, NVDA, TSLA -- 10s tick study).

Pure QPainter; no third-party drawing dependency.
"""

import math
from typing import Dict, Optional

from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QPainter, QPen, QPolygonF, QRadialGradient,
)
from PyQt6.QtWidgets import QWidget


# ---------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------
# Full-scale constants: a raw delta equal to the constant maps (via tanh)
# to ~0.76 of the radius. Derived from the p90 of |delta| across the five
# studied tickers so a "strong normal" tick reaches roughly the outer ring
# while outliers saturate gracefully instead of blowing the figure up.
PRICE_FULL_SCALE = 0.0007   # 0.07% of spot
GEX_FULL_SCALE = 0.03       # 3% of the GEX base magnitude
SPY_FULL_SCALE = 0.008      # 0.008% per tick
QQQ_FULL_SCALE = 0.011      # 0.011% per tick

# A change in the GEX impulse this large (fraction of the base) is treated
# as a Call Wall shift / repricing EVENT rather than normal flow. Normal
# ticks stay below ~7% of base; events jump 100%+ of base. 30% separates
# them cleanly. On an event the E axis flashes instead of being hidden.
GEX_EVENT_THRESHOLD = 0.30


def _tanh_norm(value: Optional[float], full_scale: float) -> float:
    """Map a raw delta to [-1, 1] with tanh; None -> 0.0."""
    if value is None or full_scale <= 0:
        return 0.0
    return math.tanh(value / full_scale)


def normalize_deltas(
    d_price: Optional[float],
    spot: Optional[float],
    d_imp: Optional[float],
    imp_base: Optional[float],
    d_spy_pct: Optional[float],
    d_qqq_pct: Optional[float],
) -> Dict[str, object]:
    """Normalize the four raw deltas to a radar-ready payload.

    Returns a dict with normalized axes in [-1, 1] (keys N/E/S/O), the
    raw GEX event ratio, and a gex_event flag. Missing inputs map to 0.0
    (axis collapses to center) so stale ticks render neutral.
    """
    # Price: relative to spot.
    price_rel = (d_price / spot) if (d_price is not None and spot) else None
    n_axis = _tanh_norm(price_rel, PRICE_FULL_SCALE)

    # GEX impulse: relative to the current base magnitude.
    base = abs(imp_base) if imp_base else None
    gex_rel = (d_imp / base) if (d_imp is not None and base) else None
    e_axis = _tanh_norm(gex_rel, GEX_FULL_SCALE)
    gex_event = gex_rel is not None and abs(gex_rel) >= GEX_EVENT_THRESHOLD

    # SPY / QQQ: already percent figures.
    s_axis = _tanh_norm(d_spy_pct, SPY_FULL_SCALE)
    o_axis = _tanh_norm(d_qqq_pct, QQQ_FULL_SCALE)

    return {
        "N": n_axis,
        "E": e_axis,
        "S": s_axis,
        "O": o_axis,
        "gex_ratio": gex_rel if gex_rel is not None else 0.0,
        "gex_event": gex_event,
    }


# ---------------------------------------------------------------------
# Widget
# ---------------------------------------------------------------------

# Axis order and screen angle (degrees, 0 = right/East, CCW positive).
# N up, E right, S down, O left.
_AXES = (
    ("N", "dPrice", 90.0),
    ("E", "dGEX", 0.0),
    ("S", "SPY", 270.0),
    ("O", "QQQ", 180.0),
)

_BG = QColor("#101418")
_GRID = QColor("#2a3038")
_AXIS = QColor("#3a4250")
_LABEL = QColor("#9aa4b2")
_POLY_LINE = QColor("#28c8a0")
_POLY_FILL = QColor(40, 200, 160, 70)
_AVG_LINE = QColor(150, 150, 150, 140)
_AVG_FILL = QColor(150, 150, 150, 40)
_EVENT = QColor("#ff5a3c")
_CONFLUENCE = QColor("#3ad0ff")
_GLOW = QColor(40, 200, 160, 90)


class MomentumRadarWidget(QWidget):
    """Floating 4-axis radar fed from main_window._auto_tick.

    Call update_data() once per AUTO tick with the normalized payload
    from normalize_deltas(), the optional 1-minute average payload, the
    racha (consecutive-direction counter) and the qqq_leads flag.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("ORION Momentum Radar")
        self.setMinimumSize(220, 220)
        self.resize(320, 320)
        self.setAutoFillBackground(True)

        self._cur: Dict[str, float] = {k: 0.0 for k, _, _ in _AXES}
        self._avg: Optional[Dict[str, float]] = None
        self._racha: int = 0
        self._gex_event: bool = False
        self._qqq_leads: bool = False
        self._ticker: str = ""

    # -- public API ----------------------------------------------------

    def update_data(
        self,
        current: Dict[str, object],
        avg_1m: Optional[Dict[str, float]] = None,
        racha: int = 0,
        qqq_leads: bool = False,
        ticker: str = "",
    ) -> None:
        """Set the latest normalized values and repaint."""
        self._cur = {k: float(current.get(k, 0.0) or 0.0) for k, _, _ in _AXES}
        self._avg = (
            {k: float(avg_1m.get(k, 0.0) or 0.0) for k, _, _ in _AXES}
            if avg_1m else None
        )
        self._racha = int(racha)
        self._gex_event = bool(current.get("gex_event", False))
        self._qqq_leads = bool(qqq_leads)
        self._ticker = ticker
        self.update()

    def clear(self) -> None:
        """Reset all axes to neutral."""
        self._cur = {k: 0.0 for k, _, _ in _AXES}
        self._avg = None
        self._racha = 0
        self._gex_event = False
        self._qqq_leads = False
        self.update()

    # -- geometry helpers ----------------------------------------------

    def _center_radius(self):
        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        radius = min(w, h) / 2.0 - 34.0
        return cx, cy, max(radius, 10.0)

    @staticmethod
    def _point(cx, cy, radius, angle_deg, value):
        """Map a [-1, 1] value on an axis to a screen point.

        Negative values are clamped toward the center (LONG-only: we only
        meaningfully expand on bullish pushes, contraction reads as weak).
        """
        frac = (value + 1.0) / 2.0  # -1 -> center, +1 -> rim
        frac = max(0.0, min(1.0, frac))
        r = radius * frac
        a = math.radians(angle_deg)
        return QPointF(cx + r * math.cos(a), cy - r * math.sin(a))

    # -- painting ------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt signature)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), _BG)

        cx, cy, radius = self._center_radius()

        # Racha glow: bullish streak (r > 2) softly lights the field.
        if self._racha > 2:
            grad = QRadialGradient(cx, cy, radius)
            grad.setColorAt(0.0, _GLOW)
            grad.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(grad))
            p.drawEllipse(QPointF(cx, cy), radius, radius)

        self._draw_grid(p, cx, cy, radius)
        self._draw_axes(p, cx, cy, radius)
        if self._avg is not None:
            self._draw_polygon(p, cx, cy, radius, self._avg,
                               _AVG_LINE, _AVG_FILL, width=1)
        self._draw_polygon(p, cx, cy, radius, self._cur,
                           _POLY_LINE, _POLY_FILL, width=2)
        self._draw_markers(p, cx, cy, radius)
        self._draw_labels(p, cx, cy, radius)
        p.end()

    def _draw_grid(self, p, cx, cy, radius) -> None:
        p.setPen(QPen(_GRID, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        for frac in (0.25, 0.5, 0.75, 1.0):
            r = radius * frac
            p.drawEllipse(QPointF(cx, cy), r, r)
        # Zero ring (neutral level = mid radius) slightly brighter.
        p.setPen(QPen(QColor("#3a4250"), 1, Qt.PenStyle.DashLine))
        p.drawEllipse(QPointF(cx, cy), radius * 0.5, radius * 0.5)

    def _draw_axes(self, p, cx, cy, radius) -> None:
        p.setPen(QPen(_AXIS, 1))
        for _, _, ang in _AXES:
            a = math.radians(ang)
            p.drawLine(
                QPointF(cx, cy),
                QPointF(cx + radius * math.cos(a), cy - radius * math.sin(a)),
            )

    def _draw_polygon(self, p, cx, cy, radius, values, line, fill, width) -> None:
        poly = QPolygonF()
        for key, _, ang in _AXES:
            poly.append(self._point(cx, cy, radius, ang, values.get(key, 0.0)))
        p.setPen(QPen(line, width))
        p.setBrush(QBrush(fill))
        p.drawPolygon(poly)

    def _draw_markers(self, p, cx, cy, radius) -> None:
        # GEX event flash on the E axis.
        if self._gex_event:
            pt = self._point(cx, cy, radius, 0.0, self._cur.get("E", 0.0))
            p.setPen(QPen(_EVENT, 2))
            p.setBrush(QBrush(_EVENT))
            p.drawEllipse(pt, 6.0, 6.0)
            p.setPen(QPen(_EVENT, 1, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(pt, 11.0, 11.0)

        # QQQ -> SPY confluence: reinforce the two market axis tips.
        if self._qqq_leads:
            p.setPen(QPen(_CONFLUENCE, 2))
            p.setBrush(QBrush(_CONFLUENCE))
            for key, ang in (("S", 270.0), ("O", 180.0)):
                pt = self._point(cx, cy, radius, ang, self._cur.get(key, 0.0))
                p.drawEllipse(pt, 4.0, 4.0)

    def _draw_labels(self, p, cx, cy, radius) -> None:
        font = QFont("Consolas", 8)
        p.setFont(font)
        p.setPen(QPen(_LABEL, 1))
        offset = 16.0
        for key, name, ang in _AXES:
            a = math.radians(ang)
            lx = cx + (radius + offset) * math.cos(a)
            ly = cy - (radius + offset) * math.sin(a)
            txt = f"{key} {name}"
            rect = p.fontMetrics().boundingRect(txt)
            p.drawText(
                QPointF(lx - rect.width() / 2.0, ly + rect.height() / 4.0),
                txt,
            )
        if self._ticker:
            p.setPen(QPen(QColor("#d0d0d0"), 1))
            p.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
            p.drawText(QPointF(8.0, 18.0), self._ticker)
        if self._racha:
            p.setPen(QPen(_LABEL, 1))
            p.setFont(QFont("Consolas", 8))
            p.drawText(QPointF(8.0, self.height() - 8.0), f"r{self._racha:+d}")


# ---------------------------------------------------------------------
# Standalone demo (real NVDA-scale values)
# ---------------------------------------------------------------------

def _demo() -> None:
    import random
    import sys
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    w = MomentumRadarWidget()
    w.show()

    spot = 216.0
    imp_base = 78_000_000.0
    history = []

    def tick() -> None:
        # Sample deltas at roughly the observed NVDA scale; occasionally
        # inject a Call Wall repricing event on the GEX axis.
        d_price = random.gauss(0.0, 0.10)
        if random.random() < 0.1:
            d_imp = random.choice([-1, 1]) * imp_base * random.uniform(1.0, 2.3)
        else:
            d_imp = random.gauss(0.0, 2_000_000.0)
        d_spy = random.gauss(0.0, 0.008)
        d_qqq = random.gauss(0.0, 0.011)
        norm = normalize_deltas(d_price, spot, d_imp, imp_base, d_spy, d_qqq)

        history.append(norm)
        if len(history) > 6:
            history.pop(0)
        avg = {
            k: sum(float(h[k]) for h in history) / len(history)
            for k in ("N", "E", "S", "O")
        }
        racha = random.randint(-3, 5)
        qqq_leads = d_qqq > 0 and d_spy > 0 and d_qqq > d_spy
        w.update_data(norm, avg, racha, qqq_leads, ticker="NVDA")

    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(800)
    tick()
    sys.exit(app.exec())


if __name__ == "__main__":
    _demo()
