#!/usr/bin/env python3
"""ymm_vocab_check.py — VEX.256 packed-single 語彙 (vaddps / vsubps / vmulps) の bit-exact 単体検証 (#779 / KH-16)。

  python3 snapins/scripts/ymm_vocab_check.py [N] [SEED]      (既定 N=20000 SEED=1)

1. RetDec が出す宣言形 `declare i256 @__asm_v*ps(i256, i256)` を lift/gen_simd.py に通し、LLVM IR 定義を得る。
2. それを呼ぶ driver (load / call / store, align 1) を IR で書き、ホスト clang で obj 化する。
3. ホスト AVX2 の _mm256_*_ps と harness/ymm_vocab_harness.c で 32B 全 bit を突合する (NaN payload を含む)。
ネガコン (規則 41): (a) 語彙定義 (.i256.ll) を外す → リンク失敗 (FAIL) (b) vaddps 定義の fadd を fsub に
取り替える → 不一致 > 0 (FAIL) (c) 未対応の i256 宣言 (vfmadd231ps) → abort スタブが出て、呼ぶと abort (FAIL)。
exit 0 = 本検証が全 bit 一致 かつ 3 本のネガコンが FAIL。
成果物は snapins/work/ymm_vocab/ (gitignore 対象)。
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SNAP = os.path.dirname(HERE)
GEN = os.path.join(SNAP, 'lift', 'gen_simd.py')
HARN = os.path.join(SNAP, 'harness', 'ymm_vocab_harness.c')
W = os.path.join(SNAP, 'work', 'ymm_vocab')
# RetDec の宣言形 (suffix の .N / __N は overload 通番で、gen_simd は名前ではなくシグネチャで意味を決める)
OPS = [('__asm_vaddps', 'vaddps'), ('__asm_vsubps.2', 'vsubps'), ('__asm_vmulps__3', 'vmulps')]
CLANG = os.environ.get('CLANG', 'clang')
UNDEF_DECL = 'declare i256 @__asm_vfmadd231ps(i256, i256, i256)\n'
UNDEF_DRIVER = ('define void @drv_fma(ptr %pa, ptr %pr) {\n'
                '  %a = load i256, ptr %pa, align 1\n'
                '  %x = call i256 @__asm_vfmadd231ps(i256 %a, i256 %a, i256 %a)\n'
                '  store i256 %x, ptr %pr, align 1\n'
                '  ret void\n}\n')
UNDEF_MAIN = ('void drv_fma(const void *a, void *r);\n'
              'int main(void) { unsigned char a[32] = {0}, r[32]; drv_fma(a, r); return 0; }\n')


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
    return ''.join('declare i256 @%s(i256, i256) local_unnamed_addr\n' % sym for sym, _ in OPS)


def driver_ll():
    out = [decl_ll()]
    for sym, mn in OPS:
        out.append('define void @drv_%s(ptr %%pa, ptr %%pb, ptr %%pr) {\n'
                   '  %%a = load i256, ptr %%pa, align 1\n'
                   '  %%b = load i256, ptr %%pb, align 1\n'
                   '  %%r = call i256 @%s(i256 %%a, i256 %%b)\n'
                   '  store i256 %%r, ptr %%pr, align 1\n'
                   '  ret void\n}\n' % (mn, sym))
    return ''.join(out)


def build(name, ll_files, extra=()):
    exe = os.path.join(W, name)
    objs = []
    for ll in ll_files:
        o = ll[:-3] + '.o'
        sh([CLANG, '-O1', '-mavx2', '-c', ll, '-o', o], check=True)
        objs.append(o)
    r = sh([CLANG, '-O1', '-mavx2', '-o', exe, HARN, *objs, *extra, '-lm'], check=True)
    return exe, r


def run_harness(exe, n, seed):
    r = sh([exe, str(n), str(seed)])
    rows = {}
    for line in r.stdout.splitlines():
        m = re.match(r'^(v\w+) calls=(\d+) lanes=(\d+) mismatch=(\d+)$', line)
        if m:
            rows[m.group(1)] = int(m.group(4))
        print('  ' + line)
    return r.returncode, rows


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    os.makedirs(W, exist_ok=True)
    decl = write(os.path.join(W, 'decl.ll'), decl_ll())
    g = sh([sys.executable, GEN, decl, os.path.join(W, 'simd.c')], check=True)
    print(g.stdout.strip())
    if 'helpers 3, undefined(abort stub) 0' not in g.stdout:
        raise SystemExit('FAIL: gen_simd が 3 語彙を生成しなかった')
    simd_ll = os.path.join(W, 'simd.c.i256.ll')
    drv = write(os.path.join(W, 'driver.ll'), driver_ll())
    sh([CLANG, '-O1', '-mavx2', '-c', drv, '-o', os.path.join(W, 'driver.o')], check=True)
    drv_o = os.path.join(W, 'driver.o')

    # 本検証
    exe, r = build('harness', [simd_ll], [drv_o])
    print('== 本検証 (生成 IR 定義 vs ホスト AVX2) n=%d seed=%d' % (n, seed))
    rc, rows = run_harness(exe, n, seed)
    ok_main = rc == 0 and len(rows) == 3 and all(v == 0 for v in rows.values())

    # ネガコン (a): 語彙定義を外す → 未定義シンボルでリンク失敗
    print('== ネガコン (a) 語彙定義なし (リンクが通らなければ FAIL)')
    ra = sh([CLANG, '-O1', '-mavx2', '-o', os.path.join(W, 'harness_novocab'), HARN, drv_o, '-lm'])
    neg_a = ra.returncode != 0
    print('  link rc=%d -> %s' % (ra.returncode, 'FAIL (期待どおり)' if neg_a else 'PASS (想定外)'))

    # ネガコン (b): vaddps の fadd を fsub に取り替える → 不一致 > 0
    print('== ネガコン (b) vaddps の演算を fsub に改変 (不一致 > 0 で FAIL)')
    txt = open(simd_ll).read()
    i = txt.index('define i256 @__asm_vaddps(')
    j = txt.index('fadd', i)
    mut = write(os.path.join(W, 'simd_mut.ll'), txt[:j] + 'fsub' + txt[j + 4:])
    exe_b, _ = build('harness_mut', [mut], [drv_o])
    rb, rows_b = run_harness(exe_b, n, seed)
    neg_b = rb != 0 and rows_b.get('vaddps', 0) > 0
    print('  rc=%d vaddps mismatch=%s -> %s' % (rb, rows_b.get('vaddps'), 'FAIL (期待どおり)' if neg_b else 'PASS (想定外)'))

    # ネガコン (c): 未対応の i256 宣言は黙って通らず、abort スタブになって呼ぶと abort する
    print('== ネガコン (c) 未対応の i256 宣言 vfmadd231ps (abort スタブ化 + 呼出で abort しなければ FAIL)')
    gu = sh([sys.executable, GEN, write(os.path.join(W, 'decl_undef.ll'), UNDEF_DECL), os.path.join(W, 'simd_undef.c')], check=True)
    print('  ' + gu.stdout.strip())
    undef_ll = os.path.join(W, 'simd_undef.c.i256.ll')
    txt_u = open(undef_ll).read()
    stub_ok = 'undefined(abort stub) 1' in gu.stdout and 'define i256 @__asm_vfmadd231ps(' in txt_u and 'call void @abort()' in txt_u
    drv_u = write(os.path.join(W, 'driver_undef.ll'), UNDEF_DECL + UNDEF_DRIVER)
    main_u = write(os.path.join(W, 'undef_main.c'), UNDEF_MAIN)
    for src in (drv_u, undef_ll):
        sh([CLANG, '-O1', '-mavx2', '-c', src, '-o', src[:-3] + '.o'], check=True)
    exe_u = os.path.join(W, 'undef_call')
    sh([CLANG, '-O1', '-mavx2', '-o', exe_u, main_u, drv_u[:-3] + '.o', undef_ll[:-3] + '.o', '-lm'], check=True)
    ru = sh([exe_u])
    neg_c = stub_ok and ru.returncode != 0
    print('  stub=%s call rc=%d -> %s' % ('あり' if stub_ok else 'なし', ru.returncode, 'FAIL (期待どおり)' if neg_c else 'PASS (想定外)'))

    verdict = ok_main and neg_a and neg_b and neg_c
    print('== 判定: 本検証 %s / ネガコン(a) %s / ネガコン(b) %s / ネガコン(c) %s -> %s' % (
        'PASS' if ok_main else 'FAIL', 'FAIL' if neg_a else 'PASS', 'FAIL' if neg_b else 'PASS', 'FAIL' if neg_c else 'PASS',
        'PASS' if verdict else 'FAIL'))
    return 0 if verdict else 1


if __name__ == '__main__':
    raise SystemExit(main())
