// prio:critical の保留 (#5596): bot コメントの窓と run 完了の窓は critical に効かない。通常の prio は従来どおり保留される (ネガコン)。
import { test } from "node:test";
import assert from "node:assert/strict";
import { BOT_COMMENT_WINDOW_H, classify, RUN_WINDOW_H, type ClassifyInput, type Snapshot } from "../src/classify.ts";

const H = 3_600_000;
const now = Date.parse("2026-10-16T12:00:00Z");
const ago = (h: number) => new Date(now - h * H).toISOString();

const snapOf = (labels: string[], botAt?: string): Snapshot => ({
  issues: [{ number: 5, title: "[X-5] t", labels, body: "", deps: null }],
  prs: [],
  runs: [],
  bot_last: botAt ? { "5": { at: botAt, head: "## 作業を始めました", art: null } } : {},
  bot_report: {},
  pm_art: {},
});

const inputOf = (over: Partial<ClassifyInput> = {}): ClassifyInput => ({
  nowMs: now,
  launched: {},
  relaunch: {},
  manualDeps: {},
  liveBlockers: {},
  fullBotBody: {},
  reportBody: {},
  outcomeReason: {},
  ...over,
});

test("窓の長さ: bot コメントは 30 分、run 完了は 1 時間 (#5596)", () => {
  assert.equal(BOT_COMMENT_WINDOW_H, 0.5);
  assert.equal(RUN_WINDOW_H, 1);
});

test("critical: 直近 30 分以内に bot コメントがあっても ready (次の tick で launch 対象)", () => {
  const { rows } = classify(snapOf(["prio:critical"], ago(0.2)), inputOf());
  assert.deepEqual(rows.recent, []);
  assert.deepEqual(rows.ready, [5]);
});

test("ネガコン: prio 無しの同じ状態 (bot コメント 0.2 時間前) は従来どおり recent", () => {
  const { rows } = classify(snapOf([], ago(0.2)), inputOf());
  assert.deepEqual(rows.recent.map(([n, why]) => [n, why]), [[5, "bot comment 0.2h ago"]]);
  assert.deepEqual(rows.ready, []);
});

test("窓の終わり: 通常の bot コメントは 0.5 時間で解け、0.6 時間前なら ready", () => {
  assert.deepEqual(classify(snapOf([], ago(0.6)), inputOf()).rows.ready, [5]);
  assert.deepEqual(classify(snapOf([], ago(0.4)), inputOf()).rows.recent.map(([n]) => n), [5]);
});

const observedRun = (doneH: number) => inputOf({
  launched: { "5": ago(doneH + 0.5) },
  launchState: { "5": "observed" } as ClassifyInput["launchState"],
  launchDoneAt: { "5": ago(doneH) },
});

test("critical: run 完了の直後 (0.3 時間) でも ready", () => {
  const { rows } = classify(snapOf(["prio:critical"]), observedRun(0.3));
  assert.deepEqual(rows.recent, []);
  assert.deepEqual(rows.ready, [5]);
});

test("ネガコン: prio 無しは run 完了の直後 (0.3 時間) なら recent (run finished)", () => {
  const { rows } = classify(snapOf([]), observedRun(0.3));
  assert.deepEqual(rows.recent.map(([n, why]) => [n, why.startsWith("run finished")]), [[5, true]]);
});

test("窓の終わり: 通常の run 完了は 1 時間で解ける (1.2 時間前なら ready)", () => {
  assert.deepEqual(classify(snapOf([]), observedRun(1.2)).rows.ready, [5]);
});

test("critical でも launch 直後 (未観測) の窓は残す: 二重投稿を防ぐため recent", () => {
  const input = inputOf({
    launched: { "5": ago(0.1) },
    launchState: { "5": "launched" } as ClassifyInput["launchState"],
  });
  const { rows } = classify(snapOf(["prio:critical"]), input);
  assert.deepEqual(rows.recent.map(([n, why]) => [n, why.startsWith("launch not observed")]), [[5, true]]);
});
