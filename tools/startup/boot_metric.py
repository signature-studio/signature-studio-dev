#!/usr/bin/env python3
"""起動指標 tools/startup/boot_metric.json を算出する (#2713 WIN-2)。

値は tools/**/REPORT*.md の表行・節と results/*.json から抽出する。手で書かない。
抽出元が無い・一意に決まらない・照合が合わない場合は MetricError で止まる (値を捏造しない)。
出典が無い項目は null とし、理由を null_reasons に書く。

commit は 2 種類を分けて持つ (混同しない):
  source[].measured_commit  : REPORT の表行・節・見出しに測定 commit として書かれたもの (無ければ null)
  source[].file_last_commit : 出典ファイルの最終更新 commit (git log -1 -- <file>)。測定 commit ではない
  record.commit             : measured_commit から取る測定 commit。書かれていなければ null (null_reasons に理由)
derived には、リテラルではなく出典の値から導いた項目の規則を書く。
harness 構造による判定 (CreateFruityInstance 未到達) は、対象ディレクトリの非 work ファイルに
呼出し構文 (コメント・.md・allow を除く) の CreateFruityInstance が 0 件であることを検査してから用いる。

使い方:
  python3 tools/startup/boot_metric.py                 # boot_metric.json を書き出す
  python3 tools/startup/boot_metric.py --check         # 既存ファイルが再算出結果と一致するか (不一致は exit 1)
  python3 tools/startup/boot_metric.py --route x64c    # 路線の現在値を標準出力へ (m11 / x64c / native-ref / flengine)
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SCHEMA = "boot_metric/v1"
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OUT = HERE / "boot_metric.json"

UNITS = 942  # unit 表の本数 (各出典の合計で検査する)
STOP_UNITS = 1  # 停止 unit 1 本 (REPORT の「unit N 後に Halt0」・boot の threw は停止 unit が 1 本失敗する)
SKIP_DIRS = {"work", "venv", "node_modules", "dist", ".wrangler", ".git"}

M11_DIR = "tools/m11"
M11_REPORT = "tools/m11/REPORT.md"
M11_APPENDIX = "tools/m11/REPORT_APPENDIX_1430.md"
M11_N2714 = "tools/m11/REPORT_N2714.md"
GUI_DIR = "tools/gui/flengine"
GUI_REPORT = "tools/gui/flengine/REPORT.md"
GUI_BOOT = "tools/gui/flengine/results/boot.json"
GUI_SURVEY = "tools/gui/flengine/results/survey_soft.json"
X64_DIR = "tools/flelift/boot"
X64_BOOT = "tools/flelift/boot/results/boot_summary_plain.json"
X64_SURVEY = "tools/flelift/boot/results/survey.json"
X64_REPORT = "tools/flelift/boot/REPORT.md"
NATIVE_REPORT = "tools/liftdiff/REPORT_LD26.md"
STARTUP = "tools/startup/STARTUP.md"
FLE_APPENDIX = "tools/gui/flengine/REPORT_APPENDIX.md"
FLE_APPENDIX_2880 = "tools/gui/flengine/REPORT_APPENDIX_2880.md"
CFI_PROBE = "tools/gui/flengine/cfi_probe.mjs"

COMMENT_LINE = ("#", "//", "/*", "* ", "*/")
COMMENT_MARK = re.compile(r"(#|//)\s")


def _call_re(word):
    w = re.escape(word)
    return re.compile(rf'(?<![@\w])_?{w}\s*\(|["\']_?{w}["\']')


def _strip_tail(line):
    """文字列リテラルの外にある行末コメント (空白の後の `#`・`//` + 空白) を落とす。"""
    quote = None
    i = 0
    while i < len(line):
        c = line[i]
        if quote:
            if c == "\\":
                i += 1
            elif c == quote:
                quote = None
        elif c in "\"'`":
            quote = c
        elif c in "#/" and (i == 0 or line[i - 1].isspace()) and COMMENT_MARK.match(line, i):
            return line[:i]
        i += 1
    return line


def _code_text(text):
    out = []
    for line in text.split("\n"):
        if line.lstrip().startswith(COMMENT_LINE):
            continue
        out.append(_strip_tail(line))
    return "\n".join(out)


class MetricError(Exception):
    """抽出元が無い・一意に決まらない・照合が合わないときの例外。値を捏造しない。"""


def git_commit(root, rel):
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "log", "-1", "--format=%h", "--", rel],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        out = ""
    return out or None


def git_show(root, commit, rel):
    try:
        return subprocess.run(
            ["git", "-C", str(root), "show", f"{commit}:{rel}"],
            capture_output=True, text=True, check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


class Source:
    def __init__(self, root, commit_of=None, show_of=None):
        self.root = Path(root)
        self.commit_of = commit_of or (lambda rel: git_commit(self.root, rel))
        self.show_of = show_of or (lambda rel, commit: git_show(self.root, commit, rel))
        self.cache = {}
        self.used = []

    def begin(self):
        self.used = []

    def end(self):
        return list(self.used)

    def _text(self, rel):
        if rel not in self.cache:
            path = self.root / rel
            if not path.is_file():
                raise MetricError(f"出典が無い: {rel}")
            self.cache[rel] = path.read_text(encoding="utf-8")
        return self.cache[rel]

    def _note(self, rel, locator, measured=None):
        entry = {
            "file": rel,
            "locator": locator,
            "measured_commit": measured,
            "file_last_commit": self.commit_of(rel),
        }
        if entry not in self.used:
            self.used.append(entry)

    def at_commit(self, rel, commit):
        """測定 commit 時点の出典の内容 (作業ツリーの後の更新は読まない)。"""
        key = (rel, commit)
        if key not in self.cache:
            text = self.show_of(rel, commit)
            if text is None:
                raise MetricError(f"測定 commit に出典が無い: {commit}:{rel}")
            self.cache[key] = text
        return self.cache[key]

    def json_value(self, rel, dotted, measured=None, at=None):
        cur = json.loads(self._text(rel) if at is None else self.at_commit(rel, at))
        for key in dotted.split("."):
            if not isinstance(cur, dict) or key not in cur:
                raise MetricError(f"JSON に無い: {rel} :: {dotted}")
            cur = cur[key]
        self._note(rel, f"json:{dotted}", measured)
        return cur

    def reach_calls(self, rel, name, measured=None, at=None):
        doc = json.loads(self._text(rel) if at is None else self.at_commit(rel, at))
        reach = doc.get("reach")
        if not isinstance(reach, list):
            raise MetricError(f"reach 配列が無い: {rel}")
        self._note(rel, f"json:reach[{name}].calls (配列に無ければ 0)", measured)
        for row in reach:
            if row.get("name") == name:
                return int(row["calls"])
        return 0

    def section(self, rel, heading):
        lines = self._text(rel).split("\n")
        level = len(heading) - len(heading.lstrip("#"))
        starts = [i for i, line in enumerate(lines) if line.startswith(heading)]
        if len(starts) != 1:
            raise MetricError(f"節の見出しが一意でない ({len(starts)} 件): {rel} :: {heading}")
        start = starts[0]
        for i in range(start + 1, len(lines)):
            m = re.match(r"^(#+) ", lines[i])
            if m and len(m.group(1)) <= level:
                return "\n".join(lines[start:i])
        return "\n".join(lines[start:])

    def match(self, rel, heading, pattern, measured=None, commit_group=None):
        """節の中で pattern に一意に一致させ、group の並びを返す。
        measured: 節・表行に書かれた測定 commit (無ければ None)。commit_group を指定すると、その group を測定 commit とする。"""
        sec = self.section(rel, heading)
        hits = list(re.finditer(pattern, sec, re.M))
        if len(hits) != 1:
            raise MetricError(f"一意に一致しない ({len(hits)} 件): {rel} :: {heading} :: {pattern}")
        groups = hits[0].groups()
        if commit_group is not None:
            measured = groups[commit_group]
        self._note(rel, f"md:{heading} /{pattern}/", measured)
        return groups

    def match_commit(self, rel, heading, pattern):
        """節に書かれた測定 commit を返す (例: 測定 commit `7e149974`)。"""
        sec = self.section(rel, heading)
        hits = re.findall(pattern, sec)
        if len(set(hits)) != 1:
            raise MetricError(f"測定 commit が一意でない: {rel} :: {heading} :: {pattern}")
        self._note(rel, f"md:{heading} /{pattern}/", hits[0])
        return hits[0]

    def find(self, rel, pattern, measured_group=None):
        """ファイル全体で pattern に一意に一致させ、group の並びを返す。"""
        hits = list(re.finditer(pattern, self._text(rel), re.M))
        if len(hits) != 1:
            raise MetricError(f"一意に一致しない ({len(hits)} 件): {rel} :: {pattern}")
        groups = hits[0].groups()
        measured = groups[measured_group] if measured_group is not None else None
        self._note(rel, f"md: /{pattern}/", measured)
        return groups

    def exists(self, rel, pattern):
        if not re.search(pattern, self._text(rel), re.M):
            raise MetricError(f"存在確認に失敗: {rel} :: {pattern}")
        self._note(rel, f"存在確認 /{pattern}/")

    def absent(self, rel_dir, word, allow=()):
        """rel_dir 以下の非 work の実行ファイルに word の呼出し構文が 0 件であることを検査する。
        語の出現ではなく呼出し構文だけを数える (コメント行・行末コメント・.md・allow を除く)。
        .md は説明文であって呼出しではないので数えない (REPORT が『呼んでいない』と書くことを禁じないため)。"""
        base = self.root / rel_dir
        if not base.is_dir():
            raise MetricError(f"出典ディレクトリが無い: {rel_dir}")
        call = _call_re(word)
        hits = []
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for name in filenames:
                path = Path(dirpath) / name
                rel = path.relative_to(self.root).as_posix()
                if path.suffix == ".md" or rel in allow:
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                if call.search(_code_text(text)):
                    hits.append(rel)
        if hits:
            raise MetricError(f"{rel_dir} の非 work ファイルに {word} の呼出しがある: {hits[:3]}")
        self._note(rel_dir, f"grep 0 件 /{word}/ (呼出し構文・コメント/.md/allow を除く)")


def _cfi(src, harness_dir, allow=()):
    """CreateFruityInstance の未到達: harness に呼出しが無く、STARTUP の DllMain の段が最後に到達する段。"""
    src.absent(harness_dir, "CreateFruityInstance", allow=allow)
    src.exists(STARTUP, r"^\| S11 \| host \|[^\n]*CreateFruityInstance")
    (last_step,) = src.find(STARTUP, r"^\| (S\d\d) \| host \|[^\n]*\*\*DllMain\*\*")
    return {"reached": False, "last_step": last_step}


def _record(rid, route, mode, build, units, stop, cfi, gui, commit, nulls, src, probes=None, derived=None):
    nulls = dict(nulls)
    for key, value in units.items():
        if value is None:
            nulls.setdefault(f"units.{key}", f"出典に {key} の計数が無い")
    for key, value, why in (
        ("commit", commit, "出典に測定 commit の記載が無い"),
        ("stop", stop, "出典に停止位置が無い"),
        ("create_fruity_instance", cfi, "出典に CreateFruityInstance の段の計数が無い"),
        ("gui_natural", gui, "出典に GUI 計数が無い"),
        ("probes", probes, "出典に probes の計数が無い"),
    ):
        if value is None:
            nulls.setdefault(key, why)
    nulls.setdefault("first_wm_paint", "全路線で未測定 (最初の WM_PAINT は後続 WIN の範囲)")
    nulls.setdefault("pixels", "全路線で未測定 (画素は後続 WIN の範囲)")
    return {
        "id": rid,
        "route": route,
        "mode": mode,
        "build": build,
        "commit": commit,
        "units": units,
        "stop": stop,
        "create_fruity_instance": cfi,
        "gui_natural": gui,
        "first_wm_paint": None,
        "pixels": None,
        "probes": probes,
        "null_reasons": nulls,
        "derived": derived or {},
        "source": src,
    }


NO_COMMIT = "表行・節・JSON に測定 commit の記載が無い (source の file_last_commit は測定 commit ではない)"


def _m11_tolerant(src):
    src.begin()
    commit, run, ok, trap, oom, miss, noproc = src.match(
        M11_REPORT, "## 14.",
        r"^\| `(de50ffa)` [^|]*\| (\d+) \| [^|]*\| (\d+)/(\d+)\((\d+)\)/(\d+)/(\d+)",
        commit_group=0,
    )
    (skipped,) = src.match(M11_REPORT, "## 14.", r"units_skipped = (\d+) の内訳")
    stop_commit, unit, va, kind = src.match(
        M11_REPORT, "## 14.",
        r"^\| `(6654322)` \(\+414ad0・43a3f0 転記, n=3\) \| \*\*\d+\*\* \| unit (\d+) \((0x[0-9a-f]+)\) 後に (Halt0)",
        commit_group=0,
    )
    total = int(ok) + int(trap) + int(miss) + int(noproc)
    if total != UNITS:
        raise MetricError(f"m11 survey 列の合計が {UNITS} でない: {total}")
    dispatched = int(run) + int(skipped) + STOP_UNITS
    if dispatched != int(unit):
        raise MetricError(f"m11 の停止 unit と dispatch 数が合わない: {dispatched} != {unit}")
    units = {
        "total": total, "ok": int(run), "skipped": int(skipped), "failed": STOP_UNITS,
        "miss": None, "noproc": None, "dispatched": dispatched, "uncovered": None,
    }
    stop = {"unit": int(unit), "va": va, "kind": kind.lower()}
    cfi = _cfi(src, M11_DIR)
    nulls = {
        "units.miss": "逐次起動は icall miss を skipped に含めて数える (§14 内訳)。miss を別に出していない",
        "units.noproc": "逐次起動の計数に proc 無しは無い (survey 行にのみ在る)",
        "units.uncovered": "逐次起動では使わない",
        "gui_natural": "通常起動 (GUI 結合なし) の GUI 計数は無い。GUI 結合版は m11-gui-tolerant",
    }
    derived = {
        "units.total": f"§14 表行の survey 列 (ok+trap+miss+noproc) の合計。{UNITS} と一致を検査",
        "units.failed": "停止 unit 1 本 (表行の「unit N 後に Halt0」)",
        "units.dispatched": "units_run + units_skipped + 停止 unit 1 本。停止 unit 番号 (表行) と一致を検査",
        "create_fruity_instance": "harness 構造による (m11 の非 work ファイルに CreateFruityInstance の参照 0 件・STARTUP の DllMain の段が最後)",
    }
    return _record(
        "m11-tolerant-sequential", "m11", "tolerant-sequential",
        "m11 通常起動 (RetDec 路線、#134 の 6654322 / de50ffa 行)",
        units, stop, cfi, None, commit, nulls, src.end(), derived=derived,
    )


def _m11_tolerant_skip(src):
    src.begin()
    (commit,) = src.match(M11_N2714, "## 1.", r"^- 測定 commit: `([0-9a-f]{8})`", commit_group=0)
    attempted, ok, noproc, skipped, miss, halt0, oob, unreach = src.match(
        M11_N2714, "## 0.",
        r"で (\d+) unit を全て試行した\*\*。ok (\d+) / noproc (\d+) / skipped (\d+) "
        r"\(miss (\d+)・halt0 (\d+)・oob (\d+)・unreachable (\d+)\)",
        measured=commit,
    )
    row_att, row_ok, row_noproc, row_skip = src.match(
        M11_N2714, "## 1.",
        r"^\| C 寛容起動 \(本 PR\) \| — \| (\d+) 試行・ok (\d+)・noproc (\d+)・skip (\d+)・boot_rc=\d+ \| — \|",
        measured=commit,
    )
    if (int(row_att), int(row_ok), int(row_noproc), int(row_skip)) != (int(attempted), int(ok), int(noproc), int(skipped)):
        raise MetricError("寛容起動の §0 と §1 表の値が食い違う")
    if int(attempted) != UNITS:
        raise MetricError(f"寛容起動の試行数が {UNITS} でない: {attempted}")
    if int(ok) + int(noproc) + int(skipped) != UNITS:
        raise MetricError("寛容起動の ok + noproc + skipped が試行数と合わない")
    if int(miss) + int(halt0) + int(oob) + int(unreach) != int(skipped):
        raise MetricError("寛容起動の skip の内訳が skipped と合わない")
    trap = int(halt0) + int(oob) + int(unreach)
    units = {
        "total": UNITS, "ok": int(ok), "skipped": int(skipped), "failed": trap,
        "miss": int(miss), "noproc": int(noproc), "dispatched": int(attempted), "uncovered": None,
    }
    cfi = _cfi(src, M11_DIR)
    nulls = {
        "units.uncovered": "逐次起動では使わない",
        "stop": "寛容起動は停止 unit を持たない (942 試行を最後まで回す)。終端の Halt0→longjmp (boot_rc=1) は stage 6 の定義に当たらない (REPORT_N2714 §6)",
        "gui_natural": "寛容起動は GUI 結合なし。GUI 結合版は m11-gui-tolerant",
    }
    derived = {
        "units.total": f"寛容起動の試行数。§0 の本文と §1 表の試行数を照合し、{UNITS} と一致を検査",
        "units.skipped": "miss + halt0 + oob + unreachable (§0 の内訳と一致を検査)",
        "units.failed": "halt0 + oob + unreachable (trap。skipped のうち miss を除いたもの)",
        "units.dispatched": "試行数 (§0 の本文)。ok + noproc + skipped の合計と一致を検査",
        "create_fruity_instance": "harness 構造による (m11 の非 work の実行ファイル (.md を除く) に CreateFruityInstance の参照 0 件・STARTUP の DllMain の段が最後)",
    }
    return _record(
        "m11-tolerant-skip", "m11", "tolerant-skip",
        "m11 寛容起動 (失敗 unit を skipped として 942 unit を逐次続行・REPORT_N2714 §0・§1 C 行)",
        units, None, cfi, None, commit, nulls, src.end(), derived=derived,
    )


def _m11_survey(src):
    src.begin()
    commit = src.match_commit(M11_APPENDIX, "## 基準 (before)", r"測定 commit `([0-9a-f]{8})`")
    ok, trap, miss, noproc = src.match(
        M11_APPENDIX, "## 基準 (before)",
        r"^\| survey \(全再生成直後, unit 別 942 本\) \| \*\*ok (\d+) / trap (\d+) / miss (\d+) / noproc (\d+)\*\*",
        measured=commit,
    )
    total = int(ok) + int(trap) + int(miss) + int(noproc)
    if total != UNITS:
        raise MetricError(f"m11 survey の合計が {UNITS} でない: {total}")
    units = {
        "total": total, "ok": int(ok), "skipped": None, "failed": int(trap),
        "miss": int(miss), "noproc": int(noproc), "dispatched": None, "uncovered": None,
    }
    nulls = {
        "units.skipped": "survey は unit を隔離実行するため skip の概念が無い",
        "units.dispatched": "survey は 942 本すべてを 1 本ずつ実行する",
        "stop": "survey は unit 別の判定で、停止位置を持たない",
        "create_fruity_instance": "survey は DllMain を通さず unit を 1 本ずつ呼ぶ",
        "gui_natural": "GUI 計数は m11-gui-survey を参照",
    }
    derived = {"units.total": f"survey 行の合計 (ok+trap+miss+noproc)。{UNITS} と一致を検査"}
    return _record(
        "m11-isolated-survey", "m11", "isolated-survey",
        "m11 隔離 survey (全再生成 IR, 測定 commit は表の値)",
        units, None, None, None, commit, nulls, src.end(), derived=derived,
    )


def _m11_gui_boot(src):
    src.begin()
    (commit,) = src.find(GUI_REPORT, r"^### HEAD `([0-9a-f]{8})` の実測 \(.*本節を正とする\)", measured_group=0)
    run = src.json_value(GUI_BOOT, "units_run", commit)
    threw = src.json_value(GUI_BOOT, "boot_threw", commit)
    total = src.json_value(GUI_BOOT, "units_total", commit)
    reg = src.reach_calls(GUI_BOOT, "RegisterClassW", commit)
    cwe = src.reach_calls(GUI_BOOT, "CreateWindowExW", commit)
    if int(total) != UNITS:
        raise MetricError(f"gui boot の units_total が {UNITS} でない: {total}")
    units = {
        "total": int(total), "ok": int(run), "skipped": None, "failed": STOP_UNITS if threw else 0,
        "miss": None, "noproc": None, "dispatched": None, "uncovered": None,
    }
    cfi = _cfi(src, GUI_DIR, allow=(CFI_PROBE,))
    nulls = {
        "units.skipped": "boot.json に units_skipped が無い (同名の baseline_boot.json は別ビルドで 4)",
        "units.dispatched": "boot.json に停止 unit の計数が無い",
        "stop": "boot.json は停止 unit を持たない。boot_threw の値 (unreachable) は REPORT §6d の memory access out of bounds と食い違う (未解決表)",
        "probes": "boot.json の probes は本 schema の probes 項目 (x64c の GetMem/FreeMem) と別の計数のため採らない",
    }
    derived = {
        "units.ok": "boot.json の units_run をそのまま採る (m11 §14 と同じ完了数の計数と仮定。boot.json に内訳は無く、検査はしていない)",
        "units.failed": "boot_threw があれば停止 unit 1 本",
        "create_fruity_instance": "harness 構造による (gui/flengine の非 work ファイルに CreateFruityInstance の参照 0 件・STARTUP の DllMain の段が最後)",
    }
    return _record(
        "m11-gui-tolerant", "m11", "tolerant-sequential",
        "m11 + GUI shim 結合の通常起動 (gui/flengine boot.json)",
        units, None, cfi, {"RegisterClassW": reg, "CreateWindowExW": cwe}, commit, nulls, src.end(),
        derived=derived,
    )


def _m11_gui_survey(src):
    src.begin()
    commit, ok_r, noproc_r, miss_r, trap_r, clobber_r = src.find(
        GUI_REPORT,
        r"測定 commit `([0-9a-f]{8})`・judge [0-9]+/[0-9]+・S1 `(\d+)/(\d+)/(\d+)/(\d+)/(\d+)`",
        measured_group=0,
    )
    total = src.json_value(GUI_SURVEY, "units_total", commit, at=commit)
    ok = src.json_value(GUI_SURVEY, "survey.ok", commit, at=commit)
    noproc = src.json_value(GUI_SURVEY, "survey.noproc", commit, at=commit)
    miss = src.json_value(GUI_SURVEY, "survey.miss", commit, at=commit)
    trap = src.json_value(GUI_SURVEY, "survey.trap", commit, at=commit)
    clobber = src.json_value(GUI_SURVEY, "survey.clobber", commit, at=commit)
    kinds = src.json_value(GUI_SURVEY, "survey.kinds", commit, at=commit)
    reg = src.reach_calls(GUI_SURVEY, "RegisterClassW", commit, at=commit)
    cwe = src.reach_calls(GUI_SURVEY, "CreateWindowExW", commit, at=commit)
    if (int(ok), int(noproc), int(miss), int(trap), int(clobber)) != (
        int(ok_r), int(noproc_r), int(miss_r), int(trap_r), int(clobber_r)
    ):
        raise MetricError("gui survey の JSON と REPORT の S1 値が食い違う")
    if sum(kinds.values()) != int(trap):
        raise MetricError("gui survey の trap 内訳 (kinds) の合計が trap と合わない")
    if int(ok) + int(noproc) + int(miss) + int(trap) != int(total) or int(total) != UNITS:
        raise MetricError(f"gui survey の合計が {UNITS} でない")
    units = {
        "total": int(total), "ok": int(ok), "skipped": None, "failed": int(trap),
        "miss": int(miss), "noproc": int(noproc), "dispatched": None, "uncovered": None,
    }
    nulls = {
        "units.skipped": "survey は skip の概念が無い",
        "stop": "survey は unit 別の判定で、停止位置を持たない",
        "create_fruity_instance": "survey は DllMain を通さない",
    }
    derived = {
        "units.total": f"survey の units_total。ok+noproc+miss+trap の合計と {UNITS} を検査",
        "units.failed": "survey の trap (kinds の合計と一致を検査。REPORT の S1 値とも照合)",
    }
    return _record(
        "m11-gui-survey", "m11", "isolated-survey",
        "m11 + GUI shim (soft stub) の隔離 survey (gui/flengine survey_soft.json)",
        units, None, None, {"RegisterClassW": reg, "CreateWindowExW": cwe}, commit, nulls, src.end(),
        derived=derived,
    )


def _x64c_boot(src):
    src.begin()
    total = src.json_value(X64_BOOT, "boot.units_total")
    run = src.json_value(X64_BOOT, "boot.units_run")
    threw_cls = src.json_value(X64_BOOT, "boot.threw.cls")
    unit = src.json_value(X64_BOOT, "boot.stopped_at_1based")
    getmem = src.json_value(X64_BOOT, "boot.getmem")
    freemem = src.json_value(X64_BOOT, "boot.freemem")
    (va,) = src.match(
        X64_REPORT, "### 4-1.",
        r"^\| plain \| [^|]*\| \*\*209 dispatch\*\* / oob \(`f_([0-9a-f]+)`\)",
    )
    failed = STOP_UNITS if threw_cls else 0
    if int(unit) != int(run):
        raise MetricError("停止 unit と units_run が合わない")
    units = {
        "total": int(total), "ok": int(run) - failed, "skipped": None, "failed": failed,
        "miss": None, "noproc": None, "dispatched": int(run), "uncovered": None,
    }
    stop = {"unit": int(unit), "va": "0x" + va, "kind": threw_cls}
    cfi = _cfi(src, X64_DIR)
    nulls = {
        "commit": NO_COMMIT,
        "units.skipped": "boot 出力に skip の計数が無い",
        "units.miss": "boot 出力に miss の計数が無い",
        "units.noproc": "boot 出力に proc 無しの計数が無い",
        "gui_natural": "boot_summary_plain.json に GUI 計数が無い",
    }
    derived = {
        "units.ok": "units_run − 停止 unit 1 本 (threw がある場合)",
        "units.dispatched": "boot.units_run (停止 unit 番号 stopped_at_1based と一致を検査)",
        "create_fruity_instance": "harness 構造による (flelift/boot の非 work ファイルに CreateFruityInstance の参照 0 件・STARTUP の DllMain の段が最後)",
    }
    return _record(
        "x64c-strict-sequential", "x64c", "strict-sequential",
        "x64c boot 連鎖 plain variant (FLE-5 末 / boot_summary_plain.json)",
        units, stop, cfi, None, None, nulls, src.end(),
        {"getmem": int(getmem), "freemem": int(freemem)}, derived,
    )


def _x64c_survey(src):
    src.begin()
    total = src.json_value(X64_BOOT, "boot.units_total")
    covered = src.json_value(X64_SURVEY, "units_covered")
    ok = src.json_value(X64_SURVEY, "byCls.ok")
    unlifted = src.json_value(X64_SURVEY, "byCls.unlifted")
    uncovered = int(total) - int(covered)
    if int(ok) + int(unlifted) != int(covered):
        raise MetricError("x64c survey の内訳が units_covered と合わない")
    units = {
        "total": int(total), "ok": int(ok), "skipped": None, "failed": int(unlifted),
        "miss": None, "noproc": None, "dispatched": None, "uncovered": uncovered,
    }
    nulls = {
        "commit": NO_COMMIT,
        "units.miss": "survey.json は closure 外と proc 無しを分けない (合計 uncovered のみ)",
        "units.noproc": "同上",
        "stop": "survey は unit 別の判定で、停止位置を持たない",
        "gui_natural": "survey.json に GUI 計数が無い",
        "create_fruity_instance": "survey は DllMain を通さない",
    }
    derived = {"units.uncovered": "boot_summary_plain の units_total − survey の units_covered"}
    return _record(
        "x64c-isolated-survey", "x64c", "isolated-survey",
        "x64c 隔離 survey (FLE-5 末 / survey.json)",
        units, None, None, None, None, nulls, src.end(), derived=derived,
    )


def _native_ref(src):
    src.begin()
    commit = src.match_commit(NATIVE_REPORT, "# liftdiff", r"測定 commit: `([0-9a-f]{8})`")
    run, total = src.match(NATIVE_REPORT, "## 1.", r"`units_run (\d+)/(\d+)`", measured=commit)
    (first_fail,) = src.match(NATIVE_REPORT, "## 1.", r"`first_fail (\d+)`", measured=commit)
    units = {
        "total": int(total), "ok": int(run), "skipped": None, "failed": None,
        "miss": None, "noproc": None, "dispatched": None, "uncovered": None,
    }
    nulls = {
        "units.failed": "first_fail 830 が失敗か停止かは REPORT に定義が無い。first_fail は record の first_fail に置いた (未解決表)",
        "units.skipped": "REPORT に skip の計数が無い",
        "stop": "停止位置は first_fail として別記",
        "create_fruity_instance": "native 参照は STARTUP の段を計数していない",
        "gui_natural": "native 参照は GUI を計数していない",
    }
    rec = _record(
        "native-ref-hybrid", "native-ref", "native-hybrid",
        "native 実機械語の hybrid 起動 (wasm ではない。参照値)",
        units, None, None, None, commit, nulls, src.end(),
    )
    rec["first_fail"] = int(first_fail)
    return rec


def _flengine_cfi(src):
    src.begin()
    (commit,) = src.match(FLE_APPENDIX_2880, "### 9-3.", r"`cfi_probe\.mjs`・commit `([0-9a-f]{8})`", commit_group=0)
    (state,) = src.match(
        FLE_APPENDIX_2880, "### 9-3.",
        r"^\| `CreateFruityInstance\(0xC0, 0xEDE95A, host, &iface\)` \| `(Aborted)`", measured=commit,
    )
    if state != "Aborted":
        raise MetricError("probe の CreateFruityInstance 呼出しが Aborted でない")
    cs, api = src.match(
        FLE_APPENDIX_2880, "### 9-3.",
        r"`\[shim\] CS-MISS key=0x([0-9a-f]+)` → `FAIL-FAST: unimplemented Win32 API: (\w+) ", measured=commit,
    )
    (commit7,) = src.match(FLE_APPENDIX, "## 7.", r"\*\*測定 commit `([0-9a-f]{8})`\*\*", commit_group=0)
    (api7,) = src.match(
        FLE_APPENDIX, "### 7-4.",
        r"`CreateFruityInstance` は `\[shim\] FAIL-FAST: unimplemented Win32 API: (\w+) \(", measured=commit7,
    )
    if api7 != api:
        raise MetricError("REPORT_APPENDIX §7-4 と 2880 §9-3 の fail-fast API が食い違う")
    (loadstring,) = src.match(
        FLE_APPENDIX_2880, "### 9-3.",
        r"\| GUI-REACH / icall_miss \| `(\w+)` ×3 のみ / \d+", measured=commit,
    )
    if loadstring != "LoadStringW":
        raise MetricError("probe の GUI-REACH が LoadStringW のみでない")
    src.exists(CFI_PROBE, r"\._CreateFruityInstance\(")
    (last_step,) = src.find(STARTUP, r"^\| (S12) \| engine \| `0x1375990` 冒頭")
    units = {k: None for k in ("total", "ok", "skipped", "failed", "miss", "noproc", "dispatched", "uncovered")}
    stop = {"unit": None, "va": None, "kind": "fail-fast", "api": api, "cs": "0x" + cs}
    cfi = {"reached": True, "last_step": last_step}
    gui = {"RegisterClassW": 0, "CreateWindowExW": 0}
    nulls = {
        "stop.unit": "CreateFruityInstance の呼出しは unit 列の外 (probe の 1 回呼び)",
        "stop.va": "呼出元 VA は未特定 (wasm name section 無し・#3077 [WIN-16])",
    }
    derived = {
        "create_fruity_instance.last_step": "STARTUP の S12 行 (0x1375990 冒頭) = CreateFruityInstance の入口。到達の下限。S13 以降は未測定 (fail-fast の位置は #3077 で未特定)",
        "gui_natural": "GUI-REACH (§9-3) は LoadStringW のみ。RegisterClassW・CreateWindowExW は一覧に無いので 0",
        "stop": "CS-MISS 行の key (cs) と FAIL-FAST 行の API (api)。§7-4 と照合",
    }
    return _record(
        "flengine-cfi-probe", "flengine", "cfi-probe",
        "flengine boot7 + cfi_probe (DllMain attach の後に CreateFruityInstance を 1 回呼ぶ・REPORT_APPENDIX_2880 §9-3)",
        units, stop, cfi, gui, commit, nulls, src.end(), derived=derived,
    )


def build(root=REPO, commit_of=None, show_of=None):
    src = Source(root, commit_of, show_of)
    records = [
        _m11_tolerant(src),
        _m11_tolerant_skip(src),
        _m11_survey(src),
        _m11_gui_boot(src),
        _m11_gui_survey(src),
        _flengine_cfi(src),
        _x64c_boot(src),
        _x64c_survey(src),
        _native_ref(src),
    ]
    return {
        "schema": SCHEMA,
        "generated_by": "tools/startup/boot_metric.py (手で編集しない)",
        "definition": "起動指標 = STARTUP.md のステップ到達 + unit 内訳 (completed / skipped / failed / miss / noproc)。数え方の対応は tools/startup/REPORT.md §8",
        "records": records,
    }


def render(doc):
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="既存 boot_metric.json が再算出結果と一致するか検査する")
    ap.add_argument("--route", help="路線の現在値だけを標準出力へ (m11 / x64c / native-ref / flengine)")
    ap.add_argument("--root", default=str(REPO), help="出典の起点 (既定: repo root。テスト用)")
    args = ap.parse_args(argv)
    try:
        doc = build(Path(args.root))
    except MetricError as e:
        print(f"boot_metric: {e}", file=sys.stderr)
        return 1
    if args.route:
        recs = [r for r in doc["records"] if r["route"] == args.route]
        if not recs:
            print(f"boot_metric: 路線が無い: {args.route}", file=sys.stderr)
            return 2
        print(render({"route": args.route, "records": recs}), end="")
        return 0
    text = render(doc)
    if args.check:
        cur = OUT.read_text(encoding="utf-8") if OUT.is_file() else ""
        if cur != text:
            print("boot_metric: boot_metric.json が再算出結果と一致しない (再生成してください)", file=sys.stderr)
            return 1
        print("boot_metric: OK (boot_metric.json は再算出結果と一致)")
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"boot_metric: wrote {OUT.relative_to(REPO)} ({len(doc['records'])} records)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
