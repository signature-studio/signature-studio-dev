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
  // 観測した run の完了時刻 (RunState.updatedAt・status completed の run のうち最も新しいもの)。観測済みで完了を見たら記録する。
  // RunState は完了後 1 時間で prune されるので、完了を見た時点でここに残す。無ければ投稿時刻から数える (古い state)。
  doneAt?: string;
}

export const OBSERVE_WINDOW_MS = 5 * 60_000;
// run の created_at は投稿の応答より前にずれることがあるので、投稿時刻のこの分だけ前から数える。
export const RUN_CREATED_SLACK_MS = 60_000;

// 投稿の後に作られた、題名が一致する issue_comment 由来の run。
function postedRuns(runs: Iterable<RunState>, title: string, launchedMs: number): RunState[] {
  const t = title.trim();
  return [...runs].filter((r) => {
    if (r.event !== "issue_comment" || r.title.trim() !== t) return false;
    const created = Date.parse(r.createdAt ?? "");
    return Number.isFinite(created) && created >= launchedMs - RUN_CREATED_SLACK_MS;
  });
}

export function observedBy(runs: Iterable<RunState>, title: string, launchedMs: number): boolean {
  return postedRuns(runs, title, launchedMs).length > 0;
}

// 投稿の run のうち完了済みの、最も新しい updatedAt。完了した run が無ければ undefined。
export function doneAtOf(runs: Iterable<RunState>, title: string, launchedMs: number): string | undefined {
  let best: string | undefined;
  for (const r of postedRuns(runs, title, launchedMs)) {
    if (r.status !== "completed") continue;
    if (best === undefined || Date.parse(r.updatedAt) > Date.parse(best)) best = r.updatedAt;
  }
  return best;
}

// 観測済みの完了時刻を前へだけ進める (prune で完了 run が消えても古い値に戻さない)。変わらなければ cur をそのまま返す。
function withDone(cur: LaunchObs, done: string | undefined): LaunchObs {
  if (done === undefined) return cur;
  if (cur.doneAt !== undefined && Date.parse(done) <= Date.parse(cur.doneAt)) return cur;
  return { ...cur, doneAt: done };
}

// 変わったときだけ次の値を返す (変わらなければ undefined)。failed の判定は、同期が新しいときだけ行う。
// done は観測した run の完了時刻 (doneAtOf)。観測済みの記録に完了時刻を足す (状態は変えない)。
export function advanceLaunch(cur: LaunchObs, nowMs: number, observed: boolean, fresh: boolean, done?: string): LaunchObs | undefined {
  const at = new Date(nowMs).toISOString();
  if (cur.state === "observed") {
    const next = withDone(cur, done);
    return next === cur ? undefined : next;
  }
  if (observed) return withDone({ ...cur, state: "observed", changedAt: at }, done);
  if (cur.state === "launched" && fresh && nowMs - Date.parse(cur.at) > OBSERVE_WINDOW_MS) return { ...cur, state: "failed", changedAt: at };
  return undefined;
}
