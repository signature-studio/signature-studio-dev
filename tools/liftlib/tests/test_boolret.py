#!/usr/bin/env python3
"""tests/test_boolret.py — liftlib.passes.boolret (LD-147 / #3180) の単体テスト。外部素材・emcc 不要。

  B1 `call i1` の結果を sext した行 (同一関数内) が zext に変わる (metadata は保持)
  B2 icmp の i1 を sext した行は変わらない
  B3 select・phi の i1 を sext した行は変わらない
  B4 件数 (変えた行数) が正しい
  B5 関数の境界: 別関数で同名の icmp 結果は対象外
  B6 ネガティブコントロール: 規則を外して全 sext を zext にすると B2・B3・B5 の判定が崩れる
  B7 `call i1` が無い入力は無変更 (n=0・バイト一致)

  python3 -m unittest tests/test_boolret.py   (tools/liftlib で実行)
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

from liftlib.passes import boolret  # noqa: E402

SYNTH = """target datalayout = "e-m:e-p:32:32-p10:8:8-p20:8:8-i64:64-i128:128-f128:64-n32:64-S128-ni:1:10:20"
declare i1 @TerminateProcess(ptr, i32)
declare i1 @HeapFree(ptr, i32, ptr)

define i64 @f_bool(ptr %p) {
entry:
  %r0 = call i1 @TerminateProcess(ptr %p, i32 -1)
  %s0 = sext i1 %r0 to i64
  %r1 = call i1 @HeapFree(ptr %p, i32 0, ptr %p)
  %s1 = sext i1 %r1 to i64, !insn.addr !7
  %c = icmp ne ptr %p, null
  %sc = sext i1 %c to i64
  %sel = select i1 %c, i1 %r0, i1 false
  %ss = sext i1 %sel to i64
  br i1 %c, label %a, label %b
a:
  br label %b
b:
  %ph = phi i1 [ %r1, %entry ], [ %sel, %a ]
  %sp = sext i1 %ph to i64
  %sum = add i64 %s0, %s1
  ret i64 %sum
}

define i64 @f_other(ptr %p) {
entry:
  %r0 = icmp eq ptr %p, null
  %sx = sext i1 %r0 to i64
  %r2 = call i1 @HeapFree(ptr %p, i32 0, ptr %p)
  %s2 = sext i1 %r2 to i64
  ret i64 %s2
}
"""

EXPECT_ZEXT = ["%s0 = zext i1 %r0 to i64", "%s1 = zext i1 %r1 to i64, !insn.addr !7", "%s2 = zext i1 %r2 to i64"]
EXPECT_KEEP = ["%sc = sext i1 %c to i64", "%ss = sext i1 %sel to i64", "%sp = sext i1 %ph to i64",
               "%sx = sext i1 %r0 to i64"]


def _lines(text):
    return set(l.strip() for l in text.split("\n"))


class BoolretTest(unittest.TestCase):

    def test_call_result_sext_becomes_zext(self):
        out, _ = boolret.apply(SYNTH)
        got = _lines(out)
        for l in EXPECT_ZEXT:
            self.assertIn(l, got)

    def test_icmp_select_phi_and_other_scope_keep_sext(self):
        out, _ = boolret.apply(SYNTH)
        got = _lines(out)
        for l in EXPECT_KEEP:
            self.assertIn(l, got)

    def test_count(self):
        _, n = boolret.apply(SYNTH)
        self.assertEqual(n, 3)

    def test_no_call_i1_is_identity(self):
        text = "define i64 @g(i64 %a) {\n  %b = sext i16 %a to i64\n  ret i64 %b\n}\n"
        out, n = boolret.apply(text)
        self.assertEqual((out, n), (text, 0))

    def test_negative_control_all_sext_would_differ(self):
        naive = SYNTH.replace("sext i1 ", "zext i1 ")
        naive_changed = sum(1 for a, b in zip(SYNTH.split("\n"), naive.split("\n")) if a != b)
        out, n = boolret.apply(SYNTH)
        self.assertEqual(naive_changed, 7)
        self.assertGreater(naive_changed, n)
        self.assertNotEqual(out, naive)


if __name__ == "__main__":
    unittest.main()
