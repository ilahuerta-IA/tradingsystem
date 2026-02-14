#!/usr/bin/env python
"""
Portfolio Backtest Runner

Runs backtests for multiple configurations and generates a combined summary.
Uses PORTFOLIO_ALLOCATION to define total capital, allocation and risk per config.

Usage:
    python tools/portfolio_backtest.py                    # All active configs
    python tools/portfolio_backtest.py --list             # List available configs
    python tools/portfolio_backtest.py --configs USDJPY_SEDNA USDJPY_PRO
    python tools/portfolio_backtest.py --strategies KOI SEDNA
    python tools/portfolio_backtest.py --assets USDJPY EURJPY
    python tools/portfolio_backtest.py --exclude TLT_KOI DIA_KOI
"""
import sys
import os
import argparse
import warnings
from datetime import datetime
from collections import defaultdict
from pathlib import Path
from io import StringIO

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Suppress matplotlib warnings
warnings.filterwarnings('ignore', message='AutoDateLocator was unable to pick')

import backtrader as bt
from config.settings import STRATEGIES_CONFIG, BROKER_CONFIG
from strategies.sunset_ogle import SunsetOgleStrategy
from strategies.koi_strategy import KOIStrategy
from strategies.sedna_strategy import SEDNAStrategy
from strategies.gemini_strategy import GEMINIStrategy
from lib.commission import ForexCommission, ETFCommission, ETFCSVData


# ETF symbols list
ETF_SYMBOLS = ['DIA', 'TLT', 'GLD', 'SPY', 'QQQ', 'IWM']

# Strategy registry
STRATEGY_REGISTRY = {
    'SunsetOgle': SunsetOgleStrategy,
    'KOI': KOIStrategy,
    'SEDNA': SEDNAStrategy,
    'GEMINI': GEMINIStrategy,
}

# =============================================================================
# PORTFOLIO CONFIGURATION
# =============================================================================
# Total portfolio capital (shared account). Each config gets a fraction.
# allocation: fraction of total capital assigned to this config (must sum ~1.0)
# risk_pct:   risk per trade as % of THIS config's allocated capital
#
# Tier A (best PF + lowest DD): risk 1.00%
# Tier B (strong PF or Calmar): risk 0.75%
# Tier C (solid but higher DD):  risk 0.65%
# Tier D (weakest metrics):      risk 0.50%
#
# Scoring: PF x Calmar / (MC95 / 10%)
# =============================================================================
PORTFOLIO_TOTAL_CAPITAL = 50_000  # EUR (demo account)

PORTFOLIO_ALLOCATION = {
    # --- Tier A: PF > 2.8, DD < 8%, MC95 < 9% ---
    'USDCHF_PRO':    {'allocation': 0.10, 'risk_pct': 1.00},  # PF 2.86, DD 7.4%, MC95 8.6%
    'USDCHF_GEMINI': {'allocation': 0.10, 'risk_pct': 1.00},  # PF 2.83, DD 7.3%, MC95 6.9%

    # --- Tier B: PF > 2.3 or Calmar > 1.2 ---
    'EURUSD_PRO':    {'allocation': 0.09, 'risk_pct': 0.75},  # PF 2.70, DD 9.4%, MC95 11.2%
    'USDCHF_KOI':   {'allocation': 0.09, 'risk_pct': 0.75},  # PF 2.62, DD 10.4%, MC95 11.3%
    'EURJPY_PRO':    {'allocation': 0.09, 'risk_pct': 0.75},  # PF 2.38, DD 11.6%, MC95 13.8%

    # --- Tier C: Solid, PF > 2.0 ---
    'EURUSD_KOI':    {'allocation': 0.08, 'risk_pct': 0.65},  # PF 2.15, DD 11.6%, MC95 11.8%
    'EURJPY_KOI':    {'allocation': 0.07, 'risk_pct': 0.65},  # PF 2.09, DD 11.0%, MC95 13.9%
    'USDJPY_KOI':    {'allocation': 0.07, 'risk_pct': 0.65},  # PF 2.09, DD 9.3%, MC95 15.4%
    'USDJPY_SEDNA':  {'allocation': 0.07, 'risk_pct': 0.65},  # PF 2.07, DD 10.7%, MC95 12.3%
    'USDJPY_PRO':    {'allocation': 0.07, 'risk_pct': 0.65},  # PF 2.07, DD 11.5%, MC95 15.7%
    'EURUSD_GEMINI': {'allocation': 0.07, 'risk_pct': 0.65},  # PF 2.04, DD 10.1%, MC95 12.0%

    # --- Tier D: Weakest ---
    'EURJPY_SEDNA':  {'allocation': 0.10, 'risk_pct': 0.50},  # PF 1.70, DD 14.5%, MC95 17.5%
}


