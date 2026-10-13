#!/usr/bin/env python3
"""dismiss_spam.py — open PR にある watchdog 由来の CHANGES_REQUESTED ('(watchdog)' を含む。'[merge-failed]' は除く) を取り下げる。
これらは fix run を起動できないまま往復回数だけを消費していた (#731)。DRY=1 で件数のみ。ONLY=番号,番号 で対象を絞る。"""
import json, os, subprocess
R = "signature-studio/signature-studio-dev"
DRY = os.environ.get("DRY") == "1"
ONLY = set(map(int, os.environ["ONLY"].split(","))) if os.environ.get("ONLY") else None
def api(*a):
    return subprocess.check_output(["gh", "api", *a], text=True)
prs = json.loads(api("--paginate", f"repos/{R}/pulls?state=open&per_page=100")) if False else None
raw = api("--paginate", f"repos/{R}/pulls?state=open&per_page=100")
nums = []
dec = json.JSONDecoder(); i = 0
while i < len(raw):
    while i < len(raw) and raw[i].isspace(): i += 1
    if i >= len(raw): break
    obj, j = dec.raw_decode(raw, i); i = j
    nums += [p["number"] for p in obj]
total = 0
for n in sorted(nums):
    if ONLY and n not in ONLY: continue
    raw = api("--paginate", f"repos/{R}/pulls/{n}/reviews")
    revs = []; i = 0
    while i < len(raw):
        while i < len(raw) and raw[i].isspace(): i += 1
        if i >= len(raw): break
        obj, j = dec.raw_decode(raw, i); i = j; revs += obj
    spam = [r for r in revs if r["user"]["login"] == "oc-reviewer-for-signature-studio[bot]" and r["state"] == "CHANGES_REQUESTED"
            and "(watchdog)" in (r.get("body") or "") and "[merge-failed]" not in (r.get("body") or "")]
    for r in spam:
        total += 1
        if DRY:
            print(f"#{n} DRY dismiss review {r['id']} ({r['commit_id'][:7]})"); continue
        try:
            subprocess.check_output(["gh", "api", "-X", "PUT", f"repos/{R}/pulls/{n}/reviews/{r['id']}/dismissals",
                                     "-f", "message=dismissed by PM: a watchdog request-changes that could not start a fix run and only consumed the round limit (#731)"],
                                    text=True, stderr=subprocess.STDOUT)
            print(f"#{n} dismissed review {r['id']}")
        except subprocess.CalledProcessError as e:
            print(f"#{n} FAILED review {r['id']}: {e.output[:120]!r}")
print("total", total, "(DRY)" if DRY else "")
