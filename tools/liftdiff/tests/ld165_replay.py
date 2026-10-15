"""1 つの関数を、同じ shard で先に走る関数の列の後に走らせ、各 case の結果と wasm の経過秒を出す (LD-165 / #3585)。

使い方 (tools/liftdiff で実行。state は bootstate の出力・units は work/m11/boot_state.json):
  python3 tests/ld165_replay.py --state work/m11/boot_state.json --target 0x1060950 \
      --prefix 0x9773f0 --patterns s,p01 --reps 3
--prefix を空にすると、対象の関数だけを新しい runner で走らせる (単独)。
batch は chunk ごとに runner を作り直すので、chunk 内の shard の順序 (vas[i::shards]) を --prefix に並べれば同じ状態になる。
"""
import argparse
import sys

sys.path.insert(0, '.')
from ldlib.session import Session  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--state', required=True)
    ap.add_argument('--target', required=True)
    ap.add_argument('--prefix', default='')
    ap.add_argument('--patterns', default='')
    ap.add_argument('--reps', type=int, default=3)
    ap.add_argument('--target-json', default='targets/m11.json')
    ap.add_argument('--solo', action='store_true', help='--patterns の case だけを、毎回新しい runner の最初の case として走らせる')
    args = ap.parse_args()
    target = int(args.target, 16)
    prefix = [int(x, 16) for x in args.prefix.split(',') if x]
    pats = [p for p in args.patterns.split(',') if p]
    sess = Session(args.target_json, shards=1, build=False, timeout=10.0, state=args.state)
    if args.solo:
        from ldlib import cases
        name = sess.fn_name(target)
        sig = sess.sigs[name]
        for rep in range(args.reps):
            for p in pats:
                nat, was = sess.make_runners()
                line = cases.case_line(target, name, p, sig, trace=True, extra='')
                n = nat.run_cases([line], ['x'])[0]
                w = was.run_cases([line], ['x'])[0]
                print('rep%d solo %s native=%s wasm=%s wasm_elapsed=%s' % (rep, p, n.get('status'), w.get('status'), w.get('_elapsed_s')), flush=True)
                nat.close(); was.close()
        return
    for rep in range(args.reps):
        res = sess.run_functions(prefix + [target], None, with_refine=False)
        for c in res[target]['cases']:
            if pats and c['pattern'] not in pats:
                continue
            print('rep%d prefix=%d %s native=%s wasm=%s wasm_elapsed=%s' % (
                rep, len(prefix), c['pattern'], c['_n'].get('status'), c['_w'].get('status'), c['_w'].get('_elapsed_s')), flush=True)


if __name__ == '__main__':
    main()
