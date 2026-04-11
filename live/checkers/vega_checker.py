"""
VEGA Strategy Checker for Live Trading.

Cross-Index Z-Score Divergence (London Repricing).
Requires TWO data feeds: leader index (e.g., SP500) and traded target (e.g., NI225).

Concept:
    Overnight SP500 moves create temporary divergence vs regional indices.
    During London session (07-12 UTC), repricing corrects this divergence.

Signal:
    z = (Close - SMA(24)) / ATR(24)  for each index
    spread = z_leader - z_target
    forecast = clip(spread / dead_zone * 20, -20, +20)
    direction = -sign(forecast)  (negative predictive correlation)

Exit: Time-based (holding_hours H4 bars), SL/TP on MT5 server as safety net.

Data feeds (matching BT convention):
    df            = leader index bars (SP500/NDX)   -- "Index A" in BT
    reference_df  = traded target bars (NI225/GDAXI) -- "Index B" in BT
"""

import math
import logging
import datetime as _dt
from datetime import datetime
from typing import Optional, Dict, Any

import pandas as pd
import numpy as np

from .base_checker import BaseChecker, Signal, SignalDirection


class VEGAChecker(BaseChecker):
    """
    VEGA strategy signal checker.

    Stateless per-bar check: compute z-score spread, apply filters, emit signal.
    Tracks last processed bar time to avoid duplicate signals on same H4 bar.
    """

    @property
    def strategy_name(self) -> str:
        return "VEGA"

    def __init__(
        self,
        config_name: str,
        params: Dict[str, Any],
        logger: Optional[logging.Logger] = None
    ):
        super().__init__(config_name, params, logger)

        # Z-score params
        self.sma_period = params.get("sma_period", 24)
        self.atr_period = params.get("atr_period", 24)

        # Signal
        self.dead_zone = params.get("dead_zone", 1.0)
        self.max_forecast = params.get("max_forecast", 20)
        self.min_forecast_entry = params.get("min_forecast_entry", 1)

        # Direction filter
        self.allow_long = params.get("allow_long", True)
        self.allow_short = params.get("allow_short", True)

        # Session / holding
        self.holding_hours = params.get("holding_hours", 3)
        self.max_trades_per_day = params.get("max_trades_per_day", 0)

        # DST
        self.dst_mode = params.get("dst_mode", "none")
        self.base_allowed_hours = list(params.get("allowed_hours", [7, 8, 9, 10, 11, 12]))

        # ATR filter
        self.min_atr_entry = params.get("min_atr_entry", 0.0)
        self.max_atr_entry = params.get("max_atr_entry", 0.0)

        # Stop / TP
        self.protective_atr_mult = params.get("protective_atr_mult", 3.5)
        self.tp_atr_mult = params.get("tp_atr_mult", 0.0)

        # Sizing (margin-allocation, NOT SL-based)
        self.capital_alloc_pct = params.get("capital_alloc_pct", 0.10)
        self.max_position_pct = params.get("max_position_pct", 0.10)
        self.max_loss_per_trade_pct = params.get("max_loss_per_trade_pct", 0.05)
        self.margin_pct_bt = params.get("margin_pct", 5.0)  # BT assumption, NOT broker's real margin
        self.is_jpy_pair = params.get("is_jpy_pair", False)
        self.jpy_rate = params.get("jpy_rate", 1.0)

        # State tracking
        self._last_processed_bar_time = None
        self._today_date = None
        self._today_allowed_hours = list(self.base_allowed_hours)
        self._trades_today = 0
        self._last_trade_date = None

        self.logger.info(
            f"[{self.config_name}] VEGA Checker initialized | "
            f"SMA={self.sma_period}, ATR={self.atr_period}, "
            f"DZ={self.dead_zone}, holding={self.holding_hours}H4bars | "
            f"DST={self.dst_mode} | "
            f"long={'Y' if self.allow_long else 'N'} "
            f"short={'Y' if self.allow_short else 'N'}"
        )

    def reset_state(self) -> None:
        """Reset checker state."""
        self._last_processed_bar_time = None
        self._today_date = None
        self._today_allowed_hours = list(self.base_allowed_hours)
        self._trades_today = 0
        self._last_trade_date = None

    def get_state_info(self) -> Dict[str, Any]:
        """Get current state for logging."""
        return {
            "strategy": self.strategy_name,
            "last_bar_time": str(self._last_processed_bar_time),
            "trades_today": self._trades_today,
            "dst_hours": self._today_allowed_hours,
        }

    # =========================================================================
    # DST (ported from vega_strategy.py — proven correct after commit 7aa2331)
    # =========================================================================

    @staticmethod
    def _bst_boundaries(year):
        """BST: last Sunday of March .. last Sunday of October."""
        mar31 = _dt.date(year, 3, 31)
        bst_start = mar31 - _dt.timedelta(days=(mar31.weekday() + 1) % 7)
        oct31 = _dt.date(year, 10, 31)
        bst_end = oct31 - _dt.timedelta(days=(oct31.weekday() + 1) % 7)
        return bst_start, bst_end

    @staticmethod
    def _us_dst_boundaries(year):
        """US DST: 2nd Sunday of March .. 1st Sunday of November."""
        mar1 = _dt.date(year, 3, 1)
        first_sun_mar = mar1 + _dt.timedelta(days=(6 - mar1.weekday()) % 7)
        dst_start = first_sun_mar + _dt.timedelta(days=7)
        nov1 = _dt.date(year, 11, 1)
        dst_end = nov1 + _dt.timedelta(days=(6 - nov1.weekday()) % 7)
        return dst_start, dst_end

    def _dst_offset_hours(self, today):
        """Return hour offset for DST (-1 in summer, 0 in winter)."""
        if self.dst_mode == "none":
            return 0
        if self.dst_mode == "us":
            dst_start, dst_end = self._us_dst_boundaries(today.year)
            return -1 if dst_start <= today < dst_end else 0
        if self.dst_mode == "london_uk":
            bst_start, bst_end = self._bst_boundaries(today.year)
            return -1 if bst_start <= today < bst_end else 0
        return 0

    def _update_dst(self, today):
        """Recompute DST-adjusted allowed_hours once per day."""
        if today == self._today_date:
            return
        self._today_date = today
        offset = self._dst_offset_hours(today)
        self._today_allowed_hours = [h + offset for h in self.base_allowed_hours]
        if offset != 0:
            self.logger.info(
                f"[{self.config_name}] DST update: offset={offset}h, "
                f"hours={self._today_allowed_hours}"
            )

    # =========================================================================
    # CALCULATIONS
    # =========================================================================

    def _calculate_sma(self, series: pd.Series, period: int) -> float:
        """Calculate Simple Moving Average from pandas Series."""
        if len(series) < period:
            return float("nan")
        return float(series.iloc[-period:].mean())

    def _calculate_atr(self, df: pd.DataFrame, period: int) -> float:
        """Calculate ATR using Wilder's RMA (matches backtrader bt.ind.ATR)."""
        if len(df) < period + 1:
            return float("nan")

        high = df["high"]
        low = df["low"]
        close = df["close"]

        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        # Wilder's RMA (alpha = 1/period)
        atr_series = tr.ewm(alpha=1.0 / period, adjust=False).mean()
        return float(atr_series.iloc[-1])

    def _compute_zscore(self, close_val: float, sma_val: float, atr_val: float) -> float:
        """Compute z-score: (close - SMA) / ATR."""
        if atr_val <= 0 or math.isnan(atr_val) or math.isnan(sma_val):
            return 0.0
        return (close_val - sma_val) / atr_val

    def _compute_forecast(self, spread: float) -> float:
        """Continuous forecast in [-max_forecast, +max_forecast]."""
        if self.dead_zone <= 0:
            return 0.0
        raw = spread / self.dead_zone * self.max_forecast
        return max(-self.max_forecast, min(self.max_forecast, raw))

    # =========================================================================
    # VEGA LOT SIZING (margin-allocation, matches BT exactly)
    # =========================================================================

    def calculate_vega_lots(
        self,
        equity: float,
        entry_price: float,
        atr_val: float,
        forecast: float,
        symbol_info: dict,
    ) -> float:
        """
        Calculate lot size using VEGA's margin-allocation method.

        This matches the BT sizing in vega_strategy.py _execute_entry():
        1. margin_per_contract = entry_price * (margin_pct_bt / 100)
        2. max_margin = equity * capital_alloc_pct * |forecast/max_forecast|
        3. contracts = max_margin / margin_per_contract
        4. Capped by max_position_pct and max_loss_per_trade_pct

        Uses BT's margin_pct (5%), NOT broker's real margin (0.5%),
        to produce the same contract count as BT for the same equity.

        Args:
            equity: Account equity in USD
            entry_price: Current price of traded index
            atr_val: Current ATR of traded index
            forecast: Forecast value [-20, +20]
            symbol_info: MT5 symbol info dict (for min_lot, max_lot, lot_step)

        Returns:
            Lot size (volume) for MT5 order
        """
        position_fraction = abs(forecast) / self.max_forecast

        # Margin per contract using BT assumption (5%), not broker's 0.5%
        margin_per_contract = entry_price * (self.margin_pct_bt / 100.0)
        if self.is_jpy_pair and self.jpy_rate > 1:
            margin_per_contract = margin_per_contract / self.jpy_rate

        if margin_per_contract <= 0:
            return 0.0

        # Capital allocation proportional to forecast strength
        max_margin = equity * self.capital_alloc_pct * position_fraction
        contracts = int(max_margin / margin_per_contract)

        # Match BT: if forecast too weak for even 1 contract, skip trade.
        # FIX 2026-04-11: Audit #3 Hallazgo #3. Previously fell back to
        # volume_min (0.1), creating tiny positions the BT would never take.
        if contracts < 1:
            return 0.0

        # Cap at absolute max position
        abs_max = int((equity * self.max_position_pct) / margin_per_contract)
        contracts = min(contracts, max(1, abs_max))

        # DD cap: if protective stop hit, max loss <= max_loss_per_trade_pct
        if atr_val > 0 and self.protective_atr_mult > 0:
            stop_dist = atr_val * self.protective_atr_mult
            loss_per_contract = stop_dist
            if self.is_jpy_pair and self.jpy_rate > 1:
                loss_per_contract = loss_per_contract / self.jpy_rate
            max_loss = equity * self.max_loss_per_trade_pct
            if loss_per_contract > 0:
                dd_cap = int(max_loss / loss_per_contract)
                if dd_cap < contracts:
                    contracts = max(1, dd_cap)

        # Clamp to broker limits
        min_lot = symbol_info.get("volume_min", 1.0)
        max_lot = symbol_info.get("volume_max", 1000.0)
        lot_step = symbol_info.get("volume_step", 1.0)

        volume = float(contracts)
        volume = round(volume / lot_step) * lot_step
        volume = max(min_lot, min(volume, max_lot))

        return volume

    # =========================================================================
    # SIGNAL CHECK
    # =========================================================================

    def check_signal(
        self,
        df: pd.DataFrame,
        reference_df: Optional[pd.DataFrame] = None,
    ) -> Signal:
        """
        Check for VEGA trading signal.

        Args:
            df: Leader index H4 bars (SP500/NDX) — "Index A" in BT
            reference_df: Traded target H4 bars (NI225/GDAXI) — "Index B" in BT

        Returns:
            Signal with direction, entry/SL/TP, and metadata including forecast
        """
        self.current_bar_index += 1

        # Require both feeds
        if reference_df is None or reference_df.empty:
            return self._create_no_signal("No reference (traded) data")
        if len(df) < self.sma_period + 5 or len(reference_df) < self.sma_period + 5:
            return self._create_no_signal("Insufficient data for SMA/ATR warmup")

        # data_provider.get_bars(include_current=False) already excludes the
        # forming bar.  df[-1] / reference_df[-1] are the last CLOSED bars,
        # equivalent to close[0] in BT's next().
        # FIX 2026-04-05: removed redundant iloc[:-1] that caused 1-bar (4h) lag.

        # Get bar time from traded index (reference_df = Index B = traded)
        # FIX 2026-04-11: bars arrive in UTC (resampled from M5 by multi_monitor).
        # Previously arrived in broker time and needed broker_to_utc().
        if "time" in reference_df.columns:
            bar_time_utc = reference_df["time"].iloc[-1]
            if isinstance(bar_time_utc, pd.Timestamp):
                bar_time_utc = bar_time_utc.to_pydatetime()
        else:
            return self._create_no_signal("No 'time' column in traded data")

        # Skip if we already processed this bar
        if self._last_processed_bar_time is not None:
            if bar_time_utc == self._last_processed_bar_time:
                return self._create_no_signal("Same H4 bar already processed")

        utc_time = bar_time_utc  # Already UTC after M5->H4 resample

        # Stale bar guard: reject bars older than 1 H4 period (4h + 30min buffer)
        # Prevents phantom signals on weekend/holiday restarts.
        # FIX 2026-04-05 v0.7.2: bot started Saturday, processed Friday's bar,
        # MT5 rejected (10017 trade disabled), signal consumed and lost.
        from datetime import datetime as _dt, timezone as _tz
        now_utc = _dt.now(_tz.utc).replace(tzinfo=None)
        bar_age_seconds = (now_utc - utc_time).total_seconds()
        max_bar_age_seconds = 4 * 3600 + 1800  # 4h30m
        if bar_age_seconds > max_bar_age_seconds:
            return self._create_no_signal(
                f"Stale bar: age {bar_age_seconds/3600:.1f}h > limit 4.5h "
                f"(bar UTC={utc_time}, now UTC={now_utc:%H:%M})"
            )

        # === COMPUTE Z-SCORES (on closed bars — forming bar already excluded) ===
        df_closed = df
        ref_closed = reference_df

        # Index A (leader) — SMA, ATR, z-score
        sma_a = self._calculate_sma(df_closed["close"], self.sma_period)
        atr_a = self._calculate_atr(df_closed, self.atr_period)
        close_a = float(df_closed["close"].iloc[-1])

        # Index B (traded target) — SMA, ATR, z-score
        sma_b = self._calculate_sma(ref_closed["close"], self.sma_period)
        atr_b = self._calculate_atr(ref_closed, self.atr_period)
        close_b = float(ref_closed["close"].iloc[-1])

        if math.isnan(atr_a) or math.isnan(atr_b) or atr_a <= 0 or atr_b <= 0:
            return self._create_no_signal(f"ATR invalid: A={atr_a}, B={atr_b}")

        z_a = self._compute_zscore(close_a, sma_a, atr_a)
        z_b = self._compute_zscore(close_b, sma_b, atr_b)
        spread = z_a - z_b
        forecast = self._compute_forecast(spread)

        # Mark bar as processed BEFORE filters (avoid re-processing on rejection)
        self._last_processed_bar_time = bar_time_utc

        # === FILTERS ===

        # DST-adjusted hours (once per day)
        self._update_dst(utc_time.date())

        # Time filter
        if self.params.get("use_time_filter"):
            if utc_time.hour not in self._today_allowed_hours:
                return self._create_no_signal(
                    f"Time filter: UTC {utc_time.hour}h not in {self._today_allowed_hours}"
                )

        # Day filter
        if self.params.get("use_day_filter"):
            allowed_days = self.params.get("allowed_days", [0, 1, 2, 3, 4])
            if utc_time.weekday() not in allowed_days:
                day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
                return self._create_no_signal(
                    f"Day filter: {day_names[utc_time.weekday()]} not allowed"
                )

        # Max trades per day
        if self.max_trades_per_day > 0:
            current_date = utc_time.date()
            if self._last_trade_date != current_date:
                self._last_trade_date = current_date
                self._trades_today = 0
            if self._trades_today >= self.max_trades_per_day:
                return self._create_no_signal(
                    f"Max trades/day reached: {self._trades_today}/{self.max_trades_per_day}"
                )

        # ATR(B) volatility filter
        if self.min_atr_entry > 0 and atr_b < self.min_atr_entry:
            return self._create_no_signal(f"ATR(B) {atr_b:.1f} < min {self.min_atr_entry}")
        if self.max_atr_entry > 0 and atr_b > self.max_atr_entry:
            return self._create_no_signal(f"ATR(B) {atr_b:.1f} > max {self.max_atr_entry}")

        # Dead zone / forecast threshold
        if abs(forecast) < self.min_forecast_entry:
            return self._create_no_signal(
                f"Forecast {forecast:.1f} below threshold {self.min_forecast_entry} "
                f"(spread={spread:.3f}, dz={self.dead_zone})"
            )

        # === DIRECTION ===
        # Negative predictive correlation: -sign(forecast)
        if forecast > 0:
            direction = SignalDirection.SHORT  # spread > 0 → SHORT target
        else:
            direction = SignalDirection.LONG   # spread < 0 → LONG target

        # Direction filter
        if direction == SignalDirection.LONG and not self.allow_long:
            return self._create_no_signal("LONG disabled for this config")
        if direction == SignalDirection.SHORT and not self.allow_short:
            return self._create_no_signal("SHORT disabled for this config")

        # === ENTRY / SL / TP ===
        entry_price = close_b

        # SL: protective stop
        if direction == SignalDirection.LONG:
            stop_loss = entry_price - (atr_b * self.protective_atr_mult)
        else:
            stop_loss = entry_price + (atr_b * self.protective_atr_mult)

        # TP: take profit (0 = disabled → use very wide TP as placeholder)
        if self.tp_atr_mult > 0:
            if direction == SignalDirection.LONG:
                take_profit = entry_price + (atr_b * self.tp_atr_mult)
            else:
                take_profit = entry_price - (atr_b * self.tp_atr_mult)
        else:
            # No TP — use very wide value (time-exit handles it)
            if direction == SignalDirection.LONG:
                take_profit = entry_price + (atr_b * 10.0)
            else:
                take_profit = entry_price - (atr_b * 10.0)

        # Update trades today
        self._trades_today += 1

        # Log signal details
        self.logger.info(
            f"[{self.config_name}] VEGA SIGNAL: {direction.value} | "
            f"UTC: {utc_time:%H:%M} | "
            f"z_A={z_a:.3f}, z_B={z_b:.3f}, spread={spread:.3f}, "
            f"forecast={forecast:.1f} | "
            f"entry={entry_price:.1f}, SL={stop_loss:.1f}, TP={take_profit:.1f} | "
            f"ATR(B)={atr_b:.1f}"
        )

        signal = self._create_signal(
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            atr=atr_b,
            reason=(
                f"VEGA {direction.value} | spread={spread:.3f} "
                f"forecast={forecast:.1f} | "
                f"z_A={z_a:.3f} z_B={z_b:.3f}"
            ),
        )

        # Attach metadata for sizing and time-exit
        signal.forecast = forecast
        signal.position_fraction = abs(forecast) / self.max_forecast
        signal.holding_bars = self.holding_hours

        return signal
