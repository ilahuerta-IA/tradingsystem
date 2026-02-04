"""
Live Trading Monitor Analyzer

Analyzes monitor_multi_*.log and trades_multi_*.jsonl files to provide:
- Error/Warning summary
- Signals detected vs executed
- Trade summary by strategy
- Slippage analysis
- State machine transitions

Usage:
    python analyze_live.py                  # Analyze latest files
    python analyze_live.py 20260203         # Analyze specific date
    python analyze_live.py --all            # Analyze all available dates
"""
import os
import sys
import json
import re
from datetime import datetime
from collections import defaultdict
from pathlib import Path


# Get logs directory
SCRIPT_DIR = Path(__file__).parent
LOGS_DIR = SCRIPT_DIR.parent / 'logs'


def find_files(date_filter=None):
    """Find log and jsonl files, optionally filtered by date."""
    if not LOGS_DIR.exists():
        print(f"ERROR: Logs directory not found: {LOGS_DIR}")
        return []
    
    log_files = sorted(LOGS_DIR.glob('monitor_multi_*.log'))
    
    if date_filter:
        log_files = [f for f in log_files if date_filter in f.name]
    
    results = []
    for log_file in log_files:
        # Extract date from filename
        date_match = re.search(r'monitor_multi_(\d{8})\.log', log_file.name)
        if date_match:
            date_str = date_match.group(1)
            jsonl_file = LOGS_DIR / f'trades_multi_{date_str}.jsonl'
            results.append({
                'date': date_str,
                'log': log_file,
                'jsonl': jsonl_file if jsonl_file.exists() else None
            })
    
    return results


def parse_log_file(filepath):
    """Parse monitor_multi_*.log file."""
    errors = []
    warnings = []
    signals = []
    state_transitions = []
    
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            
            # Extract timestamp and level
            match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) \| (\w+)\s+\| \w+ \| (.+)', line)
            if not match:
                continue
            
            timestamp_str, level, message = match.groups()
            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')
            
            # Categorize
            if level == 'ERROR':
                errors.append({'time': timestamp, 'message': message})
            elif level == 'WARNING':
                warnings.append({'time': timestamp, 'message': message})
            
            # State transitions (SCANNING -> ARMED, etc.)
            if '->' in message and any(s in message for s in ['SCANNING', 'ARMED', 'WINDOW']):
                state_transitions.append({'time': timestamp, 'message': message})
            
            # Signals
            if 'SIGNAL:' in message:
                signals.append({'time': timestamp, 'message': message})
    
    return {
        'errors': errors,
        'warnings': warnings,
        'signals': signals,
        'state_transitions': state_transitions
    }


def parse_jsonl_file(filepath):
    """Parse trades_multi_*.jsonl file."""
    events = []
    
    if not filepath or not filepath.exists():
        return events
    
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    
    return events


def analyze_events(events):
    """Analyze JSONL events."""
    analysis = {
        'monitor_starts': [],
        'monitor_stops': [],
        'signals': [],
        'trades': [],
        'trade_closed': [],
        'errors': [],
        'by_config': defaultdict(lambda: {'signals': 0, 'trades': 0, 'errors': 0})
    }
    
    for event in events:
        event_type = event.get('event_type')
        config = event.get('config', 'UNKNOWN')
        
        if event_type == 'MONITOR_START':
            analysis['monitor_starts'].append(event)
        elif event_type == 'MONITOR_STOP':
            analysis['monitor_stops'].append(event)
        elif event_type == 'SIGNAL':
            analysis['signals'].append(event)
            analysis['by_config'][config]['signals'] += 1
        elif event_type == 'TRADE':
            analysis['trades'].append(event)
            analysis['by_config'][config]['trades'] += 1
        elif event_type == 'TRADE_CLOSED':
            analysis['trade_closed'].append(event)
        elif event_type == 'ERROR':
            analysis['errors'].append(event)
            analysis['by_config'][config]['errors'] += 1
    
    return analysis


