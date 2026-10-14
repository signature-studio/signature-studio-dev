#!/usr/bin/env python3
"""playlist.setTrackColor の格納 byte 順を逆アセンブルで確かめる (PY-113 / #2943 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/settrackcolor_facts.py

確認する事実 (いずれも block00031_PE.bin の逆アセンブル):
- PyMethodDef 配列 (playlist, ファイル offset 0x1114ac8) から setTrackColor の wrapper VA を得る。
- wrapper → コア 0xd55f30 (dispatch 0xd843d0 経由): value の R/B 入替え (and 0xff00ff・shl 0x10・shr 0x10) と or 0xff000000。
- コアは 0x12e60b0 → 0x12e5d80 で、[track + idx*0x114 + 0x2c] へ `r8d & 0xffffff` を格納する。
- getTrackColor 0xd55ea0 は同じ +0x2c を読み、R/B 入替え + or 0xff000000 を返す。
最後に、格納式と取得式の往復を 2 通りの算法 (ビット演算 / バイト列の並べ替え) で検算する。
"""
import os

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
PLAYLIST_ARRAY_OFF = 0x1114AC8
SETTER_WRAPPER = 0xD56040
CORE = 0xD55F30
STORE = 0x12E5D80
GETTER = 0xD55EA0


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
    return [f"{i.mnemonic} {i.op_str}".strip() for i in md.disasm(raw[fo:fo + n * 16], va)][:n]


def main():
    import struct

    raw, v2o = load()
    names = {}
    for i in range(42):
        off = PLAYLIST_ARRAY_OFF + 32 * i
        nm, fn, _fl, _doc = struct.unpack_from("<QQIxxxxQ", raw, off)
        o = v2o(nm)
        names[raw[o:raw.index(b"\0", o)].decode()] = fn
    print(f"setTrackColor wrapper: {hex(names['setTrackColor'])} (期待 {hex(SETTER_WRAPPER)})")
    assert names["setTrackColor"] == SETTER_WRAPPER and names["getTrackColor"] == GETTER
    core = disasm(raw, v2o, CORE, 45)
    store = disasm(raw, v2o, STORE, 12)
    getter = disasm(raw, v2o, GETTER, 40)
    checks = {
        "core: R/B 入替え (and 0xff00ff, shl 0x10, shr 0x10)": all(any(s.startswith(p) for s in core) for p in ("and edx, 0xff00ff", "shl r10d, 0x10", "shr edx, 0x10")),
        "core: or 0xff000000 後に 0x12e60b0 へ渡す": any(s == "or eax, 0xff000000" for s in core),
        "store 0x12e5d80: r8d & 0xffffff を [+0x2c] へ": any(s == "and eax, 0xffffff" for s in store) and any("0x2c], eax" in s for s in store),
        "getter: [+0x2c] を読み or 0xff000000": any("0x2c]" in s for s in getter) and any(s == "or eax, 0xff000000" for s in getter),
    }
    for k, ok in checks.items():
        print(("PASS " if ok else "FAIL ") + k)
    assert all(checks.values())

    def store_fl(v):
        return (((v & 0xFF) << 16) | (v & 0xFF00) | ((v >> 16) & 0xFF)) & 0xFFFFFF

    def get_fl(u):
        return (((u & 0xFF) << 16) | (u & 0xFF00) | ((u >> 16) & 0xFF) | 0xFF000000)

    def store_bytes(v):
        b = v.to_bytes(4, "big")
        return int.from_bytes(bytes([0, b[3], b[2], b[1]]), "big")

    for v in (0x123456, 0xABCDEF):
        s1, s2 = store_fl(v), store_bytes(v)
        print(f"input {v:#08x}: stored {s1:#08x} (bit算法) / {s2:#08x} (byte算法) get {get_fl(s1):#010x}")
        assert s1 == s2 and get_fl(s1) == 0xFF000000 | v


if __name__ == "__main__":
    main()
