#!/usr/bin/env python3
"""FLEngine PE の .text 内で、絶対 VA 0x41c160 を 8 バイトで持つ箇所 (ポインタ表の候補) を列挙する (PY-5375 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_abs_table_xref.py [VA(16進)]

各箇所について次を出す:
  - 含む 8 バイト列の連続ポインタ run (.text 内の値が .text を指す連続 qword) の先頭 VA・長さ・対象 index
  - その run を RIP 相対で読む命令 (参照元の関数・命令)
  - 直接 call / jmp の数
  - 絶対 disp (base 無し) で run を指す命令の数
展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
"""
import bisect
import os
import struct
import sys
from collections import defaultdict

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    target = int(sys.argv[1], 16) if len(sys.argv) > 1 else 0x41C160
    tgt = target
    sec = {s.Name.rstrip(b"\0"): s for s in pe.sections}
    text = sec[b".text"]
    tstart = base + text.VirtualAddress
    tend = tstart + text.Misc_VirtualSize
    tdata = raw[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]

    def q(va):
        return struct.unpack_from("<Q", tdata, va - tstart)[0]

    def in_text(v):
        return tstart <= v < tend

    pat = struct.pack("<Q", tgt)
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

    pdata = sec[b".pdata"]
    pd = raw[pdata.PointerToRawData:pdata.PointerToRawData + pdata.SizeOfRawData]
    funcs = sorted(
        (base + b, base + e)
        for b, e, _ in (struct.unpack_from("<III", pd, i) for i in range(0, len(pd) - 11, 12))
        if b
    )

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    rip_refs = defaultdict(list)
    direct = []
    absref = defaultdict(int)
    for fs, fe in funcs:
        for ins in md.disasm(tdata[fs - tstart:fe - tstart + 16], fs):
            if ins.address >= fe:
                break
            if ins.mnemonic in ("call", "jmp") and ins.operands and ins.operands[0].type == capstone.x86.X86_OP_IMM:
                if ins.operands[0].imm == tgt:
                    direct.append((ins.address, ins.mnemonic, fs))
            for op in ins.operands:
                if op.type != capstone.x86.X86_OP_MEM:
                    continue
                if op.mem.base == capstone.x86.X86_REG_RIP:
                    r = run_of(ins.address + ins.size + op.mem.disp)
                    if r:
                        rip_refs[r].append((fs, ins.address, ins.mnemonic))
                elif op.mem.base == 0 and tstart <= op.mem.disp < tend:
                    r = run_of(op.mem.disp)
                    if r:
                        absref[r] += 1

    print(f"target=0x{target:x} qword_hits={len(hits)} runs={len(runs)} direct_calls_or_jmps={len(direct)}")
    for s, e in runs:
        idx = [(h - s) // 8 for h in hits if s <= h < e]
        refs = rip_refs.get((s, e), [])
        print(f"run 0x{s:x} len={(e - s) // 8} target_idx={idx} rip_refs={len(refs)} abs_refs={absref.get((s, e), 0)}")
        for fn, ia, mn in refs[:6]:
            print(f"  ref 0x{ia:x} {mn} fn=0x{fn:x}")


if __name__ == "__main__":
    main()
