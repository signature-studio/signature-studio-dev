#!/usr/bin/env python3
"""グローバル参照命令 (VA) の所属関数を線形デコードで確かめる (PY-5418 / #6207 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py6207_readers.py <命令VA(16進)> [<命令VA> ...]

参照命令の列挙は `analysis/flapi/pe_py193_refs.py <開始VA> <終了VA>` で行い、その出力の命令 VA を渡す。
<展開先> は fl-win64 の `extracted/block00031_PE.bin` を置いた先。
所属関数は、命令の直前が ret/int3 で、そこから線形デコードして対象命令の先頭に一致したものだけを採る。
一致しなければ『未確認』とする (関数先頭の確定はしない)。
"""
import os
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    text = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".text"][0]
    tva = base + text.VirtualAddress
    tb = raw[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    for arg in sys.argv[1:]:
        site = int(arg, 16)
        off = site - tva
        owner = "未確認"
        for j in range(off - 1, max(0, off - 0x20000), -1):
            if tb[j] not in (0xC3, 0xCC):
                continue
            s = tva + j + 1
            insns = list(md.disasm(tb[j + 1:j + 32], s))[:2]
            if len(insns) < 2 or insns[0].mnemonic not in ("push", "sub") \
                    or insns[1].mnemonic not in ("mov", "push", "sub", "lea", "xor", "test", "cmp", "call"):
                continue
            p = s - tva
            while p < off:
                ins = next(md.disasm(tb[p:p + 16], tva + p), None)
                if ins is None:
                    break
                p += ins.size
            if p == off:
                owner = f"{s:#x}"
                break
        ins = next(md.disasm(tb[off:off + 16], site), None)
        print(f"{site:#x} | {ins.mnemonic} {ins.op_str} | owner={owner}")


if __name__ == "__main__":
    sys.exit(main())
