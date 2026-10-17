import { test } from "node:test";
import assert from "node:assert/strict";
import { configuredApp, j, markFresh, T0, type Call } from "./helpers.ts";
import { HUMAN, IMPL_BOT, at, commentEv, issueEv, outcomeBody, send, type Ctx } from "./pm_helpers.ts";
import { DEFAULT_WAKE_PER_H, DEFAULT_WAKE_REF_DAY_MAX, selectWake, type PmTarget } from "../src/pm.ts";

// 停止行の直接の再投入 (wake・CI-250)。停止行を Worker が /oc の 1 点スコープの再投入コメントで直接起こす。
// (a) 対象: 停止行 (stopped_report) のうち prio:critical・needs-user-input・open な子持ちは起こさない (ネガコン)。
// (b) 上限: 1 時間に WAKE_PER_H 件・同じ issue は 24 時間に WAKE_REF_DAY_MAX 件。oldest-first。

const comments = (calls: Call[]) => calls.filter((c) => c.method === "POST" && /\/issues\/\d+\/comments$/.test(c.url));
const wakeTo = (calls: Call[]) => comments(calls).filter((c) => String(c.body?.body ?? "").startsWith("/oc oc_actions_allow_write"));
const live = (clock = { t: T0 }, env: Record<string, string> = {}) =>
  configuredApp({
    live: true,
    now: clock,
    env,
    handlers: [(c) => (c.url.endsWith("/dispatches") ? j(null, 204) : undefined), (c) => (c.method === "POST" && /\/issues\/\d+\/comments$/.test(c.url) ? j({}, 201) : undefined)],
  });
const gh = async (ctx: Ctx) => await (ctx.app.engine as any).d.gh();
// wake が読むのは直近の plan (停止・保留・review-only) だけ。launch を通すと、停止行は通常の再着手 (picks) で先に投稿され、wake の検査にならない。
// そこで launch は呼ばず、停止していない plan を直接置く。
const planOk = (ctx: Ctx) => {
  (ctx.app.engine as any).meta.lastPlan = { at: new Date(T0).toISOString(), picks: [], phase: { review_only: false }, stop: undefined, blocked: undefined };
};
// 停止行 (run-outcome split) を 1 件作る。ラベルは既定で oc:no-pr。
const stopped = async (ctx: Ctx, n: number, o: { labels?: string[]; atMin?: number; body?: string; prio?: string } = {}) => {
  const labels = o.labels ?? ["oc:no-pr"];
  await send(ctx.app, "issues", issueEv(n, { labels, body: o.body }));
  await send(ctx.app, "issue_comment", commentEv(n, IMPL_BOT, outcomeBody("split"), at(o.atMin ?? 10)));
  // PM の応答後 (猶予の明け) にして stopped_report に回す。
  await send(ctx.app, "issue_comment", commentEv(n, HUMAN, "<!-- oc-pm-decision: rule=skip reversible=yes -->\nPM 判断", at(0)));
};

test("既定値: WAKE_PER_H は 24・WAKE_REF_DAY_MAX は 2 (config)", async () => {
  assert.equal(DEFAULT_WAKE_PER_H, 24);
  assert.equal(DEFAULT_WAKE_REF_DAY_MAX, 2);
});

test("ネガコン: prio:critical は wake しない (停止行でも起こさない)", () => {
  const now = 1_700_000_000_000;
  const tg = (ref: number, prio: PmTarget["prio"]): PmTarget => ({ kind: "stopped_report", ref, at: new Date(now).toISOString(), prio });
  const picked = selectWake(now, [tg(1, "critical"), tg(2, "normal")], [], { perH: 24, refDayMax: 2, excludeLabels: ["needs-user-input"], labelsOf: () => [] });
  assert.deepEqual(picked.map((x) => x.ref), [2], "critical の #1 は起こさない");
});

test("ネガコン: needs-user-input の停止行は wake しない (ラベルで除外)", () => {
  const now = 1_700_000_000_000;
  const tg = (ref: number): PmTarget => ({ kind: "stopped_report", ref, at: new Date(now).toISOString(), prio: "normal" });
  const labels: Record<number, string[]> = { 1: ["needs-user-input"], 2: [] };
  const picked = selectWake(now, [tg(1), tg(2)], [], { perH: 24, refDayMax: 2, excludeLabels: ["needs-user-input"], labelsOf: (n) => labels[n] ?? [] });
  assert.deepEqual(picked.map((x) => x.ref), [2]);
});

// 正の対照: 同じ経路で、素の停止行は 1 件起こす (ネガコンが空振りでないことの確認)。
test("正の対照: 素の停止行 (ラベル無し・子無し) は /oc で 1 件起こす", async () => {
  const ctx = await live();
  await stopped(ctx, 600, { labels: [] });
  await markFresh(ctx);
  planOk(ctx);
  await ctx.app.engine.wakeStopped(await gh(ctx));
  assert.equal(wakeTo(ctx.m.calls).length, 1, "素の停止行は起こす");
  assert.equal(wakeTo(ctx.m.calls)[0].url.includes("/issues/600/comments"), true);
});

test("ネガコン: 子持ちの親は wake しない (detectPm が停止行から外す)", async () => {
  const ctx = await live();
  await stopped(ctx, 610, { labels: [] });
  await send(ctx.app, "issues", issueEv(611, { body: "親: #610" })); // 610 の open な子
  await markFresh(ctx);
  planOk(ctx);
  await ctx.app.engine.wakeStopped(await gh(ctx));
  assert.equal(wakeTo(ctx.m.calls).filter((c) => c.url.includes("/issues/610/")).length, 0, "子持ち (#610) は起こさない");
});

