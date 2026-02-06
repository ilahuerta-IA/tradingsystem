# HELIX Strategy

> ⚠️ **ESTADO: DEPRECATED (2026-02-06)**
>
> Esta estrategia ha sido **deprecada** tras análisis de backtesting e investigación académica.
>
> **Problema Diagnosticado:**
> - La estrategia base (KAMA + pullback + breakout) tiene PF < 1.0 en EURUSD
> - Spectral Entropy como filtro solo reorganiza trades, no crea edge
> - Parámetros óptimos cambian drásticamente entre runs = overfitting
> - SE se usa en literatura como **filtro de régimen**, NO como trigger de entrada
>
> **Nueva Dirección:**
> Se está explorando una estrategia basada en **divergencia de correlación EURUSD/USDCHF**
> que confirma momentum real. Ver CONTEXT.md sección "🚀 NUEVA IDEA".
>
> Este documento se mantiene como **referencia histórica** del experimento HELIX.

---

**Type:** HTF Structure + Pullback + Breakout (Spectral Entropy variant)  
**Assets:** EURUSD, USDCHF (target pairs where SEDNA fails)  
**Direction:** Long Only  
**Base:** Derived from SEDNA with SE replacing ER

---

## Table of Contents

1. [Overview](#overview)
2. [Hypothesis](#hypothesis)
3. [Key Difference from SEDNA](#key-difference-from-sedna)
4. [Entry System (3 Phases)](#entry-system-3-phases)
5. [Main Indicators](#main-indicators)
6. [Configuration Parameters](#configuration-parameters)
7. [Validation Status](#validation-status)

---

## Overview

HELIX is a **SEDNA variant** that uses **Spectral Entropy (SE)** instead of **Efficiency Ratio (ER)** as the HTF filter.

### Design Philosophy

```
HTF STRUCTURE  -->  PULLBACK  -->  BREAKOUT  -->  ENTRY
     (1)              (2)            (3)

SEDNA:  KAMA + ER_HTF + pullback → entry (ER HIGH = trending)
HELIX:  KAMA + SE_HTF + pullback → entry (SE LOW = structured) ← INVERTED LOGIC
```

---

## Hypothesis

**Problem:** SEDNA works well on JPY pairs (USDJPY, EURJPY) but fails on EUR/CHF pairs (EURUSD, USDCHF).

**Observation:**
- JPY pairs have slower, more "efficient" movements → ER detects well
- EUR/CHF pairs have faster, more complex movements → ER may miss structure

**Hypothesis:** Spectral Entropy might detect "structure" faster than ER on EUR/CHF pairs because:
- **ER** measures directional efficiency (distance traveled vs path taken)
- **SE** measures frequency structure (dominant patterns vs noise)

---

## Key Difference from SEDNA

| Aspect | SEDNA | HELIX |
|--------|-------|-------|
| **HTF Filter** | Efficiency Ratio (ER) | Spectral Entropy (SE) |
| **Filter Logic** | ER ≥ threshold (HIGH = good) | SE ≤ threshold (LOW = good) |
| **Interpretation** | High ER = trending market | Low SE = structured market |
| **Target Pairs** | USDJPY, EURJPY, DIA | EURUSD, USDCHF |

### Logic Inversion

```
SEDNA (ER):  0.0 ──────────────── 1.0
             choppy              trending
             ❌ reject           ✅ accept

HELIX (SE):  0.0 ──────────────── 1.0
             structured          noisy
             ✅ accept           ❌ reject
```

---

## Entry System (3 Phases)

### Phase 1: HTF Structure Filter (Main Trigger)

```python
def _check_htf_filter(self) -> tuple:
    # Condition 1: SE <= threshold (structured market)
    se_value = SpectralEntropy(close, scaled_period)
    if se_value > htf_se_threshold:  # INVERTED from SEDNA
        return False, se_value
    
    # Condition 2: Close > KAMA (bullish direction)
    if close <= KAMA:
        return False, se_value
    
    return True, se_value
```

**Spectral Entropy** measures market randomness via FFT:
- SE close to 0.0 = Dominant frequency (structured pattern)
- SE close to 1.0 = Spread across frequencies (random noise)

### Phase 2: Pullback Detection

Same as SEDNA - detects N bars without new Higher High, price respects KAMA.

### Phase 3: Breakout Confirmation

Same as SEDNA - High > pullback HH + buffer within N candles.

---

## Main Indicators

### Spectral Entropy (SE)

```python
def calculate_spectral_entropy(prices: list, period: int = 20) -> float:
    """
    1. Calculate returns over period
    2. Apply FFT to get frequency components
    3. Compute power spectrum
    4. Normalize to probability distribution
    5. Calculate Shannon entropy
    6. Normalize by max possible entropy
    
    Returns: 0.0 (structured) to 1.0 (random)
    """
```

**FFT-based analysis:**
- Dominant frequency = structured trend/cycle
- Spread frequencies = random noise

### KAMA (Same as SEDNA)

Kaufman's Adaptive Moving Average on HL2.

---

## Configuration Parameters

### HTF Filter (Spectral Entropy)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `use_htf_filter` | `True` | Enable SE filter |
| `htf_timeframe_minutes` | `15` | Target HTF (15m or 60m) |
| `htf_se_period` | `20` | SE period on HTF |
| `htf_se_threshold` | `0.7` | Max SE to allow entry |

### Parameters to Optimize

| Parameter | Range | Notes |
|-----------|-------|-------|
| `htf_se_period` | 10-30 | Longer = smoother, fewer signals |
| `htf_se_threshold` | 0.5-0.8 | Lower = stricter, fewer signals |
| `htf_timeframe_minutes` | 15, 30, 60 | Higher = more lag, fewer signals |

---

## Files

| File | Purpose |
|------|---------|
| `lib/filters.py` | `calculate_spectral_entropy()`, `check_spectral_entropy_filter()` |
| `lib/indicators.py` | `SpectralEntropy` (Backtrader indicator) |
| `strategies/helix_strategy.py` | Main backtest strategy |
| `config/settings.py` | `EURUSD_HELIX`, `USDCHF_HELIX` configs |

---

## Validation Status

**Current Status:** 🧪 In Development - Awaiting Backtest Validation

### Validation Criteria

| Metric | Minimum | Status |
|--------|---------|--------|
| Profit Factor | ≥ 1.5 | ❓ Pending |
| Sharpe Ratio | ≥ 0.7 | ❓ Pending |
| Max Drawdown | < 10% | ❓ Pending |
| Trades/year | ~50+ | ❓ Pending |

### Next Steps

1. Run backtest: `python run_backtest.py USDCHF_HELIX`
2. Evaluate metrics vs criteria
3. If fails → adjust SE parameters or try Hilbert Transform

---

## Lecciones Aprendidas (Post-mortem 2026-02-06)

### ❌ Lo que NO funcionó

1. **SE como filtro de entrada:**
   - Investigación académica mostró que SE se usa como filtro de RÉGIMEN, no trigger
   - Timeframes adecuados: 1H mínimo, diario ideal
   - En 5m/15m el ruido domina

2. **Estrategia base sin edge:**
   - KAMA + pullback + breakout en EURUSD = PF ~0.97
   - No tiene ventaja estadística inherente
   - Filtros solo reorganizan trades, no crean edge

3. **Optimización de parámetros:**
   - Valores óptimos cambian drásticamente entre runs
   - SE 0.80-0.82 en un run, 0.90-0.92 en otro
   - Síntoma clásico de overfitting

### 📚 Referencias Académicas Consultadas

- Cerra & Tuceryan (2012): SE para caracterización de imagen
- Fernandes et al. (2019): SE en señales EEG
- Li & Bastos (2020): "Entropy measures for biological signal analyses"
- Pan et al. (2020): SE como filtro de régimen de mercado

### ✅ Qué se aprendió

1. **Verificar edge base ANTES de añadir filtros**
2. **Indicador de régimen ≠ indicador de entrada**
3. **Parámetros inestables = posible overfitting**
4. **Correlación entre pares puede ser más confiable que indicadores sintéticos**

### 🔄 Nueva Dirección

Ver CONTEXT.md → Sección "🚀 NUEVA IDEA: Estrategia de Correlación EURUSD/USDCHF"
4. If passes → create `live/checkers/helix_checker.py`

---

## Fallback Plan

If Spectral Entropy doesn't work, the same integration point can be used for:

- **Hilbert Transform** - Instantaneous phase/amplitude analysis
- **Wavelet Decomposition** - Multi-resolution analysis
- **Hurst Exponent** - Long-term memory detection

All would replace the `_check_htf_filter()` method with same interface.

---

*Last updated: 2026-02-04*
