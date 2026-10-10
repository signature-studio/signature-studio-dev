#!/usr/bin/env python3
"""k80abi.py — kernel 80 実装の win64 slot 読みを機械語から抽出する (P0c-2 検証の入力)。

  python3 k80abi.py [OUT.json]   (既定: work/k80abi.json)

win64 slot 規約:
  slot1..4 = rcx / rdx / r8 / r9 (整数) または xmm0..xmm3 (浮動小数; 同一 slot の型は
  呼出側の宣言で決まる) — RetDec の define 引数順と同じ並び。
  slot5+   = stack ([rbp+K] / [rsp+K] の read-before-write)。

検出は read-before-write (RMW 命令 dec/add 等は read+write 両方に計上)。
xmm4..15 は callee-saved (win64) なので slot に数えない。
出力: {VA: {gpr_slots, xmm_slots, stack_args, floats}} — k80_argfix.py / kernel_diff の入力。
"""
import json
import os
import struct
import sys

import pefile
import capstone.x86 as x86
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_OP_REG

HERE = os.path.dirname(os.path.abspath(__file__))
PE = '/home/ubuntu/work/analysis/win64/extracted/block18983_PE.bin'

GPR = {}
for name, canon in [('RCX', 'rcx'), ('ECX', 'rcx'), ('CX', 'rcx'), ('CL', 'rcx'),
                    ('RDX', 'rdx'), ('EDX', 'rdx'), ('DX', 'rdx'), ('DL', 'rdx'),
                    ('R8', 'r8'), ('R8D', 'r8'), ('R8W', 'r8'), ('R8B', 'r8'),
                    ('R9', 'r9'), ('R9D', 'r9'), ('R9W', 'r9'), ('R9B', 'r9')]:
    GPR[getattr(x86, 'X86_REG_' + name)] = canon
COPYREG = {}
for _nm, _cn in [('RAX', 'rax'), ('RBX', 'rbx'), ('RSI', 'rsi'), ('RDI', 'rdi'),
                 ('R10', 'r10'), ('R11', 'r11'), ('R12', 'r12'), ('R13', 'r13'),
                 ('R14', 'r14'), ('R15', 'r15'), ('RBP', 'rbp')]:
    COPYREG[getattr(x86, 'X86_REG_' + _nm)] = _cn
COPYREG.update(GPR)
for _k in [k for k, v in COPYREG.items() if k in
           (x86.X86_REG_ECX, x86.X86_REG_CX, x86.X86_REG_CL, x86.X86_REG_EDX, x86.X86_REG_DX,
            x86.X86_REG_DL, x86.X86_REG_R8D, x86.X86_REG_R8W, x86.X86_REG_R8B,
            x86.X86_REG_R9D, x86.X86_REG_R9W, x86.X86_REG_R9B)]:
    del COPYREG[_k]
XMM = {}
for i in range(16):
    for suf in ['', 'D', 'Q', 'W', 'B', 'H']:
        try:
            XMM[getattr(x86, 'X86_REG_XMM%d%s' % (i, suf))] = 'xmm%d' % i
        except AttributeError:
            pass


