import { test } from "node:test";
import assert from "node:assert/strict";
import { T0, configuredApp, issuePayload, j, markFresh, send, type Call, type Handler } from "./helpers.ts";

// metrics 行 (#5565) の契約。フィールドを足すのは自由だが、既存のキーを消す・型を変えると Custom Dashboard のクエリが壊れる。
const NUMERIC = [
  "active", "active_impl", "active_other", "active_critical", "active_normal", "active_low",
  "target", "target_eff", "room", "ready", "ready_critical", "ready_normal", "ready_low",
  "would_launch_now", "holds", "runs_running", "runs_queued", "launched", "dispatched", "pm_dispatched", "closed",
];
const NULLABLE_NUMERIC = ["cap_est", "peak_running", "rest_remaining"];
const BOOLEAN = ["fresh", "demoted", "rate_guard"];
const ENUM: Record<string, string[]> = { mode: ["live", "partial", "dry-run"], phase: ["review-only", "launch"] };
// 文字列を入れてよいキー。これ以外に文字列があれば自由文が混ざったということ (redact 以前の話)。
const STRING_KEYS = ["m", "ts", "mode", "phase", "stop", "blocked"];

// 1 行が満たすべき形。キーが欠けると (typeof undefined になるので) ここで落ちる。
function checkMetrics(line: Record<string, unknown>): void {
  assert.equal(line.m, "metrics");
  assert.ok(typeof line.ts === "string" && !Number.isNaN(Date.parse(line.ts)), "ts は ISO 時刻");
  for (const k of NUMERIC) assert.equal(typeof line[k], "number", `metrics: ${k} は数値`);
  for (const k of NULLABLE_NUMERIC) assert.ok(line[k] === null || typeof line[k] === "number", `metrics: ${k} は数値か null`);
  for (const k of BOOLEAN) assert.equal(typeof line[k], "boolean", `metrics: ${k} は真偽値`);
  for (const [k, vs] of Object.entries(ENUM)) assert.ok(vs.includes(line[k] as string), `metrics: ${k} は ${vs.join("/")}`);
  assert.ok(line.stop === null || line.stop === "stuck-ceiling" || line.stop === "rate-guard", "stop は停止の理由か null");
  assert.ok(line.blocked === null || line.blocked === "no-import", "blocked は no-import か null");
  for (const k of Object.keys(line)) if (typeof line[k] === "string") assert.ok(STRING_KEYS.includes(k), `metrics: ${k} に文字列は入れない`);
}

// tick が呼ぶ REST (dry-run なので書き込みは無い)。配送の一覧だけ空で返す (mockFetch は未定義の呼び出しを 599 にする)。
const tickHandlers = (): Handler[] => [(c: Call) => (c.url.includes("/app/hook/deliveries") ? j([], 200) : undefined)];

// console.log の引数列を捕まえて tick を n 回まわす。metrics 行は JSON オブジェクト、既存の行は文字列で出る (engine.ts)。
async function captureTicks(seedIssues: number[], ticks: number): Promise<unknown[][]> {
  const logs: unknown[][] = [];
  const orig = console.log;
  console.log = (...a: unknown[]) => void logs.push(a);
  try {
    const ctx = await configuredApp({ handlers: tickHandlers() });
    for (const n of seedIssues) await send(ctx.app, "issues", issuePayload(n));
    await markFresh(ctx);
    for (let i = 0; i < ticks; i++) await ctx.app.engine.tick();
    return logs;
  } finally {
    console.log = orig;
  }
}

const isMetrics = (a: unknown[]): boolean => a.length === 1 && !!a[0] && typeof a[0] === "object" && (a[0] as { m?: unknown }).m === "metrics";
const metricsLines = (logs: unknown[][]): Record<string, unknown>[] => logs.filter(isMetrics).map((a) => a[0] as Record<string, unknown>);

// ---------------------------------------------------------------------------------------------------------------- metrics 行 (#5565)
test("metrics: 1 tick 1 行。JSON として parse でき、必須キーが揃う", async () => {
  const logs = await captureTicks([21], 2);
  const lines = metricsLines(logs);
  assert.equal(lines.length, 2, "2 tick で 2 行 (1 tick 1 行を超えない)");
  for (const line of lines) {
    // 1 行が単体で JSON として round-trip できる (undefined・関数などの JSON にできない値が無い) こと。
    const parsed = JSON.parse(JSON.stringify(line)) as Record<string, unknown>;
    assert.deepEqual(parsed, line);
    checkMetrics(parsed);
  }
  // metrics 以外の console.log は既存の {pm:...} の 1 行文字列のまま (形式を変えない)。
  for (const a of logs.filter((x) => !isMetrics(x))) assert.equal(typeof a[0], "string", "既存の行は文字列のまま");

  // 値の意味 (dry-run・open issue 1 件・run 0 件の世界)。
  const last = lines[1];
  assert.equal(last.ts, new Date(T0).toISOString());
  assert.equal(last.mode, "dry-run");
  assert.equal(last.phase, "launch");
  assert.equal(last.demoted, false);
  assert.equal(last.rate_guard, false);
  assert.equal(last.active, 0);
  assert.equal(last.ready, 1);
  assert.equal(last.ready_normal, 1);
  assert.equal(last.would_launch_now, 1);
  assert.equal(last.launched, 0, "dry-run は /oc を投稿しない (wouldLaunch だけ数える)");
  assert.equal(last.peak_running, 0);
  assert.equal(last.rest_remaining, null);
});

test("metrics: キーが欠けた行は同じ検査で落ちる (ネガコントロール)", async () => {
  const lines = metricsLines(await captureTicks([], 1));
  assert.equal(lines.length, 1);
  checkMetrics(lines[0]); // 実測の行は検査を通る
  const broken: Record<string, unknown> = { ...lines[0] };
  delete broken.ready;
  assert.throws(() => checkMetrics(broken), /metrics: ready は数値/);
});
