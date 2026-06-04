"""
ALTAIR Strategy Settings

Trend-following momentum strategy on NDX stocks.
D1 regime filter (CALM_UP) + H1 DTOSC timing entry.
Companion to VEGA (mean-reversion) in the Summer Triangle.

Architecture:
  Layer 1 (D1 Regime): Mom12M + ATR_ratio + Mom63d -> CALM_UP filter
  Layer 2 (H1 Signal): DTOSC bullish reversal from oversold zone
  Layer 3 (Execution): ATR-based SL/TP, risk-based sizing

Stocks: NDX tech leaders with confirmed momentum edge (pre-study).
Data: Dukascopy H1, UTC timezone.
Commission: Darwinex Zero CFD stocks ($0.02/contract, 20% margin).

Reference: Robert Miner "High Probability Trading Strategies" (Figs 2.5-2.6)
"""
import datetime


# =============================================================================
# CAPITAL & ALLOCATION
# =============================================================================
ALTAIR_TOTAL_CAPITAL = 100_000  # USD (backtest default)


# =============================================================================
# BROKER CONFIG (CFD stocks -- Darwinex Zero)
# =============================================================================
ALTAIR_BROKER_CONFIG = {
    'darwinex_zero_stock': {
        'commission_per_contract': 0.02,  # $0.02 per share per order
        'leverage': 5.0,
        'margin_percent': 20.0,
    },
}


# =============================================================================
# STOCK SYMBOLS (for run_backtest.py non-forex detection)
# =============================================================================
STOCK_SYMBOLS = [
    'NVDA', 'AMAT', 'AMD', 'AVGO', 'GOOGL', 'MSFT', 'NFLX',
    'KLAC', 'LRCX', 'MU', 'ASML',
    'CAT', 'V', 'HD', 'JPM', 'AXP', 'UNH', 'GS',
    # SP500 Tier 1-HIGH batch 1 (2026-04-11)
    'LLY', 'LMT', 'PGR', 'STZ', 'DELL', 'AMP', 'CAH',
    'FDX', 'NSC', 'PH', 'EFX', 'MPC', 'VLO',
]


# =============================================================================
# ALTAIR STRATEGY CONFIGS (one per stock)
# =============================================================================

# Shared default params (overridden per stock if needed)
_DEFAULT_PARAMS = {
    # --- DTOSC core (Miner: period=8, smooth_k=5, smooth_d=3, signal=3) ---
    'dtosc_period': 8,
    'dtosc_smooth_k': 5,
    'dtosc_smooth_d': 3,
    'dtosc_signal': 3,
    'dtosc_ob': 75,
    'dtosc_os': 25,

    # --- D1 Regime ---
    'regime_enabled': True,
    'regime_sma_period': 252,       # Mom12M: close > SMA(252d)
    'regime_atr_period': 252,       # SMA window for ATR ratio
    'regime_atr_current_period': 14,  # ATR period for current volatility
    'regime_atr_threshold': 1.0,    # Legacy single threshold (kept for reporting)
    'regime_atr_hyst_lower': 0.95,  # Hysteresis: enter CALM if atr_ratio < lower
    'regime_atr_hyst_upper': 1.05,  # Hysteresis: exit CALM if atr_ratio > upper
    'momentum_63d_period': 63,      # Mom63d sub-filter

    # --- Risk / Exit ---
    'atr_period': 14,               # ATR for SL/TP (H1 bars)
    'sl_atr_mult': 2.0,             # Fallback SL if swing low not available
    'tp_atr_mult': 4.0,             # Take profit = entry + X * ATR_H1 (Phase2+DeepCompare: D)

    # --- V2: Miner Improvements ---
    'use_tr1bh': True,              # Trailing One-Bar High entry
    'tr1bh_timeout': 5,             # Max bars in TRIGGERED state (Phase3+DeepCompare: D)
    'tr1bh_tick': 0.01,             # Tick offset above bar high
    'use_swing_low_sl': True,       # SL at swing low (vs ATR)
    'max_sl_atr_mult': 2.0,         # Max SL width in ATR mult (Phase1: 2.0 wins)

    'max_holding_bars': 120,        # Max hold ~5 trading days (H1)
    'max_entries_per_day': 1,

    # --- Session ---
    'use_time_filter': True,
    'allowed_hours': [14, 15, 16, 17, 18, 19],  # US pre-market + regular
    'use_day_filter': True,
    'allowed_days': [0, 1, 2, 3, 4],  # Mon-Fri

    # --- Sizing ---
    'risk_percent': 0.01,           # 1% risk per trade
    'capital_alloc_pct': 0.20,      # Max 20% equity per position (margin)
    'max_position_pct': 0.30,       # Absolute max position

    # --- Margin ---
    'margin_pct': 20.0,

    # --- Regime scaling ---
    # bars_per_day controls how D1 regime periods are scaled to the feed TF.
    # H1 = 7 bars/day (US stocks 14:30-21:00)
    # 30m = 13 bars/day
    # 15m = 26 bars/day
    # 5m  = 78 bars/day
    # Override per-ticker via _make_config(..., bars_per_day=13)
    'bars_per_day': 7,              # Default: H1 feed

    # --- Debug ---
    'print_signals': False,
    'export_reports': True,
}


