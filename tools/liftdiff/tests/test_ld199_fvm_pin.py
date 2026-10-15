#!/usr/bin/env python3
"""LD-199 (#4174) の 0x5c1030 fvm 固定と verdict の単体テスト (native / wasm 不要・stdlib のみ)。

  python3 tools/liftdiff/tests/test_ld199_fvm_pin.py     # 全 PASS で exit 0、1 件でも FAIL なら exit 1

(1) FVM_PIN_ARG は 0x5c1030 だけを arg 0 に固定する (据え置き FVM_HOLD_VAS は解除済み)。
(2) fvm_cand: 候補が多重 (2 件以上) でも、固定対象の関数は arg 0 だけを返す。固定しない関数は multi_candidate のまま。
(3) classify.verdict: fvm の native_extra_call diff は mismatch として数える (fvm_held で除外しない)。
"""
import os, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from ldlib import session, classify


class _Fake:
    pass


def _sess():
    s = session.Session.__new__(session.Session)
    s.analyzer = _Fake()
    s.analyzer.is_ret_fragment = lambda va: False
    s.pe = _Fake()
    return s


class TestFvmPin(unittest.TestCase):
    def test_pin_is_arg0_only_for_0x5c1030(self):
        self.assertEqual(session.FVM_PIN_ARG, {0x5c1030: 0})

    def test_pinned_multi_candidate_returns_arg0(self):
        s = _sess()
        sig = {'params': ['i'] * 3}
        fault = {'addr': '0x%x' % (session.cases.SMALL[0] + 8), 'rip': '0x0', 'detail': ''}
        cases_done = [{'pattern': 's', 'fault': fault}]
        orig = session.cases.fvm_candidates
        session.cases.fvm_candidates = lambda f, k: [0, 1]
        try:
            cand, skip = s.fvm_cand(0x5c1030, sig, cases_done)
        finally:
            session.cases.fvm_candidates = orig
        self.assertEqual((cand, skip), ([0], None))

    def test_unpinned_multi_candidate_stays_excluded(self):
        s = _sess()
        s._fault_base_arg = lambda fault, sig, cand: None
        s.analyzer.fault_arg = lambda va, rip: None
        sig = {'params': ['i'] * 3}
        cases_done = [{'pattern': 's', 'fault': {'addr': '0x0', 'rip': '0x0', 'detail': ''}}]
        orig = session.cases.fvm_candidates
        session.cases.fvm_candidates = lambda f, k: [0, 1]
        try:
            cand, skip = s.fvm_cand(0x1234, sig, cases_done)
        finally:
            session.cases.fvm_candidates = orig
        self.assertEqual((cand, skip), (None, 'multi_candidate'))


class TestVerdictCountsFvmDiff(unittest.TestCase):
    def test_fvm_native_extra_call_is_mismatch(self):
        rec = {'cases': [{'outcome': 'diff', 'pattern': 'fvm',
                          'diffs': {'calls': {'kind': 'native_extra_call'}}}]}
        self.assertEqual(classify.verdict(rec), 'mismatch')


if __name__ == '__main__':
    r = unittest.main(exit=False, verbosity=1)
    sys.exit(0 if r.result.wasSuccessful() else 1)
