"""cmp.py: native / wasm の stage dump を region ごとに比較 (image ptr は 0x180xxxxxx↔0x30xxxxxx 正規化)。
   usage: cmp.py nat.json wasm.json [stage...]"""
import sys, json, zlib, base64, struct
a = json.load(open(sys.argv[1])); b = json.load(open(sys.argv[2]))
stg = sys.argv[3:] or list(a['stages'].keys())
unz = lambda s: zlib.decompress(base64.b64decode(s))
def nq(q):
    if 0x180000000 <= q < 0x180400000: return q - 0x150000000
    return q
tot = 0
for st in stg:
    print('== stage', st)
    nd = 0
    for ra, rb in zip(a['stages'][st], b['stages'][st]):
        A = unz(ra['z']); B = unz(rb['z']); assert ra['p'] == rb['p'] and ra['s'] == rb['s'], (ra['k'], rb['k'])
        if A == B: continue
        diffs = []
        for o in range(0, ra['s'] & ~7, 8):
            qa = struct.unpack_from('<Q', A, o)[0]; qb = struct.unpack_from('<Q', B, o)[0]
            if qa != qb and nq(qa) != qb and not (ra['k'] == 'obj' and o == 0):
                # wasm 側 32bit pointer が上位 0 のまま下位一致するケースを許容
                diffs.append(o)
        if diffs:
            nd += len(diffs)
            print(f"  region {ra['k']} p={ra['p']:#x} size={ra['s']}: {len(diffs)} qword diffs; first:",
                  ', '.join(f"+{o:#x}(n={struct.unpack_from('<Q',A,o)[0]:#x}/w={struct.unpack_from('<Q',B,o)[0]:#x})" for o in diffs[:6]))
    print('  total qword diffs', nd); tot += nd
print('TOTAL', tot)
