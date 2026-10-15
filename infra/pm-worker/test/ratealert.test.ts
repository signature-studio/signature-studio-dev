import { test } from "node:test";
import assert from "node:assert/strict";
import { PmApp } from "../src/app.ts";
import { loadConfig } from "../src/config.ts";
import { rateHit, rateMarkRun } from "../src/ratealert.ts";
import { BOT, REPO, STORE_KEY, T0, configuredApp, send, type Call } from "./helpers.ts";

type Ctx = Awaited<ReturnType<typeof configuredApp>>;

const MIN = 60_000;
const OC = ".github/workflows/opencode.yaml";
const iso = (t: number) => new Date(t).toISOString();

// 完了した run。path を省くと workflow は opencode.yaml として数える (isOpencodeRun)。ここでは明示する。
const runDone = (id: number, at: number, path = OC, conclusion = "failure") => ({
  action: "completed",
  repository: REPO,
  workflow_run: { id, event: "issue_comment", display_title: `run ${id}`, name: "opencode", status: "completed", conclusion, updated_at: iso(at), created_at: iso(at - MIN), path },
});

// run の完了を cause=rate_limit のマーカーとして残す bot の投稿 (detect-rate-limit.sh / record-run-outcome.sh の本文の形)。
const marker = (run: number, at: number, o: { login?: string; pr?: boolean; cause?: string; issue?: number } = {}) => ({
  action: "created",
  repository: REPO,
  issue: { number: o.issue ?? 1000 + run, ...(o.pr ? { pull_request: { url: "x" } } : {}) },
  comment: {
    id: run * 10,
    user: { login: o.login ?? BOT },
    body: `[run-outcome] 失敗\n<!-- oc-run-outcome: no-pr reason=unknown ${o.cause ?? "cause=rate_limit"} run=${run} -->`,
    created_at: iso(at),
  },
});

const status = async (ctx: Ctx) => (await (await ctx.app.handle(new Request("https://pm.example/status"))).json()) as any;

// 直近 (完了から 5 分) の run を n 件作り、うち marked 件に率制限のマーカーを付ける。
async function addRuns(ctx: Ctx, base: number, n: number, marked: number, o: { at?: number; login?: string } = {}) {
  const at = o.at ?? ctx.clock.t - 5 * MIN;
  for (let i = 0; i < n; i++) {
    const id = base + i;
    await send(ctx.app, "workflow_run", runDone(id, at));
    if (i < marked) await send(ctx.app, "issue_comment", marker(id, at, { login: o.login }));
  }
}

const postsToIssues = (ctx: Ctx) => ctx.m.calls.filter((c: Call) => c.method !== "GET" && /\/repos\/[^/]+\/[^/]+\/issues/.test(c.url));

test("rate: 直近 30 分の 10 件中 6 件 (60%) に率制限のマーカー → 1 回目は alert なし、2 回連続で alert (件数・割合を /status に出す)", async () => {
  const ctx = await configuredApp();
  await addRuns(ctx, 100, 10, 5);
  // 6 件目は PR のコメントに付くマーカー (review / fix の detect-rate-limit.sh は PR 番号に付ける)
  await send(ctx.app, "issue_comment", marker(105, ctx.clock.t - 5 * MIN, { pr: true }));
  // マーカーの後に bot が別のコメントを付けても、マーカーは上書きされない (botLast と違う)
  await send(ctx.app, "issue_comment", { action: "created", repository: REPO, issue: { number: 1105 }, comment: { id: 1, user: { login: BOT }, body: "停止報告の本文", created_at: iso(ctx.clock.t - 4 * MIN) } });
  ctx.app.engine.rateAlert();
  let s = await status(ctx);
  assert.equal(s.rate_limit_alert, false, "1 回だけでは alert にしない");
  assert.equal(s.rate_limit_30m.streak, 1);
  assert.equal(s.rate_limit_30m.count, 6);
  assert.equal(s.rate_limit_30m.total, 10);
  ctx.clock.t += MIN;
  ctx.app.engine.rateAlert();
  s = await status(ctx);
  assert.equal(s.rate_limit_alert, true, "2 回連続で alert");
  assert.equal(s.rate_limit_30m.streak, 2);
  assert.equal(s.rate_limit_30m.rate, 0.6);
  // 通知 (起票) は行わない: alert が true でも issues への書き込みは 0 回 (dry-run でも同じ)
  assert.equal(postsToIssues(ctx).length, 0);
});

