#!/usr/bin/env python3
# SR-1c (#256): 関数 (RVA) を指す参照元を .text 全体と .rdata/.data の qword から列挙する。
# usage: python3 sr1c_callers.py <Serum2_win64.vst3> <target_rva_hex> [more_rva_hex ...]
# 出力: 直接 call/jmp (rel32) の呼出元と、絶対 qword (vtable 等) に現れる位置。
import struct
import sys

import pefile
from capstone import CS_ARCH_X86, CS_MODE_64, Cs

dll = sys.argv[1]
targets = [int(x, 16) for x in sys.argv[2:]]
pe = pefile.PE(dll, fast_load=True)
image_base = pe.OPTIONAL_HEADER.ImageBase
md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = False

tset = {image_base + t: t for t in targets}
calls = {t: [] for t in targets}
qwords = {t: [] for t in targets}

for sec in pe.sections:
    name = sec.Name.rstrip(b"\0").decode(errors="replace")
    data = sec.get_data()
    base = image_base + sec.VirtualAddress
    if sec.Characteristics & 0x20000000:  # EXECUTE
        for ins in md.disasm(data, base):
            if ins.mnemonic in ("call", "jmp") and ins.op_str.startswith("0x"):
                try:
                    dst = int(ins.op_str, 16)
                except ValueError:
                    continue
                if dst in tset:
                    calls[tset[dst]].append((ins.address, name))
    # 絶対アドレス (8 byte) の参照: 8 byte 境界でなくても拾えるよう 1 byte ずつ走査
    for off in range(0, len(data) - 7):
        v = struct.unpack_from("<Q", data, off)[0]
        if v in tset:
            qwords[tset[v]].append((base + off, name))

for t in targets:
    print(f"== target RVA 0x{t:x} ==")
    for va, sname in calls[t]:
        print(f"  call/jmp  0x{va:x} ({sname}) RVA 0x{va - image_base:x}")
    for va, sname in qwords[t]:
        print(f"  qword@    0x{va:x} ({sname}) RVA 0x{va - image_base:x}")
    print(f"  (call/jmp {len(calls[t])} 件, qword {len(qwords[t])} 件)")
