// 実装 run の打ち切りの連続: PR も出さずに cancelled / failure / timed_out で終わった run を issue ごとに数え、連続 KILLED_STOP_AT (2) 回で自動の再着手を止める。
// record-run-outcome.sh の always() step は runner の shutdown (exit 143) では走らず oc:no-pr が付かないので、Worker は workflow_run の conclusion で数える。
// 実測 (2026-10-12〜14): opencode.yaml の issue_comment で cancelled の run 100 件中、同じ題名 (issue) の run が FLE-7 10 件・SHX-T20 8 件・KH-13 6 件・KH-28 5 件。
import { test } from "node:test";
import assert from "node:assert/strict";
import { detectPm } from "../src/pm.ts";
import { KILLED_STOP_AT } from "../src/webhook.ts";
import { configuredApp, j, markFresh, runPayload, T0, type Call } from "./helpers.ts";
import { COLLAB_USER, commentEv, HUMAN, IMPL, IMPL_BOT, iso, issueEv, MEMBER_USER, OUTSIDER, outcomeBody, prEv, send, type Ctx } from "./pm_helpers.ts";

const PM_BOT = "oc-pm-for-signature-studio[bot]";
const comments = (calls: Call[], n?: number) => calls.filter((c) => c.method === "POST" && new RegExp(`/issues/${n ?? "\\d+"}/comments$`).test(c.url));
const title = (n: number) => `[CI-${n}] t`;
const sig = (ctx: Ctx, n: number) => ctx.app.engine.s.sig[String(n)]?.kill;

async function seed(ctx: Ctx, n: number, o: Parameters<typeof issueEv>[1] = {}) {
  assert.equal((await send(ctx.app, "issues", issueEv(n, o))).status, 202);
}
// issue_comment 由来の run の開始 / 完了の配送。
const started = (id: number, t: string, at: string, created = at) => runPayload(id, "in_progress", { event: "issue_comment", title: t, at, created });
function finished(id: number, conclusion: string, t: string, at: string, event = "issue_comment", created = at) {
  const p = runPayload(id, "completed", { event, title: t, at, created }) as any;
  p.workflow_run.conclusion = conclusion;
  return p;
}
async function kill(ctx: Ctx, n: number, id: number, at: string, conclusion = "cancelled") {
  await send(ctx.app, "workflow_run", started(id, title(n), at));
  await send(ctx.app, "workflow_run", finished(id, conclusion, title(n), at));
}

test("2 回連続で打ち切られた issue は stopped (killed x2) に置き、再着手の picks に入れず、PM agent (oc-pm の no_pr) に回す", async () => {
  const ctx = await configuredApp();
  await seed(ctx, 300);
  await seed(ctx, 301);
  await markFresh(ctx);
  await kill(ctx, 300, 1001, "2026-10-14T11:10:00Z");
  assert.deepEqual(sig(ctx, 300), { count: 1, at: "2026-10-14T11:10:00Z", run: 1001 });
  assert.equal(KILLED_STOP_AT, 2);
  assert.deepEqual(ctx.app.engine.killedIssues(), [], "1 回目では止めない");
  assert.ok(ctx.app.engine.plan().picks.some((p) => p.n === 300));
  await kill(ctx, 300, 1002, "2026-10-14T11:40:00Z", "failure");
  assert.deepEqual(sig(ctx, 300), { count: 2, at: "2026-10-14T11:40:00Z", run: 1002 });
  const p = ctx.app.engine.plan();
  assert.deepEqual(p.picks.map((x) => x.n), [301], "他の issue は着手する");
  assert.deepEqual(p.rows.stopped, [[300, "killed x2"]]);
  const s = ctx.app.engine.status() as any;
  assert.equal(s.killed_stopped, 1);
  assert.deepEqual(s.killed_issues, [300]);
  assert.equal(s.stopped, 1);
  assert.deepEqual(ctx.app.engine.detectPmTargets(), [{ kind: "no_pr", ref: 300, at: "2026-10-14T11:40:00Z" }]);
  assert.deepEqual(s.pm_detected, { user_answered: 0, needs_decision: 0, stuck: 0, no_pr: 1, refs_orphan: 0 });
});

