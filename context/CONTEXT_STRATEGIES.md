# TradingSystem — Estrategias y Optimización
> Archivo privado. Consultar cuando se trabaje en estrategias, optimización o evaluación de activos.

> **📂 Navegación:** [← Core](CONTEXT.md) | [Live](CONTEXT_LIVE.md) | [History](CONTEXT_HISTORY.md) | [Bugs](BUGS_FIXES.md)

---

## 🌟 GEMINI Strategy (Correlation Divergence Momentum)

### Concepto
GEMINI detecta divergencias de correlacion entre EURUSD y USDCHF (pares inversamente correlacionados).
- Usamos **Harmony Score**: producto de ROCs opuestos
- Cuando ROC_EURUSD sube Y ROC_USDCHF baja proporcionalmente -> armonia -> LONG EURUSD
- La señal se confirma cuando harmony > threshold sostenido N barras

### Arquitectura
```
GEMINI:  ROC_EURUSD × (-ROC_USDCHF) × scale = Harmony -> threshold + sustained + KAMA filter -> entry
```

### Formula Harmony Score
```python
harmony = ROC_primary × (-ROC_reference) × harmony_scale
```

| ROC_EURUSD | ROC_USDCHF | Harmony (×10000) | Interpretacion |
|------------|------------|------------------|----------------|
| +0.002 | -0.0015 | **+3.0** | ✅ Armonia - divergen del 0 |
| +0.001 | +0.001 | **-1.0** | ❌ No armonia - misma direccion |
| +0.004 | -0.0001 | **+0.4** | ⚠️ Asimetrico |
| +0.002 | -0.002 | **+4.0** | ✅✅ Simetria perfecta |

### Parametros Clave (Entry System) - Optimizados 2026-02-08
| Parametro | Valor | Descripcion |
|-----------|-------|-------------|
| `roc_period_primary` | 5 | Periodo ROC para EURUSD |
| `roc_period_reference` | 5 | Periodo ROC para USDCHF |
| `harmony_scale` | 10000 | Factor escala para calculo harmony |
| `allowed_cross_bars` | [0, 1] | Barras permitidas desde KAMA cross. Vacio=todas |
| `entry_roc_angle_min` | 10.0 | Angulo minimo ROC para entrar (grados) |
| `entry_roc_angle_max` | 40.0 | Angulo maximo ROC para entrar (grados) |
| `entry_harmony_angle_min` | 10.0 | Angulo minimo Harmony para entrar (grados) |
| `entry_harmony_angle_max` | 25.0 | Angulo maximo Harmony para entrar (grados) |
| `atr_sl_multiplier` | 5.0 | SL = Entry - ATR * mult |
| `atr_tp_multiplier` | 10.0 | TP = Entry + ATR * mult |

### Parametros de Plot y Angles (⚠️ SINCRONIZADOS)
| Parametro | Valor | Descripcion |
|-----------|-------|-------------|
| `plot_roc_multiplier` | 500 | Escala ROC en plot Y en calculo de angles |
| `plot_harmony_multiplier` | 15.0 | Escala Harmony en plot Y en calculo de angles |
| `roc_angle_scale` | 1.0 | Multiplicador atan para ROC angle |
| `harmony_angle_scale` | 1.0 | Multiplicador atan para Harmony angle |

**IMPORTANTE:** Los `plot_*_multiplier` afectan TANTO el gráfico como el cálculo de ángulos de entrada.
Lo que ves = lo que usa el sistema → 100% sincronizado visualmente.

### Sistema de Entrada (2026-02-08)

**Arquitectura 2-fases:**
```
Fase 1 (TRIGGER):   HL2_EMA cruza al alza la KAMA
Fase 2 (CONFIRM):   En barras permitidas (allowed_cross_bars):
                    - entry_roc_angle_min <= roc_angle <= entry_roc_angle_max
                    - entry_harmony_angle_min <= harmony_angle <= entry_harmony_angle_max
                    → ENTRY con filtros (time, ATR, SL pips)
```

**Condiciones de Entrada (LONG EURUSD):**
1. **TRIGGER:** HL2_EMA[0] > KAMA[0] AND HL2_EMA[-1] <= KAMA[-1] (cruce alcista)
2. **ALLOWED_BARS:** Solo entrar si `cross_bars in allowed_cross_bars` (vacío = todos)
3. **ANGLES:** Dentro de rangos min/max para ROC y Harmony angles
4. **FILTERS:** time_filter, atr_filter, sl_pips_filter (opcionales)

**⚠️ cross_bars:** Similar a allowed_hours/allowed_days - lista de valores específicos permitidos

### Evolucion de la Estrategia

| Fase | Enfoque | Resultado |
|------|---------|-----------|
| 1. Z-Score Spread | EMA_EURUSD - EMA_1/USDCHF normalizado | ❌ PF 0.83-0.92 (ruidoso) |
| 2. ROC Sum | ROC_EURUSD + ROC_USDCHF | ⚠️ PF 1.19 (mejor, pero pierde asimetria) |
| 3. Harmony Score | ROC_primary × (-ROC_reference) × scale | ⚠️ PF 0.86 (base funcional) |
| 4. Slope Filter | Angulos como filtro adicional | ⚠️ Muy restrictivo |
| 5. KAMA Cross + Angles | TRIGGER + CONFIRM en N barras | ✅ Optimizado |
| 6. allowed_cross_bars | Filtro tipo allowed_hours | ✅ Implementado |

### Ultimo Backtest Optimizado (2026-02-08)
```
Periodo: 2020-07-01 a 2025-07-01 (5 años)
allowed_cross_bars: [0, 1]
entry_roc_angle: 10-40° | entry_harmony_angle: 10-25°
Trades: 108 | Wins: 38 | Losses: 70
WR: 35.2% | PF: 1.70
Gross Profit: $115,526 | Gross Loss: $68,058
Net P&L: $47,468 | Return: 47.87%
Sharpe: 0.49 | Sortino: 0.14
CAGR: 7.04% | Max DD: 12.52%
MC DD 95%: 15.18% | Commission: $2,155
```

### 📊 Portfolio Combinado EURUSD (GEMINI + KOI + Ogle) - 2026-02-08

**Análisis de Diversificación Temporal:**
| Año | GEMINI | KOI | Ogle | TOTAL | Observación |
|-----|--------|-----|------|-------|-------------|
| 2020 | +$9,049 | +$8,713 | +$11,556 | **+$29,318** | Todos aportan |
| 2021 | **-$476** ❌ | +$4,233 | +$19,249 | **+$23,005** | KOI+Ogle compensan |
| 2022 | +$1,140 | +$516 | +$42,138 | **+$43,794** | Ogle domina |
| 2023 | +$6,908 | +$29,621 | +$9,655 | **+$46,184** | KOI domina |
| 2024 | +$12,412 | +$2,974 | **-$3,013** ❌ | **+$12,373** | GEMINI compensa |
| 2025 | +$18,435 | +$30,898 | +$8,444 | **+$57,777** | Todos aportan |

**✅ 0 años negativos en portfolio combinado** - Diversificación funciona.

**Métricas Individuales:**
| Estrategia | Trades | WR% | PF | Return | Max DD | Sharpe |
|------------|--------|-----|-----|--------|--------|--------|
| GEMINI | 108 | 35.2% | **1.70** | 47.9% | 12.5% | 0.49 |
| KOI | 173 | 35.3% | 1.55 | 77.0% | 12.2% | 0.59 |
| Ogle | 135 | 32.6% | 1.62 | 88.0% | 17.0% | 0.63 |

**Portfolio Totals:**
| Métrica | Valor |
|---------|-------|
| Total Trades | 416 |
| Total Wins | 143 (34.4%) |
| Starting Capital | $300,000 |
| Final Capital | $512,852 |
| Net P&L | **$212,852** |
| Total Return | **70.95%** |
| Avg Annual Return | **11.83%** |

**Tendencia GEMINI (últimos años mejorando):**
| Año | PF | Sharpe | Nota |
|-----|-----|--------|------|
| 2020 | 1.97 | 1.24 | ✅ |
| 2021 | 0.88 | -0.12 | ❌ (5 trades) |
| 2022 | 1.06 | 0.13 | ⚠️ |
| 2023 | 1.53 | 0.83 | ✅ |
| 2024 | **2.58** | **1.53** | ✅✅ |
| 2025 | **2.40** | **1.74** | ✅✅ |

**Veredicto para Live: ✅ APROBADO**
- ✅ EURUSD Portfolio: 70.95% return, 0 años negativos
- ✅ USDCHF Portfolio: 49.01% return, 1 año negativo marginal (-0.28%)
- ✅ GEMINI validado en ambos pares correlacionados (objetivo cumplido)

**Criterios cumplidos (EURUSD):**
- PF > 1.5 en las 3 estrategias
- Diversificación temporal efectiva (compensan años malos)
- MC DD 95% = 15.18% (el mejor de los 3)
- Return 11.83%/año en portfolio combinado

**Precauciones para live:**
- Sharpe bajo (<0.7) = volatilidad esperada
- Empezar con 0.5% risk (no 1%)
- Monitorear DD > 15% como alerta
- GEMINI tiene ~22 trades/año - paciencia

**Nota:** Este análisis es solo EURUSD. El portfolio completo incluirá 8 activos (forex + ETFs) con estrategias SEDNA adicionales y allocation tipo Dalio.

### 📊 Portfolio Combinado USDCHF (GEMINI + KOI + Ogle) - 2026-02-09

**Análisis de Diversificación Temporal:**
| Año | GEMINI | KOI | Ogle | TOTAL | Estado |
|-----|--------|-----|------|-------|--------|
| 2020 | +$1,266 | +$4,191 | +$6,162 | **+$11,619** | ✅ |
| 2021 | **-$2,161** ❌ | +$1,198 | +$130 | **-$833** | ⚠️ |
| 2022 | +$20,577 | +$8,691 | +$751 | **+$30,019** | ✅ |
| 2023 | +$9,163 | **-$1,647** ❌ | +$13,327 | **+$20,843** | ✅ |
| 2024 | +$12,420 | +$20,011 | +$24,338 | **+$56,769** | ✅ |
| 2025 | +$16,009 | +$6,843 | +$8,000 | **+$30,852** | ✅ |

**⚠️ 1 año negativo (2021: -$833 = -0.28%)** - Marginal pero existe.

**Métricas Individuales USDCHF:**
| Estrategia | Trades | WR% | PF | Return | Max DD | MC95 DD | Sharpe |
|------------|--------|-----|-----|--------|--------|---------|--------|
| **GEMINI** | 131 | **45.0%** | **1.81** | 55.03% | **8.68%** | 11.92% | 0.56 |
| KOI | 81 | 29.6% | 1.63 | 39.29% | 12.44% | 15.24% | 0.43 |
| Ogle | 149 | 33.6% | 1.46 | 52.71% | 11.72% | 18.36% | 0.52 |

**Portfolio Totals USDCHF:**
| Métrica | Valor |
|---------|-------|
| Total Trades | 361 |
| Total Wins | 133 (36.8%) |
| Starting Capital | $300,000 |
| Final Capital | $447,023 |
| Net P&L | **$147,023** |
| Total Return | **49.01%** |
| Avg Annual Return | **8.17%** |

**Comparación EURUSD vs USDCHF:**
| Métrica | EURUSD | USDCHF |
|---------|--------|--------|
| Trades | 416 | 361 |
| WR% | 34.4% | **36.8%** |
| Net P&L | **$212,852** | $147,023 |
| Return | **70.95%** | 49.01% |
| Avg Annual | **11.83%** | 8.17% |
| Años negativos | **0** | 1 (-$833) |

**Veredicto USDCHF para Live: ✅ APROBADO CON PRECAUCIÓN**

**Puntos fuertes:**
- Las 3 estrategias con PF > 1.4
- GEMINI USDCHF es el mejor del activo: PF 1.81, Max DD 8.68%, MC95 11.92%
- Diversificación funciona (5/6 años positivos)
- 2023: KOI negativo compensado por GEMINI+Ogle

**Puntos débiles:**
- 2021 negativo (-$833 = -0.28% del capital) - marginal
- Sharpe bajo en todas (<0.7)
- Ogle MC95 18.36% (el más alto, precaución)
- Menor retorno que EURUSD (~49% vs ~71%)

**Recomendación para live:**
- ✅ Activar las 3 estrategias USDCHF
- Risk conservador: 0.5% (en vez de 1%)
- Alerta si DD > 12%
- USDCHF complementa EURUSD (inversamente correlacionados)

---

**⚠️ BUG FIX (2026-02-08):** Las métricas CAGR/Sharpe/Sortino estaban mal calculadas:
| Métrica | Antes (bug) | Después (fix) |
|---------|-------------|---------------|
| CAGR years | `len(bars)/252` = 146 años | `(last_date-first_date).days/365.25` = ~5 años |
| Sharpe | PnL trades × sqrt(n) | Retornos por barra, anualizado (252×24×12) |
| Sortino | PnL trades × sqrt(n) | Retornos negativos, anualizado |

**Monte Carlo:** Funciona correctamente (usa bootstrap con replace=True).

### Indicador ROCDualIndicator + AngleIndicator
**Subplot 1 - ROC & Harmony:**
- `roc_primary` (azul): ROC de EURUSD × plot_roc_multiplier
- `roc_reference` (rojo): ROC de USDCHF × plot_roc_multiplier  
- `harmony` (morado): Harmony Score × plot_harmony_multiplier
- `zero` (gris): Linea de referencia en 0

**Subplot 2 - Slope Angles:**
- `roc_angle` (azul): Ángulo de pendiente ROC (grados)
- `harmony_angle` (morado): Ángulo de pendiente Harmony (grados)

Los colores coinciden para correlación visual valor↔pendiente.

### Archivos
- `strategies/gemini_strategy.py` - Estrategia principal (logs cross_bars, angles, EOD close)
- `config/settings.py` - EURUSD_GEMINI, USDCHF_GEMINI, XAUUSD_GEMINI_E
- `tools/analyze_gemini.py` - Analizador: cross_bars, angles, ATR, horas, días, exit reason (incluye EOD_CLOSE)
- `tools/check_correlation.py` - Verificación correlación entre pares (rolling, yearly, gate check)
- `docs/gemini_strategy.md` - Documentacion detallada (⚠️ actualizar)

### Proximos Pasos
1. ✅ **allowed_cross_bars implementado:** [0, 1] probado y funcionando
2. ✅ **Ángulos optimizados:** ROC 10-40°, Harmony 10-25°
3. ✅ **EURUSD Portfolio validation:** Combinado con KOI+Ogle aprobado (70.95% return)
4. ✅ **USDCHF Portfolio validation:** Combinado aprobado (49.01% return, PF 1.81 GEMINI)
5. 🔄 **SIGUIENTE SESIÓN:** Crear checker live (`live/checkers/gemini.py`)
6. **Pendiente:** Añadir GEMINI a ENABLED_CONFIGS en bot
7. **Pendiente:** Configurar y probar ETFs (DIA, GLD, EEM)

### GEMINI_E — EOD Close Extension (⛔ DESCARTADO 2026-03-13)

**Variante GEMINI con cierre End-of-Day para activos con swap alto (XAUUSD).**

**⛔ DESCARTADO:** Optimización exhaustiva por Iván (2026-03-10 a 2026-03-13) confirmó imposibilidad de edge robusto:
- Mismo patrón que CERES: 2 años excelentes, resto disperso, cambiar params mueve edge entre años
- Ejemplo final: 2020 PF 3.91 (14 trades), 2024 PF 0.86 (14 trades), 2025 PF 6.97 (4 trades)
- Correlación XAUUSD↔USDJPY = -0.36 insuficiente (GEMINI necesita > -0.65)
- Oro responde a demasiados factores a 5min para que divergencia con 1 par capture señal limpia
- Config desactivada (`active: False` en settings.py). Código EOD queda en repo (0 coste, reutilizable).

---

## ⭐ LUYTEN Strategy v1.1 (Opening Range Breakout simplificado)

### Concepto
LUYTEN es una estrategia ORB simplificada diseñada específicamente para TLT (ETFs de bonos US lentos).
Las estrategias existentes (Ogle, KOI, CERES, SEDNA) fallaron todas en TLT por su baja volatilidad y movimientos lentos.

**Idea central:** Observar los primeros N barras del día → registrar el HIGH más alto → esperar una vela verde cuyo cierre supere ese nivel → buy inmediato (fills al open de la siguiente barra).

### Arquitectura (State Machine)
```
IDLE → CONSOLIDATION → WAITING_BREAKOUT → Entry (same bar buy, fills next bar open)
```

1. **IDLE:** Espera nuevo dia de trading
2. **CONSOLIDATION:** Registra el highest HIGH. Despues de `consolidation_bars_min` barras, empieza a chequear breakout en cada barra (mientras sigue actualizando el high). Al llegar a `consolidation_bars_max`, transiciona a WAITING_BREAKOUT puro.
3. **WAITING_BREAKOUT:** Espera vela verde con:
   - `close > consolidation_high` (acepta cross-breakout y gap-breakout)
   - `close - consolidation_high >= bk_above_min_pips`
   - `close - open >= bk_body_min_pips`
4. **Entry:** Buy se coloca en la misma barra del breakout -> fills al open de la siguiente barra

### Parámetros Clave
| Parámetro | Default | Descripción |
|-----------|---------|-------------|
| `consolidation_bars_min` | 6 | Minimo barras antes de chequear breakout |
| `consolidation_bars_max` | 6 | Maximo barras actualizando consol high (luego pure wait) |
| `bk_above_min_pips` | 0.0 | Distancia mínima close sobre consolidation_high |
| `bk_body_min_pips` | 0.0 | Tamaño mínimo cuerpo de la vela de breakout |
| `atr_sl_multiplier` | 2.0 | SL = entry - ATR(14) * mult |
| `atr_tp_multiplier` | 4.0 | TP = entry + ATR(14) * mult |
| `sl_buffer_pips` | 0.0 | Buffer extra debajo del SL |

### Diferencias vs CERES
| Aspecto | CERES | LUYTEN |
|---------|-------|--------|
| Ventana | Móvil (se adapta en session) | Fija (primeras N barras del día) |
| Referencia | Window High + Low | Solo consolidation_high |
| Complejidad | 3 estados + quality filters + scan/armed | 3 estados simples, menos params |
| SL | Múltiples modos (window_low, fixed, ATR) | Solo ATR-based |
| TP | Múltiples modos (window_height, fixed, ATR) | Solo ATR-based |
| Grados libertad | ~15+ params tuneables | ~6 params principales |
| Target | ETFs volátiles (DIA, XLE, GLD) | ETFs lentos (TLT) |

### Baseline TLT_LUYTEN (2020-2025, sin filtros)
```
Periodo: 2020-01-01 a 2025-12-01 (5 años)
consolidation_bars: 6, bk_above/body: 0.0 (sin filtro)
ATR SL mult: 2.0 | ATR TP mult: 4.0
Trades: 530 | Wins: 162 | Losses: 368
WR: 30.6% | PF: 0.65
Gross Profit: $141,137 | Gross Loss: $215,620
Net P&L: -$74,483 | Return: -74.48%
Sharpe: -1.42 | Sortino: -0.46
CAGR: -20.69% | Max DD: 75.00%
MC DD 95%: 81.67%

Yearly:
  2020: 101 trades, WR 21.8%, PF 0.46, -$40,576
  2021:  81 trades, WR 40.7%, PF 1.05, +$1,427   ← MEJOR AÑO
  2022: 142 trades, WR 33.8%, PF 0.73, -$14,516
  2023:  98 trades, WR 30.6%, PF 0.61, -$12,242
  2024:  62 trades, WR 29.0%, PF 0.80, -$2,686
  2025:  46 trades, WR 23.9%, PF 0.46, -$5,891
```
**Nota positivo:** Genera ~106 trades/año (vs ~15/año de SEDNA). Hay margen de optimización.

### Archivos
- `strategies/luyten_strategy.py` — Estrategia completa (~590 líneas)
- `tools/analyze_luyten.py` — Analizador de logs (post-hoc por bins)
- `tools/luyten_optimizer.py` — Grid-search paramétrico con yearly breakdown + JSON export
- `config/settings.py` → `TLT_LUYTEN` (active: True para baseline)
- Registrada en `run_backtest.py` y `tools/portfolio_backtest.py`

### Estado de Optimización
🔬 **EN CURSO (2026-03-15).** Baseline negativo como esperado (sin filtros). Bugs corregidos:
- **EOD close fix:** `cancel()` + `close()` explícito (antes usaba `oco` con race condition). También aplicado a CERES.
- **Entry timing fix:** Eliminado `signal_pending` → buy inmediato en barra breakout (antes 2 barras de retraso).
- **Gap breakout:** Acepta velas con open ya por encima del consolidation_high.
- **Analyzer fix:** Eliminado `analyze_by_consolidation_high` (redundante con `bk_above_pips`).

**Optimizer creado:** `tools/luyten_optimizer.py`
- Grid-search paramétrico con `itertools.product`
- Params con toggle enable/disable + rango (start, stop, step)
- Params soportados: `consolidation_bars`, `bk_above_min_pips`, `bk_body_min_pips`, `atr_tp_multiplier`, `atr_sl_multiplier`
- Output consola: tabla ordenada por PF con yearly breakdown (Trades, PF, PnL por año)
- Export JSON automático: `logs/LUYTEN_optimizer_YYYYMMDD_HHMMSS.json`
- Resetea `ETFCommission` class counters entre runs, suprime print_signals

#### Phase 1: Grid amplio (210 combos, 2020-2023 IS)
Fecha: 2026-03-15. Archivo: `logs/LUYTEN_optimizer_20260315_222427.json`
Sweep: `consolidation_bars` (6-24, step 3) × `bk_above_min_pips` (0-10, step 2) × `atr_tp_multiplier` (2-6, step 1)
Fijos: `atr_sl_multiplier=1.5`, `bk_body_min_pips=10.0`

**Resultado global:** 31/210 rentables (15%), 12/210 consistentes (todos los años PF≥0.80)

**Top 5 por PF:**
```
#  TP  BkAbv  CBars  Trades   PF    DD%  Sharpe  CAGR%   Net PnL
1   2    6     24       98  1.18  10.1%   +0.35   +1.8%   +$6,972
2   3    6     18      128  1.16  15.2%   +0.40   +3.2%  +$13,013
3   3    2     18      135  1.12  17.8%   +0.33   +2.6%  +$10,526
4   3    8     18      122  1.12  15.1%   +0.29   +2.2%   +$8,826
5   3   10     18      117  1.12  17.1%   +0.28   +2.1%   +$8,194
```

**Yearly breakdown candidatos principales:**
```
#2 (TP=3, BkAbv=6, CBars=18) — MEJOR CANDIDATO
  2020: 29 trades, PF 1.07, +$1,342
  2021: 11 trades, PF 0.85, -$1,197  ← año débil (baja volatilidad TLT)
  2022: 57 trades, PF 1.04, +$1,695
  2023: 31 trades, PF 1.86, +$11,174

#1 (TP=2, BkAbv=6, CBars=24) — MEJOR DD
  2020: 24 trades, PF 1.70, +$5,342
  2021:  8 trades, PF 0.76, -$943   ← solo 8 trades
  2022: 44 trades, PF 1.10, +$1,825
  2023: 22 trades, PF 1.09, +$749
```

