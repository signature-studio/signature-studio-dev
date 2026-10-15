#!/usr/bin/env python3
"""x87_traps.py: .pdata 関数のうち x87 命令 (f* mnemonic) を含むものの開始 VA を 1 行 1 個 (0x 付き hex) で書く。
usage: x87_traps.py PE OUT.txt
閉包は計算しない。出力は x64c --trap に渡す trap stub の集合 (閉包に入れば gate が落ちる。x87_reach.py と同じ判定)。"""
import sys, pefile, capstone

pe = pefile.PE(sys.argv[1])
base = pe.OPTIONAL_HEADER.ImageBase
img = pe.get_memory_mapped_image()
text = next(s for s in pe.sections if s.Name.startswith(b'.text'))
tlo, thi = text.VirtualAddress, text.VirtualAddress + text.Misc_VirtualSize
d = pe.OPTIONAL_HEADER.DATA_DIRECTORY[3]
funcs = set()
for i in range(d.Size // 12):
    b, e = (int.from_bytes(img[d.VirtualAddress + 12 * i + k * 4:d.VirtualAddress + 12 * i + k * 4 + 4], 'little') for k in (0, 1))
    if tlo <= b < thi:
        funcs.add((b, e))
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
x87 = sorted(b for b, e in funcs if any(i.mnemonic.startswith('f') for i in md.disasm(bytes(img[b:e]), base + b)))
with open(sys.argv[2], 'w') as fh:
    fh.writelines('0x%x\n' % (base + b) for b in x87)
print('[iltools x87_traps] pdata funcs %d / x87 funcs %d -> %s' % (len(funcs), len(x87), sys.argv[2]))
