#!/usr/bin/env python3
"""channels 関数の PyMethodDef エントリを FLEngine PE から引き、ハンドラ先頭の逆アセンブルと
RIP 相対で参照する文字列 (PyArg 書式・kwlist 等) を出す (PY-39 の解析補助。方式は analysis/flapi_kwargs.py と同じ)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_handler_probe.py [名前 ...]
  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_handler_probe.py 0xd6b700 [0x... ...]   (VA を直接逆アセンブル。cb の確認用)
"""
import os
import struct
import sys

import capstone
import pefile

DEFAULT_NAMES = ["selectAll", "selectOneChannel", "setChannelPitch", "setStepParameterByIndex",
                 "midiNoteOn", "incEventValue", "processRECEvent"]
PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
HEAD = 40


def main():
    args = sys.argv[1:]
    vas = [int(a, 16) for a in args if a.startswith("0x")]
    names = [a for a in args if not a.startswith("0x")] or ([] if vas else DEFAULT_NAMES)
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=False)
    base = pe.OPTIONAL_HEADER.ImageBase
    secs = [(s.VirtualAddress, s.Misc_VirtualSize, s.PointerToRawData, s.SizeOfRawData)
            for s in pe.sections]

    def v2o(va):
        rva = va - base
        for vaddr, vsz, praw, rsz in secs:
            if vaddr <= rva < vaddr + max(vsz, rsz):
                return praw + (rva - vaddr)
        return None

    def o2va(off):
        for vaddr, vsz, praw, rsz in secs:
            if praw <= off < praw + rsz:
                return base + vaddr + (off - praw)
        return None

    def cstr(va):
        fo = v2o(va)
        if fo is None:
            return None
        end = raw.find(b"\0", fo, fo + 200)
        s = raw[fo:end] if end != -1 else b""
        if not s or not all(32 <= c < 127 for c in s):
            return None
        return s.decode()

    targets = {}
    for n in names:
        needle = n.encode() + b"\0"
        pos = raw.find(needle)
        while pos != -1:
            va = o2va(pos)
            if va:
                targets.setdefault(va, n)
            pos = raw.find(needle, pos + 1)

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    for va in vas:
        print(f"\n[va {va:#x}]")
        for i, ins in enumerate(md.disasm(raw[v2o(va):v2o(va) + 0x400], va)):
            print(f"   {ins.address:#x}: {ins.mnemonic} {ins.op_str}")
            if ins.mnemonic == "ret" or i >= 4 * HEAD:
                break
    for off in range(0, len(raw) - 32, 8):
        nm = struct.unpack_from("<Q", raw, off)[0]
        if nm not in targets:
            continue
        fn = struct.unpack_from("<Q", raw, off + 8)[0]
        flags = struct.unpack_from("<i", raw, off + 16)[0]
        print(f"\n[{targets[nm]}] entry={hex(o2va(off) or 0)} fn={hex(fn)} flags={flags}")
        fo = v2o(fn)
        if fo is None:
            continue
        for i, ins in enumerate(md.disasm(raw[fo:fo + 0x200], fn)):
            print(f"   {ins.address:#x}: {ins.mnemonic} {ins.op_str}")
            if i >= HEAD:
                break
        seen = set()
        for ins in md.disasm(raw[fo:fo + 0x200], fn):
            if "rip" in ins.op_str and ins.mnemonic == "lea":
                tgt = ins.address + ins.size + int(ins.op_str.split("rip")[1].split("]")[0].replace(" ", ""), 0)
                s = cstr(tgt)
                if s is not None and tgt not in seen:
                    seen.add(tgt)
                    print(f"   str@{ins.address:#x} -> {tgt:#x} {s!r}")
            if ins.mnemonic == "ret":
                break


if __name__ == "__main__":
    main()
