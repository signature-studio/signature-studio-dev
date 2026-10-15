#!/usr/bin/env python3
# #2891: unit 492 の 4473f0 配列 (arg2+0x100..+0x170) の 0 初期化経路を読取りのみで確認する。
# 対象: native ad5700 → 415610 (RTTI で managed field を 0 初期化) → 4159e0 (C shim) → 40d210 (memset, n > 32 の本体)。
# 使い方: FL_WIN64_DIR=<fl-win64 を展開した先> python3 tools/m11/trap_triage/native_zeroinit_2891.py [work/boot_final.ll]
import os
import struct
import sys

from capstone import Cs, CS_ARCH_X86, CS_MODE_64

IB = 0x400000
PE = os.path.join(os.environ['FL_WIN64_DIR'], 'extracted', 'block00031_PE.bin')
d = open(PE, 'rb').read()
pe = struct.unpack_from('<I', d, 0x3c)[0]
nsec = struct.unpack_from('<H', d, pe + 6)[0]
opt = struct.unpack_from('<H', d, pe + 20)[0]
secs = []
for i in range(nsec):
    vsz, rva, rsz, raw = struct.unpack_from('<IIII', d, pe + 24 + opt + 40 * i + 8)
    secs.append((rva, max(vsz, rsz), raw))


def va2o(va):
    rva = va - IB
    for s, sz, raw in secs:
        if s <= rva < s + sz:
            return raw + (rva - s)
    raise SystemExit('VA out of section: %x' % va)


exc_rva, exc_sz = struct.unpack_from('<II', d, pe + 24 + opt - 128 + 24)  # DataDirectory[3] = .pdata
pdata = va2o(exc_rva + IB)
md = Cs(CS_ARCH_X86, CS_MODE_64)


def dis(va, n):
    o = va2o(va)
    return list(md.disasm(d[o:o + 16 * n], va))[:n]


def show(title, va, n):
    print('# ' + title)
    for ins in dis(va, n):
        print('  %x: %s %s' % (ins.address, ins.mnemonic, ins.op_str))


print('# .pdata (VA 範囲) が覆う関数')
for va in (0x40d210, 0x40d2b9, 0x40d2d1, 0x40d30b):
    hits = []
    for i in range(exc_sz // 12):
        b, e, _ = struct.unpack_from('<III', d, pdata + 12 * i)
        if b + IB <= va < e + IB:
            hits.append('%x-%x' % (b + IB, e + IB))
    print('  %x -> %s' % (va, hits))

show('native ad5700 (unit 492 の入口): 先頭で 415610(&obj, ti)', 0xad5700, 6)
show('native 40d210 (memset(p=rcx, n=rdx, val=r8b)): n <= 32 は inline、n > 32 は 40d2d1 へ', 0x40d210, 12)
show('native 40d2d1 (n > 32 の本体: SSE movups/movaps)', 0x40d2d1, 9)
show('native 40d30b (n >= 閾値 の本体: rep stosb)', 0x40d30b, 6)
thr_va = 0x40d21b + 0xf97e2d
print('# 閾値 qword @ %x (cmp rdx,[rip+..] の参照先, 本体は .text の定数)' % thr_va)
print('  value = %d' % struct.unpack_from('<Q', d, va2o(thr_va))[0])

ir = sys.argv[1] if len(sys.argv) > 1 else 'work/boot_final.ll'
txt = open(ir).read()
s = txt.index('define i64 @function_40d210(')
body = txt[s:txt.index('\n}\n', s)]
print('# lift IR function_40d210 (%s)' % ir)
print('  block dec_label_pc_40d2d1 in whole IR: %s' % ('dec_label_pc_40d2d1:' in txt))
lines = body.splitlines()
for k, l in enumerate(lines):
    if 'icmp sgt i64 %arg2, 32' in l:
        print('  ' + l.strip())
        print('  ' + lines[k + 1].strip())
        break
