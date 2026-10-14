import { test } from "node:test";
import assert from "node:assert/strict";
import { configuredApp, issuePayload, j, markFresh, send, T0, type Call } from "./helpers.ts";

// 降格 (#2340): 同じ issue に 30 分以内に 2 回目の /oc が付いたら DO を dry-run に戻す。shadow: would_launch と VM (PM の個人アカウント) の /oc を突き合わせる。

const R = "/repos/signature-studio/signature-studio-dev";
const PM_BOT = "oc-pm-for-signature-studio[bot]";
const VM = "pycabbage";
const MIN = 60_000;
const PUSH = "Bearer ghp_valid_push_token_x";
const comments = (calls: Call[]) => calls.filter((c) => c.method === "POST" && /\/issues\/\d+\/comments$/.test(c.url));
const writeHandlers = [
  (c: Call) => (c.method === "POST" && /\/issues\/\d+\/comments$/.test(c.url) ? j({ html_url: "x" }, 201) : undefined),
  (c: Call) => (c.method === "GET" && c.url.endsWith(R) && c.auth === PUSH ? j({ permissions: { push: true } }) : undefined),
];

const ocEv = (n: number, id: number, login: string, at: number, body = "/oc\noc_artifacts: fl-win64") => ({
  action: "created",
  repository: { full_name: "signature-studio/signature-studio-dev" },
  issue: { number: n },
  comment: { id, user: { login }, body, created_at: new Date(at).toISOString() },
});

const status = async (ctx: { app: { handle(r: Request): Promise<Response> } }) => (await (await ctx.app.handle(new Request("https://pm.example/status"))).json()) as any;

test("降格 (正例): 同じ issue に 30 分以内に 2 回目の /oc (VM → PM App) が付くと dry-run に戻り、理由と counters を出す", async () => {
  const ctx = await configuredApp({ live: true, handlers: writeHandlers });
  for (const n of [11, 12]) await send(ctx.app, "issues", issuePayload(n));
  assert.equal((await send(ctx.app, "issue_comment", ocEv(11, 1, VM, T0 + 1 * MIN))).status, 202);
  ctx.clock.t = T0 + 10 * MIN;
  assert.equal((await send(ctx.app, "issue_comment", ocEv(11, 2, PM_BOT, T0 + 10 * MIN))).status, 202);
  const s = await status(ctx);
  assert.equal(s.demoted_reason, "double-oc #11");
  assert.equal(s.mode_launch, "dry-run");
  assert.equal(s.mode_dispatch, "dry-run");
  assert.equal(s.mode, "dry-run");
  assert.equal(s.counters.demoted, 1);
  // 降格後は live の設定でも投稿しない (計画だけ残す)。
  await markFresh(ctx);
  await ctx.app.engine.launch(await (ctx.app.engine as any).d.gh());
  assert.equal(comments(ctx.m.calls).length, 0);
  assert.equal((await status(ctx)).counters.wouldLaunch, 1);
});

test("降格 (ネガ): 1 件だけ / 30 分を超えた 2 件 / 判定の窓より前の 2 件 / 同じコメントの再配送 では降格しない", async () => {
  const one = await configuredApp({ live: true, handlers: writeHandlers });
  await send(one.app, "issue_comment", ocEv(11, 1, VM, T0 + 1 * MIN));
  assert.equal((await status(one)).demoted_reason, null);

  const far = await configuredApp({ live: true, handlers: writeHandlers });
  await send(far.app, "issue_comment", ocEv(11, 1, VM, T0 + 1 * MIN));
  far.clock.t = T0 + 40 * MIN;
  await send(far.app, "issue_comment", ocEv(11, 2, PM_BOT, T0 + 32 * MIN));
  assert.equal((await status(far)).demoted_reason, null);

  // 窓 (ocWatchFrom = T0) より前の 2 件は、過去の二重投稿として降格しない。
  const old = await configuredApp({ live: true, handlers: writeHandlers });
  await send(old.app, "issue_comment", ocEv(11, 1, VM, T0 - 40 * MIN));
  await send(old.app, "issue_comment", ocEv(11, 2, VM, T0 - 20 * MIN));
  assert.equal((await status(old)).demoted_reason, null);

  // 同じ id の再配送 (webhook の後に reconcile が読む) は 2 件目に数えない。
  const dup = await configuredApp({ live: true, handlers: writeHandlers });
  await send(dup.app, "issue_comment", ocEv(11, 1, VM, T0 + 1 * MIN));
  await send(dup.app, "issue_comment", ocEv(11, 1, VM, T0 + 1 * MIN));
  assert.equal((await status(dup)).demoted_reason, null);

  // /oc で始まらない PM のコメントは数えない。
  const plain = await configuredApp({ live: true, handlers: writeHandlers });
  await send(plain.app, "issue_comment", ocEv(11, 1, VM, T0 + 1 * MIN));
  await send(plain.app, "issue_comment", ocEv(11, 2, VM, T0 + 2 * MIN, "状況の共有です"));
  assert.equal((await status(plain)).demoted_reason, null);
});

