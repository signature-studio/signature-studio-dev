#!/usr/bin/env python3
"""fw_blk_writers.py の回帰テスト (#3150)。named 形と inline 定数式の store を両方数えることを確かめる。
usage: python3 tools/plugins/framework/test_fw_blk_writers.py
"""
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, 'fw_blk_writers.py')
sys.path.insert(0, HERE)
import fw_blk_writers as W  # noqa: E402

DEF_LINE = '  %v = add i64 %arg0, 1'
IR = """define i32 @function_1000(i64 %arg0) {
entry:
  %p8 = inttoptr i64 9048072 to ptr
  store i64 1, ptr %p8, align 8
  %p10 = inttoptr i64 9048080 to ptr
  %v = add i64 %arg0, 1
  store i64 %v, ptr %p10, align 8
  store i64 203, ptr inttoptr (i64 9048080 to ptr), align 8
  store i64 %arg0, ptr inttoptr (i64 7155720 to ptr), align 8
  store i64 5, ptr inttoptr (i64 1234 to ptr), align 8
  ret i32 0
}

define void @function_2000() {
  store i64 1, ptr inttoptr (i64 9048072 to ptr), align 8
  ret void
}
"""


class ScanTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.d.name, 'in.ll')
        with open(self.path, 'w') as f:
            f.write(IR)

    def tearDown(self):
        self.d.cleanup()

    def test_named_and_inline_stores_are_counted(self):
        hits = W.scan(self.path)
        self.assertEqual(len(hits), 5)
        self.assertEqual([h[4] for h in hits], [9048072, 9048080, 9048080, 7155720, 9048072])
        self.assertEqual([h[3] for h in hits], ['1', '%v', '203', '%arg0', '1'])
        self.assertEqual([h[1] for h in hits], ['function_1000'] * 4 + ['function_2000'])

    def test_def_of_value_is_returned_with_fn_mode(self):
        hits = W.scan(self.path, 'function_1000')
        ln = IR.splitlines().index(DEF_LINE) + 1
        self.assertEqual(hits[1][5], (ln, 'add i64 %arg0, 1'))
        self.assertIsNone(hits[2][5])

    def test_cli_total(self):
        r = subprocess.run([sys.executable, SCRIPT, self.path], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('BLK/ERRCODE stores total: 5', r.stdout)
        self.assertIn('literal 203 -> 9048080: 1 stores', r.stdout)
        self.assertIn('functions storing literal 1 (fn, addr): distinct = 2', r.stdout)


if __name__ == '__main__':
    unittest.main()
