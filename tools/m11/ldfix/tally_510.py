#!/usr/bin/env python3
"""tally_510.py — #510 (LD-10) の集計。audit_lsf_ssa.py の JSON と目視判定 (manual_verdicts_510.jsonl) を突合して、
 (1) 370 site / 169 関数の内訳と最終判定 (目視があれば目視、無ければ自動判定)
 (2) 静的方式 (alg1 / alg2 / alg3 / cell oracle) の目視に対する一致 (感度・偽陽性)
 (3) 20 関数標本 (seed 510) での 静的 vs 動的 (liftdiff batch_closure) vs 目視
を表示する。
使い方: python3 tally_510.py SSA.json MANUAL.jsonl [BATCH.jsonl [DROPS.tsv]]"""
import collections
import json
import random
import sys

ssa = json.load(open(sys.argv[1]))['functions']
man = {}
for ln in open(sys.argv[2]):
    r = json.loads(ln)
    man[(r['fn'], r['site'])] = r['verdict']
dyn = {}
if len(sys.argv) > 3:
    for ln in open(sys.argv[3]):
        r = json.loads(ln)
        dyn[r['function']['va'][2:]] = r['verdict']
KNOWN = {'5c0270', '41a670', '66e080', '7e5240', '806740', 'c62780', '417b70', '409c80'}

unk_fns = sorted([v for v, r in ssa.items() if any(s['kind'] == 'unk' for s in r['sites'])], key=lambda x: int(x, 16))
sites = [(v, s) for v in unk_fns for s in ssa[v]['sites'] if s['kind'] == 'unk']
print('[1] 母集団: base 解決不能 LSF site %d / %d 関数' % (len(sites), len(unk_fns)))
print('    frame 宛 (spill) %d / store 宛 %d' % (sum(1 for _v, s in sites if s['frame']), sum(1 for _v, s in sites if not s['frame'])))


def is_cell(s):
    return bool(s.get('cell')) and s['cell']['verdict'] == 'CELL_COLLAPSED'


def final(v, s):
    m = man.get((v, s['addr']))
    if m is not None:
        return ('manual', 'DROP' if m == 'TRUE_DROP' else ('UNDET' if m == 'UNDETERMINED' else 'OK'))
    return ('auto', 'DROP' if is_cell(s) else 'OK')


store_sites = [(v, s) for v, s in sites if not s['frame']]
cnt = collections.Counter(final(v, s) for v, s in store_sites)
print('[2] store 宛 %d site の最終判定 (source, verdict):' % len(store_sites), dict(sorted(cnt.items())))
drop = [(v, s) for v, s in store_sites if final(v, s)[1] == 'DROP']
undet = [(v, s) for v, s in store_sites if final(v, s)[1] == 'UNDET']
dfn = sorted({v for v, _ in drop}, key=lambda x: int(x, 16))
print('    DROP %d site / %d 関数 (うち目視確認 %d site, 自動 (cell oracle) %d site)' % (
    len(drop), len(dfn), sum(1 for v, s in drop if final(v, s)[0] == 'manual'), sum(1 for v, s in drop if final(v, s)[0] == 'auto')))
print('    UNDETERMINED %d site: %s' % (len(undet), [(v, s['addr']) for v, s in undet]))
kinds = collections.Counter()
for v, s in drop:
    kinds['cell(rip 相対セルの 2 段->1 段)' if is_cell(s) else 'その他(base/定数/0 を書く等)'] += 1
print('    DROP の型:', dict(kinds))
print('    DROP 関数:', ' '.join(dfn))

print('[3] 静的方式 vs 目視 (目視済みの store 宛 unk site のみ。UNDETERMINED 除く)')
judged = [(v, s, man[(v, s['addr'])]) for v, s in store_sites if (v, s['addr']) in man and man[(v, s['addr'])] != 'UNDETERMINED']
truth = {id(s): m == 'TRUE_DROP' for _v, s, m in judged}
n_t = sum(truth.values())
print('    目視済み %d site (TRUE_DROP %d / OK %d)' % (len(judged), n_t, len(judged) - n_t))


def ev(name, pred):
    tp = sum(1 for _v, s, m in judged if pred(s) and truth[id(s)])
    fp = sum(1 for _v, s, m in judged if pred(s) and not truth[id(s)])
    fn = sum(1 for _v, s, m in judged if not pred(s) and truth[id(s)])
    print('    %-34s TP=%d FP=%d FN=%d  感度=%d/%d' % (name, tp, fp, fn, tp, n_t))


A2 = ('SUSPECT', 'NOCAND')
A3 = ('SHALLOW', 'NOCAND')
ev('alg2 (SUSPECT|NOCAND)', lambda s: s['alg2'] in A2)
ev('alg3 (SHALLOW|NOCAND)', lambda s: s['alg3'] in A3)
ev('cell oracle (CELL_COLLAPSED)', is_cell)
ev('alg2 | cell oracle', lambda s: s['alg2'] in A2 or is_cell(s))
ev('alg3 | cell oracle', lambda s: s['alg3'] in A3 or is_cell(s))
ev('alg3 SHALLOW のみ (NOCAND 除く)', lambda s: s['alg3'] == 'SHALLOW')
ev('alg3 SHALLOW | cell oracle', lambda s: s['alg3'] == 'SHALLOW' or is_cell(s))

