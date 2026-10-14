#!/usr/bin/env python3
"""殻 (block 23663) の DispatchToEngine 呼出し (call [reg+0x1c0]) を機械抽出する (REPORT_ENGINE_LINK.md §2a・§4 の再計算)。

各呼出しについて、第 1 引数 rcx と selector rdx を、呼出し直前の直線区間で後ろ向きに追う。
rcx が [X+0x1b8] (engine) から来るものを engine 呼出しとして数える。
selector は `mov edx, imm` (`xor edx, edx` は 0) を直接取り、`mov edx, r9d` 等の register 転送は 1 段だけ辿る。
直線区間は call / jmp / ret / jcc で打ち切る (打ち切りは状態 `branch` として出す)。

usage: dispatch_calls.py <PE.bin> [--expect=<golden>]
  --expect=<golden> は `0xVA:sel,...` の列 (REPORT §4 の 9 件)。 導出結果と完全一致しなければ exit 1。
"""
import re
import sys

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_OP_REG, CS_OP_IMM

PATTERN = re.compile(rb'\xff[\x90-\x97]\xc0\x01\x00\x00|\xff\x94\x24\xc0\x01\x00\x00')
NO_WRITE = {'cmp', 'test', 'push', 'bt', 'ucomisd', 'ucomiss', 'comisd', 'comiss', 'jmp', 'call', 'ret'}
FAMILY = {}
for fam, names in {
    'rax': 'rax eax ax al ah', 'rcx': 'rcx ecx cx cl ch', 'rdx': 'rdx edx dx dl dh',
    'rbx': 'rbx ebx bx bl bh', 'rsi': 'rsi esi si sil', 'rdi': 'rdi edi di dil',
    'rbp': 'rbp ebp bp bpl', 'rsp': 'rsp esp sp spl',
    'r8': 'r8 r8d r8w r8b', 'r9': 'r9 r9d r9w r9b', 'r10': 'r10 r10d r10w r10b',
    'r11': 'r11 r11d r11w r11b', 'r12': 'r12 r12d r12w r12b', 'r13': 'r13 r13d r13w r13b',
    'r14': 'r14 r14d r14w r14b', 'r15': 'r15 r15d r15w r15b',
}.items():
    for n in names.split():
        FAMILY[n] = fam


def load_text(path):
    pe = pefile.PE(path)
    base = pe.OPTIONAL_HEADER.ImageBase
    sec = next(s for s in pe.sections if s.Name.rstrip(b'\0') == b'.text')
    funcs = sorted(
        (base + e.struct.BeginAddress, base + e.struct.EndAddress)
        for e in pe.DIRECTORY_ENTRY_EXCEPTION
    )
    return sec.get_data(), base + sec.VirtualAddress, funcs


def function_of(funcs, va):
    for lo, hi in funcs:
        if lo <= va < hi:
            return lo, hi
    return None


def decode(md, data, lo, start, end):
    return list(md.disasm(data[start - lo:end - lo], start))


def writes(ins):
    """命令が書く register family (op0 が register のもの)。 xor r,r は 0 を書く。"""
    if ins.mnemonic in NO_WRITE or not ins.operands or ins.operands[0].type != CS_OP_REG:
        return None
    return FAMILY.get(ins.reg_name(ins.operands[0].reg))


def def_of(insns, idx, fam, depth=0):
    """insns[idx] より前で fam を最後に書いた命令を探す。 (命令, 即値 or None, 打ち切り理由)。"""
    for j in range(idx - 1, -1, -1):
        ins = insns[j]
        if ins.mnemonic in ('call', 'ret', 'jmp') or ins.mnemonic.startswith('j'):
            return ins, None, 'branch'
        if writes(ins) != fam:
            continue
        ops = ins.operands
        if ins.mnemonic == 'xor' and len(ops) == 2 and ops[1].type == CS_OP_REG and ins.reg_name(ops[0].reg) == ins.reg_name(ops[1].reg):
            return ins, 0, 'imm'
        if ins.mnemonic == 'mov' and len(ops) == 2 and ops[1].type == CS_OP_IMM:
            return ins, ops[1].imm & 0xffffffff, 'imm'
        if ins.mnemonic in ('mov', 'movsxd', 'movzx') and len(ops) == 2 and ops[1].type == CS_OP_REG and depth < 2:
            src = FAMILY.get(ins.reg_name(ops[1].reg))
            if src:
                d, v, why = def_of(insns, j, src, depth + 1)
                return ins, v, why
        return ins, None, 'other'
    return None, None, 'start'


def scan(path):
    data, lo, funcs = load_text(path)
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    rows = []
    for m in PATTERN.finditer(data):
        end_va = lo + m.end()
        ff = lo + m.start()
        site = None
        for st in (m.start() - 1, m.start()):
            ins = decode(md, data, lo, lo + st, lo + st + 12)
            if ins and ins[0].mnemonic == 'call' and '0x1c0]' in ins[0].op_str and ins[0].address + ins[0].size == end_va:
                site = ins[0].address
                break
        if site is None:
            continue
        fn = function_of(funcs, site)
        if fn is None:
            rows.append((ff, None, None, None, 'nofunc'))
            continue
        insns = decode(md, data, lo, fn[0], site)
        call_idx = len(insns)
        rcx = def_of(insns, call_idx, 'rcx')
        rdx = def_of(insns, call_idx, 'rdx')
        engine = bool(rcx[0] and '0x1b8]' in rcx[0].op_str)
        rows.append((ff, fn[0], rcx, rdx, 'engine' if engine else 'other'))
    return rows


def fmt(ins):
    return f'{ins.mnemonic} {ins.op_str}' if ins else '-'


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    expect = None
    for a in sys.argv[1:]:
        if a.startswith('--expect='):
            expect = dict((int(k, 16), int(v)) for k, v in (p.split(':') for p in a[len('--expect='):].split(',')))
    rows = scan(args[0])
    engine = [r for r in rows if r[4] == 'engine']
    print(f'call sites [reg+0x1c0]: {len(rows)}  engine (rcx=[X+0x1b8]): {len(engine)}')
    print('| 呼出し | 関数 | rcx の由来 | selector (rdx) |')
    print('|--|--|--|--|')
    got = {}
    for site, f, rcx, rdx, kind in rows:
        if kind != 'engine':
            print(f'| {site:#x} | {f:#x} | {kind} | - |' if f else f'| {site:#x} | - | {kind} | - |')
            continue
        sel = rdx[1] if rdx else None
        got[site] = sel
        print(f'| {site:#x} | {f:#x} | {fmt(rcx[0])} | {sel if sel is not None else "未確定 (" + str(rdx[2]) + ")"} |')
    if expect is None:
        return 0
    ok = got == expect and all(v is not None for v in got.values())
    print(f'expect: {"PASS" if ok else "FAIL"} ({len(got)} sites vs {len(expect)} expected)')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
