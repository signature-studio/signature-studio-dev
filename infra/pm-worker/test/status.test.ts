import { test } from "node:test";
import assert from "node:assert/strict";
import { PmApp } from "../src/app.ts";
import { loadConfig } from "../src/config.ts";
import { MemoryStore } from "../src/kvstore.ts";
import { REST_REMAINING_MIN, parseRateHeaders, restGuardOn } from "../src/ratelimit.ts";
import { redact } from "../src/redact.ts";
import { signBody } from "../src/hmac.ts";
import { BOT, STORE_KEY, T0, WH_SECRET, commentPayload, configuredApp, issuePayload, j, markFresh, runPayload, send, type Call } from "./helpers.ts";

type Ctx = Awaited<ReturnType<typeof configuredApp>>;

const R = "/repos/signature-studio/signature-studio-dev";
const comments = (calls: Call[]) => calls.filter((c) => c.method === "POST" && /\/issues\/\d+\/comments$/.test(c.url));
const dispatches = (calls: Call[]) => calls.filter((c) => c.method === "POST" && c.url.endsWith("/dispatches"));
const gets = (calls: Call[]) => calls.filter((c) => c.method === "GET" && !c.url.includes("/app/"));

// 応答ごとに付ける x-ratelimit-* を変えられるモック。remaining = null ならヘッダを付けない。
function rateMock() {
  const rate = { remaining: "5000" as string | null, used: "10" as string | null, reset: "1792000000" as string | null, after: [] as string[] };
  const hdr = (): Record<string, string> => {
    const h: Record<string, string> = {};
    const next = rate.after.shift();
    const remaining = next ?? rate.remaining;
    if (remaining !== null) h["x-ratelimit-remaining"] = remaining;
    if (rate.used !== null) h["x-ratelimit-used"] = rate.used;
    if (rate.reset !== null) h["x-ratelimit-reset"] = rate.reset;
    return h;
  };
  return { rate, hdr };
}

// REST 側の『正』。issues / prs / runs / comments を書き換えてから reconcile / tick させる。
function restWorld() {
  const w = { issues: [] as any[], prs: [] as any[], runs: [] as any[], comments: [] as any[] };
  const { rate, hdr } = rateMock();
  const handlers = [
    (c: Call) => {
      if (c.method === "POST" && c.url.endsWith("/dispatches")) return j(null, 204, hdr());
      if (c.method === "POST" && /\/comments$/.test(c.url)) return j({}, 201, hdr());
      if (c.method !== "GET") return undefined;
      const u = new URL(c.url);
      const p = u.pathname;
      if (p.endsWith("/actions/runs")) return j({ workflow_runs: w.runs.filter((r) => r.status === u.searchParams.get("status")) }, 200, hdr());
      if (p.endsWith("/issues/comments")) return j([...w.comments].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)), 200, hdr());
      if (p.endsWith("/issues")) return j(u.searchParams.get("state") === "open" ? w.issues.filter((i) => i.state === "open") : w.issues, 200, hdr());
      if (p.endsWith("/pulls")) return j(w.prs, 200, hdr());
      if (/\/dependencies\/blocked_by$/.test(p)) return j([], 200, hdr());
      return undefined;
    },
  ];
  return { w, rate, handlers };
}

const restIssue = (n: number, o: Partial<{ title: string; at: string; labels: string[]; state: string }> = {}) =>
  issuePayload(n, { title: o.title, at: o.at, labels: o.labels, state: o.state }).issue;

const get = async (ctx: Ctx, path = "/status", headers: Record<string, string> = {}) => ctx.app.handle(new Request(`https://pm.example${path}`, { headers }));

// ---------------------------------------------------------------------------------------------------------------- 受入 5(d)
const EXISTING_KEYS = [
  "mode", "mode_launch", "mode_dispatch", "active_runs", "target", "room", "open_issues", "open_prs", "phase", "open_prs_excl_stuck", "stuck_prs", "launch_stop",
  "blocked", "started", "ready", "relaunch", "user", "stopped", "recent", "would_launch_now", "last_full_sync", "last_reconcile",
  "last_watchdog", "last_tick", "fresh", "counters", "last_error", "log", "configured", "installed", "pm_bot_login",
  "sync_truncated", "last_full_sync_rest_calls", "last_full_sync_comment_rest_calls", "comment_window_h", "comment_max_pages",
];
const ADDED_KEYS = [
  "last_webhook_at", "last_dispatch_at", "running", "dry_run_skipped_posts", "reconcile_diff", "rest_remaining", "rest_used", "rest_reset_at", "pm_detected",
  "no_pr_needs_pm",
];
// detail のみ (公開 /status は出さない。oc-pm の dry-run 記録)
const DETAIL_ONLY_KEYS = ["would_dispatch_pm"];

