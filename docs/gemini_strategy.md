# GEMINI Strategy

**Type:** Correlation Divergence Momentum (Harmony Score)  
**Assets:** EURUSD (primary) + USDCHF (reference)  
**Direction:** Long Only  
**Concept:** EUR strength confirmed by harmonic ROC divergence

---

## Table of Contents

1. [Overview](#overview)
2. [The Core Insight](#the-core-insight)
3. [Harmony Score Formula](#harmony-score-formula)
4. [Entry System](#entry-system)
5. [Indicators](#indicators)
6. [Configuration Parameters](#configuration-parameters)
7. [Implementation Details](#implementation-details)
8. [Evolution History](#evolution-history)
9. [Validation Criteria](#validation-criteria)

---

## Overview

GEMINI is named after the twin stars (Castor & Pollux) representing the two correlated pairs.

### Design Philosophy

```
EURUSD and USDCHF are inversely correlated (~-0.90) via USD.

Normal state:    EURUSD up   = USDCHF down   (USD weakness)
                 EURUSD down = USDCHF up     (USD strength)

Harmony Signal:  ROC_EURUSD rising WHILE ROC_USDCHF falling
                 = Both ROCs separating from zero in opposite directions
                 = EUR INTRINSIC STRENGTH
```

**Key Difference from Mean Reversion:**
- We're NOT betting on convergence
- We're CONFIRMING momentum via harmonic divergence
- Goes WITH the trend, not against it

---

## The Core Insight

### Why Harmony Score Works

The **Harmony Score** measures symmetric divergence between two ROCs:

1. **ROC_primary** (EURUSD) measures EUR/USD momentum
2. **ROC_reference** (USDCHF) measures USD/CHF momentum
3. **Harmony** = product of opposite movements

When both ROCs move away from zero in opposite directions:
- EURUSD gaining momentum UP
- USDCHF losing momentum DOWN
- = EUR has REAL intrinsic strength (not just USD weakness)

---

## Harmony Score Formula

```python
harmony = ROC_primary × (-ROC_reference) × scale
```

### Why Product Works

| ROC_EURUSD | ROC_USDCHF | Harmony | Interpretation |
|------------|------------|---------|----------------|
| +0.002 | -0.0015 | **+3.0** | ✅ Harmony - both diverging from 0 |
| +0.001 | +0.001 | **-1.0** | ❌ No harmony - same direction |
| +0.004 | -0.0001 | **+0.4** | ⚠️ Asymmetric - one barely moves |
| +0.002 | -0.002 | **+4.0** | ✅✅ Perfect symmetry |

*(Values shown with scale=10000)*

### Key Properties

- **Positive** when ROCs move in opposite directions
- **Higher value** = stronger AND more symmetric movement
- **Negative** = both ROCs same direction (no edge)
- **Scale factor** makes values visible on chart (raw values ~0.000001)

---

## Entry System (v2 - KAMA Cross + Angle Confirmation)

### Two-Phase Entry Architecture

```
Phase 1 (TRIGGER):   HL2_EMA crosses above KAMA
                     → Opens N-bar confirmation window

Phase 2 (CONFIRM):   Within the window:
                     - roc_angle >= entry_roc_angle_min
                     - harmony_angle >= entry_harmony_angle_min
                     → ENTRY (with additional filters)
```

### Entry Conditions (ALL must be true)

| Phase | Condition | Description |
|-------|-----------|-------------|
| 1 | KAMA Cross | HL2_EMA[0] > KAMA[0] AND HL2_EMA[-1] <= KAMA[-1] |
| 2 | Window Active | Within `cross_window_bars` after cross |
| 2 | ROC Angle | roc_angle >= `entry_roc_angle_min` (degrees) |
| 2 | Harmony Angle | harmony_angle >= `entry_harmony_angle_min` (degrees) |
| 2 | Filters | Time, day, ATR, SL pips filters if enabled |

### Angle Calculation (on plot-scaled values)

```python
# Calculated on PLOT-SCALED values for visual consistency
roc_plot = roc_primary * plot_roc_multiplier
roc_angle = atan((roc_plot[0] - roc_plot[-1]) * roc_angle_scale)

harmony_plot = harmony * plot_harmony_multiplier
harmony_angle = atan((harmony_plot[0] - harmony_plot[-1]) * harmony_angle_scale)
```

**Key insight:** What you SEE in the Angles subplot = what the system evaluates for entry.

### Exit Conditions

| Exit Type | Description |
|-----------|-------------|
| Stop Loss | Entry - (ATR × SL multiplier) |
| Take Profit | Entry + (ATR × TP multiplier) |

---

## Indicators

### ROCDualIndicator (Custom)

```python
class ROCDualIndicator(bt.Indicator):
    """
    Dual ROC indicator with Harmony Score.
    
    Lines:
    - roc_primary: ROC of EURUSD (blue)
    - roc_reference: ROC of USDCHF (red)
    - harmony: Scaled harmony score (purple)
    - zero: Zero reference line
    """

class AngleIndicator(bt.Indicator):
    """
    Slope angles (calculated on plot-scaled values).
    
    Lines:
    - roc_angle: ROC slope angle in degrees (blue)
    - harmony_angle: Harmony slope angle in degrees (purple)
    """
```

**Calculation:**
1. Calculate ROC for primary pair (EURUSD)
2. Calculate ROC for reference pair (USDCHF)
3. Harmony = ROC_primary × (-ROC_reference) × scale
4. Plot all three lines in subplot

### KAMA (from lib/indicators.py)

Standard Kaufman Adaptive Moving Average for trend filter.

---

## Configuration Parameters

### ROC & Harmony Settings

| Parameter | Default | Description |
|-----------|---------|-------------|
| `roc_period_primary` | 5 | ROC period for EURUSD |
| `roc_period_reference` | 5 | ROC period for USDCHF |
| `harmony_scale` | 10000 | Scale factor for harmony calculation |

### Entry System Settings (KAMA Cross + Angles)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `cross_window_bars` | 5 | Bars after KAMA cross to confirm entry |
| `entry_roc_angle_min` | 20.0 | Min ROC angle to enter (degrees) |
| `entry_harmony_angle_min` | 20.0 | Min Harmony angle to enter (degrees) |
| `roc_angle_scale` | 1.0 | Scale for ROC angle atan() |
| `harmony_angle_scale` | 1.0 | Scale for Harmony angle atan() |

### Plot Settings (SYNCED with Entry Calculation)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `plot_roc_multiplier` | 500 | Scale ROC for plot AND angle calculation |
| `plot_harmony_multiplier` | 15.0 | Scale Harmony for plot AND angle calculation |

**IMPORTANT:** `plot_*_multiplier` affects BOTH visualization AND entry calculation. Visual = Logic.

### ATR Settings

| Parameter | Default | Description |
|-----------|---------|-------------|
| `atr_length` | 14 | ATR period |
| `atr_sl_multiplier` | 3.0 | SL = ATR × this |
| `atr_tp_multiplier` | 6.0 | TP = ATR × this |

### Filters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `use_time_filter` | False | Hour-based filter |
| `use_day_filter` | False | Day-of-week filter |
| `use_sl_pips_filter` | False | SL range filter |
| `use_atr_filter` | False | ATR range filter |

---

## Implementation Details

### Data Requirements

**Primary data (self.datas[0]):** The asset being traded (EURUSD)
**Reference data (self.datas[1]):** The correlated pair (USDCHF)

```python
# Config in settings.py
'EURUSD_GEMINI': {
    'data_path': 'data/EURUSD_5m_5Yea.csv',
    'reference_data_path': 'data/USDCHF_5m_5Yea.csv',
    'reference_symbol': 'USDCHF',
    'params': {
        'harmony_threshold': 0.0,
        'harmony_scale': 10000,
        'harmony_bars': 3,
        ...
    }
}
```

### Log Format

```
ENTRY #N
Time: YYYY-MM-DD HH:MM:SS
Entry Price: X.XXXXX
Stop Loss: X.XXXXX
Take Profit: X.XXXXX
SL Pips: X.X
ATR (avg): 0.XXXXXX
Harmony Score: X.XXXX
```

---

## Evolution History

### Phase 1: Z-Score Spread (FAILED)
- **Approach:** Z-Score of price spread (EMA_EURUSD - EMA_1/USDCHF)
- **Problem:** Very noisy, constant oscillation, many false entries
- **Result:** PF 0.83-0.92 (not viable)

### Phase 2: ROC Sum (IMPROVED)
- **Approach:** ROC_EURUSD + ROC_USDCHF > threshold
- **Improvement:** Measures momentum, not position
- **Result:** PF 1.19 with threshold optimization

### Phase 3: Harmony Score
- **Approach:** ROC_primary × (-ROC_reference) × scale
- **Insight:** Product captures symmetric divergence
- **Result:** PF 0.86 - base funcional but noisy

### Phase 4: Slope Filter
- **Approach:** Add angle filters on ROC and Harmony slopes
- **Problem:** Too restrictive as additional filter
- **Result:** 0 trades with strict thresholds

### Phase 5: KAMA Cross + Angle Confirmation (CURRENT)
- **Approach:** KAMA cross as trigger, angles as confirmation within window
- **Insight:** Visual pattern - KAMA cross + rising angles = quality setup
- **Status:** Visual tuning in progress

---

## Validation Criteria

### Minimum Requirements

| Metric | Minimum | Current Status |
|--------|---------|----------------|
| Profit Factor | >= 1.5 | 🔄 Optimizing |
| Sharpe Ratio | >= 0.7 | 🔄 Pending |
| Max Drawdown | < 10% | ✅ 8.97% |
| Trades/year | ~100+ | 🔄 Pending |

### Optimization Targets

Parameters to tune:
- `harmony_threshold` - Filter weak harmonic signals
- `harmony_bars` - Require more sustained divergence
- `roc_period_*` - Different periods for each pair

---

## Files

| File | Purpose |
|------|---------|
| `strategies/gemini_strategy.py` | Main backtest strategy |
| `config/settings.py` | `EURUSD_GEMINI`, `USDCHF_GEMINI` configs |
| `tools/analyze_gemini.py` | Log analysis tool |
| `docs/gemini_strategy.md` | This documentation |

---

## Validation Status

**Current Status:** 🔄 Harmony Score Optimization Phase

### Change Log

| Date | Change |
|------|--------|
| 2026-02-06 | Initial Z-Score implementation |
| 2026-02-06 | Pivoted to ROC Sum approach |
| 2026-02-06 | Evolved to Harmony Score formula |
| 2026-02-06 | Added harmony visualization (purple line) |
| 2026-02-07 | Added Slope Filter (angle-based) |
| 2026-02-07 | Refactored to KAMA Cross + Angle Confirmation system |
| 2026-02-07 | Added AngleIndicator subplot (roc_angle, harmony_angle) |
| 2026-02-07 | Synced plot multipliers with entry calculation |
