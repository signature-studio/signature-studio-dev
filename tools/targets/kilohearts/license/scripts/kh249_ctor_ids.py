#!/usr/bin/env python3
"""kh249_ctor_ids.py — EditorModel ctor (0x180051af0) 呼出元 47 関数 (= 製品別 EditorModel 派生 ctor) を
RTTI クラス名で同定する (KH-11 #249 の 47 vs 46 差分用)。
手順: 各呼出元の先頭 24 命令内の `lea reg,[rip+X]` (= 派生 vtable) → vtable[-1] = COL → TypeDescriptor 名 (MSVC 装飾名)。
usage: kh249_ctor_ids.py [--xref work/xref_kh11.json] [--json OUT]"""
import sys, os, json, struct, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capstone
from pe_dis import pe, data, BASE, rd

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
arg = lambda k, d=None: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
xref = arg('--xref', os.path.join(HERE, 'work', 'xref_kh11.json'))
outj = arg('--json')
pd = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0]
b = data[pd.PointerToRawData:pd.PointerToRawData + pd.Misc_VirtualSize]
PD = {}
for i in range(0, len(b) // 12 * 12, 12):
    x, e, u = struct.unpack_from('<III', b, i)
    if x:
        PD[BASE + x] = BASE + e
import bisect
starts = sorted(PD)
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64); md.detail = True


def rtti_name(vt):
    col = struct.unpack('<Q', rd(vt - 8, 8))[0]
    if not (BASE < col < BASE + 0x10000000):
        return None
    sig, off, cdoff, td_rva, chd_rva = struct.unpack('<IIIII', rd(col, 20))
    if sig != 1:
        return None
    return rd(BASE + td_rva + 16, 120).split(b'\0')[0].decode('latin1')


sites = [int(x, 16) for x in json.load(open(xref))['180051af0']['calls']]
res = {}
for s in sites:
    f = starts[bisect.bisect_right(starts, s) - 1]
    a, vt = f, None
    for _ in range(24):
        ins = next(md.disasm(rd(a, 16), a, 1))
        if ins.mnemonic == 'lea' and 'rip' in ins.op_str and ins.op_str.startswith('rsi'):
            op = ins.operands[1]
            vt = a + ins.size + op.mem.disp
            break
        a += ins.size
    res['%x' % f] = {'call_site': '%x' % s, 'size': PD[f] - f, 'vtable': '%x' % vt if vt else None,
                     'rtti': rtti_name(vt) if vt else None}
for f, r in res.items():
    print(f, r['size'], r['vtable'], r['rtti'])
n_ok = sum(1 for r in res.values() if r['rtti'])
print('callers=%d rtti_resolved=%d' % (len(res), n_ok))
# em_check.mjs は ctors47.length で回すため、47 件・全件 RTTI 解決を満たさない出力は書かない (黙って縮むのを防ぐ)
if len(res) != 47 or n_ok != len(res):
    print('FAIL: 47 ctor 呼出元の全件 RTTI 解決が必要 (callers=%d rtti_resolved=%d)。出力は書きません' % (len(res), n_ok), file=sys.stderr)
    sys.exit(1)
if outj:
    json.dump(res, open(outj, 'w'), indent=1)
    # em_check.mjs が読む work/ctors47.json ([{ctor: <呼出元関数 VA>}] × 47) も再生成する (clean HEAD 再現用)
    json.dump([{'ctor': f, 'rtti': r['rtti']} for f, r in res.items()], open(os.path.join(os.path.dirname(outj), 'ctors47.json'), 'w'), indent=1)