test("LIVE: /oc を投稿した run が 2 回続けて打ち切られたら、3 回目は投稿しない (旧実装は cooldown ごとに無限に再投稿)", async () => {
  const clock = { t: T0 };
  const ctx = await configuredApp({ now: clock, live: true, handlers: [(c) => (/\/comments$/.test(c.url) && c.method === "POST" ? j({}, 201) : undefined)] });
  await seed(ctx, 310);
  const gh = await (ctx.app.engine as any).d.gh();
  const round = async (runId: number) => {
    await markFresh(ctx);
    await ctx.app.engine.launch(gh);
    const t = iso(clock.t);
    // Worker 自身の /oc 投稿の webhook (PM App の投稿)。打ち切りの連続を解く『応答』にはならない。
    if (comments(ctx.m.calls, 310).length > 0) await send(ctx.app, "issue_comment", commentEv(310, { login: PM_BOT }, "/oc oc_actions_allow_write\noc_artifacts: fl-win64", t));
    await send(ctx.app, "workflow_run", started(runId, title(310), t));
    clock.t += 10 * 60_000;
    await send(ctx.app, "workflow_run", finished(runId, "cancelled", title(310), iso(clock.t), "issue_comment", t));
  };
  await round(2001);
  assert.equal(comments(ctx.m.calls, 310).length, 1);
  clock.t += 4 * 3_600_000;
  await round(2002);
  assert.equal(comments(ctx.m.calls, 310).length, 2, "1 回目の打ち切りの後は再着手する");
  for (let i = 0; i < 3; i++) {
    clock.t += 30 * 3_600_000;
    await markFresh(ctx);
    await ctx.app.engine.launch(gh);
  }
  assert.equal(comments(ctx.m.calls, 310).length, 2, "2 回続けて打ち切られた後は、何時間たっても再投稿しない");
  assert.deepEqual(ctx.app.engine.plan().rows.stopped, [[310, "killed x2"]]);
});

test("concurrency で置換された待機中の run (後続の run がある cancelled) は数えない。コメントで起きて skipped になった run は後続に数えない", async () => {
  const ctx = await configuredApp();
  await seed(ctx, 320);
  await seed(ctx, 321);
  // 320: 待機中の run 3001 が、後から来た run 3002 に置き換えられて cancelled
  await send(ctx.app, "workflow_run", runPayload(3001, "queued", { event: "issue_comment", title: title(320), at: "2026-10-14T11:00:00Z" }));
  await send(ctx.app, "workflow_run", started(3002, title(320), "2026-10-14T11:00:05Z"));
  await send(ctx.app, "workflow_run", finished(3001, "cancelled", title(320), "2026-10-14T11:00:06Z"));
  assert.equal(sig(ctx, 320), undefined, "置換された run は数えない");
  await send(ctx.app, "workflow_run", finished(3002, "cancelled", title(320), "2026-10-14T11:20:00Z"));
  assert.equal(sig(ctx, 320)?.count, 1, "後続の無い最後の run は数える");
  // 321: agent 自身のコメントで起きた skipped の run (id が大きい) があっても、打ち切られた run は数える
  await send(ctx.app, "workflow_run", started(3101, title(321), "2026-10-14T11:00:00Z"));
  await send(ctx.app, "workflow_run", finished(3102, "skipped", title(321), "2026-10-14T11:10:00Z"));
  await send(ctx.app, "workflow_run", finished(3101, "cancelled", title(321), "2026-10-14T11:20:00Z"));
  assert.equal(sig(ctx, 321)?.count, 1);
});

test("連続: 成功した run は連続を断つ。skipped の run は断たない", async () => {
  const ctx = await configuredApp();
  await seed(ctx, 330);
  await seed(ctx, 331);
  await kill(ctx, 330, 4001, "2026-10-14T11:00:00Z");
  await kill(ctx, 330, 4002, "2026-10-14T11:10:00Z", "success");
  assert.equal(sig(ctx, 330), undefined, "成功で消える");
  await kill(ctx, 330, 4003, "2026-10-14T11:20:00Z");
  assert.equal(sig(ctx, 330)?.count, 1, "成功の後は 1 から数え直す");
  await kill(ctx, 331, 4101, "2026-10-14T11:00:00Z");
  await send(ctx.app, "workflow_run", finished(4102, "skipped", title(331), "2026-10-14T11:05:00Z"));
  await kill(ctx, 331, 4103, "2026-10-14T11:10:00Z", "timed_out");
  assert.equal(sig(ctx, 331)?.count, 2, "skipped は挟まっても連続のまま (timed_out も数える)");
});

