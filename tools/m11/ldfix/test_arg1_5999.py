#!/usr/bin/env python3
"""test_arg1_5999.py — judge_arg1_5999.py の規則を固定する (#5999)。

規則が壊れれば落ちる:
  - 修正前の loop-carry 形 (第 1 引数が %arg1 か境界値) は NG
  - fix_f552a0.py の適用後 (第 1 引数が *%arg1 の load) は OK
  - 6 件でない IR は fail-closed (終了コード 2)
  - align 付き store/load を経由した *arg1 は OK (旧正規表現は落ちる)
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
JUDGE = os.path.join(HERE, 'judge_arg1_5999.py')
FIX = os.path.join(HERE, 'fix_f552a0.py')

# 最小の function_f552a0。ループ内 5 件 + 脱出後 1 件 (計 6 件)。
# 修正前の形: 第 1 引数が loop-carry の reload (rcx.0/rcx.1) で、そのスロットは %arg1 と %21 を受ける。
BEFORE = '''define i64 @function_f552a0(i64 %arg1) local_unnamed_addr {
entry:
  %rcx.0.reg2mem = alloca i64
  %rcx.1.reg2mem = alloca i64
  %rsi.0.reg2mem = alloca i64
  %rdi.0.reg2mem = alloca i64
  store i64 %arg1, ptr %rcx.0.reg2mem
  store i64 0, ptr %rsi.0.reg2mem
  store i64 4, ptr %rdi.0.reg2mem
  br label %loop
loop:
  %rdi.0.reload = load i64, ptr %rdi.0.reg2mem
  %rsi.0.reload = load i64, ptr %rsi.0.reg2mem
  %rcx.0.reload = load i64, ptr %rcx.0.reg2mem
  %5 = call i64 @function_12df530(i64 %rcx.0.reload, i64 %rsi.0.reload)
  %10 = call i64 @function_12df530(i64 %rcx.0.reload, i64 %rsi.0.reload)
  %21 = add i64 %5, -1
  store i64 %21, ptr %rcx.1.reg2mem
  %24 = call i64 @function_12df530(i64 %21, i64 %rsi.0.reload)
  store i64 %rcx.0.reload, ptr %rcx.1.reg2mem
  %29 = call i64 @function_12df530(i64 %rcx.0.reload, i64 %rsi.0.reload)
  %35 = call i64 @function_12df530(i64 %rcx.0.reload, i64 %rsi.0.reload)
  %rcx.1.reload = load i64, ptr %rcx.1.reg2mem
  %40 = add nuw nsw i64 %rdi.0.reload, -1
  store i64 %rcx.1.reload, ptr %rcx.0.reg2mem
  store i64 %40, ptr %rdi.0.reg2mem
  %cond = icmp eq i64 %40, 0
  br i1 %cond, label %exit, label %loop
exit:
  %45 = call i64 @function_12df760(i64 %rcx.1.reload)
  ret i64 %45
}
'''

# align 付きの store/load を経由した第 1 引数 (*%arg1 を slot に退避して読み直す形)。判定は OK でなければならない。
ALIGNED = '''define i64 @function_f552a0(i64 %arg1) local_unnamed_addr {
entry:
  %p = inttoptr i64 %arg1 to ptr
  %v = load i64, ptr %p, align 8
  %s = alloca i64
  store i64 %v, ptr %s, align 8
  %r = load i64, ptr %s, align 8
  %c1 = call i64 @function_12df530(i64 %r, i64 0)
  %c2 = call i64 @function_12df530(i64 %r, i64 0)
  %c3 = call i64 @function_12df530(i64 %r, i64 0)
  %c4 = call i64 @function_12df530(i64 %r, i64 0)
  %c5 = call i64 @function_12df530(i64 %r, i64 0)
  %c6 = call i64 @function_12df760(i64 %r)
  ret i64 %c6
}
'''


def run(*args):
    return subprocess.run([sys.executable] + list(args), capture_output=True, text=True)


def main():
    fails = []
    with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as d:
        before = os.path.join(d, 'before.ll')
        after = os.path.join(d, 'after.ll')
        open(before, 'w').write(BEFORE)

        r = run(JUDGE, before)
        if r.returncode != 1 or 'ng=6' not in r.stdout:
            fails.append('修正前 IR が NG にならない (rc=%d): %s' % (r.returncode, r.stdout))

        r = run(FIX, before, after)
        if r.returncode != 0:
            fails.append('fix_f552a0 が適用できない: %s' % r.stderr)
        else:
            r = run(JUDGE, after)
            if r.returncode != 0 or 'ok=6 ng=0' not in r.stdout:
                fails.append('修正後 IR が OK にならない (rc=%d): %s' % (r.returncode, r.stdout))

        short = os.path.join(d, 'short.ll')
        open(short, 'w').write(BEFORE.replace('  %45 = call i64 @function_12df760(i64 %rcx.1.reload)\n', ''))
        r = run(JUDGE, short)
        if r.returncode != 2:
            fails.append('call 件数不足が fail-closed にならない (rc=%d)' % r.returncode)

        aligned = os.path.join(d, 'aligned.ll')
        open(aligned, 'w').write(ALIGNED)
        r = run(JUDGE, aligned)
        if r.returncode != 0 or 'ok=6 ng=0' not in r.stdout:
            fails.append('align 付き store を経由した *arg1 が OK にならない (rc=%d): %s' % (r.returncode, r.stdout))

    if fails:
        for f in fails:
            print('FAIL: ' + f)
        return 1
    print('OK: test_arg1_5999 (4 件)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
