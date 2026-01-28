# GLIESE Strategy

**Type:** HTF Range Detection + Mean Reversion + Pullback Entry  
**Assets:** USDCHF, USDCAD, EURUSD (where SEDNA does not perform well)  
**Direction:** Long Only  
**Base:** Complementary to SEDNA - Range/Compression instead of Trend

---

## Table of Contents

1. [Overview](#overview)
2. [Design Philosophy](#design-philosophy)
3. [Entry System (4 Phases)](#entry-system-4-phases)
4. [Main Indicators](#main-indicators)
5. [Exit Logic](#exit-logic)
6. [Risk Management](#risk-management)
7. [Configuration Parameters](#configuration-parameters)
8. [Differences vs SEDNA](#differences-vs-sedna)

---

## Overview

GLIESE is a **mean reversion strategy** designed to complement the trend-following strategies (SunsetOgle, KOI, SEDNA) in the portfolio.

### Core Concept

While Ogle/KOI/SEDNA look for **trending markets**, GLIESE looks for **ranging/compressed markets** and trades the bounce from range extremes back to fair value.

```
SEDNA:  Trend -> Pullback -> Breakout -> Entry (with trend)
GLIESE: Range -> Extension -> Reversal -> Pullback -> Entry (against extension)
```

### Target Assets

| Asset | Why GLIESE? |
|-------|-------------|
| USDCHF | SEDNA does not perform well |
| USDCAD | SEDNA does not perform well |
| EURUSD | SEDNA does not perform well |

### Expected Correlation

- **Negative/Low correlation** with Ogle/KOI/SEDNA
- Diversification benefit: GLIESE profits when trend strategies struggle (ranging markets)

---

## Design Philosophy

### Mean Reversion Structural

```
┌─────────────────────────────────────────────────────────────────┐
│                         HTF (15m)                               │
│                                                                 │
│   Upper Band ─────────────────────────────────────────────────  │
│                                                                 │
│   KAMA (HL2) ═══════════════════════════════════════════════   │ -- Fair Value
│                                                                 │
│   Lower Band ─────────────────────────────────────────────────  │
│                          ▲                                      │
│                          │ Extension                            │
│                    ┌─────┴─────┐                                │
│                    │   ENTRY   │                                │
│                    │   ZONE    │                                │
│                    └───────────┘                                │
└─────────────────────────────────────────────────────────────────┘
```

**Key Principle:** In a range, price oscillates around KAMA. When price extends too far below KAMA, it tends to revert back.

### Why This Works

1. **Range = Fair Value Zone**: KAMA represents consensus value
2. **Extension = Overreaction**: Price below band = temporarily oversold
3. **Reversion = Return to Equilibrium**: Statistical tendency to mean-revert
4. **Confirmation = Safety**: Wait for reversal + pullback to avoid catching falling knives

---

## Entry System (4 Phases)

### State Machine Diagram

```
┌─────────────────────┐
│     SCANNING        │ -- Initial state
│  (Looking for range)│
└──────────┬──────────┘
           │
           │ HTF confirms range:
           │ • ER < er_max_threshold
           │ • ADXR < adxr_max_threshold
           │ • KAMA slope < k × ATR
           ▼
┌─────────────────────┐
│   RANGE_DETECTED    │
│ (Range confirmed)   │
└──────────┬──────────┘
           │
           │ Price < KAMA - band_mult × ATR
           │ (Extension below lower band)
           ▼
┌─────────────────────┐
│  EXTENSION_BELOW    │
│ (Touched lower band)│ -- Wait minimum bars
└──────────┬──────────┘
           │
           │ Price > KAMA - band_mult × ATR
           │ (Crossed back above lower band)
           ▼
┌─────────────────────┐
│  REVERSAL_DETECTED  │
│ (Turn confirmed)    │
└──────────┬──────────┘
           │
           │ Pullback detected +
           │ Break of micro-swing
           ▼
┌─────────────────────┐
│   🎯 ENTRY SIGNAL   │
└─────────────────────┘
```

### Phase 1: Range Detection (HTF 15m)

Triple confirmation for ranging market:

```python
def _check_range_conditions(self) -> bool:
    """
    All three conditions must be met for valid range.
    """
    # 1. Efficiency Ratio LOW (no directional momentum)
    er_value = calculate_er(closes, htf_er_period)
    if er_value >= htf_er_max_threshold:  # e.g., >= 0.30
        return False  # Too trending
    
    # 2. ADXR LOW (no trend strength)
    adxr_value = calculate_adxr(highs, lows, closes, adxr_period)
    if adxr_value >= adxr_max_threshold:  # e.g., >= 25
        return False  # Too trending
    
    # 3. KAMA Slope FLAT (relative to ATR)
    kama_slope = abs(KAMA[0] - KAMA[kama_slope_lookback])
    slope_threshold = kama_slope_atr_mult * ATR[0]
    if kama_slope >= slope_threshold:  # e.g., >= 0.3 × ATR
        return False  # KAMA moving too fast
    
    return True  # Range confirmed
```

**Why Triple Confirmation?**
- ER low + ADXR high = possible false signal
- ER low + KAMA moving = consolidation before breakout
- All three low = genuine ranging market

### Phase 2: Extension Detection

```python
def _check_extension_below(self) -> bool:
    """
    Price has extended below the lower band.
    """
    lower_band = KAMA - (band_atr_mult * ATR)
    
    if current_close < lower_band:
        self.extension_bar_count += 1
        self.extension_min_price = min(self.extension_min_price, current_low)
        return True
    
    return False
```

**Extension Parameters:**
- `band_atr_mult`: 1.5 (default) - Lower band = KAMA - 1.5×ATR
- `extension_min_bars`: 2 - Minimum bars below band to validate
- `extension_max_bars`: 20 - Maximum bars (if exceeded = breakdown, cancel)

### Phase 3: Reversal Detection

```python
def _check_reversal(self) -> bool:
    """
    Price crossed back ABOVE the lower band.
    Confirms the range held and extension is reversing.
    """
    lower_band = KAMA - (band_atr_mult * ATR)
    
    # Must have been in extension for minimum bars
    if self.extension_bar_count < extension_min_bars:
        return False
    
    # Check if price crossed back above
    if current_close >= lower_band:
        self.reversal_confirmed = True
        return True
    
    return False
```

### Phase 4: Pullback + Entry

Uses same pullback logic as SEDNA:

```python
def _check_pullback_entry(self) -> bool:
    """
    After reversal, wait for pullback and breakout.
    Similar to SEDNA but looking for different pattern.
    """
    result = detect_pullback(
        highs=price_history['highs'],
        lows=price_history['lows'],
        closes=price_history['closes'],
        kama_values=price_history['kama'],
        min_bars=pullback_min_bars,
        max_bars=pullback_max_bars,
    )
    
    if result['valid']:
        # Set breakout level
        self.breakout_level = result['breakout_level'] + offset
        return True
    
    return False
```

---

## Main Indicators

### 1. KAMA (Kaufman's Adaptive Moving Average)

Same as SEDNA - applied to HL2:

```python
KAMA = KAMA[-1] + SC² × (Price - KAMA[-1])

Where:
  SC = ER × (fast_sc - slow_sc) + slow_sc
  ER = |Change| / Volatility
```

**Role in GLIESE:** Fair value / center line of range

### 2. Efficiency Ratio (ER)

```python
ER = |Close[0] - Close[-period]| / Sum(|Close[-i] - Close[-i-1]|)
```

**Role in GLIESE:** 
- SEDNA: ER HIGH = trend = allow entry
- GLIESE: ER LOW = range = allow entry

### 3. ADXR (Average Directional Index Rating) - NEW

```python
def calculate_adxr(highs, lows, closes, period=14, lookback=14):
    """
    ADXR = (ADX[0] + ADX[lookback]) / 2
    
    Smoother version of ADX, reduces whipsaws.
    """
    adx = calculate_adx(highs, lows, closes, period)
    adxr = (adx[-1] + adx[-1 - lookback]) / 2
    return adxr
```

**Interpretation:**
- ADXR < 20: No trend (range)
- ADXR 20-25: Weak trend / transition
- ADXR > 25: Trending

### 4. KAMA Slope (Relative to ATR)

```python
def calculate_kama_slope_normalized(kama_values, atr_values, lookback=5):
    """
    Slope normalized by ATR for cross-asset comparison.
    """
    slope = abs(kama_values[-1] - kama_values[-1 - lookback])
    normalized = slope / atr_values[-1]
    return normalized
```

**Threshold:** `kama_slope_atr_mult` (default 0.3)
- Slope < 0.3×ATR = flat (range)
- Slope >= 0.3×ATR = moving (potential trend)

### 5. Bands (KAMA ± k×ATR)

```python
upper_band = KAMA + (band_atr_mult * ATR)
lower_band = KAMA - (band_atr_mult * ATR)
```

**Default:** `band_atr_mult = 1.5`

---

## Exit Logic

### Stop Loss

```python
stop_loss = entry_price - (atr_sl_multiplier * ATR)
```

**Position:** Below the extension minimum (technical level)

### Take Profit

```python
take_profit = entry_price + (atr_tp_multiplier * ATR)
```

**Target:** Near KAMA (fair value), slightly before to ensure fill

### Cancellation Conditions

```python
def _should_cancel_setup(self) -> bool:
    """
    Cancel if range conditions break BEFORE entry.
    Once position is open, let SL/TP handle it.
    """
    # Range broke - ER surged
    if calculate_er(...) > er_cancel_threshold:
        return True
    
    # Extension took too long - probably breakdown
    if self.extension_bar_count > extension_max_bars:
        return True
    
    return False
```

---

## Risk Management

### Position Sizing

Same as other strategies:

```python
risk_amount = equity * risk_percent
price_risk = entry_price - stop_loss
position_size = risk_amount / price_risk
```

### Single Position Rule

**One position per GLIESE instance** - same as Ogle/KOI/SEDNA:
- Cannot open new position until current one closes
- Prevents averaging down (dangerous in mean-reversion)

---

## Configuration Parameters

### Range Detection (HTF 15m)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `use_htf_range_filter` | True | Enable HTF range detection |
| `htf_timeframe_minutes` | 15 | HTF for range analysis |
| `htf_er_period` | 10 | ER calculation period |
| `htf_er_max_threshold` | 0.30 | Max ER to consider range (inverted vs SEDNA) |

### ADXR Filter

| Parameter | Default | Description |
|-----------|---------|-------------|
| `use_adxr_filter` | True | Enable ADXR filter |
| `adxr_period` | 14 | ADX calculation period |
| `adxr_lookback` | 14 | Lookback for ADXR averaging |
| `adxr_max_threshold` | 25 | Max ADXR to consider range |

### KAMA Slope Filter

| Parameter | Default | Description |
|-----------|---------|-------------|
| `kama_slope_lookback` | 5 | Bars to measure slope |
| `kama_slope_atr_mult` | 0.3 | Max slope as multiple of ATR |

### Bands

| Parameter | Default | Description |
|-----------|---------|-------------|
| `band_atr_period` | 14 | ATR period for bands |
| `band_atr_mult` | 1.5 | Band width (KAMA ± k×ATR) |

### Extension Detection

| Parameter | Default | Description |
|-----------|---------|-------------|
| `extension_min_bars` | 2 | Min bars below band to validate |
| `extension_max_bars` | 20 | Max bars (cancel if exceeded) |

### Z-Score Filter (Optional)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `use_zscore_filter` | False | Enable Z-Score depth filter |
| `zscore_min_depth` | -2.0 | Min Z-Score to validate entry |

### Pullback Detection

| Parameter | Default | Description |
|-----------|---------|-------------|
| `use_pullback_filter` | True | Enable pullback confirmation |
| `pullback_min_bars` | 1 | Min bars for pullback |
| `pullback_max_bars` | 4 | Max bars for pullback |

### Cancellation

| Parameter | Default | Description |
|-----------|---------|-------------|
| `er_cancel_threshold` | 0.50 | Cancel if ER exceeds (trend starting) |

### SL/TP

| Parameter | Default | Description |
|-----------|---------|-------------|
| `atr_length` | 14 | ATR period |
| `atr_sl_multiplier` | 2.0 | SL = entry - X×ATR |
| `atr_tp_multiplier` | 3.0 | TP = entry + X×ATR |

### Standard Filters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `use_time_filter` | True | Filter by allowed hours |
| `allowed_hours` | [...] | Hours to allow entries |
| `use_day_filter` | True | Filter by allowed days |
| `allowed_days` | [0,1,2,3,4] | Days to allow (Mon-Fri) |
| `use_sl_pips_filter` | True | Filter by SL size |
| `sl_pips_min` | 5.0 | Min SL in pips |
| `sl_pips_max` | 15.0 | Max SL in pips |

---

## Differences vs SEDNA

| Aspect | SEDNA | GLIESE |
|--------|-------|--------|
| **Market Type** | Trending | Ranging |
| **ER Condition** | ER >= threshold (HIGH) | ER < threshold (LOW) |
| **ADXR** | Not used | ADXR < threshold (LOW) |
| **Entry Direction** | With trend | Counter-extension |
| **Target** | Trend continuation | Reversion to mean |
| **Assets** | USDJPY, EURJPY, DIA | USDCHF, USDCAD, EURUSD |
| **Correlation** | Positive with Ogle/KOI | Negative/Low with Ogle/KOI |

---

## Future Improvements

1. **Dynamic band width**: Adjust `band_atr_mult` based on recent range width
2. **Multi-touch validation**: Require N touches of band before entry
3. **Partial profit taking**: Scale out at KAMA, let runner go to upper band
4. **Session-based optimization**: Different parameters for London/NY sessions

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-01-28 | Initial design document |

