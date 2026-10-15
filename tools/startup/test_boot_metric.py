#!/usr/bin/env python3
"""boot_metric.py の単体テスト (固定 fixture で期待値 + ネガティブコントロール)。

fixture は一時ディレクトリに出典と同じ形の最小ファイルを作る (実 REPORT の変更に影響されない)。
実行: python3 tools/startup/test_boot_metric.py
"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boot_metric as bm  # noqa: E402

M11_REPORT = """# M11

## 13. other

x

## 14. #134 [M11-N5]: unit 23

**units_skipped = 3 の内訳**: `0xfa9390` の 1 種。

| 構成 | units_run | 停止 | survey ok/trap(oom)/miss/noproc | 所要 s / load |
|---|---|---|---|---|
| `6654322` (+414ad0・43a3f0 転記, n=3) | **53** | unit 57 (0x16fde0) 後に Halt0 | **866/29(2)/46/1** | 26.3–26.9 / 0.39→0.98 |
| `de50ffa` (指摘対応 3 点, n=1, 増分 build) | 53 | 同 | 866/29(2)/46/1 (不変) | 32.5 / 0.16→0.69 |

## 15. next

x
"""

M11_N2714 = """# M11 REPORT #2714

## 0. 結論

- **寛容起動 (`tools/m11/m11_tolerant.mjs`) で 942 unit を全て試行した**。ok 874 / noproc 1 / skipped 67 (miss 46・halt0 7・oob 13・unreachable 1)。試行 942 = ok + noproc + skipped の和で、集計は合う。clobber 0。

## 1. 測定 (測定 commit `cf64d9c8`)

- 測定 commit: `cf64d9c8` (e2e を実行した HEAD)。base は origin/main `46c92356`。

| 実行 | 変更前 (`46c92356`) | HEAD (`cf64d9c8`) | 差 |
|---|---|---|---|
| C 寛容起動 (本 PR) | — | 942 試行・ok 874・noproc 1・skip 67・boot_rc=1 | — |
"""

APPENDIX = """# appendix

## 基準 (before) #1430: xmm

測定 commit `7e149974` (origin/main, 本 branch の起点)。

| 項目 | 実測 |
|---|---|
| survey (全再生成直後, unit 別 942 本) | **ok 872 / trap 23 / miss 46 / noproc 1** (trap 内訳 OOB 15 / Halt0 7 / unreachable 1) |
"""

GUI_REPORT = """# GUI

### HEAD `703b4857` の実測 (main `b892fdc6` 取り込み後・本 PR の最終 HEAD。本節を正とする)

| 対象 | rc |
|---|---|
| e2e | 0 |

## 6i. S1 (soft) の unit 304/555 調査 (#1442 / GUI-21)

結論 (測定 commit `719f1c43`・judge 13/14・S1 `870/1/47/24/0` vs base `867/1/47/27/0`): x
"""

GUI_BOOT = {"units_run": 52, "boot_threw": "unreachable", "units_total": 942,
            "reach": [{"name": "LoadStringW", "calls": 3}]}
GUI_SURVEY = {"units_total": 942,
              "survey": {"ok": 870, "noproc": 1, "miss": 47, "trap": 24, "clobber": 0,
                         "kinds": {"unreachable": 1, "halt0->longjmp": 7,
                                   "memory access out of bounds": 16}},
              "reach": [{"name": "RegisterClassW", "calls": 2},
                        {"name": "CreateWindowExW", "calls": 2}]}
X64_BOOT = {"boot": {"units_total": 942, "units_run": 209, "threw": {"cls": "oob"},
                     "stopped_at_1based": 209, "getmem": 1886, "freemem": 776}}
X64_SURVEY = {"units_covered": 895, "byCls": {"ok": 892, "unlifted": 3}}
X64_REPORT = """# boot

### 4-1. variant 対照

| variant | link | boot 到達 | 所見 |
|---|---|---|---|
| plain | mismatch 0 / undef 0 / dup 0 | **209 dispatch** / oob (`f_816e80`) | 本命 |

### 4-2. next
"""
NATIVE = """# liftdiff — 実測

測定 commit: `2ca85816` (origin/main 時点・コード変更なし)。

## 1. 工程の実測

| 工程 | コマンド | 結果 |
|---|---|---|
| 起動 | `bootstate --mode hybrid --nobuild` | rc 0・**16 s**・`units_run 928/942`・`first_fail 830` |
"""
STARTUP = """| S08 | host | x |
| S09 | host | `0x140004b60` | `LoadLibraryW(path)` → **DllMain** (entry `0x1376820`) |
| S11 | host | `0x140006f1b` | `GetProcAddress(engine,"CreateFruityInstance")(0xC0,0xEDE95A,host,&iface)` |
| S12 | engine | `0x1375990` 冒頭, `0x13752f0` | x |
"""
APPENDIX_7 = """# appendix 7

