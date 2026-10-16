import { test } from "node:test";
import assert from "node:assert/strict";
import { configuredApp, j, markFresh, T0, type Call } from "./helpers.ts";
import { HUMAN, IMPL_BOT, PM_BOT, at, commentEv, issueEv, outcomeBody, prEv, send, type Ctx } from "./pm_helpers.ts";
import { DEFAULT_STOPPED_INTAKE_PER_H, STOPPED_REF_DAY_MAX, selectDispatch, type HistoryEntry, type PmTarget } from "../src/pm.ts";

// 停止行 (run-outcome が stop / split) を oc-pm の判断キューへ回す (CI-239・#5722)。
// (a) 検出: 停止行を oldest-first で回す。no_pr と二重に送らない。実行中・PR あり・親・保留は回さない。
// (b) 送信: 1 時間の上限 (STOPPED_INTAKE_PER_H。既定 24) と、同じ issue 24 時間 3 件の上限を守る (ネガコン)。
// (c) 再投入の判断は oc-pm が行う: 検出・送信の経路で /oc は投稿しない (ラベルの付け外しでも変わらない)。

const pmCalls = (calls: Call[]) => calls.filter((c) => c.method === "POST" && c.url.endsWith("/dispatches") && c.body?.event_type === "oc-pm");
const payloads = (ctx: Ctx) => pmCalls(ctx.m.calls).map((c) => c.body.client_payload);
const ocPosts = (ctx: Ctx) => ctx.m.calls.filter((c) => c.method === "POST" && /\/issues\/\d+\/comments$/.test(c.url));
const live = (clock = { t: T0 }, env: Record<string, string> = {}) =>
  configuredApp({
    live: true,
    now: clock,
    env,
    handlers: [(c) => (c.url.endsWith("/dispatches") ? j(null, 204) : undefined), (c) => (c.method === "POST" && /\/issues\/\d+\/comments$/.test(c.url) ? j({}, 201) : undefined)],
  });
const gh = async (ctx: Ctx) => await (ctx.app.engine as any).d.gh();
const answer = (n: number, min: number) => ["issue_comment", commentEv(n, HUMAN, "<!-- oc-pm-decision: rule=skip reversible=yes -->\nPM 判断", at(min))] as [string, unknown];
const stopped = async (ctx: Ctx, n: number, o: { labels?: string[]; reason?: string; atMin?: number; answerMin?: number; launchMin?: number; title?: string; body?: string; author?: typeof HUMAN } = {}) => {
  await send(ctx.app, "issues", issueEv(n, { labels: o.labels ?? ["oc:no-pr"], title: o.title, body: o.body, author: o.author }));
  await send(ctx.app, "issue_comment", commentEv(n, IMPL_BOT, outcomeBody(o.reason ?? "split"), at(o.atMin ?? 10)));
  if (o.answerMin !== undefined) await send(ctx.app, ...answer(n, o.answerMin));
  if (o.launchMin !== undefined) await send(ctx.app, "issue_comment", commentEv(n, PM_BOT, "/oc oc_actions_allow_write\noc_artifacts: fl-win64", at(o.launchMin)));
};

test("検出 (a): oc:no-pr の未回答は no_pr のまま (二重に送らない)。回答済み (猶予の外) は stopped_report に回す", async () => {
  const ctx = await live();
  await stopped(ctx, 501); // 未回答 → no_pr
  await stopped(ctx, 502, { answerMin: 20 }); // 回答済み・100 分前 → stopped_report
  const t = ctx.app.engine.detectPmTargets();
  assert.deepEqual(
    t.map((x) => `${x.kind}#${x.ref}`),
    ["no_pr#501", "stopped_report#502"],
  );
  assert.equal(t.find((x) => x.kind === "stopped_report")?.at, at(10), "根拠は停止の時刻");
});

test("検出: PM の回答から猶予 (PM_INTAKE_GRACE_MS) の内側なら stopped_report に回さず、ちょうど明けたら回す", async () => {
  const inside = await live();
  await stopped(inside, 503, { answerMin: 61 }); // 回答は 59 分前 (猶予の内)
  assert.deepEqual(inside.app.engine.detectPmTargets(), []);
  const edge = await live();
  await stopped(edge, 504, { answerMin: 60 }); // 回答は 60 分前 (猶予の明け)
  assert.deepEqual(edge.app.engine.detectPmTargets().map((x) => `${x.kind}#${x.ref}`), ["stopped_report#504"]);
});

test("検出: 停止の後に /oc を投稿済み (実行中)・open PR あり・open な子を持つ親・保留ラベルは回さない", async () => {
  const ctx = await live();
  await stopped(ctx, 510, { answerMin: 20, launchMin: 30 }); // 停止 (10) の後に /oc (30)
  await stopped(ctx, 511, { answerMin: 20 });
  await send(ctx.app, "pull_request", prEv(911, { body: "Closes #511" }));
  await stopped(ctx, 512, { answerMin: 20, body: "親: #1" });
  await send(ctx.app, "issues", issueEv(513, { body: "親: #512" })); // open な子
  await stopped(ctx, 514, { labels: ["oc:no-pr", "needs-user-input"], answerMin: 20 });
  await stopped(ctx, 515, { labels: ["oc:hold"], answerMin: 20 });
  assert.deepEqual(ctx.app.engine.detectPmTargets(), []);
});

test("検出: reason が stop でも split でもない停止行 (artifact など) は stopped_report に回さない。closed も回さない", async () => {
  const ctx = await live();
  await stopped(ctx, 520, { reason: "artifact", answerMin: 20 });
  await send(ctx.app, "issues", issueEv(521, { labels: [], state: "closed" }));
  await send(ctx.app, "issue_comment", commentEv(521, IMPL_BOT, outcomeBody("split"), at(10)));
  assert.deepEqual(ctx.app.engine.detectPmTargets(), []);
});

