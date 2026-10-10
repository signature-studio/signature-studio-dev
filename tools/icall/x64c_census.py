#!/usr/bin/env python3
"""x64c_census.py --pe X --funcs F [--x64c path] : x64c.py (tools/ott/lift) の対応命令集合 (i_<mnemonic> メソッド + jcc/setcc/cmov 族) に対する
PE 関数集合の命令カバレッジ (静的). 未対応 mnemonic の出現数/関数数を表にする。x64c を Delphi(RTL, VMT, x87, SEH) へ拡張する際の工数見積り用。"""
import argparse, collections, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_icall as A

ap = argparse.ArgumentParser()
ap.add_argument('--pe', required=True); ap.add_argument('--funcs', required=True)
ap.add_argument('--x64c', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ott', 'lift', 'x64c.py'))
ap.add_argument('--top', type=int, default=40)
a = ap.parse_args()
import importlib.util
spec = importlib.util.spec_from_file_location('x64c_mod', a.x64c); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
sup = {n[2:] for n in dir(mod.FnLift) if n.startswith('i_')}   # alias (i_movsxd = i_movsx 等) 込み
sup |= {'movabs', 'cmpss', 'cmpsd'}
# 派生族: x64c の one() が jcc/setcc/cmovcc, rep 系を一般処理する
fam = re.compile(r'^(j(e|ne|z|nz|b|c|nae|ae|nb|nc|be|na|a|nbe|s|ns|p|pe|np|po|o|no|l|nge|ge|nl|le|ng|g|nle)|set\w+|cmov\w+)$')
img = A.Image(a.pe)
toks = [t for t in open(a.funcs).read().replace(',', '\n').split() if t]
rng = {}; vas = []
for t in toks:
    if '-' in t:
        lo, hi = t.split('-'); rng[int(lo, 16)] = int(hi, 16); vas.append(int(lo, 16))
    else:
        vas.append(int(t, 16))
img.set_extra_starts(vas)
dis = A.Disasm(img)
cnt = collections.Counter(); fns = collections.defaultdict(set); tot = 0
for v in sorted(set(vas)):
    r = (v, rng[v]) if v in rng else img.func_range(v)
    if not r: continue
    ins = dis.scan_function(r[0], r[1], {})
    for i in ins.values():
        mn = i.mnemonic.split()[-1]
        pre = i.mnemonic.split()[0] if ' ' in i.mnemonic else ''
        tot += 1
        if mn in sup or fam.match(mn):
            if pre in ('lock',):
                cnt[i.mnemonic] += 1; fns[i.mnemonic].add(v)
            continue
        cnt[i.mnemonic] += 1; fns[i.mnemonic].add(v)
uns = sum(cnt.values())
print('%s: 命令 %d, x64c 未対応 %d (%.2f%%), 未対応 mnemonic %d 種' % (os.path.basename(a.pe), tot, uns, 100.0 * uns / max(tot, 1), len(cnt)))
for mn, c in cnt.most_common(a.top):
    print('  %-14s %7d insn / %5d 関数' % (mn, c, len(fns[mn])))