test("ネガコン (エンジン): needs-user-input の停止行は /oc で起こさない", async () => {
  const ctx = await live();
  await stopped(ctx, 630, { labels: ["needs-user-input"] });
  await markFresh(ctx);
  planOk(ctx);
  await ctx.app.engine.wakeStopped(await gh(ctx));
  assert.equal(wakeTo(ctx.m.calls).filter((c) => c.url.includes("/issues/630/")).length, 0);
});

// prio:critical の停止行は launch の通常の再着手 (ready・relaunch) では起こり得るので、wake だけの投稿数を launch の前後の差で数える。
test("ネガコン (エンジン): prio:critical の停止行は wake では /oc を投稿しない (launch の再着手とは別)", async () => {
  const ctx = await live();
  await stopped(ctx, 631, { labels: ["prio:critical"] });
  await markFresh(ctx);
  planOk(ctx);
  const before = wakeTo(ctx.m.calls).length;
  await ctx.app.engine.wakeStopped(await gh(ctx));
  assert.equal(wakeTo(ctx.m.calls).length - before, 0, "wake は prio:critical を起こさない");
});

test("上限 (a): 同じ issue は 24 時間に WAKE_REF_DAY_MAX 件まで。3 件目は起こさない", () => {
  const now = 1_700_000_000_000;
  const tg = (ref: number): PmTarget => ({ kind: "stopped_report", ref, at: new Date(now).toISOString(), prio: "normal" });
  const hist = [{ ref: 1, at: now - 10 * 60_000 }, { ref: 1, at: now - 70 * 60_000 }];
  const capped = selectWake(now, [tg(1)], hist, { perH: 24, refDayMax: 2, excludeLabels: ["needs-user-input"], labelsOf: () => [] });
  assert.deepEqual(capped, [], "24 時間に 2 件で止まる");
});

test("上限 (b): 1 時間に WAKE_PER_H 件まで。oldest-first (停止の古い順)", () => {
  const now = 1_700_000_000_000;
  const at = (min: number): string => new Date(now - min * 60_000).toISOString();
  const tg = (ref: number, min: number): PmTarget => ({ kind: "stopped_report", ref, at: at(min), prio: "normal" });
  // 新しい (#3, 5 分前) / 古い (#2, 60 分前) / 中 (#1, 30 分前)。枠は 2 件。
  const picked = selectWake(now, [tg(3, 5), tg(2, 60), tg(1, 30)], [], { perH: 2, refDayMax: 2, excludeLabels: ["needs-user-input"], labelsOf: () => [] });
  assert.deepEqual(picked.map((x) => x.ref), [2, 1]);
});

test("上限 (c): 1 時間の枠を使い切ったら残りは起こさない (同じ tick で超えない)", () => {
  const now = 1_700_000_000_000;
  const tg = (ref: number): PmTarget => ({ kind: "stopped_report", ref, at: new Date(now).toISOString(), prio: "normal" });
  const hist = [{ ref: 9, at: now - 5 * 60_000 }];
  const picked = selectWake(now, [tg(1), tg(2), tg(3)], hist, { perH: 2, refDayMax: 2, excludeLabels: ["needs-user-input"], labelsOf: () => [] });
  assert.equal(picked.length, 1, "履歴の 1 件を足して 2 件に達したら止まる");
});

test("停止中 (plan.stop・blocked・review-only) は wake しない: launch と同じ停止条件", async () => {
  for (const stop of [{ stop: "rate-guard" }, { blocked: "no-import" }, { phase: { review_only: true } }]) {
    const ctx = await live();
    await stopped(ctx, 650, { labels: [] });
    await markFresh(ctx);
    const plan = { at: new Date(T0).toISOString(), picks: [], phase: { review_only: false }, stop: undefined, blocked: undefined, ...stop };
    (ctx.app.engine as any).meta.lastPlan = plan;
    await ctx.app.engine.wakeStopped(await gh(ctx));
    assert.equal(wakeTo(ctx.m.calls).filter((c) => c.url.includes("/issues/650/")).length, 0, `停止 (${JSON.stringify(stop)}) の間は起こさない`);
  }
});

test("同期が古い間は wake しない (launch と同じ条件。古い一覧で誤った対象を起こさない)", async () => {
  const ctx = await live();
  await stopped(ctx, 640, { labels: [] });
  await markFresh(ctx);
  planOk(ctx);
  (ctx.app.engine as any).meta.fullSyncAt = undefined; // 同期が古い (fresh=false) にする
  const before = wakeTo(ctx.m.calls).length;
  await ctx.app.engine.wakeStopped(await gh(ctx));
  assert.equal(wakeTo(ctx.m.calls).length - before, 0, "同期が古い間は起こさない");
});

test("dry-run (LIVE_LAUNCH 無し): /oc は投稿せず wouldWake だけを数える", async () => {
  const clock = { t: T0 };
  const ctx = await configuredApp({ live: false, now: clock, env: {}, handlers: [] });
  await stopped(ctx, 620);
  await markFresh(ctx);
  await ctx.app.engine.wakeStopped(await gh(ctx));
  assert.equal(wakeTo(ctx.m.calls).length, 0);
});
