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
from strategies.koi_strategy import KOIStrategy
from lib.commission import ForexCommission


# Strategy registry
STRATEGY_REGISTRY = {
    'SunsetOgle': SunsetOgleStrategy,
    'KOI': KOIStrategy,
}


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
    
    # Auto-detect JPY pair from asset name
    asset_name = config['asset_name']
    is_jpy = asset_name.upper().endswith('JPY')
    
    # Reset commission counters before run
    ForexCommission.total_commission = 0.0
    ForexCommission.total_lots = 0.0
    ForexCommission.commission_calls = 0
    
    commission = ForexCommission(
        commission=broker_config['commission_per_lot'],
        is_jpy_pair=is_jpy,
        jpy_rate=params.get('jpy_rate', 150.0) if is_jpy else 1.0,
    )
    cerebro.broker.addcommissioninfo(commission)
    
    # Get strategy class
    strategy_name = config.get('strategy_name', 'SunsetOgle')
    if strategy_name not in STRATEGY_REGISTRY:
        print(f'Strategy not found: {strategy_name}')
        print(f'Available: {list(STRATEGY_REGISTRY.keys())}')
        return None
    
    StrategyClass = STRATEGY_REGISTRY[strategy_name]
    
    # Auto-inject is_jpy_pair and pip_value into params
    params['is_jpy_pair'] = is_jpy
    if is_jpy:
        params['pip_value'] = 0.01
    else:
        params['pip_value'] = 0.0001
    
    # Add strategy with parameters
    cerebro.addstrategy(StrategyClass, **params)
    
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
    
    # Get commission statistics
    total_commission = ForexCommission.total_commission
    total_lots = ForexCommission.total_lots
    num_trades = len(getattr(strategy, 'trade_reports', []))
    avg_commission = total_commission / num_trades if num_trades > 0 else 0
    avg_lots = total_lots / num_trades if num_trades > 0 else 0
    
    # Print commission summary
    print('\n' + '=' * 70)
    print('COMMISSION SUMMARY')
    print('=' * 70)
    print(f'Total Commission Paid:    ${total_commission:,.2f}')
    print(f'Total Lots Traded:        {total_lots:,.2f}')
    print(f'Avg Commission per Trade: ${avg_commission:,.2f}')
    print(f'Avg Lots per Trade:       {avg_lots:,.2f}')
    print('=' * 70)
    
    print(f'\nFinal Value: ${final_value:,.2f}')
    print(f'Return: {total_return:.2f}%')
    
    # Save log if enabled (only for SunsetOgle, KOI generates its own)
    if config.get('save_log', False) and strategy_name == 'SunsetOgle':
        save_trade_log(strategy, config_name, config['asset_name'], 
                      total_commission, avg_commission, total_lots)
    
    # Plot if enabled
    if config.get('run_plot', False):
        cerebro.plot(style='candlestick')
    
    return results


