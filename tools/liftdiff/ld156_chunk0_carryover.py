#!/usr/bin/env python3
"""LD-156 (#3385): chunk 0 の 0x5d19e0 について、両側の持ち越しの中身を候補単位で切り分ける。

  python3 ld156_chunk0_carryover.py --native 1 --reset stk --out work/ld156/n1_stk.jsonl

cmd_batch の chunk 0 (sample:800 の 0〜399 件目) を 1 組の runner で流す (ld121_restart_probe.py と同じ開始状態)。
--native 1 は対象関数の直前に native runner を作り直す (LD-121 の native 作り直し)。
--reset は対象関数の直前に wasm 側の候補だけを SNAPSHOT 時点へ戻す (ld126_wasm_state.py と同じ mask)。
  none=0・stk=1・sta=2・img=4・all=7。
対照は --native 0 --reset none (LD-121 の none と同じ経路)。
"""
import argparse, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import liftdiff
from ldlib import cases, irtool
from ldlib.session import Session

TSV = os.path.join(HERE, 'results', 'ld58_m11_sample800_shards_t1.tsv')
TARGET = os.path.join(HERE, 'targets', 'm11.json')
MASK = {'none': 0, 'stk': 1, 'sta': 2, 'img': 4, 'all': 7}
NMASK = dict(MASK, mmap=8, sta_mmap=10, all_mmap=15)   # LD-229 (#4631): native 側の候補。mmap = anon rw-p mapping (ヒープ外)


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
    ap.add_argument('--native', type=int, choices=[0, 1], required=True)
    ap.add_argument('--reset', choices=sorted(MASK), required=True)
    ap.add_argument('--native-reset', choices=sorted(NMASK), default='none',
                    help='LD-209 (#4305): native 側の候補単位の戻し (NRESET)。native を作り直さない (--native 0) ときだけ使う')
    ap.add_argument('--out', required=True)
    ap.add_argument('--chunk', type=int, default=400)
    ap.add_argument('--part', type=int, default=0)
    a = ap.parse_args()
    if a.native_reset != 'none' and a.native:
        raise SystemExit('--native-reset は --native 0 のときだけ使う (作り直すと native の持ち越しは消える)')
    nmask = NMASK[a.native_reset]
    ns = argparse.Namespace(target=TARGET, state='auto')
    sess = Session(TARGET, shards=1, build=False, trace=True, timeout=10.0, state=liftdiff.state_path(ns))
    irfeats = {} if sess.t.get('clift') else irtool.ir_features(sess.t['ir'], sess.prefix)
    vas = liftdiff.select_set(sess, 'sample:800', irfeats)
    aud = set(read_19())
    assert len(aud) == 19, len(aud)
    part = vas[a.part * a.chunk:(a.part + 1) * a.chunk]
    targets = [v for v in part if v in aud]
    mask = MASK[a.reset]
    print('[ld156] native=%d reset=%s mask=%d native_reset=%s nmask=%d part=%d fns=%d targets=%d' % (
        a.native, a.reset, mask, a.native_reset, nmask, a.part, len(part), len(targets)), flush=True)

    nat, was = sess.make_runners()

    def restart_native():
        nonlocal nat
        n2, w2 = sess.make_runners()
        nat.close()
        nat = n2
        w2.close()

    def ack(r, key):
        if r is None or ('"%s"' % key) not in r:
            raise RuntimeError('%s 応答なし (%r)' % (key, r))
        return json.loads(r)

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    out = open(a.out, 'w')
    t0 = time.time()
    try:
        for va in part:
            ndiff = wdiff = None
            if va in aud:
                if a.native:
                    restart_native()
                if nmask:
                    nat._send('NRESET %d' % nmask)
                    nat.p.stdin.flush()
                    ndiff = ack(nat._recv(30.0), 'nreset')['diff']
                if mask:
                    was._send('RESET %d' % mask)
                    was.p.stdin.flush()
                    wdiff = ack(was._recv(30.0), 'reset')['diff']
            if va not in aud:
                sess._run_one(nat, was, va, cases.PATTERN_NAMES, True)
                continue
            rec = sess._run_one(nat, was, va, cases.PATTERN_NAMES, True)
            v = liftdiff.make_record(sess, rec, irfeats)
            out.write(json.dumps({'native': a.native, 'reset': a.reset, 'native_reset': a.native_reset,
                                  'native_reset_diff': ndiff, 'wasm_reset_diff': wdiff,
                                  'va': hex(va), 'name': rec['name'], 'verdict': v.get('verdict'),
                                  'cases': [[c.get('pattern'), c.get('outcome'), c.get('native_status'), c.get('wasm_status')]
                                            for c in rec.get('cases', [])]}, default=str) + '\n')
            out.flush()
            print('[ld156] %s %s native=%d reset=%s %.0fs' % (rec['name'], v.get('verdict'), a.native, a.reset, time.time() - t0), flush=True)
    finally:
        out.close()
        nat.close()
        was.close()
    print('[ld156] done %.0fs -> %s' % (time.time() - t0, a.out), flush=True)


if __name__ == '__main__':
    main()
