# 🌊 SEDNA Strategy

**Type:** Pattern Recognition / Adaptive Momentum Breakout  
**Assets:** ETFs (DIA), extensible to Forex  
**Direction:** Long Only  
**Base:** Derived from KOI with adaptive improvements

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Differences from KOI](#differences-from-koi)
3. [The 3-Phase State Machine](#the-3-phase-state-machine)
4. [Main Indicators](#main-indicators)
5. [Entry Conditions](#entry-conditions)
6. [Exit Logic](#exit-logic)
7. [Risk Management](#risk-management)
8. [Configuration Parameters](#configuration-parameters)
9. [Current Configuration (DIA)](#current-configuration-dia)

---

## Overview

SEDNA is a **pattern-based strategy with adaptive momentum** that evolves from KOI. It identifies bullish engulfing candles confirmed by adaptive trend (KAMA) and optional momentum (CCI on HL2).

### Design Philosophy

The strategy seeks **market adaptability** through:

1. **KAMA (Kaufman's Adaptive Moving Average)**: Automatically adapts to market volatility
2. **CCI on HL2**: Momentum calculated on the midpoint of the range (more stable than HLC3)
3. **Averaged ATR**: Smoothed volatility filter to avoid noise

---

## Differences from KOI

| Component | KOI | SEDNA |
|-----------|-----|-------|
| **Trend Filter** | 5 ascending EMAs | KAMA vs EMA(HL2) |
| **Momentum** | CCI on HLC3 | CCI on HL2 (optional, can be disabled) |
| **ATR Filter** | Instantaneous ATR | Averaged ATR (N periods) |
| **Adaptability** | Fixed | Adaptive (KAMA) |

### Why KAMA?

**Kaufman's Adaptive Moving Average** adjusts its speed based on the *Efficiency Ratio*:

- **Trending market** → Faster KAMA (similar to short EMA)
- **Ranging market** → Slower KAMA (similar to long EMA)

```
Efficiency Ratio = |Change| / Volatility
SC = (ER × (fast_sc - slow_sc) + slow_sc)²
KAMA = KAMA[-1] + SC × (Price - KAMA[-1])
```

---

## The 3-Phase State Machine

```
┌─────────────┐   Pattern +    ┌──────────────────┐
│  SCANNING   │   KAMA + CCI   │ WAITING_BREAKOUT │
│  (Phase 1)  │───────────────▶│    (Phase 2)     │
└─────────────┘                └────────┬─────────┘
       ▲                                │
       │                          Price Breaks
       │ Timeout                  Pattern High
       │ (N candles)                    │
       │                                ▼
       │                       ┌─────────────┐
       └───────────────────────│   ENTRY     │
                               │  (Phase 3)  │
                               └─────────────┘
```

### Phase 1: SCANNING

The system monitors for entry conditions:

```python
def _check_entry_conditions(self, dt: datetime) -> bool:
    # 1. No existing position
    if self.position or self.order:
        return False
    
    # 2. Time Filter (optional)
    if not check_time_filter(dt, ...):
        return False
    
    # 3. Bullish Engulfing Pattern
    if not self._check_bullish_engulfing():
        return False
    
    # 4. KAMA Condition: EMA(HL2) > KAMA(HL2)
    if not self._check_kama_condition():
        return False
    
    # 5. CCI > Threshold (if enabled)
    if not self._check_cci_condition():
        return False
    
    return True
```

### Phase 2: WAITING_BREAKOUT

After pattern detection, we wait for breakout confirmation:

```python
self.pattern_detected_bar = current_bar
offset = breakout_level_offset_pips × pip_value
self.breakout_level = High[0] + offset
self.pattern_atr = average_atr  # Averaged ATR
self.state = "WAITING_BREAKOUT"
```

**State exit conditions:**
- ✅ **Breakout**: `High > breakout_level` → **ENTRY**
- ❌ **Timeout**: `bars_since > breakout_window_candles` → **SCANNING**

### Phase 3: ENTRY

Entry execution with final filters:

```python
# ATR Filter (uses averaged ATR)
if not check_atr_filter(atr_avg, atr_min, atr_max, use_atr_filter):
    return

# Calculate levels
entry_price = Close[0]
stop_level = entry_price - (atr_avg × atr_sl_multiplier)
take_level = entry_price + (atr_avg × atr_tp_multiplier)

# SL Pips Filter
sl_pips = |entry_price - stop_level| / pip_value
if not check_sl_pips_filter(sl_pips, min, max, use_filter):
    return

# Position sizing & execution
self.buy(size=calculated_size)
```

---

## Main Indicators

### 1. KAMA (Kaufman's Adaptive Moving Average)

```python
class KAMA(bt.Indicator):
    params = (
        ('period', 12),   # Efficiency ratio period
        ('fast', 2),      # Fast smoothing constant
        ('slow', 30),     # Slow smoothing constant
    )
```

**Calculation:**
```
Change = |Price[0] - Price[-period]|
Volatility = Σ|Price[-i] - Price[-i-1]| for i in range(period)
ER = Change / Volatility

fast_sc = 2 / (fast + 1)
slow_sc = 2 / (slow + 1)
SC = (ER × (fast_sc - slow_sc) + slow_sc)²

KAMA = KAMA[-1] + SC × (Price - KAMA[-1])
```

### 2. CCI on HL2

Unlike KOI which uses HLC3 (typical), SEDNA calculates CCI on HL2:

```python
def _calculate_cci_hl2(self) -> float:
    HL2 = (High + Low) / 2
    SMA_HL2 = SMA(HL2, period)
    Mean_Deviation = Σ|HL2[i] - SMA_HL2| / period
    
    CCI = (HL2 - SMA_HL2) / (0.015 × Mean_Deviation)
    return CCI
```

### 3. Averaged ATR

```python
def _get_average_atr(self) -> float:
    if len(self.atr_history) < atr_avg_period:
        return ATR[0]
    
    recent_atr = atr_history[-atr_avg_period:]
    return sum(recent_atr) / len(recent_atr)
```

---

## Entry Conditions

### Pattern Condition: Bullish Engulfing

```python
def _check_bullish_engulfing(self) -> bool:
    # Previous candle: bearish (Close < Open)
    prev_bearish = Close[-1] < Open[-1]
    
    # Current candle: bullish (Close > Open)
    curr_bullish = Close[0] > Open[0]
    
    # Engulfing: current body engulfs previous
    engulfs = Open[0] <= Close[-1] and Close[0] >= Open[-1]
    
    return prev_bearish and curr_bullish and engulfs
```

### Trend Condition: KAMA

```python
def _check_kama_condition(self) -> bool:
    # EMA(HL2) must be above KAMA(HL2)
    return EMA(HL2)[0] > KAMA(HL2)[0]
```

**Note:** With `hl2_ema_period=1`, we use raw HL2 vs KAMA.

### Momentum Condition: CCI (Optional)

```python
def _check_cci_condition(self) -> bool:
    if not use_cci_filter:
        return True  # Disabled = always passes
    
    cci = self._calculate_cci_hl2()
    return cci_threshold < cci < cci_max_threshold
```

---

## Exit Logic

### 1. Stop Loss and Take Profit (OCA Orders)

```python
# On entry execution:
stop_order = self.sell(
    exectype=bt.Order.Stop,
    price=stop_level,
    oco=limit_order
)
limit_order = self.sell(
    exectype=bt.Order.Limit,
    price=take_level,
    oco=stop_order
)
```

**OCA (One-Cancels-All):** When one order executes, the other is automatically cancelled.

### 2. KAMA Reversal Exit (Optional)

When `use_kama_exit=True`, the strategy can exit early if the trend reverses:

```python
def _check_kama_exit_condition(self) -> bool:
    # KAMA > EMA = trend reversed = exit signal
    # This is the INVERSE of entry condition
    return KAMA(HL2) > EMA(HL2)
```

**Exit Flow:**
```
Position Open + use_kama_exit=True
    |
    v
next() at candle close
    |
    +-- KAMA > EMA? (trend lost)
            |
            +-- YES: Cancel SL/TP orders
            |        Close position at market
            |        exit_reason = "KAMA_REVERSAL"
            |
            +-- NO: Continue waiting for SL/TP
```

**Key Points:**
- Evaluated at candle close (values are final)
- Cancels pending OCA orders before closing
- Tracks exit reason for reporting

### Level Calculation

```
Stop Loss   = Entry - (ATR_avg × atr_sl_multiplier)
Take Profit = Entry + (ATR_avg × atr_tp_multiplier)
```

---

## Risk Management

### Position Sizing

```python
bt_size = calculate_position_size(
    entry_price=entry_price,
    stop_loss=stop_level,
    equity=broker.get_value(),
    risk_percent=risk_percent,  # e.g., 0.5%
    pair_type='ETF',
    lot_size=lot_size,
    margin_pct=margin_pct,
)
```

### Safety Filters

| Filter | Description | Current Status |
|--------|-------------|----------------|
| **Time Filter** | Only trade during specific hours | ❌ Disabled |
| **SL Pips Filter** | Limit SL range in pips | ❌ Disabled |
| **ATR Filter** | Volatility within range | ✅ Enabled (0.00-0.80) |

---

## Configuration Parameters

### KAMA Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `kama_period` | 12 | Period for Efficiency Ratio |
| `kama_fast` | 2 | Fast smoothing constant |
| `kama_slow` | 30 | Slow smoothing constant |
| `hl2_ema_period` | 1 | EMA period to compare with KAMA (1 = raw HL2) |

### CCI Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `use_cci_filter` | True | Enable/disable CCI |
| `cci_period` | 20 | Period for CCI |
| `cci_threshold` | 100 | Minimum threshold |
| `cci_max_threshold` | 999 | Maximum threshold |

### ATR & SL/TP Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `atr_length` | 10 | ATR period |
| `atr_sl_multiplier` | 2.0 | Multiplier for Stop Loss |
| `atr_tp_multiplier` | 10.0 | Multiplier for Take Profit |
| `atr_avg_period` | 20 | Periods to average ATR (filter) |

### Breakout Window

| Parameter | Default | Description |
|-----------|---------|-------------|
| `use_breakout_window` | True | Enable breakout window |
| `breakout_window_candles` | 3 | Max candles to wait for breakout |
| `breakout_level_offset_pips` | 5.0 | Offset above pattern High |

### Exit Conditions

| Parameter | Default | Description |
|-----------|---------|-------------|
| `use_kama_exit` | False | Enable KAMA reversal exit |

---

## Current Configuration (DIA)

```python
'DIA_SEDNA': {
    'active': True,
    'strategy_name': 'SEDNA',
    'asset_name': 'DIA',
    'data_path': 'data/DIA_5m_5Yea.csv',
    
    'params': {
        # KAMA settings
        'kama_period': 10,
        'kama_fast': 2,
        'kama_slow': 30,
        'hl2_ema_period': 1,
        
        # CCI DESHABILITADO
        'use_cci_filter': False,
        'cci_period': 20,
        'cci_threshold': 100,
        
        # ATR
        'atr_length': 10,
        'atr_sl_multiplier': 2.0,
        'atr_tp_multiplier': 10.0,
        
        # Breakout Window
        'use_breakout_window': True,
        'breakout_window_candles': 3,
        'breakout_level_offset_pips': 2.0,
        
        # ATR Filter HABILITADO
        'use_atr_filter': True,
        'atr_min': 0.00,
        'atr_max': 0.80,
        'atr_avg_period': 20,
        
        # ETF Config
        'pip_value': 0.01,
        'lot_size': 1,
        'is_etf': True,
        'margin_pct': 20.0,
        'risk_percent': 0.005,  # 0.5%
    }
}
```

### Current Configuration Summary

| Component | Status |
|-----------|--------|
| **KAMA** | ✅ Active (10, 2, 30) |
| **CCI** | ❌ Disabled |
| **Breakout Window** | ✅ 3 candles, +2 pips offset |
| **ATR Filter** | ✅ Avg 20 periods, max 0.80 |
| **KAMA Exit** | ❌ Disabled (for A/B testing) |
| **Time Filter** | ❌ Disabled |
| **SL Pips Filter** | ❌ Disabled |
| **Risk per Trade** | 0.5% |
| **SL/TP Ratio** | 1:5 (2x ATR : 10x ATR) |

---

## Report Metrics

SEDNA generates automatic reports with the following metrics:

- **Win Rate**: Percentage of winning trades
- **Profit Factor**: Gross Profit / Gross Loss
- **Sharpe Ratio**: Risk-adjusted return
- **Sortino Ratio**: Similar to Sharpe, only considers downside volatility
- **Max Drawdown**: Maximum decline from peak
- **CAGR**: Compound Annual Growth Rate
- **Calmar Ratio**: CAGR / Max Drawdown
- **Yearly Statistics**: Breakdown by year

**Exit Reasons Tracked:**
- `STOP_LOSS` - Hit stop loss level
- `TAKE_PROFIT` - Hit take profit level
- `KAMA_REVERSAL` - KAMA crossed above EMA (if enabled)

---

## Changelog

| Date | Version | Changes |
|------|---------|---------|
| 2026-01-24 | 1.1 | Add KAMA reversal exit condition (use_kama_exit) |
| 2026-01-24 | 1.0 | Initial version derived from KOI |

---

*Documentation generated for TradingSystem - SEDNA Strategy*
