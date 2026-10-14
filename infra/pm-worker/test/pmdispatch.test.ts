import { test } from "node:test";
import assert from "node:assert/strict";
import { configuredApp, j, markFresh, REPO, T0, type Call } from "./helpers.ts";
import {
  CONTRIB_USER,
  COLLAB_USER,
  EVIL_BOT,
  HUMAN,
  IMPL,
  IMPL_BOT,
  MEMBER_USER,
  OUTSIDER,
  REVIEWER,
  at,
  commentEv,
  issueEv,
  outcomeBody,
  prEv,
  reviewEv,
  send,
  stopBody,
  type Ctx,
} from "./pm_helpers.ts";

const pmCalls = (calls: Call[]) => calls.filter((c) => c.method === "POST" && c.url.endsWith("/dispatches") && c.body?.event_type === "oc-pm");
const sendAll = async (ctx: Ctx, items: Array<[string, unknown]>) => {
  for (const [ev, p] of items) assert.equal((await send(ctx.app, ev, p)).status, 202);
};
const live = (clock = { t: T0 }) => configuredApp({ live: true, now: clock, handlers: [(c) => (c.url.endsWith("/dispatches") ? j(null, 204) : undefined)] });
const targets = (ctx: Ctx) => ctx.app.engine.detectPmTargets().map((t) => `${t.kind}#${t.ref}`);
const PM_REPLY = (n: number, min: number): [string, unknown] => ["issue_comment", commentEv(n, HUMAN, "判断しました", at(min), true)];

// ---------------------------------------------------------------- 検出
test("検出 stuck: oc:stuck の open PR で、最新の停止コメントに oc-pm-intent: stuck がある", async () => {
  const ctx = await configuredApp();
  await sendAll(ctx, [
    ["pull_request", prEv(10, { labels: ["oc:stuck"] })],
    ["issue_comment", commentEv(10, { login: IMPL }, stopBody(10), at(5), true)],
    // intent の無い旧形式の停止コメント
    ["pull_request", prEv(11, { labels: ["oc:stuck"] })],
    ["issue_comment", commentEv(11, { login: IMPL }, "停止 <!-- oc-fix-limit -->", at(5), true)],
    // 停止コメントはあるが oc:stuck が外れている
    ["pull_request", prEv(12, { labels: ["oc:ready"] })],
    ["issue_comment", commentEv(12, { login: IMPL }, stopBody(12), at(5), true)],
    // pr= が別の PR の番号 (コピーされたマーカー)
    ["pull_request", prEv(13, { labels: ["oc:stuck"] })],
    ["issue_comment", commentEv(13, { login: IMPL }, stopBody(10), at(5), true)],
  ]);
  assert.deepEqual(targets(ctx), ["stuck#10"]);
});

test("検出 stuck: 最新の停止コメントで判定する (新しい停止コメントに intent が無ければ対象外)", async () => {
  const ctx = await configuredApp();
  await sendAll(ctx, [
    ["pull_request", prEv(10, { labels: ["oc:stuck"] })],
    ["issue_comment", commentEv(10, { login: IMPL }, stopBody(10), at(5), true)],
  ]);
  assert.deepEqual(targets(ctx), ["stuck#10"]);
  await sendAll(ctx, [["issue_comment", commentEv(10, { login: IMPL }, "再停止 <!-- oc-fix-limit -->", at(50), true)]]);
  assert.deepEqual(targets(ctx), []);
});

test("検出 stuck: 非 bot (誰でも書ける) の偽マーカーは信じない。PM 応答があれば対象外", async () => {
  const ctx = await configuredApp();
  await sendAll(ctx, [
    ["pull_request", prEv(10, { labels: ["oc:stuck"] })],
    ["issue_comment", commentEv(10, { login: "stranger" }, stopBody(10), at(5), true)],
    ["issue_comment", commentEv(10, { login: "evil-app[bot]" }, stopBody(10), at(6), true)],
  ]);
  assert.deepEqual(targets(ctx), []);
  await sendAll(ctx, [["issue_comment", commentEv(10, { login: IMPL }, stopBody(10), at(7), true)]]);
  assert.deepEqual(targets(ctx), ["stuck#10"]);
  await sendAll(ctx, [["issue_comment", commentEv(10, { login: IMPL }, "<!-- oc-pm-decision: rule=R3 reversible=yes -->", at(8), true)]]);
  assert.deepEqual(targets(ctx), [], "PM agent のマーカー付きコメントが後にあれば対象外");
});

