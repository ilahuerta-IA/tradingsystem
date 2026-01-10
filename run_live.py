#!/usr/bin/env python3
"""
Live Trading Bot - Entry Point.

This is the main script to run the live trading bot.
Run from project root:

    python run_live.py --config EURUSD_PRO --demo-only

For help:
    python run_live.py --help

Before running:
1. Copy config/credentials/mt5_template.json to config/credentials/mt5.json
2. Fill in your MT5 credentials
3. Ensure MT5 terminal is running and logged in

WARNING: This executes REAL TRADES on your MT5 account!
Always start with --demo-only flag and a demo account.
"""

import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime

# Setup path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import STRATEGIES_CONFIG
from live.monitor import LiveTradingMonitor, setup_signal_handlers


def print_banner():
    """Print startup banner."""
    print("""
================================================================
                    LIVE TRADING SYSTEM
                       Version 0.1.0
================================================================
    """)


def list_available_configs():
    """List available strategy configurations."""
    print("\nAvailable configurations:")
    print("-" * 40)
    for name, config in STRATEGIES_CONFIG.items():
        symbol = config.get('symbol', 'N/A')
        strategy = config.get('strategy_class', 'N/A')
        print(f"  {name:<20} {symbol:<10} {strategy}")
    print()


def validate_credentials(path: Path) -> bool:
    """Check if credentials file exists."""
    if not path.exists():
        print(f"\n[FAIL] Credentials file not found: {path}")
        print("\nTo fix this:")
        print(f"  1. Copy {path.parent / 'mt5_template.json'}")
        print(f"  2. Rename to {path.name}")
        print("  3. Fill in your MT5 credentials")
        return False
    return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Live Trading Bot',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_live.py --config EURUSD_PRO --demo-only
  python run_live.py --config EURUSD_PRO --single  # Test single iteration
  python run_live.py --list-configs

Always use --demo-only with a demo account for testing!
        """
    )
    
    parser.add_argument(
        '--config', '-c',
        default='EURUSD_PRO',
        help='Strategy configuration name (default: EURUSD_PRO)'
    )
    
    parser.add_argument(
        '--demo-only', '-d',
        action='store_true',
        default=True,
        help='Only allow demo accounts (default: True)'
    )
    
    parser.add_argument(
        '--allow-live',
        action='store_true',
        help='Allow live trading (DANGEROUS - removes demo-only protection)'
    )
    
    parser.add_argument(
        '--single', '-s',
        action='store_true',
        help='Run single iteration only (for testing)'
    )
    
    parser.add_argument(
        '--list-configs', '-l',
        action='store_true',
        help='List available strategy configurations'
    )
    
    parser.add_argument(
        '--log-dir',
        type=Path,
        default=PROJECT_ROOT / 'logs',
        help='Directory for log files'
    )
    
    parser.add_argument(
        '--credentials',
        type=Path,
        default=PROJECT_ROOT / 'config' / 'credentials' / 'mt5.json',
        help='Path to MT5 credentials JSON'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Verbose output (DEBUG level)'
    )
    
    args = parser.parse_args()
    
    # List configs and exit
    if args.list_configs:
        list_available_configs()
        return 0
    
    # Print banner
    print_banner()
    
    # Validate configuration
    if args.config not in STRATEGIES_CONFIG:
        print(f"[FAIL] Unknown configuration: {args.config}")
        list_available_configs()
        return 1
    
    # Validate credentials
    if not validate_credentials(args.credentials):
        return 1
    
    # Demo-only protection
    demo_only = True
    if args.allow_live:
        print("\n" + "!" * 60)
        print("!!! WARNING: LIVE TRADING ENABLED !!!")
        print("!!! Real money will be at risk !!!")
        print("!" * 60)
        
        confirm = input("\nType 'I ACCEPT THE RISK' to continue: ")
        if confirm != 'I ACCEPT THE RISK':
            print("Cancelled.")
            return 1
        
        demo_only = False
    
    # Setup logging level
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    
    # Print configuration
    config = STRATEGIES_CONFIG[args.config]
    print(f"\nConfiguration")
    print(f"   Strategy: {args.config}")
    print(f"   Symbol:   {config.get('asset_name') or config.get('symbol', 'N/A')}")
    print(f"   Demo:     {demo_only}")
    print(f"   Mode:     {'Single iteration' if args.single else 'Continuous'}")
    print(f"   Logs:     {args.log_dir}")
    print(f"   Time:     {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Create and run monitor
    try:
        monitor = LiveTradingMonitor(
            config_name=args.config,
            demo_only=demo_only,
            log_dir=args.log_dir,
            credentials_path=args.credentials
        )
        
        # Setup signal handlers for graceful shutdown
        setup_signal_handlers(monitor)
        
        # Run
        if args.single:
            print("Running single iteration...")
            monitor.run_single_iteration()
        else:
            print("Starting live trading loop...")
            print("   Press Ctrl+C to stop\n")
            monitor.run()
        
        return 0
        
    except KeyboardInterrupt:
        print("\n\nGoodbye!")
        return 0
    except Exception as e:
        print(f"\n[FAIL] Fatal error: {e}")
        logging.exception("Fatal error")
        return 1


if __name__ == "__main__":
    sys.exit(main())
