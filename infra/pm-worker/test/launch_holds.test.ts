// /status.launch_holds の理由と解除見込み (#5110)。時間の窓で解ける見込みの時刻と、時間で解けない理由 (null) を確かめる。
import { test } from "node:test";
import assert from "node:assert/strict";
import { readyHold, recentHold, stoppedHold } from "../src/holdinfo.ts";
import { BOT_COMMENT_WINDOW_H, RUN_WINDOW_H } from "../src/classify.ts";
import { noPrCooldownMs, planLaunch } from "../src/launch.ts";

const H = 3_600_000;
const T = Date.parse("2026-10-15T00:00:00Z");
const iso = (ms: number) => new Date(ms).toISOString();

test("recent の bot コメント: 解除見込みは bot コメント + BOT_COMMENT_WINDOW_H (classify.ts の窓)", () => {
  const h = recentHold(7, "bot comment 0.2h ago", { botAt: T });
  assert.equal(h.reason, "bot-comment");
  assert.equal(h.until, iso(T + BOT_COMMENT_WINDOW_H * H));
});

test("recent の launched / run finished: 起点 + 3 時間", () => {
  assert.equal(recentHold(8, "launched 1.0h ago", { launchedAt: T }).until, iso(T + RUN_WINDOW_H * H));
  assert.equal(recentHold(8, "run finished 0.5h ago", { doneAt: T }).until, iso(T + RUN_WINDOW_H * H));
});

test("recent の oc:no-pr cooldown: lastAct + noPrCooldownMs (critical は半分)", () => {
  const h = recentHold(9, "oc:no-pr cooldown", { lastAct: T, cooldownMs: noPrCooldownMs("normal", 3) });
  assert.equal(h.reason, "oc:no-pr cooldown");
  assert.equal(h.until, iso(T + 3 * H));
  const c = recentHold(9, "oc:no-pr cooldown", { lastAct: T, cooldownMs: noPrCooldownMs("critical", 3) });
  assert.equal(c.until, iso(T + 1.5 * H));
});

test("recent の launch not observed: 観測待ちなので時間では解けない (until は null)", () => {
  const h = recentHold(10, "launch not observed yet (3 min)", { launchedAt: T });
  assert.equal(h.reason, "launch-not-observed");
  assert.equal(h.until, null);
});

test("時刻が欠けるときは捏造せず null", () => {
  assert.equal(recentHold(11, "bot comment 0.2h ago", {}).until, null);
  assert.equal(recentHold(11, "oc:no-pr cooldown", { lastAct: T }).until, null);
});

test("stopped の理由は既知の語だけを出し、本文の抜粋は理由にしない", () => {
  assert.equal(stoppedHold(1, "oc:no-pr x3").reason, "oc:no-pr");
  assert.equal(stoppedHold(1, "artifact: 新しい素材なし").reason, "artifact");
  assert.equal(stoppedHold(1, "killed x2").reason, "killed");
  assert.equal(stoppedHold(1, "parent/stuck").reason, "parent-or-stuck");
  assert.equal(stoppedHold(1, "launch-unobserved").reason, "launch-unobserved");
  assert.equal(stoppedHold(1, "stop").reason, "stop");
  assert.equal(stoppedHold(1, "着手不可 素材不足の本文").reason, "bot-report");
  assert.equal(stoppedHold(1, "着手不可 素材不足の本文").until, null);
});

test("stopped の判定根拠 (#5234): 見出し由来と run-outcome 由来の根拠が basis に出る。根拠が無いときは basis のキーを出さない", () => {
  assert.deepEqual(stoppedHold(2, "着手不可", "見出し ## 停止報告"), { n: 2, row: "stopped", reason: "bot-report", until: null, basis: "見出し ## 停止報告" });
  assert.deepEqual(stoppedHold(3, "split", "run-outcome reason=split"), { n: 3, row: "stopped", reason: "split", until: null, basis: "run-outcome reason=split" });
  assert.equal("basis" in stoppedHold(4, "stop"), false);
});

test("ready の見送り (planLaunch.held): 枠 (room) で落ちた ready は room、batch で落ちたものは batch", () => {
  const ready = Array.from({ length: 6 }, (_, i) => ({ n: 100 + i, title: "t", blocksCount: 0 }));
  const byRoom = planLaunch({ ready, relaunch: [], active: 48, target: 50, batch: 25 });
  assert.deepEqual(byRoom.picks, [100, 101]);
  assert.deepEqual(byRoom.held.map((h) => [h.n, h.why]), [[102, "room"], [103, "room"], [104, "room"], [105, "room"]]);
  const byBatch = planLaunch({ ready, relaunch: [], active: 0, target: 50, batch: 2 });
  assert.deepEqual(byBatch.picks, [100, 101]);
  assert.deepEqual(byBatch.held.map((h) => [h.n, h.why]), [[102, "batch"], [103, "batch"], [104, "batch"], [105, "batch"]]);
});

test("ready の見送り (planLaunch.held): LOW_CAP で落ちた prio:low は low-cap。枠に入った issue は held に出ない", () => {
  const ready = [
    { n: 100, title: "t", blocksCount: 0, labels: ["prio:critical"] },
    { n: 101, title: "t", blocksCount: 0, labels: ["prio:low"] },
    { n: 102, title: "t", blocksCount: 0, labels: ["prio:low"] },
  ];
  const isLow = (n: number) => n !== 100;
  const p = planLaunch({ ready, relaunch: [], active: 0, target: 50, batch: 25, low: { cap: 1, running: 0, applied: true, isLow } });
  assert.deepEqual(p.picks, [100, 101]);
  assert.deepEqual(p.held, [{ n: 102, why: "low-cap" }]);
});

test("ready の解除見込み: rate-guard は REST の reset 時刻。枠・stuck など他で解けるものは null", () => {
  const reset = Math.floor(T / 1000) + 600;
  assert.equal(readyHold(20, "rate-guard", { restReset: reset }).until, iso(reset * 1000));
  assert.equal(readyHold(20, "rate-guard", {}).until, null);
  assert.equal(readyHold(20, "room", { restReset: reset }).until, null);
  assert.equal(readyHold(20, "stuck-ceiling", { restReset: reset }).until, null);
  assert.equal(readyHold(20, "no-import", {}).row, "ready");
});
