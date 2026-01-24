# SEDNA Strategy

**Type:** HTF Trend + Pullback + Breakout  
**Assets:** ETFs (DIA), extensible to Forex  
**Direction:** Long Only  
**Base:** Derived from KOI with adaptive improvements

---

## Table of Contents

1. [Overview](#overview)
2. [Entry System (3 Phases)](#entry-system-3-phases)
3. [Main Indicators](#main-indicators)
4. [Exit Logic](#exit-logic)
5. [Risk Management](#risk-management)
6. [Configuration Parameters](#configuration-parameters)
7. [Current Configuration (DIA)](#current-configuration-dia)
8. [Backtest Results](#backtest-results)

---

## Overview

SEDNA is a **trend continuation strategy** that identifies pullbacks within established trends and enters on breakout confirmation.

### Design Philosophy

```
HTF TREND  -->  PULLBACK  -->  BREAKOUT  -->  ENTRY
   (1)           (2)            (3)
```

1. **HTF Trend Detection**: Efficiency Ratio confirms trending (not choppy) market + Close > KAMA
2. **Pullback Detection**: N bars without new Higher High, price respects KAMA support
3. **Breakout Confirmation**: Price breaks above pullback high + buffer

### Why This Architecture?

| Component | Purpose |
|-----------|---------|
| **HTF Filter** | Avoid entries in choppy/ranging markets |
| **Pullback** | Enter at better price after trend confirmation |
| **Breakout** | Confirm momentum before committing capital |

---

## Entry System (3 Phases)

### Phase 1: HTF Trend Filter (Main Trigger)

```python
def _check_htf_filter(self) -> bool:
    # Condition 1: ER >= threshold (trending market)
    er_value = EfficiencyRatio(close, scaled_period)
    if er_value < htf_er_threshold:
        return False
    
    # Condition 2: Close > KAMA (bullish direction)
    if close <= KAMA:
        return False
    
    return True
```

**Efficiency Ratio** measures trend strength:
- ER close to 1.0 = Strong trend (directional movement)
- ER close to 0.0 = Choppy/sideways (no clear direction)

**HTF Simulation**: ER period scaled by timeframe multiplier
- 5m data + 15m HTF = period x 3 = 30 bars

### Phase 2: Pullback Detection

```python
def _check_pullback_condition(self) -> bool:
    result = detect_pullback(
        highs=price_history['highs'],
        lows=price_history['lows'],
        closes=price_history['closes'],
        kama_values=price_history['kama'],
        min_bars=pullback_min_bars,  # 2
        max_bars=pullback_max_bars,  # 5
    )
    
    if result['valid']:
        self.pullback_data = result  # Store for breakout level
        return True
    return False
```

**Pullback Definition:**
1. Price made a Higher High (HH) in lookback period
2. N consecutive bars without new HH (consolidation)
3. Price respects KAMA support (all closes > KAMA)

**Returns:**
- `breakout_level`: The HH price to break
- `pullback_low`: Lowest low during pullback (potential SL reference)

### Phase 3: Breakout State Machine

```
+-----------+   Conditions   +------------------+
| SCANNING  |   Met (1+2)    | WAITING_BREAKOUT |
|           |--------------->|                  |
+-----------+                +--------+---------+
      ^                               |
      |                         High > Breakout Level?
      | Timeout                       |
      | (N candles)             YES   |   NO (wait)
      |                               v
      |                       +-------+-------+
      +-----------------------|    ENTRY      |
                              |   (Phase 3)   |
                              +---------------+
```

```python
# WAITING_BREAKOUT state
if current_high > breakout_level:
    execute_entry()
elif bars_since > breakout_window_candles:
    reset_state()  # Timeout
```

---

## Main Indicators

### 1. KAMA (Kaufman's Adaptive Moving Average)

Applied to HL2 = (High + Low) / 2

```python
class KAMA(bt.Indicator):
    params = (
        ('period', 10),   # Efficiency ratio period
        ('fast', 2),      # Fast smoothing constant
        ('slow', 30),     # Slow smoothing constant
    )
```

**Calculation:**
```
Change = |Price[0] - Price[-period]|
Volatility = Sum(|Price[-i] - Price[-i-1]|) for i in range(period)
ER = Change / Volatility

fast_sc = 2 / (fast + 1)
slow_sc = 2 / (slow + 1)
SC = (ER * (fast_sc - slow_sc) + slow_sc)^2

KAMA = KAMA[-1] + SC * (Price - KAMA[-1])
```

**Behavior:**
- **Trending market** (ER high) -> KAMA responds quickly
- **Ranging market** (ER low) -> KAMA moves slowly

### 2. Efficiency Ratio (HTF Filter)

```python
class EfficiencyRatio(bt.Indicator):
    params = (('period', 10),)
    
    def next(self):
        change = abs(self.data[0] - self.data[-self.p.period])
        volatility = sum(abs(self.data[-i] - self.data[-i-1]) 
                        for i in range(1, self.p.period + 1))
        self.lines.er[0] = change / volatility if volatility > 0 else 0
```

### 3. Pullback Detection (Reusable Filter)

Located in `lib/filters.py` - standard function usable by any strategy:

```python
def detect_pullback(
    highs: list,
    lows: list,
    closes: list,
    kama_values: list,
    min_bars: int = 2,
    max_bars: int = 5,
) -> dict:
    """
    Returns:
        'valid': bool - True if pullback detected
        'bars_since_hh': int - Bars since last HH
        'hh_price': float - The Higher High price
        'pullback_low': float - Lowest low during pullback
        'breakout_level': float - HH price (for breakout detection)
        'respects_support': bool - Price stayed above KAMA
    """
```

---

## Exit Logic

### Stop Loss and Take Profit (OCA Orders)

```python
# On entry execution:
stop_level = entry_price - (atr_avg * atr_sl_multiplier)
take_level = entry_price + (atr_avg * atr_tp_multiplier)

stop_order = self.sell(exectype=bt.Order.Stop, price=stop_level, oco=limit_order)
limit_order = self.sell(exectype=bt.Order.Limit, price=take_level, oco=stop_order)
```

**OCA (One-Cancels-All):** When one order executes, the other is automatically cancelled.

### KAMA Reversal Exit (Optional)

When `use_kama_exit=True`:

```python
def _check_kama_exit_condition(self) -> bool:
    # KAMA > EMA = trend reversed = exit signal
    return KAMA(HL2) > EMA(HL2)
```

---

## Risk Management

### Position Sizing (ETF)

```python
shares = risk_amount / price_risk
# risk_amount = equity * risk_percent (e.g., $100k * 0.5% = $500)
# price_risk = entry - stop_loss (e.g., 3 * ATR = $0.50)
# shares = $500 / $0.50 = 1,000 shares

max_shares = equity / (entry_price * margin_pct / 100)
shares = min(shares, max_shares)  # Margin constraint
```

### Optional Filters (Pre-Entry)

| Filter | Description | Status |
|--------|-------------|--------|
| **Time Filter** | Only trade during specific hours | Disabled |
| **SL Pips Filter** | Limit SL range in pips | Disabled |
| **ATR Filter** | Volatility within range | Disabled |

---

## Configuration Parameters

### HTF Filter

| Parameter | Default | Description |
|-----------|---------|-------------|
| `use_htf_filter` | True | Enable HTF trend filter |
| `htf_timeframe_minutes` | 15 | Target HTF for ER scaling |
| `htf_er_period` | 10 | ER period on HTF equivalent |
| `htf_er_threshold` | 0.40 | Min ER to allow entry (0.0-1.0) |

### Pullback Detection

| Parameter | Default | Description |
|-----------|---------|-------------|
| `use_pullback_filter` | True | Enable pullback detection |
| `pullback_min_bars` | 2 | Min bars without new HH |
| `pullback_max_bars` | 5 | Max bars to wait (timeout) |

### KAMA

| Parameter | Default | Description |
|-----------|---------|-------------|
| `kama_period` | 10 | Period for Efficiency Ratio |
| `kama_fast` | 2 | Fast smoothing constant |
| `kama_slow` | 30 | Slow smoothing constant |

### Breakout Window

| Parameter | Default | Description |
|-----------|---------|-------------|
| `use_breakout_window` | True | Enable breakout confirmation |
| `breakout_window_candles` | 3 | Max candles to wait for breakout |
| `breakout_level_offset_pips` | 2.0 | Offset above pullback HH |

### ATR and SL/TP

| Parameter | Default | Description |
|-----------|---------|-------------|
| `atr_length` | 10 | ATR period |
| `atr_sl_multiplier` | 3.0 | Multiplier for Stop Loss |
| `atr_tp_multiplier` | 10.0 | Multiplier for Take Profit |
| `atr_avg_period` | 20 | Periods to average ATR |

### Exit Conditions

| Parameter | Default | Description |
|-----------|---------|-------------|
| `use_kama_exit` | False | Enable KAMA reversal exit |

---

## Current Configuration (DIA)

```python
'DIA_SEDNA': {
    'params': {
        # KAMA settings
        'kama_period': 10,
        'kama_fast': 2,
        'kama_slow': 30,
        'hl2_ema_period': 1,
        
        # CCI (disabled - not part of 3-phase system)
        'use_cci_filter': False,
        
        # HTF Filter (MAIN TRIGGER)
        'use_htf_filter': True,
        'htf_timeframe_minutes': 15,
        'htf_er_period': 10,
        'htf_er_threshold': 0.40,
        
        # Pullback Detection
        'use_pullback_filter': True,
        'pullback_min_bars': 2,
        'pullback_max_bars': 5,
        
        # Breakout Window
        'use_breakout_window': True,
        'breakout_window_candles': 3,
        'breakout_level_offset_pips': 2.0,
        
        # ATR / SL / TP
        'atr_length': 10,
        'atr_sl_multiplier': 3.0,
        'atr_tp_multiplier': 10.0,
        
        # ETF Config
        'pip_value': 0.01,
        'is_etf': True,
        'margin_pct': 20.0,
        'risk_percent': 0.005,  # 0.5%
    }
}
```

### Configuration Summary

| Component | Status |
|-----------|--------|
| **HTF Filter** | Enabled (ER >= 0.40, Close > KAMA) |
| **Pullback** | Enabled (2-5 bars) |
| **CCI** | Disabled |
| **Breakout Window** | 3 candles, +$0.02 offset |
| **KAMA** | Active (10, 2, 30) on HL2 |
| **SL/TP Ratio** | 1:3.3 (3x ATR : 10x ATR) |
| **Risk per Trade** | 0.5% |

---

## Backtest Results

**Period:** 2020-07-01 to 2025-07-01 (5 years)  
**Asset:** DIA (Dow Jones ETF)  
**Starting Capital:** $100,000

| Metric | Value |
|--------|-------|
| **Total Trades** | 135 |
| **Win Rate** | 30.4% |
| **Profit Factor** | 1.29 |
| **Net P&L** | $17,818 |
| **Final Value** | $117,818 |
| **Return** | 17.82% |
| **Max Drawdown** | 5.88% |
| **Sharpe Ratio** | 1.20 |
| **Sortino Ratio** | 0.47 |
| **CAGR** | 3.36% |
| **Calmar Ratio** | 0.57 |

### Commission Summary

| Metric | Value |
|--------|-------|
| **Total Commission** | $2,727.48 |
| **Total Shares Traded** | 136,374 |
| **Avg Commission/Trade** | $20.20 |
| **Avg Shares/Trade** | 1,010 |

### Yearly Breakdown

| Year | Trades | WR% | PF | P&L |
|------|--------|-----|-----|-----|
| 2020 | 15 | 33.3% | 1.59 | $3,198 |
| 2021 | 24 | 33.3% | 1.23 | $2,582 |
| 2022 | 27 | 29.6% | 1.24 | $3,007 |
| 2023 | 29 | 34.5% | 1.80 | $8,949 |
| 2024 | 28 | 25.0% | 1.01 | $155 |
| 2025 | 12 | 25.0% | 0.99 | -$73 |

---

## Changelog

| Date | Version | Changes |
|------|---------|---------|
| 2026-01-24 | 2.0 | Major refactor: Replace Bullish Engulfing with HTF + Pullback system |
| 2026-01-24 | 1.1 | Add KAMA reversal exit condition |
| 2026-01-24 | 1.0 | Initial version derived from KOI |

---

*Documentation generated for TradingSystem - SEDNA Strategy*
