import { test } from "node:test";
import assert from "node:assert/strict";
import { BOT, configuredApp, j, REPO, T0, type Handler } from "./helpers.ts";
import { SIGNAL_RETRY_MS, SIGNAL_VER } from "../src/engine.ts";
import { MemoryStore } from "../src/kvstore.ts";
import { PM_LIMITS } from "../src/pm.ts";

// 導入より前に保存された状態 (版なし・起票者なし・outcome なし) から、最初の tick の全体同期で補完されることを確かめる (#2652)。
const MIN = 60_000;
const HOUR = 3_600_000;
const R = REPO.full_name;
const iso = (ms: number): string => new Date(ms).toISOString();
const IMPL_BOT = { login: BOT, type: "Bot", assoc: "CONTRIBUTOR" };
const OUTSIDER = { login: "stranger", type: "User", assoc: "NONE" };
const PM_USER = { login: "pycabbage", type: "User", assoc: "OWNER" };
const PERSON_CONTRIB = { login: "pycabbage", type: "User", assoc: "CONTRIBUTOR" };

interface Who {
  login: string;
  type: string;
  assoc: string;
}
const restIssue = (n: number, o: { who?: Who; labels?: string[] } = {}) => {
  const w = o.who ?? IMPL_BOT;
  return {
    number: n,
    title: `[CI-${n}] t${n}`,
    body: "",
    state: "open",
    updated_at: iso(T0 - HOUR),
    labels: (o.labels ?? ["oc:no-pr"]).map((name) => ({ name })),
    user: { login: w.login, type: w.type },
    author_association: w.assoc,
  };
};
const restComment = (n: number, who: Who, body: string, at: number, id: number) => ({
  id,
  issue_url: `https://api.github.com/repos/${R}/issues/${n}`,
  created_at: iso(at),
  user: { login: who.login, type: who.type },
  author_association: who.assoc,
  body,
});
const outcome = (reason: string) => `[run-outcome] 停止\n<!-- oc-run-outcome: no-pr reason=${reason} run=1 -->`;

// 対象 (Bot 起票・oc:no-pr・split) 30 件 (101-130) と、ネガコン 7 件 (201-207)。
function fixture() {
  const issues: any[] = [];
  const comments: any[] = [];
  let id = 1;
  for (let n = 101; n <= 130; n++) {
    issues.push(restIssue(n));
    comments.push(restComment(n, IMPL_BOT, outcome("split"), T0 - 30 * MIN, id++));
  }
  issues.push(restIssue(201, { who: OUTSIDER }));
  comments.push(restComment(201, IMPL_BOT, outcome("split"), T0 - 30 * MIN, id++));
  issues.push(restIssue(202, { labels: [] }));
  comments.push(restComment(202, IMPL_BOT, outcome("split"), T0 - 30 * MIN, id++));
  issues.push(restIssue(203));
  issues.push(restIssue(204, { labels: ["oc:no-pr", "needs-user-input"] }));
  comments.push(restComment(204, IMPL_BOT, outcome("split"), T0 - 30 * MIN, id++));
  issues.push(restIssue(205));
  comments.push(restComment(205, IMPL_BOT, outcome("split"), T0 - 30 * MIN, id++));
  comments.push(restComment(205, PM_USER, "判断しました", T0 - 10 * MIN, id++));
  issues.push(restIssue(206));
  comments.push(restComment(206, IMPL_BOT, outcome("artifact"), T0 - 30 * MIN, id++));
  issues.push(restIssue(207, { who: PERSON_CONTRIB }));
  comments.push(restComment(207, IMPL_BOT, outcome("split"), T0 - 30 * MIN, id++));
  comments.sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
  return { issues, comments };
}

const page = (arr: unknown[], url: string) => {
  const p = Number(new URL(url).searchParams.get("page") ?? 1);
  return arr.slice((p - 1) * 100, p * 100);
};
const isGet = (url: string, method: string, path: string) => method === "GET" && url.includes(path);

function restHandlers(fx: { issues: any[]; comments: any[] }, opts: { failOpen?: () => boolean } = {}): Handler[] {
  return [
    (c) => (isGet(c.url, c.method, `/repos/${R}/issues?state=open`) ? (opts.failOpen?.() ? j({ message: "boom" }, 500) : j(page(fx.issues, c.url))) : undefined),
    (c) => (isGet(c.url, c.method, `/repos/${R}/issues/comments`) ? j(page(fx.comments, c.url)) : undefined),
    (c) => (isGet(c.url, c.method, `/repos/${R}/issues?state=all`) ? j([]) : undefined),
    (c) => (isGet(c.url, c.method, `/repos/${R}/pulls?`) ? j([]) : undefined),
    (c) => (isGet(c.url, c.method, `/repos/${R}/actions/runs`) ? j({ workflow_runs: [] }) : undefined),
    (c) => (c.method === "GET" && /\/issues\/\d+\/events/.test(c.url) ? j([]) : undefined),
    (c) => (c.method === "POST" && c.url.endsWith("/dispatches") ? j(null, 204) : undefined),
  ];
}

