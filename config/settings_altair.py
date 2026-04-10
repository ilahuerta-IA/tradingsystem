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
    'regime_atr_threshold': 1.0,    # CALM if ATR_ratio < 1.0
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
    'bars_per_day': 7,              # H1 bars per trading day (US stocks)

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
}
