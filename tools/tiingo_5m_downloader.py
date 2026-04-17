"""
tiingo_5m_downloader.py  --  Download intraday OHLCV data from Tiingo IEX
=========================================================================
Downloads 5m, 15m or 30m bars from Tiingo IEX.  Saves in the CSV format
used by the ALTAIR pipeline (Date,Time,Open,High,Low,Close,Volume).

Only US regular-hours bars are kept: 14:30-20:55 UTC.

Pagination: IEX endpoint caps ~10 000 rows per request.  Chunk size auto-
adjusts to the chosen timeframe:
  5m  -> ~78 bars/day -> 120-day chunks  (~29 chunks for 9yr)
  15m -> ~26 bars/day -> 360-day chunks  (~10 chunks for 9yr)
  30m -> ~13 bars/day -> 720-day chunks  (~5  chunks for 9yr)

Usage
-----
    python tools/tiingo_5m_downloader.py ALB WDC              # default 5m
    python tools/tiingo_5m_downloader.py ALB WDC --tf 15min   # 15m bars
    python tools/tiingo_5m_downloader.py ALB WDC --tf 30min   # 30m bars
    python tools/tiingo_5m_downloader.py ALB WDC --fast       # skip rate-limit waits
    python tools/tiingo_5m_downloader.py ALB --min-years 0
"""
import argparse
import csv
import os
import sys
import time
from datetime import datetime, date, timedelta
from pathlib import Path

try:
    import requests as _req
except ImportError:
    sys.exit("ERROR: 'requests' not installed.  Run:  pip install requests")

# ── Constants ──────────────────────────────────────────────────────────
TIINGO_IEX_URL = "https://api.tiingo.com/iex/{ticker}/prices"
DEFAULT_START  = "2017-01-02"
DATA_DIR       = Path(__file__).resolve().parent.parent / "data"
CSV_HEADER     = ["Date", "Time", "Open", "High", "Low", "Close", "Volume"]

# US regular hours in UTC: 14:30 to 20:55
MARKET_OPEN_H  = 14
MARKET_OPEN_M  = 30
MARKET_CLOSE_H = 20
MARKET_CLOSE_M = 55

FREE_TIER_DELAY = 75   # seconds between API requests
MIN_YEARS_DEFAULT = 8

# Timeframe presets  {tf_arg: (tiingo_freq, chunk_days, csv_tag, bars_per_day)}
# chunk_days sized so bars_per_day * chunk_days < 10 000 (Tiingo row cap)
TF_PRESETS = {
    "5min":  ("5min",  120, "5m",  78),
    "15min": ("15min", 360, "15m", 26),
    "30min": ("30min", 720, "30m", 13),
}
DEFAULT_TF = "5min"


# ── Helpers (shared logic from tiingo_h1_downloader) ───────────────────

def get_api_key():
    key = os.environ.get("TIINGO_API_KEY", "").strip()
    if key:
        return key
    cred_path = os.path.join(os.path.dirname(__file__), "..",
                             "config", "credentials", "tiingo.json")
    cred_path = os.path.normpath(cred_path)
    if os.path.exists(cred_path):
        import json
        with open(cred_path, "r") as f:
            data = json.load(f)
        key = data.get("api_key", "").strip()
        if key:
            return key
    sys.exit(
        "ERROR: TIINGO_API_KEY not found.\n"
        "   Option 1: config/credentials/tiingo.json  {\"api_key\": \"...\"}\n"
        "   Option 2: $env:TIINGO_API_KEY = 'your_token'"
    )


def _api_get(url, headers, params, max_retries=5):
    wait = 120
    for attempt in range(1, max_retries + 1):
        resp = _req.get(url, headers=headers, params=params, timeout=120)
        if resp.status_code == 200:
            data = resp.json()
            return data if isinstance(data, list) else []
        if resp.status_code == 429:
            print("    Rate-limited -- waiting %d s ... (attempt %d/%d)" %
                  (wait, attempt, max_retries))
            time.sleep(wait)
            wait = min(wait + 120, 600)
            continue
        print("    HTTP %d: %s" % (resp.status_code, resp.text[:200]))
        return []
    print("    Rate-limit not cleared after %d retries" % max_retries)
    return []


def fetch_paginated(ticker, api_key, start, fast, freq, chunk_days):
    headers = {"Content-Type": "application/json",
               "Authorization": "Token %s" % api_key}
    url = TIINGO_IEX_URL.format(ticker=ticker.upper())

    start_dt = datetime.strptime(start, "%Y-%m-%d").date()
    end_dt   = date.today()
    all_bars = []
    chunk_n  = 0

    while start_dt < end_dt:
        chunk_end = min(start_dt + timedelta(days=chunk_days), end_dt)
        params = {
            "startDate": start_dt.isoformat(),
            "endDate": chunk_end.isoformat(),
            "resampleFreq": freq,
            "columns": "open,high,low,close,volume",
        }
        chunk_n += 1
        bars = _api_get(url, headers, params)
        if bars:
            all_bars.extend(bars)
            print("    chunk %d: %s -> %s  (%d bars)" %
                  (chunk_n, start_dt, chunk_end, len(bars)))
        else:
            print("    chunk %d: %s -> %s  (0 bars)" %
                  (chunk_n, start_dt, chunk_end))

        start_dt = chunk_end + timedelta(days=1)

        if not fast and start_dt < end_dt:
            time.sleep(FREE_TIER_DELAY)

    return all_bars


