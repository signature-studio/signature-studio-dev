#!/usr/bin/env python3
"""FLEngine PE (block00031_PE.bin) の .text 内で、指定 VA の RIP 相対参照を読み・書き・lea に分類する (PY-388 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_slot_refs.py <VA(16進)>

方式: .text の生バイト列から disp32 が (対象 - 次命令の先頭) に一致する位置を探し、
その直前 1〜8 バイトから始まる命令を逆アセンブルして、命令が disp32 を含むものだけ採る。
線形逆アセンブルは .text 内のデータで同期が外れるため使わない。
偽陽性 (disp32 が即値の位置に偶然一致する) は逆アセンブルで除外する。
"""
import os
import sys

import capstone
import numpy as np
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    text = pe.sections[0]
    vsec = base + text.VirtualAddress
    target = int(sys.argv[1], 16)
    buf = np.frombuffer(raw[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData],
                        dtype=np.uint8).astype(np.int64)
    n = len(buf) - 3
    v = buf[:n] | (buf[1:n + 1] << 8) | (buf[2:n + 2] << 16) | (buf[3:n + 3] << 24)
    v = np.where(v >= 1 << 31, v - (1 << 32), v)
    pos = np.arange(n) + vsec
    cands = np.nonzero(v == (target - (pos + 4)))[0]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    counts = {"read": 0, "write": 0, "lea": 0, "other": 0}
    rows = []
    for i in cands:
        at = int(pos[i])
        for back in range(1, 9):
            st = at - back
            fo = text.PointerToRawData + (st - vsec)
            ins = next(md.disasm(raw[fo:fo + 16], st), None)
            if ins and ins.address <= at < ins.address + ins.size and "rip" in ins.op_str:
                if ins.mnemonic == "lea":
                    kind = "lea"
                elif ins.operands and ins.operands[0].type == capstone.x86.X86_OP_MEM:
                    kind = "write"
                elif len(ins.operands) >= 2 and ins.operands[1].type == capstone.x86.X86_OP_MEM:
                    kind = "read"
                else:
                    kind = "other"
                counts[kind] += 1
                rows.append((kind, hex(ins.address), ins.mnemonic, ins.op_str))
                break
    print("target", hex(target), "candidates", len(cands), "counts", counts)
    for r in rows:
        if r[0] != "read":
            print(*r)


if __name__ == "__main__":
    main()