## 7. WIN-4 (fixture)

**測定 commit `5f9d7cbd`** (fixture)

### 7-4. 呼出し

- 結果: `CreateFruityInstance` は `[shim] FAIL-FAST: unimplemented Win32 API: EnterCriticalSection (未初期化/未登録)` の後に `abort()` (1 ms)。

## 8. next

x
"""
APPENDIX_2880 = """# appendix 2880

## 9. WIN-11 (fixture)

### 9-3. 実測 (`cfi_probe.mjs`・commit `ae963e28`)

| 項目 | 結果 |
|---|---|
| `CreateFruityInstance(0xC0, 0xEDE95A, host, &iface)` | `Aborted`・1 ms・`iface` = 0x0 |
| 最後の shim 行 | `[shim] CS-MISS key=0x12bd390` → `FAIL-FAST: unimplemented Win32 API: EnterCriticalSection (未初期化/未登録)` |
| GUI-REACH / icall_miss | `LoadStringW` ×3 のみ / 5 (§7-4 と同じ) |

### 9-4. next

x
"""
CFI_PROBE = "  const r = mod._CreateFruityInstance(0xC0n, 0xEDE95An, BigInt(host), BigInt(iface));\n"


def make_fixture(root, overrides=None):
    files = {
        "tools/m11/REPORT.md": M11_REPORT,
        "tools/m11/REPORT_APPENDIX_1430.md": APPENDIX,
        "tools/m11/REPORT_N2714.md": M11_N2714,
        "tools/gui/flengine/REPORT.md": GUI_REPORT,
        "tools/gui/flengine/REPORT_APPENDIX.md": APPENDIX_7,
        "tools/gui/flengine/REPORT_APPENDIX_2880.md": APPENDIX_2880,
        "tools/gui/flengine/cfi_probe.mjs": CFI_PROBE,
        "tools/gui/flengine/results/boot.json": json.dumps(GUI_BOOT),
        "tools/gui/flengine/results/survey_soft.json": json.dumps(GUI_SURVEY),
        "tools/flelift/boot/results/boot_summary_plain.json": json.dumps(X64_BOOT),
        "tools/flelift/boot/results/survey.json": json.dumps(X64_SURVEY),
        "tools/flelift/boot/REPORT.md": X64_REPORT,
        "tools/liftdiff/REPORT_LD26.md": NATIVE,
        "tools/startup/STARTUP.md": STARTUP,
    }
    files.update(overrides or {})
    for rel, text in files.items():
        if text is None:
            continue
        p = Path(root) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return root


def fixed_commit(rel):
    return "fixture"


def fixed_show(root):
    """測定 commit 時点の内容の代わりに作業ツリーの内容を返す (fixture に git 履歴は無い)。"""
    def show(rel, commit):
        p = Path(root) / rel
        return p.read_text(encoding="utf-8") if p.is_file() else None
    return show


class BootMetricTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="boot_metric_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def build(self, overrides=None):
        root = make_fixture(self.tmp / "repo", overrides)
        return bm.build(root, commit_of=fixed_commit, show_of=fixed_show(root))

    def by_id(self, doc):
        return {r["id"]: r for r in doc["records"]}

    def test_expected_values_from_fixed_fixture(self):
        recs = self.by_id(self.build())
        m11 = recs["m11-tolerant-sequential"]
        self.assertEqual(m11["units"]["ok"], 53)
        self.assertEqual(m11["units"]["skipped"], 3)
        self.assertEqual(m11["units"]["failed"], 1)
        self.assertEqual(m11["units"]["dispatched"], 57)
        self.assertEqual(m11["units"]["total"], 942)
        self.assertEqual(m11["stop"], {"unit": 57, "va": "0x16fde0", "kind": "halt0"})
        self.assertEqual(m11["commit"], "de50ffa")
        self.assertFalse(m11["create_fruity_instance"]["reached"])
        self.assertEqual(m11["create_fruity_instance"]["last_step"], "S09")

        skip = recs["m11-tolerant-skip"]
        self.assertEqual((skip["units"]["total"], skip["units"]["dispatched"]), (942, 942))
        self.assertEqual((skip["units"]["ok"], skip["units"]["noproc"], skip["units"]["skipped"]), (874, 1, 67))
        self.assertEqual((skip["units"]["miss"], skip["units"]["failed"]), (46, 21))
        self.assertIsNone(skip["stop"])
        self.assertEqual(skip["commit"], "cf64d9c8")
        self.assertEqual(skip["mode"], "tolerant-skip")
        self.assertFalse(skip["create_fruity_instance"]["reached"])

        survey = recs["m11-isolated-survey"]
        self.assertEqual((survey["units"]["ok"], survey["units"]["failed"],
                          survey["units"]["miss"], survey["units"]["noproc"]), (872, 23, 46, 1))
        self.assertEqual(survey["commit"], "7e149974")

        gui_boot = recs["m11-gui-tolerant"]
        self.assertEqual(gui_boot["units"]["ok"], 52)
        self.assertEqual(gui_boot["units"]["failed"], 1)
        self.assertEqual(gui_boot["commit"], "703b4857")
        self.assertEqual(gui_boot["gui_natural"], {"RegisterClassW": 0, "CreateWindowExW": 0})

        gui_survey = recs["m11-gui-survey"]
        self.assertEqual(gui_survey["units"]["ok"], 870)
        self.assertEqual(gui_survey["units"]["failed"], 24)
        self.assertEqual(gui_survey["commit"], "719f1c43")
        self.assertEqual(gui_survey["gui_natural"], {"RegisterClassW": 2, "CreateWindowExW": 2})

        x64 = recs["x64c-strict-sequential"]
        self.assertEqual(x64["units"]["dispatched"], 209)
        self.assertEqual(x64["units"]["ok"], 208)
        self.assertEqual(x64["stop"], {"unit": 209, "va": "0x816e80", "kind": "oob"})
        self.assertEqual(x64["probes"], {"getmem": 1886, "freemem": 776})
        self.assertIsNone(x64["commit"])

        x64s = recs["x64c-isolated-survey"]
        self.assertEqual((x64s["units"]["ok"], x64s["units"]["failed"], x64s["units"]["uncovered"]),
                         (892, 3, 47))

        native = recs["native-ref-hybrid"]
        self.assertEqual((native["units"]["ok"], native["units"]["total"], native["first_fail"]),
                         (928, 942, 830))
        self.assertEqual(native["commit"], "2ca85816")

    def test_measured_commit_is_separate_from_file_last_commit(self):
        recs = self.by_id(self.build())
        m11_src = recs["m11-tolerant-sequential"]["source"]
        self.assertTrue(any(s["measured_commit"] == "de50ffa" for s in m11_src))
        self.assertTrue(any(s["measured_commit"] == "6654322" for s in m11_src))
        self.assertTrue(all(s["file_last_commit"] == "fixture" for s in m11_src))
        x64 = recs["x64c-strict-sequential"]
        self.assertTrue(all(s["measured_commit"] is None for s in x64["source"]))
        self.assertIn("commit", x64["null_reasons"])

    def test_file_last_commit_is_8_chars_in_a_small_repo(self):
        tmp = tempfile.mkdtemp()
        try:
            git = ["git", "-C", tmp, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
            subprocess.run(["git", "-C", tmp, "init", "-q"], check=True)
            (Path(tmp) / "f.txt").write_text("x\n", encoding="utf-8")
            subprocess.run(git + ["add", "f.txt"], check=True)
            subprocess.run(git + ["commit", "-q", "-m", "x"], check=True)
            self.assertRegex(bm.git_commit(Path(tmp), "f.txt"), r"^[0-9a-f]{8}$")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_every_null_has_a_reason(self):
        for rec in self.build()["records"]:
            for key, value in rec["units"].items():
                if value is None:
                    self.assertIn(f"units.{key}", rec["null_reasons"], rec["id"])
            for key in ("commit", "stop", "create_fruity_instance", "gui_natural",
                        "first_wm_paint", "pixels", "probes"):
                if rec.get(key) is None:
                    self.assertIn(key, rec["null_reasons"], f"{rec['id']} {key}")

    def test_every_source_has_locator_and_commit_fields(self):
        for rec in self.build()["records"]:
            self.assertTrue(rec["source"], rec["id"])
            for src in rec["source"]:
                self.assertIn("measured_commit", src)
                self.assertEqual(src["file_last_commit"], "fixture")
                self.assertNotIn("commit", src)

    def test_output_is_deterministic(self):
        self.assertEqual(bm.render(self.build()), bm.render(self.build()))

    def test_negative_missing_table_row_fails(self):
        broken = M11_REPORT.replace("| `de50ffa` (指摘対応 3 点, n=1, 増分 build) | 53 |", "| `xxxxxxx` | 53 |")
        with self.assertRaises(bm.MetricError):
            self.build({"tools/m11/REPORT.md": broken})

    def test_negative_missing_json_key_fails(self):
        broken = json.dumps({"boot": {"units_total": 942, "threw": {"cls": "oob"},
                                      "stopped_at_1based": 209, "getmem": 1886, "freemem": 776}})
        with self.assertRaises(bm.MetricError):
            self.build({"tools/flelift/boot/results/boot_summary_plain.json": broken})

    def test_negative_missing_source_file_fails(self):
        with self.assertRaises(bm.MetricError):
            self.build({"tools/liftdiff/REPORT_LD26.md": None})

    def test_negative_inconsistent_survey_sum_fails(self):
        broken = APPENDIX.replace("ok 872 / trap 23", "ok 900 / trap 23")
        with self.assertRaises(bm.MetricError):
            self.build({"tools/m11/REPORT_APPENDIX_1430.md": broken})

    def test_negative_gui_survey_report_mismatch_fails(self):
        broken = GUI_REPORT.replace("S1 `870/1/47/24/0`", "S1 `871/1/47/24/0`")
        with self.assertRaises(bm.MetricError):
            self.build({"tools/gui/flengine/REPORT.md": broken})

    def test_negative_harness_mentions_create_fruity_instance_fails(self):
        with self.assertRaises(bm.MetricError):
            self.build({"tools/m11/hit.mjs": "CreateFruityInstance(0xC0)"})

    def test_doc_mention_of_create_fruity_instance_is_not_a_call(self):
        self.build({"tools/m11/note.md": "CreateFruityInstance は呼んでいない"})

    def test_negative_tolerant_sum_mismatch_fails(self):
        broken = M11_N2714.replace("ok 874 / noproc 1 / skipped 67", "ok 875 / noproc 1 / skipped 67")
        with self.assertRaises(bm.MetricError):
            self.build({"tools/m11/REPORT_N2714.md": broken})

    def test_negative_tolerant_table_mismatch_fails(self):
        broken = M11_N2714.replace("942 試行・ok 874", "942 試行・ok 873")
        with self.assertRaises(bm.MetricError):
            self.build({"tools/m11/REPORT_N2714.md": broken})

    def test_flengine_record_values(self):
        fle = self.by_id(self.build())["flengine-cfi-probe"]
        self.assertTrue(fle["create_fruity_instance"]["reached"])
        self.assertEqual(fle["create_fruity_instance"]["last_step"], "S12")
        self.assertEqual(fle["stop"]["api"], "EnterCriticalSection")
        self.assertEqual(fle["stop"]["cs"], "0x12bd390")
        self.assertEqual(fle["commit"], "ae963e28")
        self.assertEqual(fle["gui_natural"], {"RegisterClassW": 0, "CreateWindowExW": 0})
        files = {s["file"] for s in fle["source"]}
        self.assertIn(bm.FLE_APPENDIX_2880, files)
        self.assertIn(bm.FLE_APPENDIX, files)

    def test_negative_probe_source_removed_fails(self):
        with self.assertRaises(bm.MetricError):
            self.build({"tools/gui/flengine/cfi_probe.mjs": None})

    def test_negative_probe_cs_row_changed_fails(self):
        broken = APPENDIX_2880.replace("CS-MISS key=", "CS-MIS key=")
        with self.assertRaises(bm.MetricError):
            self.build({"tools/gui/flengine/REPORT_APPENDIX_2880.md": broken})

    def test_negative_fail_fast_api_mismatch_fails(self):
        broken = APPENDIX_7.replace("EnterCriticalSection (未初期化", "CreateEventW (未初期化")
        with self.assertRaises(bm.MetricError):
            self.build({"tools/gui/flengine/REPORT_APPENDIX.md": broken})

    def test_negative_non_probe_call_in_gui_dir_fails(self):
        with self.assertRaises(bm.MetricError):
            self.build({"tools/gui/flengine/harness.mjs": "mod._CreateFruityInstance(0xC0n, 0xEDE95An)\n"})

    def test_comment_mention_is_not_a_call(self):
        self.build({"tools/m11/note.sh": "CH=x   # boot7 = CreateFruityInstance (0x1375990)\n"})

    def test_call_after_string_with_comment_marker_fails(self):
        with self.assertRaises(bm.MetricError):
            self.build({"tools/m11/harness.mjs": 'log("a // b"); mod._CreateFruityInstance(0xC0n)\n'})


if __name__ == "__main__":
    unittest.main(verbosity=2)