const isPmDispatch = (c: { method: string; url: string; body: any }) => c.method === "POST" && c.url.endsWith("/dispatches") && c.body?.event_type === "oc-pm";
const fullSyncCalls = (calls: Array<{ method: string; url: string }>) => calls.filter((c) => isGet(c.url, c.method, `/repos/${R}/issues?state=open`));
const noPrRefs = (app: any) => app.engine.detectPmTargets().filter((t: any) => t.kind === "no_pr").map((t: any) => t.ref).sort((a: number, b: number) => a - b);

// 導入より前の保存値: 版なし・起票者なし・sig (outcome) なし。fullSyncAt は 3 時間前 (周期の 6 時間の内側)。
function staleStore(): MemoryStore {
  const store = new MemoryStore();
  store.put("meta", "main", { fullSyncAt: T0 - 3 * HOUR, reconcileAt: T0 - 10 * MIN });
  for (let n = 101; n <= 130; n++) {
    store.put("issues", String(n), { number: n, title: `[CI-${n}] t${n}`, labels: ["oc:no-pr"], body: "", state: "open", updatedAt: iso(T0 - HOUR), blockedByCount: 0 });
  }
  return store;
}

test("保存値の版が無い状態では、最初の tick の全体同期で補完され、Bot 起票の oc:no-pr split が no_pr の対象になる", async () => {
  const fx = fixture();
  const clock = { t: T0 };
  const ctx = await configuredApp({ now: clock, store: staleStore(), env: { LIVE_DISPATCH: "1" }, handlers: restHandlers(fx) });
  assert.deepEqual(noPrRefs(ctx.app), [], "補完の前は outcome も起票者も無いので対象外 (fail-closed)");
  await ctx.app.engine.tick();
  assert.equal(fullSyncCalls(ctx.m.calls).length, 1, "版が無いので周期を待たず全体同期が 1 回走る");
  assert.equal(ctx.app.engine.meta.signalVer, SIGNAL_VER);
  assert.deepEqual(noPrRefs(ctx.app), Array.from({ length: 30 }, (_, i) => 101 + i), "対象は Bot 起票・oc:no-pr・split の 30 件だけ");
  assert.equal(ctx.app.engine.status().pm_detected.no_pr, 30);
  // PM 起動の上限: 1 時間に送るのは PM_LIMITS.hourMax 件まで。2 回目の tick (1 分後) は同じ時間帯の枠を使い切っている。
  const first = ctx.m.calls.filter(isPmDispatch);
  assert.equal(first.length, PM_LIMITS.hourMax);
  assert.ok(first.every((c) => c.body.client_payload.kind === "no_pr"));
  clock.t += MIN;
  await ctx.app.engine.tick();
  assert.equal(ctx.m.calls.filter(isPmDispatch).length, PM_LIMITS.hourMax, "1 時間の上限を超えない");
});

test("ネガコン: 外部起票者・ラベル無し・outcome 無し・保留ラベル・PM の後続応答・reason が artifact・人間 (CONTRIBUTOR) 起票は対象外", async () => {
  const fx = fixture();
  const ctx = await configuredApp({ now: { t: T0 }, store: staleStore(), handlers: restHandlers(fx) });
  await ctx.app.engine.tick();
  const refs = noPrRefs(ctx.app);
  assert.equal(refs.length, 30, "対照: 同じ補完で対象の 30 件は検出される (空集合で通さない)");
  for (const n of [201, 202, 203, 204, 205, 206, 207]) assert.ok(!refs.includes(n), `#${n} は対象外`);
});

test("版が最新なら、周期内の tick は全体同期せず reconcile だけ行う (REST の回数を増やさない)", async () => {
  const fx = fixture();
  const store = staleStore();
  store.put("meta", "main", { fullSyncAt: T0 - 3 * HOUR, reconcileAt: T0 - 10 * MIN, signalVer: SIGNAL_VER });
  const ctx = await configuredApp({ now: { t: T0 }, store, handlers: restHandlers(fx) });
  await ctx.app.engine.tick();
  assert.equal(fullSyncCalls(ctx.m.calls).length, 0);
  assert.ok(ctx.m.calls.some((c) => isGet(c.url, c.method, `/repos/${R}/issues?state=all`)), "reconcile の一覧は読む");
});

test("補完の全体同期が失敗しても、再試行は SIGNAL_RETRY_MS (15 分) ごと。その間は reconcile だけ行う", async () => {
  const fx = fixture();
  const clock = { t: T0 };
  let failing = true;
  const ctx = await configuredApp({ now: clock, store: staleStore(), handlers: restHandlers(fx, { failOpen: () => failing }) });
  await ctx.app.engine.tick();
  assert.equal(fullSyncCalls(ctx.m.calls).length, 1);
  assert.ok(ctx.app.engine.meta.lastError, "失敗は lastError に残る");
  assert.equal(ctx.app.engine.meta.signalVer, undefined, "完了していないので版は記録しない");
  clock.t += MIN;
  await ctx.app.engine.tick();
  assert.equal(fullSyncCalls(ctx.m.calls).length, 1, "1 分後は再試行しない");
  clock.t += SIGNAL_RETRY_MS;
  failing = false;
  await ctx.app.engine.tick();
  assert.equal(fullSyncCalls(ctx.m.calls).length, 2, "15 分を過ぎたら再試行する");
  assert.equal(ctx.app.engine.meta.signalVer, SIGNAL_VER);
  assert.equal(noPrRefs(ctx.app).length, 30);
});
