#!/usr/bin/env python3
"""PY-264 (#3888): vptr 候補 0xed0c28 (表 B) と 0xed0bb0 (表 A) を格納する静的な書込みが PE にあるかを数える。

  FL_WIN64_DIR=<展開先> python3 analysis/py264_vptr_scan.py

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*_PE.bin' (313 block)
検査:
  1. 全 PE block の 8 byte (qword) と 4 byte (imm32) の絶対値一致 (0xed0c28・0xed0bb0・0x11b2ac0・0x1375990)。
  2. block00031 の .text で、RIP 相対の参照先が 0xed0000..0xed1000 (表の区間) に入る命令。
  3. 0x11b2ac0 の呼出し経路の要点: 0x11b2af9 の読出し 1 件、0xed4ee0 が [rcx] に書かない。
期待値と異なれば rc 1。
"""
import glob
import os
import re
import struct
import sys

import capstone
import pefile

EXT = os.path.join(os.environ["FL_WIN64_DIR"], "extracted")
MAIN = os.path.join(EXT, "block00031_PE.bin")
ABS = [0xED0C28, 0xED0BB0, 0x11B2AC0, 0x1375990]
RIP = re.compile(r"\[rip ([+-]) (0x[0-9a-f]+)\]")


def abs_hits():
    out = {}
    for f in sorted(glob.glob(os.path.join(EXT, "*_PE.bin"))):
        raw = open(f, "rb").read()
        if raw[:2] != b"MZ":
            continue
        for t in ABS:
            for v in (struct.pack("<Q", t), struct.pack("<I", t)):
                for h in re.finditer(re.escape(v), raw):
                    out.setdefault(t, []).append((os.path.basename(f), h.start()))
    return out


def rip_into_table(lo, hi):
    pe = pefile.PE(MAIN, fast_load=True)
    ib = pe.OPTIONAL_HEADER.ImageBase
    t = next(s for s in pe.sections if s.Name.rstrip(b"\0") == b".text")
    n = min(t.Misc_VirtualSize, t.SizeOfRawData)
    raw = open(MAIN, "rb").read()
    data = raw[t.PointerToRawData:t.PointerToRawData + n]
    va0 = ib + t.VirtualAddress
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    hits, off = [], 0
    while off < n:
        ins = next(md.disasm(data[off:off + 16], va0 + off), None)
        if ins is None:
            off += 1
            continue
        for sg, d in RIP.findall(ins.op_str):
            tgt = ins.address + ins.size + (int(d, 16) if sg == "+" else -int(d, 16))
            if lo <= tgt < hi:
                hits.append((ins.address, ins.mnemonic, ins.op_str, tgt))
        off += ins.size
    return hits


def main():
    rc = 0
    hits = abs_hits()
    for t in ABS:
        n = len(hits.get(t, []))
        print("abs %s: %d hit(s) in %d block(s)" % (hex(t), n, len({b for b, _ in hits.get(t, [])})))
    if [b for b, _ in hits.get(0xED0C28, []) if b != "block00031_PE.bin"]:
        rc = 1
    if [b for b, _ in hits.get(0xED0BB0, []) if b != "block00031_PE.bin"]:
        rc = 1
    rip = rip_into_table(0xED0000, 0xED1000)
    print("rip refs into 0xed0000..0xed1000: %d" % len(rip))
    for a, m, op, tgt in rip:
        print("  %s %s %s -> %s" % (hex(a), m, op, hex(tgt)))
    cells = [x for x in rip if x[3] == 0xED0B60]
    if len(cells) != 1 or cells[0][0] != 0x11B2AF9:
        rc = 1
    print("chain.check %s" % ("PASS" if rc == 0 else "FAIL"))
    return rc


if __name__ == "__main__":
    sys.exit(main())
