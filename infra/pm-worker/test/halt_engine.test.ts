import { test } from "node:test";
import assert from "node:assert/strict";
import { configuredApp, issuePayload, j, markFresh, send, T0, type Call } from "./helpers.ts";
import { PM_LIMITS } from "../src/pm.ts";

// launch の停止 (#2795) の統合。/status.launch_halted と launch_halted_overdue・PM への 1 回の通知・区間の解消を、時計を進めて確かめる。
const MIN = 60_000;
const iso = (min: number) => new Date(T0 + min * MIN).toISOString();
const digestCalls = (calls: Call[]) =>
  calls.filter((c) => c.method === "POST" && c.url.endsWith("/dispatches") && c.body?.event_type === "oc-pm" && c.body?.client_payload?.kind === "digest");
const ok = (c: Call) => (c.url.endsWith("/dispatches") ? j(null, 204) : undefined);

test("launch の停止: 取り込み前 (IMPORT_REQUIRED=1) は no-import で止まり、15 分で overdue、30 分で PM に 1 回だけ知らせる", async () => {
  const clock = { t: T0 };
  const ctx = await configuredApp({ live: true, now: clock, handlers: [ok], env: { IMPORT_REQUIRED: "1", LIVE_LAUNCH: "0" } });
  const tickAt = async (min: number) => {
    clock.t = T0 + min * MIN;
    await markFresh(ctx);
    await ctx.app.engine.tick();
  };
  assert.equal((await send(ctx.app, "issues", issuePayload(901))).status, 202);

  await tickAt(0);
  let s = ctx.app.engine.status() as any;
  assert.deepEqual(s.launch_halted, { reason: "no-import", since: iso(0) });
  assert.equal(s.launch_halted_overdue, false);
  assert.equal(digestCalls(ctx.m.calls).length, 0);

  await tickAt(14);
  s = ctx.app.engine.status() as any;
  assert.equal(s.launch_halted_overdue, false, "15 分未満は overdue ではない");

  await tickAt(15);
  s = ctx.app.engine.status() as any;
  assert.ok(s.ready >= 1, "着手待ちがある");
  assert.equal(s.launch_halted_overdue, true, "15 分経過・着手待ちと空き枠がある");
  assert.equal(s.launch_halted.since, iso(0), "起点は止まり始めた時刻のまま");
  assert.equal(digestCalls(ctx.m.calls).length, 0, "15 分ではまだ通知しない");

  await tickAt(29);
  assert.equal(digestCalls(ctx.m.calls).length, 0, "29 分では通知しない");

  await tickAt(30);
  let d = digestCalls(ctx.m.calls);
  assert.equal(d.length, 1, "30 分で 1 回通知する");
  assert.deepEqual(d[0].body, { event_type: "oc-pm", client_payload: { kind: "digest", ref: 0 } });

  await tickAt(31);
  await tickAt(90);
  d = digestCalls(ctx.m.calls);
  assert.equal(d.length, 1, "同じ停止区間では繰り返さない");
  assert.equal((ctx.app.engine.status() as any).counters.pmDispatched, 1);

  ctx.app.engine.importVm({ launched: {}, relaunch: {}, phase: { review_only: false, open_prs: 0, since: iso(100) }, pm_art: {} }, true);
  await tickAt(100);
  s = ctx.app.engine.status() as any;
  assert.equal(s.launch_halted, null, "取り込んだら区間は解消する");
  assert.equal(s.launch_halted_overdue, false);
  assert.equal(ctx.app.engine.meta.halt, undefined, "解消した区間は保存しない");
});

test("launch の停止: 解消した後の新しい停止は、新しい起点で数え直し、もう一度だけ通知する (dry-run は記録だけ)", async () => {
  const clock = { t: T0 };
  const ctx = await configuredApp({ now: clock, env: { IMPORT_REQUIRED: "0", LIVE_LAUNCH: "0", LIVE_DISPATCH: "0" } });
  await markFresh(ctx);
  clock.t = T0 + 5 * MIN;
  // 同期が古い (reconcile から 15 分以上) → stale で止まる。launch は書かない。
  ctx.app.engine.meta.reconcileAt = T0 - 60 * MIN;
  await ctx.app.engine.launch(null);
  let s = ctx.app.engine.status() as any;
  assert.deepEqual(s.launch_halted, { reason: "stale", since: iso(5) });
  assert.equal(await ctx.app.engine.haltNotify(null), "skipped", "30 分前は送らない");

  clock.t = T0 + 35 * MIN;
  assert.equal(await ctx.app.engine.haltNotify(null), "would", "dry-run は would に記録する");
  assert.equal(await ctx.app.engine.haltNotify(null), "skipped", "同じ区間では 2 回目を出さない");
  assert.equal((ctx.app.engine.status() as any).counters.wouldDispatchPm, 1);
  assert.equal(digestCalls(ctx.m.calls).length, 0, "dry-run は送らない");

  // 同期が新しくなって解消 → 区間は消える。次の停止は新しい起点で、もう一度 1 回だけ通知する。
  clock.t = T0 + 40 * MIN;
  ctx.app.engine.meta.reconcileAt = clock.t;
  ctx.app.engine.meta.fullSyncAt = clock.t;
  await ctx.app.engine.launch(null);
  assert.equal(ctx.app.engine.meta.halt, undefined);
  assert.equal((ctx.app.engine.status() as any).launch_halted, null);
  clock.t = T0 + 50 * MIN;
  ctx.app.engine.meta.reconcileAt = T0 - 60 * MIN;
  await ctx.app.engine.launch(null);
  s = ctx.app.engine.status() as any;
  assert.deepEqual(s.launch_halted, { reason: "stale", since: iso(50) }, "起点は今回の停止の開始");
  clock.t = T0 + 100 * MIN;
  assert.equal(await ctx.app.engine.haltNotify(null), "would", "前の区間の通知とは別に 1 回送る (同じ digest#0 の 60 分の上限の外)");
});

