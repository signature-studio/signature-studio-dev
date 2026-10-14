import { test } from "node:test";
import assert from "node:assert/strict";
import { configuredApp, j, markFresh, T0, type Call } from "./helpers.ts";
import { HUMAN, IMPL_BOT, OUTSIDER, type Author, at, commentEv, issueEv, prEv, send, type Ctx } from "./pm_helpers.ts";
import { parentNumbers, refsOnlyNumbers } from "../src/refs.ts";

const pmCalls = (calls: Call[]) => calls.filter((c) => c.method === "POST" && c.url.endsWith("/dispatches") && c.body?.event_type === "oc-pm");
const sendAll = async (ctx: Ctx, items: Array<[string, unknown]>) => {
  for (const [ev, p] of items) assert.equal((await send(ctx.app, ev, p)).status, 202);
};
const live = (clock = { t: T0 }) => configuredApp({ live: true, now: clock, handlers: [(c) => (c.url.endsWith("/dispatches") ? j(null, 204) : undefined)] });
const targets = (ctx: Ctx) => ctx.app.engine.detectPmTargets().map((t) => `${t.kind}#${t.ref}`);
// merge 済みの PR (closed + merged_at)。本文が閉じキーワードや Refs を持つかで対象が決まる。
const merged = (n: number, body: string, min = 5, author: Author = IMPL_BOT) => {
  const ev = prEv(n, { body, author, at: at(min) });
  return { ...ev, action: "closed", pull_request: { ...ev.pull_request, state: "closed", merged_at: at(min), updated_at: at(min) } };
};
const parent = (n: number, author: Author = HUMAN) => issueEv(n, { author, title: `[CI-${n}] 親`, at: at(1) });
const child = (n: number, p: number, state = "open") => issueEv(n, { body: `親: #${p}\n\n## 背景`, state, at: at(2) });

test("検出 refs_orphan: Refs のみで merge された PR の親 N が open で、open の子が無い", async () => {
  const ctx = await configuredApp();
  await sendAll(ctx, [
    ["issues", parent(100)],
    ["pull_request", merged(10, "## 概要\n\nRefs #100\n")],
  ]);
  assert.deepEqual(targets(ctx), ["refs_orphan#100"]);
});

test("ネガコン (a): 閉じキーワード (Closes / Fixes / Resolves) がある PR は検出しない", async () => {
  const ctx = await configuredApp();
  await sendAll(ctx, [
    ["issues", parent(101)],
    ["issues", parent(102)],
    ["issues", parent(103)],
    ["pull_request", merged(11, "Closes #101")],
    ["pull_request", merged(12, "Refs #102\n\nCloses #103")],
    ["pull_request", merged(13, "Refs #103\nFixes #104")],
    ["pull_request", merged(14, "Refs #102\nresolves: #105")],
  ]);
  assert.deepEqual(targets(ctx), []);
});

test("ネガコン (b): N が closed なら検出しない。merge されていない closed の PR や open の PR も対象外", async () => {
  const ctx = await configuredApp();
  await sendAll(ctx, [
    ["issues", parent(110, HUMAN)],
    ["issues", issueEv(111, { state: "closed", author: HUMAN, at: at(1) })],
    ["pull_request", merged(20, "Refs #110")],
    ["pull_request", merged(21, "Refs #111")],
    ["pull_request", { ...merged(22, "Refs #112"), pull_request: { ...prEv(22, { body: "Refs #112", at: at(5) }).pull_request, state: "closed", merged_at: null } }],
    ["pull_request", prEv(23, { body: "Refs #113", at: at(5) })],
  ]);
  assert.deepEqual(targets(ctx), ["refs_orphan#110"], "対照: N=110 だけ (111 は closed、112・113 は merge されていない)");
  await sendAll(ctx, [["issues", parent(112)], ["issues", parent(113)]]);
  assert.deepEqual(targets(ctx), ["refs_orphan#110"], "merge されていない PR の N は、N が open でも対象外");
});

test("ネガコン (c): open の子 (本文の親: #N) があれば検出しない。closed の子は数えない", async () => {
  const ctx = await configuredApp();
  await sendAll(ctx, [
    ["issues", parent(120)],
    ["issues", child(121, 120)],
    ["pull_request", merged(30, "Refs #120")],
    ["issues", parent(122)],
    ["issues", child(123, 122, "closed")],
    ["pull_request", merged(31, "Refs #122")],
    ["issues", parent(124)],
    ["issues", issueEv(125, { body: "親: #1240\n", author: HUMAN, at: at(2) })],
    ["pull_request", merged(32, "Refs #124")],
  ]);
  assert.deepEqual(targets(ctx), ["refs_orphan#122", "refs_orphan#124"], "120 だけ子があるので除外。124 は親: #1240 で別の番号");
});

