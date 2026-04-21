#!/usr/bin/env python3
"""
ORION GEX/OI Overlay -- Gamma Exposure analysis for manual trading.

Downloads options chain via yfinance, calculates GEX per strike,
identifies key institutional levels (PUT_WALL, CALL_WALL, GAMMA_FLIP),
and outputs results to console + optional matplotlib chart.

Usage:
    python tools/orion_gex.py --ticker GOOGL
    python tools/orion_gex.py --ticker GOOGL --plot
    python tools/orion_gex.py --scan GOOGL JPM GS NVDA --plot
    python tools/orion_gex.py --ticker SPY --expiry 2026-05-15 --plot

Levels are also saved to analysis/gex_levels_{ticker}_{date}.csv
for external consumption (e.g. MQL5 script for MT5 chart lines).

Dependencies: yfinance, scipy, numpy, matplotlib, mplfinance
"""

import argparse
import datetime as dt
import os
import sys

import numpy as np
from scipy.stats import norm

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

def calc_gex_per_strike(calls_df, puts_df, spot, T, r=0.045):
    """Calculate net Gamma Exposure per strike.

    GEX_call = +OI * gamma * 100 * spot^2 * 0.01
    GEX_put  = -OI * gamma * 100 * spot^2 * 0.01  (MMs short puts -> negative)

    Returns sorted DataFrame with columns:
        strike, call_oi, put_oi, call_gamma, put_gamma,
        call_gex, put_gex, net_gex
    """
    import pandas as pd

    strikes = sorted(
        set(calls_df["strike"].tolist()) | set(puts_df["strike"].tolist())
    )

    rows = []
    for K in strikes:
        c_row = calls_df[calls_df["strike"] == K]
        p_row = puts_df[puts_df["strike"] == K]

        c_oi = int(c_row["openInterest"].iloc[0]) if len(c_row) else 0
        p_oi = int(p_row["openInterest"].iloc[0]) if len(p_row) else 0

        # Use yfinance implied vol when available, else skip
        c_iv = float(c_row["impliedVolatility"].iloc[0]) if len(c_row) else 0.0
        p_iv = float(p_row["impliedVolatility"].iloc[0]) if len(p_row) else 0.0

        c_gamma = bs_gamma(spot, K, T, r, c_iv) if c_iv > 0 else 0.0
        p_gamma = bs_gamma(spot, K, T, r, p_iv) if p_iv > 0 else 0.0

        multiplier = 100 * spot ** 2 * 0.01

        c_gex = c_oi * c_gamma * multiplier
        p_gex = -p_oi * p_gamma * multiplier  # MMs short puts

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
    """Identify key GEX/OI levels.

    Returns dict with:
        PUT_WALL   -- strike with largest absolute put GEX below spot
        CALL_WALL  -- strike with largest call GEX above spot
        GAMMA_FLIP -- strike nearest to where net_gex crosses zero
        MAX_GEX    -- strike with highest absolute net_gex
        MAX_CALL_OI -- strike with highest call OI
        MAX_PUT_OI  -- strike with highest put OI
    """
    levels = {}

    # PUT_WALL: largest |put_gex| at or below spot
    below = gex_df[gex_df["strike"] <= spot].copy()
    if len(below):
        idx = below["put_gex"].abs().idxmax()
        levels["PUT_WALL"] = float(below.loc[idx, "strike"])

    # CALL_WALL: largest call_gex at or above spot
    above = gex_df[gex_df["strike"] >= spot].copy()
    if len(above):
        idx = above["call_gex"].idxmax()
        levels["CALL_WALL"] = float(above.loc[idx, "strike"])

    # GAMMA_FLIP: where net_gex crosses zero (nearest to spot)
    df_sorted = gex_df.sort_values("strike").reset_index(drop=True)
    sign_changes = []
    for i in range(1, len(df_sorted)):
        prev_gex = df_sorted.loc[i - 1, "net_gex"]
        curr_gex = df_sorted.loc[i, "net_gex"]
        if prev_gex * curr_gex < 0:
            # Linear interpolation
            s0 = df_sorted.loc[i - 1, "strike"]
            s1 = df_sorted.loc[i, "strike"]
            g0 = prev_gex
            g1 = curr_gex
            flip = s0 + (s1 - s0) * (-g0) / (g1 - g0)
            sign_changes.append(flip)
    if sign_changes:
        levels["GAMMA_FLIP"] = float(
            min(sign_changes, key=lambda x: abs(x - spot))
        )

    # MAX absolute net GEX strike
    idx = gex_df["net_gex"].abs().idxmax()
    levels["MAX_GEX"] = float(gex_df.loc[idx, "strike"])

    # MAX OI strikes
    if gex_df["call_oi"].sum() > 0:
        idx = gex_df["call_oi"].idxmax()
        levels["MAX_CALL_OI"] = float(gex_df.loc[idx, "strike"])
    if gex_df["put_oi"].sum() > 0:
        idx = gex_df["put_oi"].idxmax()
        levels["MAX_PUT_OI"] = float(gex_df.loc[idx, "strike"])

    return levels


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def fetch_options_data(ticker_str, expiry=None):
    """Fetch options chain and spot from yfinance.

    Args:
        ticker_str: e.g. 'GOOGL'
        expiry: specific expiry date string 'YYYY-MM-DD' or None (nearest).

    Returns:
        (calls_df, puts_df, spot, expiry_date_str, all_expiries)
    """
    import yfinance as yf

    tk = yf.Ticker(ticker_str)
    expiries = tk.options
    if not expiries:
        raise ValueError(f"No options expiries found for {ticker_str}")

    if expiry is None:
        # Pick nearest expiry that is >= 7 days out (skip weeklies expiring today)
        today = dt.date.today()
        chosen = None
        for exp in expiries:
            exp_date = dt.datetime.strptime(exp, "%Y-%m-%d").date()
            if (exp_date - today).days >= 7:
                chosen = exp
                break
        if chosen is None:
            chosen = expiries[-1]  # fallback to last available
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
# Output
# ---------------------------------------------------------------------------