// 降格 (#2340) の中の停止通知: dispatch と同じ降格ゲート。降格中は送らず would に数え、区間の 1 回を使わずに保留する。解除の後に送る。
test("降格中は停止通知を送らず would に数え、解除の後に 1 回送る", async () => {
  const clock = { t: T0 };
  const repoPush = (c: Call) => (c.method === "GET" && c.url.endsWith("/repos/signature-studio/signature-studio-dev") && c.auth === "Bearer ghp_valid_push_token_x" ? j({ permissions: { push: true } }) : undefined);
  const ctx = await configuredApp({ live: true, now: clock, handlers: [ok, repoPush], env: { IMPORT_REQUIRED: "1", LIVE_LAUNCH: "0" } });
  const tickAt = async (min: number) => {
    clock.t = T0 + min * MIN;
    await markFresh(ctx);
    await ctx.app.engine.tick();
  };
  const oc = (id: number, login: string, min: number) => send(ctx.app, "issue_comment", {
    action: "created",
    repository: { full_name: "signature-studio/signature-studio-dev" },
    issue: { number: 901 },
    comment: { id, user: { login }, body: "/oc\noc_artifacts: fl-win64", created_at: iso(min) },
  });
  assert.equal((await send(ctx.app, "issues", issuePayload(901))).status, 202);
  await tickAt(0);
  assert.deepEqual((ctx.app.engine.status() as any).launch_halted, { reason: "no-import", since: iso(0) });

  await oc(1, "pycabbage", 1);
  await oc(2, "oc-pm-for-signature-studio[bot]", 2);
  assert.equal((ctx.app.engine.status() as any).demoted_reason, "double-oc #901");

  const before = (ctx.app.engine.status() as any).counters.wouldDispatchPm ?? 0;
  await tickAt(31);
  assert.equal(digestCalls(ctx.m.calls).length, 0, "降格中は停止通知を送らない");
  assert.ok(((ctx.app.engine.status() as any).counters.wouldDispatchPm ?? 0) > before, "降格中は would に数える");
  assert.equal((ctx.app.engine.status() as any).counters.pmDispatched ?? 0, 0);
  assert.equal(ctx.app.engine.meta.halt?.notifiedAt, undefined, "降格中は区間の 1 回を使わない");

  await tickAt(32);
  assert.equal(digestCalls(ctx.m.calls).length, 0, "60 分以内の再試行は would の重複を数えない");

  const reset = await ctx.app.handle(new Request("https://pm.example/demote/reset", { method: "POST", headers: { authorization: "Bearer ghp_valid_push_token_x" } }));
  assert.equal(reset.status, 200);
  await tickAt(40);
  assert.equal(digestCalls(ctx.m.calls).length, 1, "解除の後に 1 回送る");
  assert.equal((ctx.app.engine.status() as any).launch_halted?.since, iso(0), "区間は解消していない");
  await tickAt(41);
  assert.equal(digestCalls(ctx.m.calls).length, 1, "送ったあとは同じ区間で繰り返さない");
});

test("停止通知が毎時上限で見送られたら、pm_skipped_hour_24h に tick ごとに数え、区間の 1 回は使わない (#3462)", async () => {
  const clock = { t: T0 };
  const ctx = await configuredApp({ live: true, now: clock, handlers: [ok], env: { IMPORT_REQUIRED: "1", LIVE_LAUNCH: "0" } });
  const tickAt = async (min: number) => {
    clock.t = T0 + min * MIN;
    await markFresh(ctx);
    await ctx.app.engine.tick();
  };
  await tickAt(0);
  ctx.store.put("meta", "pmDispatch", Array.from({ length: PM_LIMITS.hourMax }, (_, i) => ({ kind: "stuck", ref: 500 + i, at: T0 + 30 * MIN })));
  await tickAt(31);
  assert.equal(digestCalls(ctx.m.calls).length, 0, "毎時上限の内は停止通知を送らない");
  assert.equal((ctx.app.engine.status() as any).pm_skipped_hour_24h, 1);
  assert.equal(ctx.app.engine.meta.halt?.notifiedAt, undefined, "見送った通知は区間の 1 回を使わない");
  await tickAt(32);
  assert.equal((ctx.app.engine.status() as any).pm_skipped_hour_24h, 2);
});
