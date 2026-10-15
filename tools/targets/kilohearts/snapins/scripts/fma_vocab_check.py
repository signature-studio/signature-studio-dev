#!/usr/bin/env python3
"""fma_vocab_check.py — FMA3 scalar 語彙 (census の xmm FMA 7 mnemonic) の bit-exact 単体検証 (#3256 / KH-48)。

  python3 snapins/scripts/fma_vocab_check.py [N] [SEED]      (既定 N=20000 SEED=1)

1. RetDec 形の宣言 `declare i128 @__asm_vf*(i128, i128, i128)` を 1 ファイルにまとめ、lift/gen_simd.py に通して C 実装を得る。
   対象 = REPORT §12 の census (f354504c)。vfmadd の ymm 形は census 0 件のため対象外。
2. ホスト clang (-mfma -mavx2 -ffp-contract=off) で C をコンパイルし、harness/fma_vocab_harness.c が直接呼ぶ。
3. ホスト FMA3 命令 (_mm_fmadd_ss 等) と 128bit 全 bit を突合する (上位 lane は dest、NaN payload を含む)。
   NaN payload だけの差は nan_only に別計上する (mismatch には含めて判定する = 緩めない)。
判定: 非 NaN の bit は 128bit 全 bit 一致 (mismatch - nan_only)。NaN 同士の payload だけの差は nan_only に
別計上して判定から外す (wasm 仕様は算術結果の NaN payload を決定的に規定しない。緩和の件数は REPORT_APPENDIX §12-2)。
ネガコン (規則 41): (a) 語彙定義 (simd.c) を外す → リンク失敗 (FAIL)
(b) vfmadd213ss の fmaf を x*y+z (単精度の中間丸め) に改変 → 不一致 > 0 (FAIL)
(c) vfmadd213ss の被演算子順を 231 形 (s2*s3+d) に改変 → 不一致 > 0 (FAIL)
exit 0 = 本検証の 7 語彙が全 bit 一致 かつ 3 本のネガコンが FAIL。
成果物は snapins/work/fma_vocab/ (gitignore 対象)。
"""
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SNAP = os.path.dirname(HERE)
GEN = os.path.join(SNAP, 'lift', 'gen_simd.py')
LIFT = os.path.join(SNAP, 'lift')
HARN = os.path.join(SNAP, 'harness', 'fma_vocab_harness.c')
W = os.path.join(SNAP, 'work', 'fma_vocab')
MNEMONICS = ['vfmadd213sd', 'vfmadd213ss', 'vfmsub213ss', 'vfmadd231sd', 'vfmadd231ss', 'vfnmadd231sd', 'vfmadd132sd']
CLANG = os.environ.get('CLANG', 'clang')
CFLAGS = ['-O1', '-mfma', '-mavx2', '-ffp-contract=off']
# gen_simd.py の HEAD は <emscripten.h> を無条件に include する。ホスト検証用に KEEPALIVE だけ空定義する shim
SHIM = '#define EMSCRIPTEN_KEEPALIVE\n'
FMA213SS = 'fmaf(x1.f[0], x0.f[0], x2.f[0])'
def bad(v):
    """非 NaN の bit 不一致件数 (mismatch から NaN payload だけの差を除く)"""
    return v[0] - v[1]


ROW = re.compile(r'^(v\w+) calls=(\d+) bits=128 mismatch=(\d+) nan_only=(\d+)$')


def sh(cmd, check=False):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if check and r.returncode:
        print(r.stdout[-2000:], r.stderr[-3000:])
        raise SystemExit('FAILED: ' + ' '.join(cmd)[:200])
    return r


def write(path, text):
    with open(path, 'w') as f:
        f.write(text)
    return path


def decl_ll():
    return ''.join('declare i128 @__asm_%s(i128, i128, i128)\n' % m for m in MNEMONICS)


def compile_c(src, obj):
    sh([CLANG, *CFLAGS, '-I', LIFT, '-I', os.path.join(W, 'inc'), '-c', src, '-o', obj], check=True)
    return obj


def build(name, objs):
    exe = os.path.join(W, name)
    sh([CLANG, *CFLAGS, '-o', exe, HARN, *objs, '-lm'], check=True)
    return exe


def run_harness(exe, n, seed):
    r = sh([exe, str(n), str(seed)])
    rows = {}
    for line in r.stdout.splitlines():
        m = ROW.match(line)
        if m:
            rows[m.group(1)] = (int(m.group(3)), int(m.group(4)))
        print('  ' + line)
    return r.returncode, rows


def mutate_213ss(simd_c, old, new, label):
    txt = open(simd_c).read()
    i = txt.index('EX u128 __asm_vfmadd213ss(')
    j = txt.index('\n', i) if '\n' in txt[i:] else len(txt)
    line = txt[i:j]
    if line.count(old) != 1:
        raise SystemExit('FAIL: mutation %s の置換対象が 1 件でない (%d)' % (label, line.count(old)))
    return txt[:i] + line.replace(old, new) + txt[j:]


