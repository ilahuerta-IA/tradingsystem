"""Parse the GLOBAL SUMMARY from the prestudy output file."""
import os, re

fpath = os.path.join(os.path.dirname(os.path.dirname(__file__)), 
                     "context", "sp500full_prestudy_remaining293.txt")

data = open(fpath, 'rb').read()
idx = data.index(b'GLOBAL SUMMARY')
summary_data = data[idx:]

# Byte patterns (double-encoded UTF-8 via PowerShell)
PASS_BYTES = b'\xc3\x94\xc2\xa3\xc3\xa0'  # ✅ double-encoded
FAIL_BYTES = b'\xc3\x94\xc3\x98\xc3\xae'  # ❌ double-encoded - let's detect

# Find the actual fail pattern from a known fail line (SATS has a fail)
sats_idx = summary_data.index(b'SATS')
sats_end = summary_data.index(b'\n', sats_idx)
sats_line = summary_data[sats_idx:sats_end]

# Find all unique non-ASCII sequences
import collections
patterns = set()
i = 0
while i < len(sats_line):
    if sats_line[i] > 127:
        j = i
        while j < len(sats_line) and sats_line[j] > 127:
            j += 1
        patterns.add(sats_line[i:j])
        i = j
    else:
        i += 1

print("Patterns found in SATS line:")
for p in patterns:
    print(f"  {p.hex(' ')} -> {p.decode('utf-8', errors='replace')}")

FAIL_BYTES = [p for p in patterns if p != PASS_BYTES][0] if len(patterns) > 1 else None
print(f"\nPASS pattern: {PASS_BYTES.hex(' ')}")
print(f"FAIL pattern: {FAIL_BYTES.hex(' ') if FAIL_BYTES else 'NOT FOUND'}")

# Now parse all summary lines
lines = summary_data.split(b'\n')
all_pass = []
all_fail = []
total = 0

for line in lines:
    line = line.strip()
    if not line or line.startswith(b'GLOBAL') or line.startswith(b'===') or line.startswith(b'Ticker') or line.startswith(b'---'):
        continue
    # Check if it's a data line (starts with a ticker)
    parts = line.split()
    if len(parts) < 5:
        continue
    ticker = parts[0].decode('utf-8', errors='replace')
    
    # Count pass/fail markers
    pass_count = line.count(PASS_BYTES)
    fail_count = line.count(FAIL_BYTES) if FAIL_BYTES else 0
    
    if pass_count + fail_count == 4:  # Valid data line with 4 markers
        total += 1
        if pass_count == 4:
            # Extract edge, yr+, cost
            edge = parts[1].decode()
            yr_plus = parts[2].decode()
            cost_atr = parts[3].decode()
            profile = parts[4].decode()
            all_pass.append((ticker, edge, yr_plus, cost_atr, profile))
        else:
            all_fail.append(ticker)

print(f"\n{'='*60}")
print(f"TOTAL stocks analyzed: {total}")
print(f"ALL 3 TESTS PASS: {len(all_pass)}")
print(f"AT LEAST 1 FAIL: {len(all_fail)}")
print(f"{'='*60}")

# Sort by edge/day descending
all_pass.sort(key=lambda x: float(x[1]), reverse=True)

# Tier classification by edge/day
tier1_high = [(t,e,y,c,p) for t,e,y,c,p in all_pass if float(e) >= 0.0300]
tier1_med  = [(t,e,y,c,p) for t,e,y,c,p in all_pass if 0.0200 <= float(e) < 0.0300]
tier1_low  = [(t,e,y,c,p) for t,e,y,c,p in all_pass if float(e) < 0.0200]

print(f"\n{'='*65}")
print(f"  TIER 1-HIGH (Edge/d >= 3.0%): {len(tier1_high)} stocks")
print(f"  TIER 1-MED  (2.0% <= Edge/d < 3.0%): {len(tier1_med)} stocks")
print(f"  TIER 1-LOW  (Edge/d < 2.0%): {len(tier1_low)} stocks")
print(f"{'='*65}")

print(f"\n--- TIER 1-HIGH: Edge/day >= 3.0% ({len(tier1_high)} stocks) ---")
print(f"{'#':>3} {'Ticker':<8} {'Edge/d':>8} {'YR+':>6} {'Cost%':>7}")
print("-" * 38)
for i, (t,e,y,c,p) in enumerate(tier1_high, 1):
    print(f"{i:3} {t:<8} {e:>8} {y:>6} {c:>7}")

print(f"\n--- TIER 1-MED: 2.0% <= Edge/day < 3.0% ({len(tier1_med)} stocks) ---")
print(f"{'#':>3} {'Ticker':<8} {'Edge/d':>8} {'YR+':>6} {'Cost%':>7}")
print("-" * 38)
for i, (t,e,y,c,p) in enumerate(tier1_med, 1):
    print(f"{i:3} {t:<8} {e:>8} {y:>6} {c:>7}")

print(f"\n--- TIER 1-LOW: Edge/day < 2.0% ({len(tier1_low)} stocks) ---")
print(f"{'#':>3} {'Ticker':<8} {'Edge/d':>8} {'YR+':>6} {'Cost%':>7}")
print("-" * 38)
for i, (t,e,y,c,p) in enumerate(tier1_low, 1):
    print(f"{i:3} {t:<8} {e:>8} {y:>6} {c:>7}")

print(f"\n{'='*65}")
print(f"GRAND TOTAL PASS: {len(all_pass)} / {total}")
print(f"FAIL: {len(all_fail)} / {total}")

# Also print fail list compactly
print(f"\n--- FAILED STOCKS ({len(all_fail)}) ---")
for i in range(0, len(all_fail), 10):
    print("  " + ", ".join(all_fail[i:i+10]))
