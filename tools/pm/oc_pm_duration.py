#!/usr/bin/env python3
"""oc-pm run の所要時間と同時実行数を実測する (#3463)。測定値の正本は tools/pm/REPORT_3463.md。

使い方 (gh の認証が要る。REST のみ):
  python3 tools/pm/oc_pm_duration.py [--now 2026-10-15T02:15:00Z] [--hours 24] [--repo OWNER/REPO]
標準出力に要約 (JSON)。生データと行ごとの表は --raw (既定 tools/pm/work/oc_pm_runs.json、gitignore 対象)。
対象は event=repository_dispatch かつ題名が『oc-pm 』で始まる run (run-name は .github/workflows/opencode.yaml)。
所要は run の run_started_at → updated_at (issue の受入条件)。pm job の started_at → completed_at も並べて出す。
窓は (now - hours, now] に完了した run。
"""
import argparse
import datetime as dt
import json
import os
import statistics
import subprocess

REPO_DEFAULT = "signature-studio/signature-studio-dev"
WORKFLOW = "opencode.yaml"
PM_JOB = "pm"
PM_TITLE_PREFIX = "oc-pm "
PM_TIMEOUT_MIN = 30  # .github/workflows/opencode.yaml の pm job の timeout-minutes
CAP_PER_HOUR = 24  # infra/pm-worker/src/pm.ts の PM_LIMITS.hourMax (#3189 で 12 から 24 へ)
HOUR = dt.timedelta(hours=1)
DEFAULT_RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "work", "oc_pm_runs.json")
RUN_FIELDS = (".total_count as $t | .workflow_runs[] | "
              "{total: $t, id, display_title, event, status, conclusion, created_at, run_started_at, updated_at}")


def parse_ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def fmt_ts(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def is_pm_run(run):
    return run.get("event") == "repository_dispatch" and str(run.get("display_title") or "").startswith(PM_TITLE_PREFIX)


def minutes(a, b):
    return (b - a).total_seconds() / 60


def stats(vals):
    if not vals:
        return {"n": 0}
    return {
        "n": len(vals),
        "mean": round(statistics.fmean(vals), 2),
        "median": round(statistics.median(vals), 2),
        "min": round(min(vals), 2),
        "max": round(max(vals), 2),
    }


def max_concurrency(intervals):
    events = []
    for s, e in intervals:
        events.append((s, 1))
        events.append((e, -1))
    events.sort(key=lambda x: (x[0], x[1]))  # 同時刻は終了を先に数える (接するだけの 2 件は重ならない)
    cur = best = 0
    for _, d in events:
        cur += d
        best = max(best, cur)
    return best


def max_starts_per_hour(starts):
    ordered = sorted(starts)
    return max((sum(1 for u in ordered if t <= u < t + HOUR) for t in ordered), default=0)


def estimate(rate_per_h, mean_min, max_min):
    return {
        "rate_per_h": rate_per_h,
        "mean_based": round(rate_per_h * mean_min / 60, 2),
        "max_based": round(rate_per_h * max_min / 60, 2),
        "worst_timeout": round(rate_per_h * PM_TIMEOUT_MIN / 60, 2),
    }


def summarize(runs, now, hours):
    """runs: 取得した pm run の辞書 (完了した run は 'pm_job' に pm job の辞書を持つ)。"""
    start = now - dt.timedelta(hours=hours)
    completed = [r for r in runs if r["status"] == "completed"]
    done = [r for r in completed if start <= parse_ts(r["updated_at"]) <= now]
    excluded = {
        "not_completed": len(runs) - len(completed),
        "completed_before_window": sum(1 for r in completed if parse_ts(r["updated_at"]) < start),
        "completed_after_now": sum(1 for r in completed if parse_ts(r["updated_at"]) > now),
    }
    rows = []
    for r in done:
        s, f, c = parse_ts(r["run_started_at"]), parse_ts(r["updated_at"]), parse_ts(r["created_at"])
        pj = r.get("pm_job") or {}
        pm_min = minutes(parse_ts(pj["started_at"]), parse_ts(pj["completed_at"])) if pj.get("completed_at") else None
        rows.append({
            "id": r["id"],
            "title": r["display_title"],
            "conclusion": r["conclusion"],
            "created": c,
            "run_started": s,
            "updated": f,
            "run_min": minutes(s, f),
            "queue_min": minutes(c, s),
            "pm_min": pm_min,
        })
    conclusions = {}
    for x in rows:
        conclusions[x["conclusion"]] = conclusions.get(x["conclusion"], 0) + 1
    window_min = hours * 60
    busy_min = sum(minutes(max(x["run_started"], start), min(x["updated"], now)) for x in rows)
    starts = [parse_ts(r["created_at"]) for r in runs if start <= parse_ts(r["created_at"]) <= now]
    run_stats = stats([x["run_min"] for x in rows])
    return {
        "window": {"start": fmt_ts(start), "end": fmt_ts(now), "hours": hours},
        "pm_runs_fetched": len(runs),
        "pm_runs_used": len(rows),
        "excluded": excluded,
        "conclusions": conclusions,
        "run_min": run_stats,
        "pm_job_min": stats([x["pm_min"] for x in rows if x["pm_min"] is not None]),
        "queue_min": stats([x["queue_min"] for x in rows]),
        "max_concurrency_observed": max_concurrency([(x["run_started"], x["updated"]) for x in rows]),
        "avg_concurrency_observed": round(busy_min / window_min, 3),
        "dispatch_starts_in_window": len(starts),
        "max_dispatch_starts_per_rolling_hour": max_starts_per_hour(starts),
        "estimate_concurrency_at_cap": estimate(CAP_PER_HOUR, run_stats.get("mean", 0.0), run_stats.get("max", 0.0)),
        "rows": rows,
    }


def gh_json_lines(path, jq, paginate=True):
    cmd = ["gh", "api"] + (["--paginate"] if paginate else []) + [path, "--jq", jq]
    out = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600).stdout
    return [json.loads(x) for x in out.splitlines() if x.strip()]