test("検出: oldest-first (停止の古い順)。ref の大小では並べない", async () => {
  const ctx = await live();
  await stopped(ctx, 530, { atMin: 30, answerMin: 40 }); // 新しい
  await stopped(ctx, 531, { atMin: 5, answerMin: 40 }); // 古い (ref は大きい)
  await stopped(ctx, 532, { atMin: 20, answerMin: 40 });
  assert.deepEqual(
    ctx.app.engine.detectPmTargets().filter((x) => x.kind === "stopped_report").map((x) => x.ref),
    [531, 532, 530],
  );
});

test("送信 (b): 1 時間の上限 (STOPPED_INTAKE_PER_H) を守り、古い停止から送る。既定は 24", async () => {
  const ctx = await live({ t: T0 }, { STOPPED_INTAKE_PER_H: "2" });
  await stopped(ctx, 540, { atMin: 30, answerMin: 40 }); // 新しい
  await stopped(ctx, 541, { atMin: 5, answerMin: 40 }); // 古い
  await stopped(ctx, 542, { atMin: 20, answerMin: 40 });
  await markFresh(ctx);
  await ctx.app.engine.pmDispatch(await gh(ctx));
  assert.deepEqual(payloads(ctx), [
    { kind: "stopped_report", ref: 541 },
    { kind: "stopped_report", ref: 542 },
  ]);
  assert.equal(DEFAULT_STOPPED_INTAKE_PER_H, 24);
});

test("送信 (b ネガコン): 同じ issue は 24 時間に 3 件まで。4 件目は送らない (2 連続の stop でも item cap で止まる)", async () => {
  const clock = { t: T0 };
  const ctx = await live(clock);
  await stopped(ctx, 550, { answerMin: 20 });
  const step = async (addMin: number) => {
    clock.t += addMin * 60_000;
    await markFresh(ctx);
    await ctx.app.engine.pmDispatch(await gh(ctx));
    return payloads(ctx).length;
  };
  assert.equal(await step(0), 1, "1 件目");
  assert.equal(await step(61), 2, "61 分後 (同じ (kind, ref) は 60 分に 1 回)");
  assert.equal(await step(61), 3, "122 分後 (3 件目)");
  assert.equal(await step(61), 3, "183 分後。停止行の issue 上限 (同じ issue に 24 時間で STOPPED_REF_DAY_MAX = 3 件) で止まる");
  clock.t += 24 * 3_600_000;
  assert.equal(await step(0), 4, "24 時間たてば送る");
});

test("ネガコン: 停止行の検出・送信の経路では /oc を投稿しない (再投入の判断は oc-pm が行う)", async () => {
  const ctx = await live();
  await stopped(ctx, 560, { answerMin: 20 });
  await markFresh(ctx);
  await ctx.app.engine.pmDispatch(await gh(ctx));
  assert.deepEqual(payloads(ctx), [{ kind: "stopped_report", ref: 560 }]);
  assert.equal(ocPosts(ctx).length, 0, "intake は再投入しない (/oc は投稿しない)");
});

test("ネガコン: 送信の上限は intake 自身の履歴で決まる (ラベルの付け外し・PM の応答では消えない)", async () => {
  const clock = { t: T0 };
  const ctx = await live(clock);
  await stopped(ctx, 570, { answerMin: 20 });
  await markFresh(ctx);
  await ctx.app.engine.pmDispatch(await gh(ctx));
  assert.equal(payloads(ctx).length, 1);
  // ラベルを外して付け直しても、送信の記録 (履歴) は変わらない: 60 分以内は再送しない。
  await send(ctx.app, "issues", issueEv(570, { labels: [], action: "unlabeled", label: "oc:no-pr" }));
  await send(ctx.app, "issues", issueEv(570, { labels: ["oc:no-pr"], action: "labeled", label: "oc:no-pr" }));
  clock.t += 30 * 60_000;
  await markFresh(ctx);
  await ctx.app.engine.pmDispatch(await gh(ctx));
  assert.equal(payloads(ctx).length, 1, "60 分以内は同じ (kind, ref) を再送しない");
});

test("単体: selectDispatch の枠 (停止行の 1 時間の上限・同じ issue の 24 時間の上限)", () => {
  const now = 1_700_000_000_000;
  const tg = (ref: number): PmTarget => ({ kind: "stopped_report", ref, at: new Date(now).toISOString(), prio: "normal" });
  const h = (ref: number, minAgo: number): HistoryEntry => ({ kind: "stopped_report", ref, at: now - minAgo * 60_000 });
  assert.equal(STOPPED_REF_DAY_MAX, 3);
  // 同じ issue を 3 件送っていれば、4 件目は送らない (24 時間の窓)。
  const capped = selectDispatch(now, [tg(1)], [h(1, 10), h(1, 70), h(1, 130)]);
  assert.deepEqual(capped.send, []);
  assert.deepEqual(capped.skipped, [{ kind: "stopped_report", ref: 1, why: "kind" }]);
  // 3 件目まで (1 件は窓の外) は送る。
  const room = selectDispatch(now, [tg(1)], [h(1, 70), h(1, 130)]);
  assert.equal(room.send.length, 1);
  // 枠を 0 にすると送らない (停止行の受け渡しを止めるスイッチ)。
  const off = selectDispatch(now, [tg(2)], [], { stoppedPerHour: 0 });
  assert.deepEqual(off.skipped, [{ kind: "stopped_report", ref: 2, why: "hour" }]);
});
