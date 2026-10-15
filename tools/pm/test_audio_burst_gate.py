"""tools/audio/test の node テストを CI (scripts-test.yaml の glob) から実行する (#4297 / AU-46)。

対象は Linux・ブラウザ不要で閉じる node テスト 3 本。判定ロジックは各 harness 側で、ここは実行の配線だけを持つ。
  - burst_gate_test.mjs   (AU-38 / #3432): burstGate の判定を mock の結果で確かめる
  - worklet_jump_check.mjs (AU-29 / #3115): worklet の clock_jump 計上経路を vm 上で駆動する
  - safari_mock_test.mjs  (AU-35 / #3193): harness/safari.mjs の WebDriver 手順を safaridriver_mock.mjs に対して確かめる
fla_test.c・flmidi_test.c は C のテストで、この glob の対象外。
実行: python3 -m unittest discover -s tools/pm -p 'test_*.py'
"""
import os
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEST_DIR = os.path.join(ROOT, "tools", "audio", "test")
MOCK = os.path.join(TEST_DIR, "safaridriver_mock.mjs")
CASES = ["burst_gate_test.mjs", "worklet_jump_check.mjs", "safari_mock_test.mjs"]


class AudioNodeTests(unittest.TestCase):
    def run_case(self, name):
        node = shutil.which("node")
        self.assertIsNotNone(node, "node が PATH に無い (scripts-test は node を要する)")
        env = dict(os.environ, SAFARIDRIVER=MOCK)
        r = subprocess.run([node, os.path.join(TEST_DIR, name)], cwd=ROOT, env=env,
                           capture_output=True, text=True, timeout=300)
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, f"{name} が失敗 (rc={r.returncode})\n{out}")
        fails = [ln for ln in r.stdout.splitlines() if ln.startswith("FAIL")]
        self.assertEqual(fails, [], f"{name}: FAIL 行あり\n{out}")
        passes = [ln for ln in r.stdout.splitlines() if ln.startswith("PASS")]
        self.assertGreater(len(passes), 0, f"{name}: PASS 行が 1 件も無い (実行されていない疑い)\n{out}")

    def test_burst_gate(self):
        self.run_case("burst_gate_test.mjs")

    def test_worklet_jump_check(self):
        self.run_case("worklet_jump_check.mjs")

    def test_safari_mock(self):
        self.run_case("safari_mock_test.mjs")


if __name__ == "__main__":
    unittest.main()
