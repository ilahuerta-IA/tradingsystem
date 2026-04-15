"""
ALTAIR Strategy Checker for Live Trading.

Trend-Following Momentum on US Stocks (Miner DTOscillator).
Single data feed per ticker, LONG only.

Concept:
    D1 regime filter (CALM_UP) gates entry.
    DTOSC cross-up from oversold triggers Trailing One-Bar High (Tr-1BH).
    If price breaks the buy stop, enter LONG at market (close of bar).
    Risk-based sizing: shares = risk_amount / sl_distance.

State Machine:
    SCANNING   -> [DTOSC cross-up from OS + CALM_UP] -> TRIGGERED
    TRIGGERED  -> [high >= buy_stop]                  -> IN_POSITION (signal emitted)
    TRIGGERED  -> [DTOSC lost alignment / timeout]    -> SCANNING
    IN_POSITION exits handled by MT5 server (SL/TP) or time-exit in multi_monitor.

Data feed:
    df = single ticker bars at the ticker's live TF (15m / 30m / H1),
         resampled from M5 by multi_monitor.  Timestamps in UTC.

Reference: altair_strategy.py (backtrader) -- replicates logic exactly.
Reference: Robert Miner "High Probability Trading Strategies" (Figs 2.5-2.6)
"""

import math
import logging
from datetime import datetime
from typing import Optional, Dict, Any

import pandas as pd
import numpy as np

from .base_checker import BaseChecker, Signal, SignalDirection


