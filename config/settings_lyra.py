"""
LYRA Strategy Settings

Short-selling strategy on index CFDs during VOLATILE_UP regime.
D1 regime filter (VOLATILE_UP) + H1 DTOSC bearish timing entry.
Bear-market complement to ALTAIR.

Architecture:
  Layer 1 (D1 Regime): Mom12M + ATR_ratio + Mom63d -> VOLATILE_UP filter
  Layer 2 (H1 Signal): DTOSC bearish reversal from overbought zone
  Layer 3 (Execution): ATR-based SL/TP, Tr-1BL confirmation, risk-based sizing

Indices: NDX, SP500, UK100 (confirmed positive edge in prestudy).
Data: Dukascopy H1, UTC timezone.
Commission: Darwinex Zero CFD indices (margin-based, 5%).
"""
import datetime


# =============================================================================
# BROKER CONFIG (CFD indices -- Darwinex Zero)
# =============================================================================
LYRA_BROKER_CONFIG = {
    'darwinex_zero_cfd_ndx': {
        'commission_per_contract': 0.675,
        'leverage': 20.0,
        'margin_percent': 5.0,
    },
    'darwinex_zero_cfd_sp500': {
        'commission_per_contract': 0.0275,
        'leverage': 20.0,
        'margin_percent': 5.0,
    },
    'darwinex_zero_cfd_uk100': {
        'commission_per_contract': 0.98,
        'leverage': 20.0,
        'margin_percent': 5.0,
    },
    'darwinex_zero_cfd_ni225': {
        'commission_per_contract': 0.0123,
        'leverage': 20.0,
        'margin_percent': 5.0,
        'is_jpy_index': True,
        'jpy_rate': 150.0,
    },
}


# =============================================================================
# DEFAULT PARAMS
# =============================================================================
_DEFAULT_PARAMS = {
    # --- DTOSC ---
    'dtosc_period': 8,
    'dtosc_smooth_k': 5,
    'dtosc_smooth_d': 3,
    'dtosc_signal': 3,
    'dtosc_ob': 75,
    'dtosc_os': 25,

    # --- D1 Regime ---
    'regime_enabled': True,
    'regime_sma_period': 252,
    'regime_atr_period': 252,
    'regime_atr_current_period': 14,
    'regime_atr_threshold': 1.0,
    'momentum_63d_period': 63,

    # --- Allowed regimes for entry ---
    'allowed_regimes': (1,),    # 1 = VOLATILE_UP only

    # --- Resample (5m CSV -> H1 bars) ---
    'base_timeframe_minutes': 60,

    # --- Risk / Exit ---
    'atr_period': 14,
    'sl_atr_mult': 2.0,
    'tp_atr_mult': 3.0,
    'max_sl_atr_mult': 2.0,

    # --- Entry confirmation ---
    'use_tr1bl': True,
    'tr1bl_timeout': 5,
    'tr1bl_tick': 0.01,
    'use_swing_high_sl': True,

    'max_holding_bars': 35,     # ~5 trading days
    'max_entries_per_day': 1,

    # --- ATR entry filter ---
    'min_atr_entry': 0.0,       # 0 = disabled
    'max_atr_entry': 0.0,       # 0 = disabled

    # --- Session filters ---
    'use_time_filter': True,
    'allowed_hours': [14, 15, 16, 17, 18, 19],  # US session default
    'use_day_filter': True,
    'allowed_days': [0, 1, 2, 3, 4],   # Mon-Fri

    # --- Regime exit ---
    'exit_on_calm_up': True,

    # --- Sizing ---
    'risk_percent': 0.01,
    'capital_alloc_pct': 0.20,
    'max_position_pct': 0.30,

    # --- Margin ---
    'margin_pct': 5.0,

    # --- Debug ---
    'print_signals': False,
    'export_reports': True,

    # --- Plot ---
    'plot_entry_exit_lines': False,
}


# =============================================================================
# INDEX CONFIGS
# =============================================================================

LYRA_STRATEGIES_CONFIG = {

    # --- NDX: best prestudy candidate (PF 1.18, +22.94%) ---
    'NDX_LYRA': {
        'active': True,
        'strategy_name': 'LYRA',
        'asset_name': 'NDX',
        'data_path': 'data/NDX_5m_15Yea.csv',
        'from_date': datetime.datetime(2017, 1, 1),
        'to_date': datetime.datetime(2025, 12, 31),
        'starting_cash': 100_000.0,
        'broker_config_key': 'darwinex_zero_cfd_ndx',
        'params': {
            **_DEFAULT_PARAMS,
            'bars_per_day': 7,
            'allowed_hours': [14, 15, 16, 17, 18, 19],
        },
    },

    # --- SP500: modest edge (PF 1.12, +10.60%) ---
    'SP500_LYRA': {
        'active': True,
        'strategy_name': 'LYRA',
        'asset_name': 'SP500',
        'data_path': 'data/SP500_5m_15Yea.csv',
        'from_date': datetime.datetime(2017, 1, 1),
        'to_date': datetime.datetime(2025, 12, 31),
        'starting_cash': 100_000.0,
        'run_plot': True,
        'broker_config_key': 'darwinex_zero_cfd_sp500',
        'params': {
            **_DEFAULT_PARAMS,
            'bars_per_day': 7,
            'allowed_hours': [14, 15, 16, 17, 18, 19],
            'plot_entry_exit_lines': True,
        },
    },

    # --- UK100: surprise (PF 1.23, WR 46.4%, +12.65%) ---
    'UK100_LYRA': {
        'active': True,
        'strategy_name': 'LYRA',
        'asset_name': 'UK100',
        'data_path': 'data/UK100_5m_15Yea.csv',
        'from_date': datetime.datetime(2017, 1, 1),
        'to_date': datetime.datetime(2025, 12, 31),
        'starting_cash': 100_000.0,
        'broker_config_key': 'darwinex_zero_cfd_uk100',
        'params': {
            **_DEFAULT_PARAMS,
            'bars_per_day': 9,
            'allowed_hours': [8, 9, 10, 11, 12, 13, 14, 15, 16],
        },
    },

    # --- NI225: marginal (PF 1.08, +9.77%) ---
    'NI225_LYRA': {
        'active': False,
        'strategy_name': 'LYRA',
        'asset_name': 'NI225',
        'data_path': 'data/NI225_5m_15Yea.csv',
        'from_date': datetime.datetime(2017, 1, 1),
        'to_date': datetime.datetime(2025, 12, 31),
        'starting_cash': 100_000.0,
        'broker_config_key': 'darwinex_zero_cfd_ni225',
        'params': {
            **_DEFAULT_PARAMS,
            'bars_per_day': 7,
            'allowed_hours': [1, 2, 3, 4, 5, 6, 7],
        },
    },
}