test("検出 no_pr: split / stop は即、unknown は再投入済みのときだけ、blocked / artifact は対象外", async () => {
  const ctx = await configuredApp();
  const seed: Array<[string, unknown]> = [];
  const reasons: Record<number, string> = { 20: "split", 21: "stop", 22: "blocked", 23: "artifact", 24: "unknown", 25: "unknown" };
  for (const [n, r] of Object.entries(reasons)) {
    seed.push(["issues", issueEv(Number(n), { labels: ["oc:no-pr"] })]);
    seed.push(["issue_comment", commentEv(Number(n), { login: IMPL }, outcomeBody(r), at(10))]);
  }
  await sendAll(ctx, seed);
  assert.deepEqual(targets(ctx), ["no_pr#20", "no_pr#21"]);
  // 25 は Worker が再投入した (np カウント 1) 後の run でも unknown で終わった: launch (at 20) より後の outcome (at 30)
  ctx.store.put("relaunch", "np:25", { count: 1 });
  await sendAll(ctx, [
    ["issue_comment", commentEv(25, HUMAN, "/oc oc_actions_allow_write\noc_artifacts: fl-win64", at(20))],
    ["issue_comment", commentEv(25, { login: IMPL }, outcomeBody("unknown", 101), at(30))],
  ]);
  assert.deepEqual(targets(ctx), ["no_pr#20", "no_pr#21", "no_pr#25"]);
  // 24 は np カウントがあっても、再投入の後に outcome が無い (投入待ち) なら対象外
  ctx.store.put("relaunch", "np:24", { count: 1 });
  await sendAll(ctx, [["issue_comment", commentEv(24, HUMAN, "/oc oc_actions_allow_write\noc_artifacts: fl-win64", at(40))]]);
  assert.ok(!targets(ctx).includes("no_pr#24"));
});

test("検出 no_pr: 偽の outcome (非 bot) とラベルの無い issue は対象外。最後の outcome で判定する", async () => {
  const ctx = await configuredApp();
  await sendAll(ctx, [
    ["issues", issueEv(30, { labels: ["oc:no-pr"] })],
    ["issue_comment", commentEv(30, { login: "stranger" }, outcomeBody("split"), at(10))],
    ["issues", issueEv(31, { labels: [] })],
    ["issue_comment", commentEv(31, { login: IMPL }, outcomeBody("split"), at(10))],
    ["issues", issueEv(32, { labels: ["oc:no-pr"] })],
    ["issue_comment", commentEv(32, { login: IMPL }, outcomeBody("split"), at(10))],
    ["issue_comment", commentEv(32, { login: IMPL }, outcomeBody("artifact", 2), at(20))],
  ]);
  assert.deepEqual(targets(ctx), []);
});

test("検出 needs_decision: KEY に一致する最新の CHANGES_REQUESTED で、その後に PM 応答が無いもの", async () => {
  const ctx = await configuredApp();
  await sendAll(ctx, [
    ["pull_request", prEv(40)],
    ["pull_request_review", reviewEv(40, "- [blocking] 採番は PM 判断が必要です", at(10))],
    ["pull_request", prEv(41)],
    ["pull_request_review", reviewEv(41, "- [blocking] PM 判断が必要です", at(10))],
    ["issue_comment", commentEv(41, HUMAN, "決めました", at(11), true)],
    ["pull_request", prEv(42)],
    ["pull_request_review", reviewEv(42, "- [blocking] PM 判断が必要です", at(10))],
    ["pull_request_review", reviewEv(42, "OK", at(20), { state: "approved" })],
    ["pull_request", prEv(43)],
    ["pull_request_review", reviewEv(43, "- PM 判断が必要です", at(10), { login: "stranger" })],
    ["pull_request", prEv(44)],
    ["pull_request_review", reviewEv(44, "- PM 判断が必要です", at(10))],
    ["issue_comment", commentEv(44, { login: IMPL }, "<!-- oc-pm-decision: rule=R1 reversible=yes -->", at(12), true)],
  ]);
  assert.deepEqual(targets(ctx), ["needs_decision#40"]);
  // 後から KEY に一致しない差し戻しが来たら、その差し戻しで判定し直す
  await sendAll(ctx, [["pull_request_review", reviewEv(40, "- REPORT の行数が超過しています", at(30))]]);
  assert.deepEqual(targets(ctx), []);
});

