#!/usr/bin/env python3
"""SR-3c 追補: 窓外 6 関数 (§11.3) への参照経路の静的走査。前提: sr3_run.sh 実行済み (work/index.npz, work/Serum2_win64.vst3)。
出力: (1) 6 関数 VA の int32 RVA 出現 (.rdata/.pdata 別), (2) 数学名表を引く関数の呼出元 (1 段), (3) その呼出元の呼出元 (1 段)。"""
import bisect, struct, numpy as np, pefile
IMG = 0x180000000
SIX = [0x1809e3240, 0x1809eb7b0, 0x1809ef030, 0x1809ef7b0, 0x180a0a3e0, 0x180a0f3f0]
DISPATCH = 0x180a0ea50  # 数学名表 (0x180fae640, 24 件) を線形探索する関数
z = np.load('work/index.npz'); funcs = z['funcs']; refs = z['refs']
fs = funcs[:, 0].tolist()
def fi(r):
    i = bisect.bisect_right(fs, r) - 1
    return i if i >= 0 and funcs[i][0] <= r < funcs[i][1] else -1
def owner(va):
    f = fi(va - IMG)
    return int(funcs[f][0]) + IMG if f >= 0 else None
def callers(va):
    r = va - IMG
    return sorted({int(x[0]) + IMG for x in refs if x[1] == r and x[2] in (1, 2)})
pe = pefile.PE('work/Serum2_win64.vst3', fast_load=True)
dm = bytes(pe.get_memory_mapped_image())
for s in pe.sections:
    nm = s.Name.rstrip(b'\0').decode(errors='replace')
    lo = s.VirtualAddress; hi = lo + s.Misc_VirtualSize
    for v in SIX:
        for k in range(lo, hi - 4, 4):
            if struct.unpack_from('<i', dm, k)[0] == v - IMG:
                print('int32 RVA hit', hex(v), nm, hex(k + IMG))
NT = 0x180fae640 - IMG  # 数学名表 (RVA)
print('dispatch', hex(DISPATCH), 'refs into name table (rip lea):', sorted({hex(int(r[0]) + IMG) for r in refs if r[2] == 0 and NT <= r[1] < NT + 16 * 24}))
d_callers = callers(DISPATCH)
print('dispatch callers (call/jmp):', [hex(c) for c in d_callers])
for c in d_callers:
    o = owner(c)
    cs = callers(o) if o else []
    print('  caller', hex(c), 'owner', hex(o) if o else '-', 'owner callers:', [hex(x) for x in cs])
    for x in cs:
        f = fi(x - IMG)
        print('    2nd caller', hex(x), 'owner', hex(int(funcs[f][0]) + IMG) if f >= 0 else '-', 'size', int(funcs[f][1] - funcs[f][0]) if f >= 0 else '-')
