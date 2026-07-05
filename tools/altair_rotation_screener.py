"""ALTAIR Rotation Screener -- Phase 1 (monthly portfolio funnel).

Screens the SP500 universe (or any ticker list) on FREE daily Yahoo data
and classifies each ticker with a semaphore for the ALTAIR monthly
rotation process (also feeds ORION ticker selection).

Filters (thresholds in CONFIG below):
  HARD (fail any -> RED):
    - 12-1 momentum > 0        (return from t-12m to t-1m, academic convention)
    - close > SMA200
    - dollar volume            (20d avg close*volume, liquidity proxy)
  SETUP (state, not pass/fail):
    - pullback zone: distance to 52w high inside [-12%, -3%]
    - calm: 20d realized vol below its own 6m median

Semaphore:
    GREEN  = hard filters pass AND in calm/pullback setup zone (candidate NOW)
    YELLOW = hard filters pass, not in setup zone (watchlist, wait)
    RED    = fails a hard filter (do not enter; 2 consecutive months
             RED while held -> exit, hysteresis rule in runbook)
    GRAY   = data problem (missing download, insufficient bars, NaNs)

Outputs (never overwritten across months):
    results/screener/screener_YYYY-MM.csv
    results/screener/screener_YYYY-MM.html   (colored table, open in browser)

Usage:
    python tools/altair_rotation_screener.py                       # full SP500
    python tools/altair_rotation_screener.py --only NVDA JPM KO    # subset
    python tools/altair_rotation_screener.py --refresh-universe    # re-fetch SP500 list
    python tools/altair_rotation_screener.py --held JPM NVDA GOOGL GS  # mark holdings

Process doc: context/ALTAIR_ROTACION_RUNBOOK.md
"""

import argparse
import datetime
import os
import sys

import numpy as np
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)

CONFIG = {
    # data
    "period": "2y",              # daily history downloaded per ticker
    "min_bars": 280,             # need 252+21 for 12-1 momentum; below -> GRAY
    # hard filters
    "mom_12_1_min": 0.0,         # 12-1 momentum must exceed this (fraction)
    "sma_period": 200,
    "dollar_vol_min_musd": 5.0,  # 20d avg dollar volume, millions USD
    # setup zone
    "pullback_min_pct": -12.0,   # distance to 52w high lower bound
    "pullback_max_pct": -3.0,    # distance to 52w high upper bound
    "calm_vol_window": 20,       # sessions for realized vol
    "calm_median_window": 126,   # ~6 months for the vol median
    # info columns
    "atr_period": 14,            # daily ATR pct (edge/spread input, Phase 2)
}

UNIVERSE_CACHE = os.path.join(SCRIPT_DIR, "sp500_tickers.txt")
OUT_DIR = os.path.join(REPO_ROOT, "results", "screener")

STATUS_ORDER = {"GREEN": 0, "YELLOW": 1, "RED": 2, "GRAY": 3}
STATUS_COLOR = {
    "GREEN": "#c6efce",
    "YELLOW": "#ffeb9c",
    "RED": "#ffc7ce",
    "GRAY": "#d9d9d9",
}


def fetch_sp500_tickers():
    """Fetch SP500 ticker list from Wikipedia (same approach as _fetch_sp500.py)."""
    import requests
    from lxml import html as lxml_html

    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    r.raise_for_status()
    tree = lxml_html.fromstring(r.content)
    tables = tree.xpath("//table[contains(@class, 'wikitable')]")
    if not tables:
        raise RuntimeError("No wikitable found on SP500 Wikipedia page")
    tickers = []
    for row in tables[0].xpath(".//tr")[1:]:
        cells = row.xpath(".//td")
        if cells:
            tickers.append(cells[0].text_content().strip().replace(".", "-"))
    tickers = sorted(set(t for t in tickers if t))
    if len(tickers) < 400:
        raise RuntimeError("Suspicious SP500 list size: %d" % len(tickers))
    return tickers


