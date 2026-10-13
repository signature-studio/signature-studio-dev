#!/usr/bin/env python3
"""全 open PR を REVIEWING / FIXING / IDLE に分類する (指示 123: IDLE は 1 秒も存在してはならない)。

REVIEWING: その PR の現 head に対する pull_request run (review job) が in_progress/queued/pending
FIXING   : display_title がその PR のタイトルと一致する issue_comment run が in_progress/queued/pending
           (/oc コメントで起動された実装 run)
IDLE     : どちらでもない。理由 (CONFLICT / CHANGES_REQUESTED / APPROVED / NOREVIEW / COMMENTED / DRAFT) を併記。
出力: 分類ごとの件数と IDLE の一覧。JSON=1 で機械可読。
"""
import json, os, subprocess, sys
from collections import Counter

R = os.environ.get("REPO", "signature-studio/signature-studio-dev")
O, N = R.split("/")


def run(*a):
    return subprocess.run(a, capture_output=True, text=True, check=True).stdout


q = """query($o:String!,$n:String!,$c:String){repository(owner:$o,name:$n){pullRequests(states:OPEN,first:100,after:$c){pageInfo{hasNextPage endCursor} nodes{
number title isDraft mergeable reviewDecision headRefOid baseRefName updatedAt
reviews(last:30){nodes{author{login} state commit{oid} submittedAt}}}}}}"""
prs, cur = [], None
while True:
    args = ["gh", "api", "graphql", "-f", f"query={q}", "-F", f"o={O}", "-F", f"n={N}"]
    if cur:
        args += ["-f", f"c={cur}"]
    page = json.loads(run(*args))["data"]["repository"]["pullRequests"]
    prs += page["nodes"]
    if not page["pageInfo"]["hasNextPage"]:
        break
    cur = page["pageInfo"]["endCursor"]

active = []
for s in ("in_progress", "queued", "pending", "waiting"):
    active += json.loads(run("gh", "api", f"repos/{R}/actions/runs?status={s}&per_page=100"))["workflow_runs"]
rev_sha = {r["head_sha"] for r in active if r["event"] == "pull_request"}
fix_titles = {r["display_title"] for r in active if r["event"] in ("issue_comment", "workflow_dispatch")}

out = []
for p in prs:
    sha = p["headRefOid"]
    if sha in rev_sha:
        state, why = "REVIEWING", ""
    elif p["title"] in fix_titles:
        state, why = "FIXING", ""
    else:
        rv = [r for r in p["reviews"]["nodes"] if r["author"] and r["author"]["login"].startswith("oc-reviewer")]
        cur = [r for r in rv if r["commit"] and r["commit"]["oid"] == sha]
        last = cur[-1]["state"] if cur else None
        if p["mergeable"] == "CONFLICTING":
            why = "CONFLICT"
        elif p["isDraft"]:
            why = "DRAFT"
        elif last == "CHANGES_REQUESTED":
            why = "CHANGES_REQUESTED"
        elif last == "APPROVED":
            why = "APPROVED"
        elif last == "COMMENTED":
            why = "COMMENTED"
        else:
            why = "NOREVIEW"
        state = "IDLE"
    out.append((p["number"], state, why, p["updatedAt"], p["baseRefName"]))

if os.environ.get("JSON") == "1":
    print(json.dumps(out))
    sys.exit(0)
print("open PRs:", len(out), dict(Counter(s for _, s, _, _, _ in out)))
print("IDLE reasons:", dict(Counter(w for _, s, w, _, _ in out if s == "IDLE")))
for n, s, w, u, b in sorted(out):
    if s == "IDLE":
        print(f"  #{n} {w} base={b} updated={u}")
