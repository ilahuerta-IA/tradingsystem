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
    python tools/liquidity_profile.py AUS200 --from 2021-01-01 --to 2022-12-31
    python tools/liquidity_profile.py AUS200 --slot 15 --valley   # Valley detection focus
    python tools/liquidity_profile.py AUS200 --days 0,1,2,3,4     # Mon-Fri only
"""
import os
import sys
import csv
import math
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
        })

    return stats, global_mean, global_std


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


# ============================================================================
# MATPLOTLIB PLOT
# ============================================================================

def plot_profile(stats, transitions, asset, slot_minutes):
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
    plt.show()


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Liquidity/Volatility Profile Analyzer')
    parser.add_argument('asset', type=str,
                        help='Asset symbol (e.g. AUS200, EURUSD, TLT)')
    parser.add_argument('--slot', type=int, default=60,
                        choices=[15, 30, 60],
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

    args = parser.parse_args()

    from_dt = (datetime.strptime(args.from_date, '%Y-%m-%d')
               if args.from_date else None)
    to_dt = (datetime.strptime(args.to_date, '%Y-%m-%d')
             if args.to_date else None)
    allowed_days = None
    if args.days:
        allowed_days = [int(d.strip()) for d in args.days.split(',')]

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
    print_transitions(transitions, args.slot)
    print_day_of_week(rows, args.slot, allowed_days)

    if args.valley:
        print_cold_runs(cold_runs, args.slot)

    if args.plot:
        plot_profile(stats, transitions, args.asset, args.slot)

    print()


if __name__ == '__main__':
    main()
