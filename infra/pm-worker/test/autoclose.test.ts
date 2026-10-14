import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { closeComment, detectRuleA, AUTO_CLOSE_MAX } from "../src/autoclose.ts";
import { EMPTY_STATE, applyEvent, type IssueState, type PmState, type PrState } from "../src/webhook.ts";
import { configuredApp, j, markFresh, REPO, T0, type Call } from "./helpers.ts";
import { HUMAN, IMPL, REVIEWER, at, issueEv, prEv, send, type Ctx } from "./pm_helpers.ts";

const here = fileURLToPath(new URL(".", import.meta.url));
const fixturePath = `${here}fixtures/rule_a.input.json`;
const crosscheck = `${here}rule_a_crosscheck.py`;

// ---------------------------------------------------------------- 判定 (純関数)
const byNum = <T extends { number: number }>(xs: T[]): Record<string, T> => Object.fromEntries(xs.map((x) => [String(x.number), x]));
const I = (number: number, o: { body?: string; labels?: string[]; state?: "open" | "closed"; blocked?: number } = {}): IssueState => ({
  number,
  title: `[CI-${number}] t`,
  labels: o.labels ?? [],
  body: o.body ?? "",
  state: o.state ?? "open",
  updatedAt: "2026-10-14T11:00:00Z",
  blockedByCount: o.blocked ?? 0,
});
const P = (number: number, o: { state?: "open" | "closed"; merged?: boolean; closes?: number[]; mentions?: number[] } = {}): PrState => ({
  number,
  state: o.state ?? "closed",
  merged: o.merged ?? true,
  draft: false,
  ref: `${number}-x`,
  title: "",
  body: "",
  labels: [],
  updatedAt: "2026-10-14T11:00:00Z",
  closes: o.closes ?? [],
  mentions: o.mentions ?? [],
});
const state = (issues: IssueState[], prs: PrState[] = [], blockedBy: Record<string, number[]> = {}): PmState => ({
  ...EMPTY_STATE,
  issues: byNum(issues),
  prs: byNum(prs),
  blockedBy,
});
// 基本の形: 親 100 (open) に子 101 (open)、100 を Closes する merged PR 200
const base = (): PmState =>
  state(
    [I(100), I(101, { body: "親: #100" })],
    [P(200, { closes: [100] })],
  );

test("規則 A: 基本の形で閉じる候補になる (merged PR の番号と open な子の番号を持つ)", () => {
  assert.deepEqual(detectRuleA(base()), [{ n: 100, mergedPr: 200, child: 101 }]);
});

test("規則 A のネガコン (a): 子が無い親は閉じない", () => {
  assert.deepEqual(detectRuleA(state([I(100)], [P(200, { closes: [100] })])), []);
});

test("規則 A のネガコン (b): needs-user-input が付いた親は閉じない", () => {
  const s = state([I(100, { labels: ["needs-user-input"] }), I(101, { body: "親: #100" })], [P(200, { closes: [100] })]);
  assert.deepEqual(detectRuleA(s), []);
});

test("規則 A のネガコン (c): 親を参照する open PR がある間は閉じない (言及の番号で判定)", () => {
  const s = state([I(100), I(101, { body: "親: #100" })], [P(200, { closes: [100] }), P(300, { state: "open", merged: false, mentions: [100] })]);
  assert.deepEqual(detectRuleA(s), []);
  // 参照が閉じた PR だけなら閉じてよい (open PR の言及だけを見る)
  const s2 = state([I(100), I(101, { body: "親: #100" })], [P(200, { closes: [100] }), P(300, { state: "closed", merged: false, mentions: [100] })]);
  assert.deepEqual(detectRuleA(s2), [{ n: 100, mergedPr: 200, child: 101 }]);
});

test("規則 A のネガコン (d): 子以外の open issue が親を blocked_by にしていれば閉じない (子からの依存は除く)", () => {
  const other = state([I(100), I(101, { body: "親: #100" }), I(102)], [P(200, { closes: [100] })], { "102": [100] });
  assert.deepEqual(detectRuleA(other), []);
  // 子が親を待つのは、親を閉じる妨げにならない
  const child = state([I(100), I(101, { body: "親: #100" })], [P(200, { closes: [100] })], { "101": [100] });
  assert.deepEqual(detectRuleA(child), [{ n: 100, mergedPr: 200, child: 101 }]);
});

