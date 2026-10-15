#!/usr/bin/env python3
"""launchMapPages の PyMethodDef 12 件 (entry VA 0x151e058〜0x151e1b8) を FLEngine PE から引き、fn VA・flags・
docstring を出す。flags は flapi_table.json の kwsig.flags と突き合わせる (PY-120 #2984 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_launchmap_entries.py [--disasm]

- 範囲は entry VA で切る (init・length は他モジュールの PyMethodDef と名前が重なるため)。
- 記録は 32 バイト (name, fn, flags (int32 + 4 pad), doc)。
- --disasm: 各 fn を ret まで逆アセンブルし、RIP 相対の文字列・呼出し先 VA を注記する。
"""
import json
import os
import struct
import sys

import capstone
import pefile

HERE = os.path.dirname(os.path.abspath(__file__))
PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
LO, HI = 0x151E058, 0x151E1D8
TABLE = json.load(open(os.path.join(HERE, "flapi_table.json")))["modules"]["launchMapPages"]


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    secs = [(s.VirtualAddress, s.Misc_VirtualSize, s.PointerToRawData, s.SizeOfRawData) for s in pe.sections]

    def v2o(va):
        rva = va - base
        for v, vs, p, rs in secs:
            if v <= rva < v + max(vs, rs):
                return p + (rva - v)
        return None

    def cstr(va):
        fo = v2o(va) if va else None
        if fo is None:
            return None
        e = raw.find(b"\0", fo, fo + 200)
        s = raw[fo:e] if e != -1 else b""
        return s.decode() if s and len(s) < 120 and all(32 <= c < 127 for c in s) else None

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    seen = 0
    for va in range(LO, HI, 0x20):
        fo = v2o(va)
        nm, fn, flags, doc = struct.unpack_from("<QQixxxxQ", raw, fo)
        name = cstr(nm)
        if name is None:
            continue
        seen += 1
        flapi = TABLE[name]["kwsig"]["flags"]
        print(f"{name:26s} entry={va:#x} fn={fn:#x} flags={flags} flapi_flags={flapi} "
              f"{'OK' if flags == flapi else 'MISMATCH'} doc={cstr(doc)!r}")
        if "--disasm" in sys.argv[1:]:
            ffo = v2o(fn)
            for ins in md.disasm(raw[ffo:ffo + 0x1600], fn):
                note = ""
                if "rip" in ins.op_str:
                    tgt = ins.address + ins.size + int(ins.op_str.split("rip")[1].split("]")[0].replace(" ", ""), 0)
                    s = cstr(tgt)
                    note = f"  ; str {s!r}" if s is not None else f"  ; [{tgt:#x}]"
                print(f"    {ins.address:#x}: {ins.mnemonic} {ins.op_str}{note}")
                if ins.mnemonic == "ret":
                    break
    assert seen == 12, seen


if __name__ == "__main__":
    main()
