#!/usr/bin/env python3
"""crash_class.py の独立検算 (T-SH-89 / #3588)。落ちた命令を capstone で逆アセンブルし、メモリオペランドの実効アドレスを
fault 時のレジスタから再計算して、si_addr と一致するかを全 case で確かめる。crash_class.py は RIP の定数と分類規則を使い、
本スクリプトは命令のオペランドだけを使う (別アルゴリズム)。
- 実効アドレス (ea) = base + index*scale + disp (rip 相対は次命令の番地を基準)。
- si_addr は ea が canonical なら ea、非 canonical なら 0 (CPU の GP 例外が SIGSEGV として報告する値)。
usage: crash_insn.py WORKDIR   (WORKDIR に image_native.bin と native_stderr.txt がある)
"""
import re, sys, collections
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

W = sys.argv[1]
BASE = 0x30000000
img = open(W + '/image_native.bin', 'rb').read()
md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = True
M64 = (1 << 64) - 1
pat = re.compile(r'\[native\] crash case=(\d+) fn=(\d+) sig=(\S+)(?: addr=0x([0-9a-f]+) rip=0x([0-9a-f]+)((?: \w+=0x[0-9a-f]+)*))?$')


def canonical(x):
    return x < (1 << 47) or x >= (M64 + 1 - (1 << 47))


ok = bad = skipped = 0
insn_cnt = collections.Counter()
for line in open(W + '/native_stderr.txt'):
    m = pat.search(line.strip())
    if not m:
        continue
    if m.group(5) is None:
        skipped += 1
        continue
    addr = int(m.group(4), 16)
    rip = int(m.group(5), 16)
    regs = {k: int(v, 16) for k, v in re.findall(r'(\w+)=0x([0-9a-f]+)', m.group(6) or '')}
    rva = rip - BASE
    ins = next(md.disasm(img[rva:rva + 16], rip))
    mem = [o.mem for o in ins.operands if o.type == 3]   # X86_OP_MEM
    insn_cnt['%x %s %s' % (rip, ins.mnemonic, ins.op_str)] += 1
    if not mem:
        bad += 1
        print('no memory operand at', hex(rip), ins.mnemonic, ins.op_str)
        continue
    mo = mem[0]
    rn = lambda r: md.reg_name(r) if r else None
    ea = mo.disp
    if rn(mo.base) == 'rip':
        ea += rip + ins.size
    elif mo.base:
        ea += regs[rn(mo.base)]
    if mo.index:
        ea += regs[rn(mo.index)] * mo.scale
    ea &= M64
    expect = ea if canonical(ea) else 0
    if expect == addr:
        ok += 1
    else:
        bad += 1
        print('mismatch case=%s rip=%#x ea=%#x expect=%#x si_addr=%#x insn=%s %s' % (m.group(1), rip, ea, expect, addr, ins.mnemonic, ins.op_str))
print('[insn] 落ちた case (rip あり) %d 件: 実効アドレスの再計算が si_addr と一致 %d・不一致 %d (rip 無し = ALRM %d 件を除外)' % (ok + bad, ok, bad, skipped))
print('[insn] fault 命令: %s' % sorted(insn_cnt.items(), key=lambda kv: -kv[1]))
sys.exit(1 if bad else 0)
