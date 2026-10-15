"""LD-183 (#3935): batch を 1 run 行う。負荷 (CPU 占有) と case の並び (shuffle) を変えられる。

使い方: python3 tests/ld183_order_load.py TARGET --state (auto|PATH) --shards 12 --order (sorted|shuffle:SEED)
                                         --load N --out OUT.jsonl
判定 (classify / compare) と timeout の既定値は変えない。liftdiff.py cmd_batch と同じ手順を、
並びの指定と負荷の付与だけ加えて行う。負荷のプロセスは PID で止める (kill <PID>)。
"""
import argparse
import json
import os
import random
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import liftdiff  # noqa: E402
from ldlib import build_wasm, irtool  # noqa: E402
from ldlib.session import Session  # noqa: E402

HOG = 'while :; do :; done'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('target')
    ap.add_argument('--state', default='auto')
    ap.add_argument('--shards', type=int, default=12)
    ap.add_argument('--order', default='sorted')
    ap.add_argument('--load', type=int, default=0)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()

    if a.state == 'auto':
        state = os.path.join(build_wasm.load_target(a.target)['work'], 'boot_state.json')
    else:
        state = a.state
    sess = Session(a.target, shards=a.shards, build=False, trace=True, timeout=10.0, state=state)
    irfeats = {} if sess.t.get('clift') else irtool.ir_features(sess.t['ir'], sess.prefix)
    vas = liftdiff.select_set(sess, 'sample:800', irfeats)
    if a.order.startswith('shuffle:'):
        random.Random(int(a.order.split(':')[1])).shuffle(vas)
    elif a.order != 'sorted':
        raise SystemExit('bad --order')

    hogs = [subprocess.Popen(['sh', '-c', HOG]) for _ in range(a.load)]
    l0 = open('/proc/loadavg').read().split()[0]
    t0 = time.time()
    try:
        with open(a.out, 'w') as out:
            for i in range(0, len(vas), 400):
                part = vas[i:i + 400]
                res = sess.run_functions(part, None, with_refine=True)
                for va in part:
                    out.write(json.dumps(liftdiff.make_record(sess, res[va], irfeats)) + '\n')
                out.flush()
    finally:
        for p in hogs:
            p.kill()
            p.wait()
    print('[ld183] state=%s order=%s load=%d shards=%d load_1m_start=%s wall=%.0fs -> %s' % (
        os.path.basename(state), a.order, a.load, a.shards, l0, time.time() - t0, a.out), flush=True)
    liftdiff.cmd_summary(argparse.Namespace(file=a.out, md=None))


if __name__ == '__main__':
    main()
