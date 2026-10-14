import { test } from "node:test";
import assert from "node:assert/strict";
import { appendSample, capValue, nextCap, peakRunning, saturatedRunning, targetEff, SAT_FLAT_MS, SAT_WINDOW_MS, type Sample } from "../src/saturation.ts";
import { configuredApp, issuePayload, runPayload, send, type Call } from "./helpers.ts";

type Ctx = Awaited<ReturnType<typeof configuredApp>>;

const comments = (calls: Call[]) => calls.filter((c) => c.method === "POST" && /\/issues\/\d+\/comments$/.test(c.url));
const dispatches = (calls: Call[]) => calls.filter((c) => c.method === "POST" && c.url.endsWith("/dispatches"));
const MIN = 60_000;

// 稼働 run を r 件、待ち run を q 件にする。余った run は completed にする。updated_at は今の時刻 (新しい順で適用される)。
async function shape(ctx: Ctx, r: number, q: number) {
  const at = new Date(ctx.clock.t).toISOString();
  for (let i = 0; i < 100; i++) {
    await send(ctx.app, "workflow_run", runPayload(1000 + i, i < r ? "in_progress" : "completed", { event: "issue_comment", at }));
    await send(ctx.app, "workflow_run", runPayload(2000 + i, i < q ? "queued" : "completed", { event: "issue_comment", at }));
  }
}

// 観測を 1 分ずつ進める (tick 相当)。
function minutes(ctx: Ctx, n: number) {
  for (let i = 0; i < n; i++) {
    ctx.clock.t += MIN;
    ctx.app.engine.observe(ctx.clock.t);
  }
}

const st = (ctx: Ctx) => ctx.app.engine.status() as any;

// ---------------------------------------------------------------------------------------------------------------- 純関数
test("targetEff: 推定が無ければ TARGET のまま。推定があれば 上限 + 余裕 を下限 TARGET_MIN と上限 TARGET の間に収める", () => {
  assert.equal(targetEff(undefined, 80, 10, 30), 80);
  assert.equal(targetEff(60, 80, 10, 30), 70, "正例: cap 60 → 70");
  assert.equal(targetEff(20, 80, 10, 30), 30, "正例: cap 20 → 30");
  assert.equal(targetEff(5, 80, 10, 30), 30, "異常値 cap 5 でも下限 30 を下回らない");
  assert.equal(targetEff(100, 80, 10, 30), 80, "TARGET を超えない");
  assert.equal(targetEff(60, 40, 10, 30), 40, "TARGET を 40 に下げると target_eff <= 40");
});

test("saturatedRunning: queued>0 かつ running が同じ値で 30 分続いたときだけ飽和。29 分では未飽和、途中の dip で切れる", () => {
  const mk = (n: number, r: number, q: number): Sample[] => Array.from({ length: n }, (_, i) => ({ t: i * MIN, r, q }));
  assert.equal(saturatedRunning(mk(31, 60, 20)), 60);
  assert.equal(saturatedRunning(mk(30, 60, 20)), undefined, "29 分 (0..29) では飽和ではない");
  assert.equal(saturatedRunning(mk(31, 40, 0)), undefined, "queued=0 は未飽和");
  const dip = mk(31, 60, 20).map((x, i) => (i === 15 ? { ...x, r: 59 } : x));
  assert.equal(saturatedRunning(dip), undefined, "同じ値が途切れた時点で streak は最後の値から数え直す");
  const gapped = [...mk(21, 60, 20), ...mk(11, 60, 20).map((x) => ({ ...x, t: x.t + 50 * MIN }))];
  assert.equal(saturatedRunning(gapped), undefined, "観測の空き (20〜50 分) をまたぐ streak は数えない (実際に平坦だったのは 10 分)");
  assert.ok(SAT_FLAT_MS === 30 * MIN && SAT_WINDOW_MS === 24 * 60 * MIN);
});

test("nextCap / capValue: 24 時間たつと推定は消える。上限を下げたあとの古い peak では押し上げない", () => {
  const flat: Sample[] = Array.from({ length: 32 }, (_, i) => ({ t: i * MIN, r: 60, q: 20 }));
  const cap = nextCap(undefined, flat, 31 * MIN);
  assert.deepEqual(cap, { value: 60, at: 31 * MIN });
  // 60 の peak は cap.at より前。20 で飽和したら 20 へ下げ、以後の 20 の観測では上がらない
  const obs: Sample[] = [...flat];
  for (let i = 0; i < 31; i++) obs.push({ t: (32 + i) * MIN, r: 20, q: 15 });
  const down = nextCap(cap, obs, (32 + 30) * MIN);
  assert.deepEqual(down, { value: 20, at: 62 * MIN });
  assert.equal(peakRunning(obs, 62 * MIN), 60, "24 時間の窓の peak は 60 のまま");
  assert.deepEqual(nextCap(down, [...obs, { t: 63 * MIN, r: 20, q: 15 }], 63 * MIN)?.value, 20);
  assert.equal(capValue(cap, cap.at + SAT_WINDOW_MS - 1), 60);
  assert.equal(capValue(cap, cap.at + SAT_WINDOW_MS), undefined, "24 時間で期限切れ");
});

