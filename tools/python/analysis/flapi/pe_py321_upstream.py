#!/usr/bin/env python3
"""PY-321 (#4347): 動的ディスパッチ 0x410090 (TMessage* を受けて DMT を引く) を呼ぶ上流の参照形態を PE 上で走査する。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py321_upstream.py

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin' (<展開先>/extracted/block00031_PE.bin に展開される)
走査する参照形態: direct call (E8)・direct jmp (E9/EB/Jcc)・RIP 相対オペランド・即値オペランド・
絶対 qword (VMT / 関数ポインタ表)。終了 0 = 全 PASS (= 0 件の確認)。1 件でも FAIL なら終了 1。
前段: pe_py274_dispatch.py (0x410090 の rsi/rdx の受け渡し 8/8)。
"""
import os
import re
import struct
import sys

import capstone
import pefile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pe_callgraph as pc  # noqa: E402

TARGET = 0x410090
RIP = re.compile(r"\[rip ([+-]) (0x[0-9a-f]+)\]")
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print("PASS" if ok else "FAIL", name, detail)


def scan_code(raw, pe):
    text = next(s for s in pe.sections if s.Name.rstrip(b"\0") == b".text")
    base = pe.OPTIONAL_HEADER.ImageBase + text.VirtualAddress
    n = min(text.Misc_VirtualSize, text.SizeOfRawData)
    data = raw[text.PointerToRawData:text.PointerToRawData + n]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    direct, rip_refs, imm_refs = [], [], []
    off = 0
    while off < n:
        ins = next(md.disasm(data[off:off + 16], base + off), None)
        if ins is None:
            off += 1
            continue
        off += ins.size
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_IMM and op.imm == TARGET:
                (direct if ins.mnemonic.startswith(("call", "j")) else imm_refs).append(ins.address)
        m = RIP.search(ins.op_str)
        if m:
            disp = int(m.group(2), 16) * (1 if m.group(1) == "+" else -1)
            if ins.address + ins.size + disp == TARGET:
                rip_refs.append(ins.address)
    return direct, rip_refs, imm_refs


def scan_qword(raw, pe):
    base = pe.OPTIONAL_HEADER.ImageBase
    pat = struct.pack("<Q", base + TARGET)
    hits = []
    off = raw.find(pat)
    while off != -1:
        hits.append(off)
        off = raw.find(pat, off + 1)
    return hits


def main():
    raw = open(pc.PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    direct, rip_refs, imm_refs = scan_code(raw, pe)
    qhits = scan_qword(raw, pe)
    check("0x410090 への direct call/jmp は 0 件", not direct, f"sites={[hex(x) for x in direct]}")
    check("0x410090 への RIP 相対参照は 0 件", not rip_refs, f"sites={[hex(x) for x in rip_refs]}")
    check("0x410090 の即値参照は 0 件", not imm_refs, f"sites={[hex(x) for x in imm_refs]}")
    check("0x410090 の絶対 qword (VMT・関数ポインタ表) は 0 件", not qhits, f"offs={[hex(x) for x in qhits]}")

    by_va = {a: (m, o) for a, m, o in pc.load()}
    check("msgid 0x057f を edx に入れる (0xfdd5ea)", by_va.get(0xFDD5EA) == ("mov", "edx, 0x57f"),
          f"got={by_va.get(0xFDD5EA)}")
    check("0xfdd5f9 で Perform 0x60c220 を呼ぶ", by_va.get(0xFDD5F9) == ("call", "0x60c220"),
          f"got={by_va.get(0xFDD5F9)}")
    check("0x60c220 で edx (msgid) を [rbp+0x20] に格納する", by_va.get(0x60C22C) == ("mov", "dword ptr [rbp + 0x20], edx"),
          f"got={by_va.get(0x60C22C)}")
    check("0x60c220 で [rbx+0x80] のメソッドポインタを呼ぶ", by_va.get(0x60C24F) == ("call", "qword ptr [rbx + 0x80]"),
          f"got={by_va.get(0x60C24F)}")
    print()
    print("PASS 件数", sum(RESULTS), "/", len(RESULTS))
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
