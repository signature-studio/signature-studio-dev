#!/usr/bin/env python3
"""p0c4_nega.py — CAB-196 継続 (P0c-4) の負論対照 (規則 41)

  python3 tools/plugins/p0c/p0c4_nega.py

何を壊すか: `--ext` が生成した dd (double-double) の「hi/lo ペア運搬
(__frontend_reg_store.fpr2l)」の lo 引数を全部 0.0 にする。hi だけ運ぶので
  - fpr2 の slot 運搬そのものは動く (hi は正しく届く)
  - dd の精度情報だけが捨てられる
この 1 操作で「運搬は健全で、残差は dd 演算系列由来」を切り分ける (REPORT §10.3)。

判定基準 (ネガティブコントロールとして有効 = 差分が出る):
  - 0x5dfdb0: dd OFF で buf_diff が x87fix 後 (841,305) と同水準に戻る
  - 0x5dfd30: dd OFF で buf_diff が x87fix 後 (38,099) を上回る
  = 運搬だけでは x87fix 後の値に「戻らない」ので、差分の原因は dd 演算系列。
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EXP = {'0x5dfd30': 38099, '0x5dfdb0': 841305}      # x87fix 後 (REPORT §9.3 実測)
TARGETS = ['0x5dfd30', '0x5dfdb0']


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        sys.stderr.write(r.stdout[-2000:] + r.stderr[-2000:])
        raise SystemExit('[FAIL] %s' % ' '.join(cmd))
    return r.stdout


def main():
    os.environ['TMPDIR'] = os.path.join(HERE, 'work', 'tmp')
    ext = os.path.join(HERE, 'work', 'ext')
    src = os.path.join(ext, 'k80.ext.ll')
    assert os.path.exists(src), 'run p0c4_e2e.py first'
    dst = os.path.join(ext, 'k80.nega.ll')
    t = open(src).read()
    # dd の lo 運搬を全滅させる (fpr2l の値引数を 0.0 に)
    n = len(re.findall(r'call void @__frontend_reg_store\.fpr2l\(i32 [^,]+, double [^)]+\)', t))
    t = re.sub(r'(call void @__frontend_reg_store\.fpr2l\(i32 [^,]+, double )[^)]+(\))',
               r'\g<1>0.000000e+00\g<2>', t)
    open(dst, 'w').write(t)
    print('[nega] rewrote %d fpr2l stores to 0.0 -> %s' % (n, dst))

    run(['llvm-as', dst, '-o', os.path.join(ext, 'k80.nega.bc')])
    print('[nega] llvm-as OK')
    run(['python3', os.path.join(HERE, 'k80_diff.py'), '--ir', dst,
         '--only', ','.join(TARGETS), '--cases', '2000'])
    out = run([os.path.join(HERE, 'work', 'diff', 'k80diff')])
    rows = {}
    for ln in out.split('\n')[1:]:
        f = ln.split(',')
        if len(f) >= 6 and f[0] in TARGETS:
            rows[f[0]] = (f[1], int(f[4]))

    print('[nega] %-10s %-9s %10s %10s %s'
          % ('kernel', 'class', 'dd OFF', 'x87fix後', '判定'))
    ok = True
    for va in TARGETS:
        if va not in rows:
            continue
        cls, bd = rows[va]
        # dd OFF が x87fix 後と同水準 (運搬は健全) または上回る (dd が悪化源)
        good = bd >= EXP[va] * 0.5
        ok = ok and good
        print('[nega] %-10s %-9s %10d %10d %s'
              % (va, cls, bd, EXP[va],
                 '運搬は健全・残差は dd 演算系列' if good else '想定外'))
    print('[nega] negative control %s' % ('OK' if ok else 'FAIL'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
