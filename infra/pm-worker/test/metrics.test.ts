import { test } from "node:test";
import assert from "node:assert/strict";
import { configuredApp, markFresh, T0 } from "./helpers.ts";
import { METRICS_KEYS, metricsRow, missingMetricsKeys } from "../src/metrics.ts";

const status = {
  fresh: true,
  mode: "dry-run",
  phase: "launch",
  launch_stop: null,
  launch_blocked: null,
  active_all: 3,
  active_impl: 2,
  active_other: 1,
  active_by_prio: { critical: 1, normal: 1, low: 1 },
  target: 5,
  target_eff: 4,
  cap_est: null,
  room: 1,
  ready: 2,
  ready_by_prio: { critical: 0, normal: 2, low: 0 },
  would_launch_now: [{ n: 11, art: "a", relaunch: false }],
  launch_holds: [],
  running: { in_progress: 2, queued: 1, pending: 0 },
  queued: 1,
  peak_running: 4,
  counters: { launched: 7, dispatched: 2, pmDispatched: 3, closed: 1 },
  rest_remaining: 4000,
};

test("metrics 行: 1 行で JSON として parse でき、必須キーが揃う", () => {
  const row = metricsRow(status, "2026-10-16T00:00:00.000Z", false, false);
  const back = JSON.parse(JSON.stringify(row));
  assert.equal(back.m, "metrics");
  assert.deepEqual(missingMetricsKeys(back), []);
  assert.equal(back.active_critical, 1);
  assert.equal(back.would_launch_now, 1);
  assert.equal(back.runs_running, 2);
  assert.equal(back.pm_dispatched, 3);
});

test("metrics 行: 自由文 (タイトル・本文・login) を含まない", () => {
  const row = metricsRow({ ...status, launch_stop: null }, "2026-10-16T00:00:00.000Z", true, true);
  const text = JSON.stringify(row);
  assert.equal(text.includes("title"), false);
  assert.equal(text.includes("body"), false);
  assert.equal(row.demoted, true);
  assert.equal(row.rate_guard, true);
});

test("metrics 行: キーが欠けると missingMetricsKeys が検出する (ネガコン)", () => {
  const row: Record<string, unknown> = { ...metricsRow(status, "2026-10-16T00:00:00.000Z", false, false) };
  delete row.room;
  delete row.rest_remaining;
  assert.deepEqual(missingMetricsKeys(row), ["room", "rest_remaining"]);
  assert.equal(METRICS_KEYS.length, 33);
});

test("tick: 1 tick につき metrics 行が 1 行出て、必須キーが揃う", async () => {
  const logs: string[] = [];
  const orig = console.log;
  console.log = (...a: unknown[]) => void logs.push(a.map(String).join(" "));
  try {
    const ctx = await configuredApp();
    await markFresh(ctx);
    await ctx.app.engine.tick();
    const rows = logs.filter((l) => l.includes('"m":"metrics"'));
    assert.equal(rows.length, 1);
    const row = JSON.parse(rows[0]);
    assert.deepEqual(missingMetricsKeys(row), []);
    assert.equal(row.ts, new Date(T0).toISOString());
    assert.equal(row.mode, "dry-run");
  } finally {
    console.log = orig;
  }
});
