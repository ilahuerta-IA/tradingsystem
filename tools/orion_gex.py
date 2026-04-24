#!/usr/bin/env python3
"""
ORION GEX/OI Overlay -- Gamma Exposure analysis for manual trading.

Phase 1: snapshot GEX levels (CALL_WALL, PUT_WALL, GAMMA_FLIP, MAX_GEX, MAX_OI)
Phase 2: automatic reading (strength labels + bias + edge)
Phase 3: JSONL history persistence + 6 automatic patterns + multi-day evolution

Usage (single):
    python tools/orion_gex.py --ticker GOOGL
    python tools/orion_gex.py --ticker GOOGL --plot
    python tools/orion_gex.py --ticker SPY --expiry 2026-05-15 --plot

Usage (batch / routine):
    python tools/orion_gex.py --scan GOOGL JPM GS NVDA
    python tools/orion_gex.py --scan-altair          # CORE + CONTEXTO tickers

Usage (history / patterns):
    python tools/orion_gex.py --history NVDA         # last N days table
    python tools/orion_gex.py --patterns             # detected events last 5d

Outputs:
    logs/orion/history.jsonl                            -- daily history (1 line/ticker/day, last-write-wins)
    logs/orion/snapshots/{TICKER}_{YYYYMMDD_HHMM}.json  -- raw GEX snapshot per run (intraday)
    logs/orion/patterns.log                             -- detected events log

Dependencies: yfinance, scipy, numpy, matplotlib, pandas
"""

import argparse
import datetime as dt
import json
import os
import sys

import numpy as np
from scipy.stats import norm


# ---------------------------------------------------------------------------
# Constants -- ticker tiers for --scan-altair
# ---------------------------------------------------------------------------

CORE_TICKERS = ["JPM", "NVDA", "GOOGL", "V", "ALB", "WDC", "GS"]
CONTEXT_TICKERS = ["SPY", "QQQ"]
ALL_TICKERS = CORE_TICKERS + CONTEXT_TICKERS

