#!/usr/bin/env python3
"""LD-154 (#3350) の timing 記録と応答待ちの単体テスト (native / wasm 不要・stdlib のみ)。

  python3 tools/liftdiff/tests/test_ld154_timing.py     # 全 PASS で exit 0、1 件でも FAIL なら exit 1

(1) NATIVE_ITIMER_S が rt/ld_native.c の setitimer 初回値と一致する (手書きの複製の検査)。
(2) side_timing: 上限は判定を決めた場合だけ付く。runner の timeout → limit_s、応答待ちの期限切れ → recv_limit_s、
    EOF・プロセス終了・skipped → 上限なし。
(3) Runner.run_cases: 応答が来なかった case の _cause (deadline / eof / exited) と、hang/crash の status は従来どおり。
(4) ld154_repeat.timing_summary: skipped の wasm は wasm hang と別に数える。
"""
import os, re, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from ldlib import session
from ldlib.runners import Runner, ROOT


class TestNativeItimer(unittest.TestCase):
    def test_matches_c(self):
        src = open(os.path.join(ROOT, 'rt/ld_native.c')).read()
        m = re.search(r'struct itimerval it = \{ \{0, 0\}, \{(\d+), (\d+)\} \};', src)
        self.assertIsNotNone(m, 'rt/ld_native.c の setitimer 初回値の行が見つからない')
        self.assertAlmostEqual(int(m.group(1)) + int(m.group(2)) / 1e6, session.NATIVE_ITIMER_S)


class TestSideTiming(unittest.TestCase):
    def test_ok_has_no_limit(self):
        self.assertEqual(session.side_timing({'status': 'ok', '_elapsed_s': 0.1}, 1.5, 10.0), {'status': 'ok', 'elapsed_s': 0.1})

    def test_runner_timeout_has_limit_only(self):
        t = session.side_timing({'status': 'timeout', '_elapsed_s': 1.6}, 1.5, 10.0)
        self.assertEqual(t, {'status': 'timeout', 'elapsed_s': 1.6, 'cause': 'runner_timeout', 'limit_s': 1.5})

    def test_deadline_has_recv_limit_only(self):
        t = session.side_timing({'status': 'hang', '_elapsed_s': 10.0, '_cause': 'deadline'}, 1.0, 10.0)
        self.assertEqual(t, {'status': 'hang', 'elapsed_s': 10.0, 'cause': 'deadline', 'recv_limit_s': 10.0})

    def test_eof_and_exit_have_no_limit(self):
        for cause in ('eof', 'exited'):
            t = session.side_timing({'status': 'hang', '_elapsed_s': 0.006, '_cause': cause}, 1.0, 10.0)
            self.assertEqual(t, {'status': 'hang', 'elapsed_s': 0.006, 'cause': cause})

    def test_skipped(self):
        t = session.side_timing({'status': 'hang', 'detail': session.SKIPPED, '_elapsed_s': None}, 1.0, 10.0)
        self.assertEqual(t, {'status': 'skipped', 'elapsed_s': None})


class TestRunnerCause(unittest.TestCase):
    def _run(self, code, timeout):
        r = Runner('t', [sys.executable, '-c', code], [], timeout=timeout)
        try:
            return r.run_cases(['x'], ['c1'])[0]
        finally:
            r.kill()
            r.p.stdin.close(); r.p.stdout.close()

    def test_exit_gives_cause(self):
        d = self._run('import sys; sys.exit(0)', 5.0)
        self.assertIn(d['status'], ('hang', 'crash'))
        self.assertIn(d['_cause'], ('eof', 'exited'))

    def test_deadline_gives_cause(self):
        d = self._run('import time; time.sleep(30)', 0.3)
        self.assertEqual((d['status'], d['_cause']), ('hang', 'deadline'))
        self.assertLess(d['_elapsed_s'], 5.0)


class TestRepeatSummary(unittest.TestCase):
    def test_skipped_is_not_hang(self):
        sys.path.insert(0, os.path.join(HERE))
        import ld154_repeat
        d = {'0x1': {'cases': [{'timing': {'native': {'status': 'timeout', 'elapsed_s': 1.6, 'cause': 'runner_timeout', 'limit_s': 1.5},
                                           'wasm': {'status': 'skipped', 'elapsed_s': None}}}]}}
        cnt, _ = ld154_repeat.timing_summary(d)
        self.assertEqual(cnt[('wasm', 'skipped')], 1)
        self.assertEqual(cnt[('wasm', 'hang')], 0)


if __name__ == '__main__':
    r = unittest.main(exit=False, verbosity=2).result
    sys.exit(0 if r.wasSuccessful() else 1)
