// /status の自律運転の指標 (#2335)。fixture ごとに期待値を確かめ、24 時間の窓・Refs のみの判定・履歴の欠落・個票の非表示 (ネガコン) を見る。
// 時刻は configuredApp({ now: clock }) で進める。REST の一覧は syncWorld() が正 (tick の同期が webhook と食い違わないように)。
import { test } from "node:test";
import assert from "node:assert/strict";
import { refsOnlyBody } from "../src/webhook.ts";
import { PM_LIMITS } from "../src/pm.ts";
import { refsOnlyNumbers } from "../src/refs.ts";
import { BOT, MARK, REPO, T0, commentPayload, configuredApp, issuePayload, j, markFresh, runPayload, send, type Call } from "./helpers.ts";
import { outcomeBody, stopBody } from "./pm_helpers.ts";

type Ctx = Awaited<ReturnType<typeof configuredApp>>;

const MIN = 60_000;
const H = 60 * MIN;
const iso = (ms: number) => new Date(ms).toISOString();
const status = async (ctx: Ctx): Promise<any> => (await ctx.app.handle(new Request("https://pm.example/status"))).json();

// pull_request の webhook。merged_at を入れると merge 済み (GitHub は merge の後 state=closed)。
const prPayload = (n: number, o: { state?: "open" | "closed"; mergedAt?: number; body?: string; labels?: string[]; updatedAt?: number; title?: string } = {}) => ({
  action: o.state === "closed" ? "closed" : "opened",
  repository: REPO,
  pull_request: {
    number: n,
    state: o.state ?? "open",
    merged_at: o.mergedAt === undefined ? null : iso(o.mergedAt),
    draft: false,
    head: { ref: `${n}-x` },
    title: o.title ?? `pr ${n}`,
    body: o.body ?? "",
    labels: (o.labels ?? []).map((name) => ({ name })),
    updated_at: iso(o.updatedAt ?? o.mergedAt ?? T0 - 5 * MIN),
    user: { login: BOT, type: "Bot" },
    author_association: "NONE",
  },
});

// tick の同期に要る REST の最小モック。open issue の一覧は rest.issues が正。fail = true なら一覧が 500 を返す。
function syncWorld() {
  const rest = { issues: [] as any[], fail: false };
  const handlers = [
    (c: Call) => {
      if (c.method !== "GET") return undefined;
      const p = new URL(c.url).pathname;
      if (/\/issues$/.test(p)) return rest.fail ? j({ message: "down" }, 500) : j(rest.issues);
      if (p.endsWith("/pulls")) return j([]);
      if (p.endsWith("/actions/runs")) return j({ workflow_runs: [] });
      if (p.endsWith("/issues/comments")) return j([]);
      if (/\/dependencies\/blocked_by$/.test(p)) return j([]);
      return undefined;
    },
  ];
  return { rest, handlers };
}

// oc:stuck の PR に、停止コメント (bot 投稿) を付ける。
async function seedStuck(ctx: Ctx, prs: number[]) {
  for (const n of prs) {
    await send(ctx.app, "pull_request", prPayload(n, { labels: ["oc:stuck"], updatedAt: T0 - 5 * MIN }));
    await send(ctx.app, "issue_comment", commentPayload(n, MARK, stopBody(n), iso(T0 - 10 * MIN)));
  }
}

// ---------------------------------------------------------------------------------------------------------------- 受入 1
test("自律運転の指標: 空の状態では件数は 0、率・差・起点は null (捏造しない)", async () => {
  const s = await status(await configuredApp());
  assert.equal(s.stuck, 0);
  assert.equal(s.stuck_age_max_min, null);
  assert.equal(s.needs_pm, 0);
  assert.equal(s.needs_user, 0);
  assert.deepEqual(s.no_pr_by_reason, { split: 0, artifact: 0, unknown: 0, blocked: 0, stop: 0 });
  assert.deepEqual(s.refs_only_merge_rate_24h, { merged: 0, refs_only: 0, rate: null });
  assert.equal(s.open_issues_delta_24h, null);
  assert.equal(s.pm_dispatch_1h, 0);
});

