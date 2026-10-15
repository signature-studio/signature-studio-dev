// /status.launch_holds の理由と解除見込み (#5110)。時間の窓で解ける見込みの時刻と、時間で解けない理由 (null) を確かめる。
import { test } from "node:test";
import assert from "node:assert/strict";
import { recentHold, stoppedHold } from "../src/holdinfo.ts";
import { BOT_COMMENT_WINDOW_H, RUN_WINDOW_H } from "../src/classify.ts";
import { noPrCooldownMs } from "../src/launch.ts";

const H = 3_600_000;
const T = Date.parse("2026-10-15T00:00:00Z");
const iso = (ms: number) => new Date(ms).toISOString();

test("recent の bot コメント: 解除見込みは bot コメント + 1.5 時間 (classify.ts の窓)", () => {
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
