"""
Backtest execution entry point.
Orchestrates data loading, strategy initialization, and result reporting.
Replicates exactly the behavior of sunrise_ogle_eurjpy_pro.py
"""
import sys
from datetime import datetime
from pathlib import Path

import backtrader as bt

from config.settings import STRATEGIES_CONFIG, BROKER_CONFIG
from strategies.sunset_ogle import SunsetOgleStrategy
from lib.commission import ForexCommission


def run_backtest(config_name):
    """
    Execute backtest for specified configuration.
    """
    if config_name not in STRATEGIES_CONFIG:
        print(f'Configuration not found: {config_name}')
        return None
    
    config = STRATEGIES_CONFIG[config_name]
    
    if not config.get('active', False):
        print(f'Configuration {config_name} is not active')
        return None
    
    print('=' * 70)
    print(f'BACKTEST: {config_name}')
    print(f'Asset: {config["asset_name"]}')
    print(f'Period: {config["from_date"]} to {config["to_date"]}')
    print('=' * 70)
    
    # Initialize Cerebro (no standard stats like original)
    cerebro = bt.Cerebro(stdstats=False)
    
    # Load data using GenericCSVData (same as original)
    data_path = Path(config['data_path'])
    if not data_path.exists():
        print(f'Data file not found: {data_path}')
        return None
    
    # CSV format: Date,Time,Open,High,Low,Close,Volume (Darwinex format)
    # Same as original sunrise_ogle_eurjpy_pro.py
    feed_kwargs = dict(
        dataname=str(data_path),
        dtformat='%Y%m%d',
        tmformat='%H:%M:%S',
        datetime=0,
        time=1,
        open=2,
        high=3,
        low=4,
        close=5,
        volume=6,
        timeframe=bt.TimeFrame.Minutes,
        compression=5,
        fromdate=config['from_date'],
        todate=config['to_date'],
    )
    
    data = bt.feeds.GenericCSVData(**feed_kwargs)
    cerebro.adddata(data, name=config['asset_name'])
    
    print(f'Loaded data from {data_path}')
    
    # Set broker
    cerebro.broker.setcash(config.get('starting_cash', 100000.0))
    
    # Set commission scheme (same as original)
    params = config['params']
    broker_config = BROKER_CONFIG['darwinex_zero']
    
    is_jpy = params.get('is_jpy', False)
    commission = ForexCommission(
        commission=broker_config['commission_per_lot'],
        is_jpy_pair=is_jpy,
        jpy_rate=params.get('jpy_rate', 150.0) if is_jpy else 1.0,
    )
    cerebro.broker.addcommissioninfo(commission)
    
    # Add strategy with parameters
    cerebro.addstrategy(SunsetOgleStrategy, **params)
    
    # Add observers
    try:
        cerebro.addobserver(bt.observers.BuySell, barplot=False)
        cerebro.addobserver(bt.observers.Value)
    except Exception:
        pass
    
    # Run backtest
    print(f'\nStarting Cash: ${cerebro.broker.getvalue():,.2f}')
    print('Running backtest...\n')
    
    results = cerebro.run()
    strategy = results[0]
    
    # Final results
    final_value = cerebro.broker.getvalue()
    starting_cash = config.get('starting_cash', 100000.0)
    total_return = ((final_value / starting_cash) - 1) * 100
    
    print(f'\nFinal Value: ${final_value:,.2f}')
    print(f'Return: {total_return:.2f}%')
    
    # Save log if enabled
    if config.get('save_log', False):
        save_trade_log(strategy, config_name, config['asset_name'])
    
    # Plot if enabled
    if config.get('run_plot', False):
        cerebro.plot(style='candlestick')
    
    return results


def save_trade_log(strategy, config_name, asset_name):
    """Save trade log to file using trade_reports from strategy."""
    logs_dir = Path('logs')
    logs_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'{asset_name}_PRO_{timestamp}.txt'
    filepath = logs_dir / filename
    
    # Use trade_reports from strategy (new format)
    trade_reports = getattr(strategy, 'trade_reports', [])
    
    with open(filepath, 'w') as f:
        f.write(f'=== TRADE LOG: {asset_name} ===\n')
        f.write(f'Generated: {datetime.now()}\n')
        f.write(f'Configuration: {config_name}\n\n')
        
        for i, trade in enumerate(trade_reports, 1):
            f.write(f'Trade #{i}\n')
            f.write(f'  Entry: {trade.get("entry_time", "N/A")}\n')
            f.write(f'  Exit: {trade.get("exit_time", "N/A")}\n')
            f.write(f'  P&L: ${trade.get("pnl", 0):.2f}\n')
            f.write('-' * 40 + '\n')
        
        total_pnl = sum(t.get('pnl', 0) for t in trade_reports)
        f.write(f'\nTotal Trades: {len(trade_reports)}\n')
        f.write(f'Total P&L: ${total_pnl:.2f}\n')
    
    print(f'\nTrade log saved: {filepath}')


if __name__ == '__main__':
    config_to_run = 'EURJPY_PRO'
    
    if len(sys.argv) > 1:
        config_to_run = sys.argv[1]
    
    run_backtest(config_to_run)