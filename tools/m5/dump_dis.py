#!/usr/bin/env python3
# M5 (a) 素材確認用: VA の関数を capstone で人間可読 dump する (jump target と
# rip-relative 参照先も解決)。loop の帰属確認・挙動理解に使用。
#
#   python3 dump_dis.py work/FLEngine_x64.dll 0x867480 [--len 0x100]

import argparse
import sys
import capstone


def _secs(data):
    import struct
    pe_off, = struct.unpack("<I", data[0x3C:0x40])
    opt_off = pe_off + 24
    nsec, = struct.unpack("<H", data[pe_off + 6:pe_off + 8])
    optsz, = struct.unpack("<H", data[pe_off + 20:pe_off + 22])
    sec_off = opt_off + optsz
    out = []
    for i in range(nsec):
        e = sec_off + i * 40
        name = data[e:e + 8].split(b"\0")[0].decode("latin1")
        vsize, vaddr, raw_size, raw_ptr = struct.unpack("<IIII", data[e + 8:e + 24])
        out.append((name, vsize, vaddr, raw_size, raw_ptr))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("binfile")
    ap.add_argument("va")
    ap.add_argument("--len", default="0x200")
    ap.add_argument("--base", default="0x400000")
    args = ap.parse_args()

    data = open(args.binfile, "rb").read()
    secs = _secs(data)
    va = int(args.va, 0)
    base = int(args.base, 0)
    rva = va - base
    fo = None
    for (name, vsize, vaddr, raw_size, raw_ptr) in secs:
        if raw_size and vaddr <= rva < vaddr + vsize:
            off = rva - vaddr
            if off < raw_size:
                fo = raw_ptr + off
                break
    if fo is None:
        print(f"[dump_dis] FAIL: VA {hex(va)} (rva {hex(rva)}) がセクションにありません",
              file=sys.stderr)
        return 1
    length = min(int(args.len, 0), len(data) - fo)
    code = data[fo:fo + length]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    # 先に jump target を集めてラベル化する
    targets = set()
    for ins in md.disasm(code, va):
        if ins.group(capstone.CS_GRP_JUMP) or ins.group(capstone.CS_GRP_CALL):
            if ins.operands and ins.operands[0].type == capstone.x86.X86_OP_IMM:
                targets.add(ins.operands[0].imm)
        if ins.mnemonic == "ret":
            break
    md2 = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md2.detail = True
    for ins in md2.disasm(code, va):
        tpart = f"L_{ins.address + ins.size & 0xffffffff:x}" if ins.address + ins.size + 1 else ""
        lbl = f"L_{ins.operands[0].imm & 0xffffffff:08x}:" \
            if (ins.group(capstone.CS_GRP_JUMP) or ins.group(capstone.CS_GRP_CALL)) \
            and ins.operands and ins.operands[0].type == capstone.x86.X86_OP_IMM \
            else ""
        detail = ""
        for o in ins.operands:
            if o.type == capstone.x86.X86_OP_MEM and o.mem.base == capstone.x86.X86_REG_RIP:
                # rip 相対: 次の命令のアドレス基準
                tgt = ins.address + ins.size + o.mem.disp
                detail = f"  ; → VA 0x{tgt:x} (rva 0x{tgt - base:x})"
            elif o.type == capstone.x86.X86_OP_IMM and abs(o.imm) > 0xFFFF:
                detail = f"  ; imm=0x{o.imm & 0xffffffff:x}"
        jt = f"jmp {hex(ins.operands[0].imm)}" if lbl else ""
        print(f"  {ins.address - va:04x}  {lbl:<14} {ins.mnemonic} {ins.op_str}:{detail}")
        if ins.mnemonic == "ret":
            break


if __name__ == "__main__":
    sys.exit(main())
