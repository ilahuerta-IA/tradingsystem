"""
tiingo_h1_downloader.py  —  Download H1 OHLCV data from Tiingo IEX
=====================================================================
Retrieves hourly candles for US stocks via the Tiingo IEX endpoint and
saves them in the same CSV format used by Dukascopy so they are directly
compatible with the ALTAIR back-test pipeline.

Strategy:  Download 30-min bars and aggregate to 1-hour internally.
This lets us build the 19:00–20:00 UTC closing bar that Tiingo's native
1-hour resampling misses (IEX last bar is 19:30).

Pagination:  The IEX endpoint caps at ~10 000 rows per request.  At 30-min
that is ≈ 385 trading days.  We paginate in 1-year chunks to ensure full
coverage back to 2017.

8-Year minimum:  Tickers whose first available bar is after 2018-04-12
(< 8 years of history) are flagged, NOT saved, and listed at the end so
you can decide if a shorter sample is acceptable.

Output format (matching existing data/):
    Date,Time,Open,High,Low,Close,Volume
    20170801,14:00:00,120.50,121.10,120.30,120.90,1523000

Usage
-----
    $env:TIINGO_API_KEY = "YOUR_TOKEN_HERE"

    # Download 5 test tickers
    python tools/tiingo_h1_downloader.py VRT HOOD HWM TKO CVNA

    # Download all 72 pending Tier1-HIGH tickers from a file
    python tools/tiingo_h1_downloader.py --file tools/pending_tickers.txt

    # Accept tickers with < 8 years as well (saves with warning)
    python tools/tiingo_h1_downloader.py --min-years 0

Rate Limits (free tier)
-----------------------
    50 requests/hour  ·  1 000 requests/day  ·  500 unique symbols/month
"""

import argparse
import csv
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, date, timedelta, timezone
from pathlib import Path

try:
    import requests as _req
except ImportError:
    sys.exit("ERROR: 'requests' not installed.  Run:  pip install requests")

# ── Constants ──────────────────────────────────────────────────────────
TIINGO_IEX_URL = "https://api.tiingo.com/iex/{ticker}/prices"
DEFAULT_START  = "2017-01-02"
FETCH_FREQ     = "30min"               # fetch sub-hourly …
TARGET_FREQ    = "1hour"               # … then aggregate locally
DATA_DIR       = Path(__file__).resolve().parent.parent / "data"
CSV_HEADER     = ["Date", "Time", "Open", "High", "Low", "Close", "Volume"]

# Regular-hours 1-hour bars in UTC we want to produce.
# 14:00 = aggregation of [13:30, 14:00) 30-min bars  … but IEX starts at 13:30
# We build the *start-of-bar* → hour mapping for aggregation:
#   13:30 + 14:00  → bar labelled 14:00   (first bar of day)
#   14:30 + 15:00  → bar labelled 15:00
#   …
#   19:30 + (no 20:00) → bar labelled 20:00  (closing half-hour only)
# The Dukascopy bars label each hour as: 14,15,16,17,18,19,20
HOUR_BAR_LABELS = list(range(14, 21))   # 14..20 inclusive → 7 bars/day
FREE_TIER_DELAY = 75                    # seconds between API requests
CHUNK_DAYS      = 365                   # 1-year chunks for pagination
MIN_YEARS_DEFAULT = 8


# ── Helpers ────────────────────────────────────────────────────────────

def get_api_key() -> str:
    # 1. Try environment variable first
    key = os.environ.get("TIINGO_API_KEY", "").strip()
    if key:
        return key
    # 2. Try credentials JSON file
    cred_path = os.path.join(os.path.dirname(__file__), "..", "config", "credentials", "tiingo.json")
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


def _api_get(url: str, headers: dict, params: dict,
             max_retries: int = 5) -> list[dict]:
    """API GET with exponential back-off on 429 (rate-limit)."""
    wait = 120  # initial wait on 429 (seconds)
    for attempt in range(1, max_retries + 1):
        resp = _req.get(url, headers=headers, params=params, timeout=120)
        if resp.status_code == 200:
            data = resp.json()
            return data if isinstance(data, list) else []
        if resp.status_code == 429:
            print(f"    ⚠  Rate-limited — waiting {wait} s … "
                  f"(attempt {attempt}/{max_retries})")
            time.sleep(wait)
            wait = min(wait + 120, 600)   # 120 → 240 → 360 → 480 → 600
            continue
        # Any other error → stop retrying
        print(f"    ✗  HTTP {resp.status_code}: {resp.text[:200]}")
        return []
    print(f"    ✗  Rate-limit not cleared after {max_retries} retries")
    return []


