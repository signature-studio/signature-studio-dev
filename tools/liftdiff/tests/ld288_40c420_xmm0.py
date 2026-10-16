#!/usr/bin/env python3
"""LD-288 (#5888): 40c420 の wasm 戻り値が常に 0 になる原因 (lift 側) の再現と修正用 IR の生成。

  python3 tools/liftdiff/tests/ld288_40c420_xmm0.py <PE> <IN.ll> <OUT.ll>

原因: IR の `define i128 @function_40c420()` は引数を持たず、入口で `xor i128 0, 0` を使う。
      機械語は入口で xmm0 (double) を読む (movapd xmm3, xmm0 から始まる) ため、wasm は 0 から計算して 0 を返す。
修正: fix_xmm_args.py で当該関数だけ `double %in.xmm0` の署名に直し、
      wasm の入口 m11_tr_function_40c420 が引数 %a0 (raw 64bit) を double に bitcast して渡す。
      cases.MACHINE_ENTRY の 0x40c420 (['double']) と組で使う。
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
FX = os.path.join(ROOT, 'tools', 'plugins', 'lift', 'passes', 'fix_xmm_args.py')
OLD = '  %r = call i128 @function_40c420(double 0.0)\n  %z = trunc i128 %r to i64\n'
NEW = '  %x = bitcast i64 %a0 to double\n  %r = call i128 @function_40c420(double %x)\n  %z = trunc i128 %r to i64\n'


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    pe, src, dst = sys.argv[1:]
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    tmp = dst + '.fx.ll'
    r = subprocess.run([sys.executable, FX, src, tmp, '--pe', pe, '--only-funcs', 'function_40c420'],
                       capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    if r.returncode != 0:
        sys.exit('fix_xmm_args failed rc=%d: %s' % (r.returncode, r.stderr[-400:]))
    s = open(tmp).read()
    if s.count('define weak i128 @function_40c420(double %in.xmm0)') != 1:
        sys.exit('function_40c420 was not converted to (double %in.xmm0)')
    if s.count(OLD) != 1:
        sys.exit('trampoline m11_tr_function_40c420 pattern count != 1')
    open(dst, 'w').write(s.replace(OLD, NEW))
    os.remove(tmp)
    print('wrote', dst)


if __name__ == '__main__':
    main()