def print_report(date_str, log_data, event_analysis):
    """Print formatted analysis report."""
    print("\n" + "=" * 70)
    print(f"  LIVE MONITOR ANALYSIS - {date_str}")
    print("=" * 70)
    
    # Version info
    if event_analysis['monitor_starts']:
        start = event_analysis['monitor_starts'][-1]
        print(f"\nVersion: {start.get('version', 'N/A')}")
        print(f"Account: {start.get('account', 'N/A')}")
        print(f"Demo: {start.get('demo_only', 'N/A')}")
        print(f"Configs: {len(start.get('enabled_configs', []))}")
    
    # Errors
    print(f"\n{'─' * 70}")
    print("ERRORS")
    print(f"{'─' * 70}")
    
    all_errors = log_data['errors'] + [
        {'time': e.get('timestamp', ''), 'message': f"[{e.get('config')}] {e.get('error')}"} 
        for e in event_analysis['errors']
    ]
    
    if all_errors:
        for err in all_errors[:10]:  # Limit to 10
            time_str = err['time'].strftime('%H:%M:%S') if isinstance(err['time'], datetime) else err['time'][:19]
            print(f"  [{time_str}] {err['message'][:60]}")
        if len(all_errors) > 10:
            print(f"  ... and {len(all_errors) - 10} more errors")
    else:
        print("  ✓ No errors")
    
    # Warnings
    print(f"\n{'─' * 70}")
    print("WARNINGS")
    print(f"{'─' * 70}")
    
    if log_data['warnings']:
        for warn in log_data['warnings'][:5]:
            print(f"  [{warn['time'].strftime('%H:%M:%S')}] {warn['message'][:60]}")
        if len(log_data['warnings']) > 5:
            print(f"  ... and {len(log_data['warnings']) - 5} more warnings")
    else:
        print("  ✓ No warnings")
    
    # Signals vs Executions
    print(f"\n{'─' * 70}")
    print("SIGNALS vs EXECUTIONS")
    print(f"{'─' * 70}")
    
    total_signals = len(event_analysis['signals'])
    total_trades = len(event_analysis['trades'])
    
    print(f"\n  Signals detected: {total_signals}")
    print(f"  Trades executed:  {total_trades}")
    
    if total_signals > 0 and total_trades < total_signals:
        print(f"  ⚠ Missing executions: {total_signals - total_trades}")
    elif total_signals > 0 and total_trades == total_signals:
        print(f"  ✓ All signals executed")
    
    # By config breakdown
    print(f"\n  {'Config':<20} {'Signals':>8} {'Trades':>8} {'Errors':>8}")
    print(f"  {'-' * 48}")
    
    for config in sorted(event_analysis['by_config'].keys()):
        stats = event_analysis['by_config'][config]
        status = "✓" if stats['errors'] == 0 else "✗"
        print(f"  {config:<20} {stats['signals']:>8} {stats['trades']:>8} {stats['errors']:>8} {status}")
    
    # Slippage analysis
    if event_analysis['trades']:
        print(f"\n{'─' * 70}")
        print("SLIPPAGE ANALYSIS")
        print(f"{'─' * 70}")
        
        slippages = []
        for trade in event_analysis['trades']:
            slip = trade.get('slippage_pips')
            if slip is not None:
                slippages.append({
                    'config': trade.get('config'),
                    'symbol': trade.get('symbol'),
                    'slippage': slip
                })
        
        if slippages:
            for s in slippages:
                status = "⚠ HIGH" if abs(s['slippage']) > 3 else "OK"
                print(f"  {s['config']:<20} {s['slippage']:>+6.1f} pips  {status}")
            
            avg_slip = sum(s['slippage'] for s in slippages) / len(slippages)
            print(f"\n  Average slippage: {avg_slip:+.2f} pips")
        else:
            print("  No slippage data available")
    
    # Trade Closed summary
    if event_analysis['trade_closed']:
        print(f"\n{'─' * 70}")
        print("CLOSED TRADES")
        print(f"{'─' * 70}")
        
        total_pnl = 0
        for tc in event_analysis['trade_closed']:
            pnl = tc.get('pnl') or 0
            total_pnl += pnl
            reason = tc.get('close_reason', 'UNKNOWN')
            symbol = tc.get('symbol', '?')
            config = tc.get('config', '?')
            status = "✓" if pnl > 0 else "✗"
            print(f"  {config:<20} {symbol:<8} {reason:<12} ${pnl:>8.2f} {status}")
        
        print(f"\n  Total P&L: ${total_pnl:.2f}")
    
    # State transitions (interesting ones)
    if log_data['state_transitions']:
        print(f"\n{'─' * 70}")
        print("STATE TRANSITIONS (last 10)")
        print(f"{'─' * 70}")
        
        for trans in log_data['state_transitions'][-10:]:
            print(f"  [{trans['time'].strftime('%H:%M')}] {trans['message'][:55]}")
    
    print("\n" + "=" * 70)


def main():
    """Main entry point."""
    # Parse arguments
    date_filter = None
    analyze_all = False
    
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == '--all':
            analyze_all = True
        elif arg == '--help' or arg == '-h':
            print(__doc__)
            return
        else:
            date_filter = arg
    
    # Find files
    files = find_files(date_filter)
    
    if not files:
        if date_filter:
            print(f"No log files found for date: {date_filter}")
        else:
            print("No log files found in logs directory")
        return
    
    # If not --all, only analyze the latest
    if not analyze_all:
        files = [files[-1]]
    
    # Analyze each file set
    for file_set in files:
        log_data = parse_log_file(file_set['log'])
        events = parse_jsonl_file(file_set['jsonl'])
        event_analysis = analyze_events(events)
        print_report(file_set['date'], log_data, event_analysis)


if __name__ == '__main__':
    main()
