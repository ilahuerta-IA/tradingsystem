# CERES Strategy

**Type:** Opening Range + Pullback + Breakout (Intraday)  
**Assets:** ETFs (GLD target inicial, extensible a DIA, XLE, XLU, TLT)  
**Direction:** Long Only  
**Session:** Intraday — EOD close obligatorio  
**Base:** Estrategia nativa ETF (NO adaptación forex)

---

## Table of Contents

1. [Overview](#overview)
2. [Motivación Estratégica](#motivación-estratégica)
3. [Entry System (3 States)](#entry-system-3-states)
4. [Exit Logic](#exit-logic)
5. [Risk Management](#risk-management)
6. [Configuration Parameters](#configuration-parameters)
7. [Implementation Notes](#implementation-notes)
8. [Development Plan](#development-plan)
9. [Changelog](#changelog)

---

## Overview

CERES es una estrategia **intraday LONG-only** diseñada nativamente para ETFs. La tesis central:
**El comportamiento del mercado en su primera hora/dos horas de apertura (Opening Range) predice
la dirección del día.**

### Design Philosophy

```
MARKET OPEN → OPENING RANGE → QUALITY CHECK → PULLBACK + BREAKOUT → ENTRY LONG
     (1)           (2)             (3)               (4)
```

1. **Day Open Detection**: First bar of each day detected from data (DST-agnostic)
2. **Opening Range (OR)**: After optional delay_bars, collect N velas -> OR HH, OR LL, OR Height
3. **Quality Check**: Filtros opcionales sobre el OR (ángulo, ATR, ER) → si ALL OFF, pasa directo
4. **Pullback + Breakout**: Consolidación debajo del OR HH → price breaks OR HH → ENTRY LONG

### Diferencia Fundamental vs Otras Estrategias

| Aspecto | Ogle/KOI/SEDNA | CERES |
|---------|----------------|-------|
| **Trigger** | Indicadores técnicos (EMA cross, engulfing, ER+KAMA) | Opening Range del mercado |
| **Hora** | Cualquier momento del día | Solo post-apertura |
| **Diseño** | Forex 24h adaptado a ETF con parche EOD | Nativo ETF: intraday desde el diseño |
| **Window** | Dinámica (EMA cross) o N/A | Fija (primeras N velas del día) |
| **HH Referencia** | Calculado dinámicamente | Determinado por el OR (fijo y conocido) |

### Why This Architecture?

| Component | Purpose |
|-----------|---------|
| **Opening Range** | Captura el impulso institucional de apertura como dato primario |
| **Quality Filters** | Filtran ORs débiles/ruidosos (opcional, cada uno on/off) |
| **Pullback** | Confirma que el OR HH es resistencia respetada antes de romperla |
| **Breakout OR HH** | Confirma momentum alcista para entrar LONG |
| **EOD Close** | Zero overnight risk — tesis intraday pura |

---

## Motivación Estratégica

### El Problema

El bloque ETF representa el **20% del portfolio** (4 de 16 configs) pero NO tiene estrategia
propia. Todas las configs ETF actuales son adaptaciones forex con parche `eod_close`:

| Config | Estrategia | Tier | Score |
|--------|-----------|------|-------|
| DIA_PRO | Ogle (forex) | C | 1.33 |
| DIA_SEDNA | SEDNA (forex) | B | 2.70 |
| XLE_PRO | Ogle (forex) | B | 2.03 |
| XLU_KOI | KOI (forex) | C | 1.26 |

**Tasa de supervivencia forex→ETF: 27%** (4 de 15 combinaciones probadas).

**Pérdidas clave:**
- ❌ GLD eliminado (Score 0.56) — era el principal diversificador (correlación ~0 con forex)
- ❌ EWZ descartado en WF
- ❌ GLD_SEDNA eliminado (Score 0.54)

### La Solución: CERES

Estrategia diseñada **desde cero** para el comportamiento de ETFs:
- Horario fijo de mercado (no 24h)
- Apertura como evento de alta información
- Sin overnight — cierre obligatorio
- Filtros pensados para sesiones de mercado, no para forex

**Objetivo #1:** Recuperar GLD con Score > 1.50

---

## Entry System (3 States)

### State Machine

```
            first bar of new day
    IDLE ───── (+ delay_bars) ────► WINDOW_FORMING
     ▲                              │
     │                      OR completo (N velas)
     │                              │
     │                    ┌── quality filters ──┐
     │                    │                     │
     │              alguno FAIL           todos OK (o todos OFF)
     │                    │                     │
     │                  IDLE                  ARMED
     │              (espera mañana)             │
     │                                          ├── pullback_ready + breakout ──► ENTRY LONG
     │                                          │
     └──── timeout (max_bars) ──────────────────┘
```

**Solo 3 estados reales: IDLE → WINDOW_FORMING → ARMED**

Entry se ejecuta inline desde ARMED (no es un estado separado).

---

### State 1: IDLE — Esperando Primera Barra del Día

```python
# Day change detected from data (DST-agnostic):
if today != yesterday:
    day_first_bar_seen = True
    delay_remaining = delay_bars

# Each bar in IDLE:
if day_first_bar_seen:
    if delay_remaining > 0:
        delay_remaining -= 1
    else:
        state = "WINDOW_FORMING"
```

**Parámetros:**
- `delay_bars` (default: 0) — Number of bars to skip after first bar of day before starting OR
  - `delay_bars=0`: OR starts immediately at market open (first bar of day in data)
  - `delay_bars=6`: Skip 6 bars (30 min at 5min TF) after open, then start OR

**DST-agnostic:** No need for `market_open_hour`/`market_open_minute`. The data itself
contains the correct open time (13:30 UTC in summer, 14:30 UTC in winter for US ETFs).
The strategy simply detects "new day" and counts bars from there.

---

### State 2: WINDOW_FORMING — Recogiendo Opening Range

```python
# Cada barra mientras state == WINDOW_FORMING:
or_highs.append(current_high)
or_lows.append(current_low)
or_bar_count += 1

if or_bar_count >= or_candles:
    OR_HH = max(or_highs)
    OR_LL = min(or_lows)
    OR_HEIGHT = OR_HH - OR_LL
    
    # Quality check (todos opcionales)
    if quality_ok():
        state = "ARMED"
    else:
        state = "IDLE"  # OR rechazado, espera mañana
```

**Opening Range se define por número de velas** (`or_candles`):
- `or_candles = 8` en TF 15min = 2 horas de OR
- `or_candles = 4` en TF 15min = 1 hora de OR
- `or_candles = 12` en TF 5min = 1 hora de OR

Independiente del timeframe → 100% configurable.

**OR Output:**
- `OR_HH` = max(highs) primeras N velas → nivel de breakout
- `OR_LL` = min(lows) primeras N velas → nivel de SL natural
- `OR_HEIGHT` = OR_HH - OR_LL → referencia para TP proporcional

---

### Quality Filters (todos opcionales e independientes)

Cada filtro tiene su `use_X = True/False`. Si TODOS están en `False`, el OR pasa directamente
a ARMED sin juicio de calidad.

#### Filter 0: OR Height (tamaño del Opening Range)

¿El OR fue lo suficientemente grande como para generar un trade con edge? ORs muy pequeños (< 50 pips en GLD) tienen poco momentum; ORs enormes pueden tener SL excesivo.

```python
height_pips = or_height / pip_value

if height_pips < or_height_min or height_pips > or_height_max:
    return False  # OR demasiado pequeno o demasiado grande
```

| Parámetro | Default | Descripción |
|-----------|---------|-------------|
| `use_or_height_filter` | False | Habilitar filtro de altura del OR |
| `or_height_min` | 0.0 | Altura mínima en pips (evitar ORs sin rango) |
| `or_height_max` | 9999.0 | Altura máxima en pips (evitar ORs extremos) |

#### Filter 1: Ángulo del OR

Mide la dirección/fuerza del Opening Range: ¿fue alcista o plano?

```python
# Pendiente del OR: desde open de 1ª vela hasta close de última vela del OR
or_open = or_opens[0]    # Open de la primera vela del OR
or_close = or_closes[-1]  # Close de la última vela del OR
angle = calculate_angle(or_open, or_close, or_candles)

if angle < angle_min or angle > angle_max:
    return False  # OR sin dirección clara o demasiado vertical
```

| Parámetro | Default | Descripción |
|-----------|---------|-------------|
| `use_angle_filter` | False | Habilitar filtro de ángulo del OR |
| `angle_min` | 5.0 | Ángulo mínimo (evitar ORs planos) |
| `angle_max` | 80.0 | Ángulo máximo (evitar ORs verticales/insostenibles) |

#### Filter 2: ATR medio durante el OR

¿Hay suficiente volatilidad durante la formación del OR?

```python
atr_value = average(atr_values_during_or)

if atr_value < atr_min or atr_value > atr_max:
    return False  # Volatilidad fuera de rango
```

| Parámetro | Default | Descripción |
|-----------|---------|-------------|
| `use_atr_filter` | False | Habilitar filtro ATR del OR |
| `atr_min` | 0.0 | ATR mínimo (evitar ORs sin movimiento) |
| `atr_max` | 999.0 | ATR máximo (evitar ORs demasiado volátiles) |

#### Filter 3: ER del propio Opening Range

¿El movimiento del OR fue eficiente (tendencial) o ruidoso?

```python
er_or = abs(or_close - or_open) / sum_of_bar_ranges_during_or

if not (er_or_min <= er_or <= er_or_max):
    return False  # OR fuera del rango deseado
```

| Parámetro | Default | Descripción |
|-----------|---------|-------------|
| `use_er_or_filter` | False | Habilitar ER del OR (rango min/max) |
| `er_or_min` | 0.0 | ER mínimo del OR |
| `er_or_max` | 1.0 | ER máximo del OR |

#### Filter 4: ER en Timeframe Superior (contexto macro)

¿El mercado en general está tendencial hoy? Medido en TF superior.

```python
# ER calculado sobre ventana más amplia (e.g., 1h, o daily)
if er_htf < er_htf_threshold:
    return False  # Mercado choppy en escala macro
```

| Parámetro | Default | Descripción |
|-----------|---------|-------------|
| `use_er_htf_filter` | False | Habilitar ER en TF superior |
| `er_htf_threshold` | 0.3 | ER mínimo en TF superior |
| `er_htf_period` | 10 | Periodo del ER en TF superior |
| `er_htf_timeframe_minutes` | 60 | TF para escalar el periodo (15, 60, etc.) |

---

### State 3: ARMED — Esperando Pullback + Breakout

**Pullback = consolidación debajo del OR HH.** El precio no ha superado el OR HH en N barras.

```python
def ceres_pullback_ready(bars_since_or, highs_since_or, or_hh, min_bars, max_bars):
    """
    ¿Hay pullback válido?
    = N barras sin romper OR HH (consolidando debajo)
    """
    if bars_since_or < min_bars:
        return False  # Muy pronto, necesita consolidar
    if bars_since_or > max_bars:
        return False  # Timeout — señal muerta
    if any(h >= or_hh for h in highs_since_or):
        return False  # Ya rompió antes, no es pullback limpio
    return True
```

**Breakout = price rompe OR HH + buffer.**

```python
from lib.filters import check_pullback_breakout

if ceres_pullback_ready(...) and check_pullback_breakout(
    current_high=high,
    breakout_level=OR_HH,
    buffer_pips=breakout_buffer_pips,
    pip_value=pip_value
):
    execute_entry()  # LONG
```

| Parámetro | Default | Descripción |
|-----------|---------|-------------|
| `pullback_min_bars` | 2 | Mín barras consolidando debajo de OR HH |
| `pullback_max_bars` | 8 | Timeout: si no rompe en N barras → IDLE |
| `breakout_buffer_pips` | 5.0 | Buffer encima de OR HH para confirmar breakout |

**Nota:** Se reutiliza `check_pullback_breakout()` de `lib/filters.py` — misma función que usa SEDNA.

---

## Exit Logic

### Stop Loss (configurable por modo)

El SL tiene 3 modos seleccionables:

| Modo | Nivel SL | Lógica |
|------|----------|--------|
| `or_low` (default) | OR_LL - buffer | Si precio cae debajo del OR, la tesis muere |
| `fixed_pips` | Entry - sl_pips | SL fijo en pips como otras estrategias |
| `atr_mult` | Entry - (ATR × mult) | SL proporcional a volatilidad |

```python
if sl_mode == 'or_low':
    sl_price = OR_LL - (sl_buffer_pips * pip_value)
elif sl_mode == 'fixed_pips':
    sl_price = entry_price - (sl_fixed_pips * pip_value)
elif sl_mode == 'atr_mult':
    sl_price = entry_price - (atr_avg * sl_atr_mult)
```

El `sl_buffer_pips` se aplica como ajuste fino sobre el nivel. Si 0, SL estricto sin respiro.

| Parámetro | Default | Descripción |
|-----------|---------|-------------|
| `sl_mode` | 'or_low' | Modo de SL: 'or_low', 'fixed_pips', 'atr_mult' |
| `sl_buffer_pips` | 5.0 | Buffer debajo del nivel SL (flexibilidad) |
| `sl_fixed_pips` | 30.0 | Pips fijos para SL (solo si sl_mode='fixed_pips') |
| `sl_atr_mult` | 1.5 | Multiplicador ATR para SL (solo si sl_mode='atr_mult') |

### Take Profit (configurable por modo)

| Modo | Nivel TP | Lógica |
|------|----------|--------|
| `none` (default) | Sin TP | Solo EOD close decide la salida |
| `or_height_mult` | Entry + (OR_HEIGHT × mult) | Proporcional al rango del día |
| `fixed_pips` | Entry + tp_pips | TP fijo en pips |
| `atr_mult` | Entry + (ATR × mult) | Proporcional a volatilidad |

```python
if tp_mode == 'none':
    tp_price = None  # Sin TP — salida por EOD o SL
elif tp_mode == 'or_height_mult':
    tp_price = entry_price + (OR_HEIGHT * tp_or_mult)
elif tp_mode == 'fixed_pips':
    tp_price = entry_price + (tp_fixed_pips * pip_value)
elif tp_mode == 'atr_mult':
    tp_price = entry_price + (atr_avg * tp_atr_mult)
```

**`or_height_mult` es interesante:** el TP se autoescala — días de mucho movimiento = TP más
generoso, días estrechos = TP conservador.

| Parámetro | Default | Descripción |
|-----------|---------|-------------|
| `tp_mode` | 'none' | Modo TP: 'none', 'or_height_mult', 'fixed_pips', 'atr_mult' |
| `tp_or_mult` | 1.5 | Multiplicador de OR Height (solo si tp_mode='or_height_mult') |
| `tp_fixed_pips` | 50.0 | Pips fijos para TP (solo si tp_mode='fixed_pips') |
| `tp_atr_mult` | 2.0 | Multiplicador ATR para TP (solo si tp_mode='atr_mult') |

### EOD Close (obligatorio para ETFs)

```python
if use_eod_close and current_hour >= eod_close_hour and current_minute >= eod_close_minute:
    close_position()  # Cierre forzado antes de fin de sesión
```

| Parámetro | Default | Descripción |
|-----------|---------|-------------|
| `use_eod_close` | True | Habilitar cierre forzado EOD |
| `eod_close_hour` | 20 | Hora UTC de cierre |
| `eod_close_minute` | 45 | Minuto UTC de cierre |

### OCA Orders

Stop Loss y Take Profit (si existe) se envían como OCA (One-Cancels-All):

```python
stop_order = self.sell(exectype=bt.Order.Stop, price=sl_price, oco=limit_order)
limit_order = self.sell(exectype=bt.Order.Limit, price=tp_price, oco=stop_order)
```

Si `tp_mode == 'none'`, solo se envía la Stop order. La salida será por SL o EOD close.

---

## Risk Management

### Position Sizing (ETF Standard)

```python
risk_amount = equity * risk_percent  # e.g., $50K * 0.75% = $375
price_risk = entry_price - sl_price  # e.g., $172.50 - $171.00 = $1.50
shares = risk_amount / price_risk    # e.g., $375 / $1.50 = 250 shares

max_shares = equity / (entry_price * margin_pct / 100)
shares = min(shares, max_shares)     # Margin constraint
```

### Standard Pre-Entry Filters

| Filter | Descripción | Parámetros |
|--------|-------------|------------|
| **Time Filter** | Solo operar en horas configurables | `start_hour`, `end_hour` |
| **Day Filter** | Solo días configurables | `allowed_days` [0-4] |
| **SL Pips Filter** | Limitar rango de SL en pips | `use_sl_pips_filter`, `sl_pips_min`, `sl_pips_max` |
| **ATR Average** | ATR promedio en rango | `use_atr_avg_filter`, `atr_avg_min`, `atr_avg_max` |

---

## Configuration Parameters

### Resumen Completo

```python
# --- Opening Range ---
market_open_hour = 14          # Hora UTC apertura mercado
market_open_minute = 30        # Minuto UTC apertura
or_candles = 8                 # Velas para formar el OR (8 × 15min = 2h)

# --- Quality Filters (todos opcionales) ---
use_or_height_filter = False   # Altura del OR en pips
or_height_min = 0.0
or_height_max = 9999.0

use_angle_filter = False       # Angulo del OR
angle_min = 5.0
angle_max = 80.0

use_atr_filter = False         # ATR medio durante OR
atr_min = 0.0
atr_max = 999.0

use_er_or_filter = False       # ER del propio OR (rango min/max)
er_or_min = 0.0
er_or_max = 1.0

use_er_htf_filter = False      # ER en TF superior
er_htf_threshold = 0.3
er_htf_period = 10
er_htf_timeframe_minutes = 60  # Seleccionable: 15, 60, etc.

# --- Pullback + Breakout ---
pullback_min_bars = 2          # Mín barras consolidando
pullback_max_bars = 8          # Timeout
breakout_buffer_pips = 5.0     # Buffer encima de OR HH

# --- Stop Loss ---
sl_mode = 'or_low'             # 'or_low' | 'fixed_pips' | 'atr_mult'
sl_buffer_pips = 5.0           # Buffer debajo del nivel SL
sl_fixed_pips = 30.0           # Solo si sl_mode = 'fixed_pips'
sl_atr_mult = 1.5              # Solo si sl_mode = 'atr_mult'

# --- Take Profit ---
tp_mode = 'none'               # 'none' | 'or_height_mult' | 'fixed_pips' | 'atr_mult'
tp_or_mult = 1.5               # Solo si tp_mode = 'or_height_mult'
tp_fixed_pips = 50.0           # Solo si tp_mode = 'fixed_pips'
tp_atr_mult = 2.0              # Solo si tp_mode = 'atr_mult'

# --- EOD Close ---
use_eod_close = True
eod_close_hour = 20
eod_close_minute = 45

# --- Standard Filters ---
allowed_days = [0, 1, 2, 3, 4]   # Lunes a Viernes
start_hour = 14                    # No operar antes de apertura
end_hour = 20                      # No operar después de cierre - buffer

# --- ATR ---
atr_length = 14
atr_avg_period = 20

# --- Risk ---
risk_percent = 0.0075          # 0.75% (Tier C default para nuevo activo)
pip_value = 0.01               # ETF standard
is_etf = True
margin_pct = 20.0
```

---

## Implementation Notes

### Archivos a Crear

| Archivo | Propósito |
|---------|-----------|
| `strategies/ceres_strategy.py` | Estrategia Backtrader principal |
| `live/checkers/ceres_checker.py` | Checker para bot live MT5 |
| `config/settings.py` (editar) | Configs GLD_CERES, DIA_CERES, etc. |
| `tools/analyze_ceres.py` | Analyzer de métricas específicas (opcional) |

### Código Reutilizable del Sistema

| Componente | Origen | Uso en CERES |
|------------|--------|--------------|
| `check_pullback_breakout()` | `lib/filters.py` | Breakout del OR HH + buffer |
| `check_time_filter()` | `lib/filters.py` | Filtro horario |
| `check_day_filter()` | `lib/filters.py` | Filtro de días |
| `check_atr_filter()` | `lib/filters.py` | Filtro ATR range |
| `check_sl_pips_filter()` | `lib/filters.py` | Filtro SL pips range |
| Position sizing | `lib/sizing.py` | Sizing estándar ETF |
| OCA orders | Pattern estándar | SL + TP orders |
| EOD close | Pattern de Ogle/SEDNA | Cierre forzado |

### Detección de Market Open

```python
def _is_market_open(self, dt):
    """Detecta si la barra actual es la apertura del mercado."""
    return dt.hour == self.p.market_open_hour and dt.minute == self.p.market_open_minute
```

Para ETFs US:
- **Market open**: 14:30 UTC (9:30 ET)
- **Market close**: ~21:00 UTC (16:00 ET)
- **EOD close CERES**: 20:45 UTC (15 min antes del cierre real)

### Sobre el Pullback Simplificado

CERES NO usa `detect_pullback()` de `lib/filters.py` para el pullback. Razón: esa función
busca dinámicamente un HH en ventana deslizante. En CERES el HH es **conocido y fijo** (OR HH).
La lógica de pullback es más simple y directa:

```python
# ¿Estamos consolidando debajo del OR HH sin haberlo roto?
bars_since_or = current_bar - or_end_bar
no_breakout_yet = all(h < or_hh for h in highs_since_or_end)
pullback_valid = pullback_min_bars <= bars_since_or <= pullback_max_bars and no_breakout_yet
```

Sin embargo, SÍ reutiliza `check_pullback_breakout()` para la confirmación de breakout, que es
una función stateless y genérica.

---

## Development Plan

### Fase 1: GLD_CERES (Primer BT)

**Objetivo:** Recuperar GLD con Score > 1.50 (actual: 0.56 con Ogle, 0.54 con SEDNA)

1. Implementar `strategies/ceres_strategy.py` con state machine completo
2. Config `GLD_CERES` en `settings.py` con defaults sensatos
3. BT inicial con todos los filtros OFF → baseline pura (OR + pullback + breakout)
4. Activar filtros uno a uno → medir impacto individual
5. Optimización parámetros OR (candles, timeframe)
6. Walk-Forward validation
7. Si Score ≥ 1.50 → GO. Si no → iterar.

### Fase 2: Expansión a ETFs existentes

- DIA_CERES, XLE_CERES, XLU_CERES
- Comparar Score CERES vs Score actual de cada config
- Si CERES mejora → reemplazar. Si no → mantener original.

### Fase 3: Nuevos ETFs

- TLT_CERES (bonds — diversificador)
- Otros candidatos según correlación con portfolio

### Fase 4: Checker Live

- `live/checkers/ceres_checker.py` → integración con bot MT5
- Validación demo antes de producción

---

## Backtest Results

*Pendiente — se completará con resultados del primer BT de GLD_CERES.*

---

## Changelog

| Date | Version | Changes |
|------|---------|---------|
| 2026-03-03 | 0.8.1 | Add pb_depth_filter (use_pb_depth_filter, pb_depth_min/max) and allowed_pb_bars (discrete bar selection) filters |
| 2026-03-03 | 0.8 | Replace permissive pullback with Ogle mechanics (consecutive bearish candles + dynamic channel + re-arming). Remove ATR OR/Avg filters. Add WINDOW_OPEN state. New params: pullback_candles, window_periods, price_offset_mult, pullback_max_retries. Add Rearm Count to trade log. |
| 2026-03-03 | 0.7 | Remove OR Angle (useless), repurpose angle filter → PB Angle filter at entry |
| 2026-03-03 | 0.6 | Add pullback metrics to trade log + analyzer (pb_bars, pb_angle, pb_depth) |
| 2026-03-03 | 0.5 | Convert er_or_filter from threshold to min/max range (er_or_min/er_or_max) |
| 2026-03-03 | 0.4 | Fix day/time filters: move from global guard to entry point |
| 2026-03-02 | 0.3 | Add or_height filter (use_or_height_filter, or_height_min/max in pips) |
| 2026-03-02 | 0.2 | Replace market_open_hour/minute with delay_bars (DST-agnostic day detection) |
| 2026-03-01 | 0.1 | Diseño inicial documentado. Pre-implementación. |

---

*Documentation generated for TradingSystem - CERES Strategy*
*Diseño: Sesión Copilot 2026-03-01*
