#!/usr/bin/env python3
"""rest_heal.py — PM 用。open PR のうち「レビュー中でも修正中でもない」(IDLE) ものを REST だけで戻す。

GraphQL のレート制限に影響されない (gh pr comment / close / reopen は GraphQL なので使わない)。
watchdog.sh (.github/scripts, PR-B) が main に入るまでの橋渡し。分類は watchdog.sh と同じ。

  DRY=1        操作せず計画だけ
  MAX=25       1 回の実行で行う操作の上限
  AGAIN=90     同じ PR に PM が /oc を出してから AGAIN 分以内なら待つ
  ONLY=1,2,3   指定した PR 番号だけ
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

R = os.environ.get("OC_REPO", "signature-studio/signature-studio-dev")
DRY = os.environ.get("DRY") == "1"
MAX = int(os.environ.get("MAX", "25"))
AGAIN = int(os.environ.get("AGAIN", "90"))
ONLY = {int(x) for x in os.environ.get("ONLY", "").split(",") if x}
PM = "pycabbage"


def gh(*args, data=None):
    cmd = ["gh", "api", *args]
    for _ in range(4):
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode == 0:
            return json.loads(p.stdout) if p.stdout.strip() else None
        if "rate limit" in p.stderr.lower():
            print("rate limited:", p.stderr.strip()[:120], file=sys.stderr)
            subprocess.run(["timeout", "30", "tail", "-f", "/dev/null"])
            continue
        time.sleep(2)
    raise RuntimeError(f"{' '.join(args)}: {p.stderr.strip()[:200]}")


def paged(path):
    out, page = [], 1
    while True:
        chunk = gh(f"{path}{'&' if '?' in path else '?'}per_page=100&page={page}")
        out += chunk
        if len(chunk) < 100:
            return out
        page += 1


def age_min(ts):
    return int((datetime.now(timezone.utc) - datetime.fromisoformat(ts.replace("Z", "+00:00"))).total_seconds() / 60)


prs = paged(f"repos/{R}/pulls?state=open")
active_nums, active_titles = set(), set()
for st in ("in_progress", "queued", "pending", "waiting"):
    for run in gh(f"repos/{R}/actions/runs?status={st}&per_page=100")["workflow_runs"]:
        for p in run.get("pull_requests") or []:
            active_nums.add(p["number"])
        if run["event"] in ("issue_comment", "workflow_dispatch"):
            active_titles.add(run["display_title"])

acted = 0
tally = {}
for pr in sorted(prs, key=lambda p: p["updated_at"]):
    n, head = pr["number"], pr["head"]["sha"]
    if ONLY and n not in ONLY:
        continue
    if n in active_nums or pr["title"] in active_titles:
        tally["COVERED"] = tally.get("COVERED", 0) + 1
        continue
    if any(l["name"] == "oc:stuck" for l in pr["labels"]):
        tally["STUCK_LABELLED"] = tally.get("STUCK_LABELLED", 0) + 1
        print(f"#{n} STUCK_LABELLED")
        continue
    full = gh(f"repos/{R}/pulls/{n}")
    mergeable = full["mergeable"]
    for _ in range(3):
        if mergeable is not None:
            break
        time.sleep(2)
        mergeable = gh(f"repos/{R}/pulls/{n}")["mergeable"]
    reviews = [r for r in paged(f"repos/{R}/pulls/{n}/reviews") if r["user"]["login"].startswith("oc-reviewer")]
    cur = [r for r in reviews if r["commit_id"] == head]
    st = cur[-1]["state"] if cur else "NONE"
    if mergeable is False:
        cls = "CONFLICT"
    elif pr["draft"]:
        cls = "DRAFT"
    elif st == "CHANGES_REQUESTED":
        cls = "FIX"
    elif st == "APPROVED":
        cls = "APPROVED"
    else:
        cls = "NOREVIEW"
    tally[cls] = tally.get(cls, 0) + 1

    comments = paged(f"repos/{R}/issues/{n}/comments")
    mine = [c for c in comments if c["user"]["login"] == PM and c["body"].startswith("/oc")]
    last_ask = age_min(mine[-1]["created_at"]) if mine else 10**6
    upd = age_min(pr["updated_at"])
    note = f"upd {upd}m, last /oc {'-' if not mine else str(last_ask) + 'm'}"
    if cls in ("CONFLICT", "FIX") and last_ask < AGAIN:
        print(f"#{n} {cls} wait ({note})")
        continue
    if upd < 4:
        print(f"#{n} {cls} wait: just updated ({note})")
        continue
    print(f"#{n} {cls} ACT ({note})")
    if cls in ("DRAFT", "APPROVED"):
        continue  # DRAFT は gh pr ready (GraphQL) が要る、APPROVED は merge 順があるので PM が判断
    if acted >= MAX:
        print("   deferred (MAX)")
        continue
    body_lines = [ln for ln in (pr["body"] or "").splitlines() if ln.startswith("oc_artifacts:")]
    art = body_lines[0].split(":", 1)[1].strip() if body_lines else "fl-win64"
    if DRY:
        acted += 1
        continue
    if cls == "CONFLICT":
        text = (f"/oc oc_actions_allow_write\noc_artifacts: {art}\n"
                "この PR は main と競合しています (競合 PR は review run が起動しません)。origin/main を merge して競合を解消し push してください "
                "(競合解消以外の変更はしない。main 側の変更を消さないこと)。競合した箇所と解消方針を PR にコメントで報告し、何も push せずに終了しないこと。")
        gh(f"repos/{R}/issues/{n}/comments", "-f", f"body={text}")
    elif cls == "FIX":
        text = (f"/oc oc_actions_allow_write\noc_artifacts: {art}\n"
                f"oc-reviewer の最新の review (gh api repos/{R}/pulls/{n}/reviews の最後の oc-reviewer の review、および inline コメントと Copilot の指摘) を読み、"
                "必須の指摘と、すぐ直せる指摘を全て修正して push してください。妥当でないと判断した指摘は直さず、理由を PR にコメントで残してください (実測を添えること)。"
                "ほかの変更はしない。PM 判断・ユーザ判断が要る項目は、起票依頼として PR コメントに列挙してください。"
                "結果は PR にコメントで投稿し、何も push せずに終了しないこと。push すると review が再起動します。")
        gh(f"repos/{R}/issues/{n}/comments", "-f", f"body={text}")
    else:  # NOREVIEW: close -> reopen で pull_request:reopened を起こす
        gh("-X", "PATCH", f"repos/{R}/pulls/{n}", "-f", "state=closed")
        time.sleep(3)
        gh("-X", "PATCH", f"repos/{R}/pulls/{n}", "-f", "state=open")
    acted += 1
    time.sleep(4)

print("tally:", json.dumps(tally, ensure_ascii=False), "acted:", acted, "(DRY)" if DRY else "")
