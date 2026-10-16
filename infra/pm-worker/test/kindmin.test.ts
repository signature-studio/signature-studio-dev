import { test } from "node:test";
import assert from "node:assert/strict";
import { configuredApp, j, markFresh, T0, type Call } from "./helpers.ts";
import { HUMAN, IMPL, IMPL_BOT, at, commentEv, issueEv, outcomeBody, prEv, send, type Ctx } from "./pm_helpers.ts";
import type { Prio } from "../src/launch.ts";
import { KIND_LIMITS, KIND_MIN_PER_HOUR, PM_LIMITS, selectDispatch, type HistoryEntry, type PmTarget } from "../src/pm.ts";

// 毎時の最低配分 (#3704)。selectDispatch は純関数なので、時刻と履歴を直接渡して検証する。
const NOW = T0;
const MIN = 60_000;
const tg = (kind: string, ref: number, prio: Prio = "normal"): PmTarget => ({ kind: kind as PmTarget["kind"], ref, at: "2026-10-14T12:00:00Z", prio });
// detectPm と同じ並び (kind の順 → ref の昇順) で作る
const seq = (kind: string, from: number, n: number, prio: Prio = "normal"): PmTarget[] => Array.from({ length: n }, (_, i) => tg(kind, from + i, prio));
const count = (xs: PmTarget[], kind: string): number => xs.filter((x) => x.kind === kind).length;

test("(a) 本日の実測の再現: 未送信の needs_decision 5・no_pr 80・refs_orphan 60、履歴なし → refs_orphan がちょうど 3 件 (予約が無ければ 0 件)", () => {
  const targets = [...seq("needs_decision", 1, 5), ...seq("no_pr", 100, 80), ...seq("refs_orphan", 500, 60)];
  const { send: sent, skipped } = selectDispatch(NOW, targets, []);
  assert.equal(sent.length, 72, "毎時 72 件");
  assert.equal(count(sent, "refs_orphan"), 3, "refs_orphan は毎時 3 件");
  assert.equal(count(sent, "needs_decision"), 5);
  assert.equal(count(sent, "no_pr"), 64, "残りの枠 (72 - 5 - 3) を no_pr が使う");
  assert.equal(skipped.filter((s) => s.why === "reserve").length, 16, "no_pr の残りは、refs_orphan の予約で見送る");
});

test("(b) 1 分ごとに 120 回 (2 時間)、送った分を履歴に足して呼ぶ: どの 1 時間も送信は 24 件以内で、refs_orphan が毎時 3 件以上", () => {
  let hist: HistoryEntry[] = [];
  const sent: Array<PmTarget & { at: number }> = [];
  for (let m = 0; m < 120; m++) {
    const now = NOW + m * MIN;
    const targets = [...seq("needs_decision", 1, 5), ...seq("no_pr", 100, 40 + m), ...seq("refs_orphan", 500, 60)];
    const { send: picked } = selectDispatch(now, targets, hist);
    for (const t of picked) {
      hist = [...hist, { kind: t.kind, ref: t.ref, at: now }];
      sent.push({ ...t, at: now });
    }
  }
  for (let h = 0; h < 2; h++) {
    const win = sent.filter((x) => x.at >= NOW + h * 60 * MIN && x.at < NOW + (h + 1) * 60 * MIN);
    assert.ok(win.length <= PM_LIMITS.hourMax, `${h} 時間目の送信 ${win.length} 件 (上限 ${PM_LIMITS.hourMax})`);
    assert.ok(count(win, "refs_orphan") >= 3, `${h} 時間目の refs_orphan ${count(win, "refs_orphan")} 件 (3 件以上)`);
  }
});

test("(c) 送れる refs_orphan が無い間は、枠を他の kind に回して 72 件使い切る", () => {
  const targets = [...seq("needs_decision", 1, 5), ...seq("no_pr", 100, 70)];
  const { send: sent } = selectDispatch(NOW, targets, []);
  assert.equal(sent.length, 72, "空費しない");
  assert.equal(count(sent, "no_pr"), 67);
});

test("(c') 送れる refs_orphan が 1 件だけ (残りは 24 時間の抑止中) なら、予約はその 1 件まで。残りは他の kind に回す", () => {
  const history: HistoryEntry[] = [{ kind: "refs_orphan", ref: 501, at: NOW - 2 * 3_600_000 }];
  const targets = [...seq("needs_decision", 1, 5), ...seq("no_pr", 100, 70), tg("refs_orphan", 500), tg("refs_orphan", 501)];
  const { send: sent } = selectDispatch(NOW, targets, history);
  assert.equal(sent.length, 72);
  assert.deepEqual(sent.filter((x) => x.kind === "refs_orphan").map((x) => x.ref), [500]);
  assert.equal(count(sent, "no_pr"), 66);
});

test("(d) user_answered は最低配分より先に送る: 先頭に来て、refs_orphan の 3 件は残る", () => {
  const targets = [...seq("user_answered", 1, 2), ...seq("no_pr", 100, 70), ...seq("refs_orphan", 500, 60)];
  const { send: sent } = selectDispatch(NOW, targets, []);
  assert.deepEqual(sent.slice(0, 2).map((x) => x.kind), ["user_answered", "user_answered"]);
  assert.equal(count(sent, "refs_orphan"), 3);
  assert.equal(sent.length, 72);
});

