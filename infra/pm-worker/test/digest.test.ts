import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { configuredApp, issuePayload, j, markFresh, send, T0, type Call } from "./helpers.ts";
import type { Ctx } from "./pm_helpers.ts";

// 日次のダイジェスト (CI-70)。alarm の tick ごとに呼ばれ、送るのは 24 時間に 1 回の oc-pm kind=digest ref=0 だけ。
const H = 3_600_000;
const digestCalls = (calls: Call[]) =>
  calls.filter((c) => c.method === "POST" && c.url.endsWith("/dispatches") && c.body?.event_type === "oc-pm" && c.body?.client_payload?.kind === "digest");
const ok = (c: Call) => (c.url.endsWith("/dispatches") ? j(null, 204) : undefined);
const live = (clock: { t: number }) => configuredApp({ live: true, now: clock, handlers: [ok] });
// 同期を新しく保ったまま 1 tick 進める (reconcile は走らせず、watchdog・launch・pm 送信・digest の順で回す)。
const tickAfter = async (ctx: Ctx, clock: { t: number }, ms: number) => {
  clock.t += ms;
  await markFresh(ctx);
  await ctx.app.engine.tick();
};

test("digest: 初回の tick は起点だけ置き、24 時間後に oc-pm kind=digest ref=0 を 1 回送る", async () => {
  const clock = { t: T0 };
  const ctx = await live(clock);
  await tickAfter(ctx, clock, 0);
  assert.equal(digestCalls(ctx.m.calls).length, 0, "初回は起こさない");
  await tickAfter(ctx, clock, 24 * H - 60_000);
  assert.equal(digestCalls(ctx.m.calls).length, 0, "24 時間たつ前は送らない");
  await tickAfter(ctx, clock, 60_000);
  const d = digestCalls(ctx.m.calls);
  assert.equal(d.length, 1);
  assert.deepEqual(d[0].body, { event_type: "oc-pm", client_payload: { kind: "digest", ref: 0 } });
  assert.deepEqual(Object.keys(d[0].body.client_payload), ["kind", "ref"]);
  assert.equal(d[0].auth, "Bearer ghs_installation_token_value");
  const s = ctx.app.engine.status() as any;
  assert.equal(s.counters.pmDispatched, 1);
  assert.equal(s.last_digest_at, new Date(T0 + 24 * H).toISOString());
});

test("ネガコン (a): 24 時間以内の 2 回目の digest は送らない。24 時間たったら次を送る", async () => {
  const clock = { t: T0 };
  const ctx = await live(clock);
  await tickAfter(ctx, clock, 0);
  await tickAfter(ctx, clock, 24 * H);
  assert.equal(digestCalls(ctx.m.calls).length, 1);
  for (let i = 0; i < 23; i++) await tickAfter(ctx, clock, H);
  assert.equal(digestCalls(ctx.m.calls).length, 1, "23 時間後もまだ 1 件");
  await tickAfter(ctx, clock, H);
  assert.equal(digestCalls(ctx.m.calls).length, 2, "24 時間後に次の 1 件");
});

test("ネガコン (b): 毎分の tick が 3 日続いても digest は 24 時間に 1 件を超えない", async () => {
  const clock = { t: T0 };
  const ctx = await live(clock);
  await tickAfter(ctx, clock, 0);
  const sentAt: number[] = [];
  let seen = 0;
  for (let i = 0; i < 72 * 60; i++) {
    await tickAfter(ctx, clock, 60_000);
    const n = digestCalls(ctx.m.calls).length;
    if (n > seen) sentAt.push(clock.t);
    seen = n;
  }
  assert.equal(sentAt.length, 3, "起点から 72 時間で 3 件 (24・48・72 時間目)");
  for (let i = 1; i < sentAt.length; i++) assert.ok(sentAt[i] - sentAt[i - 1] >= 24 * H, "24 時間以内に 2 件送らない");
  assert.equal((ctx.app.engine.status() as any).counters.pmDispatched, 3);
});

test("dry-run: digest は POST せず、記録 (would_dispatch_pm・counters.wouldDispatchPm・last_digest_at) だけ残す", async () => {
  const clock = { t: T0 };
  const ctx = await configuredApp({ now: clock });
  await tickAfter(ctx, clock, 0);
  await tickAfter(ctx, clock, 24 * H);
  const repoPosts = ctx.m.calls.filter((c) => c.method === "POST" && c.url.includes("/repos/"));
  assert.equal(repoPosts.length, 0, "dry-run は GitHub の repos に書かない");
  const s = ctx.app.engine.status() as any;
  assert.equal(s.mode, "dry-run");
  assert.deepEqual(s.would_dispatch_pm.map((x: any) => `${x.kind}#${x.ref}`), ["digest#0"]);
  assert.equal(s.counters.wouldDispatchPm, 1);
  assert.equal(s.counters.pmDispatched, 0);
  assert.ok(s.last_digest_at);
  const pub = await (await ctx.app.handle(new Request("https://pm.example/status"))).json();
  assert.ok(!("would_dispatch_pm" in (pub as any)), "公開の /status は送信の個票を出さない");
});

test("送信に失敗しても、その試行で 24 時間の枠を使う (毎分叩き直さない)", async () => {
  const clock = { t: T0 };
  const ctx = await configuredApp({
    live: true,
    now: clock,
    handlers: [(c) => (c.url.endsWith("/dispatches") ? (c.body?.client_payload?.kind === "digest" ? j({}, 500) : j(null, 204)) : undefined)],
  });
  await tickAfter(ctx, clock, 0);
  await tickAfter(ctx, clock, 24 * H);
  assert.equal(digestCalls(ctx.m.calls).length, 1);
  assert.equal((ctx.app.engine.status() as any).counters.pmDispatched, 0);
  assert.ok((ctx.app.engine.status() as any).log.some((l: any) => l.kind === "error" && String(l.note).includes("digest")));
  await tickAfter(ctx, clock, 60_000);
  await tickAfter(ctx, clock, H);
  assert.equal(digestCalls(ctx.m.calls).length, 1, "1 時間後にも叩き直さない");
  await tickAfter(ctx, clock, 23 * H);
  assert.equal(digestCalls(ctx.m.calls).length, 2, "24 時間後に次の試行");
});

test("ネガコン (e): 日次 digest の rolling issue は plan() の picks・ready に入らない (通常の issue は従来どおり着手)", async () => {
  const clock = { t: T0 };
  const ctx = await configuredApp({ now: clock });
  assert.equal((await send(ctx.app, "issues", issuePayload(70, { title: "[CI-70] 自律運転ダイジェスト (rolling)" }))).status, 202);
  assert.equal((await send(ctx.app, "issues", issuePayload(71, { title: "[CI-71] 通常の issue" }))).status, 202);
  await markFresh(ctx);
  const p = ctx.app.engine.plan();
  assert.deepEqual(p.picks.map((x) => x.n), [71]);
  assert.deepEqual(p.rows.ready, [71]);
  assert.ok(!p.picks.some((x) => x.n === 70));
});

test("ネガコン (d): config.ts に Team プランの更新日・課金の設定が無い", () => {
  const src = readFileSync(new URL("../src/config.ts", import.meta.url), "utf8");
  assert.doesNotMatch(src, /team|2026-11-13/i);
});
