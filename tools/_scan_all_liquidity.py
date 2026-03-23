"""Scan all assets in data/ and produce a liquidity profile summary table."""
import subprocess
import re
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
os.chdir(PROJECT_ROOT)

# Discover assets from data/*.csv
data_dir = os.path.join(PROJECT_ROOT, 'data')
assets = sorted(set(
    f.replace('_5m_5Yea.csv', '')
    for f in os.listdir(data_dir)
    if f.endswith('_5m_5Yea.csv') and 'copy' not in f.lower()
))

print(f"{'Asset':<10} {'Mean':>6} {'HOTpk':>6} {'HOT_Z':>6} {'HOTtime':>8} "
      f"{'COLDlo':>7} {'COLD_Z':>7} {'Ratio':>6} {'Bull%':>6} {'Bear%':>6} "
      f"{'#HOT':>5} {'ValleyMin':>10}")
print('-' * 110)

for asset in assets:
    try:
        r = subprocess.run(
            [sys.executable, 'tools/liquidity_profile.py', asset,
             '--slot', '15', '--valley'],
            capture_output=True, text=True, timeout=180,
        )
        out = r.stdout + r.stderr

        # Global mean
        m = re.search(r'Global mean TR:\s+([\d.]+)\s+bps', out)
        mean_tr = float(m.group(1)) if m else 0

        # HOT lines
        hot_lines = re.findall(
            r'(\d{2}:\d{2})\s+\d+\s+([\d.]+)\s+[\d.]+\s+'
            r'([+-]?[\d.]+)\s+([\d.]+)%\s+([\d.]+)%\s+'
            r'[+-]?[\d.]+\s+>>HOT',
            out
        )
        n_hot = len(hot_lines)

        if hot_lines:
            best = max(hot_lines, key=lambda x: float(x[1]))
            hot_time = best[0]
            hot_peak = float(best[1])
            hot_z = float(best[2])
            hot_bull = float(best[3])
            hot_bear = float(best[4])
        else:
            hot_time = '-'
            hot_peak = hot_z = hot_bull = hot_bear = 0

        # COLD lines
        cold_lines = re.findall(
            r'(\d{2}:\d{2})\s+\d+\s+([\d.]+)\s+[\d.]+\s+'
            r'([+-]?[\d.]+)\s+[\d.]+%\s+[\d.]+%\s+'
            r'[+-]?[\d.]+\s+cold',
            out
        )
        if cold_lines:
            worst = min(cold_lines, key=lambda x: float(x[1]))
            cold_low = float(worst[1])
            cold_z = float(worst[2])
        else:
            cold_low = cold_z = 0

        ratio = hot_peak / cold_low if cold_low > 0 else 0

        # Valley duration (avg)
        vm = re.search(r'Avg valley duration:\s+([\d.]+)\s+slots\s+\((\d+)\s+min\)', out)
        valley_min = vm.group(2) if vm else '-'

        print(f"{asset:<10} {mean_tr:>6.1f} {hot_peak:>6.1f} {hot_z:>+6.2f} "
              f"{hot_time:>8} {cold_low:>7.1f} {cold_z:>+7.2f} "
              f"{ratio:>5.1f}x {hot_bull:>5.1f} {hot_bear:>5.1f} "
              f"{n_hot:>5} {valley_min:>10}")

    except Exception as e:
        print(f"{asset:<10} ERROR: {e}")
