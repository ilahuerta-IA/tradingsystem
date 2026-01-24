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
            'print_signals': True,
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
            'print_signals': True,
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
            'print_signals': True,
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
            'print_signals': True,
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
            'print_signals': True,
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

    'TLT_PRO': {
        'active': True,  # Set to False to skip this config when running
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

    'TLT_KOI': {
        'active': True,
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
            # KAMA settings (replaces 5 EMAs)
            'kama_period': 10,
            'kama_fast': 2,
            'kama_slow': 30,
            
            # HL2 EMA for KAMA comparison (period=1 = raw HL2)
            'hl2_ema_period': 1,
            
            # CCI settings (on HL2)
            'use_cci_filter': False,
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
            'breakout_level_offset_pips': 2.0,
            
            # === FILTERS ===
            
            # Time Filter
            'use_time_filter': False,
            'allowed_hours': [14, 15, 16, 17, 18, 19],
            
            # SL Pips Filter
            'use_sl_pips_filter': False,
            'sl_pips_min': 60,
            'sl_pips_max': 75,
            
            # ATR Filter (uses average ATR)
            'use_atr_filter': True,
            'atr_min': 0.00,
            'atr_max': 0.80,
            'atr_avg_period': 20,
            
            # === EXIT CONDITIONS ===
            
            # KAMA Exit: Close when KAMA > EMA (trend reversal)
            'use_kama_exit': False,  # Disabled for A/B testing
            
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
            
            # Plot options
            'plot_entry_exit_lines': True,  # Show entry/SL/TP dashed lines
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