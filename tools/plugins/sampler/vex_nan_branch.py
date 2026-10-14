#!/usr/bin/env python3
"""#540 AC5: VEX 命令を含む分岐が CPUID 固定の対象か、値 (倍精度 NaN 判定) かを判定する。
usage: vex_nan_branch.py <block PE.bin> [--branch=0x1801f2ed2] [--ctrl=0x180277ae4]
判定: 分岐の直前 7 命令が『r10 = [X] & r8; r10 == [X] なら rax = r8、r10 = [Y] & rax; jne』の形か。
X・Y が書込み不可の節にあり .text から書かれないこと、両辺の直線区間の VEX 命令数を出す。
ネガコン: --ctrl (CPUID 旗、.data) は .text からの書込みが 1 件以上あること。
形・定数・ネガコンのどれかが外れたら exit 1。
"""
import argparse
import re
import sys

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

ap = argparse.ArgumentParser()
ap.add_argument('block')
ap.add_argument('--branch', default='0x1801f2ed2')
ap.add_argument('--ctrl', default='0x180277ae4')
args = ap.parse_args()

pe = pefile.PE(args.block, fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
md = Cs(CS_ARCH_X86, CS_MODE_64)
RIP = re.compile(r'\[rip ([+-]) (0x[0-9a-f]+)\]')
EXEC, WRITE = 0x20000000, 0x80000000
bad = []


def sec_of(va):
    for s in pe.sections:
        lo = base + s.VirtualAddress
        if lo <= va < lo + s.Misc_VirtualSize:
            return s, lo
    sys.exit(f'{va:#x}: PE のセクション外')


def sec_name(s):
    return s.Name.rstrip(b'\0').decode()


def rip_target(ins):
    m = RIP.search(ins.op_str)
    if not m:
        return None
    d = int(m.group(2), 16) * (1 if m.group(1) == '+' else -1)
    return ins.address + ins.size + d


def decode_from(va, count):
    s, lo = sec_of(va)
    data = s.get_data()
    out, off = [], va - lo
    while len(out) < count and off < len(data):
        ins = next(md.disasm(data[off:off + 16], lo + off, 1), None)
        if ins is None:
            break
        out.append(ins)
        off += ins.size
    return out


def read_u64(va):
    s, lo = sec_of(va)
    return int.from_bytes(s.get_data()[va - lo:va - lo + 8], 'little')


def writes_from_text(targets):
    hits = {t: [] for t in targets}
    for s in pe.sections:
        if not s.Characteristics & EXEC:
            continue
        lo = base + s.VirtualAddress
        code = s.get_data()[:s.Misc_VirtualSize]
        off = 0
        while off < len(code):
            ins = next(md.disasm(code[off:off + 16], lo + off, 1), None)
            if ins is None:
                off += 1
                continue
            ea = rip_target(ins)
            if ea in hits and ins.mnemonic not in ('cmp', 'test', 'push', 'call', 'jmp') \
                    and '[rip' in ins.op_str.split(',')[0]:
                hits[ea].append(ins.address)
            off += ins.size
    return hits


def check(cond, msg):
    print(('OK  ' if cond else 'NG  ') + msg)
    if not cond:
        bad.append(msg)


br = int(args.branch, 16)
win = [i for i in decode_from(br - 0x30, 64) if i.address <= br]
check(bool(win) and win[-1].address == br, f'分岐 {br:#x} の直前 7 命令を復号')
if bad:
    sys.exit(1)
seq = win[-7:]
check([i.mnemonic for i in seq] == ['mov', 'and', 'cmp', 'cmove', 'mov', 'and', 'jne'],
      'mnemonic 列 = mov/and/cmp/cmove/mov/and/jne (NaN 判定の形)')
x1, x2, y = rip_target(seq[0]), rip_target(seq[2]), rip_target(seq[4])
check(seq[1].op_str == 'r10, r8' and seq[3].op_str == 'rax, r8' and seq[5].op_str == 'r10, rax',
      'オペランドが r8 の選択と rax との AND を表す')
check(x1 is not None and x1 == x2, f'X の 2 参照が同一 ({x1:#x})')
X, Y = read_u64(x1), read_u64(y)
check(X == 0x7FF0000000000000 and Y == 0x000FFFFFFFFFFFFF,
      f'定数 X={X:#018x} Y={Y:#018x} (倍精度の指数部全 1 と仮数マスク)')
fall = br + seq[-1].size
tgt = int(seq[-1].op_str, 16)
for name, va in (('X', x1), ('Y', y)):
    s, _ = sec_of(va)
    check(not s.Characteristics & WRITE, f'{name} {va:#x} は読み取り専用の節 ({sec_name(s)})')

ctrl = int(args.ctrl, 16)
hits = writes_from_text([x1, y, ctrl])
check(not hits[x1] and not hits[y], f'.text からの書込み X={len(hits[x1])} Y={len(hits[y])} (0 件であること)')
cs, _ = sec_of(ctrl)
check(bool(cs.Characteristics & WRITE) and len(hits[ctrl]) >= 1,
      f'ネガコン {ctrl:#x} ({sec_name(cs)}) は書込み {len(hits[ctrl])} 件 (1 件以上)')


def straight_vex(start, limit=40):
    n, vex, first, stop = 0, 0, None, None
    for ins in decode_from(start, limit):
        n += 1
        if ins.mnemonic.startswith('v'):
            vex += 1
            first = first or ins.address
        if ins.mnemonic in ('jmp', 'ret'):
            stop = ins.address
            break
    return n, vex, first, stop


for label, va in (('fall-through (r8 が NaN でない)', fall), ('taken (r8 が NaN)', tgt)):
    n, vex, first, stop = straight_vex(va)
    print(f'{label}: 開始 {va:#x}、直線区間 {n} 命令、VEX {vex} 件'
          f' (最初 {first and hex(first)})、終端 {stop and hex(stop)}')
print('結論: 分岐は CPUID 由来の旗ではなく r8 の値 (NaN 判定) で決まる。' if not bad else '結論: 判定不成立 (上の NG)')
sys.exit(1 if bad else 0)
