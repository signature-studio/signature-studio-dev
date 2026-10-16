#!/usr/bin/env python3
"""PY-190 / #5205 の補助: 指定した VMT の VA を、PE 内で「値として格納する」箇所を数える。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_vmt_store_refs.py <VMT VA(16進)> [...]

- abs64: ファイル全体で、その VA を 8 バイト値として持つ箇所 (VMT 自身の slot 以外の格納元を探す)
- imm32: .text 内で、その VA を 4 バイト即値として持つ箇所 (mov qword ptr [reg], imm32 など)
- rip  : .text の逆アセンブル (capstone) で、[rip+disp] が VA を指す命令
- 各箇所は、含む .pdata 関数の先頭 VA と、VA を持つ section 名を出す。
- 展開: `docs/WORKFLOW.md` §11 の fl-win64 の展開手順 (`tar --zstd -xf <artifacts>/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'`)
"""
import bisect
import os
import re
import struct
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
RIP = re.compile(r"\[rip ([+-]) (0x[0-9a-f]+)\]")


def main():
    targets = [int(a, 16) for a in sys.argv[1:]]
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    secs = [(s.Name.rstrip(b"\0").decode(), base + s.VirtualAddress, s.PointerToRawData, s.SizeOfRawData) for s in pe.sections]
    sec = {n: (v, po, sz) for n, v, po, sz in secs}
    tva, tpo, tsz = sec[".text"][0], sec[".text"][1], sec[".text"][2]
    tb = raw[tpo:tpo + tsz]
    pd_va, pd_po, pd_sz = sec[".pdata"]
    pd = raw[pd_po:pd_po + pd_sz]
    funcs = sorted((base + b, base + e) for b, e, _ in (struct.unpack_from("<III", pd, i) for i in range(0, len(pd) - 11, 12)) if b)
    starts = [f[0] for f in funcs]

    def where_fn(a):
        i = bisect.bisect_right(starts, a) - 1
        return funcs[i][0] if i >= 0 and funcs[i][0] <= a < funcs[i][1] else 0

    def where_sec(off):
        for n, v, po, sz in secs:
            if po <= off < po + sz:
                return n, v + (off - po)
        return "-", 0

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    rip_hits = {t: [] for t in targets}
    pos = 0
    while pos < len(tb):
        chunk = tb[pos:pos + 0x10000 + 32]
        last = None
        for ins in md.disasm(chunk, tva + pos):
            if ins.address - tva - pos >= 0x10000:
                break
            last = ins
            m = RIP.search(ins.op_str)
            if m:
                d = int(m.group(2), 16) * (1 if m.group(1) == "+" else -1)
                t = ins.address + ins.size + d
                if t in rip_hits:
                    rip_hits[t].append((ins.address, ins.mnemonic, ins.op_str))
        pos = pos + 1 if last is None else last.address - tva + last.size

    for t in targets:
        p8 = struct.pack("<Q", t)
        p4 = struct.pack("<I", t) if t < 1 << 32 else None
        abs64 = []
        i = raw.find(p8)
        while i >= 0:
            abs64.append(i)
            i = raw.find(p8, i + 1)
        imm32 = []
        if p4:
            j = tb.find(p4)
            while j >= 0:
                imm32.append(j)
                j = tb.find(p4, j + 1)
        print("VMT/VA %x" % t)
        print("  abs64 (file 全体): %d" % len(abs64))
        for off in abs64:
            n, v = where_sec(off)
            print("    file %x sec=%s va=%x" % (off, n, v))
        print("  imm32 (.text 全体): %d" % len(imm32))
        for off in imm32:
            print("    .text off %x va=%x" % (off, tva + off))
        print("  rip-relative (逆アセンブル済み命令): %d" % len(rip_hits[t]))
        for a, mn, op in rip_hits[t]:
            print("    %x fn=%x %s %s" % (a, where_fn(a), mn, op))


if __name__ == "__main__":
    main()
