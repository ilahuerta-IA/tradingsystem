"""ALTAIR regime path comparison: BT intraday-resampled vs live D1-native.

PURPOSE
-------
Tests THE root-cause hypothesis for ALTAIR BT-vs-live divergence: the D1
regime filter (CALM_UP = Mom12M & CALM & Mom63d) is computed from DIFFERENT
inputs in each environment, so the same calendar day can be tradeable live
but blocked in BT (or vice versa):

  - BT path  (altair_strategy.py): regime is derived from the single intraday
    feed with DAY-SCALED periods, i.e. SMA(252 * bars_per_day) over resampled
    30m/15m/H1 closes. Long-warmup indicators ride on intraday Dukascopy data.
  - Live path (altair_checker._update_regime_from_d1): regime is derived from
    MT5-NATIVE D1 bars with raw periods, i.e. SMA(252) over D1 closes.

If the two paths disagree on CALM_UP for a given day, the BT will not
reproduce a live entry (or will invent one), independent of any intraday
price/DTOSC match. This is distinct from price feed micro-differences.

WHAT IT DOES
------------
Loads the M5 Dukascopy CSV for TICKER and computes the regime BOTH ways from
the SAME data (so the comparison isolates the period-scaling / timeframe
choice, not the data source). Prints the per-bar regime around INSPECT_DATE
for the intraday path and the per-day regime for the D1 path, then reports
whether they AGREE on CALM_UP at the inspection moment.

This is a read-only diagnostic; it does not run Backtrader or place trades.

CONFIG (edit constants below)
-----------------------------
  TICKER, CSV_NAME : which asset to inspect
  BPD              : bars_per_day for the live TF (15m=26, 30m=13, H1=7)
  INSPECT_DATE     : day of the live entry under investigation (UTC)

Usage:
    python tools/altair_regime_path_compare.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# === CONFIG ===
TICKER = "JPM"
CSV_NAME = "JPM_5m_8Yea.csv"
BPD = 13                       # JPM 30m -> 13 bars/day
RESAMPLE = "30min"             # live TF for this ticker
INSPECT_DATE = "2026-05-27"    # day of the live entry the BT did not reproduce

# === ALTAIR regime params (mirror strategies/altair_strategy.py defaults) ===
SMA_P = 252
ATR_LT_P = 252
ATR_CUR_P = 14
MOM63 = 63
HYST_LO, HYST_HI = 0.95, 1.05

CSV = PROJECT_ROOT / "data" / CSV_NAME
OHLC = {"open": "first", "high": "max", "low": "min", "close": "last"}


def wilder_atr(df: pd.DataFrame, period: int) -> pd.Series:
    """Wilder RMA ATR, matching bt.ind.ATR / checker ewm(alpha=1/period)."""
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False).mean()


def compute_regime(df: pd.DataFrame, sma_p: int, atr_lt_p: int,
                   atr_cur_p: int, mom63_lb: int) -> pd.DataFrame:
    """Replicate ALTAIRStrategy._update_regime() vectorially.

    sma_p / atr_lt_p / atr_cur_p / mom63_lb are already in *bars* of the
    timeframe of df (caller scales by bars_per_day for the intraday path,
    or passes raw day-periods for the D1 path).
    """
    close = df["close"]
    sma = close.rolling(sma_p).mean()
    atr = wilder_atr(df, atr_cur_p)
    sma_atr = atr.rolling(atr_lt_p).mean()
    ratio = atr / sma_atr
    mom12 = close > sma
    mom63 = close > close.shift(mom63_lb)

    # Sticky hysteresis on the CALM flag (same as strategy _prev_calm_ok).
    calm_vals = []
    prev = False
    for r in ratio:
        if not np.isnan(r):
            if r < HYST_LO:
                prev = True
            elif r > HYST_HI:
                prev = False
        calm_vals.append(prev)
    calm = pd.Series(calm_vals, index=df.index)

    state = pd.Series("WARMING", index=df.index)
    state[mom12 & calm & mom63] = "CALM_UP"
    state[mom12 & ~calm] = "VOLATILE_UP"
    state[~mom12 & calm] = "CALM_DOWN"
    state[~mom12 & ~calm & ~(mom12 & calm & mom63)] = "VOLATILE_DOWN"
    return pd.DataFrame({
        "close": close, "sma": sma, "atr_ratio": ratio,
        "mom12": mom12, "mom63": mom63, "calm": calm, "state": state,
    })


def main() -> None:
    df = pd.read_csv(
        CSV, header=None, low_memory=False,
        names=["date", "time", "open", "high", "low", "close", "vol"])
    # Tolerate an optional header row (e.g. "Date Time ...") by coercing.
    df["dt"] = pd.to_datetime(
        df["date"].astype(str) + " " + df["time"].astype(str),
        format="%Y%m%d %H:%M:%S", errors="coerce")
    df = df.dropna(subset=["dt"]).set_index("dt").sort_index()
    for col in ("open", "high", "low", "close"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"])

    intraday = df.resample(RESAMPLE).agg(OHLC).dropna()
    bt_reg = compute_regime(
        intraday, SMA_P * BPD, ATR_LT_P * BPD, ATR_CUR_P * BPD, MOM63 * BPD)

    d1 = df.resample("1D").agg(OHLC).dropna()
    live_reg = compute_regime(d1, SMA_P, ATR_LT_P, ATR_CUR_P, MOM63)

    print("=" * 78)
    print(f"ALTAIR regime path comparison: {TICKER} around {INSPECT_DATE}")
    print("BT path = intraday-resampled (SMA 252*bpd) | "
          "Live path = D1-native (SMA 252)")
    print("=" * 78)

    print(f"\n--- BT path ({RESAMPLE}, day-scaled) | {INSPECT_DATE} session ---")
    btw = bt_reg.loc[f"{INSPECT_DATE} 13:00":f"{INSPECT_DATE} 20:00"]
    for ts, r in btw.iterrows():
        print(f"  {ts}  close={r.close:7.2f} sma={r.sma:7.2f} "
              f"atr_ratio={r.atr_ratio:5.2f} mom12={int(r.mom12)} "
              f"mom63={int(r.mom63)} calm={int(r.calm)} -> {r.state}")

    print("\n--- Live path (D1-native) | week of inspection ---")
    d_from = (pd.Timestamp(INSPECT_DATE) - pd.Timedelta(days=6)).date()
    d_to = (pd.Timestamp(INSPECT_DATE) + pd.Timedelta(days=1)).date()
    for ts, r in live_reg.loc[str(d_from):str(d_to)].iterrows():
        print(f"  {ts.date()}  close={r.close:7.2f} sma={r.sma:7.2f} "
              f"atr_ratio={r.atr_ratio:5.2f} mom12={int(r.mom12)} "
              f"mom63={int(r.mom63)} calm={int(r.calm)} -> {r.state}")

    bt_at = bt_reg.loc[f"{INSPECT_DATE} 13:00":f"{INSPECT_DATE} 19:30"]["state"]
    bt_state = bt_at.iloc[-1] if len(bt_at) else "N/A"
    live_at = live_reg.loc[:INSPECT_DATE]["state"]
    live_state = live_at.iloc[-1] if len(live_at) else "N/A"

    print("\n" + "=" * 78)
    print(f"BT regime at {INSPECT_DATE} 19:30 (intraday path): {bt_state}")
    print(f"Live regime at {INSPECT_DATE} (D1 path):          {live_state}")
    print(f"AGREE on CALM_UP: {bt_state == 'CALM_UP' == live_state}")
    if bt_state != live_state:
        print("=> Regime PATHS DISAGREE. This alone explains a BT-vs-live "
              "entry mismatch, independent of intraday price/DTOSC.")
    print("=" * 78)


if __name__ == "__main__":
    main()
