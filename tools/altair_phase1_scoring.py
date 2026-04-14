"""
ALTAIR Phase 1 -- Individual Robustness Scoring

Parses the yearly heatmap from altair_sp500_screening_results.txt and
computes a composite robustness score (0-100) for each ticker.

Scoring (ranges, NOT binary thresholds):
  Y+ ratio .......... 0-25 pts  (higher ratio = better)
  Concentration ..... 0-20 pts  (lower dominant year % = better)
  Max annual loss ... 0-20 pts  (smaller worst year = better)
  DD individual ..... 0-15 pts  (lower DD = better)
  Recent trend ...... 0-10 pts  (last 2-3 years positive = better)
  PF ................ 0-10 pts  (higher but NOT dominant factor)

Usage:
    python tools/altair_phase1_scoring.py
    python tools/altair_phase1_scoring.py --min-score 50
"""
import re
import sys
import argparse
from pathlib import Path


ANALYSIS_DIR = Path(__file__).resolve().parent.parent / "analysis"
RESULTS_FILE = ANALYSIS_DIR / "altair_sp500_screening_results.txt"


# ── Parsing ──────────────────────────────────────────────────────────────────

def parse_results(filepath):
    """Parse tier tables and yearly heatmap from screening results file."""
    text = filepath.read_text(encoding="utf-8")
    lines = text.splitlines()

    tickers = {}
    heatmap = {}
    years_cols = []

    # ── Parse TIER 1 + TIER 2 tables ──
    # Format: "  1   AXON     A   2.42  42.9   4.83   +13629   3/5    28"
    tier_re = re.compile(
        r'^\s+\d+\s+(\w+)\s+([AB])\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)'
        r'\s+([+-]?\d+)\s+(\d+)/(\d+)'
    )
    for line in lines:
        m = tier_re.match(line)
        if m:
            ticker = m.group(1)
            tickers[ticker] = {
                "config": m.group(2),
                "pf":     float(m.group(3)),
                "wr":     float(m.group(4)),
                "dd":     float(m.group(5)),
                "pnl":    int(m.group(6)),
                "y_pos":  int(m.group(7)),
                "y_tot":  int(m.group(8)),
            }

    # ── Parse yearly heatmap ──
    # Header: "Ticker  Cfg    2018    2019  ... TOTAL    PF"
    # Data:   "AXON     A       --   +7993  ... +13629  2.42"
    in_heatmap = False
    for line in lines:
        if line.strip().startswith("Ticker") and "2018" in line:
            parts = line.split()
            years_cols = [int(p) for p in parts if p.isdigit() and len(p) == 4]
            in_heatmap = True
            continue
        if in_heatmap and line.startswith("---"):
            continue
        if in_heatmap and line.strip() == "":
            # End of heatmap section
            if heatmap:
                in_heatmap = False
            continue
        if in_heatmap:
            # Split on whitespace
            parts = line.split()
            if len(parts) < 3:
                continue
            ticker = parts[0]
            if ticker not in tickers:
                continue
            # parts[1] = config letter (A or B)
            # Then year values (-- or signed int), TOTAL, PF
            values = parts[2:]
            yearly = {}
            for i, yr in enumerate(years_cols):
                if i < len(values):
                    v = values[i]
                    if v == "--":
                        yearly[yr] = None
                    else:
                        yearly[yr] = int(v)
            heatmap[ticker] = yearly

    return tickers, heatmap, years_cols


# ── Scoring functions (continuous, 0-max_pts) ───────────────────────────────

def _linear(value, lo, hi, max_pts, invert=False):
    """Linear interpolation between lo..hi mapped to 0..max_pts.
    If invert=True, lower values score higher."""
    if invert:
        value = hi - (value - lo)
        lo_old, hi_old = lo, hi
        lo, hi = 0, hi_old - lo_old
    if value <= lo:
        return 0.0
    if value >= hi:
        return float(max_pts)
    return max_pts * (value - lo) / (hi - lo)


def score_yplus(y_pos, y_tot):
    """Y+ ratio: 0-25 pts. 75%+ -> 25, 0% -> 0."""
    if y_tot == 0:
        return 0.0
    ratio = y_pos / y_tot
    return min(25.0, ratio * 33.33)


