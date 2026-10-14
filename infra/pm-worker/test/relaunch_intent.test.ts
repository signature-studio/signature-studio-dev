import { test } from "node:test";
import assert from "node:assert/strict";
import { buildLaunchBody, checkRelaunchIntent, RELAUNCH_MAX_PER_WINDOW } from "../src/launch.ts";
import { parseRelaunchIntent } from "../src/webhook.ts";
import { configuredApp, issuePayload, j, markFresh, runPayload, send, T0, type Call, type Handler } from "./helpers.ts";
import { commentEv, HUMAN, IMPL_BOT, REVIEWER, at, prEv, type Ctx } from "./pm_helpers.ts";

// PM の再投入の意図 (oc-pm-intent: relaunch) は、検査を全て通し、分類で投稿してよい行のときだけ /oc として投稿する。
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

// ---- webhook → tick → POST の統合
// 対象は issue 21 の 1 件 (必要なら issue 22)。既定の状態は『停止報告 (bot・2 時間前) の後の stopped』で、PM の判断待ち = 意図の対象。
// 意図の投稿は focus 行 (picks の /oc には無い) で数える。投稿 0 回のネガコンは、picks も止まっている状態だけで置く。

const FOCUS = "だけを実装して PR を出してください";
const REPORT = "停止します。判断を求めます。";
const GOOD = '<!-- oc-pm-intent: relaunch issue=21 arts="fl-win64 plugins-ott" focus=3 -->';
const HUMAN_INTENT = '<!-- oc-pm-intent: relaunch issue=21 arts="fl-win64" -->';

const writeHandlers: Handler[] = [
  (c: Call) => (c.method === "POST" && /\/issues\/\d+\/comments$/.test(c.url) ? j({ html_url: "x" }, 201) : undefined),
  (c: Call) => (c.method === "POST" && c.url.endsWith("/dispatches") ? j(null, 204) : undefined),
];

const postsTo = (ctx: Ctx, n: number): Call[] => ctx.m.calls.filter((c: Call) => c.method === "POST" && c.url.endsWith(`/issues/${n}/comments`));
const focusPosts = (ctx: Ctx): Call[] => postsTo(ctx, 21).filter((c) => String(c.body?.body).includes(FOCUS));

interface Opts {
  labels?: string[];
  body?: string;
  handlers?: Handler[];
  pre?: (ctx: Ctx) => Promise<void>;
  prep?: (ctx: Ctx) => void;
  hours?: number;
}

// 停止報告 (bot・T_BASE) を置いた issue 21。
async function stopped(env: Record<string, string>, o: Opts = {}): Promise<Ctx> {
  const ctx = await configuredApp({ env, handlers: [...(o.handlers ?? []), ...writeHandlers] });
  assert.equal((await send(ctx.app, "issues", issuePayload(21, { labels: o.labels, body: o.body }))).status, 202);
  assert.equal((await send(ctx.app, "issue_comment", commentEv(21, IMPL_BOT, REPORT, at(0)))).status, 202);
  return ctx;
}

async function tickNow(ctx: Ctx): Promise<void> {
  await markFresh(ctx);
  await ctx.app.engine.tick();
}

async function intentRun(env: Record<string, string>, who: { login: string; type?: string }, marker: string, o: Opts = {}) {
  const ctx = await stopped(env, o);
  await o.pre?.(ctx);
  o.prep?.(ctx);
  assert.equal((await send(ctx.app, "issue_comment", commentEv(21, who, marker, at(5)))).status, 202);
  if (o.hours) ctx.clock.t += o.hours * H;
  await tickNow(ctx);
  return { ctx, posts: postsTo(ctx, 21), counters: (ctx.app.engine.status() as any).counters };
}