def _in_market_hours(dt):
    """Return True if dt falls within US regular hours (14:30-20:55 UTC)."""
    t = dt.hour * 60 + dt.minute
    open_t = MARKET_OPEN_H * 60 + MARKET_OPEN_M
    close_t = MARKET_CLOSE_H * 60 + MARKET_CLOSE_M
    return open_t <= t <= close_t


def filter_and_format(raw_bars):
    """Filter to regular hours and format as CSV rows."""
    rows = []
    for r in raw_bars:
        dt = datetime.fromisoformat(r["date"])
        if not _in_market_hours(dt):
            continue
        o = r.get("open") or 0
        h = r.get("high") or 0
        lo = r.get("low") or 0
        c = r.get("close") or 0
        v = int(r.get("volume") or 0)
        if c == 0:
            continue
        date_str = dt.strftime("%Y%m%d")
        time_str = dt.strftime("%H:%M:%S")
        rows.append([date_str, time_str,
                     round(o, 6), round(h, 6), round(lo, 6), round(c, 6), v])
    return rows


def save_csv(ticker, rows, out_dir, csv_tag):
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / ("%s_%s_8Yea.csv" % (ticker.upper(), csv_tag))
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADER)
        writer.writerows(rows)
    return path


def download_one(ticker, api_key, start, out_dir, min_years, fast,
                 freq="5min", chunk_days=120, csv_tag="5m"):
    print()
    print("=" * 55)
    print("  %s  (%s)" % (ticker.upper(), csv_tag))
    print("=" * 55)

    raw = fetch_paginated(ticker, api_key, start, fast, freq, chunk_days)
    if not raw:
        return ("no_data", "No data returned by Tiingo")

    rows = filter_and_format(raw)
    if not rows:
        return ("no_data", "0 regular-hours bars after filtering")

    first_date = datetime.strptime(rows[0][0], "%Y%m%d").date()
    last_date  = datetime.strptime(rows[-1][0], "%Y%m%d").date()
    span_years = (last_date - first_date).days / 365.25

    n_days = len(set(r[0] for r in rows))
    bars_per_day = len(rows) / n_days if n_days > 0 else 0

    detail = ("%d bars | %d days | avg %.0f bars/day | %s -> %s (%.1f yr)" %
              (len(rows), n_days, bars_per_day,
               rows[0][0], rows[-1][0], span_years))
    print("    %s" % detail)

    if span_years < min_years:
        print("    ** SHORT: Only %.1f years (need %d). NOT SAVED." %
              (span_years, min_years))
        return ("short", detail)

    path = save_csv(ticker, rows, out_dir, csv_tag)
    print("    Saved: %s" % path)
    return ("ok", detail)


# ── Main ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Download intraday OHLCV from Tiingo IEX")
    parser.add_argument("tickers", nargs="+", help="Ticker symbols")
    parser.add_argument("--tf", choices=list(TF_PRESETS.keys()),
                        default=DEFAULT_TF,
                        help="Timeframe (default: %s)" % DEFAULT_TF)
    parser.add_argument("--start", default=DEFAULT_START,
                        help="Start date YYYY-MM-DD (default: %s)" %
                        DEFAULT_START)
    parser.add_argument("--min-years", type=float,
                        default=MIN_YEARS_DEFAULT,
                        help="Minimum years of data (default: %d)" %
                        MIN_YEARS_DEFAULT)
    parser.add_argument("--fast", action="store_true",
                        help="Skip rate-limit delays (paid tier)")
    args = parser.parse_args()

    freq, chunk_days, csv_tag, _ = TF_PRESETS[args.tf]
    api_key = get_api_key()
    tickers = [t.upper() for t in args.tickers]

    print()
    print("Tiingo %s Downloader" % csv_tag)
    print("  Tickers: %s" % ", ".join(tickers))
    print("  TF:      %s  (chunks=%d days)" % (args.tf, chunk_days))
    print("  Start:   %s" % args.start)
    print("  Min yrs: %.0f" % args.min_years)
    print("  Output:  %s" % DATA_DIR)

    results = {}
    for i, ticker in enumerate(tickers):
        status, detail = download_one(
            ticker, api_key, args.start, DATA_DIR,
            args.min_years, args.fast,
            freq=freq, chunk_days=chunk_days, csv_tag=csv_tag)
        results[ticker] = (status, detail)

        # Rate limit between tickers
        if not args.fast and i < len(tickers) - 1:
            print("\n    Waiting %d s (rate limit) ..." % FREE_TIER_DELAY)
            time.sleep(FREE_TIER_DELAY)

    # Summary
    print()
    print("=" * 55)
    print("SUMMARY")
    print("=" * 55)
    for ticker, (status, detail) in results.items():
        print("  [%s] %-6s %s" % (
            "OK" if status == "ok" else "!!", ticker, detail))
    print()


if __name__ == "__main__":
    main()
