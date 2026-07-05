"""ALTAIR 15m data archive health check + incremental update -- Phase 3.

Scans data/*_15m_8Yea.csv (Tiingo-sourced, UTC timestamps, RTH bars) and
reports per ticker: last bar, staleness, recent gaps and bad days. With
--update, appends the missing delta from yfinance (15m, limited to the
last 60 days -- hence this must run MONTHLY; older holes need the Tiingo
downloaders).

Safety guards on update:
  - refuses when the hole exceeds the yfinance window (no silent gaps)
  - re-downloads the last stored day and compares closes; >0.5% mismatch
    (split/adjustment) -> ticker flagged, NOT updated

Status per ticker:
    OK       fresh (last bar within --fresh-days trading days)
    STALE    behind but recoverable via --update (hole < 55 days)
    TIINGO   hole too old for yfinance -> use tools/tiingo_5m_downloader.py
    BAD      structural problem (unreadable, empty, adjust mismatch)

Usage:
    python tools/altair_data_health.py                 # report only
    python tools/altair_data_health.py --update        # report + fill deltas
    python tools/altair_data_health.py --only HLT URI  # subset

Process doc: context/ALTAIR_ROTACION_RUNBOOK.md (Paso 3)
"""

import argparse
import datetime
import glob
import os
import sys

import numpy as np
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "data")

FRESH_DAYS = 5          # calendar days behind = still OK
YF_WINDOW_DAYS = 55     # beyond this, yfinance 15m cannot backfill
MIN_BARS_FULL_DAY = 20  # RTH 15m = 26 bars; below this = partial/bad day
OVERLAP_TOL = 0.005     # 0.5% close mismatch -> adjustment problem


def load_archive(path):
    df = pd.read_csv(path)
    df["dt"] = pd.to_datetime(df["Date"].astype(str) + " " + df["Time"],
                              format="%Y%m%d %H:%M:%S")
    return df


def health_row(ticker, df, union_dates):
    """Health metrics for one ticker archive."""
    last_dt = df["dt"].max()
    age = (pd.Timestamp.now(tz="UTC").tz_localize(None) - last_dt).days
    dates = set(df["Date"].astype(str).unique())
    recent_union = [d for d in union_dates if d > sorted(dates)[0]]
    missing = [d for d in recent_union[-30:] if d not in dates]
    bars_last = df[df["Date"] == df["Date"].iloc[-1]].shape[0]

    if age <= FRESH_DAYS:
        status = "OK"
    elif age <= YF_WINDOW_DAYS:
        status = "STALE"
    else:
        status = "TIINGO"
    return {
        "ticker": ticker, "status": status, "last_bar": str(last_dt),
        "age_days": age, "rows": len(df),
        "gaps_30d": len(missing), "gap_dates": " ".join(missing[:5]),
        "bars_last_day": bars_last,
    }


def yf_delta(ticker, last_dt):
    """Download 15m bars after last_dt from yfinance, in archive format."""
    import yfinance as yf

    raw = yf.download(ticker, interval="15m", period="60d",
                      auto_adjust=False, prepost=False, progress=False)
    if raw.empty:
        return None, "yfinance returned no data"
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    idx = raw.index
    if idx.tz is not None:
        idx = idx.tz_convert("UTC").tz_localize(None)
    out = pd.DataFrame({
        "Date": idx.strftime("%Y%m%d"),
        "Time": idx.strftime("%H:%M:%S"),
        "Open": raw["Open"].values, "High": raw["High"].values,
        "Low": raw["Low"].values, "Close": raw["Close"].values,
        "Volume": raw["Volume"].values.astype("int64"),
        "dt": idx,
    })
    return out, None


def update_ticker(path, df, row):
    """Append yfinance delta to the archive. Returns (bars_added, error)."""
    ticker = row["ticker"]
    last_dt = df["dt"].max()
    delta, err = yf_delta(ticker, last_dt)
    if err:
        return 0, err

    # overlap sanity: compare closes on the last stored day
    last_day = df["Date"].iloc[-1]
    ours = df[df["Date"] == last_day].set_index("Time")["Close"]
    theirs = delta[delta["Date"] == str(last_day)].set_index("Time")["Close"]
    common = ours.index.intersection(theirs.index)
    if len(common) >= 3:
        diff = (ours[common] / theirs[common] - 1.0).abs().max()
        if diff > OVERLAP_TOL:
            return 0, "adjust mismatch %.2f%% (split/dividend?) -> use Tiingo" \
                % (diff * 100.0)
    elif delta["dt"].min() > last_dt + pd.Timedelta(days=4):
        return 0, "no overlap with archive -> hole risk, use Tiingo"

    new = delta[delta["dt"] > last_dt].drop(columns="dt")
    if new.empty:
        return 0, None
    new.to_csv(path, mode="a", header=False, index=False,
               float_format="%.4f")
    return len(new), None


def main():
    ap = argparse.ArgumentParser(description="15m archive health + delta update")
    ap.add_argument("--update", action="store_true", help="fill deltas via yfinance")
    ap.add_argument("--only", nargs="+", help="restrict to these tickers")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(DATA_DIR, "*_15m_8Yea.csv")))
    if args.only:
        want = set(t.upper() for t in args.only)
        files = [f for f in files if os.path.basename(f).split("_")[0] in want]
    if not files:
        print("No 15m archives found.")
        return 1

    print("Scanning %d archives..." % len(files))
    archives, rows = {}, []
    all_dates = set()
    for path in files:
        t = os.path.basename(path).split("_")[0]
        try:
            df = load_archive(path)
            archives[t] = (path, df)
            all_dates.update(df["Date"].astype(str).unique())
        except Exception as exc:
            rows.append({"ticker": t, "status": "BAD", "last_bar": "",
                         "age_days": -1, "rows": 0, "gaps_30d": -1,
                         "gap_dates": str(exc)[:60], "bars_last_day": 0})
    union_dates = sorted(all_dates)

    for t, (path, df) in sorted(archives.items()):
        rows.append(health_row(t, df, union_dates))

    rep = pd.DataFrame(rows).sort_values(["status", "ticker"])
    with pd.option_context("display.max_rows", None, "display.width", 200):
        print(rep.to_string(index=False))
    print("\nCounts: %s" % rep["status"].value_counts().to_dict())

    if args.update:
        todo = rep[rep["status"].isin(("OK", "STALE"))]["ticker"].tolist()
        print("\nUpdating %d tickers via yfinance..." % len(todo))
        for t in todo:
            path, df = archives[t]
            added, err = update_ticker(path, df, {"ticker": t})
            if err:
                print("  %-6s SKIPPED: %s" % (t, err))
            else:
                print("  %-6s +%d bars" % (t, added))
        skipped = rep[rep["status"] == "TIINGO"]["ticker"].tolist()
        if skipped:
            print("Need Tiingo backfill (hole > %dd): %s"
                  % (YF_WINDOW_DAYS, " ".join(skipped)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
