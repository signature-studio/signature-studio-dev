#!/usr/bin/env python3
"""PY-190 / #5205 の補助: slot 35 の逆アセンブル方式の復号欠落を確認する。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_decode_coverage.py

- `.text` を線形に復号した命令数・復号不能バイト数 (`pe_fe9090_table.linear_disasm` と同じ方式) を出す。
- `call qword ptr [reg + 0x118]` (slot 35) の各箇所について、含む関数の先頭から箇所までを
  単独に復号したとき、箇所に正しく届くか (届かなければ復号欠落がある) を数える。
- slot 35 を含む関数全体の復号不能バイト数を出す。
"""
import bisect
import os
import re
import struct

import capstone
import pefile

from pe_fe9090_table import linear_disasm

CALL = re.compile(r"qword ptr \[(r\w+) \+ 0x118\]")


def main():
    raw = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
    with open(raw, "rb") as f:
        data = f.read()
    pe = pefile.PE(data=data, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    img = pe.get_memory_mapped_image()
    sec = {s.Name.rstrip(b"\0"): s for s in pe.sections}
    text = sec[b".text"]
    text_lo = base + text.VirtualAddress
    tb = img[text.VirtualAddress:text.VirtualAddress + text.Misc_VirtualSize]
    pd = data[sec[b".pdata"].PointerToRawData:sec[b".pdata"].PointerToRawData + sec[b".pdata"].SizeOfRawData]
    funcs = sorted((base + b, base + e) for b, e, _ in (struct.unpack_from("<III", pd, i) for i in range(0, len(pd) - 11, 12)) if b)
    starts = [f[0] for f in funcs]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    insns, undecodable = linear_disasm(md, tb, text_lo)
    print(".text %x-%x (%d bytes): decoded %d instructions, undecodable %d bytes"
          % (text_lo, text_lo + len(tb), len(tb), len(insns), undecodable))

    sites = [i.address for i in insns if i.mnemonic == "call" and CALL.search(i.op_str)]
    print("call [reg + 0x118] sites (linear): %d" % len(sites))

    short = 0
    owners = set()
    for a in sites:
        i = bisect.bisect_right(starts, a) - 1
        if i < 0 or not (funcs[i][0] <= a < funcs[i][1]):
            short += 1
            continue
        f0 = funcs[i][0]
        owners.add(funcs[i])
        body = list(md.disasm(tb[f0 - text_lo:a - text_lo], f0))
        end = body[-1].address + body[-1].size if body else f0
        if end != a:
            short += 1
    print("sites not reached by the per-function decode from the function start: %d" % short)

    bad = 0
    for f0, f1 in sorted(owners):
        b = tb[f0 - text_lo:f1 - text_lo]
        bad += len(b) - sum(x.size for x in md.disasm(b, f0))
    print("functions containing sites: %d; undecodable bytes inside them: %d" % (len(owners), bad))


if __name__ == "__main__":
    main()
