#!/usr/bin/env python3
"""規則 A (infra/pm-worker/src/autoclose.ts) の実データ照合 (#2336)。読み取りのみ。

REST の生 JSON を、Worker と別の実装 (本文の正規表現だけ・保存経路を通さない) で再計算し、
infra/pm-worker/scripts/rule_a_dryrun.ts の出力と比べる。tools/pm/rule_a_realcheck.sh から呼ばれる。
usage: rule_a_realcheck.py <dir> <worker.json>
出力: 件数・集合の差分・除外の内訳 (JSON)。差分が 0 のとき exit 0。
"""
import json
import os
import re
import sys
from datetime import datetime, timezone

KW = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?|refs?)\s*:?\s+#(\d{1,7})\b", re.I)
PARENT = re.compile(r"^親\s*[:：]\s*(.+)$", re.M)
MENTION = re.compile(r"#(\d{1,7})\b")


def load(d, name):
    with open(os.path.join(d, name), encoding="utf-8") as f:
        return json.load(f)


def flat(xs):
    return [x for page in xs for x in page] if xs and isinstance(xs[0], list) else xs


def parent_of(body):
    m = PARENT.search(body or "")
    if not m:
        return None
    f = re.search(r"#(\d+)", m.group(1))
    return int(f.group(1)) if f else None


def independent(d, closed):
    issues = [i for i in flat(load(d, "issues_open.json")) if "pull_request" not in i]
    prs_open = flat(load(d, "pulls_open.json"))
    open_nums = {i["number"] for i in issues}
    blocked = {}
    with open(os.path.join(d, "blocked.jsonl"), encoding="utf-8") as f:
        for line in f:
            if line.strip():
                o = json.loads(line)
                blocked[o["k"]] = o["v"]
    kids = {}
    for i in issues:
        p = parent_of(i.get("body"))
        if p is not None and p != i["number"] and p in open_nums:
            kids.setdefault(p, []).append(i["number"])
    merged, open_mention = {}, {}
    for p in closed:
        if p.get("merged_at"):
            for n in {int(x) for x in KW.findall(p.get("body") or "")}:
                merged.setdefault(n, []).append(p["number"])
    for p in prs_open:
        for n in {int(x) for x in MENTION.findall((p.get("title") or "") + "\n" + (p.get("body") or ""))}:
            open_mention.setdefault(n, []).append(p["number"])
    waiting = {}
    for k, v in blocked.items():
        if k in open_nums:
            for b in v:
                waiting.setdefault(b, []).append(k)
    unknown = [i["number"] for i in issues if (i.get("issue_dependencies_summary") or {}).get("total_blocked_by", 0) > len(blocked.get(i["number"], []))]
    out, why = [], {}
    for i in issues:
        n = i["number"]
        if n not in kids:
            continue
        labels = [x["name"] for x in i.get("labels", [])]
        if "needs-user-input" in labels:
            why["needs-user-input"] = why.get("needs-user-input", 0) + 1
        elif n not in merged:
            why["no-merged-ref"] = why.get("no-merged-ref", 0) + 1
        elif n in open_mention:
            why["open-pr-mention"] = why.get("open-pr-mention", 0) + 1
        elif any(k not in set(kids[n]) for k in waiting.get(n, [])):
            why["blocks-other"] = why.get("blocks-other", 0) + 1
        elif any(u != n and u not in set(kids[n]) for u in unknown):
            why["unknown-blockers"] = why.get("unknown-blockers", 0) + 1
        else:
            out.append([n, min(merged[n]), min(kids[n])])
    return sorted(out), why, len(kids)


def main():
    d, worker_path = sys.argv[1], sys.argv[2]
    issues = [i for i in flat(load(d, "issues_open.json")) if "pull_request" not in i]
    prs_open = flat(load(d, "pulls_open.json"))
    closed_all = flat(load(d, "pulls_closed.json"))
    cut = datetime.now(timezone.utc).timestamp() - 24 * 3600
    closed_win = [p for p in closed_all if datetime.fromisoformat(p["updated_at"].replace("Z", "+00:00")).timestamp() >= cut]
    worker = json.load(open(worker_path, encoding="utf-8"))
    res = {"input": {"issues_open (PR を除く)": len(issues), "pulls_open": len(prs_open), "pulls_closed (全履歴)": len(closed_all), "pulls_closed (24 時間窓)": len(closed_win)}}
    n_parents = 0
    for label, closed in (("full_history", closed_all), ("window_24h", closed_win)):
        ind, why, n_parents = independent(d, closed)
        w = sorted(worker[label])
        res[label] = {
            "worker": len(w),
            "independent": len(ind),
            "only_worker": [x for x in w if x not in ind],
            "only_independent": [x for x in ind if x not in w],
            "parents_with_open_children": n_parents,
            "excluded_by": why,
        }
    print(json.dumps(res, ensure_ascii=False, indent=1))
    # 照合の対象が空なら、差分 0 でも検証にはならない (token が issue を読めず 0 = 0 になる場合など)。
    empty = [k for k, v in (("open issue (PR を除く)", len(issues)), ("closed PR", len(closed_all)), ("子を持つ open 親", n_parents)) if v < 1]
    if empty:
        print(f"照合の対象が空: {', '.join(empty)} (取得の失敗・token の権限を確かめる)", file=sys.stderr)
        sys.exit(2)
    ok = all(not r["only_worker"] and not r["only_independent"] for k, r in res.items() if k != "input")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
