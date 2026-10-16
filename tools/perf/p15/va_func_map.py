# PERF-P28 (#5403): lift 済み VA (0x18xxxxxxx) → wasm 関数番号の対応表を作る。
# 一次根拠は ott_run の dispatcher (wasm func 10) の `i64.const <guest 番地>; i64.eq; br_if` の葉。
# 葉の分岐先 (block の終端直後の `call N`) を wasm 関数番号とし、ott_lifted.c の `case 0x...: f_<VA>()` と照合する。
# 使い方:
#   wasm2wat tools/ott/work/lift/ottl.wasm -o <in.wat>
#   python3 tools/perf/p15/va_func_map.py <in.wat> tools/ott/work/lift/ott_lifted.c <out.json>
# guest 番地は wasm の線形メモリ上の番地 (0x30000000 基底)。VA = 0x180000000 + (guest − 0x30000000)。
import json
import re
import sys

WAT, LIFTED, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
W = open(WAT).read().split('\n')
C = open(LIFTED).read().split('\n')
BASE_GUEST, BASE_VA = 0x30000000, 0x180000000


def clean(line):
    return line.strip().split(';;')[0].strip()


cases = {}
for l in C:
    m = re.search(r'case 0x([0-9a-fA-F]+)ULL: (f_[0-9a-fA-F]+)\(\);', l)
    if m:
        cases[int(m.group(1), 16)] = m.group(2)

s = next(i for i, l in enumerate(W) if l.startswith('  (func (;10;)'))
e = s + 1
while not W[e].startswith('  (func ('):
    e += 1

rows = {}
for i in range(s, e):
    m = re.match(r'i64\.const (\d+)$', clean(W[i]))
    if not m or i + 1 >= e or clean(W[i + 1]) != 'i64.eq':
        continue
    mb = re.match(r'br_if (\d+)', clean(W[i + 2]))
    if not mb:
        continue
    guest = int(m.group(1))
    k = int(mb.group(1))
    stack = []
    for j in range(s + 1, i + 3):
        t = clean(W[j])
        if t.startswith(('block', 'loop', 'if')):
            stack.append(j)
        elif t == 'end' and stack:
            stack.pop()
    tgt = stack[-1 - k]
    d, j = 0, tgt
    while True:
        t = clean(W[j])
        if t.startswith(('block', 'loop', 'if')):
            d += 1
        elif t == 'end':
            d -= 1
        if d == 0:
            break
        j += 1
    n = j + 1
    while n < e and not re.match(r'call \d+', clean(W[n])):
        if clean(W[n]).startswith(('block', 'loop', 'if', 'end')):
            break
        n += 1
    mc = re.match(r'call (\d+)', clean(W[n])) if n < e else None
    rows[guest] = int(mc.group(1)) if mc else None

out = []
for guest in sorted(rows):
    va = BASE_VA + (guest - BASE_GUEST) if guest >= BASE_GUEST else None
    out.append({
        'guest': hex(guest),
        'va': hex(va) if va else None,
        'wasm_func': rows[guest],
        'c': cases.get(guest),
    })
json.dump(out, open(OUT, 'w'), indent=1)
both = sum(1 for r in out if r['c'] and r['wasm_func'] is not None)
print('dispatch leaves', len(out), 'with C name', both, 'C cases', len(cases))
