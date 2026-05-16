"""ALTAIR regime hysteresis BT comparison.

Tests the hypothesis that the binary regime filter (CALM_UP requires
atr_ratio < 1.0) is too fragile around the threshold. Compares baseline
vs hysteresis band [0.95, 1.05] where the previous regime is sticky
inside the band.

Tickers + TF + Config match the documented Live Demo FINAL table in
context/PROMPT_ALTAIR_LIVE.md (2026-04-15 decision):

    JPM    30m  Config B (os=20, max_sl=4.0)   PF doc: 1.57
    NVDA   15m  Config A (os=25, max_sl=2.0)   PF doc: 1.97
    GOOGL  15m  Config A (os=25, max_sl=2.0)   PF doc: 1.58
    V      H1   Config B (os=20, max_sl=4.0)   PF doc: 1.84
    ALB    H1   Config B (os=20, max_sl=4.0)   PF doc: 2.15
    WDC    H1   Config A (os=25, max_sl=2.0)   PF doc: 1.17 (bot says Cfg A)

BT period: 2017 -> 2025-12-31 (same as settings_altair to_date).

Usage:
    python tools/altair_hysteresis_compare.py
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
    ALTAIR_BROKER_CONFIG,
    _DEFAULT_PARAMS,
)
from lib.commission import ETFCommission, ETFCSVData  # noqa: E402


# (asset, csv_5m, csv_1h, resample_minutes, bars_per_day,
#  dtosc_os, max_sl_atr_mult, from_date, label)
TICKERS = [
    ("JPM",   "JPM_5m_8Yea.csv",   None, 30, 13, 20, 4.0,
     dt.datetime(2017, 2, 1), "30m Config B"),
    ("NVDA",  "NVDA_5m_8Yea.csv",  None, 15, 26, 25, 2.0,
     dt.datetime(2017, 1, 1), "15m Config A"),
    ("GOOGL", "GOOGL_5m_8Yea.csv", None, 15, 26, 25, 2.0,
     dt.datetime(2017, 1, 1), "15m Config A"),
    ("V",     None, "V_1h_8Yea.csv",     0,  7, 20, 4.0,
     dt.datetime(2017, 2, 1), "H1  Config B"),
    ("ALB",   None, "ALB_1h_8Yea.csv",   0,  7, 20, 4.0,
     dt.datetime(2017, 1, 1), "H1  Config B"),
    ("WDC",   None, "WDC_1h_8Yea.csv",   0,  7, 25, 2.0,
     dt.datetime(2017, 1, 1), "H1  Config A"),
]

BT_TO = dt.datetime(2025, 12, 31)
STARTING_CASH = 100_000.0


class HysteresisALTAIR(ALTAIRStrategy):
    """ALTAIR with hysteresis band on regime_atr_threshold.

    Adds params:
      regime_hyst_lower (float) -- enter CALM_UP only if atr_ratio < lower
      regime_hyst_upper (float) -- exit CALM_UP only if atr_ratio > upper
    Inside the band, previous regime is kept (sticky).

    When lower == upper, behavior reduces to the baseline binary filter.
    """

    params = (
        ('regime_hyst_lower', 1.0),
        ('regime_hyst_upper', 1.0),
    )

    def _update_regime(self):
        if not self.p.regime_enabled:
            self._regime_state = 'DISABLED'
            return

        try:
            close_val = float(self.data_h1.close[0])
            sma_val = float(self.regime_sma[0])
            atr_val = float(self.regime_atr[0])
            sma_atr_val = float(self.regime_sma_atr[0])
        except (IndexError, ValueError):
            self._regime_state = 'WARMING'
            return

        if (math.isnan(sma_val) or math.isnan(atr_val) or
                math.isnan(sma_atr_val) or sma_atr_val <= 0):
            self._regime_state = 'WARMING'
            return

        mom12m_ok = close_val > sma_val
        self._regime_mom12m = ((close_val / sma_val) - 1.0) * 100

        atr_ratio = atr_val / sma_atr_val
        self._regime_atr_ratio = atr_ratio

        # --- HYSTERESIS on calm_ok ---
        prev_state = getattr(self, '_regime_state', 'WARMING')
        prev_calm = prev_state in ('CALM_UP', 'CALM_DOWN')
        lower = self.p.regime_hyst_lower
        upper = self.p.regime_hyst_upper
        if atr_ratio < lower:
            calm_ok = True
        elif atr_ratio > upper:
            calm_ok = False
        else:
            # In hysteresis band -- keep previous
            calm_ok = prev_calm

        # Mom63d
        mom63d_ok = False
        self._regime_mom63d = 0.0
        lookback = self.p.momentum_63d_period * self.p.bars_per_day
        try:
            close_ago = float(self.data_h1.close[-lookback])
            if not math.isnan(close_ago) and close_ago > 0:
                self._regime_mom63d = ((close_val / close_ago) - 1.0) * 100
                mom63d_ok = close_val > close_ago
        except (IndexError, ValueError):
            pass

        if mom12m_ok and calm_ok and mom63d_ok:
            self._regime_state = 'CALM_UP'
        elif mom12m_ok and not calm_ok:
            self._regime_state = 'VOLATILE_UP'
        elif not mom12m_ok and calm_ok:
            self._regime_state = 'CALM_DOWN'
        else:
            self._regime_state = 'VOLATILE_DOWN'


def run_bt(asset, csv_5m, csv_1h, rs_min, bpd, dtosc_os, max_sl,
           from_date, hyst_lower, hyst_upper):
    cerebro = bt.Cerebro(stdstats=False)
    csv_name = csv_5m if csv_5m else csv_1h
    data = ETFCSVData(
        dataname=str(PROJECT_ROOT / "data" / csv_name),
        dtformat="%Y%m%d", tmformat="%H:%M:%S",
        datetime=0, time=1, open=2, high=3, low=4, close=5,
        volume=6, openinterest=-1,
        fromdate=from_date, todate=BT_TO,
    )
    if rs_min > 0:
        d = cerebro.resampledata(
            data, timeframe=bt.TimeFrame.Minutes, compression=rs_min)
        d._name = asset
    else:
        cerebro.adddata(data, name=asset)

    cerebro.broker.setcash(STARTING_CASH)
    bcfg = ALTAIR_BROKER_CONFIG.get("darwinex_zero_stock", {})
    ETFCommission.total_commission = 0.0
    ETFCommission.total_contracts = 0.0
    ETFCommission.commission_calls = 0
    cerebro.broker.addcommissioninfo(ETFCommission(
        commission=bcfg.get("commission_per_contract", 0.02),
        margin_pct=bcfg.get("margin_percent", 20.0),
    ))

    params = dict(_DEFAULT_PARAMS)
    params.update(dict(
        dtosc_os=dtosc_os,
        max_sl_atr_mult=max_sl,
        bars_per_day=bpd,
        export_reports=False,
        print_signals=False,
        plot_entry_exit_lines=False,
        regime_hyst_lower=hyst_lower,
        regime_hyst_upper=hyst_upper,
    ))
    cerebro.addstrategy(HysteresisALTAIR, **params)

    f = io.StringIO()
    with contextlib.redirect_stdout(f):
        try:
            res = cerebro.run()
        except Exception as e:
            return None, str(e)
    return res[0], None


def summarize(strat):
    total = strat.total_trades
    wins = strat.wins
    gp = strat.gross_profit
    gl = strat.gross_loss
    pf = (gp / gl) if gl > 0 else (float('inf') if gp > 0 else 0.0)
    wr = (wins / total * 100) if total else 0.0
    net = gp - gl
    return dict(total=total, wins=wins, pf=pf, wr=wr,
                gp=gp, gl=gl, net=net)


def main():
    print("=" * 100)
    print("ALTAIR REGIME HYSTERESIS COMPARISON")
    print("Period: per-ticker from_date -> 2025-12-31")
    print("BASELINE: regime_atr_threshold = 1.0 (binary)")
    print("HYSTERESIS: enter CALM if atr_ratio < 0.95, exit if > 1.05, sticky in band")
    print("=" * 100)

    rows = []
    for (asset, csv5, csv1, rs, bpd, os_, msl, fd, label) in TICKERS:
        print(f"\n### {asset} ({label}, from {fd.date()})")

        print("  running baseline ...")
        s_base, err = run_bt(asset, csv5, csv1, rs, bpd, os_, msl, fd,
                             hyst_lower=1.0, hyst_upper=1.0)
        if err:
            print(f"    ERROR: {err}")
            continue
        base = summarize(s_base)
        print(f"    baseline:    T={base['total']:>4d} "
              f"WR={base['wr']:>5.1f}% PF={base['pf']:>5.2f} "
              f"GP=${base['gp']:>8.0f} GL=${base['gl']:>8.0f} "
              f"NET=${base['net']:>+9.0f}")

        print("  running hysteresis [0.95, 1.05] ...")
        s_hyst, err = run_bt(asset, csv5, csv1, rs, bpd, os_, msl, fd,
                             hyst_lower=0.95, hyst_upper=1.05)
        if err:
            print(f"    ERROR: {err}")
            continue
        hyst = summarize(s_hyst)
        print(f"    hysteresis:  T={hyst['total']:>4d} "
              f"WR={hyst['wr']:>5.1f}% PF={hyst['pf']:>5.2f} "
              f"GP=${hyst['gp']:>8.0f} GL=${hyst['gl']:>8.0f} "
              f"NET=${hyst['net']:>+9.0f}")

        d_t = hyst['total'] - base['total']
        d_pf = hyst['pf'] - base['pf']
        d_net = hyst['net'] - base['net']
        print(f"    delta:       dT={d_t:+d} dPF={d_pf:+.2f} dNET=${d_net:+.0f}")

        rows.append((asset, label, base, hyst))

    # Final table
    print()
    print("=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print(f"{'Ticker':<7} {'TF/Cfg':<14} "
          f"{'T_base':>6} {'T_hyst':>6} {'dT':>5} "
          f"{'PF_base':>7} {'PF_hyst':>7} {'dPF':>6} "
          f"{'WR_base':>7} {'WR_hyst':>7} "
          f"{'NET_base':>10} {'NET_hyst':>10} {'dNET':>10}")
    for (asset, label, base, hyst) in rows:
        print(f"{asset:<7} {label:<14} "
              f"{base['total']:>6d} {hyst['total']:>6d} "
              f"{hyst['total']-base['total']:>+5d} "
              f"{base['pf']:>7.2f} {hyst['pf']:>7.2f} "
              f"{hyst['pf']-base['pf']:>+6.2f} "
              f"{base['wr']:>6.1f}% {hyst['wr']:>6.1f}% "
              f"${base['net']:>+9.0f} ${hyst['net']:>+9.0f} "
              f"${hyst['net']-base['net']:>+9.0f}")

    # Portfolio totals
    if rows:
        b_t = sum(r[2]['total'] for r in rows)
        h_t = sum(r[3]['total'] for r in rows)
        b_n = sum(r[2]['net'] for r in rows)
        h_n = sum(r[3]['net'] for r in rows)
        b_gp = sum(r[2]['gp'] for r in rows)
        b_gl = sum(r[2]['gl'] for r in rows)
        h_gp = sum(r[3]['gp'] for r in rows)
        h_gl = sum(r[3]['gl'] for r in rows)
        b_pf = b_gp / b_gl if b_gl > 0 else 0.0
        h_pf = h_gp / h_gl if h_gl > 0 else 0.0
        print("-" * 100)
        print(f"{'TOTAL':<7} {'(6 tickers)':<14} "
              f"{b_t:>6d} {h_t:>6d} "
              f"{h_t-b_t:>+5d} "
              f"{b_pf:>7.2f} {h_pf:>7.2f} "
              f"{h_pf-b_pf:>+6.2f} "
              f"{'':>7} {'':>7} "
              f"${b_n:>+9.0f} ${h_n:>+9.0f} "
              f"${h_n-b_n:>+9.0f}")


if __name__ == "__main__":
    main()
