#!/usr/bin/env python3
"""FLEngine PE の .text 全体で、指定 VA のグローバル (ポインタ格納スロット) を読んだ直後に
`[reg+disp]` へ書く命令を列挙する (PY-93 の解析補助。pe_xref.py の線形走査を流用)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_slot_writers.py <スロット VA(16進)> [disp(16進, 既定 8)]

出力: 「`mov reg, [rip+slot]` の 0x40 バイト以内に `mov [reg2+disp], ...` がある」組。
`[slot]` が指すオブジェクトのフィールドへの書込み候補。候補は逆アセンブルで必ず確認する
(reg2 が slot 由来のポインタとは限らない)。
展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
"""
import bisect
import os
import sys
import time

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
CHUNK = 1 << 16
WINDOW = 0x40


def main():
    slot = int(sys.argv[1], 16)
    disp = int(sys.argv[2], 16) if len(sys.argv) > 2 else 8
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    t0 = time.time()
    n_ins = 0
    loads = []
    stores = []
    for s in pe.sections:
        if not s.Characteristics & 0x20000000:
            continue
        start = base + s.VirtualAddress
        data = raw[s.PointerToRawData:s.PointerToRawData + s.SizeOfRawData]
        off = 0
        while off < len(data):
            end = off
            for ins in md.disasm(data[off:off + CHUNK + 16], start + off):
                if ins.address - start - off + ins.size > CHUNK:
                    break
                n_ins += 1
                end = ins.address - start + ins.size
                ops = ins.operands
                if ins.mnemonic == "mov" and len(ops) == 2 and ops[0].type == capstone.x86.X86_OP_REG \
                        and ops[1].type == capstone.x86.X86_OP_MEM and ops[1].mem.base == capstone.x86.X86_REG_RIP \
                        and ins.address + ins.size + ops[1].mem.disp == slot:
                    loads.append((ins.address, ins.reg_name(ops[0].reg)))
                if ins.mnemonic == "mov" and len(ops) == 2 and ops[0].type == capstone.x86.X86_OP_MEM \
                        and ops[0].mem.disp == disp and ops[0].mem.base not in (0, capstone.x86.X86_REG_RIP):
                    stores.append((ins.address, ins.op_str))
            off = end if end > off else off + 1
    loads.sort()
    addrs = [a for a, _ in loads]
    n_hit = 0
    for a, op in stores:
        i = bisect.bisect_left(addrs, a - WINDOW)
        if i < len(loads) and loads[i][0] <= a:
            print(f"0x{a:x} store {op} <- load 0x{loads[i][0]:x} ({loads[i][1]})")
            n_hit += 1
    print(f"instructions={n_ins} slot_loads={len(loads)} disp_stores={len(stores)} "
          f"candidates={n_hit} sec={time.time() - t0:.1f}")


if __name__ == "__main__":
    main()
