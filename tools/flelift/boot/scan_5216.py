#!/usr/bin/env python3
"""#5216 REPORT_APPENDIX_5216 §4 の静的解析の数字を PE の .text から再計算する (実機不要)。

  python3 tools/flelift/boot/scan_5216.py <block00031_PE.bin>

PE は fl-win64 の extracted/block00031_PE.bin。.text を線形に走査し、デコードできない
バイトは 1 byte 送って再同期する (capstone の disasm は不正バイトで止まるため)。
出力:
  direct  : 0x13e7628 を即値・rip 相対で指す命令数
  ptr     : 0x15e1890 を rip 相対・絶対で指す命令数 (読出し)
  ind60   : call qword ptr [reg+0x60] の数
  setter  : 0x15e1890 の読出しの直後 6 命令以内に byte ptr [...], 1 で書く箇所
"""
import sys

import capstone
import pefile

TARGET = 0x13E7628
PTR = 0x15E1890
RIP = capstone.x86.X86_REG_RIP
MEM = capstone.x86.X86_OP_MEM


def points_to(ins, addr):
    for op in ins.operands:
        if op.type != MEM:
            continue
        if op.mem.base == RIP and ins.address + ins.size + op.mem.disp == addr:
            return True
        if op.mem.base == 0 and op.mem.index == 0 and op.mem.disp == addr:
            return True
    return False


def main():
    path = sys.argv[1]
    pe = pefile.PE(path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    text = next(s for s in pe.sections if s.Name.startswith(b".text"))
    data = open(path, "rb").read()
    code = data[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]
    start = base + text.VirtualAddress
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True

    direct = ptr = ind60 = 0
    pending = []  # [描述, 読出しからの命令数]
    pos = 0
    while pos < len(code):
        r = list(md.disasm(code[pos:pos + 16], start + pos, 1))
        if not r:
            pos += 1
            continue
        ins = r[0]
        pos += ins.size
        term = ins.mnemonic in ("jmp", "call", "ret", "int3")

        if points_to(ins, TARGET) or f"0x{TARGET:x}" in ins.op_str:
            direct += 1
        if points_to(ins, PTR):
            ptr += 1
        if ins.mnemonic == "call" and "+ 0x60]" in ins.op_str:
            ind60 += 1

        still = []
        for desc, n in pending:
            if n >= 6 or term:
                continue
            if ins.mnemonic == "mov" and ins.op_str.startswith("byte ptr [") and ins.op_str.endswith(", 1"):
                print(f"setter  {desc}  ->  {ins.address:#x}: {ins.mnemonic} {ins.op_str}")
                continue
            still.append([desc, n + 1])
        pending = still
        if points_to(ins, PTR):
            pending.append([f"{ins.address:#x}: {ins.mnemonic} {ins.op_str}", 0])

    print(f"direct  {direct}")
    print(f"ptr     {ptr}")
    print(f"ind60   {ind60}")


if __name__ == "__main__":
    main()