test("/status (d): 既存のキーは全て残り、追加するキーだけが増える (スナップショット)", async () => {
  const ctx = await configuredApp({
    handlers: [(c) => (c.url.endsWith(R) && c.auth === "Bearer ghp_valid_push_token_x" ? j({ permissions: { push: true } }) : undefined)],
  });
  const detail = (await (await get(ctx, "/status?detail=1", { authorization: "Bearer ghp_valid_push_token_x" })).json()) as any;
  assert.deepEqual(Object.keys(detail).sort(), [...EXISTING_KEYS, ...ADDED_KEYS, ...DETAIL_ONLY_KEYS].sort());
  // 既存のキーの型・初期値は変えない
  assert.equal(detail.mode, "dry-run");
  assert.equal(detail.phase, "launch");
  assert.equal(detail.launch_stop, null);
  assert.equal(detail.fresh, false);
  assert.deepEqual(detail.counters, { launched: 0, dispatched: 0, wouldLaunch: 0, wouldDispatch: 0, reconciles: 0, pmDispatched: 0, wouldDispatchPm: 0 });
  assert.equal(detail.last_error, null);
  assert.deepEqual(detail.log, []);
  assert.deepEqual(detail.would_launch_now, []);
  // 公開 (detail なし) は集計だけ: 従来どおり 3 キーを除き、追加したキーは全て出る
  const pub = (await (await get(ctx)).json()) as any;
  assert.deepEqual(Object.keys(pub).sort(), [...EXISTING_KEYS, ...ADDED_KEYS].filter((k) => !["log", "would_launch_now", "last_error"].includes(k)).sort());
});

test("/status: 観測の初期値は null / 0 (残量を 0 と誤読しない)", async () => {
  const ctx = await configuredApp();
  const s = (await (await get(ctx)).json()) as any;
  assert.equal(s.last_webhook_at, null);
  assert.equal(s.last_dispatch_at, null);
  assert.deepEqual(s.running, { in_progress: 0, queued: 0, pending: 0 });
  assert.equal(s.dry_run_skipped_posts, 0);
  assert.deepEqual(s.reconcile_diff, { last: 0, total: 0 });
  assert.equal(s.rest_remaining, null);
  assert.equal(s.rest_used, null);
  assert.equal(s.rest_reset_at, null);
});

// ---------------------------------------------------------------------------------------------------------------- 受入 1
test("last_webhook_at: 署名を検証できた配送だけで更新する (401 では更新しない)", async () => {
  const clock = { t: T0 };
  const ctx = await configuredApp({ now: clock });
  const st = async () => ((await (await get(ctx)).json()) as any).last_webhook_at;
  assert.equal((await send(ctx.app, "issues", issuePayload(1), "sha256=00")).status, 401);
  assert.equal(await st(), null);
  assert.equal((await send(ctx.app, "issues", issuePayload(1))).status, 202);
  assert.equal(await st(), new Date(T0).toISOString());
  clock.t += 90_000;
  assert.equal((await send(ctx.app, "issues", issuePayload(1), signBody("other", "{}"))).status, 401);
  assert.equal(await st(), new Date(T0).toISOString(), "401 では進めない");
  await send(ctx.app, "issues", issuePayload(2));
  assert.equal(await st(), new Date(T0 + 90_000).toISOString());
});