def _get_portfolio_cash(config_name):
    """Get starting cash for a config based on portfolio allocation."""
    alloc = PORTFOLIO_ALLOCATION.get(config_name)
    if alloc:
        return PORTFOLIO_TOTAL_CAPITAL * alloc['allocation']
    return PORTFOLIO_TOTAL_CAPITAL / 12  # Default equal weight


def _get_portfolio_risk(config_name):
    """Get risk_percent override for a config based on portfolio tier."""
    alloc = PORTFOLIO_ALLOCATION.get(config_name)
    if alloc:
        return alloc['risk_pct'] / 100.0  # Convert 0.75% -> 0.0075
    return 0.01  # Default 1%


def run_single_backtest(config_name, config, silent=False, use_portfolio=False):
    """Run a single backtest and return results.
    
    If use_portfolio=True, overrides starting_cash and risk_percent
    from PORTFOLIO_ALLOCATION config.
    """
    # Initialize Cerebro
    cerebro = bt.Cerebro(stdstats=False)
    
    # Load data
    data_path = Path(config['data_path'])
    asset_name = config['asset_name']
    is_etf = asset_name.upper() in ETF_SYMBOLS
    
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
        openinterest=-1,
        fromdate=config['from_date'],
        todate=config['to_date'],
    )
    
    if is_etf:
        data = ETFCSVData(**feed_kwargs)
    else:
        feed_kwargs['timeframe'] = bt.TimeFrame.Minutes
        feed_kwargs['compression'] = 5
        data = bt.feeds.GenericCSVData(**feed_kwargs)
    
    cerebro.adddata(data, name=asset_name)
    
    # GEMINI needs a second data feed (reference pair)
    if config['strategy_name'] == 'GEMINI' and 'reference_data_path' in config:
        ref_path = Path(config['reference_data_path'])
        ref_kwargs = feed_kwargs.copy()
        ref_kwargs['dataname'] = str(ref_path)
        ref_data = bt.feeds.GenericCSVData(**ref_kwargs)
        cerebro.adddata(ref_data, name=config.get('reference_symbol', 'REF'))
    
    # Get strategy class and add with params
    strategy_class = STRATEGY_REGISTRY.get(config['strategy_name'])
    if not strategy_class:
        raise ValueError(f"Unknown strategy: {config['strategy_name']}")
    
    # Get params and auto-inject asset-specific parameters (same as run_backtest.py)
    params = config.get('params', {}).copy()
    params['print_signals'] = False
    
    # Auto-inject pair type flags
    is_jpy = asset_name.upper().endswith('JPY')
    params['is_jpy_pair'] = is_jpy
    params['is_etf'] = is_etf
    
    # Auto-inject pip_value if not explicitly set
    if is_etf:
        params['pip_value'] = params.get('pip_value', 0.01)
        params['margin_pct'] = params.get('margin_pct', 20.0)
    elif is_jpy:
        params['pip_value'] = 0.01
    else:
        params['pip_value'] = params.get('pip_value', 0.0001)
    
    # Portfolio mode: override risk_percent before adding strategy
    if use_portfolio:
        params['risk_percent'] = _get_portfolio_risk(config_name)
    
    cerebro.addstrategy(strategy_class, **params)
    
    # Broker settings - portfolio mode overrides starting_cash
    if use_portfolio:
        starting_cash = _get_portfolio_cash(config_name)
    else:
        starting_cash = config.get('starting_cash', 100000.0)
    cerebro.broker.setcash(starting_cash)
    
    # Commission
    if is_etf:
        broker_config = BROKER_CONFIG.get('darwinex_zero_etf', BROKER_CONFIG['darwinex_zero'])
        ETFCommission.total_commission = 0.0
        ETFCommission.total_contracts = 0.0
        commission = ETFCommission(
            commission=broker_config.get('commission_per_contract', 0.02),
            margin_pct=broker_config.get('margin_percent', 20.0),
        )
    else:
        broker_config = BROKER_CONFIG['darwinex_zero']
        ForexCommission.total_commission = 0.0
        ForexCommission.total_lots = 0.0
        commission = ForexCommission(
            commission=broker_config['commission_per_lot'],
            is_jpy_pair=is_jpy,
            jpy_rate=params.get('jpy_rate', 150.0) if is_jpy else 1.0,
        )
    cerebro.broker.addcommissioninfo(commission)
    
    # Run backtest
    results = cerebro.run()
    strategy = results[0]
    
    # Extract results
    final_value = cerebro.broker.get_value()
    
    # Get yearly stats from strategy
    yearly_stats = {}
    if hasattr(strategy, '_trade_pnls'):
        for trade in strategy._trade_pnls:
            year = trade['date'].year
            if year not in yearly_stats:
                yearly_stats[year] = {'trades': 0, 'wins': 0, 'pnl': 0}
            yearly_stats[year]['trades'] += 1
            yearly_stats[year]['pnl'] += trade['pnl']
            if trade['is_winner']:
                yearly_stats[year]['wins'] += 1
    
    # Compute max drawdown from equity curve
    max_drawdown_pct = 0.0
    portfolio_values = getattr(strategy, '_portfolio_values', [])
    if len(portfolio_values) > 1:
        peak = portfolio_values[0]
        for value in portfolio_values:
            if value > peak:
                peak = value
            dd = (peak - value) / peak * 100.0
            if dd > max_drawdown_pct:
                max_drawdown_pct = dd

    return {
        'config_name': config_name,
        'strategy_name': config['strategy_name'],
        'asset_name': config['asset_name'],
        'starting_cash': starting_cash,
        'final_value': final_value,
        'net_pnl': final_value - starting_cash,
        'return_pct': (final_value - starting_cash) / starting_cash * 100,
        'total_trades': getattr(strategy, 'trades', 0),
        'wins': getattr(strategy, 'wins', 0),
        'losses': getattr(strategy, 'losses', 0),
        'win_rate': getattr(strategy, 'wins', 0) / getattr(strategy, 'trades', 1) * 100 if getattr(strategy, 'trades', 0) > 0 else 0,
        'gross_profit': getattr(strategy, 'gross_profit', 0),
        'gross_loss': getattr(strategy, 'gross_loss', 0),
        'profit_factor': getattr(strategy, 'gross_profit', 0) / getattr(strategy, 'gross_loss', 1) if getattr(strategy, 'gross_loss', 0) > 0 else float('inf'),
        'max_drawdown_pct': max_drawdown_pct,
        'yearly_stats': yearly_stats,
    }


