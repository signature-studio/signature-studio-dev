// 同時実行の計数 (純関数)。Actions の同時実行の上限 (Team プランの 60) は opencode.yaml の全 run が共有するので、
// room (= target_eff - active。推定が無ければ TARGET - active) の active には、event を問わず opencode.yaml の未完了の run を全て数える。
// VM 版 (tools/pm/launch_issues.py の active_runs) は実装・fix の run だけを数えていた。review (pull_request) や oc-pm・watchdog は数えず、
// その分だけ上限を超えて queued が出た。別 workflow (scripts-test.yaml など) の run は別枠なので数えない。
import { prioOf, type Prio } from "./launch.ts";
import { isOpencodeRun, type RunState } from "./webhook.ts";

// /oc 起点の実装 run。残り (review・fix・oc-pm・watchdog など) は other。
const IMPL_EVENTS = ["issue_comment", "workflow_dispatch"];

export interface ActiveCount {
  impl: number;
  other: number;
  // impl + other。room の基準。
  all: number;
  // all の内訳。repository_dispatch は run-name の先頭 (oc-fix・oc-pm・watchdog) で分ける。
  byEvent: Record<string, number>;
}

function eventKey(r: RunState): string {
  if (r.event !== "repository_dispatch") return r.event;
  const head = /^(oc-fix|oc-pm|watchdog)\b/.exec(r.title)?.[1];
  return `repository_dispatch:${head ?? "other"}`;
}

export function countOpencodeRuns(runs: Iterable<RunState>): ActiveCount {
  const c: ActiveCount = { impl: 0, other: 0, all: 0, byEvent: {} };
  for (const r of runs) {
    if (r.status === "completed" || !isOpencodeRun(r)) continue;
    c.all++;
    if (IMPL_EVENTS.includes(r.event)) c.impl++;
    else c.other++;
    const k = eventKey(r);
    c.byEvent[k] = (c.byEvent[k] ?? 0) + 1;
  }
  return c;
}

// 未完了の opencode.yaml の run を優先の区分別に数える (countOpencodeRuns と同じ集合。合計は all と一致する)。
// issue_comment・workflow_dispatch の run は、題名 (前後の空白を除く) が一意に一致する issue の区分にする。
// 対応が取れない run (review・oc-pm など、題名が重複する issue) は normal。
export function countRunsByPrio(runs: Iterable<RunState>, issues: Iterable<{ title: string; labels: string[] }>): Record<Prio, number> {
  const byTitle = new Map<string, Prio | null>();
  for (const i of issues) {
    const k = i.title.trim();
    byTitle.set(k, byTitle.has(k) ? null : prioOf(i.labels));
  }
  const c: Record<Prio, number> = { critical: 0, normal: 0, low: 0 };
  for (const r of runs) {
    if (r.status === "completed" || !isOpencodeRun(r)) continue;
    const p = IMPL_EVENTS.includes(r.event) ? byTitle.get(r.title.trim()) : undefined;
    c[p ?? "normal"]++;
  }
  return c;
}
