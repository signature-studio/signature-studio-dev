#!/usr/bin/env python3
"""verify_engine.py — engine_claims.json の静的根拠を FLEngine_x64.dll から機械照合する (ST-T8 / #118)。stdlib のみ。
  1. 関数境界 = .pdata (RUNTIME_FUNCTION)
  2. 文字列参照 = .text の RIP 相対 lea/mov (REX? 8D|8B modrm(mod=00,rm=101)) の参照先が UTF-16LE / ASCII の NUL 終端リテラルと一致
  3. 呼出辺 = .text の E8 rel32 (関数内)。import は IAT 名で解決
  4. 機械語バイト列の一致 (呼出引数の形)
usage: verify_engine.py <FLEngine_x64.dll> [claims.json]    exit 0 = 全件一致 / 1 = 不一致あり (FAIL 行を数える)
"""
import bisect
import hashlib
import json
import os
import struct
import sys

dll = sys.argv[1]
claims = json.load(open(sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'engine_claims.json')))
d = open(dll, 'rb').read()
fails = []
oks = 0


def ok(cond, msg):
    global oks
    if cond:
        oks += 1
    else:
        fails.append(msg)
        print('FAIL', msg)


h = hashlib.sha256(d).hexdigest()
ok(len(d) == claims['dll']['size'] and h == claims['dll']['sha256'], f"DLL pin size={len(d)} sha256={h}")

pe = struct.unpack_from('<I', d, 0x3C)[0]
assert d[pe:pe + 4] == b'PE\0\0'
nsec = struct.unpack_from('<H', d, pe + 6)[0]
optsz = struct.unpack_from('<H', d, pe + 20)[0]
opt = pe + 24
assert struct.unpack_from('<H', d, opt)[0] == 0x20B
base = struct.unpack_from('<Q', d, opt + 24)[0]
dd = opt + 112
secs = []
for i in range(nsec):
    name, vsz, va, rsz, raw = struct.unpack_from('<8sIII I', d, opt + optsz + 40 * i)[:5]
    secs.append((name.rstrip(b'\0').decode(), va, max(vsz, rsz), raw, rsz))


def off(rva):
    for _n, va, sz, raw, rsz in secs:
        if va <= rva < va + sz:
            return raw + rva - va if rva - va < rsz else None
    return None


exc_rva, exc_sz = struct.unpack_from('<II', d, dd + 8 * 3)
funcs = sorted(struct.unpack_from('<II', d, off(exc_rva) + 12 * i) for i in range(exc_sz // 12))
starts = [b for b, _ in funcs]


def func_of(rva):
    i = bisect.bisect_right(starts, rva) - 1
    return funcs[i] if i >= 0 and funcs[i][0] <= rva < funcs[i][1] else None


text = next(s for s in secs if s[0] == '.text')
_, tva, _, traw, trsz = text
T = d[traw:traw + trsz]

# import 名 (IAT スロット RVA → "dll!name")
imp_rva, _ = struct.unpack_from('<II', d, dd + 8)
iat = {}
o = off(imp_rva)
while True:
    ilt, _ts, _fc, nm, ft = struct.unpack_from('<IIIII', d, o)
    if not nm:
        break
    dllname = d[off(nm):].split(b'\0')[0].decode()
    k = 0
    while True:
        e = struct.unpack_from('<Q', d, off(ilt or ft) + 8 * k)[0]
        if not e:
            break
        iat[ft + 8 * k] = f"{dllname}!{d[off(e & 0x7fffffff) + 2:].split(b'\0')[0].decode()}" if not e >> 63 else f'{dllname}!ord{e & 0xffff}'
        k += 1
    o += 20


def thunk_import(va):
    o = off(va - base)
    if o is None or d[o:o + 2] != b'\xff\x25':
        return None
    return iat.get(va - base + 6 + struct.unpack_from('<i', d, o + 2)[0])


def literals(rva):
    o = off(rva)
    if o is None:
        return set()
    out = set()
    w = bytearray()
    for k in range(0, 600, 2):
        c = d[o + k:o + k + 2]
        if len(c) < 2 or c == b'\0\0':
            break
        w += c
    try:
        out.add(bytes(w).decode('utf-16le'))
    except UnicodeDecodeError:
        pass
    a = d[o:o + 300]
    z = a.find(b'\0')
    if z > 0:
        out.add(a[:z].decode('latin1'))
    return out


def lits_in(b, e):
    got = set()
    for i in range(b - tva, e - tva - 6):
        j = i + 1 if 0x40 <= T[i] <= 0x4f else i
        if T[j] in (0x8D, 0x8B) and (T[j + 1] & 0xC7) == 0x05:
            disp = struct.unpack_from('<i', T, j + 2)[0]
            got |= literals(tva + j + 6 + disp)
    return got


def calls_in(b, e):
    out = set()
    for i in range(b - tva, e - tva - 4):
        if T[i] == 0xE8:
            out.add(tva + i + 5 + struct.unpack_from('<i', T, i + 1)[0])
    return out


A = lambda s: int(s, 16) - base  # noqa: E731

for va, what in claims['funcs'].items():
    f = func_of(A(va))
    ok(f is not None and f[0] == A(va), f"関数先頭 {va} ({what})")
for va, refs in claims['strings'].items():
    f = func_of(A(va))
    if f is None:
        ok(False, f"文字列照合の関数が無い {va}")
        continue
    got = lits_in(*f)
    for r in refs:
        ok(r in got, f"{va} が文字列 {r!r} を参照")
for caller, callee in claims['calls']:
    f = func_of(A(caller))
    ok(f is not None and A(callee) in calls_in(*f), f"{caller} → {callee} の直接 call")
for va, name in claims['imports'].items():
    ok(thunk_import(int(va, 16)) == name, f"import thunk {va} = {name} (実際 {thunk_import(int(va, 16))})")
for caller, thunk in claims['calls_import']:
    f = func_of(A(caller))
    ok(f is not None and A(thunk) in calls_in(*f), f"{caller} → import thunk {thunk} の call")
for bc in claims['bytes']:
    o = off(A(bc['site']))
    want = bytes.fromhex(bc['hex'])
    ok(o is not None and d[o:o + len(want)] == want, f"機械語 {bc['site']}: {bc['note']}")
    f = func_of(A(bc['site']))
    ok(f is not None and f[0] == A(bc['func']), f"機械語 {bc['site']} は関数 {bc['func']} 内")
    if bc['thunk']:
        rel = struct.unpack_from('<i', d, o + len(want))[0]
        ok(A(bc['site']) + len(want) + 4 + rel == A(bc['thunk']), f"機械語 {bc['site']} の call 先 = {bc['thunk']}")

print(f"verify_engine: ok {oks} / fail {len(fails)}")
sys.exit(1 if fails else 0)
