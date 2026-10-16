#!/usr/bin/env python3
"""FLEngine PE の .text 全体を命令単位で線形走査し、pe_abs_table_xref.py が出した連続ポインタ run
(0x41c160 を持つ 73 本) を指す RIP 相対参照・即値を列挙する (PY-5375 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_abs_linear_5375.py

.pdata の関数境界に依存しないので、関数外の領域にある参照も拾う。ただし data 領域を命令として
誤デコードするため、即値一致 (jcc・loopne 等) は偶然の一致を含む。実参照かは pe_disasm.py で確認する。
展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
"""
import bisect
import os
import struct
from collections import defaultdict

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
TGT = 0x41C160


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    sec = {s.Name.rstrip(b"\0"): s for s in pe.sections}
    text = sec[b".text"]
    tstart = base + text.VirtualAddress
    tend = tstart + text.Misc_VirtualSize
    tdata = raw[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]

    def q(va):
        return struct.unpack_from("<Q", tdata, va - tstart)[0]

    def in_text(v):
        return tstart <= v < tend

    pat = struct.pack("<Q", TGT)
    hits = []
    i = -1
    while True:
        i = tdata.find(pat, i + 1)
        if i < 0:
            break
        hits.append(tstart + i)
    runs = set()
    for h in hits:
        s = h
        while s - 8 >= tstart and in_text(q(s - 8)):
            s -= 8
        e = h
        while e + 8 < tend and in_text(q(e + 8)):
            e += 8
        runs.add((s, e + 8))
    runs = sorted(runs)
    rstarts = [r[0] for r in runs]

    def run_of(t):
        k = bisect.bisect_right(rstarts, t) - 1
        if k >= 0 and runs[k][0] <= t < runs[k][1]:
            return runs[k]
        return None

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    rip = defaultdict(list)
    imm = defaultdict(list)
    off = 0
    ninsn = 0
    bad = 0
    n = len(tdata)
    while off < n:
        got = list(md.disasm(tdata[off:off + 16], tstart + off, 1))
        if not got:
            off += 1
            bad += 1
            continue
        ins = got[0]
        ninsn += 1
        off += ins.size
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                r = run_of(ins.address + ins.size + op.mem.disp)
                if r:
                    rip[r].append((ins.address, ins.mnemonic))
            elif op.type == capstone.x86.X86_OP_IMM:
                r = run_of(op.imm)
                if r:
                    imm[r].append((ins.address, ins.mnemonic))

    print(f"target=0x{TGT:x} qword_hits={len(hits)} runs={len(runs)} insns={ninsn} undecodable_bytes={bad}")
    print(f"run_with_rip_ref={sum(1 for r in runs if rip.get(r))} run_with_imm_match={sum(1 for r in runs if imm.get(r))}")
    for r in runs:
        for ia, mn in rip.get(r, []):
            print(f"rip run=0x{r[0]:x} at=0x{ia:x} {mn}")
        for ia, mn in imm.get(r, []):
            print(f"imm run=0x{r[0]:x} at=0x{ia:x} {mn}")


if __name__ == "__main__":
    main()