test("数えない conclusion・event・題名: success 以外の neutral / skipped / action_required / startup_failure、issue_comment 以外、題名が一意に当たらない run", async () => {
  const ctx = await configuredApp();
  await seed(ctx, 340);
  let id = 5000;
  for (const c of ["neutral", "skipped", "action_required", "startup_failure", "stale", "unknown"]) await kill(ctx, 340, id++, "2026-10-14T11:00:00Z", c);
  assert.equal(sig(ctx, 340), undefined);
  // issue_comment 以外の run (fix・review) は実装 run ではない
  await send(ctx.app, "workflow_run", finished(id++, "cancelled", title(340), "2026-10-14T11:00:00Z", "pull_request_review"));
  await send(ctx.app, "workflow_run", finished(id++, "cancelled", title(340), "2026-10-14T11:00:00Z", "repository_dispatch"));
  assert.equal(sig(ctx, 340), undefined);
  // PR 上のコメントで起きた run (題名が PR の題名) は issue に当たらない
  await send(ctx.app, "workflow_run", finished(id++, "cancelled", "feat(pm-worker): 何かの PR", "2026-10-14T11:00:00Z"));
  // 同じ題名の open issue が 2 つ: どちらの run か分からないので数えない
  await seed(ctx, 341, { title: title(340) });
  await send(ctx.app, "workflow_run", finished(id++, "cancelled", title(340), "2026-10-14T11:00:00Z"));
  assert.equal(sig(ctx, 340), undefined);
  assert.equal(sig(ctx, 341), undefined);
  // closed の issue は数えない
  await seed(ctx, 342, { state: "closed" });
  await send(ctx.app, "workflow_run", finished(id++, "cancelled", title(342), "2026-10-14T11:00:00Z"));
  assert.equal(sig(ctx, 342), undefined);
});

test("PR を出していた run は数えない。PR が出たら連続を消す (ブランチ名 N-... か本文の Closes / Refs #N。closed の PR は消さない)", async () => {
  const ctx = await configuredApp();
  for (const n of [350, 351, 352, 353]) await seed(ctx, n);
  await send(ctx.app, "pull_request", prEv(900, { body: "Closes #350" }));
  await kill(ctx, 350, 6001, "2026-10-14T11:00:00Z");
  assert.equal(sig(ctx, 350), undefined, "open PR がある issue の打ち切りは数えない (着手済み)");
  await kill(ctx, 351, 6101, "2026-10-14T11:00:00Z");
  assert.equal(sig(ctx, 351)?.count, 1);
  await send(ctx.app, "pull_request", prEv(351, { at: "2026-10-14T11:30:00Z" })); // ブランチ名 351-x
  assert.equal(sig(ctx, 351), undefined, "PR が出たら消す");
  await kill(ctx, 352, 6201, "2026-10-14T11:00:00Z");
  await send(ctx.app, "pull_request", prEv(901, { body: "Refs #352", at: "2026-10-14T11:30:00Z" }));
  assert.equal(sig(ctx, 352), undefined, "本文の Refs #N でも消す");
  await kill(ctx, 353, 6301, "2026-10-14T11:00:00Z");
  const closed = prEv(902, { body: "Closes #353", at: "2026-10-14T11:30:00Z" });
  (closed.pull_request as any).state = "closed";
  await send(ctx.app, "pull_request", closed);
  assert.equal(sig(ctx, 353)?.count, 1, "closed の PR は着手済みにしない");
});

test("run の開始以降に merge された PR (open の一覧に出ない) も着手の証拠にする。開始より前に merge された PR は証拠にしない", async () => {
  const ctx = await configuredApp();
  await seed(ctx, 354);
  await seed(ctx, 355);
  const merged = (n: number, mergedAt: string) => {
    const e = prEv(n, { at: mergedAt });
    Object.assign(e.pull_request as any, { state: "closed", merged_at: mergedAt });
    return e;
  };
  await send(ctx.app, "pull_request", merged(354, "2026-10-14T11:05:00Z"));
  await send(ctx.app, "pull_request", merged(355, "2026-10-14T10:00:00Z"));
  for (const n of [354, 355]) {
    await send(ctx.app, "workflow_run", started(6400 + n, title(n), "2026-10-14T11:00:00Z"));
    await send(ctx.app, "workflow_run", finished(6400 + n, "cancelled", title(n), "2026-10-14T11:20:00Z", "issue_comment", "2026-10-14T11:00:00Z"));
  }
  assert.equal(sig(ctx, 354), undefined, "run の開始 (11:00) の後に merge された PR がある");
  assert.equal(sig(ctx, 355)?.count, 1, "run の開始より前 (10:00) に merge された PR は、この run の成果ではない");
});

