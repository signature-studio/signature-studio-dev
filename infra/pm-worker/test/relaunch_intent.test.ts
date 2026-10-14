import { test } from "node:test";
import assert from "node:assert/strict";
import { buildLaunchBody, checkRelaunchIntent, RELAUNCH_MAX_PER_WINDOW } from "../src/launch.ts";
import { parseRelaunchIntent } from "../src/webhook.ts";
import { configuredApp, issuePayload, j, markFresh, send, T0, type Call } from "./helpers.ts";
import { commentEv, HUMAN, IMPL_BOT, REVIEWER, at } from "./pm_helpers.ts";

// PM の再投入の意図 (oc-pm-intent: relaunch) は、検査を全て通ったときだけ /oc として投稿する。
// (a) allowlist 外の素材 (b) 実装 App 以外の書き手 (c) 24 時間で 4 回目 (d) focus=10 は拒否 (ネガコン)。

const H = 3_600_000;
const r = (o: Partial<{ bot: boolean; issue: string; arts: string; focus: string | null }> = {}) => ({
  bot: true,
  issue: "21",
  arts: "fl-win64 plugins-ott",
  focus: null,
  ...o,
});
const OK = { ok: true as const, art: "oc_artifacts: fl-win64 plugins-ott" };

test("解析: 例のマーカーから issue・arts・focus を字句のまま取り出す。無ければ null", () => {
  assert.deepEqual(parseRelaunchIntent('x <!-- oc-pm-intent: relaunch issue=778 arts="fl-win64 plugins-ott" focus=778 --> y'), {
    issue: "778",
    arts: "fl-win64 plugins-ott",
    focus: "778",
  });
  assert.deepEqual(parseRelaunchIntent('<!-- oc-pm-intent: relaunch issue=5 arts="fl-win64" -->'), { issue: "5", arts: "fl-win64", focus: null });
  assert.equal(parseRelaunchIntent("<!-- oc-pm-intent: stuck pr=5 reason=code -->"), null);
  assert.equal(parseRelaunchIntent("本文だけ"), null);
});

test("検査: 全て通れば、allowlist の素材行と focus (任意) を返す", () => {
  assert.deepEqual(checkRelaunchIntent(21, r(), [], T0), OK);
  assert.deepEqual(checkRelaunchIntent(21, r({ focus: "3" }), [], T0), { ...OK, focus: 3 });
});

test("ネガコン (a): allowlist 外の素材名・空の素材・none は拒否", () => {
  for (const arts of ["fl-win64 evil-thing", "fl-win64 `rm -rf /`", "", "none"]) {
    assert.deepEqual(checkRelaunchIntent(21, r({ arts }), [], T0), { ok: false, reason: "arts" }, arts);
  }
});

test("ネガコン (b): 実装 App 以外が書いた意図は拒否。issue が違えば拒否", () => {
  assert.deepEqual(checkRelaunchIntent(21, r({ bot: false }), [], T0), { ok: false, reason: "author" });
  assert.deepEqual(checkRelaunchIntent(21, r({ issue: "22" }), [], T0), { ok: false, reason: "issue" });
});

test("ネガコン (c): 24 時間に 3 回投稿済みなら 4 回目は拒否。窓の外 (25 時間前) は数えない", () => {
  assert.equal(RELAUNCH_MAX_PER_WINDOW, 3);
  assert.deepEqual(checkRelaunchIntent(21, r(), [T0 - 1 * H, T0 - 2 * H, T0 - 3 * H], T0), { ok: false, reason: "limit" });
  assert.deepEqual(checkRelaunchIntent(21, r(), [T0 - 25 * H, T0 - 2 * H, T0 - 3 * H], T0), OK);
});

test("ネガコン (d): focus=10 (1〜9 の外) は拒否。0 や文字も拒否", () => {
  for (const focus of ["10", "0", "x"]) {
    assert.deepEqual(checkRelaunchIntent(21, r({ focus }), [], T0), { ok: false, reason: "focus" }, focus);
  }
});

test("本文: focus があるときだけ受入条件の 1 行を足す。自由文は入らない", () => {
  const withFocus = buildLaunchBody("oc_artifacts: fl-win64 plugins-ott", 3);
  assert.equal(withFocus.split("\n").filter((l) => l.includes("だけを実装して PR を出してください")).length, 1);
  assert.ok(withFocus.includes("この issue の受入条件 3 だけを実装して PR を出してください。他の条件は子 issue にしてください。"));
  const without = buildLaunchBody("oc_artifacts: fl-win64 plugins-ott");
  assert.ok(!without.includes("この issue の受入条件"));
  assert.throws(() => buildLaunchBody("oc_artifacts: fl-win64", 10));
});