def fetch_30min_paginated(ticker: str, api_key: str, start: str,
                          fast: bool) -> list[dict]:
    """Fetch all 30-min bars for *ticker* using date-range pagination."""
    headers = {"Content-Type": "application/json",
               "Authorization": f"Token {api_key}"}
    url = TIINGO_IEX_URL.format(ticker=ticker.upper())

    start_dt = datetime.strptime(start, "%Y-%m-%d").date()
    end_dt   = date.today()
    all_bars: list[dict] = []
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
            print(f"    chunk {chunk_n}: {start_dt} → {chunk_end}  "
                  f"({len(bars):,} bars)")
        else:
            print(f"    chunk {chunk_n}: {start_dt} → {chunk_end}  "
                  f"(0 bars)")

        start_dt = chunk_end + timedelta(days=1)

        # Rate-limit between chunks (skip on --fast)
        if not fast and start_dt < end_dt:
            time.sleep(FREE_TIER_DELAY)

    return all_bars


# ── 30min → 1h aggregation ────────────────────────────────────────────

def _bar_hour_label(dt: datetime) -> int | None:
    """Map a 30-min bar timestamp to its 1-hour bar label (14-20 UTC).

    Tiingo 30-min timestamps are at :00 and :30 of each hour.
    We group into 1h bars whose label matches Dukascopy convention:
        13:30, 14:00  → label 14     (open = 13:30 open)
        14:30, 15:00  → label 15
        …
        19:30         → label 20     (only half-bar available from IEX)
    """
    h, m = dt.hour, dt.minute
    if h == 13 and m == 30:
        return 14
    if 14 <= h <= 19:
        if m == 0:
            return h        # second sub-bar of the group
        if m == 30:
            return h + 1    # first sub-bar of the next group
    return None             # pre/post market → discard


def aggregate_to_h1(raw_30: list[dict]) -> list[list]:
    """Aggregate 30-min Tiingo bars into Dukascopy-format 1h rows."""
    # Group by (date_str, hour_label)
    groups: dict[tuple[str, int], list[dict]] = defaultdict(list)

    for r in raw_30:
        dt = datetime.fromisoformat(r["date"])
        label = _bar_hour_label(dt)
        if label is None:
            continue
        date_str = dt.strftime("%Y%m%d")
        groups[(date_str, label)].append(r)

    # Build sorted H1 rows
    rows = []
    for (date_str, label) in sorted(groups):
        subs = groups[(date_str, label)]
        opens  = [s.get("open")  or 0 for s in subs]
        highs  = [s.get("high")  or 0 for s in subs]
        lows   = [s.get("low")   or 0 for s in subs]
        closes = [s.get("close") or 0 for s in subs]
        vols   = [int(s.get("volume") or 0) for s in subs]

        o  = round(opens[0], 6)                      # first sub-bar open
        h  = round(max(highs), 6)
        lo = round(min(lows), 6)
        c  = round(closes[-1], 6)                     # last sub-bar close
        v  = sum(vols)

        if c == 0:
            continue

        time_str = f"{label:02d}:00:00"
        rows.append([date_str, time_str, o, h, lo, c, v])

    return rows


# ── File I/O ───────────────────────────────────────────────────────────

def save_csv(ticker: str, rows: list[list], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{ticker.upper()}_1h_8Yea.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADER)
        writer.writerows(rows)
    return path


# ── Per-ticker orchestration ──────────────────────────────────────────

def download_one(ticker: str, api_key: str, start: str, out_dir: Path,
                 min_years: float, fast: bool) -> tuple[str, str]:
    """Download, aggregate, validate and save one ticker.

    Returns (status, detail):
        ("ok",       "12,345 bars | 2,001 days | 20170801 → 20260410")
        ("short",    "Only 4.2 years (since 20220115) — not saved")
        ("no_data",  "No data returned")
    """
    print(f"\n{'='*55}")
    print(f"  {ticker.upper()}")
    print(f"{'='*55}")

    raw = fetch_30min_paginated(ticker, api_key, start, fast)
    if not raw:
        return ("no_data", "No data returned by Tiingo")

    rows = aggregate_to_h1(raw)
    if not rows:
        return ("no_data", "0 regular-hours bars after aggregation")

    first_date = datetime.strptime(rows[0][0], "%Y%m%d").date()
    last_date  = datetime.strptime(rows[-1][0], "%Y%m%d").date()
    span_years = (last_date - first_date).days / 365.25
    days       = len({r[0] for r in rows})

    detail = (f"{len(rows):,} bars | {days:,} days | "
              f"{rows[0][0]} → {rows[-1][0]} | {span_years:.1f} yr")

    if span_years < min_years:
        print(f"  ⚠  Only {span_years:.1f} years (min {min_years}) — NOT saved")
        return ("short", f"{span_years:.1f} yr (since {rows[0][0]}) — below {min_years}-yr minimum")

    path = save_csv(ticker, rows, out_dir)
    print(f"  ✓  {detail}")
    print(f"     Saved: {path.name}")
    return ("ok", detail)