def fetch(repo, now, hours):
    since = now - dt.timedelta(hours=hours + 24)  # 窓の中で完了する run は作成が窓より前のこともあるので 1 日余分に取る
    base = f"repos/{repo}/actions/workflows/{WORKFLOW}/runs?event=repository_dispatch&created={fmt_ts(since)}..{fmt_ts(now)}"
    all_runs = gh_json_lines(base + "&per_page=100", RUN_FIELDS)
    totals = {r.pop("total") for r in all_runs}
    total = next(iter(totals), 0)
    if len(totals) > 1 or len(all_runs) != total:
        raise SystemExit(f"run 一覧の取得件数 {len(all_runs)} が total_count {sorted(totals)} と合わない (取り直す)")
    runs = [r for r in all_runs if is_pm_run(r)]
    for r in runs:
        if r["status"] == "completed":
            jobs = gh_json_lines(f"repos/{repo}/actions/runs/{r['id']}/jobs", f'.jobs[] | select(.name == "{PM_JOB}")', paginate=False)
            r["pm_job"] = jobs[0] if jobs else None
    return runs, total


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--now", help="窓の終わり (UTC の ISO 8601。既定は実行時刻)")
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--repo", default=os.environ.get("OC_REPO", REPO_DEFAULT))
    ap.add_argument("--raw", default=DEFAULT_RAW, help="生データと行ごとの表の保存先 (JSON)")
    args = ap.parse_args()
    now = parse_ts(args.now) if args.now else dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    runs, total = fetch(args.repo, now, args.hours)
    summary = summarize(runs, now, args.hours)
    rows = summary.pop("rows")
    summary["api_total_count"] = total
    os.makedirs(os.path.dirname(args.raw), exist_ok=True)
    with open(args.raw, "w", encoding="utf-8") as fh:
        json.dump({"repo": args.repo, "now": fmt_ts(now), "api_total_count": total, "runs": runs, "summary": summary,
                   "rows": [{**x, "created": fmt_ts(x["created"]), "run_started": fmt_ts(x["run_started"]),
                             "updated": fmt_ts(x["updated"])} for x in rows]}, fh, ensure_ascii=False, indent=1, default=str)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