// ---- webhook → tick → POST の統合 (意図経路だけが動くよう、oc:stuck の issue を 1 件だけ置く)

const writeHandlers = [
  (c: Call) => (c.method === "POST" && /\/issues\/\d+\/comments$/.test(c.url) ? j({ html_url: "x" }, 201) : undefined),
  (c: Call) => (c.method === "POST" && c.url.endsWith("/dispatches") ? j(null, 204) : undefined),
];

async function intentRun(env: Record<string, string>, who: { login: string; type?: string }, marker: string, prep?: (store: any) => void) {
  const ctx = await configuredApp({ env, handlers: writeHandlers });
  assert.equal((await send(ctx.app, "issues", issuePayload(21, { labels: ["oc:stuck"] }))).status, 202);
  prep?.(ctx.store);
  assert.equal((await send(ctx.app, "issue_comment", commentEv(21, who, `停止しました。${marker}`, at(5)))).status, 202);
  await markFresh(ctx);
  await ctx.app.engine.tick();
  const posts = ctx.m.calls.filter((c: Call) => c.method === "POST" && c.url.endsWith("/issues/21/comments"));
  return { ctx, posts, counters: (ctx.app.engine.status() as any).counters };
}

const GOOD = '<!-- oc-pm-intent: relaunch issue=21 arts="fl-win64 plugins-ott" focus=3 -->';

test("統合 (live): 実装 App の意図は 1 回だけ /oc として投稿し、focus 行と素材行を入れる。同じ意図は再投稿しない", async () => {
  const run = await intentRun({ LIVE_LAUNCH: "1" }, IMPL_BOT, GOOD);
  assert.equal(run.posts.length, 1);
  const body: string = run.posts[0].body.body;
  assert.ok(body.startsWith("/oc oc_actions_allow_write\noc_artifacts: fl-win64 plugins-ott\n"));
  assert.ok(body.includes("oc_artifacts: fl-win64 plugins-ott"));
  assert.ok(body.includes("この issue の受入条件 3 だけを実装して PR を出してください"));
  assert.equal(run.counters.intentLaunched, 1);
  assert.equal(run.counters.launched, 1);
  await markFresh(run.ctx);
  await run.ctx.app.engine.tick();
  assert.equal(run.ctx.m.calls.filter((c: Call) => c.method === "POST" && c.url.endsWith("/issues/21/comments")).length, 1, "処理済みの意図は再投稿しない");
});

test("統合 (dry-run 既定): 投稿せず、would の記録だけ残す", async () => {
  const run = await intentRun({}, IMPL_BOT, GOOD);
  assert.equal(run.posts.length, 0);
  assert.equal(run.counters.intentWouldLaunch, 1);
  assert.equal(run.counters.intentLaunched ?? 0, 0);
});

test("統合 (ネガコン a/b/d): 拒否は投稿 0 回で、理由を counters に記録する", async () => {
  const cases: Array<[string, { login: string; type?: string }, string, string]> = [
    ["arts", IMPL_BOT, '<!-- oc-pm-intent: relaunch issue=21 arts="fl-win64 evil-thing" -->', "arts"],
    ["author(reviewer)", { login: REVIEWER, type: "Bot" }, GOOD, "author"],
    ["author(human)", HUMAN, GOOD, "author"],
    ["focus=10", IMPL_BOT, '<!-- oc-pm-intent: relaunch issue=21 arts="fl-win64" focus=10 -->', "focus"],
  ];
  for (const [name, who, marker, reason] of cases) {
    const run = await intentRun({ LIVE_LAUNCH: "1" }, who, marker);
    assert.equal(run.posts.length, 0, name);
    assert.equal(run.counters.intentRejected?.[reason], 1, name);
  }
});

test("ネガコン (c): 24 時間に 3 回投稿済みなら、4 回目は投稿せず limit を記録する", async () => {
  const run = await intentRun({ LIVE_LAUNCH: "1" }, IMPL_BOT, GOOD, (store) => {
    store.put("relaunch", "it:21", { posted: [T0 - 1 * H, T0 - 2 * H, T0 - 3 * H] });
  });
  assert.equal(run.posts.length, 0);
  assert.equal(run.counters.intentRejected?.limit, 1);
});

test("統合 (c 窓): 25 時間前の投稿は数えないので投稿する", async () => {
  const run = await intentRun({ LIVE_LAUNCH: "1" }, IMPL_BOT, GOOD, (store) => {
    store.put("relaunch", "it:21", { posted: [T0 - 25 * H, T0 - 2 * H, T0 - 3 * H] });
  });
  assert.equal(run.posts.length, 1);
});