def score_concentration(yearly, total_pnl):
    """Profit concentration: 0-20 pts. Lower dominant % = better.
    If best year > 50% of total PnL -> flag and low score."""
    if total_pnl <= 0:
        return 0.0
    active_years = [v for v in yearly.values() if v is not None]
    if not active_years:
        return 0.0
    max_year = max(active_years)
    if max_year <= 0:
        return 0.0
    conc = max_year / total_pnl
    # conc <= 0.20 -> 20 pts, conc >= 0.80 -> 0 pts
    return max(0.0, min(20.0, 20.0 * (1.0 - (conc - 0.20) / 0.60)))


def score_max_loss(yearly):
    """Max annual loss: 0-20 pts. Smaller worst year loss = better.
    SBAC worst = -820 -> ~18 pts. STLD worst = -10614 -> ~7 pts."""
    losses = [v for v in yearly.values() if v is not None and v < 0]
    if not losses:
        return 20.0  # Never lost a year
    worst = abs(min(losses))
    # worst <= 500 -> 20, worst >= 10000 -> 0
    return max(0.0, min(20.0, 20.0 * (1.0 - worst / 10000.0)))


def score_dd(dd_pct):
    """DD score: 0-15 pts. Lower DD = better.
    DD <= 3% -> 15, DD >= 18% -> 0."""
    return max(0.0, min(15.0, 15.0 * (1.0 - (dd_pct - 3.0) / 15.0)))


def score_recent(yearly, years_cols):
    """Recent trend: 0-10 pts. Last 2-3 available years positive = better."""
    # Find the last 3 years with data (not None)
    recent = []
    for yr in sorted(years_cols, reverse=True):
        if yr in yearly and yearly[yr] is not None:
            recent.append(yearly[yr])
        if len(recent) == 3:
            break

    if not recent:
        return 0.0
    n_pos = sum(1 for v in recent if v > 0)
    n_total = len(recent)
    # Scale: all positive -> 10, none -> 0
    return 10.0 * n_pos / n_total


def score_pf(pf):
    """PF score: 0-10 pts. Higher PF = better, but capped at 10.
    PF <= 1.0 -> 0, PF >= 2.0 -> 10, linear between."""
    if pf <= 1.0:
        return 0.0
    if pf >= 2.0:
        return 10.0
    return 10.0 * (pf - 1.0)


