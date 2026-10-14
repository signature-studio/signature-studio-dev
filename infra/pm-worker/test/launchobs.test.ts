import { test } from "node:test";
import assert from "node:assert/strict";
import { advanceLaunch, observedBy, OBSERVE_WINDOW_MS, type LaunchObs } from "../src/launchobs.ts";
import { T0, configuredApp, issuePayload, j, markFresh, runPayload, send, type Call } from "./helpers.ts";

const MIN = 60_000;
const TITLE = "[CI-61] alpha";
const iso = (ms: number) => new Date(ms).toISOString();
const comments = (calls: Call[]) => calls.filter((c) => c.method === "POST" && /\/issues\/\d+\/comments$/.test(c.url));

// LIVE で /oc 投稿を受ける。issue 61 だけを ready にする。
async function live(opts: { live?: boolean } = {}) {
  const ctx = await configuredApp({
    live: opts.live ?? true,
    handlers: [(c) => (/\/issues\/\d+\/comments$/.test(c.url) && c.method === "POST" ? j({ html_url: "x" }, 201) : undefined)],
  });
  assert.equal((await send(ctx.app, "issues", issuePayload(61, { title: TITLE }))).status, 202);
  return ctx;
}

// 時刻を進め、同期を新しくしてから launch を 1 回回す。
async function tickAt(ctx: Awaited<ReturnType<typeof live>>, t: number) {
  ctx.clock.t = t;
  await markFresh(ctx);
  const gh = await (ctx.app.engine as any).d.gh();
  return ctx.app.engine.launch(gh);
}

const obsOf = (ctx: Awaited<ReturnType<typeof live>>) => ctx.store.get<LaunchObs>("launchObs", "61");
const unobserved = (ctx: Awaited<ReturnType<typeof live>>) => (ctx.app.engine.status() as any).launch_unobserved as number[];

test("観測: 投稿後 5 分以内に同じ題名の issue_comment run が現れたら observed になり、started に入る", async () => {
  const ctx = await live();
  await tickAt(ctx, T0);
  assert.equal(obsOf(ctx)?.state, "launched");
  assert.equal(comments(ctx.m.calls).length, 1);
  await send(ctx.app, "workflow_run", runPayload(7, "in_progress", { event: "issue_comment", title: TITLE, created: iso(T0 + 30_000) }));
  const plan = await tickAt(ctx, T0 + MIN);
  assert.equal(obsOf(ctx)?.state, "observed");
  assert.deepEqual(unobserved(ctx), []);
  assert.ok(ctx.app.engine.plan().rows.started.some(([n]) => n === 61));
  assert.equal(comments(ctx.m.calls).length, 1, "観測できたら再投稿しない");
  assert.ok(!plan.picks.some((p) => p.n === 61));
});

test("(a) 5 分を超えても run が現れなければ failed。status に出し、何度 tick しても再投稿しない", async () => {
  const ctx = await live();
  await tickAt(ctx, T0);
  await tickAt(ctx, T0 + OBSERVE_WINDOW_MS);
  assert.equal(obsOf(ctx)?.state, "launched", "5 分ちょうどはまだ観測の窓の中");
  assert.ok(ctx.app.engine.plan().rows.recent.some(([n]) => n === 61), "観測するまでは recent");
  await tickAt(ctx, T0 + OBSERVE_WINDOW_MS + 1000);
  assert.equal(obsOf(ctx)?.state, "failed");
  assert.deepEqual(unobserved(ctx), [61]);
  // 3 時間を過ぎても、失敗した issue は再投稿しない (従来の 3 時間判定でも戻さない)
  await tickAt(ctx, T0 + 4 * 3_600_000);
  await tickAt(ctx, T0 + 5 * 3_600_000);
  assert.equal(comments(ctx.m.calls).length, 1, "同じ issue に自動で再投稿しない");
  const p = ctx.app.engine.plan();
  assert.ok(!p.picks.some((x) => x.n === 61));
  assert.deepEqual(p.rows.stopped.filter(([n]) => n === 61), [[61, "launch-unobserved"]]);
});

test("(b) 別 issue の run (題名が違う・issue_comment 以外) は観測と見なさない", async () => {
  const ctx = await live();
  await tickAt(ctx, T0);
  await send(ctx.app, "workflow_run", runPayload(8, "in_progress", { event: "issue_comment", title: "[CI-62] beta", created: iso(T0 + 30_000) }));
  await send(ctx.app, "workflow_run", runPayload(9, "queued", { event: "workflow_dispatch", title: TITLE, created: iso(T0 + 30_000) }));
  await tickAt(ctx, T0 + 6 * MIN);
  assert.equal(obsOf(ctx)?.state, "failed");
  assert.deepEqual(unobserved(ctx), [61]);
});