test("stuck / stuck_age_max_min: oc:stuck の open PR。起点は最新の停止コメント (更新時刻ではない)。closed と他のラベルは数えない", async () => {
  const ctx = await configuredApp();
  await send(ctx.app, "pull_request", prPayload(10, { labels: ["oc:stuck"], updatedAt: T0 - 5 * MIN }));
  await send(ctx.app, "issue_comment", commentPayload(10, MARK, stopBody(10), iso(T0 - 120 * MIN)));
  await send(ctx.app, "pull_request", prPayload(11, { labels: ["oc:stuck"], updatedAt: T0 - 45 * MIN }));
  await send(ctx.app, "pull_request", prPayload(12, { labels: ["oc:ready"], updatedAt: T0 - 900 * MIN }));
  await send(ctx.app, "pull_request", prPayload(13, { state: "closed", labels: ["oc:stuck"], updatedAt: T0 - 900 * MIN }));
  const s = await status(ctx);
  assert.equal(s.stuck, 2);
  assert.equal(s.stuck_age_max_min, 120, "PR 10 は停止コメント (120 分前) が起点。更新 (5 分前) からは数えない");
});

test("stuck_age_max_min: 停止コメントの無い PR は更新時刻から数える", async () => {
  const ctx = await configuredApp();
  await send(ctx.app, "pull_request", prPayload(11, { labels: ["oc:stuck"], updatedAt: T0 - 45 * MIN }));
  const s = await status(ctx);
  assert.equal(s.stuck, 1);
  assert.equal(s.stuck_age_max_min, 45);
});

test("needs_pm / needs_user: open の issue と PR の合計。closed は数えない", async () => {
  const ctx = await configuredApp();
  await send(ctx.app, "issues", issuePayload(1, { labels: ["needs-pm"] }));
  await send(ctx.app, "issues", issuePayload(2, { labels: ["needs-user-input"] }));
  await send(ctx.app, "issues", issuePayload(3, { labels: ["needs-pm", "needs-user-input"] }));
  await send(ctx.app, "issues", issuePayload(4, { labels: ["needs-pm"], state: "closed" }));
  await send(ctx.app, "pull_request", prPayload(20, { labels: ["needs-pm"] }));
  await send(ctx.app, "pull_request", prPayload(21, { labels: ["needs-user-input"] }));
  await send(ctx.app, "pull_request", prPayload(22, { labels: ["needs-pm", "needs-user-input"] }));
  await send(ctx.app, "pull_request", prPayload(23, { state: "closed", labels: ["needs-pm", "needs-user-input"] }));
  const s = await status(ctx);
  assert.equal(s.needs_pm, 4, "issue 1・3、PR 20・22");
  assert.equal(s.needs_user, 4, "issue 2・3、PR 21・22");
});

test("no_pr_by_reason: open の oc:no-pr の issue を最新の outcome の理由で数える (outcome 無し・ラベル無し・closed は数えない)", async () => {
  const ctx = await configuredApp();
  const reasons = ["split", "artifact", "unknown", "blocked", "stop"];
  for (const [i, r] of reasons.entries()) {
    await send(ctx.app, "issues", issuePayload(30 + i, { labels: ["oc:no-pr"] }));
    await send(ctx.app, "issue_comment", commentPayload(30 + i, BOT, outcomeBody(r), iso(T0 - (10 - i) * MIN)));
  }
  // issue 30 は後の outcome (blocked) で上書きされる
  await send(ctx.app, "issue_comment", commentPayload(30, BOT, outcomeBody("blocked"), iso(T0 - 1 * MIN)));
  await send(ctx.app, "issues", issuePayload(40, { labels: ["oc:no-pr"] })); // outcome 無し
  await send(ctx.app, "issues", issuePayload(41, { labels: [] })); // ラベル無し
  await send(ctx.app, "issue_comment", commentPayload(41, BOT, outcomeBody("split"), iso(T0 - 5 * MIN)));
  await send(ctx.app, "issues", issuePayload(42, { labels: ["oc:no-pr"], state: "closed" }));
  await send(ctx.app, "issue_comment", commentPayload(42, BOT, outcomeBody("split"), iso(T0 - 5 * MIN)));
  const s = await status(ctx);
  assert.deepEqual(s.no_pr_by_reason, { split: 0, artifact: 1, unknown: 1, blocked: 2, stop: 1 });
});