def save_trade_log(strategy, config_name, asset_name, 
                   total_commission=0, avg_commission=0, total_lots=0):
    """Save detailed trade log to file using trade_reports from strategy."""
    logs_dir = Path('logs')
    logs_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'{asset_name}_PRO_{timestamp}.txt'
    filepath = logs_dir / filename
    
    # Use trade_reports from strategy
    trade_reports = getattr(strategy, 'trade_reports', [])
    
    # Get strategy params for configuration display
    p = strategy.params
    
    with open(filepath, 'w') as f:
        # Header
        f.write("=" * 80 + "\n")
        f.write(f"=== SUNRISE STRATEGY TRADE REPORT ===\n")
        f.write(f"Asset: {asset_name}\n")
        f.write(f"Generated: {datetime.now()}\n")
        f.write(f"Configuration: {config_name}\n")
        f.write(f"Trading Direction: LONG\n")
        f.write("=" * 80 + "\n\n")
        
        # Configuration parameters
        f.write("CONFIGURATION PARAMETERS:\n")
        f.write("-" * 30 + "\n")
        f.write("LONG Configuration:\n")
        f.write(f"  ATR Range: {p.atr_min:.6f} - {p.atr_max:.6f}\n")
        f.write(f"  Angle Range: {p.angle_min:.2f} to {p.angle_max:.2f} deg\n")
        f.write(f"  Candle Direction Filter: DISABLED\n")
        f.write(f"  Pullback Mode: True\n\n")
        
        f.write("Common Parameters:\n")
        f.write(f"  Risk Percent: {p.risk_percent * 100:.1f}%\n")
        
        # Time filter display
        if p.use_time_filter and hasattr(p, 'allowed_hours'):
            hours = list(p.allowed_hours)
            if hours:
                start_hour = min(hours)
                end_hour = max(hours) + 1
                f.write(f"  Trading Hours: {start_hour:02d}:00 - {end_hour:02d}:00 UTC\n")
        
        f.write(f"  Window Time Offset: DISABLED (Immediate window opening)\n")
        f.write(f"  LONG Stop Loss ATR Multiplier: {p.sl_mult}\n")
        f.write(f"  LONG Take Profit ATR Multiplier: {p.tp_mult}\n")
        
        # SL Pips filter
        if p.use_sl_pips_filter:
            f.write(f"  SL Pips Filter: ENABLED | Range: {p.sl_pips_min:.1f} - {p.sl_pips_max:.1f}\n")
        else:
            f.write(f"  SL Pips Filter: DISABLED\n")
        
        # Commission info
        f.write(f"\nCOMMISSION:\n")
        f.write(f"  Total Commission: ${total_commission:.2f}\n")
        f.write(f"  Avg per Trade: ${avg_commission:.2f}\n")
        f.write(f"  Total Lots: {total_lots:.2f}\n")
        
        f.write("\n" + "=" * 80 + "\n")
        f.write("TRADE DETAILS\n")
        f.write("=" * 80 + "\n\n")
        
        # Trade details
        for i, trade in enumerate(trade_reports, 1):
            # Entry section
            f.write(f"ENTRY #{i}\n")
            entry_time = trade.get('entry_time')
            if entry_time:
                f.write(f"Time: {entry_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            else:
                f.write(f"Time: N/A\n")
            
            f.write(f"Direction: {trade.get('direction', 'LONG')}\n")
            
            atr = trade.get('current_atr', 0)
            f.write(f"ATR Current: {atr:.6f}\n")
            
            angle = trade.get('current_angle', 0)
            f.write(f"Angle Current: {angle:.2f} deg\n")
            f.write(f"Angle Filter: ENABLED | Range: {p.angle_min:.1f}-{p.angle_max:.1f} deg | Valid: True\n")
            
            # SL Pips info
            sl_pips = trade.get('sl_pips', 0)
            if p.use_sl_pips_filter:
                f.write(f"SL Pips: {sl_pips:.1f} | Filter: ENABLED | Range: {p.sl_pips_min:.1f}-{p.sl_pips_max:.1f}\n")
            else:
                f.write(f"SL Pips: {sl_pips:.1f} | Filter: DISABLED\n")
            
            bars_to_entry = trade.get('bars_to_entry', 0)
            f.write(f"Bars to Entry: {bars_to_entry}\n")
            f.write("-" * 50 + "\n\n")
            
            # Exit section
            f.write(f"EXIT #{i}\n")
            exit_time = trade.get('exit_time')
            if exit_time:
                f.write(f"Time: {exit_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            else:
                f.write(f"Time: N/A\n")
            
            f.write(f"Exit Reason: {trade.get('exit_reason', 'N/A')}\n")
            f.write(f"P&L: {trade.get('pnl', 0):.2f}\n")
            f.write(f"Pips: {trade.get('pips', 0):.1f}\n")
            
            duration_bars = trade.get('duration_bars', 0)
            duration_min = trade.get('duration_minutes', 0)
            f.write(f"Duration: {duration_bars} bars ({duration_min} min)\n")
            f.write("=" * 80 + "\n\n")
        
        # Summary section
        f.write("\n" + "=" * 80 + "\n")
        f.write("SUMMARY\n")
        f.write("=" * 80 + "\n")
        
        total_trades = len(trade_reports)
        winning_trades = [t for t in trade_reports if t.get('pnl', 0) > 0]
        losing_trades = [t for t in trade_reports if t.get('pnl', 0) <= 0]
        
        total_pnl = sum(t.get('pnl', 0) for t in trade_reports)
        win_rate = (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0
        
        avg_win = sum(t.get('pnl', 0) for t in winning_trades) / len(winning_trades) if winning_trades else 0
        avg_loss = sum(t.get('pnl', 0) for t in losing_trades) / len(losing_trades) if losing_trades else 0
        
        f.write(f"Total Trades: {total_trades}\n")
        f.write(f"Winning Trades: {len(winning_trades)}\n")
        f.write(f"Losing Trades: {len(losing_trades)}\n")
        f.write(f"Win Rate: {win_rate:.2f}%\n")
        f.write(f"Total P&L: {total_pnl:.2f}\n")
        f.write(f"Average Win: {avg_win:.2f}\n")
        f.write(f"Average Loss: {avg_loss:.2f}\n")
        f.write(f"\nTotal Commission: ${total_commission:.2f}\n")
        f.write(f"Net P&L (after commission): ${total_pnl - total_commission:.2f}\n")
        f.write("=" * 80 + "\n")
    
    print(f'\nTrade log saved: {filepath}')


if __name__ == '__main__':
    config_to_run = 'EURJPY_PRO'
    
    if len(sys.argv) > 1:
        config_to_run = sys.argv[1]
    
    run_backtest(config_to_run)