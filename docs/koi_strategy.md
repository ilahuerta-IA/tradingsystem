# 🐟 KOI Strategy

**Type:** Pattern Recognition / Momentum Breakout  
**Assets:** Forex (EURUSD, USDJPY) & ETFs (DIA, TLT)  
**Direction:** Long Only  

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [The 3-Phase State Machine](#the-3-phase-state-machine)
3. [Entry Conditions](#entry-conditions)
4. [Exit Logic](#exit-logic)
5. [Risk Management](#risk-management)
6. [Configuration Parameters](#configuration-parameters)
7. [Asset-Specific Configurations](#asset-specific-configurations)

---

## Overview

KOI is a **pattern-based momentum strategy** that identifies bullish engulfing candles when confirmed by trend strength (5 EMAs ascending) and momentum (CCI). Unlike simple pattern scanners, it implements a **breakout confirmation window** to avoid false patterns.

### Why Bullish Engulfing + Confirmation?

Candlestick patterns alone have low reliability. KOI adds multiple confirmation layers:

1. **Pattern Quality**: True bullish engulfing (current candle completely engulfs previous)
2. **Trend Alignment**: All 5 EMAs must be individually ascending
3. **Momentum Filter**: CCI must exceed threshold (strong buying pressure)
4. **Breakout Confirmation**: Price must break pattern high within N candles

This multi-layer filtering dramatically reduces false signals.

---

## The 3-Phase State Machine

```
┌─────────────┐   Pattern +    ┌──────────────────┐
│  SCANNING   │   EMAs + CCI   │ WAITING_BREAKOUT │
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

The system monitors for a valid pattern + conditions. All must be met **simultaneously**:

```python
def _check_entry_conditions(self, dt: datetime) -> bool:
    # 1. No existing position
    if self.position or self.order:
        return False
    
    # 2. Time Filter (optional)
    if not check_time_filter(dt, self.p.allowed_hours, self.p.use_time_filter):
        return False
    
    # 3. Bullish Engulfing Pattern
    if not self._check_bullish_engulfing():
        return False
    
    # 4. All 5 EMAs Ascending
    if not self._check_emas_ascending():
        return False
    
    # 5. CCI > Threshold
    if not self._check_cci_condition():
        return False
    
    return True
```

**Result:** If all conditions pass → State changes to `WAITING_BREAKOUT`

### Phase 2: WAITING_BREAKOUT

After pattern detection, we wait for price confirmation:

```python
def _setup_breakout_window(self):
    self.pattern_detected_bar = current_bar
    offset = self.p.breakout_level_offset_pips * self.p.pip_value
    self.breakout_level = self.data.high[0] + offset  # Pattern high + offset
    self.pattern_atr = self.atr[0]   # Store ATR at pattern time
    self.pattern_cci = self.cci[0]   # Store CCI at pattern time
    self.state = "WAITING_BREAKOUT"
```

**Monitoring Logic:**
```python
# Check timeout (window expired)
bars_since = current_bar - self.pattern_detected_bar
if bars_since > self.p.breakout_window_candles:  # Default: 3
    self._reset_breakout_state()  # Back to SCANNING
    return

# Check breakout (success)
if self.data.high[0] > self.breakout_level:
    self._execute_entry()  # Enter trade!
    return
```

**Parameters:**
- `breakout_level`: Pattern high + offset (in pips)
- `breakout_window_candles`: Maximum bars to wait (default: 3)
- Pattern ATR/CCI preserved for entry execution

### Phase 3: ENTRY (Execution)

When breakout is confirmed, execute with stored pattern values:

```python
def _execute_entry(self, dt, atr_now, cci_now):
    entry_price = self.data.close[0]
    
    # ATR-based SL/TP
    self.stop_level = entry_price - (atr_now * self.p.atr_sl_multiplier)
    self.take_level = entry_price + (atr_now * self.p.atr_tp_multiplier)
    
    # Position sizing
    bt_size = calculate_position_size(
        entry_price=entry_price,
        stop_loss=self.stop_level,
        equity=self.broker.get_value(),
        risk_percent=self.p.risk_percent,
        pair_type=pair_type,  # 'ETF', 'JPY', or 'STANDARD'
        ...
    )
    
    self.order = self.buy(size=bt_size)
```

---

## Entry Conditions

### 1. Bullish Engulfing Pattern

A true bullish engulfing requires:

```python
def _check_bullish_engulfing(self) -> bool:
    # Previous candle must be bearish (red)
    prev_open = self.data.open[-1]
    prev_close = self.data.close[-1]
    if prev_close >= prev_open:
        return False
    
    # Current candle must be bullish (green)
    curr_open = self.data.open[0]
    curr_close = self.data.close[0]
    if curr_close <= curr_open:
        return False
    
    # Current body must engulf previous body
    if curr_open > prev_close or curr_close < prev_open:
        return False
    
    return True
```

**Visual:**
```
       ┌───┐
    ┌──┤   │
    │  └───┘  ← Previous (Red)
    │
┌───┴───┐
│       │
│       │     ← Current (Green) - ENGULFS previous
│       │
└───────┘
```

### 2. Five EMAs Ascending

All 5 EMAs must be individually rising:

```python
def _check_emas_ascending(self) -> bool:
    emas = [self.ema_1, self.ema_2, self.ema_3, self.ema_4, self.ema_5]
    for ema in emas:
        if ema[0] <= ema[-1]:  # Current <= Previous
            return False
    return True
```

**EMA Periods:** 10, 20, 40, 80, 120

This ensures trend strength across multiple timeframe perspectives.

### 3. CCI Momentum Filter

```python
def _check_cci_condition(self) -> bool:
    cci_val = self.cci[0]
    if cci_val <= self.p.cci_threshold:      # Default: 110
        return False
    if cci_val >= self.p.cci_max_threshold:  # Default: 999 (disabled)
        return False
    return True
```

- **Minimum (110)**: Confirms strong buying pressure
- **Maximum (999)**: Optional filter for overbought (disabled by default)

### 4. Breakout Confirmation (Optional)

```python
# With breakout window enabled (default):
breakout_level = pattern_high + (offset_pips * pip_value)

# Price must break above this level within N candles
if self.data.high[0] > self.breakout_level:
    # Execute entry
```

Can be disabled via `use_breakout_window=False` for immediate pattern entry.

---

## Exit Logic

### Stop Loss (ATR-Based)
```python
self.stop_level = entry_price - (atr * self.p.atr_sl_multiplier)  # Default: 2.0x ATR
```

### Take Profit (ATR-Based)
```python
self.take_level = entry_price + (atr * self.p.atr_tp_multiplier)  # Default: 6.0x ATR
```

### Risk-Reward Ratio
With SL = 2.0× ATR and TP = 6.0× ATR:
```
Risk-Reward = 6.0 / 2.0 = 3.0:1
```
This means we need only ~33% win rate to be profitable.

### OCA (One-Cancels-All) Orders

When entry fills, protective orders are placed:

```python
# Both orders are linked - when one fills, the other cancels
self.stop_order = self.sell(
    exectype=bt.Order.Stop,
    price=self.stop_level,
    oco=self.limit_order
)
self.limit_order = self.sell(
    exectype=bt.Order.Limit,
    price=self.take_level,
    oco=self.stop_order
)
```

---

## Risk Management

### Position Sizing

KOI uses the unified `lib/position_sizing.py` module that handles:

| Pair Type | Logic |
|-----------|-------|
| **STANDARD** (EURUSD, etc.) | Direct USD calculation |
| **JPY** (USDJPY, EURJPY) | JPY pip value conversion |
| **ETF** (DIA, TLT, etc.) | Margin-based sizing |

```python
bt_size = calculate_position_size(
    entry_price=entry_price,
    stop_loss=self.stop_level,
    equity=self.broker.get_value(),
    risk_percent=self.p.risk_percent,  # Default: 0.5%
    pair_type=pair_type,
    lot_size=self.p.lot_size,
    jpy_rate=self.p.jpy_rate,
    pip_value=self.p.pip_value,
    margin_pct=self.p.margin_pct,  # ETF margin (3.33%)
)
```

### Optional Filters

KOI supports additional filters via `use_xxx` flags:

| Filter | Parameters | Purpose |
|--------|------------|---------|
| `use_time_filter` | `allowed_hours` | Restrict trading hours |
| `use_atr_filter` | `atr_min`, `atr_max` | Volatility range |
| `use_sl_pips_filter` | `sl_pips_min`, `sl_pips_max` | Stop size range |

---

## Configuration Parameters

### Complete Parameter Reference

| Parameter | Default | Description |
|-----------|---------|-------------|
| **EMA Settings** |||
| `ema_1_period` | 10 | Fastest EMA |
| `ema_2_period` | 20 | Fast EMA |
| `ema_3_period` | 40 | Medium EMA |
| `ema_4_period` | 80 | Slow EMA |
| `ema_5_period` | 120 | Slowest EMA |
| **CCI Settings** |||
| `cci_period` | 20 | CCI calculation period |
| `cci_threshold` | 110 | Minimum CCI for entry |
| `cci_max_threshold` | 999 | Maximum CCI (999=disabled) |
| **Breakout Window** |||
| `use_breakout_window` | True | Enable breakout confirmation |
| `breakout_window_candles` | 3 | Max bars to wait for breakout |
| `breakout_level_offset_pips` | 2.0 | Offset above pattern high |
| **Exit Settings** |||
| `atr_length` | 10 | ATR calculation period |
| `atr_sl_multiplier` | 2.0 | Stop Loss = ATR × this |
| `atr_tp_multiplier` | 6.0 | Take Profit = ATR × this |
| **Time Filter** |||
| `use_time_filter` | False | Enable time restriction |
| `allowed_hours` | [] | List of allowed hours (UTC) |
| **SL Pips Filter** |||
| `use_sl_pips_filter` | False | Enable SL size filter |
| `sl_pips_min` | 5.0 | Minimum SL in pips |
| `sl_pips_max` | 50.0 | Maximum SL in pips |
| **ATR Filter** |||
| `use_atr_filter` | False | Enable ATR range filter |
| `atr_min` | 0.0 | Minimum ATR |
| `atr_max` | 1.0 | Maximum ATR |
| **Risk Management** |||
| `risk_percent` | 0.005 | Risk per trade (0.5%) |
| `lot_size` | 100000 | Standard lot size |
| `pip_value` | 0.0001 | Pip value (0.01 for JPY) |
| **Asset Config** |||
| `is_jpy_pair` | False | JPY pair flag |
| `jpy_rate` | 150.0 | JPY conversion rate |
| `is_etf` | False | ETF asset flag |
| `margin_pct` | 3.33 | ETF margin percentage |

---

## Asset-Specific Configurations

### DIA (Dow Jones ETF)

```python
'DIA_KOI': {
    'strategy_name': 'KOI',
    'asset_name': 'DIA',
    'params': {
        'cci_threshold': 100,
        'atr_sl_multiplier': 2.5,
        'atr_tp_multiplier': 7.5,
        'breakout_level_offset_pips': 0.5,
        'is_etf': True,
        'margin_pct': 3.33,
        'risk_percent': 0.005,
    }
}
```

### TLT (Treasury Bond ETF)

```python
'TLT_KOI': {
    'strategy_name': 'KOI',
    'asset_name': 'TLT',
    'params': {
        'cci_threshold': 90,
        'atr_sl_multiplier': 2.0,
        'atr_tp_multiplier': 6.0,
        'is_etf': True,
        'use_time_filter': True,
        'allowed_hours': [14, 15, 16, 17, 18, 19, 20],  # US market hours
    }
}
```

### EURUSD (Standard Forex)

```python
'EURUSD_KOI': {
    'strategy_name': 'KOI',
    'asset_name': 'EURUSD',
    'params': {
        'cci_threshold': 110,
        'use_sl_pips_filter': True,
        'sl_pips_min': 8.0,
        'sl_pips_max': 25.0,
        'pip_value': 0.0001,
    }
}
```

---

## Comparison: KOI vs Sunset Ogle

| Aspect | KOI | Sunset Ogle |
|--------|-----|-------------|
| **Signal** | Bullish Engulfing Pattern | EMA Crossover |
| **Trend Filter** | 5 EMAs ascending | Price > EMA(70) |
| **Momentum** | CCI > threshold | EMA Angle (45-95°) |
| **Confirmation** | Breakout window | Pullback + Breakout |
| **Best For** | Range breakouts | Trend continuation |
| **Assets** | Forex + ETFs | Primarily Forex |
| **R:R Default** | 3:1 | 4.3:1 |

---

## Trade Reporting

KOI generates detailed trade reports in `logs/KOI_trades_YYYYMMDD_HHMMSS.txt`:

```
=== KOI STRATEGY TRADE REPORT ===
Generated: 2026-01-13 10:30:00
EMAs: 10, 20, 40, 80, 120
CCI: 20/110
Breakout: 2.0pips, 3bars
SL: 2.0x ATR | TP: 6.0x ATR

ENTRY #1
Time: 2026-01-13 08:15:00
Entry Price: 1.08532
Stop Loss: 1.08312
Take Profit: 1.09192
SL Pips: 22.0
ATR: 0.000110
CCI: 125.43
--------------------------------------------------

EXIT #1
Time: 2026-01-13 14:30:00
Exit Reason: TAKE_PROFIT
P&L: $660.00
================================================================================
```

---

## Further Reading

- [Bullish Engulfing Pattern](https://www.investopedia.com/terms/b/bullishengulfingpattern.asp)
- [Commodity Channel Index (CCI)](https://www.investopedia.com/terms/c/commoditychannelindex.asp)
- [EMA Trading Strategies](https://www.investopedia.com/terms/e/ema.asp)
- [Backtrader Documentation](https://www.backtrader.com/docu/)