test("検出 user_answered: needs-user-input の open issue に、ラベル後に非 bot のコメントが付いた", async () => {
  const ctx = await configuredApp();
  await sendAll(ctx, [
    ["issues", issueEv(50, { labels: ["needs-user-input"], action: "labeled", label: "needs-user-input", at: at(10) })],
    ["issue_comment", commentEv(50, { login: IMPL }, "確認してください", at(11))],
    ["issues", issueEv(51, { labels: ["needs-user-input"], action: "labeled", label: "needs-user-input", at: at(10) })],
    ["issue_comment", commentEv(51, HUMAN, "A でお願いします", at(12))],
    // ラベルより前のコメントは回答ではない
    ["issues", issueEv(52, { labels: [], action: "opened", at: at(1) })],
    ["issue_comment", commentEv(52, HUMAN, "前置き", at(5))],
    ["issues", issueEv(52, { labels: ["needs-user-input"], action: "labeled", label: "needs-user-input", at: at(10) })],
    // ラベルが外れたら対象外
    ["issues", issueEv(53, { labels: ["needs-user-input"], action: "labeled", label: "needs-user-input", at: at(10) })],
    ["issue_comment", commentEv(53, HUMAN, "A", at(12))],
    ["issues", issueEv(53, { labels: [], action: "unlabeled", label: "needs-user-input", at: at(13) })],
  ]);
  assert.deepEqual(targets(ctx), ["user_answered#51"]);
});

const labeledUserInput = (n: number): [string, unknown] => ["issues", issueEv(n, { labels: ["needs-user-input"], action: "labeled", label: "needs-user-input", at: at(10) })];

test("ネガコン (user_answered): NONE / CONTRIBUTOR の第三者のコメントだけでは oc-pm を送らない。MEMBER の回答で送る", async () => {
  const ctx = await live();
  await sendAll(ctx, [labeledUserInput(57), ["issue_comment", commentEv(57, OUTSIDER, "横から失礼", at(11))], ["issue_comment", commentEv(57, CONTRIB_USER, "A です", at(12))]]);
  await markFresh(ctx);
  await ctx.app.engine.pmDispatch(await (ctx.app.engine as any).d.gh());
  assert.equal(pmCalls(ctx.m.calls).length, 0);
  await sendAll(ctx, [["issue_comment", commentEv(57, MEMBER_USER, "A です", at(13))]]);
  await ctx.app.engine.pmDispatch(await (ctx.app.engine as any).d.gh());
  assert.deepEqual(pmCalls(ctx.m.calls).map((c) => c.body.client_payload), [{ kind: "user_answered", ref: 57 }]);
});

test("検出 user_answered (ネガコン): コメント者が NONE / CONTRIBUTOR の第三者なら起こさない。MEMBER・COLLABORATOR の回答は起こす", async () => {
  const ctx = await configuredApp();
  await sendAll(ctx, [
    labeledUserInput(54),
    ["issue_comment", commentEv(54, OUTSIDER, "A です", at(11))],
    ["issue_comment", commentEv(54, CONTRIB_USER, "A です", at(12))],
    labeledUserInput(55),
    ["issue_comment", commentEv(55, MEMBER_USER, "A", at(12))],
    labeledUserInput(56),
    ["issue_comment", commentEv(56, COLLAB_USER, "A", at(12))],
    // 判定時刻は人の回答のまま (後から来た第三者のコメントで上書きされない)
    ["issue_comment", commentEv(55, OUTSIDER, "横から失礼", at(30))],
  ]);
  assert.deepEqual(targets(ctx), ["user_answered#55", "user_answered#56"]);
  assert.equal(ctx.app.engine.detectPmTargets().find((t) => t.ref === 55)?.at, at(12));
});

