#!/usr/bin/env python3
"""kh249_id_scan.py — .text 全域で製品 id (FourCC, BE dword) の imm32 を持つ命令を列挙し、含む関数の直接 call 先 ∩ EditorModel 派生 ctor (47) を求める。
usage: kh249_id_scan.py --ctors work/ctor_ids.json --json OUT"""
import sys, os, json, struct, bisect, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capstone
from pe_dis import pe, data, BASE, rd
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
arg = lambda k, d=None: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
ctors = json.load(open(arg('--ctors', os.path.join(HERE, 'work', 'ctor_ids.json'))))
plugins = json.load(open(os.path.join(HERE, '..', 'work', 'winpkg', 'product_index.json')))['plugins']
ids = {struct.unpack('>I', p['id'].encode())[0]: p['id'] for p in plugins}
pd = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0]
b = data[pd.PointerToRawData:pd.PointerToRawData + pd.Misc_VirtualSize]
PD = []
for i in range(0, len(b) // 12 * 12, 12):
    x, e, u = struct.unpack_from('<III', b, i)
    if x: PD.append((BASE + x, BASE + e))
PD.sort(); starts = [p[0] for p in PD]
t = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.text'][0]
T_LO, T_HI = BASE + t.VirtualAddress, BASE + t.VirtualAddress + t.Misc_VirtualSize
ctor_set = {int(k, 16): v for k, v in ctors.items()}
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64); md.detail = True
hits = collections.defaultdict(lambda: {'ids': set(), 'ctors': set()})
for lo, hi in PD:
    if not (T_LO <= lo < T_HI): continue
    raw = rd(lo, hi - lo)
    # 高速前フィルタ: 製品 id の BE/LE バイト列が生バイトに含まれるか
    if not any(struct.pack('<I', k) in raw for k in ids): continue
    for ins in md.disasm(raw, lo):
        if ins.mnemonic == 'call' and ins.op_str.startswith('0x'):
            tg = int(ins.op_str, 16)
            if tg in ctor_set: hits[lo]['ctors'].add(tg)
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_IMM and (op.imm & 0xffffffff) in ids and ins.size >= 5:
                hits[lo]['ids'].add(ids[op.imm & 0xffffffff])
out = {'%x' % f: {'ids': sorted(v['ids']), 'ctors': ['%x' % c for c in sorted(v['ctors'])]} for f, v in hits.items() if v['ids']}
for f, v in sorted(out.items()):
    print(f, v['ids'], [ctors['%x' % int(c, 16)]['rtti'][4:30] for c in v['ctors']])

# 製品 id ↔ ctor の最近傍 (アドレス) 対応 (KH249_REPORT §2): 各 ctor (47) に対し、id imm32 を持つ関数のうち
# |関数 VA - ctor VA| が最小のものを選び、その関数の id を ctor の id 候補とする (ctor 自身は id を持たない)。
NONPRODUCT = ('HostProxyEditorModel', 'SnapinGroupEditorModel')
id_funcs = sorted((int(f, 16), v['ids']) for f, v in out.items())
nn = {}
for c, r in sorted(ctor_set.items()):
    f, fids = min(id_funcs, key=lambda x: (abs(x[0] - c), x[0]))
    nn[c] = {'rtti': r['rtti'], 'nearest_func': f, 'dist': abs(f - c), 'ids': fids,
             'nonproduct': any(n in r['rtti'] for n in NONPRODUCT)}
by_id = collections.defaultdict(list)
for c, v in nn.items():
    for i in v['ids']: by_id[i].append(c)
dup = {i: cs for i, cs in by_id.items() if len(cs) > 1}
unused = sorted(set(ids.values()) - {'core'} - set(by_id))
prod = {c: v for c, v in nn.items() if not v['nonproduct']}
prod_by_id = collections.Counter(i for v in prod.values() for i in v['ids'])
print('nearest: ctors=%d product_ctors=%d nonproduct=%d' % (len(nn), len(prod), len(nn) - len(prod)))
print('nearest: duplicated ids (all 47 ctors) =', {i: ['%x' % c for c in cs] for i, cs in dup.items()})
for i, cs in dup.items():
    print('  dup', i, [(('%x' % c), nn[c]['rtti'][4:30], 'nonproduct' if nn[c]['nonproduct'] else 'product') for c in cs])
print('nearest: product ctors only: duplicated ids =', sorted(i for i, n in prod_by_id.items() if n > 1),
      ' ids unused by any product ctor =', sorted(set(ids.values()) - {'core'} - set(prod_by_id)))
print('nearest: ids unused by any ctor =', unused)
if arg('--json'):
    out['_nearest'] = {'%x' % c: {'rtti': v['rtti'], 'nearest_func': '%x' % v['nearest_func'], 'dist': v['dist'], 'ids': v['ids'], 'nonproduct': v['nonproduct']} for c, v in nn.items()}
    json.dump(out, open(arg('--json'), 'w'), indent=1)
