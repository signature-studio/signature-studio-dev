#!/usr/bin/env python3
"""PY-349 (#4616) の子 #5249: 固定 4 族の flags & 0x20 ガード内 store の右辺を PE から確定する。

  FL_WIN64_DIR=<展開先> python3 analysis/py349_flags20_rhs.py

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
各 assert は REPORT_PY235.md の PY-349 節の VA 1 件に対応する (失敗すると非 0 で終わる)。
"""
import os
import re
import struct
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
raw = open(PE, "rb").read()
pe = pefile.PE(data=raw, fast_load=True)
BASE = pe.OPTIONAL_HEADER.ImageBase
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)


def fo_of(va):
    rva = va - BASE
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            return s.PointerToRawData + (rva - s.VirtualAddress)
    sys.exit(f"VA {va:#x} が section 外")


def ins_at(va):
    return next(md.disasm(raw[fo_of(va):fo_of(va) + 16], va))


def text(va):
    i = ins_at(va)
    return f"{i.mnemonic} {i.op_str}".strip()


def nxt(va):
    return va + ins_at(va).size


def check(label, cond):
    print(("ok   " if cond else "FAIL ") + label)
    if not cond:
        sys.exit(1)


def rip_ea(va):
    """rip 相対の実効アドレス (命令の次の VA + disp)。"""
    m = re.search(r"\[rip \+ (0x[0-9a-f]+)\]", ins_at(va).op_str)
    return nxt(va) + int(m.group(1), 16)


CONST_VA = 0x104CCD8  # 2^-30
CALL_CVT = 0x40C660   # cvtsd2si rax, xmm0; ret

# 固定 4 族: (obj 取得の先頭 VA, 0x20 ガードの test VA, mulsd の VA, call VA, 5b8 store VA)
# 0x40000005 は guard の直後から obj 取得が始まる (entry の先頭は flags 読み込み)
FAMILIES = {
    "0x40000000": (0x104C2A6, 0x104C2C4, 0x104C2D3, 0x104C2FD, 0x104C311),
    "0x40000001": (0x104C4AF, 0x104C4CD, 0x104C4DC, 0x104C506, 0x104C51A),
    "0x40000002": (0x104C64F, 0x104C66D, 0x104C67C, 0x104C6A6, 0x104C6BA),
    "0x40000005": (0x104C926, 0x104C91F, 0x104C946, 0x104C970, 0x104C984),
}

check("0x40c660 は cvtsd2si rax, xmm0; ret",
      text(CALL_CVT) == "cvtsd2si rax, xmm0" and text(nxt(CALL_CVT)) == "ret")

const = struct.unpack("<d", raw[fo_of(CONST_VA):fo_of(CONST_VA) + 8])[0]
check(f"定数 {CONST_VA:#x} = 2^-30 (値 {const!r})", const == 2.0 ** -30)

for name, (chain, guard, mul, call, store) in FAMILIES.items():
    # obj 取得: rax = [rip+G]; rax = [rax]; rax = [rax+off]; [rbp+S] = rax
    check(f"{name}: {chain:#x} rax = [rip+G]", text(chain).startswith("mov rax, qword ptr [rip + "))
    G = rip_ea(chain)
    c2 = nxt(chain)
    check(f"{name}: {c2:#x} rax = [rax]", text(c2) == "mov rax, qword ptr [rax]")
    c3 = nxt(c2)
    m = re.fullmatch(r"mov rax, qword ptr \[rax \+ (0x[0-9a-f]+)\]", text(c3))
    check(f"{name}: {c3:#x} rax = [rax+off]", m is not None)
    off = int(m.group(1), 16)
    c4 = nxt(c3)
    m2 = re.fullmatch(r"mov qword ptr \[rbp \+ (0x[0-9a-f]+)\], rax", text(c4))
    check(f"{name}: {c4:#x} obj を [rbp+S] へ退避", m2 is not None)
    # ガード: test eax, 0x20 (flags は [rbp+0x5c0])
    check(f"{name}: {guard:#x} test eax, 0x20", text(guard) == "test eax, 0x20")
    check(f"{name}: {mul:#x} mulsd の定数 = {CONST_VA:#x}", rip_ea(mul) == CONST_VA)
    check(f"{name}: {call:#x} call 0x40c660", text(call) == f"call {CALL_CVT:#x}"
          or text(call) == "call 0x40c660")
    check(f"{name}: {store:#x} store [rbp+0x5b8] = ecx", text(store) == "mov dword ptr [rbp + 0x5b8], ecx")
    body = []
    a = guard
    while a <= store:
        body.append(text(a))
        a = nxt(a)
    check(f"{name}: 0x20 ブロック内に [obj+0x3bc]−[obj+0x3b8]・cvtsd2si・[obj+0x3b8]+eax",
          "sub eax, dword ptr [rcx + 0x3b8]" in body and "mov ecx, dword ptr [rcx + 0x3b8]" in body
          and "add ecx, eax" in body and "mov eax, dword ptr [rax + 0x3bc]" in body)
    print(f"     G={G:#x} off=obj+{off:#x} obj_slot=[rbp+{m2.group(1)}]")

print("summary: 0x20 ガード内 store (固定 4 族・同形):")
print("  v' = low32( obj.b8 + cvtsd2si( (double)(int32)v * 2^-30 * (double)(int32)(obj.bc - obj.b8) ) )")
print("  obj = *(*(*G) + off)。G・off は族ごと (REPORT_PY235.md の PY-349 節)。obj.b8 = [obj+0x3b8]・obj.bc = [obj+0x3bc]。")
