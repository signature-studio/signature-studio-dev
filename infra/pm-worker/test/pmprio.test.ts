// oc-pm の送る順の区分 (prio:critical → normal → low) と、抑止 (dup・hour・ref・kind) が優先度で破られないこと (#3703)。
// 単体は selectDispatch に対象と履歴を直接渡す。検出 (detectPm) と送信 (pmDispatch)・/status は webhook から組んだ状態で確かめる。
import { test } from "node:test";
import assert from "node:assert/strict";
import type { Prio } from "../src/launch.ts";
import { KIND_LIMITS, selectDispatch, type HistoryEntry, type PmTarget } from "../src/pm.ts";
import { configuredApp, j, markFresh, REPO, T0, type Call } from "./helpers.ts";
import { at, commentEv, HUMAN, IMPL, issueEv, outcomeBody, prEv, REVIEWER, send, type Ctx } from "./pm_helpers.ts";

const NOW = T0;
const tg = (kind: PmTarget["kind"], ref: number, prio: Prio = "normal"): PmTarget => ({ kind, ref, at: at(0), prio });
// minAgo 分前に送った履歴。prio を省くと古い保存値 (prio 無し) になる。
const h = (kind: string, ref: number, minAgo: number, prio?: Prio): HistoryEntry => ({ kind, ref, at: NOW - minAgo * 60_000, ...(prio ? { prio } : {}) });
const sel = (targets: PmTarget[], history: HistoryEntry[] = []) => selectDispatch(NOW, targets, history);
const names = (xs: Array<{ kind: string; ref: number }>) => xs.map((x) => `${x.kind}#${x.ref}`);

const pmCalls = (calls: Call[]) => calls.filter((c) => c.method === "POST" && c.url.endsWith("/dispatches") && c.body?.event_type === "oc-pm");
const sendAll = async (ctx: Ctx, items: Array<[string, unknown]>) => {
  for (const [ev, p] of items) assert.equal((await send(ctx.app, ev, p)).status, 202);
};
const live = (clock = { t: T0 }) => configuredApp({ live: true, now: clock, handlers: [(c) => (c.url.endsWith("/dispatches") ? j(null, 204) : undefined)] });
const gh = async (ctx: Ctx) => (ctx.app.engine as any).d.gh();
const noPrOutcome = (n: number, reason = "split"): Array<[string, unknown]> => [["issue_comment", commentEv(n, { login: IMPL }, outcomeBody(reason), at(10))]];

// ブランチ名の番号 (<N>-<slug>) を指定できる PR。prEv の head.ref は n-x なので、指す issue を変えるときはこれを使う。
const prOn = (n: number, branch: string, o: { labels?: string[]; body?: string } = {}) => {
  const ev = prEv(n, { labels: o.labels, body: o.body, at: at(5) });
  return { ...ev, pull_request: { ...ev.pull_request, head: { ref: branch } } };
};
// 差し戻しの review。PR の本体 (ref・labels・body) は保ち、時刻だけ進める (applyReview は PR 本体も反映する)。
const changes = (pr: ReturnType<typeof prOn>, min: number, body = "- [blocking] PM 判断が必要です") => ({
  action: "submitted",
  repository: REPO,
  pull_request: { ...pr.pull_request, updated_at: at(min) },
  review: { user: { login: REVIEWER }, state: "changes_requested", body, submitted_at: at(min) },
});

// ---------------------------------------------------------------- 単体: 整列 (selectDispatch)
test("(a) 同じ kind: 未送信の normal の no_pr 80 件 (785〜864) より後の critical の no_pr #3466 も、毎時 72 件の枠に入る (先頭)", () => {
  const normal = Array.from({ length: 80 }, (_, i) => tg("no_pr", 785 + i));
  const r = sel([...normal, tg("no_pr", 3466, "critical")]);
  assert.equal(r.send.length, 72);
  assert.deepEqual(names(r.send), ["no_pr#3466", ...Array.from({ length: 71 }, (_, i) => `no_pr#${785 + i}`)]);
  assert.deepEqual(r.skipped.map((x) => x.why), Array(9).fill("hour"), "normal の残り 9 件は毎時の上限で見送り");
});

