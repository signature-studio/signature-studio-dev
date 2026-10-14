#!/usr/bin/env python3
"""LD-83 (#2192) の site 計装 (irtool.instrument(sites=True)) の単体テスト (PE/wasm 不要・stdlib のみ)。

  python3 tools/liftdiff/tests/test_irtool_sites.py     # 全 PASS で exit 0、1 件でも FAIL なら exit 1

(1) 関数先頭の dec_label_pc_ の直後の import call・br にも site store が入る (PR #2810 レビュー blocking 1)。
    正例 = function_1c0b6c の先頭 HeapFree と先頭 br。ネガコン = 先頭 call の site store を外すと FAIL。
(2) define ごとに VA を戻す: dec_label_pc_ で始まらない先頭 block の site は記録せず、前の関数の VA を付けない。
(3) sites=False では site store が 1 件も入らない (既定 build と差が無いこと)。
"""
import os, re, sys, tempfile, unittest, io, contextlib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from ldlib import irtool

IR = '''declare void @HeapFree(i32, i32, ptr)
declare void @ExitProcess(i32)

define void @function_1c0b6c(i64 %arg1) {
dec_label_pc_1c0b6c:
  call void @HeapFree(i32 0, i32 0, ptr null)
  %c = icmp eq i64 %arg1, 0
  br i1 %c, label %dec_label_pc_1c0ba8, label %dec_label_pc_1c0b71
dec_label_pc_1c0b71:
  call void @HeapFree(i32 0, i32 0, ptr null)
  ret void
dec_label_pc_1c0ba8:
  ret void
}

define void @function_1c0c00(i1 %arg2) {
dec_label_pc_1c0c00:
  br i1 %arg2, label %dec_label_pc_1c0c10, label %dec_label_pc_1c0c10
dec_label_pc_1c0c10:
  call void @ExitProcess(i32 1)
  ret void
}

define void @function_1c0d00() {
  call void @ExitProcess(i32 1)
  ret void
}
'''

SITE_STORE_RE = re.compile(r'store volatile i64 %lds\d+\.n1, ptr @ld_blk_n')


def run_instrument(ir, sites):
    d = tempfile.mkdtemp(prefix='ld83_test_')
    src, dst = os.path.join(d, 'in.ll'), os.path.join(d, 'out.ll')
    with open(src, 'w') as f:
        f.write(ir)
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        irtool.instrument(src, dst, blocks=True, sites=sites)
    with open(dst) as f:
        return f.read(), err.getvalue()


def body(txt, name):
    m = re.search(r'^define [^\n]*@%s\(.*?^}' % re.escape(name), txt, re.M | re.S)
    return m.group(0) if m else ''


def enc(kind, va, cond=None):
    v = (1 << 62) | (kind << 56) | va
    return v if cond is None else v | (cond << 39)


class FirstLineSites(unittest.TestCase):
    def setUp(self):
        self.txt, self.err = run_instrument(IR, sites=True)

    def test_first_line_call_has_site_before_call(self):
        b = body(self.txt, 'function_1c0b6c')
        first_call = b.index('call void @HeapFree')
        self.assertIn('store volatile i64 %s, ptr' % enc(2, 0x1c0b6c), b)
        self.assertLess(b.index('store volatile i64 %s, ptr' % enc(2, 0x1c0b6c)), first_call)

    def test_first_line_br_has_site_before_br(self):
        b = body(self.txt, 'function_1c0c00')
        self.assertIn('zext i1 %arg2 to i64', b)
        m = re.search(r'add i64 %%lds\d+\.s, %d\n' % enc(1, 0x1c0c00), b)
        self.assertIsNotNone(m)
        self.assertLess(m.start(), b.index('br i1 %arg2'))

    def test_site_count(self):
        # 1c0b6c: 先頭 HeapFree・br・1c0b71 の HeapFree = 3。1c0c00: br・ExitProcess = 2。計 5
        self.assertEqual(len(SITE_STORE_RE.findall(self.txt)), 5)


class UnlabeledFunction(unittest.TestCase):
    def test_unlabeled_first_block_gets_no_va_from_previous_function(self):
        txt, err = run_instrument(IR, sites=True)
        b = body(txt, 'function_1c0d00')
        self.assertEqual(len(SITE_STORE_RE.findall(b)), 0)
        self.assertNotIn(str(enc(2, 0x1c0c10)), b)
        self.assertIn('sites skipped (block without dec_label_pc_ VA): 1', err)


class SitesOff(unittest.TestCase):
    def test_no_site_store_when_sites_false(self):
        txt, err = run_instrument(IR, sites=False)
        self.assertEqual(len(SITE_STORE_RE.findall(txt)), 0)
        self.assertEqual(err, '')


if __name__ == '__main__':
    r = unittest.main(exit=False, verbosity=2).result
    sys.exit(0 if r.wasSuccessful() else 1)
