#!/usr/bin/env python3
"""fold_const_ops の cast 畳み込みが元の型幅を使うことの回帰テスト (#643 review 指摘 1)。
usage: python3 tools/plugins/lift/passes/test_fold_const_ops.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ir5_patch import fold_const_ops  # noqa: E402


def fold_int(expr):
    out, _ = fold_const_ops(expr)
    return int(out)


class FoldCastSourceWidth(unittest.TestCase):
    def test_nested_sext_keeps_sign_from_source_width(self):
        self.assertEqual(fold_int("sext (i16 sext (i8 255 to i16) to i64)"), (1 << 64) - 1)

    def test_nested_zext_uses_source_width(self):
        self.assertEqual(fold_int("zext (i16 zext (i8 -1 to i16) to i64)"), 255)

    def test_zext_of_negative_i8_is_255(self):
        self.assertEqual(fold_int("zext (i8 -1 to i64)"), 255)

    def test_sext_of_negative_i8_is_sign_extended(self):
        self.assertEqual(fold_int("sext (i8 -2 to i64)"), (1 << 64) - 2)


if __name__ == "__main__":
    unittest.main()
