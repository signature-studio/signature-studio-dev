#!/usr/bin/env python3
"""FLEngine PE (block00031_PE.bin) の .text 内で、変位 disp (例: 0xd98) を持つ『メモリ書込み』命令を列挙する (PY-388 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_disp_stores.py <disp(16進)> [<disp> ...]

方式: disp32 / disp8 のバイト一致位置を探し、その直前から始まる命令を逆アセンブルして、
命令の第 1 オペランドが [base+disp] で、かつ第 2 オペランドが即値・レジスタの書込みだけを採る。
線形逆アセンブルは .text 内のデータで同期が外れるため使わない。base が特定できない
(書込み先のレジスタの出どころは追わない) ので、件数は上界であり、個々の行は手で確認すること。
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
    text = pe.sections[0]
    vsec = pe.OPTIONAL_HEADER.ImageBase + text.VirtualAddress
    code = raw[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    for arg in sys.argv[1:]:
        disp = int(arg, 16)
        pat = disp.to_bytes(4, "little", signed=True)
        at_list = []
        i = code.find(pat)
        while i != -1:
            at_list.append(i)
            i = code.find(pat, i + 1)
        hits = []
        for i in at_list:
            va = vsec + i - 0
            for back in range(2, 9):
                st = va - back
                fo = text.PointerToRawData + (st - vsec)
                ins = next(md.disasm(raw[fo:fo + 16], st), None)
                if not ins or not (ins.address <= va < ins.address + ins.size):
                    continue
                ops = ins.operands
                if (ins.mnemonic.startswith("mov") and ops and ops[0].type == capstone.x86.X86_OP_MEM
                        and ops[0].mem.disp == disp):
                    hits.append((hex(ins.address), ins.mnemonic, ins.op_str))
                break
        print("disp", hex(disp), "store-candidates", len(hits))
        for h in hits:
            print(*h)


if __name__ == "__main__":
    main()
