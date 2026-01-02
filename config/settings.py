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
        
        'from_date': datetime.datetime(2024, 7, 1),
        'to_date': datetime.datetime(2025, 7, 1),
        
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
            'atr_min': 0.030,
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
            
            # Time filter (5:00-18:00 UTC)
            'time_start_hour': 5,
            'time_start_minute': 0,
            'time_end_hour': 18,
            'time_end_minute': 0,
            
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