def load_universe(refresh):
    """Load SP500 tickers from cache, refreshing from Wikipedia if asked/missing."""
    if refresh or not os.path.exists(UNIVERSE_CACHE):
        print("Fetching SP500 list from Wikipedia...")
        tickers = fetch_sp500_tickers()
        with open(UNIVERSE_CACHE, "w") as f:
            f.write("\n".join(tickers) + "\n")
        print("Cached %d tickers -> %s" % (len(tickers), UNIVERSE_CACHE))
        return tickers
    with open(UNIVERSE_CACHE) as f:
        tickers = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    print("Loaded %d tickers from cache (%s). Use --refresh-universe to update."
          % (len(tickers), os.path.basename(UNIVERSE_CACHE)))
    return tickers


def download_daily(tickers):
    """Batch download daily OHLCV. Returns dict ticker -> DataFrame (may miss some)."""
    import yfinance as yf

    print("Downloading daily data for %d tickers (period=%s)..."
          % (len(tickers), CONFIG["period"]))
    raw = yf.download(
        tickers=tickers, period=CONFIG["period"], interval="1d",
        group_by="ticker", auto_adjust=True, threads=True, progress=False,
    )
    out = {}
    if len(tickers) == 1:
        df = raw.dropna(how="all")
        if not df.empty:
            out[tickers[0]] = df
        return out
    for t in tickers:
        if t not in raw.columns.get_level_values(0):
            continue
        df = raw[t].dropna(how="all")
        if not df.empty:
            out[t] = df
    return out


