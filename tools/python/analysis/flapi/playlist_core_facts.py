#!/usr/bin/env python3
"""playlist 操作コア・helper の作用 (PY-91 / #2809) の逆アセンブル事実を抽出する (PY-61 の続き)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/playlist_core_facts.py

出力: (1) 操作系コアの呼び出し先と status 書込み (2) inc 系 helper の更新式 (3) getLive 系の状態表
(4) 書式文字列 (5) mode 分岐の呼び出し先。値は逆アセンブルの事実のみ。意味づけは REPORT_PY91.md を見ること。
"""
import os
import re
import struct

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
raw = open(PE, "rb").read()
pe = pefile.PE(data=raw, fast_load=True)
BASE = pe.OPTIONAL_HEADER.ImageBase
MD = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

CORES = {
    "lockDisplayZone": 0xD56FC0, "liveDisplayZone": 0xD57150, "triggerLiveClip": 0xD577E0,
    "refreshLiveClips": 0xD579D0, "incLivePosSnap": 0xD57AF0, "incLiveTrigSnap": 0xD57C70,
    "incLiveLoopMode": 0xD57DF0, "incLiveTrigMode": 0xD57F70,
}
INC_HELPERS = {"0x100b9c0": 0x100B9C0, "0x100ba20": 0x100BA20, "0x100ba70": 0x100BA70, "0x100bad0": 0x100BAD0}
MODE_WRAPPERS = {"getLiveBlockStatus": 0xD57550, "getLiveStatus": 0xD57670}
FORMATS = {"getLiveBlockStatus": 0xD57660, "getLiveStatus": 0xD57738, "liveDisplayZone": 0xD57364,
           "soloTrack": 0xD56984, "triggerLiveClip": 0xD579C4, "getLiveBlockColor": 0xD577D8}


def fo_of(va):
    rva = va - BASE
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            return s.PointerToRawData + (rva - s.VirtualAddress)
    raise SystemExit(f"VA {va:#x} is outside sections")


def cstr(va):
    fo = fo_of(va)
    return raw[fo:raw.find(b"\0", fo, fo + 300)].decode("latin1")


def body(va, n=120):
    out = []
    for x in MD.disasm(raw[fo_of(va):fo_of(va) + n * 16], va):
        out.append(x)
        if x.mnemonic == "ret" or (x.mnemonic == "int3" and out and out[-2].mnemonic == "ret"):
            break
        if len(out) >= n:
            break
    return out


def rip_target(x):
    m = re.search(r"\[rip ([+-]) (0x[0-9a-f]+)\]", x.op_str)
    if not m:
        return None
    d = int(m.group(2), 16) * (1 if m.group(1) == "+" else -1)
    return x.address + x.size + d


def dword_at(va, i=0):
    return struct.unpack_from("<i", raw, fo_of(va) + 4 * i)[0]


def main():
    print("-- (1) 操作系コア: call 先と status 書込み")
    for name, va in CORES.items():
        calls = [x.op_str for x in body(va) if x.mnemonic == "call"]
        stats = [x.op_str for x in body(va) if x.mnemonic == "mov" and x.op_str.startswith("qword ptr [rbx + 0x60]")]
        print(f"{name:18s} {va:#x} calls={calls} status={stats}")

    print("-- (2) inc 系 helper: 更新するフィールド (S = track+0x24 の elem+X) と法")
    for hname, va in INC_HELPERS.items():
        ins = body(va)
        field = next(re.search(r"\[rbx \+ (0x[0-9a-f]+)\]", x.op_str).group(1)
                     for x in ins if re.search(r"\[rbx \+ (0x[0-9a-f]+)\]", x.op_str) and x.mnemonic == "mov")
        mask = any(x.op_str.startswith("eax, 0x80000003") for x in ins)
        mods = sorted({x.op_str.split(",")[1].strip() for x in ins
                       if x.mnemonic == "add" and x.op_str.split(",")[1].strip() in ("7", "4", "0x4")})
        print(f"{hname} S+{field} -> elem+{hex(int(field, 16) + 0x24)} mod4_mask={mask} add={mods}")

    print("-- (3) getLive 系の状態表 (lea で指す 8 個の dword) と参照するフィールド")
    for hname, va in (("0x100bf10 tbl1", 0x100BF10), ("0x100bfa0 tbl2", 0x100BFA0), ("0x100c130 tbl3", 0x100C130)):
        lea = next(x for x in body(va) if x.mnemonic == "lea" and rip_target(x))
        t = rip_target(lea)
        print(f"{hname} table={t:#x} {[dword_at(t, i) for i in range(8)]}")
    for hname, va in (("0x100beb0", 0x100BEB0), ("0x100c0f0", 0x100C0F0)):
        fields = sorted({re.search(r"\+ (0x[0-9a-f]+)\]", x.op_str).group(1)
                         for x in body(va) if re.search(r"\+ (0x[0-9a-f]+)\]", x.op_str)})
        print(f"{hname} reads={fields}")

    print("-- (4) 書式文字列 (lea r8 / rdx の指す文字列)")
    for name, va in FORMATS.items():
        print(f"{name:18s} {va:#x} {cstr(va)!r}")

    print("-- (5) mode 分岐の呼び出し先 (wrapper 内の call と -4 合流先)")
    for name, va in MODE_WRAPPERS.items():
        calls = [x.op_str for x in body(va, 80) if x.mnemonic == "call" and x.op_str.startswith("0x")]
        print(f"{name:18s} {va:#x} direct_calls={calls}")
    x = next(i for i in body(0xD5764A, 2) if i.mnemonic == "mov")
    print(f"-4 sink 0xd5764a: {x.op_str}")


if __name__ == "__main__":
    main()
