#!/usr/bin/env python3
"""規則 A (src/autoclose.ts) の独立な再計算。REST 相当の生の JSON (fixture) から、本文の正規表現だけで候補を出す。

test/autoclose.test.ts から呼ばれる。GitHub へは行かない。出力は [[親, merged PR, 子], ...] (番号順)。
usage: rule_a_crosscheck.py <fixture.json>
"""
import json
import re
import sys

KW = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?|refs?)\s*:?\s+#(\d{1,7})\b", re.I)
PARENT = re.compile(r"^親\s*[:：]\s*(.+)$", re.M)
MENTION = re.compile(r"#(\d{1,7})\b")


def parent_of(body):
    m = PARENT.search(body or "")
    if not m:
        return None
    f = re.search(r"#(\d+)", m.group(1))
    return int(f.group(1)) if f else None


def main(path):
    fx = json.load(open(path, encoding="utf-8"))
    issues = {i["number"]: i for i in fx["issues"]}
    open_nums = {n for n, i in issues.items() if i["state"] == "open"}
    kids = {}
    for n in sorted(open_nums):
        p = parent_of(issues[n]["body"])
        if p is not None and p != n and p in open_nums:
            kids.setdefault(p, []).append(n)
    merged = {}
    open_mentions = {}
    for pr in fx["prs"]:
        if pr["state"] == "closed" and pr["merged"]:
            for n in {int(x) for x in KW.findall(pr["body"] or "")}:
                merged.setdefault(n, []).append(pr["number"])
        if pr["state"] == "open":
            for n in {int(x) for x in MENTION.findall((pr["title"] or "") + "\n" + (pr["body"] or ""))}:
                open_mentions.setdefault(n, []).append(pr["number"])
    blocked = {int(k): v for k, v in fx["blockedBy"].items()}
    waiting = {}
    for k, v in blocked.items():
        if k in open_nums:
            for b in v:
                waiting.setdefault(b, []).append(k)
    unknown = [n for n in open_nums if issues[n]["blockedByCount"] > 0 and str(n) not in fx["blockedBy"]]
    out = []
    for n in sorted(open_nums):
        if "needs-user-input" in issues[n]["labels"] or n not in kids or n not in merged or n in open_mentions:
            continue
        ks = set(kids[n])
        if any(k not in ks for k in waiting.get(n, [])):
            continue
        if any(u != n and u not in ks for u in unknown):
            continue
        out.append([n, min(merged[n]), min(kids[n])])
    print(json.dumps(out))


if __name__ == "__main__":
    main(sys.argv[1])