test("(b) kind をまたぐ: critical の no_pr は、同じ tick で送られる normal の needs_decision より先", () => {
  // 入力は detectPm の順 (kind の順): needs_decision が先。
  const r = sel([tg("needs_decision", 500), tg("no_pr", 3466, "critical")]);
  assert.deepEqual(names(r.send), ["no_pr#3466", "needs_decision#500"]);
  assert.deepEqual(r.skipped, []);
});

test("(c) prio:low は最後: low の no_pr は、normal の対象より後。枠が足りないときは low が見送られる", () => {
  const low = tg("no_pr", 10, "low");
  assert.deepEqual(names(sel([low, tg("no_pr", 20), tg("stuck", 30)]).send), ["no_pr#20", "stuck#30", "no_pr#10"]);
  const full = Array.from({ length: 72 }, (_, i) => tg("no_pr", 100 + i));
  const r = sel([low, ...full]);
  assert.deepEqual(names(r.send), names(full));
  assert.deepEqual(r.skipped, [{ kind: "no_pr", ref: 10, why: "hour" }]);
});

test("(e) ネガコン (dup): critical でも、60 分以内に送った同じ (kind, ref) は送らない。60 分たてば送る", () => {
  const r = sel([tg("no_pr", 3466, "critical"), tg("no_pr", 785)], [h("no_pr", 3466, 59, "critical")]);
  assert.deepEqual(names(r.send), ["no_pr#785"]);
  assert.deepEqual(r.skipped, [{ kind: "no_pr", ref: 3466, why: "dup" }]);
  assert.deepEqual(names(sel([tg("no_pr", 3466, "critical")], [h("no_pr", 3466, 60, "critical")]).send), ["no_pr#3466"]);
});

test("(e) ネガコン (ref): 同じ ref への 24 時間 6 回の上限は、critical でも破らない。5 回までなら送る", () => {
  const six = [120, 180, 240, 300, 360, 420].map((m) => h("no_pr", 3466, m, "critical"));
  assert.deepEqual(sel([tg("no_pr", 3466, "critical")], six).skipped, [{ kind: "no_pr", ref: 3466, why: "ref" }]);
  assert.deepEqual(names(sel([tg("no_pr", 3466, "critical")], six.slice(1)).send), ["no_pr#3466"]);
});

test("(e) ネガコン (hour): 毎時 72 件の上限は、critical でも破らない", () => {
  const full = Array.from({ length: 72 }, (_, i) => h("no_pr", 100 + i, 1, "normal"));
  const r = sel([tg("no_pr", 3466, "critical")], full);
  assert.deepEqual(r.send, []);
  assert.deepEqual(r.skipped, [{ kind: "no_pr", ref: 3466, why: "hour" }]);
});

test("(e) ネガコン (kind): refs_orphan の 1 日の上限 (KIND_LIMITS.refs_orphan.dayMax) は、critical でも破らない", () => {
  const max = KIND_LIMITS.refs_orphan!.dayMax;
  const full = Array.from({ length: max }, (_, i) => h("refs_orphan", 500 + i, 120 + i, "normal"));
  assert.deepEqual(sel([tg("refs_orphan", 900, "critical")], full).skipped, [{ kind: "refs_orphan", ref: 900, why: "kind" }]);
});

