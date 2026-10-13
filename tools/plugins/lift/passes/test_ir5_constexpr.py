#!/usr/bin/env python3
"""ir5_patch.py の定数式処理 (PLG-F6-2 #545 の E2 / E5 修復) の回帰テスト + ネガティブコントロール。
  python3 test_ir5_constexpr.py            → 修復後 (作業ツリーの ir5_patch.py) が全ケース合格、かつ修復前 (git の BASE) が同じケースで不合格になること
  BASE=<rev> で修復前の版を選ぶ (既定 e64ef6f = 本修復の直前の main。 merge 後も NC が成立するよう commit 固定)。 BASE が取れない / 修復前の版が合格してしまう (= テストが欠陥を検出できない) 場合は exit 1。
ケースは Hardcore (block 19101) / Effector engine (block 18973) の実 IR から抜いた最小形:
  E5: `xor (i32 ptrtoint @g, i32 ptrtoint @g)` → 0 に畳まれた後の外側 `zext (i32 0 to i64)` が、内側を読み飛ばす旧実装では畳まれず、
      A9L が `%x = zext 0 to i64` (型の無い zext) を出す → emcc "expected type"
  E2: `bitcast (ptr @g to ptr)` の除去だけで行が変わる時に命令化の反復が止まり、外側の `icmp`/`zext` 定数式が残る → emcc "zext constexprs are no longer supported"
"""
import importlib.util, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = 'tools/plugins/lift/passes/ir5_patch.py'

CASE_E5 = ("  %17 = call i64 @function_180033cd8(i64 zext (i32 trunc (i64 add (i64 zext (i32 xor (i32 ptrtoint (ptr @g to i64), "
           "i32 ptrtoint (ptr @g to i64)) to i64), i64 64) to i32) to i64))")
CASE_E2 = ("  call void @__asm_rep_stosq_memset(ptr bitcast (ptr @g1 to ptr), i64 %0, i64 zext (i32 and (i32 trunc (i64 xor (i64 sub "
           "(i64 0, i64 zext (i1 icmp ult (i64 ptrtoint (ptr @g2 to i64), i64 ptrtoint (ptr @g1 to i64)) to i64)), i64 -1) to i32), i32 30) to i64))")


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.stderr, old = open(os.devnull, 'w'), sys.stderr   # pass の stage ログを抑える
    try:
        spec.loader.exec_module(m)
    finally:
        sys.stderr.close()
        sys.stderr = old
    return m


def quiet(f, *a):
    sys.stderr, old = open(os.devnull, 'w'), sys.stderr
    try:
        return f(*a)
    finally:
        sys.stderr.close()
        sys.stderr = old


def run_case(m, line):
    """fold (A8) → A9L (命令化) を ir5_patch の main と同じ順で当て、1 関数の本文を返す"""
    t = quiet(m.fold_xor_identity, line)[0]
    for _ in range(6):
        t, n = quiet(m.fold_const_ops, t)
        if n == 0:
            break
    t = re.sub(r'bitcast \(ptr (@[\w.$]+) to ptr\)', r'bitcast (ptr \1 to ptr)', t)
    body = 'define i64 @function_1(i64 %arg1) {\n' + t + '\n  ret i64 0\n}\n'
    blocks, res = quiet(m.lift_residual_constexpr, {'function_1': body})
    return blocks['function_1'], res


def defects(text):
    """修復後の出力に残ってはならない形"""
    d = []
    if re.search(r'= (zext|sext|trunc) [-0-9]', text):
        d.append('型の無い zext/sext/trunc (E5)')
    if re.search(r'(?<![\w])(zext|sext|trunc|icmp \w+|add|sub|xor|and|or) \(', text):
        d.append('残った定数式 (E2/E5)')
    return d


def check(m, label):
    bad = []
    for name, line in (('E5', CASE_E5), ('E2', CASE_E2)):
        out, res = run_case(m, line)
        d = defects(out) + (['A9L の残存集計が非 0: %s' % res] if res else [])
        print('  %s %s: %s' % (label, name, 'OK' if not d else 'defect=' + ', '.join(d)))
        bad += d
    return bad


def main():
    after = load(os.path.join(HERE, 'ir5_patch.py'), 'ir5_after')
    print('[修復後 (作業ツリー)]')
    bad_after = check(after, 'after')
    base = os.environ.get('BASE', 'e64ef6f')
    r = subprocess.run(['git', '-C', HERE, 'show', '%s:%s' % (base, TARGET)], capture_output=True, text=True)
    if r.returncode != 0:
        print('FAIL: 修復前の版 %s:%s が取れない (ネガティブコントロール不成立): %s' % (base, TARGET, r.stderr.strip()), file=sys.stderr)
        return 1
    with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False) as f:
        f.write(r.stdout)
    print('[修復前 (%s) — 欠陥を検出できること]' % base)
    before = load(f.name, 'ir5_before')
    os.unlink(f.name)
    bad_before = check(before, 'before')
    cases_before = sum(1 for c in (CASE_E5, CASE_E2) if defects(run_case(before, c)[0]) or run_case(before, c)[1])
    if bad_after:
        print('FAIL: 修復後でも欠陥が残る', file=sys.stderr)
        return 1
    if cases_before != 2:
        print('FAIL: 修復前の版が欠陥を出したのは 2 ケース中 %d 件 (ネガティブコントロール不成立: テストが欠陥を検出できていない)' % cases_before, file=sys.stderr)
        return 1
    print('test_ir5_constexpr: OK (修復後 欠陥 0 / 修復前 2 ケースとも欠陥を再現)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
