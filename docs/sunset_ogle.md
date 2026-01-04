# 🌅 Sunset Ogle Strategy

**Type:** Trend Following / Volatility Expansion Breakout  
**Asset:** EURJPY (5-minute timeframe)  
**Direction:** Long Only  

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [The 4-Phase State Machine](#the-4-phase-state-machine)
3. [Entry Filters](#entry-filters)
4. [Exit Logic](#exit-logic)
5. [Risk Management](#risk-management)
6. [Configuration Parameters](#configuration-parameters)
7. [Code Implementation](#code-implementation)

---

## Overview

Sunset Ogle is a **trend-following breakout strategy** that identifies volatility expansion moments after a pullback confirmation. Unlike simple indicator crossover systems, it implements a **sequential state machine** that requires price to pass through 4 specific phases before executing a trade.

### Why a State Machine?

Simple strategies like "buy when RSI < 30" execute immediately when a condition is met. This leads to:
- False signals during choppy markets
- Entries at the worst possible moment (buying into a falling knife)
- No confirmation of trend strength

The state machine approach requires:
1. A valid **signal** (EMA crossover)
2. A **pullback** confirmation (proof the move isn't exhausted)
3. A **breakout** trigger (momentum resumption)

This filtering dramatically improves trade quality.

---

## The 4-Phase State Machine

```
┌─────────────┐    Signal     ┌─────────────┐
│  SCANNING   │──────────────▶│    ARMED    │
│  (Phase 1)  │               │  (Phase 2)  │
└─────────────┘               └──────┬──────┘
       ▲                             │
       │                        Pullback
       │ Reset                   Confirmed
       │                             │
       │                             ▼
┌──────┴──────┐    Breakout   ┌─────────────┐
│    RESET    │◀──────────────│   WINDOW    │
│             │    Timeout    │  (Phase 3)  │
└─────────────┘               └──────┬──────┘
                                     │
                              Price Breaks
                                 Level
                                     │
                                     ▼
                              ┌─────────────┐
                              │   ENTRY     │
                              │  (Phase 4)  │
                              └─────────────┘
```

### Phase 1: SCANNING

The system monitors for a valid entry signal. All conditions must be met **simultaneously**:

```python
def _check_signal(self):
    # EMA Crossover: EMA(1) crosses above EMA(18) OR EMA(24)
    cross_any = (
        self._cross_above(self.ema_confirm, self.ema_fast) or
        self._cross_above(self.ema_confirm, self.ema_medium) or
        self._cross_above(self.ema_confirm, self.ema_slow)
    )
    
    # Price Filter: Close > EMA(70)
    price_above_trend = self.data.close[0] > self.ema_filter[0]
    
    # Angle Filter: 45° to 95°
    angle_valid = self.p.angle_min <= self._angle() <= self.p.angle_max
    
    # ATR Filter: 0.030 to 0.090
    atr_valid = self.p.atr_min <= self.atr[0] <= self.p.atr_max
    
    return cross_any and price_above_trend and angle_valid and atr_valid
```

**Result:** If all conditions pass → State changes to `ARMED_LONG`

### Phase 2: ARMED (Pullback Detection)

We avoid buying into euphoria by requiring a pullback after the signal:

```python
def _check_pullback(self):
    is_bearish = self.data.close[0] < self.data.open[0]  # Red candle
    
    if is_bearish:
        self.pullback_count += 1
        if self.pullback_count >= self.p.pullback_candles:  # Default: 2
            self.pullback_high = self.data.high[0]
            self.pullback_low = self.data.low[0]
            return True  # Pullback confirmed
    else:
        self._reset_state()  # Green candle without pullback = invalid
    
    return False
```

**Logic:**
- Count consecutive bearish (red) candles
- Need at least 2 red candles to confirm pullback
- If a green candle appears before 2 red → Reset to Phase 1

**Result:** If pullback confirmed → State changes to `WINDOW_OPEN`

### Phase 3: WINDOW (Breakout Setup)

Once pullback is confirmed, we define the entry parameters:

```python
def _open_window(self):
    current_bar = len(self)
    self.window_start = current_bar
    self.window_expiry = current_bar + self.p.window_periods  # Default: 2 bars
    
    # Calculate breakout level with dynamic offset
    candle_range = self.pullback_high - self.pullback_low
    offset = candle_range * self.p.price_offset_mult  # Default: 0.01 (1%)
    
    self.window_top = self.pullback_high + offset
    self.window_bottom = self.pullback_low - offset
```

**Parameters:**
- `window_top`: Price level that triggers entry
- `window_bottom`: Price level that invalidates setup (too much weakness)
- `window_expiry`: Maximum bars to wait for breakout

### Phase 4: ENTRY (Execution)

Monitor for breakout within the window:

```python
def _monitor_window(self):
    current_bar = len(self)
    
    # Timeout: Window expired without breakout
    if current_bar > self.window_expiry:
        return None  # Reset to ARMED
    
    # Success: Price breaks above window_top
    if self.data.high[0] >= self.window_top:
        return 'SUCCESS'  # Execute entry
    
    # Failure: Price breaks below window_bottom
    if self.data.low[0] <= self.window_bottom:
        return None  # Reset to ARMED
```

---

## Entry Filters

### 1. Price Filter (Trend Confirmation)
```python
price_above_ema = self.data.close[0] > self.ema_filter[0]  # EMA(70)
```
Only take long trades when price is above the 70-period EMA. This ensures we're trading with the trend.

### 2. Angle Filter (Momentum Strength)
```python
def _angle(self):
    rise = (self.ema_confirm[0] - self.ema_confirm[-1]) * self.p.angle_scale
    return math.degrees(math.atan(rise))
```
The EMA angle must be between 45° and 95°. This filters out:
- Flat markets (angle < 45°): No momentum
- Parabolic moves (angle > 95°): Likely exhaustion

### 3. ATR Filter (Volatility Range)
```python
atr_valid = 0.030 <= self.atr[0] <= 0.090
```
- **Minimum (0.030)**: Avoid low volatility periods where spreads eat profits
- **Maximum (0.090)**: Avoid extreme volatility where stops get hit easily

### 4. Time Filter
```python
def _in_time_range(self, dt):
    current = dt.hour * 60 + dt.minute
    start = 5 * 60    # 05:00 UTC
    end = 18 * 60     # 18:00 UTC
    return start <= current <= end
```
Only trade during active market hours (London + New York sessions).

---

## Exit Logic

### Stop Loss (ATR-Based)
```python
self.stop_level = bar_low - atr * self.p.sl_mult  # Default: 3.5x ATR
```
Stop loss is placed below the entry bar's low, with a buffer of 3.5× ATR.

### Take Profit (ATR-Based)
```python
self.take_level = bar_high + atr * self.p.tp_mult  # Default: 15.0x ATR
```
Take profit is 15× ATR above entry. This high ratio is typical for trend-following strategies (let winners run).

### Risk-Reward Ratio
With SL = 3.5× ATR and TP = 15× ATR:
```
Risk-Reward = 15.0 / 3.5 = 4.3:1
```
This means we need only ~24% win rate to be profitable.

---

## Risk Management

### Position Sizing (JPY Pair Correction)

For JPY pairs, standard forex math doesn't apply directly. We implement the "ERIS Logic":

```python
def _calculate_position_size(self, entry_price, stop_loss):
    raw_risk = entry_price - stop_loss
    pip_risk = raw_risk / self.p.pip_value  # 0.01 for JPY
    
    # Pip value in JPY: 100,000 × 0.01 = 1,000 JPY per pip
    pip_value_jpy = self.p.lot_size * self.p.pip_value
    value_per_pip = pip_value_jpy / entry_price  # Convert to USD
    
    equity = self.broker.get_value()
    risk_amount = equity * self.p.risk_percent  # 0.3%
    
    optimal_lots = risk_amount / (pip_risk * value_per_pip)
    optimal_lots = max(0.01, round(optimal_lots, 2))
    
    # Normalize for Backtrader's margin calculation
    real_contracts = int(optimal_lots * self.p.lot_size)
    bt_size = int(real_contracts / self.p.jpy_rate)  # Divide by ~150
    
    return max(100, bt_size)
```

**Why divide by JPY rate?**

Backtrader calculates margin and P&L assuming USD-based pricing. For JPY pairs (priced at ~150), positions appear 150× larger than they should be. Dividing normalizes this.

The `ForexCommission` class then multiplies back for accurate P&L reporting.

---

## Configuration Parameters

### Complete Parameter Reference

| Parameter | Default | Description |
|-----------|---------|-------------|
| **EMA Settings** |||
| `ema_fast_length` | 18 | Fast EMA for crossover detection |
| `ema_medium_length` | 18 | Medium EMA for crossover detection |
| `ema_slow_length` | 24 | Slow EMA for crossover detection |
| `ema_confirm_length` | 1 | Confirmation EMA (price itself) |
| `ema_filter_price_length` | 70 | Trend filter EMA |
| **ATR Settings** |||
| `atr_length` | 10 | ATR calculation period |
| `atr_min` | 0.030 | Minimum ATR for valid signal |
| `atr_max` | 0.090 | Maximum ATR for valid signal |
| **Angle Settings** |||
| `angle_min` | 45.0 | Minimum EMA angle (degrees) |
| `angle_max` | 95.0 | Maximum EMA angle (degrees) |
| `angle_scale` | 100.0 | Scaling factor for angle calculation |
| **Exit Settings** |||
| `sl_mult` | 3.5 | Stop Loss = ATR × this value |
| `tp_mult` | 15.0 | Take Profit = ATR × this value |
| **Pullback Settings** |||
| `pullback_candles` | 2 | Required bearish candles |
| `window_periods` | 2 | Breakout window duration |
| `price_offset_mult` | 0.01 | Offset for breakout level |
| **Time Filter** |||
| `time_start_hour` | 5 | Trading start (UTC) |
| `time_end_hour` | 18 | Trading end (UTC) |
| **Risk Management** |||
| `risk_percent` | 0.003 | Risk per trade (0.3%) |
| `jpy_rate` | 150.0 | JPY conversion rate |
| `lot_size` | 100000 | Standard lot size |
| `pip_value` | 0.01 | Pip value for JPY pairs |

---

## Code Implementation

### Global Invalidation Logic

A critical feature is the **Global Invalidation** - resetting the state machine when market conditions change:

```python
# In the next() method, while in ARMED state:
if self.entry_state == "ARMED_LONG":
    prev_bear = self.data.close[-1] < self.data.open[-1]  # Previous candle bearish
    cross_any = (
        self._cross_below(self.ema_confirm, self.ema_fast) or
        self._cross_below(self.ema_confirm, self.ema_medium) or
        self._cross_below(self.ema_confirm, self.ema_slow)
    )
    
    # Reset ONLY if: bearish previous candle AND opposing crossover
    if prev_bear and cross_any:
        self._reset_state()
```

**Why both conditions?**

- Crossover alone: Might just be minor fluctuation
- Bearish candle alone: Normal pullback behavior
- Both together: Strong signal that the original setup is invalid

---

## Performance Validation

Backtested on EURJPY 5m data (July 2024 - July 2025):

| Metric | Value |
|--------|-------|
| Total Trades | 38 |
| Winning Trades | 12 |
| Losing Trades | 26 |
| Win Rate | 31.6% |
| Profit Factor | 1.55 |
| Total P&L | $4,500.01 |
| Starting Capital | $100,000 |
| Return | 4.50% |

Despite a low win rate (31.6%), the strategy is profitable due to the favorable risk-reward ratio (4.3:1).

---

## Further Reading

- [Backtrader Documentation](https://www.backtrader.com/docu/)
- [ATR-Based Position Sizing](https://www.investopedia.com/terms/a/atr.asp)
- [State Machine Design Patterns](https://refactoring.guru/design-patterns/state)