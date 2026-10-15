"""oc_pm_duration.py の計算部分の単体テスト (#3463)。gh は呼ばない (CI の unittest discover で動く)。"""
import datetime as dt
import unittest

import oc_pm_duration as m

NOW = m.parse_ts("2026-10-15T12:00:00Z")


def run(id_, created, started, updated, status="completed", conclusion="success", title="oc-pm needs_decision #1", pm_job=None):
    return {"id": id_, "display_title": title, "event": "repository_dispatch", "status": status,
            "conclusion": conclusion, "created_at": created, "run_started_at": started,
            "updated_at": updated, "pm_job": pm_job}


class IsPmRun(unittest.TestCase):
    def test_only_oc_pm_dispatch(self):
        self.assertTrue(m.is_pm_run({"event": "repository_dispatch", "display_title": "oc-pm no_pr #1807"}))
        self.assertFalse(m.is_pm_run({"event": "repository_dispatch", "display_title": "oc-fix #3"}))
        self.assertFalse(m.is_pm_run({"event": "workflow_dispatch", "display_title": "oc-pm no_pr #1807"}))
        self.assertFalse(m.is_pm_run({"event": "repository_dispatch", "display_title": None}))


class Stats(unittest.TestCase):
    def test_values(self):
        s = m.stats([1.0, 2.0, 3.0, 10.0])
        self.assertEqual((s["n"], s["mean"], s["median"], s["min"], s["max"]), (4, 4.0, 2.5, 1.0, 10.0))

    def test_empty(self):
        self.assertEqual(m.stats([]), {"n": 0})


class MaxConcurrency(unittest.TestCase):
    def test_overlap_counted(self):
        # [0,10) [5,15) [12,20): 最大は 2 (3 件が同時にはならない)
        self.assertEqual(m.max_concurrency([(0, 10), (5, 15), (12, 20)]), 2)

    def test_touching_is_not_overlap(self):
        self.assertEqual(m.max_concurrency([(0, 5), (5, 10)]), 1)

    def test_three_at_once(self):
        self.assertEqual(m.max_concurrency([(0, 10), (1, 10), (2, 10)]), 3)

    def test_empty(self):
        self.assertEqual(m.max_concurrency([]), 0)


class MaxStartsPerHour(unittest.TestCase):
    def test_hour_is_half_open(self):
        # 0 と 3599 は [0, 3600) に入り、3600 は入らない
        t = [m.parse_ts("2026-10-15T10:00:00Z") + dt.timedelta(seconds=s) for s in (0, 1800, 3599, 3600)]
        self.assertEqual(m.max_starts_per_hour(t), 3)

    def test_burst(self):
        t = [m.parse_ts("2026-10-15T10:00:00Z")] * 25
        self.assertEqual(m.max_starts_per_hour(t), 25)


class Estimate(unittest.TestCase):
    def test_issue_formula(self):
        e = m.estimate(24, 3.65, 7.9)
        self.assertEqual(e["mean_based"], 1.46)  # 24 × 3.65 ÷ 60
        self.assertEqual(e["max_based"], 3.16)  # 24 × 7.9 ÷ 60
        self.assertEqual(e["worst_timeout"], 12.0)  # 24 × 30 ÷ 60


class Summarize(unittest.TestCase):
    def fixture(self):
        return [
            run("A", "2026-10-15T10:00:00Z", "2026-10-15T10:00:00Z", "2026-10-15T10:03:00Z",
                pm_job={"started_at": "2026-10-15T10:00:02Z", "completed_at": "2026-10-15T10:02:50Z"}),
            run("B", "2026-10-15T11:30:00Z", "2026-10-15T11:30:00Z", "2026-10-15T11:31:00Z", status="in_progress"),
            run("C", "2026-10-14T11:00:00Z", "2026-10-14T11:00:00Z", "2026-10-14T11:10:00Z"),
            run("D", "2026-10-15T11:59:00Z", "2026-10-15T11:59:00Z", "2026-10-15T12:05:00Z"),
            run("E", "2026-10-15T11:00:00Z", "2026-10-15T11:00:00Z", "2026-10-15T11:05:00Z", conclusion="failure"),
        ]

    def test_window_and_exclusions(self):
        s = m.summarize(self.fixture(), NOW, 24)
        self.assertEqual(s["pm_runs_fetched"], 5)
        self.assertEqual(s["pm_runs_used"], 2)
        self.assertEqual(s["excluded"], {"not_completed": 1, "completed_before_window": 1, "completed_after_now": 1})
        self.assertEqual(s["conclusions"], {"success": 1, "failure": 1})

    def test_durations_use_run_started_to_updated(self):
        s = m.summarize(self.fixture(), NOW, 24)
        self.assertEqual((s["run_min"]["n"], s["run_min"]["mean"], s["run_min"]["min"], s["run_min"]["max"]), (2, 4.0, 3.0, 5.0))
        self.assertEqual((s["pm_job_min"]["n"], s["pm_job_min"]["mean"]), (1, 2.8))

    def test_concurrency_and_starts(self):
        s = m.summarize(self.fixture(), NOW, 24)
        self.assertEqual(s["max_concurrency_observed"], 1)
        self.assertEqual(s["dispatch_starts_in_window"], 4)  # A・B・D・E (C は窓の前)
        self.assertEqual(s["max_dispatch_starts_per_rolling_hour"], 3)  # 11:00・11:30・11:59
        self.assertEqual(s["estimate_concurrency_at_cap"]["mean_based"], 1.6)


if __name__ == "__main__":
    unittest.main()