// ---------------------------------------------------------------------------------------------------------------- 受入 6
test("(正例) running=60・queued=20 が 30 分続く → target_eff=70 (29 分では変えない)。dry-run なので POST は 0 回", async () => {
  const ctx = await configuredApp({ env: { TARGET: "80" } });
  await shape(ctx, 60, 20);
  ctx.app.engine.observe(ctx.clock.t);
  minutes(ctx, 29);
  assert.equal(st(ctx).target_eff, 80, "(b) queued>0 が 29 分だけ → 変えない");
  minutes(ctx, 1);
  const s = st(ctx);
  assert.equal(s.target, 80);
  assert.equal(s.target_eff, 70);
  assert.equal(s.cap_est, 60);
  assert.equal(s.queued, 20);
  assert.equal(s.oldest_queued_age_min, 30, "queued の経過分は 30");
  assert.equal(s.peak_running, 60);
  assert.equal(s.running.in_progress, 60, "既存の running の数え方は変えない");
  assert.equal(comments(ctx.m.calls).length + dispatches(ctx.m.calls).length, 0, "(f) dry-run の計算は POST を出さない");
});

test("(正例) running=20・queued=15 が 30 分続く → target_eff=30 (下限 TARGET_MIN)", async () => {
  const ctx = await configuredApp({ env: { TARGET: "80" } });
  await shape(ctx, 20, 15);
  ctx.app.engine.observe(ctx.clock.t);
  minutes(ctx, 30);
  assert.equal(st(ctx).target_eff, 30);
  assert.equal(st(ctx).cap_est, 20);
});

test("(a) running=40・queued=0 (未飽和) → target_eff=TARGET。(d) 上限を超えない (cap 100 でも 80)", async () => {
  const ctx = await configuredApp({ env: { TARGET: "80" } });
  await shape(ctx, 40, 0);
  minutes(ctx, 40);
  assert.equal(st(ctx).target_eff, 80);
  assert.equal(st(ctx).cap_est, null);
  await shape(ctx, 100, 20);
  minutes(ctx, 31);
  assert.equal(st(ctx).cap_est, 100);
  assert.equal(st(ctx).target_eff, 80, "TARGET (80) を超えない");
});

test("(c) cap_est=5 の異常値でも target_eff>=30", async () => {
  const ctx = await configuredApp({ env: { TARGET: "80" } });
  await shape(ctx, 5, 3);
  minutes(ctx, 31);
  assert.equal(st(ctx).cap_est, 5);
  assert.equal(st(ctx).target_eff, 30);
});

test("(g) TARGET を env で 40 に下げると target_eff<=40 (running=60・queued=20 が 30 分でも)", async () => {
  const ctx = await configuredApp({ env: { TARGET: "40" } });
  await shape(ctx, 60, 20);
  minutes(ctx, 31);
  assert.equal(st(ctx).target, 40);
  assert.equal(st(ctx).target_eff, 40);
});

test("(e) 24 時間の窓を過ぎ、飽和の観測が無ければ target_eff は TARGET に戻る", async () => {
  const ctx = await configuredApp({ env: { TARGET: "80" } });
  await shape(ctx, 60, 20);
  minutes(ctx, 31);
  assert.equal(st(ctx).target_eff, 70);
  ctx.clock.t += 25 * 60 * MIN;
  await shape(ctx, 0, 0);
  minutes(ctx, 1);
  const s = st(ctx);
  assert.equal(s.target_eff, 80);
  assert.equal(s.cap_est, null);
  assert.equal(s.peak_running, 0, "24 時間より前の観測は窓から落ちる");
});

test("上限が上がったら (peak が推定を超えたら) 引き上げる。上限が下がったら飽和で下げる", async () => {
  const ctx = await configuredApp({ env: { TARGET: "80" } });
  await shape(ctx, 20, 15);
  minutes(ctx, 31);
  assert.equal(st(ctx).cap_est, 20);
  // 上限が 60 に上がった想定。running が 20 から 45 へ、待ちは残ったまま (まだ飽和ではない)
  await shape(ctx, 45, 15);
  minutes(ctx, 1);
  assert.equal(st(ctx).cap_est, 45);
  assert.equal(st(ctx).target_eff, 55);
});

test("上限を 60 → 20 に下げても、24 時間の窓の 60 の peak で 20 を押し上げ直さない (target_eff=30 のまま)", async () => {
  const ctx = await configuredApp({ env: { TARGET: "80" } });
  await shape(ctx, 60, 20);
  minutes(ctx, 31);
  assert.equal(st(ctx).cap_est, 60);
  await shape(ctx, 20, 15);
  minutes(ctx, 31);
  const s = st(ctx);
  assert.equal(s.peak_running, 60, "窓の中には 60 の観測が残っている");
  assert.equal(s.cap_est, 20);
  assert.equal(s.target_eff, 30);
  minutes(ctx, 10);
  assert.equal(st(ctx).target_eff, 30, "その後も押し上げない");
});

test("room は target_eff で決まる: 上限 20 で 35 件 (running 20 + queued 15) がある間は新規 0 件", async () => {
  const ctx = await configuredApp({ env: { TARGET: "80" } });
  for (const n of [31, 32]) assert.equal((await send(ctx.app, "issues", issuePayload(n))).status, 202);
  await shape(ctx, 20, 15);
  minutes(ctx, 31);
  const { plan } = ctx.app.engine.plan();
  assert.equal(plan.targetEff, 30);
  assert.equal(plan.room, 0);
  assert.deepEqual(plan.picks, []);
});

test("観測の保持: 同じ分の観測は後の値で置き換え、24 時間より古いものは捨てる", () => {
  let obs: Sample[] = appendSample([], { t: 0, r: 1, q: 0 }, 0);
  obs = appendSample(obs, { t: 30_000, r: 2, q: 0 }, 30_000);
  assert.deepEqual(obs, [{ t: 30_000, r: 2, q: 0 }]);
  obs = appendSample(obs, { t: MIN, r: 3, q: 0 }, MIN);
  assert.equal(obs.length, 2);
  const now = SAT_WINDOW_MS + MIN;
  obs = appendSample(obs, { t: now, r: 4, q: 0 }, now);
  assert.deepEqual(obs, [{ t: now, r: 4, q: 0 }]);
});
