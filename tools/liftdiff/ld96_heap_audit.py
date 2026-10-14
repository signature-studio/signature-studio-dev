#!/usr/bin/env python3
"""LD-96 (#2258): sample:800 (shard 1) で 19 関数の verdict が揺れる件の heap 残り計測。

  python3 ld96_heap_audit.py --mode full --out work/ld96/full.jsonl   # cmd_batch と同じ 400 件 chunk で全体を流す
  python3 ld96_heap_audit.py --mode solo --out work/ld96/solo.jsonl   # 19 関数だけを 1 回の run で流す (対照)

前提: work/ld_native・work/m11/ld_wasm.* が rt/ld_core.h の現版で build 済み (liftdiff.py build targets/m11.json)。
計測: 19 関数 (results/ld58_m11_sample800_shards_t1.tsv で r1=match・s1=mismatch) の全 case に audit=1 を付ける。
audit=1 の case は、復元の前に「高水位より外側に残った非 0 バイト数」(heap_left) を native / wasm 別に出す。
他の case の挙動・出力は変えない (audit 無しの case は従来どおり)。
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
    ap.add_argument('--mode', choices=['full', 'solo'], required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--chunk', type=int, default=400)
    ap.add_argument('--only-part', type=int, default=None, help='full: この chunk だけ流す (chunk は run_functions ごとに新しいランナー)')
    ap.add_argument('--audit-part', type=int, default=None,
                    help='full: この chunk の全関数の先頭 case (pattern z) にも audit=1 を付ける (書き手の特定用)')
    a = ap.parse_args()
    ns = argparse.Namespace(target=TARGET, state='auto')
    sess = Session(TARGET, shards=1, build=False, trace=True, timeout=10.0, state=liftdiff.state_path(ns))
    irfeats = {} if sess.t.get('clift') else irtool.ir_features(sess.t['ir'], sess.prefix)
    vas = liftdiff.select_set(sess, 'sample:800', irfeats)
    aud = set(read_19())
    assert len(aud) == 19, len(aud)

    if a.mode == 'full':
        parts = [vas[i:i + a.chunk] for i in range(0, len(vas), a.chunk)]
    else:
        parts = [[v for v in vas if v in aud]]
    part_first = set(parts[a.audit_part]) if a.audit_part is not None else set()
    orig = cases.case_line

    def patched(va, name_prefix, pattern, sig, trace=True, xfill=True, stkfill=None, extra=''):
        if va in aud or (va in part_first and pattern == 'z'):
            extra = (extra + ' ' if extra else '') + 'audit=1'
        return orig(va, name_prefix, pattern, sig, trace=trace, xfill=xfill, stkfill=stkfill, extra=extra)
    cases.case_line = patched

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    out = open(a.out, 'w')
    t0 = time.time()
    print('[ld96] mode=%s parts=%s sizes=%s audit_part=%s' % (a.mode, len(parts), [len(p) for p in parts], a.audit_part), flush=True)
    for pi, part in enumerate(parts):
        if a.only_part is not None and pi != a.only_part:
            continue
        res = sess.run_functions(part, None, with_refine=True)
        for va in part:
            if va not in aud and va not in part_first:
                continue
            rec = res[va]
            cs = []
            for c in rec.get('cases', []):
                cs.append({'pattern': c.get('pattern'), 'outcome': c.get('outcome'),
                           'native_left': (c.get('_n') or {}).get('heap_left'),
                           'wasm_left': (c.get('_w') or {}).get('heap_left'),
                           'detail': {k: v for k, v in c.items() if not k.startswith('_')} if va in aud else None})
            v = liftdiff.make_record(sess, rec, irfeats)
            out.write(json.dumps({'mode': a.mode, 'part': pi, 'va': hex(va), 'name': rec['name'],
                                  'verdict': v.get('verdict'), 'cases': cs}, default=str) + '\n')
        out.flush()
        print('[ld96] part %d done (%d fn) %.0fs' % (pi, len(part), time.time() - t0), flush=True)
    out.close()
    print('[ld96] done %.0fs -> %s' % (time.time() - t0, a.out), flush=True)


if __name__ == '__main__':
    main()
