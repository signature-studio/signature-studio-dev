#!/usr/bin/env python3
"""FLEngine PE の .text 全体で、指定 VA 範囲を指すオペランドを列挙する (PY-193 / #3380 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py193_refs.py <開始VA(16進)> <終了VA(16進)>

範囲 [開始, 終了) を指すオペランドを 3 種に分けて出す (pe_xref.py は rip 相対だけを見る):
- rip : [rip + disp] の計算先が範囲内
- abs : base レジスタ無しの [index*s + disp32] の disp が範囲内 (絶対番地。PE の固定基底向けの形)
- imm : 即値 (mov r32, imm32 等) が範囲内
- dsp : base レジスタ付きの [reg + disp] で disp が範囲内 (base の値は静的に決まらない候補)
線形走査は無効バイトで止まるため、止まったら 1 バイト進めて再同期する (pe_xref.py と同じ)。
展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
"""
import os
import sys
import time

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
CHUNK = 1 << 16


def main():
    lo = int(sys.argv[1], 16)
    hi = int(sys.argv[2], 16)
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    x86 = capstone.x86
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
                for i, op in enumerate(ins.operands):
                    if op.type == x86.X86_OP_IMM and lo <= (op.imm & 0xFFFFFFFFFFFFFFFF) < hi:
                        hits.append((ins.address, "imm", ins.mnemonic, ins.op_str, op.imm))
                    elif op.type == x86.X86_OP_MEM:
                        m = op.mem
                        if m.base == x86.X86_REG_RIP:
                            tgt = ins.address + ins.size + m.disp
                            if lo <= tgt < hi:
                                kind = "store" if i == 0 and ins.mnemonic in ("mov", "and", "or", "add", "sub", "inc", "dec") else "load"
                                hits.append((ins.address, f"rip/{kind}", ins.mnemonic, ins.op_str, tgt))
                        elif m.base == 0 and lo <= m.disp < hi:
                            hits.append((ins.address, "abs", ins.mnemonic, ins.op_str, m.disp))
                        elif m.base != 0 and lo <= m.disp < hi:
                            hits.append((ins.address, "dsp", ins.mnemonic, ins.op_str, m.disp))
            off = end if end > off else off + 1
    for addr, kind, mn, ops, tgt in hits:
        print(f"0x{addr:x} {kind:9s} {mn} {ops} -> 0x{tgt:x}")
    counts = {}
    for h in hits:
        counts[h[1].split("/")[0]] = counts.get(h[1].split("/")[0], 0) + 1
    print(f"instructions={n_ins} hits={len(hits)} by_kind={dict(sorted(counts.items()))} sec={time.time() - t0:.1f}")


if __name__ == "__main__":
    main()