test("last_dispatch_at: repository_dispatch に成功した時刻。失敗と dry-run では更新しない", async () => {
  const clock = { t: T0 };
  const w = restWorld();
  let fail = true;
  const live = await configuredApp({
    now: clock,
    live: true,
    handlers: [(c) => (fail && c.url.endsWith("/dispatches") ? j({}, 500) : undefined), ...w.handlers],
  });
  const st = async () => ((await (await get(live)).json()) as any).last_dispatch_at;
  await live.app.engine.tick();
  assert.equal(await st(), null, "失敗した dispatch は記録しない");
  fail = false;
  clock.t += 60_000;
  await live.app.engine.tick();
  assert.equal(await st(), new Date(clock.t).toISOString());
  assert.equal(dispatches(live.m.calls).length, 2);

  const dry = await configuredApp({ handlers: restWorld().handlers });
  await dry.app.engine.tick();
  const s = (await (await get(dry)).json()) as any;
  assert.equal(s.last_dispatch_at, null, "dry-run は dispatch しない");
  assert.ok(s.last_watchdog, "dry-run の would-dispatch は last_watchdog に残る (既存)");
});

test("running: in_progress / queued / pending を run の event によらず数える (completed などは数えない)", async () => {
  const ctx = await configuredApp();
  const runs: Array<[number, string, string]> = [
    [1, "in_progress", "issue_comment"], [2, "in_progress", "pull_request"], [3, "queued", "pull_request_review"],
    [4, "pending", "workflow_dispatch"], [5, "completed", "issue_comment"], [6, "waiting", "push"], [7, "queued", "repository_dispatch"],
  ];
  for (const [id, status, event] of runs) await send(ctx.app, "workflow_run", runPayload(id, status, { event }));
  const s = (await (await get(ctx)).json()) as any;
  assert.deepEqual(s.running, { in_progress: 2, queued: 2, pending: 1 });
  assert.equal(s.active_runs, 3, "TARGET に数える active_runs は従来どおり (issue_comment / workflow_dispatch / review。pull_request・push は数えない)");
});

test("dry_run_skipped_posts: dry-run のために投稿しなかった /oc 投稿と dispatch の累計。live では増えない", async () => {
  const ctx = await configuredApp({ handlers: restWorld().handlers });
  for (const n of [11, 12]) await send(ctx.app, "issues", issuePayload(n));
  await markFresh(ctx);
  const gh = await (ctx.app.engine as any).d.gh();
  await ctx.app.engine.watchdog(gh);
  await ctx.app.engine.launch(gh);
  const s = (await (await get(ctx)).json()) as any;
  assert.equal(s.counters.wouldLaunch, 2);
  assert.equal(s.counters.wouldDispatch, 1);
  assert.equal(s.dry_run_skipped_posts, 3);
  assert.equal(comments(ctx.m.calls).length + dispatches(ctx.m.calls).length, 0);
  const w = restWorld();
  const live = await configuredApp({ live: true, handlers: w.handlers });
  await send(live.app, "issues", issuePayload(11));
  await markFresh(live);
  await live.app.engine.launch(await (live.app.engine as any).d.gh());
  assert.equal(((await (await get(live)).json()) as any).dry_run_skipped_posts, 0);
  assert.equal(comments(live.m.calls).length, 1);
});

test("reconcile_diff: REST を適用して DO の内容が変わった件数 (直近 / 累計)。updatedAt だけの違いと full sync は数えない", async () => {
  const clock = { t: T0 };
  const w = restWorld();
  const ctx = await configuredApp({ now: clock, handlers: w.handlers });
  const diff = async () => ((await (await get(ctx)).json()) as any).reconcile_diff;
  // webhook で受け取った状態
  await send(ctx.app, "issues", issuePayload(1, { at: "2026-10-14T10:00:00Z" }));
  await send(ctx.app, "workflow_run", runPayload(9, "in_progress"));
  await send(ctx.app, "issue_comment", commentPayload(1, BOT, "報告 1", "2026-10-14T10:30:00Z"));
  // REST: issue 1 は同じ内容で updated_at だけ進んでいる (コメントの追加など)。issue 2 は webhook を取りこぼした。run 9 は終わっている。
  w.w.issues = [restIssue(1, { at: "2026-10-14T11:40:00Z" }), restIssue(2, { at: "2026-10-14T11:41:00Z" })];
  w.w.comments = [{ issue_url: "https://api.github.com/repos/x/y/issues/1", user: { login: BOT }, body: "報告 1", created_at: "2026-10-14T10:30:00Z" }];
  await markFresh(ctx);
  const gh = await (ctx.app.engine as any).d.gh();
  clock.t += 6 * 60_000;
  await ctx.app.engine.reconcile(gh);
  assert.deepEqual(await diff(), { last: 2, total: 2 }, "issue 2 (欠落) と run 9 (完了の欠落) の 2 件。issue 1 の updated_at と既知のコメントは数えない");
  clock.t += 6 * 60_000;
  await ctx.app.engine.reconcile(gh);
  assert.deepEqual(await diff(), { last: 0, total: 2 }, "一致していれば 0。累計は減らない");
  // issue 1 のタイトル変更と、新しい bot の報告を取りこぼした
  w.w.issues = [restIssue(1, { title: "[CI-1] renamed", at: "2026-10-14T11:50:00Z" }), restIssue(2, { at: "2026-10-14T11:41:00Z" })];
  w.w.comments.push({ issue_url: "https://api.github.com/repos/x/y/issues/2", user: { login: BOT }, body: "報告 2", created_at: "2026-10-14T12:15:00Z" });
  clock.t += 6 * 60_000;
  await ctx.app.engine.reconcile(gh);
  assert.deepEqual(await diff(), { last: 2, total: 4 });
  assert.equal(ctx.app.engine.s.issues["1"].title, "[CI-1] renamed", "差分は適用される (従来どおり)");
});

