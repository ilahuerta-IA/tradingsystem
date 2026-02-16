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
        
        'run_plot': False,
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
            'atr_max': 0.070, #Changed from 0.00090 to 0.070
            
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
            'allowed_hours': [6, 7, 8, 9, 11, 13, 15, 22, 23],
            
            # Day filter (0=Monday, 6=Sunday)
            'use_day_filter': True,
            'allowed_days': [0, 1, 3, 4],
            
            # SL pips filter
            'use_sl_pips_filter': True, # changed from False to True
            'sl_pips_min': 10.0,
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
            # EMA settings 
            'ema_fast_length': 24,
            'ema_medium_length': 24,
            'ema_slow_length': 24,
            'ema_confirm_length': 1,
            'ema_filter_price_length': 60,
            
            # ATR settings 
            'atr_length': 10,
            'atr_min': 0.00020,
            'atr_max': 0.00040,
            
            # Angle Filter 
            'use_angle_filter': False,
            'angle_min': 20.0,
            'angle_max': 85.0,
            'angle_scale': 10000.0,
            
            # SL/TP multipliers
            'sl_mult': 3.0,
            'tp_mult': 15.0,
            
            # Pullback settings
            'pullback_candles': 2,
            'window_periods': 1,
            'price_offset_mult': 0.01,
            
            # Time filter 
            'use_time_filter': True,
            'allowed_hours': [0, 1, 2, 3, 7, 8, 11, 13, 19, 20, 21, 22, 23],
            
            # Day filter (0=Monday, 6=Sunday)
            'use_day_filter': True,
            'allowed_days': [0, 1, 3, 4],
            
            # SL pips filter - DISABLED
            'use_sl_pips_filter': True, #changed from False to True
            'sl_pips_min': 10.0,
            'sl_pips_max': 50.0,
            
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
    # KO
    'USDCAD_PRO': {
        'active': False,  # Set to False to skip this config when running
        'strategy_name': 'SunsetOgle',
        'asset_name': 'USDCAD',
        'data_path': 'data/USDCAD_5m_5Yea.csv',
        
        'from_date': datetime.datetime(2020, 1, 1),
        'to_date': datetime.datetime(2025, 12, 1),
        
        'starting_cash': 100000.0,
        
        'run_plot': False,
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
            'atr_min': 0.00025,
            'atr_max': 0.00050,
            
            # Angle Filter 
            'use_angle_filter': False,
            'angle_min': 15.0,
            'angle_max': 75.0,
            'angle_scale': 10000.0,
            
            # SL/TP multipliers 
            'sl_mult': 3.0,
            'tp_mult': 15.0,
            
            # Pullback settings
            'pullback_candles': 2,
            'window_periods': 1,
            'price_offset_mult': 0.01,
            
            # Time filter 
            'use_time_filter': True,
            'allowed_hours': [0, 1, 2, 3, 7, 14, 18, 19], 
            
            # Day filter (0=Monday, 6=Sunday)
            'use_day_filter': True,
            'allowed_days': [1, 2, 3],
            
            # SL pips filter - DISABLED
            'use_sl_pips_filter': True,
            'sl_pips_min': 10.0,
            'sl_pips_max': 20.0,
            
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
        
        'from_date': datetime.datetime(2020, 1, 1),
        'to_date': datetime.datetime(2025, 12, 1),
        
        'starting_cash': 100000.0,
        
        'run_plot': False,
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
            'atr_min': 0.00035,
            'atr_max': 0.00090,
            
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
            'allowed_hours': [2, 6, 7, 8, 10, 11, 17],
            
            # Day filter (0=Monday, 6=Sunday)
            'use_day_filter': True,
            'allowed_days': [0, 1, 3, 4],
            
            # SL pips filter - DISABLED
            'use_sl_pips_filter': True,
            'sl_pips_min': 10.0,
            'sl_pips_max': 50.0,
            
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
        
        'run_plot': False,
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
            'atr_min': 0.040,
            'atr_max': 0.070,
            
            # Angle Filter
            'use_angle_filter': True,
            'angle_min': 60.0,
            'angle_max': 90.0,
            'angle_scale': 100.0,
            
            # SL/TP multipliers
            'sl_mult': 3.5,
            'tp_mult': 15.0,
            
            # Pullback settings
            'pullback_candles': 1,
            'window_periods': 2,
            'price_offset_mult': 0.01,
            
            # Time filter 
            'use_time_filter': True,
            'allowed_hours': [0, 7, 16, 19, 22, 23],
            
            # Day filter (0=Monday, 6=Sunday)
            'use_day_filter': True,
            'allowed_days': [1, 3, 4],
            
            # SL pips filter
            'use_sl_pips_filter': True,
            'sl_pips_min': 10.0,
            'sl_pips_max': 30.0,
            
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
            
            # Day filter (0=Monday, 6=Sunday)
            'use_day_filter': False,
            'allowed_days': [0, 1, 2, 3, 4],
            
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
            
            # Day filter (0=Monday, 6=Sunday)
            'use_day_filter': False,
            'allowed_days': [0, 1, 2, 3, 4],
            
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
            'cci_max_threshold': 180,
            
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
            'allowed_hours': [1, 4, 7, 11, 13, 14, 15, 16, 17, 18, 22],
            
            # Day Filter (0=Monday, 6=Sunday)
            'use_day_filter': True,
            'allowed_days': [0, 1, 2],
            
            # SL Pips Filter
            'use_sl_pips_filter': True,
            'sl_pips_min': 10.0,
            'sl_pips_max': 19.0,
            
            # ATR Filter
            'use_atr_filter': True,
            'atr_min': 0.00050,
            'atr_max': 0.00090,
            
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
    #KO
    'USDCAD_KOI': {
        'active': False,
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
            
            # Day Filter (0=Monday, 6=Sunday)
            'use_day_filter': False,
            'allowed_days': [0, 1, 2, 3, 4],
            
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
            'cci_threshold': 100,
            'cci_max_threshold': 180,
            
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
            'allowed_hours': [7, 8, 11, 13, 15, 17, 19, 23],
            
            # Day Filter (0=Monday, 6=Sunday)
            'use_day_filter': True,
            'allowed_days': [0, 1, 2, 3],
            
            # SL Pips Filter
            'use_sl_pips_filter': True,
            'sl_pips_min': 10.0,
            'sl_pips_max': 16.0,
            
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
            'cci_period': 14,
            'cci_threshold': 120,
            'cci_max_threshold': 180,
            
            # ATR
            'atr_length': 10,
            'atr_sl_multiplier': 3.5,
            'atr_tp_multiplier': 15.0,
            
            # Breakout Window
            'use_breakout_window': True,
            'breakout_window_candles': 7,
            'breakout_level_offset_pips': 7.0,
            
            # === FILTERS ===
            
            # Time Filter
            'use_time_filter': True,
            'allowed_hours': [0, 1, 3, 4, 8, 11, 13, 16, 17, 23],
            
            # Day Filter (0=Monday, 6=Sunday)
            'use_day_filter': True,
            'allowed_days': [0, 2, 3, 4],
            
            # SL Pips Filter
            'use_sl_pips_filter': True,
            'sl_pips_min': 10.0,
            'sl_pips_max': 27.0,
            
            # ATR Filter
            'use_atr_filter': True,
            'atr_min': 0.035,
            'atr_max': 0.065,
            
            # Asset config (JPY pair)
            'pip_value': 0.01,
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
            'cci_period': 14,
            'cci_threshold': 80,
            'cci_max_threshold': 130,
            
            # ATR
            'atr_length': 10,
            'atr_sl_multiplier': 3.5,
            'atr_tp_multiplier': 12.0,
            
            # Breakout Window
            'use_breakout_window': True,
            'breakout_window_candles': 10,
            'breakout_level_offset_pips': 5.0,
            
            # === FILTERS ===
            
            # Time Filter
            'use_time_filter': True,
            'allowed_hours': [1, 2, 3, 7, 8, 10, 13, 15, 16],
            
            # Day Filter (0=Monday, 6=Sunday)
            'use_day_filter': True,
            'allowed_days': [0, 1, 2, 4],
            
            # SL Pips Filter
            'use_sl_pips_filter': True,
            'sl_pips_min': 20.0,
            'sl_pips_max': 32.0,
            
            # ATR Filter
            'use_atr_filter': True,
            'atr_min': 0.07,
            'atr_max': 0.15,
            
            # Asset config (JPY pair)
            'pip_value': 0.01,
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
            
            # Day Filter (0=Monday, 6=Sunday)
            'use_day_filter': False,
            'allowed_days': [0, 1, 2, 3, 4],
            
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
            
            # Day Filter (0=Monday, 6=Sunday)
            'use_day_filter': False,
            'allowed_days': [0, 1, 2, 3, 4],
            
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
        
        'run_plot': False,
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
        
        'run_plot': False,
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
            'atr_min': 0.05,
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
        
        'run_plot': False,
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
            'allowed_hours': [1, 6, 7, 8, 12, 14, 15],
            
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
    #ko
    'USDCHF_GLIESE': {
        'active': False,
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
            'hl2_ema_period': 14,
            
            # Band settings
            'band_atr_period': 14,
            'band_atr_mult': 1.0,  # LowerBand = KAMA - 2.0 * ATR
            
            # Extension Detection (A phase)
            'extension_max_bars': 12,  # Timeout
            'allowed_extension_bars': [2, 10, 11, 12],  # Empty = all, e.g. [3,4,5,6]
            
            # Pullback Settings (C phase) - SEDNA-like
            'use_pullback_filter': True,  # Wait for pullback for larger SL
            'pullback_min_bars': 2,
            'pullback_max_bars': 10,  # Max bars to wait for pullback
            'breakout_buffer_pips': 1.0,  # buffer above extension high to trigger entry
            
            # SL/TP
            'sl_buffer_pips': 5.0,
            'use_kama_tp': False,  # No usar KAMA (muy cerca)
            'atr_sl_multiplier': 4.5,  # SL = ext_low - 2*ATR
            'atr_tp_multiplier': 10.0,  # TP = entry + 2*ATR
            
            # === FILTERS (same as SEDNA) ===
            'use_time_filter': False,
            'allowed_hours': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            
            'use_day_filter': False,
            'allowed_days': [0, 1, 3, 4],
            
            'use_sl_pips_filter': True,  # Disabled - pullback makes SL larger
            'sl_pips_min': 15.0,
            'sl_pips_max': 30.0,  # Increased for pullback
            
            'use_atr_filter': False,
            'atr_min': 0.000260,
            'atr_max': 0.000600,
            'atr_avg_period': 20,
            
            # ADXR Filter (ranging market)
            'use_adxr_filter': True,  # ENABLED
            'adxr_period': 14,
            'adxr_lookback': 10,
            'adxr_max_threshold': 20.0,  # ADXR < 25 = ranging
            'adxr_timeframe_mult': 15,    # 1=5m, 3=15m, 6=30m (on 5m data)
            'adxr_require_sync': False,  # True = must pass ADXR on BOTH 5m AND HTF
            
            # Time-Based Exit
            'use_time_exit': False,  # ENABLED - close if no TP/SL hit
            'time_exit_bars': 12,   # 12 bars = 1 hour on 5min TF
            
            # Confirmation Hold (wait N bars, cancel if low breaks extension_low - offset)
            'use_confirmation_delay': False,   # DISABLED - filter fakeouts
            'confirmation_bars': 5,           # 3 bars = 15min on 5min TF
            'confirmation_offset_pips': 1.0,  # Offset below extension_low (flexibility)
            
            # HTF Filter (Higher Timeframe for trend/range context)
            'use_htf_filter': False,          # ENABLED by default
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

    # =========================================================================
    # HELIX STRATEGY CONFIGURATIONS (SE-based variant of SEDNA)
    # Target: EURUSD (where SEDNA doesn't work well)
    # =========================================================================
    #ko
    'EURUSD_HELIX': {
        'active': False,
        'strategy_name': 'HELIX',
        'asset_name': 'EURUSD',
        'data_path': 'data/EURUSD_5m_5Yea.csv',
        
        'from_date': datetime.datetime(2020, 7, 1),
        'to_date': datetime.datetime(2025, 7, 1),
        
        'starting_cash': 100000.0,
        
        'run_plot': True,
        'generate_report': True,
        'save_log': True,
        
        'params': {
            # KAMA settings (same as SEDNA)
            'kama_period': 10,
            'kama_fast': 2,
            'kama_slow': 30,
            'hl2_ema_period': 1,
            
            # CCI settings (disabled - not part of core logic)
            'use_cci_filter': False,
            'cci_period': 20,
            'cci_threshold': 100,
            'cci_max_threshold': 999,
            
            # ATR
            'atr_length': 14,
            'atr_sl_multiplier': 3.0,
            'atr_tp_multiplier': 8.0,
            
            # Breakout Window
            'use_breakout_window': True,
            'breakout_window_candles': 5,
            'breakout_level_offset_pips': 1.0,
            
            # === FILTERS ===
            'use_time_filter': False,
            'allowed_hours': [],
            
            'use_day_filter': False,
            'allowed_days': [0, 1, 2, 3, 4],
            
            'use_sl_pips_filter': False,
            'sl_pips_min': 10,
            'sl_pips_max': 30,
            
            'use_atr_filter': False,
            'atr_min': 0.0002,
            'atr_max': 0.0006,
            'atr_avg_period': 20,
            
            # === HTF DATA (generic - any strategy can use) ===
            # Adds self.datas[1] with resampled HTF data
            'htf_data_minutes': 60,  # 0 = disabled, 60 = 1h HTF
            
            # === HTF FILTER (Spectral Entropy) ===
            'use_htf_filter': True,
            'htf_se_period': 30,  # SE period on HTF bars
            
            # SE Range filter (value-based)
            'htf_se_min': 0.0,
            'htf_se_max': 0.20,
            
            # === PULLBACK DETECTION ===
            'use_pullback_filter': True,
            'pullback_min_bars': 1,
            'pullback_max_bars': 4,
            
            # === EXIT CONDITIONS ===
            'use_kama_exit': False,
            
            # Asset config
            'pip_value': 0.0001,
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

    # =========================================================================
    # GEMINI STRATEGY CONFIGURATIONS (Correlation Divergence Momentum)
    # Concept: EUR strength confirmed by EURUSD vs USDCHF divergence
    # =========================================================================
    
    'EURUSD_GEMINI': {
        'active': True,
        'strategy_name': 'GEMINI',
        'asset_name': 'EURUSD',
        'data_path': 'data/EURUSD_5m_5Yea.csv',
        
        # Reference pair for correlation (USDCHF inverted)
        'reference_data_path': 'data/USDCHF_5m_5Yea.csv',
        'reference_symbol': 'USDCHF',
        
        'from_date': datetime.datetime(2020, 1, 1),
        'to_date': datetime.datetime(2025, 12, 1),
        
        'starting_cash': 100000.0,
        
        'run_plot': False,
        'generate_report': True,
        'save_log': True,
        
        'params': {
            # === ROC SETTINGS ===
            'roc_period_primary': 5,       # ROC period for EURUSD (12 bars = 1h on 5m)
            'roc_period_reference': 5,     # ROC period for USDCHF
            'harmony_scale': 10000,         # Scale factor for harmony calculation
            
            # === ENTRY SYSTEM: KAMA Cross + Angle Confirmation ===
            # Step 1: TRIGGER - HL2_EMA crosses above KAMA
            # Step 2: CONFIRMATION - Within N bars, check angles
            'allowed_cross_bars': [10, 11, 12, 14],   # Allowed bars since cross. Empty=all. Analysis showed 0-1 are profitable
            'entry_roc_angle_min': 10.0,    # Min ROC angle during window (degrees)
            'entry_roc_angle_max': 30.0,    # Max ROC angle (too steep = unreliable)
            'entry_harmony_angle_min': 10.0,  # Min Harmony angle during window (degrees)
            'entry_harmony_angle_max': 20.0,  # Max Harmony angle (too steep = unreliable)
            'roc_angle_scale': 1.0,         # Scale for ROC angle calculation
            'harmony_angle_scale': 1.0,     # Scale for Harmony angle calculation
            
            # === KAMA SETTINGS ===
            'kama_period': 10,
            'kama_fast': 2,
            'kama_slow': 30,
            
            # === ATR for SL/TP ===
            'atr_length': 10,
            'atr_sl_multiplier': 5.0,
            'atr_tp_multiplier': 15.0,
            
            # === FILTERS (applied after angle confirmation) ===
            'use_time_filter': True,
            'allowed_hours': [6, 7, 8, 10, 11, 13, 14, 16, 19],
            
            'use_day_filter': True,
            'allowed_days': [0, 1, 2, 3],
            
            'use_sl_pips_filter': True,
            'sl_pips_min': 15,
            'sl_pips_max': 40,
            
            'use_atr_filter': False,
            'atr_min': 0.0002,
            'atr_max': 0.0007,
            'atr_avg_period': 20,
            
            # Asset config
            'pip_value': 0.0001,
            'lot_size': 100000,
            'jpy_rate': 150.0,
            'is_etf': False,
            'margin_pct': 3.33,
            
            # Risk
            'risk_percent': 0.01,
            
            # Debug & Reporting
            'print_signals': False,  # Enable to see KAMA cross and entries
            'export_reports': True,
            
            # Plot options
            'plot_roc_multiplier': 500,    # Scale ROC for visibility
            'plot_harmony_multiplier': 15.0,  # Scale for harmony
        }
    },
    
    'USDCHF_GEMINI': {
        'active': True,  
        'strategy_name': 'GEMINI',
        'asset_name': 'USDCHF',
        'data_path': 'data/USDCHF_5m_5Yea.csv',
        
        # Reference pair (EURUSD - no inversion needed)
        'reference_data_path': 'data/EURUSD_5m_5Yea.csv',
        'reference_symbol': 'EURUSD',
        
        'from_date': datetime.datetime(2020, 1, 1),
        'to_date': datetime.datetime(2025, 12, 1),
        
        'starting_cash': 100000.0,
        
        'run_plot': False,
        'generate_report': True,
        'save_log': True,
        
        'params': {
            # === ROC SETTINGS ===
            'roc_period_primary': 5,       # ROC period for EURUSD (12 bars = 1h on 5m)
            'roc_period_reference': 5,     # ROC period for USDCHF
            'harmony_scale': 10000,         # Scale factor for harmony calculation
            
            # === ENTRY SYSTEM: KAMA Cross + Angle Confirmation ===
            # Step 1: TRIGGER - HL2_EMA crosses above KAMA
            # Step 2: CONFIRMATION - Within N bars, check angles
            'allowed_cross_bars': [0, 3, 5, 6, 7, 8, 9, 10 ,11, 12, 13, 14 ],   # Allowed bars since cross. Empty=all. Analysis showed 0-1 are profitable
            'entry_roc_angle_min': 25.0,    # Min ROC angle during window (degrees)
            'entry_roc_angle_max': 35.0,    # Max ROC angle (too steep = unreliable)
            'entry_harmony_angle_min': 15.0,  # Min Harmony angle during window (degrees)
            'entry_harmony_angle_max': 40.0,  # Max Harmony angle (too steep = unreliable)
            'roc_angle_scale': 1.0,         # Scale for ROC angle calculation
            'harmony_angle_scale': 1.0,     # Scale for Harmony angle calculation
            
            # === KAMA SETTINGS ===
            'kama_period': 10,
            'kama_fast': 2,
            'kama_slow': 30,
            
            # === ATR for SL/TP ===
            'atr_length': 10,
            'atr_sl_multiplier': 5.0,
            'atr_tp_multiplier': 10.0,
            
            # === FILTERS (applied after angle confirmation) ===
            'use_time_filter': True,
            'allowed_hours': [8, 13, 14, 17, 18, 19],
            
            'use_day_filter': True,
            'allowed_days': [1, 2, 3],
            
            'use_sl_pips_filter': True,
            'sl_pips_min': 25,
            'sl_pips_max': 40,
            
            'use_atr_filter': False,
            'atr_min': 0.0002,
            'atr_max': 0.0007,
            'atr_avg_period': 20,
            
            # Asset config
            'pip_value': 0.0001,
            'lot_size': 100000,
            'jpy_rate': 150.0,
            'is_etf': False,
            'margin_pct': 3.33,
            
            # Risk
            'risk_percent': 0.01,
            
            # Debug & Reporting
            'print_signals': False,  # Enable to see KAMA cross and entries
            'export_reports': True,
            
            # Plot options
            'plot_roc_multiplier': 500,    # Scale ROC for visibility
            'plot_harmony_multiplier': 20.0,  # Scale for harmony
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
