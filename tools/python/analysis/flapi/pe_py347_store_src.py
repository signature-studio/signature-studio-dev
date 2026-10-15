#!/usr/bin/env python3
"""PY-347 (#4604): [reg+0x100] (TMethod.Code) への 8 バイト格納のうち、格納直前の 48 バイト以内に call があり、
格納元が rax (call の戻り値) である箇所を列挙する。0x12acb70 は公開表から戻り値として得られる値とみられるため、
その候補を絞る (解析補助。候補の列挙のみで、格納値の確定はしない)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py347_store_src.py [--dump <path>]

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
終了 0 = 検査 PASS。
"""
import os
import re
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
STORE = re.compile(r"^mov qword ptr \[(\w+) \+ 0x100\], (rax)$")


def linear(md, code, start):
    out = []
    off = 0
    while off < len(code):
        got = next(md.disasm(code[off:off + 16], start + off), None)
        if got is None:
            off += 1
            continue
        out.append(got)
        off += got.size
    return out


def main():
    pe = pefile.PE(PE, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    text = next(s for s in pe.sections if s.Name.rstrip(b"\0") == b".text")
    n = min(text.Misc_VirtualSize, text.SizeOfRawData)
    raw = open(PE, "rb").read()
    code = raw[text.PointerToRawData:text.PointerToRawData + n]
    start = base + text.VirtualAddress
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = False
    insns = linear(md, code, start)
    hits = []
    for idx, ins in enumerate(insns):
        txt = f"{ins.mnemonic} {ins.op_str}"
        if not STORE.match(txt):
            continue
        window = [i for i in insns[max(0, idx - 12):idx] if ins.address - i.address <= 48]
        calls = [i for i in window if i.mnemonic == "call"]
        if calls:
            hits.append((ins.address, txt, calls[-1].address))
    for va, txt, cva in hits:
        print(f"0x{va:x} {txt} | call 0x{cva:x}")
    print(f"hits {len(hits)}")
    dump = sys.argv[sys.argv.index("--dump") + 1] if "--dump" in sys.argv else None
    if dump:
        with open(dump, "w") as f:
            for va, txt, cva in hits:
                f.write(f"0x{va:x} {txt} call=0x{cva:x}\n")
    sys.exit(0 if hits else 1)


if __name__ == "__main__":
    main()
