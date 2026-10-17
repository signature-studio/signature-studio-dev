// 同時実行の計数: room は opencode.yaml の全 run (event を問わず in_progress + queued など) の総数を基準にする。
// 2026-10-14 15:30Z の実測 (GitHub: opencode.yaml の in_progress 43 + pending 4) を固定値にして、旧い数え方 (実装・fix の run だけ) との差を検査する。
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { countOpencodeRuns, countRunsByPrio } from "../src/active.ts";
import { loadConfig } from "../src/config.ts";
import { isOpencodeRun, workflowFile, type RunState } from "../src/webhook.ts";
import { configuredApp, issuePayload, j, markFresh, runPayload, send, T0, type Call } from "./helpers.ts";

const OPENCODE = ".github/workflows/opencode.yaml";

type Wr = { event?: string; title?: string; path?: string | null; viaWorkflow?: string };
// workflow_run の配送。path は既定で opencode.yaml (null で path なし、viaWorkflow で webhook の workflow オブジェクト側に置く)。
function wr(id: number, status: string, o: Wr = {}) {
  const p = runPayload(id, status, { event: o.event, title: o.title }) as any;
  if (o.viaWorkflow) p.workflow = { path: o.viaWorkflow };
  else if (o.path !== null) p.workflow_run.path = o.path ?? OPENCODE;
  return p;
}

// 2026-10-14 15:30Z、GitHub の opencode.yaml: in_progress 43 (issue_comment 4・pull_request 21・pull_request_review 14・oc-fix 4) + pending 4 (pull_request)。
// 同時刻の Worker /status は active_runs=23 (pull_request を数えない) だった。
const MEASURED: Array<[string, string, string]> = [];
for (let i = 0; i < 4; i++) MEASURED.push(["in_progress", "issue_comment", `[IMPL-${i}] t`]);
for (let i = 0; i < 21; i++) MEASURED.push(["in_progress", "pull_request", `pr review ${i}`]);
for (let i = 0; i < 14; i++) MEASURED.push(["in_progress", "pull_request_review", `fix ${i}`]);
for (let i = 0; i < 4; i++) MEASURED.push(["in_progress", "repository_dispatch", `oc-fix #${900 + i}`]);
for (let i = 0; i < 4; i++) MEASURED.push(["pending", "pull_request", `pr pending ${i}`]);

async function loadMeasured(ctx: Awaited<ReturnType<typeof configuredApp>>) {
  let id = 1;
  for (const [status, event, title] of MEASURED) await send(ctx.app, "workflow_run", wr(id++, status, { event, title }));
  // 別 workflow の run (数えない)
  await send(ctx.app, "workflow_run", wr(id++, "in_progress", { event: "pull_request", path: ".github/workflows/scripts-test.yaml" }));
  await send(ctx.app, "workflow_run", wr(id++, "queued", { event: "workflow_dispatch", path: ".github/workflows/terms-watch.yaml" }));
}

// 旧い数え方 (engine.ts の countActive。issue_comment / workflow_dispatch / pull_request_review / oc-fix だけを、workflow を問わず数える)。
const legacyActive = (runs: RunState[]): number =>
  runs.filter((r) => r.status !== "completed" && (["issue_comment", "workflow_dispatch", "pull_request_review"].includes(r.event) || (r.event === "repository_dispatch" && r.title.startsWith("oc-fix")))).length;

const run = (id: number, status: string, event: string, o: Partial<RunState> = {}): RunState => ({ id, event, title: `run ${id}`, status, conclusion: null, updatedAt: "2026-10-14T11:30:00Z", ...o });

test("countOpencodeRuns: event を問わず opencode.yaml の未完了の run を全て数え、impl / other / event 別に分ける", () => {
  const c = countOpencodeRuns([
    run(1, "in_progress", "issue_comment", { wf: "opencode.yaml" }),
    run(2, "queued", "workflow_dispatch", { wf: "opencode.yaml" }),
    run(3, "in_progress", "pull_request", { wf: "opencode.yaml" }),
    run(4, "pending", "pull_request_review", { wf: "opencode.yaml" }),
    run(5, "in_progress", "repository_dispatch", { wf: "opencode.yaml", title: "oc-fix #1" }),
    run(6, "in_progress", "repository_dispatch", { wf: "opencode.yaml", title: "oc-pm no_pr #2" }),
    run(7, "waiting", "repository_dispatch", { wf: "opencode.yaml", title: "watchdog" }),
    run(8, "in_progress", "schedule", { wf: "opencode.yaml" }),
    run(9, "requested", "push", { wf: "opencode.yaml" }),
    run(10, "completed", "issue_comment", { wf: "opencode.yaml", conclusion: "success" }),
  ]);
  assert.deepEqual(c, {
    impl: 2,
    other: 7,
    all: 9,
    byEvent: { issue_comment: 1, workflow_dispatch: 1, pull_request: 1, pull_request_review: 1, "repository_dispatch:oc-fix": 1, "repository_dispatch:oc-pm": 1, "repository_dispatch:watchdog": 1, schedule: 1, push: 1 },
  });
});

