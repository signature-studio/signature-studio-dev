#!/usr/bin/env python3
"""mixer PyMethodDef 配列 (72 行) の各入口 wrapper を逆アセンブルし、呼び先 (call / jmp) と
PyArg 書式 (RIP 相対 lea の文字列) を一覧する (PY-205 / #3493 の解析補助。方式は pe_disasm.py と同じ)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_mixer_wrappers.py [名前 ...]

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
"""
import os
import struct
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
MIXER_ARRAY_OFF = 0x1116EA8
MIXER_ROWS = 72
SCAN = 40


def main():
    want = set(sys.argv[1:])
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
        fo = v2o(va)
        if fo is None:
            return None
        end = raw.find(b"\0", fo, fo + 200)
        s = raw[fo:end] if end != -1 else b""
        return s.decode() if s and all(32 <= c < 127 for c in s) else None

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    for i in range(MIXER_ROWS):
        off = MIXER_ARRAY_OFF + 32 * i
        nm, fn, flags = struct.unpack_from("<QQI", raw, off)
        name = cstr(nm)
        if name is None or (want and name not in want):
            continue
        fo = v2o(fn)
        calls, strs = [], []
        for ins in md.disasm(raw[fo:fo + 0x400], fn):
            if ins.address - fn > 0x400 or len(calls) > 12:
                break
            if ins.mnemonic in ("call", "jmp") and ins.op_str.startswith("0x"):
                calls.append(ins.op_str)
            if ins.mnemonic == "lea" and "rip" in ins.op_str:
                tgt = ins.address + ins.size + int(ins.op_str.split("rip")[1].split("]")[0].replace(" ", ""), 0)
                s = cstr(tgt)
                if s is not None:
                    strs.append(s)
            if ins.mnemonic == "ret" and len(calls) > 0:
                break
        print(f"{name:32s} fn={fn:#x} flags={flags:#x} calls={calls[:6]} str={strs[:3]}")


if __name__ == "__main__":
    main()
