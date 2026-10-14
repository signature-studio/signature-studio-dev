#!/usr/bin/env python3
"""FLEngine PE (block00031_PE.bin) の .text を線形走査し、[reg+disp] への書込み命令を列挙する (PY-69 の選択フラグ書込み箇所の確認用)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_scan_store.py <disp(16進)>

  例: pe_scan_store.py 0x32c   (channel item の選択フラグ +0x32c への byte 書込み)

線形走査: 復号できないバイトは 1 バイト進めて再同期する。対象は先頭オペランドがメモリ (byte ptr [reg+disp]) の
mov/set*/and/or/add/sub/xor/inc/dec/neg/not。書込みの近似で、構造体の型は見ない (所在の列挙だけ)。
"""
import os
import re
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
WRITE = re.compile(r"^(?:mov|set\w+|and|or|add|sub|xor|inc|dec|neg|not) byte ptr \[\w+ \+ (0x[0-9a-f]+)\]")


def main():
    disp = sys.argv[1].lower()
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    text = next(s for s in pe.sections if s.Name.rstrip(b"\0") == b".text")
    n = min(text.Misc_VirtualSize, text.SizeOfRawData)
    va0 = base + text.VirtualAddress
    data = raw[text.PointerToRawData:text.PointerToRawData + n]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    off, hits = 0, []
    while off < n:
        ins = next(md.disasm(data[off:off + 16], va0 + off), None)
        if ins is None:
            off += 1
            continue
        text_ins = ins.mnemonic + " " + ins.op_str
        m = WRITE.match(text_ins)
        if m and m.group(1) == disp:
            hits.append((ins.address, text_ins))
        off += ins.size
    for va, s in hits:
        print(hex(va), s)
    print(f"text {n} bytes, hits {len(hits)}", file=sys.stderr)


if __name__ == "__main__":
    main()