test("reconcile_diff: full sync (起動時・6 時間ごと) では数えない。tick は full → reconcile の順", async () => {
  const clock = { t: T0 };
  const w = restWorld();
  w.w.issues = [restIssue(1), restIssue(2), restIssue(3)];
  const ctx = await configuredApp({ now: clock, handlers: w.handlers });
  await ctx.app.engine.tick();
  assert.equal(Object.keys(ctx.app.engine.s.issues).length, 3, "full sync で取り込んだ");
  assert.deepEqual(((await (await get(ctx)).json()) as any).reconcile_diff, { last: 0, total: 0 });
  clock.t += 6 * 60_000;
  await ctx.app.engine.tick();
  const s = (await (await get(ctx)).json()) as any;
  assert.equal(s.counters.reconciles, 1);
  assert.deepEqual(s.reconcile_diff, { last: 0, total: 0 });
});

// ---------------------------------------------------------------------------------------------------------------- 受入 2
test("ratelimit: ヘッダの解釈 (有効な数値だけ採用し、無い・空・不正は無視)", () => {
  const h = (o: Record<string, string>) => new Headers(o);
  assert.deepEqual(parseRateHeaders(h({ "x-ratelimit-remaining": "4999", "x-ratelimit-used": "1", "x-ratelimit-reset": "1792000000" })), { remaining: 4999, used: 1, reset: 1792000000 });
  assert.deepEqual(parseRateHeaders(h({ "x-ratelimit-remaining": "0" })), { remaining: 0 }, "0 は有効な値");
  assert.deepEqual(parseRateHeaders(h({ "x-ratelimit-used": "7" })), { used: 7 });
  for (const bad of ["", " ", "abc", "-1", "1.5", "1e3", "NaN", "9999999999999"]) assert.equal(parseRateHeaders(h({ "x-ratelimit-remaining": bad })), null, JSON.stringify(bad));
  assert.equal(parseRateHeaders(h({})), null);
});

test("ratelimit: 境界 1,499 で止め、1,500 で継続する。未観測は止めない", () => {
  assert.equal(REST_REMAINING_MIN, 1500);
  assert.equal(restGuardOn(1499), true);
  assert.equal(restGuardOn(1500), false);
  assert.equal(restGuardOn(1501), false);
  assert.equal(restGuardOn(0), true);
  assert.equal(restGuardOn(undefined), false);
  assert.equal(restGuardOn(null), false);
});

