#!/usr/bin/env python3
"""vex_comis_flags.py の回帰テスト ([PLG-F3-14] #1774)。 実行: python3 test_vex_comis_flags.py"""
import os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = """define i64 @f(i64 %a) {
dec_label_pc_1:
  %zf.0.reg2mem = alloca i1
  %zf.0.reload = load i1, ptr %zf.0.reg2mem
  %x = call i128 @__asm_vmovq(i64 %a)
  call void @__asm_vcomisd(i128 %x, i64 %a)
  br i1 %zf.0.reload, label %t, label %e
t:
  ret i64 1
e:
  ret i64 0
}
"""

def run(src):
    d = tempfile.mkdtemp()
    i, o = os.path.join(d, 'in.ll'), os.path.join(d, 'out.ll')
    open(i, 'w').write(src)
    r = subprocess.run([sys.executable, os.path.join(HERE, 'vex_comis_flags.py'), i, o], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return open(o).read(), r.stderr

out, err = run(SRC)
# 差し替え: 直後の分岐は呼び出しで作った ZF を読む
assert re.search(r'br i1 %vc\d+zf,', out), out
assert 'br i1 %zf.0.reload' not in out
assert 'fcmp ueq double' in out and 'fcmp uno double' in out
assert 'call void @__asm_vcomisd(i128 %x, i64 %a)' in out, 'helper call must stay (unimpl marker)'
assert 'replaced_uses 1' in err, err

# ブロック外 (後続ブロック) で読まれる flag は差し替えない (xblk として数える)
SRC2 = SRC.replace('t:\n  ret i64 1', 't:\n  %y = select i1 %zf.0.reload, i64 1, i64 2\n  ret i64 %y')
out2, _ = run(SRC2)
assert re.search(r'br i1 %vc\d+zf,', out2) and 'select i1 %zf.0.reload' in out2, out2

# 呼び出しが無ければ出力は入力と同一
plain = SRC.replace('  call void @__asm_vcomisd(i128 %x, i64 %a)\n', '')
out3, _ = run(plain)
assert out3 == plain, 'no VEX comis: output must equal input'
print('ok: test_vex_comis_flags')
