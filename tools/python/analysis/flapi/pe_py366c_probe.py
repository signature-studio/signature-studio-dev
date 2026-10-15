#!/usr/bin/env python3
"""PY-366 (#4543) 続き: 大域 G (0x15eac80) の初期値と、0x41d8f0 の呼び出し経路の確認 (解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py366c_probe.py

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
  (<展開先>/extracted/block00031_PE.bin が存在すること)
終了 0 = 全 PASS。1 件でも FAIL なら終了 1。
"""
import os
import struct
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
G = 0x15EAC80
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    text = [s for s in pe.sections if s.Name.startswith(b".text")][0]
    bss = [s for s in pe.sections if s.Name.startswith(b".bss")][0]
    tva = base + text.VirtualAddress
    body = raw[text.PointerToRawData: text.PointerToRawData + text.SizeOfRawData]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    insns = list(md.disasm(body, tva))

    # 1. G は .bss 内で、.bss は raw データ 0 バイト (ローダーがゼロ初期化する) → 初期値 0
    bss_lo = base + bss.VirtualAddress
    bss_hi = bss_lo + bss.Misc_VirtualSize
    check("G は .bss 内", bss_lo <= G < bss_hi, f"{hex(bss_lo)}-{hex(bss_hi)}")
    check(".bss の raw データは 0 バイト (VirtualSize のみ・ゼロ初期化)", bss.SizeOfRawData == 0)

    # 2. 0x41d8f0 の直接 call 元 (E8) は 0x1376870 の 1 箇所
    callers = []
    for off in range(len(body) - 5):
        if body[off] == 0xE8:
            rel = struct.unpack_from("<i", body, off + 1)[0]
            if tva + off + 5 + rel == 0x41D8F0:
                callers.append(tva + off)
    check("0x41d8f0 の E8 直接 call 元は 0x1376870 のみ", callers == [0x1376870], " ".join(hex(a) for a in callers))

    # 3. 0x1376820 (0x1376870 を含む関数の先頭) は block00031 内の直接参照・RIP 相対参照を持たない
    #    (.pdata の unwind エントリだけ。呼び出しは別ブロックの間接参照に依る)
    refs = []
    for i in insns:
        if i.op_str.startswith("0x"):
            try:
                if int(i.op_str, 16) == 0x1376820:
                    refs.append(i.address)
            except ValueError:
                pass
        for op in i.operands:
            if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                if i.address + i.size + op.mem.disp == 0x1376820:
                    refs.append(i.address)
    check("0x1376820 は block00031 内に直接・RIP 相対の参照を持たない", not refs, " ".join(hex(a) for a in refs))

    ok = all(RESULTS)
    print(f"{sum(RESULTS)}/{len(RESULTS)} PASS")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
