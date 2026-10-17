import { test } from "node:test";
import assert from "node:assert/strict";
import { configuredApp, issuePayload, markFresh, send, T0, type Call } from "./helpers.ts";

// 降格の時限復帰 (CI-251): 降格から DEMOTE_AUTO_LIFT_MS (60 分) を超えたら、tick が人の操作なしで解除する。

const MIN = 60_000;
const VM = "pycabbage";
const PM_BOT = "oc-pm-for-signature-studio[bot]";
const R = "/repos/signature-studio/signature-studio-dev";
const PUSH = "Bearer ghp_valid_push_token_x";
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
const writeHandlers = [
  (c: Call) => (c.method === "POST" && /\/issues\/\d+\/comments$/.test(c.url) ? json({ html_url: "x" }, 201) : undefined),
  (c: Call) => (c.method === "GET" && c.url.endsWith(R) && c.auth === PUSH ? json({ permissions: { push: true } }) : undefined),
  (c: Call) => (c.url.endsWith("/dispatches") ? new Response(null, { status: 204 }) : undefined),
];

const ocEv = (n: number, id: number, login: string, at: number) => ({
  action: "created",
  repository: { full_name: "signature-studio/signature-studio-dev" },
  issue: { number: n },
  comment: { id, user: { login }, body: "/oc\noc_artifacts: fl-win64", created_at: new Date(at).toISOString() },
});

const status = async (ctx: { app: { handle(r: Request): Promise<Response> } }) => (await (await ctx.app.handle(new Request("https://pm.example/status"))).json()) as any;
const restores = (ctx: any) => (ctx.app.engine as any).log.filter((l: any) => l.kind === "restore");

// 2 件の /oc で issue 11 を降格させる。降格の時刻 (meta.demoted.at) を返す。
async function demoteAt(ctx: any, at: number): Promise<number> {
  ctx.clock.t = at;
  for (const n of [11, 12]) await send(ctx.app, "issues", issuePayload(n));
  await send(ctx.app, "issue_comment", ocEv(11, 1, VM, at));
  await send(ctx.app, "issue_comment", ocEv(11, 2, PM_BOT, at + 1 * MIN));
  assert.equal((await status(ctx)).demoted_reason, "double-oc #11");
  return Date.parse((ctx.app.engine as any).meta.demoted.at);
}

async function tickAt(ctx: any, at: number) {
  ctx.clock.t = at;
  await markFresh(ctx);
  await ctx.app.engine.tick();
}

test("時限復帰 (ネガ・a): 降格から 60 分以内の tick では解除しない", async () => {
  const ctx = await configuredApp({ live: true, now: { t: T0 }, handlers: writeHandlers });
  const at = await demoteAt(ctx, T0 + 1 * MIN);
  await tickAt(ctx, at + 59 * MIN);
  const s = await status(ctx);
  assert.equal(s.demoted_reason, "double-oc #11");
  assert.equal(s.counters.restored, 0);
  assert.equal(s.mode_launch, "dry-run");
  assert.equal(restores(ctx).length, 0);
});

test("時限復帰 (ネガ・境界): 降格からちょうど 60 分の tick ではまだ解除しない (超えたときだけ解除)", async () => {
  const ctx = await configuredApp({ live: true, now: { t: T0 }, handlers: writeHandlers });
  const at = await demoteAt(ctx, T0 + 1 * MIN);
  await tickAt(ctx, at + 60 * MIN);
  assert.equal((await status(ctx)).demoted_reason, "double-oc #11");
  assert.equal(restores(ctx).length, 0);
});

test("時限復帰 (正例・b・c): 降格から 60 分を超えた tick が解除し、restored が増え、log の note は auto-stale", async () => {
  const ctx = await configuredApp({ live: true, now: { t: T0 }, handlers: writeHandlers });
  const at = await demoteAt(ctx, T0 + 1 * MIN);
  await tickAt(ctx, at + 61 * MIN);
  const s = await status(ctx);
  assert.equal(s.demoted_reason, null);
  assert.equal(s.mode_launch, "live");
  assert.equal(s.counters.restored, 1);
  assert.equal(restores(ctx).length, 1);
  assert.equal(restores(ctx)[0].note, "auto-stale");
});

test("時限復帰 (ネガ・手動): 手動の /demote/reset の note は manual のまま", async () => {
  const ctx = await configuredApp({ live: true, now: { t: T0 }, handlers: writeHandlers });
  await demoteAt(ctx, T0 + 1 * MIN);
  const reset = await ctx.app.handle(new Request("https://pm.example/demote/reset", { method: "POST", headers: { authorization: PUSH } }));
  assert.equal(reset.status, 200);
  assert.equal(restores(ctx).at(-1).note, "manual");
});