test("rate (a): 1 回だけ満たしたあとで満たさなくなったら alert にならない (連続が切れる)", async () => {
  const ctx = await configuredApp();
  await addRuns(ctx, 100, 10, 6);
  ctx.app.engine.rateAlert();
  ctx.clock.t += MIN;
  await addRuns(ctx, 200, 20, 0, { at: ctx.clock.t - MIN });
  ctx.app.engine.rateAlert();
  const s = await status(ctx);
  assert.equal(s.rate_limit_30m.count, 6);
  assert.equal(s.rate_limit_30m.total, 30);
  assert.equal(s.rate_limit_30m.streak, 0, "6/30 = 20% は満たさない");
  assert.equal(s.rate_limit_alert, false);
});

test("rate (b): 件数が 5 件未満 (4 件 / 4 件 = 100%) なら alert にならない", async () => {
  const ctx = await configuredApp();
  await addRuns(ctx, 100, 4, 4);
  ctx.app.engine.rateAlert();
  ctx.clock.t += MIN;
  ctx.app.engine.rateAlert();
  const s = await status(ctx);
  assert.equal(s.rate_limit_30m.count, 4);
  assert.equal(s.rate_limit_alert, false);
});

test("rate (c): 割合が 30% 未満 (5 件 / 20 件 = 25%) なら alert にならない。ちょうど 30% (6 / 20) は満たす", async () => {
  const low = await configuredApp();
  await addRuns(low, 100, 20, 5);
  low.app.engine.rateAlert();
  low.clock.t += MIN;
  low.app.engine.rateAlert();
  assert.equal((await status(low)).rate_limit_alert, false);

  const edge = await configuredApp();
  await addRuns(edge, 100, 20, 6);
  edge.app.engine.rateAlert();
  edge.clock.t += MIN;
  edge.app.engine.rateAlert();
  assert.equal((await status(edge)).rate_limit_alert, true);
});

test("rate (d): 率制限のマーカーの無い失敗 run 12 件 (Prepare PR context の失敗相当) → 0 件で alert なし", async () => {
  const ctx = await configuredApp();
  await addRuns(ctx, 100, 12, 0);
  ctx.app.engine.rateAlert();
  ctx.clock.t += MIN;
  ctx.app.engine.rateAlert();
  const s = await status(ctx);
  assert.equal(s.rate_limit_30m.count, 0);
  assert.equal(s.rate_limit_30m.total, 12);
  assert.equal(s.rate_limit_alert, false);
});

test("rate (e)(f): alert が true のとき、issues への POST は 0 回 (記録のみ・dry-run)", async () => {
  const ctx = await configuredApp();
  await addRuns(ctx, 100, 10, 6);
  ctx.app.engine.rateAlert();
  ctx.clock.t += MIN;
  ctx.app.engine.rateAlert();
  assert.equal((await status(ctx)).rate_limit_alert, true);
  assert.equal(postsToIssues(ctx).length, 0);
  assert.equal((await status(ctx)).mode_launch, "dry-run");
});

test("rate: 第三者の投稿に付いたマーカーは数えない (bot の投稿だけ)", async () => {
  const ctx = await configuredApp();
  await addRuns(ctx, 100, 10, 0);
  for (let i = 0; i < 6; i++) await send(ctx.app, "issue_comment", marker(100 + i, ctx.clock.t - 5 * MIN, { login: "someone-else" }));
  ctx.app.engine.rateAlert();
  ctx.clock.t += MIN;
  ctx.app.engine.rateAlert();
  const s = await status(ctx);
  assert.equal(s.rate_limit_30m.count, 0);
  assert.equal(s.rate_limit_alert, false);
});

