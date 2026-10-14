"""launch_issues.py の判定を固定データで検査する (#2325)。

実行: python3 -m unittest discover -s tools/pm -p 'test_*.py'
gh・状態ファイルには触れない (PHASE / LAUNCHED / RELAUNCH / HERE は一時ディレクトリに差し替える)。
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import issue_snapshot  # noqa: E402
import launch_issues as lj  # noqa: E402

BOT = "opencode-for-signature-studio[bot]"
RUN_OUTCOME = "<!-- oc-run-outcome: no-pr reason=stop run=1 -->"
PM_MARK = "<!-- oc-pm-kind: launch -->"


def ts(hours_ago):
    t = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def pulls(stuck, normal):
    out = []
    for k in range(stuck):
        out.append({"number": 1000 + k, "labels": [{"name": "oc:stuck"}]})
    for k in range(normal):
        out.append({"number": 2000 + k, "labels": [{"name": "oc:ready"}]})
    return out


def snapshot(issue_numbers, comments=()):
    d = {
        "issues": [{"number": n, "title": f"[TEST-{n}] t", "labels": [], "body": "", "deps": None}
                   for n in issue_numbers],
        "prs": [],
        "bot_last": issue_snapshot.bot_last_of(list(comments)),
        "pm_art": {},
        "runs": [],
    }
    # 実際の issues_state.json と同じく JSON を通す (bot_last のキーは文字列になる)
    return json.loads(json.dumps(d))


def bot_comment(n, body, hours_ago=1):
    return {"user": {"login": BOT}, "issue_url": f"https://api.github.com/repos/x/y/issues/{n}",
            "created_at": ts(hours_ago), "body": body}


class LaunchIssuesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = self.tmp.name
        for name, value in [("HERE", d), ("PHASE", os.path.join(d, "phase.json")),
                            ("LAUNCHED", os.path.join(d, "launched.json")),
                            ("RELAUNCH", os.path.join(d, "relaunch.json")),
                            ("STUCK_HIGH", 40)]:
            p = mock.patch.object(lj, name, value)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(lj, "full_bot_body", return_value="")  # gh を呼ばない
        p.start()
        self.addCleanup(p.stop)

    def set_phase(self, review_only):
        with open(lj.PHASE, "w") as f:
            json.dump({"review_only": review_only}, f)

    # (a) stuck 17 + 非 stuck 8 → 8 と数える
    def test_stuck_prs_are_not_counted(self):
        self.assertEqual(lj.count_open_prs(pulls(17, 8)), (8, 17))

    # (b) 非 stuck 85 → REVIEW-ONLY
    def test_review_only_when_normal_prs_over_high(self):
        self.set_phase(False)
        op, _ = lj.count_open_prs(pulls(0, 85))
        self.assertTrue(lj.phase_update(op)["review_only"])

    # (c) stuck 41 + 非 stuck 5 → stuck の上限で停止
    def test_stop_when_stuck_over_limit(self):
        self.set_phase(False)
        op, stuck = lj.count_open_prs(pulls(41, 5))
        self.assertEqual((op, stuck), (5, 41))
        self.assertIsNotNone(lj.launch_stop_reason(stuck))

    # (f) 非 stuck 79 + stuck 30 → LAUNCH (境界)
    def test_launch_at_boundary(self):
        self.set_phase(False)
        op, stuck = lj.count_open_prs(pulls(30, 79))
        self.assertFalse(lj.phase_update(op)["review_only"])
        self.assertIsNone(lj.launch_stop_reason(stuck))

    # (d) 凡例の語「素材不足」だけを含む run-outcome コメント → stopped/relaunch に入らず ready
    def test_run_outcome_legend_word_is_not_a_stop(self):
        legend = "凡例: reason=stop は『素材不足』『停止報告』などを含む報告です。" + RUN_OUTCOME
        d = snapshot([10], [bot_comment(10, legend)])
        _, _, _, rows = lj.classify(d)
        self.assertIn(10, rows["ready"])
        self.assertEqual(rows["stopped"], [])
        self.assertEqual(rows["relaunch"], [])

    # (e) 「素材不足」を含むマーカー無しの bot の停止報告 → 従来どおり stopped (ネガコン)
    def test_plain_bot_stop_report_is_still_stopped(self):
        d = snapshot([11], [bot_comment(11, "素材不足のため停止します。fl-win64 が無い。")])
        _, _, _, rows = lj.classify(d)
        self.assertEqual([n for n, _ in rows["stopped"]], [11])
        self.assertNotIn(11, rows["ready"])

    # PM マーカーのコメントも停止報告に数えない
    def test_pm_marker_comment_is_not_a_stop(self):
        d = snapshot([12], [bot_comment(12, "着手不可: 素材不足です。" + PM_MARK)])
        _, _, _, rows = lj.classify(d)
        self.assertIn(12, rows["ready"])
        self.assertEqual(rows["stopped"], [])


if __name__ == "__main__":
    unittest.main()
