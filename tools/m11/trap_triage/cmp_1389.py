#!/usr/bin/env python3
# #1389: repro_1389.sh の出力 (rec_<label>.json = 呼出し k ごとの dest 内容, cost_<label>.json = unit ごとの f413060 呼出し数) を比較する。
# 呼出し k の unit は cost の f413060 を unit 順に累積して引く (呼出しは unit 順に起きるため)。
# 出力: OFF 決定性 (off vs off2)・OFF/ON の差分 (呼出し番号・unit VA・フィールド) を数値で出す。
import json, sys, os
from collections import Counter

d = sys.argv[1]
def load(label):
    # 呼出し k を (unit VA, unit 内の順番 j) に対応づける。呼出しは unit 順に起きる。
    rec = json.load(open(os.path.join(d, f'rec_{label}.json')))
    cost = json.load(open(os.path.join(d, f'cost_{label}.json')))
    keyed = {}
    k = 0
    for c in cost:
        for j in range(int(c.get('f413060', 0))):
            if k < len(rec):
                keyed[(c['va'], j)] = rec[k]
            k += 1
    return rec, keyed

def cmp(a_label, b_label):
    ra, ka = load(a_label)
    rb, kb = load(b_label)
    common = sorted(set(ka) & set(kb), key=lambda x: (int(x[0], 16), x[1]))
    diffs = []
    for key in common:
        a, b = ka[key], kb[key]
        fields = [f for f in ('st', 'len', 'rc', 'h') if a[f] != b[f]]
        if fields:
            diffs.append({'unit': key[0], 'j': key[1], 'fields': fields,
                          a_label: {f: a[f] for f in ('st', 'len', 'rc', 'h')}, b_label: {f: b[f] for f in ('st', 'len', 'rc', 'h')}})
    only_a = len(ka) - len(common); only_b = len(kb) - len(common)
    n = len(common)
    print(f'[cmp_1389] {a_label} vs {b_label}: 記録数 {len(ra)} / {len(rb)}, unit・順番で揃った呼出し {n} 件 (片側のみ {only_a} / {only_b}), 差分 {len(diffs)} 件')
    print(f'[cmp_1389]   差分のフィールド: {dict(Counter(f for x in diffs for f in x["fields"]))}')
    print(f'[cmp_1389]   差分の unit (VA): {dict(Counter(str(x["unit"]) for x in diffs))}')
    for x in diffs[:20]:
        print('[cmp_1389]   ' + json.dumps(x, ensure_ascii=False))
    return diffs

off_vs_off2 = cmp('off', 'off2')
off_vs_on = cmp('off', 'on')
ok = len(off_vs_off2) == 0
print(f'[cmp_1389] OFF 決定性 (off == off2): {"一致" if ok else "不一致"}')
sys.exit(0 if ok else 1)