def _make_config(ticker, csv_filename, from_date, active=True,
                 universe='ndx', **overrides):
    """Build a single ALTAIR config entry."""
    params = dict(_DEFAULT_PARAMS)
    params.update(overrides)
    return {
        'active': active,
        'universe': universe,
        'strategy_name': 'ALTAIR',
        'asset_name': ticker,
        'data_path': f'data/{csv_filename}',
        'from_date': from_date,
        'to_date': datetime.datetime(2025, 12, 31),
        'starting_cash': 100000.0,
        'broker_config_key': 'darwinex_zero_stock',
        'params': params,
    }


ALTAIR_STRATEGIES_CONFIG = {
    # --- NDX STOCKS (Phase 1-4 optimized, Option D) ---
    'NVDA_ALTAIR': _make_config(
        'NVDA', 'NVDA_1h_8Yea.csv',
        datetime.datetime(2017, 1, 1),
        universe='ndx',
    ),
    'AMAT_ALTAIR': _make_config(
        'AMAT', 'AMAT_1h_8Yea.csv',
        datetime.datetime(2017, 1, 1),
        universe='ndx',
        active=False,  # Shrp 0.17 (min 0.30), 4th semiconductor (no diversification), zigzag equity
    ),
    'AMD_ALTAIR': _make_config(
        'AMD', 'AMD_1h_8Yea.csv',
        datetime.datetime(2017, 1, 1),
        universe='ndx',
    ),
    'AVGO_ALTAIR': _make_config(
        'AVGO', 'AVGO_1h_8Yea.csv',
        datetime.datetime(2017, 1, 1),
        universe='ndx',
    ),
    'GOOGL_ALTAIR': _make_config(
        'GOOGL', 'GOOGL_1h_8Yea.csv',
        datetime.datetime(2017, 1, 1),
        universe='ndx',
    ),
    'MSFT_ALTAIR': _make_config(
        'MSFT', 'MSFT_1h_8Yea.csv',
        datetime.datetime(2017, 1, 1),
        universe='ndx',
    ),
    'NFLX_ALTAIR': _make_config(
        'NFLX', 'NFLX_1h_8Yea.csv',
        datetime.datetime(2017, 1, 1),
        universe='ndx',
        active=False,  # Shrp 0.23 (min 0.30), worstDD 12.9% (portfolio worst), -$12.7K 2021
    ),

    # --- DJ30 STOCKS (diversification study, Section 31-32) ---
    'CAT_ALTAIR': _make_config(
        'CAT', 'CAT_1h_8Yea.csv',
        datetime.datetime(2017, 6, 1),
        universe='dj30',
        max_sl_atr_mult=4.0, dtosc_os=20,
    ),
    'V_ALTAIR': _make_config(
        'V', 'V_1h_8Yea.csv',
        datetime.datetime(2017, 2, 1),
        universe='dj30',
        max_sl_atr_mult=4.0, dtosc_os=20,
    ),
    'HD_ALTAIR': _make_config(
        'HD', 'HD_1h_8Yea.csv',
        datetime.datetime(2017, 2, 1),
        universe='dj30',
        active=False,  # PF 0.42-0.81 all SL/TP combos, DD>20%, structural loser
    ),
    'JPM_ALTAIR': _make_config(
        'JPM', 'JPM_1h_8Yea.csv',
        datetime.datetime(2017, 2, 1),
        universe='dj30',
        max_sl_atr_mult=4.0, dtosc_os=20,
    ),
    'AXP_ALTAIR': _make_config(
        'AXP', 'AXP_1h_8Yea.csv',
        datetime.datetime(2017, 12, 1),
        universe='dj30',
        max_sl_atr_mult=4.0, dtosc_os=20,
    ),
    'UNH_ALTAIR': _make_config(
        'UNH', 'UNH_1h_8Yea.csv',
        datetime.datetime(2017, 12, 1),
        universe='dj30',
        active=False,  # PF 0.65-0.76 all SL/TP combos, PROT_STOP>80%
    ),
    'GS_ALTAIR': _make_config(
        'GS', 'GS_1h_8Yea.csv',
        datetime.datetime(2017, 2, 1),
        universe='dj30',
        max_sl_atr_mult=4.0, dtosc_os=20,
    ),

    # --- FASE D: 15m EXPANSION (2026-04-19) ---
    # GS 15m: 2026-06-04 re-eval (hysteresis ON, bars_per_day=26 = correct 15m
    # scaling). Config A (defaults) beats B: PF 1.56 vs 1.40, 6/6 winning years
    # vs 4/8. Switched B->A per universe sweep (tools/altair_sweep.py).
    'GS_15m_ALTAIR': _make_config(
        'GS', 'GS_15m_8Yea.csv',
        datetime.datetime(2017, 2, 1),
        universe='dj30',
        bars_per_day=26,     # 15m native (was implicitly H1=7, now correct)
        resample_minutes=0,  # native 15m, no resample needed
    ),

    # --- SP500 SCREENING (Section 39, 2026-04-11) ---
    # ALB: rank #4, Config B: PF 2.15, WR 54.5%, +$7,609, 4/5yr+
    'ALB_ALTAIR': _make_config(
        'ALB', 'ALB_1h_8Yea.csv',
        datetime.datetime(2017, 1, 1),
        universe='sp500',
        max_sl_atr_mult=4.0, dtosc_os=20,  # Config B
    ),
    # WDC: rank #11, Config A: PF 1.88, WR 44.0%, +$12,058, 5/7yr+
    'WDC_ALTAIR': _make_config(
        'WDC', 'WDC_1h_8Yea.csv',
        datetime.datetime(2017, 1, 1),
        universe='sp500',
        # Config A (default): PF 1.88, best for WDC
    ),

    # --- SP500 TIER 1-HIGH BATCH 1 (Section 39, 2026-04-11) ---
    # A/B tested: Config A (NDX) vs Config B (DJ30). Best config per stock.
    # Config B wins 5 vs 2 -- SP500 behaves like DJ30 blue-chips.
    'NSC_ALTAIR': _make_config(
        'NSC', 'NSC_1h_8Yea.csv',
        datetime.datetime(2018, 3, 1),
        universe='sp500',
        max_sl_atr_mult=4.0, dtosc_os=20,  # Config B: PF 2.33, 6/6yr+
    ),
    'CAH_ALTAIR': _make_config(
        'CAH', 'CAH_1h_8Yea.csv',
        datetime.datetime(2018, 3, 1),
        universe='sp500',
        # Config A (default): PF 1.53, 4/5yr+
    ),
    'FDX_ALTAIR': _make_config(
        'FDX', 'FDX_1h_8Yea.csv',
        datetime.datetime(2017, 12, 1),
        universe='sp500',
        max_sl_atr_mult=4.0, dtosc_os=20,  # Config B: PF 1.46, 3/4yr+
    ),
    'VLO_ALTAIR': _make_config(
        'VLO', 'VLO_1h_8Yea.csv',
        datetime.datetime(2017, 12, 1),
        universe='sp500',
        max_sl_atr_mult=4.0, dtosc_os=20,  # Config B: PF 1.40, 3/6yr+
    ),
    'EFX_ALTAIR': _make_config(
        'EFX', 'EFX_1h_8Yea.csv',
        datetime.datetime(2017, 12, 1),
        universe='sp500',
        max_sl_atr_mult=4.0, dtosc_os=20,  # Config B: PF 1.17, 2/5yr+
    ),
    'MPC_ALTAIR': _make_config(
        'MPC', 'MPC_1h_8Yea.csv',
        datetime.datetime(2018, 3, 1),
        universe='sp500',
        max_sl_atr_mult=4.0, dtosc_os=20,  # Config B: PF 1.12, 4/6yr+
    ),
    'PGR_ALTAIR': _make_config(
        'PGR', 'PGR_1h_8Yea.csv',
        datetime.datetime(2018, 3, 1),
        universe='sp500',
        # Config A (default): PF 1.01, borderline. DD 17% alto.
    ),
    # --- SP500 BATCH 1 LOSERS (structural: low H1 volatility, <2 trades/yr) ---
    'LLY_ALTAIR': _make_config(
        'LLY', 'LLY_1h_8Yea.csv',
        datetime.datetime(2017, 12, 1),
        universe='sp500',
        active=False,  # PF 0.46/0.20 (A/B). 13 trades in 8yr. Same as HD/UNH: pharma too stable for DTOSC pullback
    ),
    'LMT_ALTAIR': _make_config(
        'LMT', 'LMT_1h_8Yea.csv',
        datetime.datetime(2017, 6, 1),
        universe='sp500',
        active=False,  # PF 0.56/0.77 (A/B). Defense sector: low vol, sparse entries
    ),
    'PH_ALTAIR': _make_config(
        'PH', 'PH_1h_8Yea.csv',
        datetime.datetime(2018, 3, 1),
        universe='sp500',
        active=False,  # PF 0.71/0.65 (A/B). Industrial: pullbacks = regime changes, not dips
    ),
    'STZ_ALTAIR': _make_config(
        'STZ', 'STZ_1h_8Yea.csv',
        datetime.datetime(2018, 3, 1),
        universe='sp500',
        active=False,  # PF 0.74/0.68 (A/B). Consumer staples: low momentum recurrence
    ),
    'AMP_ALTAIR': _make_config(
        'AMP', 'AMP_1h_8Yea.csv',
        datetime.datetime(2018, 3, 1),
        universe='sp500',
        active=False,  # PF 0.90/0.96 (A/B). Financial services: close but never profitable
    ),

    # --- FASE E: LIVE-REAL CANDIDATE PORTFOLIO (Darwinex Zero, 2026-06-04) ---
    # DISTINCT from live-demo (FOREX.comGLOBAL). This is the target portfolio for
    # the real-money Darwinex Zero account (CFD stocks, $0.02/share, 5x leverage).
    # Universe re-evaluation via tools/altair_sweep.py (regime hysteresis ON,
    # native 15m, bars_per_day=26). Selection criterion (Ivan): BOTH presets
    # (A & B) profitable = parameter-robust edge, weighting winning-years and
    # recent-year strength over the 8-year aggregate PF.
    #
    # FULL LIVE-REAL PORTFOLIO = proven core + Tier 1 + Tier 2 (see context/
    # CONTEXT_LIVE.md "ALTAIR Live-Real" for the rationale and roadmap):
    #   CORE (reuse existing configs above, already live-demo validated):
    #     NVDA_ALTAIR (15m A 2.13), GOOGL_ALTAIR (15m A 1.64),
    #     GS_15m_ALTAIR (15m A 1.56), JPM_ALTAIR (30m B 1.62)
    #   TIER 1 (new, native 15m, both presets win, top winning-years/Sharpe):
    #     ETN, TDG, HII, NOC  -> defined below
    #   TIER 2 (support diversifiers, native 15m, both presets win, lower edge
    #           or single-sector overlap): MSCI, MPC, PGR, GRMN, COHR, AVGO
    #           -> defined below
    # All Tier 1/2 use Config A (defaults: dtosc_os=25, max_sl_atr_mult=2.0).
    # active=False until live-real wiring (do NOT enable on the demo bot).
    #
    # --- Tier 1: core diversifiers (industrial / defense) ---
    'ETN_ALTAIR': _make_config(
        'ETN', 'ETN_15m_8Yea.csv',
        datetime.datetime(2017, 1, 1),
        universe='sp500',
        bars_per_day=26, resample_minutes=0,
        active=False,  # 15m A PF 1.67 / B 1.64, 8/8 winning years, Sharpe 0.96
    ),
    'TDG_ALTAIR': _make_config(
        'TDG', 'TDG_15m_8Yea.csv',
        datetime.datetime(2017, 1, 1),
        universe='sp500',
        bars_per_day=26, resample_minutes=0,
        active=False,  # 15m A PF 1.85 / B 1.20, 6/7 winning years, Sharpe 1.01 (best)
    ),
    'HII_ALTAIR': _make_config(
        'HII', 'HII_15m_8Yea.csv',
        datetime.datetime(2017, 1, 1),
        universe='sp500',
        bars_per_day=26, resample_minutes=0,
        active=False,  # 15m A PF 1.67 / B 1.54, 7/8 winning years
    ),
    'NOC_ALTAIR': _make_config(
        'NOC', 'NOC_15m_8Yea.csv',
        datetime.datetime(2017, 1, 1),
        universe='sp500',
        bars_per_day=26, resample_minutes=0,
        active=False,  # 15m A PF 1.78 / B 1.27, 6/7 winning years
    ),
    # --- Tier 2: support diversifiers (financials / energy / insurance /
    #     consumer-tech / semis). Lower or sector-overlapping edge; enable
    #     selectively for correlation balance, not all at once. ---
    'MSCI_ALTAIR': _make_config(
        'MSCI', 'MSCI_15m_8Yea.csv',
        datetime.datetime(2017, 1, 1),
        universe='sp500',
        bars_per_day=26, resample_minutes=0,
        active=False,  # 15m A PF 1.74 / B 1.39 (financial data)
    ),
    'MPC_15m_ALTAIR': _make_config(
        'MPC', 'MPC_15m_8Yea.csv',
        datetime.datetime(2018, 3, 1),
        universe='sp500',
        bars_per_day=26, resample_minutes=0,
        active=False,  # 15m A PF 1.45 / B 1.32 (energy/refining)
    ),
    'PGR_15m_ALTAIR': _make_config(
        'PGR', 'PGR_15m_8Yea.csv',
        datetime.datetime(2018, 3, 1),
        universe='sp500',
        bars_per_day=26, resample_minutes=0,
        active=False,  # 15m A PF 1.43 / B 1.32 (insurance)
    ),
    'GRMN_ALTAIR': _make_config(
        'GRMN', 'GRMN_15m_8Yea.csv',
        datetime.datetime(2017, 1, 1),
        universe='sp500',
        bars_per_day=26, resample_minutes=0,
        active=False,  # 15m A PF 1.52 / B 1.27 (consumer tech)
    ),
    'COHR_ALTAIR': _make_config(
        'COHR', 'COHR_15m_8Yea.csv',
        datetime.datetime(2017, 1, 1),
        universe='sp500',
        bars_per_day=26, resample_minutes=0,
        active=False,  # 15m A PF 1.94 / B 1.57 (photonics/semis, high but volatile)
    ),
    'AVGO_15m_ALTAIR': _make_config(
        'AVGO', 'AVGO_15m_8Yea.csv',
        datetime.datetime(2017, 1, 1),
        universe='sp500',
        bars_per_day=26, resample_minutes=0,
        active=False,  # 15m A PF 1.43 / B 1.45 (semis, overlaps NVDA-tech)
    ),
    # --- Tier 2b: resample 5m->15m candidates (2026-06-04 5m sweep) ---
    # WARNING: source CSV is 5m, needs resample_minutes=15. The standard
    # run_backtest does NOT consume resample_minutes (only altair_sweep.py does
    # the in-memory resample). PF/year figures below come from the SWEEP tool,
    # NOT reproducible by a direct run_backtest until the engine consumes the
    # resample param. Kept active=False, documented for live-real Darwinex Zero.
    # Only the 3 robust survivors of the 5m sweep are kept; rest discarded
    # (Ivan 2026-06-04: numbers not convincing). Best preset per ticker.
    'MCO_15m_ALTAIR': _make_config(
        'MCO', 'MCO_5m_8Yea.csv',
        datetime.datetime(2018, 1, 1),
        universe='sp500',
        bars_per_day=26, resample_minutes=15,
        active=False,  # 5m->15m Config A PF 1.57, Sharpe 0.88, DD 5.9%, 7/7 yrs (best 5m pick)
    ),
    'HCA_15m_ALTAIR': _make_config(
        'HCA', 'HCA_5m_8Yea.csv',
        datetime.datetime(2018, 1, 1),
        universe='sp500',
        bars_per_day=26, resample_minutes=15,
        max_sl_atr_mult=4.0, dtosc_os=20,  # Config B
        active=False,  # 5m->15m Config B PF 1.55, Sharpe 0.71, DD 13.4%, 5/7 yrs (A also wins 1.50)
    ),
    'WST_15m_ALTAIR': _make_config(
        'WST', 'WST_5m_8Yea.csv',
        datetime.datetime(2018, 1, 1),
        universe='sp500',
        bars_per_day=26, resample_minutes=15,
        max_sl_atr_mult=4.0, dtosc_os=20,  # Config B
        active=False,  # 5m->15m Config B PF 1.58, Sharpe 0.73, DD 4.6% (lowest), 4/6 yrs (A also wins 1.34)
    ),
}
