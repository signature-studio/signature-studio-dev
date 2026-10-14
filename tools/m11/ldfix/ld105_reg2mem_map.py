#!/usr/bin/env python3
"""ld105_reg2mem_map.py — #2312 (LD-105) cf3790 の残り spill 宛 site の reg2mem 突合表。

機械語の [rbp+disp] store を IR の reg2mem slot (stack_var_-(disp+8)) に対応づけ、
各 site について次を 1 行に並べる (判定は入れない。判定は突合表を見て人が行う):
  machine   = store 直前 5 命令 (値の由来)
  slot      = 対応する IR slot 名 (alloca の有無)
  ir_store  = その slot への store の値と、値の IR 定義 (1 段)
  ir_reload = slot の reload を使う IR 命令 (最初の 1 件)
入力: tools/m11/work/boot_final3.ll (M11_WORK で差し替え可) / m11_image.bin (機械語)
出力: results/ld105_reg2mem_map.tsv
使い方: python3 ld105_reg2mem_map.py [OUT.tsv]
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '../../..'))
sys.path.insert(0, HERE)
from ldmach_img import ImageMachine  # noqa: E402
from ld110_reg2mem_link import frame_size  # noqa: E402

W = os.environ.get('M11_WORK', os.path.join(REPO, 'tools/m11/work'))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'results/ld105_reg2mem_map.tsv')
FN, FN_END = 0xcf3790, 0xcf3790 + 0x1000
SITES = ['cf3b03', 'cf3b54', 'cf3b62', 'cf3baf', 'cf3bbd', 'cf3c0e', 'cf3c1c', 'cf3dfa',
         'cf3e08', 'cf3e7a', 'cf3e88', 'cf3f47', 'cf3f55', 'cf3fd3', 'cf3fe1']

mach = ImageMachine(os.path.join(W, 'm11_image.bin'), os.path.join(W, 'boot*.drc.config.json'))
ins = list(mach.cs.disasm(mach.read(FN - mach.base, FN_END - FN), FN, FN_END - FN))
idx = {x.address: i for i, x in enumerate(ins)}

ll = open(os.path.join(W, 'boot_final3.ll')).read().splitlines()
start = next(i for i, l in enumerate(ll) if l.startswith('define weak i64 @function_cf3790('))
end = next(i for i in range(start, len(ll)) if ll[i] == '}')
body = ll[start:end]
defs = {}
for l in body:
    m = re.match(r'\s+(%[\w.]+) = (.*)', l)
    if m:
        defs.setdefault(m.group(1), l.strip())


def slot_of(site):
    a = int(site, 16)
    x = ins[idx[a]]
    m = re.search(r'\[rbp \+ (0x[0-9a-f]+)\]', x.op_str)
    return int(m.group(1), 16)


FRAME = frame_size(ins)


def ir_name(disp):
    # 旧式 -(disp+8) は frame 位置の仮定が誤り (#2389)。cf3790 は F=472 (push 4 本 + sub rsp 0x1b8)
    return 'stack_var_-%d' % (FRAME - disp)


rows = ['site\tdisp\tslot\talloca\tir_stores\tir_reload_use\tmachine_prev5\tir_store_value_def']
for s in SITES:
    a = int(s, 16)
    disp = slot_of(s)
    name = ir_name(disp)
    alloca = any(('%' + name + '.') in l and 'alloca' in l for l in body)
    stores = [l.strip() for l in body if re.search(r'store \S+ \S+, ptr %' + re.escape(name) + r'\.', l)]
    reload_use = '-'
    rl = [re.search(r'(%\S+) = load \S+, ptr %' + re.escape(name) + r'\.\S*reg2mem', l) for l in body]
    rl = [m.group(1) for m in rl if m]
    if rl:
        uses = [l.strip() for l in body if re.search(re.escape(rl[0]) + r'(?![\w.])', l) and ' = load ' not in l]
        reload_use = uses[0] if uses else '-'
    val_def = '-'
    if stores:
        m = re.search(r'store \S+ (%\S+), ptr', stores[-1])
        if m and m.group(1) in defs:
            val_def = defs[m.group(1)]
    i = idx[a]
    prev = '; '.join('%x %s %s' % (x.address, x.mnemonic, x.op_str) for x in ins[max(0, i - 5):i])
    rows.append('\t'.join([s, hex(disp), name, 'yes' if alloca else 'no', str(len(stores)),
                           reload_use, prev, val_def]))

with open(OUT, 'w') as f:
    f.write('\n'.join(rows) + '\n')
print('[ld105] %d site -> %s' % (len(SITES), OUT))
