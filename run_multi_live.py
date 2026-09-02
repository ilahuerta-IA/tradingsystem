#!/usr/bin/env python
"""
Run Multi-Strategy Live Trading Bot.

This script runs the multi-strategy monitor that handles
multiple strategies and symbols simultaneously.

Configuration:
    - Edit live/bot_settings.py to enable/disable configs
    - Strategy configs are in config/settings.py

Usage:
    python run_multi_live.py
    python run_multi_live.py --single  # Single iteration for testing
"""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from live.multi_monitor import MultiStrategyMonitor, setup_signal_handlers


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Multi-Strategy Live Trading Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python run_multi_live.py              # Run continuously
    python run_multi_live.py --single     # Single iteration (testing)
    python run_multi_live.py --no-demo    # Allow real accounts (DANGER!)
        """
    )
    parser.add_argument(
        "--single",
        action="store_true",
        help="Run single iteration (for testing)"
    )
    parser.add_argument(
        "--no-demo",
        action="store_true",
        help="Allow real accounts (DANGER: only for production!)"
    )
    
    args = parser.parse_args()
    
    # Live/demo gate lives in bot_settings.DEMO_ONLY (local, manually edited).
    # --no-demo remains as CLI override; only that path asks for confirmation
    # (bot_settings=False is a deliberate config, must not block unattended restarts).
    from live.bot_settings import DEMO_ONLY
    demo_only = DEMO_ONLY and not args.no_demo
    
    if not demo_only and args.no_demo:
        print("\n" + "=" * 60)
        print("WARNING: REAL ACCOUNT MODE ENABLED!")
        print("This will execute trades on a real account.")
        print("=" * 60)
        response = input("Type 'I UNDERSTAND' to continue: ")
        if response != "I UNDERSTAND":
            print("Aborted.")
            sys.exit(1)
    
    monitor = MultiStrategyMonitor(demo_only=demo_only)
    setup_signal_handlers(monitor)
    
    print("\n" + "=" * 60)
    print("Multi-Strategy Live Trading Bot")
    print("=" * 60)
    print(f"Demo Only: {demo_only}")
    print(f"Mode: {'Single iteration' if args.single else 'Continuous'}")
    print("=" * 60 + "\n")
    
    if args.single:
        monitor.run_single_iteration()
    else:
        monitor.run()


if __name__ == "__main__":
    main()