test("降格の解除は手動だけ: 認証なしは 401、push 権限ありで解除、以後の launch は live に戻る (自動で再昇格しない)", async () => {
  const ctx = await configuredApp({ live: true, handlers: writeHandlers });
  for (const n of [11, 12]) await send(ctx.app, "issues", issuePayload(n));
  await send(ctx.app, "issue_comment", ocEv(11, 1, VM, T0 + 1 * MIN));
  await send(ctx.app, "issue_comment", ocEv(11, 2, PM_BOT, T0 + 2 * MIN));
  assert.equal((await status(ctx)).demoted_reason, "double-oc #11");
  await markFresh(ctx);
  await ctx.app.engine.launch(await (ctx.app.engine as any).d.gh());
  assert.equal(comments(ctx.m.calls).length, 0, "降格中は投稿しない");
  const noAuth = await ctx.app.handle(new Request("https://pm.example/demote/reset", { method: "POST" }));
  assert.equal(noAuth.status, 401);
  assert.equal((await status(ctx)).demoted_reason, "double-oc #11", "認証なしでは解除されない");
  const ok = await ctx.app.handle(new Request("https://pm.example/demote/reset", { method: "POST", headers: { authorization: PUSH } }));
  assert.equal(ok.status, 200);
  assert.deepEqual(await ok.json(), { ok: true, reset: true });
  const s = await status(ctx);
  assert.equal(s.demoted_reason, null);
  assert.equal(s.mode_launch, "live");
  assert.equal(s.counters.restored, 1);
  await ctx.app.engine.launch(await (ctx.app.engine as any).d.gh());
  assert.equal(comments(ctx.m.calls).length, 1, "解除後は 12 だけ投稿する (11 は投稿済み)");
});

// 解除の後の full sync (6 時間ごと) は、解除前の /oc を created_at 降順で読み直す。そこで再降格してはならない。
test("解除は full sync で取り消されない: 解除前の /oc の組は、読み直しても再降格しない (コメントは API と同じ降順)", async () => {
  const listed: any[] = [];
  const read = (c: Call) => {
    if (c.method !== "GET") return undefined;
    const p = new URL(c.url).pathname;
    if (p.endsWith("/issues/comments")) return j([...listed].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)));
    if (p.endsWith("/issues")) return j([issuePayload(11).issue, issuePayload(12).issue]);
    if (p.endsWith("/actions/runs")) return j({ workflow_runs: [] });
    if (p.endsWith("/pulls")) return j([]);
    if (/\/dependencies\/blocked_by$/.test(p)) return j([]);
    return undefined;
  };
  const ctx = await configuredApp({ live: true, handlers: [...writeHandlers, read] });
  const oc = async (n: number, id: number, login: string, at: number) => {
    listed.push({ id, issue_url: `https://api.github.com${R}/issues/${n}`, user: { login }, body: "/oc\noc_artifacts: fl-win64", created_at: new Date(at).toISOString(), updated_at: new Date(at).toISOString() });
    ctx.clock.t = at;
    return send(ctx.app, "issue_comment", ocEv(n, id, login, at));
  };
  for (const n of [11, 12]) await send(ctx.app, "issues", issuePayload(n));
  await oc(11, 1, VM, T0 + 1 * MIN);
  await oc(11, 2, PM_BOT, T0 + 10 * MIN);
  assert.equal((await status(ctx)).demoted_reason, "double-oc #11");
  ctx.clock.t = T0 + 20 * MIN;
  const reset = await ctx.app.handle(new Request("https://pm.example/demote/reset", { method: "POST", headers: { authorization: PUSH } }));
  assert.deepEqual(await reset.json(), { ok: true, reset: true });
  await oc(12, 3, PM_BOT, T0 + 3 * 60 * MIN);
  ctx.clock.t = T0 + 6 * 60 * MIN;
  await ctx.app.engine.fullSync((await (ctx.app.engine as any).d.gh()) as any);
  const s = await status(ctx);
  assert.equal(s.demoted_reason, null, "解除が full sync で取り消されない");
  assert.equal(s.mode_launch, "live");
  assert.equal(s.counters.demoted, 1);
  assert.equal(s.counters.restored, 1);
});

