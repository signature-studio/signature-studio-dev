#!/usr/bin/env python3
"""LD-126 (#2723): sample:800 (shard 1) の 19 関数のうち chunk 1 に含まれる 18 件の揺れを、wasm 側の持ち越し候補ごとに戻して切り分ける。

  python3 ld126_wasm_state.py --reset none --out work/ld126/none.jsonl
  python3 ld126_wasm_state.py --reset stk  --out work/ld126/stk.jsonl

cmd_batch の chunk 1 (sample:800 の 400 件目以降) を 1 組の runner で流す (ld121_restart_probe.py と同じ開始状態)。
--reset は、shard 1 の 19 関数のうち chunk 1 に含まれる 18 件の直前に、wasm 側の次の候補だけを SNAPSHOT 時点の内容へ戻す (RESET 行)。
  stk: wasm スタック (と SP)   sta: C 静的変数 (g_heap・g_inbuf・g_arena を除く data/bss)   img: image 全体 (WR 範囲外を含む)
  all: 上の 3 つすべて。none は戻さない (ld121 の none と同じ経路で、ビルドの変更の対照に使う)。
"""
import argparse, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import liftdiff
from ldlib import cases, irtool
from ldlib.session import Session

TSV = os.path.join(HERE, 'results', 'ld58_m11_sample800_shards_t1.tsv')
TARGET = os.path.join(HERE, 'targets', 'm11.json')
MASK = {'none': 0, 'stk': 1, 'sta': 2, 'img': 4, 'all': 7, 'sp': 8, 'sta_img': 6, 'sta_sp': 10}


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
    ap.add_argument('--reset', choices=sorted(MASK), required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--chunk', type=int, default=400)
    ap.add_argument('--part', type=int, default=1)
    ap.add_argument('--limit', type=int, default=0, help='診断用: chunk の先頭 N 件だけ流す (0 = 全件)')
    a = ap.parse_args()
    ns = argparse.Namespace(target=TARGET, state='auto')
    sess = Session(TARGET, shards=1, build=False, trace=True, timeout=10.0, state=liftdiff.state_path(ns))
    irfeats = {} if sess.t.get('clift') else irtool.ir_features(sess.t['ir'], sess.prefix)
    vas = liftdiff.select_set(sess, 'sample:800', irfeats)
    aud = set(read_19())
    assert len(aud) == 19, len(aud)
    part = vas[a.part * a.chunk:(a.part + 1) * a.chunk]
    if a.limit:
        part = part[:a.limit]
    targets = [v for v in part if v in aud]
    mask = MASK[a.reset]
    print('[ld126] reset=%s mask=%d part=%d fns=%d targets=%d' % (a.reset, mask, a.part, len(part), len(targets)), flush=True)

    nat, was = sess.make_runners()

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    out = open(a.out, 'w')
    t0 = time.time()
    try:
        for va in part:
            if va in aud and mask:
                was._send('RESET %d' % mask)
                was.p.stdin.flush()
            if va not in aud:
                sess._run_one(nat, was, va, cases.PATTERN_NAMES, True)
                continue
            rec = sess._run_one(nat, was, va, cases.PATTERN_NAMES, True)
            v = liftdiff.make_record(sess, rec, irfeats)
            out.write(json.dumps({'reset': a.reset, 'va': hex(va), 'name': rec['name'], 'verdict': v.get('verdict'),
                                  'cases': [[c.get('pattern'), c.get('outcome'), c.get('native_status'), c.get('wasm_status')]
                                            for c in rec.get('cases', [])]}, default=str) + '\n')
            out.flush()
            print('[ld126] %s %s %s %.0fs' % (rec['name'], v.get('verdict'), a.reset, time.time() - t0), flush=True)
    finally:
        out.close()
        nat.close()
        was.close()
    print('[ld126] done %.0fs -> %s' % (time.time() - t0, a.out), flush=True)


if __name__ == '__main__':
    main()
