#!/usr/bin/env python3
"""PY-5414 (#6015) の D の型の手がかりを PE から測る。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/py69_d_type_probe.py

- (1) [0x855878] の値 (D を作る引数) と、その値の先頭 qword・関数ポインタ表の長さ (.text 内を指す連続 qword 数)。
- (2) RIP 相対で 0x855878 / 0x855940 を指す命令を全 .text から列挙する (capstone の detail で解決)。
  0x855940 を `lea reg,[rip+..]` で取って `mov [reg],...` で格納する箇所があれば、vtable として構築されている手がかり。
- (3) 0x620e00 の周辺 (D の生成箇所) と 0x410320 (0x867710 の戻り値の経路) の逆アセンブル。
"""
import os
import struct

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
RAW = open(PE, "rb").read()
PEF = pefile.PE(data=RAW, fast_load=True)
BASE = PEF.OPTIONAL_HEADER.ImageBase
TEXT = [s for s in PEF.sections if s.Name.rstrip(b"\0") == b".text"][0]
TLO = BASE + TEXT.VirtualAddress
THI = TLO + TEXT.Misc_VirtualSize
MD = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
MD.detail = True
RIP = capstone.x86.X86_REG_RIP
X86_OP_MEM = capstone.x86.X86_OP_MEM
TARGETS = (0x855878, 0x855940)
CHUNK = 1 << 16


def fo(va):
    rva = va - BASE
    for s in PEF.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            off = rva - s.VirtualAddress
            return None if off >= s.SizeOfRawData else s.PointerToRawData + off
    raise SystemExit(f"VA {va:#x} が section 外")


def q(va):
    return struct.unpack_from("<Q", RAW, fo(va))[0]


def dis(start, count):
    off = fo(start)
    for ins in MD.disasm(RAW[off:off + count * 16], start, count):
        print(f"  {ins.address:x}: {ins.mnemonic} {ins.op_str}")


def main():
    v = q(0x855878)
    print(f"(1) [0x855878] = {v:#x}")
    print(f"    [{v:#x}] = {q(v):#x}")
    n = 0
    while TLO <= q(0x855940 + 8 * n) < THI:
        n += 1
    print(f"    0x855940 から .text を指す連続 qword: {n} 個")

    hits = {t: [] for t in TARGETS}
    off = TEXT.PointerToRawData
    tb = RAW[off:off + TEXT.SizeOfRawData]
    pos = 0
    while pos < len(tb):
        ins_list = list(MD.disasm(tb[pos:pos + CHUNK], TLO + pos, CHUNK))
        if not ins_list:
            pos += 1
            continue
        for ins in ins_list:
            for op in ins.operands:
                if op.type == X86_OP_MEM and op.mem.base == RIP:
                    t = ins.address + ins.size + op.mem.disp
                    if t in hits:
                        hits[t].append((ins.address, ins.mnemonic, ins.op_str))
        last = ins_list[-1]
        pos = last.address - TLO + last.size
        if pos >= len(tb) - 16:
            break
    for t in TARGETS:
        print(f"(2) RIP 相対で {t:#x} を指す命令: {len(hits[t])} 件")
        for a, m, s in hits[t][:12]:
            print(f"    {a:x}: {m} {s}")

    vcall = q(0x855940 - 0x30)
    print(f"(3) dl=1 のときの仮想呼出し先 [0x855940-0x30] = {vcall:#x} (0x410320 の call qword [rax-0x30])")
    dis(vcall, 6)
    print("(4) 0x620e00 周辺 (D の生成)")
    dis(0x620DF4, 4)
    print("    0x410320 (0x867710 の戻り値の経路)")
    dis(0x410320, 7)


if __name__ == "__main__":
    main()
