#!/usr/bin/env python3
"""PY-306 (#4150): block00031_PE.bin の .text 全体で、global ポインタ slot (rip 相対) への書込み・lea と、slot の初期値 (.data の 8 バイト) を列挙する。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py306_slot_writers.py <slot VA(16進,カンマ区切り)>

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> extracted/block00031_PE.bin
出力: slot ごとの 直接書込み件数・lea 件数・初期値 (link VA)。所要 約 65 秒。
"""
import os
import sys

import capstone
import pefile
from capstone.x86 import X86_OP_MEM, X86_REG_RIP

WRITE_MNEMONICS = {"mov", "add", "sub", "inc", "dec", "and", "or", "xor", "xchg"}


def main():
    raw = open(os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin"), "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    targets = [int(x, 16) for x in sys.argv[1].split(",")]
    text = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".text"][0]
    va0 = base + text.VirtualAddress
    code = raw[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    md.skipdata = True
    writes = {t: [] for t in targets}
    leas = {t: [] for t in targets}
    for ins in md.disasm(code, va0):
        if ins.id == 0:
            continue
        for idx, op in enumerate(ins.operands):
            if op.type != X86_OP_MEM or op.mem.base != X86_REG_RIP:
                continue
            tgt = ins.address + ins.size + op.mem.disp
            if tgt not in writes:
                continue
            if idx == 0 and ins.mnemonic in WRITE_MNEMONICS:
                writes[tgt].append("%s %s %s" % (hex(ins.address), ins.mnemonic, ins.op_str))
            elif ins.mnemonic == "lea":
                leas[tgt].append(hex(ins.address))
    for t in targets:
        sec = [s for s in pe.sections if s.VirtualAddress <= t - base < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData)]
        init = "-"
        if sec and t - base - sec[0].VirtualAddress + 8 <= sec[0].SizeOfRawData:
            off = sec[0].PointerToRawData + (t - base - sec[0].VirtualAddress)
            init = hex(int.from_bytes(raw[off:off + 8], "little"))
        print(hex(t), "init", init, "direct-writes", len(writes[t]), "lea", len(leas[t]))
        for w in writes[t][:5]:
            print("   ", w)


if __name__ == "__main__":
    main()
