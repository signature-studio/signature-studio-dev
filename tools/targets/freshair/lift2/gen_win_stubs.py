#!/usr/bin/env python3
"""gen_win_stubs.py <core> — PE import 表の全 API に対する **weak** 既定実装 (0 戻り) を C として出力。
* host_wasm.c は FA_WIN_STUBS 定義時にこのヘッダを include する。
* shim/fa_win_shim.h の特定実装 (HeapAlloc 等) は strong 定義でこちらを上書きする。
* mlift が `declare @win_<dll>_<name>` を出す未対応 API を link エラーにせず fail-soft にする
  (FA-2c: 制御層 closure は framework 側 import を多数呼ぶため)。"""
import sys, struct
core = sys.argv[1]
d = open(core, 'rb').read()
e = struct.unpack_from('<I', d, 0x3c)[0]; coff = e + 4; opt = coff + 20
nsec = struct.unpack_from('<H', d, coff + 2)[0]
secs = []
for k in range(nsec):
    o = opt + 240 + 40 * k
    vsz, va, rsz, ro = struct.unpack_from('<IIII', d, o + 8)
    secs.append((va, vsz, ro, rsz))
def R(rva):
    for va, vsz, ro, rsz in secs:
        if va <= rva < va + max(vsz, rsz): return ro + (rva - va)
imp = R(0x125a258)
print('/* 自動生成 (gen_win_stubs.py): PE import 表の全 API に対する weak 既定 (0 戻り)。')
print(' * host_wasm.c とは別 TU (strong 定義との衝突を避けるため)。 */')
print('#include <stdint.h>')
print('#include <emscripten.h>')
print('typedef uint64_t u64;')
seen = set()
k = 0
while True:
    oft, ts, fc, nm, ft = struct.unpack_from('<IIIII', d, imp + 20 * k)
    if not nm: break
    s = R(nm); dll = d[s:d.index(b'\0', s)].decode('latin1').lower().replace('.dll', '')
    t = oft if oft else ft
    for i in range(100000):
        v = struct.unpack_from('<Q', d, R(t) + 8 * i)[0]
        if not v: break
        if v >> 63:
            fn = 'ord%d' % (v & 0xffff)
        else:
            s2 = R(v); fn = d[s2 + 2:d.index(b'\0', s2 + 2)].decode('latin1')
        import re
        sym = 'win_%s_%s' % (re.sub(r'\W', '_', dll), re.sub(r'\W', '_', fn))
        if sym in seen: continue
        seen.add(sym)
        print('__attribute__((weak)) EMSCRIPTEN_KEEPALIVE u64 %s(u64 a, u64 b, u64 c, u64 d) { return 0; }' % sym)
    k += 1