def compute_scores(tickers, heatmap, years_cols):
    """Compute composite robustness score for each ticker."""
    results = []
    for ticker, info in tickers.items():
        yearly = heatmap.get(ticker, {})
        if not yearly:
            continue

        s_yp = score_yplus(info["y_pos"], info["y_tot"])
        s_co = score_concentration(yearly, info["pnl"])
        s_ml = score_max_loss(yearly)
        s_dd = score_dd(info["dd"])
        s_rc = score_recent(yearly, years_cols)
        s_pf = score_pf(info["pf"])

        total = s_yp + s_co + s_ml + s_dd + s_rc + s_pf

        # Flags
        flags = []
        active_years = [v for v in yearly.values() if v is not None]
        if info["pnl"] > 0:
            max_yr = max(active_years) if active_years else 0
            if max_yr > 0 and max_yr / info["pnl"] > 0.50:
                flags.append("CONC")
        if info["y_tot"] > 0 and info["y_pos"] / info["y_tot"] < 0.40:
            flags.append("LOW_Y+")
        if info["dd"] > 15.0:
            flags.append("HI_DD")
        losses = [v for v in active_years if v < 0]
        if losses and abs(min(losses)) > 8000:
            flags.append("BIG_LOSS")
        # Recent declining: last 2 years both negative
        recent_2 = []
        for yr in sorted(years_cols, reverse=True):
            if yr in yearly and yearly[yr] is not None:
                recent_2.append(yearly[yr])
            if len(recent_2) == 2:
                break
        if len(recent_2) == 2 and all(v < 0 for v in recent_2):
            flags.append("DECLINING")

        results.append({
            "ticker": ticker,
            "config": info["config"],
            "pf": info["pf"],
            "dd": info["dd"],
            "pnl": info["pnl"],
            "y_pos": info["y_pos"],
            "y_tot": info["y_tot"],
            "s_yp": s_yp,
            "s_co": s_co,
            "s_ml": s_ml,
            "s_dd": s_dd,
            "s_rc": s_rc,
            "s_pf": s_pf,
            "score": total,
            "flags": flags,
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


# ── Display ──────────────────────────────────────────────────────────────────

def display(results, min_score=0):
    sep = "=" * 110
    print()
    print(sep)
    print("ALTAIR PHASE 1 -- Individual Robustness Scoring")
    print(sep)
    print()
    print("Scoring:  Y+(0-25)  Conc(0-20)  MaxLoss(0-20)  DD(0-15)  Recent(0-10)  PF(0-10)  = TOTAL(0-100)")
    print()

    header = (
        f"{'#':>3}  {'Ticker':<6} {'Cfg':>3}  {'PF':>5} {'DD%':>6} "
        f"{'PnL':>8} {'Y+':>5}  "
        f"{'Y+s':>5} {'Cnc':>5} {'MLs':>5} {'DDs':>5} {'Rcs':>5} {'PFs':>5} "
        f"{'SCORE':>6}  {'Flags'}"
    )
    print(header)
    print("-" * 110)

    n = 0
    for r in results:
        if r["score"] < min_score:
            continue
        n += 1
        flags_str = ",".join(r["flags"]) if r["flags"] else ""
        print(
            f"{n:>3}  {r['ticker']:<6} {r['config']:>3}  "
            f"{r['pf']:>5.2f} {r['dd']:>5.2f}% "
            f"{r['pnl']:>+8d} {r['y_pos']}/{r['y_tot']:>1}  "
            f"{r['s_yp']:>5.1f} {r['s_co']:>5.1f} {r['s_ml']:>5.1f} "
            f"{r['s_dd']:>5.1f} {r['s_rc']:>5.1f} {r['s_pf']:>5.1f} "
            f"{r['score']:>6.1f}  {flags_str}"
        )

    print("-" * 110)
    print(f"  {n} tickers scored (min_score={min_score})")

    # Summary by tier
    top = [r for r in results if r["score"] >= 65]
    mid = [r for r in results if 50 <= r["score"] < 65]
    low = [r for r in results if r["score"] < 50]
    flagged = [r for r in results if r["flags"]]

    print()
    print(sep)
    print("SUMMARY")
    print(sep)
    print(f"  Score >= 65 (strong candidates): {len(top)}")
    for r in top:
        f = f"  [{','.join(r['flags'])}]" if r['flags'] else ""
        print(f"    {r['ticker']:<6} {r['score']:>5.1f}  PF={r['pf']:.2f}  DD={r['dd']:.1f}%{f}")
    print(f"  Score 50-64 (borderline):        {len(mid)}")
    for r in mid:
        f = f"  [{','.join(r['flags'])}]" if r['flags'] else ""
        print(f"    {r['ticker']:<6} {r['score']:>5.1f}  PF={r['pf']:.2f}  DD={r['dd']:.1f}%{f}")
    print(f"  Score < 50 (weak / flagged):     {len(low)}")
    for r in low:
        f = f"  [{','.join(r['flags'])}]" if r['flags'] else ""
        print(f"    {r['ticker']:<6} {r['score']:>5.1f}  PF={r['pf']:.2f}  DD={r['dd']:.1f}%{f}")

    if flagged:
        print()
        print("  Flagged tickers:")
        for r in flagged:
            print(f"    {r['ticker']:<6} score={r['score']:>5.1f}  flags={','.join(r['flags'])}")

    print()


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="ALTAIR Phase 1 robustness scoring")
    parser.add_argument("--min-score", type=float, default=0,
                        help="Only show tickers with score >= this value")
    args = parser.parse_args()

    if not RESULTS_FILE.exists():
        print(f"ERROR: {RESULTS_FILE} not found. Run altair_sp500_ab_test.py --pending first.")
        sys.exit(1)

    tickers, heatmap, years_cols = parse_results(RESULTS_FILE)
    if not tickers:
        print("ERROR: No tickers parsed from results file.")
        sys.exit(1)

    results = compute_scores(tickers, heatmap, years_cols)
    display(results, min_score=args.min_score)


if __name__ == "__main__":
    main()
