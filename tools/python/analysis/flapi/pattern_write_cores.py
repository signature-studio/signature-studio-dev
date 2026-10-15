#!/usr/bin/env python3
"""PY-4871 (#5130): patterns 書き込み系 6 関数のハンドラ → 書式 → コア VA を PE から抽出する (実機不要)。

  python3 analysis/flapi/pattern_write_cores.py <PE.bin>

ハンドラ先頭から ret までを逆アセンブルし、(1) PyArg の書式文字列 (rip 相対 lea の指す文字列)、
(2) 0xd843d0 (job 投入) の直前の `lea r8, [rip+..]` が指す関数 (コア) の VA を出す。
ensureValidNoteRecord は 0xd843d0 を経由しないので、コアは None。
"""
import re
import sys

import capstone
import pefile
from capstone.x86 import X86_OP_MEM

HANDLERS = {
    "setChannelLoop": 0xD65E00,
    "clearPattern": 0xD66D50,
    "clonePattern": 0xD66B80,
    "burnLoop": 0xD666D0,
    "setLoopStarterRootNote": 0xD668C0,
    "ensureValidNoteRecord": 0xD65930,
}
DISPATCH = 0xD843D0
FMT = re.compile(rb"^[a-zA-Z|]+$")


def main():
    path = sys.argv[1]
    pe = pefile.PE(path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    text = next(s for s in pe.sections if s.Name.startswith(b".text"))
    data = open(path, "rb").read()
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True

    def off(va):
        return text.PointerToRawData + (va - base - text.VirtualAddress)

    def body(va, n=0x800):
        out = []
        for ins in md.disasm(data[off(va):off(va) + n], va):
            out.append(ins)
            if ins.mnemonic in ("ret", "int3"):
                break
        return out

    def rip_target(ins):
        m = [o for o in ins.operands if o.type == X86_OP_MEM][0].mem
        return ins.address + ins.size + m.disp

    for name, va in HANDLERS.items():
        ins = body(va)
        fmt = None
        for x in ins:
            if x.mnemonic == "lea" and "[rip" in x.op_str:
                t = rip_target(x)
                s = data[off(t):off(t) + 16].split(b"\0")[0]
                if FMT.match(s) and fmt is None:
                    fmt = s
        core = None
        for i, x in enumerate(ins):
            if x.mnemonic == "call" and x.op_str == hex(DISPATCH):
                for j in range(i - 1, max(i - 40, 0), -1):
                    p = ins[j]
                    if p.mnemonic == "lea" and p.op_str.startswith("r8, [rip"):
                        core = rip_target(p)
                        break
                break
        print(f"{name} handler={va:#x} fmt={fmt!r} core={core and hex(core)}")


if __name__ == "__main__":
    main()
