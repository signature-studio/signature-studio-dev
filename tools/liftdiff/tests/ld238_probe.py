"""LD-238 (#4423): LD-211 で segv のまま残った 5 関数 (668390 6683d0 784520 8e7e10 a965c0) を、
2 段の this 疑似オブジェクト (blob=vmt2) で native 実行する (動的プローブ)。

使い方: cd tools/liftdiff && FL_WIN64_DIR=... python3 tests/ld238_probe.py [--out work/ld238_probe.json]
前提: work/m11/sigs.json・work/m11/boot_state.json・build 済み (liftdiff.py build targets/m11.json)。
方法: 各関数について、整数 / ptr 引数 arg を 1 つだけ vmt2 の this にした case を arg ごと・xfill 1/0 で native 実行する。
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
os.chdir(HERE)
from ldlib import cases
from ldlib.session import Session

TARGETS = ['668390', '6683d0', '784520', '8e7e10', 'a965c0']
# IR 由来の署名が実引数と合わない関数の上書き (逆アセンブルで確認)。
# 784520: rcx=this・rdx=arg1・xmm2=単精度 float (arg2)、戻りは xmm0 の float。IR は float を落とし i128 としていた。
SIG_OVERRIDE = {'784520': {'ret': 'float', 'params': ['i64', 'i64', 'float']}}


def vmt2_line(va, name, arg, psig):
    # arg0 は常に vmt2 の this (rcx)。テスト対象の arg (arg>0) だけ別の有効ポインタを渡す (LD-238 §7: 旧版は arg0 に整数を渡していた)。
    kinds = cases.kinds_of(psig['params'])
    toks = []
    for i, k in enumerate(kinds):
        if k == 'd':
            toks.append('d:0x%x' % cases.FP_D[i % 4])
        elif k == 'f':
            toks.append('f:0x%x' % cases.FP_F[i % 4])
        elif i == 0:
            toks.append('i:a:0x%x' % cases.PTR_SLOTS[0])
        elif i == arg:
            toks.append('i:a:0x%x' % cases.PTR_SLOTS[1])
        else:
            toks.append('i:0x%x' % cases.SMALL[i])
    return 'id=%x:vmt2_%d fn=%x blob=vmt2 args=%s trace=0 xfill=%d sig=%s rt=%s' % (
        va, arg, va, ','.join(toks), 1, ','.join(psig['params']), psig['ret'])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='work/ld238_probe.json')
    ap.add_argument('--target', default='targets/m11.json')
    a = ap.parse_args()
    from ldlib import build_wasm
    build_wasm.ensure_native()  # 素材同梱の古い work/ld_native は仮 proc thunk を敷けず全 case が segv する (#3088)
    sess = Session(a.target, build=False, shards=1, trace=False, state='work/m11/boot_state.json')
    nat, was = sess.make_runners()
    res = {}
    try:
        for h in TARGETS:
            name = sess.prefix + h
            va = int(h, 16)
            sig = sess.sigs[name]
            ov = SIG_OVERRIDE.get(h)
            psig = {'ret': ov['ret'], 'params': ov['params']} if ov else {'ret': 'i64', 'params': sig['params'], 'defined': True}
            lines, ids = [], []
            for arg, ty in enumerate(psig['params']):
                if ty in ('i64', 'ptr'):
                    lines.append(vmt2_line(va, name, arg, psig))
                    ids.append('%s:vmt2:%d' % (h, arg))
            rn = nat.run_cases(lines, ids)
            rows = []
            for tag, r in zip(ids, rn):
                rows.append({'case': tag, 'status': r.get('status'), 'rax': r.get('rax'),
                             'rdx': r.get('rdx'), 'x0': r.get('x0'), 'fault': r.get('fault')})
            ok = [r for r in rows if r['status'] == 'ok']
            res[name] = {'n_ok': len(ok), 'n_run': len(rows), 'rows': rows}
            print(name, 'ok=%d/%d' % (len(ok), len(rows)), flush=True)
            for r in rows:
                print('   ', r['case'], r['status'], r['fault'], flush=True)
    finally:
        nat.close(); was.close()
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(res, open(a.out, 'w'), indent=1)
    print('wrote', a.out)


if __name__ == '__main__':
    main()
