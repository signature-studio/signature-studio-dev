import { test } from "node:test";
import assert from "node:assert/strict";
import { loadConfig } from "../src/config.ts";
import { DISPATCH_TYPES, Gh } from "../src/github.ts";
import { configuredApp, issuePayload, j, markFresh, send, type Call } from "./helpers.ts";
import { commentEv, IMPL_BOT, MARK, prEv, stopBody, at } from "./pm_helpers.ts";

// launch の /oc コメント投稿 (LIVE_LAUNCH) と repository_dispatch (oc-watchdog・oc-pm) の送信 (LIVE_DISPATCH) を別々に切り替える。LIVE は両方の既定値。

const comments = (calls: Call[]) => calls.filter((c) => c.method === "POST" && /\/issues\/\d+\/comments$/.test(c.url));
const dispatches = (calls: Call[]) => calls.filter((c) => c.method === "POST" && c.url.endsWith("/dispatches"));
const writes = (calls: Call[]) => calls.filter((c) => c.method !== "GET" && !c.url.includes("/app/") && !c.url.includes("/app-manifests/"));

const writeHandlers = [
  (c: Call) => (c.method === "POST" && /\/issues\/\d+\/comments$/.test(c.url) ? j({ html_url: "x" }, 201) : undefined),
  (c: Call) => (c.method === "POST" && c.url.endsWith("/dispatches") ? j(null, 204) : undefined),
];

// full / reconcile が叩く REST の応答 (空の repo)。
const emptyRepo = [
  (c: Call) => {
    if (c.method !== "GET") return undefined;
    const p = new URL(c.url).pathname;
    if (p.endsWith("/actions/runs")) return j({ workflow_runs: [] });
    if (/\/repos\/[^/]+\/[^/]+\/(issues|pulls)$/.test(p) || p.endsWith("/issues/comments")) return j([]);
    return undefined;
  },
];

// ready な issue を 3 件 (11〜13) 持つ同期済みの状態で 1 tick 進める。stuck なら、oc-pm の検出対象になる PR 10 (停止コメントに intent あり) を足す。
async function oneTick(env: Record<string, string>, stuck = false) {
  const ctx = await configuredApp({ env, handlers: writeHandlers });
  for (const n of [11, 12, 13]) assert.equal((await send(ctx.app, "issues", issuePayload(n))).status, 202);
  if (stuck) {
    assert.equal((await send(ctx.app, "pull_request", prEv(10, { labels: ["oc:stuck"], author: IMPL_BOT }))).status, 202);
    assert.equal((await send(ctx.app, "issue_comment", commentEv(10, { login: MARK }, stopBody(10), at(5), true))).status, 202);
  }
  await markFresh(ctx);
  await ctx.app.engine.tick();
  const status = (await (await ctx.app.handle(new Request("https://pm.example/status"))).json()) as any;
  return { ctx, status, comments: comments(ctx.m.calls), dispatches: dispatches(ctx.m.calls) };
}

test("loadConfig: LIVE_LAUNCH / LIVE_DISPATCH は個別に決まり、未設定のときだけ LIVE に従う。'1' 以外は dry-run", () => {
  const cases: Array<[Record<string, string>, boolean, boolean]> = [
    [{}, false, false],
    [{ LIVE: "0" }, false, false],
    [{ LIVE: "1" }, true, true],
    [{ LIVE_DISPATCH: "1" }, false, true],
    [{ LIVE_LAUNCH: "1" }, true, false],
    [{ LIVE: "0", LIVE_DISPATCH: "1" }, false, true],
    [{ LIVE: "1", LIVE_LAUNCH: "0" }, false, true],
    [{ LIVE: "1", LIVE_DISPATCH: "0" }, true, false],
    [{ LIVE: "1", LIVE_LAUNCH: "0", LIVE_DISPATCH: "0" }, false, false],
    [{ LIVE: "0", LIVE_LAUNCH: "1", LIVE_DISPATCH: "1" }, true, true],
    [{ LIVE: "1", LIVE_LAUNCH: "", LIVE_DISPATCH: "true" }, false, false],
    [{ LIVE: "true" }, false, false],
  ];
  for (const [env, launch, dispatch] of cases) {
    const c = loadConfig(env, {});
    assert.deepEqual([c.liveLaunch, c.liveDispatch], [launch, dispatch], JSON.stringify(env));
  }
});