test("ネガコン (f): 本文に N 以外の #M が併記されていても対象は Refs の N だけ", async () => {
  const ctx = await configuredApp();
  await sendAll(ctx, [
    ["issues", parent(130)],
    ["issues", parent(131)],
    ["issues", parent(132)],
    ["pull_request", merged(40, "## 関連\n\n- #131 と #132 を参照\n- Refs #130\n")],
  ]);
  assert.deepEqual(targets(ctx), ["refs_orphan#130"]);
});

test("ネガコン (h): 起票者が許可外 (NONE の人) の親は送らない。OWNER の親は対象", async () => {
  const ctx = await configuredApp();
  await sendAll(ctx, [
    ["issues", parent(140, OUTSIDER)],
    ["issues", parent(141, HUMAN)],
    ["pull_request", merged(41, "Refs #140\nRefs #141")],
  ]);
  assert.deepEqual(targets(ctx), ["refs_orphan#141"]);
});

test("送信: refs_orphan の payload は kind と ref だけ。本文の文字列は現れない", async () => {
  const ctx = await live();
  const evil = '{"kind":"x","ref":99999999} Refs #7 \\" supply';
  await sendAll(ctx, [
    ["issues", parent(150)],
    ["pull_request", merged(42, `Refs #150 ${evil}`)],
  ]);
  await markFresh(ctx);
  await ctx.app.engine.pmDispatch(await (ctx.app.engine as any).d.gh());
  const d = pmCalls(ctx.m.calls);
  assert.equal(d.length, 1);
  assert.deepEqual(d[0].body, { event_type: "oc-pm", client_payload: { kind: "refs_orphan", ref: 150 } });
});

test("ネガコン (d): refs_orphan は 1 日 10 件まで。11 件目は送らない (全体の上限に加えて効く)", async () => {
  const ctx = await live();
  const nums = Array.from({ length: 11 }, (_, i) => 200 + i);
  for (const n of nums) await sendAll(ctx, [["issues", parent(n)], ["pull_request", merged(n + 100, `Refs #${n}`)]]);
  await markFresh(ctx);
  await ctx.app.engine.pmDispatch(await (ctx.app.engine as any).d.gh());
  const sent = pmCalls(ctx.m.calls).map((c) => c.body.client_payload.ref);
  assert.deepEqual(sent, nums.slice(0, 10));
  assert.ok(!sent.includes(210), "11 件目は送らない");
});

test("ネガコン (e): 同じ N は 24 時間に 1 回まで。24 時間たてば送る", async () => {
  const clock = { t: T0 };
  const ctx = await live(clock);
  await sendAll(ctx, [["issues", parent(160)], ["pull_request", merged(50, "Refs #160")]]);
  const gh = await (ctx.app.engine as any).d.gh();
  const step = async (addMin: number) => {
    clock.t += addMin * 60_000;
    await markFresh(ctx);
    await ctx.app.engine.pmDispatch(gh);
    return pmCalls(ctx.m.calls).length;
  };
  assert.equal(await step(0), 1);
  assert.equal(await step(60), 1, "60 分後も送らない (通常の oc-pm の 60 分より長く抑える)");
  assert.equal(await step(60 * 22), 1, "23 時間後");
  assert.equal(await step(59), 1, "23 時間 59 分後");
  assert.equal(await step(1), 2, "24 時間後は送る");
});

test("ネガコン (g): dry-run では fetch の POST が 0 回。/status の would_dispatch_pm に kind と ref だけ記録する", async () => {
  const ctx = await configuredApp();
  await sendAll(ctx, [["issues", parent(170)], ["pull_request", merged(60, "Refs #170")]]);
  await markFresh(ctx);
  const r = await ctx.app.engine.pmDispatch(await (ctx.app.engine as any).d.gh());
  assert.deepEqual(r.would.map((t) => `${t.kind}#${t.ref}`), ["refs_orphan#170"]);
  assert.equal(pmCalls(ctx.m.calls).length, 0);
  const s = ctx.app.engine.status() as any;
  assert.deepEqual(s.would_dispatch_pm.map((x: any) => `${x.kind}#${x.ref}`), ["refs_orphan#170"]);
  assert.equal(s.pm_detected.refs_orphan, 1);
});

test("解析: Refs の番号は閉じキーワードの無い本文だけ。親は行頭の『親:』の番号", () => {
  assert.deepEqual(refsOnlyNumbers("Refs #1, Refs #2\n関連 #3"), [1, 2]);
  assert.deepEqual(refsOnlyNumbers("refs: #7"), [7]);
  assert.deepEqual(refsOnlyNumbers("prefs #8 Refs #12345678"), []);
  assert.deepEqual(refsOnlyNumbers("Refs #5\nCloses #6"), []);
  assert.deepEqual(refsOnlyNumbers("closes #6 Refs #5"), []);
  assert.deepEqual(parentNumbers("親: #2319\n\n本文 #5"), [2319]);
  assert.deepEqual(parentNumbers("本文\r\n親: #10、#11\r\n"), [10, 11]);
  assert.deepEqual(parentNumbers("親 #30\n親: なし"), []);
});
