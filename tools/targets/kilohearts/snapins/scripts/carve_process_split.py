#!/usr/bin/env python3
"""Carve EQ (ksge) process 直接 closure を unique 側 / infra 側に分け、infra の扱いを表にする (KH-156 / #5378)。

入力: work/callgraph.pkl (callgraph.py)、work/closures_sets.pkl (closures.py)、snapins/snapins.json。
closure = process root (GraphicEqDsp の vtable slot 14 = RVA 0x37d210) から直接 call/jmp で辿った到達集合 (145 関数)。
unique = closure ∩ sets['graphiceq'] (25)。infra = closure − unique (120)。
出力: stdout に件数と、infra 側から unique 側が呼ぶ callee の表 (khbase lift 済みか・snapins の lift 対象か)。
usage: carve_process_split.py work/callgraph.pkl work/closures_sets.pkl snapins.json
"""
import sys, json, pickle, collections

B = 0x180000000
PROCESS_RVA = 0x37d210


def main(cgp, setp, snapp):
    res = pickle.load(open(cgp, 'rb'))['res']
    sets = pickle.load(open(setp, 'rb'))['sets']
    snap = json.load(open(snapp))
    seen = {PROCESS_RVA}
    q = collections.deque([PROCESS_RVA])
    while q:
        f = q.popleft()
        for n in res[f]['calls'] + res[f]['jmps']:
            if n in res and n not in seen:
                seen.add(n)
                q.append(n)
    uniq = seen & set(sets['graphiceq'])
    infra = seen - uniq
    print(f'process direct closure {len(seen)} / unique {len(uniq)} / infra {len(infra)}')
    print('unique IAT calls', sum(res[f]['iat'] for f in uniq), '/ infra IAT calls', sum(res[f]['iat'] for f in infra))
    kb = {int(v, 16) - B for v in snap['khbase']['lift'].values()}
    cnt = collections.Counter()
    print('infra callees called by the unique side (khbase lift の有無):')
    for c in sorted({n for f in uniq for n in res[f]['calls'] + res[f]['jmps'] if n in infra}):
        callers = sorted(f for f in uniq if c in res[f]['calls'] or c in res[f]['jmps'])
        tag = 'khbase-lifted' if c in kb else 'not-khbase'
        cnt[tag] += 1
        print(f'  {c + B:#x} {tag:14s} callers={[hex(x) for x in callers]}')
    print('callee tally', dict(cnt))
    lifted = infra & kb
    outside = infra - kb
    for name, S in (('infra khbase-lifted', lifted), ('infra not-khbase', outside)):
        print(f'{name}: n {len(S)} / size B {sum(res[f]["size"] for f in S)} / IAT calls {sum(res[f]["iat"] for f in S)}')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3])
