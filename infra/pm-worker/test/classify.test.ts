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
  // hold (oc:hold) は launch_issues.py に無い Worker 版の区分。fixture に oc:hold は無いので空であることを確かめ、残りを突き合わせる。
  const { hold, ...ts } = classify(fx.snapshot, input).rows;
  assert.deepEqual(hold, []);
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

test("分類 (#2651): oc:hold の issue は hold 行に置き、launch の行 (ready・relaunch・stopped・recent) に入れない。ラベルを外すと ready に戻る", () => {
  const now = Date.parse("2026-10-14T12:00:00Z");
  const issue = (n: number, labels: string[], body = "") => ({ number: n, title: `[X-${n}] t`, labels, body, deps: null });
  const snap: Snapshot = {
    issues: [
      issue(80, []),
      issue(81, ["oc:hold"]),
      issue(82, ["oc:hold", "needs-user-input"]),
      issue(83, ["oc:hold"], "依存: #80"),
      // 停止報告 + 素材の追加で relaunch 候補になる issue。oc:hold が無ければ relaunch に入る (対照)。
      issue(84, ["oc:hold", "oc:no-pr"]),
      // 似た名前のラベルは oc:hold ではない (判定を広げると落ちる)。
      issue(85, ["hold"]),
      issue(86, ["oc:holdx"]),
      issue(87, ["oc:hold-old"]),
    ],
    prs: [],
    runs: [],
    bot_last: { "84": { at: new Date(now - 5 * 3_600_000).toISOString(), head: "素材不足のため停止します", art: "oc_artifacts: fl-win64 work-m11" } },
    bot_report: { "84": { at: new Date(now - 5 * 3_600_000).toISOString(), head: "素材不足のため停止します", art: "oc_artifacts: fl-win64 work-m11" } },
    pm_art: {},
  };
  const input: ClassifyInput = {
    nowMs: now,
    launched: {},
    relaunch: {},
    manualDeps: {},
    liveBlockers: {},
    fullBotBody: { "84": "素材不足のため停止します" },
    reportBody: { "84": "素材不足のため停止します" },
    outcomeReason: { "84": "artifact" },
  };
  const { rows } = classify(snap, input);
  assert.deepEqual(rows.hold, [[81, ""], [83, ""], [84, ""]], "oc:hold は hold 行 (needs-user-input が付くものは user 行が先)");
  assert.deepEqual(rows.user, [[82, ""]]);
  assert.deepEqual(rows.blocked, [], "hold が blocked より先");
  assert.deepEqual(rows.relaunch, [], "oc:hold の 84 は relaunch に入らない");
  assert.deepEqual(rows.ready, [80, 85, 86, 87], "似た名前のラベルは launch の対象のまま");
  const unhold = (ns: number[]) => ({ ...snap, issues: snap.issues.map((i) => (ns.includes(i.number) ? { ...i, labels: i.labels.filter((l) => l !== "oc:hold") } : i)) });
  const control = classify(unhold([84]), input).rows;
  assert.deepEqual(control.relaunch.map(([n]) => n), [84], "対照: oc:hold を外すと 84 は relaunch に入る");
  const after = classify(unhold([81, 83, 84]), input).rows;
  assert.ok(after.ready.includes(81), "ラベルを外すと ready に戻る");
  assert.deepEqual(after.hold, []);
});

test("分類 (#2758): 素材の再投入の基準は本文の oc_artifacts 行 (無ければ推定)", () => {
  const now = Date.parse("2026-10-14T12:00:00Z");
  const at = new Date(now - 5 * 3_600_000).toISOString();
  const head = "素材不足: plugins-serum2 が無い";
  const snap = (artLine?: string): Snapshot => ({
    issues: [{ number: 90, title: "[CI-90] t90", labels: [], body: "", deps: null, ...(artLine ? { artLine } : {}) }],
    prs: [],
    runs: [],
    bot_last: { "90": { at, head, art: null } },
    bot_report: { "90": { at, head, art: null } },
    pm_art: {},
  });
  const input: ClassifyInput = {
    nowMs: now,
    launched: {},
    relaunch: {},
    manualDeps: {},
    liveBlockers: {},
    fullBotBody: { "90": head },
    reportBody: { "90": head },
    outcomeReason: { "90": "artifact" },
  };
  const withBody = classify(snap("oc_artifacts: fl-win64 work-m11"), input).rows;
  assert.deepEqual(withBody.relaunch, [[90, "oc_artifacts: fl-win64 work-m11 plugins-serum2"]]);
  const inferred = classify(snap(), input).rows;
  assert.deepEqual(inferred.relaunch, [[90, "oc_artifacts: fl-win64 toolchain-retdec toolchain-emsdk plugins-serum2"]], "対照: 本文の行が無ければ推定値が基準");
});

test("分類 (#2758): 本文が oc_artifacts: none なら、不足素材は none を外して fl-win64 を補って足す (none と混在させない)", () => {
  const now = Date.parse("2026-10-14T12:00:00Z");
  const at = new Date(now - 5 * 3_600_000).toISOString();
  const head = "素材不足: plugins-serum2 が無い";
  const snap: Snapshot = {
    issues: [{ number: 91, title: "[CI-91] t91", labels: [], body: "", deps: null, artLine: "oc_artifacts: none" }],
    prs: [],
    runs: [],
    bot_last: { "91": { at, head, art: null } },
    bot_report: { "91": { at, head, art: null } },
    pm_art: {},
  };
  const input: ClassifyInput = {
    nowMs: now,
    launched: {},
    relaunch: {},
    manualDeps: {},
    liveBlockers: {},
    fullBotBody: { "91": head },
    reportBody: { "91": head },
    outcomeReason: { "91": "artifact" },
  };
  const rows = classify(snap, input).rows;
  assert.deepEqual(rows.relaunch, [[91, "oc_artifacts: fl-win64 plugins-serum2"]]);
});

test("分類 (#2758): 不足素材が fl-win64 のとき、本文の none・本文の行のどちらでも fl-win64 を重複させない", () => {
  const now = Date.parse("2026-10-14T12:00:00Z");
  const at = new Date(now - 5 * 3_600_000).toISOString();
  const head = "素材不足: fl-win64 が無い";
  const snap = (artLine: string): Snapshot => ({
    issues: [{ number: 92, title: "[CI-92] t92", labels: [], body: "", deps: null, artLine }],
    prs: [],
    runs: [],
    bot_last: { "92": { at, head, art: null } },
    bot_report: { "92": { at, head, art: null } },
    pm_art: {},
  });
  const input: ClassifyInput = {
    nowMs: now,
    launched: {},
    relaunch: {},
    manualDeps: {},
    liveBlockers: {},
    fullBotBody: { "92": head },
    reportBody: { "92": head },
    outcomeReason: { "92": "artifact" },
  };
  assert.deepEqual(classify(snap("oc_artifacts: none"), input).rows.relaunch, [[92, "oc_artifacts: fl-win64"]]);
  assert.deepEqual(classify(snap("oc_artifacts: plugins-ott"), input).rows.relaunch, [[92, "oc_artifacts: fl-win64 plugins-ott"]]);
});