test("REST: 同期で読んだコメントも author_association で絞る (第三者の REST のコメントでは起こさない)", async () => {
  const ctx = await configuredApp({
    handlers: [
      (c) => {
        if (c.method !== "GET" || !new URL(c.url).pathname.endsWith("/issues/comments")) return undefined;
        const comment = (n: number, login: string, assoc: string) => ({
          id: n,
          issue_url: `https://api.github.com/repos/${REPO.full_name}/issues/${n}`,
          created_at: at(12),
          user: { login, type: "User" },
          author_association: assoc,
          body: "A",
        });
        return j([comment(70, OUTSIDER.login, "NONE"), comment(71, "member-user", "MEMBER")]);
      },
    ],
  });
  await sendAll(ctx, [
    ["issues", issueEv(70, { labels: ["needs-user-input"], action: "labeled", label: "needs-user-input", at: at(10) })],
    ["issues", issueEv(71, { labels: ["needs-user-input"], action: "labeled", label: "needs-user-input", at: at(10) })],
  ]);
  assert.deepEqual(targets(ctx), []);
  const gh = await (ctx.app.engine as any).d.gh();
  await (ctx.app.engine as any).syncComments(gh, Date.parse(at(0)));
  assert.deepEqual(targets(ctx), ["user_answered#71"]);
});

// ---------------------------------------------------------------- REST の補完
test("REST: reviews と labeled の時刻を取りこぼしなく補う (webhook が無くても検出できる)", async () => {
  const ctx = await configuredApp({
    handlers: [
      (c) => {
        if (c.method !== "GET") return undefined;
        const p = new URL(c.url).pathname;
        if (/\/pulls\/60\/reviews$/.test(p)) return j([{ user: { login: REVIEWER }, state: "CHANGES_REQUESTED", body: "PM 判断が必要です", submitted_at: at(10) }]);
        if (/\/issues\/61\/events$/.test(p)) return j([{ event: "labeled", label: { name: "needs-user-input" }, created_at: at(10) }]);
        return undefined;
      },
    ],
  });
  await sendAll(ctx, [
    ["pull_request", prEv(60)],
    ["issues", issueEv(61, { labels: ["needs-user-input"], action: "edited", at: at(20) })],
    ["issue_comment", commentEv(61, HUMAN, "A", at(15))],
  ]);
  assert.deepEqual(targets(ctx), []);
  const gh = await (ctx.app.engine as any).d.gh();
  await (ctx.app.engine as any).syncSignals(gh);
  assert.deepEqual(targets(ctx), ["user_answered#61", "needs_decision#60"].sort((a, b) => (a.startsWith("user") ? -1 : 1)));
  const before = ctx.m.calls.length;
  await (ctx.app.engine as any).syncSignals(gh);
  assert.equal(ctx.m.calls.length, before, "取得済みの reviews / labeled は取り直さない");
});

test("REST: 取得に失敗しても同期は続く (検出は webhook の分だけで動く)", async () => {
  const ctx = await configuredApp({ handlers: [(c) => (c.method === "GET" && /\/(reviews|events)$/.test(c.url) ? j({}, 500) : undefined)] });
  await sendAll(ctx, [["pull_request", prEv(60)]]);
  const gh = await (ctx.app.engine as any).d.gh();
  await (ctx.app.engine as any).syncSignals(gh);
  assert.deepEqual(targets(ctx), []);
});

// ---------------------------------------------------------------- 送信とネガコン
const seedStuck = async (ctx: Ctx, nums: number[], author = IMPL_BOT) => {
  for (const n of nums) {
    await sendAll(ctx, [
      ["pull_request", prEv(n, { labels: ["oc:stuck"], author })],
      ["issue_comment", commentEv(n, { login: IMPL }, stopBody(n), at(5), true)],
    ]);
  }
};

