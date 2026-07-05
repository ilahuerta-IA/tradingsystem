"""ALTAIR rotation report -- Phase 5 (monthly decision support).

Crosses the monthly screener snapshots (results/screener/screener_*.csv)
with the current portfolio and proposes actions with hysteresis:

    MANTENER  held, filters pass in the latest month
    VIGILAR   held, RED in the latest month only (1 strike)
    SALIR     held, RED in the last 2 consecutive months (2 strikes)
    ENTRAR    not held, GREEN in the latest month (setup + edge ok)
    CANDIDATO not held, setup-ready but edge pending (fill spread table)

The proposal is decision SUPPORT: Ivan decides (Axiom 7). Any executed
change goes to config/settings.py AND live/bot_settings.py (Axiom 1),
with active=False for exits (Axiom 9) and a live version bump (Axiom 13).

Usage:
    python tools/altair_rotation_report.py                  # held from latest CSV
    python tools/altair_rotation_report.py --held JPM NVDA  # override

Output: console + results/screener/rotation_YYYY-MM.txt
Process doc: context/ALTAIR_ROTACION_RUNBOOK.md (Paso 6)
"""

import argparse
import glob
import os
import sys

import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
SCREEN_DIR = os.path.join(REPO_ROOT, "results", "screener")


def load_snapshots():
    """Load all monthly screener CSVs, oldest to newest. Returns list of
    (month, DataFrame indexed by ticker)."""
    snaps = []
    for path in sorted(glob.glob(os.path.join(SCREEN_DIR, "screener_*.csv"))):
        month = os.path.basename(path)[len("screener_"):-len(".csv")]
        df = pd.read_csv(path).set_index("ticker")
        snaps.append((month, df))
    return snaps


def main():
    ap = argparse.ArgumentParser(description="ALTAIR monthly rotation report")
    ap.add_argument("--held", nargs="+",
                    help="current portfolio (default: HELD column of latest CSV)")
    args = ap.parse_args()

    snaps = load_snapshots()
    if not snaps:
        print("No screener snapshots in %s -- run the screener first." % SCREEN_DIR)
        return 1
    months = [m for m, _ in snaps]
    latest_month, latest = snaps[-1]
    prev = snaps[-2][1] if len(snaps) >= 2 else None

    if args.held:
        held = [t.upper() for t in args.held]
    else:
        held = latest[latest["held"] == "HELD"].index.tolist()

    lines = []
    lines.append("ALTAIR rotation report -- %s" % latest_month)
    lines.append("Snapshots available: %s" % ", ".join(months))
    if prev is None:
        lines.append("NOTE: only 1 snapshot -> hysteresis (2 strikes) not yet "
                     "computable; SALIR needs next month's run.")
    lines.append("")

    lines.append("--- Portfolio (%d held) ---" % len(held))
    for t in held:
        if t not in latest.index:
            lines.append("%-6s ???      not in screener universe" % t)
            continue
        now = latest.loc[t]
        red_now = now["status"] == "RED"
        red_prev = (prev is not None and t in prev.index
                    and prev.loc[t]["status"] == "RED")
        if red_now and red_prev:
            action = "SALIR"
        elif red_now:
            action = "VIGILAR"
        else:
            action = "MANTENER"
        lines.append("%-6s %-9s status=%-6s mom=%s%% note=%s"
                     % (t, action, now["status"], now["mom_12_1_pct"],
                        str(now["note"])[:60]))

    greens = latest[(latest["status"] == "GREEN") & (latest["held"] != "HELD")]
    lines.append("")
    lines.append("--- ENTRAR: %d (GREEN, setup + edge ok) ---" % len(greens))
    for t, r in greens.sort_values("mom_12_1_pct", ascending=False).iterrows():
        lines.append("%-6s mom=%5s%%  edge=%s  %s"
                     % (t, r["mom_12_1_pct"], r.get("edge_ratio", ""),
                        str(r["note"])[:50]))

    cand = latest[latest["note"].astype(str).str.startswith("setup ready BUT")]
    cand = cand[cand["held"] != "HELD"]
    lines.append("")
    lines.append("--- CANDIDATO: %d (setup ready, edge/spread pending) ---" % len(cand))
    for t, r in cand.sort_values("mom_12_1_pct", ascending=False).iterrows():
        lines.append("%-6s mom=%5s%%  atr=%s%%  %s"
                     % (t, r["mom_12_1_pct"], r["atr14_pct"],
                        str(r["note"])[:50]))

    lines.append("")
    lines.append("Reminder: changes go to config/settings.py AND "
                 "live/bot_settings.py; exits keep the config with "
                 "active=False; bump live version.")

    report = "\n".join(lines)
    print(report)
    out_path = os.path.join(SCREEN_DIR, "rotation_%s.txt" % latest_month)
    with open(out_path, "w") as f:
        f.write(report + "\n")
    print("\nSaved: %s" % out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
