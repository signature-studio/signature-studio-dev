#!/usr/bin/env python3
"""LD-83 (#2192) の site 計装 (irtool.instrument(sites=True)) の単体テスト (PE/wasm 不要・stdlib のみ)。

  python3 tools/liftdiff/tests/test_irtool_sites.py     # 全 PASS で exit 0、1 件でも FAIL なら exit 1

(1) 関数先頭の dec_label_pc_ の直後の import call・br にも site store が入る。
    正例 = function_1c0b6c の先頭 HeapFree と先頭 br。ネガコン = 先頭 call の site store を外すと FAIL。
(2) define ごとに VA を戻す: dec_label_pc_ で始まらない先頭 block の site は記録せず、前の関数の VA を付けない。
(3) sites=False では site store が 1 件も入らない (既定 build と差が無いこと)。
(4) results/ld83/decode_sites.py: blk 列の B/J/C 分解と ord 連番検査。ネガコン = 1 件抜くと sites と ord が変わる。
"""
import json, os, re, sys, tempfile, unittest, io, contextlib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'results', 'ld83'))
from ldlib import irtool
import decode_sites

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

IR_LABELS = '''declare void @HeapFree(i32, i32, ptr)

define void @function_1c2109(i1 %arg1) {
dec_label_pc_1c2109:
  call void @HeapFree(i32 0, i32 0, ptr null)
  br i1 %arg1, label %25, label %dec_label_pc_1c2173
; <label>:25:
  call void @HeapFree(i32 0, i32 0, ptr null)
  br label %dec_label_pc_1c2173
dec_label_pc_1c2173.thread4:
  call void @HeapFree(i32 0, i32 0, ptr null)
  ret void
dec_label_pc_1c2173:
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


class OtherLabelBoundary(unittest.TestCase):
    # (2') dec_label_pc_ 以外の境界 (`; <label>:25:`・`dec_label_pc_<VA>.thread4:`) は B 記録が無いので、
    # そこから次の dec_label_pc_ までの site は記録せず skipped に数える (直前の block の VA を付けない)
    def test_sites_after_other_labels_are_skipped(self):
        txt, err = run_instrument(IR_LABELS, sites=True)
        b = body(txt, 'function_1c2109')
        # 記録は先頭の HeapFree (ord 0) と br (ord 1) の 2 件だけ。`; <label>:25` と `.thread4` の call は記録しない
        self.assertEqual(len(SITE_STORE_RE.findall(b)), 2)
        self.assertIn('store volatile i64 %s, ptr' % enc(2, 0x1c2109), b)
        self.assertNotIn('store volatile i64 %s, ptr' % (enc(2, 0x1c2109) | (2 << 40)), b)
        self.assertIn('sites skipped (block without dec_label_pc_ VA): 2', err)


class SitesOff(unittest.TestCase):
    def test_no_site_store_when_sites_false(self):
        txt, err = run_instrument(IR, sites=False)
        self.assertEqual(len(SITE_STORE_RE.findall(txt)), 0)
        self.assertEqual(err, '')


def blk_list(drop=None):
    # function_1c0b6c の 1 case: B1c0b6c, C(ord0), J(ord1, cond=0), B1c0b71, C(ord0)
    seq = [0x1c0b6c,
           (1 << 62) | (2 << 56) | 0x1c0b6c,
           (1 << 62) | (1 << 56) | (1 << 40) | 0x1c0b6c,
           0x1c0b71,
           (1 << 62) | (2 << 56) | 0x1c0b71]
    return [hex(v) for i, v in enumerate(seq) if i != drop]


class DecodeSites(unittest.TestCase):
    def write_run(self, blk):
        d = tempfile.mkdtemp(prefix='ld83_dec_')
        p = os.path.join(d, 'run.json')
        with open(p, 'w') as f:
            json.dump([{'function': {'va': '0x1c0b6c'}, 'cases': [
                {'pattern': 'vm0', 'outcome': 'diff', 'raw': {'wasm': {'blk': blk, 'blk_over': 0}}}]}], f)
        return p

    def test_counts_and_order(self):
        items = [decode_sites.decode(v) for v in decode_sites.vals(blk_list())]
        self.assertEqual([t[0] for t in items], ['B', 'C', 'J', 'B', 'C'])
        self.assertEqual(items[2], ('J', 0x1c0b6c, 1, 0))
        self.assertTrue(decode_sites.ord_ok(items))
        self.assertEqual(decode_sites.seq_str(items, 5), 'B1c0b6c C1c0b6c.0 J1c0b6c.1=0 B1c0b71 C1c0b71.0')

    def test_negative_control_drop_one_site(self):
        # 先頭の call の記録を 1 件抜くと site 数が 3 → 2、J の ord が 1 から始まるため NG になる
        items = [decode_sites.decode(v) for v in decode_sites.vals(blk_list(drop=1))]
        self.assertEqual(sum(1 for t in items if t[0] in 'JC'), 2)
        self.assertFalse(decode_sites.ord_ok(items))

    def test_callee_blocks_between_sites_are_positive(self):
        # 呼び出し元 block (B 1801c0b6c) の C.0 の後に呼び出し先 block (B 1801c0b71・C.0・J.1) が挟まり、戻った後に C.1 が続く
        # (実データと同じ形: B は 33 bit、site は下位 32 bit。旧 ord 判定は戻りを扱えず NG になる)
        seq = [0x1801c0b6c, (1 << 62) | (2 << 56) | 0x801c0b6c,
               0x1801c0b71, (1 << 62) | (2 << 56) | 0x801c0b71,
               (1 << 62) | (1 << 56) | (1 << 40) | (1 << 39) | 0x801c0b71,
               (1 << 62) | (2 << 56) | (1 << 40) | 0x801c0b6c]
        items = [decode_sites.decode(v) for v in decode_sites.vals([hex(v) for v in seq])]
        self.assertTrue(decode_sites.ord_ok(items))

    def test_site_without_block_is_ng(self):
        # 先頭の B を抜くと、site の VA が積まれていない (記録の欠落・ring の切れ目)
        items = [decode_sites.decode(v) for v in decode_sites.vals(blk_list(drop=0))]
        self.assertFalse(decode_sites.ord_ok(items))

    def test_cli_runs(self):
        out = io.StringIO()
        saved = sys.argv
        sys.argv = ['decode_sites.py', self.write_run(blk_list()), '--seq', '5']
        try:
            with contextlib.redirect_stdout(out):
                decode_sites.main()
        finally:
            sys.argv = saved
        self.assertIn('0x1c0b6c\tvm0\tdiff\t2\t1\t2\t3\t5\tok\t0', out.getvalue())


if __name__ == '__main__':
    r = unittest.main(exit=False, verbosity=2).result
    sys.exit(0 if r.wasSuccessful() else 1)
