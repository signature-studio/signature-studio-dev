#!/usr/bin/env python3
"""MX-60 (#5498) 追補: 0x17b460 が呼出元の xmm2 を読むかを CFG で判定する。

入口から、xmm2 を書く前に xmm2 を読む (または call で xmm2 が渡りうる) 経路が
あるかを調べる。ある → 呼出元の xmm2 (float 引数) が使われうる。
無い → 呼出元が xmm2 に float を載せる必要は無い (受入 1 の判定)。

間接 jmp・関数外への jmp は保守的に「読む」扱いにする。
call は引数の読みを capstone の regs_read が表さないため、xmm2 を書く前に到達する call は
保守的に「読む」扱いにする (呼出先の解析は行わない)。

usage: mx60d_entry_xmm2.py <pe> [entry_rva_hex]
"""
import struct
import sys

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_REG_XMM2 as XMM2


def main(pe_path, entry_rva):
    pe = pefile.PE(pe_path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = open(pe_path, 'rb').read()
    text = [s for s in pe.sections if s.Characteristics & 0x20000000][0]
    t_lo = base + text.VirtualAddress
    t_hi = t_lo + text.Misc_VirtualSize
    blob = data[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]
    ex = pe.OPTIONAL_HEADER.DATA_DIRECTORY[3]
    ex_sec = [s for s in pe.sections if s.VirtualAddress <= ex.VirtualAddress < s.VirtualAddress + s.Misc_VirtualSize][0]
    ex_off = ex.VirtualAddress - ex_sec.VirtualAddress + ex_sec.PointerToRawData
    funcs = {}
    for k in range(ex.Size // 12):
        b, e = struct.unpack_from('<II', data, ex_off + k * 12)[:2]
        funcs[base + b] = base + e
    a_in = base + entry_rva
    cand = [b for b, e in funcs.items() if b <= a_in < e]
    if not cand:
        print('entry %#x is not inside a pdata function' % a_in)
        return 1
    fs = max(cand)
    fe = funcs[fs]
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    code = blob[fs - t_lo:fe - t_lo]
    ins = {i.address: i for i in md.disasm(code, fs)}
    order = sorted(ins)
    print('== 0x%x (関数先頭 %#x): %d 命令 (%#x-%#x) ==' % (entry_rva, fs - base, len(order), fs - base, fe - base))

    reads_before_def = []
    seen = set()
    stack = [fs]
    unknown = []
    while stack:
        a = stack.pop()
        if a in seen or a not in ins:
            if a not in ins and a not in seen and fs <= a < fe:
                unknown.append(a)
            continue
        seen.add(a)
        i = ins[a]
        rd = XMM2 in i.regs_read or i.mnemonic == 'call'
        wr = XMM2 in i.regs_write and i.mnemonic != 'call'
        if rd:
            reads_before_def.append(i)
        if wr and not rd:
            continue  # この経路では xmm2 は呼出元の値を失う
        if i.mnemonic.startswith('ret') or i.mnemonic == 'int3':
            continue
        nxt = a + i.size
        if i.mnemonic == 'jmp':
            if i.operands and i.operands[0].type == X86_OP_IMM:
                t = i.operands[0].imm
                if fs <= t < fe:
                    stack.append(t)
                else:
                    unknown.append(a)
            else:
                unknown.append(a)
            continue
        if i.mnemonic.startswith('j'):
            if i.operands and i.operands[0].type == X86_OP_IMM:
                t = i.operands[0].imm
                if fs <= t < fe:
                    stack.append(t)
                else:
                    unknown.append(a)
            else:
                unknown.append(a)
        stack.append(nxt)

    print('== 入口から xmm2 を読みうる (または call で渡りうる) 命令: %d 件 ==' % len(reads_before_def))
    for i in sorted(reads_before_def, key=lambda x: x.address):
        print('   %#x  %s %s' % (i.address - base, i.mnemonic, i.op_str))
    print('== 制御が解析できない箇所: %d 件 ==' % len(unknown))
    for a in unknown:
        print('   %#x' % (a - base))
    verdict = 'xmm2 を読む経路あり (呼出元の float 引数が使われうる)' if reads_before_def else \
        'xmm2 を読む経路なし (呼出元の xmm2 は使われない)'
    print('== 判定: %s ==' % verdict)
    return 0


if __name__ == '__main__':
    rva = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x17B460
    sys.exit(main(sys.argv[1], rva))