def print_config_summary(result):
    """Print summary for a single config."""
    print(f"\n{'='*70}")
    print(f"  {result['config_name']} ({result['asset_name']} - {result['strategy_name']})")
    print(f"{'='*70}")
    print(f"  Trades: {result['total_trades']} | Wins: {result['wins']} | WR: {result['win_rate']:.1f}%")
    print(f"  Profit Factor: {result['profit_factor']:.2f}")
    print(f"  Net P&L: ${result['net_pnl']:,.0f} | Return: {result['return_pct']:.2f}% | Max DD: {result['max_drawdown_pct']:.2f}%")
    
    if result['yearly_stats']:
        print(f"\n  Year    Trades  Wins   WR%      P&L")
        print(f"  {'-'*45}")
        for year in sorted(result['yearly_stats'].keys()):
            ys = result['yearly_stats'][year]
            wr = ys['wins'] / ys['trades'] * 100 if ys['trades'] > 0 else 0
            print(f"  {year}    {ys['trades']:>4}   {ys['wins']:>3}  {wr:>5.1f}%  ${ys['pnl']:>10,.0f}")


def print_portfolio_summary(results):
    """Print combined portfolio summary."""
    if not results:
        print("\nNo results to summarize.")
        return
    
    print("\n")
    print("=" * 80)
    print("  PORTFOLIO COMBINED SUMMARY")
    print("=" * 80)
    
    # Group by strategy
    by_strategy = defaultdict(list)
    for r in results:
        by_strategy[r['strategy_name']].append(r)
    
    # Combine yearly stats
    all_years = set()
    for r in results:
        all_years.update(r['yearly_stats'].keys())
    all_years = sorted(all_years)
    
    # Build yearly table
    yearly_combined = {}
    for year in all_years:
        yearly_combined[year] = {
            'trades': 0,
            'wins': 0,
            'pnl_by_strategy': defaultdict(float),
            'pnl_total': 0
        }
        for r in results:
            if year in r['yearly_stats']:
                ys = r['yearly_stats'][year]
                yearly_combined[year]['trades'] += ys['trades']
                yearly_combined[year]['wins'] += ys['wins']
                yearly_combined[year]['pnl_by_strategy'][r['strategy_name']] += ys['pnl']
                yearly_combined[year]['pnl_total'] += ys['pnl']
    
    # Print yearly table
    strategies = sorted(by_strategy.keys())
    
    # Header
    header = f"{'Year':<6} {'Trades':>7} {'Wins':>5} {'WR%':>6}"
    for strat in strategies:
        header += f" {'P&L ' + strat:>14}"
    header += f" {'TOTAL':>14}"
    
    print(f"\n{header}")
    print("-" * len(header))
    
    grand_total = 0
    for year in all_years:
        yc = yearly_combined[year]
        wr = yc['wins'] / yc['trades'] * 100 if yc['trades'] > 0 else 0
        
        row = f"{year:<6} {yc['trades']:>7} {yc['wins']:>5} {wr:>5.1f}%"
        for strat in strategies:
            pnl = yc['pnl_by_strategy'].get(strat, 0)
            row += f" ${pnl:>12,.0f}"
        row += f" ${yc['pnl_total']:>12,.0f}"
        
        # Mark good years
        if yc['pnl_total'] > 0:
            row += " +"
        
        print(row)
        grand_total += yc['pnl_total']
    
    print("-" * len(header))
    
    # Portfolio totals
    total_starting = sum(r['starting_cash'] for r in results)
    total_final = sum(r['final_value'] for r in results)
    total_trades = sum(r['total_trades'] for r in results)
    total_wins = sum(r['wins'] for r in results)
    total_return = (total_final - total_starting) / total_starting * 100
    avg_annual_return = total_return / len(all_years) if all_years else 0
    
    print(f"\n{'='*80}")
    print("  PORTFOLIO TOTALS")
    print(f"{'='*80}")
    print(f"  Configs executed:     {len(results)}")
    print(f"  Total Trades:         {total_trades}")
    print(f"  Total Wins:           {total_wins} ({total_wins/total_trades*100:.1f}%)" if total_trades > 0 else "  Total Wins:           0")
    print(f"  Starting Capital:     ${total_starting:,.0f}")
    print(f"  Final Capital:        ${total_final:,.0f}")
    print(f"  Net P&L:              ${total_final - total_starting:,.0f}")
    # Weighted max drawdown (by allocation)
    total_allocation = sum(r['starting_cash'] for r in results)
    weighted_dd = sum(r['max_drawdown_pct'] * r['starting_cash'] for r in results) / total_allocation if total_allocation > 0 else 0
    worst_dd = max(r['max_drawdown_pct'] for r in results) if results else 0
    worst_dd_name = max(results, key=lambda r: r['max_drawdown_pct'])['config_name'] if results else 'N/A'
    print(f"  Total Return:         {total_return:.2f}%")
    print(f"  Avg Annual Return:    {avg_annual_return:.2f}%")
    print(f"  Weighted Max DD:      {weighted_dd:.2f}%")
    print(f"  Worst Individual DD:  {worst_dd:.2f}% ({worst_dd_name})")
    print(f"{'='*80}\n")