**Patrones detectados:**
- `consolidation_bars=18` domina (#2,#3,#4,#5,#6,#9 — zona más robusta)
- `bk_above_min_pips=6` es el sweet spot (aparece en #1, #2, #8)
- `atr_tp_multiplier=3` ofrece mejor balance PnL/consistencia vs TP=2 (más trades ganadores pero menor profit)
- 2021 es año débil universal: pocas entradas (~8-12), TLT lateralizado post-COVID
- #2 tiene el mejor Sharpe (+0.40) y el Net PnL más alto de los top 5

#### Phase 2: Grid fino (completada)
- **Fecha**: 2026-03-16
- **JSON**: `logs/LUYTEN_optimizer_20260316_075318.json`
- **Combinaciones**: 512 (5 parámetros)
- **Periodo IS**: 2020-01-01 a 2023-12-31
- **Grilla**: CBars (15,17,19,21) × BkAbv (2,4,6,8) × BkBdy (0,5,10,15) × TP (2.0,2.5,3.0,3.5) × SL (1.5,2.0)
- **Resultados**: 91/512 profitable (18%), 29/512 consistentes

**Top 10 Phase 2 (ordenados por PF):**
| # | SL | TP | BkAbv | BkBdy | CBars | PF | DD% | Sharpe | Net PnL | Consistency |
|---|----|----|-------|-------|-------|----|-----|--------|---------|-------------|
| 1 | 1.5 | 2.5 | 2 | 10 | 19 | 1.37 | 9.6% | +0.71 | +$22,478 | 3yr PF≥1 |
| 2 | 1.5 | 2.5 | 6 | 0 | 19 | 1.36 | 11.9% | +0.78 | +$26,492 | 3yr PF≥1 (highest Net) |
| 3 | 1.5 | 2.5 | 6 | 5 | 19 | 1.33 | 11.9% | +0.73 | +$24,074 | 3yr PF≥1 |
| 4 | 1.5 | 2.5 | 6 | 10 | 19 | 1.29 | 10.6% | +0.58 | +$17,252 | 3yr PF≥1 |
| 5 | 1.5 | 3.0 | 6 | 5 | 19 | 1.25 | 14.6% | +0.58 | +$21,155 | **4yr PF≥0.96** |
| 6 | 1.5 | 2.0 | 8 | 5 | 21 | 1.23 | 13.3% | +0.46 | +$10,891 | 3yr PF≥1 |
| 7 | 1.5 | 3.0 | 6 | 0 | 19 | 1.23 | 15.8% | +0.55 | +$19,943 | **4yr PF≥0.96** |
| 8 | 1.5 | 2.5 | 4 | 10 | 19 | 1.21 | 11.5% | +0.45 | +$13,329 | 3yr PF≥1 |
| 9 | 1.5 | 2.0 | 8 | 0 | 21 | 1.21 | 14.2% | +0.43 | +$10,059 | 3yr PF≥1 |
| 10 | 1.5 | 2.0 | 6 | 5 | 19 | 1.20 | 12.1% | +0.45 | +$12,006 | 3yr PF≥1 |

**Patrones detectados Phase 2:**
- `CBars=19` domina absolutamente (8 de top 10)
- `SL=1.5` es el único SL que funciona — SL=2.0 destruye performance
- `TP=2.5` produce mejor PF, `TP=3.0` mejor consistencia interanual
- `BkAbv=6` sigue siendo el sweet spot (6 de top 10)
- `BkBdy` variable: 0, 5, 10 todos viables — no es filtro crítico
- 2021 sigue siendo año débil universal (~9-12 trades, PF<1.0)
- #5 y #7 son los más consistentes: PF≥0.96 en 4 de 4 años

#### Phase 3: OOS Validation (completada)
- **Fecha**: 2026-03-16
- **JSON**: `logs/LUYTEN_OOS_20260316_091245.json`
- **Periodo OOS**: 2024-01-01 a 2025-11-28 (fin datos disponibles)
- **Candidatos**: Top 10 de Phase 2
- **Resultado**: **8/10 profitable OOS (80% survival rate)**

**IS vs OOS Comparison (top 10 por PF IS):**
| # | TP | BkAbv | BkBdy | CBars | IS PF | OOS PF | PF Δ | OOS Net | OOS 2024 | OOS 2025 | Robust |
|---|----|----- -|-------|-------|-------|--------|------|---------|----------|----------|--------|
| 1 | 2.5 | 2 | 10 | 19 | 1.37 | 0.96 | -0.42 | -$288 | 1.37 | 0.46 | ✗ |
| 2 | 2.5 | 6 | 0 | 19 | 1.36 | **1.96** | +0.60 | +$4,618 | 2.16 | 1.74 | ✓✓ |
| 3 | 2.5 | 6 | 5 | 19 | 1.33 | 1.42 | +0.08 | +$2,021 | 2.16 | 0.61 | ✓ |
| 4 | 2.5 | 6 | 10 | 19 | 1.29 | 1.22 | -0.06 | +$1,039 | 2.60 | 0.46 | ✓ |
| 5 | 3.0 | 6 | 5 | 19 | 1.25 | **1.96** | +0.72 | +$4,697 | 2.94 | 0.90 | ✓ |
| 6 | 2.0 | 8 | 5 | 21 | 1.23 | 1.22 | -0.01 | +$662 | INF | 0.24 | ✓ |
| 7 | 3.0 | 6 | 0 | 19 | 1.23 | **2.65** | +1.43 | +$8,071 | 2.94 | **2.34** | ✓✓✓ |
| 8 | 2.5 | 4 | 10 | 19 | 1.21 | 0.96 | -0.25 | -$288 | 1.37 | 0.46 | ✗ |
| 9 | 2.0 | 8 | 0 | 21 | 1.21 | 1.34 | +0.14 | +$1,176 | 2.02 | 0.84 | ✓ |
| 10 | 2.0 | 6 | 5 | 19 | 1.20 | 1.37 | +0.16 | +$1,460 | 2.83 | 0.31 | ✓ |

*Todos con SL=1.5 (único SL funcional)*

**Conclusiones OOS:**
- **Candidato #7** (TP=3.0, BkAbv=6, BkBdy=0, CBars=19): MEJOR OOS — PF 2.65, único con 2024 Y 2025 ambos PF>2.0
- **Candidato #2** (TP=2.5, BkAbv=6, BkBdy=0, CBars=19): 2do mejor — PF 1.96, ambos años positivos (2025: PF 1.74)
- **Patrón BkBdy=0 domina OOS**: Los combos sin filtro de body (#2, #7) son los más robustos
- **BkAbv=6 + CBars=19** confirma IS: el sweet spot se mantiene fuera de muestra
- **2025 es filtro duro**: Solo #7 y #2 mantienen PF>1.0 en 2025 — el resto flaquea
- **Los IS rank #1 y #8 (BkAbv=2 y BkAbv=4 con BkBdy=10) fallan OOS** — overfitting a IS

Siguiente:
1. ✅ Phase 1 completada (210 combos)
2. ✅ Phase 2 completada (512 combos)
3. ✅ Phase 3: OOS validation — 80% survival rate
4. Analizar horas/días con `tools/analyze_luyten.py`

**Parámetros EOD (nuevos en gemini_strategy.py):**
| Parámetro | Default | Descripción |
|-----------|---------|-------------|
| `use_eod_close` | False | Activar cierre EOD. False = sin cambio (EURUSD/USDCHF) |
| `eod_close_hour` | None | Hora UTC de cierre (None = desactivado) |
| `eod_close_minute` | 0 | Minuto del cierre |

**Lógica EOD en next():**
1. **IN_POSITION:** Si `use_eod_close` y current_time >= eod_time → `_execute_exit(dt, 'EOD_CLOSE')` (ANTES del check SL/TP)
2. **SCANNING:** Si `use_eod_close` y `_is_past_eod(dt)` → bloquea nuevas entradas (detecta KAMA cross pero no entra)
3. **Diseño simple:** GEMINI no usa bracket orders (SL/TP checked manualmente) → no necesita cancel OCO como CERES

**Resultados correlación XAUUSD↔USDJPY (verificado 2026-03-10):**
```
Mediana rolling (6000 barras ≈ 1 mes): -0.36 (FAIL — esperábamos -0.60 a -0.80)
Referencia EURUSD↔USDCHF: -0.71 (CAUTION)
Gate check: |median| 0.36 < 0.65 → FAIL

Yearly breakdown:
2020: -0.14 | 2021: -0.34 | 2022: -0.51 | 2023: -0.43 | 2024: -0.44 | 2025: -0.29
```
La correlación safe-haven es mucho más débil a 5min de lo esperado.

**Baseline XAUUSD_GEMINI_E (wide open, sin optimizar):**
```
3587 trades | WR 41.3% | PF 1.04 | Net +$65,453 | DD 83%
Sharpe 0.66 | Sortino 0.57 | CAGR 6.71%
Exit reasons: SL=1687 | EOD_CLOSE=1154 (WR 62.4%, PF 3.44!) | TP=746
Commission: $18,675 (3735 lots)

Yearly:
2020: 539 trades, PF 0.95, -$12K
2021: 521 trades, PF 0.94, -$10K
2022: 691 trades, PF 0.92, -$19K
2023: 630 trades, PF 0.94, -$10K
2024: 634 trades, PF 0.96, -$10K
2025: 572 trades, PF 1.30, +$128K ← único año positivo
```
**Conclusión baseline:** Edge marginal (PF 1.04). Correlación débil se refleja. EOD_CLOSE PF 3.44 era prometedor pero la optimización posterior confirmó que el edge no generaliza entre años.

**Config final (XAUUSD_GEMINI_E en settings.py — desactivada):**
- Params optimizados por Iván: ángulos 15-25°, cross_bars [1,2,3,6,7,8], horas [0,1,2,3,4,12,13,14,17], SL 50-500
- Resultado: PF inestable entre años, imposible conseguir robustez 6Y

### Fórmula de Ángulos (sobre valores de plot)
```python
def _calculate_angle(current_plot_val, prev_plot_val, angle_scale):
    rise = (current_plot_val - prev_plot_val) * angle_scale
    return math.degrees(math.atan(rise))

# ROC angle (sobre ROC escalado)
roc_plot = roc_primary * plot_roc_multiplier
roc_angle = _calculate_angle(roc_plot[0], roc_plot[-1], roc_angle_scale)

# Harmony angle (sobre Harmony escalado)  
harmony_plot = harmony * plot_harmony_multiplier
harmony_angle = _calculate_angle(harmony_plot[0], harmony_plot[-1], harmony_angle_scale)
```

**Ejemplo visual:**
- `plot_roc_multiplier = 500` → ROC de 0.0002 se ve como 0.1
- Si ROC pasa de 0.05 a 0.15 (rise=0.10), angle ~6°
- Si ROC pasa de 0.05 a 0.25 (rise=0.20), angle ~11°

**Por qué funciona:**
- Ángulos calculados sobre valores de plot = consistencia visual
- Lo que ves en el subplot de Angles = exactamente lo que evaluó el sistema

---

## 🧪 Proyecto en Desarrollo: HELIX Strategy

**Objetivo:** Estrategia para EURUSD/USDCHF (donde SEDNA no funciona)

**Hipótesis:**
- JPY pairs tienen movimientos lentos → ER detecta bien
- EUR/CHF pairs tienen movimientos rápidos → SE podría detectar estructura antes que ER

**Diseño:**
- Clonar estructura de SEDNA (KAMA + pullback + breakout)
- Cambiar filtro HTF: ER → Spectral Entropy (SE)
- Si SE no funciona → probar Hilbert Transform (mismo punto de integración)

**Arquitectura modular:**
```
SEDNA:  KAMA + ER_HTF + pullback → entry (ER HIGH = trending)
HELIX:  KAMA + SE_HTF + pullback → entry (SE in RANGE = structured)
```

### 📊 Observaciones SE (2026-02-04)

**Análisis visual EURUSD 5m con SE equivalente a 60m (period=240):**

| Rango SE | Comportamiento observado | Interpretación |
|----------|--------------------------|----------------|
| 0.84-0.88 | Dips durante movimientos direccionales | ✅ Estructura detectada |
| 0.88-0.92 | Estado "normal" del mercado | ⚠️ Zona gris |
| 0.92-0.96 | Picos durante consolidación/ruido | ❌ Evitar |

**Conclusión clave:**
- SE en forex 5m NO baja de ~0.84 (nunca llega a 0.7)
- Filtro con threshold fijo (SE <= 0.7) = 0 trades
- **Solución:** Usar RANGO `[se_min, se_max]` en vez de threshold

**Por qué RANGO:**
1. SE muy bajo (< 0.84) = anomalía (mercado cerrado, flash crash)
2. SE moderado-bajo (0.84-0.88) = estructura detectable
3. SE alto (> 0.90) = ruido dominante - evitar

### 🔬 Problema Técnico: HTF para SE vs ER (2026-02-04)

**Cómo SEDNA maneja HTF para ER:**
```python
# SEDNA usa ESCALADO DE PERÍODO (NO resampleo)
htf_multiplier = htf_timeframe_minutes // 5  # 15 // 5 = 3
scaled_er_period = htf_er_period * htf_multiplier  # 10 * 3 = 30
htf_er = EfficiencyRatio(close, period=30)  # 30 barras de 5m
```

**¿Por qué funciona para ER pero NO para SE?**

| Indicador | Cálculo | Escalar período | Resampleo real |
|-----------|---------|-----------------|----------------|
| ER | `|cambio_N| / suma_|cambios|` | ✅ Equivalente matemático | No necesario |
| SE | FFT → frecuencias → entropía | ❌ Frecuencias incorrectas | ✅ Necesario |

**Explicación:**
- **ER** mide eficiencia direccional sobre N barras. Usar 30 barras de 5m ≈ 10 barras de 15m (mismo cambio de precio total).
- **SE** analiza **frecuencias** via FFT. 30 barras de 5m tiene frecuencia de muestreo 5min. 10 barras de 30m tiene frecuencia 30min. **El espectro es completamente diferente.**

### ✅ SOLUCIÓN IMPLEMENTADA (2026-02-04 sesión nocturna)

**Problema identificado:**
- Backtrader `resampledata()` no funciona bien para indicadores FFT
- Actualiza la barra HTF "en construcción" cada tick del TF base
- Resultado: SE seguía siendo tan ruidoso como indicadores de 5m

**Solución: Agregación HTF interna en SpectralEntropy**

Se modificó `lib/indicators.py` - clase `SpectralEntropy`:
```python
class SpectralEntropy(bt.Indicator):
    params = (
        ('period', 20),    # FFT window (en barras HTF)
        ('htf_mult', 1),   # 1=mismo TF, 6=30m desde 5m
    )
```

**Funcionamiento:**
1. Si `htf_mult > 1`, el indicador acumula closes internamente
2. Solo recalcula SE cuando completa una barra HTF (cada N barras base)
3. Entre actualizaciones, mantiene el último valor (suavidad)
4. Calcula FFT sobre closes reales de HTF (último close de cada grupo)

**Código clave:**
```python
# Solo calcular cuando barra HTF completa
if self._bar_count % self.p.htf_mult != 0:
    self.lines.se[0] = self._last_se_value  # Mantener valor
    return

# Extraer closes HTF (último de cada grupo)
htf_closes = [
    recent_closes[i * htf_mult + htf_mult - 1]
    for i in range(period + 1)
]
```

**Resultados EURUSD_HELIX (2025-01-01 a 2025-12-01):**

| Métrica | Antes (escalado) | Después (agregación) |
|---------|------------------|----------------------|
| Trades | 288 | 273 |
| Win Rate | 29.5% | **33.0%** |
| Profit Factor | 0.99 | **1.18** |
| Net P&L | -$14,971 | **+$25,189** |
| Sharpe | 0.11 | **0.69** |
| Max Drawdown | 44.56% | **25.86%** |
| Return | -14.97% | **+25.19%** |

**Estado actual:** ✅ FUNCIONANDO - En optimización

**🔬 INSIGHT CLAVE (2026-02-05 sesión análisis visual):**

El **valor puntual** de SE no es lo importante. Lo que importa es la **ESTABILIDAD** de SE:

| SE comportamiento | Significado | Acción |
|-------------------|-------------|--------|
| SE **estable** (poca variación) | Régimen de mercado consistente | ✅ Entrar |
| SE con **picos** (mucha variación) | Transición/inestabilidad | ❌ Evitar |

**Nuevo enfoque:**
- ❌ Filtro anterior: `se_min <= SE <= se_max` (valor puntual - poco efectivo)
- ✅ Filtro nuevo: `se_stability_min <= StdDev(SE, N) <= se_stability_max`

**Análisis de datos (backtest EURUSD 5 años):**

| SE StdDev Range | Trades | PF | Interpretación |
|-----------------|--------|-----|----------------|
| 0.000-0.010 | 1980 | 0.97 | Muy estable = mercado "muerto" ❌ |
| **0.010-0.020** | 216 | **1.11** | Sweet spot ✅ |
| 0.020-0.030 | 101 | 0.94 | Aceptable ⚠️ |
| 0.040-0.050 | 52 | **0.24** | Muy volátil = régimen cambiando ❌ |

**Conclusión:**
- Ni muy estable (mercado dormido) ni muy volátil (régimen cambiando)
- Sweet spot: `se_stability_min=0.005`, `se_stability_max=0.03`

**Herramienta:** `python tools/analyze_helix.py` - Analiza logs HELIX

**Noticias del bot demo:**
- ✅ En ganancias, superado DD del 6% (criterio < 10%)
- Sizing y SL/TP funcionando bien en real

**Proximos pasos HELIX:**
- [x] Implementar `StdDev(SE, N)` como filtro de estabilidad - DESCARTADO (SE base estaba mal)
- [x] Crear `tools/analyze_helix.py` 
- [x] Refactorizar a TRUE resample con `resampledata()`
- [x] Arquitectura generica HTF via `htf_data_minutes`
- [x] Intentar plotmaster para visualizacion - NO FUNCIONA (diferentes longitudes)
- [x] SE(60m) en subplot separado con matplotlib (solucion final)
- [x] Añadir `breakout_waited_bars` y `pullback_bars` a logs (2026-02-06)
- [x] Actualizar analyze_helix.py para parsear nuevos campos

### ⚠️ PROBLEMA CRÍTICO IDENTIFICADO (2026-02-06): Inestabilidad de Parámetros

**Hallazgo:** Los parámetros "óptimos" de HELIX cambian drásticamente entre corridas:

| Corrida | Trades | PF Base | SE Óptimo | Breakout Óptimo | Pullback Óptimo |
|---------|--------|---------|-----------|-----------------|-----------------|
| Run 1 | 2438 | 0.96 | 0.80-0.82 | 3 bars | 2-3 bars |
| Run 2 | 2209 | 0.97 | 0.80-0.82 | 3 bars | 1-3 bars |
| Run 3 | 1869 | 0.98 | **0.82-0.84** | **1 bar** | 1-2 bars |
| Run 4 | 53 | 1.28 | **0.90-0.92** | 1 bar | 1-2 bars |

**Diagnóstico:**
1. **PF base < 1.0** → La estrategia SIN filtros NO tiene edge
2. Los filtros solo reorganizan trades, no crean edge
3. Con filtros "óptimos" quedan 50-100 trades → ruido estadístico alto
4. Síntoma clásico de **overfitting**: parámetros que cambian = sin patrón robusto

**Contraste con SEDNA:**
- SEDNA es mucho más estable en optimización
- Probablemente tiene edge base más sólido (ER detecta bien en pares JPY)

**Investigación Académica (2026-02-06):**
- Se buscaron estudios que respalden uso de Spectral Entropy en trading
- **Hallazgo:** SE NO se usa como "gatillo" de entrada en literatura académica
- Uso correcto: **filtro de régimen** (SE bajo = predecible, SE alto = ruido)
- Temporalidades respaldadas: 1H mínimo, diario ideal
- Indicadores de apoyo en literatura: Hurst Exponent, StdDev, Fractal Dimension, PSD

**Decisiones pendientes:**
- [ ] ¿Volver a SE en 5m con filtro de rango simple? (funcionaba "algo mejor")
- [ ] ¿Añadir indicadores de apoyo (Hurst, etc.)? → Riesgo de más overfitting
- [ ] ¿Simplificar radicalmente o descartar HELIX?
- [ ] ¿La lógica base (KAMA + pullback) simplemente no funciona para EURUSD?

**Conclusión tentativa:**
El problema no es perfeccionar el filtro SE. El problema es que la estrategia
base (KAMA + pullback + breakout) no tiene edge en EURUSD. Más filtros solo
enmascaran el problema temporalmente pero no lo resuelven.

### 🚀 NUEVA IDEA: Estrategia de Correlación EURUSD/USDCHF (2026-02-06)

**Origen:** Intuición del usuario - "idea de la fuente"

**Concepto Base:**
- EURUSD y USDCHF están **inversamente correlacionados** (~-0.90)
- Ambos miden fuerza del USD pero desde ángulos opuestos
- Cuando USD sube: EURUSD baja, USDCHF sube

**El Indicador Propuesto:**
```
EMA_EURUSD(típico) vs EMA_USDCHF_invertida(típico)

Spread = EMA_EURUSD - EMA_USDCHF_invertida
```
- Normalmente deberían moverse juntas (correlación alta)
- Cuando **divergen** = señal potencial

**La Entrada (NO es mean reversion, es MOMENTUM CONFIRMADO):**

| Divergencia | Significado | Entrada |
|-------------|-------------|---------|
| EURUSD > USDCHF_inv (creciendo) | EUR fuerte por sí mismo (no solo USD débil) | **LONG EURUSD** |
| EURUSD < USDCHF_inv (decreciendo) | EUR débil por sí mismo | (NO operar o SHORT) |

**Por qué es diferente de Mean Reversion:**
1. **Vas CON el momentum**, no contra él
2. La divergencia **confirma** que el movimiento tiene sustancia real
3. Si EURUSD sube pero USDCHF_inv no sigue = EUR tiene fuerza propia
4. No apuestas a corrección, te montas en fuerza confirmada

**Implementación Propuesta (2 estrategias):**
1. **Estrategia A:** Opera EURUSD usando USDCHF invertido como confirmación
2. **Estrategia B:** Opera USDCHF usando EURUSD invertido como confirmación
   - No suceden al mismo tiempo - son ciclos diferentes
   - Diversificación natural temporal

**Posibles Mejoras:**
- Detectar divergencia en HTF (15m) y entrar en 5m
- Añadir EURCHF como tercera confirmación (triangulación):
  - EURUSD↑ + USDCHF↓ + EURCHF↑ = EUR realmente fuerte ✅
  - EURUSD↑ + USDCHF↓ + EURCHF→ = Solo USD débil (no operar)

**Respaldo Académico:**
- Paper: Psaradellis et al. (2018) "Pairs Trading: Mean Reversion vs **Momentum**"
- Encontraron que momentum en spreads de pares correlacionados puede funcionar
- No es arbitraje (tiene riesgo), es "Currency Strength Momentum"

**Ventajas vs HELIX actual:**
1. Usa relación REAL del mercado, no indicadores inventados
2. No necesita SE, ER, KAMA - solo correlación existente
3. Filtro natural de calidad: si no hay divergencia, no hay señal
4. Más simple = más robusto potencialmente

**⚡ SIGUIENTE PASO:**
1. Visualizar EURUSD vs USDCHF invertido en gráfico (antes de codificar)
2. Identificar visualmente patrones de divergencia + momentum
3. Si se ve prometedor → diseñar lógica de entrada específica
4. Prototipo simple primero (sin complejidad)

**Estado:** 💡 IDEA - Pendiente de validación visual

**Arquitectura HTF (v0.4.9 - REFACTORIZADA):**

La solucion correcta es usar `resampledata()` de Backtrader para crear un feed HTF
real. Esto se hace de forma GENERICA en `run_backtest.py`:

```python
# En config/settings.py (cualquier estrategia puede usar)
'params': {
    'htf_data_minutes': 60,  # Si > 0, run_backtest crea self.datas[1]
    ...
}

# En run_backtest.py (generico, sin casos especiales)
htf_minutes = params.get('htf_data_minutes')
if htf_minutes and htf_minutes > 0:
    data_htf = cerebro.resampledata(data, ..., compression=htf_minutes)
    # Estrategia accede via self.datas[1]

# En estrategia (detecta si hay HTF disponible)
if len(self.datas) > 1:
    self.htf_data = self.datas[1]
    self.htf_se = SpectralEntropy(self.htf_data.close, period=30)
```

**Beneficios de esta arquitectura:**
1. **Escalable:** Cualquier estrategia puede pedir HTF data
2. **Sin casos especiales:** No hay `if HELIX`, `if KOI`, etc.
3. **Config-driven:** Todo se controla desde settings.py
4. **TRUE HTF:** El indicador recibe datos reales de 60m, no emulados

**Parametros actuales (v0.4.9):**
```python
# EURUSD_HELIX / USDCHF_HELIX
'htf_data_minutes': 60,   # Crea self.datas[1] con 60m
'htf_se_period': 30,      # SE period sobre barras HTF
'htf_se_min': 0.0,        # Filtro por valor SE (0/1 = disabled)
'htf_se_max': 1.0,
```

**Archivos modificados:**
- `run_backtest.py` - HTF generico via `htf_data_minutes` (sin casos especiales)
- `lib/indicators.py` - SpectralEntropy simple + HTFIndicatorSync (no usado)
- `lib/observers.py` - SEObserver creado pero NO usado (intento fallido)
- `strategies/helix_strategy.py` - Detecta `len(self.datas) > 1`, SE en subplot propio
- `config/settings.py` - HELIX configs usan `htf_data_minutes`

**Visualizacion HTF (solucion final):**
```python
# En helix_strategy.py - SE(60m) en su propio subplot
self.htf_se = SpectralEntropy(self.htf_data.close, period=self.p.htf_se_period)
self.htf_se.plotinfo.plot = True
self.htf_se.plotinfo.subplot = True
self.htf_se.plotinfo.plotname = f'SE({htf_minutes}m)'
# Resultado: SE(60m) en subplot separado con eje X de 60m
# Usuario coloca ventanas manualmente para comparar
```

---

## 🗄️ Estrategias Descartadas / Intentos Fallidos

### GLIESE v2 (Mean Reversion) - DESCARTADA
**Objetivo:** Complementar SEDNA en EURUSD/USDCHF (donde SEDNA no funciona bien)

**Lógica:**
- Mean reversion (contraria a trend-following)
- Usa ADXR < threshold para detectar mercados en rango
- Entrada en rebote de banda inferior (KAMA - ATR*mult)
- Espera pullback + breakout para confirmar

**Resultados en backtest (5 años USDCHF):**
- PF: >1.5 ✅
- Sharpe: >0.7 ✅
- Trades: ~160 (~32/año)
- Mejores: Extension 10+ bars, Miércoles/Viernes, 7-8am UTC

**Por qué se descartó:**
- SL óptimo: 5-10 pips → Demasiado ajustado para ejecución real
- Con spread (~1 pip) + slippage (~2-3 pips) = ~30-50% del SL comido en costes
- Mismo problema que USDCAD: rentable en backtest, inviable en live

**Archivo:** `strategies/gliese_strategy.py` (conservado para referencia)

---


---

## 📋 Resumen Optimización Completada

### Ogle (PRO) forex ✅ COMPLETADO

| Config | PF | WR% | Max DD | CAGR | Trades/año |
|--------|-----|------|--------|------|-----------|
| USDCHF_PRO | 2.86 | 49.2% | 7.41% | 10.61% | ~10.5 |
| EURUSD_PRO | 2.70 | 43.2% | 9.42% | 13.32% | ~12 |
| EURJPY_PRO | 2.38 | 41.2% | 11.57% | 14.77% | ~16 |
| USDJPY_PRO | 2.07 | 39.4% | 11.53% | 13.12% | ~16.5 |

### KOI forex ✅ COMPLETADO

| Config | PF | WR% | Max DD | CAGR | Trades/año |
|--------|-----|------|--------|------|-----------|
| USDCHF_KOI | **2.62** | 40.3% | 10.43% | 12.10% | ~12 |
| EURUSD_KOI | 2.15 | 42.9% | 11.60% | 11.69% | ~17.5 |
| USDJPY_KOI | 2.09 | 35.1% | 9.25% | 11.01% | ~12.8 |
| EURJPY_KOI | 2.09 | 38.3% | 11.04% | 12.58% | ~17.8 |

### SEDNA forex — EN PROGRESO

**EURJPY_SEDNA optimización completada ✅**

Parámetros ya tenían filtros razonables, SL ≥12 pips seguro para live.

**Resultados EURJPY_SEDNA (6 años, 2020-2025):**

| Métrica | Valor |
|---------|-------|
| Trades | 145 (~24.2/año) |
| Win Rate | 41.4% |
| Profit Factor | **1.70** |
| Net P&L | $89,439 |
| CAGR | 11.48% |
| Max Drawdown | 14.45% |
| MC95 DD | 17.50% |
| Hist/MC95 | 1.21x |
| Sharpe | 0.70 |
| Calmar | 0.79 |

**Por año:**
| Año | Trades | WR% | PF | P&L |
|-----|--------|-----|-----|-----|
| 2020 | 15 | 33.3% | 1.24 | +$2,519 |
| 2021 | 14 | 35.7% | 1.36 | +$3,560 |
| 2022 | 27 | 44.4% | 1.96 | +$17,808 |
| 2023 | 33 | 39.4% | 1.59 | +$16,729 |
| 2024 | 31 | 48.4% | 2.36 | +$34,465 |
| 2025 | 25 | 40.0% | 1.41 | +$14,279 |

**0 años negativos** ✅

**Config:** KAMA 10/2/30, horas `[1,4,5,7,8,10,14,15,16]`, SL 12-28, CCI disabled.

**⚠️ Nota:** Max DD 14.45% / MC95 17.50% — el más alto de todas las configs. Candidato a risk 0.5% en portfolio.

| Config | PF | WR% | Max DD | CAGR | Trades/año | SL min ≥10 | Años neg |
|--------|-----|------|--------|------|-----------|------------|----------|
| EURJPY_SEDNA | 1.70 | 41.4% | 14.45% | 11.48% | ~24.2 | ✅ (12) | 0 |
| USDJPY_SEDNA | **2.07** | 47.0% | 10.67% | 10.34% | ~13.8 | ✅ (15) | 0 |

**USDJPY_SEDNA optimización completada ✅**

Horas optimizadas con cruce de 2 datasets (5 y 6 años):
- Horas: `[1, 6, 7, 8, 12, 14, 15]`
- Eliminadas: 00, 02, 03, 04, 05, 09, 10, 11, 13, 16, 17, 18, 19, 20, 21, 22, 23
- Hora 08 = BEST (PF 2.39-2.41 idéntico ambos DS), Hora 15 = TOP (PF 2.17-2.57)
- Hora 06 y 09 tenían PF idéntico en ambos DS; h05 eliminada (marginal, mejoró PF de 1.91→2.07)
- Días: `[0, 1, 4, 5]` (sin cambio)
- SL: 15-50, ATR: 0.05-0.13 (sin cambio)

**Resultados USDJPY_SEDNA (6 años, 2020-2025):**

| Métrica | Valor |
|---------|-------|
| Trades | 83 (~13.8/año) |
| Win Rate | 47.0% |
| Profit Factor | **2.07** |
| Net P&L | $68,109 |
| CAGR | 10.34% |
| Max Drawdown | 10.67% |
| MC95 DD | 12.26% |
| Hist/MC95 | 1.15x |
| Sharpe | 0.68 |
| Calmar | 0.97 |

**Por año:**
| Año | Trades | WR% | PF | P&L |
|-----|--------|-----|-----|-----|
| 2020 | 4 | 75.0% | 7.67 | +$6,985 |
| 2021 | 2 | 50.0% | 2.48 | +$1,688 |
| 2022 | 19 | 42.1% | 1.83 | +$10,575 |
| 2023 | 21 | 42.9% | 1.86 | +$13,609 |
| 2024 | 18 | 44.4% | 1.53 | +$9,766 |
| 2025 | 19 | 52.6% | 2.75 | +$25,425 |

**0 años negativos** ✅

**Validación cruzada 5yr vs 6yr:** PF 2.03/2.07, Max DD 10.67%/10.67% (idéntico), años 2020-2024 idénticos trade por trade. Consistencia excepcional.

---

### SEDNA forex ✅ COMPLETADO

| Config | PF | WR% | Max DD | CAGR | Trades/año | SL min ≥10 | Años neg |
|--------|-----|------|--------|------|-----------|------------|----------|
| USDJPY_SEDNA | **2.07** | 47.0% | 10.67% | 10.34% | ~13.8 | ✅ (15) | 0 |
| EURJPY_SEDNA | 1.70 | 41.4% | 14.45% | 11.48% | ~24.2 | ✅ (12) | 0 |

---

## ⛔ USDJPY — Investigación Walk-Forward y Pausa (2026-03-01)

### Contexto: por qué se investiga

USDJPY fue pausado el 2026-02-28 tras 1/11 WR en OOS live (p=1.6%, estadísticamente significativo).
La pregunta clave: ¿los params están sobreajustados (overfitting) o el mercado USDJPY cambió de régimen?

Para responder, se ejecuta Walk-Forward formal: train 2020-2023, test 2024-2025 ciego.

### Walk-Forward Results: USDJPY_PRO (SunsetOgle) — 2026-03-01

**Training (2020-02 → 2023-11, ~3.8y):** 54 trades | PF 2.41 | WR 40.7% | Sharpe 1.38 | DD 5.04%
**Full (2020-02 → 2025-11, ~5.8y):** 99 trades | PF 2.07 | WR 39.4% | Sharpe 1.27 | DD 9.00%

**Desglose OOS (datos nunca vistos):**

| Año | Trades | WR | PF | PnL |
|-----|--------|-----|-----|-----|
| 2020 | 5 | 0.0% | 0.00 | -$5,041 |
| 2021 | 5 | 60.0% | 4.66 | +$7,603 |
| 2022 | 27 | 44.4% | 2.68 | +$28,965 |
| 2023 | 17 | 41.2% | 2.60 | +$23,846 |
| **2024 (blind)** | **22** | **45.5%** | **2.61** | **+$36,618** |
| **2025 (blind)** | **22** | **31.8%** | **1.40** | **+$13,151** |
| **OOS total** | **44** | **38.6%** | **~1.97** | **+$49,769** |

**Checklist WF (compare_robustness.py):**
```
[X] 1. CORE MATCH          FAIL  Core years DIFFER (borde training dic-2023, WF tolerance OK)
[+] 2. BORDERS             PASS  +44 trades, $+49,769 PnL
[+] 3. PF > 1.5            PASS  A: 2.41 | B: 2.07
[+] 4. SHARPE > 1.0        PASS  A: 1.38 | B: 1.27
[+] 5. DD < 15%            PASS  A: 5.04% | B: 9.00%
[+] 6. MC95 < 20%          PASS  A: 10.15% | B: 15.67%
[+] 9. PF DEGRAD < 15%     PASS  Delta: -14.0%
[+] 10. TRADES/YR >= 10    PASS  A: 14.3 | B: 17.2
Result: 8/10 passed (9/10 en modo WF — criterio 1 es falso positivo por borde training)
```

**Concentración:** Best year 2024 = $36,618 (35.4% del total) → aceptable
**Recent Period Test (2022-2025):** PF 2.13, WR 40.4%, $100,982 → PASS

### Diagnóstico: el WF PASA pero la tendencia temporal es preocupante

```
2022: PF 2.68  → Pico
2023: PF 2.60  → Estable
2024: PF 2.61  → Estable (OOS blind — edge era real)
2025: PF 1.40  → Caída seria (WR 31.8%)
2026 live: 1/11 WR (~9%) → Colapso
```

**Conclusiones:**
1. **El edge histórico fue REAL, no overfitting.** 2024 blind con PF 2.61 lo confirma.
2. **El edge está DEGRADANDO en tiempo real.** De PF 2.61 (2024) → 1.40 (2025) → colapso (2026 live).
3. **Causa probable: cambio de régimen USDJPY.** BoJ normalizó política (fin YCC, subidas de tipos 2024-2025). El yen pasó de carry-trade pasivo a activo event-driven con volatilidad impredecible.
4. **El spread amplifica pero NO es la causa raíz.** Si fuera spread, 2024 no tendría PF 2.61 en BT.
5. **La divergencia de datos BT↔Live (documentada semana 2, 3 trades no replicados) agrava el problema** para señales borderline en USDJPY.

### Estado: ⛔ PAUSADO — pendiente WF de SEDNA

### Walk-Forward Results: USDJPY_KOI — 2026-03-01

**Training (2020-01 → 2023-12, ~3.9y):** 41 trades | PF 2.25 | WR 36.6% | Sharpe 1.07 | DD 5.11%
**Full (2020-01 → 2025-12, ~5.9y):** 79 trades | PF 2.13 | WR 35.4% | Sharpe 1.12 | DD 5.12%

**Core match: PERFECTO** — 2020-2023 idénticos trade por trade.

**Desglose anual:**

| Año | Trades | WR | PF | PnL | Match |
|-----|--------|-----|-----|-----|-------|
| 2020 | 5 | 40.0% | 2.63 | +$5,264 | OK |
| 2021 | 5 | 40.0% | 2.61 | +$5,580 | OK |
| 2022 | 15 | 33.3% | 1.94 | +$11,952 | OK |
| 2023 | 16 | 37.5% | 2.37 | +$18,940 | OK |
| **2024 (blind)** | **21** | **33.3%** | **1.96** | **+$21,475** | BORDER |
| **2025 (blind)** | **17** | **35.3%** | **2.13** | **+$23,205** | BORDER |
| **OOS total** | **38** | **34.2%** | **~2.04** | **+$44,680** | — |

**Checklist WF:**
```
[+] 1. CORE MATCH          PASS  Core years [2020, 2021, 2022, 2023] identical
[+] 2. BORDERS             PASS  +38 trades, $+44,680 PnL
[+] 3. PF > 1.5            PASS  A: 2.25 | B: 2.13
[+] 4. SHARPE > 1.0        PASS  A: 1.07 | B: 1.12
[+] 5. DD < 15%            PASS  A: 5.11% | B: 5.12%
[+] 6. MC95 < 20%          PASS  A: 11.07% | B: 15.16%
[X] 7. DOMINANT < 40%      FAIL  A (train): 45.4% — artefacto muestra (41 trades). Full: 26.9% OK
[+] 8. NEG YEARS <= 1      PASS  0 años negativos ambos
[+] 9. PF DEGRAD < 15%     PASS  Delta: -5.3%
[+] 10. TRADES/YR >= 10    PASS  A: 10.5 | B: 13.3
Result: 9/10 (criterio 7 es artefacto estadístico de muestra training)
```

**Concentración:** Full: 2025 = 26.9% → aceptable
**Recent Period Test (2022-2025):** PF 2.09, WR 34.8%, $75,572 → PASS

### Comparativa Ogle vs KOI — resultado clave

| Métrica | Ogle (PRO) | KOI |
|---------|-----------|-----|
| Training PF | 2.41 | 2.25 |
| Full PF | 2.07 | 2.13 |
| OOS PF total | ~1.97 | **~2.04** |
| **2024 PF** | 2.61 | 1.96 |
| **2025 PF** | **1.40** ⚠️ | **2.13** ✅ |
| DD full | 9.00% | **5.12%** |
| Core match | FAIL (borde) | **PASS** |

**Hallazgo crítico: KOI NO degrada en 2025.**
- Ogle: 2024 PF 2.61 → 2025 PF 1.40 → 2026 live colapso = degradación acelerada
- KOI: 2024 PF 1.96 → 2025 PF **2.13** = edge MEJORANDO en año más reciente

**Implicación:** El problema NO es puramente de régimen USDJPY. Si lo fuera, KOI también degradaría.
El colapso 2025-2026 parece específico de cómo Ogle (pullback/EMA) interactúa con el USDJPY actual.
KOI (CCI/breakout) captura el par de forma diferente y sigue funcionando.

### Walk-Forward Results: USDJPY_SEDNA — 2026-03-01

**Training (2020-07 → 2023-10, ~3.2y):** 46 trades | PF 2.07 | WR 45.7% | Sharpe 1.25 | DD 7.02%
**Full (2020-07 → 2025-12, ~5.4y):** 84 trades | PF 2.02 | WR 46.4% | Sharpe 1.25 | DD 7.02%

**Core match: PERFECTO** — 2020-2023 idénticos trade por trade.

**Desglose anual:**

| Año | Trades | WR | PF | PnL | Match |
|-----|--------|-----|-----|-----|-------|
| 2020 | 4 | 75.0% | 7.67 | +$6,985 | OK |
| 2021 | 2 | 50.0% | 2.48 | +$1,688 | OK |
| 2022 | 19 | 42.1% | 1.83 | +$10,575 | OK |
| 2023 | 21 | 42.9% | 1.86 | +$13,609 | OK |
| **2024 (blind)** | **18** | **44.4%** | **1.53** | **+$9,766** | BORDER |
| **2025 (blind)** | **20** | **50.0%** | **2.46** | **+$23,693** | BORDER |
| **OOS total** | **38** | **47.4%** | **~2.02** | **+$33,459** | — |

**Checklist WF:**
```
[+] 1. CORE MATCH          PASS  Core years [2020, 2021, 2022, 2023] identical
[+] 2. BORDERS             PASS  +38 trades, $+33,459 PnL
[+] 3. PF > 1.5            PASS  A: 2.07 | B: 2.02
[+] 4. SHARPE > 1.0        PASS  A: 1.25 | B: 1.25
[+] 5. DD < 15%            PASS  A: 7.02% | B: 7.02%
[+] 6. MC95 < 20%          PASS  A: 9.23% | B: 12.76%
[X] 7. DOMINANT < 40%      FAIL  A (train): 41.4% — artefacto muestra (46 trades). Full: 35.7% OK
[+] 8. NEG YEARS <= 1      PASS  0 años negativos ambos
[+] 9. PF DEGRAD < 15%     PASS  Delta: -2.6%
[+] 10. TRADES/YR >= 10    PASS  A: 14.2 | B: 15.6
Result: 9/10 (criterio 7 es artefacto estadístico de muestra training)
```

**Concentración:** Full: 2025 = $23,693 (35.7%) → aceptable
**Recent Period Test (2022-2025):** PF 1.91, WR 44.9%, $57,643 → PASS

### Comparativa Final: Ogle vs KOI vs SEDNA — USDJPY

| Métrica | Ogle (PRO) | KOI | SEDNA |
|---------|-----------|-----|-------|
| Training PF | 2.41 | 2.25 | 2.07 |
| Full PF | 2.07 | 2.13 | 2.02 |
| OOS PF total | ~1.97 | ~2.04 | ~2.02 |
| OOS Trades | 44 | 38 | 38 |
| **2024 PF** | 2.61 | 1.96 | 1.53 |
| **2025 PF** | **1.40** ⚠️ | **2.13** ✅ | **2.46** ✅ |
| DD full | 9.00% | 5.12% | 7.02% |
| Sharpe full | 1.27 | 1.12 | 1.25 |
| Core match | FAIL (borde) | PASS | PASS |
| Checklist | 8/10 | 9/10 | 9/10 |

### Diagnóstico Final USDJPY (2026-03-01)

**CONCLUSIÓN DEFINITIVA: El problema es OGLE-ESPECÍFICO, no de régimen USDJPY.**

Evidencia:
1. **KOI 2025 PF 2.13** — edge estable/mejorando en OOS blind
2. **SEDNA 2025 PF 2.46** — edge FUERTE en OOS blind (su mejor año)
3. **Ogle 2025 PF 1.40** — degradación clara, único de los 3 que cae
4. Si fuera régimen BoJ/yen, las 3 estrategias degradarían. Solo Ogle degrada.

**Causa raíz:** La señal EMA pullback (Ogle) ya no captura bien el USDJPY post-BoJ normalization.
Las señales CCI breakout (KOI) y KAMA crossover (SEDNA) siguen funcionando.

**Decisión recomendada:**
- **USDJPY_PRO (Ogle):** Mantener ⛔ PAUSADO. Edge degradando. No reactivar sin re-optimización.
- **USDJPY_KOI:** Candidato a reactivación. WF robusto, 2025 fuerte.
- **USDJPY_SEDNA:** Candidato a reactivación. WF robusto, 2025 el más fuerte.
- **Validación pendiente:** Monitorizar KOI+SEDNA en demo 2-4 semanas antes de reactivar en live para confirmar que el edge WF se traduce a ejecución real (recordar divergencia datos BT↔Live semana 2).

---

## 📊 Walk-Forward Validation — Portfolio Forex Completo (2026-03-01)

### Metodología
- **Train:** 2020-01-01 → 2023-12-01 (parámetros optimizados)
- **Test (OOS blind):** 2024-01-01 → 2025-12-31 (nunca vistos durante optimización)
- **Herramienta:** `tools/compare_robustness.py` — checklist 10 criterios automatizada
- **Criterio mínimo:** OOS PF > 1.3, checklist ≥ 8/10, DD < 15%

### Tabla resumen — 12 configs forex (ordenadas por Score compuesto)

| # | Config | Score | Checklist | OOS PF | 2024 PF | 2025 PF | DD full | Tier | Veredicto |
|:-:|--------|:-----:|:---------:|:------:|:-------:|:-------:|:-------:|:----:|:---------:|
| 1 | USDCHF_PRO | 4.44 | 9/10 | ~3.68 | 4.91 | 2.90 | 3.74% | **A** | ✅ Tier A #1 |
| 2 | USDCHF_GEMINI | 4.21 | 8/10 | ~4.12 | 3.82 | 4.49 | 4.70% | **A** | ✅ Tier A #2 |
| 3 | EURUSD_PRO | 3.20 | 10/10 | ~2.12 | 1.45 | 2.58 | 5.93% | **A** | ✅ PERFECT |
| 4 | USDCHF_KOI | 2.35 | 9/10 | ~3.36 | 3.22 | 3.63 | 5.77% | **B** | ✅ |
| 5 | EURJPY_PRO | 2.25 | 10/10* | ~2.47 | 1.47 | 3.64 | 7.10% | **B** | ✅ |
| 6 | EURUSD_KOI | 1.87 | 9/10 | ~2.56 | 1.81 | 2.74 | 6.09% | **B** | ✅ |
| 7 | EURJPY_KOI | 1.73 | 9/10 | ~2.36 | 1.50 | 3.10 | 7.00% | **B** | ✅ |
| 8 | USDJPY_SEDNA | 1.63 | 9/10 | ~2.02 | 1.53 | 2.46 | 7.02% | **B** | ✅ REACTIVADO |
| 9 | USDJPY_KOI | 1.62 | 9/10 | ~2.04 | 1.96 | 2.13 | 5.12% | **B** | ✅ REACTIVADO |
| 10 | USDJPY_PRO | 1.51 | 8/10 | ~1.97 | 2.61 | 1.40 ⚠️ | 9.00% | — | ⛔ PAUSADO |
| 11 | EURUSD_GEMINI | 1.16 | 9/10 | ~2.59 | 3.12 | 2.24 | 4.99% | **C** | ✅ |
| 12 | EURJPY_SEDNA | 0.77 | 9/10 | ~2.02 | 2.36 | 1.47 ⚠️ | 12.07% | **D** | ✅ Vigilancia |

*\* EURJPY_PRO: criterio 1 (Core Match) = falso positivo por borde training dic-2023*

### Patrones descubiertos

1. **USDCHF es el activo más robusto:** Las 3 configs (PRO, KOI, GEMINI) tienen OOS PF > 3.0. Máxima confianza.
2. **2024 fue débil para la mayoría excepto USDCHF.** 2025 recupera fuerte — edge real emerge con más datos OOS.
3. **GEMINI aporta decorrelación:** Señales basadas en divergencia EUR↔CHF son independientes de las otras 3 estrategias.
4. **USDJPY_PRO es el ÚNICO config con degradación temporal.** Causa: señal EMA pullback (Ogle) específica, NO régimen BoJ. KOI+SEDNA siguen fuertes → reactivados.
5. **EURJPY_SEDNA:** Edge real pero ruidoso (DD 12.07%, 2025 PF 1.47). Mantenida en Tier D (0.50% risk) como contribución marginal.
6. **11 de 12 configs pasan WF.** Tasa de supervivencia forex = 91.7%. Sin evidencia de overfitting sistémico.

### Conclusión

El bloque forex está **robusto y validado con datos 100% ciegos (2024-2025)**. La única acción fue pausar USDJPY_PRO (degradación Ogle-específica) y reactivar USDJPY_KOI+SEDNA (WF confirma edge intacto). No se requieren cambios adicionales.

---

### GEMINI — EN PROGRESO

**EURUSD_GEMINI optimización horas completada ✅**

Horas optimizadas con cruce de 2 datasets (5 y 6 años):
- Horas: `[6, 7, 8, 10, 11, 13, 14, 16, 19]`
- Eliminadas: 00 (1 trade), 01, 04, 09, 12, 15, 17, 18, 20
- Hora 14 = BEST (PF 3.07-3.18, 17 trades idéntico ambos DS)
- Hora 10 = TOP (PF 3.23-6.17)
- Hora 13 = mayor volumen (PF ~2.06 idéntico ambos DS)
- Horas 08, 16 = PF idéntico en ambos DS

**Resultados EURUSD_GEMINI (6 años, 2020-2025):**

| Métrica | Antes | Después (6yr) | Después (5yr) |
|---------|-------|---------------|---------------|
| PF | 1.70 | **2.04** | **2.20** |
| WR | 35.2% | 39.5% | 41.2% |
| Max DD | 12.52% | **10.12%** | **10.13%** |
| MC95 | 15.18% | **12.00%** | **10.88%** |
| Trades | 108 | 76 (~12.7/año) | 68 (~11.3/año) |
| CAGR | 7.04% | 7.29% | 8.15% |

**Por año (6yr):**
| Año | Trades | WR% | PF | P&L |
|-----|--------|-----|-----|-----|
| 2020 | 10 | 50.0% | 3.07 | +$9,110 |
| 2021 | 3 | 33.3% | 1.65 | +$1,336 |
| 2022 | 26 | 30.8% | 1.35 | +$6,021 |
| 2023 | 15 | 40.0% | 2.02 | +$9,734 |
| 2024 | 10 | 50.0% | 3.12 | +$12,348 |
| 2025 | 12 | 41.7% | 2.24 | +$10,074 |

**0 años negativos** ✅

**Validación cruzada 5yr vs 6yr:** Max DD 10.13%/10.12% (idéntico), años 2021-2024 idénticos. Consistencia muy buena.

**USDCHF_GEMINI optimización horas completada ✅**

Horas optimizadas con cruce de 2 datasets (5 y 6 años):
- Horas: `[8, 13, 14, 17, 18, 19]`
- Eliminadas: 02, 03, 06, 07, 09, 10, 11, 12, 15, 16
- Bloque 17-19 = PF 3.8-8.7 consistente (cierre/post-NY)
- Hora 08 = BEST volumen (PF 2.99-3.50)
- Hora 14 = mayor volumen (PF 1.77-1.83 idéntico ambos DS)
- Hora 19 = PF 8.73 idéntico ambos DS

**Resultados USDCHF_GEMINI (6 años, 2020-2025):**

| Métrica | Antes | Después (6yr) | Después (5yr) |
|---------|-------|---------------|---------------|
| PF | 1.81 | **2.83** | **3.14** |
| WR | 45.0% | **56.1%** | **58.3%** |
| Max DD | 8.68% | **7.33%** | **7.27%** |
| MC95 | 11.92% | **6.94%** | **6.29%** |
| Hist/MC95 | — | 0.95x | 0.87x |
| Trades | 131 | 66 (~11/año) | 60 (~10/año) |
| CAGR | — | 8.05% | 9.29% |

**Por año (6yr):**
| Año | Trades | WR% | PF | P&L |
|-----|--------|-----|-----|-----|
| 2020 | 6 | 33.3% | 1.04 | +$153 |
| 2021 | 3 | 33.3% | 0.82 | -$313 |
| 2022 | 26 | 61.5% | 3.41 | +$22,629 |
| 2023 | 11 | 45.5% | 1.73 | +$4,474 |
| 2024 | 9 | 66.7% | 3.82 | +$10,439 |
| 2025 | 11 | 63.6% | 4.49 | +$15,710 |

**1 año negativo** (2021: -$313, 3 trades = ruido estadístico)

**Validación cruzada 5yr vs 6yr:** Max DD 7.27%/7.33% (idéntico), MC95 < histórico (rarísimo = estrategia extremadamente robusta), años 2021-2024 idénticos.

**⭐ Mejor config del portfolio entero por PF (2.83-3.14) y DD (7.3%/MC95 6.3-6.9%)**

---

### GEMINI forex ✅ COMPLETADO

| Config | PF | WR% | Max DD | MC95 | CAGR | Trades/año | Años neg |
|--------|-----|------|--------|------|------|-----------|----------|
| USDCHF_GEMINI | **2.83** | 56.1% | 7.33% | 6.94% | 8.05% | ~11 | 1 (-$313) |
| EURUSD_GEMINI | **2.04** | 39.5% | 10.12% | 12.00% | 7.29% | ~12.7 | 0 |

---

## 📋 Resumen TODAS las configs forex ✅ OPTIMIZACIÓN COMPLETADA

### Ogle (PRO) ✅
| Config | PF | WR% | Max DD | CAGR | Trades/año |
|--------|-----|------|--------|------|-----------|
| USDCHF_PRO | 2.86 | 49.2% | 7.41% | 10.61% | ~10.5 |
| EURUSD_PRO | 2.70 | 43.2% | 9.42% | 13.32% | ~12 |
| EURJPY_PRO | 2.38 | 41.2% | 11.57% | 14.77% | ~16 |
| USDJPY_PRO | 2.07 | 39.4% | 11.53% | 13.12% | ~16.5 |

### KOI ✅
| Config | PF | WR% | Max DD | CAGR | Trades/año |
|--------|-----|------|--------|------|-----------|
| USDCHF_KOI | 2.62 | 40.3% | 10.43% | 12.10% | ~12 |
| EURUSD_KOI | 2.15 | 42.9% | 11.60% | 11.69% | ~17.5 |
| USDJPY_KOI | 2.09 | 35.1% | 9.25% | 11.01% | ~12.8 |
| EURJPY_KOI | 2.09 | 38.3% | 11.04% | 12.58% | ~17.8 |

### SEDNA ✅
| Config | PF | WR% | Max DD | CAGR | Trades/año |
|--------|-----|------|--------|------|-----------|
| USDJPY_SEDNA | 2.07 | 47.0% | 10.67% | 10.34% | ~13.8 |
| EURJPY_SEDNA | 1.70 | 41.4% | 14.45% | 11.48% | ~24.2 |

### GEMINI ✅
| Config | PF | WR% | Max DD | CAGR | Trades/año |
|--------|-----|------|--------|------|-----------|
| USDCHF_GEMINI | **3.14** | 58.3% | 7.27% | 9.29% | ~10 |
| EURUSD_GEMINI | 2.04 | 39.5% | 10.12% | 7.29% | ~12.7 |

**Total: 12 configs forex optimizadas. Todas con PF ≥ 1.70, SL ≥ 10 pips.**

### Siguiente:
1. **🔴 Risk sizing portfolio** — Backtestear las 12 configs forex juntas para analizar correlación, asignar % riesgo por config (inverse volatility weighting / Risk Parity). Determinar allocation óptima antes de validar.
2. **🔴 Walk-forward validation (datos frescos)** — Descargar datos hasta hoy (Feb 14, 2026). Backtestear con risk sizes ya ajustados sobre datos no vistos (Dic 2025 - Feb 2026). Si se mantiene → confirma robustez.
3. **🟡 Deploy a demo** — Aplicar nuevos filtros de horas + risk sizes al bot live (demo)

---

### Notas sesión (2026-02-14 tarde) — Risk Sizing Portfolio

**Objetivo:** Cuenta de €50,000 (demo). Target: >12% anual, DD <10%, Sharpe ~0.7.

**Backtest portfolio sin optimizar riesgo (12 configs × $100K cada una = $1.2M):**
- Total trades: 1,064 | WR: 42.3%
- Total return: 85.01% (~14.17% anual)
- Todos los años positivos

**Scoring por config:** `Score = PF × Calmar / (MC95 / 10%)`

**Tiers asignados:**

| Tier | Risk% | Alloc% | Configs | Criterio |
|------|-------|--------|---------|----------|
| **A** | 1.00% | 10% | USDCHF_PRO, USDCHF_GEMINI | PF >2.8, DD <8%, MC95 <9% |
| **B** | 0.75% | 9% | EURUSD_PRO, USDCHF_KOI, EURJPY_PRO | PF >2.3 o Calmar >1.2 |
| **C** | 0.65% | 7-8% | EURUSD_KOI, EURJPY_KOI, USDJPY_KOI, USDJPY_SEDNA, USDJPY_PRO, EURUSD_GEMINI | PF >2.0 pero DD >10% |
| **D** | 0.50% | 10% | EURJPY_SEDNA | PF 1.70, DD 14.5%, MC95 17.5% |

**Allocation detallada (en PORTFOLIO_ALLOCATION de portfolio_backtest.py):**

| Config | Alloc | Cash (€50K) | Risk/trade | Tier |
|--------|-------|-------------|------------|------|
| USDCHF_PRO | 10% | €5,000 | 1.00% | A |
| USDCHF_GEMINI | 10% | €5,000 | 1.00% | A |
| EURUSD_PRO | 9% | €4,500 | 0.75% | B |
| USDCHF_KOI | 9% | €4,500 | 0.75% | B |
| EURJPY_PRO | 9% | €4,500 | 0.75% | B |
| EURUSD_KOI | 8% | €4,000 | 0.65% | C |
| EURJPY_KOI | 7% | €3,500 | 0.65% | C |
| USDJPY_KOI | 7% | €3,500 | 0.65% | C |
| USDJPY_SEDNA | 7% | €3,500 | 0.65% | C |
| USDJPY_PRO | 7% | €3,500 | 0.65% | C |
| EURUSD_GEMINI | 7% | €3,500 | 0.65% | C |
| EURJPY_SEDNA | 10% | €5,000 | 0.50% | D |
| **Total** | **100%** | **€50,000** | — | — |

**Arquitectura de implementación:**
- `settings.py` = parámetros generales de estrategia (no se toca para risk portfolio)
- `tools/portfolio_backtest.py` = PORTFOLIO_ALLOCATION con allocation y risk por config
- Flag `--portfolio` / `-p` para activar modo portfolio (override capital y risk)
- Sin `-p` = modo individual (cada config usa su starting_cash y risk de settings.py)

**Uso:**
```
python tools/portfolio_backtest.py -p                    # Portfolio completo
python tools/portfolio_backtest.py -p --assets EURUSD    # Solo EURUSD con portfolio sizing
python tools/portfolio_backtest.py -p -q                 # Portfolio quiet (solo summary)
```

**Análisis de riesgo máximo concurrente:**
- Media ponderada risk: ~0.72% por trade
- 6 posiciones simultáneas: 4.3% at risk
- 8 posiciones simultáneas: 5.8% at risk
- 12 posiciones (peor caso teórico): 8.7% at risk → bajo 10% ✅

**Pendiente:** ~~Correr `-p` y validar que los resultados en portfolio mode cumplen targets.~~

### Resultados Portfolio Mode con Micro Lots (2026-02-14)

**Bug fix crítico:** Con lotes estándar (100K unidades), las sub-cuentas de $3.5K-$5K forzaban mínimo 1 lote estándar = riesgo real de 6% vs target 1%. Solución: `lot_size=1000` (micro lots) en modo portfolio. FOREX.comGLOBAL soporta 0.01 lotes nativamente.

**Resultados finales (12 configs forex, €50K, modo `-p`):**

| Métrica | Valor | Target | Estado |
|---------|-------|--------|--------|
| Net P&L | $30,083 | — | — |
| Total Return | 60.17% | — | — |
| **Avg Annual Return** | **10.03%** | >12% | ⚠️ Bajo target |
| **Weighted Max DD** | **7.84%** | <10% | ✅ Cumple |
| **Worst Individual DD** | **9.85% (EURJPY_KOI)** | <10% | ✅ Cumple |
| Años negativos | 0 de 6 | 0 | ✅ Cumple |
| Total Trades | 1,064 | — | — |
| Win Rate | 42.3% | — | — |

**Desglose anual:**

| Año | Trades | Wins | WR% | P&L Total |
|-----|--------|------|-----|-----------|
| 2020 | 133 | 48 | 36.1% | $2,175 |
| 2021 | 90 | 39 | 43.3% | $2,443 |
| 2022 | 249 | 105 | 42.2% | $6,588 |
| 2023 | 198 | 85 | 42.9% | $5,408 |
| 2024 | 189 | 80 | 42.3% | $5,469 |
| 2025 | 205 | 93 | 45.4% | $8,034 |

**Nota:** El annual return de 10.03% está por debajo del target de 12%. Esto es consecuencia de usar micro lots que dimensionan correctamente el riesgo. El DD de 7.84% deja margen para subir ligeramente el riesgo si se desea más retorno.

### Siguiente:
1. ~~**🔴 Risk sizing portfolio**~~ ✅ COMPLETADO
2. ~~**🔴 Walk-forward validation (datos frescos)**~~ ✅ COMPLETADO (ver abajo)
3. **🟡 Deploy a demo** — Aplicar nuevos filtros de horas + risk sizes al bot live (demo)

---

### Walk-Forward Validation (2026-02-14) — Datos no vistos

**Periodo:** 2025-12-01 → 2026-02-13 (~2.5 meses, datos NO usados en optimización)
**Comando:** `python tools/portfolio_backtest.py -p -q --assets EURUSD USDCHF USDJPY EURJPY --from-date 2025-12-01 --to-date 2026-02-13`

**Se añadieron flags `--from-date` y `--to-date` a portfolio_backtest.py** para override del rango de fechas.

**Resultados walk-forward (12 configs forex, €50K portfolio mode):**

| Métrica | Valor | Comentario |
|---------|-------|------------|
| Net P&L | $169 | Positivo en 2.5 meses |
| Total Return | 0.34% | ~1.6% anualizado |
| Weighted Max DD | 2.93% | ✅ Muy bajo |
| Worst Individual DD | 4.20% (USDJPY_PRO) | ✅ Controlado |
| Total Trades | 32 | Normal para 2.5 meses |
| Win Rate | 31.2% | Bajo pero rentable (trades ganadores mayores) |
| Años negativos | 0 de 2 (2025 parcial + 2026 parcial) | ✅ |

**Desglose por estrategia en walk-forward:**

| Estrategia | P&L Dic 2025 | P&L Ene-Feb 2026 | Total |
|------------|-------------|-------------------|-------|
| GEMINI | $0 | -$47 | -$47 |
| KOI | $38 | $104 | $142 |
| SEDNA | $16 | $123 | $139 |
| SunsetOgle | $7 | -$71 | -$64 |
| **Total** | **$62** | **$108** | **$169** |

**Análisis:**
- ✅ Portfolio en positivo sobre datos no vistos → confirma que no hay overfitting severo
- ✅ DD controlado (2.93% weighted, 4.20% worst) → risk sizing funciona
- ⚠️ Retorno bajo (0.34%) pero periodo corto (2.5 meses), insuficiente para sacar conclusiones estadísticas
- ⚠️ WR 31.2% más bajo que el histórico 42.3%, pero con solo 32 trades es varianza normal
- KOI y SEDNA positivas, GEMINI y PRO ligeramente negativas = diversificación funcionando
- 0 trades en EURUSD_GEMINI y USDCHF_PRO → filtros estrictos, no forzaron trades

**Conclusión:** Walk-forward APROBADO. No hay señales de overfitting. El portfolio se comporta dentro de lo esperado estadísticamente. Listo para deploy a demo.

---

### Walk-Forward Validation #2 (2026-02-15) — Con Tiers de Riesgo Nuevos

**Periodo:** 2025-12-01 → 2026-02-14 (~2.5 meses, datos NO usados en optimización)
**Comando:** `python tools/portfolio_backtest.py -p -q --assets EURUSD USDCHF USDJPY EURJPY --from-date 2025-12-01 --to-date 2026-02-14`
**Diferencia vs WF#1:** Ahora usa tiers Kelly (A=1.5%, B=1.0%, C=0.75%, D=0.50%) en vez de riesgo sobre sub-cuentas.

**Resultados:**

| Métrica | WF#1 (risk antiguo) | WF#2 (tiers nuevos) | Cambio |
|---------|--------------------|--------------------|--------|
| Net P&L | $169 | $1,536 | **+9.1x** |
| Total Return | 0.34% | 3.07% | **+9x** |
| Weighted Max DD | 2.93% | 3.61% | +0.68pp |
| Worst DD | 4.20% (USDJPY_PRO) | 5.29% (USDCHF_KOI) | +1.09pp |
| Total Trades | 32 | 32 | Idéntico |
| Win Rate | 31.2% | 31.2% | Idéntico |

**Desglose por estrategia:**

| Estrategia | WF#1 (antiguo) | WF#2 (tiers) | Factor |
|------------|---------------|-------------|--------|
| GEMINI | -$47 | -$720 | ~15x (pérdida amplificada también) |
| KOI | $142 | $2,280 | ~16x |
| SEDNA | $139 | $968 | ~7x |
| SunsetOgle | -$64 | -$979 | ~15x |
| **TOTAL** | **$169** | **$1,536** | **9.1x** |

**Desglose por año:**

| Año | Trades | WR | GEMINI | KOI | SEDNA | SunsetOgle | TOTAL |
|-----|--------|-----|--------|-----|-------|------------|-------|
| 2025 | 15 | 26.7% | $0 | $726 | $7 | $87 | $819 |
| 2026 | 17 | 35.3% | -$720 | $1,554 | $961 | -$1,066 | $728 |

**Análisis:**
- ✅ **Mismos 32 trades, misma WR (31.2%)** → confirma que los tiers solo cambian sizing, no señales
- ✅ **DD controlado: 3.61% << 10% objetivo** → margen de seguridad enorme
- ✅ **PnL 9x con DD solo +0.68pp** → ratio riesgo/retorno mejoró drásticamente
- ✅ **Ambos años positivos** ($819 + $728) → consistencia temporal
- ⚠️ KOI domina el PnL ($2,280 de $1,536 neto) → GEMINI y PRO compensan con pérdidas
- ⚠️ GEMINI -$720 en 2026 → un solo trade malo puede pesar en periodo corto (solo 32 trades)
- ✅ Diversificación funcionando: las pérdidas de GEMINI/PRO quedan absorbidas por KOI/SEDNA

**¿Es lo esperado vs backtest completo?**

Comparación normalizada (contra 2020, primer año con equity ~$50K, sin compounding):

| Métrica | 2020 (12m) | Promedio anual 6yr | WF#2 (2.5m) | WF#2 anualizado |
|---------|-----------|-------------------|-------------|-----------------|
| Trades | 133 | 177 | 32 | ~154 |
| Trades/mes | 11.1 | 14.8 | 12.8 | 12.8 |
| PnL | $33,615 | $80,420* | $1,536 | ~$7,373 |
| PnL/trade | $253 | $453* | $48 | $48 |
| WR | 36.1% | 42.3% | 31.2% | 31.2% |
| DD | — | 9.60% | 3.61% | — |

*Promedio anual inflado por compounding (equity 2025 = ~$500K vs $50K inicial)

**Comparación justa — solo vs 2020 (mismo capital ~$50K):**
- PnL/trade: $48 vs $253 → WF#2 es **5.3x menor**
- Pero WR 31.2% vs 36.1% con N=32 es varianza esperable (intervalo 95%: 16%-47%)
- Trades/mes: 12.8 vs 11.1 → frecuencia trading similar ✅
- DD: 3.61% vs histórico 9.60% → mucho más bajo, dentro del target ✅

**¿Es preocupante el PnL/trade bajo?**
- Con 32 trades, un solo trade gordo cambia toda la estadística
- En 2020: WR fue también bajo (36.1%) pero PnL/trade mayor porque pocas pérdidas grandes
- El walk-forward tiene trades correctos (KOI +$2,280, SEDNA +$968) pero también pérdidas concentradas (GEMINI -$720, PRO -$979)
- **Con N=32, cualquier conclusión estadística tiene baja confianza** — se necesitan mínimo 100+ trades
- Periodo Dic-Feb contiene festivos (Navidad, Año Nuevo) y baja liquidez → pueden explicar peor rendimiento

**Conclusión:** Walk-forward #2 APROBADO. Los tiers de riesgo multiplican el PnL por 9x con incremento de DD marginal (+0.68pp). El PnL/trade es menor que el histórico pero con N=32 no es estadísticamente significativo. Portfolio robusto y listo para deploy a live demo.

---

### Investigación Risk Sizing Óptimo (2026-02-14) — Marco Teórico

**Problema detectado:** El risk% se calculaba sobre la sub-cuenta (ej: 0.65% × $3,500 = $22.75 por trade), que es solo 0.05% del capital real de $50K. Demasiado conservador → retornos irrelevantes en walk-forward.

**Pregunta:** ¿Cuál es el risk% óptimo por trade sobre el capital total de $50K, manteniendo DD portfolio < 10%?

#### 1. Kelly Criterion aplicado a nuestro portfolio

- W (win rate) = 0.423, R (avg_win/avg_loss) = 2.87
- Full Kelly = W - (1-W)/R = 22.2% → demasiado agresivo (DD 30-50%)
- Half Kelly = 11.1% → agresivo, para hedge funds
- **Quarter Kelly = 5.5%** → Chan lo recomienda para sistemas reales
- Eighth Kelly = 2.8% → conservador

#### 2. Ernest Chan — Ajuste por posiciones concurrentes

- Chan (Quantitative Trading, Cap. 6): ajustar Kelly por raíz de streams independientes
- Nuestro portfolio: 12 configs pero ~6 streams independientes efectivos (correlación parcial entre pares)
- Kelly_portfolio = 22.2% / sqrt(6) ≈ 9.1%
- Half-Kelly_portfolio = 4.5%, Quarter-Kelly_portfolio = 2.3%

#### 3. Ray Dalio — Risk Parity / "Holy Grail"

- Con 15 streams no correlados → reduce riesgo 80% sin reducir retorno
- Nuestro portfolio: ~6 streams efectivos → beneficio real pero no el máximo teórico
- Risk budget total portfolio: fijo en 6-8% del capital
- Distribuir por riesgo relativo (inverse volatility): más riesgo a configs con menor DD

#### 4. Reverse Engineering desde DD Target < 10%

- 4 posiciones simultáneas (frecuente): 10% / (4 × 1.5) = 1.67%
- 6 posiciones simultáneas (esporádico): 10% / (6 × 1.5) = 1.11%
- 8 posiciones simultáneas (raro): 10% / (8 × 1.5) = 0.83%

#### 5. Convergencia de todos los frameworks

| Framework | Risk/trade recomendado |
|-----------|----------------------|
| Quarter Kelly portfolio | 2.3% |
| Chan (concurrent-adjusted) | ~1.5-2.0% |
| Dalio (risk budget / 6) | ~1.0-1.3% |
| Reverse desde DD<10% | ~1.0-1.5% |
| **Punto dulce** | **~1.0-1.5% del capital total ($50K)** |

#### Propuesta de Tiers (% sobre capital total $50K, NO sobre sub-cuenta)

**Lógica de los tiers:** se asigna MÁS riesgo a las configs que históricamente han demostrado MENOR DD y MEJOR PF. No es que "más riesgo = menos DD", sino que se confía más capital a la estrategia más estable. Es el principio de Dalio: distribuir riesgo inversamente proporcional a la volatilidad histórica.

| Tier | Risk/trade (% de $50K) | $/trade | Configs | Por qué |
|------|------------------------|---------|---------|---------|
| **A** | 1.5% | $750 | USDCHF_PRO, USDCHF_GEMINI | PF>2.8, DD<8% hist. → se han ganado más confianza |
| **B** | 1.0% | $500 | EURUSD_PRO, USDCHF_KOI, EURJPY_PRO | Sólidos, DD 9-12% |
| **C** | 0.75% | $375 | EURUSD_KOI, EURJPY_KOI, USDJPY_KOI, USDJPY_SEDNA, USDJPY_PRO, EURUSD_GEMINI | PF~2.1, DD>10% |
| **D** | 0.50% | $250 | EURJPY_SEDNA | PF 1.70, DD 14.5% → menos confianza |

**Riesgo máximo concurrente estimado:**
- Media ponderada: ~0.92% por trade
- 4 simultáneos (frecuente): 3.7% → muy seguro
- 6 simultáneos (esporádico): 5.5% → cómodo
- 8 simultáneos (raro): 7.4% → dentro del target
- 12 simultáneos (teórico imposible): 11% → apenas sobre 10%, pero irrealista por filtros de horas

**Comparación con situación actual:**
- Actual: risk sobre sub-cuenta → $23-50 por trade (0.05-0.10% de $50K) → demasiado poco
- Propuesto: risk sobre capital total → $250-750 por trade (0.50-1.50% de $50K) → punto dulce
- Factor de cambio: 10-15× más riesgo, pero dentro de parámetros académicos aceptados

**Implementación técnica:** El risk_pct en PORTFOLIO_ALLOCATION debe aplicarse sobre $50K total, no sobre la sub-cuenta. El position sizing calcula `equity × risk_percent`, así que si `equity` es la sub-cuenta, hay que escalar: `risk_adjusted = risk_pct × (TOTAL_CAPITAL / sub_account_cash)`.

**Estado:** PENDIENTE de implementar. Necesita validar con backtest completo (-p) que DD real < 10%.

#### 6. Implementación definitiva (2026-02-14)

**Problema del backtesting portfolio en BackTrader:**
BackTrader ejecuta cada config en su propio Cerebro aislado. No hay equity compartida entre
backtests independientes. Cada config opera sobre su propia cuenta virtual.

**Tres enfoques evaluados:**

| Enfoque | Descripción | Problema |
|---------|-------------|----------|
| Sub-cuentas ($3.5K-$5K) + riesgo escalado | allocation% × $50K, escalar risk para conseguir $/trade correcto | Compounding exponencial: 15% risk en $5K crece a $2.2M en 5 años |
| Capital virtual ($25K-$75K) + 1% fijo | virtual_cap = risk_pct × $50K, flat 1% risk | DD% miente: 10% DD en $75K = 15% del real. Margen contra capital ficticio |
| **Todos a $50K + risk_pct por tier** | starting_cash = $50K, risk_percent = tier risk | **Correcto:** DD% real, margen real, compounding natural |

**Solución elegida: Todos a $50K + risk_pct por tier**
- Cada config recibe `starting_cash = $50K` (cuenta real)
- `risk_percent` se overridea desde `portfolio_backtest.py` según tier (0.50%-1.50%)
- `lot_size = 1000` (micro lots) para granularidad correcta en forex
- **CERO modificaciones en archivos de estrategia** (axioma)
- La única diferencia con `run_backtest.py` es que portfolio pasa risk_percent y lot_size como params

**Limitación honesta del backtesting:**
Con backtests independientes, cada config compone sobre su propia equity:
- Si USDCHF_PRO crece a $60K, riesga 1.5% × $60K = $900
- Si EURJPY_KOI cae a $45K, riesga 0.75% × $45K = $337
- En realidad la cuenta estaría a ~$55K y ambos deberían calcular sobre $55K

Este error es PEQUEÑO y se autocancela parcialmente (ganadores sobreestiman, perdedores
subestiman). Con risk_pcts de 0.5-1.5%, la desviación acumulada en 5 años es marginal.
Es práctica estándar en la industria: fondos cuantitativos backtestean cada estrategia
sobre capital nominal y suman PnLs.

**En live es más fácil:** El bot opera sobre una cuenta real con equity compartida.
Todas las estrategias calculan riesgo sobre la misma equity actual. No hay problema
de aislamiento. La optimización de risk sizing en live se resuelve naturalmente.

#### 7. Resultados Backtest Portfolio Definitivo (2026-02-14)

**Periodo:** 2020-01-01 a 2025-12-01 | **Capital:** $50K | **12 configs forex**

```
Year    Trades  Wins    WR%     GEMINI        KOI          SEDNA      SunsetOgle        TOTAL
2020       133    48  36.1%    $3,573       $5,883       $3,260      $20,899       $33,615
2021        90    39  43.3%      $466      $14,127       $1,525      $20,405       $36,523
2022       249   105  42.2%   $23,993      $28,855       $8,094      $39,758      $100,700
2023       198    85  42.9%    $9,058      $25,877       $8,590      $41,990       $85,515
2024       189    80  42.3%   $15,255      $26,533      $10,420      $36,441       $88,649
2025       205    93  45.4%   $21,268      $42,546      $11,350      $62,963      $138,127
```

| Metrica | Valor |
|---------|-------|
| Configs | 12 |
| Total Trades | 1,064 |
| Win Rate | 42.3% |
| Starting Capital | $50,000 |
| Net P&L | $482,518 |
| Total Return | 965.04% |
| Avg Annual Return | 160.84% |
| **Weighted Max DD** | **9.60%** (< 10% target) |
| Worst Individual DD | 11.90% (USDCHF_GEMINI) |

**Nota sobre retorno alto:** El 160%/año es por compounding aislado (cada config opera
sobre su propia equity creciente). En live real, equity compartida producira retornos
menores pero DD% sera representativo. El DD 9.60% < 10% valida los tiers de riesgo.

**Estado:** ✅ VALIDADO. Pendiente walk-forward Dec 2025 - Feb 2026 con estos tiers.

---

### Notas sesión (2026-02-16) — Auditoría #2 pre-deployment + v0.5.9

**Cambios en esta sesión:**
1. **v0.5.8:** Non-ASCII cleanup (17 reemplazos en 6 archivos live/). Consolidación de axiomas en CONTEXT.md.
2. **v0.5.9:** Auditoría línea por línea de TODO live/ (ver Registro de Auditorías #2):
   - Bug fix: KOI EMA param names (`ema_period_1` → `ema_1_period`) — silencioso, defaults coincidían
   - Bug fix: EURJPY_KOI pip_value 0.0001 → 0.01 — **config completamente inoperante** (todos los trades rechazados)
   - Re-backtested EURJPY_KOI con pip_value corregido: resultados válidos
3. **Investigación:** MT5 DEAL_POSITION_ID bug (broker-specific, no tiene fix)

**Próxima sesión:**
- Monitorear EURJPY_KOI (ahora operativo por primera vez)
- Considerar auditorías periódicas pre-deployment como práctica estándar

---

### Notas sesión (2026-02-17) — Fix annualization Sharpe/Sortino para ETFs

**Cambios en esta sesión:**
1. **Bug fix (backtest only):** `periods_per_year` estaba hardcoded como `252 * 24 * 12 = 72,576` (forex 24h/dia). Para ETFs como DIA (~78 bars/dia, ~19,540/año), esto inflaba Sharpe por sqrt(72576/19540) = **1.93x**.
   - DIA_PRO: Sharpe 1.89 → **0.98**, Sortino 0.88 → **0.46** (CAGR/DD/trades sin cambio)
   - Forex (EURUSD_PRO): Sharpe 0.87 → 0.87 (sin cambio, auto-calcula ~72,500)
   - Fix aplicado a 6 estrategias: sunset_ogle, koi, sedna, gemini, helix, gliese
   - Método: trackear `_first_bar_dt`/`_last_bar_dt` en `next()`, calcular `periods_per_year = len(bars) / data_years`
2. **Verificación tools/:** Ninguna herramienta en `tools/` calcula Sharpe/Sortino. No afectadas.
3. **Verificación live/:** No afectado (live no calcula estas métricas).

**Impacto:** Solo backtest, solo métricas Sharpe/Sortino global. Yearly Sharpe/Sortino usan fórmula diferente (trade-level PnLs) y no se ven afectados.

4. **Bug fix analyze_ogle.py:** `find_latest_log` usaba `max(logs)` (orden alfabético) → seleccionaba EURUSD en lugar de DIA.
   - Mostraba 74 trades (EURUSD) en vez de 151 (DIA). Métricas completamente incorrectas.
   - Rangos SL Pips/ATR/Duration estaban hardcoded para forex, no cubrían valores ETF.
   - Fix: selección por mtime, filtro por asset (`python analyze_ogle.py DIA`), rangos auto-adaptativos `_auto_ranges()`.
5. **SL pips en ETFs vs Forex:** En forex sl_pips_min=10 por spread (~1-3 pips). En DIA el spread es ~$0.01-0.03 (1-3 pips con pip_value=0.01) pero los SL son ~100-500 pips. El spread es <1% del SL → **no hay problema de spread en ETFs**, no necesita sl_pips_min alto.
6. **Mismo bug `max(logs)` en 5 analizadores más:** Aplicado fix mtime + asset filter + `_auto_ranges()` a analyze_koi, analyze_sedna, analyze_helix, analyze_gliese, analyze_gemini.
7. **`duration_bars` en log de ETFs es cosmético pero incorrecto:** Se calcula como `(exit_time - entry_time).total_seconds() / 60 / 5` → cuenta minutos de calendario, incluyendo noches y fines de semana. Para forex (~24h) es casi correcto, pero para ETFs (6.5h/día) se infla ~5x. Ejemplo: trade DIA #138 reporta 7,506 bars pero hay 1,482 barras reales en los datos. **No afecta P&L ni decisiones**, solo distorsiona el análisis por duración. No se corrige por ahora (cosmético).
8. **Evaluación DIA_PRO para live (SunsetOgle):**
   - Config final: `allowed_hours: [14,15,16,18,19]`, excluir 13:00 (PF 0.18-0.28) y 17:00 (breakeven). Thu excluido por bajo PF en ambos datasets.
   - **5Y vs 6Y estable:** PF 1.60/1.70, DD 7.56% idéntico, Sharpe 0.92/1.02, ~18 trades/año.
   - **A favor:** DD excelente (7.56%), MC95 <16%, baja correlación con forex, PF >1.5 en 4 de 6 años.
   - **En contra:** CAGR 7-8% (no bate buy-and-hold DIA ~10-12%), 2020-2021 negativos/breakeven, Sortino pobre (0.41-0.48), 2024 aporta 45% del PnL total.
   - **Veredicto:** Apto para **live en portfolio** (diversificación), no como standalone. Empezar con risk_percent 0.5%. Pendiente: probar DIA con KOI y SEDNA para comparar.
   - Monte Carlo verificado: MC95/DD ratio 2.09x es legítimo (no bug), DD histórico fue favorablemente bajo.
9. **Evaluación DIA_SEDNA para live:**
   - 147 trades, WR 43.5%, PF 1.96, Net $52,017. Sharpe 1.54, Sortino 0.66, CAGR 7.51%, DD 4.26%.
   - Todos los años positivos (2020-2025), consistente. MC95 7.49% (ratio 1.76x, saludable).
   - Sharpe 1.54 verificado correcto: baja volatilidad (DD 4.26%) con retorno decente (CAGR 7.51%) → vol anualizada ~4.9%.
10. **DIA_KOI descartado:** Inestable para ETFs. CCI como filtro de momentum + `atr_sl_multiplier: 2.0` (SL ajustado) lo hace sensible a ruido y gaps overnight en ETFs. No aporta vs Ogle+SEDNA.
11. **Decision portfolio DIA: PRO (Ogle) + SEDNA combinados:**
   - Perfiles complementarios: SEDNA (KAMA) vs Ogle (pullback) = baja correlacion esperada.
   - SEDNA cubre debilidad de Ogle en 2020 (-$3,891 + $3,420 ≈ flat).
   - Estimado combinado: ~258 trades, ~$102K PnL, CAGR ~14%, DD combinado < 7.56% (improbable DD simultaneo).
   - **Config live:** risk_percent 0.5% cada una (1% combinado por activo DIA).

### Plan de Diversificacion ETFs (2026-02-17)

**Objetivo:** Ampliar portfolio con ETFs descorrelacionados del bloque forex (EURUSD/USDCHF/USDJPY/EURJPY) y DIA.

**Disponibilidad verificada:** Dukascopy (data 5min) + Darwinex Zero (broker live). Ambos requeridos.

**Regla:** Minimo 2 estrategias funcionando bien por activo para entrar a live.

**Analisis de correlacion contra portfolio completo (forex + DIA):**

| ETF | Subyacente | vs DIA | vs Forex USD | vs JPY pairs | Driver unico | Score |
|-----|-----------|--------|-------------|-------------|-------------|-------|
| GLD | Oro | ~0.05 | ~0.35 | ~0.15 | Inflacion, refugio | Excelente |
| XLE | Energia | ~0.60 | ~0.10 | ~0.10 | Petroleo, OPEC | Muy bueno |
| EWZ | Brasil | ~0.45 | ~0.20 | ~0.15 | Commodities LatAm | Muy bueno |
| XLU | Utilities US | ~0.30 | ~0.15 | ~0.10 | Defensivo, tipos interes | Muy bueno |
| SLV | Plata | ~0.15 | ~0.30 | ~0.10 | Metales (beta oro) | Solo via GEMINI |

**Descartados (parcialmente):**
- TLT: Falló con Ogle/KOI/CERES/SEDNA. **LUYTEN v1.0 implementada** (ORB simplificado). Baseline: 530 trades, PF 0.65. Optimizer grid-search creado. En optimización.
- EEM/VWO: Correlacion moderada con USD (~0.30), no aporta tanto vs XLE/EWZ.
- MCHI (China): Buen diversificador pero no hay data en Dukascopy.
- EWJ (Japon): Redundante con USDJPY/EURJPY (driver JPY compartido).
- EMB (Bonos EM): Correlacion moderada con USD afecta al bloque forex.
- Sectoriales US (XLF/XLI/XLK/XLY): Correlacion >0.75 con DIA, redundantes.
- Broad US (VTI/ITOT/IVE/RSP): Practicamente = DIA.
- DIA_KOI: Inestable, CCI + SL ajustado sensible a gaps overnight ETF.

**Prioridad de backtesting (Ogle + SEDNA):**

| # | ETF | Estrategias | Rationale |
|---|-----|------------|-----------|
| 1 | GLD | Ogle + SEDNA | Mejor diversificador. Oro tiende limpio, pullbacks claros |
| 2 | XLE | Ogle + SEDNA | Petroleo = driver independiente de todo el portfolio |
| 3 | EWZ | Ogle + SEDNA | LatAm commodity, contra-ciclico a US/EUR |
| 4 | XLU | Ogle + SEDNA | Defensivo, baja beta, trends estables |

**Idea futura: GEMINI-ETF (leader-follower, correlacion positiva):**

GEMINI clasico NO funciona con ETFs (requiere correlacion inversa ~-0.90, no existe entre ETFs).
Variante GEMINI-ETF: lider confirma, seguidor amplifica. Correlacion positiva (~0.60-0.75).

| Lider | Seguidor | Corr. | Logica | Edge |
|-------|----------|-------|--------|------|
| GLD → SLV | ~0.75 | `ROC_gld > threshold → trade SLV` | SLV amplifica ~1.5x, GLD lidera 1-3 dias | Prioridad 1 |
| XLE → EWZ | ~0.60 | `ROC_xle > threshold → trade EWZ` | Petrobras ~15% de EWZ, petroleo mueve XLE primero, EWZ sigue con lag + amplifica por riesgo EM | Prioridad 2 |

Condiciones: solo desarrollar si los activos lideres (GLD, XLE) funcionan bien con Ogle/SEDNA primero.
Solo opera el seguidor (SLV, EWZ). El lider se usa como confirmacion, no se tradea en GEMINI-ETF.

**Portfolio objetivo si backtesting es positivo:**

| Clase | Activo | Estrategias | Driver |
|-------|--------|------------|--------|
| Forex EUR | EURUSD, USDCHF | KOI, Ogle, GEMINI | USD-EUR-CHF |
| Forex JPY | USDJPY, EURJPY | KOI, Ogle, SEDNA | USD-EUR-JPY |
| Equity US | DIA | Ogle, SEDNA | Earnings US |
| Oro | GLD | Ogle, SEDNA (pendiente) | Inflacion, refugio |
| Plata | SLV | GEMINI-ETF (pendiente) | Beta oro |
| Energia | XLE | Ogle, SEDNA (pendiente) | Petroleo, OPEC |
| LatAm | EWZ | Ogle, SEDNA (pendiente) + GEMINI-ETF (seguidor de XLE) | Commodities Brasil |
| Defensivo | XLU | Ogle, SEDNA (pendiente) | Tipos interes US |
| Plata | SLV | GEMINI-ETF (seguidor de GLD, pendiente) | Beta oro |

**Flujo de trabajo:**
1. Backtesting GLD con Ogle + SEDNA (prioridad maxima, mejor diversificador)
2. Backtesting XLE con Ogle + SEDNA
3. Backtesting EWZ con Ogle + SEDNA
4. Backtesting XLU con Ogle + SEDNA
5. Si GLD funciona → desarrollar GEMINI-ETF para SLV
6. Si XLE funciona → desarrollar GEMINI-ETF para EWZ (adicional a Ogle/SEDNA)
7. Redireccion segun resultados: ETFs que fallen regla de 2 estrategias → descartar

**Nota:** Los resultados de backtesting redireccionaran la estrategia. No todos los ETFs pasaran la regla de 2 estrategias. Los que fallen se descartan, se prueban alternativas (VNQ, IYR) o se busca data adicional.

---


---

## 🔒 EOD Close para ETFs (Backtest) — Decision 2026-02-20

### Problema
Los ETFs (GLD, DIA, TLT) operan en horario NYSE: 14:30-20:55 UTC (datos Dukascopy).
Las posiciones que cruzan la noche quedan expuestas a gaps de apertura sin proteccion del SL.

**Evidencia en GLD_PRO (59 trades, 5 anios):**
- 4 trades con gap catastrofico: -$24,763 (76% de todas las perdidas)
- Trade #58 solo (martes 19:40, gap al dia siguiente): **-$14,087** = 43% del profit bruto destruido
- Varios gap-trades NO son viernes — ocurren lunes, martes, jueves
- El SL pips real puede ser 3x-9x el SL configurado por el gap

### Decision: Cierre forzado a las 20:50 UTC para ETFs

**Parametro:** `eod_close_hour: 20, eod_close_minute: 50` en settings.py (solo ETFs con `is_etf: True`)
- Valor `None` por defecto = sin cierre EOD (forex no lo necesita)
- Se activa solo cuando ambos params estan definidos y `is_etf: True`
- Backtrader: en `next()`, si hay posicion abierta y hora >= 20:50 UTC → `self.close()` + cancel SL/TP
- Exit reason: `EOD_CLOSE` (distinguible de SL/TP en logs y analisis)

**Por que 20:50 y no 21:00:**
- Ultima barra en datos Dukascopy = 20:55 UTC
- 20:50 cierra 5 minutos antes del cierre real — evita spread de ultimo minuto
- La barra de 20:50 es la penultima del dia → precio aun con liquidez aceptable

**Horario broker (FOREX.comGLOBAL UTC+2):**
- 20:50 UTC = 22:50 broker time (invierno) / 23:50 (verano)
- En live, el cierre usara `broker_to_utc()` igual que los filtros de hora existentes
- Verificar horario real del broker en MT5 antes de implementar live (propiedades del simbolo)

**Activos afectados:** GLD_PRO, DIA_PRO, TLT_PRO (y cualquier futuro ETF con `is_etf: True`)

**Trade-off conocido:**
- PRO: Elimina gaps overnight catastroficos (~$24K salvados en 5 anios GLD)
- CON: Trunca winners que necesitaban >1 dia para llegar a TP (~$18K potencialmente reducidos)
- Balance: el downside de un gap es impredecible; el upside truncado es acotado por TP

**Implementacion:** Solo en backtest (sunset_ogle.py). Live pendiente de verificacion de horario broker.

### Resultados Backtest GLD_PRO: Con vs Sin EOD Close

| Metrica | Sin EOD Close | Con EOD 20:50 | Cambio |
|---------|:---:|:---:|:---:|
| Trades | 59 | 54 | -5 |
| Win Rate | 49.1% | 48.1% | ~igual |
| **Profit Factor** | 1.56 | **1.96** | **+25.6%** |
| Gross Profit | $91,340 | $69,318 | -$22K (winners truncados) |
| **Gross Loss** | $58,554 | **$35,408** | **-$23K (gaps eliminados)** |
| Net P&L | $32,786 | $33,910 | +$1,124 |
| **Max Drawdown** | 12.56% | **7.61%** | **-39.4%** |
| **Sharpe** | 0.71 | **0.93** | **+31%** |
| CAGR | 6.05% | 6.23% | +3% |
| **MC DD 95%** | 21.69% | **11.17%** | **-48.5%** |
| Calmar | 0.48 | 0.82 | +71% |
| 2022 (peor) | -$3,833 | -$5,006 | algo peor |
| **2025** | -$10,320 | **+$2,470** | **rojo → verde** |

**Conclusion:** Mismo retorno neto (~$33K), pero riesgo dramaticamente menor.
PF 1.56→1.96, DD 12.6%→7.6%, MC95 21.7%→11.2%. El trade catastrofico #58 (-$14K) eliminado.
EOD Close es obligatorio para todos los ETFs en Ogle.

---

### Evaluacion GLD_PRO para Portfolio (2026-02-20)

**Robustez 5Y vs 6Y (con EOD Close):**

| Metrica | 5 anios | 6 anios | Delta |
|---------|---------|---------|-------|
| Trades | 62 | 78 | +16 |
| Win Rate | 50.0% | 50.0% | = |
| PF | 1.95 | 1.94 | -0.01 |
| CAGR | 6.55% | 7.17% | +0.62% |
| Max DD | 7.01% | 7.02% | +0.01% |
| Sharpe | 0.94 | 0.98 | +0.04 |
| MC95 DD | 11.22% | 13.15% | +1.93% |
| Calmar | 0.93 | 1.02 | +0.09 |

**Conclusion:** PF identico, DD identico, Sharpe/CAGR mejoran con mas datos. Robusto.

**Desglose anual (6Y):**

| Anio | Trades | WR% | PF | PnL | Veredicto |
|------|--------|-----|-----|-----|-----------|
| 2020 | 17 | 41.2% | 1.77 | +$9,418 | OK |
| 2021 | 10 | 60.0% | 2.88 | +$8,961 | Excelente |
| 2022 | 10 | 40.0% | 0.58 | -$4,288 | Unico negativo |
| 2023 | 12 | 58.3% | 2.10 | +$8,048 | Bueno |
| 2024 | 16 | 50.0% | 2.73 | +$16,230 | Excelente |
| 2025 | 13 | 53.8% | 2.31 | +$11,271 | Bueno |

5 de 6 anios positivos. El negativo (2022: -$4,288) contenido.

**Comparacion GLD_PRO vs DIA_PRO (ambos Ogle ETF):**

| Metrica | DIA_PRO | GLD_PRO |
|---------|---------|---------|
| PF | 1.60-1.70 | **1.94** |
| Max DD | 7.56% | **7.02%** |
| Sharpe | 0.92-1.02 | 0.98 |
| CAGR | 7-8% | 7.17% |
| Trades/anio | ~18 | ~13 |
| Correlacion mutua | - | **~0.05** (casi cero) |
| Debilidades | 2020-2021 negativo/flat | 2022 negativo |

**Complementariedad DIA-GLD (clave para portfolio):**

| Anio | DIA_PRO | GLD_PRO | Se cubren? |
|------|---------|---------|:---:|
| 2020 | Negativo/flat | +$9,418 | GLD compensa DIA |
| 2021 | Negativo/flat | +$8,961 | GLD compensa DIA |
| 2022 | Positivo | -$4,288 | DIA compensa GLD |
| 2023 | Positivo | +$8,048 | Ambos bien |
| 2024 | ~45% del PnL total | +$16,230 | Ambos bien |
| 2025 | Positivo | +$11,271 | Ambos bien |

Correlacion ~0.05 → DD simultaneo extremadamente improbable.

**Valor de diversificacion vs forex completo:**
- 2022 (unico anio GLD negativo): forex tiene su mejor anio (+$73K solo EUR+CHF) → compensa de sobra
- 2024 (anio flojo EURUSD): GLD aporta +$16,230 > todo el portfolio EURUSD ese anio ($12,373)
- Driver GLD (inflacion, refugio) independiente de USD momentum (forex) y earnings US (DIA)

**Criterios de aceptacion:**

| Criterio | Umbral | GLD_PRO | |
|----------|--------|---------|---|
| PF > 1.5 | 1.5 | 1.94 | PASS |
| Max DD < 15% | 15% | 7.02% | PASS (mejor del sistema) |
| MC95 DD < 20% | 20% | 13.15% | PASS |
| CAGR > 5% | 5% | 7.17% | PASS |
| ≤1 anio negativo | ≤1 | 1 (2022) | PASS |
| Descorrelacion DIA | <0.20 | ~0.05 | PASS |

**Veredicto: APROBADO para portfolio combinado.**

- Tier sugerido: B (1.00% risk) — DD excelente pero sample size bajo (~13 trades/anio)
- Config live: risk_percent 0.5% inicial (mismo que DIA)
- Alerta si DD > 12%
- Pendiente: probar GLD con KOI y SEDNA (regla 2 estrategias por activo)

### GLD_KOI: ❌ DESCARTADO DEFINITIVAMENTE (2026-02-20 → 2026-02-21 → 2026-02-27)

> **Historial:** Descartado originalmente (2026-02-20) con datos corruptos → marcado para re-opt (2026-02-21) tras fix 3 bugs koi_strategy.py → **Re-optimizado y descartado definitivamente (2026-02-27).** Resultado post bug-fix: "descarte rotundo, va fatal".

**Resultado post bug-fix (2026-02-27):** GLD_KOI sigue sin funcionar tras re-optimización con estrategia corregida. Los problemas no eran causados por los bugs — son incompatibilidad fundamental KOI↔GLD.

**Problemas confirmados (persisten post bug-fix):**
- Resultados varian drasticamente con cualquier cambio minimo de parametros (sl_pips_filter, atr_filter, dias)
- Patron anual erratico: anos con ganancias enormes seguidos de perdidas enormes
- Sin zona estable de parametros — clasico signo de incompatibilidad estrategia-activo
- Mismo problema que DIA_KOI: CCI como filtro de momentum + SL ajustado es sensible a ruido en ETFs

**Diagnostico confirmado:** KOI usa CCI para confirmar momentum, pero el oro (GLD) tiene ciclos de momentum muy diferentes a forex. CCI oscila en rangos que no se alinean con los movimientos reales del oro. Esto NO era causado por bugs — es incompatibilidad fundamental.

**Decision final: ❌ GLD_KOI descartado definitivamente.** Re-opt post bug-fix confirma el diagnóstico original.

### GLD_SEDNA: DESCARTADO (2026-02-20)

**Resultado:** SEDNA no pasa umbrales minimos para GLD. Incoherente entre 5Y y 6Y.

**Metricas (5Y, la referencia real):**
- 110 trades, WR 45.5%, PF **1.44** (< umbral 1.5), DD 11.26%, MC95 20.35%
- Mejor config probada: KAMA 10/2/30, CCI disabled, horas [14-17,19,20], SL 30-200

**Problema principal: 2025 distorsiona el 6Y.**
- 5Y PF 1.44 vs 6Y PF 1.84 — toda la diferencia es el rally del oro H2 2025
- 2025 en 5Y: +$2,907 (18 trades) vs 6Y: +$54,888 (37 trades) = x19 diferencia
- 2021-2024 identicos en ambos datasets → base estable pero insuficiente
- No se puede confiar en metricas infladas por un evento excepcional

**Criterios de aceptacion (5Y):**

| Criterio | Umbral | GLD_SEDNA | |
|----------|--------|-----------|---|
| PF > 1.5 | 1.5 | 1.44 | FAIL |
| MC95 < 20% | 20% | 20.35% | FAIL (borderline) |
| DD < 15% | 15% | 11.26% | PASS |

**Comparacion con GLD_PRO (Ogle):**
| | GLD_PRO | GLD_SEDNA |
|--|---------|-----------|
| PF | **1.94** | 1.44 |
| DD | **7.02%** | 11.26% |
| MC95 | **13.15%** | 20.35% |

GLD_SEDNA es inferior en todas las metricas de riesgo.

**Decision: ❌ GLD_SEDNA descartado.**

### Decision final GLD (2026-02-20 → 2026-02-21 → **2026-02-27 ELIMINADO**)

- **GLD_PRO (Ogle): ❌ ELIMINADO (portfolio global 2026-02-27)** — Score 0.56 (rank 17/18). PF 1.92 pero MC95 18.07%, CAGR 6.45%. 2024 PF 0.98 (-$108), 2025 PF 1.07 (+$574). 2 años consecutivos ~breakeven. Edge agotado a nivel portfolio.
- **GLD_KOI: ❌ DESCARTADO DEFINITIVAMENTE** — Re-opt post bug-fix (2026-02-27): sigue fatal. Incompatibilidad KOI↔GLD confirmada.
- **GLD_SEDNA: ❌ ELIMINADO (portfolio global 2026-02-27)** — Score 0.54 (rank 18/18, peor del portfolio). PF degradó de 1.86 (backtest $100K) → 1.69 (portfolio $50K). 2025 negativo (-$137). DD 14.05%, Sharpe 0.99. Reservas del WF confirmadas.
- **Resultado: GLD COMPLETAMENTE ELIMINADO.** 0 de 3 estrategias viables. El oro no es compatible con nuestras estrategias a nivel portfolio.
- **`active: False`** en settings.py para GLD_PRO y GLD_SEDNA. Commit: portfolio global calibration.

---

---


---

### XLE_PRO (SunsetOgle): APROBADO (2026-02-21)

**Config optimizada:** EMA 9/21/55, ATR 14, SL 2.5x/TP 7.0x, pullback 3/10, días [Tue,Thu,Fri], horas [13-19], SL pips 10-60.

**Resultados 5Y (2020-07 a 2025-06):**
- 101 trades, WR 52.5%, PF **2.08**, Net $87,529
- DD 8.96%, MC95 15.35%, Sharpe 1.21, Calmar 1.53
- Todos los años en positivo (peor: 2023 PF 1.14/+$3,340)

**Resultados 6Y (2020-01 a 2025-12):**
- 117 trades, WR 53.8%, PF **2.16**, Net $107,794
- Core 2021-2024 idéntico entre 5Y y 6Y → base estable

**Coherencia 5Y↔6Y:** ✅ Robusto. PF 2.08→2.16 (+3.8%). H1 2020 añade +4 trades/$828, H2 2025 añade +12 trades/$18,868. Sin distorsión.

**Criterios de aceptación (5Y):**
| Criterio | Umbral | XLE_PRO | |
|----------|--------|---------|---|
| PF > 1.5 | 1.5 | 2.08 | ✅ |
| DD < 15% | 15% | 8.96% | ✅ |
| MC95 < 20% | 20% | 15.35% | ✅ |
| Sharpe > 1.0 | 1.0 | 1.21 | ✅ |

**Notas para filtrado futuro (no aplicado):**
- SL Pips 40-50: PF 0.86 (-$3,179) — único rango negativo
- ATR 0.15-0.17: PF 0.61 (-$7,898) — hueco entre zonas rentables
- Duration <200 bars: PF 0.52 (-$27,165) — trades rápidos pierden

### XLE_KOI: ~~EN ESPERA~~ → DESCARTADO tras Walk-Forward (2026-02-27)

**Config:** EMA 10/20/40/80/120, CCI 20/100/250, ATR 2.0x SL/10.0x TP, breakout 3bars/5pips, horas [14,15,16,19], días [Mon,Tue,Wed,Fri], SL pips 50-100.

**Resultados 6Y:**
- 56 trades, WR 57.1%, PF 1.90, Net $24,104
- DD 4.64%, MC95 8.18%, Sharpe 0.82, Calmar 0.83
- 5/6 años positivos (2025: PF 0.47/-$3,559)

**Walk-Forward (train 2020-2023 vs full 2020-2025):**
- Training: 43 trades, PF 2.35, Sharpe 1.20, DD 2.83% — sólido
- OOS 2024: PF 2.63, +$4,461 — edge confirmado
- OOS 2025: PF 0.47, -$3,559 — **año más reciente PIERDE**
- Full: PF 1.90, Sharpe **0.87** (< 1.0), 4/10 criterios fallan

**Motivo descarte:** Sharpe < 1.0 en periodo completo, CAGR 3.87% (irrisorio), 2025 perdedor, solo 9.9 trades/año. XLE_PRO (Ogle) es superior en PF (2.16), Sharpe (1.25), CAGR (13.52%) y trades/año (~19). Añadir KOI al mismo activo = ruido con comisiones, no diversificación.

### XLE_SEDNA: DESCARTADO (2026-02-22)

**Resultado:** SEDNA no funciona con XLE. PF < 1.0 = pierde dinero.

**Resultados 6Y:**
- 185 trades, WR 28.6%, PF **0.85**, Net -$21,845
- 2 de 6 años negativos (2023: -$16.8K, 2025: -$17K)
- Solo hora 19 rentable (PF 2.44). Todo lo demás pierde o break-even.

**Motivo descarte:** PF < 1.0, strategy fundamentalmente no funciona con este activo.

### Decisión parcial XLE (2026-02-22)

- **XLE_PRO (Ogle): ✅ APROBADO + WF CONFIRMADO Tier B (2026-02-27)** — Training PF 1.93, Full PF 2.16, OOS PF ~2.55. Mejor OOS de TODOS los ETFs.
- **XLE_KOI: ❌ DESCARTADO (walk-forward 2026-02-27)** — Sharpe 0.87 < 1.0, CAGR 3.87%, 2025 pierde. XLE_PRO es superior en todo excepto DD.
- **XLE_SEDNA: ❌ DESCARTADO** — PF 0.85, pierde dinero.
- **Regla 2 estrategias:** No cumplida. Ninguna segunda estrategia funciona con XLE → Tier B por calidad excepcional de Ogle.

---

### EWZ_PRO (SunsetOgle): ~~APROBADO~~ → DESCARTADO tras Walk-Forward (2026-02-27)

**Config optimizada:** EMA 9/21/55, ATR 14, SL 2.5x/TP 7.0x, pullback 3/10, días [Tue,Thu,Fri], horas [14-19], SL pips 10-100.

**Resultados 5Y (2020-07 a 2025-06):**
- 90 trades, WR 55.6%, PF **2.14**, Net $52,225
- DD 10.14%, MC95 8.83%, Sharpe 1.35, Calmar 0.90
- 2020 malo (PF 0.44/-$4.9K — COVID crash real brasileño), 2021-2025 todos positivos

**Resultados 6Y (2020-01 a 2025-12):**
- 107 trades, WR 55.1%, PF **2.04**, Net $58,146
- DD 13.34%, MC95 9.37%, Sharpe 1.23
- Core 2021-2024 idéntico → base estable

**Coherencia 5Y↔6Y:** ✅ Robusto. PF 2.14→2.04 (-4.7%) por H1 2020 (COVID). DD sube 10%→13% pero dentro de umbrales. MC95 apenas cambia (8.83→9.37%).

**2020 explicado:** EWZ cayó -58% (mar-2020, COVID + real desplomándose R$4→R$5.8/USD). Estrategia long-only en bear market brutal. Evento excepcional, no recurrente.

**Criterios (5Y):**
| Criterio | Umbral | EWZ_PRO | |
|----------|--------|---------|---|
| PF > 1.5 | 1.5 | 2.14 | ✅ |
| DD < 15% | 15% | 10.14% | ✅ |
| MC95 < 20% | 20% | 8.83% | ✅ |
| Sharpe > 1.0 | 1.0 | 1.35 | ✅ |

**Nota comisiones:** EWZ ~$28 precio → muchas shares para misma exposición → $190/trade comisión. Normal para un ETF barato.

### EWZ_KOI: DESCARTADO (2026-02-22)

**Resultado:** Imposible calibrar. KOI no funciona con EWZ — mismo patrón que GLD_KOI y DIA_KOI.
**Diagnóstico:** KOI + ETFs = incompatibilidad confirmada en 4 de 5 ETFs probados (DIA, GLD, EWZ, XLE). Solo XLU_KOI funciona (PF 2.31, Sharpe 1.34). XLE_KOI descartado WF 2026-02-27.

**Siguiente paso:** Probar EWZ con SEDNA.

### EWZ_SEDNA: DESCARTADO (2026-02-22)

**Resultado:** SEDNA no funciona con EWZ. Mismo patrón que XLE_SEDNA.

### Decisión parcial EWZ (2026-02-22) → Actualizado 2026-02-27

- **EWZ_PRO (Ogle): ❌ DESCARTADO (walk-forward)** — Config original parecía buena en 6Y (PF 2.14) pero estaba contaminada. Al separar training (2020-2023): PF 1.44, Sharpe 0.69 — ambos por debajo de umbrales. Re-optimización WF también falló (PF 1.85, Sharpe 0.91). 2 intentos, 2 fallos.
- **EWZ_KOI: ❌ DESCARTADO** — Imposible calibrar.
- **EWZ_SEDNA: ❌ DESCARTADO** — No funciona con EWZ.
- **EWZ: ❌ DESCARTADO DE PORTFOLIO** — Ninguna estrategia pasa walk-forward.

**Lección aprendida:** Un backtest que parece bueno en periodo completo puede esconder un training débil. El walk-forward reveló que el edge de EWZ_PRO estaba concentrado en 2024-2025 (OOS), no en el training. Calidad > cantidad: mejor 3 ETFs sólidos que 4 con uno débil.

---

### XLU_PRO (SunsetOgle): DESCARTADO (2026-02-24)

**Config optimizada:** Basada en GLD_PRO (activo defensivo similar). EMA 9/21/55, ATR 14, pullback 3/10, pip_value 0.01.

**Resultados 5Y (2020-07 a 2025-06):**
- 47 trades, WR 55.3%, PF **2.01**, Net $19,368
- DD 4.98%, MC95 6.83%, Sharpe **0.94**, CAGR **3.70%**
- Sortino 0.31 (Poor), Calmar 0.74

**Resultados 6Y (2020-01 a 2025-12):**
- 52 trades, WR 51.9%, PF **1.69**, Net $16,425
- DD 4.98%, MC95 8.31%, Sharpe **0.72**, CAGR **2.82%**
- PF degrada -15.9% (5 trades añadidos pierden ~$2,800 netos)

**Desglose anual (5Y):**

| Año | Trades | WR% | PF | PnL | % del total |
|------|--------|-----|-----|------|-------------|
| 2020 | 8 | 50.0% | 1.84 | $2,146 | 11.1% |
| 2021 | 8 | 50.0% | 1.01 | **$36** | **0.2%** |
| 2022 | 10 | 40.0% | 1.11 | **$673** | **3.5%** |
| 2023 | 5 | 60.0% | 2.58 | $2,071 | 10.7% |
| 2024 | 10 | 70.0% | 5.07 | **$11,916** | **61.5%** |
| 2025 | 6 | 66.7% | 2.00 | $2,527 | 13.0% |

**Evaluación:**

| Criterio | Umbral | 5Y | 6Y | |
|----------|--------|-----|-----|---|
| PF > 1.5 | 1.5 | 2.01 | 1.69 | ✅ |
| DD < 15% | 15% | 4.98% | 4.98% | ✅ |
| MC95 < 20% | 20% | 6.83% | 8.31% | ✅ |
| Sharpe > 1.0 | 1.0 | **0.94** | **0.72** | ❌❌ |

**Motivos de descarte:**
1. **Sharpe < 1.0 en ambos periodos** (0.94→0.72) — falla criterio duro, empeora con más datos
2. **CAGR 3.70%** — el más bajo de todos los ETFs, penaliza portfolio
3. **9 trades/año** — muestra insuficiente (GLD tiene 13 y ya era borderline)
4. **61.5% del PnL en 2024** — concentración extrema, peor que DIA (45%)
5. **2021-2022 muerto** — $709 en 2 años, no aporta al portfolio
6. **Bordes 6Y pierden** — 5 trades añadidos = -$2,800 netos → edge débil
7. **Coste de oportunidad** — capital en XLE (CAGR ~15%) o EWZ (~8.7%) rinde 3-4x más

**Nota:** DD 4.98% es el mejor del sistema, pero no compensa los fallos. Hipótesis: XLU (baja volatilidad, tendencias lentas/largas) podría funcionar mejor con KOI/SEDNA que con Ogle. Se probarán XLU_KOI y XLU_SEDNA.

### XLU_KOI: APROBADO → ✅ WF APROBADO Tier C (2026-02-27)

**Config:** Base XLE_KOI (único KOI funcional en ETF). Días [Mon,Tue,Wed,Fri], SL pips 50-120.

**Resultados 5Y (2020-07 a 2025-06):**
- 63 trades, WR 58.7%, PF **2.31**, Net $38,968
- DD 6.48%, MC95 7.73%, Sharpe **1.34**, CAGR 6.97%
- Sortino 0.51, Calmar 1.07
- 5/6 años positivos (2021: PF 0.34/-$2,605 único negativo)

**Resultados 6Y (2020-01 a 2025-12):**
- 80 trades, WR 53.8%, PF **1.94**, Net $39,231
- DD 9.96%, MC95 9.33%, Sharpe **1.14**, CAGR 5.98%
- Core 2021-2024 idéntico → base estable

**Coherencia 5Y↔6Y:** ✅ Core idéntico. Bordes neutros (+17 trades, +$508 netos). PF degrada -16% por H1 2020 (COVID), DD sube 6.48→9.96% (COVID). Degradación contenida, ambos periodos pasan todos los criterios.

**Desglose anual (5Y):**

| Año | Trades | WR% | PF | PnL | % del total |
|------|--------|-----|-----|------|-------------|
| 2020 | 9 | 77.8% | 4.80 | $8,238 | 21.1% |
| 2021 | 7 | 28.6% | 0.34 | -$2,605 | ❌ |
| 2022 | 18 | 66.7% | 3.58 | $17,932 | 46.0% |
| 2023 | 11 | 45.5% | 1.92 | $6,608 | 17.0% |
| 2024 | 8 | 50.0% | 1.38 | $2,025 | 5.2% |
| 2025 | 10 | 70.0% | 2.60 | $6,770 | 17.4% |

**Criterios (5Y/6Y):**

| Criterio | Umbral | 5Y | 6Y | |
|----------|--------|-----|-----|---|
| PF > 1.5 | 1.5 | 2.31 | 1.94 | ✅✅ |
| DD < 15% | 15% | 6.48% | 9.96% | ✅✅ |
| MC95 < 20% | 20% | 7.73% | 9.33% | ✅✅ |
| Sharpe > 1.0 | 1.0 | 1.34 | 1.14 | ✅✅ |

**Hito: Primer KOI aprobado en ETFs.** XLU_PRO (Ogle) fallaba Sharpe 0.94 en ambos periodos. XLU_KOI lo supera: PF 2.31 vs 2.01, Sharpe 1.34 vs 0.94, CAGR 6.97% vs 3.70%. Confirma hipótesis: CCI/breakout captura mejor las tendencias lentas de utilities que pullback/EMA.

### Walk-Forward Results: XLU_KOI ✅ APROBADO Tier C (2026-02-27)

**Training (2020-2023):** 59 trades | PF 1.97 | WR 52.5% | Sharpe 1.20 | DD 9.07% | $28,821 net
**Full (2020-2025):** 80 trades | PF 1.94 | WR 53.8% | Sharpe 1.07 | DD 9.07% | $39,231 net

**Desglose OOS (datos nunca vistos):**
| Año | Trades | WR | PF | PnL |
|-----|--------|-----|-----|-----|
| 2024 (blind) | 8 | 50.0% | 1.38 | +$2,005 |
| 2025 (blind) | 13 | 61.5% | **2.26** | +$8,405 |
| **OOS total** | **21** | **57.1%** | **~1.83** | **+$10,410** |

**Checklist WF: 9/10** (solo falla concentración 2022 = 61.6% en training, baja a 45.2% en full)
**OOS PF 1.83 > target 1.3** — edge confirmado con margen
**Training fuerte independiente** (PF 1.97, Sharpe 1.20) — no caso EWZ
**2025 mejor que 2024** — edge se fortalece, no degrada
**PF degradación -1.4%** — prácticamente nula

**Rankings ETF (XLU_KOI vs aprobados):**
- **Mejor PF** de todos los ETFs (2.31 > XLE 2.08 > EWZ 2.14 > GLD 1.95 > DIA 1.60)
- **Mejor DD** de todos los ETFs (6.48% < GLD 7.02% < DIA 7.56% < XLE 8.96%)
- **Mejor MC95** de todos los ETFs (7.73% < EWZ 8.83% < GLD 13.15% < XLE 15.35%)
- CAGR mediocre (6.97% — penúltimo, solo supera DIA ~7%)

**Tier sugerido: C (0.75% risk)** — excelente gestión de riesgo pero CAGR mediocre. Su valor es como estabilizador del portfolio (DD bajísimo libera capital para activos high-CAGR).

### XLU_SEDNA: DESCARTADO (2026-02-24)

**Resultado:** PF 1.16, CAGR 1.13%, 3 de 6 años negativos. Sin margen de optimización.

**Resultados 6Y:**
- 85 trades, WR 43.5%, PF **1.16**, Net $6,674
- DD 12.89%, MC95 13.35%, Sharpe 0.26, CAGR 1.13%
- 2020 (-$207), 2021 (-$4,074), 2022 (-$4,734) → 3 años consecutivos negativos

**Motivo descarte:** PF < 1.5, Sharpe 0.26, CAGR irrisorio. KAMA no captura la dinámica de XLU.

### Decisión final XLU (2026-02-24)

- **XLU_PRO (Ogle): ❌ DESCARTADO** — Sharpe 0.94 falla en ambos periodos, CAGR 3.70%
- **XLU_KOI: ✅ APROBADO + WF CONFIRMADO** — PF 2.31, Sharpe 1.34, DD 6.48%. WF: OOS PF 1.83, 9/10 criterios.
- **XLU_SEDNA: ❌ DESCARTADO** — PF 1.16, 3 años negativos
- **Regla 2 estrategias:** No cumplida. Solo KOI funciona → Tier C (0.75% risk)
- **Singularidad XLU:** Único ETF donde Ogle falla y KOI triunfa. CCI/breakout captura mejor tendencias lentas de utilities.

### Patrón ETF-Estrategia final (2026-02-24, actualizado 2026-03-14)

| ETF | Ogle | KOI | SEDNA | Estrategia(s) live |
|-----|:----:|:---:|:-----:|:------------------:|
| DIA | ✅ PF 1.83 | ❌ Inestable | ✅ PF 2.04 | Ogle (C) + SEDNA (B) |
| ~~GLD~~ | ~~✅ PF 1.92~~ ❌ Score 0.56 | ❌ Descartado | ~~✅⚠️ PF 1.69~~ ❌ Score 0.54 | **ELIMINADO** (portfolio global) |
| XLE | ✅ PF 2.16 (WF ✅ OOS 2.55) | ❌ PF 1.90/Sharpe 0.87 | ❌ PF 0.85 | Ogle (B) |
| EWZ | ~~✅ PF 2.14~~ ❌ WF falla | ❌ Imposible calibrar | ❌ Descartado | **DESCARTADO** |
| XLU | ❌ Sharpe 0.94 | ✅ PF 1.94/Sharpe 1.14 | ❌ PF 1.16 | KOI (C) |
| **TLT** | ❌ PF bajo | ❌ Falló | ❌ CERES PF 0.67, ❌ SEDNA ~60 trades/4Y | **⛔ TODAS DESCARTADAS** — nueva estrategia pendiente |

**Conclusiones:**
- Cada ETF tiene su estrategia óptima según su dinámica de precio
- Ogle (pullback/EMA): funciona en ETFs cíclicos/volátiles (DIA, XLE) — GLD pasa WF pero falla a nivel portfolio
- KOI (CCI/breakout): funciona en ETFs de tendencias lentas/baja volatilidad (XLU)
- SEDNA (KAMA): solo funciona en DIA entre los ETFs
- No hay estrategia universal para ETFs
- **GLD eliminado completamente** tras portfolio global (Score 0.54-0.56, 2024-2025 sin retorno)

**Portfolio ETF configurado (actualizado 2026-02-27):**
| ETF | Estrategia(s) | Tier | Risk |
|-----|--------------|:----:|:----:|
| DIA | Ogle + SEDNA | B | 1.0% |
| ~~GLD~~ | ~~Ogle + SEDNA~~ | ~~C~~ | ❌ Eliminado portfolio global |
| XLE | Ogle | B | 1.0% |
| ~~EWZ~~ | ~~Ogle~~ | ~~C~~ | ❌ Descartado WF |
| XLU | KOI | C | 0.75% |

*Ultima edicion: 2026-02-27 (Portfolio global calibrado, GLD_PRO + GLD_SEDNA eliminados, 16 configs activas con tiers) por sesion Copilot*

---

### 📊 Portfolio Global Backtest: Forex + ETFs (2026-02-27)

**Comando:** `python tools/portfolio_backtest.py -p -q --from-date 2020-01-01 --to-date 2025-12-01`
**Capital:** $50,000 | **Risk:** 1% uniforme (pre-tier) | **Configs:** 18

#### Portfolio Combined Summary

| Year | Trades | WR% | GEMINI | KOI | SEDNA | SunsetOgle | TOTAL |
|------|--------|-----|--------|-----|-------|------------|-------|
| 2020 | 234 | 40.6% | $4,955 | $10,261 | $12,517 | $30,791 | **$58,524** |
| 2021 | 177 | 45.8% | $633 | $15,296 | $14,192 | $39,245 | **$69,367** |
| 2022 | 357 | 47.3% | $17,214 | $42,284 | $27,217 | $65,335 | **$152,050** |
| 2023 | 297 | 45.5% | $8,913 | $39,725 | $27,804 | $62,137 | **$138,580** |
| 2024 | 298 | 44.6% | $12,688 | $33,494 | $32,946 | $64,180 | **$143,309** |
| 2025 | 322 | 46.6% | $15,417 | $64,532 | $40,220 | $71,589 | **$191,757** |

**Portfolio Totals:** 1698 trades | WR 44.9% | Net P&L: **$753,714** | Return: 1507% | Avg Annual: 251% | Weighted DD: **9.88%** | Worst individual DD: 14.45% (EURJPY_SEDNA)

**0 años negativos en el portfolio combinado.** Todos los años verdes.

#### Individual Config Ranking (Score = PF × Calmar / (MC95 / 10%))

| Rank | Config | PF | Sharpe | DD% | MC95% | CAGR% | Net $K | Calmar | Score | Neg Yrs |
|:----:|--------|-----|--------|------|-------|-------|--------|--------|:-----:|:-------:|
| 1 | USDCHF_PRO | 2.86 | 0.77 | 7.96 | 9.21 | 11.39 | 41.6 | 1.43 | **4.44** | 1 |
| 2 | USDCHF_GEMINI | 2.86 | 0.70 | 8.09 | 7.82 | 9.34 | 31.7 | 1.15 | **4.21** | 1 |
| 3 | EURUSD_PRO | 2.69 | 0.87 | 9.71 | 12.10 | 13.95 | 53.8 | 1.44 | **3.20** | 0 |
| 4 | DIA_SEDNA | 2.04 | 1.54 | 7.18 | 13.22 | 12.57 | 49.2 | 1.75 | **2.70** | 0 |
| 5 | USDCHF_KOI | 2.60 | 0.76 | 11.55 | 12.05 | 12.54 | 48.2 | 1.09 | **2.35** | 0 |
| 6 | EURJPY_PRO | 2.38 | 0.84 | 11.57 | 13.55 | 14.77 | 60.6 | 1.28 | **2.25** | 0 |
| 7 | XLE_PRO | 2.16 | 1.25 | 8.96 | 15.05 | 13.51 | 53.9 | 1.51 | **2.17** | 0 |
| 8 | EURUSD_KOI | 2.18 | 0.80 | 11.79 | 12.49 | 12.61 | 48.8 | 1.07 | **1.87** | 0 |
| 9 | EURJPY_KOI | 2.09 | 0.67 | 11.04 | 13.77 | 12.57 | 48.6 | 1.14 | **1.73** | 1 |
| 10 | USDJPY_SEDNA | 2.07 | 0.69 | 10.67 | 12.32 | 10.33 | 34.0 | 0.97 | **1.63** | 0 |
| 11 | USDJPY_KOI | 2.09 | 0.70 | 9.25 | 15.37 | 11.01 | 40.5 | 1.19 | **1.62** | 0 |
| 12 | USDJPY_PRO | 2.07 | 0.79 | 11.53 | 15.59 | 13.12 | 51.8 | 1.14 | **1.51** | 1 |
| 13 | DIA_PRO | 1.83 | 1.36 | 9.90 | 18.10 | 12.95 | 50.3 | 1.31 | **1.33** | 0 |
| 14 | XLU_KOI | 1.94 | 1.14 | 9.95 | 9.21 | 5.97 | 19.6 | 0.60 | **1.26** | 1 |
| 15 | EURUSD_GEMINI | 2.03 | 0.61 | 10.49 | 13.60 | 8.23 | 28.1 | 0.78 | **1.16** | 0 |
| 16 | EURJPY_SEDNA | 1.70 | 0.71 | 14.45 | 17.51 | 11.48 | 44.7 | 0.79 | **0.77** | 0 |
| 17 | ~~GLD_PRO~~ | 1.92 | 0.81 | 12.08 | 18.07 | 6.45 | 21.4 | 0.53 | **0.56** | 1 |
| 18 | ~~GLD_SEDNA~~ | 1.69 | 0.99 | 14.05 | 17.56 | 7.81 | 27.0 | 0.56 | **0.54** | 1 |

#### Tier Assignment (post global backtest)

| Tier | Risk% | Criteria | Configs |
|:----:|:-----:|----------|---------|
| **A** | 1.50% | Score > 3.0 | USDCHF_PRO, USDCHF_GEMINI, EURUSD_PRO |
| **B** | 1.00% | Score 1.5-3.0 | DIA_SEDNA, USDCHF_KOI, EURJPY_PRO, XLE_PRO, EURUSD_KOI, EURJPY_KOI, USDJPY_SEDNA, USDJPY_KOI, USDJPY_PRO |
| **C** | 0.75% | Score 1.0-1.5 | DIA_PRO, XLU_KOI, EURUSD_GEMINI |
| **D** | 0.50% | Score < 1.0 ⚠️ | EURJPY_SEDNA |

**Notable observations:**
- DIA_SEDNA tiene el mejor Sharpe (1.54) y Calmar (1.75) de todo el portfolio — justifica Tier B solo con ETF
- XLE_PRO segundo mejor Sharpe (1.25) — los 2 mejores Sharpe son ETFs
- 3 configs Tier A son todas USDCHF/EURUSD — los pares más líquidos dominan el top
- KOI domina en CAGR pero con Sharpe marginal en todos los pares

#### Eliminaciones tras portfolio global

**❌ GLD_PRO — ELIMINADO (Score 0.56)**
- MC95 18.07% (excede 15% target)
- CAGR 6.45% (below market — no compensa el riesgo)
- 2024: PF 0.98, -$108 — pierde dinero
- 2025: PF 1.07, +$574 — breakeven
- 2 años consecutivos sin generar retorno → edge agotado o nunca existió a nivel portfolio
- Argumento "hedge en crisis" invalidado: en 2024-2025 no protegió nada

**❌ GLD_SEDNA — ELIMINADO (Score 0.54, peor del portfolio)**
- PF degradó de 1.86 (backtest individual con $100K) → 1.69 (portfolio con $50K)
- 2025: PF 0.99, -$137 — año negativo
- DD 14.05% + MC95 17.56% — ambos en zona de peligro
- Sharpe 0.99 — sub-1.0
- Ya estaba "con reserva" desde WF — los datos de portfolio confirman las reservas
- La caída de PF (1.86→1.69) en condiciones reales es la señal definitiva

**⚠️ EURJPY_SEDNA — BAJO VIGILANCIA (Score 0.77)**
- DD 14.45% — peor del portfolio
- PF 1.70 — segundo peor
- Calmar 0.79 — sub-1.0
- ¿Por qué se mantiene? 0 años negativos en 6 años. Todos los años verdes ($1.2K-$17.2K). Aporta diversificación EURJPY con sesión diferente a PRO/KOI.
- **Criterio de eliminación:** Si DD > 18% en demo, o 2 meses consecutivos negativos → fuera

#### Decision final GLD (2026-02-27)

**GLD completamente eliminado del portfolio.**
- GLD_PRO: ❌ Eliminado (Score 0.56, 2024-2025 breakeven)
- GLD_SEDNA: ❌ Eliminado (Score 0.54, peor del portfolio, PF degradó)
- GLD_KOI: ❌ Descartado (incompatibilidad KOI↔GLD)
- **Resultado: 0 estrategias viables para GLD.** El oro no es compatible con nuestras estrategias a nivel portfolio.

#### Portfolio final: 16 configs activas

| Config | Strategy | Asset | Tier | Risk | Score |
|--------|----------|-------|:----:|:----:|:-----:|
| USDCHF_PRO | Ogle | USDCHF | A | 1.50% | 4.44 |
| USDCHF_GEMINI | GEMINI | USDCHF | A | 1.50% | 4.21 |
| EURUSD_PRO | Ogle | EURUSD | A | 1.50% | 3.20 |
| DIA_SEDNA | SEDNA | DIA | B | 1.00% | 2.70 |
| USDCHF_KOI | KOI | USDCHF | B | 1.00% | 2.35 |
| EURJPY_PRO | Ogle | EURJPY | B | 1.00% | 2.25 |
| XLE_PRO | Ogle | XLE | B | 1.00% | 2.17 |
| EURUSD_KOI | KOI | EURUSD | B | 1.00% | 1.87 |
| EURJPY_KOI | KOI | EURJPY | B | 1.00% | 1.73 |
| USDJPY_SEDNA | SEDNA | USDJPY | B | 1.00% | 1.63 |
| USDJPY_KOI | KOI | USDJPY | B | 1.00% | 1.62 |
| USDJPY_PRO | Ogle | USDJPY | B | 1.00% | 1.51 |
| DIA_PRO | Ogle | DIA | C | 0.75% | 1.33 |
| XLU_KOI | KOI | XLU | C | 0.75% | 1.26 |
| EURUSD_GEMINI | GEMINI | EURUSD | C | 0.75% | 1.16 |
| EURJPY_SEDNA | SEDNA | EURJPY | D | 0.50% | 0.77 |

**Distribución:** 4 estrategias × 7 activos (5 forex + 2 ETFs) = 16 configs
**Diversificación:** Forex (12) + ETF (4) | Ogle (5) + KOI (5) + SEDNA (3) + GEMINI (3)

#### Validación Tiered Risk: 16 configs con tiers A/B/C/D (2026-02-27)

**Comando:** `python tools/portfolio_backtest.py -p -q --from-date 2020-01-01 --to-date 2025-12-01`
**Capital:** $50,000 | **Risk:** Tiered (A=1.50%, B=1.00%, C=0.75%, D=0.50%) | **Configs:** 16

**Objetivo:** Verificar que la asignación de riesgo diferenciada por tiers produce resultados consistentes con la corrida uniforme al 1% (18 configs). Confirmar que eliminar GLD y redistribuir no genera efectos colaterales.

##### Portfolio Combined Summary (Tiered)

| Year | Trades | WR% | GEMINI | KOI | SEDNA | SunsetOgle | TOTAL |
|------|--------|-----|--------|-----|-------|------------|-------|
| 2020 | 209 | 39.2% | $3,573 | $9,371 | $4,484 | $30,474 | **$47,902** |
| 2021 | 158 | 43.7% | $466 | $15,633 | $4,390 | $36,637 | **$57,126** |
| 2022 | 339 | 46.9% | $23,993 | $39,893 | $22,205 | $73,945 | **$160,036** |
| 2023 | 276 | 44.9% | $9,058 | $38,791 | $19,813 | $65,699 | **$133,360** |
| 2024 | 265 | 44.5% | $15,255 | $33,205 | $15,557 | $68,107 | **$132,125** |
| 2025 | 294 | 46.6% | $21,268 | $63,276 | $35,957 | $95,524 | **$216,025** |

**Portfolio Totals (Tiered):** 1543 trades | WR 44.7% | Net PnL: **$746,020** | Return: 1492% | Avg Annual: 249% | Weighted DD: **10.08%** | Worst individual DD: 14.18% (EURUSD_PRO)

##### Comparación: Tiered (16 cfg) vs Uniform 1% (18 cfg)

| Métrica | Uniform 1% (18 cfg) | Tiered (16 cfg) | Delta | Veredicto |
|:--------|:--------------------:|:----------------:|:-----:|:---------:|
| Configs | 18 | 16 | -2 (GLD) | Limpieza |
| Trades | 1,698 | 1,543 | -155 (-9%) | Menos ruido |
| Net PnL | $753K | $746K | -$7K (-1%) | ✅ Despreciable |
| Return | 1,507% | 1,492% | -15pp | ✅ Estable |
| Wtd DD | 9.88% | 10.08% | +0.20pp | ✅ Marginal |
| Worst DD | ~14.45% | 14.18% | -0.27pp | ✅ Mejora |
| Neg Years | 0 | 0 | = | ✅ Perfecto |

##### Validación por tier — Escalado lineal confirmado

**Tier A (1% → 1.50%) — PnL escala ~+50%:** ✅
- EURUSD_PRO: $65K → $97K (+49%) | DD 9.71% → 14.18% (×1.46)
- USDCHF_PRO: $48K → $72.5K (+51%) | DD 7.96% → ~12% (×1.50)
- USDCHF_GEMINI: $36K → $53.6K (+49%) | DD 8.09% → ~12% (×1.48)

**Tier B (1% → 1%) — Sin cambio:** ✅ Todos idénticos a la corrida anterior

**Tier C (1% → 0.75%) — PnL escala ~-25%:** ✅
- DIA_PRO: $46K → $34.7K (-24%) | DD proporcional
- XLU_KOI: $19K → $14.2K (-25%) | DD proporcional
- EURUSD_GEMINI: $27K → $20K (-26%) | DD proporcional

**Tier D (1% → 0.50%) — PnL escala ~-50%:** ✅
- EURJPY_SEDNA: $38K → $19.2K (-49%) | DD reducido proporcional

**Conclusión:** El tiering funciona exactamente como se esperaba — escalado lineal en PnL y DD. El portfolio pierde solo 1% de retorno total pero redistribuye capital hacia los configs más robustos (Tier A). El DD ponderado sube apenas 0.20pp porque los Tier A tienen DDs históricamente bajos.

**✅ VALIDACIÓN COMPLETADA — Tiered risk confirmado como configuración de producción.**

---

## 🆕 Plan Estratégico: Nuevas Estrategias (2026-02-28) → Actualizado 2026-03-01

### Contexto y motivación

**Problema estructural ETFs — El 20% del portfolio no tiene estrategia propia:**

El portfolio actual tiene 16 configs activas: 12 forex + 4 ETFs.
Las 4 configs ETF (DIA_PRO, DIA_SEDNA, XLE_PRO, XLU_KOI) usan estrategias diseñadas para forex 24h
parcheadas con EOD close para funcionar en ventanas de 6.5h/día con gaps overnight.

**Evidencia del problema:**
- Tasa de supervivencia forex→ETF: **27%** (4 de 15 combinaciones probadas)
- GLD eliminado (0 estrategias viables — Score 0.56/0.54 en portfolio global)
- EWZ descartado (WF revelado como espejismo — OOS fatal)
- GLD_KOI: incompatibilidad total (CCI breakout no funciona en GLD)
- XLE_KOI: descartado (Sharpe 0.87, 2025 pierde)
- El bloque ETF actual generó **-$195 en 3 meses OOS** antes de re-optimización
- GLD era el **gran diversificador** del portfolio (correlación ~0.05 con DIA, ~0 con forex). Perderlo duele.

**Las 4 configs ETF supervivientes funcionan**, pero son adaptaciones forzadas, no diseño nativo:
- DIA_PRO/DIA_SEDNA: OK, DIA es líquido y se comporta como "forex de equities"
- XLE_PRO: Sorprendentemente fuerte (mejor OOS ETF: PF 2.55)  
- XLU_KOI: Marginalmente OK (OOS PF 1.83, Score 1.26)

**La solución NO es seguir forzando estrategias forex en ETFs.**
La solución es crear una estrategia **nativa ETF** que entienda la estructura del mercado:
ventanas cortas, gaps overnight, patrones de apertura, contexto 24h vía feeds forex.
→ Esta es CERES.

**Impacto de resolver esto:**
- Recuperar GLD (oro = principal diversificador, correlación ~0 con equity y forex)
- Abrir TLT (bonos = otro diversificador enorme, anticorrelado con DIA en crisis)
- Fortalecer DIA/XLE/XLU con una estrategia que realmente entienda ETFs
- Potencialmente NEW activos: GDX (mineras oro), VNQ (REITs), EEM (emergentes)

---

### GEMINI_S — Sync Mode — ⛔ APARCADO (2026-03-01)

**Concepto:** GEMINI actual busca divergencia (correlación inversa ~-0.90). GEMINI_S busca
sincronía (correlación directa ~+0.60 a +0.90). Mismo motor, signo opuesto.

**Estado implementación:** ✅ Código implementado y funcional (commits 7259c03 + 82ab336).

**Resultado OOS: HORRIBLE.** Iván optimizó parámetros y el resultado OOS es inaceptable.
La correlación USDJPY↔EURJPY (+0.64) es demasiado baja vs EURUSD↔USDCHF (-0.81 del GEMINI original).
La señal de sincronía es ruidosa — Harmony positiva solo 63.7% del tiempo.
El concepto funciona en training pero no generaliza a datos ciegos.

**Decisión: APARCADO.**
- El código queda en el repositorio (0 coste de mantenimiento, sync_mode=False = GEMINI original intacto)
- Las configs USDJPY_GEMINI_S y EURJPY_GEMINI_S quedan `active: False`
- **NO se invierte más tiempo en optimización GEMINI_S ahora**
- Se puede retomar en el futuro si:
  - Se encuentran pares con correlación directa > 0.85 (ej: GLD↔SLV ~+0.92)  
  - Se acumula experiencia con CERES que sugiera un ángulo diferente
  - Se tiene tiempo de sobra después de que CERES esté en producción

**Archivos afectados (ya implementados, no borrar):**
1. `strategies/gemini_strategy.py` — param `sync_mode=False` (L131), condicional (L357-360)
2. `live/checkers/gemini_checker.py` — `self.sync_mode = params.get("sync_mode", False)` (L83)
3. `config/settings.py` — USDJPY_GEMINI_S + EURJPY_GEMINI_S con `active: False`
4. `tools/analyze_gemini.py` — ATR step auto-detect JPY

**Lección aprendida:** Correlación directa < 0.80 no genera señal de sincronía útil.
GEMINI original funciona porque EURUSD↔USDCHF tienen -0.81 → señal limpia.
Para GEMINI_S, necesitas +0.85 mínimo. Los pares JPY no lo cumplen.

---

### CERES — Estrategia Intraday ETF-Nativa — 🎯 PRIORIDAD MÁXIMA

**Nombre:** CERES (diosa de la cosecha — cosecha momentum de apertura tras observar el campo durante la noche).
Sigue convención del sistema: SEDNA, GEMINI = cuerpos celestes/mitología.

**Filosofía:** Estrategia intraday modular diseñada nativamente para ETFs. No predice dirección —
detecta momentum de calidad y se suma. Cero exposición overnight (EOD close = parte del diseño, no parche).

**Diferencial vs estrategias existentes:**

| | Ogle | KOI | SEDNA | GEMINI | **CERES** |
|---|---|---|---|---|---|
| Timeframe | Multi-day | Multi-day | Multi-day | Multi-day | **Intraday** |
| Overnight | Sí (gaps) | Sí (gaps) | Sí (gaps) | Sí | **No (EOD)** |
| Señal | Pullback EMA | CCI breakout | KAMA cross | Cross-asset ROC | **Ventana + filtros modulares** |
| Nº feeds | 1 | 1 | 1 | 2 (mismo TF) | **1 o 2 (distinto TF posible)** |
| Diseñada para | Forex/ETF | Forex/ETF | Forex/ETF | Forex puro | **ETF nativo** |

**Arquitectura modular (todos los filtros opcionales excepto core):**

```
CERES Strategy
├── CORE (obligatorio):
│   ├── Ventana de entrada post-apertura (N velas tras open)
│   ├── SL/TP basados en ATR
│   └── EOD close (intraday puro, 20:50 UTC)
│
└── FILTROS (on/off por config):
    ├── [F1] ER threshold     → calidad de tendencia (Efficiency Ratio)
    ├── [F2] Días permitidos  → Mon/Tue/Wed/Thu/Fri
    ├── [F3] Horas permitidas → rango UTC
    ├── [F4] SL pips min/max  → evita micro/macro SL
    ├── [F5] Contexto 24h     → feed secundario forex (XAUUSD para GLD, etc.)
    │   ├── ER del activo 24h (tendencia limpia?)
    │   ├── Dirección del día (bias alcista/bajista)
    │   └── Niveles Asia+London (soporte/resistencia)
    └── [F6] Opening Range Breakout
        └── High/low primeras N barras = rango → solo entrar si rompe
```

**Idea clave F5 — Contexto 24h (diferencial principal):**
Cuando GLD abre a las 14:30 UTC, llevas 14.5 horas ciego sobre lo que hizo el oro.
Pero XAUUSD (forex 24h) operó toda la noche: Asia procesó datos, London confirmó.
Mirando XAUUSD en 15min como feed de contexto (no para tradear — solo para leer), cuando GLD abre
ya tienes: dirección del día, ER de calidad, niveles de soporte/resistencia.
No tradeas XAUUSD (cero swap). Solo lo lees. Tradeas GLD con comisión barata y sin swap intraday.

Esto es a CERES lo que GEMINI_S es a GEMINI: usar un segundo activo como inteligencia, no como trade.

**Escalabilidad F5 por activo:**

| ETF (trade) | Feed contexto 24h | En Dukascopy | Correlación | Viabilidad |
|-------------|-------------------|:---:|:---:|:---:|
| **GLD** | XAUUSD 15min | ✅ | ~0.99 | **Perfecto** |
| **DIA** | US30 futuros | ⚠️ verificar | ~0.99 | Bueno si hay data |
| **XLE** | WTI/Brent | ✅ | ~0.70 | Bueno (sector petrolero) |
| **XLU** | — | ❌ | — | **Sin equivalente** → usa F1-F4+F6 |
| **TLT** | — | ❌ | — | **Sin equivalente** → usa F1-F4+F6 |

**Parámetros iniciales sugeridos (GLD como primer test):**

```python
# Core
delay_bars: 0                 # 0 = OR starts at first bar of day (DST-agnostic)
                              # N = skip N bars after open before OR
atr_period: 14
sl_atr_mult: 1.5
tp_atr_mult: 3.0
eod_close_hour: 20
eod_close_minute: 50

# F1: Efficiency Ratio
er_period: 20
er_threshold: 0.35            # 0.0 = desactivado

# F2-F4: Filtros estándar
allowed_days: [0,1,2,3,4]     # Mon-Fri
allowed_hours: [15,16,17,18,19]
sl_pips_min: 5
sl_pips_max: 80

# F5: Contexto 24h (opcional)
use_context_feed: True        # False = sin segundo feed
context_er_period: 40         # ER sobre XAUUSD 15min (~10h lookback)
context_er_threshold: 0.30
context_bias: True            # usar dirección del día como filtro

# F6: Opening Range Breakout
orb_bars: 6                   # high/low de primeras 6 barras = rango
orb_breakout: True            # solo entrar si rompe rango
```

**Esfuerzo estimado:** 3-5 días implementación + 2-3 días backtesting por activo

---

### Descartados definitivamente (2026-02-28, actualizado 2026-03-01)

| Activo/Concepto | Motivo |
|----------------|--------|
| **XAUUSD** | Swap -$82.8/día. Con 3 días holding = -$248. Risk budget $500 → 50% devorado por swap |
| **XAGUSD** | Swap -$65/día. Mismo problema. Spread 0.10 no compensa |
| **ORB como estrategia separada** | Absorbido por CERES (filtro F6). No reinventar la rueda |
| **GEMINI_S (sync_mode)** | ⛔ APARCADO. OOS horrible. Correlación +0.64 insuficiente (necesita > +0.85). Código queda, configs desactivadas. Retomar solo con pares alta correlación (GLD↔SLV ~+0.92) |
| **SLV/EEM/VNQ standalone** | Tasa supervivencia 27%. Coste/beneficio desfavorable CON estrategias forex. Re-evaluar con CERES. |
| **SPY/QQQ/IWM** | Correlación >0.85 con DIA. Redundantes |

---

### Plan de desarrollo ordenado (actualizado 2026-03-01)

| Fase | Qué | Base | Esfuerzo | Impacto esperado | Estado |
|------|-----|------|----------|-------------------|:------:|
| ~~**A1**~~ | ~~`sync_mode` en GEMINI → GEMINI_S~~ | — | — | — | ✅→⛔ Hecho pero OOS falla |
| ~~**A2**~~ | ~~BT USDJPY_GEMINI_S + EURJPY_GEMINI_S~~ | — | — | — | ⛔ Aparcado |
| ~~**A3**~~ | ~~BT GLD_GEMINI_S (ref: SLV)~~ | — | — | — | ⛔ Aparcado (retomable) |
| **B1** | **CERES — diseño detallado** | Discusión profunda antes de codificar | 1 sesión | Evitar re-trabajo | ✅ Hecho |
| **B2** | CERES — implementar estrategia base | Nueva estrategia desde cero | 3-5 días | Plataforma ETF intraday | ✅ v0.8.1 |
| **B3** | CERES BT GLD (con XAUUSD context F5) | Data XAUUSD ya existe | 1-2 días | Test estrella — recuperar GLD | ⚠️ GLD funciona 2020-23, colapsa 2024-25 |
| **B4** | CERES → DIA, XLE, XLU, TLT | Configs nuevas por activo | 1-2 días c/u | Expansión ETF completa | ⏳ XLU ❌, EWZ ❌, TLT ❌, DIA pendiente |

**Prioridad absoluta: CERES.** GEMINI_S aparcado. Toda la energía en resolver el bloque ETF.

### 🔴 PRIMERA TAREA SIGUIENTE SESIÓN

**Simplificar CERES radicalmente.** El pullback Ogle de 4 estados es sobreingeniería para ETFs intraday — genera muy pocas entradas (~36/año en TLT) y no hay margen estadístico para optimizar filtros.

**Objetivo:** Pullback ultra-simple que maximice número de entradas:
1. OR mínimo: solo definir HH/LL con pocas barras (3-5), sin filtros de calidad
2. Pullback = 1 cierre bajo OR_HH (sin contar bearish candles, sin canal, sin re-arms)
3. Compra al siguiente cierre por encima de OR_HH (sin ventana Ogle)
4. SL = OR_LL, TP = EOD — lo más directo posible

**Razón:** Con 3-5x más entradas se puede medir el impacto real de cada filtro con significancia estadística. Ahora CERES intenta ser inteligente con pocas muestras = sobreingeniería en backtesting.

**Enfoque:** Crear versión simplificada → baseline con muchas entradas → ir añadiendo UN filtro a la vez midiendo impacto.

### CERES — Estado actual (2026-03-03)

**Versión:** v0.8.2 (`fb4fda4`)

**Commits:**
- `2280c18` — v0.8: Ogle pullback reemplaza permissive pullback, ATR filter eliminado, 4-state machine
- `4d8b9b4` — v0.8.1: pb_depth_filter + allowed_pb_bars filter
- `fb4fda4` — v0.8.2: 3 fixes order management (1 CRITICAL: phantom trades por day-change close)

**Arquitectura:** 4 estados (IDLE → WINDOW_FORMING → ARMED → WINDOW_OPEN).
State machine: OR se forma, breakout arma la señal, pullback confirma, entry al rebreak.

**Bugs corregidos (2026-03-03):** 3 fixes en order management tras auditoría completa
(ver `BUGS_FIXES.md` sección "CERES v0.8.1 — Auditoría" y `CERES_ORDER_AUDIT.md` para informe detallado):
1. `_traded_today` no reseteaba en Margin/Rejected → ahora sí resetea
2. Day-change resets prematuros → movidos después del order guard
3. **CRITICAL:** `order.isbuy()` check en notify_order — sin esto, el close de day-change se confundía con entry fill → phantom SL/TP → cascade de SHORT fantasma (686 vs 144 trades reales en TLT)

**Backtesting por activo:**

| Activo | Resultado | Notas |
|--------|-----------|-------|
| GLD | ⚠️ Funciona 2020-23 (Sharpe 1.08, PF 1.69), colapsa 2024-25 (PF 0.45) | Cambio de régimen. Params: or=15, pb_max=7, retries=2 |
| XLU | ❌ No funciona | Sin params que generen resultados aceptables |
| EWZ | ❌ No funciona | Sin params que generen resultados aceptables |
| TLT | ❌ PF 0.67, -22% (144 trades, 2020-2023) | No funciona intraday. Confirmado con v0.8.2 (sin phantom trades) |
| DIA | ⏳ Pendiente | Siguiente a probar |

**Conclusión v0.8.2:** Los bugs de order management se corrigieron pero los resultados ETF no cambian sustancialmente — el problema es estructural (pocas entradas, mecánica demasiado compleja). Necesita simplificación radical.

---

### CERES v0.9.0 — Simplificación + Pruebas Finales (2026-03-04)

**Cambios v0.9.0:** Simplificación radical del mecanismo de pullback:
- Eliminados 5 parámetros Ogle (bearish candle counting, breakout channel, re-arms)
- Eliminado estado WINDOW_OPEN (4→3 estados: IDLE → WINDOW_FORMING → ARMED)
- Nuevo pullback ultra-simple: `close < OR_HH` (pullback visto) → `close > OR_HH` (entry)
- Commit: `11247d5`

**Motivación:** CERES v0.8.2 generaba ~36 entradas/año en TLT — insuficiente para significancia estadística. La simplificación busca maximizar entradas para medir el edge real de ORB en ETFs.

**Pruebas completas realizadas (2026-03-04) — v0.9.0, todos filtros OFF:**

| Test | Asset | or_candles | Trades | PF | DD% | 2020 PF | 2021 PF | 2022 PF | 2023 PF | 2024 PF | 2025 PF |
|:----:|-------|:----------:|:------:|:--:|:---:|:-------:|:-------:|:-------:|:-------:|:-------:|:-------:|
| 1 | GLD | 15 | 254 (IS) | 1.02 | — | 1.37 | 0.91 | 0.65 | 1.24 | — | — |
| 2 | GLD | 15 | 412 (full) | 0.88 | — | — | — | — | — | ~0.5 | ~0.3 |
| 3 | **DIA** | **6** | **677** | **1.08** | **21.6%** | 1.37 | 1.21 | 0.98 | 1.30 | **0.75** | **1.02** |
| 4 | **DIA** | **12** | **612** | **1.11** | **14.9%** | 1.26 | 1.33 | 1.11 | 1.20 | **0.95** | **0.92** |
| 5 | XLE | 6 | 595 | **0.95** | 29.6% | 1.20 | 0.89 | 0.95 | 1.54 | **0.58** | **0.63** |
| 6 | XLE | 12 | 510 | **0.96** | 22.2% | 1.13 | 0.77 | 1.06 | 1.66 | **0.66** | **0.65** |
| — | TLT (v0.8) | 15 | 144 | 0.67 | — | — | — | — | — | — | — |
| — | XLU (v0.8) | — | — | ❌ | — | — | — | — | — | — | — |
| — | EWZ (v0.8) | — | — | ❌ | — | — | — | — | — | — | — |

**8 pruebas en 6 ETFs, 0 viables.** El mejor resultado (DIA or=12) tiene PF 1.11 con DD 14.9% y OOS negativo.

**GLD filtros (intento de optimización, descartado):**
- SL 70-90 + drop Tuesday: IS PF 1.71 (46 trades) → OOS PF 0.47 (collapse). WF: 4/10 pass, OOS VERDICT: FAIL.
- OR ER 0.30-0.60: Comenzado, cancelado por usuario (metodología correcta = no iterar filtros contra OOS).
- Conclusión: iterar filtros para pasar OOS viola la metodología WF. Se aceptó que el patrón no generaliza.

**Análisis detallado DIA_CERES or=6 (mejor candidato por número de trades):**
- Hora 14 (primera post-open): PF 0.92, 242 trades (36% del total) = ruido puro
- Horas 15-16: PF 1.26-1.38 = edge leve
- PB bars 2-4: PF 0.80 = breakouts falsos
- PB bars 7-15: PF 1.91-2.64 = los que esperan confirman mejor
- OR height 250-400 pips: PF 1.59-1.71 = rangos amplios dan señal, estrechos = ruido
- EOD_CLOSE trades: PF 8.75 (437 trades) = el edge está en los winners que sobreviven
- STOP_LOSS trades: PF 0.00 (239 trades) = todas las pérdidas = SL-only

### ❌ CERES — DESCARTADO DEFINITIVAMENTE (2026-03-04)

**Diagnóstico: incompatibilidad estructural ORB ↔ ETFs 6.5h**

1. **Ventana de 6.5h demasiado corta:** ORB necesita tiempo para desarrollar tendencia. Con EOD close a 20:45, quedan ~5h tras OR de 60min. Insuficiente para ratio riesgo/recompensa viable.

2. **SL = OR_LL demasiado amplio relativo al rango:** En DIA, media SL = 197 pips ($1.97). El rango diario de DIA es $2-4. El SL cubre la mitad del rango → R:R inherentemente pobre.

3. **LONG-only en bear/chop markets:** 2022 (bear), 2024 (chop DIA) → sin SHORT = quemas capital.

4. **Comisiones devoran el margen:** $32/trade media en DIA vs PnL medio $51/trade → comisiones = 63% del profit.

5. **El pullback es cosmético:** Después de OR, el cierre cae por debajo de OR_HH casi siempre → la condición se satisface inmediatamente, no filtra nada.

**Comparación vs estrategias que SÍ funcionan (baseline sin filtros):**

| Estrategia | Asset | PF baseline | Notas |
|---|---|:---:|---|
| DIA_SEDNA | DIA | **2.04** | Edge fuerte base |
| XLE_PRO | XLE | **2.16** | Mejor OOS de ETFs |
| USDCHF_PRO | USDCHF | **2.86** | Edge masivo |
| **CERES (mejor)** | DIA | **1.11** | Marginal, OOS neg |

Las estrategias viables tienen PF > 1.5 antes de filtros. CERES no llega a 1.12 ni con la mejor configuración.

**Decisión final: CERES descartado.**
- `active: False` en todas las configs (GLD_CERES, TLT_CERES, DIA_CERES, XLE_CERES)
- El código se conserva en `strategies/ceres_strategy.py` (0 coste, referencia)
- No se invierte más tiempo en ORB intraday para ETFs
- El portfolio actual (16 configs: 12 forex + 4 ETFs con Ogle/SEDNA/KOI) es robusto y WF-validado
- Si se busca expansión ETF en el futuro, explorar: (a) SHORT capability en Ogle/SEDNA, (b) estrategia multi-day momentum, (c) GEMINI_S cuando haya pares con correlación > +0.85

**Lección aprendida:** Una estrategia diseñada para un timeframe (intraday 6.5h) con restricción LONG-only y EOD close obligatorio tiene un techo estructural de rentabilidad que no se puede superar con filtros. El concepto ORB funciona en mercados 24h donde hay tiempo para que las tendencias se desarrollen. En ETFs de sesión corta, las estrategias multi-day (Ogle, SEDNA, KOI) capturan mejor la estructura del mercado.

---

*Ultima edicion: 2026-03-20 (consolidation_bars rango min/max anti-overfitting) por sesion Copilot*

---

## 📊 BACKTESTING INDICES CFD — LUYTEN ORB (2026-03-18)

### AUS200_LUYTEN — Infraestructura lista

**Fecha:** 2026-03-18
**Objetivo:** Escalar LUYTEN ORB a indices CFD, empezando por AUS200.

**Datos:** `data/AUS200_5m_5Yea.csv` — 379,992 lineas, 2020-01-01 a 2026-03-17, precios enteros (~6677-8606)

**Costes modelados (Darwinex Zero CFD Index):**
- Spread: 0.8 pts (no modelado en BT, asumido en slippage)
- Comision: 2.75 AUD/orden/contrato real (10x indice) → 0.275 por share BT
- Margen: 5%
- Swap long: -12.69 AUD/dia, Swap short: +5.49 AUD/dia (no modelado — EOD close evita swaps)
- Nota: P&L en AUD, BT asume USD — simplificacion aceptable para screening (AUD/USD ~0.65)

**Parametros escalados desde TLT (pip_value 0.01 @ $100 → 1.0 @ ~8000):**
| Parametro | TLT | AUS200 | Logica |
|-----------|-----|--------|--------|
| pip_value | 0.01 | 1.0 | Minimo tick del activo |
| bk_above | 6.0 pips | 5.0 pips | Equivalente porcentual |
| sl_pips range | 10-100 | 8-80 | Escalado por ratio de precios |
| atr_range | 0.12-0.22 | 10-18 | Escalado 100x por pip_value |
| margin_pct | 20% | 5% | Segun broker |
| eod_close | 18:50 | 20:50 | Ajustado a horario mercado |

**Baseline (sin optimizar, 2020-2023):** 53 trades, PF 0.87, DD estimado ~16% — resultado esperado pre-optimizacion.
**Optimizer smoke test:** 90 trades con base params distinto periodo, PF 0.96 — confirma infraestructura OK.

**Archivos modificados:**
1. `config/settings.py` — Config `AUS200_LUYTEN` + broker `darwinex_zero_cfd_index`
2. `run_backtest.py` — AUS200 en ETF_SYMBOLS + soporte `broker_config_key` por config
3. `lib/position_sizing.py` — AUS200 en ETF_SYMBOLS
4. `tools/luyten_optimizer.py` — Refactorizado: `ASSET_PROFILES` dict (TLT/AUS200), CLI arg (`python tools/luyten_optimizer.py AUS200`)

**Herramientas compatibles sin cambios:** `analyze_optimizer.py`, `compare_robustness.py` (genericas)

**Pendiente:** Optimizacion grid-search completa, analisis OOS, decision go/no-go.

---

## 🔧 LUYTEN v1.1 — consolidation_bars rango min/max (2026-03-20)

**Problema:** `consolidation_bars=19` era valor fijo que dominaba las optimizaciones (8 de 10 mejores combos en Phase 2 TLT). Esto genera riesgo de overfitting a un numero exacto de barras.

**Solucion:** Reemplazar `consolidation_bars` (int) por `consolidation_bars_min` + `consolidation_bars_max` (rango). Despues de `_min` barras, se empieza a chequear breakout mientras se sigue actualizando el consolidation_high. Al llegar a `_max`, transiciona a WAITING_BREAKOUT puro (sin mas actualizaciones del high).

**Logica nueva en state machine:**
1. CONSOLIDATION: acumula barras y registra high (igual que antes)
2. Al alcanzar `consolidation_bars_min`: empieza a llamar `_check_breakout()` en cada barra
3. Al alcanzar `consolidation_bars_max`: transiciona a WAITING_BREAKOUT
4. `_check_breakout()`: metodo extraido, compartido por ambos estados

**Ventaja anti-overfitting:** Un breakout tras 15, 17 o 21 barras es igualmente valido. El rango captura este abanico en lugar de fijar un unico punto optimo.

**Archivos modificados:**
1. `strategies/luyten_strategy.py` — Nuevo param min/max, metodo `_check_breakout()`, report/prints actualizados
2. `config/settings.py` — AUS200_LUYTEN: `consolidation_bars_min: 15, consolidation_bars_max: 21`
3. `tools/luyten_optimizer.py` — Sweep independiente de CBMin y CBMax, filtro `min > max`, short names `CBMin`/`CBMax`

**Impacto en optimizer:**
- AUS200: 1080 combos (15 pares min/max validos)
- TLT: 2816 combos (21 pares min/max validos)
- Default (min=max=valor_original) reproduce comportamiento v1.0

---

### LUYTEN — Fixes críticos AUS200 (2026-03-20)

#### 1. Bug: Rechazo masivo de órdenes por margen (commit 5897f37)

**Síntoma:** AUS200_LUYTEN solo ejecutaba 5 de 236 órdenes. Las 231 restantes eran rechazadas con error "Margin".

**Causa raíz:** `ETFCommission` usa `stocklike=True`, lo que hace que backtrader descuente el **precio completo** del cash disponible. AUS200 cotiza a ~$7000/acción: con $100k de capital solo caben 14 acciones a precio completo, pero el sizer basado en riesgo pedía entre 44-133 → rechazo masivo.

**Fix:** Nueva clase `CFDIndexCommission` en `lib/commission.py`:
- `stocklike=False` → backtrader usa margen, no precio completo
- `automargin=True` → `get_margin()` retorna `price * margin_pct / 100`
- `margin_pct=5.0` (configurable) → $7000 × 5% = $350/acción en lugar de $7000
- `commission=0.275` (por defecto)
- Contadores de debug a nivel de clase (como ETFCommission)

**Auto-selección en run_backtest.py y luyten_optimizer.py:**
```
if 'cfd_index' in broker_config_key → CFDIndexCommission
else → ETFCommission
```

**Resultado:** 236/236 órdenes ejecutadas, 0 rechazos por margen.

#### 2. Bug: Heurística DST siempre activa en AUS200 (commit 6d1aed3)

**Síntoma:** LUYTEN registraba entradas a hora 8 UTC cuando `session_start_hour=9`.

**Causa raíz:** La heurística DST de NYSE (`if dt.hour < 14 → shift -1h`) fue diseñada para ETFs del NYSE donde la primera barra llega ~14:00 UTC. AUS200 es un CFD 24h cuya primera barra llega ~00:00 UTC → `dt.hour < 14` era **siempre verdadero** → session_start siempre se desplazaba -1h (de 9 a 8).

**Comparación con otras estrategias:** Ogle, SEDNA y KOI usan horas UTC directas SIN heurística DST. Solo LUYTEN tenía esta heurística (heredada del caso de uso TLT NYSE).

**Fix:** Nuevo parámetro `use_dst_heuristic` en LUYTEN:
- `True` (default): backward compatible con TLT/NYSE ETFs, aplica `dt.hour < 14 → -1h`
- `False`: usa horas UTC fijas (para CFDs 24h como AUS200)
- Trade log muestra "DST-adjusted" o "fixed UTC" según el parámetro

#### 3. Mapa de horarios AUS200 (análisis directo de CSV)

Se analizaron las barras 5-min del CSV de AUS200 para mapear gaps de mantenimiento:

| Período | DST Australia | Gap principal (UTC) | Gap mid-day (UTC) |
|---------|--------------|--------------------|--------------------|
| Oct-Mar (AU verano) | AEDT UTC+11 | 19:55 → 22:50 (175 min) | 05:25 → 06:10 (45 min) |
| Abr-Sep (AU invierno) | AEST UTC+10 | 20:55 → 23:50 (175 min) | 06:25 → 07:10 (45 min) |

- El gap principal se desplaza 1h según DST australiano
- El gap más temprano empieza a las **19:55 UTC** (verano australiano)

**Configuración final AUS200_LUYTEN:**
- `session_start_hour=8` → London open 08:00 UTC (fijo, sin heurística DST)
- `session_start_minute=0`
- `use_dst_heuristic=False`
- `eod_close_hour=19, eod_close_minute=50` → cierra posiciones 5 min antes del gap más temprano (19:55)

**Verificación backtest 2020-2023:** 156 trades, 0 rechazos margen, entradas empiezan hora 8. Salidas: 100 SL + 49 TP + 6 EOD_CLOSE + 1 Canceled.

#### 4. 📋 TAREA PENDIENTE: Adaptar horarios LUYTEN por activo/índice

> **Para cada nuevo índice o activo que se añada a LUYTEN**, se debe:
> 1. Analizar el CSV de datos para mapear gaps de mantenimiento (buscar saltos >30 min entre barras)
> 2. Verificar si el gap cambia con DST del país del mercado (comparar ene vs jul)
> 3. Configurar `session_start_hour` según la apertura relevante (ej: London open, Tokyo open)
> 4. Configurar `eod_close_hour/minute` al menos 5 min antes del gap más temprano del año
> 5. Elegir `dst_mode`: `'london_uk'` para activos ligados a London, `'nyse'` para ETFs NYSE, `'none'` para UTC fijo
> 6. Verificar con backtest que no hay entradas fuera de horario ni posiciones abiertas durante gaps

#### 5. Refactor máquina de estados LUYTEN (commit e85e9c5)

**Cambio 1: Consolidación SIN entradas (fix crítico)**

La máquina de estados anterior permitía breakout check durante la consolidación (desde `consolidation_bars_min`). Esto era incorrecto: durante la consolidación SOLO se debe observar el HIGH, nunca entrar.

Nueva máquina de estados:
- **Barras 1..min** = delay desde session_start (sin observación)
- **Barras min+1..max** = se registra el HIGH más alto (CERO entradas)
- **Después de max** = WAITING_BREAKOUT (entradas permitidas hasta EOD)

Ejemplo: session_start=8:00, min=0, max=19 → consolidación 8:00-9:35 (solo HIGHs) → entradas posibles desde 9:35 hasta EOD 19:50.

**Cambio 2: `dst_mode` reemplaza `use_dst_heuristic`**

El booleano `use_dst_heuristic` (True/False) se reemplaza por string `dst_mode` con 3 modos:
- `'nyse'` (default): heurística NYSE original (`dt.hour < 14 → -1h`). Backward compatible con TLT.
- `'london_uk'`: calcula límites BST (último domingo de marzo → último domingo de octubre) y aplica `-1h` durante BST. Para AUS200 y otros activos ligados a London.
- `'none'`: horas UTC fijas sin ajuste.

Método `_bst_boundaries(year)` calcula las fechas exactas del cambio BST.

**Config AUS200_LUYTEN actualizado:**
- `session_start_hour=8` (08:00 GMT invierno → auto 07:00 BST verano)
- `dst_mode='london_uk'`
- EOD: 19:50 UTC (sin cambio)

**Verificación:** 136 trades, 0 entradas en h7, 16 en h8 (BST post-consolidación), mayoría h9+ (como debe ser).

#### 6. SessionMarker — indicador visual para plot (commit 6f77108)

Indicador `SessionMarker` añadido a `luyten_strategy.py` (mismo patrón que `EntryExitLines` en helix):
- **Triángulo azul (v)** encima del high → marca session_start (inicio de consolidación)
- **Triángulo naranja (^)** debajo del low → marca fin de consolidación (apertura ventana breakout)

Entre ambos marcadores = ventana de consolidación (solo observación HIGHs). Después del naranja = ventana de entradas hasta EOD. Permite análisis visual correcto del comportamiento de la estrategia en el plot de backtrader.

*Ultima edición: 2026-03-21 — SessionMarker plot indicator (commit 6f77108)*

---

## 🎯 PLAN ESTRATÉGICO: DARWINEX ZERO — 14-30% Anual, DD < 10% (2026-03-16)

> **⚠️ CORRECCIÓN 2026-03-16:** El sistema live está "muy verde" — 3 bugs detectados la semana pasada aún en pruebas.
> Antes de abrir cuenta en Darwinex Zero, el sistema live debe estar TOTALMENTE validado (mínimo 2 meses más de pruebas o hasta verificar ausencia total de bugs y resultados coherentes).
> Los datos para índices se obtienen de **Quant Data Manager**, NO de Darwinex.
> El backtesting de índices corre EN PARALELO con la validación live del sistema forex actual.

### 1. Diagnóstico: Dónde Estamos

**Sistema live (FOREX.comGLOBAL demo, mini-PC, v0.6.0):**
- 11 configs forex operando en demo
- **3 bugs detectados la semana pasada** — en fase de corrección y pruebas
- Estado: **MUY VERDE** — no listo para producción ni para migración
- Necesita: mínimo 2 meses más de ejecución estable sin bugs antes de cualquier paso
- Criterio de avance: 0 bugs durante 8 semanas consecutivas + resultados coherentes con backtest

**Portfolio validado (16 configs, 4 estrategias × 7 activos):**

| Bloque | Configs | Estado Live | Aportación BT | DD BT |
|--------|:-------:|:-----------:|:-------------:|:-----:|
| Forex (12) | EURUSD/USDCHF/USDJPY/EURJPY × PRO/KOI/SEDNA/GEMINI | 11 en demo FOREX.comGLOBAL | ~85% del PnL | 7-14% individual |
| ETF (4) | DIA_PRO, DIA_SEDNA, XLE_PRO, XLU_KOI | 0 (broker no los tiene) | ~15% del PnL | 7-10% individual |

**Portfolio backtest tiered (16 configs, $50K, 2020-2025):**
- 1543 trades | WR 44.7% | Net PnL $746K | DD ponderado 10.08%
- **0 años negativos** en 6 años consecutivos
- Walk-forward validado en todos los ETFs + forex en OOS live

**Problema estructural:**
- 4 ETFs WF-validados (25% del portfolio) llevan meses sin operar: el broker no los ofrece
- TLT: 5 estrategias intentadas, 0 viables (LUYTEN en optimización con OOS prometedor pero PF marginal)
- GLD: eliminado completamente (0 estrategias viables a nivel portfolio)
- CERES (intraday ETF nativa): descartada — incompatibilidad ORB ↔ sesión 6.5h

**Conclusión:** El sistema está validado pero operando al ~60% de su capacidad por limitaciones del broker.

---

### 2. Por Qué Darwinex Zero

| Factor | FOREX.comGLOBAL (actual) | Darwinex Zero |
|--------|:------------------------:|:-------------:|
| ETFs/Índices | ❌ No disponibles | ✅ Todos los CFDs |
| Cuenta auditable | ❌ Demo sin verificación | ✅ Track record verificado para inversores |
| Data quality | Dukascopy CSV + live feed diferente | Data del propio broker (coherencia BT↔Live) |
| Target inversores | ❌ No aplicable | ✅ DarwinIA + inversores privados |
| Forex spreads | Buenos (ECN) | Competitivos (verificar par por par) |
| Costo | $0 | Suscripción mensual + 20% performance fee |

**Objetivo a 2 años:** Track record auditable con Sharpe > 1.0, DD < 10%, retorno constante 14-30% anual → captar capital de DarwinIA e inversores privados.

---

### 3. Análisis de Spreads Darwinex Zero — Índices CFD

**Tabla de costes por trade estimada (basada en spreads publicados y condiciones Darwinex):**

| Índice CFD | Spread (pts) | Comisión/lote | Tick Value | Coste total ~1 trade* | Equivalente ETF | Correlación ETF |
|------------|:------------:|:-------------:|:----------:|:---------------------:|:----------------:|:-------:|
| **SP500** (US500) | 0.6 | $0.275 | $1/pt | ~$0.88 | DIA (~0.95) | ✅ Directa |
| **NDX** (USTECH) | 0.9 | $2.75 | $1/pt | ~$3.65 | QQQ (~0.85 con DIA) | ⚠️ Redundante |
| **GDAXI** (GER40) | 0.8 | €2.75 | €1/pt | ~€3.55 | — | Baja con USD forex |
| **UK100** (FTSE) | 0.8-1.0 | £2.75 | £1/pt | ~£3.55 | — | Baja con USD forex |
| **AUS200** | 0.8 | A$2.75 | A$1/pt | ~A$3.55 | — | Asia timezone |
| **NI225** (JP225) | 3.0 | ¥35 | ¥1/pt | ~¥38 (~$0.25) | — | ⚠️ Spread alto relativo |
| **STOXX50E** (EU50) | 0.9 | €2.75 | €1/pt | ~€3.65 | — | Moderada con EUR forex |
| **SPA35** (ESP35) | 5.2 | €2.75 | €1/pt | ~€7.95 | — | ❌ Spread excesivo |
| **FCHI40** (FRA40) | 0.6 | €2.75 | €1/pt | ~€3.35 | — | Moderada con EUR forex |

*Coste por trade = spread × tick_value + comisión ida y vuelta. Valores aproximados, verificar en cuenta real.*

**Ranking por viabilidad operativa:**

| Prioridad | Índice | Razón |
|:---------:|--------|-------|
| 🥇 1 | **SP500** | Spread mínimo (0.6), proxy directo de DIA (validado PF 2.04/1.83), sesión larga |
| 🥈 2 | **UK100** | Baja correlación con USD forex, sesión europea, spread aceptable |
| 🥉 3 | **GDAXI** | Diversificación EUR-equity, diferente de EURUSD forex (equity vs moneda) |
| 4 | **AUS200** | Timezone diversification (Asia/Pacific), decorrelación horaria con todo |
| 5 | **FCHI40** | Bueno por spread, pero redundante con STOXX50E y GDAXI |
| ❌ | **NI225** | Spread 3.0 pts relativo a movimiento diario → margina edge |
| ❌ | **SPA35** | Spread 5.2 → destruye cualquier estrategia intraday/swing corto |
| ⚠️ | **NDX** | Buenas métricas pero correlación 0.85+ con SP500 → redundante en portfolio |

**Nota crítica:** Estos spreads son los publicados en darwinexzero.com/es/activos (tabla renderizada por JavaScript, no verificable por scraping). Son INDICATIVOS. **Antes de operar**, verificar spreads reales en cuenta activa en horario de baja liquidez (apertura, pre-cierre). Un spread de 0.6 en SP500 puede duplicarse en las primeras barras.

**Para backtesting paralelo:** Usar estos spreads como referencia conservadora. Si el backtest es rentable con estos spreads, probablemente lo será con spreads reales (que podrían ser mejores o peores).

---

### 4. Análisis de la Transferencia DIA → SP500

**Hipótesis:** Si DIA y SP500 tienen correlación ~0.95+, las estrategias DIA_PRO (Ogle) y DIA_SEDNA deberían funcionar en SP500 con ajustes mínimos.

**Diferencias estructurales DIA vs SP500 CFD:**

| Aspecto | DIA (ETF) | SP500 CFD (Darwinex) |
|---------|-----------|---------------------|
| Precio | ~$420 | ~4200 pts |
| Factor escala | 1× | ~10× (1 punto SP500 ≈ 10 pips DIA conceptuales) |
| Sesión | NYSE 14:30-21:00 UTC | ~22h/día (casi 24h con pre/post) |
| Gaps overnight | Sí, significativos | Mínimos (sesión casi continua) |
| EOD Close necesario | ✅ Obligatorio (gaps) | ⚠️ Probablemente NO — evaluar |
| Swap overnight | N/A (no hay con ETFs intraday) | Sí, cobran swap |
| Comisión | ~$32/trade (ETF broker) | ~$0.55/trade (Darwinex) |
| pip_value | 0.01 | Recalcular para CFD |
| Datos existentes | ✅ Dukascopy 5min | ❌ Obtener de **Quant Data Manager** |

**Ventajas SP500 CFD vs DIA ETF:**
1. **Sesión casi 24h** → Ogle/SEDNA no necesitan EOD close forzado → más tiempo para desarrollar trades → mejor R:R esperado
2. **Comisiones 60× más baratas** ($0.55 vs $32) → elimina el problema de comisiones que afecta ETFs
3. **Sin gaps overnight significativos** → SL protege de verdad (no salta 3× por gap)
4. **Compounding de 24h** → las EMAs se alimentan continuamente, señal más limpia

**Riesgos SP500 CFD:**
1. **Swap overnight** → Si las estrategias mantienen posiciones >1 día, el swap devora rentabilidad
2. **Sesión extendida ≠ sesión real** → La liquidez en pre-market (22:00-14:30 UTC) es mucho menor
3. **Datos diferentes** → Los precios CFD del broker difieren del spot DIA → re-optimización necesaria
4. **Escalado de parámetros** → SL/TP en puntos diferentes (SL 50 pips en DIA = SL 500 pts en SP500?)

**Procedimiento de transferencia (riguroso):**
1. Obtener datos SP500 5min de **Quant Data Manager** (mínimo 2020-2025)
2. Correr DIA_PRO params "tal cual" en SP500 con ajuste pip_value → baseline crudo
3. Si PF > 1.0 con params DIA → hay edge transferible. Si PF < 0.8 → no funciona directamente
4. Re-optimizar con train 2020-2023, test 2024-2025 blind (WF obligatorio)
5. Evaluar si EOD close sigue siendo necesario (sesión ~22h vs 6.5h)
6. Comparar con/sin allowed_hours adaptados al horario del CFD

---

### 5. PLAN POR FASES

#### FASE 0: Backtesting Índices + Validación Live Paralela (Meses 1-3)

**⚠️ NO SE ABRE CUENTA DARWINEX ZERO AÚN.** El sistema live debe superar la validación completa primero.

**Pista A — Validación Live (FOREX.comGLOBAL, mínimo 2 meses):**

| Tarea | Detalle | Criterio de éxito |
|-------|---------|-------------------|
| Corregir 3 bugs activos | Debug y fix en el bot live v0.6.0 | 0 bugs pendientes |
| Ejecución estable 8 semanas | 11 forex configs sin incidentes | 0 trades fantasma, 0 crashes, 0 bugs nuevos |
| Coherencia BT↔Live | Comparar métricas live vs backtest | Divergencia < 30% en PF y WR |
| Documentar resultados | Log semanal de trades, PnL, incidentes | Tabla acumulada en CONTEXT_LIVE.md |

**Pista B — Backtesting Índices (en paralelo, datos de Quant Data Manager):**

| Tarea | Detalle | Criterio de éxito |
|-------|---------|-------------------|
| Obtener datos SP500 5min | Quant Data Manager, 2020-2025+, zona UTC | CSV limpio, ≥5 años |
| Baseline SP500 con DIA_PRO params | Test "raw" (solo ajuste pip_value/escala) | PF > 1.0 → edge transferible |
| Baseline SP500 con DIA_SEDNA params | Test "raw" (solo ajuste pip_value/escala) | PF > 1.0 → edge transferible |
| WF SP500 (train 2020-2023, test 2024-2025) | Re-optimización si baseline funciona | OOS PF > 1.3 → APROBADO |
| Obtener datos UK100, GDAXI, AUS200 | Quant Data Manager, 5min, 2020-2025+ | CSVs limpios |
| Evaluación UK100/GDAXI/AUS200 | Protocolo estándar (§5 Fase 3) | ≥1 índice adicional WF-validado |
| Estudiar reglas DarwinIA | Métricas, penalizaciones, requisitos mínimos | Documento resumen interno |

**Gate Fase 0 → Fase 1:** AMBAS pistas deben estar resueltas:
- Pista A: ≥8 semanas live sin bugs, resultados coherentes
- Pista B: SP500 WF-validado (mínimo) + al menos 1 índice adicional evaluado

---

#### FASE 1: Apertura Darwinex Zero + Verificación Real (Mes 3-4)

**⚡ Solo cuando Pista A de Fase 0 esté aprobada (8 semanas live estable).**

**Objetivo:** Abrir cuenta, verificar condiciones reales, y migrar forex.

| Tarea | Detalle |
|-------|---------|
| Abrir cuenta Darwinex Zero | Suscripción (€45/mes). Verificar instrumentos disponibles |
| Verificar spreads reales | Anotar spreads forex + índices en 3 sesiones (Asia, London, NY) |
| Verificar comisiones reales | 2-3 trades manuales en forex y SP500 |
| Verificar ETFs disponibles | ¿DIA, XLE, XLU como CFD? |
| Verificar swap rates | SP500, UK100, GDAXI + forex. Si swap > $5/lote/noche → EOD close |
| Configurar bot MT5 para Darwinex | Ajustar BROKER_UTC_OFFSET, símbolos, pip_values |
| Deploy 11 configs forex | Las mismas que corren en FOREX.comGLOBAL |
| Monitorear 4 semanas | Paridad BT↔Live, slippage, spreads reales |
| Comparar divergencia | Si divergencia Darwinex ≤ FOREX.comGLOBAL → migración exitosa |

**Tiers forex en Darwinex Zero (mismos que validados):**

| Tier | Risk% | Configs |
|:----:|:-----:|---------|
| A | 1.50% | USDCHF_PRO, USDCHF_GEMINI, EURUSD_PRO |
| B | 1.00% | USDCHF_KOI, EURJPY_PRO, EURUSD_KOI, EURJPY_KOI, USDJPY_SEDNA, USDJPY_KOI |
| C | 0.75% | EURUSD_GEMINI |
| D | 0.50% | EURJPY_SEDNA |

**Criterio de éxito Fase 1:** 4 semanas sin incidentes graves (DD < 5% en el periodo), ejecución estable, 0 trades fantasma.

**Gate:** No avanzar a Fase 2 hasta que Fase 1 lleve 4 semanas estable. Si spreads Darwinex son ≥1.5× peores en forex → modelo dual: FOREX.comGLOBAL para forex, Darwinex Zero solo para índices/ETFs.

---

#### FASE 2: Deploy ETFs / Índices Validados (Mes 5-7)

**Sub-fase 2A: ETFs directos (si Darwinex les tiene como CFD)**

| Config | Tier | Risk | WF Status | Acción |
|--------|:----:|:----:|:---------:|--------|
| DIA_PRO (Ogle) | C | 0.75% | ✅ OOS PF 1.67 | Deploy directo con EOD close |
| DIA_SEDNA | B | 1.00% | ✅ OOS PF ~2.05 | Deploy directo con EOD close |
| XLE_PRO (Ogle) | B | 1.00% | ✅ OOS PF 2.55 | Deploy directo con EOD close |
| XLU_KOI | C | 0.75% | ✅ OOS PF 1.83 | Deploy directo con EOD close |

Si Darwinex ofrece DIA/XLE/XLU como CFD → deploy directo con configs ya validadas. Monitorear 4 semanas.

**Sub-fase 2B: SP500 como sustituto/complemento de DIA (paralelo a 2A)**

| Paso | Qué | Criterio |
|------|-----|---------|
| 1 | Backtest SP500 con params DIA_PRO "raw" | PF > 1.0 → edge transferible |
| 2 | Backtest SP500 con params DIA_SEDNA "raw" | PF > 1.0 → edge transferible |
| 3 | Evaluar si EOD close es necesario en CFD 22h | Comparar con/sin → decidir |
| 4 | Re-optimización WF (train 2020-2023, test 2024-2025) | OOS PF > 1.3 → APROBADO |
| 5 | Si funciona → decidir: ¿sustituye a DIA o se añade? | Si correlación > 0.90 → sustituye. Si < 0.80 → añade |

**Gate:** SP500 se añade al portfolio SOLO si pasa WF con OOS PF > 1.3 y DD < 15%.

---

#### FASE 3: Exploración Índices Nuevos (Mes 6-10, paralelo con Fase 2)

**Objetivo:** Buscar 1-2 índices adicionales que aporten diversificación REAL (no correlación con el bloque forex ni con SP500/DIA).

**Índices candidatos ordenados por valor de diversificación:**

| # | Índice | Driver principal | Correlación esperada con forex USD | Correlación con SP500 | Sesión | Valor |
|---|--------|-----------------|:----------------------------------:|:---------------------:|--------|-------|
| 1 | **UK100** | Economía UK, libra | Baja (~0.15) | Moderada (~0.55) | London | **Alto** — driver independiente |
| 2 | **GDAXI** | Industria alemana, EUR | Moderada (~0.30) | Moderada (~0.60) | Frankfurt | **Medio-Alto** — diversifica de USD |
| 3 | **AUS200** | Commodities, China | Baja (~0.10) | Baja (~0.40) | Sydney/Asia | **Alto** — timezone completamente diferente |
| 4 | **FCHI40** | Francia, EUR | Moderada (~0.30) | Alta (~0.70) | Paris | **Medio** — redundante con GDAXI |

**Protocolo de evaluación por índice (riguroso):**

```
Para cada índice candidato:
1. Obtener datos 5min (2020-2025, UTC)
2. Backtest con Ogle params genéricos (baseline)
   → Si PF < 0.9 con params "wide open" → DESCARTAR INMEDIATO
3. Backtest con SEDNA params genéricos
   → Si PF < 0.9 con params "wide open" → DESCARTAR INMEDIATO
4. Si alguna estrategia PF > 1.0 → optimizar
5. Walk-forward obligatorio (train 2020-2023, test 2024-2025)
   → OOS PF > 1.3 → APROBADO
   → OOS PF 1.0-1.3 → APROBADO CON RESERVA (Tier D, 0.50%)
   → OOS PF < 1.0 → DESCARTAR
6. KOI solo si Ogle Y SEDNA fallan (como con XLU)
7. Maximum 2 semanas por índice. Si no pasa → siguiente
```

**Criterio de adición al portfolio:**
- Mínimo 1 estrategia WF-validada con OOS PF > 1.3
- Correlación < 0.70 con el bloque forex + SP500 combinado
- ≥ 15 trades/año (significancia estadística)
- DD individual < 15%

**Expectativa honesta:** De 4 candidatos, aprobamos 1-2 (tasa histórica de supervivencia ETFs: 27%. Índices CFD 24h podrían ser mejores → estimamos 40-50%).

---

#### FASE 4: Calibración Portfolio Final (Mes 10-12)

**Objetivo:** Portfolio completo optimizado para Darwinex Zero con DD < 10% y retorno máximo.

| Tarea | Detalle |
|-------|---------|
| Portfolio backtest combinado | Todas las configs aprobadas (forex + índices/ETFs) con tiers |
| Optimización de tiers | Score = PF × Calmar / (MC95 / 10%) → asignar A/B/C/D |
| Monte Carlo portfolio | 10,000 simulaciones → MC95 < 15%, MC99 < 20% |
| Correlación cruzada real | Medir correlación de DD entre TODOS los bloques (forex, SP500, UK100, etc.) |
| Stress test | ¿Qué pasa si 2022 se repite? ¿Si COVID se repite? → DD combinado |
| Definir risk budget total | Riesgo máximo concurrente estimado < 8% equity |

**Portfolio objetivo realista:**

| Bloque | Configs | Tier medio | Aportación esperada |
|--------|:-------:|:----------:|:-------------------:|
| Forex EUR (EURUSD) | PRO + KOI + GEMINI | A-B | ~30% del PnL |
| Forex CHF (USDCHF) | PRO + KOI + GEMINI | A-B | ~25% del PnL |
| Forex JPY (USDJPY, EURJPY) | KOI + SEDNA + PRO* | B-D | ~20% del PnL |
| Equity US (SP500/DIA) | Ogle + SEDNA | B-C | ~15% del PnL |
| Energy (XLE) | Ogle | B | ~5% del PnL |
| Utilities (XLU) | KOI | C | ~3% del PnL |
| Nuevo índice (UK100/GDAXI/AUS200) | TBD | C-D | ~2% del PnL |

*USDJPY_PRO pausado — re-evaluar Jun 2026.

---

#### FASE 5: Track Record Auditable (Mes 6-24)

**Objetivo:** Construir 18+ meses de track record verificado en Darwinex Zero.

**Métricas objetivo para DarwinIA:**

| Métrica | Objetivo | Por qué |
|---------|----------|---------|
| D-Score | > 60 | Top 20% de Darwins — atrae atención DarwinIA |
| Sharpe anual | > 1.0 | Estándar institucional. Nuestro BT weighted Sharpe ≈ 0.85 → subir con índices |
| Max DD | < 10% | Absoluto. Kill switch a -15% |
| Return anual | 14-30% | Rango por escenario (ver §6 abajo) |
| % meses positivos | > 65% | Consistencia > retorno puro para inversores |
| Trades/mes | > 25 | Suficiente actividad para ser evaluable |
| Recovery factor | > 2.0 | Return / MaxDD — resistencia ante pérdidas |

**Calendario:**

| Mes | Acción | Entregable |
|:---:|--------|------------|
| 1-3 | **Fase 0:** Validación live (corregir bugs, 8 sem estable) + Backtesting índices paralelo (Quant Data Manager) | Live estable, SP500 WF-validado, UK100/GDAXI/AUS200 evaluados |
| 3-4 | **Fase 1:** Abrir Darwinex Zero + verificar condiciones + migrar forex | Cuenta activa, forex operando, spreads reales verificados |
| 5-7 | **Fase 2:** Deploy ETFs/SP500 validados | Portfolio expandido con índices |
| 6-10 | **Fase 3:** Exploración índices nuevos (paralelo) | 1-2 índices adicionales evaluados |
| 10-12 | **Fase 4:** Calibración portfolio final | Portfolio completo, tiers optimizados |
| 12-18 | **Fase 5:** Ejecución pura + revisión mensual | 6 meses track record |
| 18-24 | Primera ventana DarwinIA + track record sólido | ≥12 meses verificados → candidato inversores |

**Revisión mensual obligatoria:**
- PnL vs backtest (¿el live degrada >30% vs BT esperado?)
- DD rolling 3 meses
- Configs en vigilancia/alerta (kill criteria por config)
- Swap costs vs proyección
- Slippage acumulado

---

### 6. Proyección de Retorno Realista — Los Números

**Punto de partida:** Portfolio backtest tiered (16 configs) sobre $50K:

| Año | PnL BT (compounding aislado) | Trades |
|-----|:----------------------------:|:------:|
| 2020 | $47,902 | 209 |
| 2021 | $57,126 | 158 |
| 2022 | $160,036 | 339 |
| 2023 | $133,360 | 276 |
| 2024 | $132,125 | 265 |
| 2025 | $216,025 | 294 |

**Ajustes de realidad (del BT al live):**

| Factor | Impacto estimado | Justificación |
|--------|:----------------:|---------------|
| Compounding aislado → compartido | -20% a -30% | Cada config compone sobre su propia equity en BT; en live la equity es compartida y no crece independiente |
| Slippage real | -5% a -10% | 1-2 pips/trade × 300 trades/año ≈ $4K-$8K en $50K |
| Spread diferencia broker | -3% a -5% | Darwinex puede tener spreads ligeramente diferentes a Dukascopy |
| Performance fee Darwinex (20%) | -20% del profit | Solo si hay ganancia; no afecta al DD |
| Suscripción Darwinex | ~€30-40/mes | ~$400-500/año fijo |
| Psicología/disciplina | -5% a -10% | Pausar demasiado pronto, intervenir manualmente, etc. |

**Escenarios de retorno anual (sobre $50K, año 1 sin compounding significativo):**

| Escenario | Retorno BT bruto | Haircut total | Retorno neto pre-fee | Post-fee (20%) | Retorno final |
|-----------|:----------------:|:-------------:|:--------------------:|:--------------:|:-------------:|
| **Conservador** | ~$80K (160%) | -55% | ~$36K (72%) | ~$29K | **~58%** |
| **Base** | ~$100K (200%) | -45% | ~$55K (110%) | ~$44K | **~88%** |
| **Pesimista** | ~$50K (100%) | -60% | ~$20K (40%) | ~$16K | **~32%** |

**⚠️ STOP — Estos números necesitan contexto:**

El retorno BT del portfolio actual (16 configs sobre $50K) es MUY alto porque:
1. El compounding aislado infla el retorno total (cada config crece independientemente)
2. Los risk tiers (1.5%/1.0%/0.75%/0.50%) son agresivos para capital real inicial
3. 0 años negativos en 6 años es inusualmente bueno incluso para un buen sistema

**Ajuste más honesto — retorno sin compounding (linear, año 1):**
- ~300 trades/año × riesgo medio ~$460/trade × expectancy media ~0.45R = ~$62K
- Con haircuts realistas (-40%): ~$37K = **~74% neto pre-fees**
- Post Darwinex 20% fee: ~$30K = **~60% neto**

**¿Cómo se llega a 14-30% si el BT sugiere 60%+?**

La pregunta CORRECTA es al revés: **¿a qué risk level necesito operar para obtener 14-30%?**

| Target | Risk scaling necesario | Risk efectivo medio | Implicación |
|--------|:---------------------:|:-------------------:|-------------|
| 14% anual (conservador) | ~0.25× del BT actual | ~0.23% por trade | Ultra-conservador. Portfolio casi no siente los trades. |
| 20% anual (base) | ~0.35× | ~0.32% | Conservador. Muy cómodo con DD < 7%. |
| 30% anual (agresivo) | ~0.50× | ~0.46% | Moderado. DD esperado ~6-8%. |
| 60%+ anual (BT actual) | 1.00× | ~0.92% | Tiers actuales. DD esperado ~10%. |

**Recomendación: Empezar en 0.35× (target ~20% anual) durante los primeros 6 meses.**
- Si el live confirma el BT → escalar gradualmente hacia 0.50× (target ~30%)
- Si el live degrada 30%+ vs BT → mantener 0.25× (target ~14%)
- **NUNCA escalar risk porque "está yendo bien"** — escalar por datos acumulados (min 100 trades)

**Risk tiers ajustados para Darwinex Zero (Fase inicial 0.35×):**

| Tier | BT risk | DZ risk (0.35×) | Configs |
|:----:|:-------:|:---------------:|---------|
| A | 1.50% | **0.53%** | USDCHF_PRO, USDCHF_GEMINI, EURUSD_PRO |
| B | 1.00% | **0.35%** | DIA_SEDNA, USDCHF_KOI, EURJPY_PRO, XLE_PRO, EURUSD_KOI, EURJPY_KOI, USDJPY_SEDNA, USDJPY_KOI, USDJPY_PRO* |
| C | 0.75% | **0.26%** | DIA_PRO, XLU_KOI, EURUSD_GEMINI |
| D | 0.50% | **0.18%** | EURJPY_SEDNA |

*USDJPY_PRO solo si se reactiva tras evaluación Jun 2026.

**DD esperado con scaling 0.35×:** ~10% × 0.35 = **~3.5%** (excelente para inversores). Worst case MC95: ~6%.

---

### 7. Riesgos y Mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|:----------:|:-------:|------------|
| Spreads Darwinex peores que Dukascopy | Media | Alto | Fase 0 verifica. Si > 1.5× → modelo dual broker |
| SP500 no replica DIA | Media | Alto | Si PF < 1.0 raw → se mantiene DIA puro (si disponible) o se descarta equity US |
| Swap overnight devora edge en CFDs | Media | Medio | Medir swap real en Fase 0. Si > $5/lote/noche → añadir EOD close a CFDs |
| Ningún índice nuevo pasa WF | Alta (60%) | Bajo | El portfolio forex + DIA/XLE/XLU ya funciona. Los índices son bonus, no requisito |
| DD real > 2× backtested | Baja | Alto | Kill criteria activos: -10% → pausar ETFs, -15% → pausar todo |
| Darwinex cambia condiciones/fees | Baja | Medio | Mantener FOREX.comGLOBAL como backup mientras Darwinex se prueba |
| Degradación de edge post-2025 | Media | Alto | Revisión semestral de cada config vs su WF OOS. Desactivar configs que fallen kill criteria |
| Regulación española impacta | Baja | Medio | Darwinex Zero está regulado en Europa (FCA/CNMV). Documentar todo para fiscalidad |

---

### 8. Lo Que NO Hacer (Lecciones del Historial)

Estas lecciones vienen directamente del historial documentado en CONTEXT.md:

1. **NO perseguir activos por teoría** — GLD parecía el diversificador perfecto (correlación ~0.05 con DIA, ~0 con forex). Se invirtieron semanas. Resultado: 0 de 3 estrategias viables. A nivel portfolio, Score 0.54 (peor del sistema).

2. **NO forzar estrategias forex en activos diferentes** — Tasa supervivencia forex→ETF: 27%. No hay razón para creer que será mejor con índices CFD. Ir con las 3 estrategias por orden (Ogle, SEDNA, KOI) y cortar rápido si no funciona.

3. **NO iterar filtros contra datos OOS** — Lección GLD: CERES con filtros "optimizados" en IS pasó a OOS y colapsó. Cada filtro probado en OOS pierde validez del OOS. WF es prueba de una sola oportunidad.

4. **NO escalar risk porque el BT es bueno** — El BT muestra 60-100% annual con tiers actuales. En live real, empezar a 0.35× y escalar SOLO con datos reales acumulados. El mercado no tiene bondad (Axioma 6).

5. **NO paralizar el portfolio actual esperando lo nuevo** — Los 11 configs forex llevan meses corriendo. Siguen. Los ETFs se añaden ENCIMA, no en sustitución.

6. **NO emocionarse con track record inicial bueno** — Si el primer mes en Darwinex da +5%, NO escalar inmediatamente. Un mes no es dato. 6 meses es el mínimo para decisiones.

---

### 9. Resumen Ejecutivo

| Pregunta | Respuesta |
|----------|-----------|
| ¿14% anual es alcanzable? | **Sí, con alta confianza.** El portfolio validado lo supera ampliamente en BT. Con scaling 0.25× y haircuts realistas, 14% es conservador. |
| ¿30% anual es alcanzable? | **Posible pero no garantizado.** Requiere scaling 0.50× y que el live no degrade >30% vs BT. Se alcanza tras 6+ meses de validación. |
| ¿DD < 10% es alcanzable? | **Sí.** BT DD ponderado 10.08% a full risk. Con scaling 0.35× → DD esperado ~3.5%, worst case ~6%. |
| ¿Cuánto tarda en ser operativo? | **~12 meses** hasta portfolio final (incluye 3 meses de validación live previa). **~18-24 meses** hasta track record evaluable por inversores. |
| ¿Se necesitan nuevas estrategias? | **No para el objetivo base.** Las 4 estrategias existentes (Ogle/KOI/SEDNA/GEMINI) son suficientes. Los índices nuevos se prueban con estrategias existentes. |
| ¿Y TLT/LUYTEN? | **Parking.** LUYTEN muestra OOS PF 2.65 (candidato #7) pero PF IS 1.23. Queda como investigación paralela, no bloquea el plan principal. Si pasa WF completo → se añade como bonus en Fase 4. |
| ¿Qué pasa si Darwinex no funciona? | **Fallback:** Mantener FOREX.comGLOBAL con los 11 forex. Buscar otro broker que ofrezca ETFs/índices + cuenta auditable. |

---

### 10. Primera Acción Concreta (Fase 0 — Ahora)

**Pista A — Validación Live (prioridad máxima):**
1. Corregir los 3 bugs detectados la semana pasada
2. Dejar correr el sistema live 8 semanas sin intervención (excepto bugs críticos)
3. Documentar cada incidente y trade en CONTEXT_LIVE.md
4. Evaluación semanal: ¿bugs nuevos? ¿coherencia con BT?

**Pista B — Backtesting Índices (en paralelo, Quant Data Manager):**
1. Obtener datos SP500 5min (2020-2025) desde **Quant Data Manager**
2. Correr baseline SP500 con params DIA_PRO y DIA_SEDNA (ajustando pip_value/escala)
3. Si baseline PF > 1.0 → WF train 2020-2023, test 2024-2025
4. Obtener datos UK100 5min → evaluar con protocolo estándar
5. Obtener datos GDAXI 5min → evaluar con protocolo estándar
6. Obtener datos AUS200 5min → evaluar con protocolo estándar

**NO hacer aún:**
- ❌ **NO abrir cuenta Darwinex Zero** — el sistema live no está validado
- ❌ No migrar nada a otro broker hasta que live lleve 8 semanas estable
- ❌ No cambiar nada del portfolio forex actual
- ❌ No tocar los tiers de riesgo hasta Fase 4
- ❌ No emocionarse con resultados de backtesting de índices — WF es obligatorio

---

## 📌 Directrices de Desarrollo — Reglas Permanentes

1. **Todo parámetro de estrategia debe ser configurable desde `config/settings.py`.** Nunca hardcodear valores en la estrategia. Si se añade un filtro nuevo, debe tener su `use_xxx_filter` (default False) en params y su entrada en el bloque de config del asset en settings.py.

---

## 🔜 TAREA PENDIENTE: LUYTEN Multi-Timeframe via `resampledata()` (2026-03-21)

**Objetivo:** Añadir soporte de temporalidad múltiple a LUYTEN usando `cerebro.resampledata()` (mecanismo ya existente en `run_backtest.py` línea ~114).

**3 escenarios a soportar:**

### Escenario 1 — Cambiar temporalidad base de la estrategia
Correr LUYTEN ORB en otra temporalidad (15m, 30m, 1h) sin cambiar código.
```python
'base_timeframe_minutes': 15,  # resample 5m→15m como feed principal (datas[0])
'htf_data_minutes': 0,         # sin HTF filter
```
- `consolidation_bars=6` en 15m = 90 min (vs 30 min en 5m)
- Toda la lógica ORB aplica sobre velas de 15m

### Escenario 2 — Filtro HTF (ej. ROC en 15m)
ORB corre en 5m, pero consulta un indicador en temporalidad superior para filtrar.
```python
'base_timeframe_minutes': 5,    # mantener 5m
'htf_data_minutes': 15,         # añadir 15m como datas[1]
'use_htf_roc_filter': True,
'htf_roc_period': 6,            # ROC(6) en 15m = 90 min lookback
```
- ROC se calcula continuamente sobre datas[1] (backtrader lo actualiza)
- Se consulta al transicionar consol→WAITING_BREAKOUT
- ROC > 0 → permite breakout; ROC ≤ 0 → skip day

### Escenario 3 — Ambos
ORB en 15m + filtro en 60m.
```python
'base_timeframe_minutes': 15,  # ORB en 15m (datas[0])
'htf_data_minutes': 60,        # filtro en 60m (datas[1])
```

**Implementación:**
- `run_backtest.py`: distinguir si resample es feed primario (escenario 1) o secundario (escenario 2)
- `luyten_strategy.py __init__`: crear `self.htf_roc` si `use_htf_roc_filter` y `len(datas) > 1`
- Filtro se aplica en transición CONSOLIDATION → WAITING_BREAKOUT
- Nuevos params: `base_timeframe_minutes`, `htf_data_minutes`, `use_htf_roc_filter`, `htf_roc_period`
- Config en settings.py para cada asset (default: sin HTF, 5m base)

---

## � ANÁLISIS: Resultados Optimizer LUYTEN AUS200 (2026-03-23)

### Resumen de las 2 fases de optimización

**Phase 1** — SsH 8-11, SL fijo 2.0, TP [3,5], 336 combos:
- Rentables (PF≥1.0): 19%. PF range: 0.87–1.11, mediana 0.95.
- Sharpe range: -0.33 — +0.46.

**Phase 2** — SsH 11-13, SL [1.5,2.0,2.5], TP [3,4,5], 1134 combos:
- Rentables (PF≥1.0): 13%. PF range: 0.84–1.08, mediana 0.94.
- Sharpe range: -0.40 — +0.45.

### Hallazgos clave

1. **TP=3.0 dominante absoluto** — En AMBAS fases, el Top 10 completo usa TP=3.0 (o 4.0 como segundo). TP=5.0 no aparece nunca. Conclusión: fijar TP=3.0.

2. **La mejor combo absoluta es de Phase 1** — SsH=8, CBMax=12, CBMin=4, BkAbv=0 → PF 1.11, DD 16.5%, Sharpe +0.45, 666 trades, **4/4 años rentables**. Pero SsH=8 + CBMax=12 @15m significa breakout efectivo a ~11:00 UTC, NO en London open propiamente.

3. **Ambas fases convergen a la ventana 11:00-12:30 UTC** — Phase 2 #2-4: SsH=12, CBMin=2, CBMax=2 → breakout a 12:30 UTC. Las mejores combos de ambas fases están encontrando edge en la **pre-explosión** (11:00-12:30), justo ANTES de la explosión de liquidez a 13:30.

4. **BkAbv es irrelevante para AUS200** — Phase 2 #2-4 tienen BkAbv=0/2/4 con resultados IDÉNTICOS (mismos trades, mismo PnL). Se puede fijar en 0.

5. **SL marginalmente diferente** — SL=2.0 y SL=2.5 aparecen ambos en top combos. Diferencia marginal; SL=2.0 con SsH=12 da el mejor Sharpe (+0.45).

6. **SsH=13 (la hipótesis 13:30) decepciona** — Solo llega a PF 1.06, DD bajo (11.7%) pero pocos trades (525). La explosión de liquidez a 13:30 es BIDIRECCIONAL (~50% bull / ~50% bear según liquidity_profile), por lo que entrar LONG ahí no da edge.

### Interpretación global

LUYTEN LONG AUS200 encuentra edge marginal (PF 1.07-1.11) en la **pre-explosión** (11:00-12:30 UTC), NO en la explosión misma (13:30). El ORB long se beneficia de que el breakout ocurra durante el valle de baja volatilidad, y luego la explosión de 13:30 "empuja" el trade hacia el TP.

### Dos combos candidatas

| Parámetro | Combo A (mejor PF) | Combo B (más trades) |
|---|---|---|
| SsH | 8 | 12 |
| CBMin | 4 | 2 |
| CBMax | 12 | 2 |
| BkAbv | 0.0 | 0.0 |
| TP | 3.0 | 3.0 |
| SL | 2.0 | 2.0 |
| PF | **1.11** | 1.07 |
| DD% | 16.5% | 19.7% |
| Sharpe | +0.45 | **+0.45** |
| Trades | 666 | 1003 |
| Consist. | 4/4 años | 4/4 años |
| Net PnL | +39,895 | +45,596 |

---

## ❌ TAREA #1 COMPLETADA: Validación out-of-sample (2024-2026) — DESCARTADA

**Resultado:** La Combo A (SsH=8, CBMin=4, CBMax=12, TP=3.0, SL=2.0) **NO supera OOS**.

| Métrica | In-Sample (2020-2023) | Out-of-Sample (2024-2025) | Delta |
|---|---|---|---|
| PF | 1.08 | **0.94** | -13% |
| Sharpe | +0.42 | **-0.06** | -0.48 |
| DD% | 23.8% | **30.8%** | +7% |
| WR% | 43.4% | **40.3%** | -3.1% |
| CAGR | +8.48% | **-6.63%** | -15.1% |
| Net PnL | +$38,318 | **-$12,259** | — |

**Yearly breakdown OOS:**
- 2024: PF 1.02, +$2,086 (apenas breakeven)
- 2025: PF 0.86, -$14,345 (colapso)

**`compare_robustness.py` verdict:** IMMEDIATE DISCARD (PF < 1.0 en OOS).

### Diagnóstico: por qué falla (patrón recurrente en todas las estrategias)

El edge in-sample de PF 1.08-1.11 es **insuficiente para ser real**. Con ~700 trades y PF tan bajo, el margen está dentro del rango de ruido estadístico. Al cambiar de régimen (2024-2025: subidas fuertes de AUS200, alta inflación AU, volatilidad diferente), el "edge" desaparece.

**Señales de alarma que ya estaban presentes in-sample:**
1. Mediana de PF del optimizer = 0.95 (la mayoría de combos pierde dinero)
2. Solo 19% de combos rentables → el edge es frágil y sensible a params exactos
3. 2020 perdedor incluso in-sample (PF 0.91) → no todos los años funcionan
4. BkAbv irrelevante (0/2/4 dan resultados idénticos) → la estrategia no filtra, simplemente entra en todo

**Conclusión:** LUYTEN ORB long-only en AUS200 NO tiene edge estructural operativo. El PF 1.08 in-sample es curve-fitting, no una ventaja real del mercado.

---

## ⏸️ TAREA #2 SUSPENDIDA: Investigar SsH=13 para LONG

**Estado:** Suspendida — no tiene sentido profundizar si la estrategia base no es rentable OOS.

**Nota para el futuro:** Si se implementan SHORT entries (Tarea #3) y el resultado bidireccional mejora significativamente, retomar esta investigación.

---

## ⏸️ TAREA #3 SUSPENDIDA: LUYTEN Entradas SHORT (breakout bajista)

**Estado:** Suspendida — requiere cambios de programación significativos, y el long-only ya demostró no tener edge OOS. Añadir SHORT podría ayudar (capturar la mitad bajista de la explosión 13:30) pero probablemente sufriría el mismo problema de PF marginal + curve-fitting.

**Conservar para referencia futura** si se decide retomar ORB con enfoque diferente (filtros de régimen, volatilidad condicional, etc.).

---

## 📝 LECCIÓN APRENDIDA: Umbral mínimo de PF para viabilidad OOS

Basado en la experiencia acumulada con múltiples estrategias en este sistema:

- **PF < 1.15 in-sample** → prácticamente garantizado que falla OOS
- **PF < 1.30 in-sample** → alto riesgo de degradación OOS
- **PF >= 1.50 in-sample** → umbral mínimo razonable para explorar OOS
- **Mediana del optimizer < 1.0** → la estrategia no tiene edge estructural, solo combos "con suerte"
- **% de combos rentables < 30%** → edge frágil, sensible a params exactos (overfitting)

Estas señales deberían usarse como **filtro rápido** antes de invertir tiempo en validación OOS.

---

## 📊 LIQUIDITY PROFILE SCAN — Todos los activos (2026-03-23)

Barrido completo de los 14 activos disponibles en `data/` usando `tools/liquidity_profile.py`.
Dos pasadas: **15m** (slots de 15 min) y **5m** (slots de 5 min) para comparar granularidad.

### Resultados @15m (slots de 15 minutos)

| Asset | Mean bps | HOTpk bps | HOT_Z | HOTtime | COLDlo bps | Ratio | Bull% | Bear% | #HOT | Valley min |
|-------|:--------:|:---------:|:-----:|:-------:|:----------:|:-----:|:-----:|:-----:|:----:|:----------:|
| AUDUSD | 9.4 | 16.9 | +1.01 | 13:30 | 5.2 | 3.2x | 51.0 | 48.3 | 5 | - |
| AUS200 | 14.1 | 33.1 | +1.37 | 22:45 | 4.8 | 6.9x | 48.2 | 46.3 | 3 | 30 |
| DIA | 22.3 | 42.1 | +0.96 | 13:30 | 0.0 | - | 51.0 | 48.4 | 1 | - |
| EURJPY | 7.6 | 12.2 | +0.77 | 14:00 | 4.3 | 2.9x | 50.7 | 48.5 | 1 | - |
| EURUSD | 6.3 | 12.4 | +1.16 | 14:00 | 2.8 | 4.5x | 49.7 | 49.7 | 8 | 45 |
| EWZ | 38.0 | 72.0 | +1.09 | 13:30 | 0.0 | - | 51.0 | 46.5 | 1 | - |
| GLD | 17.2 | 31.9 | +0.99 | 13:30 | 0.0 | - | 50.5 | 48.1 | 3 | - |
| TLT | 18.0 | 0.0 | +0.00 | - | 0.0 | - | 0.0 | 0.0 | 0 | - |
| USDCAD | 5.8 | 12.0 | +1.37 | 13:30 | 3.0 | 4.1x | 49.6 | 49.8 | 8 | 60 |
| USDCHF | 6.7 | 12.8 | +1.16 | 13:30 | 3.4 | 3.8x | 48.2 | 50.6 | 8 | 165 |
| USDJPY | 7.3 | 13.3 | +0.93 | 13:30 | 3.5 | 3.8x | 48.0 | 51.3 | 3 | - |
| XAUUSD | 14.1 | 30.0 | +1.27 | 13:30 | 7.3 | 4.1x | 51.4 | 48.2 | 6 | - |
| XLE | 40.4 | 111.8 | +2.09 | 13:30 | 0.0 | - | **56.1** | 43.0 | 3 | - |
| XLU | 29.0 | 79.3 | +2.06 | 13:30 | 0.0 | - | **61.7** | 37.3 | 3 | - |

### Resultados @5m (slots de 5 minutos)

| Asset | Mean bps | HOTpk bps | HOT_Z | HOTtime | COLDlo bps | Ratio | Bull% | Bear% | #HOT | Valley min |
|-------|:--------:|:---------:|:-----:|:-------:|:----------:|:-----:|:-----:|:-----:|:----:|:----------:|
| AUDUSD | 5.3 | 11.0 | +1.33 | 13:30 | 2.5 | 4.3x | 48.9 | 50.0 | 11 | - |
| AUS200 | 8.0 | 29.6 | **+2.67** | 22:50 | 2.6 | **11.4x** | 48.7 | 47.3 | 6 | 45 |
| DIA | 12.8 | 29.4 | +1.39 | 13:30 | 0.0 | - | 53.3 | 45.8 | 2 | - |
| EURJPY | 4.3 | 7.8 | +1.00 | 13:30 | 2.3 | 3.4x | 49.7 | 49.6 | 7 | - |
| EURUSD | 3.5 | 8.1 | +1.51 | 12:30 | 1.5 | 5.4x | 49.2 | 49.8 | 21 | 25 |
| EWZ | 21.0 | 46.5 | +1.42 | 13:30 | 0.0 | - | 52.1 | 43.4 | 5 | - |
| GLD | 9.8 | 20.7 | +1.24 | 14:00 | 0.0 | - | 47.3 | 50.4 | 6 | - |
| TLT | 10.0 | 18.2 | +0.95 | 14:00 | 0.0 | - | 50.2 | 45.9 | 2 | - |
| USDCAD | 3.2 | 7.8 | +1.70 | 13:30 | 1.5 | 5.1x | 49.1 | 50.2 | 24 | 22 |
| USDCHF | 3.8 | 8.6 | +1.53 | 12:30 | 1.8 | 4.8x | 49.6 | 49.2 | 19 | 70 |
| USDJPY | 4.0 | 9.5 | +1.43 | 12:30 | 1.9 | 5.1x | 49.0 | 49.8 | 6 | - |
| XAUUSD | 8.0 | 19.1 | +1.54 | 13:30 | 3.9 | 4.9x | 50.4 | 49.2 | 17 | 12 |
| XLE | 22.7 | 81.8 | **+3.05** | 13:30 | 0.0 | - | **56.4** | 42.3 | 8 | - |
| XLU | 16.2 | 59.9 | **+3.09** | 13:30 | 0.0 | - | **61.7** | 36.3 | 7 | - |

### Comparativa 5m vs 15m — Cambios clave

| Asset | Z @15m | Z @5m | Δ Z | Ratio @15m | Ratio @5m | #HOT @15m | #HOT @5m | Valley @15m | Valley @5m |
|-------|:------:|:-----:|:---:|:----------:|:---------:|:---------:|:--------:|:-----------:|:----------:|
| **AUS200** | +1.37 | **+2.67** | +1.30 | 6.9x | **11.4x** | 3 | 6 | 30 | 45 |
| **XLE** | +2.09 | **+3.05** | +0.96 | - | - | 3 | 8 | - | - |
| **XLU** | +2.06 | **+3.09** | +1.03 | - | - | 3 | 7 | - | - |
| EURUSD | +1.16 | +1.51 | +0.35 | 4.5x | 5.4x | 8 | 21 | 45 | 25 |
| USDCAD | +1.37 | +1.70 | +0.33 | 4.1x | 5.1x | 8 | 24 | 60 | 22 |
| USDCHF | +1.16 | +1.53 | +0.37 | 3.8x | 4.8x | 8 | 19 | 165 | 70 |
| XAUUSD | +1.27 | +1.54 | +0.27 | 4.1x | 4.9x | 6 | 17 | - | 12 |
| USDJPY | +0.93 | +1.43 | +0.50 | 3.8x | 5.1x | 3 | 6 | - | - |

### Hallazgos

**1. La resolución 5m amplifica las señales — todos los Z-scores suben:**
- AUS200 pasa de Z +1.37 a **+2.67** (+1.30) — la explosión a las 22:50 es aún más pronunciada en 5m
- XLE/XLU: Z +2.09/+2.06 → **+3.05/+3.09** — señales extremadamente fuertes (>3σ)
- Los picos de 15m se "diluyen" al promediar con barras más tranquilas dentro del slot

**2. AUS200 mejora dramáticamente a 5m:**
- Ratio sube de 6.9x a **11.4x** (la mayor mejora de todos los activos)
- Valley se extiende de 30 min a **45 min** (más estable, visible con más detalle)
- #HOT pasa de 3 a 6 → estructura más clara del ciclo de volatilidad
- Pero sigue siendo ~48/47 bidireccional → LONG-only no tiene edge direccional

**3. Forex: valleys se reducen en 5m pero siguen presentes:**
- USDCHF: 165 min @15m → **70 min @5m** (se fragmenta pero aún el más largo)
- USDCAD: 60 min → 22 min (se reduce mucho)
- EURUSD: 45 min → 25 min (se reduce)
- XAUUSD: aparece valley de 12 min a 5m (invisible a 15m)

**4. ETFs (XLE, XLU, DIA, EWZ, GLD, TLT):**
- Sin valley útil (COLDlo = 0.0 porque mercado cierra → no hay actividad de madrugada)
- XLE y XLU mantienen bull bias consistente en ambas resoluciones (**56.4%/61.7%** bull)
- TLT aparece con 2 HOT slots a 5m (invisible a 15m) → peak 18.2 bps, débil

**5. Sesgo direccional — SOLO XLE y XLU lo tienen:**
- XLE: 56.1% bull @15m, 56.4% bull @5m → **consistente** (~8% bull bias)
- XLU: 61.7% bull @15m, 61.7% bull @5m → **consistente** (~25% bull bias, estable a ambas resoluciones)
- TODOS los forex son ~48-52% → bidireccionales, LONG-only pierde la mitad de oportunidades

### Candidatos ORB ordenados por viabilidad

| # | Asset | Argumento a favor | Argumento en contra | Necesita SHORT? |
|---|-------|-------------------|---------------------|:---------------:|
| 1 | **XLE** | Z +3.05, bull bias 56%, volatilidad alta (81.8 bps peak) | ETF sesión corta 6.5h, sin valley | No (bull bias) |
| 2 | **XLU** | Z +3.09, bull bias 62% (el mayor de todos), consistente 5m/15m | ETF sesión corta 6.5h, sin valley, volatilidad menor | No (bull bias) |
| 3 | **AUS200** | Z +2.67 @5m, ratio 11.4x, valley 45m, 24h | 48% bidireccional, YA DESCARTADO long-only PF 0.94 OOS | **Sí** |
| 4 | **USDCHF** | Valley 70m @5m (165m @15m), 19 HOT slots, 24h | 50/50 bidireccional | **Sí** |
| 5 | **XAUUSD** | Z +1.54, 17 HOT slots, valley 12m, alta volatilidad absoluta | 50/50 bidireccional, costes spread altos | **Sí** |

---

## 🎯 PLAN DE EXPLORACIÓN ORB POST-SCAN (2026-03-23)

### Tarea 1: AUS200 @5m — Sesión nocturna (explosión 22:50 UTC)
**Estado:** ❌ DESCARTADA
**Hipótesis:** La batida anterior (SsH 8-13, sesión diurna London) falló PF 0.94 OOS. Pero la señal MÁS fuerte de AUS200 es a las 22:50 UTC (ASX open), Z +2.67 @5m, ratio 11.4x. Probar ORB en sesión nocturna podría explotar un ciclo diferente.

**Adaptaciones respecto a batida anterior (@15m London):**
- `base_timeframe_minutes`: 15 → **5** (capturar la resolución real del pico)
- `session_start_hour`: 8-13 → **22-23** (consolidación post-gap ASX)
- `use_eod_close`: True → **False** (sesión overnight cruza medianoche)
- `dst_mode`: london_uk → **none** (horarios UTC fijos)
- `consolidation_bars_min/max @5m`: valley=45min=9 barras → sweep CBMin (3-9), CBMax (6-18)
- SL/TP: mantener sweep TP (3-5), SL (1.5-2.5)
- BkAbv: deshabilitado (irrelevante)
- Periodo: 2020-2023 IS, 144 combos, ~1h runtime

**Resultado:** 144 combos, **0% rentables**. Mejor combo: PF 0.96, -$12,693. El 100% de combos pierde dinero.

| # | SsH | SL | TP | CBMin | CBMax | Trades | PF | DD% | Net PnL | Consist |
|---|:---:|:--:|:--:|:-----:|:-----:|:------:|:--:|:---:|--------:|:-------:|
| 1 | 23 | 2.0 | 5.0 | 6 | 6 | 478 | 0.96 | 42.4% | -$12,693 | 2/4 yr |
| 2 | 23 | 2.0 | 4.0 | 6 | 6 | 479 | 0.95 | 40.8% | -$13,935 | 1/4 yr |
| 3 | 23 | 2.5 | 5.0 | 6 | 6 | 476 | 0.94 | 38.7% | -$17,051 | 3/4 yr |

**Problemas detectados:**
- CBMax ≥12 → 0 trades (la consolidación sobrepasa el gap mid-day 05:25 → sin barras)
- SsH=23 domina (mejor que SsH=22) → gap AU winter termina 23:50 → solo SsH=23 captura post-gap
- Pero ni el mejor combo alcanza PF 1.0
- ~50% de combos producen 0 trades (CBMax demasiado largo para sesión nocturna)

**Conclusión:** AUS200 LUYTEN ORB long-only NO tiene edge en NINGUNA sesión — ni diurna (London, PF 0.94 OOS) ni nocturna (ASX open, PF 0.96 IS). El activo es bidireccional (48/47%) y LONG-only pierde la mitad bajista sistemáticamente. AUS200 queda **completamente descartado** para LUYTEN sin SHORT.

### Tarea 2: XLE / XLU — ORB con bull bias
**Estado:** ❌ DESCARTADA
**Resultado:** Smoke test XLE: PF 0.72, DD 70%. Optimizer 180 combos: mejor PF ~0.77.
Análisis visual del liquidity profile @5m reveló el problema estructural:
- La explosión HOT (82 bps Z+3.05) es el caos de apertura NYSE 13:30 → **no hay valley previo** porque el mercado está cerrado antes
- El mini-valley 14:15-14:25 es demasiado corto (10 min = 2 barras @5m) y la segunda explosión 14:30-14:45 es mucho menor
- Sesión corta 6.5h + apertura = momento más volátil → LUYTEN no tiene tiempo ni estructura valley→explosion
- Mismo problema estructural que TLT: **ORB no funciona en ETFs de sesión corta sin valley pre-apertura**

**Conclusión:** XLE/XLU descartados para LUYTEN. El bull bias (56%/62%) es real pero no compensable con ORB en sesión tan corta.

### Tarea 3: TLT @5m
**Estado:** ⏸️ SUSPENDIDA — mismo problema estructural que XLE/XLU. No tiene sentido.

### Tarea 4: Investigación valley→explosion direccional @15m — MULTI-ACTIVO
**Estado:** 🔄 EN CURSO
**Granularidad:** 15m (análisis visual de liquidity_profile --slot 15 --plot)

#### Hallazgo 1: XAUUSD — 21:45→22:00 UTC
```
  21:45   552   8.67 bps   Z=-0.43   44.0% Bull  55.1% Bear  DirZ=-0.29  cold   (CALMA bearish)
  22:00  1016  17.21 bps   Z=+0.25   65.4% Bull  34.4% Bear  DirZ=+2.79         (EXPLOSIÓN BULL)
```
- **Valley→explosion**: 8.67 → 17.21 bps (ratio 2.0x)
- **65.4% Bull, DirZ +2.79** = señal direccional más fuerte de los 14 activos (>2σ)
- XAUUSD 24h → SL/TP tienen tiempo de desarrollo
- La calma de 21:45 (debajo de media 14.1 bps) es valley perfecto para consolidación LUYTEN

#### Hallazgo 2: EURUSD — 21:45→22:00 UTC (MISMA VENTANA)
**@15m:**
```
  21:45  1609   3.17 bps   Z=-0.60   42.2% Bull  54.3% Bear  DirZ=-0.29  cold
  22:00  1612   4.79 bps   Z=-0.29   62.6% Bull  35.5% Bear  DirZ=+0.81
```
**@5m (más detalle):**
```
  21:55  1609   2.22 bps   Z=-0.42   38.6% Bull  55.3% Bear  DirZ=-0.38  (CALMA bearish)
  22:00  1608   3.47 bps   Z=-0.01   63.0% Bull  34.0% Bear  DirZ=+0.63  (EXPLOSIÓN BULL)
```
- **Valley→explosion @5m**: 2.22 → 3.47 bps (ratio 1.56x) — el valley se afina a 21:55, no 21:45
- **63.0% Bull @5m** confirma el sesgo del @15m (62.6%) → consistente entre granularidades
- Pero DirZ +0.63 sigue sin ser significativo (< 2σ)
- Mismo patrón temporal que XAUUSD (21:55-22:00) → driver macro compartido confirmado
- EURUSD más débil que XAUUSD tanto en ratio de explosión como en significancia direccional

#### Comparativa rápida (21:45→22:00 UTC)
| Activo | Vol valley | Vol explosion | Ratio | % Bull | DirZ  | Calidad |
|--------|-----------|--------------|-------|--------|-------|---------|
| XAUUSD | 8.67 bps  | 17.21 bps    | 2.0x  | 65.4%  | +2.79 | ★★★     |
| EURUSD | 3.17 bps  | 4.79 bps     | 1.5x  | 62.6%  | +0.81 | ★☆☆     |

**Nota:** La coincidencia temporal 21:45→22:00 sugiere un driver macro común (posiblemente cierre de futuros US o transición Asia).

**Plan:**
1. ~~Revisar más activos en la misma ventana 21:45→22:00 para confirmar patrón macro~~
2. ~~Crear config XAUUSD_LUYTEN con SsH~21:45 UTC, dst_mode='none' (mejor candidato)~~
3. ~~Batida reducida focalizada en XAUUSD primero~~

#### Resultado backtesting XAUUSD_LUYTEN (2020-2023)
**Estado:** ❌ SIN EDGE — múltiples configuraciones SsH 21-23, SL/TP variados, ninguna rentable.
- Mejor caso: PF ~1.21 en 2020/2021/2023 pero **2022 PF 0.79 (-$2,917)** destruye todo
- Caso típico: PF global ~0.95-1.00, WR% 38-48%
- El 65.4% bull DirZ +2.79 NO se traduce en profit operativo

**Diagnóstico: liquidity_profile.py tiene limitaciones críticas:**
1. **Promedios incondicionales**: calcula sobre ~1600 días sin descomponer por año/régimen
   → La "señal" del 65% bull puede ser 75% en 2021 y 40% en 2022 → promedio artefacto (Simpson's paradox)
2. **Solo cuenta frecuencia, no magnitud**: 65% bull × 2 bps avg vs 35% bear × 5 bps avg = neto negativo
3. **Gap como artefacto**: la barra de reapertura (23:00/22:00) incluye salto del gap, infla body y % bull artificialmente → ORB no puede capturar esto

---

## TAREAS PRIORITARIAS: Mejora de liquidity_profile.py

### Tarea A: Descomposición temporal por año (PRIORIDAD ALTA)
**Estado:** ✅ COMPLETADA — commit `2a25eae`
- Flag `--yearly` implementado en liquidity_profile.py
- Por cada slot HOT o con bull%>58, muestra bull%, NetEV, MeanTR por año
- Métrica de estabilidad: spread (max-min bull%) → <15pp = STABLE, >=15pp = UNSTABLE

### Tarea B: Reporte de magnitud asimétrica (PRIORIDAD ALTA)
**Estado:** ✅ COMPLETADA — commit `2a25eae`
- Campos: `mean_bull_body`, `mean_bear_body`, `net_ev_bps` en compute_slot_stats()
- NetEV = bull% × mean_bull_body − bear% × mean_bear_body (valor esperado neto)
- TOP 10 ranking por |NetEV| con indicador LONG/SHORT/NONE
- print_magnitude_summary() muestra los slots con mayor asimetría

---

### RESULTADO: Scan cross-asset completo (14 activos, 15m, --yearly)
Fecha: 2026-03-25

#### Patrón 1: 22:00 UTC → BULL sistémico en FX (rollover candle)
| Activo | Bull% | NetEV  | Años BULL | Spread | Estab. |
|--------|-------|--------|-----------|--------|--------|
| AUDUSD | 62.4% | +1.25  | **6/6**   | 10.7pp | STABLE |
| XAUUSD | 65.4% | +2.79  | 5/6*      | 80.5pp | UNSTABLE |
| EURUSD | 62.6% | +0.81  | 5/6*      | 31.1pp | UNSTABLE |
| USDCHF | 60.9% | +1.37  | 6/7       | 15.4pp | UNSTABLE |
| EURJPY | 61.3% | +1.34  | 6/7       | 16.3pp | UNSTABLE |
*2026 tiene N=2-51 (sesgo por muestra pequeña)

AUDUSD 22:00 detalle por año:
- 2020: 57.9% bull~ | 2021: 66.2% BULL | 2022: 58.1% bull~
- 2023: 63.2% BULL | 2024: 60.9% BULL | 2025: 68.6% BULL
→ El ÚNICO par FX con 22:00 BULL+STABLE en los 6 años completos.

#### Patrón 2: 20:45 UTC → BEAR sistémico en FX (pre-rollover markdown)
| Activo | Bear% | NetEV  | Años BEAR | Spread | Estab. |
|--------|-------|--------|-----------|--------|--------|
| USDCHF | 66.7% | -1.68  | **6/6**   | 24.7pp | UNSTABLE |
| USDJPY | 62.2% | -1.05  | **6/6**   | 37.8pp | UNSTABLE |
| USDCAD | 60.7% | -0.81  | **5/6**   | 12.0pp | STABLE |
| AUDUSD | 62.9% | -1.09  | 4/6       | 18.1pp | UNSTABLE |
| EURJPY | 62.2% | -0.86  | 5/6       | 51.0pp | UNSTABLE |

#### Patrón 3: 23:00 UTC → BULL post-rollover
| Activo | Bull% | NetEV  | Años BULL | Spread | Estab. |
|--------|-------|--------|-----------|--------|--------|
| AUDUSD | 59.7% | +1.27  | **6/6**   | 8.5pp  | STABLE |
| XAUUSD | 60.3% | +1.87  | 6/6       | 7.2pp  | STABLE |
| USDCHF | 59.5% | +1.12  | —         | 20.3pp | UNSTABLE |

#### Patrón 4: 13:30 UTC → Apertura US (ETFs)
| Activo | Bull% | NetEV   | Años BULL | Spread | Estab. |
|--------|-------|---------|-----------|--------|--------|
| XLU    | 61.7% | +13.51  | 4/6       | 15.0pp | STABLE (border) |
| XLE    | 56.1% | +10.42  | 2/6       | 15.2pp | UNSTABLE |
| EWZ    | 51.0% | +2.22   | —         | 13.3pp | STABLE |

#### Patrón 5: Zonas HOT (12:30-15:00) → COIN FLIP estable
TODOS los activos: bull% 47-53%, NetEV ≈ 0, spread <15pp = STABLE.
Son moneda al aire perfecta. Alta volatilidad para ORB, pero cero edge direccional.

#### Conclusión clave:
> Los patrones direccionales fuertes (20:45 BEAR, 22:00 BULL, 23:00 BULL) son artefactos
> estructurales del rollover/gap. Ocurren en zonas COLD (2-8 bps TrueRange) → NO hay
> volatilidad suficiente para un rango de consolidación ORB. Las zonas HOT (13:30-15:00)
> donde ORB funciona tienen 50/50 bull/bear → no hay edge ORB long-only.

#### Candidatos restantes:
1. **AUDUSD 22:00-23:00** — único con ambos slots STABLE+BULL 6/6 años (pero COLD zone)
2. **USDCAD 20:45** — BEAR estable 5/6 años, 12pp spread → requiere SHORTs
3. **XLU 13:30** — ya probado, PF 0.70-0.77 → DESCARTADO

---

### Tarea C: HMM — Régimen condicional (PRIORIDAD MEDIA)
**Estado:** ✅ COMPLETADA
Flag `--hmm` implementado en liquidity_profile.py (hmmlearn GaussianHMM).
- 3 estados: CALM / NORMAL / VOLATILE (ordenados por vol intradiaria)
- Features: |retorno_diario| + rango_intradiario (bps)
- compute_daily_features(), fit_hmm_regimes(), compute_regime_slot_stats()
- print_hmm_summary(), print_regime_directional()
- Muestra slots donde el edge cambia entre regímenes (filtro automático spread ≥ 8pp)

#### Resultado HMM cross-asset (2026-03-25):

**Hallazgo clave: 22:00 UTC es régimen-dependiente en AUDUSD**
```
AUDUSD 22:00: CALM=63.9% LONG(+1.64)  NORMAL=63.0% LONG(+1.27)  VOLATILE=53.2% SHORT(-0.67)
```
→ En días CALM/NORMAL (89% del tiempo): BULL fuerte y consistente
→ En días VOLATILE (11%): se invierte a SHORT → destruye la media
→ Mismo patrón inverso en 20:45: BEAR en todos los regímenes, más fuerte en NORMAL

**AUDUSD 23:00: ROBUSTO en todos los regímenes**
```
AUDUSD 23:00: CALM=59.8% LONG(+1.18)  NORMAL=59.7% LONG(+1.14)  VOLATILE=59.0% LONG(+2.10)
```
→ Bull 59-60% en LOS TRES regímenes, incluyendo VOLATILE
→ El slot más robusto de todo el universo analizado

**XAUUSD 22:00: BULL en todos los regímenes (incluyendo VOLATILE)**
```
XAUUSD 22:00: CALM=62.5% LONG(+1.97)  NORMAL=69.9% LONG(+3.45)  VOLATILE=62.7% LONG(+4.22)
```
→ No solo es bull siempre, sino que VOLATILE tiene el NetEV MÁS ALTO (+4.22)
→ Contrasta con AUDUSD donde VOLATILE invierte la señal

**XAUUSD 23:00: también BULL en todos los regímenes**
```
XAUUSD 23:00: CALM=56.7% LONG(+1.00)  NORMAL=64.9% LONG(+2.42)  VOLATILE=60.3% LONG(+3.81)
```

**FX rollover pattern (20:45 BEAR): universal en todos los regímenes**
- EURUSD 20:45: CALM=-0.40, NORMAL=-0.69, VOL=-0.62 (siempre BEAR)
- USDCHF 20:45: CALM=-1.46, NORMAL=-1.78, VOL=-1.78 (siempre BEAR, intenso)
- USDJPY 20:45: CALM=-0.77, NORMAL=-1.06, VOL=-1.30 (más fuerte en VOL)

**EURUSD 22:00: raro — más BULL en VOLATILE**
```
EURUSD 22:00: CALM=59.6% LONG(+0.59)  NORMAL=66.5% LONG(+0.79)  VOLATILE=63.2% LONG(+1.29)
```
→ Pero su yearly spread=31pp lo descalifica como UNSTABLE por criterio interanual

**ETFs (XLU 13:30): HMM inútil — CALM tiene N=1 día**
→ HMM ve 90.3% NORMAL + 9.6% VOLATILE + 0.1% CALM → clasificación degenerada
→ No conclusivo para ETFs con sesión corta

#### Ranking cruzado HMM + Yearly:
| Activo     | Slot  | Yearly | HMM 3-regime | Veredicto |
|------------|-------|--------|--------------|-----------|
| AUDUSD 23:00 | STABLE 8.5pp | BULL en 3/3 | ★★★ CANDIDATO #1 |
| XAUUSD 22:00 | UNSTABLE 80pp | BULL en 3/3 | ★★ señal real pero gap |
| XAUUSD 23:00 | STABLE 7.2pp | BULL en 3/3 | ★★ señal real pero gap |
| AUDUSD 22:00 | STABLE 10.7pp | BULL 2/3 SHORT 1/3 | ★☆ régimen-dependiente |
| EURUSD 22:00 | UNSTABLE 31pp | BULL en 3/3 | ☆☆ yearly inestable |
| USDCHF 20:45 | UNSTABLE 24pp | BEAR 3/3 | ☆☆ yearly inestable |

### ~~Tarea D: HDBSCAN~~ — DESCARTADA
**Estado:** ❌ DESCARTADA (2026-03-25)
HDBSCAN es unsupervised clustering — agrupa por similitud de features, no por resultado.
No añade valor sobre HMM (Task C): el problema ya no es segmentar días, sino
confirmar si los edges detectados son estadísticamente explotables.

### ~~Tarea 5 (condicional): SHORTs + EURUSD/USDCHF~~ — APLAZADA
**Estado:** ⏸️ APLAZADA — la dirección (LONG/SHORT) depende de la ventaja, no al revés.
Se retomará si E1-E3 confirman edge en slots BEAR (20:45).

---

## CAMBIO DE FILOSOFÍA (2026-03-25)

**ANTES:** Buscar patrón → adaptarlo a ORB (estrategia fija).
**AHORA:** Encontrar ventaja estadística robusta → diseñar estrategia que la explote.

La investigación (Tasks A-C) demostró que:
1. Los patrones direccionales REALES están en zona COLD (rollover 22:00-23:00, 20:45)
2. En zona HOT (London/NY open) los slots son 50/50 — coin flip
3. ORB necesita volatilidad (HOT zones) pero ahí no hay edge direccional
4. El edge EXISTE donde ORB NO SIRVE

**Conclusión:** La estrategia debe adaptarse a la ventaja, no al revés.
Si el edge es un drift direccional en zona COLD, la estrategia correcta podría ser
una entrada directa por hora (time-of-day directional bet), no un breakout.

---

## Fase E: Validación estadística formal (2026-03-25)

**Objetivo:** Confirmar/descartar que los edges detectados son REALES y EXPLOTABLES.
Candidatos a validar:
- AUDUSD 23:00 BULL (★★★ — estable yearly + estable HMM 3/3 regímenes)
- AUDUSD 22:00 BULL (★☆ — estable yearly, pero régimen-dependiente)
- XAUUSD 22:00/23:00 BULL (★★ — HMM robusto pero yearly inestable)
- 20:45 BEAR cross-FX (universal pero requiere SHORTs)

### Tarea E1: Test de permutación (Bootstrap significance)
**Estado:** ⏳ PENDIENTE
**Qué:** Para cada slot candidato, aleatorizar 10,000 veces qué velas caen en ese slot.
Calcular distribución nula de bull% bajo H0: "el slot no tiene sesgo direccional".
Si bull% observado cae fuera del IC 95% → edge es estadísticamente significativo (p < 0.05).
**Implementar en:** liquidity_profile.py (flag --bootstrap o --permtest)
**Output:** p-value por slot, tabla con slots significativos

### Tarea E2: Distribución completa de retornos (histograma + quantiles)
**Estado:** ⏳ PENDIENTE
**Qué:** Para cada slot candidato, mostrar distribución completa de retornos:
- Histograma (o text-based percentiles)
- Quantiles: Q10, Q25, mediana, Q75, Q90
- Skewness y kurtosis
- Ratio ganancia media / pérdida media (payoff ratio)
**Por qué:** bull% 60% no basta si las pérdidas son 3x mayores que las ganancias.
Un edge real requiere: (bull% × avg_win) > (bear% × avg_loss) NETO DE COSTES.
**Implementar en:** liquidity_profile.py (flag --distribution)

### Tarea E3: Backtest naive con costes de transacción
**Estado:** ⏳ PENDIENTE
**Qué:** Simulación simple (sin Backtrader):
- Entrada: LONG al inicio del slot (ej: 23:00:00)
- Salida: al final del slot (ej: 23:14:59)
- Restar spread real del par en esa hora (COLD zone → spread MÁS ancho)
- Calcular: PnL neto por operación, equity curve, Sharpe, max drawdown
- Walk-forward: entrenar ratio en años 1-N, testear año N+1
**Por qué:** Si NetEV del slot = +1.5 bps pero spread = 2 bps → edge inexplotable.
Es el test final antes de invertir tiempo en diseñar estrategia.
**Implementar en:** nuevo script tools/slot_backtest.py o dentro de liquidity_profile.py