test("(d') 残りの枠が予約ぶんしか無いときも user_answered は送る (予約で押し出さない)", () => {
  const history: HistoryEntry[] = Array.from({ length: PM_LIMITS.hourMax - 3 }, (_, i) => ({ kind: "no_pr", ref: 700 + i, at: NOW - 30 * MIN }));
  const targets = [...seq("user_answered", 1, 3), ...seq("refs_orphan", 500, 60)];
  const { send: sent } = selectDispatch(NOW, targets, history);
  assert.deepEqual(sent.map((x) => x.kind), ["user_answered", "user_answered", "user_answered"], "予約の 3 枠は user_answered が使う");
});

test("(e) 同じ窓で既に最低配分の件数を送っていれば、その tick では予約しない (他の kind が枠を使う)", () => {
  const history: HistoryEntry[] = [900, 901, 902].map((ref) => ({ kind: "refs_orphan", ref, at: NOW - 10 * MIN }));
  const targets = [...seq("needs_decision", 1, 5), ...seq("no_pr", 100, 70), ...seq("refs_orphan", 500, 60)];
  const { send: sent } = selectDispatch(NOW, targets, history);
  assert.equal(count(sent, "refs_orphan"), 0, "残りは他の kind");
  assert.equal(count(sent, "no_pr"), 64, "履歴の 3 件 + needs_decision 5 + no_pr 64 = 72 (残りの枠は no_pr が使う)");
});

test("(f) 最低配分の設定: refs_orphan は毎時 3 件。1 日の上限は 24 × 3 = 72 (最低配分を 24 時間続けられる値)", () => {
  assert.equal(KIND_MIN_PER_HOUR.refs_orphan, 3);
  assert.equal(KIND_LIMITS.refs_orphan?.dayMax, 72);
  assert.equal(KIND_LIMITS.refs_orphan?.dupMs, 24 * 3_600_000, "同じ N に 24 時間 1 回は変えない");
});

test("(f') 上限の設定 (#CI-232): 毎時 72 起動、同じ ref は 24 時間に 6 回まで。旧値 (36・3) ではない", () => {
  assert.equal(PM_LIMITS.hourMax, 72);
  assert.equal(PM_LIMITS.refDayMax, 6);
});

test("(g) 区分順と予約の両立: prio:critical の no_pr 70 件が先に送られ、normal の refs_orphan の 3 件は残る。入力の並びが逆でも同じ (区分が先頭キー)", () => {
  const crit = seq("no_pr", 100, 70, "critical");
  const norm = seq("refs_orphan", 500, 60);
  for (const targets of [[...crit, ...norm], [...norm, ...crit]]) {
    const { send: sent } = selectDispatch(NOW, targets, []);
    assert.equal(sent.length, 72);
    assert.equal(count(sent, "refs_orphan"), 3, "予約の 3 件は残る");
    assert.equal(count(sent, "no_pr"), 69);
    assert.ok(sent.slice(0, 69).every((x) => x.kind === "no_pr"), "critical の no_pr が先に送られる");
  }
});

// ---------------------------------------------------------------- engine (検出から送信まで)
const pmCalls = (calls: Call[]) => calls.filter((c) => c.method === "POST" && c.url.endsWith("/dispatches") && c.body?.event_type === "oc-pm");
const sendAll = async (ctx: Ctx, items: Array<[string, unknown]>) => {
  for (const [ev, p] of items) assert.equal((await send(ctx.app, ev, p)).status, 202);
};
const live = (clock = { t: T0 }) => configuredApp({ live: true, now: clock, handlers: [(c) => (c.url.endsWith("/dispatches") ? j(null, 204) : undefined)] });

test("(a) 検出から送信まで: 未送信の no_pr 70 件 + refs_orphan 60 件 → 1 回の tick で 72 件、うち refs_orphan 3 件。/status の kind 別の件数も合う", async () => {
  const clock = { t: T0 };
  const ctx = await live(clock);
  const seed: Array<[string, unknown]> = [];
  for (let n = 300; n < 370; n++) {
    seed.push(["issues", issueEv(n, { labels: ["oc:no-pr"] })]);
    seed.push(["issue_comment", commentEv(n, { login: IMPL }, outcomeBody("split"), at(10))]);
  }
  for (let n = 400; n < 460; n++) {
    seed.push(["issues", issueEv(n, { author: HUMAN, title: `[CI-${n}] 親`, at: at(1) })]);
    const ev = prEv(n + 500, { body: `Refs #${n}`, author: IMPL_BOT, at: at(5) });
    seed.push(["pull_request", { ...ev, action: "closed", pull_request: { ...ev.pull_request, state: "closed", merged_at: at(5), updated_at: at(5) } }]);
  }
  await sendAll(ctx, seed);
  await markFresh(ctx);
  await ctx.app.engine.pmDispatch(await (ctx.app.engine as any).d.gh());
  const sent = pmCalls(ctx.m.calls).map((c) => c.body.client_payload.kind as string);
  assert.equal(sent.length, PM_LIMITS.hourMax);
  assert.equal(sent.filter((k) => k === "refs_orphan").length, 3);
  assert.equal(sent.filter((k) => k === "no_pr").length, 69);
  const s = ctx.app.engine.status() as any;
  assert.deepEqual(s.pm_dispatch_1h_by_kind, { user_answered: 0, needs_decision: 0, stuck: 0, no_pr: 69, refs_orphan: 3, stopped_report: 0 });
  assert.equal(s.pm_dispatch_1h, PM_LIMITS.hourMax, "内訳の合計は pm_dispatch_1h と同じ");
  assert.equal(s.pm_skipped_hour_24h, 58, "見送り = no_pr の残り 1 (予約 reserve) + refs_orphan の残り 57 (毎時上限 hour)");
});
