"""Broker-session CSV filter for backtest/live feed parity.

Dukascopy CSVs quote near-24h, but Darwinex Zero only streams prices
during its own session, so live indicators never see overnight bars
(session study 2026-10-02: 10.5% of GDAXI 5m bars untradeable, ATR
diff p95 16.7%, ~9.8% of entry signals flip).

This module filters a 5m CSV (Date,Time,OHLCV, UTC) down to the broker
session (broker time = UTC+2 winter / UTC+3 summer, EU DST) and caches
the filtered file so the backtest consumes the same bars live sees.
"""

import os
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd


def _last_sunday(year, month):
    d = datetime(year, month, 31)
    while d.weekday() != 6:
        d -= timedelta(days=1)
    return d


def _broker_minutes(ts_index):
    """Return (weekday, minute-of-day) arrays in broker time (EU DST)."""
    years = range(ts_index[0].year, ts_index[-1].year + 1)
    ts = ts_index.to_numpy()
    yrs = ts_index.year.to_numpy()
    is_dst = np.zeros(len(ts), dtype=bool)
    for y in years:
        start = _last_sunday(y, 3).replace(hour=1)
        end = _last_sunday(y, 10).replace(hour=1)
        sel = yrs == y
        is_dst[sel] = (ts[sel] >= np.datetime64(start)) & (ts[sel] < np.datetime64(end))
    offset_h = np.where(is_dst, 3, 2)
    broker = pd.DatetimeIndex(ts + offset_h.astype("timedelta64[h]"))
    return broker.weekday, broker.hour * 60 + broker.minute


def _parse_hhmm(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def filter_csv_to_broker_session(csv_path, spec, cache_dir="data/_session_cache"):
    """Filter a Date,Time 5m CSV to the broker session. Returns cached path.

    spec keys (broker time, 'HH:MM'):
      open      -- first tradeable bar start (inclusive)
      close     -- session end (exclusive; '24:00' = until midnight)
      fri_close -- optional earlier close on Fridays (exclusive)
      days      -- optional list of broker weekdays (default Mon-Fri)
    """
    csv_path = Path(csv_path)
    open_min = _parse_hhmm(spec["open"])
    close_min = _parse_hhmm(spec["close"])
    fri_close_min = _parse_hhmm(spec["fri_close"]) if spec.get("fri_close") else close_min
    days = spec.get("days", [0, 1, 2, 3, 4])

    tag = "o{}_c{}_f{}".format(open_min, close_min, fri_close_min)
    cache = Path(cache_dir) / "{}__{}.csv".format(csv_path.stem, tag)
    if cache.exists() and os.path.getmtime(cache) >= os.path.getmtime(csv_path):
        return cache

    df = pd.read_csv(csv_path, dtype={"Date": str, "Time": str})
    ts = pd.to_datetime(df["Date"] + df["Time"], format="%Y%m%d%H:%M:%S")
    weekday, minutes = _broker_minutes(pd.DatetimeIndex(ts))
    close_arr = np.where(weekday == 4, fri_close_min, close_min)
    mask = np.isin(weekday, days) & (minutes >= open_min) & (minutes < close_arr)

    cache.parent.mkdir(parents=True, exist_ok=True)
    df[mask].to_csv(cache, index=False)
    kept = int(mask.sum())
    print("Session filter {}: {}/{} bars kept ({:.1f}%) -> {}".format(
        csv_path.name, kept, len(df), 100.0 * kept / len(df), cache.name))
    return cache
