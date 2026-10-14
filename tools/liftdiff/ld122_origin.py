#!/usr/bin/env python3
"""LD-122 (#2682): 0x959a40 の全体 run 限定 diff の出所を切り分ける。

全体 run (`batch --set sample:800 --shards 12`) の chunk 1・shard 4 で、0x959a40 は 1 つの runner で
SHARD の順に流れる。その前置列を 1 本の runner に流し直し、前置の組み合わせごとに 0x959a40 の verdict を見る。
tools/liftdiff で実行する (素材展開・wasm ビルド済みであること。REPORT_APPENDIX_LD122.md §2)。
  FL_WIN64_DIR=... python3 ld122_origin.py > results/ld122_959a40_origin.tsv
"""
import argparse, sys, time
sys.path.insert(0, '.')
from ldlib import cases
from ldlib.session import Session
import liftdiff as L

TARGET = 'targets/m11.json'
Y = 0x959a40
X = 0x50abe0
Z = 0x43a3f0
W = 0x5bfff0
SHARD = [0x6ee1a0, 0x821920, 0x43ba70, 0x646130, 0x103aa50, 0x424520, 0xd2bb50, 0x40fee0, 0x6619e0,
         0x59ba50, 0x76e6b0, 0x6cb920, 0x409350, 0x6ceeb0, 0x8ce510, 0x6bba60, 0x414370, 0x12b5450,
         0x11e7860, 0xe5afb0, 0x85a950, 0x66e080, 0xd2b620, 0x64ff10, 0xe21c90, 0x5bfff0, 0x50abe0,
         0x43a3f0, 0x959a40]
ALL = list(cases.PATTERN_NAMES)
PRE_Q0 = ALL[:ALL.index('q0')]
TAIL = ['qall', 'vm0', 'u16']

EXPS = [
    ('solo', [(Y, ALL)], False),
    ('A_X_then_Y', [(X, ALL), (Y, ALL)], False),
    ('A_X_then_Y_rep2', [(X, ALL), (Y, ALL)], False),
    ('A_X_then_Y_rep3', [(X, ALL), (Y, ALL)], False),
    ('B_W_then_Y', [(W, ALL), (Y, ALL)], False),
    ('C_W_X_then_Y', [(W, ALL), (X, ALL), (Y, ALL)], False),
    ('D_X_Z_then_Y', [(X, ALL), (Z, ALL), (Y, ALL)], False),
    ('S27_Z_then_Y', [(Z, ALL), (Y, ALL)], False),
    ('E0_X_fresh_then_Y', [(X, ALL), (Y, ALL)], True),
    ('E1_X_preq0_then_Y', [(X, PRE_Q0), (Y, ALL)], False),
    ('E1b_X_preq0_then_Y', [(X, PRE_Q0), (Y, ALL)], False),
    ('E2_X_q0only_then_Y', [(X, ['q0']), (Y, ALL)], False),
    ('E4_X_preq0_q0_then_Y', [(X, PRE_Q0 + ['q0']), (Y, ALL)], False),
    ('E5_X_tail_then_Y', [(X, TAIL), (Y, ALL)], False),
    ('R_shard4_replay', [(v, ALL) for v in SHARD], False),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default='')
    a = ap.parse_args()
    sess = Session(TARGET, build=False, shards=1, timeout=10.0, trace=True,
                   state=L.state_path(argparse.Namespace(state='auto', target=TARGET)))
    print('#experiment\tn\tY_verdict\tY_tags\tY_outcomes\tfirst_outcomes', flush=True)
    for name, seq, fresh in EXPS:
        if a.only and a.only not in name:
            continue
        t0 = time.time()
        nat, was = sess.make_runners()
        out = []
        try:
            for i, (va, pats) in enumerate(seq):
                if fresh and i > 0:
                    nat.close(); was.close(); nat, was = sess.make_runners()
                out.append(sess._run_one(nat, was, va, pats, True))
        finally:
            nat.close(); was.close()
        rec = L.make_record(sess, out[-1], {})
        tags = ','.join(t['tag'] for t in rec.get('tags', [])) or '-'
        y_out = ','.join('%s=%s' % (c['pattern'], c['outcome']) for c in out[-1]['cases'])
        prev = ','.join('%s=%s' % (c['pattern'], c['outcome']) for c in out[0]['cases']) if len(out) > 1 else '-'
        print('%s\t%d\t%s\t%s\t%s\t%s' % (name, len(seq), rec['verdict'], tags, y_out, prev), flush=True)
        print('# %s %.0fs' % (name, time.time() - t0), file=sys.stderr, flush=True)


if __name__ == '__main__':
    main()
