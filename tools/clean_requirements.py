from pathlib import Path
import codecs
import re
import datetime
import sys

root = Path(__file__).resolve().parents[1]
req_path = root / "requirements.txt"
if not req_path.exists():
    print(f"No requirements.txt at {req_path}")
    sys.exit(1)

data = req_path.read_bytes()

# Detect encoding
enc = None
if data.startswith(codecs.BOM_UTF16_LE):
    enc = 'utf-16-le'
elif data.startswith(codecs.BOM_UTF16_BE):
    enc = 'utf-16-be'
elif data.startswith(codecs.BOM_UTF8):
    enc = 'utf-8-sig'
else:
    # Heuristic: if many zero bytes at odd indices, assume UTF-16-LE
    sample = data[:200]
    zeros = sum(1 for i in range(1, len(sample), 2) if sample[i] == 0)
    if zeros > (len(sample) // 4):
        enc = 'utf-16-le'
    else:
        enc = 'utf-8'

try:
    text = data.decode(enc)
except Exception:
    text = data.decode('latin-1')

lines = [ln.strip() for ln in text.splitlines()]

# Normalize and filter
seen = {}
skip_names = {'pip', 'setuptools', 'wheel', 'distribute', 'pkg-resources'}

name_re = re.compile(r'^\s*([A-Za-z0-9_.+-]+)')

def get_name(s):
    m = name_re.match(s)
    if not m:
        return s.strip().lower()
    return m.group(1).lower()

def score(s):
    if '==' in s:
        return 3
    if any(op in s for op in ('>=', '<=', '!=', '~=', '>')):
        return 2
    if s.startswith('git+') or '://' in s:
        return 1
    return 0

# Collect best entry per package name
for ln in lines:
    if not ln or ln.startswith('#'):
        continue
    # Remove leading BOM if present on first line
    if ln.startswith('\ufeff'):
        ln = ln.lstrip('\ufeff')
    name = get_name(ln)
    if name in skip_names:
        continue
    if name in seen:
        if score(ln) > score(seen[name]):
            seen[name] = ln
    else:
        seen[name] = ln

# Sort by package name
out_lines = [seen[n] for n in sorted(seen.keys())]

# Backup original bytes
bak = root / 'requirements.txt.bak'
if bak.exists():
    ts = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    bak = root / f'requirements.txt.bak-{ts}'
bak.write_bytes(data)

# Write cleaned requirements as UTF-8
req_path.write_text('\n'.join(out_lines) + ('\n' if out_lines else ''), encoding='utf-8')

print(f"Detected encoding: {enc}")
print(f"Original entries: {len([ln for ln in lines if ln and not ln.startswith('#')])}")
print(f"Cleaned entries: {len(out_lines)}")
print(f"Backup written to: {bak}")
print(f"Wrote cleaned requirements to: {req_path}")
