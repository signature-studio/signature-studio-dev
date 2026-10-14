import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { classify, type ClassifyInput, type Snapshot } from "../src/classify.ts";

const here = fileURLToPath(new URL(".", import.meta.url));
const fixturePath = `${here}fixtures/classify.input.json`;
const crosscheck = `${here}classify_crosscheck.py`;

interface Fixture extends ClassifyInput {
  now: string;
  snapshot: Snapshot;
}

const fx: Fixture & { now: string } = JSON.parse(readFileSync(fixturePath, "utf8"));

test("分類: 固定 JSON で TS の classify が期待どおりの行に振り分ける", () => {
  const input: ClassifyInput = {
    nowMs: Date.parse(fx.now),
    launched: fx.launched,
    relaunch: fx.relaunch,
    manualDeps: fx.manualDeps,
    liveBlockers: fx.liveBlockers,
    fullBotBody: fx.fullBotBody,
    reportBody: fx.reportBody,
    outcomeReason: fx.outcomeReason,
  };
  const { rows } = classify(fx.snapshot, input);
  assert.deepEqual(rows.user, [[2, ""]]);
  assert.deepEqual(rows.blocked, [
    [3, [1]],
    [5, [6]],
    [7, [8]],
    [9, [10]],
    [19, [18]],
  ]);
  assert.deepEqual(rows.started, [
    [4, ["PR#900", "PR#901"]],
    [16, ["run555"]],
  ]);
  assert.deepEqual(rows.relaunch, [
    [12, "oc_artifacts: fl-win64 toolchain-retdec toolchain-emsdk work-m11"],
    [21, "oc_artifacts: fl-win64 work-m11"],
  ]);
  assert.deepEqual(rows.stopped, [
    [13, "停止します。判断を求めます。"],
    [17, "素材不足: work-m11 が無い"],
  ]);
  assert.deepEqual(rows.recent, [
    [11, "launched 1.0h ago"],
    [14, "bot comment 1.0h ago"],
  ]);
  // 被ブロック数の多い順 (1,6,8,10,18 は各 1 件)、同数は番号順。0 件の 15,20 が後ろ。
  assert.deepEqual(rows.ready, [1, 6, 8, 10, 18, 15, 20]);
});

test("分類 (ネガコン): 最後の run-outcome が artifact でなければ、停止報告に素材が挙がっていても再投入しない", () => {
  const input: ClassifyInput = {
    nowMs: Date.parse(fx.now),
    launched: fx.launched,
    relaunch: fx.relaunch,
    manualDeps: fx.manualDeps,
    liveBlockers: fx.liveBlockers,
    fullBotBody: fx.fullBotBody,
    reportBody: fx.reportBody,
    outcomeReason: { ...fx.outcomeReason, "12": "split", "21": "unknown" },
  };
  const { rows } = classify(fx.snapshot, input);
  assert.deepEqual(rows.relaunch, []);
  assert.deepEqual(rows.stopped.map(([n]) => n), [12, 13, 17, 21]);
});

test("分類: TS と Python (tools/pm/launch_issues.py の classify) が同じ rows を返す", () => {
  const input: ClassifyInput = {
    nowMs: Date.parse(fx.now),
    launched: fx.launched,
    relaunch: fx.relaunch,
    manualDeps: fx.manualDeps,
    liveBlockers: fx.liveBlockers,
    fullBotBody: fx.fullBotBody,
    reportBody: fx.reportBody,
    outcomeReason: fx.outcomeReason,
  };
  const ts = classify(fx.snapshot, input).rows;
  const py = JSON.parse(execFileSync("python3", [crosscheck, fixturePath], { encoding: "utf8" }));
  assert.deepEqual(ts, py);
});

test("分類: STOP_RE の判定から run-outcome と PM マーカーの本文を除く (素材不足の定型文を停止報告にしない)", () => {
  const now = Date.parse("2026-10-14T12:00:00Z");
  const at = new Date(now - 30 * 60_000).toISOString();
  const outcome = "理由の分類: artifact=素材不足\n<!-- oc-run-outcome: no-pr reason=artifact run=1 -->";
  const snap = (body: string): Snapshot => ({
    issues: [{ number: 70, title: "[X-1] t", labels: ["oc:no-pr"], body: "", deps: null }],
    prs: [],
    runs: [],
    bot_last: { "70": { at, head: body.slice(0, 400), art: null } },
    bot_report: {},
    pm_art: {},
  });
  const input = (body: string): ClassifyInput => ({
    nowMs: now,
    launched: {},
    relaunch: {},
    manualDeps: {},
    liveBlockers: {},
    fullBotBody: { "70": body },
    reportBody: {},
    outcomeReason: {},
  });
  const plain = classify(snap("素材不足のため停止します"), input("素材不足のため停止します")).rows;
  assert.deepEqual(plain.stopped.map(([n]) => n), [70], "対照: マーカーの無い停止報告は stopped");
  const marked = classify(snap(outcome), input(outcome)).rows;
  assert.deepEqual(marked.stopped, [], "run-outcome は stopped にしない");
  assert.deepEqual(marked.recent.map(([n]) => n), [70]);
});
