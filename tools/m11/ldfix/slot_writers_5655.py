#!/usr/bin/env python3
# slot_writers_5655.py: #5655 (LD-282) indirect_slots_5655.py が挙げた slot について、PE 全体の .text 内の
# RIP 相対参照 (store 形 / load 形) を列挙する。閉包外の書込み元を確定するための静的走査。
# 使い方: python3 slot_writers_5655.py <block00031_PE.bin> <slot_va>... (16 進可)
# 限界: 逆方向の参照 (lea で取ったアドレスを経由する書込み・レジスタ経由の間接書込み) は含まない。
import sys
import capstone
import pefile

pe = pefile.PE(sys.argv[1], fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
targets = {int(a, 16) for a in sys.argv[2:]}
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True
X86 = capstone.x86

text = next(s for s in pe.sections if s.Name.rstrip(b'\0') == b'.text')
t_lo = base + text.VirtualAddress
t_hi = t_lo + text.Misc_VirtualSize
data = pe.get_data(text.VirtualAddress, text.Misc_VirtualSize)

hits = {t: [] for t in targets}
off = 0
while off < len(data):
    end = off
    for i in md.disasm(data[off:], t_lo + off):
        end = i.address - t_lo + i.size
        for op in i.operands:
            if op.type == X86.X86_OP_MEM and op.mem.base == X86.X86_REG_RIP:
                t = i.address + i.size + op.mem.disp
                if t in hits:
                    is_store = i.operands[0].type == X86.X86_OP_MEM and i.operands[0].mem.base == X86.X86_REG_RIP \
                        and i.mnemonic in ('mov', 'add', 'sub', 'or', 'and', 'xor', 'inc', 'dec', 'xchg', 'lock xadd', 'xadd')
                    hits[t].append((hex(i.address), i.mnemonic, 'store' if is_store else 'load/ref'))
    if end >= len(data):
        break
    off = end + 1

for t in sorted(hits):
    st = [h for h in hits[t] if h[2] == 'store']
    print('slot=%s refs=%d stores=%d %s' % (hex(t), len(hits[t]), len(st), hits[t][:8]))
