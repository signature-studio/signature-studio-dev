"""LD-158 (#3470): ret=i128 の 39 関数について、native 実行の戻り後レジスタを実測する (動的プローブ)。

使い方: cd tools/liftdiff && python3 tests/ld158_ret_probe.py [--out work/ld158_probe.json]
前提: work/m11_ldfix/sigs.json・work/m11_ldfix/boot_state.json・build 済み (liftdiff.py build targets/m11.json)。

方法: 各関数を 11 pattern × xfill {1,0} で native 実行し、戻り後の rax / rdx / xmm0(x0) を取る。
  - rax_w : 戻り後 rax が入口値 SENTINEL と異なる実行が 1 件以上 (rax が書かれた)
  - x0_w  : 戻り後 xmm0 が入口値 (xfill=1 は 1.25、xfill=0 は 0) のどちらとも異なる実行が 1 件以上
  - rdx_w : rdx 入口値を知れる pattern (arg1 が小整数: z,s,p0,q0,vm0,u16) で、戻り後 rdx が
            入口値 (z は xfill で 0/0x12、他は 5) と異なる実行が 1 件以上
  書かれたことは『戻り値として使われた』ことを意味しない (呼出し側の利用は未確認)。本表は書き込みの実測。
"""
import argparse, json, os, subprocess, sys, collections

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
os.chdir(HERE)
from ldlib import cases, compare
from ldlib.session import Session

SENT = compare.SENTINEL
X_ONE = 0x3ff4000000000000  # xfill で xmm0 (int 引数 0) に入る 1.25
SMALL1 = {'z', 's', 'p0', 'q0', 'vm0', 'u16'}  # arg1 が整数の pattern (ptr でない)


def entry_rdx(pat, xfill):
    if pat == 'z':
        return 0x12 if xfill else 0
    return cases.SMALL[1]


def targets():
    s = json.load(open('work/m11_ldfix/sigs.json'))
    return sorted(k for k, v in s.items() if v['ret'] == 'i128' and v['defined'])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='work/ld158_probe.json')
    ap.add_argument('--target', default='targets/m11.json')
    ap.add_argument('--names', default='', help='既定は i128 戻りの 39 関数。陰性対照用に別の関数名をカンマ区切りで渡せる')
    a = ap.parse_args()
    sess = Session(a.target, build=False, shards=1, trace=False, state='work/m11_ldfix/boot_state.json')
    nat, was = sess.make_runners()
    names = a.names.split(',') if a.names else targets()
    res = {}
    try:
        for name in names:
            va = int(name[len(sess.prefix):], 16)
            sig = sess.sigs[name]
            psig = {'ret': 'i64', 'params': sig['params'], 'defined': True}
            lines, ids = [], []
            for xf in (1, 0):
                for p in cases.PATTERN_NAMES:
                    lines.append(cases.case_line(va, name, p, psig, trace=False, xfill=bool(xf)))
                    ids.append('%x:%s:%d' % (va, p, xf))
            rn = nat.run_cases(lines, ids)
            rows = []
            for ln, r in zip(ids, rn):
                p, xf = ln.split(':')[1], int(ln.split(':')[2])
                rows.append({'pattern': p, 'xfill': xf, 'status': r.get('status'),
                             'rax': r.get('rax'), 'rdx': r.get('rdx'), 'x0': r.get('x0')})
            ok = [r for r in rows if r['status'] == 'ok']
            rax_w = any(int(r['rax'], 16) != SENT for r in ok)
            x0_w = any(int(r['x0'], 16) not in (X_ONE, 0) for r in ok)
            rdx_w = any(int(r['rdx'], 16) != entry_rdx(r['pattern'], r['xfill'])
                        for r in ok if r['pattern'] in SMALL1)
            rdx_vals = sorted({r['rdx'] for r in ok})
            x0_vals = sorted({r['x0'] for r in ok})
            res[name] = {'va': hex(va), 'params': sig['params'], 'n_ok': len(ok), 'n_run': len(rows),
                         'rax_w': rax_w, 'rdx_w': rdx_w, 'x0_w': x0_w,
                         'distinct_rdx': len(rdx_vals), 'distinct_x0': len(x0_vals), 'rows': rows}
            print(name, 'ok=%d/%d' % (len(ok), len(rows)), 'rax_w=%d rdx_w=%d x0_w=%d' % (rax_w, rdx_w, x0_w),
                  'distinct_rdx=%d distinct_x0=%d' % (len(rdx_vals), len(x0_vals)), flush=True)
    finally:
        nat.close(); was.close()
    json.dump(res, open(a.out, 'w'), indent=1)
    print('wrote', a.out)


if __name__ == '__main__':
    main()