test("規則 A のネガコン (d'): blocked_by の一覧が不明な open issue があれば、子でない限り閉じない", () => {
  const unknown = state([I(100), I(101, { body: "親: #100" }), I(103, { blocked: 1 })], [P(200, { closes: [100] })]);
  assert.deepEqual(detectRuleA(unknown), []);
  // 不明な issue が子なら閉じてよい
  const child = state([I(100), I(101, { body: "親: #100", blocked: 1 })], [P(200, { closes: [100] })]);
  assert.deepEqual(detectRuleA(child), [{ n: 100, mergedPr: 200, child: 101 }]);
});

test("規則 A のネガコン (e): merged PR が無い (closed のまま merge されていない・参照なし) なら閉じない", () => {
  assert.deepEqual(detectRuleA(state([I(100), I(101, { body: "親: #100" })], [P(200, { closes: [100], merged: false })])), []);
  assert.deepEqual(detectRuleA(state([I(100), I(101, { body: "親: #100" })], [P(200, { closes: [] })])), []);
  // open の PR が merge 済みと同じ参照を持っても、merged ではないので数えない
  assert.deepEqual(detectRuleA(state([I(100), I(101, { body: "親: #100" })], [P(200, { state: "open", merged: false, closes: [100] })])), []);
});

test("規則 A のネガコン (f): 親が既に closed なら対象外", () => {
  assert.deepEqual(detectRuleA(state([I(100, { state: "closed" }), I(101, { body: "親: #100" })], [P(200, { closes: [100] })])), []);
});

test("規則 A のネガコン (g): 子が全て closed なら対象外 (残りを追跡する open の子が無い)", () => {
  assert.deepEqual(detectRuleA(state([I(100), I(101, { body: "親: #100", state: "closed" })], [P(200, { closes: [100] })])), []);
});

test("規則 A: 移行前の保存値 (open PR に mentions が無い) が残る間は、どの親も閉じない", () => {
  const legacy: PrState = { ...P(300, { state: "open", merged: false }), mentions: undefined };
  assert.deepEqual(detectRuleA(state([I(100), I(101, { body: "親: #100" })], [P(200, { closes: [100] }), legacy])), []);
});

test("規則 A: 複数の候補は番号順。merged PR と子は最小の番号を使う", () => {
  const s = state(
    [I(100), I(110), I(101, { body: "親: #100" }), I(102, { body: "親: #100" }), I(111, { body: "親: #110" })],
    [P(209, { closes: [110] }), P(205, { closes: [100] }), P(200, { closes: [100] })],
  );
  assert.deepEqual(detectRuleA(s), [
    { n: 100, mergedPr: 200, child: 101 },
    { n: 110, mergedPr: 209, child: 111 },
  ]);
});

test("closeComment: 書式 (規則・merged PR・残りの追跡先・マーカー)", () => {
  assert.equal(
    closeComment({ n: 100, mergedPr: 200, child: 101 }),
    "[auto-close] 規則 A: merged PR #200、残りは #101 が追跡 <!-- oc-auto-close: rule=A -->",
  );
});