// 解除の後は、解除前の /oc を相手にしない (解除の時刻より前の投稿とは組にしない)。
test("解除の後: 解除前の /oc から 30 分以内の新しい /oc では再降格しない", async () => {
  const ctx = await configuredApp({ live: true, handlers: writeHandlers });
  await send(ctx.app, "issue_comment", ocEv(11, 1, VM, T0 + 1 * MIN));
  await send(ctx.app, "issue_comment", ocEv(11, 2, PM_BOT, T0 + 2 * MIN));
  assert.equal((await status(ctx)).demoted_reason, "double-oc #11");
  ctx.clock.t = T0 + 5 * MIN;
  const reset = await ctx.app.handle(new Request("https://pm.example/demote/reset", { method: "POST", headers: { authorization: PUSH } }));
  assert.equal(reset.status, 200);
  ctx.clock.t = T0 + 8 * MIN;
  await send(ctx.app, "issue_comment", ocEv(11, 3, PM_BOT, T0 + 8 * MIN));
  assert.equal((await status(ctx)).demoted_reason, null);
  // 解除の後の 2 件目は、解除の後の /oc どうしで判定する。
  await send(ctx.app, "issue_comment", ocEv(11, 4, VM, T0 + 9 * MIN));
  assert.equal((await status(ctx)).demoted_reason, "double-oc #11");
});

// 降格中は oc-pm digest も止める (dispatch と同じ降格ゲート)。解除の後は次の 24 時間で送る。
test("降格中は oc-pm digest を送らず would に数える。解除の後は送る", async () => {
  const clock = { t: T0 };
  const digestCalls = (calls: Call[]) => calls.filter((c) => c.method === "POST" && c.url.endsWith("/dispatches") && c.body?.client_payload?.kind === "digest");
  const dispatchOk = (c: Call) => (c.url.endsWith("/dispatches") ? j(null, 204) : undefined);
  const ctx = await configuredApp({ live: true, now: clock, handlers: [...writeHandlers, dispatchOk] });
  const tick = async (at: number) => {
    clock.t = at;
    await markFresh(ctx);
    await ctx.app.engine.tick();
  };
  for (const n of [11, 12]) await send(ctx.app, "issues", issuePayload(n));
  await tick(T0);
  clock.t = T0 + 1 * MIN;
  await send(ctx.app, "issue_comment", ocEv(11, 1, VM, T0 + 1 * MIN));
  clock.t = T0 + 2 * MIN;
  await send(ctx.app, "issue_comment", ocEv(11, 2, PM_BOT, T0 + 2 * MIN));
  assert.equal((await status(ctx)).demoted_reason, "double-oc #11");
  const before = (await status(ctx)).counters.wouldDispatchPm ?? 0;
  await tick(T0 + 24 * 60 * MIN);
  assert.equal(digestCalls(ctx.m.calls).length, 0, "降格中は digest を送らない");
  const s = await status(ctx);
  assert.ok(s.counters.wouldDispatchPm > before, "降格中の digest は wouldDispatchPm に数える");
  assert.ok((ctx.app.engine.status() as any).would_dispatch_pm.some((x: any) => x.kind === "digest" && x.ref === 0), "would_dispatch_pm に digest#0 が残る");
  assert.equal(s.counters.pmDispatched, 0);
  const reset = await ctx.app.handle(new Request("https://pm.example/demote/reset", { method: "POST", headers: { authorization: PUSH } }));
  assert.equal(reset.status, 200);
  await tick(T0 + 48 * 60 * MIN);
  assert.equal(digestCalls(ctx.m.calls).length, 1, "解除の後は次の 24 時間で digest を送る");
  assert.equal((await status(ctx)).mode_dispatch, "live");
});

test("shadow: would_launch と VM の /oc を 15 分の窓で突き合わせ、issue 番号だけを出す (recall・precision・vm_only・worker_only)", async () => {
  const ctx = await configuredApp({ handlers: writeHandlers });
  for (const n of [11, 12, 13]) await send(ctx.app, "issues", issuePayload(n));
  await markFresh(ctx);
  await ctx.app.engine.launch(await (ctx.app.engine as any).d.gh());
  ctx.clock.t = T0 + 5 * MIN;
  await send(ctx.app, "issue_comment", ocEv(11, 1, VM, T0 + 5 * MIN));
  const s = await status(ctx);
  assert.deepEqual(Object.keys(s.shadow).sort(), ["posts", "precision", "recall", "vm_only", "window_start", "worker_only"]);
  assert.equal(s.shadow.posts, 1);
  assert.equal(s.shadow.recall, 1);
  assert.equal(s.shadow.precision, 1 / 3);
  assert.deepEqual(s.shadow.vm_only, []);
  assert.deepEqual(s.shadow.worker_only, [12, 13]);
  assert.equal(s.shadow.window_start, new Date(T0 + 5 * MIN - 15 * MIN).toISOString());
  // 個票 (題名・本文) を出さない。
  assert.ok(!JSON.stringify(s.shadow).includes("[CI-"));
});

test("shadow: VM の投稿が 0 件の窓では recall を 100% とせず null にする。候補も無ければ precision は null", async () => {
  const ctx = await configuredApp({ handlers: writeHandlers });
  const s = await status(ctx);
  assert.equal(s.shadow.posts, 0);
  assert.equal(s.shadow.recall, null);
  assert.equal(s.shadow.precision, null);
  assert.deepEqual(s.shadow.vm_only, []);
});