test("rest: 全応答 (成功・失敗) の x-ratelimit-* を DO に記録し、/status に remaining・used・reset_at を出す。再起動後も残る", async () => {
  const m = rateMock();
  const ctx = await configuredApp({
    handlers: [(c) => (c.url.includes(`${R}/issues`) ? j(c.url.includes("fail") ? { message: "x" } : [], c.url.includes("fail") ? 403 : 200, m.hdr()) : undefined)],
  });
  await markFresh(ctx);
  const gh = await (ctx.app.engine as any).d.gh();
  m.rate.remaining = "4321";
  m.rate.used = "679";
  m.rate.reset = "1792000000";
  await gh.req("GET", `${R}/issues?x=1`);
  let s = (await (await get(ctx)).json()) as any;
  assert.equal(s.rest_remaining, 4321);
  assert.equal(s.rest_used, 679);
  assert.equal(s.rest_reset_at, new Date(1792000000 * 1000).toISOString());
  // 失敗応答 (403) のヘッダも記録する
  m.rate.remaining = "0";
  await assert.rejects(gh.req("GET", `${R}/issues?fail=1`));
  s = (await (await get(ctx)).json()) as any;
  assert.equal(s.rest_remaining, 0);
  // 保存 (tick / launch の最後の saveMeta) の後、同じ store から作り直した App でも読める
  await ctx.app.engine.launch(gh);
  const again = new PmApp({ store: ctx.store, cfg: loadConfig({}, {}), storeKey: STORE_KEY, now: () => T0, fetch: ctx.m.f, scheduleSoon: async () => {} });
  const s2 = again.engine.status() as any;
  assert.equal(s2.rest_remaining, 0);
  assert.equal(s2.rest_reset_at, new Date(1792000000 * 1000).toISOString());
});

test("rest (c): ヘッダの無い応答・空・不正な値では残量を更新しない (0 にしない)", async () => {
  const m = rateMock();
  const ctx = await configuredApp({ handlers: [(c) => (c.url.includes(`${R}/issues`) ? j([], 200, m.hdr()) : undefined)] });
  const gh = await (ctx.app.engine as any).d.gh();
  const rem = async () => ((await (await get(ctx)).json()) as any).rest_remaining;
  // 観測前にヘッダの無い応答が来ても null のまま (0 にならない)
  m.rate.remaining = m.rate.used = m.rate.reset = null;
  await gh.req("GET", `${R}/issues?a=1`);
  assert.equal(await rem(), null);
  m.rate.remaining = "1700";
  m.rate.used = "3300";
  m.rate.reset = "1792000000";
  await gh.req("GET", `${R}/issues?a=2`);
  assert.equal(await rem(), 1700);
  // ヘッダが無い
  m.rate.remaining = m.rate.used = m.rate.reset = null;
  await gh.req("GET", `${R}/issues?a=3`);
  assert.equal(await rem(), 1700, "ヘッダの無い応答では更新しない");
  // 空文字・不正な値
  for (const bad of ["", "abc", "-5", "1e2"]) {
    m.rate.remaining = bad;
    await gh.req("GET", `${R}/issues?a=4`);
    assert.equal(await rem(), 1700, JSON.stringify(bad));
  }
  // remaining が無く used だけある応答は、remaining を変えない
  m.rate.remaining = null;
  m.rate.used = "3301";
  await gh.req("GET", `${R}/issues?a=5`);
  const s = (await (await get(ctx)).json()) as any;
  assert.equal(s.rest_remaining, 1700);
  assert.equal(s.rest_used, 3301);
  assert.equal(s.rest_reset_at, new Date(1792000000 * 1000).toISOString(), "reset も維持");
});

test("rest: Gh を使わない呼び出し (JWT の /app/*・呼び出し側の token の確認) は記録しない", async () => {
  const ctx = await configuredApp({
    handlers: [(c) => (c.url.endsWith(R) ? j({ permissions: { push: true } }, 200, { "x-ratelimit-remaining": "3" }) : undefined)],
  });
  const r = await get(ctx, "/status?detail=1", { authorization: "Bearer ghp_valid_push_token_x" });
  assert.equal(r.status, 200);
  assert.equal(((await r.json()) as any).rest_remaining, null, "呼び出し側の token の残量を混ぜない");
});

// ---------------------------------------------------------------------------------------------------------------- 受入 5(b)
async function liveCtx(env: Record<string, string> = {}, live = true) {
  const w = restWorld();
  const ctx = await configuredApp({ live, env, handlers: w.handlers });
  for (const n of [11, 12, 13]) await send(ctx.app, "issues", issuePayload(n));
  await markFresh(ctx);
  const gh = await (ctx.app.engine as any).d.gh();
  const observe = async (remaining: string) => {
    w.rate.remaining = remaining;
    await gh.req("GET", `${R}/issues?probe=1`);
  };
  return { ...ctx, w, gh, observe };
}

