#!/usr/bin/env python3
"""FLEngine PE の .text 全体で、関数ポインタ表 0xfe2c80〜0xfe2ea0・0xd1af20・vtable V=0x125b1c0 の +0x60 格納値
0x1262970 を参照する命令を列挙する (PY-322 / #4371 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py322_probe.py

参照の種類:
- rip : [rip+disp] の参照先 (次命令 + disp)。
- abs : メモリ・オペランドの disp (base 無し) がその範囲に入る。
- imm : 即値オペランドがその範囲に入る。
- qword: 全 section の 8 byte 境界の格納値 (表の要素・関数先頭・vtable 格納)。
展開: tar --zstd -xf $HOME/artifacts/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
"""
import os
import struct
import time

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
TABLE_LO, TABLE_HI = 0xFE2C80, 0xFE2EA0
SINGLE = {0xD1AF20: "0xd1af20", 0x1262970: "0x1262970", 0x125B1C0: "0x125b1c0",
          0xD14800: "0xd14800", 0xD147D0: "0xd147d0"}
CHUNK = 1 << 16


def label(v):
    if TABLE_LO <= v <= TABLE_HI:
        return "table"
    return SINGLE.get(v)


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    t0 = time.time()
    n_ins = 0
    hits = []
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
                n_ins += 1
                end = ins.address - start + ins.size
                for op in ins.operands:
                    if op.type == capstone.x86.X86_OP_MEM:
                        if op.mem.base == capstone.x86.X86_REG_RIP:
                            tgt, kind = ins.address + ins.size + op.mem.disp, "rip"
                        else:
                            tgt, kind = op.mem.disp, "abs"
                        r = label(tgt)
                        if r:
                            hits.append((ins.address, kind, ins.mnemonic, ins.op_str, r))
                    elif op.type == capstone.x86.X86_OP_IMM:
                        r = label(op.imm)
                        if r:
                            hits.append((ins.address, "imm", ins.mnemonic, ins.op_str, r))
            off = end if end > off else off + 1
    for addr, kind, mn, ops, r in hits:
        print(f"0x{addr:x} {kind:4s} {mn} {ops} -> {r}")
    print(f"instructions={n_ins} hits={len(hits)} sec={time.time() - t0:.1f}")

    stored = {}
    for sec in pe.sections:
        d = raw[sec.PointerToRawData:sec.PointerToRawData + sec.SizeOfRawData]
        for p in range(0, len(d) - 7, 8):
            q = struct.unpack_from("<Q", d, p)[0]
            r = label(q)
            if r:
                va = base + sec.VirtualAddress + p
                stored.setdefault(r, []).append(hex(va))
    for k, v in sorted(stored.items()):
        print(f"stored {k}: n={len(v)} at {v[:8]}")


if __name__ == "__main__":
    main()
