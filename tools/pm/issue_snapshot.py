#!/usr/bin/env python3
"""open issue の状態を REST だけで集計して JSON に保存する (指示 132: 全チケットは『ブロックされている』か
『着手済み』のどちらかであるべき)。出力: このスクリプトと同じディレクトリの issues_state.json

分類のための素材だけを集める。判定は launch_issues.py が行う。
  issues   : open issue (PR を除く) の number/title/labels/body/created/updated/milestone/dependencies summary
  prs      : 全 PR (open+closed+merged) の number/state/merged/head ref/body 先頭/title
  bot_last : issue ごとの『最後の bot コメント』(時刻と先頭 400 文字)。直近の実行報告の有無を見る。
             run-outcome・PM のマーカーを含むコメントは停止報告ではないので入れない (bot_last_of)
  runs     : 実行中・待機中の run (event, title, created)
"""
import os
import json, re, subprocess, sys

R = "signature-studio/signature-studio-dev"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "issues_state.json")
BOTS = {"opencode-for-signature-studio[bot]"}
MARKERS = ("<!-- oc-run-outcome:", "<!-- oc-pm-")


def bot_last_of(comments):
    """コメント列から issue ごとの最後の bot コメントを返す。マーカー付きのコメントは除く。"""
    bot_last = {}
    for c in comments:
        if c["user"]["login"] not in BOTS:
            continue
        body = c.get("body") or ""
        if any(m in body for m in MARKERS):
            continue
        n = int(c["issue_url"].rsplit("/", 1)[1])
        if n not in bot_last or c["created_at"] > bot_last[n]["at"]:
            am = re.search(r"^\s*`?(oc_artifacts:[^\n`]*)`?\s*$", body, re.M)
            bot_last[n] = {"at": c["created_at"], "head": body[:400], "art": am.group(1).strip() if am else None}
    return bot_last


def api(path, paginate=True):
    cmd = ["gh", "api"] + (["--paginate", "--slurp"] if paginate else []) + [path]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"gh api failed: {path}: {out.stderr[:200]}")
    data = json.loads(out.stdout)
    if paginate:
        return [x for page in data for x in (page if isinstance(page, list) else [page])]
    return data


def main():
    raw = api(f"repos/{R}/issues?state=open&per_page=100")
    issues = []
    for i in raw:
        if "pull_request" in i:
            continue
        issues.append({
            "id": i["id"], "number": i["number"], "title": i["title"],
            "labels": [l["name"] for l in i["labels"]],
            "body": i.get("body") or "", "created": i["created_at"], "updated": i["updated_at"],
            "milestone": (i.get("milestone") or {}).get("title"),
            "comments": i["comments"],
            "deps": i.get("issue_dependencies_summary"),
        })
    prs_raw = api(f"repos/{R}/pulls?state=all&per_page=100")
    prs = [{"number": p["number"], "state": p["state"], "merged": bool(p.get("merged_at")), "draft": p["draft"],
            "ref": p["head"]["ref"], "title": p["title"], "body": (p.get("body") or "")[:3000]} for p in prs_raw]
    # 直近 2 日のコメントから、issue ごとの最後の bot コメントを取る
    comments = api(f"repos/{R}/issues/comments?since=2026-10-12T00:00:00Z&per_page=100")
    bot_last = bot_last_of(comments)
    pm_art = {}  # PM (pycabbage) が過去の /oc コメントに書いた oc_artifacts の最後の行
    for c in comments:
        n = int(c["issue_url"].rsplit("/", 1)[1])
        if c["user"]["login"] == "pycabbage":
            m = re.search(r"^oc_artifacts:[^\n]*$", c.get("body") or "", re.M)
            if m and (n not in pm_art or c["created_at"] > pm_art[n]["at"]):
                pm_art[n] = {"at": c["created_at"], "line": m.group(0)}
    runs = []
    for st in ("in_progress", "queued", "pending", "waiting"):
        for page in api(f"repos/{R}/actions/runs?status={st}&per_page=100"):
            for w in page.get("workflow_runs", []):
                runs.append({"id": w["id"], "event": w["event"], "title": w["display_title"], "status": st, "created": w["created_at"]})
    json.dump({"issues": issues, "prs": prs, "bot_last": bot_last, "pm_art": pm_art, "runs": runs}, open(OUT, "w"), ensure_ascii=False)
    print(f"issues={len(issues)} prs={len(prs)} bot_last={len(bot_last)} runs={len(runs)} -> {OUT}")


if __name__ == "__main__":
    main()
