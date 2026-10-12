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
if arg('--json'): json.dump(out, open(arg('--json'), 'w'), indent=1)
