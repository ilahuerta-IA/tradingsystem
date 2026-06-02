"""ORION GEX GUI package.

Modules:
  main_window    - single-window app (control bar, log, GEX chart, AUTO poll)
  chart_widget   - pyqtgraph GEX-by-strike chart
  spot_provider  - MT5 live spot attach
  order_executor - MT5 order placement
  momentum_radar - Momentum Confluence Sensor (floating 4-axis radar widget)

Momentum Confluence Radar (momentum_radar)
------------------------------------------
Separate, resizable floating window. Pure QPainter. LONG-only. Fed from
main_window._auto_tick (10s cadence). Visualizes 4 per-tick deltas as a
radar polygon so confluence (all axes expanding outward = bullish push)
is readable at a glance.

Axes (all normalized RELATIVE so one scaling works across any ticker):
  N  dPrice    : tanh((dPrice / spot)      / 0.0007)   # 0.07% of spot
  E  dNET_GEX  : tanh((dIMP   / IMP_base)  / 0.03)     # 3% of GEX base
  S  dSPY%     : tanh(dSPY% / 0.008)
  O  dQQQ%     : tanh(dQQQ% / 0.011)

GEX event: when |dIMP| >= ~30% of base (Call Wall shift / repricing), the
E axis FLASHES as an alert (the large sudden variation IS the signal, it
then stabilizes) instead of being hidden. QQQ->SPY lead-lag (QQQ moves
first, SPY confirms) marks the market axes as a confluence signal. The 1m
average (last 6 ticks) is drawn as a translucent baseline polygon; racha
r>2 triggers a glow. Scaling constants are empirical (ODT study, 5 tickers).
"""

