#!/usr/bin/env python3
"""fa8_scan.py <pe> — .pdata 関数境界で全関数を逆アセンブルし、FA-8 の経路上の呼出元/書込元を列挙する (静的)。
  出力: callers(<target>) = [関数 start]、store(+0x318) = [関数 start: 命令]"""
import sys, struct, pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
pe = pefile.PE(sys.argv[1]); base = pe.OPTIONAL_HEADER.ImageBase
TG = {0x1803debc0: 'setter_debc0', 0x180ca1480: 'ca1480', 0x180c9d700: 'c9d700', 0x180ca7db0: 'ca7db0', 0x180da6c00: 'da6c00', 0x180da6bf0: 'da6bf0'}
dd = pe.OPTIONAL_HEADER.DATA_DIRECTORY[3]; raw = pe.get_data(dd.VirtualAddress, dd.Size)
fn = sorted(struct.unpack_from('<III', raw, i)[:2] for i in range(0, len(raw) - 11, 12))
md = Cs(CS_ARCH_X86, CS_MODE_64)
callers = {v: [] for v in TG.values()}; st = []
for b, e in fn:
    if e <= b: continue
    code = pe.get_data(b, e - b)
    for i in md.disasm(code, base + b):
        if i.mnemonic in ('call', 'jmp') and i.op_str.startswith('0x'):
            t = int(i.op_str, 16)
            if t in TG: callers[TG[t]].append((base + b, i.address))
        elif i.mnemonic == 'mov' and i.op_str.startswith('qword ptr [') and '+ 0x318]' in i.op_str.split(',')[0]:
            st.append((base + b, i.address, i.op_str))
print('functions=%d' % len(fn))
for k, v in callers.items(): print('callers(%s) n=%d distinct_funcs=%d: %s' % (k, len(v), len({x[0] for x in v}), ' '.join('%x@%x' % (a, c) for a, c in v)[:600]))
print('store[+0x318] n=%d' % len(st))
for a, c, o in st[:30]: print('  func %x insn %x: %s' % (a, c, o))
