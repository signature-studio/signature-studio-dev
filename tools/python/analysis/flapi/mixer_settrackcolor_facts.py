#!/usr/bin/env python3
"""mixer.setTrackColor / getTrackColor の格納式を逆アセンブルで確かめる (PY-115 / #2951 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/mixer_settrackcolor_facts.py

確認する事実 (いずれも block00031_PE.bin の逆アセンブル。根拠は REPORT_PY115.md §2):
- PyMethodDef 配列 (mixer, ファイル offset 0x1116ea8, 72 行) から setTrackColor (0xd5edd0)・getTrackColor (0xd5ec60) を得る。
- setter コア 0xd5ed20: value の R/B 入替え + or 0xff000000 を作り、track 要素 (base + index*0x28f*8) を rcx にして 0x12c17a0 を呼ぶ。
- 0x12c17a0: 要素の +0 (byte) をフラグ、+4 (dword) へ値を格納する。
- getter 0xd5ec60: 0x12c18f0 を呼び、戻り値を R/B 入替え + or 0xff000000 する。
- 0x12c18f0: フラグが立っていれば +4 の値をそのまま返す。無ければ既定色 (グローバル参照先の値) の R/B 入替えを返す。
既定色の参照先は実行時の値 (.bss) で静的に確定できないため、既定経路の値は本スクリプトでは検査しない (REPORT_PY115 §4)。
最後に、格納式と取得式の往復を検算する (set(0x123456) → get = 0xff123456)。
"""
import os
import struct

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
MIXER_ARRAY_OFF = 0x1116EA8
MIXER_ROWS = 72
SETTER_WRAPPER = 0xD5EDD0
SETTER_CORE = 0xD5ED20
GETTER = 0xD5EC60
STORE = 0x12C17A0
GET_CORE = 0x12C18F0


def load():
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

    return raw, v2o


def disasm(raw, v2o, va, n):
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    fo = v2o(va)
    return [f"{i.mnemonic} {i.op_str}".strip() for _, i in zip(range(n), md.disasm(raw[fo:fo + n * 16], va))]


def main():
    raw, v2o = load()
    names = {}
    for i in range(MIXER_ROWS):
        off = MIXER_ARRAY_OFF + 32 * i
        nm, fn, _fl, _doc = struct.unpack_from("<QQIxxxxQ", raw, off)
        o = v2o(nm)
        names[raw[o:raw.index(b"\0", o)].decode()] = fn
    print(f"setTrackColor wrapper: {names['setTrackColor']:#x} (期待 {SETTER_WRAPPER:#x})")
    print(f"getTrackColor: {names['getTrackColor']:#x} (期待 {GETTER:#x})")
    assert names["setTrackColor"] == SETTER_WRAPPER and names["getTrackColor"] == GETTER

    core = disasm(raw, v2o, SETTER_CORE, 60)
    store = disasm(raw, v2o, STORE, 12)
    getter = disasm(raw, v2o, GETTER, 40)
    get_core = disasm(raw, v2o, GET_CORE, 12)
    checks = {
        "setter core: R/B 入替え (and 0xff00ff・shl 0x10・shr 0x10) と or 0xff000000": all(
            any(s.startswith(p) for s in core) for p in ("and ecx, 0xff00ff", "shl r8d, 0x10", "shr ecx, 0x10")
        ) and any(s == "or eax, 0xff000000" for s in core),
        "setter core: 要素 = base + index*0x28f*8 (imul r8,r8,0x28f・lea rdx,[rdx+r8*8]) を rcx にして 0x12c17a0": any(s == "imul r8, r8, 0x28f" for s in core) and any(s == "lea rdx, [rdx + r8*8]" for s in core) and any(s == "call 0x12c17a0" for s in core),
        "store 0x12c17a0: 要素 +0 (byte) をフラグ、+4 (dword) へ値": any(s == "mov byte ptr [rcx], al" for s in store) and any(s == "mov dword ptr [rcx + 4], edx" for s in store),
        "getter: 要素 = base + index*0x28f*8 を rcx にして 0x12c18f0 を呼ぶ": any(s == "imul rcx, rcx, 0x28f" for s in getter) and any(s == "call 0x12c18f0" for s in getter),
        "getter: 戻り値の R/B 入替え + or 0xff000000": any(s == "or esi, 0xff000000" for s in getter) and any(s == "and ecx, 0xff00ff" for s in getter),
        "0x12c18f0: フラグ +0 を見て +4 を返す (フラグ立ち経路)": any(s == "cmp byte ptr [rcx], 0" for s in get_core) and any(s == "mov eax, dword ptr [rcx + 4]" for s in get_core),
    }
    for k, ok in checks.items():
        print(("PASS " if ok else "FAIL ") + k)
    assert all(checks.values())

    stride = 0x28F * 8
    print(f"track 要素の stride: {stride:#x} (= 0x28f*8)")
    print(f"既定色の参照先 (0x12c18fa の RIP 参照): {0x12C1901 + 0x321F57:#x} (.data 内の pointer。その先は実行時に決まる)")

    def store_fl(v):
        return ((((v & 0xFF) << 16) | (v & 0xFF00) | ((v >> 16) & 0xFF)) | 0xFF000000) & 0xFFFFFFFF

    def get_fl(u):
        return ((((u & 0xFF) << 16) | (u & 0xFF00) | ((u >> 16) & 0xFF)) | 0xFF000000) & 0xFFFFFFFF

    for v in (0x123456, 0xABCDEF):
        s = store_fl(v)
        print(f"input {v:#08x}: stored {s:#010x} get {get_fl(s):#010x}")
        assert get_fl(s) == 0xFF000000 | v


if __name__ == "__main__":
    main()
