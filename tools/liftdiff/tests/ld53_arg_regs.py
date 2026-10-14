#!/usr/bin/env python3
"""LD-53 (#1546): i128 投入形の判定材料。呼び先の本体と呼出し側の引数レジスタを数える。

  python3 tools/liftdiff/tests/ld53_arg_regs.py <PE>

callee: 各 VA から最初の ret までの命令 (分岐を追わない近似。691dd0 は ret が 1 本なので厳密) で、
  rcx / rdx / r8 / r9 / xmm0 を参照する命令数と、メモリ基底に使う命令数を数える。
caller: ld53_callers_linear.py と同じ線形走査で call rel32 の呼び先 (691dd0・653c80) を集め、直前 WINDOW 命令
  (制御転送で止める) 内で rcx / rdx / r8 / r9 を宛先に書く命令の有無を数える。
control: 計数の対照。合成命令 (mov rax, r9 / mov rax, [rdx+8]) で ref_r9・deref_rdx が 1 になることを確かめる。
判定 ((a) 2 レジスタ分解 / (b) ポインタ渡し) は人が REPORT_APPENDIX_LD53.md §7 で行う。
"""
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'liftdiff'))
import capstone  # noqa: E402
from ldlib import pe as P  # noqa: E402

CALLEES = [0x40c660, 0x40c750, 0x691dd0, 0x653c80]
CALLER_TARGETS = [0x691dd0, 0x653c80]
WINDOW = 12
CONTROLS = [
    ('mov rax, r9', b'\x4c\x89\xc8\xc3', 'ref_r9'),
    ('mov rax, [rdx+8]', b'\x48\x8b\x42\x08\xc3', 'deref_rdx'),
]
FAMILIES = {
    'rcx': ['rcx', 'ecx', 'cx', 'cl', 'ch'],
    'rdx': ['rdx', 'edx', 'dx', 'dl', 'dh'],
    'r8': ['r8', 'r8d', 'r8w', 'r8b'],
    'r9': ['r9', 'r9d', 'r9w', 'r9b'],
    'xmm0': ['xmm0'],
}


def mentions(ins, names):
    return any(re.search(r'\b%s\b' % n, ins.op_str) for n in names)


def writes(ins, names):
    """命令の先頭オペランド (宛先) が names のいずれかか。粗い判定。"""
    dst = ins.op_str.split(',')[0].strip().lower()
    return dst in names


def base_deref(ins, names):
    return bool(re.search(r'\[(%s)\b' % '|'.join(names), ins.op_str))


def load(pe_path):
    p = P.PE(pe_path)
    txt = [s for s in p.sections if s['name'] == '.text'][0]
    base = p.base + txt['rva']
    return txt['data'], base


def linear(md, data, base):
    insns = []
    off = 0
    while off < len(data):
        got = list(md.disasm(data[off:off + 16], base + off, 1))
        if got:
            insns.append(got[0])
            off += got[0].size
        else:
            off += 1
    return insns


def count_body(body):
    cnt = Counter()
    for ins in body:
        for reg, names in FAMILIES.items():
            if mentions(ins, names):
                cnt['ref_' + reg] += 1
        for reg in ('rdx', 'r8', 'r9', 'rcx'):
            if base_deref(ins, FAMILIES[reg]):
                cnt['deref_' + reg] += 1
    return cnt


def callee_report(md, data, base, va):
    off = va - base
    body = []
    for ins in md.disasm(data[off:off + 0x400], va):
        body.append(ins)
        if ins.mnemonic == 'ret':
            break
    cnt = count_body(body)
    print('callee %x: 本体命令 %d (先頭から最初の ret まで)' % (va, len(body)))
    print('  %s' % ', '.join('%s=%d' % (k, cnt[k]) for k in sorted(cnt)))


def control_report(md):
    for name, code, key in CONTROLS:
        cnt = count_body(list(md.disasm(code, 0)))
        print('control %s: %s=%d (期待 1)' % (name, key, cnt[key]))


def caller_report(insns, target):
    cnt = Counter()
    for i, ins in enumerate(insns):
        if ins.mnemonic != 'call' or len(ins.bytes) != 5 or ins.bytes[0] != 0xE8:
            continue
        tgt = ins.address + ins.size + int.from_bytes(ins.bytes[1:5], 'little', signed=True)
        if tgt != target:
            continue
        prev = []
        for x in reversed(insns[max(0, i - WINDOW):i]):
            if x.mnemonic in ('call', 'jmp', 'ret') or x.mnemonic.startswith('j'):
                break
            prev.append(x)
        cnt['call'] += 1
        for reg in ('rcx', 'rdx', 'r8', 'r9'):
            if any(writes(x, FAMILIES[reg]) for x in prev):
                cnt['write_' + reg] += 1
            else:
                cnt['nowrite_' + reg] += 1
    print('callers %x (線形走査の E8 一致, 窓 %d 命令): %s' % (
        target, WINDOW, ', '.join('%s=%d' % (k, cnt[k]) for k in sorted(cnt))))


def main():
    pe_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.environ.get('FL_WIN64_DIR', ''), 'extracted', 'block00031_PE.bin')
    data, base = load(pe_path)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = False
    print('# LD-53 引数レジスタの読み書き (PE=%s, .text VA=%x)' % (os.path.basename(pe_path), base))
    for va in CALLEES:
        callee_report(md, data, base, va)
    control_report(md)
    insns = linear(md, data, base)
    for target in CALLER_TARGETS:
        caller_report(insns, target)
    return 0


if __name__ == '__main__':
    sys.exit(main())
