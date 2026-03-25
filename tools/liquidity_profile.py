"""
Liquidity / Volatility Profile Analyzer

Analyzes intraday price movement patterns to detect:
- High-liquidity time slots (session opens, closes, news windows)
- Low-volatility "valleys" (calm before the storm)
- Valley-to-peak transitions with duration stats
- Normalized metrics (basis points) for cross-asset comparison

Works with any asset in the data/ folder (5m Dukascopy CSV).

Usage:
    python tools/liquidity_profile.py AUS200                      # 1h slots, full data
    python tools/liquidity_profile.py EURUSD --slot 15            # 15-min slots
    python tools/liquidity_profile.py AUS200 --slot 30 --plot     # 30-min slots + chart
    python tools/liquidity_profile.py XAUUSD --slot 15 --yearly   # per-year directional breakdown
    python tools/liquidity_profile.py AUDUSD --slot 15 --hmm      # HMM regime-conditioned analysis
    python tools/liquidity_profile.py AUDUSD --slot 15 --permtest # E1: permutation significance test
    python tools/liquidity_profile.py AUDUSD --slot 15 --distribution  # E2: return distribution
    python tools/liquidity_profile.py AUDUSD --slot 15 --naive-bt # E3: naive backtest with costs
    python tools/liquidity_profile.py AUS200 --from 2021-01-01 --to 2022-12-31
    python tools/liquidity_profile.py AUS200 --slot 15 --valley   # Valley detection focus
    python tools/liquidity_profile.py AUS200 --days 0,1,2,3,4     # Mon-Fri only
"""
import os
import sys
import csv
import math
import random
import argparse
from datetime import datetime, timedelta
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, '..', 'data'))


# ============================================================================
# DATA LOADING
# ============================================================================

def load_csv_data(asset, from_date=None, to_date=None):
    """Load 5m OHLCV data from CSV. Returns list of dicts."""
    filename = f'{asset}_5m_5Yea.csv'
    filepath = os.path.join(DATA_DIR, filename)
    if not os.path.exists(filepath):
        print(f'File not found: {filepath}')
        sys.exit(1)

    rows = []
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            dt = datetime.strptime(
                f'{row["Date"]} {row["Time"]}', '%Y%m%d %H:%M:%S')
            if from_date and dt < from_date:
                continue
            if to_date and dt >= to_date:
                continue
            rows.append({
                'dt': dt,
                'open': float(row['Open']),
                'high': float(row['High']),
                'low': float(row['Low']),
                'close': float(row['Close']),
                'volume': int(row['Volume']) if row['Volume'] else 0,
            })
    return rows


# ============================================================================
# SLOT AGGREGATION
# ============================================================================

