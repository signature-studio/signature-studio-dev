#!/usr/bin/env python3
"""LF4 の比較定数が機械語側 (PE の定数領域) と一致することを確認する (SR-11)。

usage: verify_lf4_const.py <PE> <patched_base_lf.ll>
  - 機械語: 0x18004fe4c の `ucomisd xmm0, qword ptr [rip + d]` の定数 (PE 実バイト)
  - IR    : LF4 が挿入した `fcmp ugt double %lf4d, %lf4c` の `bitcast i64 N to double`
  両者の double 値が一致すれば OK。不一致なら exit 1。
"""
import re, sys
import pefile, capstone

LF4_VA = 0x18004fe4c
FN_D = 0x18004fad0

pe_path, ir_path = sys.argv[1], sys.argv[2]
pe = pefile.PE(pe_path, fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
img = pe.get_memory_mapped_image()
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

code = img[LF4_VA - base - 0x10:LF4_VA - base + 0x10]
ins = next(i for i in md.disasm(code, LF4_VA - 0x10) if i.address == LF4_VA)
m = re.search(r'\[rip \+ 0x([0-9a-f]+)\]', ins.op_str)
if not m or ins.mnemonic != 'ucomisd':
    raise SystemExit(f'LF4 site is not ucomisd [rip+disp]: {ins.mnemonic} {ins.op_str}')
caddr = ins.address + ins.size + int(m.group(1), 16)
pe_bits = int.from_bytes(img[caddr - base:caddr - base + 8], 'little')

lines = open(ir_path).read().splitlines()
s = next(i for i, l in enumerate(lines) if l.startswith('define') and 'function_18004fad0(' in l)
e = next(i for i in range(s, len(lines)) if lines[i].startswith('}'))
ir_bits = [int(m.group(1)) for m in
           (re.match(r'\s*%lf4c = bitcast i64 (\d+) to double', lines[i]) for i in range(s, e)) if m]
if len(ir_bits) != 1:
    raise SystemExit(f'IR の LF4 定数 candidate = {len(ir_bits)} (expect 1)')

import struct
pe_d = struct.unpack('<d', pe_bits.to_bytes(8, 'little'))[0]
ir_d = struct.unpack('<d', ir_bits[0].to_bytes(8, 'little'))[0]
print(f'LF4 const: PE@{caddr:#x} = {pe_d!r} (bits {pe_bits}), IR = {ir_d!r} (bits {ir_bits[0]})')
if pe_bits != ir_bits[0]:
    raise SystemExit('LF4 const mismatch: PE と IR が一致しない')
print('LF4 const OK')