def main():
    t0 = time.time()
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    os.makedirs(os.path.join(W, 'inc'), exist_ok=True)
    write(os.path.join(W, 'inc', 'emscripten.h'), SHIM)
    decl = write(os.path.join(W, 'decl.ll'), decl_ll())
    g = sh([sys.executable, GEN, decl, os.path.join(W, 'simd.c')], check=True)
    print(g.stdout.strip())
    if 'helpers 7, undefined(abort stub) 0' not in g.stdout:
        raise SystemExit('FAIL: gen_simd が 7 語彙を生成しなかった')
    simd_c = os.path.join(W, 'simd.c')
    simd_o = compile_c(simd_c, os.path.join(W, 'simd.o'))

    # 本検証 (生成 C 実装 vs ホスト FMA3)
    exe = build('harness', [simd_o])
    print('== 本検証 (生成 C 実装 vs ホスト FMA3・128bit 全 bit・NaN 含む) n=%d seed=%d' % (n, seed))
    rc, rows = run_harness(exe, n, seed)
    ok_main = rc == 0 and len(rows) == len(MNEMONICS) and all(bad(v) == 0 for v in rows.values())
    nan_total = sum(v[1] for v in rows.values())

    # ネガコン (a): 語彙定義 (simd.c) を外す → 未定義シンボルでリンク失敗
    print('== ネガコン (a) 語彙定義なし (リンクが通らなければ FAIL)')
    ra = sh([CLANG, *CFLAGS, '-o', os.path.join(W, 'harness_novocab'), HARN, '-lm'])
    neg_a = ra.returncode != 0
    print('  link rc=%d -> %s' % (ra.returncode, 'FAIL (期待どおり)' if neg_a else 'PASS (想定外)'))

    # ネガコン (b): vfmadd213ss の fmaf を x*y+z (単精度 2 段丸め) に改変 → 不一致 > 0
    print('== ネガコン (b) vfmadd213ss の fmaf を単精度 2 段丸め x*y+z に改変 (不一致 > 0 で FAIL)')
    mut_b = write(os.path.join(W, 'simd_mut_b.c'),
                  mutate_213ss(simd_c, FMA213SS, '((x1.f[0] * x0.f[0]) + x2.f[0])', 'b'))
    exe_b = build('harness_mut_b', [compile_c(mut_b, os.path.join(W, 'simd_mut_b.o'))])
    rb, rows_b = run_harness(exe_b, n, seed)
    neg_b = rb != 0 and bad(rows_b.get('vfmadd213ss', (0, 0))) > 0
    print('  rc=%d vfmadd213ss mismatch=%s -> %s' % (rb, rows_b.get('vfmadd213ss'), 'FAIL (期待どおり)' if neg_b else 'PASS (想定外)'))

    # ネガコン (c): vfmadd213ss の被演算子順を 231 形 (s2*s3 + d) に改変 → 不一致 > 0
    print('== ネガコン (c) vfmadd213ss の被演算子順を 231 形 fmaf(s2, s3, d) に改変 (不一致 > 0 で FAIL)')
    mut_c = write(os.path.join(W, 'simd_mut_c.c'),
                  mutate_213ss(simd_c, FMA213SS, 'fmaf(x1.f[0], x2.f[0], x0.f[0])', 'c'))
    exe_c = build('harness_mut_c', [compile_c(mut_c, os.path.join(W, 'simd_mut_c.o'))])
    rc_c, rows_c = run_harness(exe_c, n, seed)
    neg_c = rc_c != 0 and bad(rows_c.get('vfmadd213ss', (0, 0))) > 0
    print('  rc=%d vfmadd213ss mismatch=%s -> %s' % (rc_c, rows_c.get('vfmadd213ss'), 'FAIL (期待どおり)' if neg_c else 'PASS (想定外)'))

    verdict = ok_main and neg_a and neg_b and neg_c
    print('== 判定: 本検証 %s (非 NaN bit 不一致 %d / NaN payload のみの差 %d 件) / ネガコン(a) %s / ネガコン(b) %s / ネガコン(c) %s -> %s' % (
        'PASS' if ok_main else 'FAIL', sum(bad(v) for v in rows.values()), nan_total, 'FAIL' if neg_a else 'PASS', 'FAIL' if neg_b else 'PASS',
        'FAIL' if neg_c else 'PASS', 'PASS' if verdict else 'FAIL'))
    print('== wall %.2f 秒 (N=%d 語彙 %d 件/各)' % (time.time() - t0, n, len(MNEMONICS)))
    return 0 if verdict else 1


if __name__ == '__main__':
    raise SystemExit(main())
