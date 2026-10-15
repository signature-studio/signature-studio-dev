#!/usr/bin/env python3
"""FLEngine PE の `.data` スロット G (VA 0x15e2e18 = 0x16b6e00 の番地を格納) の読込み箇所ごとに、
読んだ値 (&Y = 0x16b6e00) を持つレジスタの別名を線形区間で追い、Y 自体への store が起きるかを出す (PY-4876 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py4876_slot_readers.py <読込み VA csv>

- 読込み VA は pe_xref.py 0x15e2e18 の load 行から取る (既定の 35 箇所は REPORT_PY193.md §6 の再測定)。
- 区間は call/ret/jmp で止める (最大 60 命令)。別名は mov/lea/movzx/movsxd の複写で広げ、別名を
  上書きする mov で消す。STORE-via-alias は別名を base にした store (= Y 自体への書込み候補)。
  別名を値として格納する場合は「alias を格納」。
- 区間外・間接 call の先は見ない (静的に解決できない)。
- 展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
"""
import os
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
X = capstone.x86
ARG_REGS = {X.X86_REG_RCX, X.X86_REG_RDX, X.X86_REG_R8, X.X86_REG_R9}


def load_text():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    for s in pe.sections:
        if s.Characteristics & 0x20000000:
            st = base + s.VirtualAddress
            d = raw[s.PointerToRawData:s.PointerToRawData + s.SizeOfRawData]
            yield st, d


def window(md, d, st, a):
    off = a - st
    return list(md.disasm(d[off:off + 600], a))[:60]


def trace(ins_all):
    first = ins_all[0]
    alias = {first.operands[0].reg}
    out = []
    for ins in ins_all[1:]:
        if ins.mnemonic in ("call", "ret", "jmp"):
            tag = " (引数に別名?)" if ins.mnemonic == "call" and alias & ARG_REGS else ""
            out.append(f"{ins.address:x} {ins.mnemonic} {ins.op_str}{tag}")
            break
        ops = ins.operands
        mem = [op for op in ops if op.type == X.X86_OP_MEM]
        for k, op in enumerate(ops):
            if k == 0 and op.type == X.X86_OP_MEM and op.mem.base in alias and ins.mnemonic not in ("lea", "cmp", "test"):
                out.append(f"{ins.address:x} STORE-via-alias {ins.mnemonic} {ins.op_str}")
        if mem and ops[0].type == X.X86_OP_MEM:
            for op in ops[1:]:
                if op.type == X.X86_OP_REG and op.reg in alias:
                    out.append(f"{ins.address:x} alias を格納 {ins.mnemonic} {ins.op_str}")
        if ops and ops[0].type == X.X86_OP_REG:
            src_alias = any(op.type == X.X86_OP_REG and op.reg in alias for op in ops[1:])
            if ins.mnemonic in ("mov", "movzx", "movsxd", "lea") and src_alias:
                alias.add(ops[0].reg)
            elif ins.mnemonic in ("mov", "lea", "xor", "movzx", "movsxd", "pop") and not src_alias:
                alias.discard(ops[0].reg)
                if not alias:
                    out.append(f"{ins.address:x} alias 消滅 {ins.mnemonic} {ins.op_str}")
                    break
    return out


def main():
    loads = [int(x, 16) for x in sys.argv[1].split(",")]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    text = list(load_text())
    stores = 0
    for a in loads:
        st, d = next((st, d) for st, d in text if st <= a < st + len(d))
        ins_all = window(md, d, st, a)
        first = ins_all[0]
        out = trace(ins_all)
        stores += sum("STORE-via-alias" in line for line in out)
        print(f"0x{a:x} first={first.mnemonic} {first.op_str}")
        for line in out:
            print("  " + line)
        if not out:
            print("  (区間内に参照なし)")
    print(f"sites={len(loads)} store_via_alias={stores}")


if __name__ == "__main__":
    main()