def evaluate_ticker(df):
    """Compute metrics and semaphore for one ticker. Returns dict of row values."""
    row = {}
    c = df["Close"].astype(float)
    n = len(c)
    row["bars"] = n
    if n < CONFIG["min_bars"] or c.isna().tail(5).all():
        row["status"] = "GRAY"
        row["note"] = "insufficient history (%d bars < %d)" % (n, CONFIG["min_bars"])
        return row

    close = float(c.iloc[-1])
    row["close"] = round(close, 2)

    # 12-1 momentum: close 21 sessions ago vs close 252 sessions ago
    mom = float(c.iloc[-21] / c.iloc[-252] - 1.0)
    row["mom_12_1_pct"] = round(mom * 100.0, 1)

    sma200 = float(c.rolling(CONFIG["sma_period"]).mean().iloc[-1])
    row["above_sma200"] = "Y" if close > sma200 else "N"

    hi52 = float(c.iloc[-252:].max())
    dist = (close / hi52 - 1.0) * 100.0
    row["dist_52w_high_pct"] = round(dist, 1)

    logret = np.log(c / c.shift(1))
    vol20 = logret.rolling(CONFIG["calm_vol_window"]).std() * np.sqrt(252.0) * 100.0
    vol_now = float(vol20.iloc[-1])
    vol_med = float(vol20.iloc[-CONFIG["calm_median_window"]:].median())
    row["vol20_ann_pct"] = round(vol_now, 1)
    row["vol_med6m_pct"] = round(vol_med, 1)
    calm = vol_now < vol_med
    row["calm"] = "Y" if calm else "N"

    dvol = float((c * df["Volume"]).rolling(20).mean().iloc[-1]) / 1e6
    row["dollar_vol_musd"] = round(dvol, 1)

    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - c.shift(1)).abs(),
        (df["Low"] - c.shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr = float(tr.rolling(CONFIG["atr_period"]).mean().iloc[-1])
    row["atr14_pct"] = round(atr / close * 100.0, 2)

    if any(np.isnan(v) for v in (mom, sma200, vol_now, vol_med, dvol, atr)):
        row["status"] = "GRAY"
        row["note"] = "NaN in metrics"
        return row

    fails = []
    if mom <= CONFIG["mom_12_1_min"]:
        fails.append("momentum")
    if close <= sma200:
        fails.append("sma200")
    if dvol < CONFIG["dollar_vol_min_musd"]:
        fails.append("liquidity")

    in_zone = CONFIG["pullback_min_pct"] <= dist <= CONFIG["pullback_max_pct"]

    if fails:
        row["status"] = "RED"
        row["note"] = "fails: " + ",".join(fails)
    elif in_zone and calm:
        row["status"] = "GREEN"
        row["note"] = "setup ready (calm + pullback)"
    else:
        row["status"] = "YELLOW"
        why = []
        if not in_zone:
            why.append("outside pullback zone")
        if not calm:
            why.append("vol not calm")
        row["note"] = "watch: " + ", ".join(why)
    return row


def write_html(df, path, stamp, universe_size):
    """Write a simple self-contained colored HTML table."""
    cols = list(df.columns)
    counts = df["status"].value_counts().to_dict()
    legend = " | ".join("%s: %d" % (s, counts.get(s, 0))
                        for s in ("GREEN", "YELLOW", "RED", "GRAY"))
    parts = [
        "<html><head><meta charset='ascii'><title>ALTAIR screener %s</title>" % stamp,
        "<style>body{font-family:Segoe UI,Arial,sans-serif;font-size:13px}",
        "table{border-collapse:collapse}td,th{border:1px solid #bbb;",
        "padding:3px 8px;text-align:right}th{background:#eee}",
        "td:first-child,td:nth-child(2){text-align:left}</style></head><body>",
        "<h2>ALTAIR rotation screener -- %s</h2>" % stamp,
        "<p>Universe: %d tickers | %s</p>" % (universe_size, legend),
        "<p>GREEN = enter candidate (filters + setup) | YELLOW = filters ok, wait",
        " | RED = fails hard filter | GRAY = fix data first</p>",
        "<table><tr>" + "".join("<th>%s</th>" % c for c in cols) + "</tr>",
    ]
    for _, r in df.iterrows():
        color = STATUS_COLOR.get(r["status"], "#ffffff")
        tds = "".join("<td>%s</td>" % ("" if pd.isna(v) else v) for v in r)
        parts.append("<tr style='background:%s'>%s</tr>" % (color, tds))
    parts.append("</table></body></html>")
    with open(path, "w") as f:
        f.write("\n".join(parts))


def main():
    ap = argparse.ArgumentParser(description="ALTAIR monthly rotation screener")
    ap.add_argument("--only", nargs="+", help="screen only these tickers")
    ap.add_argument("--refresh-universe", action="store_true",
                    help="re-fetch SP500 list from Wikipedia")
    ap.add_argument("--held", nargs="+", default=[],
                    help="tickers currently in the ALTAIR portfolio (marked)")
    args = ap.parse_args()

    tickers = [t.upper() for t in args.only] if args.only \
        else load_universe(args.refresh_universe)
    held = set(t.upper() for t in args.held)

    data = download_daily(tickers)
    missing = [t for t in tickers if t not in data]

    rows = []
    for t in tickers:
        if t in data:
            row = evaluate_ticker(data[t])
        else:
            row = {"status": "GRAY", "note": "download failed / no data", "bars": 0}
        row["ticker"] = t
        row["held"] = "HELD" if t in held else ""
        rows.append(row)

    cols = ["ticker", "held", "status", "close", "mom_12_1_pct", "above_sma200",
            "dist_52w_high_pct", "vol20_ann_pct", "vol_med6m_pct", "calm",
            "dollar_vol_musd", "atr14_pct", "bars", "note"]
    df = pd.DataFrame(rows)
    for c in cols:
        if c not in df.columns:
            df[c] = np.nan
    df = df[cols]
    df["_o"] = df["status"].map(STATUS_ORDER)
    df = df.sort_values(["_o", "mom_12_1_pct"], ascending=[True, False]) \
           .drop(columns="_o").reset_index(drop=True)

    os.makedirs(OUT_DIR, exist_ok=True)
    stamp = datetime.date.today().strftime("%Y-%m")
    csv_path = os.path.join(OUT_DIR, "screener_%s.csv" % stamp)
    html_path = os.path.join(OUT_DIR, "screener_%s.html" % stamp)
    df.to_csv(csv_path, index=False)
    write_html(df, html_path, stamp, len(tickers))

    print("\n=== Summary (%s) ===" % stamp)
    for s in ("GREEN", "YELLOW", "RED", "GRAY"):
        sub = df[df["status"] == s]
        print("%-6s %4d" % (s, len(sub)), end="")
        if s == "GREEN" and len(sub):
            print("  -> " + " ".join(sub["ticker"].head(25)), end="")
        print()
    if missing:
        print("Download failed: %s" % " ".join(missing[:20]))
    print("\nCSV : %s" % csv_path)
    print("HTML: %s" % html_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