def list_configs():
    """List all available configurations."""
    print("\n" + "=" * 70)
    print("  AVAILABLE CONFIGURATIONS")
    print("=" * 70)
    
    # Group by strategy
    by_strategy = defaultdict(list)
    for name, cfg in STRATEGIES_CONFIG.items():
        by_strategy[cfg['strategy_name']].append((name, cfg))
    
    for strategy in sorted(by_strategy.keys()):
        print(f"\n  {strategy}:")
        print(f"  {'-'*50}")
        for name, cfg in sorted(by_strategy[strategy]):
            status = "* ACTIVE" if cfg.get('active', True) else "  inactive"
            print(f"    {name:<25} {cfg['asset_name']:<10} {status}")
    
    print("\n")


def main():
    parser = argparse.ArgumentParser(
        description='Run portfolio backtests with combined summary',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/portfolio_backtest.py                     # All active configs
  python tools/portfolio_backtest.py --list              # List available configs
  python tools/portfolio_backtest.py --configs USDJPY_SEDNA USDJPY_PRO
  python tools/portfolio_backtest.py --strategies KOI SEDNA
  python tools/portfolio_backtest.py --assets USDJPY EURJPY DIA
  python tools/portfolio_backtest.py --exclude TLT_KOI TLT_PRO
        """
    )
    
    parser.add_argument('--list', '-l', action='store_true',
                        help='List all available configurations')
    parser.add_argument('--configs', '-c', nargs='+', metavar='CONFIG',
                        help='Specific config names to run (e.g., USDJPY_KOI EURJPY_SEDNA)')
    parser.add_argument('--strategies', '-s', nargs='+', metavar='STRATEGY',
                        help='Filter by strategy (e.g., KOI SEDNA SunsetOgle)')
    parser.add_argument('--assets', '-a', nargs='+', metavar='ASSET',
                        help='Filter by asset (e.g., USDJPY EURJPY DIA)')
    parser.add_argument('--exclude', '-x', nargs='+', metavar='CONFIG',
                        help='Exclude specific configs')
    parser.add_argument('--all', action='store_true',
                        help='Run ALL configs (including inactive)')
    parser.add_argument('--portfolio', '-p', action='store_true',
                        help='Use PORTFOLIO_ALLOCATION for capital and risk sizing')
    parser.add_argument('--quiet', '-q', action='store_true',
                        help='Only show final summary, not individual results')
    
    args = parser.parse_args()
    
    # List mode
    if args.list:
        list_configs()
        return
    
    # Determine which configs to run
    configs_to_run = {}
    
    if args.configs:
        # Specific configs
        for name in args.configs:
            if name in STRATEGIES_CONFIG:
                configs_to_run[name] = STRATEGIES_CONFIG[name]
            else:
                print(f"Warning: Config '{name}' not found, skipping.")
    else:
        # Filter from all configs
        for name, cfg in STRATEGIES_CONFIG.items():
            # Check active status
            if not args.all and not cfg.get('active', True):
                continue
            
            # Filter by strategy
            if args.strategies and cfg['strategy_name'] not in args.strategies:
                continue
            
            # Filter by asset
            if args.assets and cfg['asset_name'] not in args.assets:
                continue
            
            configs_to_run[name] = cfg
    
    # Apply exclusions
    if args.exclude:
        for name in args.exclude:
            configs_to_run.pop(name, None)
    
    if not configs_to_run:
        print("No configurations to run. Use --list to see available configs.")
        return
    
    # Print header
    print("\n" + "=" * 80)
    print("  PORTFOLIO BACKTEST RUNNER")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Running {len(configs_to_run)} configuration(s)")
    if args.portfolio:
        print(f"  Mode: PORTFOLIO (capital: ${PORTFOLIO_TOTAL_CAPITAL:,.0f}, tiered risk)")
    else:
        print(f"  Mode: INDIVIDUAL (each config uses its own starting_cash & risk)")
    print("=" * 80)
    
    for name in sorted(configs_to_run.keys()):
        cfg = configs_to_run[name]
        alloc = PORTFOLIO_ALLOCATION.get(name, {})
        if args.portfolio and alloc:
            cash = PORTFOLIO_TOTAL_CAPITAL * alloc['allocation']
            risk = alloc['risk_pct']
            print(f"    . {name} ({cfg['asset_name']} - {cfg['strategy_name']}) "
                  f"[${cash:,.0f} | risk {risk:.2f}%]")
        else:
            print(f"    . {name} ({cfg['asset_name']} - {cfg['strategy_name']})")
    
    # Run backtests
    results = []
    for name in sorted(configs_to_run.keys()):
        cfg = configs_to_run[name]
        
        if not args.quiet:
            print(f"\n{'-'*80}")
            print(f"  Running: {name}")
            print(f"{'-'*80}")
        
        try:
            result = run_single_backtest(name, cfg, silent=args.quiet,
                                         use_portfolio=args.portfolio)
            results.append(result)
            
            if not args.quiet:
                print_config_summary(result)
                
        except Exception as e:
            print(f"  ERROR running {name}: {e}")
            import traceback
            traceback.print_exc()
    
    # Print combined summary
    print_portfolio_summary(results)


if __name__ == '__main__':
    main()
