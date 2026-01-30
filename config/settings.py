"""
Central configuration for all strategies and assets.
"""
import datetime

STRATEGIES_CONFIG = {
    'EURJPY_PRO': {
        'active': True,  # Set to False to skip this config when running
        'strategy_name': 'SunsetOgle',
        'asset_name': 'EURJPY',
        'data_path': 'data/EURJPY_5m_5Yea.csv',
        
        'from_date': datetime.datetime(2020, 1, 1),
        'to_date': datetime.datetime(2025, 12, 1),
        
        'starting_cash': 100000.0,
        
        'run_plot': True,
        'generate_report': True,
        'save_log': True,
        'debug_mode': False,
        
        'params': {
            # EMA settings
            'ema_fast_length': 18,
            'ema_medium_length': 18,
            'ema_slow_length': 24,
            'ema_confirm_length': 1,
            'ema_filter_price_length': 70,
            
            # ATR settings
            'atr_length': 10,
            'atr_min': 0.040,
            'atr_max': 0.090,
            
            # Angle Filter
            'use_angle_filter': True,
            'angle_min': 45.0,
            'angle_max': 95.0,
            'angle_scale': 100.0,
            
            # SL/TP multipliers
            'sl_mult': 3.5,
            'tp_mult': 15.0,
            
            # Pullback settings
            'pullback_candles': 2,
            'window_periods': 2,
            'price_offset_mult': 0.01,
            
            # Time filter
            'use_time_filter': True,
            'allowed_hours': [5, 6, 7, 8, 9, 12, 13, 15, 16, 17],
            
            # SL pips filter
            'use_sl_pips_filter': False,
            'sl_pips_min': 20.0,
            'sl_pips_max': 50.0,
            
            # Risk management
            'risk_percent': 0.01,
            'lot_size': 100000,
            
            # JPY pair settings
            'jpy_rate': 150.0,
            'pip_value': 0.01,
            
            # Debug
            'print_signals': False,
        }
    },

    'EURUSD_PRO': {
        'active': True,  # Set to False to skip this config when running
        'strategy_name': 'SunsetOgle',
        'asset_name': 'EURUSD',
        'data_path': 'data/EURUSD_5m_5Yea.csv',
        
        'from_date': datetime.datetime(2020, 1, 1),
        'to_date': datetime.datetime(2025, 12, 1),
        
        'starting_cash': 100000.0,
        
        'run_plot': False,
        'generate_report': True,
        'save_log': True,
        'debug_mode': False,
        
        'params': {
            # EMA settings - EXACT from original sunrise_ogle_eurusd_pro.py
            'ema_fast_length': 24,
            'ema_medium_length': 24,
            'ema_slow_length': 24,
            'ema_confirm_length': 1,
            'ema_filter_price_length': 60,
            
            # ATR settings - EXACT from original
            'atr_length': 10,
            'atr_min': 0.00020,
            'atr_max': 0.00040,
            
            # Angle Filter - DISABLED for EURUSD (original has no angle filter)
            'use_angle_filter': False,
            'angle_min': 20.0,
            'angle_max': 85.0,
            'angle_scale': 10000.0,
            
            # SL/TP multipliers - EXACT from original
            'sl_mult': 3.0,
            'tp_mult': 15.0,
            
            # Pullback settings - EXACT from original
            'pullback_candles': 2,
            'window_periods': 1,
            'price_offset_mult': 0.01,
            
            # Time filter - EXACT from original (22:00-08:00 UTC)
            'use_time_filter': True,
            'allowed_hours': [22, 23, 0, 1, 2, 3, 4, 5, 6, 7, 8],
            
            # SL pips filter - DISABLED
            'use_sl_pips_filter': False,
            'sl_pips_min': 9.0,
            'sl_pips_max': 21.0,
            
            # Risk management - EXACT from original
            'risk_percent': 0.01,
            'lot_size': 100000,
            
            # Standard pair settings
            'jpy_rate': 150.0,
            'pip_value': 0.0001,
            
            # Debug
            'print_signals': False,
        }
    },

    'USDCAD_PRO': {
        'active': True,  # Set to False to skip this config when running
        'strategy_name': 'SunsetOgle',
        'asset_name': 'USDCAD',
        'data_path': 'data/USDCAD_5m_5Yea.csv',
        
        'from_date': datetime.datetime(2020, 1, 1),
        'to_date': datetime.datetime(2025, 12, 1),
        
        'starting_cash': 100000.0,
        
        'run_plot': True,
        'generate_report': True,
        'save_log': True,
        'debug_mode': False,
        
        'params': {
            # EMA settings 
            'ema_fast_length': 24,
            'ema_medium_length': 30,
            'ema_slow_length': 36,
            'ema_confirm_length': 1,
            'ema_filter_price_length': 40,
            
            # ATR settings 
            'atr_length': 10,
            'atr_min': -1.00020,
            'atr_max': 1.00040,
            
            # Angle Filter 
            'use_angle_filter': True,
            'angle_min': 45.0,
            'angle_max': 75.0,
            'angle_scale': 10000.0,
            
            # SL/TP multipliers 
            'sl_mult': 3.0,
            'tp_mult': 15.0,
            
            # Pullback settings
            'pullback_candles': 2,
            'window_periods': 1,
            'price_offset_mult': 0.01,
            
            # Time filter - EXACT from original (18:00-12:00 UTC)
            'use_time_filter': True,
            'allowed_hours': [18, 19, 20, 21, 22, 23, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
            
            # SL pips filter - DISABLED
            'use_sl_pips_filter': False,
            'sl_pips_min': 9.0,
            'sl_pips_max': 18.0,
            
            # Risk management - EXACT from original
            'risk_percent': 0.01,
            'lot_size': 100000,
            
            # Standard pair settings
            'jpy_rate': 150.0,
            'pip_value': 0.0001,
            
            # Debug
            'print_signals': False,
        }
    },

    'USDCHF_PRO': {
        'active': True,  # Set to False to skip this config when running
        'strategy_name': 'SunsetOgle',
        'asset_name': 'USDCHF',
        'data_path': 'data/USDCHF_5m_5Yea.csv',
        
        'from_date': datetime.datetime(2020, 7, 1),
        'to_date': datetime.datetime(2025, 7, 1),
        
        'starting_cash': 100000.0,
        
        'run_plot': True,
        'generate_report': True,
        'save_log': True,
        'debug_mode': False,
        
        'params': {
            # EMA settings 
            'ema_fast_length': 24,
            'ema_medium_length': 30,
            'ema_slow_length': 36,
            'ema_confirm_length': 1,
            'ema_filter_price_length': 40,
            
            # ATR settings 
            'atr_length': 10,
            'atr_min': 0.0003,
            'atr_max': 0.0009,
            
            # Angle Filter 
            'use_angle_filter': False,
            'angle_min': 45.0,
            'angle_max': 75.0,
            'angle_scale': 10000.0,
            
            # SL/TP multipliers 
            'sl_mult': 2.5,
            'tp_mult': 10.0,
            
            # Pullback settings
            'pullback_candles': 2,
            'window_periods': 2,
            'price_offset_mult': 0.01,
            
            # Time filter 
            'use_time_filter': True,
            'allowed_hours': [3, 6, 7, 9, 10, 11, 12, 13, 17, 20],
            
            # SL pips filter - DISABLED
            'use_sl_pips_filter': False,
            'sl_pips_min': 7.0,
            'sl_pips_max': 21.0,
            
            # Risk management
            'risk_percent': 0.01,
            'lot_size': 100000,
            
            # Standard pair settings
            'jpy_rate': 150.0,
            'pip_value': 0.0001,
            
            # Debug
            'print_signals': False,
        }
    },

    'USDJPY_PRO': {
        'active': True,  # Set to False to skip this config when running
        'strategy_name': 'SunsetOgle',
        'asset_name': 'USDJPY',
        'data_path': 'data/USDJPY_5m_5Yea.csv',
        
        'from_date': datetime.datetime(2020, 1, 1),
        'to_date': datetime.datetime(2025, 12, 1),
        
        'starting_cash': 100000.0,
        
        'run_plot': True,
        'generate_report': True,
        'save_log': True,
        'debug_mode': False,
        
        'params': {
            # EMA settings
            'ema_fast_length': 12,
            'ema_medium_length': 24,
            'ema_slow_length': 24,
            'ema_confirm_length': 1,
            'ema_filter_price_length': 50,
            
            # ATR settings
            'atr_length': 10,
            'atr_min': 0.030,
            'atr_max': 0.045,
            
            # Angle Filter
            'use_angle_filter': True,
            'angle_min': 45.0,
            'angle_max': 90.0,
            'angle_scale': 100.0,
            
            # SL/TP multipliers
            'sl_mult': 1.5,
            'tp_mult': 15.0,
            
            # Pullback settings
            'pullback_candles': 1,
            'window_periods': 2,
            'price_offset_mult': 0.01,
            
            # Time filter - EXACT from original (1:00-15:00 UTC)
            'use_time_filter': True,
            'allowed_hours': [0, 1, 2, 3, 4, 10, 11, 12],
            
            # SL pips filter
            'use_sl_pips_filter': True,
            'sl_pips_min': 4.0,
            'sl_pips_max': 11.0,
            
            # Risk management
            'risk_percent': 0.01,
            'lot_size': 100000,
            
            # JPY pair settings
            'jpy_rate': 150.0,
            'pip_value': 0.01,
            
            # Debug
            'print_signals': False,
        }
    },

    'DIA_PRO': {
        'active': True,  # Set to False to skip this config when running
        'strategy_name': 'SunsetOgle',
        'asset_name': 'DIA',
        'data_path': 'data/DIA_5m_5Yea.csv',
        
        'from_date': datetime.datetime(2020, 1, 1),
        'to_date': datetime.datetime(2025, 12, 1),
        
        'starting_cash': 100000.0,
        
        'run_plot': True,
        'generate_report': True,
        'save_log': True,
        'debug_mode': False,
        
        'params': {
            # EMA settings 
            'ema_fast_length': 12,
            'ema_medium_length': 18,
            'ema_slow_length': 36,
            'ema_confirm_length': 1,
            'ema_filter_price_length': 50,
            
            # ATR settings 
            'atr_length': 10,
            'atr_min': 0.00,
            'atr_max': 1.60,
            
            # Angle Filter 
            'use_angle_filter': False,
            'angle_min': 45.0,
            'angle_max': 75.0,
            'angle_scale': 10000.0,
            
            # SL/TP multipliers 
            'sl_mult': 3.5,
            'tp_mult': 12.0,
            
            # Pullback settings
            'pullback_candles': 2,
            'window_periods': 2,
            'price_offset_mult': 0.01,
            
            # Time filter 
            'use_time_filter': True,
            'allowed_hours': [14, 15, 16, 18, 19, 20],
            
            # SL pips filter - DISABLED
            'use_sl_pips_filter': False,
            'sl_pips_min': 7.0,
            'sl_pips_max': 21.0,
            
            # Risk management
            'risk_percent': 0.01,
                                               
            # ETF Asset config
            'pip_value': 0.01,   # ETF: 2 decimal places
            'lot_size': 1,       # ETF: 1 share per contract
            'jpy_rate': 1.0,     # Not used for ETF
            'is_etf': True,
            'margin_pct': 20.0,  # 20% margin (5:1 leverage)
            
            # Debug
            'print_signals': False,
        }
    },
    # KO
    'TLT_PRO': {
        'active': False,  # Set to False to skip this config when running
        'strategy_name': 'SunsetOgle',
        'asset_name': 'TLT',
        'data_path': 'data/TLT_5m_5Yea.csv',
        
        'from_date': datetime.datetime(2020, 1, 1),
        'to_date': datetime.datetime(2025, 12, 30),
        
        'starting_cash': 100000.0,
        
        'run_plot': True,
        'generate_report': True,
        'save_log': True,
        'debug_mode': False,
        
        'params': {
            # EMA settings 
            'ema_fast_length': 5,
            'ema_medium_length': 7,
            'ema_slow_length': 12,
            'ema_confirm_length': 1,
            'ema_filter_price_length': 30,
            
            # ATR settings 
            'atr_length': 10,
            'atr_min': 0.00,
            'atr_max': 1.00,
            
            # Angle Filter 
            'use_angle_filter': False,
            'angle_min': 0.0,
            'angle_max': 85.0,
            'angle_scale': 10000.0,
            
            # SL/TP multipliers 
            'sl_mult': 3.5,
            'tp_mult': 8.0,
            
            # Pullback settings
            'pullback_candles': 2,
            'window_periods': 3,
            'price_offset_mult': 0.01,
            
            # Time filter 
            'use_time_filter': True,
            'allowed_hours': [14, 15, 16, 18, 19],
            
            # SL pips filter - DISABLED
            'use_sl_pips_filter': True,
            'sl_pips_min': 20.0,
            'sl_pips_max': 60.0,
            
            # Risk management
            'risk_percent': 0.01,
                                               
            # ETF Asset config
            'pip_value': 0.01,   # ETF: 2 decimal places
            'lot_size': 1,       # ETF: 1 share per contract
            'jpy_rate': 1.0,     # Not used for ETF
            'is_etf': True,
            'margin_pct': 20.0,  # 20% margin (5:1 leverage)
            
            # Debug
            'print_signals': False,
        }
    },

    # =========================================================================
    # KOI STRATEGY CONFIGURATIONS
    # =========================================================================
    
    'EURUSD_KOI': {
        'active': True,
        'strategy_name': 'KOI',
        'asset_name': 'EURUSD',
        'data_path': 'data/EURUSD_5m_5Yea.csv',
        
        'from_date': datetime.datetime(2020, 1, 1),
        'to_date': datetime.datetime(2025, 12, 1),
        
        'starting_cash': 100000.0,
        
        'run_plot': False,
        'generate_report': True,
        'save_log': True,
        
        'params': {
            # 5 EMAs
            'ema_1_period': 10,
            'ema_2_period': 20,
            'ema_3_period': 40,
            'ema_4_period': 80,
            'ema_5_period': 120,
            
            # CCI
            'cci_period': 20,
            'cci_threshold': 110,
            'cci_max_threshold': 999,
            
            # ATR
            'atr_length': 10,
            'atr_sl_multiplier': 2.0,
            'atr_tp_multiplier': 6.0,
            
            # Breakout Window
            'use_breakout_window': True,
            'breakout_window_candles': 3,
            'breakout_level_offset_pips': 2.0,
            
            # === FILTERS ===
            
            # Time Filter
            'use_time_filter': True,
            'allowed_hours': [0, 4, 5, 7, 8, 10, 11, 12, 13, 14, 16, 18, 22, 23],
            
            # SL Pips Filter
            'use_sl_pips_filter': True,
            'sl_pips_min': 8.0,
            'sl_pips_max': 14.0,
            
            # ATR Filter
            'use_atr_filter': True,
            'atr_min': 0.00050,
            'atr_max': 0.00100,
            
            # Asset config
            'pip_value': 0.0001,
            'lot_size': 100000,
            'jpy_rate': 150.0,
            
            # Risk
            'risk_percent': 0.01,
            
            # Debug & Reporting
            'print_signals': False,
            'export_reports': True,
        }
    },

    'USDCAD_KOI': {
        'active': True,
        'strategy_name': 'KOI',
        'asset_name': 'USDCAD',
        'data_path': 'data/USDCAD_5m_5Yea.csv',
        
        'from_date': datetime.datetime(2020, 1, 1),
        'to_date': datetime.datetime(2025, 12, 1),
        
        'starting_cash': 100000.0,
        
        'run_plot': True,
        'generate_report': True,
        'save_log': True,
        
        'params': {
            # 5 EMAs
            'ema_1_period': 10,
            'ema_2_period': 20,
            'ema_3_period': 40,
            'ema_4_period': 80,
            'ema_5_period': 120,
            
            # CCI
            'cci_period': 25,
            'cci_threshold': 100,
            'cci_max_threshold': 130,
            
            # ATR
            'atr_length': 10,
            'atr_sl_multiplier': 3.0,
            'atr_tp_multiplier': 12.0,
            
            # Breakout Window
            'use_breakout_window': True,
            'breakout_window_candles': 5,
            'breakout_level_offset_pips': 5.0,
            
            # === FILTERS ===
            
            # Time Filter
            'use_time_filter': True,
            'allowed_hours': [1, 5, 6, 7, 8, 11, 12, 13, 14, 15, 16, 17],
            
            # SL Pips Filter
            'use_sl_pips_filter': True,
            'sl_pips_min': 10.0,
            'sl_pips_max': 18.0,
            
            # ATR Filter
            'use_atr_filter': False,
            'atr_min': 0.00050,
            'atr_max': 0.00100,
            
            # Asset config
            'pip_value': 0.0001,
            'lot_size': 100000,
            'jpy_rate': 150.0,
            
            # Risk
            'risk_percent': 0.01,
            
            # Debug & Reporting
            'print_signals': False,
            'export_reports': True,
        }
    },

    'USDCHF_KOI': {
        'active': True,
        'strategy_name': 'KOI',
        'asset_name': 'USDCHF',
        'data_path': 'data/USDCHF_5m_5Yea.csv',
        
        'from_date': datetime.datetime(2020, 1, 1),
        'to_date': datetime.datetime(2025, 12, 1),
        
        'starting_cash': 100000.0,
        
        'run_plot': True,
        'generate_report': True,
        'save_log': True,
        
        'params': {
            # 5 EMAs
            'ema_1_period': 10,
            'ema_2_period': 20,
            'ema_3_period': 40,
            'ema_4_period': 80,
            'ema_5_period': 120,
            
            # CCI
            'cci_period': 20,
            'cci_threshold': 100,
            'cci_max_threshold': 150,
            
            # ATR
            'atr_length': 10,
            'atr_sl_multiplier': 3.0,
            'atr_tp_multiplier': 12.0,
            
            # Breakout Window
            'use_breakout_window': True,
            'breakout_window_candles': 3,
            'breakout_level_offset_pips': 5.0,
            
            # === FILTERS ===
            
            # Time Filter
            'use_time_filter': True,
            'allowed_hours': [0,1,2,3,4,5,6,7,8,9,10,11,13,14,15,16,17,18,19,20,21,22,23],
            
            # SL Pips Filter
            'use_sl_pips_filter': True,
            'sl_pips_min': 10.5,
            'sl_pips_max': 14.5,
            
            # ATR Filter
            'use_atr_filter': False,
            'atr_min': 0.00035,
            'atr_max': 0.00044,
            
            # Asset config
            'pip_value': 0.0001,
            'lot_size': 100000,
            'jpy_rate': 150.0,
            
            # Risk
            'risk_percent': 0.01,
            
            # Debug & Reporting
            'print_signals': False,
            'export_reports': True,
        }
    },
    # ========================================================================= 
    'USDJPY_KOI': {
        'active': True,
        'strategy_name': 'KOI',
        'asset_name': 'USDJPY',
        'data_path': 'data/USDJPY_5m_5Yea.csv',
        
        'from_date': datetime.datetime(2020, 1, 1),
        'to_date': datetime.datetime(2025, 12, 1),
        
        'starting_cash': 100000.0,
        
        'run_plot': True,
        'generate_report': True,
        'save_log': True,
        
        'params': {
            # 5 EMAs
            'ema_1_period': 10,
            'ema_2_period': 20,
            'ema_3_period': 40,
            'ema_4_period': 80,
            'ema_5_period': 120,
            
            # CCI
            'cci_period': 14,
            'cci_threshold': 120,
            'cci_max_threshold': 300,
            
            # ATR
            'atr_length': 10,
            'atr_sl_multiplier': 3.5,
            'atr_tp_multiplier': 10.0,
            
            # Breakout Window
            'use_breakout_window': True,
            'breakout_window_candles': 7,
            'breakout_level_offset_pips': 7.0,
            
            # === FILTERS ===
            
            # Time Filter
            'use_time_filter': True,
            'allowed_hours': [0,1,2,3,4,5,6,7,10,11,13,15,16,17,18,19,20,21],
            
            # SL Pips Filter
            'use_sl_pips_filter': True,
            'sl_pips_min': 15.0,
            'sl_pips_max': 30.0,
            
            # ATR Filter
            'use_atr_filter': True,
            'atr_min': 0.05,
            'atr_max': 0.10,
            
            # Asset config (JPY pair)
            'pip_value': 0.01,
            'lot_size': 100000,
            'jpy_rate': 150.0,
            
            # Risk
            'risk_percent': 0.005,
            
            # Debug & Reporting
            'print_signals': False,
            'export_reports': True,
        }
    },

    'EURJPY_KOI': {
        'active': True,
        'strategy_name': 'KOI',
        'asset_name': 'EURJPY',
        'data_path': 'data/EURJPY_5m_5Yea.csv',
        
        'from_date': datetime.datetime(2020, 1, 1),
        'to_date': datetime.datetime(2025, 12, 1),
        
        'starting_cash': 100000.0,
        
        'run_plot': True,
        'generate_report': True,
        'save_log': True,
        
        'params': {
            # 5 EMAs
            'ema_1_period': 10,
            'ema_2_period': 20,
            'ema_3_period': 40,
            'ema_4_period': 80,
            'ema_5_period': 120,
            
            # CCI
            'cci_period': 14,
            'cci_threshold': 80,
            'cci_max_threshold': 130,
            
            # ATR
            'atr_length': 10,
            'atr_sl_multiplier': 2.5,
            'atr_tp_multiplier': 12.0,
            
            # Breakout Window
            'use_breakout_window': True,
            'breakout_window_candles': 10,
            'breakout_level_offset_pips': 5.0,
            
            # === FILTERS ===
            
            # Time Filter
            'use_time_filter': True,
            'allowed_hours': [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 14, 15, 16, 17, 19],
            
            # SL Pips Filter
            'use_sl_pips_filter': True,
            'sl_pips_min': 18.0,
            'sl_pips_max': 28.0,
            
            # ATR Filter
            'use_atr_filter': True,
            'atr_min': 0.074,
            'atr_max': 0.095,
            
            # Asset config
            'pip_value': 0.0001,
            'lot_size': 100000,
            'jpy_rate': 150.0,
            
            # Risk
            'risk_percent': 0.005,
            
            # Debug & Reporting
            'print_signals': False,
            'export_reports': True,
        }
    },

    # =========================================================================
    # ETF KOI CONFIGURATIONS
    # =========================================================================
    
    'DIA_KOI': {
        'active': True,
        'strategy_name': 'KOI',
        'asset_name': 'DIA',
        'data_path': 'data/DIA_5m_5Yea.csv',
        
        'from_date': datetime.datetime(2020, 1, 1),
        'to_date': datetime.datetime(2025, 12, 1),
        
        'starting_cash': 100000.0,
        
        'run_plot': True,
        'generate_report': True,
        'save_log': True,
        
        'params': {
            # 5 EMAs
            'ema_1_period': 10,
            'ema_2_period': 20,
            'ema_3_period': 40,
            'ema_4_period': 80,
            'ema_5_period': 120,
            
            # CCI
            'cci_period': 20,
            'cci_threshold': 100,
            'cci_max_threshold': 999,
            
            # ATR
            'atr_length': 10,
            'atr_sl_multiplier': 2.0,
            'atr_tp_multiplier': 10.0,
            
            # Breakout Window
            'use_breakout_window': True,
            'breakout_window_candles': 3,
            'breakout_level_offset_pips': 5.0,
            
            # === FILTERS ===
            
            # Time Filter 
            'use_time_filter': True,
            'allowed_hours': [14, 15, 16, 17, 18, 19],
            
            # SL Pips Filter (disabled - ETF uses ATR filter)
            'use_sl_pips_filter': False,
            'sl_pips_min': 60,   # $1 min (pip_value=0.01 -> 100 pips)
            'sl_pips_max': 75,  # $20 max
            
            # ATR Filter (optimized for DIA)
            'use_atr_filter': True,
            'atr_min': 0.30,  # $0.30 ATR min
            'atr_max': 0.40,  # $0.40 ATR max
            
            # ETF Asset config
            'pip_value': 0.01,   # ETF: 2 decimal places
            'lot_size': 1,       # ETF: 1 share per contract
            'jpy_rate': 1.0,     # Not used for ETF
            'is_etf': True,
            'margin_pct': 20.0,  # 20% margin (5:1 leverage)
            
            # Risk
            'risk_percent': 0.005,
            
            # Debug & Reporting
            'print_signals': False,
            'export_reports': True,
        }
    },
    # KO
    'TLT_KOI': {
        'active': False,
        'strategy_name': 'KOI',
        'asset_name': 'TLT',
        'data_path': 'data/TLT_5m_5Yea.csv',
        
        'from_date': datetime.datetime(2020, 7, 1),
        'to_date': datetime.datetime(2025, 7, 1),
        
        'starting_cash': 100000.0,
        
        'run_plot': True,
        'generate_report': True,
        'save_log': True,
        
        'params': {
            # 5 EMAs
            'ema_1_period': 10,
            'ema_2_period': 20,
            'ema_3_period': 40,
            'ema_4_period': 80,
            'ema_5_period': 120,
            
            # CCI
            'cci_period': 14,
            'cci_threshold': 50,
            'cci_max_threshold': 999,
            
            # ATR
            'atr_length': 10,
            'atr_sl_multiplier': 6.0,
            'atr_tp_multiplier': 15.0,
            
            # Breakout Window
            'use_breakout_window': True,
            'breakout_window_candles': 10,
            'breakout_level_offset_pips': 2.0,
            
            # === FILTERS ===
            
            # Time Filter 
            'use_time_filter': False,
            'allowed_hours': [14, 15, 16, 17, 18, 19],
            
            # SL Pips Filter (disabled - ETF uses ATR filter)
            'use_sl_pips_filter': False,
            'sl_pips_min': 5,   # $1 min (pip_value=0.01 -> 100 pips)
            'sl_pips_max': 35,  # $20 max
            
            # ATR Filter (optimized for TLT)
            'use_atr_filter': False,
            'atr_min': 0.04,  
            'atr_max': 0.08,  
            
            # ETF Asset config
            'pip_value': 0.01,   # ETF: 2 decimal places
            'lot_size': 1,       # ETF: 1 share per contract
            'jpy_rate': 1.0,     # Not used for ETF
            'is_etf': True,
            'margin_pct': 20.0,  # 20% margin (5:1 leverage)
            
            # Risk
            'risk_percent': 0.005,
            
            # Debug & Reporting
            'print_signals': False,
            'export_reports': True,
        }
    },

    # =========================================================================
    # SEDNA STRATEGY CONFIGURATIONS
    # =========================================================================
    
    'DIA_SEDNA': {
        'active': True,
        'strategy_name': 'SEDNA',
        'asset_name': 'DIA',
        'data_path': 'data/DIA_5m_5Yea.csv',
        
        'from_date': datetime.datetime(2020, 1, 1),
        'to_date': datetime.datetime(2025, 12, 1),
        
        'starting_cash': 100000.0,
        
        'run_plot': True,
        'generate_report': True,
        'save_log': True,
        
        'params': {
            # KAMA settings
            'kama_period': 10,
            'kama_fast': 2,
            'kama_slow': 30,
            'hl2_ema_period': 1,  # EMA period for KAMA comparison (1 = raw HL2)
            
            # CCI settings (optional momentum filter)
            'use_cci_filter': False,  # Disabled - not part of 3-phase system
            'cci_period': 20,
            'cci_threshold': 100,
            'cci_max_threshold': 999,
            
            # ATR
            'atr_length': 14,
            'atr_sl_multiplier': 3.0,
            'atr_tp_multiplier': 8.0,
            
            # Breakout Window
            'use_breakout_window': True,
            'breakout_window_candles': 7,
            'breakout_level_offset_pips': 1.0,
            
            # === FILTERS ===
            
            # Time Filter
            'use_time_filter': False,
            'allowed_hours': [13, 14, 15, 17, 18, 19, 20, 21, 22, 23],
            
            # Day Filter (0=Monday, 6=Sunday)
            'use_day_filter': True,
            'allowed_days': [0, 1, 3, 4],  # Monday-Friday
            
            # SL Pips Filter
            'use_sl_pips_filter': False,
            'sl_pips_min': 60,
            'sl_pips_max': 75,
            
            # ATR Filter (uses average ATR)
            'use_atr_filter': True,
            'atr_min': 0.30,
            'atr_max': 9.99,
            'atr_avg_period': 20,
            
            # === HTF FILTER (Higher Timeframe Efficiency Ratio) ===
            # Main trigger: ER >= threshold AND Close > KAMA
            'use_htf_filter': True,
            'htf_timeframe_minutes': 15,
            'htf_er_period': 10,
            'htf_er_threshold': 0.45,
            
            # === PULLBACK DETECTION ===
            # Detects consolidation after HH for trend continuation
            'use_pullback_filter': True,
            'pullback_min_bars': 1,
            'pullback_max_bars': 4,
            
            # === EXIT CONDITIONS ===
            
            # KAMA Exit: Close when KAMA > EMA (trend reversal)
            'use_kama_exit': False,
            
            # ETF Asset config
            'pip_value': 0.01,
            'lot_size': 1,
            'jpy_rate': 1.0,
            'is_etf': True,
            'margin_pct': 20.0,
            
            # Risk
            'risk_percent': 0.005,
            
            # Debug & Reporting
            'print_signals': False,
            'export_reports': True,
        }
    },

    # =========================================================================
    # SEDNA FOREX CONFIGURATIONS
    # =========================================================================
    
    'EURJPY_SEDNA': {
        'active': True,
        'strategy_name': 'SEDNA',
        'asset_name': 'EURJPY',
        'data_path': 'data/EURJPY_5m_5Yea.csv',
        
        'from_date': datetime.datetime(2020, 1, 1),
        'to_date': datetime.datetime(2025, 12, 1),
        
        'starting_cash': 100000.0,
        
        'run_plot': True,
        'generate_report': True,
        'save_log': True,
        
        'params': {
            # KAMA settings
            'kama_period': 10,
            'kama_fast': 2,
            'kama_slow': 30,
            'hl2_ema_period': 1,
            
            # CCI settings
            'use_cci_filter': False,
            'cci_period': 20,
            'cci_threshold': 100,
            'cci_max_threshold': 999,
            
            # ATR
            'atr_length': 10,
            'atr_sl_multiplier': 3.0,
            'atr_tp_multiplier': 8.0,
            
            # Breakout Window
            'use_breakout_window': True,
            'breakout_window_candles': 5,
            'breakout_level_offset_pips': 1.0,
            
            # === FILTERS ===
            'use_time_filter': True,
            'allowed_hours': [1, 4, 5, 7, 8, 10, 14, 15, 16],
            
            # Day Filter (0=Monday, 6=Sunday)
            'use_day_filter': True,
            'allowed_days': [0, 1, 2, 4], 
            
            # SL Pips Filter
            'use_sl_pips_filter': True,
            'sl_pips_min': 12,
            'sl_pips_max': 28,
            
            'use_atr_filter': False,
            'atr_min': 0.03,
            'atr_max': 0.15,
            'atr_avg_period': 20,
            
            # === HTF FILTER ===
            'use_htf_filter': True,
            'htf_timeframe_minutes': 15,
            'htf_er_period': 10,
            'htf_er_threshold': 0.40,
            
            # === PULLBACK DETECTION ===
            'use_pullback_filter': True,
            'pullback_min_bars': 1,
            'pullback_max_bars': 4,
            
            # === EXIT CONDITIONS ===
            'use_kama_exit': False,
            
            # JPY Pair config
            'pip_value': 0.01,
            'lot_size': 100000,
            'jpy_rate': 150.0,
            'is_etf': False,
            'margin_pct': 3.33,
            
            # Risk
            'risk_percent': 0.01,
            
            # Debug & Reporting
            'print_signals': False,
            'export_reports': True,
        }
    },

    'USDJPY_SEDNA': {
        'active': True,
        'strategy_name': 'SEDNA',
        'asset_name': 'USDJPY',
        'data_path': 'data/USDJPY_5m_5Yea.csv',
        
        'from_date': datetime.datetime(2020, 1, 1),
        'to_date': datetime.datetime(2025, 12, 1),
        
        'starting_cash': 100000.0,
        
        'run_plot': True,
        'generate_report': True,
        'save_log': True,
        
        'params': {
            # KAMA settings
            'kama_period': 10,
            'kama_fast': 2,
            'kama_slow': 30,
            'hl2_ema_period': 1,
            
            # CCI settings
            'use_cci_filter': False,
            'cci_period': 20,
            'cci_threshold': 100,
            'cci_max_threshold': 999,
            
            # ATR
            'atr_length': 10,
            'atr_sl_multiplier': 3.0,
            'atr_tp_multiplier': 8.0,
            
            # Breakout Window
            'use_breakout_window': True,
            'breakout_window_candles': 5,
            'breakout_level_offset_pips': 1.0,
            
            # === FILTERS ===
            'use_time_filter': True,
            'allowed_hours': [0, 1, 2, 5, 7, 8, 9, 12, 14, 15, 16, 17, 18, 20, 21],
            
            # Day Filter (0=Monday, 6=Sunday)
            'use_day_filter': True,
            'allowed_days': [0, 1, 4, 5], 
            
            # SL Pips Filter
            'use_sl_pips_filter': True,
            'sl_pips_min': 15,
            'sl_pips_max': 50,
            
            'use_atr_filter': True,
            'atr_min': 0.05,
            'atr_max': 0.13,
            'atr_avg_period': 20,
            
            # === HTF FILTER ===
            'use_htf_filter': True,
            'htf_timeframe_minutes': 15,
            'htf_er_period': 10,
            'htf_er_threshold': 0.40,
            
            # === PULLBACK DETECTION ===
            'use_pullback_filter': True,
            'pullback_min_bars': 1,
            'pullback_max_bars': 4,
            
            # === EXIT CONDITIONS ===
            'use_kama_exit': False,
            
            # JPY Pair config
            'pip_value': 0.01,
            'lot_size': 100000,
            'jpy_rate': 150.0,
            'is_etf': False,
            'margin_pct': 3.33,
            
            # Risk
            'risk_percent': 0.01,
            
            # Debug & Reporting
            'print_signals': False,
            'export_reports': True
        }
    },

    # =========================================================================
    # GLIESE v2 STRATEGY CONFIGURATIONS (Simplified Mean Reversion)
    # =========================================================================
    
    'USDCHF_GLIESE': {
        'active': True,
        'strategy_name': 'GLIESE',
        'asset_name': 'USDCHF',
        'data_path': 'data/USDCHF_5m_5Yea.csv',
        
        'from_date': datetime.datetime(2020, 7, 1),
        'to_date': datetime.datetime(2025, 7, 1),
        
        'starting_cash': 100000.0,
        
        'run_plot': False,
        'generate_report': True,
        'save_log': True,
        
        'params': {
            # KAMA settings (center line)
            'kama_period': 10,
            'kama_fast': 2,
            'kama_slow': 30,
            
            # HL2 EMA for stability
            'hl2_ema_period': 10,
            
            # Band settings
            'band_atr_period': 14,
            'band_atr_mult': 1.0,  # LowerBand = KAMA - 1.0 * ATR (más cercana)
            
            # Extension Detection (A phase)
            'extension_min_bars': 8,  
            'extension_max_bars': 15,
            
            # Pullback Settings (C phase)
            'pullback_max_bars': 15,  # Más tiempo para breakout
            'breakout_buffer_pips': 1.0,  # Buffer más pequeño
            
            # SL/TP
            'sl_buffer_pips': 5.0,
            'use_kama_tp': False,  # No usar KAMA (muy cerca)
            'atr_sl_multiplier': 1.5,  # SL = ext_low - 2*ATR
            'atr_tp_multiplier': 10.0,  # TP = entry + 2*ATR
            
            # === FILTERS (same as SEDNA) ===
            'use_time_filter': False,
            'allowed_hours': [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
            
            'use_day_filter': False,
            'allowed_days': [0, 2, 3, 4],
            
            'use_sl_pips_filter': False,
            'sl_pips_min': 0.0,
            'sl_pips_max': 20.0,
            
            'use_atr_filter': False,
            'atr_min': 0.00025,
            'atr_max': 0.00060,
            'atr_avg_period': 20,
            
            # ADXR Filter (ranging market)
            'use_adxr_filter': True,  # ENABLED
            'adxr_period': 14,
            'adxr_lookback': 14,
            'adxr_max_threshold': 25.0,  # ADXR < 25 = ranging
            'adxr_timeframe_mult': 6,    # 1=5m, 3=15m, 6=30m (on 5m data)
            
            # Time-Based Exit
            'use_time_exit': False,  # DISABLED - close if no TP/SL hit
            'time_exit_bars': 12,   # 12 bars = 1 hour on 5min TF
            
            # Confirmation Hold (wait N bars, cancel if low breaks extension_low - offset)
            'use_confirmation_delay': False,   # DISABLED - filter fakeouts
            'confirmation_bars': 3,           # 3 bars = 15min on 5min TF
            'confirmation_offset_pips': 2.0,  # Offset below extension_low (flexibility)
            
            # HTF Filter (Higher Timeframe for trend/range context)
            'use_htf_filter': False,          # DISABLED by default
            'htf_timeframe_minutes': 15,      # 15m or 30m
            'htf_er_period': 10,              # ER period on HTF
            'htf_er_max_threshold': 0.30,     # ER < 0.30 = ranging (for mean reversion)
            
            # Asset config
            'pip_value': 0.0001,
            'lot_size': 100000,
            'jpy_rate': 1.0,
            'is_etf': False,
            'margin_pct': 3.33,
            
            # Risk
            'risk_percent': 0.005,
            
            # Debug & Reporting
            'print_signals': False,
            'export_reports': True,
            
            # Plot options
            'plot_bands': True,
            'plot_entry_exit_lines': True,  # Show entry/SL/TP lines on plot
        }
    },

    'USDCAD_GLIESE': {
        'active': True,
        'strategy_name': 'GLIESE',
        'asset_name': 'USDCAD',
        'data_path': 'data/USDCAD_5m_5Yea.csv',
        
        'from_date': datetime.datetime(2020, 1, 1),
        'to_date': datetime.datetime(2025, 12, 1),
        
        'starting_cash': 100000.0,
        
        'run_plot': True,
        'generate_report': True,
        'save_log': True,
        
        'params': {
            # KAMA settings
            'kama_period': 10,
            'kama_fast': 2,
            'kama_slow': 30,
            
            # Band settings
            'band_atr_period': 14,
            'band_atr_mult': 1.5,
            
            # ATR for SL/TP
            'atr_length': 14,
            'atr_sl_multiplier': 2.0,
            'atr_tp_multiplier': 3.0,
            
            # Breakout Window
            'use_breakout_window': True,
            'breakout_window_candles': 5,
            'breakout_level_offset_pips': 2.0,
            
            # === RANGE DETECTION (HTF 15m) ===
            'use_htf_range_filter': True,
            'htf_timeframe_minutes': 15,
            'htf_er_period': 10,
            'htf_er_max_threshold': 0.30,
            
            # ADXR Filter
            'use_adxr_filter': True,
            'adxr_period': 14,
            'adxr_lookback': 14,
            'adxr_max_threshold': 25.0,
            
            # KAMA Slope Filter
            'use_kama_slope_filter': True,
            'kama_slope_lookback': 5,
            'kama_slope_atr_mult': 0.3,
            
            # Extension Detection
            'extension_min_bars': 2,
            'extension_max_bars': 20,
            
            # Z-Score Filter
            'use_zscore_filter': False,
            'zscore_min_depth': -2.0,
            
            # Pullback Detection
            'use_pullback_filter': True,
            'pullback_min_bars': 1,
            'pullback_max_bars': 4,
            
            # Cancellation
            'er_cancel_threshold': 0.50,
            
            # === STANDARD FILTERS ===
            'use_time_filter': False,
            'allowed_hours': [],
            
            'use_day_filter': False,
            'allowed_days': [0, 1, 2, 3, 4],
            
            'use_sl_pips_filter': False,
            'sl_pips_min': 5.0,
            'sl_pips_max': 15.0,
            
            'use_atr_filter': False,
            'atr_min': 0.0003,
            'atr_max': 0.0010,
            'atr_avg_period': 20,
            
            # Asset config
            'pip_value': 0.0001,
            'lot_size': 100000,
            'jpy_rate': 1.0,
            'is_etf': False,
            'margin_pct': 3.33,
            
            # Risk
            'risk_percent': 0.01,
            
            # Debug & Reporting
            'print_signals': False,
            'export_reports': True,
            
            # Plot options
            'plot_entry_exit_lines': True,
            'plot_bands': True,
        }
    },

    'EURUSD_GLIESE': {
        'active': True,
        'strategy_name': 'GLIESE',
        'asset_name': 'EURUSD',
        'data_path': 'data/EURUSD_5m_5Yea.csv',
        
        'from_date': datetime.datetime(2020, 1, 1),
        'to_date': datetime.datetime(2025, 12, 1),
        
        'starting_cash': 100000.0,
        
        'run_plot': True,
        'generate_report': True,
        'save_log': True,
        
        'params': {
            # KAMA settings
            'kama_period': 10,
            'kama_fast': 2,
            'kama_slow': 30,
            
            # Band settings
            'band_atr_period': 14,
            'band_atr_mult': 1.5,
            
            # ATR for SL/TP
            'atr_length': 14,
            'atr_sl_multiplier': 2.0,
            'atr_tp_multiplier': 3.0,
            
            # Breakout Window
            'use_breakout_window': True,
            'breakout_window_candles': 5,
            'breakout_level_offset_pips': 2.0,
            
            # === RANGE DETECTION (HTF 15m) ===
            'use_htf_range_filter': True,
            'htf_timeframe_minutes': 15,
            'htf_er_period': 10,
            'htf_er_max_threshold': 0.30,
            
            # ADXR Filter
            'use_adxr_filter': True,
            'adxr_period': 14,
            'adxr_lookback': 14,
            'adxr_max_threshold': 25.0,
            
            # KAMA Slope Filter
            'use_kama_slope_filter': True,
            'kama_slope_lookback': 5,
            'kama_slope_atr_mult': 0.3,
            
            # Extension Detection
            'extension_min_bars': 2,
            'extension_max_bars': 20,
            
            # Z-Score Filter
            'use_zscore_filter': False,
            'zscore_min_depth': -2.0,
            
            # Pullback Detection
            'use_pullback_filter': True,
            'pullback_min_bars': 1,
            'pullback_max_bars': 4,
            
            # Cancellation
            'er_cancel_threshold': 0.50,
            
            # === STANDARD FILTERS ===
            'use_time_filter': False,
            'allowed_hours': [],
            
            'use_day_filter': False,
            'allowed_days': [0, 1, 2, 3, 4],
            
            'use_sl_pips_filter': False,
            'sl_pips_min': 5.0,
            'sl_pips_max': 15.0,
            
            'use_atr_filter': False,
            'atr_min': 0.00020,
            'atr_max': 0.00050,
            'atr_avg_period': 20,
            
            # Asset config
            'pip_value': 0.0001,
            'lot_size': 100000,
            'jpy_rate': 1.0,
            'is_etf': False,
            'margin_pct': 3.33,
            
            # Risk
            'risk_percent': 0.01,
            
            # Debug & Reporting
            'print_signals': False,
            'export_reports': True,
            
            # Plot options
            'plot_entry_exit_lines': True,
            'plot_bands': True,
        }
    },
}

# Broker settings for commission calculation
BROKER_CONFIG = {
    'darwinex_zero': {
        'commission_per_lot': 2.50,  # USD per round-trip lot
        'leverage': 30.0,
        'margin_percent': 3.33,
    },
    'darwinex_zero_etf': {
        'commission_per_contract': 0.02,  # USD per contract
        'leverage': 5.0,
        'margin_percent': 20.0,
    }
}