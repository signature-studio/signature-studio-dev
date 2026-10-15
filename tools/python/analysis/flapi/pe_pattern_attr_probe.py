#!/usr/bin/env python3
"""PY-174 (#4009): patterns 単体属性 3 関数の PE 解析補助。注釈付き逆アセンブルと、グローバルへの直接書込み検索を行う。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_pattern_attr_probe.py <VA(16進)> [<VA> ...]
  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_pattern_attr_probe.py --writers

展開: 素材 fl-win64 を tar --zstd -xf <素材>.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
rip 相対の参照先は ; で注釈する。IAT 参照は DLL!名前、文字列は ASCII 先頭 60 字。
"""
import os
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
RAW = open(PE, "rb").read()
PE_OBJ = pefile.PE(data=RAW, fast_load=True)
PE_OBJ.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
BASE = PE_OBJ.OPTIONAL_HEADER.ImageBase
SECS = [(s.VirtualAddress, max(s.Misc_VirtualSize, s.SizeOfRawData), s.PointerToRawData, s.Name.rstrip(b"\0"))
        for s in PE_OBJ.sections]
IAT = {}
for imp in getattr(PE_OBJ, "DIRECTORY_ENTRY_IMPORT", []):
    for f in imp.imports:
        IAT[f.address] = imp.dll.decode() + "!" + (f.name.decode() if f.name else "ord%s" % f.ordinal)


def fo(va):
    rva = va - BASE
    for v, sz, p, _ in SECS:
        if v <= rva < v + sz:
            return p + (rva - v)
    return None


def cstr(va):
    o = fo(va)
    if o is None:
        return None
    return RAW[o:RAW.index(b"\0", o)]


def rip_target(ins):
    if "rip + " in ins.op_str:
        return ins.address + ins.size + int(ins.op_str.split("rip + ")[1].split("]")[0], 16)
    if "rip - " in ins.op_str:
        return ins.address + ins.size - int(ins.op_str.split("rip - ")[1].split("]")[0], 16)
    return None


def annotate(ins):
    tgt = rip_target(ins)
    if tgt is None:
        return ""
    if tgt in IAT:
        return "  ; IAT " + IAT[tgt]
    s = cstr(tgt)
    if s and 1 < len(s) and s.isascii():
        return "  ; [%s] -> %s" % (hex(tgt), s[:60].decode())
    return "  ; [%s]" % hex(tgt)


def disasm(va, count=160):
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    o = fo(va)
    out = []
    for ins in md.disasm(RAW[o:o + count * 16], va):
        out.append("%s %s %s%s" % (hex(ins.address), ins.mnemonic, ins.op_str, annotate(ins)))
        if ins.mnemonic == "ret" or len(out) >= count:
            break
    return out


def writers():
    """.text 内で rip 相対の mov により書込まれる先を列挙する (直接書込みのみ。間接ポインタ経由は見ない)。"""
    text = [s for s in SECS if s[3] == b".text"][0]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    code = RAW[text[2]:text[2] + text[1]]
    hits = {}
    off = 0
    while off < len(code):
        got = next(md.disasm(code[off:off + 16], BASE + text[0] + off), None)
        if got is None:
            off += 1
            continue
        if got.mnemonic == "mov" and got.op_str.split(",")[0].startswith(("qword ptr [rip", "dword ptr [rip")):
            tgt = rip_target(got)
            if tgt is not None:
                hits.setdefault(hex(tgt), []).append(hex(got.address))
        off += got.size
    return hits


if __name__ == "__main__":
    if sys.argv[1:2] == ["--writers"]:
        for k, v in sorted(writers().items()):
            print(k, v)
    else:
        for a in sys.argv[1:]:
            print("=== " + a)
            print("\n".join(disasm(int(a, 16))))