class ALTAIRChecker(BaseChecker):
    """
    ALTAIR strategy signal checker.

    Stateful: maintains a 3-state machine (SCANNING / TRIGGERED / IN_POSITION)
    that persists across calls to check_signal().

    Unlike VEGA (stateless per bar), ALTAIR needs state because the Tr-1BH
    entry spans multiple bars between DTOSC trigger and price confirmation.
    """

    @property
    def strategy_name(self) -> str:
        return "ALTAIR"

    def __init__(
        self,
        config_name: str,
        params: Dict[str, Any],
        logger: Optional[logging.Logger] = None,
    ):
        super().__init__(config_name, params, logger)

        # DTOSC params
        self.dtosc_period = params.get("dtosc_period", 8)
        self.dtosc_smooth_k = params.get("dtosc_smooth_k", 5)
        self.dtosc_smooth_d = params.get("dtosc_smooth_d", 3)
        self.dtosc_signal = params.get("dtosc_signal", 3)
        self.dtosc_ob = params.get("dtosc_ob", 75)
        self.dtosc_os = params.get("dtosc_os", 25)

        # Regime params (day-scaled by bars_per_day)
        self.regime_enabled = params.get("regime_enabled", True)
        self.regime_sma_period = params.get("regime_sma_period", 252)
        self.regime_atr_period = params.get("regime_atr_period", 252)
        self.regime_atr_current_period = params.get("regime_atr_current_period", 14)
        self.regime_atr_threshold = params.get("regime_atr_threshold", 1.0)
        self.momentum_63d_period = params.get("momentum_63d_period", 63)
        self.bars_per_day = params.get("bars_per_day", 7)

        # Risk / exit
        self.atr_period = params.get("atr_period", 14)
        self.sl_atr_mult = params.get("sl_atr_mult", 2.0)
        self.tp_atr_mult = params.get("tp_atr_mult", 4.0)

        # Tr-1BH
        self.use_tr1bh = params.get("use_tr1bh", True)
        self.tr1bh_timeout = params.get("tr1bh_timeout", 5)
        self.tr1bh_tick = params.get("tr1bh_tick", 0.01)

        # Swing low SL
        self.use_swing_low_sl = params.get("use_swing_low_sl", True)
        self.max_sl_atr_mult = params.get("max_sl_atr_mult", 2.0)

        # Holding / session
        self.max_holding_bars = params.get("max_holding_bars", 120)
        self.max_entries_per_day = params.get("max_entries_per_day", 1)
        self.use_time_filter = params.get("use_time_filter", True)
        self.allowed_hours = list(params.get("allowed_hours", [14, 15, 16, 17, 18, 19]))
        self.use_day_filter = params.get("use_day_filter", True)
        self.allowed_days = list(params.get("allowed_days", [0, 1, 2, 3, 4]))

        # Sizing
        self.risk_percent = params.get("risk_percent", 0.01)
        self.capital_alloc_pct = params.get("capital_alloc_pct", 0.20)
        self.max_position_pct = params.get("max_position_pct", 0.30)
        self.margin_pct_bt = params.get("margin_pct", 20.0)

        # --- State machine ---
        self._state = "SCANNING"
        self._triggered_bar_count = 0
        self._triggered_buy_stop = 0.0
        self._frozen_swing_low = None

        # Swing low tracking (continuous)
        self._swing_low = float("inf")
        self._tracking_oversold = False

        # Regime cache
        self._regime_state = "UNKNOWN"

        # Duplicate bar guard
        self._last_processed_bar_time = None

        # Daily trade counter
        self._trades_today = 0
        self._last_trade_date = None

        # Position tracking (for time-exit)
        self._in_position = False
        self._entry_bar_time = None
        self._bars_held = 0

        self.logger.info(
            "[%s] ALTAIR Checker initialized | "
            "DTOSC=%d/%d/%d/%d OS=%d | "
            "bars_per_day=%d | Regime=%s | "
            "SL_max=%.1fx ATR | TP=%.1fx ATR | "
            "Tr-1BH=%s timeout=%d",
            self.config_name,
            self.dtosc_period, self.dtosc_smooth_k,
            self.dtosc_smooth_d, self.dtosc_signal, self.dtosc_os,
            self.bars_per_day,
            "ON" if self.regime_enabled else "OFF",
            self.max_sl_atr_mult, self.tp_atr_mult,
            "ON" if self.use_tr1bh else "OFF", self.tr1bh_timeout,
        )

    # =========================================================================
    # STATE MANAGEMENT
    # =========================================================================

    def reset_state(self) -> None:
        """Reset state machine to initial state."""
        self._state = "SCANNING"
        self._triggered_bar_count = 0
        self._triggered_buy_stop = 0.0
        self._frozen_swing_low = None
        self._swing_low = float("inf")
        self._tracking_oversold = False
        self._regime_state = "UNKNOWN"
        self._last_processed_bar_time = None
        self._trades_today = 0
        self._last_trade_date = None
        self._in_position = False
        self._entry_bar_time = None
        self._bars_held = 0

    def get_state_info(self) -> Dict[str, Any]:
        """Get current state for logging / persistence."""
        return {
            "strategy": self.strategy_name,
            "state": self._state,
            "last_bar_time": str(self._last_processed_bar_time),
            "trades_today": self._trades_today,
            "regime": self._regime_state,
            "triggered_bar_count": self._triggered_bar_count,
            "triggered_buy_stop": self._triggered_buy_stop,
            "frozen_swing_low": self._frozen_swing_low,
            "swing_low": self._swing_low if self._swing_low != float("inf") else None,
            "in_position": self._in_position,
            "bars_held": self._bars_held,
        }

    def restore_state(self, state_dict: Dict[str, Any]) -> None:
        """Restore state from persistence (bot restart recovery)."""
        self._state = state_dict.get("state", "SCANNING")
        self._triggered_bar_count = state_dict.get("triggered_bar_count", 0)
        self._triggered_buy_stop = state_dict.get("triggered_buy_stop", 0.0)
        self._frozen_swing_low = state_dict.get("frozen_swing_low")
        sw = state_dict.get("swing_low")
        self._swing_low = sw if sw is not None else float("inf")
        self._in_position = state_dict.get("in_position", False)
        self._bars_held = state_dict.get("bars_held", 0)
        bar_time_str = state_dict.get("last_bar_time")
        if bar_time_str and bar_time_str != "None":
            try:
                self._last_processed_bar_time = datetime.fromisoformat(bar_time_str)
            except (ValueError, TypeError):
                self._last_processed_bar_time = None
        self.logger.info(
            "[%s] ALTAIR state restored: %s (bars_held=%d)",
            self.config_name, self._state, self._bars_held,
        )

    # =========================================================================
    # INDICATORS (match BT exactly)
    # =========================================================================

    @staticmethod
    def _sma(series: pd.Series, period: int) -> pd.Series:
        """Simple Moving Average."""
        return series.rolling(window=period, min_periods=period).mean()

    @staticmethod
    def _atr_wilder(df: pd.DataFrame, period: int) -> pd.Series:
        """ATR using Wilder's RMA (matches backtrader bt.ind.ATR)."""
        high = df["high"]
        low = df["low"]
        close = df["close"]

        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        # Wilder RMA: alpha = 1/period
        return tr.ewm(alpha=1.0 / period, adjust=False).mean()

    def _compute_dtosc(self, df: pd.DataFrame):
        """Compute DT Oscillator (fast + slow lines).

        Returns (fast_series, slow_series) as pd.Series.
        Matches DTOscillator indicator in altair_strategy.py exactly.
        """
        high = df["high"]
        low = df["low"]
        close = df["close"]

        highest = high.rolling(window=self.dtosc_period, min_periods=self.dtosc_period).max()
        lowest = low.rolling(window=self.dtosc_period, min_periods=self.dtosc_period).min()

        denom = highest - lowest
        denom = denom.replace(0, 1e-10)
        raw_k = 100.0 * (close - lowest) / denom

        sk = self._sma(raw_k, self.dtosc_smooth_k)
        sd = self._sma(sk, self.dtosc_smooth_d)  # fast line
        signal = self._sma(sd, self.dtosc_signal)  # slow line

        return sd, signal

    # =========================================================================
    # REGIME (D1, computed from intraday bars via bars_per_day scaling)
    # =========================================================================

    def _update_regime(self, df: pd.DataFrame) -> str:
        """Compute D1 regime from the feed's bars using day-scaled periods.

        Matches _update_regime() in altair_strategy.py:
          Mom12M: close > SMA(252 * bpd)
          ATR ratio: ATR(14 * bpd) / SMA(ATR, 252 * bpd) < 1.0
          Mom63d: close > close[-63 * bpd]
        """
        if not self.regime_enabled:
            self._regime_state = "DISABLED"
            return self._regime_state

        bpd = self.bars_per_day

        # Mom12M: SMA of close over 252 trading days
        sma_period = self.regime_sma_period * bpd
        if len(df) < sma_period + 10:
            self._regime_state = "WARMING"
            return self._regime_state

        close_val = float(df["close"].iloc[-1])

        sma_val = float(self._sma(df["close"], sma_period).iloc[-1])
        if math.isnan(sma_val) or sma_val <= 0:
            self._regime_state = "WARMING"
            return self._regime_state

        mom12m_ok = close_val > sma_val

        # ATR ratio: current ATR / long-term average ATR
        atr_current_period = self.regime_atr_current_period * bpd
        atr_long_period = self.regime_atr_period * bpd

        atr_current = self._atr_wilder(df, atr_current_period)
        sma_atr = self._sma(atr_current, atr_long_period)

        atr_val = float(atr_current.iloc[-1])
        sma_atr_val = float(sma_atr.iloc[-1])

        if math.isnan(atr_val) or math.isnan(sma_atr_val) or sma_atr_val <= 0:
            self._regime_state = "WARMING"
            return self._regime_state

        atr_ratio = atr_val / sma_atr_val
        calm_ok = atr_ratio < self.regime_atr_threshold

        # Mom63d: close > close[63 trading days ago]
        lookback = self.momentum_63d_period * bpd
        mom63d_ok = False
        if len(df) > lookback:
            close_ago = float(df["close"].iloc[-lookback - 1])
            if not math.isnan(close_ago) and close_ago > 0:
                mom63d_ok = close_val > close_ago

        if mom12m_ok and calm_ok and mom63d_ok:
            self._regime_state = "CALM_UP"
        elif mom12m_ok and not calm_ok:
            self._regime_state = "VOLATILE_UP"
        elif not mom12m_ok and calm_ok:
            self._regime_state = "CALM_DOWN"
        else:
            self._regime_state = "VOLATILE_DOWN"

        return self._regime_state

    def _update_regime_from_d1(self, d1_df: pd.DataFrame) -> str:
        """Compute D1 regime directly from D1 bars (no bpd scaling).

        For live mode: multi_monitor fetches D1 bars from MT5 (400 bars ~1.5yr)
        and passes them here. This avoids needing 20,000+ M5 bars for regime.

        Same logic as _update_regime() but periods are in trading days directly:
          Mom12M: close > SMA(252)
          ATR ratio: ATR(14) / SMA(ATR, 252) < 1.0
          Mom63d: close > close[-63]
        """
        if not self.regime_enabled:
            self._regime_state = "DISABLED"
            return self._regime_state

        sma_period = self.regime_sma_period  # 252 (days, no bpd scaling)
        if len(d1_df) < sma_period + 10:
            self._regime_state = "WARMING"
            return self._regime_state

        close_val = float(d1_df["close"].iloc[-1])

        sma_val = float(self._sma(d1_df["close"], sma_period).iloc[-1])
        if math.isnan(sma_val) or sma_val <= 0:
            self._regime_state = "WARMING"
            return self._regime_state

        mom12m_ok = close_val > sma_val

        # ATR ratio (D1 periods, no bpd scaling)
        atr_current = self._atr_wilder(d1_df, self.regime_atr_current_period)
        sma_atr = self._sma(atr_current, self.regime_atr_period)

        atr_val = float(atr_current.iloc[-1])
        sma_atr_val = float(sma_atr.iloc[-1])

        if math.isnan(atr_val) or math.isnan(sma_atr_val) or sma_atr_val <= 0:
            self._regime_state = "WARMING"
            return self._regime_state

        atr_ratio = atr_val / sma_atr_val
        calm_ok = atr_ratio < self.regime_atr_threshold

        # Mom63d (D1 periods)
        lookback = self.momentum_63d_period
        mom63d_ok = False
        if len(d1_df) > lookback:
            close_ago = float(d1_df["close"].iloc[-lookback - 1])
            if not math.isnan(close_ago) and close_ago > 0:
                mom63d_ok = close_val > close_ago

        if mom12m_ok and calm_ok and mom63d_ok:
            self._regime_state = "CALM_UP"
        elif mom12m_ok and not calm_ok:
            self._regime_state = "VOLATILE_UP"
        elif not mom12m_ok and calm_ok:
            self._regime_state = "CALM_DOWN"
        else:
            self._regime_state = "VOLATILE_DOWN"

        return self._regime_state

    # =========================================================================
    # DTOSC SIGNAL CHECK
    # =========================================================================

    def _check_dtosc_crossup(self, fast: pd.Series, slow: pd.Series) -> bool:
        """Check for DTOSC bullish reversal from oversold zone.

        Matches _check_dtosc_signal() in altair_strategy.py:
          fast crosses above slow AND (fast[-1] < OS or slow[-1] < OS)
        """
        if len(fast) < 2 or len(slow) < 2:
            return False

        fast_now = float(fast.iloc[-1])
        fast_prev = float(fast.iloc[-2])
        slow_now = float(slow.iloc[-1])
        slow_prev = float(slow.iloc[-2])

        if any(math.isnan(v) for v in (fast_now, fast_prev, slow_now, slow_prev)):
            return False

        # Bullish cross: fast crosses above slow
        cross_up = (fast_now > slow_now) and (fast_prev <= slow_prev)
        if not cross_up:
            return False

        # Must come from oversold zone
        from_oversold = (fast_prev < self.dtosc_os) or (slow_prev < self.dtosc_os)
        return from_oversold

    # =========================================================================
    # SWING LOW TRACKING
    # =========================================================================

    def _track_swing_low(self, fast_val: float, low_val: float):
        """Track lowest low while DTOSC fast is in oversold zone.

        Matches _track_swing_low() in altair_strategy.py.
        """
        if math.isnan(fast_val):
            return

        if fast_val < self.dtosc_os:
            if not self._tracking_oversold:
                self._tracking_oversold = True
                self._swing_low = low_val
            else:
                self._swing_low = min(self._swing_low, low_val)
        else:
            self._tracking_oversold = False

    # =========================================================================
    # SIZING (matches BT _execute_entry exactly)
    # =========================================================================

    def calculate_shares(
        self,
        equity: float,
        entry_price: float,
        sl_distance: float,
        symbol_info: dict,
    ) -> float:
        """Calculate position size (shares/lots) using risk-based method.

        Matches altair_strategy.py _execute_entry() sizing:
          shares = risk_amount / sl_distance
          Capped by capital_alloc_pct and max_position_pct (margin-based).

        Args:
            equity: Account equity in USD
            entry_price: Entry price
            sl_distance: |entry - stop_loss| in price units
            symbol_info: MT5 symbol info dict

        Returns:
            Volume (lots) for MT5 order. 0 if trade should be skipped.
        """
        if sl_distance <= 0 or entry_price <= 0:
            return 0.0

        # Risk-based sizing
        risk_amount = equity * self.risk_percent
        shares = int(risk_amount / sl_distance)
        if shares < 1:
            return 0.0

        # Cap by capital allocation (margin)
        margin_per_share = entry_price * (self.margin_pct_bt / 100.0)
        if margin_per_share > 0:
            max_by_alloc = int((equity * self.capital_alloc_pct) / margin_per_share)
            shares = min(shares, max(1, max_by_alloc))

        # Absolute max position cap
        if margin_per_share > 0:
            abs_max = int((equity * self.max_position_pct) / margin_per_share)
            shares = min(shares, max(1, abs_max))

        # Clamp to broker limits
        min_lot = symbol_info.get("volume_min", 1.0)
        max_lot = symbol_info.get("volume_max", 10000.0)
        lot_step = symbol_info.get("volume_step", 1.0)

        volume = float(shares)
        if lot_step > 0:
            volume = round(volume / lot_step) * lot_step
        volume = max(min_lot, min(volume, max_lot))

        return volume

    # =========================================================================
    # MAIN SIGNAL CHECK
    # =========================================================================

    def check_signal(
        self,
        df: pd.DataFrame,
        reference_df: Optional[pd.DataFrame] = None,
        d1_df: Optional[pd.DataFrame] = None,
    ) -> Signal:
        """Check for ALTAIR trading signal.

        Args:
            df: Ticker bars at live TF (15m/30m/H1), timestamps in UTC.
                Resampled from M5 by multi_monitor. Last bar is CLOSED.
            reference_df: Not used (single-feed strategy). Ignored.
            d1_df: D1 bars from MT5 for regime computation (live mode).
                If provided, regime uses D1 directly (no bpd scaling).
                If None, falls back to computing regime from df (BT mode).

        Returns:
            Signal with direction LONG, entry/SL/TP, and metadata.
        """
        self.current_bar_index += 1

        if df is None or df.empty:
            return self._create_no_signal("No data")

        # Minimum data for indicator warmup.
        # If D1 data provided for regime, only need DTOSC + ATR warmup.
        # Otherwise need full regime warmup from intraday bars.
        if d1_df is not None:
            min_bars = max(
                self.dtosc_period + self.dtosc_smooth_k + self.dtosc_smooth_d + self.dtosc_signal + 10,
                self.atr_period + 5,
            )
        else:
            min_bars = max(
                self.regime_sma_period * self.bars_per_day + 50,
                self.dtosc_period + self.dtosc_smooth_k + self.dtosc_smooth_d + self.dtosc_signal + 10,
                self.atr_period + 5,
            )
        if len(df) < min_bars:
            return self._create_no_signal(
                "Insufficient data: %d bars < %d required" % (len(df), min_bars)
            )

        # Get bar time (UTC)
        if "time" not in df.columns:
            return self._create_no_signal("No 'time' column in data")

        bar_time_utc = df["time"].iloc[-1]
        if isinstance(bar_time_utc, pd.Timestamp):
            bar_time_utc = bar_time_utc.to_pydatetime()

        # Duplicate bar guard
        if self._last_processed_bar_time is not None:
            if bar_time_utc == self._last_processed_bar_time:
                return self._create_no_signal("Same bar already processed")

        # Stale bar guard (same pattern as VEGA)
        from datetime import timezone as _tz
        now_utc = datetime.now(_tz.utc).replace(tzinfo=None)
        bar_age_seconds = (now_utc - bar_time_utc).total_seconds()
        # Allow up to 2x the ticker's TF + 30min buffer
        # bars_per_day=7 -> H1 -> 3600s, bars_per_day=26 -> 15m -> 900s
        seconds_per_bar = int(6.5 * 3600 / self.bars_per_day)  # 6.5h trading day
        max_bar_age = seconds_per_bar * 2 + 1800
        if bar_age_seconds > max_bar_age:
            return self._create_no_signal(
                "Stale bar: age %.1fh > limit %.1fh (bar UTC=%s)"
                % (bar_age_seconds / 3600, max_bar_age / 3600, bar_time_utc)
            )

        # Mark bar as processed
        self._last_processed_bar_time = bar_time_utc

        # --- Compute indicators ---
        fast, slow = self._compute_dtosc(df)
        atr_series = self._atr_wilder(df, self.atr_period)

        fast_now = float(fast.iloc[-1])
        slow_now = float(slow.iloc[-1])
        atr_val = float(atr_series.iloc[-1])
        close_val = float(df["close"].iloc[-1])
        high_val = float(df["high"].iloc[-1])
        low_val = float(df["low"].iloc[-1])

        if math.isnan(atr_val) or atr_val <= 0:
            return self._create_no_signal("ATR invalid: %.4f" % atr_val)

        # Track swing low continuously (matches BT)
        self._track_swing_low(fast_now, low_val)

        # Update regime (D1 if available, else from intraday bars)
        if d1_df is not None:
            self._update_regime_from_d1(d1_df)
        else:
            self._update_regime(df)

        # --- If IN_POSITION: count bars held, no new signals ---
        if self._in_position:
            self._bars_held += 1
            return self._create_no_signal(
                "IN_POSITION (bars_held=%d)" % self._bars_held
            )

        # --- TRIGGERED state: Tr-1BH confirmation ---
        if self._state == "TRIGGERED":
            return self._handle_triggered(
                df, fast_now, slow_now, atr_val, close_val, high_val,
                bar_time_utc,
            )

        # --- SCANNING state: check for new entry ---

        # Time filter (UTC)
        if self.use_time_filter:
            if bar_time_utc.hour not in self.allowed_hours:
                return self._create_no_signal(
                    "Time filter: UTC %dh not in %s" % (bar_time_utc.hour, self.allowed_hours)
                )

        # Day filter (UTC)
        if self.use_day_filter:
            if bar_time_utc.weekday() not in self.allowed_days:
                return self._create_no_signal("Day filter: weekday %d" % bar_time_utc.weekday())

        # Max entries per day
        if self.max_entries_per_day > 0:
            current_date = bar_time_utc.date()
            if self._last_trade_date != current_date:
                self._last_trade_date = current_date
                self._trades_today = 0
            if self._trades_today >= self.max_entries_per_day:
                return self._create_no_signal(
                    "Max entries/day: %d/%d" % (self._trades_today, self.max_entries_per_day)
                )

        # Regime filter
        if self.regime_enabled:
            if self._regime_state != "CALM_UP":
                return self._create_no_signal("Regime: %s (need CALM_UP)" % self._regime_state)

        # DTOSC cross-up from oversold
        if not self._check_dtosc_crossup(fast, slow):
            return self._create_no_signal("No DTOSC cross-up")

        # --- All conditions met: transition to TRIGGERED ---
        if self.use_tr1bh:
            self._state = "TRIGGERED"
            self._triggered_bar_count = 0
            self._triggered_buy_stop = high_val + self.tr1bh_tick
            # Freeze swing low at trigger time (matches BT)
            self._frozen_swing_low = (
                self._swing_low if self._swing_low != float("inf") else None
            )
            sw_str = "%.2f" % self._frozen_swing_low if self._frozen_swing_low else "N/A"
            self.logger.info(
                "[%s] TRIGGERED: buy_stop=%.2f swing_low=%s | "
                "DTOSC fast=%.1f slow=%.1f | Regime=%s",
                self.config_name, self._triggered_buy_stop, sw_str,
                fast_now, slow_now, self._regime_state,
            )
            return self._create_no_signal(
                "TRIGGERED: waiting for price confirmation (buy_stop=%.2f)"
                % self._triggered_buy_stop
            )
        else:
            # V1 fallback: direct entry (no Tr-1BH)
            return self._try_direct_entry(
                df, atr_val, close_val, bar_time_utc,
            )

    # =========================================================================
    # TRIGGERED STATE HANDLER
    # =========================================================================

    def _handle_triggered(
        self,
        df: pd.DataFrame,
        fast_now: float,
        slow_now: float,
        atr_val: float,
        close_val: float,
        high_val: float,
        bar_time_utc: datetime,
    ) -> Signal:
        """Handle TRIGGERED state (Trailing One-Bar High confirmation).

        Matches _handle_triggered() in altair_strategy.py.
        """
        self._triggered_bar_count += 1

        # Check DTOSC alignment (fast must stay above slow)
        if fast_now < slow_now:
            self._state = "SCANNING"
            self.logger.info(
                "[%s] TRIGGERED->SCANNING: DTOSC lost alignment "
                "(fast=%.1f < slow=%.1f)",
                self.config_name, fast_now, slow_now,
            )
            return self._create_no_signal("TRIGGERED cancelled: DTOSC alignment lost")

        # Check timeout
        if self._triggered_bar_count >= self.tr1bh_timeout:
            self._state = "SCANNING"
            self.logger.info(
                "[%s] TRIGGERED->SCANNING: Timeout (%d bars)",
                self.config_name, self.tr1bh_timeout,
            )
            return self._create_no_signal("TRIGGERED cancelled: timeout")

        # Check if price broke buy stop
        if high_val >= self._triggered_buy_stop:
            # Price confirmed! Check max SL distance before entering
            entry_price = close_val

            if (self.use_swing_low_sl
                    and self._frozen_swing_low is not None
                    and self.max_sl_atr_mult > 0
                    and not math.isnan(atr_val) and atr_val > 0):
                sl_level = self._frozen_swing_low - self.tr1bh_tick
                sl_dist = entry_price - sl_level
                if sl_dist > self.max_sl_atr_mult * atr_val:
                    self._state = "SCANNING"
                    self.logger.info(
                        "[%s] TRIGGERED->SCANNING: SL too wide "
                        "(%.2f > %.1fx ATR=%.2f)",
                        self.config_name, sl_dist,
                        self.max_sl_atr_mult, atr_val,
                    )
                    return self._create_no_signal(
                        "SL too wide: %.2f > %.1fx ATR" % (sl_dist, self.max_sl_atr_mult)
                    )

            # --- Execute entry signal ---
            return self._emit_entry_signal(
                df, atr_val, entry_price, bar_time_utc,
            )
        else:
            # Trail buy stop to current bar's high
            self._triggered_buy_stop = high_val + self.tr1bh_tick
            self.logger.debug(
                "[%s] TRIGGERED bar %d/%d: trailing buy_stop=%.2f",
                self.config_name, self._triggered_bar_count,
                self.tr1bh_timeout, self._triggered_buy_stop,
            )
            return self._create_no_signal(
                "TRIGGERED: trailing (bar %d/%d, buy_stop=%.2f)"
                % (self._triggered_bar_count, self.tr1bh_timeout, self._triggered_buy_stop)
            )

    # =========================================================================
    # ENTRY SIGNAL EMISSION
    # =========================================================================

    def _emit_entry_signal(
        self,
        df: pd.DataFrame,
        atr_val: float,
        entry_price: float,
        bar_time_utc: datetime,
    ) -> Signal:
        """Build and emit LONG entry signal.

        Matches _execute_entry() in altair_strategy.py for SL/TP levels.
        """
        # SL level
        if self.use_swing_low_sl and self._frozen_swing_low is not None:
            stop_loss = self._frozen_swing_low - self.tr1bh_tick
            sl_dist = entry_price - stop_loss
            if sl_dist <= 0:
                self._state = "SCANNING"
                return self._create_no_signal("Swing low above entry -- invalid")
        else:
            sl_dist = atr_val * self.sl_atr_mult
            stop_loss = entry_price - sl_dist

        # TP level (always ATR-based)
        take_profit = entry_price + atr_val * self.tp_atr_mult

        # Transition state
        self._state = "SCANNING"  # Reset for next signal search
        self._in_position = True
        self._entry_bar_time = bar_time_utc
        self._bars_held = 0
        self._triggered_bar_count = 0
        self._trades_today += 1

        self.logger.info(
            "[%s] ALTAIR SIGNAL: LONG | UTC=%s | "
            "entry=%.2f SL=%.2f TP=%.2f | "
            "SL_dist=%.2f (%.1fx ATR) | ATR=%.2f | "
            "Regime=%s | DTOSC OS=%d",
            self.config_name, bar_time_utc.strftime("%Y-%m-%d %H:%M"),
            entry_price, stop_loss, take_profit,
            sl_dist, sl_dist / atr_val if atr_val > 0 else 0, atr_val,
            self._regime_state, self.dtosc_os,
        )

        signal = self._create_signal(
            direction=SignalDirection.LONG,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            atr=atr_val,
            reason=(
                "ALTAIR LONG | SL=%.2f TP=%.2f | "
                "swing_low=%s | ATR=%.2f"
                % (
                    stop_loss, take_profit,
                    "%.2f" % self._frozen_swing_low if self._frozen_swing_low else "N/A",
                    atr_val,
                )
            ),
        )

        # Attach metadata for sizing and time-exit
        signal.sl_distance = sl_dist
        signal.holding_bars = self.max_holding_bars

        return signal

    def _try_direct_entry(
        self,
        df: pd.DataFrame,
        atr_val: float,
        close_val: float,
        bar_time_utc: datetime,
    ) -> Signal:
        """V1 fallback: direct entry without Tr-1BH confirmation."""
        entry_price = close_val

        # Freeze swing low
        self._frozen_swing_low = (
            self._swing_low if self._swing_low != float("inf") else None
        )

        # Check max SL distance
        if (self.use_swing_low_sl
                and self._frozen_swing_low is not None
                and self.max_sl_atr_mult > 0
                and atr_val > 0):
            sl_level = self._frozen_swing_low - self.tr1bh_tick
            sl_dist = entry_price - sl_level
            if sl_dist > self.max_sl_atr_mult * atr_val:
                return self._create_no_signal(
                    "SL too wide: %.2f > %.1fx ATR" % (sl_dist, self.max_sl_atr_mult)
                )

        self._trades_today += 1
        return self._emit_entry_signal(df, atr_val, entry_price, bar_time_utc)

    # =========================================================================
    # POSITION EXIT NOTIFICATION (called by multi_monitor)
    # =========================================================================

    def notify_position_closed(self):
        """Called when the position is closed (SL/TP/TIME_EXIT).

        Resets IN_POSITION so the checker can scan for new signals.
        """
        self._in_position = False
        self._entry_bar_time = None
        self._bars_held = 0
        self.logger.info(
            "[%s] Position closed notification -- returning to SCANNING",
            self.config_name,
        )