test("統合 (live): 停止報告の後の実装 App の意図は 1 回だけ /oc として投稿し、focus 行と素材行を入れる。同じ意図は再投稿しない", async () => {
  const run = await intentRun({ LIVE_LAUNCH: "1" }, IMPL_BOT, GOOD);
  assert.equal(run.posts.length, 1);
  const body: string = run.posts[0].body.body;
  assert.ok(body.startsWith("/oc oc_actions_allow_write\noc_artifacts: fl-win64 plugins-ott\n"));
  assert.ok(body.includes("oc_artifacts: fl-win64 plugins-ott"));
  assert.ok(body.includes("この issue の受入条件 3 だけを実装して PR を出してください"));
  assert.equal(run.counters.intentLaunched, 1);
  assert.equal(run.counters.launched, 1);
  assert.equal(run.ctx.app.engine.s.botLast["21"]?.body, REPORT, "意図の投稿は停止報告の窓 (botLast) を動かさない");
  await tickNow(run.ctx);
  assert.equal(postsTo(run.ctx, 21).length, 1, "処理済みの意図は再投稿しない");
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

test("統合 (c 窓): 24 時間に 3 回投稿済みなら 4 回目は投稿せず limit を記録する。25 時間前の投稿は数えないので投稿する", async () => {
  const limited = await intentRun({ LIVE_LAUNCH: "1" }, IMPL_BOT, GOOD, {
    prep: (ctx) => ctx.store.put("relaunch", "it:21", { posted: [T0 - 1 * H, T0 - 2 * H, T0 - 3 * H] }),
  });
  assert.equal(limited.posts.length, 0);
  assert.equal(limited.counters.intentRejected?.limit, 1);
  const window = await intentRun({ LIVE_LAUNCH: "1" }, IMPL_BOT, GOOD, {
    prep: (ctx) => ctx.store.put("relaunch", "it:21", { posted: [T0 - 25 * H, T0 - 2 * H, T0 - 3 * H] }),
  });
  assert.equal(window.posts.length, 1);
});

// 分類で投稿してはいけない 6 状態 (指摘 B1) と、oc:no-pr の上限・未観測の launch。いずれも投稿 0 回で、理由を数える。
const negatives: Array<[string, string, Opts]> = [
  ["needs-user-input", "user", { labels: ["needs-user-input"] }],
  ["pm-apply", "user", { labels: ["pm-apply"] }],
  ["oc:stuck", "user", { labels: ["oc:stuck"] }],
  ["oc:hold (#2651)", "hold", { labels: ["oc:hold"] }],
  ["open PR 21-x (started)", "started", { pre: async (ctx) => assert.equal((await send(ctx.app, "pull_request", { ...prEv(91), pull_request: { ...prEv(91).pull_request, head: { ref: "21-x" } } })).status, 202) }],
  [
    "依存: #22 (open) (blocked)",
    "blocked",
    {
      body: "依存: #22",
      pre: async (ctx) => assert.equal((await send(ctx.app, "issues", issuePayload(22))).status, 202),
    },
  ],
  ["oc:no-pr + 上限 (np=3・cooldown 後)", "stopped", { labels: ["oc:no-pr"], hours: 7, prep: (ctx) => ctx.store.put("relaunch", "np:21", { count: 3 }) }],
  [
    "launch 未観測 (failed)",
    "stopped",
    { prep: (ctx) => ctx.store.put("launchObs", "21", { state: "failed", at: at(0), changedAt: at(0) }) },
  ],
];

for (const [name, reason, o] of negatives) {
  test(`ネガコン (B1): ${name} は意図で /oc を投稿せず、理由 ${reason} を数える`, async () => {
    const run = await intentRun({ LIVE_LAUNCH: "1" }, IMPL_BOT, GOOD, o);
    assert.equal(run.posts.length, 0, name);
    assert.equal(focusPosts(run.ctx).length, 0, name);
    assert.equal(run.counters.intentRejected?.[reason], 1, name);
  });
}

test("統合 (oc:no-pr の cooldown 中): 投稿せず、処理済みにもしない。cooldown が過ぎたら投稿する", async () => {
  const ctx = await stopped({ LIVE_LAUNCH: "1" }, { labels: ["oc:no-pr"] });
  assert.equal((await send(ctx.app, "issue_comment", commentEv(21, IMPL_BOT, GOOD, at(5)))).status, 202);
  await tickNow(ctx);
  assert.equal(postsTo(ctx, 21).length, 0);
  assert.equal((ctx.app.engine.status() as any).counters.intentRejected, undefined, "待ちは拒否として数えない");
  ctx.clock.t += 5 * H; // 報告 (10:00) から 7 時間。既定の cooldown (6 時間) を過ぎる
  await tickNow(ctx);
  assert.equal(postsTo(ctx, 21).length, 1);
  assert.equal(focusPosts(ctx).length, 1, "意図の本文 (focus 行) で投稿された");
});

test("統合 (prio:critical の cooldown): 報告から 3 時間で critical の意図は投稿し、通常の oc:no-pr は 6 時間まで待つ (ネガコン)", async () => {
  const crit = await stopped({ LIVE_LAUNCH: "1" }, { labels: ["oc:no-pr", "prio:critical"] });
  const norm = await stopped({ LIVE_LAUNCH: "1" }, { labels: ["oc:no-pr"] });
  for (const ctx of [crit, norm]) assert.equal((await send(ctx.app, "issue_comment", commentEv(21, IMPL_BOT, GOOD, at(5)))).status, 202);
  for (const ctx of [crit, norm]) {
    await tickNow(ctx); // 報告 (10:00) から 2 時間
    assert.equal(postsTo(ctx, 21).length, 0);
    ctx.clock.t += 1 * H; // 報告から 3 時間
    await tickNow(ctx);
  }
  assert.equal(focusPosts(crit).length, 1, "critical は 3 時間で、意図の本文 (focus 行) を投稿する (picks の素の投稿ではない)");
  assert.equal(postsTo(norm, 21).length, 0, "通常は 6 時間まで投稿しない");
});

test("統合 (picks との競合): 同じ tick で ready の issue に意図があれば、意図の投稿が focus 付きで入り、picks は投稿しない", async () => {
  const ctx = await configuredApp({ env: { LIVE_LAUNCH: "1" }, handlers: writeHandlers });
  assert.equal((await send(ctx.app, "issues", issuePayload(22))).status, 202);
  const intent22 = '<!-- oc-pm-intent: relaunch issue=22 arts="fl-win64 plugins-ott" focus=3 -->';
  assert.equal((await send(ctx.app, "issue_comment", commentEv(22, IMPL_BOT, intent22, at(5)))).status, 202);
  await tickNow(ctx);
  const ps = postsTo(ctx, 22);
  assert.equal(ps.length, 1);
  assert.ok(String(ps[0].body.body).includes(FOCUS), "picks が先に投稿して、意図が focus なしで処理済みになることはない");
});

test("統合 (書き手の競合): 第三者の意図は、実装 App の意図の前後どちらに来ても置き換えない", async () => {
  for (const order of [
    [
      [IMPL_BOT, GOOD],
      [HUMAN, HUMAN_INTENT],
    ],
    [
      [HUMAN, HUMAN_INTENT],
      [IMPL_BOT, GOOD],
    ],
  ] as const) {
    const ctx = await stopped({ LIVE_LAUNCH: "1" });
    for (const [i, [who, marker]] of order.entries()) {
      assert.equal((await send(ctx.app, "issue_comment", commentEv(21, who, marker, at(5 + i)))).status, 202);
    }
    await tickNow(ctx);
    const ps = postsTo(ctx, 21);
    assert.equal(ps.length, 1);
    assert.ok(String(ps[0].body.body).includes("oc_artifacts: fl-win64 plugins-ott"), "実装 App の素材行で投稿する");
    assert.equal((ctx.app.engine.status() as any).counters.intentRejected, undefined, "第三者の意図は残らない (拒否として数えない)");
  }
});

test("統合 (中断の引き継ぎ): 意図の投稿が 403 で止まったら、同じ tick の picks も投稿しない", async () => {
  const deny: Handler = (c: Call) => (c.method === "POST" && /\/issues\/21\/comments$/.test(c.url) ? j({ message: "forbidden" }, 403) : undefined);
  const ctx = await stopped({ LIVE_LAUNCH: "1" }, { handlers: [deny] });
  assert.equal((await send(ctx.app, "issues", issuePayload(22))).status, 202);
  assert.equal((await send(ctx.app, "issue_comment", commentEv(21, IMPL_BOT, GOOD, at(5)))).status, 202);
  await tickNow(ctx);
  assert.equal(postsTo(ctx, 21).length, 1, "意図は 1 回試す");
  assert.equal(postsTo(ctx, 22).length, 0, "止まった後は picks も投稿しない");
  assert.equal((ctx.app.engine.status() as any).counters.launched, 0);
});

// 分類が確定する前 (blocked_by が未同期) の ready な issue は、意図を待つ。拒否にも処理済みにもしない (指摘 B1 round 2)。
test("統合 (unknown): blocked_by が未同期の ready な issue の意図は、投稿も拒否もせず待つ。同期して依存が無いと確定したら投稿する", async () => {
  const ctx = await configuredApp({ env: { LIVE_LAUNCH: "1" }, handlers: writeHandlers });
  assert.equal((await send(ctx.app, "issues", issuePayload(21, { blocked: 1 }))).status, 202);
  assert.equal((await send(ctx.app, "issue_comment", commentEv(21, IMPL_BOT, GOOD, at(5)))).status, 202);
  await tickNow(ctx);
  assert.equal(postsTo(ctx, 21).length, 0);
  assert.equal((ctx.app.engine.status() as any).counters.intentRejected, undefined, "待ちは拒否として数えない");
  assert.equal(ctx.store.get<{ seen?: string }>("relaunch", "it:21")?.seen, undefined, "待ちは処理済みにしない");
  assert.equal((await send(ctx.app, "issues", issuePayload(21))).status, 202);
  await tickNow(ctx);
  assert.equal(focusPosts(ctx).length, 1, "依存が無いと確定した後の tick で投稿される");
});

// 子 issue を持つ親は、意図でも着手させない (ネガコン。指摘 M2・round 3 B1)。停止報告に素材行があるかどうかに依らず、PR の有無で分類 (stopped / blocked) した行で拒否する。
const PARENT_CASES: Array<[string, string, boolean, string]> = [
  ["停止報告に素材行あり・PR あり (closed)", `${REPORT}\noc_artifacts: fl-win64`, true, "stopped"],
  ["停止報告に素材行なし・PR あり (closed)", REPORT, true, "stopped"],
  ["停止報告に素材行なし・PR なし", REPORT, false, "blocked"],
];
for (const [name, report, withPr, reason] of PARENT_CASES) {
  test(`ネガコン (M2・B1): 子 issue を持つ親 (${name}) は意図で /oc を投稿せず、${reason} として数える`, async () => {
    const ctx = await configuredApp({ env: { LIVE_LAUNCH: "1" }, handlers: writeHandlers });
    assert.equal((await send(ctx.app, "issues", issuePayload(21))).status, 202);
    assert.equal((await send(ctx.app, "issues", issuePayload(22, { body: "親: #21" }))).status, 202);
    if (withPr) {
      const pr = prEv(91);
      assert.equal((await send(ctx.app, "pull_request", { ...pr, pull_request: { ...pr.pull_request, head: { ref: "21-x" }, state: "closed" } })).status, 202);
    }
    assert.equal((await send(ctx.app, "issue_comment", commentEv(21, IMPL_BOT, report, at(0)))).status, 202);
    assert.equal((await send(ctx.app, "issue_comment", commentEv(21, IMPL_BOT, GOOD, at(5)))).status, 202);
    await tickNow(ctx);
    assert.equal(postsTo(ctx, 21).length, 0, name);
    assert.equal((ctx.app.engine.status() as any).counters.intentRejected?.[reason], 1, name);
  });
}

// 実行中の run だけで started の issue は、意図を捨てずに待つ (指摘 m1 round 3)。run が完了して停止報告の行に入ったら投稿する。
test("統合 (m1): 実行中の run だけで started の issue の意図は待つ。run が完了して停止報告の行に入ったら投稿する", async () => {
  const ctx = await stopped({ LIVE_LAUNCH: "1" });
  assert.equal((await send(ctx.app, "workflow_run", runPayload(31, "in_progress", { event: "issue_comment", title: "[CI-21] t21" }))).status, 202);
  assert.equal((await send(ctx.app, "issue_comment", commentEv(21, IMPL_BOT, GOOD, at(5)))).status, 202);
  await tickNow(ctx);
  assert.equal(postsTo(ctx, 21).length, 0);
  assert.equal((ctx.app.engine.status() as any).counters.intentRejected, undefined, "待ちは拒否として数えない");
  assert.equal(ctx.store.get<{ seen?: string }>("relaunch", "it:21")?.seen, undefined, "待ちは処理済みにしない");
  assert.equal((await send(ctx.app, "workflow_run", runPayload(31, "completed", { event: "issue_comment", title: "[CI-21] t21", at: "2026-10-14T13:00:00Z" }))).status, 202);
  await tickNow(ctx);
  assert.equal(focusPosts(ctx).length, 1, "run の完了後の tick で投稿される");
});

// 第三者の意図を先に処理した後で、created_at の古い実装 App の意図が遅れて届いても、捨てずに投稿する (指摘 M3 round 2)。
test("統合 (M3 順序): 第三者の意図を処理した後に、より古い created_at の実装 App の意図が届いても投稿する", async () => {
  const ctx = await stopped({ LIVE_LAUNCH: "1" });
  assert.equal((await send(ctx.app, "issue_comment", commentEv(21, HUMAN, HUMAN_INTENT, at(5)))).status, 202);
  await tickNow(ctx);
  assert.equal(postsTo(ctx, 21).length, 0);
  assert.equal((ctx.app.engine.status() as any).counters.intentRejected?.author, 1);
  assert.equal((await send(ctx.app, "issue_comment", commentEv(21, IMPL_BOT, GOOD, at(3)))).status, 202);
  await tickNow(ctx);
  assert.equal(focusPosts(ctx).length, 1, "実装 App の意図は時刻に依らず処理される");
});