test("Python 版 (test/rule_a_crosscheck.py) と同じ判定: 固定 fixture の候補が一致する (本文の参照の抽出は webhook の保存経路を通す)", () => {
  const fx = JSON.parse(readFileSync(fixturePath, "utf8"));
  const upd = "2026-10-14T11:00:00Z";
  let s: PmState = structuredClone(EMPTY_STATE);
  for (const i of fx.issues) {
    const issue = { number: i.number, title: `[CI-${i.number}] t`, body: i.body, state: i.state, updated_at: upd, labels: i.labels.map((name: string) => ({ name })), issue_dependencies_summary: { total_blocked_by: i.blockedByCount } };
    s = applyEvent(s, "issues", { issue }, IMPL, [], REVIEWER);
  }
  for (const p of fx.prs) {
    const pull_request = { number: p.number, title: p.title, body: p.body, state: p.state, merged_at: p.merged ? "2026-10-14T10:30:00Z" : null, updated_at: upd, labels: [], head: { ref: `${p.number}-x` }, user: { login: "x", type: "Bot" } };
    s = applyEvent(s, "pull_request", { pull_request }, IMPL, [], REVIEWER);
  }
  s = { ...s, blockedBy: fx.blockedBy };
  const py = JSON.parse(execFileSync("python3", [crosscheck, fixturePath], { encoding: "utf8" })) as number[][];
  const ts = detectRuleA(s).map((t) => [t.n, t.mergedPr, t.child]);
  assert.deepEqual(ts, py);
  assert.deepEqual(py, [
    [100, 200, 101],
    [110, 210, 111],
    [115, 215, 116],
    [190, 290, 191],
  ]);
});

// ---------------------------------------------------------------- 保存 (webhook の参照抽出)
test("保存: PR の参照は body を切る前の全文から取る (3000 字より後ろの #N も、open PR の言及として残る)", () => {
  const long = "x".repeat(3500) + " #100";
  const r = applyEvent(EMPTY_STATE, "pull_request", { action: "opened", pull_request: { ...prEv(300, { body: long }).pull_request } }, IMPL, [], REVIEWER);
  assert.equal(r.prs["300"].body.length, 3000);
  assert.deepEqual(r.prs["300"].mentions, [100]);
  assert.deepEqual(r.prs["300"].closes, []);
});

test("保存: closes は Closes / Fixes / Resolves / Refs のキーワードの参照だけ (本文の言及は closes に入れない)", () => {
  const body = "Closes #100\nFixes: #101\nResolves #102\nRefs #103\nsee #104 and #105\nclosed ok";
  const r = applyEvent(EMPTY_STATE, "pull_request", { action: "closed", pull_request: { ...prEv(200, { body }).pull_request, state: "closed", merged_at: at(1) } }, IMPL, [], REVIEWER);
  assert.deepEqual(r.prs["200"].closes, [100, 101, 102, 103]);
  assert.deepEqual(r.prs["200"].mentions, [100, 101, 102, 103, 104, 105]);
  assert.equal(r.prs["200"].merged, true);
  assert.equal(r.prs["200"].body, "");
});

// ---------------------------------------------------------------- エンジン (dry-run / live)
const CLOSE_PATH = `/repos/${REPO.full_name}/issues/`;
const isComment = (c: Call) => c.method === "POST" && c.url.endsWith("/comments");
const isClose = (c: Call) => c.method === "PATCH" && c.url.includes(CLOSE_PATH) && !c.url.endsWith("/comments");
// GitHub リポジトリへの書き込み (installation token の取得 POST /app/... は数えない)
const writes = (calls: Call[]) => calls.filter((c) => c.method !== "GET" && c.url.includes("/repos/"));

// 親 n (open) と子 n+1 (open) と、n を Closes する merged PR 200+n を送る。
async function seedRuleA(ctx: Ctx, ns: number[]): Promise<void> {
  for (const n of ns) {
    const evs: Array<[string, unknown]> = [
      ["issues", issueEv(n, {})],
      ["issues", issueEv(n + 1000, { body: `親: #${n}` })],
      ["pull_request", { action: "closed", repository: REPO, pull_request: { ...prEv(200 + n).pull_request, state: "closed", merged_at: at(1), body: `Closes #${n}` } }],
    ];
    for (const [ev, p] of evs) assert.equal((await send(ctx.app, ev, p)).status, 202);
  }
}
const engineGh = async (ctx: Ctx) => (ctx.app.engine as any).d.gh();
const writeOk = (c: Call) => (isComment(c) ? j({ id: 1 }, 201) : isClose(c) ? j({ state: "closed" }, 200) : undefined);