def get_slot_key(dt, slot_minutes):
    """Return (hour, minute_start) tuple for a given datetime and slot size."""
    total_minutes = dt.hour * 60 + dt.minute
    slot_start = (total_minutes // slot_minutes) * slot_minutes
    return (slot_start // 60, slot_start % 60)


def aggregate_to_slots(rows, slot_minutes, allowed_days=None):
    """Aggregate 5m bars into time-of-day slots.

    For each slot, compute the aggregated OHLC (highest high, lowest low, etc.)
    across the 5m bars that fall within that slot on each day.  Then derive
    per-slot-per-day metrics: range, body, true range.

    Returns dict: slot_key -> list of per-day metric dicts.
    """
    # Group raw bars by (date, slot_key)
    day_slot_bars = defaultdict(list)
    for row in rows:
        if allowed_days is not None and row['dt'].weekday() not in allowed_days:
            continue
        sk = get_slot_key(row['dt'], slot_minutes)
        day_key = row['dt'].date()
        day_slot_bars[(day_key, sk)].append(row)

    # Also need previous slot close for true range calc
    # Build day -> list of (slot_key, bars) sorted by time
    day_slots_sorted = defaultdict(list)
    for (day_key, sk), bars in day_slot_bars.items():
        day_slots_sorted[day_key].append((sk, bars))
    for day_key in day_slots_sorted:
        day_slots_sorted[day_key].sort()

    # Build slot -> metrics
    slot_metrics = defaultdict(list)
    for day_key, slots_list in day_slots_sorted.items():
        prev_close = None
        for sk, bars in slots_list:
            slot_open = bars[0]['open']
            slot_high = max(b['high'] for b in bars)
            slot_low = min(b['low'] for b in bars)
            slot_close = bars[-1]['close']
            slot_volume = sum(b['volume'] for b in bars)
            mid_price = (slot_high + slot_low) / 2.0

            range_abs = slot_high - slot_low
            body_abs = abs(slot_close - slot_open)
            # True Range: max(H-L, |H-prevC|, |L-prevC|)
            if prev_close is not None:
                tr = max(range_abs,
                         abs(slot_high - prev_close),
                         abs(slot_low - prev_close))
            else:
                tr = range_abs

            # Normalize to basis points (range / mid_price * 10000)
            if mid_price > 0:
                range_bps = range_abs / mid_price * 10000
                body_bps = body_abs / mid_price * 10000
                tr_bps = tr / mid_price * 10000
            else:
                range_bps = body_bps = tr_bps = 0.0

            # Signed body: positive = bullish, negative = bearish
            body_signed = slot_close - slot_open
            body_signed_bps = body_signed / mid_price * 10000 if mid_price > 0 else 0.0

            slot_metrics[sk].append({
                'date': day_key,
                'range_bps': range_bps,
                'body_bps': body_bps,
                'tr_bps': tr_bps,
                'range_abs': range_abs,
                'volume': slot_volume,
                'body_signed_bps': body_signed_bps,
            })
            prev_close = slot_close

    return slot_metrics


# ============================================================================
# STATISTICS
# ============================================================================

def compute_slot_stats(slot_metrics):
    """Compute mean, std, z-score, percentiles for each slot.

    Returns list of dicts sorted by slot time, plus global mean/std.
    """
    # Global stats across ALL slots (for z-score normalization)
    all_tr = []
    for sk, metrics in slot_metrics.items():
        for m in metrics:
            all_tr.append(m['tr_bps'])
    global_mean = sum(all_tr) / len(all_tr) if all_tr else 0
    global_std = _std(all_tr, global_mean) if all_tr else 1

    stats = []
    for sk in sorted(slot_metrics.keys()):
        metrics = slot_metrics[sk]
        n = len(metrics)
        ranges = [m['range_bps'] for m in metrics]
        bodies = [m['body_bps'] for m in metrics]
        trs = [m['tr_bps'] for m in metrics]
        vols = [m['volume'] for m in metrics]
        range_abs_list = [m['range_abs'] for m in metrics]

        mean_tr = sum(trs) / n
        std_tr = _std(trs, mean_tr)
        z_score = (mean_tr - global_mean) / global_std if global_std > 0 else 0

        # Percentile 75 and 90 of TR (for peak detection)
        sorted_tr = sorted(trs)
        p75 = _percentile(sorted_tr, 75)
        p90 = _percentile(sorted_tr, 90)

        # Directional bias
        signed = [m['body_signed_bps'] for m in metrics]
        n_bull = sum(1 for s in signed if s > 0)
        n_bear = sum(1 for s in signed if s < 0)
        bull_pct = n_bull / n * 100 if n > 0 else 0
        bear_pct = n_bear / n * 100 if n > 0 else 0
        mean_signed = sum(signed) / n

        # Magnitude asymmetry: avg body of bull vs bear candles
        bull_bodies = [s for s in signed if s > 0]
        bear_bodies = [abs(s) for s in signed if s < 0]
        mean_bull_body = (sum(bull_bodies) / len(bull_bodies)
                         if bull_bodies else 0.0)
        mean_bear_body = (sum(bear_bodies) / len(bear_bodies)
                         if bear_bodies else 0.0)
        # Net expected value: freq × magnitude
        net_ev_bps = (bull_pct / 100 * mean_bull_body
                      - bear_pct / 100 * mean_bear_body)

        stats.append({
            'slot': sk,
            'slot_label': f'{sk[0]:02d}:{sk[1]:02d}',
            'n_days': n,
            'mean_range_bps': sum(ranges) / n,
            'mean_body_bps': sum(bodies) / n,
            'mean_tr_bps': mean_tr,
            'std_tr_bps': std_tr,
            'z_score': z_score,
            'p75_tr_bps': p75,
            'p90_tr_bps': p90,
            'mean_volume': sum(vols) / n,
            'mean_range_abs': sum(range_abs_list) / n,
            'bull_pct': bull_pct,
            'bear_pct': bear_pct,
            'mean_signed_bps': mean_signed,
            'mean_bull_body': mean_bull_body,
            'mean_bear_body': mean_bear_body,
            'net_ev_bps': net_ev_bps,
        })

    return stats, global_mean, global_std


def compute_yearly_slot_stats(slot_metrics):
    """Compute per-year directional stats for each slot.

    Returns dict: slot_key -> list of yearly stat dicts.
    Reveals regime instability (Simpson's paradox).
    """
    results = {}
    for sk in sorted(slot_metrics.keys()):
        metrics = slot_metrics[sk]
        # Group by year
        year_groups = defaultdict(list)
        for m in metrics:
            year_groups[m['date'].year].append(m)

        yearly = []
        for year in sorted(year_groups.keys()):
            ymetrics = year_groups[year]
            n = len(ymetrics)
            signed = [m['body_signed_bps'] for m in ymetrics]
            n_bull = sum(1 for s in signed if s > 0)
            n_bear = sum(1 for s in signed if s < 0)
            bull_pct = n_bull / n * 100 if n > 0 else 0
            bear_pct = n_bear / n * 100 if n > 0 else 0
            mean_signed = sum(signed) / n

            # Magnitude asymmetry per year
            bull_bodies = [s for s in signed if s > 0]
            bear_bodies = [abs(s) for s in signed if s < 0]
            mean_bull_body = (sum(bull_bodies) / len(bull_bodies)
                             if bull_bodies else 0.0)
            mean_bear_body = (sum(bear_bodies) / len(bear_bodies)
                             if bear_bodies else 0.0)
            net_ev = (bull_pct / 100 * mean_bull_body
                      - bear_pct / 100 * mean_bear_body)

            trs = [m['tr_bps'] for m in ymetrics]
            mean_tr = sum(trs) / n

            yearly.append({
                'year': year,
                'n': n,
                'bull_pct': bull_pct,
                'bear_pct': bear_pct,
                'mean_signed': mean_signed,
                'mean_bull_body': mean_bull_body,
                'mean_bear_body': mean_bear_body,
                'net_ev_bps': net_ev,
                'mean_tr': mean_tr,
            })
        results[sk] = yearly
    return results


def _std(values, mean):
    if len(values) < 2:
        return 0.0
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(variance)


def _percentile(sorted_vals, pct):
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * pct / 100.0
    f = int(k)
    c = f + 1
    if c >= len(sorted_vals):
        return sorted_vals[-1]
    return sorted_vals[f] + (k - f) * (sorted_vals[c] - sorted_vals[f])


# ============================================================================
# ZONE CLASSIFICATION
# ============================================================================

def classify_zones(stats, hot_threshold=0.75, cold_threshold=-0.50):
    """Classify each slot as HOT (high volatility), COLD (valley), or NEUTRAL.

    Args:
        hot_threshold:  z-score above which a slot is HOT
        cold_threshold: z-score below which a slot is COLD
    """
    for s in stats:
        if s['z_score'] >= hot_threshold:
            s['zone'] = 'HOT'
        elif s['z_score'] <= cold_threshold:
            s['zone'] = 'COLD'
        else:
            s['zone'] = '--'

    # Compute distance (in slots) from each slot to the next HOT slot
    # Wraps around midnight (circular)
    n = len(stats)
    hot_indices = [i for i, s in enumerate(stats) if s['zone'] == 'HOT']
    for i, s in enumerate(stats):
        if s['zone'] == 'HOT':
            s['dist_to_hot'] = 0
        elif hot_indices:
            # Find nearest HOT going forward (circular)
            dists = [((h - i) % n) for h in hot_indices]
            s['dist_to_hot'] = min(dists)
        else:
            s['dist_to_hot'] = -1

    return stats


# ============================================================================
# VALLEY-PEAK DETECTION
# ============================================================================

def detect_valley_peaks(stats):
    """Detect transitions from COLD zones to HOT zones.

    Returns list of transitions with:
    - valley start/end slots
    - valley duration (in slot units)
    - peak slot and intensity (z-score)
    - acceleration (z-score delta from valley to peak)
    """
    transitions = []
    n = len(stats)

    # Find contiguous COLD runs followed by HOT
    i = 0
    while i < n:
        # Find start of COLD run
        if stats[i].get('zone') != 'COLD':
            i += 1
            continue

        valley_start = i
        # Extend valley to end of COLD run
        j = i + 1
        while j < n and stats[j].get('zone') == 'COLD':
            j += 1
        valley_end = j - 1  # last COLD slot

        # Look for HOT within next slots after valley end
        # Use wide window: up to half of total slots (handles market gaps)
        lookahead = max(4, n // 2)
        peak_idx = None
        for k in range(j, min(j + lookahead, n)):
            if stats[k].get('zone') == 'HOT':
                peak_idx = k
                break

        if peak_idx is not None:
            valley_duration = valley_end - valley_start + 1
            valley_mean_z = sum(
                stats[x]['z_score'] for x in range(valley_start, valley_end + 1)
            ) / valley_duration
            gap_slots = peak_idx - valley_end - 1  # neutral slots between

            transitions.append({
                'valley_start': stats[valley_start]['slot_label'],
                'valley_end': stats[valley_end]['slot_label'],
                'valley_slots': valley_duration,
                'valley_mean_z': valley_mean_z,
                'gap_slots': gap_slots,
                'peak_slot': stats[peak_idx]['slot_label'],
                'peak_z': stats[peak_idx]['z_score'],
                'acceleration': stats[peak_idx]['z_score'] - valley_mean_z,
                'peak_bull_pct': stats[peak_idx].get('bull_pct', 0),
                'peak_bear_pct': stats[peak_idx].get('bear_pct', 0),
                'peak_signed_bps': stats[peak_idx].get('mean_signed_bps', 0),
            })

        i = j  # Continue after this valley

    return transitions


# ============================================================================
# CONSECUTIVE VALLEY ANALYSIS
# ============================================================================

def analyze_consecutive_cold(stats, slot_minutes):
    """Analyze all COLD runs: their duration and what follows.

    Useful for LUYTEN: how long do calm periods last before volatility?
    """
    runs = []
    n = len(stats)
    i = 0
    while i < n:
        if stats[i].get('zone') != 'COLD':
            i += 1
            continue
        start = i
        j = i + 1
        while j < n and stats[j].get('zone') == 'COLD':
            j += 1
        end = j - 1
        duration_slots = end - start + 1
        duration_min = duration_slots * slot_minutes

        # What follows this COLD run?
        if j < n:
            next_zone = stats[j].get('zone', '--')
            next_z = stats[j]['z_score']
        else:
            next_zone = 'END'
            next_z = 0.0

        runs.append({
            'start': stats[start]['slot_label'],
            'end': stats[end]['slot_label'],
            'duration_slots': duration_slots,
            'duration_min': duration_min,
            'mean_z': sum(
                stats[x]['z_score'] for x in range(start, end + 1)
            ) / duration_slots,
            'followed_by': next_zone,
            'next_z': next_z,
        })
        i = j
    return runs


# ============================================================================
# PRINTING
# ============================================================================

def print_header(asset, slot_minutes, from_date, to_date, n_rows, n_days):
    print()
    print('=' * 90)
    print(f'  LIQUIDITY PROFILE: {asset}')
    print(f'  Slot size: {slot_minutes}m  |  Data: {n_rows:,} bars (5m)')
    print(f'  Period: {from_date} to {to_date}  |  Trading days: ~{n_days}')
    print('=' * 90)


def print_profile_table(stats, global_mean, global_std, asset, slot_minutes):
    """Print the main time-of-day volatility profile table."""
    print()
    print('-' * 105)
    print(f'  TIME-OF-DAY VOLATILITY PROFILE ({slot_minutes}m slots)')
    print(f'  Global mean TR: {global_mean:.2f} bps  |  Std: {global_std:.2f} bps')
    print('-' * 105)
    print(f'  {"Slot":<8} {"N":>5} {"MeanTR":>9} {"StdTR":>8} '
          f'{"Z-Score":>8} {"Bull%":>6} {"Bear%":>6} {"Bias":>7} '
          f'{"Zone":>6} {"ToHOT":>6}  {"Bar"}')
    print(f'  {"":8} {"days":>5} {"(bps)":>9} {"(bps)":>8} '
          f'{"":>8} {"":>6} {"":>6} {"(bps)":>7} '
          f'{"":>6} {"slots":>6}')
    print('-' * 105)

    # Find max mean_tr for bar scaling
    max_tr = max(s['mean_tr_bps'] for s in stats) if stats else 1

    for s in stats:
        bar_len = int(s['mean_tr_bps'] / max_tr * 25)
        bar = '#' * bar_len
        zone_str = s.get('zone', '--')
        if zone_str == 'HOT':
            zone_disp = '>>HOT'
        elif zone_str == 'COLD':
            zone_disp = ' cold'
        else:
            zone_disp = '  --'

        dist_hot = s.get('dist_to_hot', -1)
        dist_str = f'{dist_hot:>4}' if dist_hot >= 0 else '  --'

        # Direction indicator
        bias = s.get('mean_signed_bps', 0)
        bias_str = f'{bias:>+7.2f}'

        print(f'  {s["slot_label"]:<8} {s["n_days"]:>5} '
              f'{s["mean_tr_bps"]:>9.2f} {s["std_tr_bps"]:>8.2f} '
              f'{s["z_score"]:>+8.2f} '
              f'{s.get("bull_pct", 0):>5.1f}% {s.get("bear_pct", 0):>5.1f}% '
              f'{bias_str} '
              f'{zone_disp:>6} {dist_str:>6}  {bar}')

    print('-' * 105)


def print_top_slots(stats, n=10):
    """Print top N most volatile slots with directional bias."""
    ranked = sorted(stats, key=lambda s: s['mean_tr_bps'], reverse=True)
    print()
    print(f'  TOP {n} MOST VOLATILE SLOTS:')
    print(f'  {"#":>3} {"Slot":<8} {"MeanTR":>9} {"Z-Score":>8} '
          f'{"Bull%":>6} {"Bear%":>6} {"Bias":>7} {"Zone":>6}')
    for i, s in enumerate(ranked[:n], 1):
        bias = s.get('mean_signed_bps', 0)
        bull = s.get('bull_pct', 0)
        bear = s.get('bear_pct', 0)
        print(f'  {i:>3} {s["slot_label"]:<8} '
              f'{s["mean_tr_bps"]:>9.2f} {s["z_score"]:>+8.2f} '
              f'{bull:>5.1f}% {bear:>5.1f}% {bias:>+7.2f} '
              f'{s.get("zone", "--"):>6}')


def print_top_quiet(stats, n=10):
    """Print top N quietest slots."""
    ranked = sorted(stats, key=lambda s: s['mean_tr_bps'])
    print()
    print(f'  TOP {n} QUIETEST SLOTS (potential consolidation zones):')
    print(f'  {"#":>3} {"Slot":<8} {"MeanTR":>9} {"Z-Score":>8} {"Zone":>6}')
    for i, s in enumerate(ranked[:n], 1):
        print(f'  {i:>3} {s["slot_label"]:<8} '
              f'{s["mean_tr_bps"]:>9.2f} {s["z_score"]:>+8.2f} '
              f'{s.get("zone", "--"):>6}')


def print_directional_hot(stats):
    """Print directional bias analysis for HOT zone slots.

    Groups consecutive HOT slots into explosion zones and shows whether
    the typical move is bullish or bearish -- critical for directional
    strategies (e.g. long-only LUYTEN).
    """
    hot_slots = [s for s in stats if s.get('zone') == 'HOT']
    if not hot_slots:
        print('\n  No HOT zones detected for directional analysis.')
        return

    # Group consecutive HOT slots into explosion zones
    zones = []
    current_group = [hot_slots[0]]
    for i in range(1, len(hot_slots)):
        prev = hot_slots[i - 1]['slot']
        curr = hot_slots[i]['slot']
        # Check if consecutive (same hour, adjacent minutes or next hour)
        prev_total = prev[0] * 60 + prev[1]
        curr_total = curr[0] * 60 + curr[1]
        # Find slot_minutes from gap between any two adjacent stats
        all_totals = sorted(s['slot'][0] * 60 + s['slot'][1] for s in stats)
        slot_min = all_totals[1] - all_totals[0] if len(all_totals) > 1 else 60
        if curr_total - prev_total == slot_min:
            current_group.append(hot_slots[i])
        else:
            zones.append(current_group)
            current_group = [hot_slots[i]]
    zones.append(current_group)

    print()
    print('-' * 90)
    print('  DIRECTIONAL BIAS OF HOT ZONES (explosion direction)')
    print('-' * 90)
    print(f'  {"Zone":<17} {"Slots":>5} {"MeanTR":>9} {"Bull%":>7} '
          f'{"Bear%":>7} {"Bias":>8} {"Verdict":>10}')
    print(f'  {"(start - end)":<17} {"":>5} {"(bps)":>9} {"":>7} '
          f'{"":>7} {"(bps)":>8} {"":>10}')
    print('-' * 90)

    for group in zones:
        label_start = group[0]['slot_label']
        label_end = group[-1]['slot_label']
        if len(group) == 1:
            label = f'{label_start:<17}'
        else:
            label = f'{label_start}-{label_end:<11}'
        n_slots = len(group)
        mean_tr = sum(s['mean_tr_bps'] for s in group) / n_slots
        mean_bull = sum(s.get('bull_pct', 0) for s in group) / n_slots
        mean_bear = sum(s.get('bear_pct', 0) for s in group) / n_slots
        mean_bias = sum(s.get('mean_signed_bps', 0) for s in group) / n_slots

        # Verdict: strong if >60%, moderate if >55%
        if mean_bull >= 60:
            verdict = 'BULLISH'
        elif mean_bull >= 55:
            verdict = 'bull~'
        elif mean_bear >= 60:
            verdict = 'BEARISH'
        elif mean_bear >= 55:
            verdict = 'bear~'
        else:
            verdict = 'MIXED'

        print(f'  {label} {n_slots:>5} {mean_tr:>9.2f} '
              f'{mean_bull:>6.1f}% {mean_bear:>6.1f}% '
              f'{mean_bias:>+8.2f} {verdict:>10}')

    # Global HOT summary
    all_bull = sum(s.get('bull_pct', 0) for s in hot_slots) / len(hot_slots)
    all_bear = sum(s.get('bear_pct', 0) for s in hot_slots) / len(hot_slots)
    all_bias = sum(s.get('mean_signed_bps', 0) for s in hot_slots) / len(hot_slots)
    print(f'\n  Overall HOT direction: Bull {all_bull:.1f}%  Bear {all_bear:.1f}%  '
          f'Bias {all_bias:+.2f} bps')
    if all_bear > all_bull + 5:
        print('  >>> WARNING: HOT explosions lean BEARISH -- risky for long-only <<<')
    elif all_bull > all_bear + 5:
        print('  >>> HOT explosions lean BULLISH -- favorable for long-only <<<')
    else:
        print('  >>> HOT explosions are MIXED -- no strong directional edge <<<')


def print_transitions(transitions, slot_minutes):
    """Print valley-to-peak transitions with directional bias."""
    if not transitions:
        print('\n  No COLD -> HOT transitions detected.')
        return

    print()
    print('-' * 105)
    print('  VALLEY -> PEAK TRANSITIONS (calm before the storm)')
    print('-' * 105)
    print(f'  {"Valley":<17} {"Dur":>5} {"ValZ":>7} {"Gap":>4} '
          f'{"Peak":>7} {"PeakZ":>7} {"Accel":>7} '
          f'{"Bull%":>7} {"Bear%":>7} {"Dir":>8}')
    print(f'  {"(start - end)":<17} {"slots":>5} {"mean":>7} {"":>4} '
          f'{"slot":>7} {"":>7} {"dZ":>7} '
          f'{"":>7} {"":>7} {"":>8}')
    print('-' * 105)

    for t in transitions:
        dur_min = t['valley_slots'] * slot_minutes
        bull = t.get('peak_bull_pct', 0)
        bear = t.get('peak_bear_pct', 0)
        if bull >= 55:
            dir_str = 'BULL'
        elif bear >= 55:
            dir_str = 'BEAR'
        else:
            dir_str = 'MIXED'
        print(f'  {t["valley_start"]}-{t["valley_end"]:<11} '
              f'{t["valley_slots"]:>3} ({dur_min:>3}m) '
              f'{t["valley_mean_z"]:>+7.2f} {t["gap_slots"]:>3}s '
              f'{t["peak_slot"]:>7} {t["peak_z"]:>+7.2f} '
              f'{t["acceleration"]:>+7.2f} '
              f'{bull:>6.1f}% {bear:>6.1f}% {dir_str:>8}')

    # Summary
    avg_valley_dur = sum(t['valley_slots'] for t in transitions) / len(transitions)
    avg_accel = sum(t['acceleration'] for t in transitions) / len(transitions)
    avg_bull = sum(t.get('peak_bull_pct', 0) for t in transitions) / len(transitions)
    avg_bear = sum(t.get('peak_bear_pct', 0) for t in transitions) / len(transitions)
    print(f'\n  Avg valley duration: {avg_valley_dur:.1f} slots '
          f'({avg_valley_dur * slot_minutes:.0f} min)')
    print(f'  Avg acceleration (valley->peak dZ): {avg_accel:+.2f}')
    print(f'  Avg peak direction: Bull {avg_bull:.1f}% / Bear {avg_bear:.1f}%')
    print(f'  Transitions found: {len(transitions)}')


def print_cold_runs(runs, slot_minutes):
    """Print analysis of consecutive COLD (valley) periods."""
    if not runs:
        print('\n  No COLD runs detected.')
        return

    print()
    print('-' * 90)
    print('  VALLEY (COLD) RUNS -- Duration & What Follows')
    print('-' * 90)
    print(f'  {"Start":<7} {"End":<7} {"Dur":>5} {"Time":>6} '
          f'{"ValZ":>7} {"Follows":>8} {"NextZ":>7}')
    print('-' * 90)

    for r in runs:
        print(f'  {r["start"]:<7} {r["end"]:<7} '
              f'{r["duration_slots"]:>3}sl {r["duration_min"]:>4}m '
              f'{r["mean_z"]:>+7.2f} {r["followed_by"]:>8} '
              f'{r["next_z"]:>+7.2f}')

    # Distribution of valley durations
    durations = [r['duration_min'] for r in runs]
    followed_hot = [r for r in runs if r['followed_by'] == 'HOT']
    print(f'\n  Total COLD runs: {len(runs)}')
    print(f'  Duration range: {min(durations)}-{max(durations)} min')
    print(f'  Avg duration: {sum(durations)/len(durations):.0f} min')
    if followed_hot:
        hot_durs = [r['duration_min'] for r in followed_hot]
        print(f'  Valleys followed by HOT: {len(followed_hot)} '
              f'(avg {sum(hot_durs)/len(hot_durs):.0f} min)')


def print_day_of_week(rows, slot_minutes, allowed_days=None):
    """Print volatility by day of week."""
    day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    day_metrics = defaultdict(list)

    for row in rows:
        dow = row['dt'].weekday()
        if allowed_days is not None and dow not in allowed_days:
            continue
        mid = (row['high'] + row['low']) / 2.0
        if mid > 0:
            range_bps = (row['high'] - row['low']) / mid * 10000
            day_metrics[dow].append(range_bps)

    if not day_metrics:
        return

    print()
    print('-' * 50)
    print('  VOLATILITY BY DAY OF WEEK')
    print('-' * 50)
    print(f'  {"Day":<5} {"N bars":>8} {"MeanRng":>10} {"StdRng":>10}')
    print(f'  {"":5} {"":>8} {"(bps)":>10} {"(bps)":>10}')
    print('-' * 50)

    for dow in sorted(day_metrics.keys()):
        vals = day_metrics[dow]
        n = len(vals)
        mean_v = sum(vals) / n
        std_v = _std(vals, mean_v)
        print(f'  {day_names[dow]:<5} {n:>8} {mean_v:>10.2f} {std_v:>10.2f}')


def print_yearly_breakdown(yearly_stats, stats, slot_minutes):
    """Print per-year directional analysis for HOT and interesting slots.

    Shows regime stability: if bull% swings wildly across years,
    the aggregate signal is an artifact (Simpson's paradox).
    """
    # Focus on HOT slots + any slot with bull_pct > 58 or bear_pct > 58
    focus_slots = []
    for s in stats:
        if (s.get('zone') == 'HOT'
                or s.get('bull_pct', 0) > 58
                or s.get('bear_pct', 0) > 58):
            focus_slots.append(s['slot'])

    if not focus_slots:
        # Fall back to top 5 most volatile
        ranked = sorted(stats, key=lambda s: s['mean_tr_bps'], reverse=True)
        focus_slots = [s['slot'] for s in ranked[:5]]

    print()
    print('=' * 110)
    print(f'  YEARLY DIRECTIONAL BREAKDOWN ({slot_minutes}m)  '
          '(regime stability check)')
    print('=' * 110)

    for sk in sorted(focus_slots):
        if sk not in yearly_stats:
            continue
        yearly = yearly_stats[sk]
        slot_label = f'{sk[0]:02d}:{sk[1]:02d}'

        # Find aggregate stats for this slot
        agg = next((s for s in stats if s['slot'] == sk), None)
        zone = agg.get('zone', '--') if agg else '--'
        agg_bull = agg.get('bull_pct', 0) if agg else 0
        agg_net = agg.get('net_ev_bps', 0) if agg else 0

        print(f'\n  Slot {slot_label}  (zone={zone}, '
              f'agg bull={agg_bull:.1f}%, agg NetEV={agg_net:+.2f} bps)')
        print(f'  {"Year":>6} {"N":>5} {"Bull%":>7} {"Bear%":>7} '
              f'{"BullBody":>9} {"BearBody":>9} {"NetEV":>8} '
              f'{"MeanTR":>8} {"Verdict":>10}')
        print('  ' + '-' * 85)

        bull_pcts = []
        for y in yearly:
            # Verdict per year
            if y['bull_pct'] >= 60:
                verdict = 'BULL'
            elif y['bull_pct'] >= 55:
                verdict = 'bull~'
            elif y['bear_pct'] >= 60:
                verdict = 'BEAR'
            elif y['bear_pct'] >= 55:
                verdict = 'bear~'
            else:
                verdict = 'MIXED'

            print(f'  {y["year"]:>6} {y["n"]:>5} '
                  f'{y["bull_pct"]:>6.1f}% {y["bear_pct"]:>6.1f}% '
                  f'{y["mean_bull_body"]:>8.2f} {y["mean_bear_body"]:>8.2f} '
                  f'{y["net_ev_bps"]:>+8.2f} '
                  f'{y["mean_tr"]:>8.2f} {verdict:>10}')
            bull_pcts.append(y['bull_pct'])

        # Stability check
        if bull_pcts:
            spread = max(bull_pcts) - min(bull_pcts)
            std_bull = _std(bull_pcts, sum(bull_pcts) / len(bull_pcts))
            stable = 'STABLE' if spread < 15 else 'UNSTABLE'
            print(f'  {"":>6} {"":>5} '
                  f'spread={spread:.1f}pp  std={std_bull:.1f}pp  '
                  f'=> {stable}')

    print()
    print('-' * 110)
    print('  STABILITY LEGEND: spread < 15pp = STABLE (regime-independent)')


# ============================================================================
# HMM REGIME DETECTION (Task C)
# ============================================================================

def compute_daily_features(rows):
    """Compute daily return and intraday volatility for HMM training.

    Returns list of dicts with 'date', 'daily_ret', 'intraday_vol' fields,
    sorted by date.
    """
    # Group bars by date
    day_bars = defaultdict(list)
    for r in rows:
        day_bars[r['dt'].date()].append(r)

    features = []
    prev_close = None
    for day in sorted(day_bars.keys()):
        bars = sorted(day_bars[day], key=lambda b: b['dt'])
        if len(bars) < 2:
            prev_close = bars[-1]['close']
            continue
        day_open = bars[0]['open']
        day_close = bars[-1]['close']
        day_high = max(b['high'] for b in bars)
        day_low = min(b['low'] for b in bars)
        mid = (day_high + day_low) / 2.0
        if mid <= 0:
            prev_close = day_close
            continue

        # Daily return (vs prev close if available, else vs today's open)
        ref = prev_close if prev_close else day_open
        daily_ret = (day_close - ref) / ref * 10000  # bps

        # Intraday volatility: high-low range in bps
        intraday_vol = (day_high - day_low) / mid * 10000

        features.append({
            'date': day,
            'daily_ret': daily_ret,
            'intraday_vol': intraday_vol,
        })
        prev_close = day_close

    return features


def fit_hmm_regimes(daily_features, n_states=3, random_seed=42):
    """Fit Gaussian HMM on daily features and label each day.

    Uses |daily_ret| + intraday_vol as observation features.
    States are sorted by increasing intraday_vol mean so that:
      state 0 = calm, state 1 = normal, state 2 = volatile.

    Returns (labels dict {date: regime_int}, model, state_names list).
    """
    try:
        from hmmlearn.hmm import GaussianHMM
        import numpy as np
    except ImportError:
        print('\n  hmmlearn not installed -- pip install hmmlearn')
        return None, None, None

    if len(daily_features) < 60:
        print(f'\n  Not enough days ({len(daily_features)}) for HMM training.')
        return None, None, None

    X = np.array([
        [abs(f['daily_ret']), f['intraday_vol']]
        for f in daily_features
    ])

    model = GaussianHMM(
        n_components=n_states,
        covariance_type='full',
        n_iter=200,
        random_state=random_seed,
        tol=1e-4,
    )
    model.fit(X)
    raw_states = model.predict(X)

    # Sort states by intraday_vol mean (ascending) -> calm < normal < volatile
    vol_means = [model.means_[s][1] for s in range(n_states)]
    state_order = sorted(range(n_states), key=lambda s: vol_means[s])
    remap = {old: new for new, old in enumerate(state_order)}

    state_names = {0: 'CALM', 1: 'NORMAL', 2: 'VOLATILE'}
    if n_states == 2:
        state_names = {0: 'CALM', 1: 'VOLATILE'}

    labels = {}
    for i, feat in enumerate(daily_features):
        labels[feat['date']] = remap[raw_states[i]]

    return labels, model, state_names


def compute_regime_slot_stats(slot_metrics, regime_labels):
    """Compute slot stats separately for each regime.

    Returns dict: regime_id -> list of slot stat dicts (same format as
    compute_slot_stats output).
    """
    # Split slot_metrics by regime
    regime_slot_metrics = defaultdict(lambda: defaultdict(list))
    for sk, metrics in slot_metrics.items():
        for m in metrics:
            regime = regime_labels.get(m['date'])
            if regime is not None:
                regime_slot_metrics[regime][sk].append(m)

    regime_stats = {}
    for regime_id in sorted(regime_slot_metrics.keys()):
        stats, _, _ = compute_slot_stats(regime_slot_metrics[regime_id])
        regime_stats[regime_id] = stats
    return regime_stats


def print_hmm_summary(regime_labels, state_names, daily_features):
    """Print regime distribution summary."""
    import numpy as np

    counts = defaultdict(int)
    for r in regime_labels.values():
        counts[r] += 1
    total = sum(counts.values())

    # Compute mean features per regime
    regime_feats = defaultdict(list)
    for f in daily_features:
        r = regime_labels.get(f['date'])
        if r is not None:
            regime_feats[r].append(f)

    print()
    print('=' * 100)
    print('  HMM REGIME DETECTION (Gaussian HMM, sorted by intraday vol)')
    print('=' * 100)
    print(f'  {"Regime":<12} {"Name":<10} {"Days":>5} {"Pct":>6} '
          f'{"AvgAbsRet":>10} {"AvgVol":>10}')
    print('  ' + '-' * 65)

    for rid in sorted(counts.keys()):
        name = state_names.get(rid, f'S{rid}')
        pct = counts[rid] / total * 100
        feats = regime_feats[rid]
        avg_ret = sum(abs(f['daily_ret']) for f in feats) / len(feats)
        avg_vol = sum(f['intraday_vol'] for f in feats) / len(feats)
        print(f'  {rid:<12} {name:<10} {counts[rid]:>5} {pct:>5.1f}% '
              f'{avg_ret:>10.1f} {avg_vol:>10.1f}')

    print()


def print_regime_directional(regime_stats, state_names, slot_minutes,
                             global_stats):
    """Print per-regime directional analysis for the most interesting slots.

    Focus on slots that have significant directional bias in at least one
    regime, even if the aggregate is flat.
    """
    # Find all slots present across regimes
    all_slots = set()
    for rid, stats_list in regime_stats.items():
        for s in stats_list:
            all_slots.add(s['slot'])

    # Build comparable table: for each slot, gather per-regime bull% and NetEV
    slot_data = defaultdict(dict)
    for rid, stats_list in regime_stats.items():
        for s in stats_list:
            slot_data[s['slot']][rid] = s

    # Find interesting slots: max bull% - min bull% across regimes >= 8pp
    # OR any regime has |NetEV| >= 0.8
    interesting = []
    for sk in sorted(all_slots):
        regimes = slot_data[sk]
        bull_pcts = [regimes[r].get('bull_pct', 50) for r in regimes]
        net_evs = [regimes[r].get('net_ev_bps', 0) for r in regimes]
        spread = max(bull_pcts) - min(bull_pcts) if bull_pcts else 0
        max_netev = max(abs(nev) for nev in net_evs) if net_evs else 0
        if spread >= 8 or max_netev >= 0.8:
            # Get aggregate stats
            agg = next((s for s in global_stats if s['slot'] == sk), None)
            interesting.append((sk, spread, max_netev, agg))

    # Sort by max regime spread
    interesting.sort(key=lambda x: x[1], reverse=True)

    print()
    print('=' * 110)
    print(f'  PER-REGIME DIRECTIONAL ANALYSIS ({slot_minutes}m slots)  '
          '(HMM-conditioned)')
    print('=' * 110)

    shown = 0
    for sk, spread, max_ne, agg in interesting[:20]:
        agg_bull = agg.get('bull_pct', 0) if agg else 0
        agg_net = agg.get('net_ev_bps', 0) if agg else 0
        zone = agg.get('zone', '--') if agg else '--'
        label = f'{sk[0]:02d}:{sk[1]:02d}'

        print(f'\n  Slot {label}  (zone={zone}, '
              f'agg bull={agg_bull:.1f}%, agg NetEV={agg_net:+.2f} bps, '
              f'regime spread={spread:.1f}pp)')
        print(f'  {"Regime":<12} {"Name":<10} {"N":>5} {"Bull%":>7} '
              f'{"Bear%":>7} {"BullBdy":>8} {"BearBdy":>8} '
              f'{"NetEV":>8} {"MeanTR":>8} {"Edge":>8}')
        print('  ' + '-' * 95)

        for rid in sorted(slot_data[sk].keys()):
            s = slot_data[sk][rid]
            name = state_names.get(rid, f'S{rid}')
            net = s.get('net_ev_bps', 0)
            edge = ('LONG' if net > 0.1
                    else ('SHORT' if net < -0.1 else 'NONE'))
            print(f'  {rid:<12} {name:<10} {s["n_days"]:>5} '
                  f'{s.get("bull_pct", 0):>6.1f}% '
                  f'{s.get("bear_pct", 0):>6.1f}% '
                  f'{s.get("mean_bull_body", 0):>8.2f} '
                  f'{s.get("mean_bear_body", 0):>8.2f} '
                  f'{net:>+8.2f} '
                  f'{s["mean_tr_bps"]:>8.2f} '
                  f'{edge:>8}')

        shown += 1

    if shown == 0:
        print('\n  No slots with significant regime variation found.')

    print()
    print('-' * 110)
    print('  INTERPRETATION: If a slot shows LONG in one regime and '
          'SHORT/NONE in another,')
    print('  the aggregate signal is regime-dependent, not a universal edge.')
    print('                    spread >= 15pp = UNSTABLE (regime-dependent, '
          'aggregate is misleading)')
    print('-' * 110)


def print_magnitude_summary(stats, n_top=10):
    """Print top slots by NetEV (frequency x magnitude expected value).

    NetEV = bull% x mean_bull_body - bear% x mean_bear_body
    Positive = long-only has expected edge.  Negative = short-only has edge.
    """
    ranked = sorted(stats, key=lambda s: abs(s.get('net_ev_bps', 0)),
                    reverse=True)

    print()
    print('-' * 100)
    print(f'  TOP {n_top} SLOTS BY NET EXPECTED VALUE '
          '(freq x magnitude, long-only edge)')
    print('-' * 100)
    print(f'  {"#":>3} {"Slot":<8} {"Bull%":>6} {"Bear%":>6} '
          f'{"BullBdy":>8} {"BearBdy":>8} {"NetEV":>8} '
          f'{"MeanTR":>8} {"Zone":>6} {"Edge":>8}')
    print(f'  {"":>3} {"":8} {"":>6} {"":>6} '
          f'{"(bps)":>8} {"(bps)":>8} {"(bps)":>8} '
          f'{"(bps)":>8} {"":>6} {"":>8}')
    print('-' * 100)

    for i, s in enumerate(ranked[:n_top], 1):
        net_ev = s.get('net_ev_bps', 0)
        edge = 'LONG' if net_ev > 0.1 else ('SHORT' if net_ev < -0.1 else 'NONE')
        print(f'  {i:>3} {s["slot_label"]:<8} '
              f'{s.get("bull_pct", 0):>5.1f}% '
              f'{s.get("bear_pct", 0):>5.1f}% '
              f'{s.get("mean_bull_body", 0):>8.2f} '
              f'{s.get("mean_bear_body", 0):>8.2f} '
              f'{net_ev:>+8.2f} '
              f'{s["mean_tr_bps"]:>8.2f} '
              f'{s.get("zone", "--"):>6} '
              f'{edge:>8}')


# ============================================================================
# PHASE E: STATISTICAL VALIDATION
# ============================================================================

# --- E1: Permutation Test (Bootstrap Significance) ---

def permutation_test_slots(slot_metrics, n_permutations=10000, seed=42):
    """Permutation test for directional bias significance.

    For each slot, shuffles the bull/bear labels across ALL slots to build
    a null distribution of bull%.  Computes empirical p-value.

    Returns list of dicts with slot_key, observed bull%, p-value, significant.
    """
    rng = random.Random(seed)

    # Collect all signed bodies across all slots (the universe)
    all_signed = []
    slot_order = sorted(slot_metrics.keys())
    slot_sizes = {}
    for sk in slot_order:
        metrics = slot_metrics[sk]
        signs = [1 if m['body_signed_bps'] > 0 else 0 for m in metrics]
        slot_sizes[sk] = len(signs)
        all_signed.extend(signs)

    total_obs = len(all_signed)

    results = []
    for sk in slot_order:
        n = slot_sizes[sk]
        observed_bulls = sum(
            1 for m in slot_metrics[sk] if m['body_signed_bps'] > 0
        )
        observed_pct = observed_bulls / n * 100 if n else 0

        # Null distribution: randomly sample n observations from all_signed
        null_counts = []
        for _ in range(n_permutations):
            sample = rng.choices(all_signed, k=n)
            null_counts.append(sum(sample))

        null_counts.sort()
        # Two-sided p-value: how extreme is observed vs null?
        count_ge = sum(1 for c in null_counts if c >= observed_bulls)
        count_le = sum(1 for c in null_counts if c <= observed_bulls)
        p_upper = count_ge / n_permutations
        p_lower = count_le / n_permutations
        p_value = 2 * min(p_upper, p_lower)
        p_value = min(p_value, 1.0)

        # Null mean for reference
        null_mean_pct = sum(null_counts) / n_permutations / n * 100 if n else 50

        results.append({
            'slot': sk,
            'slot_label': f'{sk[0]:02d}:{sk[1]:02d}',
            'n_days': n,
            'observed_bull_pct': observed_pct,
            'null_mean_pct': null_mean_pct,
            'p_value': p_value,
            'significant_05': p_value < 0.05,
            'significant_01': p_value < 0.01,
        })

    return results


def print_permtest_results(perm_results, slot_minutes):
    """Print permutation test results, highlighting significant slots."""
    print()
    print('=' * 100)
    print(f'  E1: PERMUTATION TEST — DIRECTIONAL SIGNIFICANCE ({slot_minutes}m)')
    print(f'  H0: "slot has no directional bias" (bull% = global baseline)')
    print(f'  Method: 10,000 permutations, two-sided test')
    print('=' * 100)
    print(f'  {"Slot":<8} {"N":>5} {"Bull%":>7} {"Null%":>7} '
          f'{"Diff":>7} {"p-value":>10} {"Sig":>6}')
    print('  ' + '-' * 65)

    sig_slots = []
    for r in perm_results:
        diff = r['observed_bull_pct'] - r['null_mean_pct']
        if r['significant_01']:
            sig = '**'
        elif r['significant_05']:
            sig = '*'
        else:
            sig = ''

        # Only print significant or near-significant slots
        if r['p_value'] < 0.10 or abs(diff) > 3:
            print(f'  {r["slot_label"]:<8} {r["n_days"]:>5} '
                  f'{r["observed_bull_pct"]:>6.1f}% '
                  f'{r["null_mean_pct"]:>6.1f}% '
                  f'{diff:>+6.1f}% '
                  f'{r["p_value"]:>10.4f} {sig:>6}')
            if r['significant_05']:
                sig_slots.append(r)

    # Summary
    total = len(perm_results)
    n_sig_05 = sum(1 for r in perm_results if r['significant_05'])
    n_sig_01 = sum(1 for r in perm_results if r['significant_01'])
    print(f'\n  Total slots: {total}  |  '
          f'Significant p<0.05: {n_sig_05}  |  p<0.01: {n_sig_01}')

    # Expected false positives under H0
    expected_fp = total * 0.05
    print(f'  Expected false positives at p<0.05 under H0: '
          f'{expected_fp:.1f} slots')
    if n_sig_05 <= expected_fp:
        print('  >>> WARNING: significant count within noise range <<<')
    else:
        print(f'  >>> {n_sig_05 - expected_fp:.0f} slots ABOVE noise floor <<<')

    if sig_slots:
        print(f'\n  SIGNIFICANT DIRECTIONAL SLOTS (p < 0.05):')
        for r in sorted(sig_slots, key=lambda x: x['p_value']):
            direction = 'BULL' if r['observed_bull_pct'] > 50 else 'BEAR'
            print(f'    {r["slot_label"]}  {direction}  '
                  f'bull={r["observed_bull_pct"]:.1f}%  '
                  f'p={r["p_value"]:.4f}')

    print()


# --- E2: Return Distribution Analysis ---

def compute_return_distribution(slot_metrics):
    """Compute full return distribution stats per slot.

    Returns list of dicts with quantiles, skewness, kurtosis, payoff ratio.
    """
    slot_order = sorted(slot_metrics.keys())
    results = []

    for sk in slot_order:
        metrics = slot_metrics[sk]
        signed = sorted(m['body_signed_bps'] for m in metrics)
        n = len(signed)
        if n < 10:
            continue

        mean_ret = sum(signed) / n
        std_ret = _std(signed, mean_ret)

        # Quantiles
        q10 = _percentile(signed, 10)
        q25 = _percentile(signed, 25)
        q50 = _percentile(signed, 50)  # median
        q75 = _percentile(signed, 75)
        q90 = _percentile(signed, 90)

        # Skewness (Fisher)
        if std_ret > 0:
            skew = (sum((v - mean_ret) ** 3 for v in signed)
                    / (n * std_ret ** 3))
        else:
            skew = 0.0

        # Excess kurtosis
        if std_ret > 0:
            kurt = (sum((v - mean_ret) ** 4 for v in signed)
                    / (n * std_ret ** 4)) - 3.0
        else:
            kurt = 0.0

        # Payoff analysis
        wins = [s for s in signed if s > 0]
        losses = [abs(s) for s in signed if s < 0]
        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        payoff_ratio = avg_win / avg_loss if avg_loss > 0 else float('inf')

        # Expected value per trade
        win_rate = len(wins) / n
        expectancy = win_rate * avg_win - (1 - win_rate) * avg_loss

        results.append({
            'slot': sk,
            'slot_label': f'{sk[0]:02d}:{sk[1]:02d}',
            'n': n,
            'mean': mean_ret,
            'std': std_ret,
            'q10': q10,
            'q25': q25,
            'median': q50,
            'q75': q75,
            'q90': q90,
            'skew': skew,
            'kurtosis': kurt,
            'win_rate': win_rate * 100,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'payoff_ratio': payoff_ratio,
            'expectancy': expectancy,
        })

    return results


def print_distribution_results(dist_results, slot_minutes):
    """Print return distribution analysis for slots with directional bias."""
    # Filter to interesting slots: expectancy != 0 or win_rate far from 50
    interesting = [r for r in dist_results
                   if abs(r['win_rate'] - 50) > 4 or abs(r['expectancy']) > 0.3]

    if not interesting:
        interesting = sorted(dist_results,
                             key=lambda x: abs(x['expectancy']),
                             reverse=True)[:10]

    print()
    print('=' * 115)
    print(f'  E2: RETURN DISTRIBUTION ANALYSIS ({slot_minutes}m)')
    print(f'  Full distribution of per-slot returns (body_signed_bps)')
    print('=' * 115)

    # Table 1: Quantiles
    print(f'\n  {"Slot":<8} {"N":>5} {"Mean":>7} {"Med":>7} '
          f'{"Q10":>7} {"Q25":>7} {"Q75":>7} {"Q90":>7} '
          f'{"Skew":>7} {"Kurt":>7}')
    print('  ' + '-' * 85)

    for r in sorted(interesting, key=lambda x: x['slot']):
        print(f'  {r["slot_label"]:<8} {r["n"]:>5} '
              f'{r["mean"]:>+7.2f} {r["median"]:>+7.2f} '
              f'{r["q10"]:>+7.2f} {r["q25"]:>+7.2f} '
              f'{r["q75"]:>+7.2f} {r["q90"]:>+7.2f} '
              f'{r["skew"]:>+7.2f} {r["kurtosis"]:>+7.2f}')

    # Table 2: Payoff analysis
    print(f'\n  {"Slot":<8} {"WinRate":>8} {"AvgWin":>8} {"AvgLoss":>8} '
          f'{"Payoff":>8} {"Expect":>8} {"Edge":>8}')
    print(f'  {"":8} {"(%)":>8} {"(bps)":>8} {"(bps)":>8} '
          f'{"ratio":>8} {"(bps)":>8} {"":>8}')
    print('  ' + '-' * 70)

    for r in sorted(interesting, key=lambda x: x['expectancy'], reverse=True):
        if r['expectancy'] > 0.1:
            edge = 'LONG'
        elif r['expectancy'] < -0.1:
            edge = 'SHORT'
        else:
            edge = '--'

        pr_str = (f'{r["payoff_ratio"]:>8.2f}'
                  if r['payoff_ratio'] < 100 else '     inf')
        print(f'  {r["slot_label"]:<8} {r["win_rate"]:>7.1f}% '
              f'{r["avg_win"]:>8.2f} {r["avg_loss"]:>8.2f} '
              f'{pr_str} '
              f'{r["expectancy"]:>+8.3f} {edge:>8}')

    print()


# --- E3: Naive Backtest with Transaction Costs ---

def naive_slot_backtest(slot_metrics, slot_minutes, spread_bps=1.0,
                        direction='long'):
    """Simulate trading a single slot: enter at open, exit at close.

    Args:
        slot_metrics: dict slot_key -> list of per-day metric dicts
        slot_minutes: slot size
        spread_bps: round-trip transaction cost in bps
        direction: 'long' or 'short'

    Returns dict per slot: equity curve, Sharpe, max DD, PnL stats.
    """
    slot_order = sorted(slot_metrics.keys())
    results = []

    for sk in slot_order:
        metrics = sorted(slot_metrics[sk], key=lambda m: m['date'])
        n = len(metrics)
        if n < 60:
            continue

        # PnL per trade
        pnls = []
        for m in metrics:
            raw = m['body_signed_bps']
            if direction == 'short':
                raw = -raw
            net = raw - spread_bps
            pnls.append(net)

        # Equity curve (cumulative)
        equity = [0.0]
        for pnl in pnls:
            equity.append(equity[-1] + pnl)

        # Stats
        total_pnl = equity[-1]
        mean_pnl = sum(pnls) / n
        std_pnl = _std(pnls, mean_pnl) if n > 1 else 1.0
        sharpe = mean_pnl / std_pnl * math.sqrt(252) if std_pnl > 0 else 0

        # Max drawdown
        peak = 0.0
        max_dd = 0.0
        for eq in equity:
            if eq > peak:
                peak = eq
            dd = peak - eq
            if dd > max_dd:
                max_dd = dd

        # Win rate (net of costs)
        wins = sum(1 for p in pnls if p > 0)
        win_rate = wins / n * 100

        # Profit factor
        gross_win = sum(p for p in pnls if p > 0)
        gross_loss = abs(sum(p for p in pnls if p < 0))
        pf = gross_win / gross_loss if gross_loss > 0 else float('inf')

        # Walk-forward: split by year
        year_pnls = defaultdict(list)
        for m, pnl in zip(metrics, pnls):
            year_pnls[m['date'].year].append(pnl)

        yearly_results = []
        for year in sorted(year_pnls.keys()):
            yp = year_pnls[year]
            yn = len(yp)
            y_total = sum(yp)
            y_mean = y_total / yn
            y_std = _std(yp, y_mean) if yn > 1 else 1.0
            y_sharpe = y_mean / y_std * math.sqrt(252) if y_std > 0 else 0
            y_wins = sum(1 for p in yp if p > 0)
            y_gw = sum(p for p in yp if p > 0)
            y_gl = abs(sum(p for p in yp if p < 0))
            y_pf = y_gw / y_gl if y_gl > 0 else float('inf')
            yearly_results.append({
                'year': year,
                'n': yn,
                'total_pnl': y_total,
                'mean_pnl': y_mean,
                'sharpe': y_sharpe,
                'win_rate': y_wins / yn * 100 if yn else 0,
                'pf': y_pf,
            })

        results.append({
            'slot': sk,
            'slot_label': f'{sk[0]:02d}:{sk[1]:02d}',
            'direction': direction.upper(),
            'n_trades': n,
            'spread_bps': spread_bps,
            'total_pnl': total_pnl,
            'mean_pnl': mean_pnl,
            'std_pnl': std_pnl,
            'sharpe': sharpe,
            'max_dd': max_dd,
            'win_rate': win_rate,
            'profit_factor': pf,
            'equity': equity,
            'yearly': yearly_results,
        })

    return results


def print_naive_backtest(bt_results, slot_minutes, focus_slots=None):
    """Print naive backtest results with walk-forward yearly breakdown."""

    # Filter to focus_slots if provided, else show top 10 by Sharpe
    if focus_slots:
        show = [r for r in bt_results if r['slot'] in focus_slots]
    else:
        show = sorted(bt_results, key=lambda x: x['sharpe'], reverse=True)[:10]

    if not show:
        print('\n  No backtest results to show.')
        return

    spread = show[0]['spread_bps'] if show else 0

    print()
    print('=' * 115)
    print(f'  E3: NAIVE SLOT BACKTEST ({slot_minutes}m)')
    print(f'  Strategy: enter at slot open, exit at slot close')
    print(f'  Transaction cost: {spread:.1f} bps round-trip')
    print('=' * 115)

    # Summary table
    print(f'\n  {"Slot":<8} {"Dir":<6} {"N":>5} {"TotPnL":>9} '
          f'{"MeanPnL":>9} {"Sharpe":>8} {"MaxDD":>8} '
          f'{"WinR%":>7} {"PF":>7}')
    print('  ' + '-' * 80)

    for r in sorted(show, key=lambda x: x['sharpe'], reverse=True):
        pf_str = (f'{r["profit_factor"]:>7.2f}'
                  if r['profit_factor'] < 100 else '    inf')
        print(f'  {r["slot_label"]:<8} {r["direction"]:<6} '
              f'{r["n_trades"]:>5} '
              f'{r["total_pnl"]:>+9.1f} '
              f'{r["mean_pnl"]:>+9.3f} '
              f'{r["sharpe"]:>+8.2f} '
              f'{r["max_dd"]:>8.1f} '
              f'{r["win_rate"]:>6.1f}% '
              f'{pf_str}')

    # Walk-forward yearly breakdown for each slot
    for r in sorted(show, key=lambda x: x['slot']):
        print(f'\n  --- {r["slot_label"]} {r["direction"]} '
              f'(spread={r["spread_bps"]:.1f} bps) ---')
        print(f'  {"Year":>6} {"N":>5} {"TotPnL":>9} {"MeanPnL":>9} '
              f'{"Sharpe":>8} {"WinR%":>7} {"PF":>7} {"Verdict":>10}')
        print('  ' + '-' * 70)

        all_profitable = True
        for y in r['yearly']:
            pf_str = (f'{y["pf"]:>7.2f}'
                      if y['pf'] < 100 else '    inf')
            if y['total_pnl'] > 0:
                verdict = 'WIN'
            else:
                verdict = 'LOSS'
                all_profitable = False
            print(f'  {y["year"]:>6} {y["n"]:>5} '
                  f'{y["total_pnl"]:>+9.1f} '
                  f'{y["mean_pnl"]:>+9.3f} '
                  f'{y["sharpe"]:>+8.2f} '
                  f'{y["win_rate"]:>6.1f}% '
                  f'{pf_str} {verdict:>10}')

        if all_profitable:
            print(f'  >>> ALL YEARS PROFITABLE — robust edge <<<')
        else:
            losing_years = [y['year'] for y in r['yearly']
                            if y['total_pnl'] <= 0]
            print(f'  >>> LOSING YEARS: {losing_years} <<<')

    print()


# ============================================================================
# MATPLOTLIB PLOT
# ============================================================================

def plot_profile(stats, transitions, asset, slot_minutes, save_dir=None):
    """Generate matplotlib chart with volatility profile and zone markers."""
    try:
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
    except ImportError:
        print('\n  matplotlib not installed -- skipping plot.')
        return

    labels = [s['slot_label'] for s in stats]
    tr_vals = [s['mean_tr_bps'] for s in stats]
    z_vals = [s['z_score'] for s in stats]
    zones = [s.get('zone', '--') for s in stats]

    # Colors by zone
    colors = []
    for z in zones:
        if z == 'HOT':
            colors.append('#e74c3c')
        elif z == 'COLD':
            colors.append('#3498db')
        else:
            colors.append('#95a5a6')

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 9), sharex=True,
                                    gridspec_kw={'height_ratios': [3, 1]})
    fig.suptitle(f'{asset} -- Liquidity Profile ({slot_minutes}m slots)',
                 fontsize=14, fontweight='bold')

    # Top: TR bars
    ax1.bar(range(len(labels)), tr_vals, color=colors, edgecolor='white',
            linewidth=0.5)
    ax1.set_ylabel('Mean True Range (bps)')
    ax1.axhline(y=sum(tr_vals)/len(tr_vals), color='orange',
                linestyle='--', linewidth=1, label='Global Mean')
    ax1.legend(loc='upper right')
    ax1.grid(axis='y', alpha=0.3)

    # Mark transitions with arrows
    for t in transitions:
        # Find peak index
        peak_label = t['peak_slot']
        if peak_label in labels:
            idx = labels.index(peak_label)
            ax1.annotate('', xy=(idx, tr_vals[idx]),
                         xytext=(idx, tr_vals[idx] * 1.15),
                         arrowprops=dict(arrowstyle='->', color='red', lw=2))

    # Bottom: Z-score line
    ax2.fill_between(range(len(labels)), z_vals,
                     where=[z >= 0.75 for z in z_vals],
                     color='#e74c3c', alpha=0.3, label='HOT zone')
    ax2.fill_between(range(len(labels)), z_vals,
                     where=[z <= -0.50 for z in z_vals],
                     color='#3498db', alpha=0.3, label='COLD zone')
    ax2.plot(range(len(labels)), z_vals, color='black', linewidth=1.2)
    ax2.axhline(y=0, color='gray', linestyle='-', linewidth=0.5)
    ax2.axhline(y=0.75, color='red', linestyle=':', linewidth=0.8, alpha=0.7)
    ax2.axhline(y=-0.50, color='blue', linestyle=':', linewidth=0.8, alpha=0.7)
    ax2.set_ylabel('Z-Score')
    ax2.legend(loc='upper right')
    ax2.grid(axis='y', alpha=0.3)

    # X-axis labels
    step = max(1, len(labels) // 24)
    ax2.set_xticks(range(0, len(labels), step))
    ax2.set_xticklabels([labels[i] for i in range(0, len(labels), step)],
                        rotation=45, ha='right', fontsize=8)
    ax2.set_xlabel('Time of Day (UTC)')

    plt.tight_layout()
    if save_dir:
        path = os.path.join(save_dir, f'{asset}_{slot_minutes}m_profile.png')
        fig.savefig(path, dpi=150, bbox_inches='tight')
        print(f'  Saved: {path}')
        plt.close(fig)
    else:
        plt.show()


def plot_permtest(perm_results, asset, slot_minutes, save_dir=None):
    """E1 plot: directional bias significance per slot."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print('\n  matplotlib not installed -- skipping plot.')
        return

    labels = [r['slot_label'] for r in perm_results]
    diffs = [r['observed_bull_pct'] - r['null_mean_pct'] for r in perm_results]
    p_vals = [r['p_value'] for r in perm_results]

    # Colors: green/red for significant bull/bear, gray otherwise
    colors = []
    for r, d in zip(perm_results, diffs):
        if r['significant_05'] and d > 0:
            colors.append('#2ecc71')
        elif r['significant_05'] and d < 0:
            colors.append('#e74c3c')
        else:
            colors.append('#bdc3c7')

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(18, 9), sharex=True,
                                    gridspec_kw={'height_ratios': [2, 1]})
    fig.suptitle(f'{asset} — E1: Permutation Test ({slot_minutes}m slots)',
                 fontsize=14, fontweight='bold')

    # Top: bull% deviation from null
    ax1.bar(range(len(labels)), diffs, color=colors, edgecolor='white',
            linewidth=0.3)
    ax1.axhline(y=0, color='black', linewidth=0.8)
    ax1.set_ylabel('Bull% − Null Mean (%)')
    ax1.set_title('Directional Bias Deviation (green=BULL, red=BEAR, gray=NS)')
    ax1.grid(axis='y', alpha=0.3)

    # Annotate top significant slots
    for i, (r, d) in enumerate(zip(perm_results, diffs)):
        if r['significant_01'] and abs(d) > 3:
            ax1.annotate(f'{d:+.1f}%\np={r["p_value"]:.4f}',
                         xy=(i, d), fontsize=6, ha='center',
                         va='bottom' if d > 0 else 'top')

    # Bottom: -log10(p-value)
    neg_log_p = [-math.log10(max(p, 1e-10)) for p in p_vals]
    ax2.bar(range(len(labels)), neg_log_p, color=colors, edgecolor='white',
            linewidth=0.3)
    ax2.axhline(y=-math.log10(0.05), color='orange', linestyle='--',
                linewidth=1.2, label='p = 0.05')
    ax2.axhline(y=-math.log10(0.01), color='red', linestyle='--',
                linewidth=1.2, label='p = 0.01')
    ax2.set_ylabel('−log₁₀(p-value)')
    ax2.legend(loc='upper right')
    ax2.grid(axis='y', alpha=0.3)

    # X-axis labels
    step = max(1, len(labels) // 24)
    ax2.set_xticks(range(0, len(labels), step))
    ax2.set_xticklabels([labels[i] for i in range(0, len(labels), step)],
                        rotation=45, ha='right', fontsize=8)
    ax2.set_xlabel('Time of Day (UTC)')

    plt.tight_layout()
    if save_dir:
        path = os.path.join(save_dir, f'{asset}_{slot_minutes}m_E1_permtest.png')
        fig.savefig(path, dpi=150, bbox_inches='tight')
        print(f'  Saved: {path}')
        plt.close(fig)
    else:
        plt.show()


def plot_distribution(dist_results, asset, slot_minutes, save_dir=None):
    """E2 plot: return distribution + expectancy for interesting slots."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print('\n  matplotlib not installed -- skipping plot.')
        return

    # Select interesting slots
    interesting = sorted(dist_results,
                         key=lambda x: abs(x['expectancy']),
                         reverse=True)[:20]
    interesting.sort(key=lambda x: x['slot'])

    if not interesting:
        print('\n  No interesting slots to plot.')
        return

    labels = [r['slot_label'] for r in interesting]
    exp_vals = [r['expectancy'] for r in interesting]
    win_rates = [r['win_rate'] for r in interesting]
    payoffs = [min(r['payoff_ratio'], 3.0) for r in interesting]

    fig, axes = plt.subplots(3, 1, figsize=(18, 12), sharex=True,
                              gridspec_kw={'height_ratios': [2, 1, 1]})
    fig.suptitle(
        f'{asset} — E2: Return Distribution ({slot_minutes}m slots)',
        fontsize=14, fontweight='bold')

    # Top: Expectancy bar chart
    colors = ['#2ecc71' if e > 0.1 else '#e74c3c' if e < -0.1
              else '#95a5a6' for e in exp_vals]
    axes[0].bar(range(len(labels)), exp_vals, color=colors,
                edgecolor='white', linewidth=0.3)
    axes[0].axhline(y=0, color='black', linewidth=0.8)
    axes[0].set_ylabel('Expectancy (bps/trade)')
    axes[0].set_title('Expected Value per Trade (green=LONG edge, red=SHORT edge)')
    axes[0].grid(axis='y', alpha=0.3)

    # Annotate top
    for i, (r, e) in enumerate(zip(interesting, exp_vals)):
        if abs(e) > 0.5:
            axes[0].annotate(f'{e:+.2f}', xy=(i, e), fontsize=7,
                             ha='center',
                             va='bottom' if e > 0 else 'top')

    # Middle: Win rate
    wr_colors = ['#2ecc71' if w > 55 else '#e74c3c' if w < 45
                 else '#f39c12' for w in win_rates]
    axes[1].bar(range(len(labels)), win_rates, color=wr_colors,
                edgecolor='white', linewidth=0.3)
    axes[1].axhline(y=50, color='black', linewidth=0.8, linestyle='--')
    axes[1].set_ylabel('Win Rate (%)')
    axes[1].set_ylim(30, 70)
    axes[1].grid(axis='y', alpha=0.3)

    # Bottom: Payoff ratio
    pr_colors = ['#2ecc71' if p > 1.1 else '#e74c3c' if p < 0.9
                 else '#f39c12' for p in payoffs]
    axes[2].bar(range(len(labels)), payoffs, color=pr_colors,
                edgecolor='white', linewidth=0.3)
    axes[2].axhline(y=1.0, color='black', linewidth=0.8, linestyle='--')
    axes[2].set_ylabel('Payoff Ratio')
    axes[2].set_ylim(0.5, 2.0)
    axes[2].grid(axis='y', alpha=0.3)

    axes[2].set_xticks(range(len(labels)))
    axes[2].set_xticklabels(labels, rotation=45, ha='right', fontsize=8)
    axes[2].set_xlabel('Time of Day (UTC)')

    plt.tight_layout()
    if save_dir:
        path = os.path.join(save_dir, f'{asset}_{slot_minutes}m_E2_distribution.png')
        fig.savefig(path, dpi=150, bbox_inches='tight')
        print(f'  Saved: {path}')
        plt.close(fig)
    else:
        plt.show()


def plot_naive_backtest(bt_results, asset, slot_minutes, focus_slots=None,
                        save_dir=None):
    """E3 plot: equity curves + yearly PnL breakdown."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print('\n  matplotlib not installed -- skipping plot.')
        return

    # Select slots to show
    if focus_slots:
        show = [r for r in bt_results if r['slot'] in focus_slots]
    else:
        show = sorted(bt_results, key=lambda x: x['sharpe'],
                      reverse=True)[:6]

    if not show:
        print('\n  No backtest results to plot.')
        return

    spread = show[0]['spread_bps']

    # Collect all years for the yearly subplot
    all_years = sorted(set(
        y['year'] for r in show for y in r['yearly']
    ))

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(18, 10),
                                    gridspec_kw={'height_ratios': [3, 2]})
    fig.suptitle(
        f'{asset} — E3: Naive Backtest ({slot_minutes}m, '
        f'spread={spread:.1f} bps)',
        fontsize=14, fontweight='bold')

    # Top: Equity curves
    palette = ['#2ecc71', '#e74c3c', '#3498db', '#f39c12',
               '#9b59b6', '#1abc9c']
    for i, r in enumerate(sorted(show, key=lambda x: x['sharpe'],
                                  reverse=True)):
        color = palette[i % len(palette)]
        ax1.plot(r['equity'], label=(
            f'{r["slot_label"]} {r["direction"]} '
            f'(Sh={r["sharpe"]:+.2f}, PF={r["profit_factor"]:.2f})'),
            color=color, linewidth=1.2, alpha=0.85)

    ax1.axhline(y=0, color='black', linewidth=0.5)
    ax1.set_ylabel('Cumulative PnL (bps)')
    ax1.set_title('Equity Curves (net of spread)')
    ax1.legend(loc='best', fontsize=8)
    ax1.grid(alpha=0.3)

    # Bottom: Yearly PnL grouped bar chart
    n_slots = len(show)
    n_years = len(all_years)
    bar_width = 0.8 / n_slots
    x = list(range(n_years))

    for i, r in enumerate(sorted(show, key=lambda x: x['slot'])):
        year_pnls = {y['year']: y['total_pnl'] for y in r['yearly']}
        vals = [year_pnls.get(yr, 0) for yr in all_years]
        offsets = [xi + i * bar_width - (n_slots - 1) * bar_width / 2
                   for xi in x]
        bar_colors = ['#2ecc71' if v > 0 else '#e74c3c' for v in vals]
        ax2.bar(offsets, vals, width=bar_width, label=r['slot_label'],
                color=bar_colors, edgecolor=palette[i % len(palette)],
                linewidth=1.5)

    ax2.axhline(y=0, color='black', linewidth=0.8)
    ax2.set_xticks(x)
    ax2.set_xticklabels([str(yr) for yr in all_years], fontsize=10)
    ax2.set_ylabel('Year PnL (bps)')
    ax2.set_title('Walk-Forward Yearly Breakdown')
    ax2.legend(loc='best', fontsize=8)
    ax2.grid(axis='y', alpha=0.3)

    plt.tight_layout()
    if save_dir:
        path = os.path.join(save_dir, f'{asset}_{slot_minutes}m_E3_backtest.png')
        fig.savefig(path, dpi=150, bbox_inches='tight')
        print(f'  Saved: {path}')
        plt.close(fig)
    else:
        plt.show()


def main():
    parser = argparse.ArgumentParser(
        description='Liquidity/Volatility Profile Analyzer')
    parser.add_argument('asset', type=str,
                        help='Asset symbol (e.g. AUS200, EURUSD, TLT)')
    parser.add_argument('--slot', type=int, default=60,
                        choices=[5, 15, 30, 60],
                        help='Slot size in minutes (default: 60)')
    parser.add_argument('--from', dest='from_date', type=str, default=None,
                        help='Start date YYYY-MM-DD')
    parser.add_argument('--to', dest='to_date', type=str, default=None,
                        help='End date YYYY-MM-DD')
    parser.add_argument('--plot', action='store_true',
                        help='Show matplotlib chart')
    parser.add_argument('--valley', action='store_true',
                        help='Focus on valley analysis (COLD run details)')
    parser.add_argument('--days', type=str, default=None,
                        help='Filter by day of week (comma-separated, 0=Mon)')
    parser.add_argument('--hot', type=float, default=0.75,
                        help='Z-score threshold for HOT zone (default: 0.75)')
    parser.add_argument('--cold', type=float, default=-0.50,
                        help='Z-score threshold for COLD zone (default: -0.50)')
    parser.add_argument('--yearly', action='store_true',
                        help='Show per-year directional breakdown '
                             '(regime stability check)')
    parser.add_argument('--hmm', action='store_true',
                        help='HMM regime detection: split analysis by '
                             'calm/normal/volatile regimes')
    parser.add_argument('--hmm-states', type=int, default=3,
                        choices=[2, 3],
                        help='Number of HMM states (default: 3)')
    parser.add_argument('--permtest', action='store_true',
                        help='E1: Permutation test for directional significance')
    parser.add_argument('--distribution', action='store_true',
                        help='E2: Full return distribution analysis')
    parser.add_argument('--naive-bt', action='store_true',
                        help='E3: Naive slot backtest with transaction costs')
    parser.add_argument('--spread', type=float, default=1.0,
                        help='Round-trip spread in bps for naive backtest '
                             '(default: 1.0)')
    parser.add_argument('--bt-direction', type=str, default='long',
                        choices=['long', 'short'],
                        help='Trade direction for naive backtest '
                             '(default: long)')
    parser.add_argument('--focus-slots', type=str, default=None,
                        help='Comma-separated slots for E3 focus '
                             '(e.g. "22:00,23:00,20:45")')
    parser.add_argument('--plot-dir', type=str, default=None,
                        help='Save plots as PNG to this directory '
                             '(instead of showing interactively)')

    args = parser.parse_args()

    from_dt = (datetime.strptime(args.from_date, '%Y-%m-%d')
               if args.from_date else None)
    to_dt = (datetime.strptime(args.to_date, '%Y-%m-%d')
             if args.to_date else None)
    allowed_days = None
    if args.days:
        allowed_days = [int(d.strip()) for d in args.days.split(',')]

    save_dir = args.plot_dir
    if save_dir:
        os.makedirs(save_dir, exist_ok=True)
        import matplotlib
        matplotlib.use('Agg')

    # Load data
    print(f'\nLoading {args.asset} data...')
    rows = load_csv_data(args.asset, from_dt, to_dt)
    if not rows:
        print('No data loaded.')
        sys.exit(1)

    n_days = len(set(r['dt'].date() for r in rows))
    actual_from = rows[0]['dt'].strftime('%Y-%m-%d')
    actual_to = rows[-1]['dt'].strftime('%Y-%m-%d')

    # Aggregate
    slot_metrics = aggregate_to_slots(rows, args.slot, allowed_days)
    stats, global_mean, global_std = compute_slot_stats(slot_metrics)
    stats = classify_zones(stats, hot_threshold=args.hot,
                           cold_threshold=args.cold)
    transitions = detect_valley_peaks(stats)
    cold_runs = analyze_consecutive_cold(stats, args.slot)

    # Print results
    print_header(args.asset, args.slot, actual_from, actual_to,
                 len(rows), n_days)
    print_profile_table(stats, global_mean, global_std, args.asset, args.slot)
    print_top_slots(stats, n=10)
    print_top_quiet(stats, n=10)
    print_directional_hot(stats)
    print_magnitude_summary(stats)
    print_transitions(transitions, args.slot)
    print_day_of_week(rows, args.slot, allowed_days)

    if args.yearly:
        yearly_stats = compute_yearly_slot_stats(slot_metrics)
        print_yearly_breakdown(yearly_stats, stats, args.slot)

    if args.hmm:
        daily_feats = compute_daily_features(rows)
        regime_labels, hmm_model, state_names = fit_hmm_regimes(
            daily_feats, n_states=args.hmm_states)
        if regime_labels is not None:
            print_hmm_summary(regime_labels, state_names, daily_feats)
            regime_stats = compute_regime_slot_stats(
                slot_metrics, regime_labels)
            print_regime_directional(
                regime_stats, state_names, args.slot, stats)

    if args.permtest:
        perm_results = permutation_test_slots(slot_metrics)
        print_permtest_results(perm_results, args.slot)
        if args.plot:
            plot_permtest(perm_results, args.asset, args.slot, save_dir)

    if args.distribution:
        dist_results = compute_return_distribution(slot_metrics)
        print_distribution_results(dist_results, args.slot)
        if args.plot:
            plot_distribution(dist_results, args.asset, args.slot, save_dir)

    if args.naive_bt:
        # Parse focus slots
        focus = None
        if args.focus_slots:
            focus = []
            for s in args.focus_slots.split(','):
                s = s.strip()
                parts = s.split(':')
                if len(parts) == 2:
                    focus.append((int(parts[0]), int(parts[1])))
        bt_results = naive_slot_backtest(
            slot_metrics, args.slot,
            spread_bps=args.spread,
            direction=args.bt_direction)
        print_naive_backtest(bt_results, args.slot, focus_slots=focus)
        if args.plot:
            plot_naive_backtest(bt_results, args.asset, args.slot,
                                focus_slots=focus, save_dir=save_dir)

    if args.valley:
        print_cold_runs(cold_runs, args.slot)

    if args.plot:
        plot_profile(stats, transitions, args.asset, args.slot, save_dir)

    print()


if __name__ == '__main__':
    main()
