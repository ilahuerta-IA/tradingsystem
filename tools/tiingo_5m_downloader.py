"""
tiingo_5m_downloader.py  --  Download 5m OHLCV data from Tiingo IEX
=====================================================================
Adapts tiingo_h1_downloader.py for 5-minute bars.  No aggregation needed
(Tiingo delivers native 5m candles).  Saves in the same CSV format used
by the ALTAIR pipeline (Date,Time,Open,High,Low,Close,Volume).

Only US regular-hours bars are kept: 14:30-20:55 UTC (78 bars/day).

Pagination: IEX endpoint caps ~10 000 rows per request.  At 5-min that is
~128 trading days.  We paginate in 120-day chunks.

Usage
-----
    python tools/tiingo_5m_downloader.py ALB WDC
    python tools/tiingo_5m_downloader.py ALB WDC --fast   # skip rate-limit waits
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
FETCH_FREQ     = "5min"
DATA_DIR       = Path(__file__).resolve().parent.parent / "data"
CSV_HEADER     = ["Date", "Time", "Open", "High", "Low", "Close", "Volume"]

# US regular hours in UTC: 14:30 to 20:55  (78 5-min bars/day)
# IEX 5m bars: timestamps at 14:30, 14:35, ... 20:50, 20:55
MARKET_OPEN_H  = 14
MARKET_OPEN_M  = 30
MARKET_CLOSE_H = 20
MARKET_CLOSE_M = 55

FREE_TIER_DELAY = 75   # seconds between API requests
CHUNK_DAYS      = 120  # ~128 trading days of 5m data per chunk
MIN_YEARS_DEFAULT = 8


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


def fetch_5m_paginated(ticker, api_key, start, fast):
    headers = {"Content-Type": "application/json",
               "Authorization": "Token %s" % api_key}
    url = TIINGO_IEX_URL.format(ticker=ticker.upper())

    start_dt = datetime.strptime(start, "%Y-%m-%d").date()
    end_dt   = date.today()
    all_bars = []
    chunk_n  = 0

    while start_dt < end_dt:
        chunk_end = min(start_dt + timedelta(days=CHUNK_DAYS), end_dt)
        params = {
            "startDate": start_dt.isoformat(),
            "endDate": chunk_end.isoformat(),
            "resampleFreq": FETCH_FREQ,
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


def save_csv(ticker, rows, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / ("%s_5m_8Yea.csv" % ticker.upper())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADER)
        writer.writerows(rows)
    return path


def download_one(ticker, api_key, start, out_dir, min_years, fast):
    print()
    print("=" * 55)
    print("  %s  (5m)" % ticker.upper())
    print("=" * 55)

    raw = fetch_5m_paginated(ticker, api_key, start, fast)
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

    path = save_csv(ticker, rows, out_dir)
    print("    Saved: %s" % path)
    return ("ok", detail)


# ── Main ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Download 5m OHLCV from Tiingo IEX")
    parser.add_argument("tickers", nargs="+", help="Ticker symbols")
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

    api_key = get_api_key()
    tickers = [t.upper() for t in args.tickers]

    print()
    print("Tiingo 5m Downloader")
    print("  Tickers: %s" % ", ".join(tickers))
    print("  Start:   %s" % args.start)
    print("  Min yrs: %.0f" % args.min_years)
    print("  Output:  %s" % DATA_DIR)

    results = {}
    for i, ticker in enumerate(tickers):
        status, detail = download_one(
            ticker, api_key, args.start, DATA_DIR,
            args.min_years, args.fast)
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
