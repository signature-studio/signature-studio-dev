#!/usr/bin/env python3
"""x64c_qfc.py: tools/flelift/x64c.py に QuickFontCache_x64.dll 用の SSSE3 handler (pshufb/pmulhrsw/phaddw, XMM 形のみ)
を注入して main() を実行する薄いラッパー。tools/flelift は編集しない (担当外)。CLI は x64c.py と同一。"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'flelift'))
import x64c
from x64c import FnLift, Unsup


def i_pshufb(self, ins, ops):
    if self.ismm(ins, ops[0]):
        raise Unsup('pshufb mm')
    di = self.xd(ins, ops[0])
    self.L('{ X128 m_ = %s; X128 a_ = X[%d]; X128 r_; for (int k_ = 0; k_ < 16; k_++) '
           'r_.b[k_] = (m_.b[k_] & 0x80) ? 0 : a_.b[m_.b[k_] & 15]; X[%d] = r_; }' % (self.xs(ins, ops[1], 'x128'), di, di))


def i_pmulhrsw(self, ins, ops):
    if self.ismm(ins, ops[0]):
        raise Unsup('pmulhrsw mm')
    self.lane(ins, ops, 'w', 8, '(uint16_t)((((int32_t)a_.sw[k_] * (int32_t)b_.sw[k_] >> 14) + 1) >> 1)')


def i_phaddw(self, ins, ops):
    if self.ismm(ins, ops[0]):
        raise Unsup('phaddw mm')
    di = self.xd(ins, ops[0])
    self.L('{ X128 b_ = %s; X128 a_ = X[%d]; X128 r_; for (int k_ = 0; k_ < 4; k_++) '
           '{ r_.w[k_] = (uint16_t)(a_.w[2*k_] + a_.w[2*k_+1]); r_.w[4+k_] = (uint16_t)(b_.w[2*k_] + b_.w[2*k_+1]); } X[%d] = r_; }'
           % (self.xs(ins, ops[1], 'x128'), di, di))


# QFC_NEGCTL (ネガコン専用): none_ssse3 = handler 無効 (unsup が出る) / pmulhrsw = 丸め +1 を落とす /
#   pshufb = 0x80 bit の 0 化を落とす / phaddw = 各和に +1 する。いずれも qfc_diff が FAIL することを確認する
NEG = os.environ.get('QFC_NEGCTL', '')
if NEG == 'pmulhrsw':
    def i_pmulhrsw(self, ins, ops):
        self.lane(ins, ops, 'w', 8, '(uint16_t)(((int32_t)a_.sw[k_] * (int32_t)b_.sw[k_] >> 15))')
elif NEG == 'pshufb':
    def i_pshufb(self, ins, ops):
        di = self.xd(ins, ops[0])
        self.L('{ X128 m_ = %s; X128 a_ = X[%d]; X128 r_; for (int k_ = 0; k_ < 16; k_++) r_.b[k_] = a_.b[m_.b[k_] & 15]; X[%d] = r_; }' % (self.xs(ins, ops[1], 'x128'), di, di))
elif NEG == 'phaddw':
    def i_phaddw(self, ins, ops):
        di = self.xd(ins, ops[0])
        self.L('{ X128 b_ = %s; X128 a_ = X[%d]; X128 r_; for (int k_ = 0; k_ < 4; k_++) { r_.w[k_] = (uint16_t)(a_.w[2*k_] + a_.w[2*k_+1] + 1); r_.w[4+k_] = (uint16_t)(b_.w[2*k_] + b_.w[2*k_+1] + 1); } X[%d] = r_; }' % (self.xs(ins, ops[1], 'x128'), di, di))
if NEG != 'none_ssse3':
    FnLift.i_pshufb, FnLift.i_pmulhrsw, FnLift.i_phaddw = i_pshufb, i_pmulhrsw, i_phaddw

if __name__ == '__main__':
    x64c.main()
