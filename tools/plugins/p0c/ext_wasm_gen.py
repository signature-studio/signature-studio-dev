#!/usr/bin/env python3
"""ext_wasm_gen.py — f80_lower.py --ext の IR 生成器そのもの (_ext_arith / _ext_fist_round /
_ext_store_f32) から試験用 .ll を生成する (P0c-8 / #311)。

  python3 ext_wasm_gen.py OUT.ll [--break]

生成関数 t_c0 / t_c1 (chop=0/1):  void t_cN(double ah, double al, double bh, double bl, ptr o)
  o+0..47  : mul(h,l) add(h,l) sub(h,l)   (dd = round64 後の hi/lo)
  o+48     : i32  fist(mul)   (R10 clamp 込み)
  o+52,56  : f32  store(mul) / store(add)
ext_core_test.c の検証対象 [1][2][3][4][5] と同一の演算を、実 pass が出す IR で実行する。

--break: ネガティブコントロール。Dekker 分割定数 2^27+1 (0x41A0000002000000) を 2^26+1
  (0x4190000002000000) に壊す。これで native x87 との bit 比較が FAIL しなければならない。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import f80_lower as F  # noqa: E402


def gen_func(chop, brk):
    mi = F.ExtMinter()
    ext = {'%a', '%b'}
    L = []
    for nm, op, base in (('mul', 'fmul', '%m'), ('add', 'fadd', '%s'), ('sub', 'fsub', '%d')):
        seq = F._ext_arith(op, '%a', '%b', base, ext, mi, bool(chop), op == 'fmul')
        L += seq
    # fist(mul) / f32(mul) / f32(add): 結果ペア %m / %s は ext に加える
    ext2 = ext | {'%m', '%s', '%d'}
    n = F._ext_fist_round('%m', mi, bool(chop), L)
    L.append('  %%fi = fptosi double %s to i32' % n)
    fm = F._ext_store_f32('%m', mi, bool(chop), L)
    fa = F._ext_store_f32('%s', mi, bool(chop), L)
    del ext2
    for off, nm in ((0, '%m.x87h'), (8, '%m.x87l'), (16, '%s.x87h'), (24, '%s.x87l'),
                    (32, '%d.x87h'), (40, '%d.x87l')):
        p = '%%po%d' % off
        L.append('  %s = getelementptr i8, ptr %%o, i64 %d' % (p, off))
        L.append('  store double %s, ptr %s, align 8' % (nm, p))
    L.append('  %pi = getelementptr i8, ptr %o, i64 48')
    L.append('  store i32 %fi, ptr %pi, align 4')
    L.append('  %pf1 = getelementptr i8, ptr %o, i64 52')
    L.append('  store float %s, ptr %%pf1, align 4' % fm)
    L.append('  %pf2 = getelementptr i8, ptr %o, i64 56')
    L.append('  store float %s, ptr %%pf2, align 4' % fa)
    body = '\n'.join(L)
    if brk:
        body = body.replace('0x41A0000002000000', '0x4190000002000000')
    return ('define void @t_c%d(double %%a.x87h, double %%a.x87l, double %%b.x87h, double %%b.x87l, ptr %%o) {\n'
            'entry:\n%s\n  ret void\n}\n' % (chop, body))


def main():
    out = sys.argv[1]
    brk = '--break' in sys.argv[2:]
    txt = ''.join(gen_func(c, brk) for c in (0, 1))
    txt += ('\ndeclare double @llvm.rint.f64(double)\ndeclare double @llvm.floor.f64(double)\n'
            'declare double @llvm.ceil.f64(double)\ndeclare double @llvm.trunc.f64(double)\n'
            'declare float @nextafterf(float, float)\n')
    open(out, 'w').write(txt)
    print('[ext_wasm_gen] %s: %d lines%s' % (out, txt.count('\n'), ' (BROKEN: negative control)' if brk else ''))


if __name__ == '__main__':
    main()
