#!/usr/bin/env python3
"""LD-11 (#548) の比較系修正の単体テスト (PE/wasm 不要・stdlib のみ)。

  python3 tools/liftdiff/tests/test_compare_ld11.py     # 全 PASS で exit 0、1 件でも FAIL なら exit 1

(1) cmp_mem: 部分上書き (byte store) された ptr 入りワードを byte 単位で比較する。
    正例 = issue #548 の 0x6cd8a0 (native 0x1000000224623b0 / wasm 0x1000000220623b0、delta 0x400000)。
    ネガコン = 書込み byte の値差 / 書込まれていない byte の rebase 漏れ / 片側だけ書込み / 書込み byte に ptr を入れて rebase 漏れ → 全て diff。
(2) compare_case: wasm timeout で native が長い case は wasm_trap でなく wasm_timeout_native_long。
    ネガコン = native が短い (native_ms * slowdown < timeout) / native ms 不明 → 従来どおり wasm_trap (欠陥として残る)。
"""
import os, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from ldlib import compare, classify

DELTA = 0x400000
WIN = [(0x22000000, 0x22100000)]          # wasm 座標の arena。native は +DELTA
CTX = compare.Ctx(DELTA, WIN, (0x10000, 0x20000))


def blk(pre, post, off=0x35a8, r='arena'):
    return {'r': r, 'o': hex(off), 'b': pre.to_bytes(8, 'little').hex(), 'a': post.to_bytes(8, 'little').hex()}


def mem(*b):
    return {'status': 'ok', 'mem': list(b)}


PRE_N, PRE_W = 0x224623b0, 0x220623b0       # 同じ ptr の native / wasm 表現 (差 = DELTA)
ONE = 1 << 56                               # mov byte [rcx+0x35af], 1 → byte 7 に 1


class CmpMem(unittest.TestCase):
    def test_issue_0x6cd8a0_equal(self):
        n, w = mem(blk(PRE_N, PRE_N | ONE)), mem(blk(PRE_W, PRE_W | ONE))
        self.assertEqual(compare.cmp_mem(n, w, CTX)[1], 0)

    def test_issue_values_would_fail_with_word_compare(self):
        # 旧実装 (語単位 ctx.eq) では不一致になることの確認 = 本修正が効いている証拠
        self.assertFalse(CTX.eq(PRE_N | ONE, PRE_W | ONE))

    def test_unchanged_block_ptr_still_equal(self):
        n, w = mem(blk(PRE_N, PRE_N)), mem(blk(PRE_W, PRE_W))
        self.assertEqual(compare.cmp_mem(n, w, CTX)[1], 0)

    def test_full_word_ptr_write_still_equal(self):
        n, w = mem(blk(0, PRE_N)), mem(blk(0, PRE_W))
        self.assertEqual(compare.cmp_mem(n, w, CTX)[1], 0)

    # ---- ネガティブコントロール ----
    def test_neg_written_byte_value_differs(self):
        n, w = mem(blk(PRE_N, PRE_N | ONE)), mem(blk(PRE_W, PRE_W | (2 << 56)))
        self.assertEqual(compare.cmp_mem(n, w, CTX)[1], 1)

    def test_neg_unchanged_bytes_wrong_rebase(self):
        # wasm 側の未変更 byte が native の ptr と対応しない (差が DELTA でない)
        n, w = mem(blk(PRE_N, PRE_N | ONE)), mem(blk(PRE_W + 0x1000, PRE_W + 0x1000 | ONE))
        self.assertEqual(compare.cmp_mem(n, w, CTX)[1], 1)

    def test_neg_only_native_writes(self):
        n, w = mem(blk(PRE_N, PRE_N | ONE)), mem(blk(PRE_W, PRE_W))
        self.assertEqual(compare.cmp_mem(n, w, CTX)[1], 1)

    def test_neg_written_bytes_differ_in_ptr_word(self):
        # ptr 入りワードの下位 3 byte を書換え。変化 byte は生値比較なので、書込み値が 1 ずれれば diff (未変更 byte の rebase 許容に吸収されない)
        post_n = (PRE_N & ~0xffffff) | 0x4623b1
        post_w = (PRE_W & ~0xffffff) | 0x0623b2
        n, w = mem(blk(PRE_N, post_n)), mem(blk(PRE_W, post_w))
        self.assertEqual(compare.cmp_mem(n, w, CTX)[1], 1)

    def test_neg_wasm_only_block(self):
        n, w = {'status': 'ok', 'mem': []}, mem(blk(PRE_W, PRE_W | ONE))
        self.assertEqual(compare.cmp_mem(n, w, CTX)[1], 1)


def case(status_n, status_w, **kw):
    n = {'status': status_n, 'calls': [], 'mem': [], **kw}
    return n, {'status': status_w, 'calls': [], 'mem': []}


class WasmTimeout(unittest.TestCase):
    def cc(self, n, w, ctx=CTX):
        return compare.compare_case(n, w, ctx, {}, {})

    def test_native_long_is_separate_outcome(self):
        n, w = case('ok', 'timeout', ms=900.0)       # 900 * 20 >= 1000
        r = self.cc(n, w)
        self.assertEqual(r['outcome'], 'wasm_timeout_native_long')
        self.assertEqual(r['native_ms'], 900.0)

    def test_neg_native_short_stays_wasm_trap(self):
        n, w = case('ok', 'timeout', ms=0.5)          # 0.5 * 20 < 1000 → wasm の無限ループ疑い = 欠陥のまま
        self.assertEqual(self.cc(n, w)['outcome'], 'wasm_trap')

    def test_neg_unknown_native_ms_stays_wasm_trap(self):
        n, w = case('ok', 'timeout')
        self.assertEqual(self.cc(n, w)['outcome'], 'wasm_trap')

    def test_threshold_follows_target_timeout(self):
        n, w = case('ok', 'timeout', ms=60.0)
        short = compare.Ctx(DELTA, WIN, (0, 1), wasm_timeout_ms=1000, wasm_slowdown=20.0)   # 60*20=1200 >= 1000
        long_ = compare.Ctx(DELTA, WIN, (0, 1), wasm_timeout_ms=10000, wasm_slowdown=20.0)  # 1200 < 10000
        self.assertEqual(self.cc(n, w, short)['outcome'], 'wasm_timeout_native_long')
        self.assertEqual(self.cc(n, w, long_)['outcome'], 'wasm_trap')

    def test_non_timeout_trap_unchanged(self):
        n, w = case('ok', 'trap', ms=900.0)
        self.assertEqual(self.cc(n, w)['outcome'], 'wasm_trap')

    def test_native_long_is_not_a_mismatch_verdict(self):
        n, w = case('ok', 'timeout', ms=900.0)
        c = self.cc(n, w)
        rec = {'cases': [c]}
        self.assertEqual(classify.verdict(rec), 'unexec')
        self.assertEqual(classify.unexec_reason(rec), 'wasm_timeout_native_long')
        # 他 case に実不一致があれば mismatch のまま (偽陽性除去が本物の欠陥を隠さない)
        self.assertEqual(classify.verdict({'cases': [c, {'outcome': 'diff'}]}), 'mismatch')


if __name__ == '__main__':
    r = unittest.main(exit=False, verbosity=2).result
    sys.exit(0 if r.wasSuccessful() else 1)
