"""ORION market-order executor.

Direct BUY/SELL market orders for the manual observation tool. Strict
guards by design (DEMO-only, spread filter, lot rounding to broker
constraints, hard cap on risk).

NOT live trading infrastructure. This is a development helper for the
manual GEX workflow: one click -> one market order with SL/TP at
fixed % distance from fill price (1:1 R:R).

Public API:
    OrionOrderExecutor(spot_provider, log_dir)
    .compute_plan(ticker, side, sl_pct, risk_pct) -> Plan or error
    .execute(plan) -> dict (mt5 result + persisted to orders.jsonl)
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
from dataclasses import dataclass, asdict
from typing import Optional, Tuple


# Hard limits (defense in depth). Even if the GUI passes silly values,
# the executor refuses to send anything beyond these.
MAX_RISK_PCT = 0.02         # never risk more than 2% per click
MAX_SPREAD_FRACTION = 0.30  # spread must be <= 30% of SL distance
DEMO_TRADE_MODE = 0         # MT5: 0 = DEMO, 1 = CONTEST, 2 = REAL


@dataclass
class OrderPlan:
    ticker: str
    symbol: str           # MT5 symbol name
    side: str             # "BUY" or "SELL"
    entry_price: float    # ask for BUY, bid for SELL
    sl_price: float
    tp_price: float
    sl_pct: float
    risk_pct: float
    lots: float
    contract_size: float
    equity: float
    risk_money: float
    spread_price: float
    spread_fraction: float  # spread / sl_distance
    notes: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


class OrionOrderError(Exception):
    pass


class OrionOrderExecutor:
    """Wraps MT5 order_send with ORION-specific guards."""

    def __init__(self, spot_provider, log_dir: str):
        self._spot = spot_provider
        self._log_dir = log_dir
        os.makedirs(self._log_dir, exist_ok=True)
        self._orders_log = os.path.join(self._log_dir, "orders.jsonl")

    # ---- preflight ---------------------------------------------------

    def is_demo_account(self) -> Tuple[bool, str]:
        """Return (is_demo, message). Refuses if MT5 unavailable."""
        mt5 = self._spot.mt5()
        if mt5 is None:
            return False, "MT5 not connected"
        info = mt5.account_info()
        if info is None:
            return False, "account_info unavailable"
        if int(info.trade_mode) != DEMO_TRADE_MODE:
            return False, (
                f"account is NOT demo (trade_mode={info.trade_mode}); "
                f"orders blocked"
            )
        return True, f"DEMO account #{info.login}, equity {info.equity:.2f}"

    # ---- planning ----------------------------------------------------

    def compute_plan(
        self,
        ticker: str,
        side: str,
        sl_pct: float,
        risk_pct: float,
    ) -> OrderPlan:
        """Build an OrderPlan with all numbers rounded to broker steps.

        Raises OrionOrderError on any precondition failure (so the GUI
        can show a single explanatory message).
        """
        side = side.upper()
        if side not in ("BUY", "SELL"):
            raise OrionOrderError(f"invalid side: {side}")
        if not (0 < sl_pct < 0.05):
            raise OrionOrderError(f"sl_pct out of range: {sl_pct}")
        if not (0 < risk_pct <= MAX_RISK_PCT):
            raise OrionOrderError(
                f"risk_pct out of range (max {MAX_RISK_PCT}): {risk_pct}"
            )

        mt5 = self._spot.mt5()
        if mt5 is None:
            raise OrionOrderError("MT5 not connected")

        symbol = self._spot.resolve(ticker)
        if symbol is None:
            raise OrionOrderError(f"symbol not found in MT5 for {ticker}")

        sym_info = mt5.symbol_info(symbol)
        if sym_info is None:
            raise OrionOrderError(f"symbol_info({symbol}) failed")

        tick = mt5.symbol_info_tick(symbol)
        if tick is None or not tick.bid or not tick.ask:
            raise OrionOrderError(f"no live tick for {symbol}")

        bid = float(tick.bid)
        ask = float(tick.ask)
        spread = ask - bid

        if side == "BUY":
            entry = ask
            sl = entry * (1.0 - sl_pct)
            tp = entry * (1.0 + sl_pct)  # 1:1 R:R
        else:
            entry = bid
            sl = entry * (1.0 + sl_pct)
            tp = entry * (1.0 - sl_pct)

        sl_distance = abs(entry - sl)
        if sl_distance <= 0:
            raise OrionOrderError("computed SL distance is zero")

        spread_fraction = spread / sl_distance if sl_distance > 0 else 1.0
        if spread_fraction > MAX_SPREAD_FRACTION:
            raise OrionOrderError(
                f"spread too wide: {spread:.4f} = "
                f"{spread_fraction*100:.1f}% of SL distance "
                f"(max {MAX_SPREAD_FRACTION*100:.0f}%). "
                f"Wait for tighter spread or increase SL%."
            )

        # Sizing: risk_money = equity * risk_pct
        # money_at_risk_per_lot = sl_distance * contract_size
        # lots = risk_money / money_at_risk_per_lot
        acc = mt5.account_info()
        if acc is None:
            raise OrionOrderError("account_info unavailable")
        equity = float(acc.equity)
        risk_money = equity * risk_pct
        contract_size = float(sym_info.trade_contract_size or 1.0)
        loss_per_lot = sl_distance * contract_size
        if loss_per_lot <= 0:
            raise OrionOrderError("loss_per_lot is zero")
        raw_lots = risk_money / loss_per_lot

        # Round DOWN to volume_step, clamp to [volume_min, volume_max].
        vstep = float(sym_info.volume_step or 0.01)
        vmin = float(sym_info.volume_min or 0.01)
        vmax = float(sym_info.volume_max or 100.0)
        steps = math.floor(raw_lots / vstep)
        lots = max(vmin, min(vmax, steps * vstep))
        if lots < vmin:
            raise OrionOrderError(
                f"computed lots {raw_lots:.4f} below volume_min {vmin}"
            )

        # Round prices to broker digits.
        digits = int(sym_info.digits or 2)
        entry = round(entry, digits)
        sl = round(sl, digits)
        tp = round(tp, digits)

        notes = (
            f"raw_lots={raw_lots:.4f} step={vstep} "
            f"contract_size={contract_size} digits={digits}"
        )

        return OrderPlan(
            ticker=ticker,
            symbol=symbol,
            side=side,
            entry_price=entry,
            sl_price=sl,
            tp_price=tp,
            sl_pct=sl_pct,
            risk_pct=risk_pct,
            lots=lots,
            contract_size=contract_size,
            equity=equity,
            risk_money=risk_money,
            spread_price=spread,
            spread_fraction=spread_fraction,
            notes=notes,
        )

    # ---- execution ---------------------------------------------------

    def execute(self, plan: OrderPlan, comment: str = "ORION") -> dict:
        """Send the market order and persist the outcome."""
        mt5 = self._spot.mt5()
        if mt5 is None:
            raise OrionOrderError("MT5 not connected")

        # Refuse non-demo at send time as well (defense in depth).
        is_demo, msg = self.is_demo_account()
        if not is_demo:
            raise OrionOrderError(msg)

        order_type = (
            mt5.ORDER_TYPE_BUY if plan.side == "BUY"
            else mt5.ORDER_TYPE_SELL
        )

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": plan.symbol,
            "volume": plan.lots,
            "type": order_type,
            "price": plan.entry_price,
            "sl": plan.sl_price,
            "tp": plan.tp_price,
            "deviation": 20,
            "magic": 990001,
            "comment": comment[:31],
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        ts = dt.datetime.now().isoformat(timespec="seconds")

        if result is None:
            err = mt5.last_error()
            record = {
                "ts": ts, "status": "send_failed",
                "error": str(err), "request": request,
            }
            self._persist(record)
            raise OrionOrderError(f"order_send returned None: {err}")

        record = {
            "ts": ts,
            "status": "ok" if result.retcode == mt5.TRADE_RETCODE_DONE
            else "rejected",
            "retcode": int(result.retcode),
            "comment": str(result.comment),
            "deal": int(result.deal) if result.deal else None,
            "order": int(result.order) if result.order else None,
            "price": float(result.price) if result.price else None,
            "volume": float(result.volume) if result.volume else None,
            "plan": plan.as_dict(),
        }
        self._persist(record)
        return record

    # ---- internals ---------------------------------------------------

    def _persist(self, record: dict) -> None:
        try:
            with open(self._orders_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            pass
