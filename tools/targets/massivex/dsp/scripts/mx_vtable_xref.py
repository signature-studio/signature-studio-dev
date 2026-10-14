#!/usr/bin/env python3
# MX-3b U1: 指定 VA (vtable 先頭) を RIP 相対 disp32 で参照する命令を .text 全体から集める。
# 線形逆アセンブルは途中で止まる (データ・未対応命令) ため使わない。代わりに
# disp32 の 4 バイトを全位置で照合し、その直前 15 バイトから復号した命令のうち
# 末尾が disp32 の直後 (後続 imm 0/1/2/4/8 B) に一致し rip 参照を持つものを採る。
# usage: mx_vtable_xref.py <pe> <target_va_hex> [<target_va_hex> ...]
import sys, struct
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64


def main():
    pe = pefile.PE(sys.argv[1], fast_load=True)
    targets = [int(t, 16) for t in sys.argv[2:]]
    IB = pe.OPTIONAL_HEADER.ImageBase
    data = pe.get_memory_mapped_image()
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    text = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.text'][0]
    code = data[text.VirtualAddress:text.VirtualAddress + text.Misc_VirtualSize]
    ip_base = IB + text.VirtualAddress
    for tva in targets:
        found = set()
        for p in range(len(code) - 4):
            disp = struct.unpack_from('<i', code, p)[0]
            for imm in (0, 1, 2, 4, 8):
                if ip_base + p + 4 + imm + disp != tva:
                    continue
                end = p + 4 + imm
                for s in range(max(0, p - 15), p):
                    ins = next(md.disasm(code[s:s + 16], ip_base + s, 1), None)
                    if ins is None or s + ins.size != end:
                        continue
                    if any(op.type == 3 and op.mem.base != 0 and md.reg_name(op.mem.base) == 'rip'
                           for op in ins.operands):
                        found.add((ins.address, ins.mnemonic, ins.op_str))
                    break
        for a, m, o in sorted(found):
            print('0x%x %s %s -> 0x%x' % (a, m, o, tva))
        print('# target 0x%x: %d refs' % (tva, len(found)))


if __name__ == '__main__':
    main()
