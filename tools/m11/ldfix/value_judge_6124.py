#!/usr/bin/env python3
# value_judge_6124.py: 同一ブロック複数 IR load と機械 chain の 1:1 対応を、実行時の値の一致で判定する (#6124 / LD-298・診断専用)。
# 修復は行わない (fix_d17.py / link_d17.py は変更しない)。
# 入力:
#   groups: [{"k": "11e0ff8", "blk": "128c320", "ir": [0, 1], "mach": [0, 1]}, ...]  静的な候補 (IR load 番号・chain 番号)
#   rows:   [{"side": "ir" | "mach", "k": "...", "blk": "...", "idx": n, "hit": h, "value": v}, ...]  実行時の観測 (hit = ブロック入口 1 回ごと)
# 判定 (K 組・ブロック単位):
#   一致     : 全 hit で観測が揃い、IR load i と chain j の値が全 hit で等しい対応が、各 chain・各 IR load に 1 つずつだけ存在する
#   不一致   : 全 hit で観測が揃うが、chain の全候補が IR load と値の一致で結べない (または 1 対 1 にならない)
#   判定不能 : 観測の欠落・hit 0 件・候補が複数 (順序で決めない)
# 使い方: python3 value_judge_6124.py <groups.json> <rows.json> [--out result.json]
import argparse, json, sys


def judge_group(g, rows):
    key = (g['k'], g['blk'])
    ir_ids, mach_ids = list(g['ir']), list(g['mach'])
    if not ir_ids or not mach_ids:
        return '判定不能', 'static: 片側が空'
    vals = {}
    hits = set()
    for r in rows:
        if (r['k'], r['blk']) != key:
            continue
        vals[(r['side'], r['idx'], r['hit'])] = r['value']
        hits.add(r['hit'])
    if not hits:
        return '判定不能', 'hit 0 件'
    for h in hits:
        for side, ids in (('ir', ir_ids), ('mach', mach_ids)):
            for i in ids:
                if (side, i, h) not in vals:
                    return '判定不能', '観測欠落 (%s %d hit %s)' % (side, i, h)
    cand = {j: [] for j in mach_ids}
    for j in mach_ids:
        for i in ir_ids:
            if all(vals[('ir', i, h)] == vals[('mach', j, h)] for h in hits):
                cand[j].append(i)
    if any(len(c) == 0 for c in cand.values()):
        return '不一致', '値が全 hit で一致する IR load が無い chain がある'
    if any(len(c) > 1 for c in cand.values()):
        return '判定不能', '候補が複数 (順序では決めない)'
    used = [c[0] for c in cand.values()]
    if len(set(used)) != len(used) or len(ir_ids) != len(mach_ids):
        return '判定不能', '1 対 1 にならない'
    return '一致', 'hit %d 件で %d 組' % (len(hits), len(used))


def judge(groups, rows):
    out = []
    for g in groups:
        v, why = judge_group(g, rows)
        out.append({'k': g['k'], 'blk': g['blk'], 'verdict': v, 'why': why})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('groups')
    ap.add_argument('rows')
    ap.add_argument('--out')
    a = ap.parse_args()
    groups = json.load(open(a.groups))
    rows = json.load(open(a.rows))
    res = judge(groups, rows)
    counts = {}
    for r in res:
        counts[r['verdict']] = counts.get(r['verdict'], 0) + 1
    print('[value_judge_6124] groups=%d %s' % (len(res), json.dumps(counts, ensure_ascii=False)))
    if a.out:
        json.dump(res, open(a.out, 'w'), ensure_ascii=False, indent=1)
    return 0


if __name__ == '__main__':
    sys.exit(main())
