#!/usr/bin/env python3
"""set_other 非 imm の gep 17 件 (lea [reg+d]) と書込可能グローバル global_store 3 件の接続判定 (#4891 / M11-N227 / 親 #3907).

入力は m11_setother_mem_class.py の出力 mem_class_rows.json のうち conn が gep / global_store の行。
IR (boot_final 系の final3_base.ll) は変更しない。区分は 実値化 / 復元不能 / 未決 の 3 値で、未分類 0 を確認する。

global_store (書込可能グローバル VA を読む 3 件):
  対象は呼出し元 CFG 上の最後のグローバル格納 (store)。IR で VA を指す store を全件数える。
  store が 0 件なら 未決 (no_store_in_ir)。store があっても値の到達定義は未実装なので 未決 (store_value_unchecked)。
gep (lea [reg+d] の 17 件):
  対象は基底 reg の SSA 値に対する GEP。基底 SSA の特定は未実装のため 未決 (base_ssa_unmapped)。

使い方: python3 m11_setother_gep_global.py mem_class_rows.json --ir final3_base.ll --out gep_global_rows.json
"""
import argparse, collections, json, re

ap = argparse.ArgumentParser()
ap.add_argument('rows'); ap.add_argument('--ir', required=True); ap.add_argument('--out', required=True)
a = ap.parse_args()
rows = json.load(open(a.rows))
ir = open(a.ir).read().split('\n')
TARGET = [r for r in rows if r['conn'] in ('gep', 'global_store')]


def store_count(va):
    """IR 全体で VA (i64 十進) を指すアドレスへの store 件数と、その呼出し元関数名の集合。"""
    alias = set()
    pat_alias = re.compile(r'(%\S+) = inttoptr i64 ' + str(va) + r' to ptr')
    for l in ir:
        m = pat_alias.search(l)
        if m:
            alias.add(m.group(1))
    lit = re.compile(r'inttoptr \(i64 ' + str(va) + r' to ptr\)|inttoptr i64 ' + str(va) + r' to ptr')
    fn = None
    fns = []
    n = 0
    for l in ir:
        if l.startswith('define'):
            fn = l.split('@')[1].split('(')[0]
        if not l.lstrip().startswith('store ') and ' store ' not in l:
            continue
        if lit.search(l) or any(re.search(re.escape(x) + r'(?![\w.])', l.split('store', 1)[1]) for x in alias):
            n += 1
            fns.append(fn)
    return n, fns


out = []
cache = {}
for r in TARGET:
    x = dict(r)
    if r['conn'] == 'global_store':
        va = int(r['def'], 16) + 7 + int(re.search(r'\[rip \+ (0x[0-9a-f]+|\d+)\]', r['def_insn']).group(1), 0)
        if va not in cache:
            cache[va] = store_count(va)
        n, fns = cache[va]
        x['target_va'] = hex(va)
        x['store_count'] = n
        x['store_fns'] = fns[:5]
        if n == 0:
            x.update({'class': '未決', 'why': 'no_store_in_ir'})
        else:
            x.update({'class': '未決', 'why': 'store_value_unchecked'})
    else:
        x.update({'class': '未決', 'why': 'base_ssa_unmapped'})
    out.append(x)

json.dump(out, open(a.out, 'w'), ensure_ascii=False, indent=1)
cnt = collections.Counter(r['class'] for r in out)
print('[gep-global] 対象 %d 件 (gep %d・global_store %d)' % (len(out), sum(r['conn'] == 'gep' for r in out), sum(r['conn'] == 'global_store' for r in out)))
print('  実値化   %d' % cnt['実値化'])
print('  復元不能 %d' % cnt['復元不能'])
print('  未決     %d' % cnt['未決'])
print('  未分類   %d' % (len(out) - cnt['実値化'] - cnt['復元不能'] - cnt['未決']))
for k, v in sorted(collections.Counter((r['conn'], r['why']) for r in out).items()):
    print('  %-14s %-24s %d' % (k[0], k[1], v))
for r in out:
    if r['conn'] == 'global_store':
        print('  global_store %s va=%s stores=%d %s' % (r['caller'], r['target_va'], r['store_count'], r['store_fns']))
