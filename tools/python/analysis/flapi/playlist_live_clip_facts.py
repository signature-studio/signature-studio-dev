#!/usr/bin/env python3
"""triggerLiveClip のコア 0x1221bc0 の後半・refreshLiveClips・zone 系の事実を検算する (PY-104 / #2906)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/playlist_live_clip_facts.py

出力: 各項目の期待命令 (mnemonic・オペランド) と、RIP 相対で指す定数の実値。期待と違えば SystemExit。
意味づけは REPORT_PY104.md を見ること。
"""
import os
import struct

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
raw = open(PE, "rb").read()
pe = pefile.PE(data=raw, fast_load=True)
BASE = pe.OPTIONAL_HEADER.ImageBase
MD = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)


def fo_of(va):
    rva = va - BASE
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            return s.PointerToRawData + (rva - s.VirtualAddress)
    raise SystemExit(f"VA {va:#x} is outside sections")


def insn_at(va):
    for x in MD.disasm(raw[fo_of(va):fo_of(va) + 16], va):
        return x
    raise SystemExit(f"no insn at {va:#x}")


def expect(va, mnemonic, needle):
    x = insn_at(va)
    ok = x.mnemonic == mnemonic and needle in x.op_str
    print(f"{va:#x} {x.mnemonic} {x.op_str:<40} {'OK' if ok else 'NG'}")
    if not ok:
        raise SystemExit(f"expectation failed at {va:#x}")
    return x


def rip_target(va):
    x = insn_at(va)
    disp = int(x.op_str.split("rip + ")[1].split("]")[0], 16)
    return x.address + x.size + disp


def u8(va):
    return raw[fo_of(va)]


def f32(va):
    return struct.unpack("<f", raw[fo_of(va):fo_of(va) + 4])[0]


def main():
    print("## 1 velocity の mask (K の集合)")
    expect(0x1222265, "movzx", "byte ptr [rip + 0x913]")
    t = rip_target(0x1222265)
    print(f"  mask byte at {t:#x} = {u8(t):#04x} -> K set = {[k for k in range(8) if u8(t) >> k & 1]}")
    if u8(t) != 0x05:
        raise SystemExit("mask changed")
    expect(0x122225a, "ja", "0x1222274")

    print("## 2 flags の判定 (0x1221bc0 の前半)")
    expect(0x1221bfb, "and", "eax, 3")
    expect(0x1221c09, "test", "eax, 0x20")
    expect(0x1221c18, "and", "eax, 7")
    expect(0x1221c3e, "test", "eax, 0x30000")
    expect(0x1221c45, "mov", "0x1f3")
    expect(0x1221d21, "test", "eax, 1")
    expect(0x1221d47, "test", "eax, 2")
    expect(0x1222b49, "test", "eax, 0x40000000")
    expect(0x1222182, "movss", "xmm3")
    t = rip_target(0x1222182)
    print(f"  recursion velocity at {t:#x} = {f32(t)}")
    if f32(t) != -1.0:
        raise SystemExit("recursion velocity changed")

    print("## 3 refreshLiveClips (0x1222b90) = 0x1221bc0(-1, 0, 0x30000, -1.0f)")
    expect(0x1222b94, "or", "ecx, 0xffffffff")
    expect(0x1222b99, "mov", "r8d, 0x30000")
    expect(0x1222b9f, "movss", "xmm3, dword ptr [rip + 0xd]")
    t = rip_target(0x1222b9f)
    print(f"  velocity constant at {t:#x} = {f32(t)}")
    expect(0x1222ba7, "call", "0x1221bc0")

    print("## 4 S+0xa8 の mode 分岐 (0x100b890)")
    expect(0x100b89f, "cmp", "edx, 2")
    expect(0x100b8a2, "jge", "0x100b95a")
    expect(0x100b95a, "mov", "eax, edi")
    expect(0x100b8dd, "call", "0xe59e90")

    print("## 5 zone 系 (liveDisplayZone -> 0xd84f70 -> 0xfdc630)")
    expect(0xd84f74, "call", "0xfdc630")
    expect(0xfdc66b, "call", "qword ptr [rax + 0x80]")
    expect(0xfdc661, "mov", "rax, qword ptr [rax + 8]")
    expect(0xfdc685, "call", "0xe5abd0")
    expect(0xfdc68d, "call", "0x420b00")
    expect(0xfdc6a6, "mov", "dword ptr [rbx + 0x58], eax")
    expect(0xfdc6be, "call", "0x737020")
    expect(0x420b00, "mov", "eax, dword ptr [rcx + 8]")
    expect(0x737065, "cmp", "esi, 2")
    print("OK: all expectations hold")


if __name__ == "__main__":
    main()
