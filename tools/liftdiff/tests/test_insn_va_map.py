#!/usr/bin/env python3
"""LD-131 (#2801) の命令 VA 表 (results/ld131/insn_va_map.py) の単体テスト (PE/x64c 実行不要・stdlib のみ)。

  python3 tools/liftdiff/tests/test_insn_va_map.py     # 全 PASS で exit 0、1 件でも FAIL なら exit 1

fixture は x64c 出力 (tools/ott/lift/x64c.py・OTT_vst2_win64.dll の 6 root lift) の実行行の抜粋。
(1) 1801c0b6f の je は jcc で分岐先 1801c0ba8。(2) 1801c0b82 の call は import 呼出し (HeapFree)。
(3) 直接呼出し 1801c213c は call で 1801c0b6c。(4) 未 lift の呼出し 1801c20ea は guest 番地 301c3d80 を VA 1801c3d80 に戻す。
(5) ラベル行・blank 行は命令にしない (命令数は VA 注記行の数と一致)。
ネガコン: 注記行の書式を崩すと (2) が FAIL する。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'results', 'ld131'))
import insn_va_map

FIXTURE = '''void f_1801c0b6c(void) {
L_1801c0b6c:;
  /* 1801c0b6c: test rcx, rcx */
  { uint64_t a_ = (uint64_t)(R[1]); uint64_t b_ = (uint64_t)(R[1]); uint64_t r_ = a_ & b_; FL_LOGIC(64, r_); }
  /* 1801c0b6f: je 0x1801c0ba8 */
  if (CC_E) goto L_1801c0ba8;
  /* 1801c0b71: push rbx */
  { uint64_t v_ = R[3]; R[RSP] -= 8; ST64(R[RSP], v_); }
  /* 1801c0b82: call qword ptr [rip + 0x218e8] */
  R[RSP] -= 8; ST64(R[RSP], 0x301c0b88ULL); imp_HeapFree();
  /* 1801c0b8c: call 0x1801bafb0 */
  R[RSP] -= 8; ST64(R[RSP], 0x301c0b91ULL); f_1801bafb0();
  /* 1801c0b8a: jne 0x1801c0ba3 */
  if (!CC_E) goto L_1801c0ba3;
  /* 1801c0ba3: ret */
  return;
}
void f_1801c20c8(void) {
L_1801c20c8:;
  /* 1801c20c8: push rbx */
  { uint64_t v_ = R[3]; R[RSP] -= 8; ST64(R[RSP], v_); }
  /* 1801c20ea: call 0x1801c3d80 */
  R[RSP] -= 8; ST64(R[RSP], 0x301c20efULL); ott_unlifted(0x301c3d80ULL);
  /* 1801c213c: call 0x1801c0b6c */
  R[RSP] -= 8; ST64(R[RSP], 0x301c2141ULL); f_1801c0b6c();
  /* 1801c2175: call qword ptr [rip + 0x20085] */
  R[RSP] -= 8; ST64(R[RSP], 0x301c217aULL); imp_SetLastError();
  /* 1801c2180: jmp 0x1801c20c8 */
  goto L_1801c20c8;
}
'''


class InsnVaMapTest(unittest.TestCase):
    def setUp(self):
        self.rows = insn_va_map.parse(FIXTURE.splitlines())
        self.by = {(r['fn'], r['va']): r for r in self.rows}

    def test_jcc_target(self):
        r = self.by[('1801c0b6c', '1801c0b6f')]
        self.assertEqual((r['kind'], r['target']), ('jcc', '1801c0ba8'))
        self.assertEqual(r['insn'], 'je 0x1801c0ba8')

    def test_import_call(self):
        r = self.by[('1801c0b6c', '1801c0b82')]
        self.assertEqual((r['kind'], r['target']), ('call-imp', 'HeapFree'))

    def test_direct_call_and_fallthrough_order(self):
        r = self.by[('1801c0b6c', '1801c0b8c')]
        self.assertEqual((r['kind'], r['target']), ('call', '1801bafb0'))
        self.assertEqual(self.by[('1801c20c8', '1801c213c')]['target'], '1801c0b6c')

    def test_unlifted_call_maps_to_va(self):
        r = self.by[('1801c20c8', '1801c20ea')]
        self.assertEqual((r['kind'], r['target']), ('call-unlifted', '1801c3d80'))

    def test_labels_are_not_instructions(self):
        n = sum(1 for ln in FIXTURE.splitlines() if ln.lstrip().startswith('/* '))
        self.assertEqual(len(self.rows), n)
        self.assertEqual(len([r for r in self.rows if r['fn'] == '1801c0b6c']), 7)

    def test_jmp_and_plain(self):
        self.assertEqual(self.by[('1801c20c8', '1801c2180')]['kind'], 'jmp')
        self.assertEqual(self.by[('1801c0b6c', '1801c0b6c')]['kind'], '')


if __name__ == '__main__':
    unittest.main()
