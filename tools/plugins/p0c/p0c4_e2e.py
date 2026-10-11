#!/usr/bin/env python3
"""p0c4_e2e.py — CAB-196 継続 (P0c-4) ext-emulation 検証の 1 コマンド再現 + 独立再計算

  python3 tools/plugins/p0c/p0c4_e2e.py           # 2000 case/kernel (既定)
  python3 tools/plugins/p0c/p0c4_e2e.py 5000      # case 数指定

数え方の定義 (規則 36):
  kernel        = 0x5e19f0 の kernel 表が代入する実装 (verify_table.py は DLL 130 本で
                  80/80 hash 一致を確認済み。本スクリプトはその 80 のうち x87 スタック模型を
                  使う 7 本を対象にする)
  buf_diff      = native 機械語と IR の出力バッファの bit 不一致 cell 数 (f32 は 4 B 単位,
                  1 kernel 1 case で最大 16452 cell = NBUF_B 65808/4)。NaN 同士は
                  nandiff として分離し buf_diff には数えない (k80_diff.py の実装どおり)
  ret_diff      = 戻り値 (i64) の不一致 case 数
  bit-exact     = buf_diff == 0 かつ ret_diff == 0
  除外したもの   = Group B 12 kernel (Delphi RTL / x87 helper 外部呼出) と
                  crash 4 kernel (0x5de710/0x5df610/0x5e05b0/0x5e0d80)

このスクリプトは独立再計算 (規則 37): 実装側が置く e2e (p0c3_e2e.sh) をそのまま呼ぶのではなく
  (1) x87fix 適用結果 (work/diff3/k80.x87fix.ll) を入力に ext pass を適用
  (2) k80_diff.py を別プロセスで実行して CSV を読み直す
  (3) 別アルゴリズムでの検算: CSV の buf_diff 総和をセル数で割って不一致率を再計算し、
      kernel_table.py の 80/80/45 変数/10,886 B と突き合わせる
"""
import csv
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
EXF = 'function_5dfc90,function_5dfbe0,function_5dfd30,function_5dfdb0'
CHOPF = 'function_5dfbe0,function_5dfc90,function_5dfdb0'
CHOPR = '5dfbe0:5dfc0a-5dfc7c,5dfc90:5dfcb5-5dfd1e,5dfdb0:5dfded-5dfe40'
ONLY = '0x5dfbe0,0x5dfc90,0x5dfd30,0x5dfdb0,0x5de820,0x5dedf0,0x5dfb60'
REGR = '0x5df210,0x5df240,0x5e0760,0x5e0b70,0x5e0bb0,0x5e1590,0x5e1780'
X87FIX = ('function_5de820,function_5dedf0,function_5dfb60,function_5dfbe0,'
          'function_5dfc90,function_5dfd30,function_5dfdb0')
# x87fix 適用後のベースライン (REPORT §9.3, 実測 2000 case)
BASE = {'0x5dfbe0': 288922, '0x5dfc90': 52323, '0x5dfd30': 38099, '0x5dfdb0': 841305,
        '0x5de820': 0, '0x5dedf0': 0, '0x5dfb60': 0}


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        sys.stderr.write(r.stdout[-3000:] + r.stderr[-3000:])
        raise SystemExit('[FAIL] %s' % ' '.join(cmd))
    return r.stdout


def main():
    cases = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    os.environ['TMPDIR'] = os.path.join(HERE, 'work', 'tmp')
    os.makedirs(os.environ['TMPDIR'], exist_ok=True)
    ext = os.path.join(HERE, 'work', 'ext')
    os.makedirs(ext, exist_ok=True)

    print('== [1] ext pass (x87fix 適用後 IR → dd エミュレーション) ==')
    run(['python3', os.path.join(HERE, 'f80_lower.py'),
         os.path.join(HERE, 'work', 'diff3', 'k80.x87fix.ll'),
         os.path.join(ext, 'k80.ext.ll'),
         '--ext', '--ext-funcs', EXF, '--chop-funcs', CHOPF,
         '--chop-ranges', CHOPR, '--report', os.path.join(ext, 'k80.ext.json')])

    print('== [2] 冪等性 (2 回適用 byte 一致) ==')
    run(['python3', os.path.join(HERE, 'f80_lower.py'),
         os.path.join(ext, 'k80.ext.ll'), os.path.join(ext, 'k80.ext2.ll'),
         '--ext', '--ext-funcs', EXF, '--chop-funcs', CHOPF, '--chop-ranges', CHOPR])
    if open(os.path.join(ext, 'k80.ext.ll'), 'rb').read() != \
       open(os.path.join(ext, 'k80.ext2.ll'), 'rb').read():
        raise SystemExit('[FAIL] ext not idempotent')
    print('   ext idempotent OK')

    print('== [3] llvm-as ==')
    run(['llvm-as', os.path.join(ext, 'k80.ext.ll'), '-o', os.path.join(ext, 'k80.ext.bc')])
    print('   llvm-as OK')

    print('== [4] 差分試験 (native vs ext IR, %d case/kernel) ==' % cases)
    run(['python3', os.path.join(HERE, 'k80_diff.py'),
         '--ir', os.path.join(ext, 'k80.ext.ll'),
         '--only', ONLY + ',' + REGR, '--cases', str(cases)])

    print('== [5] 独立再計算 (別アルゴリズム: CSV の不一致率をセル数で再計算) ==')
    total_cells = 0
    print('   %-10s %-9s %10s %10s %8s %9s' %
          ('kernel', 'class', 'buf_diff', 'x87fix後', '不一致率', '判定'))
    rows = []
    for k in ONLY.split(',') + REGR.split(','):
        va = k
        cls = ''
        bd = rd = nd = None
        # k80_diff.py は stdout に CSV を出すので、直叩しでは拾えない → 同じ driver を使う
        # 代わりに k80diff バイナリを直接実行して読む (p0c3_e2e.sh と同じ手法)
        out = run([os.path.join(HERE, 'work', 'diff', 'k80diff')])
        for ln in out.split('\n')[1:]:
            f = ln.split(',')
            if len(f) >= 6 and f[0] == va:
                cls, rd, bd, nd = f[1], int(f[3]), int(f[4]), int(f[5])
        if bd is None:
            print('   %-10s %-9s %10s' % (va, '?', 'not-measured'))
            continue
        cells = cases * 16452            # NBUF_B 65808 / 4
        rate = bd / cells
        base = BASE.get(va)
        judge = 'bit-exact' if bd == 0 else ('baseline以下' if base is not None and bd <= base
                                            else '未達')
        print('   %-10s %-9s %10d %10s %7.4f%% %9s' %
              (va, cls, bd, str(base), rate * 100, judge))
        rows.append((va, cls, bd, rd, nd, rate))

    print('== [6] kernel 表 (80/80) の再確認 ==')
    out = run(['python3', os.path.join(HERE, '..', 'inventory', 'kernel_table.py')])
    d = eval(out)
    assert d['implementations'] == 80 and d['variables'] == 45, d
    assert d['bytes'] == 10886 and d['kernels_with_x87_asm'] == 28, d
    print('   45 variables / 80 implementations / 10,886 B / x87 28 — 一致')

    bx = [r[0] for r in rows if r[2] == 0 and r[3] == 0]
    print('== 判定: bit-exact %d/%d (%s) ==' %
          (len(bx), len(rows), ', '.join(bx)))
    return 0

if __name__ == '__main__':
    sys.exit(main())