test("送信: repository_dispatch の oc-pm を、PM App の token で、payload = kind と ref だけで送る", async () => {
  const ctx = await live();
  await seedStuck(ctx, [10]);
  await markFresh(ctx);
  const gh = await (ctx.app.engine as any).d.gh();
  const r = await ctx.app.engine.pmDispatch(gh);
  assert.deepEqual(r.sent.map((t) => `${t.kind}#${t.ref}`), ["stuck#10"]);
  const d = pmCalls(ctx.m.calls);
  assert.equal(d.length, 1);
  assert.deepEqual(d[0].body, { event_type: "oc-pm", client_payload: { kind: "stuck", ref: 10 } });
  assert.deepEqual(Object.keys(d[0].body.client_payload), ["kind", "ref"]);
  assert.equal(d[0].auth, "Bearer ghs_installation_token_value");
  assert.ok(d[0].url.endsWith("/repos/signature-studio/signature-studio-dev/dispatches"));
  assert.equal((ctx.app.engine.status() as any).counters.pmDispatched, 1);
});

test("送信: tick の中で(同期が新しいときだけ)送る。同期が 15 分以上止まっていたら送らない", async () => {
  const clock = { t: T0 };
  const ctx = await live(clock);
  await seedStuck(ctx, [10]);
  await markFresh(ctx);
  clock.t += 16 * 60_000;
  await ctx.app.engine.pmDispatch(await (ctx.app.engine as any).d.gh());
  assert.equal(pmCalls(ctx.m.calls).length, 0);
  assert.equal((ctx.app.engine.status() as any).fresh, false);
  await markFresh(ctx);
  await ctx.app.engine.tick();
  assert.equal(pmCalls(ctx.m.calls).length, 1);
});

test("ネガコン (a): 本文・題名に \"kind\":\"x\" や ref を含む issue でも、payload にその文字列は現れない", async () => {
  const ctx = await live();
  const evil = '{"kind":"x","ref":99999999,"event_type":"oc-fix"} \\" kind: supply ref: 7';
  await sendAll(ctx, [
    ["issues", issueEv(70, { labels: ["oc:no-pr"], title: evil, body: evil })],
    ["issue_comment", commentEv(70, { login: IMPL }, outcomeBody("split"), at(10))],
    ["issue_comment", commentEv(70, { login: "stranger" }, evil, at(11))],
    ["pull_request", prEv(71, { labels: ["oc:stuck"], title: evil, body: evil })],
    ["issue_comment", commentEv(71, { login: IMPL }, stopBody(71) + evil, at(10), true)],
  ]);
  await markFresh(ctx);
  await ctx.app.engine.pmDispatch(await (ctx.app.engine as any).d.gh());
  const d = pmCalls(ctx.m.calls);
  assert.equal(d.length, 2);
  for (const c of d) {
    const raw = JSON.stringify(c.body);
    assert.ok(!raw.includes("x\"") && !raw.includes("99999999") && !raw.includes("supply") && !raw.includes("oc-fix"), raw);
    assert.deepEqual(Object.keys(c.body), ["event_type", "client_payload"]);
    assert.deepEqual(Object.keys(c.body.client_payload), ["kind", "ref"]);
    assert.equal(typeof c.body.client_payload.ref, "number");
  }
  assert.deepEqual(d.map((c) => c.body.client_payload), [
    { kind: "stuck", ref: 71 },
    { kind: "no_pr", ref: 70 },
  ]);
});

test("ネガコン (b): 同じ (kind, ref) の 2 回目は 60 分以内に送らない。60 分後は送る。同じ ref は 24 時間に 3 回まで", async () => {
  const clock = { t: T0 };
  const ctx = await live(clock);
  await seedStuck(ctx, [10]);
  await markFresh(ctx);
  const gh = await (ctx.app.engine as any).d.gh();
  const step = async (addMin: number) => {
    clock.t += addMin * 60_000;
    await markFresh(ctx);
    await ctx.app.engine.pmDispatch(gh);
    return pmCalls(ctx.m.calls).length;
  };
  assert.equal(await step(0), 1);
  assert.equal(await step(1), 1, "1 分後");
  assert.equal(await step(58), 1, "59 分後");
  assert.equal(await step(2), 2, "61 分後");
  assert.equal(await step(61), 3, "122 分後");
  assert.equal(await step(61), 3, "同じ ref は 24 時間に 3 回まで (4 回目は送らない)");
  assert.equal(await step(60 * 24), 4, "24 時間たてば送る");
});