def print_levels(ticker, spot, levels, expiry, gex_df):
    """Pretty-print key levels to console."""
    print(f"\n{'='*60}")
    print(f"  ORION GEX -- {ticker}  |  Spot: {spot:.2f}  |  Expiry: {expiry}")
    print(f"{'='*60}")

    order = [
        "CALL_WALL", "MAX_CALL_OI", "GAMMA_FLIP",
        "MAX_GEX", "PUT_WALL", "MAX_PUT_OI",
    ]
    for key in order:
        if key in levels:
            val = levels[key]
            dist = ((val / spot) - 1) * 100
            tag = ""
            if val > spot:
                tag = "(above)"
            elif val < spot:
                tag = "(below)"
            else:
                tag = "(at spot)"
            print(f"  {key:<14s}  {val:>10.2f}  {dist:>+6.1f}%  {tag}")

    # Top 5 net GEX strikes
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
    print()


def save_levels_csv(ticker, spot, levels, expiry, gex_df):
    """Save levels to analysis/ folder."""
    import pandas as pd

    out_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "analysis"
    )
    os.makedirs(out_dir, exist_ok=True)

    today = dt.date.today().strftime("%Y%m%d")
    fname = f"gex_levels_{ticker}_{today}.csv"
    path = os.path.join(out_dir, fname)

    rows = []
    for name, price in levels.items():
        rows.append({"ticker": ticker, "level": name, "price": price,
                      "spot": spot, "expiry": expiry,
                      "date": dt.date.today().isoformat()})
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"  Levels saved: {path}")

    # Also save full GEX profile
    gex_path = os.path.join(out_dir, f"gex_profile_{ticker}_{today}.csv")
    gex_df.to_csv(gex_path, index=False)
    return path


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def plot_gex(ticker, spot, levels, gex_df, expiry):
    """Bar chart of net GEX per strike with key levels annotated."""
    import matplotlib.pyplot as plt

    # Filter to strikes within +/-15% of spot for readability
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
    ax.bar(df_plot["strike"], df_plot["net_gex"], width=(hi - lo) / len(df_plot) * 0.7,
           color=colors, alpha=0.7, edgecolor="none")

    # Spot line
    ax.axvline(spot, color="blue", linewidth=1.5, linestyle="--", label=f"Spot {spot:.2f}")

    # Level lines
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

    ax.set_title(f"ORION GEX -- {ticker} | Expiry {expiry} | Spot {spot:.2f}",
                 fontsize=13, fontweight="bold")
    ax.set_xlabel("Strike")
    ax.set_ylabel("Net Gamma Exposure ($)")
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    ax.axhline(0, color="black", linewidth=0.5)

    plt.tight_layout()
    plt.show()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def process_ticker(ticker, expiry=None, do_plot=False):
    """Full GEX pipeline for a single ticker."""
    try:
        calls, puts, spot, chosen_exp, all_exp = fetch_options_data(ticker, expiry)
    except Exception as e:
        print(f"  ERROR [{ticker}]: {e}")
        return None

    # Time to expiry in years
    exp_date = dt.datetime.strptime(chosen_exp, "%Y-%m-%d").date()
    T = max((exp_date - dt.date.today()).days, 1) / 365.0

    gex_df = calc_gex_per_strike(calls, puts, spot, T)
    levels = identify_levels(gex_df, spot)

    print_levels(ticker, spot, levels, chosen_exp, gex_df)
    save_levels_csv(ticker, spot, levels, chosen_exp, gex_df)

    if do_plot:
        plot_gex(ticker, spot, levels, gex_df, chosen_exp)

    return levels


def main():
    parser = argparse.ArgumentParser(
        description="ORION GEX/OI Overlay -- Gamma Exposure analysis"
    )
    parser.add_argument("--ticker", "-t", type=str, help="Single ticker (e.g. GOOGL)")
    parser.add_argument("--scan", "-s", nargs="+", help="Batch: list of tickers")
    parser.add_argument("--expiry", "-e", type=str, default=None,
                        help="Specific expiry YYYY-MM-DD (default: nearest >= 7d)")
    parser.add_argument("--plot", "-p", action="store_true",
                        help="Show matplotlib GEX bar chart")
    args = parser.parse_args()

    if not args.ticker and not args.scan:
        parser.error("Provide --ticker or --scan")

    tickers = args.scan if args.scan else [args.ticker]

    print(f"\nORION GEX -- {dt.datetime.now().strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"Tickers: {', '.join(tickers)}")

    for tk in tickers:
        process_ticker(tk.upper(), expiry=args.expiry, do_plot=args.plot)


if __name__ == "__main__":
    main()
