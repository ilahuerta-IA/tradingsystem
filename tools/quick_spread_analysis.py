"""Quick spread analysis for GEMINI strategy."""
import re
from collections import defaultdict
from pathlib import Path

def analyze_spread_quality():
    """Analyze trades by spread z-score to find quality sweet spot."""
    log_dir = Path("logs")
    log_files = list(log_dir.glob("GEMINI_trades_*.txt"))
    
    if not log_files:
        print("No GEMINI trade logs found")
        return
    
    latest = max(log_files, key=lambda x: x.stat().st_mtime)
    print(f"Analyzing: {latest.name}\n")
    
    with open(latest, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Parse entries and exits (handle different line endings)
    content = content.replace('\r\n', '\n')
    
    entry_pattern = r'ENTRY #(\d+)\s+Time: ([\d\-: ]+).*?Spread Z-Score: ([\d.]+)'
    exit_pattern = r'EXIT #(\d+)\s+Time: ([\d\-: ]+)\s+Exit Reason: (\w+)\s+P&L: \$([-\d,.]+)'
    
    entries = {m[0]: {'time': m[1], 'spread': float(m[2])} 
               for m in re.findall(entry_pattern, content, re.DOTALL)}
    exits = {m[0]: {'time': m[1], 'reason': m[2], 'pnl': float(m[3].replace(',', ''))} 
             for m in re.findall(exit_pattern, content, re.DOTALL)}
    
    # Parse hour from entry time
    from datetime import datetime as dt
    for tid in entries:
        try:
            entry_time = dt.strptime(entries[tid]['time'].strip(), '%Y-%m-%d %H:%M:%S')
            entries[tid]['hour'] = entry_time.hour
            entries[tid]['day'] = entry_time.weekday()  # 0=Monday
        except:
            entries[tid]['hour'] = -1
            entries[tid]['day'] = -1
    
    # Combine
    trades = []
    for tid in entries:
        if tid in exits:
            trades.append({
                'spread': entries[tid]['spread'],
                'hour': entries[tid].get('hour', -1),
                'day': entries[tid].get('day', -1),
                'reason': exits[tid]['reason'],
                'pnl': exits[tid]['pnl']
            })
    
    print(f"Total trades parsed: {len(trades)}\n")
    
    # Analyze by spread ranges (0.1 buckets)
    print("=" * 70)
    print("ANALYSIS BY SPREAD Z-SCORE (0.1 buckets)")
    print("=" * 70)
    print(f"{'Spread':>6}  {'Trades':>6}  {'Wins':>5}  {'WR%':>6}  {'Net PnL':>12}  {'Avg PnL':>10}")
    print("-" * 70)
    
    buckets = defaultdict(lambda: {'trades': 0, 'wins': 0, 'pnl': 0})
    
    for t in trades:
        bucket = round(t['spread'], 1)
        buckets[bucket]['trades'] += 1
        buckets[bucket]['pnl'] += t['pnl']
        if t['pnl'] > 0:
            buckets[bucket]['wins'] += 1
    
    for spread in sorted(buckets.keys()):
        b = buckets[spread]
        wr = b['wins'] / b['trades'] * 100 if b['trades'] > 0 else 0
        avg = b['pnl'] / b['trades'] if b['trades'] > 0 else 0
        # Mark profitable ranges
        marker = " <-- PROFIT" if b['pnl'] > 0 else ""
        print(f"{spread:6.1f}  {b['trades']:6}  {b['wins']:5}  {wr:5.1f}%  ${b['pnl']:11,.0f}  ${avg:9,.0f}{marker}")
    
    # Summary by threshold
    print("\n" + "=" * 70)
    print("CUMULATIVE ANALYSIS (if we only trade above threshold)")
    print("=" * 70)
    print(f"{'Threshold':>9}  {'Trades':>6}  {'Wins':>5}  {'WR%':>6}  {'Net PnL':>12}  {'PF':>6}")
    print("-" * 70)
    
    thresholds = [1.5, 1.6, 1.7, 1.8, 1.9, 2.0, 2.2, 2.5, 3.0]
    for thresh in thresholds:
        filtered = [t for t in trades if t['spread'] >= thresh]
        if not filtered:
            continue
        total = len(filtered)
        wins = sum(1 for t in filtered if t['pnl'] > 0)
        wr = wins / total * 100. if total > 0 else 0
        net = sum(t['pnl'] for t in filtered)
        gross_profit = sum(t['pnl'] for t in filtered if t['pnl'] > 0)
        gross_loss = abs(sum(t['pnl'] for t in filtered if t['pnl'] < 0))
        pf = gross_profit / gross_loss if gross_loss > 0 else 999
        print(f">= {thresh:5.1f}  {total:6}  {wins:5}  {wr:5.1f}%  ${net:11,.0f}  {pf:6.2f}")
    
    # Find break-even point
    print("\n" + "=" * 70)
    print("FINDING OPTIMAL THRESHOLD (max trades with PF >= 1.5)")
    print("=" * 70)
    
    best_thresh = None
    best_trades = 0
    
    for thresh in [1.5 + i*0.05 for i in range(40)]:  # 1.5 to 3.45
        filtered = [t for t in trades if t['spread'] >= thresh]
        if len(filtered) < 50:  # Need minimum trades
            continue
        gross_profit = sum(t['pnl'] for t in filtered if t['pnl'] > 0)
        gross_loss = abs(sum(t['pnl'] for t in filtered if t['pnl'] < 0))
        pf = gross_profit / gross_loss if gross_loss > 0 else 0
        
        if pf >= 1.5 and len(filtered) > best_trades:
            best_thresh = thresh
            best_trades = len(filtered)
    
    if best_thresh:
        filtered = [t for t in trades if t['spread'] >= best_thresh]
        wins = sum(1 for t in filtered if t['pnl'] > 0)
        net = sum(t['pnl'] for t in filtered)
        gross_profit = sum(t['pnl'] for t in filtered if t['pnl'] > 0)
        gross_loss = abs(sum(t['pnl'] for t in filtered if t['pnl'] < 0))
        pf = gross_profit / gross_loss if gross_loss > 0 else 0
        print(f"Best threshold: >= {best_thresh:.2f}")
        print(f"Trades: {len(filtered)}, Wins: {wins}, WR: {wins/len(filtered)*100:.1f}%")
        print(f"Net PnL: ${net:,.0f}, PF: {pf:.2f}")
    else:
        print("No threshold found with PF >= 1.5 and >= 50 trades")
    
    # Analyze by exit reason
    print("\n" + "=" * 70)
    print("ANALYSIS BY EXIT REASON")
    print("=" * 70)
    
    by_reason = defaultdict(lambda: {'count': 0, 'pnl': 0})
    for t in trades:
        by_reason[t['reason']]['count'] += 1
        by_reason[t['reason']]['pnl'] += t['pnl']
    
    for reason, data in sorted(by_reason.items()):
        avg = data['pnl'] / data['count'] if data['count'] > 0 else 0
        print(f"{reason:12}: {data['count']:5} trades, Net: ${data['pnl']:12,.0f}, Avg: ${avg:9,.0f}")
    
    # Analyze by Hour
    print("\n" + "=" * 70)
    print("ANALYSIS BY HOUR (UTC)")
    print("=" * 70)
    print(f"{'Hour':>4}  {'Trades':>6}  {'Wins':>5}  {'WR%':>6}  {'Net PnL':>12}  {'PF':>6}")
    print("-" * 55)
    
    by_hour = defaultdict(lambda: {'trades': 0, 'wins': 0, 'pnl': 0, 'gp': 0, 'gl': 0})
    for t in trades:
        h = t['hour']
        if h < 0:
            continue
        by_hour[h]['trades'] += 1
        by_hour[h]['pnl'] += t['pnl']
        if t['pnl'] > 0:
            by_hour[h]['wins'] += 1
            by_hour[h]['gp'] += t['pnl']
        else:
            by_hour[h]['gl'] += abs(t['pnl'])
    
    profitable_hours = []
    for h in sorted(by_hour.keys()):
        data = by_hour[h]
        wr = data['wins'] / data['trades'] * 100 if data['trades'] > 0 else 0
        pf = data['gp'] / data['gl'] if data['gl'] > 0 else 999
        marker = " <--" if data['pnl'] > 0 else ""
        print(f"{h:4}  {data['trades']:6}  {data['wins']:5}  {wr:5.1f}%  ${data['pnl']:11,.0f}  {pf:6.2f}{marker}")
        if data['pnl'] > 0:
            profitable_hours.append(h)
    
    print(f"\nProfitable hours: {profitable_hours}")
    
    # Sweet spot analysis: spread >= threshold AND profitable hours
    print("\n" + "=" * 70)
    print("SWEET SPOT ANALYSIS (spread threshold + hour filter)")
    print("=" * 70)
    
    # Find combinations with PF >= 1.2 and trades >= 30
    print(f"{'Spread':>6} {'Hours':>15}  {'Trades':>6}  {'WR%':>6}  {'Net':>12}  {'PF':>6}")
    print("-" * 70)
    
    # Test different thresholds with profitable hours
    for thresh in [1.5, 1.6, 1.7, 1.8, 2.0]:
        if not profitable_hours:
            continue
        filtered = [t for t in trades if t['spread'] >= thresh and t['hour'] in profitable_hours]
        if len(filtered) < 30:
            continue
        wins = sum(1 for t in filtered if t['pnl'] > 0)
        net = sum(t['pnl'] for t in filtered)
        gp = sum(t['pnl'] for t in filtered if t['pnl'] > 0)
        gl = abs(sum(t['pnl'] for t in filtered if t['pnl'] < 0))
        pf = gp / gl if gl > 0 else 999
        wr = wins / len(filtered) * 100
        hrs = str(profitable_hours[:5]) + "..." if len(profitable_hours) > 5 else str(profitable_hours)
        print(f">={thresh:4.1f}  {hrs:>15}  {len(filtered):6}  {wr:5.1f}%  ${net:11,.0f}  {pf:6.2f}")


if __name__ == "__main__":
    analyze_spread_quality()
