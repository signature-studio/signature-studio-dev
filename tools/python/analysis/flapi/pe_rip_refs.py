#!/usr/bin/env python3
"""RIP 相対で指す VA を持つ命令を全セクションから探す (PY-222 / #3624 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_rip_refs.py <VA(16進)>[,<VA(16進)>...]

- 命令を 1 バイトずつ進めて復号するので、線形走査で同期が外れた箇所も拾う。
- 出力: 命令の VA・mnemonic・オペランド。値は PE 上の初期値ではなく、参照の位置だけを示す。
"""
import os
import re
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
raw = open(PE, "rb").read()
pe = pefile.PE(data=raw, fast_load=True)
BASE = pe.OPTIONAL_HEADER.ImageBase
MD = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
targets = {int(t, 16) for t in sys.argv[1].split(",")}
RIP = re.compile(r"rip \+ (0x[0-9a-f]+)")

for s in pe.sections:
    if not s.Characteristics & 0x20:
        continue
    base = BASE + s.VirtualAddress
    data = raw[s.PointerToRawData:s.PointerToRawData + s.SizeOfRawData]
    i = 0
    while i < len(data):
        insn = next(MD.disasm(data[i:i + 16], base + i), None)
        if insn is None:
            i += 1
            continue
        m = RIP.search(insn.op_str)
        if m and insn.address + insn.size + int(m.group(1), 16) in targets:
            print(f"{insn.address:#x} {insn.mnemonic} {insn.op_str}")
        i += insn.size
