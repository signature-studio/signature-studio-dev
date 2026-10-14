import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { countOpenPrs, nextReviewOnly } from "../src/phase.ts";
import { REPO, configuredApp, issuePayload, send } from "./helpers.ts";

const here = fileURLToPath(new URL(".", import.meta.url));
const fixturePath = `${here}fixtures/phase.input.json`;
const crosscheck = `${here}phase_crosscheck.py`;

const prPayload = (n: number, labels: string[], state = "open", o: { title?: string; body?: string } = {}) => ({
  action: "opened",
  repository: REPO,
  pull_request: {
    number: n,
    state,
    merged_at: null,
    draft: false,
    head: { ref: `${n}-x` },
    title: o.title ?? `pr ${n}`,
    body: o.body ?? "",
    updated_at: "2026-10-14T11:00:00Z",
    labels: labels.map((name) => ({ name })),
  },
});

// 非 stuck の open PR を plain 件、oc:stuck の open PR を stuck 件 webhook で入れる。
async function seedPrs(ctx: Awaited<ReturnType<typeof configuredApp>>, plain: number, stuck: number) {
  for (let i = 0; i < plain; i++) assert.equal((await send(ctx.app, "pull_request", prPayload(1000 + i, ["oc:ready"]))).status, 202);
  for (let i = 0; i < stuck; i++) assert.equal((await send(ctx.app, "pull_request", prPayload(2000 + i, ["oc:stuck"]))).status, 202);
}

// plan() の戻りを、判定に使う形 (phase / picks / stop / 集計) にそろえる。
const phaseOf = (ctx: Awaited<ReturnType<typeof configuredApp>>, prev?: boolean) => {
  if (prev !== undefined) ctx.store.put("meta", "phase", { review_only: prev });
  const { plan, picks } = ctx.app.engine.plan();
  return { phase: plan.phase, picks, stop: plan.stop, open_prs_excl_stuck: plan.open_prs_excl_stuck, stuck_prs: plan.stuck_prs };
};

test("Python 版 (launch_issues.py) と同じ数値: 固定 JSON で TS の count/phase が一致する", () => {
  const fx = JSON.parse(readFileSync(fixturePath, "utf8"));
  const py = JSON.parse(execFileSync("python3", [crosscheck, fixturePath], { encoding: "utf8" }));
  const ts = fx.cases.map((c: any) => {
    const { openExclStuck, stuck } = countOpenPrs(c.pulls.map((p: any) => ({ state: p.state, labels: p.labels.map((l: any) => l.name) })));
    return { open_prs_excl_stuck: openExclStuck, stuck, review_only: nextReviewOnly(c.prev, openExclStuck) };
  });
  assert.deepEqual(ts, py);
});

test("(a) stuck 17 + 非 stuck 8 → launch (stuck は数えない)", async () => {
  const ctx = await configuredApp();
  await send(ctx.app, "issues", issuePayload(11));
  await seedPrs(ctx, 8, 17);
  const p = phaseOf(ctx, false);
  assert.equal(p.phase.review_only, false);
  assert.equal(p.open_prs_excl_stuck, 8);
  assert.equal(p.stuck_prs, 17);
  assert.deepEqual(p.picks.map((x) => x.n), [11]);
});

test("(b) 非 stuck 85 → review-only で picks=[]", async () => {
  const ctx = await configuredApp();
  await send(ctx.app, "issues", issuePayload(11));
  await seedPrs(ctx, 85, 0);
  const p = phaseOf(ctx, false);
  assert.equal(p.phase.review_only, true);
  assert.deepEqual(p.picks, []);
});

test("(c) 境界: 80 は直前が LAUNCH なら launch / 81 で review-only / 直前が review-only の 10 は review-only / 9 で launch", async () => {
  const cases: Array<[number, boolean, boolean]> = [
    [80, false, false],
    [81, false, true],
    [10, true, true],
    [9, true, false],
  ];
  for (const [n, prev, want] of cases) {
    const ctx = await configuredApp();
    await send(ctx.app, "issues", issuePayload(11));
    await seedPrs(ctx, n, 0);
    const p = phaseOf(ctx, prev);
    assert.equal(p.phase.review_only, want, `open=${n} prev=${prev}`);
    assert.equal(p.picks.length === 0, want, `picks は review-only の間だけ空`);
  }
});

test("(c') 非 stuck 79 + stuck 30 は、直前が LAUNCH なら launch・直前が review-only なら review-only のまま", async () => {
  for (const [prev, want] of [
    [false, false],
    [true, true],
  ] as const) {
    const ctx = await configuredApp();
    await send(ctx.app, "issues", issuePayload(11));
    await seedPrs(ctx, 79, 30);
    assert.equal(phaseOf(ctx, prev).phase.review_only, want);
  }
});

test("(d) stuck 41 (STUCK_HIGH=40 超) → launch を止める (stuck-ceiling)", async () => {
  const ctx = await configuredApp();
  await send(ctx.app, "issues", issuePayload(11));
  await seedPrs(ctx, 5, 41);
  const p = phaseOf(ctx, false);
  assert.equal(p.stop, "stuck-ceiling");
  assert.deepEqual(p.picks, []);
});

test("(d') stuck 40 ちょうどは止めない (上限は超えたときだけ)", async () => {
  const ctx = await configuredApp();
  await send(ctx.app, "issues", issuePayload(11));
  await seedPrs(ctx, 5, 40);
  const p = phaseOf(ctx, false);
  assert.equal(p.stop, undefined);
  assert.deepEqual(p.picks.map((x) => x.n), [11]);
});

// 既定 review_only: true は 10〜80 の帯 (直前の値を使う区間) でだけ効く。帯の中の 30 件で確かめる。
test("(e) ネガコン: 状態なし (phase 未保存) → 帯の中では review-only。旧実装は常に launch だった", async () => {
  const ctx = await configuredApp();
  await send(ctx.app, "issues", issuePayload(11));
  await seedPrs(ctx, 30, 0);
  const p = phaseOf(ctx);
  assert.equal(p.phase.review_only, true);
  assert.deepEqual(p.picks, []);
});

test("(f) /status は集計だけを返し、PR・issue の題名と本文を含まない", async () => {
  const ctx = await configuredApp();
  await send(ctx.app, "issues", issuePayload(11, { title: "[CI-11] SECRET-ISSUE-TITLE" }));
  await send(ctx.app, "pull_request", prPayload(1000, ["oc:ready"], "open", { title: "SECRET-PR-TITLE", body: "SECRET-PR-BODY" }));
  await send(ctx.app, "pull_request", prPayload(2000, ["oc:stuck"], "open", { title: "SECRET-STUCK-TITLE", body: "SECRET-STUCK-BODY" }));
  const res = await ctx.app.handle(new Request("https://pm.example/status"));
  const text = await res.text();
  const s = JSON.parse(text);
  // 状態なしの既定は review-only だが、非 stuck 1 件 (< 10) なので解除されて launch になる
  assert.equal(s.phase, "launch");
  assert.equal(s.open_prs_excl_stuck, 1);
  assert.equal(s.stuck_prs, 1);
  assert.equal(s.open_prs, 2, "既存キーは変えない");
  assert.ok(!/SECRET-/.test(text), "個票 (題名・本文) を /status に出さない");
});
