#!/usr/bin/env python3
"""iat_check.py: ia32 の絶対 disp32 による IAT 間接 call/jmp が、lift 出力で正しい import 名に解決されているかを検査する (#1098 受入 4)。

  python3 iat_check.py <ott_lifted.c> <block22434_PE.bin>        gate (不一致があれば exit 1)
  python3 iat_check.py <ott_lifted.c> <block22434_PE.bin> neg    ネガコン (IAT の 1 slot 名を故意に壊し、FAIL を期待)

判定は x64c (pefile) とは独立に、import directory を生バイトから読んで slot→名の表を作る。
命令の抽出は capstone (32bit 線形掃引ではなく、lift 出力の `/* va: ... */` コメント行の mnemonic / operand 文字列) を用いる。
"""
import re, struct, sys
from capstone import Cs, CS_ARCH_X86, CS_MODE_32
from capstone.x86 import X86_OP_MEM

C = sys.argv[1]; PEF = sys.argv[2]; NEG = len(sys.argv) > 3
img = open(PEF, 'rb').read()
e_lfanew = struct.unpack_from('<I', img, 0x3C)[0]
nsec = struct.unpack_from('<H', img, e_lfanew + 6)[0]
opt = e_lfanew + 24
IMG = struct.unpack_from('<I', img, opt + 28)[0]
dd_import_rva = struct.unpack_from('<I', img, opt + 96 + 8)[0]
sec_hdr = opt + struct.unpack_from('<H', img, e_lfanew + 20)[0]
secs = []
for i in range(nsec):
    o = sec_hdr + 40 * i
    vsz, vaddr, rawsz, rawptr = struct.unpack_from('<IIII', img, o + 8)
    secs.append((vaddr, max(vsz, rawsz), rawptr))


def rva2off(rva):
    for vaddr, sz, rawptr in secs:
        if vaddr <= rva < vaddr + sz:
            return rawptr + (rva - vaddr)
    raise SystemExit('[iat] FAIL: rva 0x%x not in any section' % rva)


def cstr(off):
    return img[off:img.index(b'\0', off)].decode('ascii', 'replace')


slot_name = {}          # slot VA -> name (raw parse)
off = rva2off(dd_import_rva)
while True:
    oft, _, _, name_rva, ft = struct.unpack_from('<IIIII', img, off)
    if oft == 0 and name_rva == 0 and ft == 0:
        break
    lt = oft if oft else ft
    k = 0
    while True:
        ent = struct.unpack_from('<I', img, rva2off(lt) + 4 * k)[0]
        if ent == 0:
            break
        if ent & 0x80000000:
            nm = 'ord%d' % (ent & 0xFFFF)
        else:
            nm = cstr(rva2off(ent) + 2)
        slot_name[IMG + ft + 4 * k] = nm
        k += 1
    off += 20
if NEG and slot_name:   # ネガコン: 先頭 slot の名前を壊す
    k0 = min(slot_name); slot_name[k0] = slot_name[k0] + '_X'
print('[iat] import slots (raw parse) %d' % len(slot_name))

# lift 出力の各命令 (`/* VA: call|jmp ... */` コメント) について、PE の生バイトを VA で単独デコードし、
# 絶対 disp32 (base=0, index=0) の間接 call/jmp で IAT slot を指すものを期待値にする。
# 線形掃引は data-in-code で命令境界がずれるため使わない (命令の起点は lift の再帰降下に従う)。
md = Cs(CS_ARCH_X86, CS_MODE_32); md.detail = True
text = secs[0]
def bytes_of_va(va, n=16):
    rva = va - IMG
    for vaddr, sz, rawptr in secs:
        if vaddr <= rva < vaddr + sz:
            return img[rawptr + (rva - vaddr):rawptr + (rva - vaddr) + n]
    return b''
src = open(C).read().split('\n')
cands = []
for i, ln in enumerate(src):
    m = re.match(r'\s*/\* ([0-9a-f]+): (call|jmp) dword ptr \[(0x[0-9a-f]+)\] \*/', ln)
    if m:
        cands.append((i, int(m.group(1), 16), m.group(2), int(m.group(3), 16)))
expect = {}
abs_other = 0
for i, va, mn, disp in cands:
    ins = next(md.disasm(bytes_of_va(va), va, 1), None)
    if ins is None or ins.mnemonic != mn or ins.operands[0].type != 3 or ins.operands[0].mem.base != 0 or ins.operands[0].mem.index != 0 \
       or (ins.operands[0].mem.disp & 0xffffffff) != disp:
        raise SystemExit('[iat] FAIL: va 0x%x の生バイト decode が lift コメント (%s dword ptr [0x%x]) と一致しない' % (va, mn, disp))
    if disp in slot_name:
        expect[va] = (i, slot_name[disp])
    else:
        abs_other += 1
print('[iat] lift の絶対 disp32 call/jmp %d (うち IAT slot %d / それ以外 %d、生バイト decode と一致)' % (len(cands), len(expect), abs_other))
got = {}
for va, (i, nm_want) in expect.items():
    nxt = src[i + 1] if i + 1 < len(src) else ''
    mm = re.search(r'imp_([A-Za-z0-9_]+)\(\)', nxt)
    got[va] = mm.group(1) if mm else ('<' + nxt.strip()[:40] + '>')
expect = {va: nm for va, (i, nm) in expect.items()}
lifted = sum(1 for va in expect if va in got)
bad = [(hex(va), expect[va], got[va]) for va in expect if va in got and got[va] != expect[va]]
print('[iat] IAT 参照のうち lift で imp_ 呼び出しになったもの %d / %d、名前の不一致 %d' % (lifted, len(expect), len(bad)))
for b in bad[:10]:
    print('[iat] MISMATCH %s want %s got %s' % b)
if bad or lifted != len(expect):
    print('[iat] FAIL')
    sys.exit(1)
print('[iat] OK: 絶対 disp32 IAT 参照の解決名 == PE import directory の実データ (%d 件)' % lifted)