print('[4] 既知 TRUE_DROP 8 関数 (#484) での静的方式の感度 (関数単位)')
hit_f = {}
for v in sorted(KNOWN):
    r = ssa.get(v)
    a1 = any(x['deficit'] > 0 for x in r['alg1'])
    a2 = any((not s['frame']) and s['alg2'] in A2 for s in r['sites'])
    a3 = any((not s['frame']) and s['alg3'] in A3 for s in r['sites'])
    hit_f[v] = (a1, a2, a3)
    print('    %-7s alg1=%s alg2=%s alg3=%s' % (v, a1, a2, a3))
print('    関数単位 (alg1|alg2|alg3): %d/%d' % (sum(1 for x in hit_f.values() if any(x)), len(KNOWN)))

print('[5] 20 関数標本 (random.Random(510).sample(169 関数, 20)) での 静的 vs 動的 vs 目視')
smp = sorted(random.Random(510).sample(unk_fns, 20), key=lambda x: int(x, 16))
rows = []
for v in smp:
    ss = [s for s in ssa[v]['sites'] if s['kind'] == 'unk']
    nf = [s for s in ss if not s['frame']]
    st = any(s['alg2'] in A2 or s['alg3'] in A3 or is_cell(s) for s in nf)
    mdrop = any(man.get((v, s['addr'])) == 'TRUE_DROP' for s in nf)
    fin = [final(v, s)[1] for s in nf]
    rows.append((v, len(ss), len(nf), st, mdrop, any(x == 'DROP' for x in fin), dyn.get(v, '-')))
    print('    %-8s sites=%d store宛=%d 静的flag=%-5s 目視DROP=%-5s 最終DROP=%-5s 動的=%s' % rows[-1])
nfn = [r for r in rows if r[2] > 0]
print('    store 宛 site を持つ標本関数 %d / 20 のうち: 静的 flag %d, 最終 DROP %d, 動的 mismatch %d, 動的 match %d, 動的 unexec %d' % (
    len(nfn), sum(1 for r in nfn if r[3]), sum(1 for r in nfn if r[5]),
    sum(1 for r in nfn if r[6] == 'mismatch'), sum(1 for r in nfn if r[6] == 'match'), sum(1 for r in nfn if r[6] == 'unexec')))
fd = [r for r in nfn if r[5]]
print('    最終 DROP の標本関数 %d 本の動的 verdict: %s' % (len(fd), dict(collections.Counter(r[6] for r in fd))))

print('[6] 全 169 関数: 最終 DROP 関数 %d 本の動的 verdict (liftdiff batch_closure): %s' % (
    len(dfn), dict(collections.Counter(dyn.get(v, 'absent') for v in dfn))))

frame_sites = [(v, s) for v, s in sites if s['frame']]
fc = collections.Counter((s.get('cell') or {}).get('verdict', '-') for _v, s in frame_sites)
fcf = sorted({v for v, s in frame_sites if (s.get('cell') or {}).get('verdict') == 'CELL_COLLAPSED'}, key=lambda x: int(x, 16))
print('[7] frame 宛 (spill) %d site: cell oracle (幅 64 以外の load でセル自身を読む形のみ検出) %s, CELL_COLLAPSED の関数 %d' % (len(frame_sites), dict(fc), len(fcf)))
fj = collections.Counter()
for v, s in frame_sites:
    m = man.get((v, s['addr']))
    if m:
        fj[(m, (s.get('cell') or {}).get('verdict', '-'))] += 1
print('    目視済み (消費者判定) %d site: %s' % (sum(fj.values()), dict(sorted(fj.items()))))
fdrop = [(v, s) for v, s in frame_sites if man.get((v, s['addr'])) == 'TRUE_DROP']
fcand = [(v, s) for v, s in frame_sites if (s.get('cell') or {}).get('verdict') == 'CELL_COLLAPSED' and man.get((v, s['addr'])) is None]
print('    frame 宛 TRUE_DROP (目視) %d site / %d 関数, 目視未確認の oracle 候補 %d site / %d 関数' % (
    len(fdrop), len({v for v, _ in fdrop}), len(fcand), len({v for v, _ in fcand})))
allf = sorted(set(dfn) | {v for v, _ in fdrop} | {v for v, _ in fcand}, key=lambda x: int(x, 16))
print('[8] 脱落関数の和集合: store 宛 DROP %d 関数 + frame 宛 (目視 TRUE_DROP または oracle 候補) = %d 関数 / 169 関数' % (len(dfn), len(allf)))
if len(sys.argv) > 4:
    with open(sys.argv[4], 'w') as f:
        f.write('fn\tsite\tdest\tsource\tkind\tcell_va\twidth\ttext\n')
        rows = [(v, s, 'store', final(v, s)[0]) for v, s in drop] + [(v, s, 'frame', 'manual') for v, s in fdrop] + [(v, s, 'frame', 'candidate') for v, s in fcand]
        for v, s, dest, src in sorted(rows, key=lambda r: (int(r[0], 16), int(r[1]['addr'], 16))):
            c = s.get('cell')
            f.write('%s\t%s\t%s\t%s\t%s\t%s\t%d\t%s\n' % (v, s['addr'], dest, src, 'cell' if c and c['verdict'] == 'CELL_COLLAPSED' else 'other',
                                                         c['cell'] if c else '', s['w'], s['text']))
