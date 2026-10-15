#!/usr/bin/env python3
"""rdata_raw_unexpected ([KH-93] #4257 / D11) の回帰テスト。
--raw-va 時に窓化されず値として残る .rdata の素の VA のうち、許可リスト外のものを検出する。
検出を壊す (常に空を返す) と (b) が FAIL する。ネガティブコントロール: 許可を外すと (a) が FAIL する。
素材 (HeartCore.core_64) が無い環境では skip する。
usage: python3 tools/targets/kilohearts/license/lift/test_rdata_raw.py
"""
import os, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kh_lower  # noqa: E402

CORE = os.environ.get('KH_CORE') or os.path.join(HERE, '..', '..', 'work', 'winpkg', 'HeartCore.core_64')
RDATA_UTF16_NONSTR = 0x1813d47a2   # UTF-16 文字列 "LicenseManagerHelper" (窓化対象外・許可リスト)
RDATA_UTF16 = [0x181e79826, 0x181e79834]   # UTF-16 文字列 "Groups" / "New Group..." (許可リスト)
TEXT_VA = 0x180054c37   # .text 内の関数 VA (rdata 外。素の値として残っても検出対象外)


@unittest.skipUnless(os.path.exists(CORE), 'HeartCore.core_64 が無い (素材未展開)')
class RdataRawUnexpected(unittest.TestCase):
    def test_allowed_is_not_reported(self):
        """(a) 許可リスト内の .rdata VA は報告しない"""
        allow = {RDATA_UTF16_NONSTR, *RDATA_UTF16}
        self.assertEqual(kh_lower.rdata_raw_unexpected(CORE, allow, allow), set())

    def test_unallowed_rdata_is_reported(self):
        """(b) 許可外の .rdata VA は報告する (ネガティブコントロール: 許可を外すと検出される)"""
        raw = {RDATA_UTF16_NONSTR, *RDATA_UTF16}
        got = kh_lower.rdata_raw_unexpected(CORE, raw, set())
        self.assertEqual(got, raw)

    def test_non_rdata_is_not_reported(self):
        """(c) .rdata 以外 (.text) の素の値は、許可リスト外でも検出対象にしない"""
        self.assertEqual(kh_lower.rdata_raw_unexpected(CORE, {TEXT_VA}, set()), set())


if __name__ == '__main__':
    unittest.main()