test("ネガコン (c): 全体で 1 時間に 12 起動まで。13 件目は送らない", async () => {
  const clock = { t: T0 };
  const ctx = await live(clock);
  await seedStuck(ctx, Array.from({ length: 15 }, (_, i) => 100 + i));
  await markFresh(ctx);
  const gh = await (ctx.app.engine as any).d.gh();
  await ctx.app.engine.pmDispatch(gh);
  assert.equal(pmCalls(ctx.m.calls).length, 12);
  assert.deepEqual(pmCalls(ctx.m.calls).map((c) => c.body.client_payload.ref), Array.from({ length: 12 }, (_, i) => 100 + i));
  clock.t += 30 * 60_000;
  await markFresh(ctx);
  await ctx.app.engine.pmDispatch(gh);
  assert.equal(pmCalls(ctx.m.calls).length, 12, "30 分後もまだ 12 件");
  clock.t += 31 * 60_000;
  await markFresh(ctx);
  await ctx.app.engine.pmDispatch(gh);
  assert.deepEqual(
    pmCalls(ctx.m.calls).slice(12, 15).map((c) => c.body.client_payload.ref),
    [112, 113, 114],
    "1 時間たった分の枠では、未送信の対象を先に送る (送信済みの再送が押し出さない)",
  );
  assert.equal(pmCalls(ctx.m.calls).length, 24, "その時間の枠も 12 件まで");
});

test("ネガコン (d): 許可外の起票者 (assoc が NONE の人・許可外の bot) の対象は送らない。MEMBER/COLLABORATOR・許可 bot は送る", async () => {
  const ctx = await live();
  await seedStuck(ctx, [10], OUTSIDER);
  await seedStuck(ctx, [11], EVIL_BOT);
  await seedStuck(ctx, [12], { ...HUMAN, assoc: "CONTRIBUTOR" });
  await seedStuck(ctx, [13], { ...IMPL_BOT, type: "User" });
  await seedStuck(ctx, [14], { ...HUMAN, assoc: "MEMBER" });
  await seedStuck(ctx, [15], { ...HUMAN, assoc: "COLLABORATOR" });
  await seedStuck(ctx, [16], { login: REVIEWER, type: "Bot", assoc: "NONE" });
  await sendAll(ctx, [
    ["issues", issueEv(80, { labels: ["oc:no-pr"], author: OUTSIDER })],
    ["issue_comment", commentEv(80, { login: IMPL }, outcomeBody("split"), at(10))],
    ["issues", issueEv(81, { labels: ["needs-user-input"], author: OUTSIDER, action: "labeled", label: "needs-user-input", at: at(10) })],
    ["issue_comment", commentEv(81, OUTSIDER, "A", at(12))],
    ["pull_request", prEv(82, { author: OUTSIDER })],
    ["pull_request_review", reviewEv(82, "PM 判断が必要です", at(10))],
  ]);
  await markFresh(ctx);
  await ctx.app.engine.pmDispatch(await (ctx.app.engine as any).d.gh());
  assert.deepEqual(pmCalls(ctx.m.calls).map((c) => c.body.client_payload.ref), [14, 15, 16]);
});

test("ネガコン (e): KEY に一致しない差し戻しは送らない。COMMENTED と APPROVED も送らない", async () => {
  const ctx = await live();
  await sendAll(ctx, [
    ["pull_request", prEv(90)],
    ["pull_request_review", reviewEv(90, "- REPORT の行数が上限 250 を超えています\n- Closes を Refs にしてください\n- repo 外パスがあります", at(10))],
    ["pull_request", prEv(91)],
    ["pull_request_review", reviewEv(91, "PM 判断が必要です", at(10), { state: "commented" })],
    ["pull_request", prEv(92)],
    ["pull_request_review", reviewEv(92, "PM 判断は済みました", at(10), { state: "approved" })],
  ]);
  await markFresh(ctx);
  await ctx.app.engine.pmDispatch(await (ctx.app.engine as any).d.gh());
  assert.equal(pmCalls(ctx.m.calls).length, 0);
  assert.deepEqual(targets(ctx), []);
});