test("issue が close されたら連続を消す。reopen したら 0 から数える", async () => {
  const ctx = await configuredApp();
  await seed(ctx, 360);
  await kill(ctx, 360, 7001, "2026-10-14T11:00:00Z");
  await kill(ctx, 360, 7002, "2026-10-14T11:10:00Z");
  assert.equal((ctx.app.engine.status() as any).killed_stopped, 1);
  await send(ctx.app, "issues", issueEv(360, { state: "closed", action: "closed", at: "2026-10-14T11:30:00Z" }));
  assert.equal(sig(ctx, 360), undefined);
  assert.equal((ctx.app.engine.status() as any).killed_stopped, 0);
  await send(ctx.app, "issues", issueEv(360, { action: "reopened", at: "2026-10-14T11:40:00Z" }));
  await kill(ctx, 360, 7003, "2026-10-14T11:50:00Z");
  assert.equal(sig(ctx, 360)?.count, 1);
});

test("コメントによる解除: PM の応答・PM のマーカー付き bot コメント・人の回答は連続を消す。Worker 自身の /oc・マーカーの無い bot・第三者・kill より前のコメントは消さない", async () => {
  const ctx = await configuredApp();
  const cases: Array<[number, string, ReturnType<typeof commentEv>, boolean]> = [
    [370, "Worker 自身の /oc (PM App)", commentEv(370, { login: PM_BOT }, "/oc oc_actions_allow_write\noc_artifacts: fl-win64", "2026-10-14T12:00:00Z"), false],
    [371, "実装 bot の報告 (マーカーなし)", commentEv(371, { login: IMPL }, "着手します", "2026-10-14T12:00:00Z"), false],
    [372, "第三者のコメント", commentEv(372, OUTSIDER, "どうなった?", "2026-10-14T12:00:00Z"), false],
    [373, "kill より前の PM コメント", commentEv(373, HUMAN, "様子を見ます", "2026-10-14T11:05:00Z"), false],
    [374, "PM のログインの通常コメント", commentEv(374, HUMAN, "分割します", "2026-10-14T12:00:00Z"), true],
    [375, "実装 bot の oc-pm-decision マーカー (PM agent)", commentEv(375, IMPL_BOT, "<!-- oc-pm-decision: rule=R4 reversible=yes -->\n分割", "2026-10-14T12:00:00Z"), true],
    [376, "MEMBER の人のコメント", commentEv(376, MEMBER_USER, "この issue は重い", "2026-10-14T12:00:00Z"), true],
    [377, "COLLABORATOR の人のコメント", commentEv(377, COLLAB_USER, "了解", "2026-10-14T12:00:00Z"), true],
    [378, "人の /oc は着手であって応答ではない", commentEv(378, HUMAN, "/oc oc_actions_allow_write", "2026-10-14T12:00:00Z"), false],
    [379, "実装 bot の oc-run-outcome", commentEv(379, IMPL_BOT, outcomeBody("unknown"), "2026-10-14T12:00:00Z"), false],
  ];
  for (const [n] of cases) {
    await seed(ctx, n);
    await kill(ctx, n, 8000 + n, "2026-10-14T11:10:00Z");
    assert.equal(sig(ctx, n)?.count, 1, `前提 #${n}`);
  }
  for (const [, , ev] of cases) await send(ctx.app, "issue_comment", ev);
  for (const [n, what, , released] of cases) assert.equal(sig(ctx, n) === undefined, released, `#${n} ${what}`);
});