test("rate: 窓 (30 分) の外の run・完了していない run・opencode.yaml 以外の workflow は数えない", async () => {
  const ctx = await configuredApp();
  await addRuns(ctx, 100, 10, 6);
  // 窓の外 (完了から 31 分)
  const old = ctx.clock.t - 31 * MIN;
  await send(ctx.app, "workflow_run", runDone(500, old));
  await send(ctx.app, "issue_comment", marker(500, old));
  // 別 workflow (scripts-test.yaml) の run
  await send(ctx.app, "workflow_run", runDone(501, ctx.clock.t - 5 * MIN, ".github/workflows/scripts-test.yaml"));
  await send(ctx.app, "issue_comment", marker(501, ctx.clock.t - 5 * MIN));
  ctx.app.engine.rateAlert();
  const s = await status(ctx);
  assert.equal(s.rate_limit_30m.count, 6);
  assert.equal(s.rate_limit_30m.total, 10);
});

test("rate: 同じ分の二重の評価 (alarm と cron が重なった tick) は 1 回と数える", async () => {
  const ctx = await configuredApp();
  await addRuns(ctx, 100, 10, 6);
  ctx.app.engine.rateAlert();
  ctx.clock.t += 5_000;
  ctx.app.engine.rateAlert();
  const s = await status(ctx);
  assert.equal(s.rate_limit_30m.streak, 1);
  assert.equal(s.rate_limit_alert, false);
});

test("rate: 評価が途切れた (間が空いた) 後の 1 回は連続に数えない", async () => {
  const ctx = await configuredApp();
  await addRuns(ctx, 100, 10, 6);
  ctx.app.engine.rateAlert();
  ctx.clock.t += 10 * MIN;
  ctx.app.engine.rateAlert();
  const s = await status(ctx);
  assert.equal(s.rate_limit_30m.streak, 1);
  assert.equal(s.rate_limit_alert, false);
});

test("rate: マーカーは保存され、再起動 (同じ store から作り直した App) の後も数える", async () => {
  const ctx = await configuredApp();
  await addRuns(ctx, 100, 10, 6);
  const again = new PmApp({ store: ctx.store, cfg: loadConfig({}, {}), storeKey: STORE_KEY, now: () => T0 + 1 * MIN, fetch: ctx.m.f, scheduleSoon: async () => {} });
  again.engine.rateAlert();
  assert.equal(again.engine.status().rate_limit_30m !== null, true);
  assert.equal((again.engine.status() as any).rate_limit_30m.count, 6);
});

test("rateMarkRun: cause=rate_limit と run=N の組だけを読む (text の語・別の原因・別のマーカーは読まない)", () => {
  assert.equal(rateMarkRun("x\n<!-- oc-run-outcome: no-pr reason=stop cause=rate_limit run=123 -->"), 123);
  assert.equal(rateMarkRun("<!-- oc-run-outcome: cause=rate_limit run=45 -->"), 45);
  assert.equal(rateMarkRun("<!-- oc-run-outcome: no-pr reason=stop run=7 -->"), undefined, "原因の無いマーカー");
  assert.equal(rateMarkRun("rate_limit_error run=9 (本文の語)"), undefined, "マーカーの外の語");
  assert.equal(rateMarkRun("<!-- oc-run-outcome: no-pr reason=unknown cause=rate_limit_x run=5 -->"), undefined, "cause の値が完全一致しない");
  assert.equal(rateMarkRun("<!-- oc-run-outcome: no-pr reason=unknown cause=rate_limit -->"), undefined, "run が無い");
});

test("rateHit: 件数 5 以上かつ割合 30% 以上 (境界を含む)", () => {
  assert.equal(rateHit(5, 16), true, "5/16 = 31%");
  assert.equal(rateHit(6, 20), true, "6/20 = 30% ちょうど");
  assert.equal(rateHit(5, 20), false, "25%");
  assert.equal(rateHit(4, 4), false, "件数 4");
  assert.equal(rateHit(0, 0), false);
});
