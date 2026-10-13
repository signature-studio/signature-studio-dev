#!/usr/bin/env python3
"""fa7_static_reads.py <core> <filter_rep.json> — Filter process closure (lift 済み 114 関数) が参照する [reg+disp] の disp のうち
M (Filter model) の param 領域 [0x19b8, 0xa400) に入るものを列挙し、ID descriptor 表 (ids.txt) の各 ID の desc 範囲 [desc_off, desc_off+0x148) と突合する。
出力: 各 disp が属する ID (desc 範囲) の一覧と、ID 0x156..0x15b (343/344/346 含む) が読まれるか。"""
import sys, re, json, collections
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
import pefile
core, rep, ids = sys.argv[1], sys.argv[2], sys.argv[3]
pe = pefile.PE(core); base = pe.OPTIONAL_HEADER.ImageBase
funcs = json.load(open(rep))['funcs']
desc = {}
for l in open(ids):
    m = re.match(r'(\d+) desc_id=\d+ desc_off=0x([0-9a-f]+)', l)
    if m: desc[int(m.group(1))] = int(m.group(2), 16)
order = sorted(desc.items(), key=lambda kv: kv[1])
def owner(d):
    for i, o in order:
        if o <= d < o + 0x48: return i      # descriptor 実体 = 0x48 B (cell 0x9db8.. は別領域) / 0x148 は record 刻み
    return None
md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = False
hits = collections.defaultdict(set); ndisp = 0
for fa, info in funcs.items():
    a = int(fa, 16)
    code = pe.get_data(a - base, info['size'])
    for ins in md.disasm(code, a):
        for m in re.finditer(r'\[[a-z0-9]+(?: [+*] [a-z0-9]+(?: \* \d)?)? \+ (0x[0-9a-f]+)\]', ins.op_str):
            d = int(m.group(1), 16)
            if 0x19b8 <= d < 0xa400:
                ndisp += 1; hits[d].add(fa)
print('closure funcs=%d, M-param-region disp 参照 %d 件 (distinct disp %d)' % (len(funcs), ndisp, len(hits)))
byid = collections.defaultdict(list)
for d in sorted(hits):
    byid[owner(d)].append(hex(d))
for i in sorted(byid, key=lambda x: (x is None, x)): print('  ID', i, byid[i])
target = [343, 344, 346, 342, 345, 347]
rd = [i for i in target if i in byid]
print('RESULT: closure が読む descriptor ID のうち {0x156..0x15b} に該当:', rd)
sys.exit(0 if not rd else 1)