test("(f) 回帰: prio が無い入力 (全て normal) と、prio の無い古い履歴は、従来の順 (未送信の先・送信済みは古い順・入力順) のまま", () => {
  assert.deepEqual(names(sel([tg("no_pr", 5), tg("needs_decision", 4)]).send), ["no_pr#5", "needs_decision#4"], "未送信は入力順");
  assert.deepEqual(names(sel([tg("no_pr", 1), tg("no_pr", 2)], [h("no_pr", 1, 100)]).send), ["no_pr#2", "no_pr#1"], "未送信の 2 が、送信済みの 1 より先");
  assert.deepEqual(names(sel([tg("no_pr", 1), tg("no_pr", 2)], [h("no_pr", 1, 70), h("no_pr", 2, 100)]).send), ["no_pr#2", "no_pr#1"], "送信済み同士は古い送信から");
  assert.deepEqual(
    names(sel([tg("no_pr", 1), tg("no_pr", 2)], [h("no_pr", 1, 70, "normal"), h("no_pr", 2, 100, "normal")]).send),
    ["no_pr#2", "no_pr#1"],
    "prio:normal の履歴も同じ",
  );
});

// ---------------------------------------------------------------- 検出 (detectPm の prio)
test("検出 (issue 起点): no_pr・user_answered は issue 自身のラベル、refs_orphan は親 issue のラベルで prio を決める", async () => {
  const ctx = await configuredApp();
  const merged = (n: number, body: string) => {
    const ev = prEv(n, { body, at: at(5) });
    return { ...ev, action: "closed", pull_request: { ...ev.pull_request, state: "closed", merged_at: at(5), updated_at: at(5) } };
  };
  await sendAll(ctx, [
    ["issues", issueEv(3466, { labels: ["oc:no-pr", "prio:critical"] })],
    ...noPrOutcome(3466),
    ["issues", issueEv(3470, { labels: ["oc:no-pr", "prio:low"] })],
    ...noPrOutcome(3470, "stop"),
    ["issues", issueEv(3471, { labels: ["oc:no-pr"] })],
    ...noPrOutcome(3471),
    ["issues", issueEv(3472, { labels: ["needs-user-input", "prio:critical"], action: "labeled", label: "needs-user-input", at: at(10) })],
    ["issue_comment", commentEv(3472, HUMAN, "A", at(12))],
    ["issues", issueEv(3473, { labels: ["prio:critical"], title: "[CI-3473] 親", at: at(1) })],
    ["pull_request", merged(700, "Refs #3473")],
  ]);
  assert.deepEqual(ctx.app.engine.detectPmTargets().map((t) => `${t.kind}#${t.ref}:${t.prio}`), [
    "user_answered#3472:critical",
    "no_pr#3466:critical",
    "no_pr#3470:low",
    "no_pr#3471:normal",
    "refs_orphan#3473:critical",
  ]);
});

test("検出 (PR 起点): stuck・needs_decision の prio は、PR 自体のラベルと指す issue (ブランチ名・Closes/Refs・本文の #N) の高い方。引けなければ normal", async () => {
  const ctx = await configuredApp();
  const cases: Array<[number, string, { labels?: string[]; body?: string }]> = [
    [601, "3466-x", {}],
    [602, "9100-x", { labels: ["prio:low"], body: "Refs #3420" }],
    [603, "9101-x", { body: "Closes #3466" }],
    [604, "9102-x", { labels: ["prio:critical"] }],
    [605, "3420-x", { labels: ["prio:critical"] }],
    [606, "3478-x", { labels: ["prio:low"] }],
    [607, "9103-x", { body: "#9999" }],
    [608, "9104-x", { labels: ["prio:low"] }],
    // PR 自体のラベルが無ければ normal (low の issue より高い)
    [609, "9105-x", { body: "Refs #3420" }],
  ];
  await sendAll(ctx, [
    ["issues", issueEv(3466, { labels: ["prio:critical"] })],
    ["issues", issueEv(3478, {})],
    ["issues", issueEv(3420, { labels: ["prio:low"] })],
  ]);
  for (const [n, branch, o] of cases) {
    const p = prOn(n, branch, o);
    await sendAll(ctx, [["pull_request", p], ["pull_request_review", changes(p, 10)]]);
  }
  assert.deepEqual(ctx.app.engine.detectPmTargets().map((t) => [t.ref, t.prio]), [
    [601, "critical"],
    [602, "low"],
    [603, "critical"],
    [604, "critical"],
    [605, "critical"],
    [606, "normal"],
    [607, "normal"],
    [608, "low"],
    [609, "normal"],
  ]);
});

