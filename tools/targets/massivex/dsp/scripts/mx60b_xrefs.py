#!/usr/bin/env python3
"""MX-60 (#5498) 追補: 0x17a2ac0 / 0x17a4b0 / 0x17b460 の直接呼出元と、vptr 書込みの所在を数える。

mx60_callers.py の続き。受入 2 (rbx の動的型) のため、次を出す:
  1. 対象 RVA を直接 call/jmp (E8/E9) する関数 (呼出元の関数 RVA と命令 RVA)。
  2. 対象 vtable (0x1841836a8・0x183976038) のアドレスを RIP 相対で読む命令 (vptr 書込みの候補)。
  3. 対象 RVA を引数の即値として持つ mov/lea (関数ポインタの取得)。

usage: mx60b_xrefs.py <pe>
"""
import struct
import sys

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP

FUNCS = {0x17A2AC0: 'F_caller_of_P2', 0x17A4B0: 'F_vtbl_writer', 0x17B460: 'F_caller_of_scalar'}
VTABLES = {0x1841836A8: 'vt_IInstrument', 0x183976038: 'vt_other'}  # VA


def main(pe_path):
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
    funcs = sorted((base + struct.unpack_from('<II', data, ex_off + k * 12)[0],
                    base + struct.unpack_from('<II', data, ex_off + k * 12)[1]) for k in range(ex.Size // 12))
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    tgt_abs = {base + k: v for k, v in FUNCS.items()}
    vt_abs = dict(VTABLES)
    direct = {k: [] for k in tgt_abs}
    vt_ref = {k: [] for k in vt_abs}
    imm_ref = {k: [] for k in tgt_abs}
    for fs, fe in funcs:
        if not (t_lo <= fs < t_hi):
            continue
        for i in md.disasm(blob[fs - t_lo:fe - t_lo], fs):
            if i.mnemonic in ('call', 'jmp') and i.operands and i.operands[0].type == X86_OP_IMM:
                if i.operands[0].imm in direct:
                    direct[i.operands[0].imm].append((i.address - base, fs - base, i.mnemonic))
            for op in i.operands:
                if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
                    ea = i.address + i.size + op.mem.disp
                    if ea in vt_ref:
                        vt_ref[ea].append((i.address - base, fs - base, i.mnemonic))
                if op.type == X86_OP_IMM and op.imm in imm_ref:
                    imm_ref[op.imm].append((i.address - base, fs - base, i.mnemonic))
    print('== 直接 call/jmp (E8/E9) の呼出元 ==')
    for k in sorted(tgt_abs):
        print('  %#x (%s): %d 件' % (k - base, tgt_abs[k], len(direct[k])))
        for site, fn, mn in direct[k]:
            print('    %#x in fn %#x (%s)' % (site, fn, mn))
    print('== vtable 先頭の RIP 相対参照 (vptr 書込みの候補) ==')
    for k in sorted(vt_abs):
        print('  %#x (%s): %d 件' % (k - base, vt_abs[k], len(vt_ref[k])))
        for site, fn, mn in vt_ref[k]:
            print('    %#x in fn %#x (%s)' % (site, fn, mn))
    print('== 対象 VA の即値参照 (関数ポインタ) ==')
    for k in sorted(tgt_abs):
        print('  %#x (%s): %d 件' % (k - base, tgt_abs[k], len(imm_ref[k])))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