test("rate-guard (b): 残量 1,499 で launch を止め、1,500 で継続する (境界)", async () => {
  const stop = await liveCtx();
  await stop.observe("1499");
  const plan = await stop.app.engine.launch(stop.gh);
  assert.equal(comments(stop.m.calls).length, 0);
  assert.equal(plan.stop, "rate-guard");
  assert.deepEqual(plan.picks, []);
  let s = stop.app.engine.status() as any;
  assert.equal(s.launch_stop, "rate-guard");
  assert.equal(s.rest_remaining, 1499);

  const go = await liveCtx();
  await go.observe("1500");
  const plan2 = await go.app.engine.launch(go.gh);
  assert.equal(plan2.stop, undefined);
  assert.deepEqual(comments(go.m.calls).map((c) => c.url.match(/issues\/(\d+)\//)?.[1]), ["11", "12", "13"]);
  s = go.app.engine.status() as any;
  assert.equal(s.launch_stop, null);
  assert.equal(s.rest_remaining, 1500);
});

test("rate-guard: 回復したら再開し、遷移のときだけログに残す (毎回は書かない)", async () => {
  const c = await liveCtx();
  await c.observe("1499");
  await c.app.engine.launch(c.gh);
  await c.app.engine.launch(c.gh);
  assert.equal(comments(c.m.calls).length, 0);
  const notes = () => (c.app.engine.status() as any).log.map((l: any) => l.note).filter((x: string) => x?.startsWith("rate-guard"));
  assert.deepEqual(notes(), ["rate-guard on remaining=1499"]);
  await c.observe("4800");
  await c.app.engine.launch(c.gh);
  assert.equal(comments(c.m.calls).length, 3);
  assert.deepEqual(notes(), ["rate-guard on remaining=1499", "rate-guard off remaining=4800"]);
});

test("rate-guard: 投稿の応答で残量が下がったら、同じ launch の残りも止める", async () => {
  const c = await liveCtx();
  await c.observe("1501");
  c.w.rate.after = ["1499"]; // 最初の投稿の応答が 1,499 を返す
  await c.app.engine.launch(c.gh);
  assert.equal(comments(c.m.calls).length, 1, "1 件投稿した時点で 1,499 になり、残りは投稿しない");
  assert.equal((c.app.engine.status() as any).launch_stop, "rate-guard");
});

test("rate-guard: 残量が未観測 (ヘッダなし) なら止めない", async () => {
  const c = await liveCtx();
  assert.equal((c.app.engine.status() as any).rest_remaining, null);
  await c.app.engine.launch(c.gh);
  assert.equal(comments(c.m.calls).length, 3);
});

test("rate-guard: dry-run でも計画 (would_launch_now) は止まるが、投稿はもともとしない", async () => {
  const c = await liveCtx({}, false);
  await c.observe("1499");
  await c.app.engine.launch(c.gh);
  let s = c.app.engine.status() as any;
  assert.equal(s.launch_stop, "rate-guard");
  assert.deepEqual(s.would_launch_now, []);
  assert.equal(s.counters.wouldLaunch, 0);
  await c.observe("1500");
  await c.app.engine.launch(c.gh);
  s = c.app.engine.status() as any;
  assert.equal(s.launch_stop, null);
  assert.deepEqual(s.counters.wouldLaunch, 3);
  assert.equal(comments(c.m.calls).length, 0, "dry-run は書かない");
});

test("rate-guard: stuck-ceiling (既存) が先に立つときは launch_stop の値を変えない", async () => {
  const c = await liveCtx({ STUCK_HIGH: "0" });
  await send(c.app, "pull_request", {
    action: "opened",
    repository: { full_name: "signature-studio/signature-studio-dev" },
    pull_request: { number: 900, state: "open", head: { ref: "x" }, title: "t", body: "", labels: [{ name: "oc:stuck" }], updated_at: "2026-10-14T11:00:00Z" },
  });
  await c.observe("1000");
  await c.app.engine.launch(c.gh);
  assert.equal((c.app.engine.status() as any).launch_stop, "stuck-ceiling");
  assert.equal(comments(c.m.calls).length, 0);
});

test("rate-guard: 止めるのは launch だけ。tick の同期 (読み取り) と watchdog の dispatch は続く", async () => {
  const clock = { t: T0 };
  const w = restWorld();
  w.w.issues = [restIssue(11), restIssue(12), restIssue(13)];
  const ctx = await configuredApp({ now: clock, live: true, handlers: w.handlers });
  w.rate.remaining = "1499";
  await ctx.app.engine.tick(); // full sync → dispatch → launch
  assert.ok(gets(ctx.m.calls).length > 0, "読み取りは続く");
  assert.equal(dispatches(ctx.m.calls).length, 1);
  assert.equal(comments(ctx.m.calls).length, 0);
  assert.equal((ctx.app.engine.status() as any).launch_stop, "rate-guard");
  const readsBefore = gets(ctx.m.calls).length;
  clock.t += 6 * 60_000; // reconcile の周期
  w.rate.remaining = "1500"; // reconcile の応答で残量が戻ったことを知り、同じ tick の launch が通る
  await ctx.app.engine.tick();
  assert.ok(gets(ctx.m.calls).length > readsBefore, "guard 中も reconcile の読み取りを続けた");
  assert.equal(((await (await get(ctx)).json()) as any).counters.reconciles, 1);
  assert.equal(comments(ctx.m.calls).length, 3, "残量が戻ったら launch する");
});

// ---------------------------------------------------------------------------------------------------------------- 受入 3 / 5(a)
const DUMMY_PEM = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEADUMMYDUMMYDUMMYDUMMYDUMMYDUMMY0123456789\nQUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVo=\n-----END RSA PRIVATE KEY-----";
const DUMMY_SECRET = "whsec_DUMMY_secret_value_9f8e7d6c5b4a";
const DUMMY_TOKEN = "ghp_DUMMYtokenDUMMYtoken0123456789abcdef";
const DUMMY_JWT = "eyJhbGciOiJSUzI1NiJ9.eyJpc3MiOiI0MjQyIn0.c2lnbmF0dXJlLWR1bW15LXZhbHVl";
const DUMMY_BEARER = "Bearer dummy-opaque-bearer-credential-123";

test("secret (a): ダミーの PEM / secret / token を状態に入れても、/status の JSON と console.log に 0 件", async () => {
  const logs: string[] = [];
  const orig = console.log;
  console.log = (...a: unknown[]) => void logs.push(a.map(String).join(" "));
  try {
    const w = restWorld();
    const ctx = await configuredApp({
      live: true,
      handlers: [
        (c) => (c.url.endsWith(R) && c.auth === "Bearer ghp_valid_push_token_x" ? j({ permissions: { push: true } }) : undefined),
        (c) => (c.method === "POST" && c.url.endsWith("/dispatches") ? j({ message: DUMMY_TOKEN }, 500) : undefined), // 失敗応答の本文
        (c) => (c.method === "POST" && /\/issues\/12\/comments$/.test(c.url) ? j({ message: DUMMY_PEM }, 403) : undefined),
        ...w.handlers,
      ],
    });
    // (i) webhook の自由文 (タイトル・本文・コメント・PR・run) に入れる
    const evil = `${DUMMY_PEM} ${DUMMY_SECRET} ${DUMMY_TOKEN} ${DUMMY_JWT} ${DUMMY_BEARER}`;
    for (const n of [11, 12]) await send(ctx.app, "issues", issuePayload(n, { title: evil, body: evil }));
    await send(ctx.app, "issue_comment", commentPayload(11, BOT, evil));
    await send(ctx.app, "issue_comment", commentPayload(11, "pycabbage", `oc_artifacts: fl-win64\n${evil}`));
    await send(ctx.app, "pull_request", {
      action: "opened",
      repository: { full_name: "signature-studio/signature-studio-dev" },
      pull_request: { number: 900, state: "open", head: { ref: DUMMY_TOKEN }, title: evil, body: evil, updated_at: "2026-10-14T11:00:00Z" },
    });
    await send(ctx.app, "workflow_run", runPayload(1, "in_progress", { title: `run ${evil}` }));
    await markFresh(ctx);
    const gh = await (ctx.app.engine as any).d.gh();
    await ctx.app.engine.watchdog(gh); // 失敗 → ログ
    await ctx.app.engine.launch(gh); // 12 の投稿が 403 → ログ
    // (ii) 出力される自由文 (last_error・ログの note) に直接入れる: 古い保存値・想定外のエラー文を想定
    const eng = ctx.app.engine as any;
    eng.meta.lastError = { at: "2026-10-14T12:00:00.000Z", what: `boom ${DUMMY_PEM} ${DUMMY_SECRET}`.replace(DUMMY_SECRET, WH_SECRET) + ` ${DUMMY_TOKEN} ${DUMMY_JWT}` };
    eng.log.push({ at: "2026-10-14T12:00:00.000Z", kind: "error", note: `${DUMMY_BEARER} ${DUMMY_PEM}` });
    eng.pushLog({ kind: "error", note: `note ${DUMMY_TOKEN} ${DUMMY_JWT} ${DUMMY_BEARER} ${DUMMY_PEM}` });
    // 実行時に分かっている本物の secret (復号済みの webhook secret・PEM・installation token・STORE_KEY) も note に入れてみる
    const realPemLine = ctx.pems.pkcs1.split("\n")[1];
    eng.pushLog({ kind: "error", note: `real ${WH_SECRET} ${realPemLine} ghs_installation_token_value ${STORE_KEY}` });

    const pub = await (await get(ctx)).text();
    const det = await (await get(ctx, "/status?detail=1", { authorization: "Bearer ghp_valid_push_token_x" })).text();
    const out = [pub, det, ...logs].join("\n");
    const needles = [
      DUMMY_SECRET, DUMMY_TOKEN, DUMMY_JWT, DUMMY_BEARER, "DUMMYDUMMYDUMMY", "MIIEpAIBAAKCAQEA", "BEGIN RSA PRIVATE KEY", "QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVo",
      WH_SECRET, realPemLine, "ghs_installation_token_value", STORE_KEY, "ghp_valid_push_token_x", "dummy-opaque-bearer-credential",
    ];
    for (const needle of needles) assert.ok(!out.includes(needle), `漏れた: ${needle.slice(0, 24)}`);
    // 検査が空振りでないこと: ログも detail も実際に出力されている
    assert.ok(logs.length >= 4 && logs.some((l) => l.includes("[redacted]")));
    assert.ok(JSON.parse(det).log.length >= 4 && det.includes("[redacted]"));
    assert.ok(JSON.parse(det).last_error.what.startsWith("boom "));
    assert.ok(!JSON.parse(pub).log && !JSON.parse(pub).last_error, "公開の /status に自由文のキーは無い");
    // この検査自身のネガコン: 取り除く前の文字列ならヒットする
    assert.ok(JSON.stringify({ note: DUMMY_TOKEN }).includes(DUMMY_TOKEN));
  } finally {
    console.log = orig;
  }
});

test("secret: redact は PEM・token・JWT・Bearer・署名・既知のリテラルを消し、普通の文は変えない", () => {
  for (const s of [DUMMY_PEM, DUMMY_TOKEN, DUMMY_JWT, DUMMY_BEARER, "github_pat_11ABCDEFG0123456789_abcdefghij", "sha256=" + "a".repeat(64), "gho_abcdefgh12345678"]) {
    assert.equal(redact(`x ${s} y`), "x [redacted] y", s.slice(0, 20));
  }
  assert.equal(redact("PEM 途中切れ -----BEGIN PRIVATE KEY-----\nAAAA"), "PEM 途中切れ [redacted]");
  assert.equal(redact("a hunter2-literal b", ["hunter2-literal"]), "a [redacted] b");
  assert.equal(redact("short ab", ["ab"]), "short ab", "短すぎるリテラルは対象外");
  const plain = "GET /repos/signature-studio/signature-studio-dev/issues/12/comments -> 403 (state not fresh: launch skipped)";
  assert.equal(redact(plain, ["unrelated-secret-value"]), plain);
});

test("secret: 集計のみ (個票なし)。公開の /status に issue のタイトル・本文・コメント・login を出さない", async () => {
  const ctx = await configuredApp();
  await send(ctx.app, "issues", issuePayload(5, { title: "TITLE-MARK", body: "BODY-MARK" }));
  await send(ctx.app, "issue_comment", commentPayload(5, BOT, "COMMENT-MARK"));
  await send(ctx.app, "workflow_run", runPayload(3, "in_progress", { title: "RUNTITLE-MARK" }));
  const text = await (await get(ctx)).text();
  for (const m of ["TITLE-MARK", "BODY-MARK", "COMMENT-MARK", "RUNTITLE-MARK"]) assert.ok(!text.includes(m), m);
  for (const v of Object.values(JSON.parse(text))) assert.ok(typeof v !== "string" || v.length < 80, "長い自由文を持つ値が無い");
});

// 参照されない import の警告を避ける
void MemoryStore;
void WH_SECRET;
