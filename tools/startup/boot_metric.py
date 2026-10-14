#!/usr/bin/env python3
"""起動指標 tools/startup/boot_metric.json を算出する (#2713 WIN-2)。

値は tools/**/REPORT*.md の表行・節と results/*.json から抽出する。手で書かない。
抽出元が無い・一意に決まらない場合は MetricError で止まる (値を捏造しない)。
出典が無い項目は null とし、理由を null_reasons に書く。
各レコードの commit は、REPORT 表行に書かれた測定 commit (あれば) か、出典ファイルの最終更新 commit。

使い方:
  python3 tools/startup/boot_metric.py                 # boot_metric.json を書き出す
  python3 tools/startup/boot_metric.py --check         # 既存ファイルが再算出結果と一致するか (不一致は exit 1)
  python3 tools/startup/boot_metric.py --route x64c    # 路線の現在値を標準出力へ (m11 / x64c / native-ref)
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SCHEMA = "boot_metric/v1"
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OUT = HERE / "boot_metric.json"

M11_REPORT = "tools/m11/REPORT.md"
M11_APPENDIX = "tools/m11/REPORT_APPENDIX_1430.md"
GUI_BOOT = "tools/gui/flengine/results/boot.json"
GUI_SURVEY = "tools/gui/flengine/results/survey_soft.json"
X64_BOOT = "tools/flelift/boot/results/boot_summary_plain.json"
X64_SURVEY = "tools/flelift/boot/results/survey.json"
X64_REPORT = "tools/flelift/boot/REPORT.md"
NATIVE_REPORT = "tools/liftdiff/REPORT_LD26.md"
STARTUP = "tools/startup/STARTUP.md"


class MetricError(Exception):
    """抽出元が無い・一意に決まらないときの例外。値を捏造しない。"""


def git_commit(root, rel):
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "log", "-1", "--format=%h", "--", rel],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        out = ""
    return out or None


class Source:
    def __init__(self, root, commit_of=None):
        self.root = Path(root)
        self.commit_of = commit_of or (lambda rel: git_commit(self.root, rel))
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

    def _note(self, rel, locator, commit=None):
        entry = {"file": rel, "locator": locator, "commit": commit or self.commit_of(rel)}
        if entry not in self.used:
            self.used.append(entry)

    def json_value(self, rel, dotted):
        cur = json.loads(self._text(rel))
        for key in dotted.split("."):
            if not isinstance(cur, dict) or key not in cur:
                raise MetricError(f"JSON に無い: {rel} :: {dotted}")
            cur = cur[key]
        self._note(rel, f"json:{dotted}")
        return cur

    def reach_calls(self, rel, name):
        doc = json.loads(self._text(rel))
        reach = doc.get("reach")
        if not isinstance(reach, list):
            raise MetricError(f"reach 配列が無い: {rel}")
        self._note(rel, f"json:reach[{name}].calls (配列に無ければ 0)")
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

    def match(self, rel, heading, pattern):
        """節の中で pattern に一意に一致させ、group(1..) を返す。"""
        sec = self.section(rel, heading)
        hits = list(re.finditer(pattern, sec, re.M))
        if len(hits) != 1:
            raise MetricError(f"一意に一致しない ({len(hits)} 件): {rel} :: {heading} :: {pattern}")
        self._note(rel, f"md:{heading} /{pattern}/")
        return hits[0].groups()

    def match_commit(self, rel, heading, pattern):
        """表行の測定 commit を返す (例: 測定 commit `7e149974`)。"""
        sec = self.section(rel, heading)
        hits = re.findall(pattern, sec)
        if len(set(hits)) != 1:
            raise MetricError(f"測定 commit が一意でない: {rel} :: {heading} :: {pattern}")
        return hits[0]

    def exists(self, rel, pattern, value):
        if not re.search(pattern, self._text(rel), re.M):
            raise MetricError(f"存在確認に失敗: {rel} :: {pattern}")
        self._note(rel, f"存在確認 /{pattern}/")
        return value


def _record(rid, route, mode, build, units, stop, cfi, gui, commit, nulls, src, probes=None):
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
        "source": src,
    }


def _m11_tolerant(src):
    src.begin()
    commit, run, ok, trap, oom, miss, noproc = src.match(
        M11_REPORT, "## 14.",
        r"^\| `(de50ffa)` [^|]*\| (\d+) \| [^|]*\| (\d+)/(\d+)\((\d+)\)/(\d+)/(\d+)",
    )
    (skipped,) = src.match(M11_REPORT, "## 14.", r"units_skipped = (\d+) の内訳")
    unit, va, kind = src.match(
        M11_REPORT, "## 14.",
        r"^\| `6654322` \(\+414ad0・43a3f0 転記, n=3\) \| \*\*\d+\*\* \| unit (\d+) \((0x[0-9a-f]+)\) 後に (Halt0)",
    )
    total = int(ok) + int(trap) + int(miss) + int(noproc)
    if total != 942:
        raise MetricError(f"m11 survey の合計が 942 でない: {total}")
    dispatched = int(run) + int(skipped) + 1
    if dispatched != int(unit):
        raise MetricError(f"m11 の停止 unit と dispatch 数が合わない: {dispatched} != {unit}")
    units = {
        "total": 942, "ok": int(run), "skipped": int(skipped), "failed": 1,
        "miss": None, "noproc": None, "dispatched": dispatched, "uncovered": None,
    }
    stop = {"unit": int(unit), "va": va, "kind": kind.lower()}
    cfi = src.exists(STARTUP, r"^\| S09 \| host \|", {"reached": False, "last_step": "S09"})
    nulls = {
        "units.miss": "逐次起動は icall miss を skipped に含めて数える (§14 内訳)。miss を別に出していない",
        "units.noproc": "逐次起動の計数に proc 無しは無い (survey 行にのみ在る)",
        "units.uncovered": "逐次起動では使わない",
        "gui_natural": "通常起動 (GUI 結合なし) の GUI 計数は無い。GUI 結合版は m11-gui-tolerant",
    }
    return _record(
        "m11-tolerant-sequential", "m11", "tolerant-sequential",
        "m11 通常起動 (RetDec 路線、#134 の 6654322 / de50ffa 行)",
        units, stop, cfi, None, commit, nulls, src.end(),
    )


def _m11_survey(src):
    src.begin()
    commit = src.match_commit(M11_APPENDIX, "## 基準 (before)", r"測定 commit `([0-9a-f]{8})`")
    ok, trap, miss, noproc = src.match(
        M11_APPENDIX, "## 基準 (before)",
        r"^\| survey \(全再生成直後, unit 別 942 本\) \| \*\*ok (\d+) / trap (\d+) / miss (\d+) / noproc (\d+)\*\*",
    )
    total = int(ok) + int(trap) + int(miss) + int(noproc)
    if total != 942:
        raise MetricError(f"m11 survey の合計が 942 でない: {total}")
    units = {
        "total": 942, "ok": int(ok), "skipped": None, "failed": int(trap),
        "miss": int(miss), "noproc": int(noproc), "dispatched": None, "uncovered": None,
    }
    nulls = {
        "units.skipped": "survey は unit を隔離実行するため skip の概念が無い",
        "units.dispatched": "survey は 942 本すべてを 1 本ずつ実行する",
        "stop": "survey は unit 別の判定で、停止位置を持たない",
        "create_fruity_instance": "survey は DllMain を通さず unit を 1 本ずつ呼ぶ",
        "gui_natural": "GUI 計数は m11-gui-survey を参照",
    }
    return _record(
        "m11-isolated-survey", "m11", "isolated-survey",
        "m11 隔離 survey (全再生成 IR, 測定 commit は表の値)",
        units, None, None, None, commit, nulls, src.end(),
    )


def _m11_gui_boot(src):
    src.begin()
    run = src.json_value(GUI_BOOT, "units_run")
    threw = src.json_value(GUI_BOOT, "boot_threw")
    reg = src.reach_calls(GUI_BOOT, "RegisterClassW")
    cwe = src.reach_calls(GUI_BOOT, "CreateWindowExW")
    units = {
        "total": 942, "ok": int(run), "skipped": None, "failed": 1 if threw else 0,
        "miss": None, "noproc": None, "dispatched": None, "uncovered": None,
    }
    cfi = src.exists(STARTUP, r"^\| S09 \| host \|", {"reached": False, "last_step": "S09"})
    nulls = {
        "units.skipped": "boot.json に units_skipped が無い (同名の baseline_boot.json は別ビルドで 4)",
        "units.dispatched": "boot.json に停止 unit の計数が無い",
        "stop": "boot.json は停止 unit を持たない。boot_threw の値 (unreachable) は REPORT §6d の memory access out of bounds と食い違う",
    }
    gui = {"RegisterClassW": reg, "CreateWindowExW": cwe}
    return _record(
        "m11-gui-tolerant", "m11", "tolerant-sequential",
        "m11 + GUI shim 結合の通常起動 (gui/flengine boot.json)",
        units, None, cfi, gui, src_commit(src, GUI_BOOT), nulls, src.end(),
    )


def _m11_gui_survey(src):
    src.begin()
    ok = src.json_value(GUI_SURVEY, "survey.ok")
    noproc = src.json_value(GUI_SURVEY, "survey.noproc")
    miss = src.json_value(GUI_SURVEY, "survey.miss")
    trap = src.json_value(GUI_SURVEY, "survey.trap")
    reg = src.reach_calls(GUI_SURVEY, "RegisterClassW")
    cwe = src.reach_calls(GUI_SURVEY, "CreateWindowExW")
    if int(ok) + int(noproc) + int(miss) + int(trap) != 942:
        raise MetricError("gui survey の合計が 942 でない")
    units = {
        "total": 942, "ok": int(ok), "skipped": None, "failed": int(trap),
        "miss": int(miss), "noproc": int(noproc), "dispatched": None, "uncovered": None,
    }
    nulls = {
        "units.skipped": "survey は skip の概念が無い",
        "stop": "survey は unit 別の判定で、停止位置を持たない",
        "create_fruity_instance": "survey は DllMain を通さない",
    }
    return _record(
        "m11-gui-survey", "m11", "isolated-survey",
        "m11 + GUI shim (soft stub) の隔離 survey (gui/flengine survey_soft.json)",
        units, None, None, {"RegisterClassW": reg, "CreateWindowExW": cwe},
        src_commit(src, GUI_SURVEY), nulls, src.end(),
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
    failed = 1 if threw_cls else 0
    if int(unit) != int(run):
        raise MetricError("停止 unit と units_run が合わない")
    units = {
        "total": int(total), "ok": int(run) - failed, "skipped": None, "failed": failed,
        "miss": None, "noproc": None, "dispatched": int(run), "uncovered": None,
    }
    stop = {"unit": int(unit), "va": "0x" + va, "kind": threw_cls}
    cfi = src.exists(STARTUP, r"^\| S09 \| host \|", {"reached": False, "last_step": "S09"})
    nulls = {
        "units.skipped": "boot 出力に skip の計数が無い",
        "units.miss": "boot 出力に miss の計数が無い",
        "units.noproc": "boot 出力に proc 無しの計数が無い",
        "gui_natural": "boot_summary_plain.json に GUI 計数が無い",
        "create_fruity_instance": "ハーネスは DllMain 経路のみ。CreateFruityInstance を呼ばない (tools/flelift/boot に参照無し)",
    }
    return _record(
        "x64c-strict-sequential", "x64c", "strict-sequential",
        "x64c boot 連鎖 plain variant (FLE-5 末 / boot_summary_plain.json)",
        units, stop, cfi, None, src_commit(src, X64_BOOT), nulls, src.end(),
        {"getmem": int(getmem), "freemem": int(freemem)},
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
        "units.miss": "survey.json は closure 外と proc 無しを分けない (合計 uncovered のみ)",
        "units.noproc": "同上",
        "stop": "survey は unit 別の判定で、停止位置を持たない",
        "gui_natural": "survey.json に GUI 計数が無い",
        "create_fruity_instance": "survey は DllMain を通さない",
    }
    return _record(
        "x64c-isolated-survey", "x64c", "isolated-survey",
        "x64c 隔離 survey (FLE-5 末 / survey.json)",
        units, None, None, None, src_commit(src, X64_SURVEY), nulls, src.end(),
    )


def _native_ref(src):
    src.begin()
    commit = src.match_commit(NATIVE_REPORT, "# liftdiff", r"測定 commit: `([0-9a-f]{8})`")
    run, total = src.match(NATIVE_REPORT, "## 1.", r"`units_run (\d+)/(\d+)`")
    (first_fail,) = src.match(NATIVE_REPORT, "## 1.", r"`first_fail (\d+)`")
    units = {
        "total": int(total), "ok": int(run), "skipped": None, "failed": None,
        "miss": None, "noproc": None, "dispatched": None, "uncovered": None,
    }
    nulls = {
        "units.failed": "first_fail 830 が失敗か停止かは REPORT に定義が無い。first_fail は record の first_fail に置いた",
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


def src_commit(src, rel):
    """レコードの commit: 出典ファイルの最終更新 commit (表行に測定 commit が無い場合)。"""
    return src.commit_of(rel)


def build(root=REPO, commit_of=None):
    src = Source(root, commit_of)
    records = [
        _m11_tolerant(src),
        _m11_survey(src),
        _m11_gui_boot(src),
        _m11_gui_survey(src),
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
    ap.add_argument("--route", help="路線の現在値だけを標準出力へ (m11 / x64c / native-ref)")
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
