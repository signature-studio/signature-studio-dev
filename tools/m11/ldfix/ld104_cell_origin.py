#!/usr/bin/env python3
"""ld104_cell_origin.py — #2288 (LD-104) spill 宛未判定 c589b0・128f9e0 24 site の機械語側の出自確認。

24 site は `mov rA,[rip+X]; mov rA,[rA]; mov [rbp+D],rA` の型で、セル K (LVA) の内容 V (LVA) を
さらに 1 段 deref した値を spill に store する。本スクリプトは次を機械的に数える:
  (a) 24 site の rip 相対セル K / 内容 V と、V が指す 8 byte の image 上の値
  (b) m11_image.bin の RetDec 関数区間 (config の decompilerDefined) 全体で、K・V を指す rip 相対参照の
      読み (R) / 書き (W) / RMW の件数と参照元関数・アドレス
  (c) K の絶対アドレス表現 (immediate の 0x15e0ab0 / 0x11e0ab0) の件数
K の内容は image 上で DIR64 補正済み (m11_image_gen.py は .reloc の指す値だけを VA→LVA に直す) なので、
K は PE ローダが V を指すように初期化するセルと読める。ただし .reloc 表そのものは image に無いため、
これは補正の痕跡からの推定であり、PE の .reloc 表での確認は未実施 (REPORT_2288 §7)。
関数区間は RetDec config の範囲のみ。区間外 (config に無い .text) の書き込みは走査できない。
使い方: python3 ld104_cell_origin.py [OUT_DIR]   環境変数: M11_WORK (既定 tools/m11/work)
出力: OUT_DIR/ld104_sites.tsv (24 site の K/V)、OUT_DIR/ld104_cell_refs.tsv (K/V を指す参照の全件)
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '../../..'))
sys.path.insert(0, HERE)
from ldmach_img import ImageMachine  # noqa: E402
from lb_base import IMG_BASE  # noqa: E402

W = os.environ.get('M11_WORK', os.path.join(REPO, 'tools/m11/work'))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'results')
mach = ImageMachine(os.path.join(W, 'm11_image.bin'), os.path.join(W, 'boot*.drc.config.json'))
rows = [ln.rstrip('\n').split('\t') for ln in open(os.path.join(HERE, 'results/spill178_1161.tsv'))][1:]
TARGET = {'c589b0', '128f9e0'}
sites = [r for r in rows if r[0] in TARGET and r[4] == '未判定']
RIP = re.compile(r'\[rip ([+-]) 0x([0-9a-f]+)\]')
WRITE_MN = {'mov', 'movsd', 'movss', 'movq', 'movups', 'movdqu', 'movaps'}
RMW_MN = {'add', 'sub', 'and', 'or', 'xor', 'inc', 'dec', 'neg', 'not', 'xadd', 'bts', 'btr', 'btc'}


def kind_of(x):
    first = x.op_str.split(',')[0]
    mem_first = '[' in first
    if mem_first and x.mnemonic in WRITE_MN:
        return 'W'
    if mem_first and x.mnemonic in RMW_MN:
        return 'RMW'
    return 'R'


def ins_of(fn_va):
    rva, n = mach.fns[fn_va]
    return list(mach.cs.disasm(mach.read(fn_va - IMG_BASE, n), fn_va, n))


def cell_of(ins, sva):
    idx = next(i for i, x in enumerate(ins) if x.address == sva)
    p2, p1 = ins[idx - 2], ins[idx - 1]
    m = RIP.search(p2.op_str)
    if p2.mnemonic != 'mov' or not m or not p1.op_str.endswith('[rax]'):
        return None
    disp = int(m.group(2), 16) * (1 if m.group(1) == '+' else -1)
    return p2.address + p2.size + disp


K_VA_TARGET = None
site_rows = []
for fn, site, _src, _verdict, _status, _oracle, text in sites:
    ins = ins_of(int(fn, 16))
    cva = cell_of(ins, int(site, 16))
    if cva is None:
        site_rows.append([fn, site, '-', '-', '-', '-', text])
        continue
    k = cva - IMG_BASE
    v = int.from_bytes(mach.read(k, 8), 'little')
    vb = mach.read(v, 8)
    site_rows.append([fn, site, '%x' % cva, '%x' % k, '%x' % v, vb.hex(), text])

ks = {r[3] for r in site_rows if r[3] != '-'}
vs = {r[4] for r in site_rows if r[4] != '-'}
assert len(ks) == 1 and len(vs) == 1, (ks, vs)
K_VA = int(next(iter(ks), '0'), 16) + IMG_BASE
V_LVA = int(next(iter(vs)), 16)
V_VA = V_LVA + IMG_BASE

refs = []
abs_refs = []
for fn_va in sorted(mach.fns):
    ins = ins_of(fn_va)
    for x in ins:
        m = RIP.search(x.op_str)
        if m:
            disp = int(m.group(2), 16) * (1 if m.group(1) == '+' else -1)
            tgt = x.address + x.size + disp
            if tgt == K_VA or V_VA <= tgt < V_VA + 8:
                which = 'K' if tgt == K_VA else 'V'
                refs.append([which, '%x' % fn_va, '%x' % x.address, kind_of(x), '%x' % tgt, '%s %s' % (x.mnemonic, x.op_str)])
        if re.search(r'0x(15e0ab0|11e0ab0|16b81b0|12b81b0)\b', x.op_str):
            abs_refs.append(['abs', '%x' % fn_va, '%x' % x.address, '-', '-', '%s %s' % (x.mnemonic, x.op_str)])

os.makedirs(OUT, exist_ok=True)
with open(os.path.join(OUT, 'ld104_sites.tsv'), 'w') as f:
    f.write('fn\tsite\tcell_va\tK_lva\tV_lva\tV_qword_image\ttext\n')
    for r in site_rows:
        f.write('\t'.join(r) + '\n')
with open(os.path.join(OUT, 'ld104_cell_refs.tsv'), 'w') as f:
    f.write('target\tfn\taddr\tkind\ttarget_va\tinsn\n')
    for r in refs + abs_refs:
        f.write('\t'.join(r) + '\n')

print('[ld104] site %d (c589b0 %d / 128f9e0 %d) / K_lva 0x%x / V_lva 0x%x / V の image 値 %s' % (
    len(site_rows), sum(1 for r in site_rows if r[0] == 'c589b0'), sum(1 for r in site_rows if r[0] == '128f9e0'),
    K_VA - IMG_BASE, V_LVA, site_rows[0][5]))
print('[ld104] K を指す rip 参照 (全 RetDec 関数): %d' % sum(1 for r in refs if r[0] == 'K'))
for kind in ('R', 'W', 'RMW'):
    print('        kind %s: %d' % (kind, sum(1 for r in refs if r[0] == 'K' and r[3] == kind)))
for fn in sorted(TARGET):
    print('        うち %s: %d (R %d / W %d)' % (fn, sum(1 for r in refs if r[0] == 'K' and r[1] == fn),
          sum(1 for r in refs if r[0] == 'K' and r[1] == fn and r[3] == 'R'),
          sum(1 for r in refs if r[0] == 'K' and r[1] == fn and r[3] == 'W')))
print('[ld104] V (8 byte) を指す rip 参照: %d (R %d / W %d / RMW %d)' % (
    sum(1 for r in refs if r[0] == 'V'), sum(1 for r in refs if r[0] == 'V' and r[3] == 'R'),
    sum(1 for r in refs if r[0] == 'V' and r[3] == 'W'), sum(1 for r in refs if r[0] == 'V' and r[3] == 'RMW')))
print('[ld104] K/V の絶対アドレス表現 (immediate): %d' % len(abs_refs))
print('[ld104] -> %s, %s' % (os.path.join(OUT, 'ld104_sites.tsv'), os.path.join(OUT, 'ld104_cell_refs.tsv')))
