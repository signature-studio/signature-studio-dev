#!/usr/bin/env python3
"""fix_arg_width.py の回帰テスト (#1834 [PLG-F3-17])。 fail-closed の skip / call site の trunc 剥がし / 0 → i64 0 / それ以外の zext を確かめる。
usage: python3 tools/plugins/sampler/test_fix_arg_width.py
"""
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, 'fix_arg_width.py')


def run_pass(ll):
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, 'in.ll')
        dst = os.path.join(d, 'out.ll')
        with open(src, 'w') as f:
            f.write(ll)
        r = subprocess.run([sys.executable, SCRIPT, src, dst], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        with open(dst) as f:
            return f.read(), r.stderr


TARGET = """define i64 @f(i64 %arg1, i32 %arg2) {
entry:
  %c = icmp eq i32 %arg2, 0
  %p = inttoptr i64 %arg2 to ptr
  ret i64 0
}
"""


class FixArgWidth(unittest.TestCase):
    def test_definition_and_icmp_become_i64(self):
        out, err = run_pass(TARGET)
        self.assertIn('define i64 @f(i64 %arg1, i64 %arg2)', out)
        self.assertIn('icmp eq i64 %arg2, 0', out)
        self.assertNotIn('i32 %arg2', out)
        self.assertIn('defs = 1', err)

    def test_skip_when_other_use_exists(self):
        ll = """define i64 @g(i32 %arg2) {
entry:
  %x = add i32 %arg2, 1
  %p = inttoptr i64 %arg2 to ptr
  ret i64 0
}
"""
        out, err = run_pass(ll)
        self.assertIn('define i64 @g(i32 %arg2)', out)
        self.assertIn('skip g %arg2', err)

    def test_call_site_trunc_is_stripped(self):
        ll = TARGET + """define i64 @h(i64 %w) {
entry:
  %t = trunc i64 %w to i32
  %r = call i64 @f(i64 0, i32 %t)
  ret i64 %r
}
"""
        out, _ = run_pass(ll)
        self.assertIn('call i64 @f(i64 0, i64 %w)', out)
        self.assertNotIn('zext i32 %t', out)

    def test_call_site_zero_becomes_i64_zero(self):
        ll = TARGET + """define i64 @h2() {
entry:
  %r = call i64 @f(i64 0, i32 0)
  ret i64 %r
}
"""
        out, _ = run_pass(ll)
        self.assertIn('call i64 @f(i64 0, i64 0)', out)

    def test_call_site_other_value_is_zext(self):
        ll = TARGET + """define i64 @h3(i32 %v) {
entry:
  %r = call i64 @f(i64 0, i32 %v)
  ret i64 %r
}
"""
        out, _ = run_pass(ll)
        self.assertIn('%argw_1 = zext i32 %v to i64', out)
        self.assertIn('call i64 @f(i64 0, i64 %argw_1)', out)


if __name__ == '__main__':
    unittest.main()