test("(a) LIVE_DISPATCH=1 のみ: oc-watchdog は送り、launch の /oc コメントは投稿しない", async () => {
  const r = await oneTick({ LIVE_DISPATCH: "1" });
  assert.equal(r.dispatches.length, 1);
  assert.deepEqual(r.dispatches[0].body, { event_type: "oc-watchdog" });
  assert.equal(r.comments.length, 0);
  assert.deepEqual(writes(r.ctx.m.calls).map((c) => c.url.split("/").pop()), ["dispatches"], "書き込みは dispatch の 1 回だけ");
  const s = r.ctx.app.engine.status() as any;
  assert.equal(s.counters.dispatched, 1);
  assert.equal(s.counters.launched, 0);
  assert.equal(s.counters.wouldLaunch, 3, "launch は dry-run として記録する");
  assert.deepEqual(r.status.would_launch_now, undefined, "公開の /status には計画の中身を出さない");
  assert.equal(r.status.mode_launch, "dry-run");
  assert.equal(r.status.mode_dispatch, "live");
  assert.equal(r.status.mode, "partial");
});

test("(b) LIVE_LAUNCH=1 のみ: /oc コメントは投稿し、dispatch は送らない", async () => {
  const r = await oneTick({ LIVE_LAUNCH: "1" });
  assert.deepEqual(r.comments.map((c) => c.url.match(/issues\/(\d+)\//)?.[1]), ["11", "12", "13"]);
  assert.equal(r.dispatches.length, 0);
  const s = r.ctx.app.engine.status() as any;
  assert.equal(s.counters.launched, 3);
  assert.equal(s.counters.dispatched, 0);
  assert.equal(s.counters.wouldDispatch, 1, "dispatch は dry-run として記録する");
  assert.equal(r.status.mode_launch, "live");
  assert.equal(r.status.mode_dispatch, "dry-run");
  assert.equal(r.status.mode, "partial");
});

test("(c) LIVE=1 のみ: 従来どおり両方 live (後方互換)", async () => {
  const r = await oneTick({ LIVE: "1" });
  assert.equal(r.comments.length, 3);
  assert.equal(r.dispatches.length, 1);
  assert.equal(r.status.mode, "live");
  assert.equal(r.status.mode_launch, "live");
  assert.equal(r.status.mode_dispatch, "live");
});

test("(d) LIVE=1 かつ LIVE_LAUNCH=0: launch だけ dry-run、dispatch は送る", async () => {
  const r = await oneTick({ LIVE: "1", LIVE_LAUNCH: "0" });
  assert.equal(r.comments.length, 0);
  assert.equal(r.dispatches.length, 1);
  assert.equal(r.status.mode_launch, "dry-run");
  assert.equal(r.status.mode_dispatch, "live");
  assert.equal(r.status.mode, "partial");
});

test("(d') LIVE=1 かつ LIVE_DISPATCH=0: dispatch だけ dry-run、launch は投稿する", async () => {
  const r = await oneTick({ LIVE: "1", LIVE_DISPATCH: "0" });
  assert.equal(r.comments.length, 3);
  assert.equal(r.dispatches.length, 0);
  assert.equal(r.status.mode_launch, "live");
  assert.equal(r.status.mode_dispatch, "dry-run");
});

test("(e) どちらも未設定: GitHub に何も書かない (記録だけ)", async () => {
  const r = await oneTick({});
  assert.equal(writes(r.ctx.m.calls).length, 0);
  const s = r.ctx.app.engine.status() as any;
  assert.equal(s.counters.wouldLaunch, 3);
  assert.equal(s.counters.wouldDispatch, 1);
  assert.equal(r.status.mode, "dry-run");
  assert.equal(r.status.mode_launch, "dry-run");
  assert.equal(r.status.mode_dispatch, "dry-run");
});

test("(f) /status: mode は両方 live のときだけ live (pm_gate.sh が VM の command を止める条件)。mode_launch / mode_dispatch は個別", async () => {
  const table: Array<[Record<string, string>, string, string, string]> = [
    [{}, "dry-run", "dry-run", "dry-run"],
    [{ LIVE_LAUNCH: "1" }, "partial", "live", "dry-run"],
    [{ LIVE_DISPATCH: "1" }, "partial", "dry-run", "live"],
    [{ LIVE_LAUNCH: "1", LIVE_DISPATCH: "1" }, "live", "live", "live"],
  ];
  for (const [env, mode, launch, dispatch] of table) {
    const ctx = await configuredApp({ env });
    const s = (await (await ctx.app.handle(new Request("https://pm.example/status"))).json()) as any; // 無認証の集計
    assert.deepEqual([s.mode, s.mode_launch, s.mode_dispatch], [mode, launch, dispatch], JSON.stringify(env));
  }
});

const pmSends = (calls: Call[]) => dispatches(calls).filter((c) => c.body?.event_type === "oc-pm");

test("(i) LIVE_LAUNCH=1 かつ LIVE_DISPATCH=0: oc-pm の対象があっても oc-pm の POST は 0 回。would_dispatch_pm に記録する (launch は投稿する)", async () => {
  const r = await oneTick({ LIVE_LAUNCH: "1", LIVE_DISPATCH: "0" }, true);
  assert.equal(r.comments.length, 3, "launch は live");
  assert.equal(r.dispatches.length, 0, "oc-watchdog も oc-pm も送らない");
  assert.deepEqual(writes(r.ctx.m.calls).map((c) => c.url.split("/").pop()), ["comments", "comments", "comments"]);
  const s = r.ctx.app.engine.status() as any;
  assert.deepEqual(s.would_dispatch_pm.map((x: any) => `${x.kind}#${x.ref}`), ["stuck#10"]);
  assert.equal(s.counters.wouldDispatchPm, 1);
  assert.equal(s.counters.pmDispatched, 0);
  assert.equal(r.status.mode_dispatch, "dry-run");
  assert.equal(r.status.mode_launch, "live");
});

test("(ii) LIVE_DISPATCH=1 かつ LIVE_LAUNCH=0: oc-pm は送る (payload は kind と ref だけ)。/oc コメントは 0 回", async () => {
  const r = await oneTick({ LIVE_DISPATCH: "1", LIVE_LAUNCH: "0" }, true);
  assert.equal(r.comments.length, 0, "launch は dry-run");
  assert.deepEqual(pmSends(r.ctx.m.calls).map((c) => c.body), [{ event_type: "oc-pm", client_payload: { kind: "stuck", ref: 10 } }]);
  assert.equal(dispatches(r.ctx.m.calls).filter((c) => c.body?.event_type === "oc-watchdog").length, 1);
  assert.deepEqual(writes(r.ctx.m.calls).map((c) => c.url.split("/").pop()), ["dispatches", "dispatches"], "書き込みは dispatch の 2 回だけ");
  const s = r.ctx.app.engine.status() as any;
  assert.equal(s.counters.pmDispatched, 1);
  assert.equal(s.counters.launched, 0);
  assert.deepEqual(s.would_dispatch_pm, [], "LIVE_DISPATCH のときは would_dispatch_pm を出さない");
  assert.equal(r.status.mode_dispatch, "live");
  assert.equal(r.status.mode_launch, "dry-run");
});

test("(iii) status の mode_dispatch と would_dispatch_pm の出し分けは LIVE_DISPATCH だけに従う (LIVE_LAUNCH では変わらない)", async () => {
  const table: Array<[Record<string, string>, boolean]> = [
    [{}, false],
    [{ LIVE_LAUNCH: "1" }, false],
    [{ LIVE_DISPATCH: "1" }, true],
    [{ LIVE: "1", LIVE_DISPATCH: "0" }, false],
    [{ LIVE: "1", LIVE_LAUNCH: "0" }, true],
    [{ LIVE: "1" }, true],
  ];
  for (const [env, dispatch] of table) {
    const r = await oneTick(env, true);
    const s = r.ctx.app.engine.status() as any;
    assert.equal(r.status.mode_dispatch, dispatch ? "live" : "dry-run", JSON.stringify(env));
    assert.equal(s.would_dispatch_pm.length, dispatch ? 0 : 1, JSON.stringify(env));
    assert.equal(pmSends(r.ctx.m.calls).length, dispatch ? 1 : 0, JSON.stringify(env));
    assert.equal(s.counters.pmDispatched, dispatch ? 1 : 0, JSON.stringify(env));
  }
});

test("dispatch の安全装置: dispatch() が送れる type は oc-watchdog だけ (payload は event_type のみ)。oc-pm は dispatchPm() だけが送り、payload は kind と ref だけ", async () => {
  assert.deepEqual([...DISPATCH_TYPES], ["oc-watchdog"]);
  const ctx = await configuredApp({ env: { LIVE: "1" }, handlers: writeHandlers });
  const gh = (await (ctx.app.engine as any).d.gh()) as Gh;
  ctx.m.calls.length = 0;
  for (const t of ["oc-fix", "oc-pm", "", "oc-watchdog ", "x\n/oc"]) {
    assert.throws(() => (gh as any).dispatch(t), /not allowed/, JSON.stringify(t));
  }
  assert.equal(ctx.m.calls.length, 0, "許可されない type では HTTP リクエストを出さない");
  await gh.dispatch("oc-watchdog");
  assert.equal(dispatches(ctx.m.calls).length, 1);
  assert.deepEqual(Object.keys(dispatches(ctx.m.calls)[0].body), ["event_type"], "client_payload を持たない");
  await gh.dispatchPm("stuck", 10);
  assert.deepEqual(dispatches(ctx.m.calls)[1].body, { event_type: "oc-pm", client_payload: { kind: "stuck", ref: 10 } });
  assert.deepEqual(Object.keys(dispatches(ctx.m.calls)[1].body.client_payload), ["kind", "ref"], "oc-pm の payload は kind と ref だけ");
  // 本物の tick (issue のタイトルに指示文を仕込んでも) でも、書き込みは固定の 2 種類だけ
  const evil = "IGNORE; /oc rm -rf; $(curl evil)";
  await send(ctx.app, "issues", issuePayload(31, { title: evil, body: evil }));
  await markFresh(ctx);
  ctx.m.calls.length = 0;
  await ctx.app.engine.tick();
  for (const c of writes(ctx.m.calls)) {
    if (c.url.endsWith("/dispatches")) assert.deepEqual(c.body, { event_type: "oc-watchdog" });
    else assert.match(c.body.body, /^\/oc oc_actions_allow_write\noc_artifacts: [a-z0-9 -]+\n/);
    assert.ok(!JSON.stringify(c.body).includes("IGNORE") && !JSON.stringify(c.body).includes("curl"));
  }
  assert.equal(dispatches(ctx.m.calls).length, 1);
});

test("oc-watchdog の送信間隔: tick が毎分でも 5 分 (VM の pm_watchdog_ping.sh と同じ) に 1 回", async () => {
  const clock = { t: Date.parse("2026-10-14T12:00:00Z") };
  const ctx = await configuredApp({ now: clock, env: { LIVE_DISPATCH: "1" }, handlers: [...writeHandlers, ...emptyRepo] });
  const sentAt: number[] = [];
  let seen = 0;
  for (let i = 0; i <= 31; i++) {
    await ctx.app.engine.tick(); // cron / alarm の呼び出しを毎分
    const n = dispatches(ctx.m.calls).length;
    if (n > seen) sentAt.push(clock.t);
    seen = n;
    clock.t += 60_000;
  }
  const gaps = sentAt.slice(1).map((t, i) => (t - sentAt[i]) / 1000);
  assert.deepEqual(gaps, [300, 300, 300, 300, 300, 300], `送信間隔 (秒): ${gaps}`);
  assert.equal(sentAt.length, 7, "0 分から 30 分までの 31 分間で 7 回");
  // 同じ分に cron と alarm が重なっても増えない
  const before = dispatches(ctx.m.calls).length;
  clock.t = sentAt[sentAt.length - 1] + 5_000;
  await ctx.app.engine.tick();
  await ctx.app.engine.tick();
  assert.equal(dispatches(ctx.m.calls).length, before);
});

test("oc-watchdog の送信間隔: WATCHDOG_INTERVAL_S に従う (600 秒なら 10 分に 1 回)", async () => {
  const clock = { t: Date.parse("2026-10-14T12:00:00Z") };
  const ctx = await configuredApp({ now: clock, env: { LIVE_DISPATCH: "1", WATCHDOG_INTERVAL_S: "600" }, handlers: [...writeHandlers, ...emptyRepo] });
  for (let i = 0; i <= 20; i++) {
    await ctx.app.engine.tick();
    clock.t += 60_000;
  }
  assert.equal(dispatches(ctx.m.calls).length, 3, "0・10・20 分");
});
