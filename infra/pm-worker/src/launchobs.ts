// /oc 投稿 (launch) の観測。投稿後に、題名が issue 題名と一致する issue_comment 由来の run が現れたかで決める。
//   launched → observed (run が現れた) / launched → failed (5 分を超えても現れない) / failed → observed (遅れて現れた)
// 純関数のみ。DO への書き込みは engine が行う。
import type { RunState } from "./webhook.ts";

export type LaunchState = "launched" | "observed" | "failed";

export interface LaunchObs {
  state: LaunchState;
  // 投稿時刻 (launchedAt と同じ値)
  at: string;
  // この状態になった時刻
  changedAt: string;
}

export const OBSERVE_WINDOW_MS = 5 * 60_000;
// run の created_at は投稿の応答より前にずれることがあるので、投稿時刻のこの分だけ前から数える。
export const RUN_CREATED_SLACK_MS = 60_000;

export function observedBy(runs: Iterable<RunState>, title: string, launchedMs: number): boolean {
  const t = title.trim();
  for (const r of runs) {
    if (r.event !== "issue_comment" || r.title.trim() !== t) continue;
    const created = Date.parse(r.createdAt ?? "");
    if (Number.isFinite(created) && created >= launchedMs - RUN_CREATED_SLACK_MS) return true;
  }
  return false;
}

// 変わったときだけ次の値を返す (変わらなければ undefined)。failed の判定は、同期が新しいときだけ行う。
export function advanceLaunch(cur: LaunchObs, nowMs: number, observed: boolean, fresh: boolean): LaunchObs | undefined {
  if (cur.state === "observed") return undefined;
  const at = new Date(nowMs).toISOString();
  if (observed) return { ...cur, state: "observed", changedAt: at };
  if (cur.state === "launched" && fresh && nowMs - Date.parse(cur.at) > OBSERVE_WINDOW_MS) return { ...cur, state: "failed", changedAt: at };
  return undefined;
}
