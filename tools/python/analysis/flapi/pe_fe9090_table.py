#!/usr/bin/env python3
"""PY-190 / #5205 の補助: reset `0xfe9090` を指す関数ポインタ表 (先頭 VA `0xfe2a90`) の参照を調べる。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_fe9090_table.py

出力:
  1. 表の先頭 19 エントリ (VA と格納値)
  2. `0xfe9090` を値として持つ 8 バイト・4 バイトの絶対アドレス格納箇所 (イメージ全体)
  3. `.text` 内で表の VA を disp (絶対または rip 相対) として参照する命令
  4. 表の VA を値として持つ 8 バイトの格納箇所 (イメージ全体)
"""
import os
import re
import struct

import capstone
import pefile

TABLE = 0xFE2A90
TARGET = 0xFE9090
ENTRIES = 19
RIP = re.compile(r"\[rip ([+-]) (0x[0-9a-f]+)\]")


def main():
    raw = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
    with open(raw, "rb") as f:
        data = f.read()
    pe = pefile.PE(data=data, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    img = pe.get_memory_mapped_image()
    text = [s for s in pe.sections if s.Name.startswith(b".text")][0]
    tva = base + text.VirtualAddress
    code = img[text.VirtualAddress:text.VirtualAddress + text.Misc_VirtualSize]

    print("table %x (entries %d)" % (TABLE, ENTRIES))
    for k in range(ENTRIES):
        off = TABLE - base + 8 * k
        print("  %x -> %x" % (TABLE + 8 * k, struct.unpack_from("<Q", img, off)[0]))

    def scan(pat):
        out, i = [], img.find(pat)
        while i != -1:
            out.append(base + i)
            i = img.find(pat, i + 1)
        return out

    print("8-byte stores of target %x: %s" % (TARGET, ["%x" % v for v in scan(struct.pack("<Q", TARGET))]))
    print("4-byte stores of target %x: %s" % (TARGET, ["%x" % v for v in scan(struct.pack("<I", TARGET))]))
    print("8-byte stores of table %x: %s" % (TABLE, ["%x" % v for v in scan(struct.pack("<Q", TABLE))]))

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    refs = []
    for ins in md.disasm(code, tva):
        m = RIP.search(ins.op_str)
        d = int(m.group(2), 16) * (1 if m.group(1) == "+" else -1) if m else None
        hit = ("0x%x" % TABLE) in ins.op_str or (d is not None and ins.address + ins.size + d == TABLE)
        if hit:
            refs.append("%x %s %s" % (ins.address, ins.mnemonic, ins.op_str))
    print("code refs to table %x in .text: %d" % (TABLE, len(refs)))
    for r in refs:
        print("  " + r)


if __name__ == "__main__":
    main()
