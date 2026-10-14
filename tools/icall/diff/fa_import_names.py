#!/usr/bin/env python3
"""fa_import_names.py — SlateCore.core_64 の PE import 表を読み、ott_native.c (IMPL) に無い未実装 import を index 順に出す。
用法: python3 tools/icall/diff/fa_import_names.py
出力: 実装数・未実装数と、idx 0 / 64 の (DLL, 名前, IAT slot VA)。idx は ott_load の登録順 (g_nimp) と同じ。"""
import struct, re, os
HERE = os.path.dirname(os.path.abspath(__file__))
T = os.path.abspath(os.path.join(HERE, '..', '..'))
DLL = os.path.join(T, 'targets', 'freshair', 'work', 'win', 'Fresh Air', 'C__ProgramData_Slate Digital', 'Fresh Air', 'SlateCore.core_64')
src = open(os.path.join(T, 'ott', 'native', 'ott_native.c')).read()
IMPL = set(re.findall(r'\{"([A-Za-z0-9_]+)",\s*k_', src))
d = open(DLL, 'rb').read()
pe = struct.unpack_from('<I', d, 0x3c)[0]
nsec = struct.unpack_from('<H', d, pe + 6)[0]
osz = struct.unpack_from('<H', d, pe + 20)[0]
opt = pe + 24
secs = []
so = opt + osz
for i in range(nsec):
    vs, va, rs, rp = struct.unpack_from('<IIII', d, so + i * 40 + 8)
    secs.append((va, max(vs, rs), rp))
def rva2off(r):
    for va, sz, rp in secs:
        if va <= r < va + sz:
            return rp + (r - va)
    raise ValueError(hex(r))
def cstr(off):
    return d[off:d.index(b'\0', off)].decode('latin1')
idr = struct.unpack_from('<I', d, opt + 112 + 8)[0]
off = rva2off(idr)
missing = []
while True:
    oft, _, _, nm, ft = struct.unpack_from('<IIIII', d, off)
    if nm == 0:
        break
    dll = cstr(rva2off(nm))
    lookup = rva2off(oft if oft else ft)
    k = 0
    while True:
        v = struct.unpack_from('<Q', d, lookup + k * 8)[0]
        if v == 0:
            break
        name = ('%s!#%d' % (dll, v & 0xffff)) if (v >> 63) else cstr(rva2off(v & 0x7fffffff) + 2)
        if name not in IMPL:
            missing.append((dll, name, ft + k * 8))
        k += 1
    off += 20
print('implemented', len(IMPL), 'missing', len(missing))
for i in (0, 64):
    print('idx', i, missing[i] if i < len(missing) else None)