# ── Main ───────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Download H1 OHLCV from Tiingo IEX (30min→1h aggregation)")
    ap.add_argument("tickers", nargs="*", help="Ticker symbols")
    ap.add_argument("--file", "-f", help="File with one ticker per line")
    ap.add_argument("--start", default=DEFAULT_START,
                    help="Start date YYYY-MM-DD (default: 2017-01-02)")
    ap.add_argument("--fast", action="store_true",
                    help="Skip inter-chunk delay (paid tier / testing)")
    ap.add_argument("--min-years", type=float, default=MIN_YEARS_DEFAULT,
                    help=f"Minimum years of data required (default: {MIN_YEARS_DEFAULT})")
    ap.add_argument("--outdir", default=str(DATA_DIR), help="Output directory")
    ap.add_argument("--no-resume", action="store_true",
                    help="Re-download even if CSV already exists in output dir")
    args = ap.parse_args()

    # Collect tickers
    tickers = list(args.tickers)
    if args.file:
        p = Path(args.file)
        if not p.exists():
            sys.exit(f"File not found: {args.file}")
        tickers.extend(
            line.strip().upper()
            for line in p.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
    if not tickers:
        ap.print_help()
        sys.exit(1)

    # De-duplicate preserving order
    seen = set()
    unique = []
    for t in tickers:
        t = t.upper().strip()
        if t and t not in seen:
            seen.add(t)
            unique.append(t)
    tickers = unique

    api_key = get_api_key()
    out_dir = Path(args.outdir)

    print(f"\nTiingo H1 Downloader  (30min→1h aggregation)")
    print(f"{'─'*55}")
    print(f"  Tickers   : {len(tickers)}")
    print(f"  Start     : {args.start}")
    print(f"  Min years : {args.min_years}")
    print(f"  Output    : {out_dir}")
    print(f"  Fast mode : {args.fast}")
    print(f"  List      : {', '.join(tickers[:10])}" +
          (f" … +{len(tickers)-10} more" if len(tickers) > 10 else ""))

    results: dict[str, list[tuple[str, str]]] = {
        "ok": [], "short": [], "no_data": [], "skipped": []
    }
    t0 = time.time()

    for i, ticker in enumerate(tickers):
        # Resume support: skip if CSV already exists
        csv_path = out_dir / f"{ticker.upper()}_1h_8Yea.csv"
        if csv_path.exists() and not args.no_resume:
            print(f"\n  ⏭  {ticker} — already exists, skipping "
                  f"(use --no-resume to re-download)")
            results["skipped"].append((ticker, str(csv_path.name)))
            continue

        status, detail = download_one(
            ticker, api_key, args.start, out_dir, args.min_years, args.fast)
        results[status].append((ticker, detail))

    elapsed = time.time() - t0

    # ── Summary ────────────────────────────────────────────────────────
    print(f"\n{'═'*55}")
    print(f"  SUMMARY  ({elapsed:.0f}s elapsed)")
    print(f"{'═'*55}")

    if results["ok"]:
        print(f"\n  ✓ SAVED ({len(results['ok'])}):")
        for tk, d in results["ok"]:
            print(f"    {tk:6s}  {d}")

    if results["skipped"]:
        print(f"\n  ⏭ SKIPPED — already on disk ({len(results['skipped'])}):")
        for tk, d in results["skipped"]:
            print(f"    {tk:6s}  {d}")

    if results["short"]:
        print(f"\n  ⚠ TOO SHORT — not saved ({len(results['short'])}):")
        for tk, d in results["short"]:
            print(f"    {tk:6s}  {d}")

    if results["no_data"]:
        print(f"\n  ✗ NO DATA ({len(results['no_data'])}):")
        for tk, d in results["no_data"]:
            print(f"    {tk:6s}  {d}")

    print(f"\n  Total: ✓ {len(results['ok'])}  "
          f"⏭ {len(results['skipped'])}  "
          f"⚠ {len(results['short'])}  "
          f"✗ {len(results['no_data'])}")
    print(f"{'═'*55}")


if __name__ == "__main__":
    main()
