#!/usr/bin/env python3
"""k80abi.xmm_read_width / scan_function の xmm 入力の読み幅の回帰テスト (#3641)。
  1 命令 (+ ret) の機械語を直接 disassemble し、xmm1 (最初の read) の幅を見る。PE は不要。
  scalar double (*sd) は 64、scalar single (*ss) は 32。packed 整数の *sd (pmaxsd・vpmaxsd) は 32。
  cvt 系は変換元の幅で決める (cvtss2sd の源は単精度なので 32、cvtsd2ss の源は倍精度なので 64)。
  ネガティブコントロール: 接頭辞だけで判定する旧版 (`*sd` を 32 とする) に差し替えると FAIL する。
  packed の除外を外した版 (語尾 `sd` だけで 64 とする) に差し替えると pmaxsd・vpmaxsd が FAIL する。
usage: python3 tools/plugins/p0c/test_k80abi_width.py
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import k80abi as K  # noqa: E402
from capstone import Cs, CS_ARCH_X86, CS_MODE_64  # noqa: E402

MD = Cs(CS_ARCH_X86, CS_MODE_64)
MD.detail = True
TVA = 0x1000
RET = b'\xc3'

# (機械語, xmm1 の期待する読み幅, 注記)
CASES = [
    (b'\xf2\x0f\x58\xc1', 64, 'addsd xmm0,xmm1'),
    (b'\xf2\x0f\x51\xc1', 64, 'sqrtsd xmm0,xmm1'),
    (b'\xf2\x0f\x10\xc1', 64, 'movsd xmm0,xmm1'),
    (b'\xf3\x0f\x7e\xc1', 64, 'movq xmm0,xmm1'),
    (b'\xf2\x0f\x5a\xc1', 64, 'cvtsd2ss xmm0,xmm1 (源は倍精度)'),
    (b'\xf3\x0f\x59\xc1', 32, 'mulss xmm0,xmm1'),
    (b'\xf3\x0f\x10\xc1', 32, 'movss xmm0,xmm1'),
    (b'\xf3\x0f\x5a\xc1', 32, 'cvtss2sd xmm0,xmm1 (源は単精度)'),
    (b'\x66\x0f\x38\x3d\xc1', 32, 'pmaxsd xmm0,xmm1 (packed 整数。語尾 sd でも 128 bit)'),
    (b'\xc4\xe2\x79\x3d\xc1', 32, 'vpmaxsd xmm0,xmm0,xmm1 (VEX packed 整数)'),
]


class TestXmmReadWidth(unittest.TestCase):
    def test_width_follows_machine_code(self):
        for code, want, note in CASES:
            with self.subTest(insn=note):
                td = code + RET
                _, x, _, _, _, xw, *_ = K.scan_function(MD, td, TVA, TVA, TVA + len(td))
                self.assertIn('xmm1', x, note)
                self.assertEqual(xw.get('xmm1'), want, note)


if __name__ == '__main__':
    unittest.main()