// ---------------------------------------------------------------- 送信 (pmDispatch・live)
test("送信 (a): 未送信の normal の no_pr 80 件 (785〜864) があっても、critical の no_pr #3466 が毎時 72 件の最初の枠に入る", async () => {
  const ctx = await live();
  const items: Array<[string, unknown]> = [];
  for (let n = 785; n <= 864; n++) items.push(["issues", issueEv(n, { labels: ["oc:no-pr"] })], ...noPrOutcome(n));
  items.push(["issues", issueEv(3466, { labels: ["oc:no-pr", "prio:critical"] })], ...noPrOutcome(3466));
  await sendAll(ctx, items);
  await markFresh(ctx);
  const r = await ctx.app.engine.pmDispatch(await gh(ctx));
  assert.equal(r.sent.length, 72);
  assert.deepEqual(names(r.sent.slice(0, 2)), ["no_pr#3466", "no_pr#785"]);
  assert.equal(pmCalls(ctx.m.calls).length, 72);
  assert.equal(pmCalls(ctx.m.calls)[0].body.client_payload.ref, 3466);
});

test("送信 (d): PR 起点の needs_decision は、指す issue が critical の PR を、normal の PR より先に送る。履歴に prio を残す", async () => {
  const ctx = await live();
  const p500 = prOn(500, "3478-x");
  const p501 = prOn(501, "3466-x");
  await sendAll(ctx, [
    ["issues", issueEv(3478, {})],
    ["issues", issueEv(3466, { labels: ["prio:critical"] })],
    ["pull_request", p500],
    ["pull_request_review", changes(p500, 10)],
    ["pull_request", p501],
    ["pull_request_review", changes(p501, 10)],
  ]);
  await markFresh(ctx);
  const r = await ctx.app.engine.pmDispatch(await gh(ctx));
  assert.deepEqual(names(r.sent), ["needs_decision#501", "needs_decision#500"]);
  assert.deepEqual(
    ctx.store.get<any[]>("meta", "pmDispatch")?.map((x) => [x.ref, x.prio]),
    [
      [501, "critical"],
      [500, "normal"],
    ],
  );
});

// ---------------------------------------------------------------- /status
test("/status: pm_dispatch_1h_by_prio は直近 1 時間の送信を区分別に数え、pm_detected.critical は critical の検出数。prio の無い古い履歴は normal", async () => {
  const clock = { t: T0 };
  const ctx = await live(clock);
  ctx.store.put("meta", "pmDispatch", [{ kind: "digest", ref: 0, at: T0 - 30 * 60_000 }]);
  await sendAll(ctx, [
    ["issues", issueEv(3466, { labels: ["oc:no-pr", "prio:critical"] })],
    ...noPrOutcome(3466),
    ["issues", issueEv(3478, { labels: ["oc:no-pr"] })],
    ...noPrOutcome(3478),
  ]);
  await markFresh(ctx);
  await ctx.app.engine.pmDispatch(await gh(ctx));
  const s = ctx.app.engine.status() as any;
  assert.deepEqual(s.pm_dispatch_1h_by_prio, { critical: 1, normal: 2, low: 0 });
  assert.equal(s.pm_dispatch_1h, 3, "内訳の合計は pm_dispatch_1h と一致する");
  assert.deepEqual(s.pm_detected, { user_answered: 0, needs_decision: 0, stuck: 0, no_pr: 2, refs_orphan: 0, stopped_report: 0, critical: 1 });
  clock.t += 61 * 60_000;
  const later = ctx.app.engine.status() as any;
  assert.deepEqual(later.pm_dispatch_1h_by_prio, { critical: 0, normal: 0, low: 0 }, "1 時間たったら数えない");
});