def load_pe(path):
    pe = pefile.PE(data=open(path, 'rb').read(), fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    pd = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0].get_data()
    F = {}
    for k in range(len(pd) // 12):
        b, e, u = struct.unpack_from('<III', pd, 12 * k)
        if b and not u & 1:
            F[base + b] = base + e
    tva = [base + s.VirtualAddress for s in pe.sections if s.Name.rstrip(b'\0') == b'.text'][0]
    td = [s.get_data()[:s.Misc_VirtualSize] for s in pe.sections if s.Name.rstrip(b'\0') == b'.text'][0]
    return base, F, tva, td


def scan_function(MD, td, tva, va, fend):
    gpr_arg, xmm_arg = [], []
    gpr_deref = set()
    gpr_base = set()
    gpr_idx = set()
    gpr_w, xmm_w = set(), set()
    xmm_width = {}                                         # xmmN -> 32/64 (初回 read 命令から)
    stack_reads = []                                       # (entry_rsp 相対 offset, insn)
    sub_rsp = 0
    push_n = 0
    rbp_established = False
    frame_fixed = 0                                        # rbp = entry_rsp - frame_fixed (mov rbp,rsp 時点)
    for i in MD.disasm(td[va - tva:fend - tva], va):
        m = i.mnemonic
        if m == 'push':
            push_n += 1
            continue
        if m == 'pop':
            push_n -= 1
            continue
        if m == 'sub' and i.operands[0].type == X86_OP_REG and i.operands[0].reg == x86.X86_REG_RSP:
            sub_rsp += i.operands[1].imm
        if m == 'add' and i.operands[0].type == X86_OP_REG and i.operands[0].reg == x86.X86_REG_RSP:
            sub_rsp -= i.operands[1].imm
        if m == 'mov' and not rbp_established and len(i.operands) == 2 \
                and i.operands[0].type == X86_OP_REG and i.operands[0].reg == x86.X86_REG_RBP \
                and i.operands[1].type == X86_OP_REG and i.operands[1].reg == x86.X86_REG_RSP:
            rbp_established = True
            frame_fixed = 8 * push_n + sub_rsp
        reads, writes = [], []
        for o in i.operands:
            if o.type == X86_OP_REG:
                if o.access & 2:
                    writes.append(o.reg)
                if o.access & 1:
                    reads.append(o.reg)
            elif o.type == X86_OP_MEM:
                if o.mem.base != 0:
                    reads.append(o.mem.base)
                if o.mem.index != 0:
                    reads.append(o.mem.index)
                if o.mem.base in COPYREG:
                    gpr_deref.add(COPYREG[o.mem.base])
                    gpr_base.add(COPYREG[o.mem.base])
                if o.mem.index in COPYREG:
                    gpr_deref.add(COPYREG[o.mem.index])
                    if o.mem.base in COPYREG:
                        gpr_idx.add(COPYREG[o.mem.index])
                if (o.mem.base == x86.X86_REG_RBP and rbp_established) or o.mem.base == x86.X86_REG_RSP:
                    if o.access & 1:                       # mem が読み替数のときだけ arg 候補
                        rel = (o.mem.disp - frame_fixed) if o.mem.base == x86.X86_REG_RBP \
                            else (o.mem.disp - 8 * push_n - sub_rsp)
                        stack_reads.append((rel, i))
        for r in reads:
            if r in GPR and GPR[r] not in gpr_w and GPR[r] not in gpr_arg:
                gpr_arg.append(GPR[r])
        for r in writes:
            if r in GPR:
                gpr_w.add(GPR[r])
        for r in reads:
            if r in XMM:
                xn = XMM[r]
                if int(xn[3:]) < 4 and xn not in xmm_w and xn not in xmm_arg:
                    xmm_arg.append(xn)
                    xmm_width[xn] = 64 if (m.startswith('movq') or m.startswith('movsd')
                                           or m.startswith('movapd') or m.startswith('movupd')) else 32
        for r in writes:
            if r in XMM:
                xmm_w.add(XMM[r])
    # reg-reg copy (mov rA, rB) による base/idx/used 伝播 (copy 経由の deref を吸収)
    copies = []
    for i in MD.disasm(td[va - tva:fend - tva], va):
        if i.mnemonic == 'mov' and len(i.operands) == 2 and \
                i.operands[0].type == X86_OP_REG and i.operands[1].type == X86_OP_REG and \
                i.operands[0].reg in COPYREG and i.operands[1].reg in COPYREG:
            copies.append((COPYREG[i.operands[0].reg], COPYREG[i.operands[1].reg]))
    # copy 逆向き伝播 (mov dst, src で dst が base なら src の値も base として
    # 使われ得る — 顺方向は shr 等の変換を挟むため伝播しない)
    for _ in range(8):
        ch = False
        for dst, src in copies:
            if dst in gpr_base and src not in gpr_base:
                gpr_base.add(src)
                ch = True
            if dst in gpr_idx and src not in gpr_idx:
                gpr_idx.add(src)
                ch = True
        if not ch:
            break
    # stack args: entry_rsp 相対 offset ≥ 8 (retaddr の上) を read-before-write で
    seen = {}
    for off, ins in stack_reads:
        if off < 8:
            continue
        mn = ins.mnemonic
        isfp = (mn.startswith('fld') or mn.startswith('fild') or mn.endswith('ss') or mn.endswith('sd')) \
            and not mn.startswith('cvtsi')
        w = 32
        if isfp:
            if mn.endswith('sd') or mn.startswith('fld') and 'qword' in ins.op_str:
                w = 64
            op = ins.operands[0] if ins.operands else None
            if op is not None and getattr(op, 'size', 0) in (4, 8) and not mn.startswith('fld'):
                w = op.size * 8
        if off not in seen:
            seen[off] = (isfp, w, ins.mnemonic, ins.op_str)
    return gpr_arg, xmm_arg, sorted(gpr_deref), sorted(gpr_base), sorted(gpr_idx), xmm_width, seen


def main():
    outp = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'work', 'k80abi.json')
    cl = json.load(open(os.path.join(HERE, 'work', 'f80_classes.json')))
    vas = sorted(int(r['va'], 16) for r in cl['kernels'])
    base, F, tva, td = load_pe(PE)
    MD = Cs(CS_ARCH_X86, CS_MODE_64)
    MD.detail = True
    out = {}
    for va in vas:
        g, x, gd, gb, gx, xw, st = scan_function(MD, td, tva, va, F[va])
        out[hex(va)] = {'gpr_slots': g, 'gpr_base': gb, 'gpr_idx': gx, 'xmm_slots': x, 'xmm_width': xw,
                        'stack': [{'off': k, 'fp': v[0], 'width': v[1], 'insn': v[2]}
                                  for k, v in sorted(st.items())]}
    os.makedirs(os.path.dirname(outp), exist_ok=True)
    json.dump(out, open(outp, 'w'), indent=1)
    print('[k80abi] kernels=%d -> %s' % (len(out), outp))
    for va in ('0x5de3e0', '0x5de820', '0x5dfbe0', '0x5e03f0', '0x5dfa40'):
        a = out[va]
        print(' ', va, 'gpr=%s xmm=%s(w=%s) stack=%s' % (
            a['gpr_slots'], a['xmm_slots'], a['xmm_width'],
            [(x['off'], 'fp%d' % x['width'] if x['fp'] else 'i%d' % x['width']) for x in a['stack']]))


if __name__ == '__main__':
    main()
