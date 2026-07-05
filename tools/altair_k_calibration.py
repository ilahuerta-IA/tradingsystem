"""Calibrate k = ATR(15m) / ATR(daily) for US stocks -- Phase 2 input.

Uses the dual-granularity 15m CSVs in data/ (*_15m_8Yea.csv, RTH bars).
For each ticker: ATR(14) on native 15m bars vs ATR(14) on bars resampled
to daily, both as median over the recent window. k lets the rotation
screener estimate intraday ATR from FREE daily data (no 15m download
needed for the edge/spread filter).

Usage:
    python tools/altair_k_calibration.py            # all *_15m_8Yea.csv
    python tools/altair_k_calibration.py --years 2  # recent window only

Output: per-ticker k table + cross-ticker median/std. The median gets
hardcoded in tools/altair_rotation_screener.py CONFIG (documented).
"""

import argparse
import glob
import os

import numpy as np
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "data")


def atr14(df):
    """ATR(14) series from an OHLC frame."""
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - df["Close"].shift(1)).abs(),
        (df["Low"] - df["Close"].shift(1)).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(14).mean()


def ticker_k(path, years):
    df = pd.read_csv(path)
    df["dt"] = pd.to_datetime(df["Date"].astype(str) + " " + df["Time"],
                              format="%Y%m%d %H:%M:%S")
    if years:
        cutoff = df["dt"].max() - pd.DateOffset(years=years)
        df = df[df["dt"] >= cutoff]
    if len(df) < 5000:
        return None

    atr_15m = float(atr14(df).median())

    daily = df.groupby("Date").agg(
        Open=("Open", "first"), High=("High", "max"),
        Low=("Low", "min"), Close=("Close", "last"))
    if len(daily) < 100:
        return None
    atr_d = float(atr14(daily).median())
    if atr_d <= 0:
        return None
    return atr_15m / atr_d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=2,
                    help="recent window in years (0 = full history)")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(DATA_DIR, "*_15m_8Yea.csv")))
    print("Calibrating k on %d tickers (window: %s)..."
          % (len(files), "%dy" % args.years if args.years else "full"))
    ks = {}
    for path in files:
        t = os.path.basename(path).split("_")[0]
        k = ticker_k(path, args.years)
        if k is not None:
            ks[t] = k

    vals = np.array(sorted(ks.values()))
    print("\n%-6s %s" % ("TICKER", "k"))
    for t in sorted(ks, key=ks.get):
        print("%-6s %.4f" % (t, ks[t]))
    print("\nn=%d  median=%.4f  mean=%.4f  std=%.4f  p10=%.4f  p90=%.4f"
          % (len(vals), np.median(vals), vals.mean(), vals.std(),
             np.percentile(vals, 10), np.percentile(vals, 90)))


if __name__ == "__main__":
    main()