test("countOpencodeRuns: 別 workflow の run は数えない。path の無い run (古い保存値) は opencode.yaml として数える", () => {
  const c = countOpencodeRuns([
    run(1, "in_progress", "pull_request", { wf: "scripts-test.yaml" }),
    run(2, "in_progress", "schedule", { wf: "terms-watch.yaml" }),
    run(3, "in_progress", "issue_comment"),
    run(4, "in_progress", "pull_request", { wf: "opencode.yaml" }),
  ]);
  assert.equal(c.all, 2);
  assert.equal(isOpencodeRun(run(5, "queued", "push", { wf: "opencode.yml" })), false, "拡張子違いは別 workflow");
});

test("workflowFile: REST / webhook の path からファイル名を取る (@ref 付きも)", () => {
  assert.equal(workflowFile(OPENCODE), "opencode.yaml");
  assert.equal(workflowFile(`${OPENCODE}@refs/heads/main`), "opencode.yaml");
  assert.equal(workflowFile("opencode.yaml"), "opencode.yaml");
  assert.equal(workflowFile(""), undefined);
  assert.equal(workflowFile(undefined), undefined);
  assert.equal(workflowFile(42), undefined);
});

test("実測 (15:30Z): opencode.yaml は 47 件。旧い数え方だと 23 件で、room が 35 に膨らむ (TARGET=58 なら正しくは 11)", async () => {
  const ctx = await configuredApp();
  await loadMeasured(ctx);
  const runs = Object.values(ctx.app.engine.s.runs);
  assert.equal(legacyActive(runs), 23, "旧: 別 workflow の workflow_dispatch まで数え、pull_request の review は数えない");
  const c = ctx.app.engine.activeRuns();
  assert.deepEqual({ impl: c.impl, other: c.other, all: c.all }, { impl: 4, other: 43, all: 47 });
  assert.deepEqual(c.byEvent, { issue_comment: 4, pull_request: 25, pull_request_review: 14, "repository_dispatch:oc-fix": 4 });
  await markFresh(ctx);
  const s = ctx.app.engine.status() as any;
  assert.equal(s.target, 58, "既定の TARGET");
  assert.equal(s.active_runs, 47);
  assert.equal(s.active_all, 47);
  assert.equal(s.active_impl, 4);
  assert.equal(s.active_other, 43);
  assert.equal(s.queued, 5, "queued は #2381 の定義のまま (workflow を問わず queued・pending・waiting の合計)");
  assert.equal(s.room, 11, "58 - 47");
  assert.deepEqual(s.running, { in_progress: 44, queued: 1, pending: 4 }, "running は従来どおり workflow を問わない");
});

test("launch (LIVE): ready が十分あっても、投稿するのは room (= TARGET - opencode.yaml の全 run) 件だけ。合計は TARGET を超えない", async () => {
  const ctx = await configuredApp({ live: true, handlers: [(c) => (/\/issues\/\d+\/comments$/.test(c.url) && c.method === "POST" ? j({ html_url: "x" }, 201) : undefined)] });
  await loadMeasured(ctx);
  for (let n = 100; n < 120; n++) assert.equal((await send(ctx.app, "issues", issuePayload(n))).status, 202);
  await markFresh(ctx);
  const gh = await (ctx.app.engine as any).d.gh();
  const plan = await ctx.app.engine.launch(gh);
  assert.equal(plan.room, 11);
  const posted = ctx.m.calls.filter((c: Call) => c.method === "POST" && /\/issues\/\d+\/comments$/.test(c.url));
  assert.equal(posted.length, 11, "旧い数え方なら room=35 で ready 20 件を全て投稿していた");
  assert.equal(plan.active + posted.length, 58, "合計は TARGET");
});

test("launch: opencode.yaml の run が TARGET に達していれば投稿しない。1 件下回れば 1 件だけ投稿する", async () => {
  const ctx = await configuredApp({ live: true, handlers: [(c) => (/\/issues\/\d+\/comments$/.test(c.url) && c.method === "POST" ? j({ html_url: "x" }, 201) : undefined)] });
  for (let i = 1; i <= 57; i++) await send(ctx.app, "workflow_run", wr(i, i % 2 ? "in_progress" : "queued", { event: i % 3 ? "pull_request" : "pull_request_review" }));
  for (let n = 200; n < 205; n++) await send(ctx.app, "issues", issuePayload(n));
  await markFresh(ctx);
  const gh = await (ctx.app.engine as any).d.gh();
  let plan = await ctx.app.engine.launch(gh);
  assert.equal(plan.active, 57);
  assert.equal(plan.room, 1);
  const posted = () => ctx.m.calls.filter((c: Call) => c.method === "POST" && /\/issues\/\d+\/comments$/.test(c.url)).length;
  assert.equal(posted(), 1);
  await send(ctx.app, "workflow_run", wr(58, "in_progress", { event: "issue_comment", title: "[CI-200] t200" }));
  plan = await ctx.app.engine.launch(gh);
  assert.equal(plan.room, 0);
  assert.equal(posted(), 1, "room=0 では投稿しない");
});

