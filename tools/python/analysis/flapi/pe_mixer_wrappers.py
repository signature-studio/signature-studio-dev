#!/usr/bin/env python3
"""mixer PyMethodDef 配列 (72 行) の各入口 wrapper を逆アセンブルし、呼び先 (直接 call / jmp、間接 call の
呼び先スロット) と PyArg 書式 (RIP 相対 lea の文字列) を一覧する (PY-205 / #3493 の解析補助。方式は pe_disasm.py と同じ)。

- 関数は最初の ret で打ち切る (複数 ret の関数は最初の ret までしか読まない)。
- 間接 call は `call qword ptr [reg]` の reg を直前の `mov reg, qword ptr [rip+X]` に戻して、呼び先スロットの VA と
  .data の raw 値 (`bss` は実行時に埋まる) を表示する。`call qword ptr [rip+X]` は X を直接解決する。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_mixer_wrappers.py [名前 ...]
  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_mixer_wrappers.py --table
  (--table: 表順 0xd5eef0〜0xd614d0 の行を index・名前・VA と、provider/fl_engine.c の C 実装の有無 (済/未) で出す)
展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
"""
import os
import re
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

    def raw_qword(va):
        rva = va - base
        for v, vs, p, rs in secs:
            if v <= rva < v + rs:
                fo = p + (rva - v)
                return struct.unpack_from("<Q", raw, fo)[0] if fo + 8 <= len(raw) else None
        return None

    def cstr(va):
        fo = v2o(va)
        if fo is None:
            return None
        end = raw.find(b"\0", fo, fo + 200)
        s = raw[fo:end] if end != -1 else b""
        return s.decode() if s and all(32 <= c < 127 for c in s) else None

    def rip_target(ins):
        disp = int(ins.op_str.split("rip")[1].split("]")[0].replace(" ", ""), 0)
        return ins.address + ins.size + disp

    def slot_label(va):
        val = raw_qword(va)
        return f"[{va:#x}]=" + (f"{val:#x}" if val is not None else "bss")

    if "--table" in sys.argv[1:]:
        src_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../provider/fl_engine.c")
        src = open(src_path, encoding="utf-8").read()
        for i in range(MIXER_ROWS):
            nm, fn, _ = struct.unpack_from("<QQI", raw, MIXER_ARRAY_OFF + 32 * i)
            name = cstr(nm)
            if name is None or not (0xD5EEF0 <= fn <= 0xD614D0):
                continue
            done = "済" if f"FL_H(mixer, {name})" in src else "未"
            print(f"{i:3d} {name:32s} {fn:#x} C={done}")
        return
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    for i in range(MIXER_ROWS):
        off = MIXER_ARRAY_OFF + 32 * i
        nm, fn, flags = struct.unpack_from("<QQI", raw, off)
        name = cstr(nm)
        if name is None or (want and name not in want):
            continue
        fo = v2o(fn)
        calls, strs, regslot = [], [], {}
        for ins in md.disasm(raw[fo:fo + 0x400], fn):
            if ins.address - fn > 0x400 or len(calls) > 12:
                break
            if ins.mnemonic == "ret":
                break
            if ins.mnemonic == "mov" and "rip" in ins.op_str and ins.op_str.startswith("r"):
                regslot[ins.op_str.split(",")[0]] = rip_target(ins)
            if ins.mnemonic in ("call", "jmp"):
                reg = re.fullmatch(r"qword ptr \[(\w+)\]", ins.op_str)
                if ins.op_str.startswith("0x"):
                    calls.append(ins.op_str)
                elif "rip" in ins.op_str:
                    calls.append(f"ind {slot_label(rip_target(ins))}")
                elif reg and reg.group(1) in regslot:
                    calls.append(f"ind {reg.group(1)}->{slot_label(regslot[reg.group(1)])}")
                elif reg:
                    calls.append(f"ind {reg.group(1)}->?")
            if ins.mnemonic == "lea" and "rip" in ins.op_str:
                s = cstr(rip_target(ins))
                if s is not None:
                    strs.append(s)
        print(f"{name:32s} fn={fn:#x} flags={flags:#x} calls={calls[:6]} str={strs[:3]}")


if __name__ == "__main__":
    main()
