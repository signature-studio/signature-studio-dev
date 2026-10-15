#!/usr/bin/env python3
"""#2850: ldlib/pe.py Analyzer の xmm 入力 slot で、ゼロ化イディオム (同一レジスタの xorps/pxor 等) の読みを除く。

  python3 tools/liftdiff/tests/test_pe_zero_idiom.py     (pytest でも可)

既定 (zero_idiom=False) は従来どおり読みを数える (arity_x の挙動を変えない)。zero_idiom=True のときだけ除く。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from ldlib.pe import Analyzer  # noqa: E402

BASE = 0x140000000
RVA = 0x1000
CASES = [
    # (名前, 機械語, 既定の xmm_slots, zero_idiom=True の xmm_slots)
    ('pxor xmm1,xmm1; movaps xmm0,xmm1; ret', b'\x66\x0f\xef\xc9' b'\x0f\x28\xc1' b'\xc3', [1], []),
    ('xorps xmm2,xmm2; addss xmm0,xmm2; ret', b'\x0f\x57\xd2' b'\xf3\x0f\x58\xc2' b'\xc3', [0, 2], [0]),
    ('addss xmm0,xmm3; ret (非ゼロ化の読みは残る)', b'\xf3\x0f\x58\xc3' b'\xc3', [0, 3], [0, 3]),
]


class FakePE:
    base = BASE

    def __init__(self, code):
        self.sections = [dict(name='.text', rva=RVA, vsize=len(code), rawsize=len(code), flags=0x60000020, data=code)]

    def in_iat(self, rva):
        return False


def slots(code, zero_idiom):
    return Analyzer(FakePE(code)).analyze(BASE + RVA, zero_idiom=zero_idiom)['xmm_slots']


def test_zero_idiom_slots():
    for name, code, default, zi in CASES:
        assert slots(code, False) == default, (name, 'default')
        assert slots(code, True) == zi, (name, 'zero_idiom')


if __name__ == '__main__':
    test_zero_idiom_slots()
    print('OK: %d cases' % len(CASES))
