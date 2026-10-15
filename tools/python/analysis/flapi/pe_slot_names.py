#!/usr/bin/env python3
"""FLEngine PE の .text 全体で、関数ポインタ slot の登録呼出しの名前を列挙する (PY-103 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_slot_names.py <slot VA(16進)>[,<slot VA(16進)>...]

登録の形: `lea rdx, [rip+slot]` の直後 (WINDOW byte 以内) の `lea r8, [rip+name]` が指す UTF-16LE 文字列を
名前として出す。`lea rdx` の直後の `call` が登録関数 (例: 0x653dd0) である。`pe_xref.py` は register 経由の
store (slot を `rdx` で渡して書かせる形) を見ないため、登録の名前はこのツールで読む。
展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
"""
import os
import sys
import time

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
CHUNK = 1 << 16
WINDOW = 24


def rip_target(ins, op):
    return ins.address + ins.size + op.mem.disp


def utf16_at(raw, off):
    buf = bytearray()
    for i in range(0, 512, 2):
        ch = raw[off + i:off + i + 2]
        if ch == b"\0\0" or len(ch) < 2:
            break
        buf += ch
    return buf.decode("utf-16-le", errors="replace")


def main():
    targets = {int(x, 16) for x in sys.argv[1].split(",")}
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    t0 = time.time()
    leas = []
    for s in pe.sections:
        if not s.Characteristics & 0x20000000:
            continue
        start = base + s.VirtualAddress
        data = raw[s.PointerToRawData:s.PointerToRawData + s.SizeOfRawData]
        off = 0
        while off < len(data):
            end = off
            for ins in md.disasm(data[off:off + CHUNK + 16], start + off):
                if ins.address - start - off + ins.size > CHUNK:
                    break
                end = ins.address - start + ins.size
                if ins.mnemonic == "lea" and len(ins.operands) == 2:
                    op = ins.operands[1]
                    if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                        leas.append((ins.address, ins.operands[0].reg, rip_target(ins, op)))
            off = end if end > off else off + 1
    r8 = capstone.x86.X86_REG_R8
    rdx = capstone.x86.X86_REG_RDX
    for addr, reg, tgt in leas:
        if reg != rdx or tgt not in targets:
            continue
        names = [t for a, r, t in leas if r == r8 and addr < a <= addr + WINDOW]
        for name_va in names:
            rva = name_va - base
            for s in pe.sections:
                if s.VirtualAddress <= rva < s.VirtualAddress + s.SizeOfRawData:
                    off = s.PointerToRawData + rva - s.VirtualAddress
                    print(f"slot=0x{tgt:x} site=0x{addr:x} name={utf16_at(raw, off)!r} (0x{name_va:x})")
                    break
    print(f"leas={len(leas)} sec={time.time() - t0:.1f}")


if __name__ == "__main__":
    main()
