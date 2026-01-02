"""
Central configuration for all strategies and assets.
Parameters match EXACTLY sunrise_ogle_eurjpy_pro.py
"""
import datetime

STRATEGIES_CONFIG = {
    'EURJPY_PRO': {
        'active': True,
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
            
            # Angle settings
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
            
            # Time filter - List of allowed hours (UTC)
            # Original range 5:00-18:00 means trading until 17:59
            'use_time_filter': True,
            'allowed_hours': [5, 6, 7, 8, 9, 12, 13, 15, 16, 17],
            
            # SL pips filter - Filters trades by stop loss size in pips
            # Useful for avoiding trades with too tight or too wide stops
            'use_sl_pips_filter': False,
            'sl_pips_min': 20.0,
            'sl_pips_max': 50.0,
            
            # Risk management
            'risk_percent': 0.003,
            
            # JPY pair settings
            'is_jpy': True,
            'jpy_rate': 150.0,
            'lot_size': 100000,
            'pip_value': 0.01,
            
            # Debug
            'print_signals': True,
        }
    }
}

# Broker settings
BROKER_CONFIG = {
    'darwinex_zero': {
        'commission_per_lot': 2.50,
        'leverage': 30.0,
        'margin_percent': 3.33,
    }
}