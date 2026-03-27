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
        'active': False,  # Set to False to skip this config when running
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
        'to_date': datetime.datetime(2023, 12, 1),
        
        'starting_cash': 100000.0,
        
        'run_plot': False,
        'generate_report': True,
        'save_log': True,
        'debug_mode': False,
        
        'params': {
            # EMA settings 
            'ema_fast_length': 9,
            'ema_medium_length': 11,
            'ema_slow_length': 11,
            'ema_confirm_length': 1,
            'ema_filter_price_length': 50,
            
            # ATR settings 
            'atr_length': 10,
            'atr_min': 0.20,
            'atr_max': 1.20,
            
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
            'allowed_hours': [14, 15, 16, 17, 18],
            
            # Day filter (0=Monday, 6=Sunday)
            'use_day_filter': False,
            'allowed_days': [1, 2, 3, 4],
            
            # SL pips filter - DISABLED
            'use_sl_pips_filter': True,
            'sl_pips_min': 100.0,
            'sl_pips_max': 700.0,
            
            # Risk management
            'risk_percent': 0.01,
                                               
            # ETF Asset config
            'pip_value': 0.01,   # ETF: 2 decimal places
            'lot_size': 1,       # ETF: 1 share per contract
            'jpy_rate': 1.0,     # Not used for ETF
            'is_etf': True,
            'margin_pct': 20.0,  # 20% margin (5:1 leverage)
            
            # EOD close (UTC) - close open positions before market close
            'eod_close_hour': 20,
            'eod_close_minute': 50,
            
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
            
            # EOD close (UTC) - close open positions before market close
            'eod_close_hour': 20,
            'eod_close_minute': 50,
            
            # Debug
            'print_signals': False,
        }
    },

    'GLD_PRO': {
        'active': False,  # Eliminated: portfolio score 0.56, 2024-2025 breakeven, MC95 18%
        'strategy_name': 'SunsetOgle',
        'asset_name': 'GLD',
        'data_path': 'data/GLD_5m_5Yea.csv',
        
        'from_date': datetime.datetime(2020, 1, 1),
        'to_date': datetime.datetime(2025, 12, 31),
        
        'starting_cash': 100000.0,
        
        'run_plot': False,
        'generate_report': True,
        'save_log': True,
        'debug_mode': False,
        
        'params': {
            # EMA settings
            'ema_fast_length': 11,
            'ema_medium_length': 15,
            'ema_slow_length': 24,
            'ema_confirm_length': 1,
            'ema_filter_price_length': 90,
            
            # ATR settings
            'atr_length': 10,
            'atr_min': 0.10,
            'atr_max': 9.50,
            
            # Angle Filter
            'use_angle_filter': False,
            'angle_min': 45.0,
            'angle_max': 75.0,
            'angle_scale': 10000.0,
            
            # SL/TP multipliers
            'sl_mult': 2.5,
            'tp_mult': 6.0,
            
            # Pullback settings
            'pullback_candles': 3,
            'window_periods': 10,
            'price_offset_mult': 0.01,
            
            # Time filter
            'use_time_filter': False,
            'allowed_hours': [13, 14, 15, 16, 17, 18],
            
            # Day filter (0=Monday, 6=Sunday)
            'use_day_filter': True,
            'allowed_days': [0, 1, 3, 4],
            
            # SL pips filter
            'use_sl_pips_filter': True,
            'sl_pips_min': 10.0,
            'sl_pips_max': 200.0,
            
            # Risk management
            'risk_percent': 0.01,
            
            # ETF Asset config
            'pip_value': 0.01,   # ETF: 2 decimal places
            'lot_size': 1,       # ETF: 1 share per contract
            'jpy_rate': 1.0,     # Not used for ETF
            'is_etf': True,
            'margin_pct': 20.0,  # 20% margin (5:1 leverage)
            
            # EOD close (UTC) - close open positions before market close
            'eod_close_hour': 20,
            'eod_close_minute': 50,
            
            # Debug
            'print_signals': False,
        }
    },

    'XLE_PRO': {
        'active': True,
        'strategy_name': 'SunsetOgle',
        'asset_name': 'XLE',
        'data_path': 'data/XLE_5m_5Yea.csv',
        
        'from_date': datetime.datetime(2020, 1, 1),
        'to_date': datetime.datetime(2023, 12, 31),
        
        'starting_cash': 100000.0,
        
        'run_plot': False,
        'generate_report': True,
        'save_log': True,
        'debug_mode': False,
        
        'params': {
            # EMA settings
            'ema_fast_length': 5,
            'ema_medium_length': 7,
            'ema_slow_length': 9,
            'ema_confirm_length': 1,
            'ema_filter_price_length': 50,
            
            # ATR settings
            'atr_length': 10,
            'atr_min': 0.00,
            'atr_max': 9.50,
            
            # Angle Filter
            'use_angle_filter': False,
            'angle_min': 45.0,
            'angle_max': 75.0,
            'angle_scale': 10000.0,
            
            # SL/TP multipliers
            'sl_mult': 2.0,
            'tp_mult': 6.0,
            
            # Pullback settings
            'pullback_candles': 2,
            'window_periods': 10,
            'price_offset_mult': 0.00,
            
            # Time filter
            'use_time_filter': True,
            'allowed_hours': [13, 14, 16, 17, 18, 19],
            
            # Day filter (0=Monday, 6=Sunday)
            'use_day_filter': True,
            'allowed_days': [1, 3, 4],
            
            # SL pips filter
            'use_sl_pips_filter': True,
            'sl_pips_min': 10.0,
            'sl_pips_max': 60.0,
            
            # Risk management
            'risk_percent': 0.01,
            
            # ETF Asset config
            'pip_value': 0.01,   # ETF: 2 decimal places
            'lot_size': 1,       # ETF: 1 share per contract
            'jpy_rate': 1.0,     # Not used for ETF
            'is_etf': True,
            'margin_pct': 20.0,  # 20% margin (5:1 leverage)
            
            # EOD close (UTC) - close open positions before market close
            'eod_close_hour': 20,
            'eod_close_minute': 50,
            
            # Debug
            'print_signals': False,
        }
    },

    'EWZ_PRO': {
        'active': False,
        'strategy_name': 'SunsetOgle',
        'asset_name': 'EWZ',
        'data_path': 'data/EWZ_5m_5Yea.csv',
        
        'from_date': datetime.datetime(2020, 1, 1),
        'to_date': datetime.datetime(2023, 12, 1),
        
        'starting_cash': 100000.0,
        
        'run_plot': False,
        'generate_report': True,
        'save_log': True,
        'debug_mode': False,
        
        'params': {
            # EMA settings
            'ema_fast_length': 5,
            'ema_medium_length': 11,
            'ema_slow_length': 11,
            'ema_confirm_length': 1,
            'ema_filter_price_length': 50,
            
            # ATR settings
            'atr_length': 10,
            'atr_min': 0.01,
            'atr_max': 0.10,
            
            # Angle Filter
            'use_angle_filter': False,
            'angle_min': 45.0,
            'angle_max': 75.0,
            'angle_scale': 10000.0,
            
            # SL/TP multipliers
            'sl_mult': 4.0,
            'tp_mult': 8.0,
            
            # Pullback settings
            'pullback_candles': 2,
            'window_periods': 10,
            'price_offset_mult': 0.01,
            
            # Time filter
            'use_time_filter': True,
            'allowed_hours': [13, 15, 16, 17, 18],
            
            # Day filter (0=Monday, 6=Sunday)
            'use_day_filter': True,
            'allowed_days': [0, 1, 3, 4],
            
            # SL pips filter
            'use_sl_pips_filter': True,
            'sl_pips_min': 10.0,
            'sl_pips_max': 50.0,
            
            # Risk management
            'risk_percent': 0.01,
            
            # ETF Asset config
            'pip_value': 0.01,   # ETF: 2 decimal places
            'lot_size': 1,       # ETF: 1 share per contract
            'jpy_rate': 1.0,     # Not used for ETF
            'is_etf': True,
            'margin_pct': 20.0,  # 20% margin (5:1 leverage)
            
            # EOD close (UTC) - close open positions before market close
            'eod_close_hour': 20,
            'eod_close_minute': 50,
            
            # Debug
            'print_signals': False,
        }
    },

    'XLU_PRO': {
        'active': False,
        'strategy_name': 'SunsetOgle',
        'asset_name': 'XLU',
        'data_path': 'data/XLU_5m_5Yea.csv',
        
        'from_date': datetime.datetime(2020, 1, 1),
        'to_date': datetime.datetime(2023, 1, 31),
        
        'starting_cash': 100000.0,
        
        'run_plot': False,
        'generate_report': True,
        'save_log': True,
        'debug_mode': False,
        
        'params': {
            # EMA settings
            'ema_fast_length': 7,
            'ema_medium_length': 7,
            'ema_slow_length': 9,
            'ema_confirm_length': 1,
            'ema_filter_price_length': 100,
            
            # ATR settings
            'atr_length': 10,
            'atr_min': 0.00,
            'atr_max': 99.20,
            
            # Angle Filter
            'use_angle_filter': False,
            'angle_min': 45.0,
            'angle_max': 75.0,
            'angle_scale': 10000.0,
            
            # SL/TP multipliers
            'sl_mult': 4.0,
            'tp_mult': 8.0,
            
            # Pullback settings
            'pullback_candles': 2,
            'window_periods': 7,
            'price_offset_mult': 0.01,
            
            # Time filter
            'use_time_filter': False,
            'allowed_hours': [13, 14, 15, 19, 20],
            
            # Day filter (0=Monday, 6=Sunday)
            'use_day_filter': False,
            'allowed_days': [0, 1, 3, 4],
            
            # SL pips filter
            'use_sl_pips_filter': True,
            'sl_pips_min': 10.0,
            'sl_pips_max': 900.0,
            
            # Risk management
            'risk_percent': 0.01,
            
            # ETF Asset config
            'pip_value': 0.01,   # ETF: 2 decimal places
            'lot_size': 1,       # ETF: 1 share per contract
            'jpy_rate': 1.0,     # Not used for ETF
            'is_etf': True,
            'margin_pct': 20.0,  # 20% margin (5:1 leverage)
            
            # EOD close (UTC) - close open positions before market close
            'eod_close_hour': 20,
            'eod_close_minute': 50,
            
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
        'active': False,
        'strategy_name': 'KOI',
        'asset_name': 'DIA',
        'data_path': 'data/DIA_5m_5Yea.csv',
        
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
            'cci_max_threshold': 250,
            
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
            'use_time_filter': False,
            'allowed_hours': [14, 15, 16, 17, 18, 19],
            
            # Day Filter (0=Monday, 6=Sunday)
            'use_day_filter': True,
            'allowed_days': [0, 1, 3, 4],
            
            # SL Pips Filter (disabled - ETF uses ATR filter)
            'use_sl_pips_filter': True,
            'sl_pips_min': 50,   # $1 min (pip_value=0.01 -> 100 pips)
            'sl_pips_max': 90,  # $20 max
            
            # ATR Filter (optimized for DIA)
            'use_atr_filter': True,
            'atr_min': 0.25,  # $0.30 ATR min
            'atr_max': 0.50,  # $0.40 ATR max
            
            # ETF Asset config
            'pip_value': 0.01,   # ETF: 2 decimal places
            'lot_size': 1,       # ETF: 1 share per contract
            'jpy_rate': 1.0,     # Not used for ETF
            'is_etf': True,
            'margin_pct': 20.0,  # 20% margin (5:1 leverage)
            
            # EOD close (UTC) - close open positions before market close
            'eod_close_hour': 20,
            'eod_close_minute': 50,
            
            # Risk
            'risk_percent': 0.01,
            
            # Debug & Reporting
            'print_signals': False,
            'export_reports': True,
        }
    },

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
            
            # EOD close (UTC) - close open positions before market close
            'eod_close_hour': 20,
            'eod_close_minute': 50,
            
            # Risk
            'risk_percent': 0.005,
            
            # Debug & Reporting
            'print_signals': False,
            'export_reports': True,
        }
    },

    'GLD_KOI': {
        'active': False,
        'strategy_name': 'KOI',
        'asset_name': 'GLD',
        'data_path': 'data/GLD_5m_5Yea.csv',
        
        'from_date': datetime.datetime(2020, 1, 1),
        'to_date': datetime.datetime(2023, 12, 31),
        
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
            'cci_max_threshold': 250,
            
            # ATR
            'atr_length': 10,
            'atr_sl_multiplier': 5.0,
            'atr_tp_multiplier': 10.0,
            
            # Breakout Window
            'use_breakout_window': True,
            'breakout_window_candles': 3,
            'breakout_level_offset_pips': 5.0,
            
            # === FILTERS ===
            
            # Time Filter 
            'use_time_filter': False,
            'allowed_hours': [14, 15, 16, 17, 18, 19],
            
            # Day Filter (0=Monday, 6=Sunday)
            'use_day_filter': False,
            'allowed_days': [0, 1, 3, 4],
            
            # SL Pips Filter (disabled - ETF uses ATR filter)
            'use_sl_pips_filter': True,
            'sl_pips_min': 10,   # $1 min (pip_value=0.01 -> 100 pips)
            'sl_pips_max': 500,  # $20 max
            
            # ATR Filter (optimized for DIA)
            'use_atr_filter': False,
            'atr_min': 0.25,  # $0.30 ATR min
            'atr_max': 0.50,  # $0.40 ATR max
            
            # ETF Asset config
            'pip_value': 0.01,   # ETF: 2 decimal places
            'lot_size': 1,       # ETF: 1 share per contract
            'jpy_rate': 1.0,     # Not used for ETF
            'is_etf': True,
            'margin_pct': 20.0,  # 20% margin (5:1 leverage)
            
            # EOD close (UTC) - close open positions before market close
            'eod_close_hour': 20,
            'eod_close_minute': 50,
            
            # Risk
            'risk_percent': 0.01,
            
            # Debug & Reporting
            'print_signals': False,
            'export_reports': True,
        }
    },

    'XLE_KOI': {
        'active': False,
        'strategy_name': 'KOI',
        'asset_name': 'XLE',
        'data_path': 'data/XLE_5m_5Yea.csv',
        
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
            'cci_max_threshold': 150,
            
            # ATR
            'atr_length': 10,
            'atr_sl_multiplier': 3.0,
            'atr_tp_multiplier': 6.0,
            
            # Breakout Window
            'use_breakout_window': True,
            'breakout_window_candles': 3,
            'breakout_level_offset_pips': 5.0,
            
            # === FILTERS ===
            
            # Time Filter 
            'use_time_filter': True,
            'allowed_hours': [14, 15, 16, 19],
            
            # Day Filter (0=Monday, 6=Sunday)
            'use_day_filter': True,
            'allowed_days': [0, 1, 2, 4],
            
            # SL Pips Filter (disabled - ETF uses ATR filter)
            'use_sl_pips_filter': True,
            'sl_pips_min': 50,   # $1 min (pip_value=0.01 -> 100 pips)
            'sl_pips_max': 100,  # $20 max
            
            # ATR Filter (optimized for DIA)
            'use_atr_filter': False,
            'atr_min': 0.25,  # $0.30 ATR min
            'atr_max': 0.50,  # $0.40 ATR max
            
            # ETF Asset config
            'pip_value': 0.01,   # ETF: 2 decimal places
            'lot_size': 1,       # ETF: 1 share per contract
            'jpy_rate': 1.0,     # Not used for ETF
            'is_etf': True,
            'margin_pct': 20.0,  # 20% margin (5:1 leverage)
            
            # EOD close (UTC) - close open positions before market close
            'eod_close_hour': 20,
            'eod_close_minute': 50,
            
            # Risk
            'risk_percent': 0.01,
            
            # Debug & Reporting
            'print_signals': False,
            'export_reports': True,
        }
    },

    'EWZ_KOI': {
        'active': False,
        'strategy_name': 'KOI',
        'asset_name': 'EWZ',
        'data_path': 'data/EWZ_5m_5Yea.csv',
        
        'from_date': datetime.datetime(2020, 1, 1),
        'to_date': datetime.datetime(2025, 12, 1),
        
        'starting_cash': 100000.0,
        
        'run_plot': False,
        'generate_report': True,
        'save_log': True,
        
        'params': {
            # 5 EMAs
            'ema_1_period': 20,
            'ema_2_period': 20,
            'ema_3_period': 40,
            'ema_4_period': 80,
            'ema_5_period': 100,
            
            # CCI
            'cci_period': 20,
            'cci_threshold': 110,
            'cci_max_threshold': 350,
            
            # ATR
            'atr_length': 10,
            'atr_sl_multiplier': 4.0,
            'atr_tp_multiplier': 8.0,
            
            # Breakout Window
            'use_breakout_window': True,
            'breakout_window_candles': 10,
            'breakout_level_offset_pips': 5.0,
            
            # === FILTERS ===
            
            # Time Filter 
            'use_time_filter': False,
            'allowed_hours': [14, 15, 16, 19],
            
            # Day Filter (0=Monday, 6=Sunday)
            'use_day_filter': False,
            'allowed_days': [0, 1, 2, 4],
            
            # SL Pips Filter (disabled - ETF uses ATR filter)
            'use_sl_pips_filter': False,
            'sl_pips_min': 50,   # $1 min (pip_value=0.01 -> 100 pips)
            'sl_pips_max': 100,  # $20 max
            
            # ATR Filter (optimized for DIA)
            'use_atr_filter': False,
            'atr_min': 0.25,  # $0.30 ATR min
            'atr_max': 0.50,  # $0.40 ATR max
            
            # ETF Asset config
            'pip_value': 0.01,   # ETF: 2 decimal places
            'lot_size': 1,       # ETF: 1 share per contract
            'jpy_rate': 1.0,     # Not used for ETF
            'is_etf': True,
            'margin_pct': 20.0,  # 20% margin (5:1 leverage)
            
            # EOD close (UTC) - close open positions before market close
            'eod_close_hour': 20,
            'eod_close_minute': 50,
            
            # Risk
            'risk_percent': 0.01,
            
            # Debug & Reporting
            'print_signals': False,
            'export_reports': True,
        }
    },

    'XLU_KOI': {
        'active': True,
        'strategy_name': 'KOI',
        'asset_name': 'XLU',
        'data_path': 'data/XLU_5m_5Yea.csv',
        
        'from_date': datetime.datetime(2020, 1, 1),
        'to_date': datetime.datetime(2023, 12, 31),
        
        'starting_cash': 100000.0,
        
        'run_plot': False,
        'generate_report': True,
        'save_log': True,
        
        'params': {
            # 5 EMAs
            'ema_1_period': 10,
            'ema_2_period': 20,
            'ema_3_period': 40,
            'ema_4_period': 60,
            'ema_5_period': 60,
            
            # CCI
            'cci_period': 20,
            'cci_threshold': 100,
            'cci_max_threshold': 200,
            
            # ATR
            'atr_length': 10,
            'atr_sl_multiplier': 3.5,
            'atr_tp_multiplier': 8.0,
            
            # Breakout Window
            'use_breakout_window': True,
            'breakout_window_candles': 3,
            'breakout_level_offset_pips': 5.0,
            
            # === FILTERS ===
            
            # Time Filter 
            'use_time_filter': False,
            'allowed_hours': [14, 15, 16, 17, 18, 19],
            
            # Day Filter (0=Monday, 6=Sunday)
            'use_day_filter': True,
            'allowed_days': [0, 1, 2, 4],
            
            # SL Pips Filter (disabled - ETF uses ATR filter)
            'use_sl_pips_filter': True,
            'sl_pips_min': 50,   # $1 min (pip_value=0.01 -> 100 pips)
            'sl_pips_max': 120,  # $20 max
            
            # ATR Filter (optimized for DIA)
            'use_atr_filter': False,
            'atr_min': 0.25,  # $0.30 ATR min
            'atr_max': 0.50,  # $0.40 ATR max
            
            # ETF Asset config
            'pip_value': 0.01,   # ETF: 2 decimal places
            'lot_size': 1,       # ETF: 1 share per contract
            'jpy_rate': 1.0,     # Not used for ETF
            'is_etf': True,
            'margin_pct': 20.0,  # 20% margin (5:1 leverage)
            
            # EOD close (UTC) - close open positions before market close
            'eod_close_hour': 20,
            'eod_close_minute': 50,
            
            # Risk
            'risk_percent': 0.01,
            
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
            'allowed_hours': [13, 14, 15, 17, 18, 19, 20],
            
            # Day Filter (0=Monday, 6=Sunday)
            'use_day_filter': True,
            'allowed_days': [0, 1, 3, 4],  # Monday-Friday
            
            # SL Pips Filter
            'use_sl_pips_filter': False,
            'sl_pips_min': 10,
            'sl_pips_max': 200,
            
            # ATR Filter (uses average ATR)
            'use_atr_filter': True,
            'atr_min': 0.30,
            'atr_max': 0.75,
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
            
            # EOD close (UTC) - close open positions before market close
            'eod_close_hour': 20,
            'eod_close_minute': 50,
            
            # Risk
            'risk_percent': 0.01,
            
            # Debug & Reporting
            'print_signals': False,
            'export_reports': True,
        }
    },

    'TLT_SEDNA': {
        'active': False,  # New: pending optimization. Template from DIA_SEDNA.
        'strategy_name': 'SEDNA',
        'asset_name': 'TLT',
        'data_path': 'data/TLT_5m_5Yea.csv',
        
        'from_date': datetime.datetime(2020, 1, 1),
        'to_date': datetime.datetime(2023, 12, 31),
        
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
            'use_cci_filter': False,
            'cci_period': 20,
            'cci_threshold': 100,
            'cci_max_threshold': 999,
            
            # ATR
            'atr_length': 14,
            'atr_sl_multiplier': 3.0,
            'atr_tp_multiplier': 6.0,
            
            # Breakout Window
            'use_breakout_window': True,
            'breakout_window_candles': 7,
            'breakout_level_offset_pips': 1.0,
            
            # === FILTERS ===
            
            # Time Filter
            'use_time_filter': False,
            'allowed_hours': [13, 14, 15, 17, 18, 19, 20],
            
            # Day Filter (0=Monday, 6=Sunday)
            'use_day_filter': False,
            'allowed_days': [0, 1, 3, 4],
            
            # SL Pips Filter
            'use_sl_pips_filter': False,
            'sl_pips_min': 10,
            'sl_pips_max': 200,
            
            # ATR Filter (uses average ATR)
            'use_atr_filter': False,
            'atr_min': 0.30,
            'atr_max': 0.75,
            'atr_avg_period': 20,
            
            # === HTF FILTER (Higher Timeframe Efficiency Ratio) ===
            'use_htf_filter': True,
            'htf_timeframe_minutes': 15,
            'htf_er_period': 10,
            'htf_er_threshold': 0.45,
            
            # === PULLBACK DETECTION ===
            'use_pullback_filter': True,
            'pullback_min_bars': 1,
            'pullback_max_bars': 40,
            
            # === EXIT CONDITIONS ===
            'use_kama_exit': False,
            
            # ETF Asset config
            'pip_value': 0.01,
            'lot_size': 1,
            'jpy_rate': 1.0,
            'is_etf': True,
            'margin_pct': 20.0,
            
            # EOD close (UTC) - close open positions before market close
            'eod_close_hour': 20,
            'eod_close_minute': 50,
            
            # Risk
            'risk_percent': 0.01,
            
            # Debug & Reporting
            'print_signals': False,
            'export_reports': True,
        }
    },

    'GLD_SEDNA': {
        'active': False,  # Eliminated: portfolio score 0.54, worst score, 2025 negative, PF dropped 1.86->1.69
        'strategy_name': 'SEDNA',
        'asset_name': 'GLD',
        'data_path': 'data/GLD_5m_5Yea.csv',
        
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
            'use_cci_filter': False,  # disabled - not part of 3-phase system
            'cci_period': 20,
            'cci_threshold': 100,
            'cci_max_threshold': 999,
            
            # ATR
            'atr_length': 10,
            'atr_sl_multiplier': 3.0,
            'atr_tp_multiplier': 9.0,
            
            # Breakout Window
            'use_breakout_window': True,
            'breakout_window_candles': 5,
            'breakout_level_offset_pips': 0.0,
            
            # === FILTERS ===
            
            # Time Filter
            'use_time_filter': True,
            'allowed_hours': [14, 15, 17, 19, 20],            
            # Day Filter (0=Monday, 6=Sunday)
            'use_day_filter': True,
            'allowed_days': [0, 1, 2, 3],
            
            # SL Pips Filter
            'use_sl_pips_filter': True,
            'sl_pips_min': 30,
            'sl_pips_max': 120,
            
            # ATR Filter (uses average ATR)
            'use_atr_filter': True,
            'atr_min': 0.15,
            'atr_max': 0.40,
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
            
            # EOD close (UTC) - close open positions before market close
            'eod_close_hour': 20,
            'eod_close_minute': 50,
            
            # Risk
            'risk_percent': 0.01,
            
            # Debug & Reporting
            'print_signals': False,
            'export_reports': True,
        }
    },

    'XLE_SEDNA': {
        'active': False,
        'strategy_name': 'SEDNA',
        'asset_name': 'XLE',
        'data_path': 'data/XLE_5m_5Yea.csv',
        
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
            'atr_tp_multiplier': 10.0,
            
            # Breakout Window
            'use_breakout_window': True,
            'breakout_window_candles': 7,
            'breakout_level_offset_pips': 1.0,
            
            # === FILTERS ===
            
            # Time Filter
            'use_time_filter': False,
            'allowed_hours': [13, 14, 15, 17, 18, 19, 20, 21, 22, 23],
            
            # Day Filter (0=Monday, 6=Sunday)
            'use_day_filter': False,
            'allowed_days': [0, 1, 3, 4],  # Monday-Friday
            
            # SL Pips Filter
            'use_sl_pips_filter': False,
            'sl_pips_min': 60,
            'sl_pips_max': 75,
            
            # ATR Filter (uses average ATR)
            'use_atr_filter': False,
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
            'pullback_max_bars': 8,
            
            # === EXIT CONDITIONS ===
            
            # KAMA Exit: Close when KAMA > EMA (trend reversal)
            'use_kama_exit': False,
            
            # ETF Asset config
            'pip_value': 0.01,
            'lot_size': 1,
            'jpy_rate': 1.0,
            'is_etf': True,
            'margin_pct': 20.0,
            
            # EOD close (UTC) - close open positions before market close
            'eod_close_hour': 20,
            'eod_close_minute': 50,
            
            # Risk
            'risk_percent': 0.01,
            
            # Debug & Reporting
            'print_signals': False,
            'export_reports': True,
        }
    },

    'EWZ_SEDNA': {
        'active': False,
        'strategy_name': 'SEDNA',
        'asset_name': 'EWZ',
        'data_path': 'data/EWZ_5m_5Yea.csv',
        
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
            'atr_length': 10,
            'atr_sl_multiplier': 5.0,
            'atr_tp_multiplier': 15.0,
            
            # Breakout Window
            'use_breakout_window': True,
            'breakout_window_candles': 7,
            'breakout_level_offset_pips': 1.0,
            
            # === FILTERS ===
            
            # Time Filter
            'use_time_filter': True,
            'allowed_hours': [14, 15, 17, 19, 20],
            
            # Day Filter (0=Monday, 6=Sunday)
            'use_day_filter': True,
            'allowed_days': [0, 1, 2, 4],  # Monday-Friday
            
            # SL Pips Filter
            'use_sl_pips_filter': True,
            'sl_pips_min': 10,
            'sl_pips_max': 90,
            
            # ATR Filter (uses average ATR)
            'use_atr_filter': False,
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
            'pullback_max_bars': 10,
            
            # === EXIT CONDITIONS ===
            
            # KAMA Exit: Close when KAMA > EMA (trend reversal)
            'use_kama_exit': False,
            
            # ETF Asset config
            'pip_value': 0.01,
            'lot_size': 1,
            'jpy_rate': 1.0,
            'is_etf': True,
            'margin_pct': 20.0,
            
            # EOD close (UTC) - close open positions before market close
            'eod_close_hour': 20,
            'eod_close_minute': 50,
            
            # Risk
            'risk_percent': 0.01,
            
            # Debug & Reporting
            'print_signals': False,
            'export_reports': True,
        }
    },

    'XLU_SEDNA': {
        'active': False,
        'strategy_name': 'SEDNA',
        'asset_name': 'XLU',
        'data_path': 'data/XLU_5m_5Yea.csv',
        
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
            'atr_sl_multiplier': 6.0,
            'atr_tp_multiplier': 12.0,
            
            # Breakout Window
            'use_breakout_window': True,
            'breakout_window_candles': 15,
            'breakout_level_offset_pips': 3.0,
            
            # === FILTERS ===
            
            # Time Filter
            'use_time_filter': True,
            'allowed_hours': [13, 14, 16, 17, 18, 19, 20],
            
            # Day Filter (0=Monday, 6=Sunday)
            'use_day_filter': False,
            'allowed_days': [0, 1, 3, 4],  # Monday-Friday
            
            # SL Pips Filter
            'use_sl_pips_filter': False,
            'sl_pips_min': 60,
            'sl_pips_max': 75,
            
            # ATR Filter (uses average ATR)
            'use_atr_filter': False,
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
            'pullback_min_bars': 2,
            'pullback_max_bars': 7,
            
            # === EXIT CONDITIONS ===
            
            # KAMA Exit: Close when KAMA > EMA (trend reversal)
            'use_kama_exit': False,
            
            # ETF Asset config
            'pip_value': 0.01,
            'lot_size': 1,
            'jpy_rate': 1.0,
            'is_etf': True,
            'margin_pct': 20.0,
            
            # EOD close (UTC) - close open positions before market close
            'eod_close_hour': 20,
            'eod_close_minute': 50,
            
            # Risk
            'risk_percent': 0.01,
            
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
        'to_date': datetime.datetime(2025, 12, 11),
        
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

    # =========================================================================
    # GEMINI_E (EOD Close) — For swap-heavy assets (XAUUSD, etc.)
    # Same GEMINI logic + forced close before swap rollover
    # =========================================================================

    'XAUUSD_GEMINI_E': {
        'active': False,  # DESCARTADO 2026-03-13: correlacion -0.36 insuficiente, optimizacion = overfitting por anio
        'strategy_name': 'GEMINI',
        'asset_name': 'XAUUSD',
        'data_path': 'data/XAUUSD_5m_5Yea.csv',

        # Reference: USDJPY (safe-haven inverse correlation)
        'reference_data_path': 'data/USDJPY_5m_5Yea.csv',
        'reference_symbol': 'USDJPY',

        'from_date': datetime.datetime(2020, 1, 1),
        'to_date': datetime.datetime(2025, 12, 1),

        'starting_cash': 100000.0,

        'run_plot': False,
        'generate_report': True,
        'save_log': True,

        'params': {
            # === ROC SETTINGS ===
            'roc_period_primary': 5,
            'roc_period_reference': 5,
            'harmony_scale': 10000,

            # === ENTRY SYSTEM: KAMA Cross + Angle Confirmation ===
            # Baseline: wide open, user optimizes later
            'allowed_cross_bars': [1, 2, 3, 6, 7, 8],       # Empty = all bars allowed
            'entry_roc_angle_min': 15.0,
            'entry_roc_angle_max': 20.0,
            'entry_harmony_angle_min': 20.0,
            'entry_harmony_angle_max': 25.0,
            'roc_angle_scale': 1.0,
            'harmony_angle_scale': 1.0,

            # === KAMA SETTINGS ===
            'kama_period': 10,
            'kama_fast': 2,
            'kama_slow': 30,

            # === ATR for SL/TP ===
            'atr_length': 14,
            'atr_sl_multiplier': 3.0,
            'atr_tp_multiplier': 6.0,

            # === FILTERS (baseline: minimal, user optimizes later) ===
            'use_time_filter': True,
            'allowed_hours': [0, 1, 2, 3, 4, 12, 13, 14, 17],

            'use_day_filter': False,
            'allowed_days': [0, 2, 3, 4],

            'use_sl_pips_filter': True,
            'sl_pips_min': 50,
            'sl_pips_max': 500,

            'use_atr_filter': False,
            'atr_min': 0.1,
            'atr_max': 10.0,
            'atr_avg_period': 20,

            # === EOD CLOSE (avoid swap -$75/lot/day) ===
            'use_eod_close': True,
            'eod_close_hour': 20,       # 20:45 UTC (before 22:00 rollover)
            'eod_close_minute': 45,

            # === ASSET CONFIG — XAUUSD ===
            # pip_value: 0.01, lot_size: 100 oz, leverage: 20 (5% margin)
            # Broker: FOREX.com GLOBAL, spread ~1.37 pts
            # Swap long: -$75/lot/day, Swap short: +$44.2/lot/day
            'pip_value': 0.01,
            'lot_size': 100,
            'leverage': 20,
            'jpy_rate': 150.0,
            'is_etf': False,
            'margin_pct': 5.0,

            # Risk
            'risk_percent': 0.01,

            # Debug & Reporting
            'print_signals': False,
            'export_reports': True,

            # Plot options
            'plot_roc_multiplier': 500,
            'plot_harmony_multiplier': 60.0,
        }
    },

    # =========================================================================
    # GEMINI_S (Sync Mode) — Correlation SYNC (same direction) pairs
    # sync_mode=True: Harmony = ROC_primary * ROC_reference (positive = synced)
    # =========================================================================

    'USDJPY_GEMINI_S': {
        'active': False,
        'strategy_name': 'GEMINI',
        'asset_name': 'USDJPY',
        'data_path': 'data/USDJPY_5m_5Yea.csv',

        # Reference: EURJPY (corr ~+0.75 with USDJPY)
        'reference_data_path': 'data/EURJPY_5m_5Yea.csv',
        'reference_symbol': 'EURJPY',

        'from_date': datetime.datetime(2020, 1, 1),
        'to_date': datetime.datetime(2025, 12, 1),

        'starting_cash': 100000.0,

        'run_plot': False,
        'generate_report': True,
        'save_log': True,

        'params': {
            # === SYNC MODE ===
            'sync_mode': True,              # KEY: ROC*ROC instead of ROC*(-ROC)

            # === ROC SETTINGS ===
            'roc_period_primary': 5,
            'roc_period_reference': 5,
            'harmony_scale': 10000,

            # === ENTRY SYSTEM: KAMA Cross + Angle Confirmation ===
            'allowed_cross_bars': [1, 3, 5, 6],       # Empty = all bars allowed (exploratory)
            'entry_roc_angle_min': 10.0,
            'entry_roc_angle_max': 20.0,
            'entry_harmony_angle_min': 10.0,
            'entry_harmony_angle_max': 20.0,
            'roc_angle_scale': 1.0,
            'harmony_angle_scale': 1.0,

            # === KAMA SETTINGS ===
            'kama_period': 10,
            'kama_fast': 2,
            'kama_slow': 30,

            # === ATR for SL/TP ===
            'atr_length': 10,
            'atr_sl_multiplier': 5.0,
            'atr_tp_multiplier': 10.0,

            # === FILTERS (wide open for initial exploration) ===
            'use_time_filter': False,
            'allowed_hours': [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 13, 14, 15, 16, 17],

            'use_day_filter': True,           # Always filter weekends in forex
            'allowed_days': [1, 2, 3, 4],

            'use_sl_pips_filter': True,
            'sl_pips_min': 10,
            'sl_pips_max': 70,

            'use_atr_filter': False,
            'atr_min': 0.01,
            'atr_max': 0.15,
            'atr_avg_period': 20,

            # Asset config
            'pip_value': 0.01,
            'is_jpy_pair': True,
            'lot_size': 100000,
            'jpy_rate': 150.0,
            'is_etf': False,
            'margin_pct': 3.33,

            # Risk
            'risk_percent': 0.01,

            # Debug & Reporting
            'print_signals': False,
            'export_reports': True,

            # Plot options
            'plot_roc_multiplier': 500,
            'plot_harmony_multiplier': 20.0,
        }
    },

    'EURJPY_GEMINI_S': {
        'active': False,
        'strategy_name': 'GEMINI',
        'asset_name': 'EURJPY',
        'data_path': 'data/EURJPY_5m_5Yea.csv',

        # Reference: USDJPY (corr ~+0.75 with EURJPY)
        'reference_data_path': 'data/USDJPY_5m_5Yea.csv',
        'reference_symbol': 'USDJPY',

        'from_date': datetime.datetime(2020, 1, 1),
        'to_date': datetime.datetime(2025, 12, 1),

        'starting_cash': 100000.0,

        'run_plot': False,
        'generate_report': True,
        'save_log': True,

        'params': {
            # === SYNC MODE ===
            'sync_mode': True,              # KEY: ROC*ROC instead of ROC*(-ROC)

            # === ROC SETTINGS ===
            'roc_period_primary': 5,
            'roc_period_reference': 5,
            'harmony_scale': 10000,

            # === ENTRY SYSTEM: KAMA Cross + Angle Confirmation ===
            'allowed_cross_bars': [],       # Empty = all bars allowed (exploratory)
            'entry_roc_angle_min': 5.0,
            'entry_roc_angle_max': 80.0,
            'entry_harmony_angle_min': 5.0,
            'entry_harmony_angle_max': 80.0,
            'roc_angle_scale': 1.0,
            'harmony_angle_scale': 1.0,

            # === KAMA SETTINGS ===
            'kama_period': 10,
            'kama_fast': 2,
            'kama_slow': 30,

            # === ATR for SL/TP ===
            'atr_length': 10,
            'atr_sl_multiplier': 5.0,
            'atr_tp_multiplier': 10.0,

            # === FILTERS (wide open for initial exploration) ===
            'use_time_filter': False,
            'allowed_hours': [],

            'use_day_filter': True,           # Always filter weekends in forex
            'allowed_days': [0, 1, 2, 3, 4],

            'use_sl_pips_filter': False,
            'sl_pips_min': 10,
            'sl_pips_max': 80,

            'use_atr_filter': False,
            'atr_min': 0.01,
            'atr_max': 0.15,
            'atr_avg_period': 20,

            # Asset config
            'pip_value': 0.01,
            'is_jpy_pair': True,
            'lot_size': 100000,
            'jpy_rate': 150.0,
            'is_etf': False,
            'margin_pct': 3.33,

            # Risk
            'risk_percent': 0.01,

            # Debug & Reporting
            'print_signals': False,
            'export_reports': True,

            # Plot options
            'plot_roc_multiplier': 500,
            'plot_harmony_multiplier': 15.0,
        }
    },

    # =========================================================================
    # CERES - Opening Range + Pullback + Breakout (Intraday ETF)
    # =========================================================================

    'GLD_CERES': {
        'active': False,
        'strategy_name': 'CERES',
        'asset_name': 'GLD',
        'data_path': 'data/GLD_5m_5Yea.csv',

        'from_date': datetime.datetime(2020, 1, 1),
        'to_date': datetime.datetime(2023, 12, 31),

        'starting_cash': 100000.0,

        'run_plot': False,
        'generate_report': True,
        'save_log': True,
        'debug_mode': False,

        'params': {
            # Consolidation Window
            'delay_bars': 0,
            'consolidation_bars': 15,

            # Window Quality Filters
            'use_window_height_filter': True,
            'window_height_min': 50.0,
            'window_height_max': 100.0,

            'use_window_er_filter': True,
            'window_er_min': 0.0,
            'window_er_max': 0.30,

            'use_window_atr_filter': False,
            'window_atr_min': 0.0,
            'window_atr_max': 9999.0,

            'use_er_htf_filter': False,
            'er_htf_threshold': 0.35,
            'er_htf_period': 10,
            'er_htf_timeframe_minutes': 15,

            # Scan / Armed limits
            'use_max_scan_bars': False,
            'min_scan_bars': 0,
            'max_scan_bars': 50,
            'use_max_armed_bars': False,
            'min_armed_bars': 0,
            'max_armed_bars': 30,

            # Breakout
            'use_body_breakout': False,
            'breakout_offset_mult': 0.0,
            'use_bk_candle_filter': False,
            'bk_candle_min': 0.0,
            'bk_candle_max': 9999.0,
            'use_bk_ratio_filter': False,
            'bk_ratio_min': 0.0,
            'bk_ratio_max': 1.0,

            # Stop Loss
            'sl_mode': 'window_low',
            'sl_buffer_pips': 1.0,
            'sl_fixed_pips': 30.0,
            'sl_atr_mult': 3.0,

            # Take Profit
            'tp_mode': 'window_height_mult',
            'tp_window_mult': 1.5,
            'tp_fixed_pips': 50.0,
            'tp_atr_mult': 8.0,

            # EOD Close (UTC, standard time; DST auto-adjusts -1h)
            'use_eod_close': True,
            'eod_close_hour': 20,
            'eod_close_minute': 45,

            # Standard Filters
            'use_time_filter': False,
            'allowed_hours': [],
            'use_day_filter': False,
            'allowed_days': [0, 1, 2, 3, 4],

            'use_sl_pips_filter': True,
            'sl_pips_min': 60.0,
            'sl_pips_max': 110.0,

            # ATR
            'atr_length': 14,
            'atr_avg_period': 20,

            # Risk management
            'risk_percent': 0.01,
            'pip_value': 0.01,
            'lot_size': 1,
            'jpy_rate': 1.0,
            'is_etf': True,
            'margin_pct': 20.0,

            # Debug
            'print_signals': False,
            'export_reports': True,
            'plot_entry_exit_lines': False,
        }
    },

    'TLT_CERES': {
        'active': False,
        'strategy_name': 'CERES',
        'asset_name': 'TLT',
        'data_path': 'data/TLT_5m_5Yea.csv',

        'from_date': datetime.datetime(2020, 1, 1),
        'to_date': datetime.datetime(2023, 12, 31),

        'starting_cash': 100000.0,

        'run_plot': False,
        'generate_report': True,
        'save_log': True,
        'debug_mode': False,

        'params': {
            # Consolidation Window (v1.0)
            'delay_bars': 0,
            'consolidation_bars': 15,

            # Window Quality Filters (ALL OFF for baseline)
            'use_window_height_filter': False,
            'window_height_min': 10.0,
            'window_height_max': 200.0,

            'use_window_er_filter': False,
            'window_er_min': 0.0,
            'window_er_max': 0.9,

            'use_window_atr_filter': False,
            'window_atr_min': 0.0,
            'window_atr_max': 9999.0,

            'use_er_htf_filter': False,
            'er_htf_threshold': 0.35,
            'er_htf_period': 10,
            'er_htf_timeframe_minutes': 15,

            # Scan / Armed limits
            'use_max_scan_bars': False,
            'min_scan_bars': 0,
            'max_scan_bars': 50,
            'use_max_armed_bars': False,
            'min_armed_bars': 0,
            'max_armed_bars': 30,

            # Breakout
            'use_body_breakout': False,
            'breakout_offset_mult': 0.0,
            'use_bk_candle_filter': False,
            'bk_candle_min': 0.0,
            'bk_candle_max': 9999.0,
            'use_bk_ratio_filter': False,
            'bk_ratio_min': 0.0,
            'bk_ratio_max': 1.0,

            # Stop Loss
            'sl_mode': 'window_low',
            'sl_buffer_pips': 1.0,
            'sl_fixed_pips': 30.0,
            'sl_atr_mult': 3.0,

            # Take Profit
            'tp_mode': 'none',
            'tp_window_mult': 1.5,
            'tp_fixed_pips': 50.0,
            'tp_atr_mult': 10.0,

            # EOD Close (UTC, standard time; DST auto-adjusts -1h)
            'use_eod_close': True,
            'eod_close_hour': 20,
            'eod_close_minute': 45,

            # Standard Filters
            'use_time_filter': False,
            'allowed_hours': [],
            'use_day_filter': False,
            'allowed_days': [0, 1, 2, 3, 4],

            'use_sl_pips_filter': False,
            'sl_pips_min': 5.0,
            'sl_pips_max': 220.0,

            # ATR
            'atr_length': 14,
            'atr_avg_period': 20,

            # Risk management
            'risk_percent': 0.01,
            'pip_value': 0.01,
            'lot_size': 1,
            'jpy_rate': 1.0,
            'is_etf': True,
            'margin_pct': 20.0,

            # Debug
            'print_signals': False,
            'export_reports': True,
            'plot_entry_exit_lines': False,
        }
    },

    'DIA_CERES': {
        'active': False,
        'strategy_name': 'CERES',
        'asset_name': 'DIA',
        'data_path': 'data/DIA_5m_5Yea.csv',

        'from_date': datetime.datetime(2021, 1, 1),
        'to_date': datetime.datetime(2021, 12, 1),

        'starting_cash': 100000.0,

        'run_plot': False,
        'generate_report': True,
        'save_log': True,
        'debug_mode': False,

        'params': {
            # Consolidation Window (v1.0)
            'delay_bars': 0,
            'consolidation_bars': 10,

            # Window Quality Filters (ALL OFF for baseline)
            'use_window_height_filter': True,
            'window_height_min': 100.0,
            'window_height_max': 150.0,

            'use_window_er_filter': False,
            'window_er_min': 0.00,
            'window_er_max': 0.30,

            'use_window_atr_filter': False,
            'window_atr_min': 0.3,
            'window_atr_max': 0.6,

            'use_er_htf_filter': False,
            'er_htf_threshold': 0.35,
            'er_htf_period': 10,
            'er_htf_timeframe_minutes': 15,

            # Scan / Armed limits
            'use_max_scan_bars': True,
            'min_scan_bars': 35,
            'max_scan_bars': 55,
            'use_max_armed_bars': False,
            'min_armed_bars': 7,
            'max_armed_bars': 17,

            # Breakout
            'use_body_breakout': False,
            'breakout_offset_mult': 0.25,
            'use_bk_candle_filter': False,
            'bk_candle_min': 20.0,
            'bk_candle_max': 40.0,
            'use_bk_ratio_filter': False,
            'bk_ratio_min': 0.25,
            'bk_ratio_max': 0.50,

            # Stop Loss
            'sl_mode': 'atr_mult',
            'sl_buffer_pips': 1.0,
            'sl_fixed_pips': 30.0,
            'sl_atr_mult': 2.0,

            # Take Profit
            'tp_mode': 'atr_mult',
            'tp_window_mult': 1.5,
            'tp_fixed_pips': 50.0,
            'tp_atr_mult': 5.0,

            # EOD Close (UTC, standard time; DST auto-adjusts -1h)
            'use_eod_close': True,
            'eod_close_hour': 20,
            'eod_close_minute': 45,

            # Standard Filters (ALL OFF for baseline)
            'use_time_filter': False,
            'allowed_hours': [16, 18, 19, 20],
            'use_day_filter': False,
            'allowed_days': [1, 2, 3, 4],

            'use_sl_pips_filter': False,
            'sl_pips_min': 70.0,
            'sl_pips_max': 200.0,

            # ATR
            'atr_length': 14,
            'atr_avg_period': 20,

            # Risk management
            'risk_percent': 0.01,
            'pip_value': 0.01,
            'lot_size': 1,
            'jpy_rate': 1.0,
            'is_etf': True,
            'margin_pct': 20.0,

            # Debug
            'print_signals': False,
            'export_reports': True,
            'plot_entry_exit_lines': False,
        }
    },

    'XLE_CERES': {
        'active': False,
        'strategy_name': 'CERES',
        'asset_name': 'XLE',
        'data_path': 'data/XLE_5m_5Yea.csv',

        'from_date': datetime.datetime(2020, 1, 1),
        'to_date': datetime.datetime(2025, 12, 1),

        'starting_cash': 100000.0,

        'run_plot': False,
        'generate_report': True,
        'save_log': True,
        'debug_mode': False,

        'params': {
            # Consolidation Window (v1.0)
            'delay_bars': 0,
            'consolidation_bars': 12,

            # Window Quality Filters (ALL OFF for baseline)
            'use_window_height_filter': False,
            'window_height_min': 10.0,
            'window_height_max': 9999.0,

            'use_window_er_filter': False,
            'window_er_min': 0.0,
            'window_er_max': 1.0,

            'use_window_atr_filter': False,
            'window_atr_min': 0.0,
            'window_atr_max': 9999.0,

            'use_er_htf_filter': False,
            'er_htf_threshold': 0.35,
            'er_htf_period': 10,
            'er_htf_timeframe_minutes': 15,

            # Scan / Armed limits
            'use_max_scan_bars': False,
            'min_scan_bars': 0,
            'max_scan_bars': 50,
            'use_max_armed_bars': False,
            'min_armed_bars': 0,
            'max_armed_bars': 30,

            # Breakout
            'use_body_breakout': False,
            'breakout_offset_mult': 0.0,
            'use_bk_candle_filter': False,
            'bk_candle_min': 0.0,
            'bk_candle_max': 9999.0,
            'use_bk_ratio_filter': False,
            'bk_ratio_min': 0.0,
            'bk_ratio_max': 1.0,

            # Stop Loss
            'sl_mode': 'window_low',
            'sl_buffer_pips': 1.0,
            'sl_fixed_pips': 30.0,
            'sl_atr_mult': 3.0,

            # Take Profit
            'tp_mode': 'none',
            'tp_window_mult': 1.5,
            'tp_fixed_pips': 50.0,
            'tp_atr_mult': 10.0,

            # EOD Close (UTC, standard time; DST auto-adjusts -1h)
            'use_eod_close': True,
            'eod_close_hour': 20,
            'eod_close_minute': 45,

            # Standard Filters (ALL OFF)
            'use_time_filter': False,
            'allowed_hours': [],
            'use_day_filter': False,
            'allowed_days': [0, 1, 2, 3, 4],

            'use_sl_pips_filter': False,
            'sl_pips_min': 5.0,
            'sl_pips_max': 500.0,

            # ATR
            'atr_length': 14,
            'atr_avg_period': 20,

            # Risk management
            'risk_percent': 0.01,
            'pip_value': 0.01,
            'lot_size': 1,
            'jpy_rate': 1.0,
            'is_etf': True,
            'margin_pct': 20.0,

            # Debug
            'print_signals': False,
            'export_reports': True,
            'plot_entry_exit_lines': False,
        }
    },

    # =================================================================
    # CERES — FOREX (XAUUSD with EOD close to avoid swap)
    # =================================================================

    'XAUUSD_CERES': {
        'active': False,
        'strategy_name': 'CERES',
        'asset_name': 'XAUUSD',
        'data_path': 'data/XAUUSD_5m_5Yea.csv',

        'from_date': datetime.datetime(2020, 1, 1),
        'to_date': datetime.datetime(2023, 12, 31),

        'starting_cash': 100000.0,

        'run_plot': False,
        'generate_report': True,
        'save_log': True,
        'debug_mode': False,

        'params': {
            # Consolidation Window (v1.0)
            'delay_bars': 0,
            'consolidation_bars': 10,

            # Window Quality Filters (ALL OFF for baseline)
            'use_window_height_filter': True,
            'window_height_min': 250.0,
            'window_height_max': 300.0,

            'use_window_er_filter': False,
            'window_er_min': 0.0,
            'window_er_max': 1.0,

            'use_window_atr_filter': False,
            'window_atr_min': 0.0,
            'window_atr_max': 9999.0,

            'use_er_htf_filter': False,
            'er_htf_threshold': 0.35,
            'er_htf_period': 10,
            'er_htf_timeframe_minutes': 60,

            # Scan / Armed limits
            'use_max_scan_bars': False,
            'min_scan_bars': 45,
            'max_scan_bars': 50,
            'use_max_armed_bars': False,
            'min_armed_bars': 0,
            'max_armed_bars': 30,

            # Breakout
            'use_body_breakout': False,
            'breakout_offset_mult': 0.0,
            'use_bk_candle_filter': False,
            'bk_candle_min': 40.0,
            'bk_candle_max': 80.0,
            'use_bk_ratio_filter': True,
            'bk_ratio_min': 0.0,
            'bk_ratio_max': 0.25,

            # Stop Loss
            'sl_mode': 'atr_mult',
            'sl_buffer_pips': 100.0,
            'sl_fixed_pips': 500.0,
            'sl_atr_mult': 3.0,

            # Take Profit
            'tp_mode': 'atr_mult',
            'tp_window_mult': 1.5,
            'tp_fixed_pips': 1000.0,
            'tp_atr_mult': 8.0,

            # EOD Close (UTC, before 22:00 rollover to avoid swap)
            'use_eod_close': True,
            'eod_close_hour': 21,
            'eod_close_minute': 45,

            # Standard Filters
            'use_time_filter': False,
            'allowed_hours': [],
            'use_day_filter': False,
            'allowed_days': [0, 1, 2, 3, 4],

            'use_sl_pips_filter': False,
            'sl_pips_min': 0.0,
            'sl_pips_max': 9999.0,

            # ATR
            'atr_length': 14,
            'atr_avg_period': 20,

            # Risk management
            'risk_percent': 0.01,

            # XAUUSD: 1 lot = 100 oz, pip = $0.01, margin 5% (20:1)
            'pip_value': 0.01,
            'lot_size': 100,
            'jpy_rate': 1.0,
            'is_etf': False,
            'leverage': 20.0,

            # Debug
            'print_signals': False,
            'export_reports': True,
            'plot_entry_exit_lines': False,
        }
    },

    # =========================================================================
    # LUYTEN (Opening Range Breakout simplified)
    # =========================================================================
    #
    'AUS200_LUYTEN': {
        'active': False,
        'strategy_name': 'LUYTEN',
        'asset_name': 'AUS200',
        'data_path': 'data/AUS200_5m_5Yea.csv',

        'from_date': datetime.datetime(2024, 1, 1),
        'to_date': datetime.datetime(2025, 12, 1),

        'starting_cash': 100000.0,

        'run_plot': True,
        'generate_report': True,
        'save_log': True,
        'debug_mode': False,

        # Override broker config for CFD index (AUS200 Darwinex Zero)
        'broker_config_key': 'darwinex_zero_cfd_index',

        'params': {
            # Session start -- 08:00 UTC winter / 07:00 UTC BST (auto via london_uk DST)
            'session_start_hour': 12,
            'session_start_minute': 00,
            'dst_mode': 'london_uk',  # shift -1h during UK BST (late Mar - late Oct)

            # Consolidation range (min-max bars to reduce overfitting)
            'consolidation_bars_min': 2,
            'consolidation_bars_max': 2,

            # Breakout filters -- scaled from TLT (pip_value=1.0 vs 0.01)
            # TLT bk_above=6 pips * 0.01 = $0.06 on ~$100 = 0.06%
            # AUS200 0.06% of ~8000 = ~5 pts
            'bk_above_min_pips': 0.0,
            'bk_body_min_pips': 0.0,

            # Multi-timeframe
            # base_timeframe_minutes: resample primary feed (0 or 5 = keep 5m)
            # htf_data_minutes: secondary HTF feed for filters (0 = disabled)
            'base_timeframe_minutes': 15,
            'htf_data_minutes': 60,  # 30m HTF for additional filter signals
            'use_htf_roc_filter': False,
            'htf_roc_period': 5,

            # SL / TP -- ATR multipliers (same ratios as TLT)
            'atr_sl_multiplier': 2.0,
            'atr_tp_multiplier': 3.0,
            'sl_buffer_pips': 0.0,

            # EOD Close (UTC) -- AUS200 gap starts 19:55 (AU summer) / 20:55 (AU winter)
            'use_eod_close': False,
            'eod_close_hour': 19,
            'eod_close_minute': 30,

            # ATR
            'atr_length': 14,
            'atr_avg_period': 20,

            # Standard Filters -- start permissive, optimize later
            'use_time_filter': False,
            'allowed_hours': [],
            'use_day_filter': False,
            'allowed_days': [0, 1, 2, 3, 4],

            # SL pips filter -- scaled from TLT
            # TLT: 10-100 pips * 0.01 = 0.10-1.00 (0.1%-1.0% of ~$100)
            # AUS200: 0.1%-1.0% of ~8000 = 8-80 pts
            'use_sl_pips_filter': False,
            'sl_pips_min': 10.0,
            'sl_pips_max': 800.0,

            # ATR Range Filter -- scaled from TLT
            # TLT: 0.12-0.22 on ~$100 price = 0.12%-0.22%
            # AUS200: 0.12%-0.22% of ~8000 = ~10-18 pts
            'use_atr_range_filter': False,
            'atr_range_min': 12.0,
            'atr_range_max': 18.0,

            # Consolidation Price Filter
            # Skip day if price at consol_start < price at session_start
            'use_consol_price_filter': False,

            # Risk management
            'risk_percent': 0.01,

            # CFD index config
            'pip_value': 1.0,
            'lot_size': 1,
            'jpy_rate': 1.0,
            'is_etf': True,
            'margin_pct': 5.0,

            # Debug
            'print_signals': False,
            'export_reports': True,
        }
    },

    'XLE_LUYTEN': {
        'active': False,
        'strategy_name': 'LUYTEN',
        'asset_name': 'XLE',
        'data_path': 'data/XLE_5m_5Yea.csv',

        'from_date': datetime.datetime(2020, 1, 1),
        'to_date': datetime.datetime(2020, 2, 29),

        'starting_cash': 100000.0,

        'run_plot': True,
        'generate_report': True,
        'save_log': True,
        'debug_mode': False,

        'params': {
            # Session start -- NYSE open 14:30 UTC winter / 13:30 UTC summer
            'session_start_hour': 15,
            'session_start_minute': 15,
            'dst_mode': 'nyse',

            # Consolidation range
            'consolidation_bars_min': 6,
            'consolidation_bars_max': 10,

            # Breakout filters
            'bk_above_min_pips': 0.0,
            'bk_body_min_pips': 0.0,

            # Multi-timeframe
            'base_timeframe_minutes': 5,
            'htf_data_minutes': 0,
            'use_htf_roc_filter': False,
            'htf_roc_period': 5,

            # SL / TP
            'atr_sl_multiplier': 2.0,
            'atr_tp_multiplier': 3.0,
            'sl_buffer_pips': 0.0,

            # EOD Close -- NYSE close 21:00 UTC winter / 20:00 UTC summer
            'use_eod_close': True,
            'eod_close_hour': 20,
            'eod_close_minute': 00,

            # ATR
            'atr_length': 14,
            'atr_avg_period': 20,

            # Filters
            'use_time_filter': False,
            'allowed_hours': [],
            'use_day_filter': False,
            'allowed_days': [0, 1, 2, 3, 4],
            'use_sl_pips_filter': False,
            'sl_pips_min': 0.0,
            'sl_pips_max': 9999.0,
            'use_atr_range_filter': False,
            'atr_range_min': 0.0,
            'atr_range_max': 999.0,
            'use_consol_price_filter': False,

            # Risk management
            'risk_percent': 0.01,

            # ETF config -- XLE ~$60, same as TLT structure
            'pip_value': 0.01,
            'lot_size': 1,
            'jpy_rate': 1.0,
            'is_etf': True,
            'margin_pct': 20.0,

            # Debug
            'print_signals': False,
            'export_reports': True,
        }
    },

    # =========================================================================
    # LUYTEN — XAUUSD  (valley 21:45 → bull explosion 22:00 UTC, DirZ +2.79)
    # =========================================================================

    'XAUUSD_LUYTEN': {
        'active': False,
        'strategy_name': 'LUYTEN',
        'asset_name': 'XAUUSD',
        'data_path': 'data/XAUUSD_5m_5Yea.csv',

        'from_date': datetime.datetime(2020, 1, 1),
        'to_date': datetime.datetime(2023, 12, 31),

        'starting_cash': 100000.0,

        'run_plot': False,
        'generate_report': True,
        'save_log': True,
        'debug_mode': False,

        'params': {
            # Session start -- gold daily reopen after 1h gap
            # Winter: gap 22:00-22:59, reopen 23:00 → session_start 23:00
            # Summer (DST): gap 21:00-21:59, reopen 22:00 → shift -1h via nyse
            # Valley pre-gap: 21:45 winter / 20:45 summer (8.67 bps, cold)
            # Explosion post-gap: 23:00 winter / 22:00 summer (17.21 bps, 65.4% bull)
            'session_start_hour': 21,
            'session_start_minute': 0,
            'dst_mode': 'us',  # shift -1h during US DST (2nd Sun Mar .. 1st Sun Nov)

            # Consolidation range
            'consolidation_bars_min': 3,   # 15 min minimum (3x5m)
            'consolidation_bars_max': 6,   # 30 min maximum (6x5m)

            # Breakout filters -- off for baseline
            'bk_above_min_pips': 0.0,
            'bk_body_min_pips': 0.0,

            # Multi-timeframe
            'base_timeframe_minutes': 5,
            'htf_data_minutes': 0,
            'use_htf_roc_filter': False,
            'htf_roc_period': 5,

            # SL / TP
            'atr_sl_multiplier': 5.0,
            'atr_tp_multiplier': 10.0,   # asymmetric R:R for gold momentum
            'sl_buffer_pips': 0.0,

            # EOD Close -- before next 22:00 rollover (swap -$75/lot/day)
            'use_eod_close': True,
            'eod_close_hour': 22,
            'eod_close_minute': 15,

            # ATR
            'atr_length': 14,
            'atr_avg_period': 20,

            # Standard Filters -- all off for baseline
            'use_time_filter': False,
            'allowed_hours': [],
            'use_day_filter': False,
            'allowed_days': [0, 1, 2, 3, 4],
            'use_sl_pips_filter': False,
            'sl_pips_min': 0.0,
            'sl_pips_max': 9999.0,
            'use_atr_range_filter': False,
            'atr_range_min': 0.0,
            'atr_range_max': 999.0,
            'use_consol_price_filter': False,

            # Risk management
            'risk_percent': 0.01,

            # XAUUSD: 1 lot = 100 oz, pip = $0.01, margin 5% (20:1)
            'pip_value': 0.01,
            'lot_size': 100,
            'jpy_rate': 1.0,
            'is_etf': False,
            'margin_pct': 5.0,

            # Debug
            'print_signals': False,
            'export_reports': True,
        }
    },

    # =========================================================================
    # LUYTEN -- SP500  (valley 02:00-05:00 UTC -> London/US explosion)
    #
    # Liquidity profile data:
    #   Valley 02:00-05:00: range ~11.5 pts (27 bps), z-score -0.50
    #   Explosions: 07:00 London +15 bps, 13:30 US open +30.7 bps
    #   Direction: 52.7% Long / 47.1% Short -> NEUTRAL -> BOTH required
    #   Spread 0.6 pts -> 17x ratio -> negligible
    #   Expansion: @1h 3.5pts, @2h 5.7pts, @4h 10.1pts, @8h 15.4pts
    #   Breakout delay: median 40 min, mean 60 min
    #   ATR(14) @5m in valley ~2-3 pts -> mult 5 ~11.5 pts ~valley range
    # =========================================================================

    # --- A) 5m, valley=consolidation, BOTH, SL=5x TP=8x (R:R~1.6) ---
    # Full valley 02:00-05:00 = consolidation (36 bars x 5m)
    # SL 5xATR ~11.5 pts (= valley range), TP 8xATR ~20 pts (8h horizon)
    'SP500_LUYTEN_A_5m_BOTH': {
        'active': True,
        'strategy_name': 'LUYTEN',
        'asset_name': 'SP500',
        'data_path': 'data/SP500_5m_5Yea.csv',

        'from_date': datetime.datetime(2020, 1, 1),
        'to_date': datetime.datetime(2023, 12, 20),

        'starting_cash': 100000.0,

        'run_plot': True,
        'generate_report': True,
        'save_log': True,
        'debug_mode': False,

        'broker_config_key': 'darwinex_zero_cfd_sp500',

        'params': {
            # Session start = valley start (winter 02:00 / summer 01:00 via US DST)
            'session_start_hour': 2,
            'session_start_minute': 0,
            'dst_mode': 'us',  # CME shifts -1h in summer (gap 22->21 UTC)

            # 36 bars x 5m = 3h (02:00-05:00 winter / 01:00-04:00 summer)
            'consolidation_bars_min': 0,
            'consolidation_bars_max': 36,

            'bk_above_min_pips': 0.0,
            'bk_body_min_pips': 0.0,

            'base_timeframe_minutes': 5,
            'htf_data_minutes': 0,
            'use_htf_roc_filter': False,
            'htf_roc_period': 5,

            # SL 5xATR ~valley range; TP 8xATR -> 8h horizon (15+ pts)
            'atr_sl_multiplier': 3.0,
            'atr_tp_multiplier': 8.0,
            'sl_buffer_pips': 0.0,

            # EOD: winter 21:00 / summer 20:00 (auto via US DST)
            'use_eod_close': True,
            'eod_close_hour': 21,
            'eod_close_minute': 0,

            'atr_length': 14,
            'atr_avg_period': 20,

            'use_time_filter': False,
            'allowed_hours': [],
            'use_day_filter': False,
            'allowed_days': [0, 1, 2, 3, 4],
            'use_sl_pips_filter': False,
            'sl_pips_min': 0.0,
            'sl_pips_max': 9999.0,
            'use_atr_range_filter': False,
            'atr_range_min': 0.0,
            'atr_range_max': 999.0,
            'use_consol_price_filter': False,

            # BOTH -- data says 52.7/47.1, no directional bias
            'enable_long': True,
            'enable_short': False,

            'risk_percent': 0.01,

            'pip_value': 1.0,
            'lot_size': 1,
            'jpy_rate': 1.0,
            'is_etf': True,
            'margin_pct': 5.0,

            'print_signals': False,
            'export_reports': True,
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
    },
    'darwinex_zero_cfd_index': {
        # AUS200: 2.75 AUD/order/contract, contract=10xIndex
        # Per BT unit (1 index point): 2.75/10 = 0.275 AUD per order
        'commission_per_contract': 0.275,
        'leverage': 20.0,
        'margin_percent': 5.0,
    },
    'darwinex_zero_cfd_sp500': {
        # SP500: 0.275 USD/order/contract, contract=10xIndex
        # Per BT unit (1 index point): 0.275/10 = 0.0275 USD per order
        'commission_per_contract': 0.0275,
        'leverage': 20.0,
        'margin_percent': 5.0,
    },
}
