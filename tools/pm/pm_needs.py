#!/usr/bin/env python3
"""open PR のうち、oc-reviewer の最新の CHANGES_REQUESTED が PM の判断・起票を求めていて、
その review より後に PM (pycabbage) の応答コメントが無いものを列挙する。REST のみ。

差し戻しが 6 回以上に積み上がった PR の主因は、reviewer が『実装 agent では解消しない』と書いた
PM 判断を PM が決めていなかったこと (2026-10-13 の実測)。これを定期的に洗い出す。

env: ONLY=番号,番号 / SHOW=1 で該当行を表示
"""
import json, os, re, subprocess, sys

R = "signature-studio/signature-studio-dev"
PM = "pycabbage"
REVIEWER = "oc-reviewer-for-signature-studio[bot]"
KEY = re.compile(r"PM 判断|PM に求める|PM が決め|PM の決定|起票依頼|PM 起票|PM 採番|PM 承認|PM が .*(起票|判断)")


def api(path):
    out = subprocess.run(["gh", "api", "--paginate", "--slurp", path], capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"gh api failed: {path}: {out.stderr[:200]}")
    pages = json.loads(out.stdout)
    return [x for page in pages for x in (page if isinstance(page, list) else [page])]


def main():
    only = {int(x) for x in os.environ.get("ONLY", "").split(",") if x}
    prs = api(f"repos/{R}/pulls?state=open&per_page=100")
    rows = []
    for p in sorted(prs, key=lambda x: x["number"]):
        n = p["number"]
        if only and n not in only:
            continue
        reviews = api(f"repos/{R}/pulls/{n}/reviews?per_page=100")
        mine = [r for r in reviews if r["user"]["login"] == REVIEWER and r["state"] in ("CHANGES_REQUESTED", "APPROVED")]
        if not mine or mine[-1]["state"] != "CHANGES_REQUESTED":
            continue
        last = mine[-1]
        body = last.get("body") or ""
        hits = [l.strip() for l in body.splitlines() if KEY.search(l)]
        if not hits:
            continue
        comments = api(f"repos/{R}/issues/{n}/comments?per_page=100")
        answered = any(c["user"]["login"] == PM and c["created_at"] > last["submitted_at"] for c in comments)
        cr_count = sum(1 for r in reviews if r["user"]["login"] == REVIEWER and r["state"] == "CHANGES_REQUESTED")
        rows.append((n, answered, cr_count, last["submitted_at"][11:19], hits[0][:110], len(hits)))
    print(f"{'PR':>5} {'PM応答':6} {'CR数':>4} {'review':8} 該当行(先頭)")
    waiting = 0
    for n, ans, cr, at, h, k in rows:
        waiting += 0 if ans else 1
        print(f"#{n:<4} {'済み' if ans else '未回答':6} {cr:>4} {at:8} ({k}) {h}")
    print(f"PM 判断を求められているのに未回答: {waiting} 件 / 判断を求める差し戻し: {len(rows)} 件")


if __name__ == "__main__":
    main()