test("ネガコン (f): dry-run では fetch の POST が 0 回。/status の would_dispatch_pm と counters に記録する", async () => {
  const ctx = await configuredApp();
  await seedStuck(ctx, [10, 11]);
  await sendAll(ctx, [
    ["issues", issueEv(20, { labels: ["oc:no-pr"] })],
    ["issue_comment", commentEv(20, { login: IMPL }, outcomeBody("stop"), at(10))],
  ]);
  await markFresh(ctx);
  const gh = await (ctx.app.engine as any).d.gh();
  const post0 = ctx.m.calls.filter((c) => c.method === "POST").length;
  const r = await ctx.app.engine.pmDispatch(gh);
  assert.equal(r.sent.length, 0);
  assert.equal(r.would.length, 3);
  assert.equal(ctx.m.calls.filter((c) => c.method === "POST").length, post0, "dry-run は GitHub に POST しない");
  assert.equal(pmCalls(ctx.m.calls).length, 0);
  const s = ctx.app.engine.status() as any;
  assert.equal(s.mode, "dry-run");
  assert.deepEqual(s.would_dispatch_pm.map((x: any) => `${x.kind}#${x.ref}`), ["stuck#10", "stuck#11", "no_pr#20"]);
  assert.equal(s.counters.wouldDispatchPm, 3);
  assert.equal(s.counters.pmDispatched, 0);
  assert.deepEqual(s.pm_detected, { user_answered: 0, needs_decision: 0, stuck: 2, no_pr: 1 });
  // dry-run でも抑止は効く (同じ記録を毎分増やさない)
  await ctx.app.engine.pmDispatch(gh);
  assert.equal((ctx.app.engine.status() as any).counters.wouldDispatchPm, 3);
  // 公開の /status は個票 (issue 番号) を出さない
  const pub = await (await ctx.app.handle(new Request("https://pm.example/status"))).json();
  assert.ok(!("would_dispatch_pm" in (pub as any)));
  assert.equal((pub as any).pm_detected.stuck, 2);
});

test("送信失敗: エラーを記録して落ちず、同じ対象を次の tick で叩き直さない。403 / 429 はそこで打ち切る", async () => {
  const clock = { t: T0 };
  let status = 500;
  const ctx = await configuredApp({ live: true, now: clock, handlers: [(c) => (c.url.endsWith("/dispatches") ? j({}, status) : undefined)] });
  await seedStuck(ctx, [10, 11]);
  await markFresh(ctx);
  const gh = await (ctx.app.engine as any).d.gh();
  await ctx.app.engine.pmDispatch(gh);
  assert.equal(pmCalls(ctx.m.calls).length, 2, "500 は次の対象へ進む");
  assert.equal((ctx.app.engine.status() as any).counters.pmDispatched, 0);
  assert.ok((ctx.app.engine.status() as any).log.some((l: any) => l.kind === "error"));
  clock.t += 60_000;
  await markFresh(ctx);
  await ctx.app.engine.pmDispatch(gh);
  assert.equal(pmCalls(ctx.m.calls).length, 2, "60 分以内は叩き直さない");
  clock.t += 61 * 60_000;
  status = 429;
  await markFresh(ctx);
  await ctx.app.engine.pmDispatch(gh);
  assert.equal(pmCalls(ctx.m.calls).length, 3, "429 で打ち切る");
});

test("履歴は DO (store) に残り、live と dry-run で分かれる", async () => {
  const ctx = await live();
  await seedStuck(ctx, [10]);
  await markFresh(ctx);
  await ctx.app.engine.pmDispatch(await (ctx.app.engine as any).d.gh());
  const h = ctx.store.get<any[]>("meta", "pmDispatch");
  assert.equal(h?.length, 1);
  assert.deepEqual({ kind: h?.[0].kind, ref: h?.[0].ref }, { kind: "stuck", ref: 10 });
  assert.equal(ctx.store.get("meta", "pmWould"), undefined);
});