test("再配送・順不同: 同じ完了の配送を重ねても 1 回。古い run の遅れた配送で数えない。reconcile が付けた conclusion=unknown は本当の完了で上書きして数える", async () => {
  const ctx = await configuredApp();
  await seed(ctx, 380);
  await kill(ctx, 380, 9001, "2026-10-14T11:00:00Z");
  await send(ctx.app, "workflow_run", finished(9001, "cancelled", title(380), "2026-10-14T11:00:00Z"));
  assert.equal(sig(ctx, 380)?.count, 1, "同じ配送の再送");
  await kill(ctx, 380, 9005, "2026-10-14T11:20:00Z");
  assert.equal(sig(ctx, 380)?.count, 2);
  await send(ctx.app, "workflow_run", started(9003, title(380), "2026-10-14T11:10:00Z"));
  await send(ctx.app, "workflow_run", finished(9003, "cancelled", title(380), "2026-10-14T11:15:00Z"));
  assert.deepEqual(sig(ctx, 380), { count: 2, at: "2026-10-14T11:20:00Z", run: 9005 }, "古い run (id が小さい) の遅れた配送は数えない");
  // reconcile が『一覧に無い』ことから completed / unknown にした後に、本当の完了が届く
  await seed(ctx, 381);
  await send(ctx.app, "workflow_run", started(9101, title(381), "2026-10-14T11:00:00Z"));
  await send(ctx.app, "workflow_run", finished(9101, "unknown", title(381), "2026-10-14T11:00:00Z"));
  assert.equal(sig(ctx, 381), undefined);
  await send(ctx.app, "workflow_run", finished(9101, "cancelled", title(381), "2026-10-14T11:01:00Z"));
  assert.equal(sig(ctx, 381)?.count, 1);
});

test("再配送・順不同 (2): 連続が解けた後の同じ完了の再配送は数え直さない。run が prune された後の古い run の遅れた配送も数えない", async () => {
  const ctx = await configuredApp();
  // 解除の後に、数えた run の完了が再配送されても 1 に戻さない (run の状態が残っている間)
  await seed(ctx, 382);
  await kill(ctx, 382, 9201, "2026-10-14T11:00:00Z");
  await send(ctx.app, "issue_comment", commentEv(382, HUMAN, "分割します", "2026-10-14T11:30:00Z"));
  assert.equal(sig(ctx, 382), undefined);
  await send(ctx.app, "workflow_run", finished(9201, "cancelled", title(382), "2026-10-14T11:00:00Z"));
  assert.equal(sig(ctx, 382), undefined, "同じ完了の再配送で再び数えない");
  // 最後に数えた run が prune された後でも、id の小さい run の遅れた配送は数えない
  await seed(ctx, 383);
  await kill(ctx, 383, 9305, "2026-10-14T11:20:00Z");
  delete (ctx.app.engine.s.runs as Record<string, unknown>)["9305"];
  await send(ctx.app, "workflow_run", started(9303, title(383), "2026-10-14T11:10:00Z"));
  await send(ctx.app, "workflow_run", finished(9303, "cancelled", title(383), "2026-10-14T11:15:00Z"));
  assert.deepEqual(sig(ctx, 383), { count: 1, at: "2026-10-14T11:20:00Z", run: 9305 });
});

test("人の /oc (PM の手動の再着手) は解除ではないが、oc-pm の no_pr は送らない (PM が応答済み)。その run がまた打ち切られれば再び検出する", async () => {
  const ctx = await configuredApp();
  await seed(ctx, 416);
  await kill(ctx, 416, 9810, "2026-10-14T11:10:00Z");
  await kill(ctx, 416, 9811, "2026-10-14T11:30:00Z");
  assert.deepEqual(ctx.app.engine.detectPmTargets().map((t) => t.ref), [416]);
  await send(ctx.app, "issue_comment", commentEv(416, HUMAN, "/oc oc_actions_allow_write", "2026-10-14T12:00:00Z"));
  assert.deepEqual(ctx.app.engine.killedIssues(), [[416, 2]], "自動の再着手は止めたまま");
  assert.deepEqual(ctx.app.engine.detectPmTargets(), []);
  await kill(ctx, 416, 9812, "2026-10-14T12:30:00Z");
  assert.deepEqual(ctx.app.engine.detectPmTargets().map((t) => t.ref), [416]);
});

test("明示的な終了状態 (oc:stuck / needs-user-input / blocked / pm-apply、blocked_by あり) の issue は数えない", async () => {
  const ctx = await configuredApp();
  const labels = ["oc:stuck", "needs-user-input", "blocked", "pm-apply"];
  for (const [i, l] of labels.entries()) {
    await seed(ctx, 390 + i, { labels: [l] });
    await kill(ctx, 390 + i, 9500 + i, "2026-10-14T11:00:00Z");
    assert.equal(sig(ctx, 390 + i), undefined, l);
  }
  const blocked = issueEv(395);
  (blocked.issue as any).issue_dependencies_summary = { total_blocked_by: 1 };
  await send(ctx.app, "issues", blocked);
  await kill(ctx, 395, 9510, "2026-10-14T11:00:00Z");
  assert.equal(sig(ctx, 395), undefined);
});

