#!/usr/bin/env python
"""
VEGA Diagnostic Cross-Join Tool

Step 1C of context/VEGA_DIAG_PLAN.md.

Reads:
  - BT diag CSV produced by VEGAStrategy when export_diag=True
    (logs/VEGA_diag_<ref>_<timestamp>.csv).
  - Live monitor_multi log file containing 'VEGA diag:' lines
    emitted by vega_checker v0.9.4+ once per H4 bar.

Cross-joins by timestamp_utc and reports per-column delta
(absolute and relative). Used to identify whether the BT vs live
forecast drift originates in close_b, sma/atr, or downstream
(spread / forecast clip).

Usage:
    python tools/vega_diff_diag.py --bt logs/VEGA_diag_GDAXI_20260502_091855.csv \\
                                   --live logs/monitor_multi_2026-04-22.log \\
                                   [--config NDAXI_VEGA] \\
                                   [--out logs/vega_drift_report.csv]

If --live is a directory, scans all *.log files inside.
If --config is omitted, processes ALL VEGA diag lines found.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Add parent for any future shared imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# Live log line shape (Step 5 adds atr_a_dense / atr_b_dense between
# atr_* and z_*; older logs without those fields still parse via the
# optional groups).
# 2026-04-22 14:05:01,234 - INFO - [NDAXI_VEGA] VEGA diag: t=2026-04-22T12:00:00
#   close_a=27000.1 sma_a=26800.0 atr_a=200.0 [atr_a_dense=NNN] z_a=1.0
#   close_b=24000.1 sma_b=... atr_b=... [atr_b_dense=NNN] z_b=...
#   spread=... forecast=...
LIVE_LINE_RE = re.compile(
    r"\[(?P<config>[^\]]+)\]\s+VEGA diag:\s+t=(?P<ts>\S+)\s+"
    r"close_a=(?P<close_a>-?\d+\.?\d*)\s+"
    r"sma_a=(?P<sma_a>-?\d+\.?\d*)\s+"
    r"atr_a=(?P<atr_a>-?\d+\.?\d*)\s+"
    r"(?:atr_a_dense=(?P<atr_a_dense>-?\d+\.?\d*|nan|NaN)\s+)?"
    r"z_a=(?P<z_a>-?\d+\.?\d*)\s+"
    r"close_b=(?P<close_b>-?\d+\.?\d*)\s+"
    r"sma_b=(?P<sma_b>-?\d+\.?\d*)\s+"
    r"atr_b=(?P<atr_b>-?\d+\.?\d*)\s+"
    r"(?:atr_b_dense=(?P<atr_b_dense>-?\d+\.?\d*|nan|NaN)\s+)?"
    r"z_b=(?P<z_b>-?\d+\.?\d*)\s+"
    r"spread=(?P<spread>-?\d+\.?\d*)\s+"
    r"forecast=(?P<forecast>-?\d+\.?\d*)"
)

# Columns the BT diag CSV writes (unchanged across Step 5).
NUMERIC_COLS = (
    "close_a", "sma_a", "atr_a", "z_a",
    "close_b", "sma_b", "atr_b", "z_b",
    "spread", "forecast",
)

# Extra columns only present in live (Step 5). Optional in regex; when
# absent or NaN they are skipped from the cross-join report.
LIVE_EXTRA_COLS = ("atr_a_dense", "atr_b_dense")


def parse_bt_csv(path: Path) -> dict:
    """Return {timestamp_utc: {col: float, ...}}."""
    rows = {}
    with path.open("r", encoding="ascii") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts = row["timestamp_utc"]
            try:
                rows[ts] = {c: float(row[c]) for c in NUMERIC_COLS}
            except (KeyError, ValueError) as e:
                print(f"WARN: skipping BT row ts={ts}: {e}")
    return rows


def parse_live_logs(paths: list[Path], config_filter: str | None) -> dict:
    """Return {timestamp_utc: {col: float, ...}}. Last write wins."""
    rows = {}
    matched = 0
    for path in paths:
        try:
            with path.open("r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    m = LIVE_LINE_RE.search(line)
                    if not m:
                        continue
                    if config_filter and m.group("config") != config_filter:
                        continue
                    matched += 1
                    ts = m.group("ts")
                    try:
                        row = {c: float(m.group(c)) for c in NUMERIC_COLS}
                    except ValueError:
                        continue
                    # Optional Step 5 columns (NaN if not present or 'nan')
                    for c in LIVE_EXTRA_COLS:
                        raw = m.group(c)
                        if raw is None:
                            row[c] = float("nan")
                        else:
                            try:
                                row[c] = float(raw)
                            except ValueError:
                                row[c] = float("nan")
                    rows[ts] = row
        except OSError as e:
            print(f"WARN: cannot read {path}: {e}")
    print(f"Live diag lines matched: {matched} (unique ts: {len(rows)})")
    return rows


def normalize_ts(ts: str) -> str:
    """Ensure ISO with seconds for join."""
    try:
        dt = datetime.fromisoformat(ts)
        return dt.isoformat(timespec="seconds")
    except ValueError:
        return ts


def cross_join(bt: dict, live: dict) -> list[dict]:
    """Inner join on normalized timestamp_utc."""
    bt_norm = {normalize_ts(k): v for k, v in bt.items()}
    live_norm = {normalize_ts(k): v for k, v in live.items()}
    common = sorted(set(bt_norm) & set(live_norm))
    rows = []
    for ts in common:
        row = {"timestamp_utc": ts}
        for c in NUMERIC_COLS:
            bv = bt_norm[ts][c]
            lv = live_norm[ts][c]
            row[f"bt_{c}"] = bv
            row[f"live_{c}"] = lv
            row[f"delta_{c}"] = lv - bv
            row[f"rel_{c}"] = ((lv - bv) / bv * 100.0) if bv != 0 else 0.0
        # Step 5: dense ATR (live-only) compared against BT atr_a/b baseline.
        for c, bt_col in (("atr_a_dense", "atr_a"), ("atr_b_dense", "atr_b")):
            lv = live_norm[ts].get(c, float("nan"))
            bv = bt_norm[ts][bt_col]
            row[f"live_{c}"] = lv
            if lv == lv and bv != 0:  # not NaN
                row[f"delta_{c}"] = lv - bv
                row[f"rel_{c}"] = (lv - bv) / bv * 100.0
            else:
                row[f"delta_{c}"] = float("nan")
                row[f"rel_{c}"] = float("nan")
        rows.append(row)
    return rows


def print_summary(rows: list[dict]) -> None:
    if not rows:
        print("\nNo overlapping bars between BT and live. Nothing to compare.")
        return

    print(f"\n{'='*78}")
    print(f"  CROSS-JOIN: {len(rows)} overlapping H4 bars")
    print(f"  Range: {rows[0]['timestamp_utc']} -> {rows[-1]['timestamp_utc']}")
    print(f"{'='*78}\n")

    # Per-column stats
    print(f"{'Column':<12} {'mean|d|':>12} {'max|d|':>12} {'mean rel%':>12} "
          f"{'max rel%':>12}")
    print("-" * 78)
    for c in NUMERIC_COLS:
        deltas = [abs(r[f"delta_{c}"]) for r in rows]
        rels = [abs(r[f"rel_{c}"]) for r in rows]
        mean_d = sum(deltas) / len(deltas)
        max_d = max(deltas)
        mean_r = sum(rels) / len(rels)
        max_r = max(rels)
        print(f"{c:<12} {mean_d:>12.4f} {max_d:>12.4f} "
              f"{mean_r:>11.2f}% {max_r:>11.2f}%")

    # Worst 5 bars by |delta_forecast|
    print(f"\nWorst 5 bars by |delta_forecast|:")
    print("-" * 78)
    worst = sorted(rows, key=lambda r: abs(r["delta_forecast"]), reverse=True)[:5]
    print(f"{'timestamp':<22} {'bt_fcst':>10} {'live_fcst':>10} "
          f"{'d_close_b':>10} {'d_sma_b':>10} {'d_atr_b':>10}")
    for r in worst:
        print(f"{r['timestamp_utc']:<22} "
              f"{r['bt_forecast']:>10.4f} {r['live_forecast']:>10.4f} "
              f"{r['delta_close_b']:>10.4f} {r['delta_sma_b']:>10.4f} "
              f"{r['delta_atr_b']:>10.4f}")

    # Diagnostic verdict (table from VEGA_DIAG_PLAN.md)
    print(f"\n{'='*78}")
    print("  DIAGNOSTIC VERDICT")
    print(f"{'='*78}")
    rel_close = sum(abs(r["rel_close_b"]) for r in rows) / len(rows)
    rel_close_a = sum(abs(r["rel_close_a"]) for r in rows) / len(rows)
    rel_sma = sum(abs(r["rel_sma_b"]) for r in rows) / len(rows)
    rel_atr = sum(abs(r["rel_atr_b"]) for r in rows) / len(rows)
    rel_fcst = sum(abs(r["rel_forecast"]) for r in rows) / len(rows)

    print(f"  mean |rel close_a| = {rel_close_a:.2f}%")
    print(f"  mean |rel close_b| = {rel_close:.2f}%")
    print(f"  mean |rel sma_b|   = {rel_sma:.2f}%")
    print(f"  mean |rel atr_b|   = {rel_atr:.2f}%")
    print(f"  mean |rel forecast|= {rel_fcst:.2f}%")
    print()

    # Step 5: dense ATR validation (only when live emitted dense values).
    dense_a_rows = [r for r in rows
                    if r["rel_atr_a_dense"] == r["rel_atr_a_dense"]]
    dense_b_rows = [r for r in rows
                    if r["rel_atr_b_dense"] == r["rel_atr_b_dense"]]
    if dense_a_rows or dense_b_rows:
        print(f"  --- Step 5: DENSE H4 ATR (M1->H4) vs BT ---")
        if dense_a_rows:
            rel_dense_a = sum(abs(r["rel_atr_a_dense"]) for r in dense_a_rows) / len(dense_a_rows)
            rel_classic_a = sum(abs(r["rel_atr_a"]) for r in dense_a_rows) / len(dense_a_rows)
            print(f"  mean |rel atr_a_dense| = {rel_dense_a:.2f}%  "
                  f"(n={len(dense_a_rows)}, classic atr_a = {rel_classic_a:.2f}%)")
        if dense_b_rows:
            rel_dense_b = sum(abs(r["rel_atr_b_dense"]) for r in dense_b_rows) / len(dense_b_rows)
            rel_classic_b = sum(abs(r["rel_atr_b"]) for r in dense_b_rows) / len(dense_b_rows)
            print(f"  mean |rel atr_b_dense| = {rel_dense_b:.2f}%  "
                  f"(n={len(dense_b_rows)}, classic atr_b = {rel_classic_b:.2f}%)")
        print("  Target: dense drift < 3% (classic typically 7-8%)")
        print()

    # Heuristic verdict (informative; final call always by Ivan)
    if rel_close > 0.5 or rel_close_a > 0.5:
        print("  -> CLOSE drift > 0.5%: probable H1 (broker feed). "
              "Consider feed switch (Darwinex Cero) or DZ recalibration.")
    elif rel_sma > 0.3 or rel_atr > 0.5:
        print("  -> SMA/ATR drift with close OK: probable H2 (warmup or "
              "history mix). Persistence of state may help.")
    elif rel_fcst > 5.0 and rel_close < 0.2:
        print("  -> Forecast drift without upstream cause: probable H3 "
              "(bug in clip / formula). Audit code.")
    else:
        print("  -> No clear drift pattern. Sample may be too small "
              "(need >=10 overlapping bars in session).")
    print(f"{'='*78}\n")


def write_csv(rows: list[dict], out_path: Path) -> None:
    if not rows:
        return
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="ascii", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Detailed report written: {out_path} ({len(rows)} rows)")


def main():
    p = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--bt", required=True, type=Path,
                   help="BT diag CSV (logs/VEGA_diag_*.csv).")
    p.add_argument("--live", required=True, type=Path,
                   help="Live log file or directory of *.log files.")
    p.add_argument("--config", default=None,
                   help="Filter live lines by config name (e.g. NDAXI_VEGA).")
    p.add_argument("--out", type=Path, default=None,
                   help="Optional path to write detailed cross-join CSV.")
    args = p.parse_args()

    if not args.bt.is_file():
        print(f"ERROR: BT file not found: {args.bt}")
        sys.exit(1)

    if args.live.is_dir():
        live_paths = sorted(args.live.glob("*.log"))
        if not live_paths:
            print(f"ERROR: no *.log files in {args.live}")
            sys.exit(1)
    elif args.live.is_file():
        live_paths = [args.live]
    else:
        print(f"ERROR: live path not found: {args.live}")
        sys.exit(1)

    print(f"BT CSV:    {args.bt}")
    print(f"Live logs: {len(live_paths)} file(s)")
    if args.config:
        print(f"Config:    {args.config}")

    bt = parse_bt_csv(args.bt)
    print(f"BT rows:   {len(bt)}")
    live = parse_live_logs(live_paths, args.config)

    rows = cross_join(bt, live)
    print_summary(rows)

    if args.out:
        write_csv(rows, args.out)


if __name__ == "__main__":
    main()
