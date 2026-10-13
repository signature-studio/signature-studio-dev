"""L1 census: 0x1800c2ef4–f05 の直接 vtable 通知 `call [rax+0x30]` (edx=0x800010) が raw IR に残るかを数える。

使い方: python3 l1_census.py <PE> <raw.ll>
"""
import re
import sys

import capstone
import pefile

LO, HI = 0x1800C2B50, 0x1800C2F99
SITE = 0x1800C2EF4
PE_PATH, LL_PATH = sys.argv[1], sys.argv[2]

pe = pefile.PE(PE_PATH, fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
img = pe.get_memory_mapped_image()
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
ins = list(md.disasm(img[LO - base:HI - base], LO))

in_site = lambda a: SITE <= a <= SITE + 0x11
sites = [i for i in ins if i.mnemonic == 'call' and '+ 0x30]' in i.op_str and in_site(i.address)]
edx_const = [i for i in ins if i.mnemonic == 'mov' and i.op_str == 'edx, 0x800010' and in_site(i.address)]
into = [i for i in ins if i.mnemonic.startswith('j') and i.op_str == '0x%x' % SITE]

ll = open(LL_PATH).read().splitlines()
meta = {}
for l in ll:
    m = re.match(r'(!\d+) = !\{i64 (\d+)\}', l)
    if m:
        meta[m.group(1)] = int(m.group(2))
covered = [a for a in set(meta.values()) if in_site(a)]
has_block = any(l.startswith('dec_label_pc_%x:' % SITE) for l in ll)

print('machine: direct call [reg+0x30] sites   =', len(sites))
print('machine: edx=0x800010 loads             =', len(edx_const))
print('machine: edges into site block          =', len(into))
print('IR: insn.addr entries covering site     =', len(covered))
print('IR: block dec_label_pc_%x present      =' % SITE, has_block)