test("oc:no-pr の再投入 (reason=unknown) の枠に載る issue でも、打ち切りが連続していれば再着手しない", async () => {
  const clock = { t: T0 };
  const ctx = await configuredApp({ now: clock });
  await seed(ctx, 400, { labels: ["oc:no-pr"] });
  await send(ctx.app, "issue_comment", commentEv(400, IMPL_BOT, outcomeBody("unknown"), iso(T0 - 30 * 60_000)));
  clock.t += 30 * 3_600_000;
  await markFresh(ctx);
  assert.deepEqual(ctx.app.engine.plan().picks.map((p) => [p.n, p.np]), [[400, "unknown"]], "対照: 打ち切りの記録が無ければ cooldown の後に 1 回再着手する");
  await kill(ctx, 400, 9601, iso(clock.t - 3_000_000));
  await kill(ctx, 400, 9602, iso(clock.t - 1_000_000));
  const p = ctx.app.engine.plan();
  assert.deepEqual(p.picks, []);
  assert.deepEqual(p.rows.stopped, [[400, "killed x2"]]);
});

test("oc-pm の検出: no_pr として 1 回だけ送る。hold ラベル・PM の応答後・PR の後・起票者が許可外のものは送らない", async () => {
  const ctx = await configuredApp();
  for (const n of [410, 411, 412, 413]) await seed(ctx, n);
  await seed(ctx, 414, { labels: ["oc:no-pr"] });
  await send(ctx.app, "issue_comment", commentEv(414, IMPL_BOT, outcomeBody("split"), "2026-10-14T11:00:00Z"));
  for (const [i, n] of [410, 411, 412, 413, 414].entries()) {
    await kill(ctx, n, 9700 + i * 10, "2026-10-14T11:10:00Z");
    await kill(ctx, n, 9701 + i * 10, "2026-10-14T11:30:00Z");
  }
  assert.equal(ctx.app.engine.killedIssues().length, 5);
  assert.deepEqual(ctx.app.engine.detectPmTargets().map((t) => [t.kind, t.ref]).sort(), [["no_pr", 410], ["no_pr", 411], ["no_pr", 412], ["no_pr", 413], ["no_pr", 414]]);
  assert.equal(ctx.app.engine.detectPmTargets().filter((t) => t.ref === 414).length, 1, "oc:no-pr (split) の検出と重なる issue は 1 件");
  // 411: hold ラベルが付いた → 送らない (user 行)
  await send(ctx.app, "issues", issueEv(411, { labels: ["needs-user-input"], action: "labeled", at: "2026-10-14T11:40:00Z" }));
  // 412: PM agent が判断 (マーカー) を残した → 連続を消す
  await send(ctx.app, "issue_comment", commentEv(412, IMPL_BOT, "<!-- oc-pm-decision: rule=R4 reversible=yes -->", "2026-10-14T11:45:00Z"));
  // 413: PR が出た
  await send(ctx.app, "pull_request", prEv(413, { at: "2026-10-14T11:50:00Z" }));
  assert.deepEqual(ctx.app.engine.detectPmTargets().map((t) => t.ref).sort(), [410, 414]);
  // 起票者が許可されていない issue は対象にしない (既存の絞り込みのまま)
  await seed(ctx, 415, { author: OUTSIDER });
  await kill(ctx, 415, 9800, "2026-10-14T11:10:00Z");
  await kill(ctx, 415, 9801, "2026-10-14T11:30:00Z");
  assert.equal(ctx.app.engine.killedIssues().some(([n]) => n === 415), true);
  assert.ok(!detectPm(ctx.app.engine.s, { bots: [], npCount: () => 0 }).some((t) => t.ref === 415));
});

test("dry-run でも状態は数える (書き込みは無し)。oc-pm は would に記録する", async () => {
  const ctx = await configuredApp();
  await seed(ctx, 420);
  await kill(ctx, 420, 9900, "2026-10-14T11:10:00Z");
  await kill(ctx, 420, 9901, "2026-10-14T11:30:00Z");
  await markFresh(ctx);
  const gh = await (ctx.app.engine as any).d.gh();
  const r = await ctx.app.engine.pmDispatch(gh);
  assert.deepEqual(r.would.map((t) => [t.kind, t.ref]), [["no_pr", 420]]);
  assert.deepEqual(r.sent, []);
  assert.ok(ctx.m.calls.every((c) => c.method === "GET" || c.url.includes("/app/") || c.url.includes("/app-manifests/")), "dry-run は GitHub に書き込まない");
});
