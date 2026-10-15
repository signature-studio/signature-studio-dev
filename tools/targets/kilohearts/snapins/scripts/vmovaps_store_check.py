#!/usr/bin/env python3
"""vmovaps_store_check.py — VEX.256 vmovaps の store 形 (`vmovaps ymmword ptr [m], ymm`) の bit-exact 単体検証 (#3358 / KH-54)。

  python3 snapins/scripts/vmovaps_store_check.py [N] [SEED]      (既定 N=20000 SEED=1)

1. RetDec 形 (typed pointer・`%old = load i256, i256* %p` + `call void @__asm_vmovaps(i256 %old, i256 %val)`) の IR を書く。
2. lift/kh_passes.py の pass_storelow を実際に通し、呼出が 32B の `store i256` に復元されることを確かめる。
3. 復元 IR を (typed → opaque ptr 変換して) ホスト clang で obj 化し、ホスト AVX2 の 32B ロード→ストアと 32B 全 bit 突合する
   (harness/vmovaps_store_harness.c)。
ネガコン (規則 41): (a) pass を外す → 呼出が残り abort スタブへ落ちて FAIL (b) 復元 store を no-op に改変 → 不一致 > 0 で FAIL。
exit 0 = 本検証が全 bit 一致 かつ 2 本のネガコンが FAIL。
成果物は snapins/work/vmovaps_store/ (gitignore 対象)。
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SNAP = os.path.dirname(HERE)
LIFT = os.path.join(SNAP, 'lift')
HARN = os.path.join(SNAP, 'harness', 'vmovaps_store_harness.c')
W = os.path.join(SNAP, 'work', 'vmovaps_store')
CLANG = os.environ.get('CLANG', 'clang')
sys.path.insert(0, LIFT)

# RetDec 形 (LLVM12 typed pointer)。call は overload 接尾 .2 / __2 のどちらも許容される (pass 側で吸収)。
DRIVER_TYPED = ('define void @fn_store(i256* %ps, i256* %pd) {\n'
                '  %old = load i256, i256* %pd, align 1\n'
                '  %val = load i256, i256* %ps, align 1\n'
                '  call void @__asm_vmovaps.2(i256 %old, i256 %val)\n'
                '  ret void\n}\n')
ABORT_STUB = ('declare void @abort() noreturn\n'
              'define void @__asm_vmovaps.2(i256 %a0, i256 %a1) {\n  call void @abort()\n  unreachable\n}\n')


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


def run_pass(text):
    """kh_passes.pass_storelow を 1 関数に通し、復元後の .ll 全文を返す。"""
    import kh_passes as kp
    lines = text.split('\n')
    start = next(i for i, l in enumerate(lines) if l.startswith('define void @fn_store('))
    end = next(i for i in range(start, len(lines)) if lines[i] == '}')
    fn = kp.Fn(0x1000, start, end)
    cx = kp.Ctx(None, lines, {})
    kp.pass_storelow(cx, fn, None)
    for k, v in fn.sub.items():
        lines[k] = v
    return '\n'.join(lines), cx.report.get('storelow', {})


def to_opaque(text):
    return re.sub(r'i256\*', 'ptr', text)


def build_exe(name, ll_text, extra_ll=()):
    exe = os.path.join(W, name)
    srcs = []
    main_ll = write(os.path.join(W, name + '.ll'), to_opaque(ll_text))
    sh([CLANG, '-O1', '-mavx2', '-c', main_ll, '-o', main_ll[:-3] + '.o'], check=True)
    srcs.append(main_ll[:-3] + '.o')
    for ll in extra_ll:
        o = ll + '.o'
        sh([CLANG, '-O1', '-mavx2', '-c', ll, '-o', o], check=True)
        srcs.append(o)
    sh([CLANG, '-O1', '-mavx2', '-o', exe, HARN, *srcs, '-lm'], check=True)
    return exe


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    os.makedirs(W, exist_ok=True)
    # 本検証
    restored, rep = run_pass(DRIVER_TYPED)
    ok_restore = ('call void @__asm_vmovaps' not in restored and
                  'store i256 %val, ptr %pd, align 1' in to_opaque(restored) and rep.get('vmovaps256') == 1)
    print('[kh_passes storelow] %s' % rep)
    print('== 本検証 (pass 復元 32B store vs ホスト AVX2) n=%d seed=%d' % (n, seed))
    print('  復元 IR: %s' % ('store 1 件 (call なし)' if ok_restore else 'NG'))
    exe = build_exe('harness', restored)
    r = sh([exe, str(n), str(seed)])
    print('  ' + r.stdout.strip())
    ok_main = ok_restore and r.returncode == 0 and 'mismatch=0' in r.stdout

    # ネガコン (a): pass を外す → 呼出が残り、abort スタブへ落ちて FAIL
    print('== ネガコン (a) pass を外す (呼出が残り abort スタブで FAIL)')
    exe_a = build_exe('harness_nopass', DRIVER_TYPED + ABORT_STUB)
    ra = sh([exe_a, str(n), str(seed)])
    neg_a = ra.returncode != 0
    print('  rc=%d -> %s' % (ra.returncode, 'FAIL (期待どおり)' if neg_a else 'PASS (想定外)'))

    # ネガコン (b): 復元 store の値を no-op に改変 → 不一致 > 0
    print('== ネガコン (b) 復元 store を no-op に改変 (不一致 > 0 で FAIL)')
    mut = restored.replace('store i256 %val', '%kdead = add i256 0, 0 ; %val', 1)
    exe_b = build_exe('harness_mut', mut)
    rb = sh([exe_b, str(n), str(seed)])
    print('  ' + rb.stdout.strip().splitlines()[-1])
    neg_b = rb.returncode != 0
    print('  rc=%d -> %s' % (rb.returncode, 'FAIL (期待どおり)' if neg_b else 'PASS (想定外)'))

    verdict = ok_main and neg_a and neg_b
    print('== 判定: 本検証 %s / ネガコン(a) %s / ネガコン(b) %s -> %s' % (
        'PASS' if ok_main else 'FAIL', 'FAIL' if neg_a else 'PASS', 'FAIL' if neg_b else 'PASS', 'PASS' if verdict else 'FAIL'))
    return 0 if verdict else 1


if __name__ == '__main__':
    raise SystemExit(main())
