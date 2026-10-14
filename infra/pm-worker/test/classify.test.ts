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

test("分類: TS と Python (tools/pm/launch_issues.py の classify) が同じ rows を返す", () => {
  const input: ClassifyInput = {
    nowMs: Date.parse(fx.now),
    launched: fx.launched,
    relaunch: fx.relaunch,
    manualDeps: fx.manualDeps,
    liveBlockers: fx.liveBlockers,
    fullBotBody: fx.fullBotBody,
  };
  const ts = classify(fx.snapshot, input).rows;
  const py = JSON.parse(execFileSync("python3", [crosscheck, fixturePath], { encoding: "utf8" }));
  assert.deepEqual(ts, py);
});