test("workflow_run: path は run 自身か webhook の workflow オブジェクトから取り、配送に無ければ既知の値を残す", async () => {
  const ctx = await configuredApp();
  await send(ctx.app, "workflow_run", wr(1, "in_progress", { path: null, viaWorkflow: ".github/workflows/scripts-test.yaml" }));
  await send(ctx.app, "workflow_run", wr(2, "in_progress", { path: `${OPENCODE}@refs/heads/main` }));
  assert.equal(ctx.app.engine.s.runs["1"].wf, "scripts-test.yaml");
  assert.equal(ctx.app.engine.s.runs["2"].wf, "opencode.yaml");
  assert.equal(ctx.app.engine.countActive(), 1);
  // path の無い後続の配送 (updated_at が新しい) でも wf を失わない
  const later = wr(1, "completed", { path: null });
  later.workflow_run.updated_at = "2026-10-14T11:40:00Z";
  await send(ctx.app, "workflow_run", later);
  assert.equal(ctx.app.engine.s.runs["1"].wf, "scripts-test.yaml");
  assert.equal(ctx.app.engine.s.runs["1"].status, "completed");
});

test("reconcile: REST の run (path 付き) で、path の無かった保存値が opencode.yaml / 別 workflow に分かれる", async () => {
  const clock = { t: Date.parse("2026-10-14T12:00:00Z") };
  const rest = [
    { id: 1, event: "pull_request", display_title: "r1", status: "in_progress", conclusion: null, updated_at: "2026-10-14T11:30:00Z", path: OPENCODE },
    { id: 2, event: "pull_request", display_title: "r2", status: "in_progress", conclusion: null, updated_at: "2026-10-14T11:30:00Z", path: ".github/workflows/scripts-test.yaml" },
  ];
  const ctx = await configuredApp({
    now: clock,
    handlers: [
      (c) => {
        if (c.method !== "GET") return undefined;
        const u = new URL(c.url);
        if (u.pathname.endsWith("/actions/runs")) return j({ workflow_runs: u.searchParams.get("status") === "in_progress" ? rest : [] });
        if (/\/repos\/[^/]+\/[^/]+\/issues$/.test(u.pathname) || u.pathname.endsWith("/issues/comments") || u.pathname.endsWith("/pulls")) return j([]);
        return undefined;
      },
    ],
  });
  // 旧い保存値 (wf なし) を作る
  await send(ctx.app, "workflow_run", wr(1, "in_progress", { event: "pull_request", path: null }));
  await send(ctx.app, "workflow_run", wr(2, "in_progress", { event: "pull_request", path: null }));
  assert.equal(ctx.app.engine.countActive(), 2, "path が分かるまでは過大に数える");
  await markFresh(ctx);
  clock.t += 6 * 60_000;
  await ctx.app.engine.reconcile((await (ctx.app.engine as any).d.gh()) as any);
  assert.equal(ctx.app.engine.countActive(), 1);
  assert.equal(ctx.app.engine.s.runs["2"].wf, "scripts-test.yaml");
});

test("#2381 との結合: room = target_eff - active_all。推定の上限があれば target_eff が下がり、active_all を引いた残りが room になる", async () => {
  const ctx = await configuredApp();
  await loadMeasured(ctx);
  await markFresh(ctx);
  const room = (cap: { value: number; at: number } | undefined) => {
    ctx.app.engine.meta.cap = cap;
    const s = ctx.app.engine.status() as any;
    return [s.target_eff, s.room, s.active_all];
  };
  assert.deepEqual(room(undefined), [58, 11, 47], "推定が無ければ target_eff = TARGET");
  assert.deepEqual(room({ value: 55, at: T0 }), [58, 11, 47], "55 + 余裕 10 は TARGET を超えない");
  assert.deepEqual(room({ value: 40, at: T0 }), [50, 3, 47]);
  assert.deepEqual(room({ value: 20, at: T0 }), [30, 0, 47], "下限 30 でも active_all が上回れば room は 0");
});

test("TARGET: 既定は 58 (opencode.yaml の run の総数の目標)。wrangler.toml も 58 で、env で下げられる", () => {
  assert.equal(loadConfig({}, {}).target, 58);
  assert.equal(loadConfig({ TARGET: "40" }, {}).target, 40);
  const toml = readFileSync(new URL("../wrangler.toml", import.meta.url), "utf8");
  assert.match(toml, /^TARGET = "58"$/m);
});

