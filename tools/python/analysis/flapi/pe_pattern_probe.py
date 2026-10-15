#!/usr/bin/env python3
"""patterns の数え・選択系 4 関数 (PY-173 / #3220) の逆アセンブル事実を出し、期待する命令列を検査する。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_pattern_probe.py [--negctl]

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
検査: 期待する命令の部分文字列が無ければ exit 1。--negctl は patternCount の走査上限を 1 つ壊し、exit 1 になることを確かめる。
"""
import os
import re
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
PRED = 0x12D8D30
ENUM_N = 80

# (関数 VA, 名前, 期待する命令の部分文字列 (順不同で含まれること))
EXPECT = [
    (0xD64D40, "patternCount", ["mov esi, 1", "mov dl, 1", "xor r8, r8", "xor r9, r9", "call 0x12d8d30",
                                 "cmp esi, 0x3e8", "add ebx, 1", "mov ecx, ebx"]),
    (0xD64D20, "patternNumber", ["mov ecx, dword ptr [rax]"]),
    (0xD66060, "isPatternDefault", ["cmp rax, 1", "cmp rax, 0x3e7", "mov dl, 1", "mov r8b, 1", "mov r9b, 1",
                                     "call 0x12d8d30"]),
    (0xD65FF0, "isPatternSelected", ["sub edx, 1", "call 0xea7420"]),
    (0xEA7420, "selector_list", ["cmp dword ptr [r9 + r11*4], edx", "lea r11, [r11 + r11*2]"]),
]


def load():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    return raw, base, pe.sections


def to_off(va, base, secs):
    rva = va - base
    for s in secs:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            return s.PointerToRawData + (rva - s.VirtualAddress)
    sys.exit("VA が section 外: %#x" % va)


def disasm(raw, base, secs, va, n):
    off = to_off(va, base, secs)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    out = []
    for i, ins in enumerate(md.disasm(raw[off:off + n * 16], va)):
        if i >= n:
            break
        out.append("%s %s %s" % (hex(ins.address), ins.mnemonic, ins.op_str))
    return out


def main():
    neg = "--negctl" in sys.argv
    raw, base, secs = load()
    ok = True
    for va, name, want in EXPECT:
        lines = disasm(raw, base, secs, va, ENUM_N if name != "selector_list" else 40)
        text = "\n".join(lines)
        if neg and name == "patternCount":
            want = [w.replace("cmp esi, 0x3e8", "cmp esi, 0x3e7") for w in want]
        missing = [w for w in want if w not in text]
        print("# %s %#x: %s" % (name, va, "OK" if not missing else "NG missing=%s" % missing))
        ok = ok and not missing
    lines = disasm(raw, base, secs, PRED, 60)
    first = lines[0]
    m = re.search(r"\[rip \+ (0x[0-9a-f]+)\]", first)
    table = (PRED + 7 + int(m.group(1), 16)) if m else None
    print("# predicate %#x: table=%s stride=0xc0 (shl 3; lea *3; lea *8)" % (PRED, hex(table) if table else "?"))
    fields = sorted({(w, int(d, 16)) for w, d in re.findall(r"(byte|dword|qword) ptr \[rcx \+ (0x[0-9a-f]+)\]", "\n".join(lines))})
    for w, d in fields:
        print("#   field +%#x width=%s" % (d, w))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
