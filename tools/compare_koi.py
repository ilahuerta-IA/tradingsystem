"""Comparar configuraciones por activo (OGLE, KOI, SEDNA)"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import STRATEGIES_CONFIG

# Agrupar por activo
assets = {}
for name, cfg in STRATEGIES_CONFIG.items():
    asset = cfg['asset_name']
    if asset not in assets:
        assets[asset] = {}
    strategy = cfg['strategy_name']
    assets[asset][name] = cfg['params']

print('=== COMPARACIÓN POR ACTIVO ===\n')

for asset in ['USDJPY', 'EURJPY', 'EURUSD', 'USDCHF']:
    if asset not in assets:
        continue
    print(f'{"="*60}')
    print(f'{asset}')
    print(f'{"="*60}')
    for config_name, p in assets[asset].items():
        print(f'\n  {config_name}:')
        print(f'    pip_value: {p.get("pip_value")}')
        print(f'    jpy_rate: {p.get("jpy_rate")}')
        print(f'    SL pips: {p.get("use_sl_pips_filter")} -> {p.get("sl_pips_min")}-{p.get("sl_pips_max")}')
        print(f'    ATR filter: {p.get("use_atr_filter")} -> {p.get("atr_min")}-{p.get("atr_max")}')
        print(f'    SL mult: {p.get("atr_sl_multiplier", p.get("sl_mult"))}, TP mult: {p.get("atr_tp_multiplier", p.get("tp_mult"))}')
    print()
