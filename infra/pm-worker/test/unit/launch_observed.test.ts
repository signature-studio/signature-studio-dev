import { describe, expect, it } from "vitest";
import { classify, type ClassifyInput, type Rows, type Snapshot, type SnapRun } from "../../src/classify.ts";
import { advanceLaunch, doneAtOf, type LaunchObs } from "../../src/launchobs.ts";
import type { RunState } from "../../src/webhook.ts";

// 観測済み launch の recent 判定: 投稿からの 3 時間ではなく、観測した run の完了からの 3 時間で数える (#2645)。
const TITLE = "[CI-61] alpha";
const H = 3_600_000;
const MIN = 60_000;
const T0 = Date.parse("2026-10-14T12:00:00Z");
const at = (ms: number) => new Date(ms).toISOString();

function snap(runs: SnapRun[] = []): Snapshot {
  return {
    issues: [{ number: 61, title: TITLE, labels: [], body: "", deps: { total_blocked_by: 0 } }],
    prs: [],
    runs,
    bot_last: {},
    pm_art: {},
  };
}

// issue 61 が投稿済み (launchedAt) で、観測状態 (state) と完了時刻 (doneAt) を持つ入力。
function input(o: { launchedAt: number; state?: "launched" | "observed" | "failed"; doneAt?: number }): ClassifyInput {
  return {
    nowMs: T0,
    launched: { "61": at(o.launchedAt) },
    launchState: o.state ? { "61": o.state } : {},
    launchDoneAt: o.doneAt !== undefined ? { "61": at(o.doneAt) } : {},
    relaunch: {},
    manualDeps: {},
    liveBlockers: {},
    fullBotBody: {},
  };
}

// issue 61 が入った行の名前 (1 行だけに入ること)。
function bucket(rows: Rows): string[] {
  return (Object.keys(rows) as Array<keyof Rows>).filter((k) => rows[k].some((x) => (Array.isArray(x) ? x[0] : x) === 61));
}

describe("観測済み launch の分類 (#2645)", () => {
  it("(a) 観測済み・run 進行中 → started (完了済みの run があっても、進行中の run を優先する)", () => {
    const r = classify(snap([{ id: 7, event: "issue_comment", title: TITLE }]), input({ launchedAt: T0 - 40 * MIN, state: "observed", doneAt: T0 - 30 * MIN })).rows;
    expect(bucket(r)).toEqual(["started"]);
    expect(r.started).toEqual([[61, ["run7"]]]);
  });

  it("(b) 観測済み・完了から 3 時間以内・報告なし → recent (投稿からは 3 時間を過ぎていても recent)", () => {
    const r = classify(snap(), input({ launchedAt: T0 - 3.5 * H, state: "observed", doneAt: T0 - H })).rows;
    expect(bucket(r)).toEqual(["recent"]);
    expect(r.recent).toEqual([[61, "run finished 1.0h ago"]]);
  });

  it("(c) 観測済み・完了から 3 時間を過ぎたら候補 (ready) に戻る (投稿からは 3 時間以内でも戻る)", () => {
    const r = classify(snap(), input({ launchedAt: T0 - H, state: "observed", doneAt: T0 - 3 * H - MIN })).rows;
    expect(bucket(r)).toEqual(["ready"]);
  });

  it("(d1) 観測済み・完了時刻の無い launch → 投稿から 3 時間以内は recent", () => {
    const r = classify(snap(), input({ launchedAt: T0 - H, state: "observed" })).rows;
    expect(bucket(r)).toEqual(["recent"]);
    expect(r.recent).toEqual([[61, "launched 1.0h ago"]]);
  });

  it("(d2) 観測済み・完了時刻の無い launch → 投稿から 3 時間を過ぎたら ready", () => {
    const r = classify(snap(), input({ launchedAt: T0 - 4 * H, state: "observed" })).rows;
    expect(bucket(r)).toEqual(["ready"]);
  });
});

const run = (o: Partial<RunState> & { id: number }): RunState => ({
  event: "issue_comment",
  title: TITLE,
  status: "completed",
  conclusion: "success",
  updatedAt: at(T0),
  createdAt: at(T0 - MIN),
  ...o,
});

describe("観測した run の完了時刻 (#2645)", () => {
  const launchedMs = T0 - 10 * MIN;

  it("doneAtOf: 投稿の後に作られた、題名一致の完了済み run の最新の updatedAt を返す", () => {
    const runs: RunState[] = [
      run({ id: 1, updatedAt: at(T0 - 8 * MIN) }),
      run({ id: 2, updatedAt: at(T0 - 2 * MIN) }),
      run({ id: 3, status: "in_progress", updatedAt: at(T0 - MIN) }),
      run({ id: 4, title: "[CI-62] beta", updatedAt: at(T0) }),
      run({ id: 5, event: "workflow_dispatch", updatedAt: at(T0) }),
      run({ id: 6, createdAt: at(T0 - 30 * MIN), updatedAt: at(T0) }),
    ];
    expect(doneAtOf(runs, TITLE, launchedMs)).toBe(at(T0 - 2 * MIN));
  });

  it("doneAtOf: 完了済みの run が無ければ undefined", () => {
    expect(doneAtOf([run({ id: 1, status: "in_progress" })], TITLE, launchedMs)).toBeUndefined();
  });

  it("advanceLaunch: launched → observed で完了時刻を残す。観測済みでは完了時刻を前へだけ進める", () => {
    const cur: LaunchObs = { state: "launched", at: at(launchedMs), changedAt: at(launchedMs) };
    const obs = advanceLaunch(cur, T0, true, true, at(T0 - 2 * MIN));
    expect(obs).toEqual({ state: "observed", at: at(launchedMs), changedAt: at(T0), doneAt: at(T0 - 2 * MIN) });
    expect(advanceLaunch(obs!, T0 + MIN, true, true, at(T0 - 5 * MIN))).toBeUndefined();
    expect(advanceLaunch(obs!, T0 + MIN, true, true, at(T0 - MIN))?.doneAt).toBe(at(T0 - MIN));
  });

  it("advanceLaunch: 完了時刻が無い観測済みは、完了時刻が後から無くなっても変えない (prune で run が消えた後)", () => {
    const cur: LaunchObs = { state: "observed", at: at(launchedMs), changedAt: at(T0), doneAt: at(T0 - 2 * MIN) };
    expect(advanceLaunch(cur, T0 + 2 * H, true, true, undefined)).toBeUndefined();
  });
});