test("pm_dispatch_1h: 直近 1 時間の oc-pm 送信数 (dry-run の would を含む)。61 分前の分は数えない", async () => {
  const clock = { t: T0 };
  const ctx = await configuredApp({ now: clock });
  await seedStuck(ctx, [10, 11]);
  await markFresh(ctx);
  const gh = await (ctx.app.engine as any).d.gh();
  await ctx.app.engine.pmDispatch(gh);
  let s = await status(ctx);
  assert.equal(s.counters.wouldDispatchPm, 2);
  assert.equal(s.pm_dispatch_1h, 2, "dry-run の would 2 件");
  clock.t += 61 * MIN;
  await markFresh(ctx);
  await ctx.app.engine.pmDispatch(gh);
  s = await status(ctx);
  assert.equal(s.counters.wouldDispatchPm, 4);
  assert.equal(s.pm_dispatch_1h, 2, "61 分前の 2 件は数えず、今回の 2 件だけ (履歴は 24 時間分残る)");
  assert.equal(ctx.store.get<unknown[]>("meta", "pmWould")?.length, 4);
});

test("pm_dispatch_1h: live は実際に送った件数を数える (POST は送った回数だけ)", async () => {
  const clock = { t: T0 };
  const ctx = await configuredApp({ live: true, now: clock, handlers: [(c) => (c.url.endsWith("/dispatches") ? j(null, 204) : undefined)] });
  await seedStuck(ctx, [10, 11]);
  await markFresh(ctx);
  await ctx.app.engine.pmDispatch(await (ctx.app.engine as any).d.gh());
  const s = await status(ctx);
  assert.equal(s.counters.pmDispatched, 2);
  assert.equal(s.pm_dispatch_1h, 2);
  assert.equal(ctx.m.calls.filter((c) => c.method === "POST" && c.url.endsWith("/dispatches")).length, 2);
});

test("pm_dispatch_cap / pm_skipped_hour_24h: 毎時上限で見送った件数は tick ごとに増え、24 時間の窓を過ぎると 0 になる (#3462)", async () => {
  const clock = { t: T0 };
  const ctx = await configuredApp({ now: clock });
  await seedStuck(ctx, Array.from({ length: PM_LIMITS.hourMax + 2 }, (_, i) => 10 + i));
  const gh = await (ctx.app.engine as any).d.gh();
  const tickAt = async (ms: number) => {
    clock.t = ms;
    await markFresh(ctx);
    await ctx.app.engine.pmDispatch(gh);
  };
  await tickAt(T0);
  let s = await status(ctx);
  assert.equal(s.pm_dispatch_cap, 24);
  assert.equal(s.pm_dispatch_1h, PM_LIMITS.hourMax, "上限まで送る");
  assert.equal(s.pm_skipped_hour_24h, 2, "上限を超えた 2 件は見送る");
  await tickAt(T0 + MIN);
  assert.equal((await status(ctx)).pm_skipped_hour_24h, 4, "次の tick も上限の内。送った 24 件は重複で見送り、残りの 2 件が毎時上限で見送られる");
  clock.t = T0 + 23 * H;
  assert.equal((await status(ctx)).pm_skipped_hour_24h, 4, "24 時間の窓の内は残る");
  clock.t = T0 + 24 * H + MIN;
  s = await status(ctx);
  assert.equal(s.pm_skipped_hour_24h, 0, "24 時間を過ぎた見送りは数えない");
  assert.equal(s.pm_dispatch_cap, PM_LIMITS.hourMax);
});

// ---------------------------------------------------------------------------------------------------------------- 受入 1 (判定) と (c)
test("refsOnlyBody: Refs #N のみだけ true。Closes / Fixes が 1 つでもあれば false (併記を含む)", () => {
  assert.equal(refsOnlyBody("Refs #1"), true);
  assert.equal(refsOnlyBody("背景の説明\n\nRefs #12\n"), true);
  assert.equal(refsOnlyBody("refs #1"), true, "大文字小文字は区別しない");
  assert.equal(refsOnlyBody("Closes #1"), false);
  assert.equal(refsOnlyBody("Fixes #1"), false);
  assert.equal(refsOnlyBody("Resolved #1"), false);
  assert.equal(refsOnlyBody("Refs #1\nCloses #1"), false, "併記は refs のみではない");
  assert.equal(refsOnlyBody("Closes #1\nRefs #1"), false);
  assert.equal(refsOnlyBody("Fixes: #1"), false, "コロン付きの closing keyword も閉じる");
  assert.equal(refsOnlyBody("Refs #1, see Prefixes #2"), true, "Prefixes は fix の語ではない");
  assert.equal(refsOnlyBody("本文なし"), false, "参照が無い");
  assert.equal(refsOnlyBody(""), false);
  assert.equal(refsOnlyBody("Refs #x"), false, "番号でない");
});