test("NO_PR_COOLDOWN_H: 既定は 1 時間。wrangler.toml も 1 で、env で変えられる (#2650・CI-232)", () => {
  assert.equal(loadConfig({}, {}).noPrCooldownH, 1);
  assert.equal(loadConfig({ NO_PR_COOLDOWN_H: "2" }, {}).noPrCooldownH, 2);
  const toml = readFileSync(new URL("../wrangler.toml", import.meta.url), "utf8");
  assert.match(toml, /^NO_PR_COOLDOWN_H = "1"$/m);
});

test("LOW_CAP: 既定は 10。空・空白・非数・負は既定に戻し、0 は有効。wrangler.toml も 10 (#2721)", () => {
  assert.equal(loadConfig({}, {}).lowCap, 10);
  assert.equal(loadConfig({ LOW_CAP: "" }, {}).lowCap, 10);
  assert.equal(loadConfig({ LOW_CAP: "  " }, {}).lowCap, 10);
  assert.equal(loadConfig({ LOW_CAP: "abc" }, {}).lowCap, 10);
  assert.equal(loadConfig({ LOW_CAP: "-1" }, {}).lowCap, 10);
  assert.equal(loadConfig({ LOW_CAP: "0" }, {}).lowCap, 0);
  assert.equal(loadConfig({ LOW_CAP: "4" }, {}).lowCap, 4);
  const toml = readFileSync(new URL("../wrangler.toml", import.meta.url), "utf8");
  assert.match(toml, /^LOW_CAP = "10"$/m);
});

test("STOPPED_INTAKE_PER_H: 既定は 48 (停止行の 1 時間の上限。#5722・#5899)。wrangler.toml も 48 で、env で下げられる", () => {
  assert.equal(loadConfig({}, {}).stoppedIntakePerH, 48);
  assert.equal(loadConfig({ STOPPED_INTAKE_PER_H: "12" }, {}).stoppedIntakePerH, 12);
  assert.equal(loadConfig({ STOPPED_INTAKE_PER_H: "0" }, {}).stoppedIntakePerH, 0, "0 は停止行の受け渡しを止める");
  assert.equal(loadConfig({ STOPPED_INTAKE_PER_H: "abc" }, {}).stoppedIntakePerH, 48, "非数は既定に戻す");
  // wake (CI-250) の既定と上書き。wrangler.toml も同じ値。
  assert.equal(loadConfig({}, {}).wakePerH, 24);
  assert.equal(loadConfig({}, {}).wakeRefDayMax, 2);
  assert.equal(loadConfig({ WAKE_PER_H: "6", WAKE_REF_DAY_MAX: "1" }, {}).wakePerH, 6);
  assert.equal(loadConfig({ WAKE_PER_H: "0" }, {}).wakePerH, 0, "0 は wake を止める");
  const toml = readFileSync(new URL("../wrangler.toml", import.meta.url), "utf8");
  assert.match(toml, /^STOPPED_INTAKE_PER_H = "48"$/m);
  assert.match(toml, /^WAKE_PER_H = "24"$/m);
  assert.match(toml, /^WAKE_REF_DAY_MAX = "2"$/m);
});

test("active: 未完了の opencode.yaml の run を区分別に数える。合計は all と一致し、対応の取れない run は normal (#2721)", () => {
  const issues = [
    { title: "[A-1] a", prio: "low" as const },
    { title: "[A-2] b", prio: "critical" as const },
    { title: "[A-3] c", prio: "normal" as const },
    { title: "[A-4] dup", prio: "low" as const },
    { title: "[A-4] dup", prio: "normal" as const },
  ];
  const run = (id: number, event: string, title: string, status: string, wf?: string) =>
    ({ id, event, title, status, conclusion: null, updatedAt: "2026-10-14T11:00:00Z", ...(wf ? { wf } : {}) }) as RunState;
  const runs = [
    run(1, "issue_comment", "[A-1] a", "in_progress"),
    run(2, "workflow_dispatch", " [A-2] b ", "queued"),
    run(3, "issue_comment", "[A-3] c", "completed"),
    run(4, "issue_comment", "[A-4] dup", "in_progress"),
    run(5, "pull_request_review", "[A-1] a", "in_progress"),
    run(6, "issue_comment", "unknown", "in_progress"),
    run(7, "issue_comment", "[A-1] a", "in_progress", "other.yaml"),
  ];
  const by = countRunsByPrio(runs, issues);
  assert.deepEqual(by, { critical: 1, normal: 3, low: 1 });
  assert.equal(by.critical + by.normal + by.low, countOpencodeRuns(runs).all);
});
