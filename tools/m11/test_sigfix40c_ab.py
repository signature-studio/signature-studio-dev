#!/usr/bin/env python3
"""M11-N223 (#4809): m11_sigfix40c_ab.py の停止規則の確認。

callee の定義が 1 件でない・BODY_OLD が 1 件でないとき、variant を作らずに止まること。
"""
import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('g', os.path.join(HERE, 'm11_sigfix40c_ab.py'))
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

HEAD = 'define i128 @function_40c650(double %in.xmm0) local_unnamed_addr {\n'
ONE = HEAD + g.BODY_OLD + '  ret i128 0\n}\n'


class ReplaceCalleeBodyRule(unittest.TestCase):
    def test_one_body_is_replaced(self):
        out = g.replace_callee_body(ONE, g.BODY_ZERO)
        self.assertIn(g.BODY_ZERO, out)
        self.assertNotIn(g.BODY_OLD, out)

    def test_zero_body_exits(self):
        with self.assertRaises(SystemExit):
            g.replace_callee_body(HEAD + '  ret i128 0\n}\n', g.BODY_ZERO)

    def test_two_bodies_exit(self):
        with self.assertRaises(SystemExit):
            g.replace_callee_body(HEAD + g.BODY_OLD + g.BODY_OLD + '  ret i128 0\n}\n', g.BODY_ZERO)

    def test_two_definitions_exit(self):
        with self.assertRaises(SystemExit):
            g.replace_callee_body(ONE + ONE, g.BODY_ZERO)


class RewriteCallsRule(unittest.TestCase):
    def test_call_sites_become_zero(self):
        s = '  %6 = call i64 @function_40c650(double %xmmcv.72.f)\n'
        self.assertEqual(g.rewrite_calls(s), '  %6 = call i64 @function_40c650(double 0.0)\n')

    def test_definition_line_is_untouched(self):
        s = ONE
        self.assertEqual(g.rewrite_calls(s), s)


if __name__ == '__main__':
    unittest.main()
