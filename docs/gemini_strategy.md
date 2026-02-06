# GEMINI Strategy

**Type:** Correlation Divergence Momentum  
**Assets:** EURUSD (primary) + USDCHF (reference), or vice versa  
**Direction:** Long Only  
**Concept:** EUR strength confirmed by EURUSD vs USDCHF divergence

---

## Table of Contents

1. [Overview](#overview)
2. [The Core Insight](#the-core-insight)
3. [Entry System](#entry-system)
4. [Indicators](#indicators)
5. [Configuration Parameters](#configuration-parameters)
6. [Implementation Details](#implementation-details)
7. [Validation Criteria](#validation-criteria)

---

## Overview

GEMINI is named after the twin stars (Castor & Pollux) representing the two correlated pairs.

### Design Philosophy

```
EURUSD and USDCHF are inversely correlated (~-0.90) via USD.

Normal state:    EURUSD up   = USDCHF down   (USD weakness)
                 EURUSD down = USDCHF up     (USD strength)

Divergence:      EURUSD up   > USDCHF_inv up  = EUR INTRINSIC STRENGTH
                 (EUR is rising more than just USD weakness would explain)
```

**Key Difference from Mean Reversion:**
- We're NOT betting on convergence
- We're CONFIRMING momentum via divergence
- Goes WITH the trend, not against it

---

## The Core Insight

### Why Divergence Confirms Momentum

When EURUSD rises AND USDCHF doesn't fall proportionally:

1. **Normal correlation:** USD weak → EURUSD up, USDCHF down (inverse)
2. **Divergence:** EURUSD up > expected → EUR has REAL strength
3. **Signal:** This momentum is driven by EUR, not just USD

### Mathematical Basis

```python
# Normalize both to z-scores for comparison
z_eurusd = (EMA_EURUSD - mean) / std
z_usdchf_inv = (1/EMA_USDCHF - mean) / std

# Spread = difference
spread = z_eurusd - z_usdchf_inv

# When spread > threshold AND growing → EUR intrinsic strength
```

---

## Entry System

### Entry Conditions (ALL must be true)

| Condition | Description |
|-----------|-------------|
| Spread > threshold | z-score spread above 0.5 (configurable) |
| Spread momentum | Spread growing for N consecutive bars |
| KAMA filter | Price > KAMA (optional trend confirmation) |
| Filters pass | Time, day, ATR, SL pips filters if enabled |

### Exit Conditions

| Exit Type | Description |
|-----------|-------------|
| Stop Loss | Entry - (ATR × SL multiplier) |
| Take Profit | Entry + (ATR × TP multiplier) |

---

## Indicators

### SpreadDivergence (Custom)

```python
class SpreadDivergence(bt.Indicator):
    """
    Calculates normalized spread between two correlated pairs.
    
    Lines:
    - spread: Raw z-score spread
    - spread_ema: Smoothed spread
    - signal: Entry signal markers
    """
```

**Calculation:**
1. EMA(HL2) for both pairs
2. Invert reference if needed (1/USDCHF)
3. Z-score normalize both (50-bar lookback)
4. Spread = z(primary) - z(reference_inv)

### KAMA (from lib/indicators.py)

Standard Kaufman Adaptive Moving Average for trend filter.

---

## Configuration Parameters

### Spread Divergence Settings

| Parameter | Default | Description |
|-----------|---------|-------------|
| `spread_ema_period` | 20 | EMA period for HL2 |
| `spread_zscore_period` | 50 | Lookback for z-score calculation |
| `spread_entry_threshold` | 0.5 | Min spread for entry (z-score) |
| `spread_momentum_bars` | 3 | Spread must grow N bars |
| `invert_reference` | True | Invert reference (USDCHF → 1/USDCHF) |

### ATR Settings

| Parameter | Default | Description |
|-----------|---------|-------------|
| `atr_length` | 14 | ATR period |
| `atr_sl_multiplier` | 3.0 | SL = ATR × this |
| `atr_tp_multiplier` | 8.0 | TP = ATR × this |

### Filters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `use_kama_filter` | True | Require price > KAMA |
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
    ...
}
```

### Inversion Logic

For EURUSD_GEMINI (trading EURUSD, reference USDCHF):
- USDCHF needs inversion (1/price) to compare
- `invert_reference=True`

For USDCHF_GEMINI (trading USDCHF, reference EURUSD):
- EURUSD doesn't need inversion
- `invert_reference=False`

### Log Format

```
datetime,symbol,direction,entry_price,sl,tp,atr,spread,spread_ema,spread_momentum,kama,exit_reason,exit_price,pnl,bars_held
```

---

## Validation Criteria

### Minimum Requirements

| Metric | Minimum | Status |
|--------|---------|--------|
| Profit Factor | >= 1.5 | Pending |
| Sharpe Ratio | >= 0.7 | Pending |
| Max Drawdown | < 10% | Pending |
| Trades/year | ~100+ | Pending |

### Discard Criteria

If with default parameters:
- < 100 trades/year with PF > 1.05 → DISCARD

### Next Steps

1. Run initial backtest: `python run_backtest.py EURUSD_GEMINI`
2. Analyze spread distribution and entry quality
3. Optimize threshold and momentum parameters
4. If viable → implement USDCHF_GEMINI variant

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

**Current Status:** 🧪 Initial Development - Awaiting First Backtest

### Change Log

| Date | Change |
|------|--------|
| 2026-02-06 | Initial implementation |