test("Refs のみの判定の統一 (#2623): 指標の refsOnlyBody と refs_orphan の refsOnlyNumbers が表の 4 入力で同じ値", () => {
  const cases: Array<[string, boolean]> = [
    ["Closes:#6 Refs #5", false],
    ["Refs owner/repo#5", false],
    ["Refs:#5", true],
    ["Refs #12345678", false],
  ];
  for (const [body, refsOnly] of cases) {
    assert.equal(refsOnlyBody(body), refsOnly, `指標: ${body}`);
    assert.equal(refsOnlyNumbers(body).length > 0, refsOnly, `refs_orphan: ${body}`);
  }
});

test("refs_only_merge_rate_24h: 直近 24 時間に merge された PR のうち、本文が Refs のみの件数と率", async () => {
  const ctx = await configuredApp();
  const merged = (n: number, agoMin: number, body: string) => prPayload(n, { state: "closed", mergedAt: T0 - agoMin * MIN, body });
  await send(ctx.app, "pull_request", merged(1, 120, "Refs #100")); // 数える: Refs のみ
  await send(ctx.app, "pull_request", merged(2, 180, "Closes #101")); // 数える: 閉じる
  await send(ctx.app, "pull_request", merged(3, 240, "Refs #102\n\nCloses #103")); // 数える: 併記は refs ではない
  await send(ctx.app, "pull_request", merged(4, 300, "Refs #104")); // 数える: Refs のみ
  await send(ctx.app, "pull_request", merged(8, 24 * 60 - 1, "Refs #108")); // 数える: 23 時間 59 分前
  await send(ctx.app, "pull_request", merged(5, 25 * 60, "Refs #105")); // 数えない: 25 時間前
  await send(ctx.app, "pull_request", merged(9, 24 * 60, "Refs #109")); // 数えない: ちょうど 24 時間前
  await send(ctx.app, "pull_request", prPayload(6, { state: "closed", body: "Refs #106", updatedAt: T0 - 60 * MIN })); // merge されずに閉じた
  await send(ctx.app, "pull_request", prPayload(7, { body: "Refs #107" })); // open
  const s = await status(ctx);
  assert.deepEqual(s.refs_only_merge_rate_24h, { merged: 5, refs_only: 3, rate: 0.6 });
});

// ---------------------------------------------------------------------------------------------------------------- ネガコン (b)(c)
test("ネガコン (b): 24 時間より前に merge された PR は refs_only_merge_rate_24h に入らない", async () => {
  const ctx = await configuredApp();
  await send(ctx.app, "pull_request", prPayload(5, { state: "closed", mergedAt: T0 - 25 * H, body: "Refs #105" }));
  await send(ctx.app, "pull_request", prPayload(9, { state: "closed", mergedAt: T0 - 24 * H, body: "Refs #109" }));
  assert.deepEqual((await status(ctx)).refs_only_merge_rate_24h, { merged: 0, refs_only: 0, rate: null });
});

test("ネガコン (c): Closes #N と Refs #N が併記の PR は refs_only に数えない (merge には数える)", async () => {
  const ctx = await configuredApp();
  await send(ctx.app, "pull_request", prPayload(3, { state: "closed", mergedAt: T0 - 30 * MIN, body: "Refs #102\n\nCloses #102" }));
  assert.deepEqual((await status(ctx)).refs_only_merge_rate_24h, { merged: 1, refs_only: 0, rate: 0 });
});