test("dry-run (既定): 候補を wouldClose に数え、書き込みは 0 回。同じ候補は 3 時間は数え直さない", async () => {
  const clock = { t: T0 };
  const ctx = await configuredApp({ now: clock });
  await seedRuleA(ctx, [100]);
  await markFresh(ctx);
  const r1 = await ctx.app.engine.autoClose(await engineGh(ctx));
  assert.deepEqual(r1.would.map((t) => t.n), [100]);
  assert.deepEqual(r1.closed, []);
  assert.equal(writes(ctx.m.calls).length, 0);
  let s = ctx.app.engine.status() as any;
  assert.equal(s.mode_close, "dry-run");
  assert.equal(s.auto_close_detected, 1);
  assert.equal(s.counters.wouldClose, 1);
  assert.equal(s.counters.closed, 0);
  assert.ok(s.log.some((l: any) => l.kind === "would-close" && l.n === 100));
  clock.t += 1 * 3_600_000;
  await markFresh(ctx);
  await ctx.app.engine.autoClose(await engineGh(ctx));
  s = ctx.app.engine.status() as any;
  assert.equal(s.counters.wouldClose, 1);
  clock.t += 3 * 3_600_000;
  await markFresh(ctx);
  await ctx.app.engine.autoClose(await engineGh(ctx));
  s = ctx.app.engine.status() as any;
  assert.equal(s.counters.wouldClose, 2);
  assert.equal(writes(ctx.m.calls).length, 0);
});

test("LIVE=1 だけでは閉じない (規則 A は LIVE_CLOSE=1 が要る)", async () => {
  const ctx = await configuredApp({ live: true, handlers: [writeOk] });
  await seedRuleA(ctx, [100]);
  await markFresh(ctx);
  await ctx.app.engine.autoClose(await engineGh(ctx));
  assert.equal(writes(ctx.m.calls).length, 0);
  assert.equal((ctx.app.engine.status() as any).mode_close, "dry-run");
});

test("LIVE_CLOSE=1: 親にコメント (PM App の token・規定の書式) → state=closed・state_reason=completed で閉じ、状態も closed にする", async () => {
  const ctx = await configuredApp({ env: { LIVE_CLOSE: "1" }, handlers: [writeOk] });
  await seedRuleA(ctx, [100]);
  await markFresh(ctx);
  const r = await ctx.app.engine.autoClose(await engineGh(ctx));
  assert.deepEqual(r.closed, [{ n: 100, mergedPr: 300, child: 1100 }]);
  const w = writes(ctx.m.calls);
  assert.equal(w.length, 2);
  assert.ok(isComment(w[0]), "コメントを先に書く");
  assert.equal(w[0].body.body, "[auto-close] 規則 A: merged PR #300、残りは #1100 が追跡 <!-- oc-auto-close: rule=A -->");
  assert.ok(isClose(w[1]));
  assert.deepEqual(w[1].body, { state: "closed", state_reason: "completed" });
  assert.equal(w[0].auth, "Bearer ghs_installation_token_value");
  assert.equal(w[1].auth, "Bearer ghs_installation_token_value");
  assert.equal((ctx.app.engine.status() as any).counters.closed, 1);
  assert.equal((ctx.app.engine.status() as any).mode_close, "live");
  // 閉じた後は再び候補にならない
  assert.equal((await ctx.app.engine.autoClose(await engineGh(ctx))).closed.length, 0);
});

test("LIVE_CLOSE=1: 1 tick に閉じるのは最大 5 件 (残りは次の tick)", async () => {
  const ctx = await configuredApp({ env: { LIVE_CLOSE: "1" }, handlers: [writeOk] });
  await seedRuleA(ctx, [100, 110, 120, 130, 140, 150, 160]);
  await markFresh(ctx);
  const r1 = await ctx.app.engine.autoClose(await engineGh(ctx));
  assert.equal(r1.closed.length, AUTO_CLOSE_MAX);
  assert.equal(writes(ctx.m.calls).filter(isClose).length, 5);
  await markFresh(ctx);
  const r2 = await ctx.app.engine.autoClose(await engineGh(ctx));
  assert.equal(r2.closed.length, 2);
  assert.equal((ctx.app.engine.status() as any).counters.closed, 7);
});

