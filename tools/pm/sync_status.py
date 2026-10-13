#!/usr/bin/env python3
"""Project V2 (#2) の Status を issue / PR の実態から導出して同期する (指示 122: 1 タスク = 1 チケット = 1 PR)。

規則 (open な issue のみ。closed は常に Done):
  open かつ ready な PR が 1 本以上 -> In review
  open な draft PR のみ              -> In progress
  PR 無し + 進行中/待機中の実装 run   -> In progress
  PR 無し + 現在 In review/In progress (残骸) -> Ready
  それ以外は現状維持 (Backlog / Ready)
チケットの特定: PR の head ブランチ名 N-slug の N (AGENTS.md §3 の命名規約)。
DRY=1 で変更案だけ表示。終了コード 0。
"""
import json, os, re, subprocess, sys
from collections import Counter, defaultdict

R = os.environ.get("REPO", "signature-studio/signature-studio-dev")
OWNER, PNUM = "signature-studio", "2"
DRY = os.environ.get("DRY") == "1"


def sh(*a):
    return subprocess.run(a, capture_output=True, text=True, check=True).stdout


def js(*a):
    return json.loads(sh(*a))


issues = {i["number"]: i for i in js("gh", "issue", "list", "-R", R, "--state", "all", "--limit", "3000", "--json", "number,state,title")}
prs = js("gh", "pr", "list", "-R", R, "--state", "open", "--limit", "300", "--json", "number,isDraft,headRefName")
items = js("gh", "project", "item-list", PNUM, "--owner", OWNER, "--limit", "1000", "--format", "json")["items"]
fields = js("gh", "project", "field-list", PNUM, "--owner", OWNER, "--format", "json")["fields"]
st = [f for f in fields if f["name"] == "Status"][0]
opt = {o["name"]: o["id"] for o in st["options"]}
pid = [p for p in js("gh", "project", "list", "--owner", OWNER, "--format", "json")["projects"] if str(p["number"]) == PNUM][0]["id"]

ready, draft = defaultdict(list), defaultdict(list)
for p in prs:
    m = re.match(r"(\d+)-", p["headRefName"])
    if m:
        (draft if p["isDraft"] else ready)[int(m.group(1))].append(p["number"])

title2num = {i["title"]: n for n, i in issues.items()}
running = set()
for s in ("in_progress", "queued"):
    for r in js("gh", "api", f"repos/{R}/actions/runs?status={s}&per_page=100")["workflow_runs"]:
        if r["event"] == "issue_comment" and r["display_title"] in title2num:
            running.add(title2num[r["display_title"]])

changes, kept = [], Counter()
for it in items:
    c = it.get("content") or {}
    if c.get("type") != "Issue":
        continue
    n, cur = c["number"], it.get("status", "none")
    iss = issues.get(n)
    if not iss:
        continue
    if iss["state"] == "CLOSED":
        want = "Done"
    elif n in ready:
        want = "In review"
    elif n in draft or n in running:
        want = "In progress"
    elif cur in ("In review", "In progress"):
        want = "Ready"
    else:
        want = cur
    if want != cur:
        changes.append((it["id"], n, cur, want))
    else:
        kept[cur] += 1

print("transitions:", dict(Counter(f"{a}->{b}" for _, _, a, b in changes)))
print("unchanged:", dict(kept))
if DRY or not changes:
    sys.exit(0)

import time
for i in range(0, len(changes), 10):
    chunk = changes[i:i + 10]
    body = " ".join(
        f'm{k}: updateProjectV2ItemFieldValue(input:{{projectId:"{pid}",itemId:"{iid}",fieldId:"{st["id"]}",'
        f'value:{{singleSelectOptionId:"{opt[w]}"}}}}){{projectV2Item{{id}}}}'
        for k, (iid, n, a, w) in enumerate(chunk)
    )
    for attempt in range(4):
        out = subprocess.run(["gh", "api", "graphql", "-f", f"query=mutation{{{body}}}"], capture_output=True, text=True)
        if out.returncode == 0:
            break
        time.sleep(3)
    else:
        print("mutation failed:", out.stderr[:300])
        sys.exit(1)
print("applied", len(changes))
