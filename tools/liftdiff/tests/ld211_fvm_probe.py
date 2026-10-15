"""LD-211 (#4378): ret=i128 のうち全 pattern が native segv で判定不能だった 11 関数について、
this 疑似オブジェクト (blob=vmt、arena+0x1000 → VMT arena+0x2000) を引数に与えて native 実行し、
戻り後の rax / rdx / xmm0 (x0) と segv の fault アドレスを取る (動的プローブ)。

使い方: cd tools/liftdiff && FL_WIN64_DIR=... python3 tests/ld211_fvm_probe.py [--out work/ld211_probe.json]
前提: work/m11/sigs.json・work/m11/boot_state.json・build 済み (liftdiff.py build targets/m11.json)。
方法: 各関数について (a) 整数引数 arg を 1 つだけ this にした case (arg ごと・xfill 1/0)、
      (b) 全整数引数を this にした case (各引数は別の arena 領域) を native 実行する。
      書換えは『戻り値として使われた』を意味しない (本表は書き込みの実測)。
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
os.chdir(HERE)
from ldlib import cases, compare
from ldlib.session import Session

SENT = compare.SENTINEL
X_ONE = 0x3ff4000000000000
TARGETS = ['45e1a0', '45e280', '45e2e0', '45eb00', '45ecc0', '45ed20',
           '668390', '6683d0', '784520', '8e7e10', 'a965c0']


def allptr_line(va, name, sig):
    kinds = cases.kinds_of(sig['params'])
    toks = []
    for i, k in enumerate(kinds[:len(sig['params'])]):
        if k == 'i':
            toks.append('i:a:0x%x' % (cases.PTR_SLOTS[0] + 0x40 * i))
        else:
            toks.append('d:0x%x' % cases.FP_D[i % 4] if k == 'd' else 'f:0x%x' % cases.FP_F[i % 4])
    return 'id=%x:allptr fn=%x blob=vmt args=%s trace=0 xfill=1 sig=%s rt=i64' % (
        va, va, ','.join(toks), ','.join(sig['params']))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='work/ld211_probe.json')
    ap.add_argument('--target', default='targets/m11.json')
    a = ap.parse_args()
    sess = Session(a.target, build=False, shards=1, trace=False, state='work/m11/boot_state.json')
    nat, was = sess.make_runners()
    res = {}
    try:
        for h in TARGETS:
            name = sess.prefix + h
            va = int(h, 16)
            sig = sess.sigs[name]
            psig = {'ret': 'i64', 'params': sig['params'], 'defined': True}
            lines, ids = [], []
            for xf in (1, 0):
                for arg, ty in enumerate(sig['params']):
                    if ty in ('i64', 'ptr'):
                        lines.append(cases.fvm_line(va, name, arg, psig, trace=False, xfill=bool(xf)))
                        ids.append('%s:fvm%d:%d' % (h, arg, xf))
            lines.append(allptr_line(va, name, sig))
            ids.append('%s:allptr:1' % h)
            rn = nat.run_cases(lines, ids)
            rows = []
            for ln, r in zip(ids, rn):
                _, tag, xf = ln.split(':')
                rows.append({'case': tag, 'xfill': int(xf), 'status': r.get('status'),
                             'rax': r.get('rax'), 'rdx': r.get('rdx'), 'x0': r.get('x0'),
                             'fault': r.get('fault')})
            ok = [r for r in rows if r['status'] == 'ok']
            res[name] = {'n_ok': len(ok), 'n_run': len(rows), 'rows': rows,
                         'x0_w': any(int(r['x0'], 16) not in (X_ONE, 0) for r in ok),
                         'rax_w': any(int(r['rax'], 16) != SENT for r in ok)}
            print(name, 'ok=%d/%d' % (len(ok), len(rows)), 'rax_w=%s x0_w=%s' % (res[name]['rax_w'], res[name]['x0_w']),
                  flush=True)
    finally:
        nat.close(); was.close()
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(res, open(a.out, 'w'), indent=1)
    print('wrote', a.out)


if __name__ == '__main__':
    main()
