"""status_sync.py を固定 fixture で検査する (#2361)。

実行: python3 -m unittest tools/pm/test_status_sync.py
GitHub には触れない (REST の応答は FakeGH / FakeOpener で差し替える)。STATUS.md は一時ファイルに写す。
"""
import io
import json
import os
import re
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from email.message import Message
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import status_sync as sc  # noqa: E402

REAL_STATUS = os.path.join(HERE, "..", "..", "docs", "STATUS.md")
NOW = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
NOW_S = "2026-10-14T12:00Z"
MEASURE = re.compile(r"[0-9]+\.[0-9]+|[0-9] ?%|[0-9] ?(ms|GiB|MiB|MB|KB)\b|[0-9] s\b")


def ts(minutes_ago, now=NOW):
    return (now - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def pr(number, title, body="", ago=60, labels=(), base="main", merged=True):
    t = ts(ago)
    return {"number": number, "title": title, "body": body, "state": "closed",
            "merged_at": t if merged else None, "updated_at": t, "base": {"ref": base},
            "labels": [{"name": n} for n in labels]}


def issue(number, title, body="", labels=(), ago=120):
    return {"number": number, "title": title, "body": body, "updated_at": ts(ago),
            "labels": [{"name": n} for n in labels]}


class FakeGH:
    """get(path, params) の差し替え。pulls / issues / issues/N だけ答える。"""

    def __init__(self, prs, issues=()):
        self.prs = list(prs)
        self.issues = {i["number"]: i for i in issues}
        self.calls = []
        self.pages = []

    def __call__(self, path, params=None):
        params = params or {}
        self.calls.append(path)
        if path == "pulls":
            rows = [p for p in self.prs if p["state"] == "closed" and p["base"]["ref"] == params["base"]]
            rows.sort(key=lambda p: p["updated_at"], reverse=True)
            self.pages.append(params["page"])
            return rows[(params["page"] - 1) * params["per_page"]:params["page"] * params["per_page"]]
        if path == "issues":
            rows = sorted((i for i in self.issues.values() if i["updated_at"] >= params["since"]),
                          key=lambda i: i["updated_at"], reverse=True)
            return rows[(params["page"] - 1) * params["per_page"]:params["page"] * params["per_page"]]
        if path.startswith("issues/"):
            return self.issues.get(int(path.split("/")[1]))
        raise AssertionError(f"想定外の path: {path}")


class FakeResp:
    def __init__(self, body, remaining):
        self.headers = Message()
        self.headers["X-Ratelimit-Remaining"] = str(remaining)
        self._b = json.dumps(body).encode()

    def read(self, *a):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeOpener:
    def __init__(self, remaining):
        self.remaining = remaining
        self.urls = []

    def __call__(self, req, timeout=None):
        self.urls.append(req.full_url)
        return FakeResp([], self.remaining)


def real_map_block():
    with open(REAL_STATUS, encoding="utf-8") as f:
        return sc.MAP_RE.search(f.read()).group(0)


def status_text(inner=None):
    inner = inner if inner is not None else "- 期間: (未実行)\n- merge 件数: (未実行)\n- updated: (未実行)"
    return ("# STATUS (test)\n\n手書き A: 更新責任は PM。\n\n## 5. 要約\n\n"
            f"{sc.BEGIN}\n{inner}\n{sc.END}\n\n手書き B\n\n{real_map_block()}\n\n末尾の 1 行\n")


def issues_20():
    return [
        issue(1, "[LD-5] 件数揺れ"), issue(2, "[ICALL-7] 落ち"), issue(3, "[PLG-F3-24] host 構造体"),
        issue(4, "[PLG-E10] 一括 lift"), issue(5, "[M11-N101] unit 158"), issue(6, "[CI-43] pr-lint"),
        issue(7, "[DOCS-22] STATUS"), issue(9, "題名に AREA なし", labels=["area:gui"]),
        issue(20, "[HB-H22] iargs"), issue(21, "題名に AREA なし", body="MS5 の続き"),
    ]


def prs_20():
    return [
        pr(101, "fix: a", "Closes #1"),
        pr(102, "fix: b", "Refs #2"),
        pr(103, "fix: c", "Fixes #3"),
        pr(104, "fix: d", "Closes #4"),
        pr(105, "fix: e", "Closes #5"),
        pr(106, "fix: f", "Closes #6"),
        pr(107, "docs: g", "Closes #7"),
        pr(108, "[KH-25] Ghidra route"),
        pr(109, "fix: h", "Closes #9", labels=["oc:ready"]),
        pr(110, "feat(ipp): pffft 差替え", "p99 は 0.5 ms で 12% 改善、3 GiB を使う"),
        pr(111, "fix(ldfix): x"),
        pr(112, "docs: MS6 の記述"),
        pr(113, "chore: misc", "MS9 の続き。親: #3"),
        pr(114, "feat(plugins/framework): x"),
        pr(115, "chore: tidy"),
        pr(116, "misc", "Closes #99"),
        pr(117, "[T-SH-3] x"),
        pr(118, "[P0c-3] x"),
        pr(119, "fix(m11): 12.5 ms 短縮 (99%)"),
        pr(120, "fix: i", "Closes #20"),
    ]


EXPECT_20 = {
    101: "liftdiff", 102: "icall", 103: "plugins/framework", 104: "plugins", 105: "m11", 106: "その他",
    107: "その他", 108: "targets/kilohearts", 109: "gui", 110: "ipp", 111: "m11/ldfix", 112: "MS6",
    113: "MS9", 114: "plugins/framework", 115: "その他", 116: "その他", 117: "shared", 118: "plugins/p0c",
    119: "m11", 120: "hostbridge",
}


def noise():
    return [
        pr(130, "[LD-9] 古い", ago=25 * 60),
        pr(133, "[LD-9] 閉じただけ", merged=False),
        pr(134, "docs(status): sync merged PRs", ago=30),
        pr(135, "[LD-9] 別 base", base="dev"),
    ]


class Env(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "STATUS.md")

    def write(self, text):
        with open(self.path, "w", encoding="utf-8", newline="") as f:
            f.write(text)

    def read(self):
        with open(self.path, "rb") as f:
            return f.read()

    def run_main(self, gh, *args, now=NOW_S):
        out, err = io.StringIO(), io.StringIO()
        rc = sc.main(["--status", self.path, "--now", now, *args], get=gh, out=out, err=err)
        return rc, out.getvalue(), err.getvalue()

    def inner(self):
        t = self.read().decode()
        b, e = sc.find_auto(t)
        return t[b:e]


class MappingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(REAL_STATUS, encoding="utf-8") as f:
            cls.mapper = sc.Mapper(sc.load_map(f.read()))

    # (a) 写像
    def test_20_prs_map_as_expected(self):
        gh = FakeGH([], issues_20())
        issues = {i["number"]: i for i in issues_20()}
        got = {p["number"]: self.mapper.classify(p, issues) for p in prs_20()}
        self.assertEqual(got, EXPECT_20)
        self.assertEqual(len(got), 20)

    def test_area_longest_prefix(self):
        for title, want in [("[L-12] x", "flp"), ("[LD-5] x", "liftdiff"), ("[HB-H22] x", "hostbridge"),
                            ("[H-1] x", "hosting"), ("[PLG-P0b-15] x", "plugins/framework"),
                            ("[PLG-X-4] x", "plugins"), ("[PLG-G2-3] x", "plugins"), ("[T-SH-12] x", "shared"),
                            ("[ST-T16 子-3] x", "startup"), ("[SHX-T9f] x", "shimx"), ("[MX] x", "targets/massivex"),
                            ("[CI-4-hostbridge-nfo] x", "その他"), ("[ZZZ-1] x", None), ("AREA なし", None)]:
            self.assertEqual(self.mapper.area_target(title), want, title)

    def test_priority_issue_area_over_pr_title_and_ms(self):
        issues = {1: issue(1, "[LD-5] x")}
        p = pr(1000, "[KH-1] MS6 docs(m11)", "Closes #1")
        self.assertEqual(self.mapper.classify(p, issues), "liftdiff")
        self.assertEqual(self.mapper.classify(pr(1001, "[KH-1] MS6"), {}), "targets/kilohearts")
        self.assertEqual(self.mapper.classify(pr(1002, "docs: MS13 と MS6"), {}), "MS6")

    def test_closes_does_not_follow_parent_or_self(self):
        self.assertEqual(sc.linked_numbers(pr(5, "x", "親: #1\nCloses #5\nrefs #7, fixes #8\n(Prefs #9)")), [7, 8])

    # 写像表と §3 の整合 (実ファイル)
    def test_real_map_targets_exist_in_status_tables(self):
        with open(REAL_STATUS, encoding="utf-8") as f:
            text = f.read()
        d = sc.load_map(text)
        valid = set(d["ms"]) | set(d["subsystems"]) | {sc.OTHER}
        for k in ("areas", "labels", "scopes"):
            for key, tgt in d[k].items():
                self.assertIn(tgt, valid, f"{k}[{key}] -> {tgt}")
        sec3 = text.split("## 3.")[1].split("## 4.")[0]
        names = set()
        for line in sec3.splitlines():
            m = re.match(r"\| `([^`]+)`", line)
            if not m:
                continue
            cell = m.group(1)
            br = re.search(r"\{([^}]*)\}", cell)
            if br:
                names |= {cell[:br.start()] + x for x in br.group(1).split(",")}
            names.add(cell)
        for s in d["subsystems"]:
            self.assertIn(s, names, f"subsystems の {s} が STATUS.md §3 に無い")

    def test_real_status_has_initial_auto_section(self):
        with open(REAL_STATUS, encoding="utf-8") as f:
            text = f.read()
        sc.find_auto(text)
        self.assertIn("status_sync.py", text.split("---")[0])
        self.assertLess(len(text.splitlines()), 300)


class SyncTest(Env):
    def sync(self, prs, issues=(), *args, now=NOW_S):
        gh = FakeGH(prs, issues)
        rc, out, err = self.run_main(gh, *args, now=now)
        return gh, rc, out, err

    def test_render_counts_and_representatives(self):
        self.write(status_text())
        gh, rc, out, err = self.sync(prs_20() + noise(), issues_20())
        self.assertEqual(rc, 0, err)
        inner = self.inner()
        self.assertIn("- 期間: 2026-10-13T12:00Z 〜 2026-10-14T12:00Z (直近 24 時間)", inner)
        self.assertIn("- merge 件数: 20", inner)
        self.assertIn(f"- updated: {NOW_S}", inner)
        self.assertIn("| MS6 | 1 | #112 |", inner)
        self.assertIn("| MS9 | 1 | #113 |", inner)
        self.assertIn("| `m11` | 2 | #119, #105 |", inner)
        self.assertIn("| `plugins/framework` | 2 | #114, #103 |", inner)
        rows = re.findall(r"^\| .+ \| (\d+) \|", inner, re.M)
        self.assertEqual(sum(map(int, rows)), 20)
        self.assertTrue(all(len(re.findall(r"#\d+", r)) <= 3 for r in inner.splitlines()))
        self.assertTrue(inner.rstrip("\n").splitlines()[-1].startswith("| その他 | 4 |"))

    def test_representatives_are_capped_at_three(self):
        self.write(status_text())
        prs = [pr(200 + k, f"fix(icall): {k}") for k in range(5)]
        self.sync(prs)
        self.assertIn("| `icall` | 5 | #204, #203, #202 |", self.inner())

    # (b) 冪等
    def test_idempotent_and_check(self):
        self.write(status_text())
        gh = FakeGH(prs_20() + noise(), issues_20())
        rc, _, _ = self.run_main(gh, "--check")
        self.assertEqual(rc, 1)
        self.assertEqual(self.read(), status_text().encode())
        rc, out, _ = self.run_main(gh)
        self.assertEqual(rc, 0)
        first = self.read()
        rc, out, _ = self.run_main(gh)
        self.assertEqual((rc, self.read()), (0, first))
        self.assertIn("差分なし", out)
        rc, _, _ = self.run_main(gh, "--check")
        self.assertEqual(rc, 0)

    def test_same_content_later_clock_does_not_rewrite(self):
        self.write(status_text())
        gh = FakeGH(prs_20(), issues_20())
        self.run_main(gh)
        first = self.read()
        rc, _, _ = self.run_main(FakeGH(prs_20(), issues_20()), now="2026-10-14T12:30Z")
        self.assertEqual((rc, self.read()), (0, first))

    def test_check_prints_diff_and_does_not_write(self):
        self.write(status_text())
        rc, out, _ = self.run_main(FakeGH(prs_20(), issues_20()), "--check")
        self.assertEqual(rc, 1)
        self.assertIn("+- merge 件数: 20", out)
        self.assertEqual(self.read(), status_text().encode())

    # (c) 自動節の外が 1 byte でも変わると fail
    def test_outside_is_byte_identical_after_write(self):
        before = status_text()
        self.write(before)
        self.run_main(FakeGH(prs_20(), issues_20()))
        after = self.read().decode()
        self.assertNotEqual(after, before)
        b, e = sc.find_auto(before)
        b2, e2 = sc.find_auto(after)
        self.assertEqual(before[:b], after[:b2])
        self.assertEqual(before[e:], after[e2:])

    def test_negative_control_outside_change_is_refused(self):
        before = status_text()
        orig = sc.splice
        places = {
            "先頭": lambda g: 0,
            "begin マーカー内": lambda g: g.index(sc.BEGIN) + 3,
            "end マーカー内": lambda g: g.index(sc.END) + 3,
            "end の直後": lambda g: g.index(sc.END) + len(sc.END),
            "写像ブロック内": lambda g: g.index("<!-- status-map") + 20,
            "末尾の直前": lambda g: len(g) - 1,
            "末尾": lambda g: len(g),
        }
        for name, at in places.items():
            def buggy(text, inner, at=at):
                good = orig(text, inner)
                i = at(good)
                return good[:i] + "X" + good[i:]
            self.write(before)
            with mock.patch.object(sc, "splice", buggy):
                rc, _, err = self.run_main(FakeGH(prs_20(), issues_20()))
            self.assertEqual(rc, 2, name)
            self.assertIn("自動節の外", err)
            self.assertEqual(self.read(), before.encode(), name)

    def test_outside_function_detects_every_outside_byte(self):
        t = status_text()
        b, e = sc.find_auto(t)
        base = sc.outside(t)
        for i in list(range(0, b)) + list(range(e, len(t))):
            mutated = t[:i] + ("Y" if t[i] != "Y" else "Z") + t[i + 1:]
            try:
                self.assertNotEqual(sc.outside(mutated), base, f"i={i}")
            except sc.Invalid:
                pass  # マーカー自体の破壊は構造エラーとして検出される
        for i in range(b, e):
            mutated = t[:i] + ("Y" if t[i] != "Y" else "Z") + t[i + 1:]
            self.assertEqual(sc.outside(mutated), base, f"i={i}")

    def test_markers_missing_or_duplicated_is_error(self):
        for text in (status_text().replace(sc.END, ""), status_text() + sc.BEGIN,
                     status_text().replace(sc.BEGIN, "@@").replace(sc.END, sc.BEGIN).replace("@@", sc.END)):
            self.write(text)
            gh = FakeGH([])
            rc, _, err = self.run_main(gh)
            self.assertEqual(rc, 2)
            self.assertEqual(gh.calls, [])
            self.assertEqual(self.read(), text.encode())

    def test_missing_map_is_error(self):
        text = status_text().replace("<!-- status-map", "<!-- not-a-map")
        self.write(text)
        rc, _, err = self.run_main(FakeGH([]))
        self.assertEqual(rc, 2)
        self.assertIn("写像ブロック", err)

    # (d) 6 時間未満は no-op
    def test_debounce_under_interval_is_noop(self):
        self.write(status_text())
        self.run_main(FakeGH(prs_20(), issues_20()), now="2026-10-14T06:01Z")
        before = self.read()
        gh = FakeGH(prs_20() + [pr(300, "[LD-1] 新規")], issues_20())
        rc, out, _ = self.run_main(gh, "--min-interval-hours", "6")
        self.assertEqual(rc, 0)
        self.assertIn("no-op", out)
        self.assertEqual(gh.calls, [])
        self.assertEqual(self.read(), before)

    def test_debounce_negative_control_at_interval_runs(self):
        self.write(status_text())
        self.run_main(FakeGH(prs_20(), issues_20()), now="2026-10-14T06:00Z")
        gh = FakeGH(prs_20() + [pr(300, "[LD-1] 新規")], issues_20())
        rc, out, _ = self.run_main(gh, "--min-interval-hours", "6")
        self.assertEqual(rc, 0)
        self.assertNotIn("no-op", out)
        self.assertTrue(gh.calls)
        self.assertIn("- merge 件数: 21", self.inner())

    def test_debounce_off_by_default_and_unparsable_updated_runs(self):
        self.write(status_text())
        gh = FakeGH(prs_20(), issues_20())
        rc, out, _ = self.run_main(gh, "--min-interval-hours", "6")
        self.assertTrue(gh.calls)
        self.run_main(gh, "--min-interval-hours", "0")
        self.assertIn("- merge 件数: 20", self.inner())

    # (e) 写像不能 PR は「その他」の件数だけ
    def test_unmappable_prs_are_counted_only(self):
        self.write(status_text())
        prs = [pr(401, "chore: tidy"), pr(402, "misc", "Closes #99"), pr(403, "fix(icall): x")]
        self.sync(prs)
        inner = self.inner()
        self.assertIn("| その他 | 2 | — |", inner)
        self.assertIn("| `icall` | 1 | #403 |", inner)
        self.assertNotIn("#401", inner)
        self.assertNotIn("#402", inner)

    def test_no_merge_still_renders_other_row(self):
        self.write(status_text())
        self.sync([])
        inner = self.inner()
        self.assertIn("- merge 件数: 0", inner)
        self.assertIn("| その他 | 0 | — |", inner)

    # (f) 24 時間より古い merge を数えない
    def test_window_boundary(self):
        self.write(status_text())
        prs = [pr(501, "fix(icall): a", ago=24 * 60 - 1), pr(502, "fix(icall): b", ago=24 * 60),
               pr(503, "fix(icall): c", ago=24 * 60 + 1), pr(504, "fix(icall): d", ago=48 * 60)]
        self.sync(prs)
        inner = self.inner()
        self.assertIn("- merge 件数: 2", inner)
        self.assertIn("| `icall` | 2 | #502, #501 |", inner)

    def test_hours_option_changes_window(self):
        self.write(status_text())
        prs = [pr(501, "fix(icall): a", ago=60), pr(502, "fix(icall): b", ago=3 * 60)]
        self.sync(prs, (), "--hours", "2")
        inner = self.inner()
        self.assertIn("- merge 件数: 1", inner)
        self.assertIn("(直近 2 時間)", inner)

    def test_noise_not_counted(self):
        self.write(status_text())
        self.sync(noise(), issues_20())
        self.assertIn("- merge 件数: 0", self.inner())

    def test_pagination_stops_at_cutoff_without_loss(self):
        self.write(status_text())
        old = [pr(600 + k, "fix(icall): old", ago=26 * 60 + k) for k in range(40)]
        with mock.patch.object(sc, "PER_PAGE", 4):
            gh, rc, _, err = self.sync(prs_20() + old, issues_20())
        self.assertEqual(rc, 0, err)
        self.assertIn("- merge 件数: 20", self.inner())
        self.assertEqual(max(gh.pages), 6)

    def test_bulk_issue_preload_when_many_links(self):
        self.write(status_text())
        n = sc.PRELOAD_MIN + 5
        prs = [pr(700 + k, "fix: x", f"Closes #{800 + k}") for k in range(n)]
        isl = [issue(800 + k, "[ICALL-1] x") for k in range(n)]
        gh, rc, _, err = self.sync(prs, isl)
        self.assertEqual(rc, 0, err)
        self.assertEqual([c for c in gh.calls if c.startswith("issues/")], [])
        self.assertIn(f"| `icall` | {n} |", self.inner())

    def test_few_links_fetch_individually(self):
        self.write(status_text())
        gh, rc, _, _ = self.sync([pr(700, "fix: x", "Closes #800")], [issue(800, "[ICALL-1] x")])
        self.assertEqual(gh.calls.count("issues"), 0)
        self.assertEqual(gh.calls.count("issues/800"), 1)

    # (g) 測定値のパターンを自動節に書かない
    def test_no_measurement_patterns_in_auto_section(self):
        self.write(status_text())
        self.sync(prs_20() + noise(), issues_20())
        inner = self.inner()
        self.assertIsNone(MEASURE.search(inner), MEASURE.search(inner))
        for needle in ("12.5", "99%", "0.5 ms", "3 GiB", "pffft"):
            self.assertNotIn(needle, inner)

    def test_measurement_checker_negative_control(self):
        for s in ("12.5", "短縮 99%", "0.5 ms", "3 GiB", "8 MiB", "2 MB", "4 KB", "5 s", "x 12.5 ms"):
            self.assertIsNotNone(MEASURE.search(s), s)
        self.assertIsNone(MEASURE.search("- merge 件数: 20\n| `m11` | 2 | #119, #105 |\n2026-10-14T12:00Z"))

    def test_status_sync_prs_are_not_counted(self):
        self.write(status_text())
        self.sync([pr(900, "docs(status): sync merged PRs"), pr(901, "docs(status): sync merged PRs (2)")])
        self.assertIn("- merge 件数: 0", self.inner())


class ClientTest(Env):
    def run_with(self, remaining):
        self.write(status_text())
        opener = FakeOpener(remaining)
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {"GH_TOKEN": "t"}):
            rc = sc.main(["--status", self.path, "--now", NOW_S], out=out, err=err, opener=opener)
        return rc, opener, err.getvalue()

    # 4. rate limit の残りが 1,500 未満なら中断する
    def test_aborts_below_threshold_and_does_not_write(self):
        rc, opener, err = self.run_with(1499)
        self.assertEqual(rc, 3)
        self.assertIn("1499", err)
        self.assertEqual(len(opener.urls), 1)
        self.assertEqual(self.read(), status_text().encode())

    def test_continues_at_threshold(self):
        rc, opener, err = self.run_with(1500)
        self.assertEqual(rc, 0, err)
        self.assertIn("- merge 件数: 0", self.inner())
        self.assertIn("graphql=0", err)

    def test_rest_only(self):
        rc, opener, _ = self.run_with(5000)
        self.assertTrue(opener.urls)
        for u in opener.urls:
            self.assertTrue(u.startswith("https://api.github.com/repos/"), u)
            self.assertNotIn("graphql", u)
        self.assertIn("state=closed", opener.urls[0])
        self.assertIn("sort=updated", opener.urls[0])

    def test_no_token_is_error(self):
        self.write(status_text())
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(sc.subprocess, "run", return_value=mock.Mock(returncode=1, stdout="")):
            rc = sc.main(["--status", self.path], out=io.StringIO(), err=io.StringIO())
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
