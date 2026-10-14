#!/usr/bin/env python3
"""LD-121 (#2681): sample:800 (shard 1) の 19 関数の揺れを、runner の状態持ち越しで分類する。

  python3 ld121_restart_probe.py --restart none --out work/ld121/none.jsonl
  python3 ld121_restart_probe.py --restart wasm --out work/ld121/wasm.jsonl

cmd_batch の chunk 1 (sample:800 の 400 件目以降) を 1 組の runner で流す (ld96_heap_audit.py --mode full --only-part 1 と同じ開始状態)。
--restart は、chunk 1 に含まれる 19 関数の直前に作り直す側 (none・native・wasm・both)。
作り直した側は chunk 開始時と同じ init 状態になり、もう一方は前の関数の状態を持ち越す。
"""
import argparse, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import liftdiff
from ldlib import cases, irtool
from ldlib.session import Session

TSV = os.path.join(HERE, 'results', 'ld58_m11_sample800_shards_t1.tsv')
TARGET = os.path.join(HERE, 'targets', 'm11.json')


def read_19():
    out = []
    for l in open(TSV):
        f = l.rstrip('\n').split('\t')
        if f[0] == 'va' or len(f) < 6:
            continue
        if f[1] == 'match' and f[5] == 'mismatch':
            out.append(int(f[0], 16))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--restart', choices=['none', 'native', 'wasm', 'both'], required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--chunk', type=int, default=400)
    ap.add_argument('--part', type=int, default=1)
    a = ap.parse_args()
    ns = argparse.Namespace(target=TARGET, state='auto')
    sess = Session(TARGET, shards=1, build=False, trace=True, timeout=10.0, state=liftdiff.state_path(ns))
    irfeats = {} if sess.t.get('clift') else irtool.ir_features(sess.t['ir'], sess.prefix)
    vas = liftdiff.select_set(sess, 'sample:800', irfeats)
    aud = set(read_19())
    assert len(aud) == 19, len(aud)
    part = vas[a.part * a.chunk:(a.part + 1) * a.chunk]
    targets = [v for v in part if v in aud]
    print('[ld121] restart=%s part=%d fns=%d targets=%d' % (a.restart, a.part, len(part), len(targets)), flush=True)

    nat, was = sess.make_runners()

    def restart():
        nonlocal nat, was
        n2, w2 = sess.make_runners()
        if a.restart in ('native', 'both'):
            nat.close()
            nat = n2
        else:
            n2.close()
        if a.restart in ('wasm', 'both'):
            was.close()
            was = w2
        else:
            w2.close()

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    out = open(a.out, 'w')
    t0 = time.time()
    try:
        for va in part:
            if va in aud and a.restart != 'none':
                restart()
            if va not in aud:
                sess._run_one(nat, was, va, cases.PATTERN_NAMES, True)
                continue
            rec = sess._run_one(nat, was, va, cases.PATTERN_NAMES, True)
            v = liftdiff.make_record(sess, rec, irfeats)
            out.write(json.dumps({'restart': a.restart, 'va': hex(va), 'name': rec['name'], 'verdict': v.get('verdict'),
                                  'cases': [[c.get('pattern'), c.get('outcome'), c.get('native_status'), c.get('wasm_status')]
                                            for c in rec.get('cases', [])]}, default=str) + '\n')
            out.flush()
            print('[ld121] %s %s %s %.0fs' % (rec['name'], v.get('verdict'), a.restart, time.time() - t0), flush=True)
    finally:
        out.close()
        nat.close()
        was.close()
    print('[ld121] done %.0fs -> %s' % (time.time() - t0, a.out), flush=True)


if __name__ == '__main__':
    main()