test("LIVE_CLOSE=1: 閉じる書き込みが失敗しても、同じ親は 24 時間は再試行しない (二重のコメントを避ける)", async () => {
  const clock = { t: T0 };
  const failClose = (c: Call) => (isComment(c) ? j({ id: 1 }, 201) : isClose(c) ? j({ message: "boom" }, 500) : undefined);
  const ctx = await configuredApp({ now: clock, env: { LIVE_CLOSE: "1" }, handlers: [failClose] });
  await seedRuleA(ctx, [100]);
  await markFresh(ctx);
  const r1 = await ctx.app.engine.autoClose(await engineGh(ctx));
  assert.equal(r1.closed.length, 0);
  assert.equal(ctx.m.calls.filter(isComment).length, 1);
  clock.t += 2 * 3_600_000;
  await markFresh(ctx);
  await ctx.app.engine.autoClose(await engineGh(ctx));
  assert.equal(ctx.m.calls.filter(isComment).length, 1, "24 時間以内は再試行しない");
  assert.ok((ctx.app.engine.status() as any).log.some((l: any) => l.kind === "error" && l.n === 100));
  clock.t += 24 * 3_600_000;
  await markFresh(ctx);
  await ctx.app.engine.autoClose(await engineGh(ctx));
  assert.equal(ctx.m.calls.filter(isComment).length, 2, "24 時間を過ぎたら再試行する");
});

test("LIVE_CLOSE=1: 同期が古い間は閉じない (一覧の取りこぼしで参照を誤認しない)", async () => {
  const clock = { t: T0 };
  const ctx = await configuredApp({ now: clock, env: { LIVE_CLOSE: "1" }, handlers: [writeOk] });
  await seedRuleA(ctx, [100]);
  await markFresh(ctx);
  clock.t += 16 * 60_000;
  const r = await ctx.app.engine.autoClose(await engineGh(ctx));
  assert.deepEqual(r.closed, []);
  assert.equal(writes(ctx.m.calls).length, 0);
});

test("LIVE_CLOSE=1: レート制限の守りの間 (残量が 1,500 未満) は閉じない", async () => {
  const ctx = await configuredApp({ env: { LIVE_CLOSE: "1" }, handlers: [writeOk] });
  await seedRuleA(ctx, [100]);
  await markFresh(ctx);
  ctx.app.engine.recordRate({ remaining: 1000 });
  const r = await ctx.app.engine.autoClose(await engineGh(ctx));
  assert.deepEqual(r.closed, []);
  assert.equal(writes(ctx.m.calls).length, 0);
  // 守りが解けたら、止めた候補は 24 時間の抑止を受けずに次の tick で閉じる
  await markFresh(ctx);
  ctx.app.engine.recordRate({ remaining: 4000 });
  assert.deepEqual((await ctx.app.engine.autoClose(await engineGh(ctx))).closed.map((t) => t.n), [100]);
});

test("LIVE_CLOSE=1 のネガコン: 子が無い親・merged PR の無い親は、どちらも書き込まない", async () => {
  const ctx = await configuredApp({ env: { LIVE_CLOSE: "1" }, handlers: [writeOk] });
  await send(ctx.app, "issues", issueEv(300, {}));
  await send(ctx.app, "issues", issueEv(310, {}));
  await send(ctx.app, "issues", issueEv(311, { body: "親: #310" }));
  await markFresh(ctx);
  await ctx.app.engine.autoClose(await engineGh(ctx));
  assert.equal(writes(ctx.m.calls).length, 0);
});

// 規則 A の判定は HUMAN (OWNER) の起票でも bot の起票でも同じ (起票者で絞らない)。
test("起票者で絞らない: 人が起票した親でも、規則 A の条件を満たせば対象になる", () => {
  const s = state([{ ...I(100), author: HUMAN.login, authorType: "User", assoc: "OWNER" } as IssueState, I(101, { body: "親: #100" })], [P(200, { closes: [100] })]);
  assert.deepEqual(detectRuleA(s), [{ n: 100, mergedPr: 200, child: 101 }]);
});
