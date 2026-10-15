#!/usr/bin/env python3
"""LD-268 (#5268): chunk 0 の 0x5d19e0 で、native の NRST_MMAP 領域の一覧 (NMMAPN) を取る。

  python3 ld268_mmap_regions.py --out results/ld268_mmap/regions.json

ld156_chunk0_carryover.py と同じ開始状態 (sample:800 の 0〜399 件目を流し、対象関数の直前で止める) で
native runner の NMMAPN だけを問い合わせる。戻しは行わない。
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import liftdiff
from ldlib import cases, irtool
from ldlib.session import Session

TARGET = os.path.join(HERE, 'targets', 'm11.json')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    ns = argparse.Namespace(target=TARGET, state='auto')
    sess = Session(TARGET, shards=1, build=False, trace=True, timeout=10.0, state=liftdiff.state_path(ns))
    irfeats = {} if sess.t.get('clift') else irtool.ir_features(sess.t['ir'], sess.prefix)
    vas = liftdiff.select_set(sess, 'sample:800', irfeats)
    nat, was = sess.make_runners()
    try:
        nat._send('NMMAPN')
        nat.p.stdin.flush()
        r = nat._recv(30.0)
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        json.dump({'nmmapn': r}, open(a.out, 'w'), indent=1)
        print(r, flush=True)
    finally:
        nat.close()
        was.close()


if __name__ == '__main__':
    main()
