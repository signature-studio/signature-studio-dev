#!/usr/bin/env python3
"""FLEngine PE の .text 内で `call qword ptr [reg + 0x118]` (VMT slot 35) の全箇所を列挙し、
各箇所を含む関数 (.pdata) に TPublicChannel / TPreviewChannel の VMT・クラス参照スロットが現れるかを出す (PY-190 / #3371 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_slot35_sites.py

- refs 列は「箇所を含む関数の中に、その型の VMT 値・RIP 相対のクラス参照スロットが直接現れる」かどうかだけを示す。
  受け手の実行時の型は決めない (呼出し元をたどる解析は行わない)。
- 展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
"""
import bisect
import os
import re
import struct

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
CH_VMTS = {0xfe2cf8: "TPublicChannel", 0xfe2fc8: "TPreviewChannel"}
CH_SLOTS = {0xfe2c30, 0xfe2ed8, 0xfe2f00, 0xfe31a9}
RESET = 0xfe9090
RIP = re.compile(r"\[rip ([+-]) (0x[0-9a-f]+)\]")
CALL = re.compile(r"qword ptr \[(r\w+) \+ 0x118\]")


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    sec = {s.Name.rstrip(b"\0"): s for s in pe.sections}
    text = sec[b".text"]
    text_lo = base + text.VirtualAddress
    tb = raw[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]
    pd = raw[sec[b".pdata"].PointerToRawData:sec[b".pdata"].PointerToRawData + sec[b".pdata"].SizeOfRawData]
    funcs = sorted((base + b, base + e) for b, e, _ in (struct.unpack_from("<III", pd, i) for i in range(0, len(pd) - 11, 12)) if b)
    starts = [f[0] for f in funcs]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    sites = []
    pos = 0
    while pos < len(tb):
        chunk = tb[pos:pos + 0x10000 + 32]
        last = None
        for ins in md.disasm(chunk, text_lo + pos):
            if ins.address - text_lo - pos >= 0x10000:
                break
            last = ins
            if ins.mnemonic == "call" and CALL.search(ins.op_str):
                sites.append(ins.address)
        pos = pos + 1 if last is None else last.address - text_lo + last.size

    refs_cache = {}

    def refs(fn):
        if fn not in refs_cache:
            hits = set()
            for ins in md.disasm(tb[fn[0] - text_lo:fn[1] - text_lo], fn[0]):
                m = RIP.search(ins.op_str)
                if m:
                    d = int(m.group(2), 16) * (1 if m.group(1) == "+" else -1)
                    if ins.address + ins.size + d in CH_SLOTS:
                        hits.add("slot:%x" % (ins.address + ins.size + d))
                for v in re.findall(r"0x[0-9a-f]+", ins.op_str):
                    if int(v, 16) in CH_VMTS:
                        hits.add("vmt:" + CH_VMTS[int(v, 16)])
            refs_cache[fn] = sorted(hits)
        return refs_cache[fn]

    print("call [reg + 0x118] sites:", len(sites))
    for a in sites:
        i = bisect.bisect_right(starts, a) - 1
        fn = funcs[i] if i >= 0 and funcs[i][0] <= a < funcs[i][1] else None
        h = refs(fn) if fn else []
        print("%x fn=%s refs=%s" % (a, "%x" % fn[0] if fn else "-", ",".join(h) or "-"))

    direct = []
    for i in range(len(tb) - 5):
        if tb[i] == 0xE8:
            d = struct.unpack_from("<i", tb, i + 1)[0]
            if text_lo + i + 5 + d == RESET:
                direct.append(text_lo + i)
    print("direct call sites to reset %x: %s" % (RESET, ",".join("%x" % a for a in direct) or "-"))
    for a in direct:
        i = bisect.bisect_right(starts, a) - 1
        fn = funcs[i] if i >= 0 and funcs[i][0] <= a < funcs[i][1] else None
        print("  %x in fn=%s" % (a, "%x" % fn[0] if fn else "-"))


if __name__ == "__main__":
    main()