test("(b) 投稿より前に作られた同じ題名の run (古い run) は、今回の投稿の観測にしない", async () => {
  const ctx = await live();
  await send(ctx.app, "workflow_run", runPayload(5, "completed", { event: "issue_comment", title: TITLE, created: iso(T0 - 30 * MIN), at: iso(T0 - 29 * MIN) }));
  await tickAt(ctx, T0);
  await tickAt(ctx, T0 + 6 * MIN);
  assert.equal(obsOf(ctx)?.state, "failed");
});

test("(c) failed の後に run が遅れて現れたら observed に直す", async () => {
  const ctx = await live();
  await tickAt(ctx, T0);
  await tickAt(ctx, T0 + 6 * MIN);
  assert.equal(obsOf(ctx)?.state, "failed");
  assert.deepEqual(unobserved(ctx), [61]);
  await send(ctx.app, "workflow_run", runPayload(10, "in_progress", { event: "issue_comment", title: TITLE, created: iso(T0 + MIN) }));
  await tickAt(ctx, T0 + 7 * MIN);
  assert.equal(obsOf(ctx)?.state, "observed");
  assert.deepEqual(unobserved(ctx), []);
});

test("(d) dry-run は投稿しないので観測記録も作らず、失敗にもしない", async () => {
  const ctx = await live({ live: false });
  await tickAt(ctx, T0);
  await tickAt(ctx, T0 + 10 * MIN);
  assert.equal(comments(ctx.m.calls).length, 0);
  assert.equal(obsOf(ctx), undefined);
  assert.deepEqual(ctx.store.all("launchObs"), []);
  assert.deepEqual(unobserved(ctx), []);
});

test("同期が古い間は失敗にしない (観測の判定は同期が新しいときだけ)", async () => {
  const ctx = await live();
  await tickAt(ctx, T0);
  ctx.clock.t = T0 + 20 * MIN;
  const meta = ctx.store.get<any>("meta", "main") ?? {};
  meta.fullSyncAt = ctx.clock.t;
  meta.reconcileAt = T0;
  ctx.store.put("meta", "main", meta);
  ctx.app.engine.meta = meta;
  await (ctx.app.engine as any).launch(await (ctx.app.engine as any).d.gh());
  assert.equal(obsOf(ctx)?.state, "launched");
});

test("観測後に run が完了し、報告が無いまま 3 時間たったら従来どおり再着手の候補に戻る (観測済みは 3 時間判定を残す)", async () => {
  const ctx = await live();
  await tickAt(ctx, T0);
  await send(ctx.app, "workflow_run", runPayload(7, "in_progress", { event: "issue_comment", title: TITLE, created: iso(T0 + 30_000) }));
  await tickAt(ctx, T0 + MIN);
  assert.equal(obsOf(ctx)?.state, "observed");
  await send(ctx.app, "workflow_run", runPayload(7, "completed", { event: "issue_comment", title: TITLE, created: iso(T0 + 30_000), at: iso(T0 + 10 * MIN) }));
  assert.ok(ctx.app.engine.plan().rows.recent.some(([n]) => n === 61), "完了直後は 3 時間以内なので recent");
  ctx.clock.t = T0 + 4 * 3_600_000;
  assert.ok(ctx.app.engine.plan().picks.some((p) => p.n === 61), "3 時間を過ぎたら候補に戻る");
});

test("観測の純関数: 作成時刻の境界・5 分の境界・failed の後の観測", () => {
  const run = (created: number, title = TITLE, event = "issue_comment") => ({ id: 1, event, title, status: "in_progress", conclusion: null, updatedAt: "", createdAt: iso(created) });
  assert.equal(observedBy([run(T0 - 61_000)], TITLE, T0), false, "投稿の 61 秒前は数えない");
  assert.equal(observedBy([run(T0 - 59_000)], TITLE, T0), true, "投稿の 59 秒前までは数える (時刻のずれ)");
  assert.equal(observedBy([run(T0 + MIN, "[CI-62] beta")], TITLE, T0), false);
  assert.equal(observedBy([{ ...run(T0 + MIN), createdAt: undefined }], TITLE, T0), false, "作成時刻が無い run は数えない");
  const cur: LaunchObs = { state: "launched", at: iso(T0), changedAt: iso(T0) };
  assert.equal(advanceLaunch(cur, T0 + OBSERVE_WINDOW_MS, false, true), undefined);
  assert.equal(advanceLaunch(cur, T0 + OBSERVE_WINDOW_MS + 1, false, true)?.state, "failed");
  assert.equal(advanceLaunch(cur, T0 + OBSERVE_WINDOW_MS + 1, false, false), undefined, "同期が古いときは失敗にしない");
  assert.equal(advanceLaunch(cur, T0 + OBSERVE_WINDOW_MS + 1, true, false)?.state, "observed", "観測できたら同期が古くても観測済み");
  const failed: LaunchObs = { ...cur, state: "failed" };
  assert.equal(advanceLaunch(failed, T0 + 9 * MIN, true, true)?.state, "observed");
  assert.equal(advanceLaunch({ ...cur, state: "observed" }, T0 + 9 * MIN, false, true), undefined);
});
