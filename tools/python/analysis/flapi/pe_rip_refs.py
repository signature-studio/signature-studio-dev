#!/usr/bin/env python3
""".text を線形走査し、RIP 相対オペランドが指す先が指定 VA の命令を列挙する (PY-39 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_rip_refs.py <VA(16進)> [<VA(16進)> ...]

例: pe_rip_refs.py 0x154528c   (selectAll の *p の指す int32 を参照する命令)
出力: 命令アドレス・命令・参照先 VA。書込み/読込みの区別は行わない (mnemonic と先頭オペランドで目視する)。

線形走査: 復号できないバイトは 1 バイト進めて再同期する (pe_scan_store.py と同じ方式)。
"""
import os
import re
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
RIP = re.compile(r"\[rip ([+-]) (0x[0-9a-f]+)\]")


def main():
    targets = {int(a, 16) for a in sys.argv[1:]}
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    text = next(s for s in pe.sections if s.Name.rstrip(b"\0") == b".text")
    n = min(text.Misc_VirtualSize, text.SizeOfRawData)
    va0 = pe.OPTIONAL_HEADER.ImageBase + text.VirtualAddress
    data = raw[text.PointerToRawData:text.PointerToRawData + n]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    off, hits = 0, 0
    while off < n:
        ins = next(md.disasm(data[off:off + 16], va0 + off), None)
        if ins is None:
            off += 1
            continue
        m = RIP.search(ins.op_str)
        if m:
            d = int(m.group(2), 16) * (1 if m.group(1) == "+" else -1)
            slot = ins.address + ins.size + d
            if slot in targets:
                hits += 1
                print(f"{hex(ins.address)} {ins.mnemonic} {ins.op_str} -> {hex(slot)}")
        off += ins.size
    print(f"hits {hits}", file=sys.stderr)


if __name__ == "__main__":
    main()