// ---------------------------------------------------------------------------------------------------------------- 受入 1 (履歴) とネガコン (d)
test("open_issues_delta_24h: 履歴が 24 時間分に満たないときは null。満たせば 24 時間前の点との差 (ネガコン (d))", async () => {
  const clock = { t: T0 };
  const w = syncWorld();
  const ctx = await configuredApp({ now: clock, handlers: w.handlers });
  const delta = async () => (await status(ctx)).open_issues_delta_24h;
  const tickAt = async (h: number, open: number) => {
    clock.t = T0 + h * H;
    w.rest.issues = Array.from({ length: open }, (_, i) => issuePayload(i + 1).issue);
    await ctx.app.engine.tick();
  };
  await tickAt(0, 5);
  assert.equal(await delta(), null, "履歴 1 点 (0 時間分)");
  for (let h = 1; h < 24; h++) await tickAt(h, 5 + h);
  assert.equal(await delta(), null, "23 時間分の履歴では、24 時間前の点が無いので捏造しない");
  await tickAt(24, 29);
  assert.equal((await status(ctx)).open_issues, 29);
  assert.equal(await delta(), 24, "24 時間前の点 (5 件) との差 29 - 5");
});

test("openHist: 1 時間に 1 点。最大 48 点で古い方から捨てる。同期が古い間は記録しない", async () => {
  const clock = { t: T0 };
  const w = syncWorld();
  const ctx = await configuredApp({ now: clock, handlers: w.handlers });
  const hist = () => ctx.store.get<Array<{ at: number; open: number }>>("meta", "openHist") ?? [];
  const tickAt = async (ms: number) => {
    clock.t = ms;
    await ctx.app.engine.tick();
  };
  await tickAt(T0);
  await tickAt(T0 + 5 * MIN);
  await tickAt(T0 + 59 * MIN);
  assert.equal(hist().length, 1, "1 時間未満では増えない");
  await tickAt(T0 + H);
  assert.equal(hist().length, 2);
  for (let h = 2; h < 50; h++) await tickAt(T0 + h * H);
  assert.equal(hist().length, 48, "最大 48 点");
  assert.equal(hist()[0].at, T0 + 2 * H, "古い方 (0 時間・1 時間) から捨てる");
  assert.equal(hist().at(-1)?.at, T0 + 49 * H);
  w.rest.fail = true;
  await tickAt(T0 + 50 * H);
  assert.equal(hist().length, 48, "同期が 15 分以上止まっている間は記録しない");
});

// ---------------------------------------------------------------------------------------------------------------- ネガコン (a)
test("ネガコン (a): 題名・本文・コメント・ブランチ名・run 名に入れたダミーの文字列は、公開 /status の JSON に 0 件", async () => {
  const MARK = "SECRET-AUTO-MARK";
  const ctx = await configuredApp();
  const evil = `${MARK} 題名 本文 ${MARK}`;
  await send(ctx.app, "issues", issuePayload(1, { title: evil, body: evil, labels: ["needs-pm", "oc:no-pr"] }));
  await send(ctx.app, "issues", issuePayload(2, { title: evil, body: evil, labels: ["needs-user-input"] }));
  await send(ctx.app, "issue_comment", commentPayload(1, BOT, `${outcomeBody("split")}\n${evil}`, iso(T0 - 10 * MIN)));
  await send(ctx.app, "issue_comment", commentPayload(1, "pycabbage", evil));
  await send(ctx.app, "issue_comment", commentPayload(2, "pycabbage", evil));
  await send(ctx.app, "pull_request", prPayload(10, { labels: ["oc:stuck"], title: evil, body: evil, updatedAt: T0 - 5 * MIN }));
  await send(ctx.app, "issue_comment", commentPayload(10, MARK, `${stopBody(10)} ${evil}`, iso(T0 - 20 * MIN)));
  await send(ctx.app, "pull_request", prPayload(11, { state: "closed", mergedAt: T0 - 30 * MIN, body: `Refs #1 ${evil}`, title: evil }));
  await send(ctx.app, "workflow_run", runPayload(7, "in_progress", { title: evil }));
  const text = await (await ctx.app.handle(new Request("https://pm.example/status"))).text();
  assert.ok(!text.includes(MARK), "公開の応答に題名・本文・コメントの文字列が無い");
  // 検査が空振りでないこと: fixture の集計は実際に数えられている
  const s = JSON.parse(text);
  assert.equal(s.stuck, 1);
  assert.equal(s.needs_pm, 1);
  assert.equal(s.needs_user, 1);
  assert.equal(s.no_pr_by_reason.split, 1);
  assert.equal(s.refs_only_merge_rate_24h.refs_only, 1);
});
