#!/usr/bin/env python3
"""FLEngine PE (block00031_PE.bin) の関数 VA を直接 call (E8 rel32) している箇所と、
.text 外に出現する 8 バイト・4 バイト RVA (VMT スロット・.pdata) を列挙する (PY-388 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_e8_callers.py <VA(16進)> [<VA> ...]

線形逆アセンブル (pe_disasm.py の先頭から) は .text 先頭の非命令データで止まるため使わず、
E8 バイトを直接走査して候補を出す。候補は pe_disasm.py で目視確認すること。
"""
import os
import struct
import sys

import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    targets = {int(a, 16) for a in sys.argv[1:]}
    text = next(s for s in pe.sections if s.Name.startswith(b".text"))
    data = raw[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]
    start = base + text.VirtualAddress
    calls = {t: [] for t in targets}
    for i in range(len(data) - 5):
        if data[i] != 0xE8:
            continue
        rel = struct.unpack_from("<i", data, i + 1)[0]
        dst = start + i + 5 + rel
        if dst in calls:
            calls[dst].append(start + i)
    for t in sorted(targets):
        print(f"{hex(t)} direct E8 callers: {len(calls[t])}")
        for c in calls[t]:
            print(f"  {hex(c)}")
        for sec in pe.sections:
            if sec.Name.startswith(b".text"):
                continue
            d = raw[sec.PointerToRawData:sec.PointerToRawData + sec.SizeOfRawData]
            name = sec.Name.rstrip(b"\0").decode()
            for fmt, label in ((struct.pack("<Q", t), "8-byte ptr"),
                               (struct.pack("<I", t - base), "4-byte RVA")):
                j = d.find(fmt)
                while j != -1:
                    print(f"  {label} in {name}: {hex(base + sec.VirtualAddress + j)}")
                    j = d.find(fmt, j + 1)


if __name__ == "__main__":
    main()
