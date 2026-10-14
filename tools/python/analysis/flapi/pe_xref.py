#!/usr/bin/env python3
"""FLEngine PE の .text 全体で、RIP 相対に指定 VA を参照する命令を列挙する (PY-73 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_xref.py <VA(16進)>[,<VA(16進)>...]

参照先 = 次命令アドレス + disp (絶対 VA。ImageBase 0x400000 を含む)。第 1 オペランドがメモリなら store、
それ以外は load と分類する。線形走査は無効バイトで止まるため、止まったら 1 バイト進めて再同期する。
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
    targets = {int(x, 16) for x in sys.argv[1].split(",")}
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
                for i, op in enumerate(ins.operands):
                    if op.type != capstone.x86.X86_OP_MEM or op.mem.base != capstone.x86.X86_REG_RIP:
                        continue
                    tgt = ins.address + ins.size + op.mem.disp
                    if tgt in targets:
                        kind = "store" if i == 0 and ins.mnemonic == "mov" else "load"
                        hits.append((ins.address, kind, ins.mnemonic, ins.op_str, tgt))
            off = end + 1 if end > off else off + 1
    for addr, kind, mn, ops, tgt in hits:
        print(f"0x{addr:x} {kind:5s} {mn} {ops} -> 0x{tgt:x}")
    stores = sum(1 for h in hits if h[1] == "store")
    print(f"instructions={n_ins} hits={len(hits)} stores={stores} sec={time.time() - t0:.1f}")


if __name__ == "__main__":
    main()
