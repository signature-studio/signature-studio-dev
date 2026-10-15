#!/usr/bin/env python3
"""playlist の時間 ↔ block 変換・wall clock 参照・inc 系の排他 (PY-105 / #2908) の逆アセンブル事実を抽出する。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/playlist_time_facts.py

出力: (1) 0x1221b30 (liveTimeToBlockNum)・0x1221aa0 (liveBlockNumToTime) が読む global の slot と値
(2) 呼出し先の thunk が指す kernel32 の名前 (0x423550・0x4232e0・0x423980)
(3) 0x1221b30・0x1221aa0 の record 幅 (imul ..., 0xd = 13 dword) と ret 前の分岐の要点 (4) inc 系 4 件の CS 呼出し。
値は逆アセンブルの事実のみ。意味づけは REPORT_PY105.md を見ること。
"""
import os
import re
import struct

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
raw = open(PE, "rb").read()
pe = pefile.PE(data=raw, fast_load=True)
pe.parse_data_directories()
BASE = pe.OPTIONAL_HEADER.ImageBase
MD = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
IMPORTS = {f.address: (d.dll.decode(), f.name.decode() if f.name else f"ord{f.ordinal}")
           for d in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []) for f in d.imports}
TIME_FNS = {"liveTimeToBlockNum": 0x1221B30, "liveBlockNumToTime": 0x1221AA0}
THUNKS = {"0x423550": 0x423550, "0x4232e0": 0x4232E0, "0x423980": 0x423980}
INC_HELPERS = {"0x100b9c0": 0x100B9C0, "0x100ba20": 0x100BA20, "0x100ba70": 0x100BA70, "0x100bad0": 0x100BAD0}


def fo_of(va):
    rva = va - BASE
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            return s.PointerToRawData + (rva - s.VirtualAddress)
    return None


def sec_of(va):
    rva = va - BASE
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            return s.Name.rstrip(b"\0").decode()
    return "?"


def body(va, n):
    out = []
    for x in MD.disasm(raw[fo_of(va):fo_of(va) + n * 16], va):
        out.append(x)
        if x.mnemonic == "ret" or len(out) >= n:
            break
    return out


def rip_slot(x):
    m = re.search(r"\[rip ([+-]) (0x[0-9a-f]+)\]", x.op_str)
    if not m:
        return None
    return x.address + x.size + int(m.group(2), 16) * (1 if m.group(1) == "+" else -1)


def main():
    print("-- (1) 時間変換が読む global (slot → 指す先 → 値。.bss は実行時値で静的には未確定)")
    for name, va in TIME_FNS.items():
        for x in body(va, 90):
            slot = rip_slot(x)
            if slot is None or x.mnemonic not in ("mov", "cvtsi2sd"):
                continue
            ptr = struct.unpack_from("<Q", raw, fo_of(slot))[0]
            fo = fo_of(ptr) if 0x400000 <= ptr < 0x2000000 else None
            val = struct.unpack_from("<i", raw, fo)[0] if fo is not None and sec_of(ptr) == ".data" else None
            print(f"{name:20s} {x.address:#x} slot={slot:#x} ptr={ptr:#x}[{sec_of(ptr)}] file_dword={val}")
        recs = sorted({x.op_str.split(",")[-1].strip() for x in body(va, 90) if x.mnemonic == "imul" and "0xd" in x.op_str})
        print(f"{name:20s} record stride (dword) = {recs}")

    print("-- (2) 呼出し先 thunk の kernel32 名 (jmp [rip+X] の IAT 先)")
    for name, va in THUNKS.items():
        x = body(va, 1)[0]
        print(f"{name} {x.mnemonic} {x.op_str} -> {IMPORTS.get(rip_slot(x), '-')}")

    print("-- (3) 時間変換の分岐 (fallback の imul/idiv・比較の立つ位置)")
    for name, va in TIME_FNS.items():
        ins = body(va, 90)
        print(f"{name:20s} " + ", ".join(f"{x.mnemonic} {x.op_str}" for x in ins if x.mnemonic in ("idiv", "imul") and "rip" not in x.op_str)[:200])

    print("-- (4) inc 系 4 件の critical section 呼出し (先頭 Enter / ret 前 Leave の数)")
    for name, va in INC_HELPERS.items():
        ins = body(va, 40)
        enter = sum(1 for x in ins if x.mnemonic == "call" and x.op_str == "0x4232e0")
        leave = sum(1 for x in body(va, 60) if x.mnemonic == "call" and x.op_str == "0x423980")
        print(f"{name} enter={enter} leave={leave}")


if __name__ == "__main__":
    main()