test("closed になった PR / issue の手がかりは reconcile の prune で捨てる", async () => {
  const ctx = await configuredApp();
  await seedStuck(ctx, [10]);
  assert.ok(ctx.store.get("sig", "10"));
  await sendAll(ctx, [["pull_request", { ...prEv(10, { labels: ["oc:stuck"], at: at(60) }), pull_request: { ...prEv(10, { labels: ["oc:stuck"], at: at(60) }).pull_request, state: "closed" } }]]);
  (ctx.app.engine as any).prune();
  assert.equal(ctx.store.get("sig", "10"), undefined);
});

// ---------------------------------------------------------------- pm-apply / needs-user-input (依頼者・PM 適用の待ち) は対象外
test("ネガコン (g): pm-apply / needs-user-input が付いた oc:no-pr の issue は、検出も oc-pm の送信も /oc の再投入も 0 回", async () => {
  const clock = { t: T0 + 4 * 3_600_000 };
  const ctx = await configuredApp({
    live: true,
    now: clock,
    handlers: [(c) => (c.method === "POST" && (c.url.endsWith("/dispatches") || /\/issues\/\d+\/comments$/.test(c.url)) ? j({}, 201) : undefined)],
  });
  const seed: Array<[string, unknown]> = [];
  // 91・92 は unknown (再投入の条件を満たす)。93 は split (検出の対照)。94 はラベル無しの unknown (再投入の対照)。
  for (const [n, labels, reason] of [
    [91, ["oc:no-pr", "pm-apply"], "unknown"],
    [92, ["oc:no-pr", "needs-user-input"], "unknown"],
    [93, ["oc:no-pr"], "split"],
    [94, ["oc:no-pr"], "unknown"],
  ] as Array<[number, string[], string]>) {
    seed.push(["issues", issueEv(n, { labels })]);
    seed.push(["issue_comment", commentEv(n, { login: IMPL }, outcomeBody(reason), at(10))]);
  }
  await sendAll(ctx, seed);
  await markFresh(ctx);
  assert.deepEqual(targets(ctx), ["no_pr#93"], "対照: ラベルの無い split の 93 だけが対象");
  const { picks, rows } = ctx.app.engine.plan();
  assert.deepEqual(picks.map((p) => p.n), [94], "対照: ラベルの無い unknown の 94 だけが再投入される (91・92 は hold で除外)");
  assert.ok(rows.user.some(([n]) => n === 91) && rows.user.some(([n]) => n === 92));
  await ctx.app.engine.launch(await (ctx.app.engine as any).d.gh());
  await ctx.app.engine.pmDispatch(await (ctx.app.engine as any).d.gh());
  const oc = ctx.m.calls.filter((c) => c.method === "POST" && /\/issues\/\d+\/comments$/.test(c.url));
  assert.deepEqual(oc.map((c) => c.url.match(/issues\/(\d+)\//)?.[1]), ["94"]);
  assert.deepEqual(pmCalls(ctx.m.calls).map((c) => c.body.client_payload), [{ kind: "no_pr", ref: 93 }]);
});

test("pm-apply の issue (oc:no-pr なし) も、ready なら着手しない。needs-user-input の user_answered は対象のまま", async () => {
  const ctx = await configuredApp();
  await sendAll(ctx, [
    ["issues", issueEv(95, { labels: ["pm-apply"] })],
    ["issues", issueEv(96, { labels: [] })],
    ["issues", issueEv(97, { labels: ["needs-user-input", "pm-apply"], action: "labeled", label: "needs-user-input", at: at(10) })],
    ["issue_comment", commentEv(97, HUMAN, "A", at(12))],
  ]);
  await markFresh(ctx);
  assert.deepEqual(ctx.app.engine.plan().picks.map((p) => p.n), [96]);
  assert.deepEqual(targets(ctx), ["user_answered#97"]);
});