DEFAULT_RISK_FREE = 0.045


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _project_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _logs_dir():
    path = os.path.join(_project_root(), "logs", "orion")
    os.makedirs(os.path.join(path, "snapshots"), exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# Black-Scholes Gamma
# ---------------------------------------------------------------------------

def bs_gamma(S, K, T, r, sigma):
    """Black-Scholes gamma for a European option.

    Args:
        S: Spot price.
        K: Strike price.
        T: Time to expiry in years (must be > 0).
        r: Risk-free rate (annualized).
        sigma: Implied volatility (annualized).

    Returns:
        Gamma value (same for calls and puts).
    """
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    return float(norm.pdf(d1) / (S * sigma * np.sqrt(T)))


# ---------------------------------------------------------------------------
# GEX calculation
# ---------------------------------------------------------------------------

def _safe_int(val):
    """Coerce yfinance numeric (may be NaN/None) to int, default 0."""
    try:
        if val is None:
            return 0
        f = float(val)
        if f != f:  # NaN check
            return 0
        return int(f)
    except (TypeError, ValueError):
        return 0


def _safe_float(val):
    """Coerce yfinance numeric (may be NaN/None) to float, default 0.0."""
    try:
        if val is None:
            return 0.0
        f = float(val)
        if f != f:  # NaN check
            return 0.0
        return f
    except (TypeError, ValueError):
        return 0.0


def calc_gex_per_strike(calls_df, puts_df, spot, T, r=DEFAULT_RISK_FREE):
    """Calculate net Gamma Exposure per strike.

    GEX_call = +OI * gamma * 100 * spot^2 * 0.01
    GEX_put  = -OI * gamma * 100 * spot^2 * 0.01  (MMs short puts -> negative)
    """
    import pandas as pd

    strikes = sorted(
        set(calls_df["strike"].tolist()) | set(puts_df["strike"].tolist())
    )

    rows = []
    for K in strikes:
        c_row = calls_df[calls_df["strike"] == K]
        p_row = puts_df[puts_df["strike"] == K]

        c_oi = _safe_int(c_row["openInterest"].iloc[0]) if len(c_row) else 0
        p_oi = _safe_int(p_row["openInterest"].iloc[0]) if len(p_row) else 0

        c_iv = _safe_float(c_row["impliedVolatility"].iloc[0]) if len(c_row) else 0.0
        p_iv = _safe_float(p_row["impliedVolatility"].iloc[0]) if len(p_row) else 0.0

        c_gamma = bs_gamma(spot, K, T, r, c_iv) if c_iv > 0 else 0.0
        p_gamma = bs_gamma(spot, K, T, r, p_iv) if p_iv > 0 else 0.0

        multiplier = 100 * spot ** 2 * 0.01

        c_gex = c_oi * c_gamma * multiplier
        p_gex = -p_oi * p_gamma * multiplier

        rows.append({
            "strike": K,
            "call_oi": c_oi,
            "put_oi": p_oi,
            "call_gamma": c_gamma,
            "put_gamma": p_gamma,
            "call_gex": c_gex,
            "put_gex": p_gex,
            "net_gex": c_gex + p_gex,
        })

    return pd.DataFrame(rows)


def identify_levels(gex_df, spot):
    """Identify key GEX/OI levels (returns dict)."""
    levels = {}

    below = gex_df[gex_df["strike"] <= spot].copy()
    if len(below):
        idx = below["put_gex"].abs().idxmax()
        levels["PUT_WALL"] = float(below.loc[idx, "strike"])

    above = gex_df[gex_df["strike"] >= spot].copy()
    if len(above):
        idx = above["call_gex"].idxmax()
        levels["CALL_WALL"] = float(above.loc[idx, "strike"])

    df_sorted = gex_df.sort_values("strike").reset_index(drop=True)
    sign_changes = []
    for i in range(1, len(df_sorted)):
        prev_gex = df_sorted.loc[i - 1, "net_gex"]
        curr_gex = df_sorted.loc[i, "net_gex"]
        if prev_gex * curr_gex < 0:
            s0 = df_sorted.loc[i - 1, "strike"]
            s1 = df_sorted.loc[i, "strike"]
            flip = s0 + (s1 - s0) * (-prev_gex) / (curr_gex - prev_gex)
            sign_changes.append(flip)
    if sign_changes:
        levels["GAMMA_FLIP"] = float(
            min(sign_changes, key=lambda x: abs(x - spot))
        )

    idx = gex_df["net_gex"].abs().idxmax()
    levels["MAX_GEX"] = float(gex_df.loc[idx, "strike"])

    if gex_df["call_oi"].sum() > 0:
        idx = gex_df["call_oi"].idxmax()
        levels["MAX_CALL_OI"] = float(gex_df.loc[idx, "strike"])
    if gex_df["put_oi"].sum() > 0:
        idx = gex_df["put_oi"].idxmax()
        levels["MAX_PUT_OI"] = float(gex_df.loc[idx, "strike"])

    return levels


# ---------------------------------------------------------------------------
# Phase 2 -- Automatic analysis (strengths + reading)
# ---------------------------------------------------------------------------

def _gex_at_strike(gex_df, strike, column):
    row = gex_df[gex_df["strike"] == strike]
    if not len(row):
        return 0.0
    return float(row[column].iloc[0])


def _oi_at_strike(gex_df, strike, side):
    col = "call_oi" if side == "call" else "put_oi"
    row = gex_df[gex_df["strike"] == strike]
    if not len(row):
        return 0
    return int(row[col].iloc[0])


def _strength_label(rel):
    if rel > 0.30:
        return "DOMINANTE"
    if rel >= 0.15:
        return "FUERTE"
    return "REFERENCIA"


def analyze_levels(gex_df, spot, levels):
    """Compute relative strengths, asymmetry, regime and reading metadata.

    Returns dict with normalized analysis fields used by reading + history.
    """
    total_abs_gex = float(gex_df["net_gex"].abs().sum()) or 1.0
    total_oi = int(gex_df["call_oi"].sum() + gex_df["put_oi"].sum()) or 1

    call_wall = levels.get("CALL_WALL")
    put_wall = levels.get("PUT_WALL")
    gamma_flip = levels.get("GAMMA_FLIP")

    call_wall_gex = abs(_gex_at_strike(gex_df, call_wall, "call_gex")) if call_wall else 0.0
    put_wall_gex = abs(_gex_at_strike(gex_df, put_wall, "put_gex")) if put_wall else 0.0

    call_wall_strength = call_wall_gex / total_abs_gex
    put_wall_strength = put_wall_gex / total_abs_gex

    call_wall_oi = _oi_at_strike(gex_df, call_wall, "call") if call_wall else 0
    put_wall_oi = _oi_at_strike(gex_df, put_wall, "put") if put_wall else 0

    # Asymmetry: PUT_WALL gex / CALL_WALL gex
    if call_wall_gex > 0:
        asym = put_wall_gex / call_wall_gex
    else:
        asym = float("inf") if put_wall_gex > 0 else 1.0

    # Regime
    if gamma_flip is None:
        regime = "UNKNOWN"
    elif spot >= gamma_flip:
        regime = "STABLE"
    else:
        regime = "SHORT_GAMMA"

    # Distance flags
    def dist_pct(strike):
        if strike is None:
            return None
        return (strike / spot - 1.0) * 100.0

    dist_call = dist_pct(call_wall)
    dist_put = dist_pct(put_wall)
    dist_flip = dist_pct(gamma_flip)

    # Pinning detection: spot within 0.5% of CALL_WALL or GAMMA_FLIP
    pinning = False
    pinning_target = None
    for name, d in (("CALL_WALL", dist_call), ("GAMMA_FLIP", dist_flip)):
        if d is not None and abs(d) < 0.5:
            pinning = True
            pinning_target = name
            break

    return {
        "total_abs_gex": total_abs_gex,
        "total_oi": total_oi,
        "call_wall_strength": call_wall_strength,
        "put_wall_strength": put_wall_strength,
        "call_wall_label": _strength_label(call_wall_strength),
        "put_wall_label": _strength_label(put_wall_strength),
        "call_wall_oi": call_wall_oi,
        "put_wall_oi": put_wall_oi,
        "asym": asym,
        "regime": regime,
        "dist_call_pct": dist_call,
        "dist_put_pct": dist_put,
        "dist_flip_pct": dist_flip,
        "pinning": pinning,
        "pinning_target": pinning_target,
    }


def _bias_text(asym):
    if asym == float("inf") or asym > 3:
        return f"Asimetria {asym:.1f}x (suelo MUY FUERTE / techo debil)"
    if asym < 0.33:
        return f"Asimetria {asym:.2f}x (techo MUY FUERTE / suelo debil)"
    if 0.7 <= asym <= 1.5:
        return f"Asimetria {asym:.2f}x (EQUILIBRADO)"
    if asym > 1.5:
        return f"Asimetria {asym:.2f}x (sesgo alcista, suelo > techo)"
    return f"Asimetria {asym:.2f}x (sesgo bajista, techo > suelo)"


def _regime_text(analysis, spot, levels):
    flip = levels.get("GAMMA_FLIP")
    if flip is None:
        return "Regimen indeterminado (no GAMMA_FLIP detectado)"
    diff_pct = (spot - flip) / spot * 100
    if analysis["regime"] == "STABLE":
        return f"Regimen ESTABLE (spot {diff_pct:+.2f}% sobre flip {flip:.2f})"
    return f"Regimen SHORT-GAMMA (spot {diff_pct:+.2f}% bajo flip {flip:.2f}, volatilidad acelerada)"


def _edge_text(spot, levels, analysis):
    lines = []
    cw = levels.get("CALL_WALL")
    pw = levels.get("PUT_WALL")
    if analysis["pinning"]:
        lines.append(
            f"PINNING en {analysis['pinning_target']} -- evitar trades direccionales"
        )
    if cw is not None:
        lines.append(
            f"Subida hacia {cw:.2f} = resistencia {analysis['call_wall_label']} (TP natural)"
        )
    if pw is not None:
        lines.append(
            f"Bajada hacia {pw:.2f} = soporte {analysis['put_wall_label']} (rebote esperado)"
        )
    return lines


def print_reading(ticker, spot, levels, analysis):
    """Print the LECTURA AUTOMATICA block."""
    print()
    print("  >>> LECTURA AUTOMATICA <<<")
    print(f"  {_regime_text(analysis, spot, levels)}")
    print(f"  {_bias_text(analysis['asym'])}")
    for line in _edge_text(spot, levels, analysis):
        print(f"  {line}")
    print()


# ---------------------------------------------------------------------------
# Output (console + CSV)
# ---------------------------------------------------------------------------

def print_levels(ticker, spot, levels, expiry, gex_df, analysis=None):
    """Pretty-print key levels to console (with optional Phase 2 labels)."""
    print(f"\n{'='*64}")
    print(f"  ORION GEX -- {ticker}  |  Spot: {spot:.2f}  |  Expiry: {expiry}")
    print(f"{'='*64}")

    order = [
        "CALL_WALL", "MAX_CALL_OI", "GAMMA_FLIP",
        "MAX_GEX", "PUT_WALL", "MAX_PUT_OI",
    ]
    for key in order:
        if key not in levels:
            continue
        val = levels[key]
        dist = ((val / spot) - 1) * 100
        tag = "(at spot)"
        if val > spot:
            tag = "(above)"
        elif val < spot:
            tag = "(below)"

        extra = ""
        if analysis:
            if key == "CALL_WALL":
                extra = (f"  [{analysis['call_wall_label']}]"
                         f"  Fuerza {analysis['call_wall_strength']*100:.0f}%"
                         f" | OI {analysis['call_wall_oi']:,}")
            elif key == "PUT_WALL":
                extra = (f"  [{analysis['put_wall_label']}]"
                         f"  Fuerza {analysis['put_wall_strength']*100:.0f}%"
                         f" | OI {analysis['put_wall_oi']:,}")
        print(f"  {key:<14s}  {val:>10.2f}  {dist:>+6.1f}%  {tag}{extra}")

    top5 = gex_df.reindex(
        gex_df["net_gex"].abs().nlargest(5).index
    ).sort_values("strike")
    print(f"\n  Top GEX strikes:")
    print(f"  {'Strike':>10s}  {'Net GEX':>12s}  {'Call OI':>8s}  {'Put OI':>8s}")
    for _, r in top5.iterrows():
        print(
            f"  {r['strike']:>10.2f}  {r['net_gex']:>12,.0f}"
            f"  {r['call_oi']:>8,.0f}  {r['put_oi']:>8,.0f}"
        )


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def plot_gex(ticker, spot, levels, gex_df, expiry):
    import matplotlib.pyplot as plt

    lo = spot * 0.85
    hi = spot * 1.15
    df_plot = gex_df[
        (gex_df["strike"] >= lo) & (gex_df["strike"] <= hi)
    ].copy()

    if df_plot.empty:
        print(f"  WARNING: No strikes in [{lo:.0f}, {hi:.0f}] range for plot.")
        return

    colors = ["green" if x >= 0 else "red" for x in df_plot["net_gex"]]

    fig, ax = plt.subplots(figsize=(14, 6))
    ax.bar(df_plot["strike"], df_plot["net_gex"],
           width=(hi - lo) / len(df_plot) * 0.7,
           color=colors, alpha=0.7, edgecolor="none")

    ax.axvline(spot, color="blue", linewidth=1.5, linestyle="--",
               label=f"Spot {spot:.2f}")

    level_colors = {
        "PUT_WALL": "darkred",
        "CALL_WALL": "darkgreen",
        "GAMMA_FLIP": "purple",
        "MAX_GEX": "orange",
        "MAX_CALL_OI": "limegreen",
        "MAX_PUT_OI": "salmon",
    }
    for name, price in levels.items():
        if lo <= price <= hi:
            c = level_colors.get(name, "gray")
            ax.axvline(price, color=c, linewidth=1.2, linestyle="-.",
                       label=f"{name} {price:.2f}")

    ax.set_title(
        f"ORION GEX -- {ticker} | Expiry {expiry} | Spot {spot:.2f}",
        fontsize=13, fontweight="bold")
    ax.set_xlabel("Strike")
    ax.set_ylabel("Net Gamma Exposure ($)")
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    ax.axhline(0, color="black", linewidth=0.5)
    plt.tight_layout()
    plt.show()


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def fetch_options_data(ticker_str, expiry=None):
    """Fetch options chain + spot from yfinance."""
    import yfinance as yf

    tk = yf.Ticker(ticker_str)
    expiries = tk.options
    if not expiries:
        raise ValueError(f"No options expiries found for {ticker_str}")

    if expiry is None:
        today = dt.date.today()
        chosen = None
        for exp in expiries:
            exp_date = dt.datetime.strptime(exp, "%Y-%m-%d").date()
            if (exp_date - today).days >= 7:
                chosen = exp
                break
        if chosen is None:
            chosen = expiries[-1]
    else:
        if expiry not in expiries:
            raise ValueError(
                f"Expiry {expiry} not available. Options: {expiries[:10]}"
            )
        chosen = expiry

    chain = tk.option_chain(chosen)
    hist = tk.history(period="5d")
    if hist.empty:
        raise ValueError(f"No price history for {ticker_str}")
    spot = float(hist["Close"].iloc[-1])

    return chain.calls, chain.puts, spot, chosen, expiries


# ---------------------------------------------------------------------------
# Phase 3 -- History persistence (JSONL + snapshots)
# ---------------------------------------------------------------------------

def _history_path():
    return os.path.join(_logs_dir(), "history.jsonl")


def _snapshot_path(ticker, stamp):
    """stamp is YYYYMMDD_HHMM so multiple runs/day are preserved (for --compare)."""
    return os.path.join(_logs_dir(), "snapshots", f"{ticker}_{stamp}.json")


def _patterns_log_path():
    return os.path.join(_logs_dir(), "patterns.log")


def append_history(ticker, spot, levels, analysis, expiry, gex_df):
    """Append today's record to history.jsonl + write raw snapshot.

    If a record for (ticker, today) already exists, REPLACE it (idempotent).
    """
    today = dt.date.today().isoformat()
    record = {
        "date": today,
        "ticker": ticker,
        "spot": round(spot, 4),
        "expiry": expiry,
        "call_wall": levels.get("CALL_WALL"),
        "put_wall": levels.get("PUT_WALL"),
        "gamma_flip": levels.get("GAMMA_FLIP"),
        "max_gex_strike": levels.get("MAX_GEX"),
        "max_call_oi": levels.get("MAX_CALL_OI"),
        "max_put_oi": levels.get("MAX_PUT_OI"),
        "asym": _safe_round(analysis["asym"], 3),
        "total_gex": round(analysis["total_abs_gex"], 0),
        "total_oi": int(analysis["total_oi"]),
        "regime": analysis["regime"],
        "call_wall_strength": round(analysis["call_wall_strength"], 4),
        "put_wall_strength": round(analysis["put_wall_strength"], 4),
        "call_wall_oi": int(analysis["call_wall_oi"]),
        "put_wall_oi": int(analysis["put_wall_oi"]),
        "pinning": bool(analysis["pinning"]),
    }

    path = _history_path()
    # Read existing, drop same-day same-ticker, append, rewrite.
    existing = []
    if os.path.exists(path):
        with open(path, "r", encoding="ascii") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("date") == today and obj.get("ticker") == ticker:
                    continue
                existing.append(obj)
    existing.append(record)
    with open(path, "w", encoding="ascii") as f:
        for obj in existing:
            f.write(json.dumps(obj) + "\n")

    # Raw snapshot per ticker/run (timestamped HHMM so we keep all intraday runs).
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M")
    snap_path = _snapshot_path(ticker, stamp)
    snapshot = {
        "meta": record,
        "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
        "gex_profile": gex_df.to_dict(orient="records"),
    }
    with open(snap_path, "w", encoding="ascii") as f:
        json.dump(snapshot, f, default=_json_default)


def _safe_round(val, n):
    if val is None or val == float("inf") or val == float("-inf"):
        return None
    try:
        return round(float(val), n)
    except (TypeError, ValueError):
        return None


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(f"Object of type {type(o)} is not JSON serializable")


def load_history(ticker=None, days=7):
    """Load history.jsonl as DataFrame, optionally filtered by ticker + days."""
    import pandas as pd

    path = _history_path()
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_json(path, lines=True)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"]).dt.date
    if ticker:
        df = df[df["ticker"] == ticker]
    if days:
        cutoff = dt.date.today() - dt.timedelta(days=days)
        df = df[df["date"] >= cutoff]
    return df.sort_values(["ticker", "date"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Phase 3 -- Pattern detection (6 rules)
# ---------------------------------------------------------------------------

def detect_patterns(history_df, ticker):
    """Apply the 6 ORION patterns on ticker subset.

    Returns list of (pattern_name, message) tuples for events triggered today.
    """
    events = []
    df = history_df[history_df["ticker"] == ticker].sort_values("date").reset_index(drop=True)
    if len(df) < 1:
        return events

    today_row = df.iloc[-1]
    today_call = today_row.get("call_wall")
    today_put = today_row.get("put_wall")
    today_flip = today_row.get("gamma_flip")
    today_spot = today_row.get("spot")
    today_asym = today_row.get("asym")

    # 1. WALL CONSOLIDADO -- same call_wall or put_wall for >=3 consecutive days
    if len(df) >= 3:
        last3 = df.tail(3)
        if today_call is not None and (last3["call_wall"] == today_call).all():
            count = _count_consecutive(df["call_wall"].tolist(), today_call)
            events.append((
                "WALL_CONSOLIDADO",
                f"CALL_WALL CONSOLIDADO en {today_call:.2f} ({count} dias) -- "
                f"resistencia institucional confirmada"))
        if today_put is not None and (last3["put_wall"] == today_put).all():
            count = _count_consecutive(df["put_wall"].tolist(), today_put)
            events.append((
                "WALL_CONSOLIDADO",
                f"PUT_WALL CONSOLIDADO en {today_put:.2f} ({count} dias) -- "
                f"soporte institucional confirmado"))

    # 2. WALL MIGRANDO -- wall strike moves >2% in <=3 days
    if len(df) >= 2:
        for label, col in (("CALL_WALL", "call_wall"), ("PUT_WALL", "put_wall")):
            today_val = df.iloc[-1][col]
            for lookback in (1, 2, 3):
                if len(df) <= lookback:
                    continue
                prev_val = df.iloc[-1 - lookback][col]
                if prev_val is None or today_val is None or prev_val == 0:
                    continue
                change_pct = (today_val - prev_val) / prev_val * 100
                if abs(change_pct) > 2.0:
                    direction = "arriba" if change_pct > 0 else "abajo"
                    events.append((
                        "WALL_MIGRANDO",
                        f"{label} migra {prev_val:.2f}->{today_val:.2f} "
                        f"({change_pct:+.1f}%) en {lookback} dia(s) -- "
                        f"presion {direction}"))
                    break

    # 3. ASIMETRIA EXTREMA
    if today_asym is not None:
        if today_asym == float("inf") or today_asym > 3:
            events.append((
                "ASIMETRIA_EXTREMA",
                f"Asimetria {today_asym:.1f}x -- sesgo claro: suelo MUY fuerte, techo debil"))
        elif today_asym < 0.33:
            events.append((
                "ASIMETRIA_EXTREMA",
                f"Asimetria {today_asym:.2f}x -- sesgo claro: techo MUY fuerte, suelo debil"))

    # 4. PINNING ACTIVO
    if today_row.get("pinning"):
        target_strike = today_call if today_call is not None else today_flip
        if target_strike is not None:
            events.append((
                "PINNING_ACTIVO",
                f"PINNING en {target_strike:.2f} -- rango lateral, evitar trades direccionales"))

    # 5. REGIMEN FLIPPED -- spot crosses GAMMA_FLIP between yesterday and today
    if len(df) >= 2 and today_flip is not None:
        prev_row = df.iloc[-2]
        prev_flip = prev_row.get("gamma_flip")
        prev_spot = prev_row.get("spot")
        if prev_flip is not None and prev_spot is not None:
            prev_above = prev_spot >= prev_flip
            today_above = today_spot >= today_flip
            if prev_above != today_above:
                direction = "alcista (long-gamma)" if today_above else "bajista (short-gamma)"
                events.append((
                    "REGIMEN_FLIPPED",
                    f"FLIPPED {direction} -- spot cruzo el GAMMA_FLIP en {today_flip:.2f}, "
                    f"esperar cambio de volatilidad"))

    # 6. WALL ROTO -- spot exceeds previous CALL_WALL or breaks previous PUT_WALL
    if len(df) >= 2:
        prev_row = df.iloc[-2]
        prev_call = prev_row.get("call_wall")
        prev_put = prev_row.get("put_wall")
        if prev_call is not None and today_spot > prev_call:
            events.append((
                "WALL_ROTO",
                f"CALL_WALL roto ({prev_call:.2f} -> spot {today_spot:.2f}) -- "
                f"resistencia cedio, momentum alcista institucional"))
        if prev_put is not None and today_spot < prev_put:
            events.append((
                "WALL_ROTO",
                f"PUT_WALL roto ({prev_put:.2f} -> spot {today_spot:.2f}) -- "
                f"soporte cedio, momentum bajista institucional"))

    return events


def _count_consecutive(values, target):
    """Count trailing consecutive occurrences of target in list."""
    count = 0
    for v in reversed(values):
        if v == target:
            count += 1
        else:
            break
    return count


def log_patterns(ticker, events):
    """Append detected events to patterns.log with timestamp."""
    if not events:
        return
    path = _patterns_log_path()
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(path, "a", encoding="ascii") as f:
        for name, msg in events:
            f.write(f"{ts}  {ticker:6s}  [{name:18s}]  {msg}\n")


def print_patterns(ticker, events):
    if not events:
        return
    print(f"\n  >>> PATRONES DETECTADOS ({ticker}) <<<")
    for name, msg in events:
        print(f"  [{name}] {msg}")


# ---------------------------------------------------------------------------
# Phase 3 -- CLI views (--history / --patterns)
# ---------------------------------------------------------------------------

def cmd_history(ticker, days=7):
    """Print history evolution table for one ticker."""
    df = load_history(ticker, days=days)
    if df.empty:
        print(f"  No history for {ticker} in last {days} days.")
        return
    print(f"\n{'='*72}")
    print(f"  ORION HISTORY -- {ticker}  (last {days} days, {len(df)} records)")
    print(f"{'='*72}")
    print(f"  {'Date':<12s} {'Spot':>8s} {'CallW':>8s} {'PutW':>8s} "
          f"{'Flip':>8s} {'Asym':>6s} {'Regime':>12s}")
    for _, r in df.iterrows():
        cw = r.get("call_wall")
        pw = r.get("put_wall")
        fl = r.get("gamma_flip")
        asym = r.get("asym")
        print(f"  {str(r['date']):<12s} {r['spot']:>8.2f} "
              f"{cw if cw is None else f'{cw:>8.2f}'} "
              f"{pw if pw is None else f'{pw:>8.2f}'} "
              f"{fl if fl is None else f'{fl:>8.2f}'} "
              f"{asym if asym is None else f'{asym:>6.2f}'} "
              f"{str(r.get('regime', '-')):>12s}")
    print()


def cmd_patterns(days=5):
    """Re-run detection on history and print all triggered events for last N days."""
    df = load_history(days=days)
    if df.empty:
        print(f"  No history loaded for last {days} days.")
        return
    print(f"\n{'='*72}")
    print(f"  ORION PATTERNS -- last {days} days")
    print(f"{'='*72}")
    tickers = sorted(df["ticker"].unique())
    total = 0
    for tk in tickers:
        events = detect_patterns(df, tk)
        if events:
            print_patterns(tk, events)
            total += len(events)
    print(f"\n  Total events: {total}")


# ---------------------------------------------------------------------------
# Phase 4 -- Intraday compare (--compare TICKER)
# ---------------------------------------------------------------------------

def _list_snapshots(ticker):
    """Return list of (filepath, mtime) for all snapshots of ticker, newest first."""
    import glob
    pattern = os.path.join(_logs_dir(), "snapshots", f"{ticker}_*.json")
    files = glob.glob(pattern)
    files_with_mtime = [(f, os.path.getmtime(f)) for f in files]
    files_with_mtime.sort(key=lambda x: x[1], reverse=True)
    return files_with_mtime


def _load_snapshot(path):
    with open(path, "r", encoding="ascii") as f:
        return json.load(f)


def _fmt_strike(val):
    if val is None:
        return "  --  "
    return f"{val:.2f}"


def _arrow(prev, curr):
    if prev is None or curr is None:
        return "?"
    if curr > prev:
        return "UP"
    if curr < prev:
        return "DN"
    return "=="


def cmd_compare(ticker):
    """Compare the 2 most recent snapshots for ticker. Shows GEX/level migration."""
    snaps = _list_snapshots(ticker)
    if len(snaps) < 2:
        print(f"  Need at least 2 snapshots for {ticker}, found {len(snaps)}.")
        print(f"  Run: python tools/orion_gex.py --ticker {ticker}  (twice)")
        return

    new_path, _ = snaps[0]
    old_path, _ = snaps[1]
    new_snap = _load_snapshot(new_path)
    old_snap = _load_snapshot(old_path)

    new_meta = new_snap["meta"]
    old_meta = old_snap["meta"]
    new_ts = new_snap.get("timestamp", os.path.basename(new_path))
    old_ts = old_snap.get("timestamp", os.path.basename(old_path))

    # Time delta
    try:
        t_new = dt.datetime.fromisoformat(new_ts)
        t_old = dt.datetime.fromisoformat(old_ts)
        delta_min = int((t_new - t_old).total_seconds() / 60)
        delta_str = f"{delta_min} min"
    except (ValueError, TypeError):
        delta_str = "?"

    print(f"\n{'='*64}")
    print(f"  ORION DIFF -- {ticker}  |  {old_ts} -> {new_ts}  ({delta_str})")
    print(f"{'='*64}")

    # Spot
    s0 = old_meta["spot"]
    s1 = new_meta["spot"]
    spot_pct = (s1 / s0 - 1) * 100 if s0 else 0
    print(f"  Spot:        {s0:>8.2f} -> {s1:>8.2f}   ({spot_pct:+.2f}%)")

    # Walls + flip
    for label, key in (("CALL_WALL", "call_wall"),
                       ("PUT_WALL ", "put_wall"),
                       ("GAMMA_FLIP", "gamma_flip"),
                       ("MAX_GEX  ", "max_gex_strike")):
        v0 = old_meta.get(key)
        v1 = new_meta.get(key)
        arrow = _arrow(v0, v1)
        delta = ""
        if v0 is not None and v1 is not None and v0 != v1:
            delta = f"  {v1 - v0:+.2f}"
        print(f"  {label}:  {_fmt_strike(v0):>8s} -> {_fmt_strike(v1):>8s}  [{arrow}]{delta}")

    # Asymmetry
    a0 = old_meta.get("asym")
    a1 = new_meta.get("asym")
    if a0 is not None and a1 is not None:
        delta_a = a1 - a0
        print(f"  Asimetria:   {a0:>8.2f} -> {a1:>8.2f}   ({delta_a:+.2f})")

    # Per-strike NetGEX changes (top movers)
    new_profile = {row["strike"]: row["net_gex"] for row in new_snap["gex_profile"]}
    old_profile = {row["strike"]: row["net_gex"] for row in old_snap["gex_profile"]}
    common = set(new_profile) & set(old_profile)
    diffs = []
    for strike in common:
        change = new_profile[strike] - old_profile[strike]
        if abs(change) > 0:
            diffs.append((strike, old_profile[strike], new_profile[strike], change))
    diffs.sort(key=lambda x: abs(x[3]), reverse=True)

    print(f"\n  Top NetGEX changes per strike (top 8):")
    print(f"  {'Strike':>8s}  {'Before':>14s}  {'After':>14s}  {'Delta':>14s}  Bar")
    for strike, b, a, d in diffs[:8]:
        bar_len = min(int(abs(d) / 1_000_000), 20)
        bar = ("+" if d > 0 else "-") * bar_len
        print(f"  {strike:>8.2f}  {b:>14,.0f}  {a:>14,.0f}  {d:>+14,.0f}  {bar}")

    # Auto interpretation
    print(f"\n  >>> INTERPRETACION <<<")
    interp = []
    # Spot moved significantly?
    if abs(spot_pct) < 0.2:
        interp.append("Spot estable")
    elif spot_pct > 0:
        interp.append(f"Spot SUBE {spot_pct:+.2f}%")
    else:
        interp.append(f"Spot BAJA {spot_pct:+.2f}%")

    # MAX_GEX migration
    mg0 = old_meta.get("max_gex_strike")
    mg1 = new_meta.get("max_gex_strike")
    if mg0 is not None and mg1 is not None and mg0 != mg1:
        if mg1 > mg0:
            interp.append(f"MAX_GEX migra ARRIBA ({mg0:.2f} -> {mg1:.2f}) -- peso institucional sube")
        else:
            interp.append(f"MAX_GEX migra ABAJO ({mg0:.2f} -> {mg1:.2f}) -- peso institucional baja")

    # Wall migration
    cw0 = old_meta.get("call_wall")
    cw1 = new_meta.get("call_wall")
    if cw0 is not None and cw1 is not None and cw0 != cw1:
        if cw1 > cw0:
            interp.append(f"CALL_WALL SUBE {cw0:.2f} -> {cw1:.2f} (techo se aleja, alcista)")
        else:
            interp.append(f"CALL_WALL BAJA {cw0:.2f} -> {cw1:.2f} (techo se acerca, bajista)")
    pw0 = old_meta.get("put_wall")
    pw1 = new_meta.get("put_wall")
    if pw0 is not None and pw1 is not None and pw0 != pw1:
        if pw1 > pw0:
            interp.append(f"PUT_WALL SUBE {pw0:.2f} -> {pw1:.2f} (suelo se eleva, alcista)")
        else:
            interp.append(f"PUT_WALL BAJA {pw0:.2f} -> {pw1:.2f} (suelo cede, bajista)")

    # Asymmetry shift
    if a0 is not None and a1 is not None:
        delta_a = a1 - a0
        if abs(delta_a) >= 0.10:
            if delta_a > 0:
                interp.append(f"Asimetria sube {delta_a:+.2f} (sesgo se vuelve mas alcista)")
            else:
                interp.append(f"Asimetria baja {delta_a:+.2f} (sesgo se vuelve mas bajista)")

    # Regime change
    if old_meta.get("regime") != new_meta.get("regime"):
        interp.append(f"REGIMEN CAMBIA: {old_meta.get('regime')} -> {new_meta.get('regime')}")

    if not interp:
        interp.append("Sin cambios significativos")
    for line in interp:
        print(f"  - {line}")
    print()


# ---------------------------------------------------------------------------
# Process / Main
# ---------------------------------------------------------------------------

def process_ticker(ticker, expiry=None, do_plot=False, persist=True):
    """Full GEX pipeline for a single ticker (Phase 1 + 2 + optional history)."""
    try:
        calls, puts, spot, chosen_exp, _ = fetch_options_data(ticker, expiry)
    except Exception as e:
        print(f"  ERROR [{ticker}]: {e}")
        return None

    exp_date = dt.datetime.strptime(chosen_exp, "%Y-%m-%d").date()
    T = max((exp_date - dt.date.today()).days, 1) / 365.0

    gex_df = calc_gex_per_strike(calls, puts, spot, T)
    levels = identify_levels(gex_df, spot)
    analysis = analyze_levels(gex_df, spot, levels)

    # Data quality guard: yfinance serves OI=0 outside US market hours
    # (pre-market and weekends). Skip persist to avoid contaminating history.
    total_oi = _safe_int(calls["openInterest"].sum()) + _safe_int(puts["openInterest"].sum())
    data_ok = total_oi > 0
    if not data_ok:
        print(f"\n  WARNING [{ticker}]: yfinance returned empty open interest "
              f"(total OI=0).")
        print(f"  Likely cause: US market closed / pre-market window.")
        print(f"  Run again after US open (15:30 UTC ~ 17:30 ES summer) "
              f"or post-close (~22:30 ES) for valid snapshot.")

    print_levels(ticker, spot, levels, chosen_exp, gex_df, analysis)
    print_reading(ticker, spot, levels, analysis)

    if persist and not data_ok:
        print(f"  History persistence SKIPPED (OI=0, would contaminate JSONL).")
    if persist and data_ok:
        append_history(ticker, spot, levels, analysis, chosen_exp, gex_df)
        # Detect patterns AFTER persisting today's record
        history_df = load_history(ticker=ticker, days=10)
        events = detect_patterns(history_df, ticker)
        if events:
            print_patterns(ticker, events)
            log_patterns(ticker, events)

    if do_plot:
        plot_gex(ticker, spot, levels, gex_df, chosen_exp)

    return {"levels": levels, "analysis": analysis}


def main():
    parser = argparse.ArgumentParser(
        description="ORION GEX/OI Overlay -- Gamma Exposure analysis"
    )
    parser.add_argument("--ticker", "-t", type=str, help="Single ticker (e.g. GOOGL)")
    parser.add_argument("--scan", "-s", nargs="+", help="Batch: list of tickers")
    parser.add_argument("--scan-altair", action="store_true",
                        help=f"Scan ALTAIR core+context: {' '.join(ALL_TICKERS)}")
    parser.add_argument("--expiry", "-e", type=str, default=None,
                        help="Specific expiry YYYY-MM-DD (default: nearest >= 7d)")
    parser.add_argument("--plot", "-p", action="store_true",
                        help="Show matplotlib GEX bar chart")
    parser.add_argument("--history", type=str, metavar="TICKER",
                        help="Show last 7 days history table for TICKER")
    parser.add_argument("--patterns", action="store_true",
                        help="Show patterns detected in last 5 days (all tickers)")
    parser.add_argument("--compare", type=str, metavar="TICKER",
                        help="Compare 2 most recent intraday snapshots for TICKER")
    parser.add_argument("--days", type=int, default=None,
                        help="Override day window for --history (default 7) "
                             "or --patterns (default 5)")
    parser.add_argument("--no-persist", action="store_true",
                        help="Disable history append (debugging)")
    args = parser.parse_args()

    # History view (no fetch)
    if args.history:
        days = args.days if args.days else 7
        cmd_history(args.history.upper(), days=days)
        return

    # Patterns view (no fetch)
    if args.patterns:
        days = args.days if args.days else 5
        cmd_patterns(days=days)
        return

    # Compare view (no fetch)
    if args.compare:
        cmd_compare(args.compare.upper())
        return

    # Decide tickers
    if args.scan_altair:
        tickers = ALL_TICKERS
    elif args.scan:
        tickers = [t.upper() for t in args.scan]
    elif args.ticker:
        tickers = [args.ticker.upper()]
    else:
        parser.error("Provide --ticker, --scan, --scan-altair, --history, --patterns or --compare")

    print(f"\nORION GEX -- {dt.datetime.now().strftime('%Y-%m-%d %H:%M')} local")
    print(f"Tickers: {', '.join(tickers)}")

    for tk in tickers:
        process_ticker(
            tk, expiry=args.expiry, do_plot=args.plot,
            persist=not args.no_persist,
        )


if __name__ == "__main__":
    main()
