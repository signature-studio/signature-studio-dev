#!/usr/bin/env python3
"""SHIMX_TRACE_FILE の JSON Lines (1 行 1 イベント) を集計する (SHX-T12 #789)。

  python3 scripts/ftrace_summary.py <trace.jsonl> [--json out.json]

集計の定義 (REPORT の数え方と一致させること):
  events       : 行数 (空行は除く)。JSON として読めない行があれば異常終了 (exit 2)
  by_api       : api 名ごとの件数
  ok / fail    : "ok" が true / false のイベント数
  write        : "write" が true のイベント数 (書込系 open)
  fail_err     : fail イベントの err 別件数
  distinct_posix_opened : ok かつ api が CreateFile* で posix が非 null の一意なパス数
"""
import json
import sys
from collections import Counter

OPEN_APIS = ("CreateFileW", "CreateFileA")


def summarize(lines):
    events = []
    for i, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise ValueError(f"line {i}: invalid JSON: {e}") from e
    by_api = Counter(e["api"] for e in events)
    ok = sum(1 for e in events if e["ok"])
    fail = len(events) - ok
    write = sum(1 for e in events if e.get("write") is True)
    fail_err = Counter(e["err"] for e in events if not e["ok"])
    opened = {e["posix"] for e in events if e["api"] in OPEN_APIS and e["ok"] and e.get("posix")}
    return {
        "events": len(events),
        "by_api": dict(sorted(by_api.items())),
        "ok": ok,
        "fail": fail,
        "write": write,
        "fail_err": {str(k): v for k, v in sorted(fail_err.items())},
        "distinct_posix_opened": len(opened),
    }


def main(argv):
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 1
    try:
        with open(argv[1], encoding="utf-8") as f:
            result = summarize(f)
    except ValueError as e:
        print(f"[ftrace_summary] FAIL: {e}", file=sys.stderr)
        return 2
    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if "--json" in argv:
        with open(argv[argv.index("--json") + 1], "w", encoding="utf-8") as f:
            f.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
