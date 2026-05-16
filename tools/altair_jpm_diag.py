"""Diag: dump JPM 30m bars + ALTAIR internals around 2026-05-04 live signal.

Live triggered JPM_ALTAIR LONG at UTC=2026-05-04 18:00 with entry=307.88,
SL=306.49, TP=313.35, ATR=1.37, DTOSC OS=20, Regime=CALM_UP.
BT (Dukascopy 5m -> 30m resample) shows ZERO trades in 2026-05-02..05-16.

This script reproduces JPM_ALTAIR BT and dumps per-30m-bar diagnostics
(OHLC, DTOSC fast/slow, regime, ATR, state, swing_low) for the window
2026-05-01..2026-05-08 so we can see why the signal didn't fire.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import io
import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import backtrader as bt  # noqa: E402

from strategies.altair_strategy import ALTAIRStrategy  # noqa: E402
from config.settings_altair import (  # noqa: E402
    ALTAIR_STRATEGIES_CONFIG,
    ALTAIR_BROKER_CONFIG,
    _make_config,
)
from lib.commission import ETFCommission, ETFCSVData  # noqa: E402

DIAG_START = dt.datetime(2026, 5, 1, 0, 0)
DIAG_END = dt.datetime(2026, 5, 8, 23, 59)

BT_FROM = dt.datetime(2024, 1, 1)
BT_TO = dt.datetime(2026, 5, 16)


class JPMDiagStrategy(ALTAIRStrategy):
    """Wraps ALTAIRStrategy to dump per-bar internals in DIAG window."""

    def __init__(self):
        super().__init__()
        self._diag_rows = []

    def next(self):
        # Capture state BEFORE super().next() mutates it.
        dt_now = self.data_h1.datetime.datetime(0)
        in_window = DIAG_START <= dt_now <= DIAG_END
        pre_state = self.state

        if in_window:
            try:
                fast_now = float(self.dtosc.fast[0])
                fast_prev = float(self.dtosc.fast[-1])
                slow_now = float(self.dtosc.slow[0])
                slow_prev = float(self.dtosc.slow[-1])
            except (IndexError, ValueError):
                fast_now = fast_prev = slow_now = slow_prev = float('nan')
            try:
                atr_val = float(self.atr_h1[0])
            except (IndexError, ValueError):
                atr_val = float('nan')

            o = float(self.data_h1.open[0])
            h = float(self.data_h1.high[0])
            l = float(self.data_h1.low[0])
            c = float(self.data_h1.close[0])

        # Run normal logic
        super().next()

        if in_window:
            post_state = self.state
            regime = getattr(self, '_regime_state', '?')
            atr_ratio = getattr(self, '_regime_atr_ratio', float('nan'))
            mom63 = getattr(self, '_regime_mom63d', float('nan'))
            swing_low = self._swing_low if self._swing_low != float('inf') else None
            buy_stop = self._triggered_buy_stop if pre_state == "TRIGGERED" else None

            # Bullish cross check (matches _check_dtosc_signal logic)
            cross_up = (fast_now > slow_now) and (fast_prev <= slow_prev)
            from_os = (fast_prev < self.p.dtosc_os
                       or slow_prev < self.p.dtosc_os)
            sig_now = cross_up and from_os

            self._diag_rows.append(dict(
                dt=dt_now, o=o, h=h, l=l, c=c,
                atr=atr_val,
                fast=fast_now, slow=slow_now,
                fast_prev=fast_prev, slow_prev=slow_prev,
                cross_up=cross_up, from_os=from_os, signal=sig_now,
                regime=regime, atr_ratio=atr_ratio, mom63=mom63,
                pre_state=pre_state, post_state=post_state,
                swing_low=swing_low, buy_stop=buy_stop,
            ))


def main():
    base = ALTAIR_STRATEGIES_CONFIG["JPM_ALTAIR"]
    cfg = _make_config(
        "JPM", "JPM_5m_8Yea.csv", BT_FROM,
        active=True, universe=base.get("universe", "ndx"),
    )
    base_params = base["params"]
    for key in ("max_sl_atr_mult", "dtosc_os"):
        if key in base_params:
            cfg["params"][key] = base_params[key]
    cfg["params"]["bars_per_day"] = 13
    cfg["params"]["export_reports"] = False
    cfg["params"]["print_signals"] = True

    cerebro = bt.Cerebro(stdstats=False)
    data_path = PROJECT_ROOT / cfg["data_path"]
    data = ETFCSVData(
        dataname=str(data_path),
        dtformat="%Y%m%d", tmformat="%H:%M:%S",
        datetime=0, time=1, open=2, high=3, low=4, close=5,
        volume=6, openinterest=-1,
        fromdate=BT_FROM, todate=BT_TO,
    )
    cerebro.resampledata(data, timeframe=bt.TimeFrame.Minutes,
                         compression=30)._name = "JPM"

    cerebro.broker.setcash(100_000)
    bcfg = ALTAIR_BROKER_CONFIG.get("darwinex_zero_stock", {})
    cerebro.broker.addcommissioninfo(ETFCommission(
        commission=bcfg.get("commission_per_contract", 0.02),
        margin_pct=bcfg.get("margin_percent", 20.0),
    ))
    cerebro.addstrategy(JPMDiagStrategy, **cfg["params"])

    f = io.StringIO()
    with contextlib.redirect_stdout(f):
        res = cerebro.run()
    strat = res[0]
    captured = f.getvalue()

    print(f"=== JPM ALTAIR diag window {DIAG_START} -> {DIAG_END} ===")
    print(f"Config: dtosc_os={cfg['params'].get('dtosc_os')}, "
          f"max_sl_atr_mult={cfg['params'].get('max_sl_atr_mult')}, "
          f"bars_per_day={cfg['params'].get('bars_per_day')}\n")

    # Filter print_signals output for our window
    print("--- state transitions (print_signals) in window ---")
    target_strs = [d.strftime("%Y-%m-%d") for d in (
        DIAG_START + dt.timedelta(days=i) for i in range(9)
    )]
    for line in captured.splitlines():
        if any(s in line for s in target_strs):
            print(f"  {line}")

    print()
    print("--- per-bar internals (30m bars) ---")
    print(f"  {'dt':<19} {'O':>7} {'H':>7} {'L':>7} {'C':>7} {'ATR':>5} "
          f"{'fast':>6} {'slow':>6} {'fastP':>6} {'slowP':>6} "
          f"{'X':>2} {'OS':>2} {'SIG':>3} "
          f"{'regime':<12} {'mom63':>6} {'aRat':>5} "
          f"{'state':<10} {'->':<10} {'swL':>7} {'buyS':>7}")
    for r in strat._diag_rows:
        sl_str = f"{r['swing_low']:.2f}" if r['swing_low'] is not None else "-"
        bs_str = f"{r['buy_stop']:.2f}" if r['buy_stop'] else "-"
        print(f"  {r['dt'].strftime('%Y-%m-%d %H:%M'):<19} "
              f"{r['o']:>7.2f} {r['h']:>7.2f} {r['l']:>7.2f} {r['c']:>7.2f} "
              f"{r['atr']:>5.2f} "
              f"{r['fast']:>6.1f} {r['slow']:>6.1f} "
              f"{r['fast_prev']:>6.1f} {r['slow_prev']:>6.1f} "
              f"{'Y' if r['cross_up'] else '.':>2} "
              f"{'Y' if r['from_os'] else '.':>2} "
              f"{'YES' if r['signal'] else '.':>3} "
              f"{r['regime']:<12} {r['mom63']:>6.2f} {r['atr_ratio']:>5.2f} "
              f"{r['pre_state']:<10} {r['post_state']:<10} "
              f"{sl_str:>7} {bs_str:>7}")

    # Quick summary
    print()
    sigs = [r for r in strat._diag_rows if r['signal']]
    print(f"DTOSC signals fired in window: {len(sigs)}")
    for r in sigs:
        print(f"  {r['dt']} fast={r['fast']:.1f} slow={r['slow']:.1f} "
              f"fastP={r['fast_prev']:.1f} slowP={r['slow_prev']:.1f} "
              f"regime={r['regime']}")


if __name__ == "__main__":
    main()
