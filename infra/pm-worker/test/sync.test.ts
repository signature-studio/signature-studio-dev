// コメント同期 (新しい順・窓で止める) と、一覧の打ち切り → fresh=false (#2380)。
// GitHub は fetch モック。ページ付きの fixture (48 時間 12,000 件) で、窓内のページだけを読むことと、旧実装 (昇順・40 ページ) が
// 同じ fixture の直近のコメントを取り込めないことを確かめる。
import { test } from "node:test";
import assert from "node:assert/strict";
import { Gh } from "../src/github.ts";
import { loadConfig } from "../src/config.ts";
import { EMPTY_STATE, applyEvent } from "../src/webhook.ts";
import { BOT, T0, configuredApp, issuePayload, j, markFresh, mockFetch, runPayload, send, type Call, type Handler } from "./helpers.ts";

const H = 3_600_000;
const R = "signature-studio/signature-studio-dev";
const iso = (ms: number) => new Date(ms).toISOString().replace(/\.\d{3}Z$/, "Z");
const posts = (calls: Call[]) => calls.filter((c) => c.method === "POST" && /\/issues\/\d+\/comments$/.test(c.url));
const dispatches = (calls: Call[]) => calls.filter((c) => c.method === "POST" && c.url.endsWith("/dispatches"));

// ---------------------------------------------------------------- fixture
interface Cm {
  id: number;
  issue_url: string;
  user: { login: string };
  body: string;
  created_at: string;
  updated_at: string;
}
interface Special {
  agoMin: number;
  login: string;
  body: string;
  issue: number;
}

// total 件を span の間に等間隔で並べ、specials (agoMin 分前) を混ぜる。id は時刻順の昇順。
function makeComments(total: number, spanH: number, specials: Special[] = [], endMs = T0): Cm[] {
  const noise = total - specials.length;
  const startMs = endMs - spanH * H;
  const rows: Array<{ at: number; login: string; body: string; issue: number }> = [];
  for (let i = 0; i < noise; i++) {
    rows.push({ at: startMs + Math.floor(((i + 1) * spanH * H) / (noise + 1)), login: `user${i % 37}`, body: `NOISE-BODY-${i}`, issue: 1000 + (i % 53) });
  }
  for (const s of specials) rows.push({ at: endMs - s.agoMin * 60_000, login: s.login, body: s.body, issue: s.issue });
  rows.sort((a, b) => a.at - b.at);
  return rows.map((r, i) => ({
    id: 100000 + i,
    issue_url: `https://api.github.com/repos/${R}/issues/${r.issue}`,
    user: { login: r.login },
    body: r.body,
    created_at: iso(r.at),
    updated_at: iso(r.at),
  }));
}

const OC = "/oc oc_actions_allow_write\noc_artifacts: fl-win64 toolchain-retdec\nPM が着手を依頼します";
const SPECIALS: Special[] = [
  { agoMin: 120, login: "pycabbage", body: OC, issue: 501 }, // 直近 3 時間以内の /oc
  { agoMin: 40 * 60, login: "pycabbage", body: OC, issue: 503 }, // 窓 (24 時間) の外
  { agoMin: 180, login: BOT, body: "停止します 古い報告", issue: 502 },
  { agoMin: 10, login: BOT, body: "停止します 最新の報告 A", issue: 502 },
  { agoMin: 10, login: BOT, body: "停止します 最新の報告 B (同時刻・id が大きい)", issue: 502 },
  { agoMin: 300, login: "pycabbage", body: "oc_artifacts: fl-win64 plugins-ott", issue: 504 },
  { agoMin: 60, login: "pycabbage", body: "再依頼\noc_artifacts: fl-win64", issue: 504 },
];
const FX48 = makeComments(12_000, 48, SPECIALS);

// ---------------------------------------------------------------- GitHub のモック
const page = <T>(all: T[], u: URL): T[] => {
  const per = Number(u.searchParams.get("per_page") ?? 30);
  const p = Number(u.searchParams.get("page") ?? 1);
  return all.slice((p - 1) * per, p * per);
};

interface World {
  comments?: Cm[];
  issues?: any[];
  pullsOpen?: any[];
  pullsClosed?: any[]; // 更新が新しい順
  runs?: Record<string, any[]>;
  issuesUpdated?: any[];
}
// コメント一覧は GitHub と同じく sort=created の既定が昇順。direction=desc で新しい順。since は updated_at の絞り込み。
function api(w: World, rec: { commentPages: number[] } = { commentPages: [] }): Handler {
  const asc = () => w.comments ?? [];
  let desc: Cm[] | null = null;
  let descOf: Cm[] | null = null;
  return (c: Call) => {
    if (c.method !== "GET") return undefined;
    const u = new URL(c.url);
    const p = u.pathname;
    if (p.endsWith("/issues/comments")) {
      rec.commentPages.push(Number(u.searchParams.get("page") ?? 1));
      let list = asc();
      const since = u.searchParams.get("since");
      if (since) list = list.filter((x) => x.updated_at >= since);
      if (u.searchParams.get("direction") === "desc") {
        if (descOf !== w.comments || !desc) {
          desc = [...asc()].reverse();
          descOf = w.comments ?? null;
        }
        list = since ? desc.filter((x) => x.updated_at >= since) : desc;
      }
      return j(page(list, u));
    }
    if (p.endsWith("/actions/runs")) return j({ workflow_runs: page(w.runs?.[u.searchParams.get("status") ?? ""] ?? [], u) });
    if (/\/repos\/[^/]+\/[^/]+\/issues$/.test(p)) return j(page(u.searchParams.get("since") ? (w.issuesUpdated ?? []) : (w.issues ?? []), u));
    if (p.endsWith("/pulls")) return j(page(u.searchParams.get("state") === "open" ? (w.pullsOpen ?? []) : (w.pullsClosed ?? []), u));
    if (/\/dependencies\/blocked_by$/.test(p)) return j([]);
    return undefined;
  };
}

const openIssue = (n: number, title = `[CI-${n}] t${n}`) => ({
  number: n,
  title,
  body: "",
  state: "open",
  updated_at: "2026-10-14T10:00:00Z",
  labels: [],
  issue_dependencies_summary: { total_blocked_by: 0 },
});
const manyIssues = (count: number, from = 7000) => Array.from({ length: count }, (_, i) => openIssue(from + i));
const prObj = (n: number, state: "open" | "closed", updatedMs: number, ref = `${n}-x`) => ({
  number: n,
  state,
  merged_at: null,
  draft: false,
  head: { ref },
  title: "t",
  body: "",
  updated_at: iso(updatedMs),
});

async function boot(w: World, o: { live?: boolean; env?: Record<string, string>; now?: { t: number } } = {}) {
  const rec = { commentPages: [] as number[] };
  const ctx = await configuredApp({ live: o.live, env: o.env, now: o.now, handlers: [api(w, rec), (c) => (/\/issues\/\d+\/comments$/.test(c.url) && c.method === "POST" ? j({}, 201) : undefined), (c) => (c.url.endsWith("/dispatches") ? j(null, 204) : undefined)] });
  return { ...ctx, rec, status: () => ctx.app.engine.status() as any };
}

// 旧実装: since=48 時間前・昇順・40 ページ。打ち切りを知らない。
async function legacyComments(ctx: Awaited<ReturnType<typeof boot>>, windowH = 48) {
  const gh = (await (ctx.app.engine as any).d.gh()) as Gh;
  const r = await gh.list<any>(`/repos/${R}/issues/comments?since=${encodeURIComponent(iso(T0 - windowH * H))}`, 40);
  for (const c of r.items) {
    const n = Number(String(c.issue_url).split("/").pop());
    (ctx.app.engine as any).applyAll("issue_comment", { action: "created", comment: c, issue: { number: n } });
  }
  return r;
}

// ---------------------------------------------------------------- Gh.list
test("Gh.list: 上限で止めて続きがあれば truncated=true、上限ちょうどで読み尽くしていれば false (次の 1 ページで確かめる)", async () => {
  const mk = (n: number) => {
    const all = Array.from({ length: n }, (_, i) => i);
    const calls: number[] = [];
    const m = mockFetch([(c) => { const u = new URL(c.url); calls.push(Number(u.searchParams.get("page"))); return j(page(all, u)); }]);
    return { gh: new Gh(m.f, async () => "t", R), calls };
  };
  let x = mk(250);
  let r = await x.gh.list("/repos/a/b/things", 2);
  assert.deepEqual([r.items.length, r.truncated, r.pages], [200, true, 2], "上限 2 ページで 250 件目まであるので打ち切り");
  assert.deepEqual(x.calls, [1, 2, 3], "続きの確認に 3 ページ目を 1 回だけ読む");
  x = mk(200);
  r = await x.gh.list("/repos/a/b/things", 2);
  assert.deepEqual([r.items.length, r.truncated], [200, false], "上限ちょうどで終わった場合は打ち切りではない");
  assert.deepEqual(x.calls, [1, 2, 3], "3 ページ目は空");
  x = mk(150);
  r = await x.gh.list("/repos/a/b/things", 2);
  assert.deepEqual([r.items.length, r.truncated, r.pages], [150, false, 2]);
  assert.deepEqual(x.calls, [1, 2], "100 件未満のページで終わる");
  x = mk(0);
  r = await x.gh.list("/repos/a/b/things?x=1", 3);
  assert.deepEqual([r.items.length, r.truncated, r.pages], [0, false, 1]);
});

test("Gh.list: stop に当たった項目より後ろは捨てて終える。上限ちょうどで窓の端に届いたなら打ち切りではない", async () => {
  const all = Array.from({ length: 450 }, (_, i) => 450 - i); // 新しい順 (値が大きいほど新しい)
  const calls: number[] = [];
  const m = mockFetch([(c) => { const u = new URL(c.url); calls.push(Number(u.searchParams.get("page"))); return j(page(all, u)); }]);
  const gh = new Gh(m.f, async () => "t", R);
  let r = await gh.list<number>("/x", 10, undefined, (v) => v <= 120);
  assert.equal(r.items.length, 330, "121 以上の 330 件");
  assert.deepEqual([r.truncated, r.pages, calls], [false, 4, [1, 2, 3, 4]]);
  calls.length = 0;
  r = await gh.list<number>("/x", 3, undefined, (v) => v <= 150); // 300 件を読み切った次のページ (151 以下) は窓の外
  assert.deepEqual([r.items.length, r.truncated, r.pages, calls], [300, false, 3, [1, 2, 3, 4]], "上限ちょうどで、次は窓の外だけ → 打ち切りではない");
  calls.length = 0;
  r = await gh.list<number>("/x", 3, undefined, (v) => v <= 100);
  assert.deepEqual([r.items.length, r.truncated, r.pages], [300, true, 3], "上限に達して窓の端に届かない → 打ち切り");
});

// ---------------------------------------------------------------- 正例
test("正例: 48 時間 12,000 件でも窓 24 時間なら窓内のページだけを読み、直近の /oc と最新の bot 報告が入る (fresh=true)", async () => {
  assert.equal(FX48.length, 12_000);
  const ctx = await boot({ comments: FX48, issues: [openIssue(501), openIssue(502), openIssue(504)] });
  await ctx.app.engine.fullSync((await (ctx.app.engine as any).d.gh()) as Gh);
  const inWindow = FX48.filter((c) => c.created_at >= iso(T0 - 24 * H)).length;
  assert.ok(inWindow > 5900 && inWindow < 6100, `窓内 ${inWindow} 件`);
  const maxPage = Math.max(...ctx.rec.commentPages);
  assert.ok(maxPage <= Math.ceil(inWindow / 100) + 1, `読んだ最後のページ ${maxPage}`);
  assert.ok(ctx.rec.commentPages.length <= Math.ceil(inWindow / 100) + 1, "コメント取得の REST 回数は 窓内の件数 / 100 の切り上げ + 1 以内");
  const st = ctx.app.engine.s;
  assert.equal(st.launchedAt["501"], iso(T0 - 120 * 60_000), "直近 3 時間以内の /oc");
  assert.equal(st.launchedAt["503"], undefined, "窓の外の /oc は読まない");
  assert.equal(st.botLast["502"].body, "停止します 最新の報告 B (同時刻・id が大きい)", "最新の bot 報告 (同時刻は id が大きい方)");
  assert.equal(st.pmArt["504"].line, "oc_artifacts: fl-win64", "最新の oc_artifacts 行");
  const s = ctx.status();
  assert.equal(s.fresh, true);
  assert.deepEqual(s.sync_truncated, []);
  assert.equal(s.last_full_sync_comment_rest_calls, ctx.rec.commentPages.length);
  const gets = ctx.m.calls.filter((c) => c.method === "GET" && c.url.includes("/repos/"));
  assert.equal(s.last_full_sync_rest_calls, gets.length, "全体同期の REST 回数 (全一覧の合計) を /status に出す");
  assert.equal(s.comment_window_h, 24);
  assert.equal(s.comment_max_pages, 80);
});

// ---------------------------------------------------------------- ネガコン (a)
test("ネガコン (a): 旧実装相当 (昇順・40 ページ) では同じ fixture の直近の /oc も最新の bot 報告も取り込めない", async () => {
  const ctx = await boot({ comments: FX48 });
  const r = await legacyComments(ctx);
  assert.equal(r.items.length, 4000);
  assert.equal(r.truncated, true, "旧実装は打ち切ったことを返さなかった (今は返す)");
  const st = ctx.app.engine.s;
  assert.equal(st.launchedAt["501"], undefined, "直近の /oc が落ちる");
  assert.equal(st.botLast["502"], undefined, "最新の bot 報告が落ちる");
  assert.equal(st.pmArt["504"], undefined);
  assert.ok(st.launchedAt["503"], "古い側 (-40 時間) の /oc は読めている = fixture は『古い側だけ読む』欠陥を再現している");
});

// ---------------------------------------------------------------- (b) 上限で窓の端に届かない
test("(b) 上限に達して窓の端に届かない → fresh=false。launch も watchdog も書かず、/status.sync_truncated に出る。旧実装は fresh=true のまま launch", async () => {
  const issues = [openIssue(601), openIssue(602), openIssue(603)];
  const ctx = await boot({ comments: FX48, issues }, { live: true, env: { COMMENT_MAX_PAGES: "40" } });
  await ctx.app.engine.tick();
  const s = ctx.status();
  assert.equal(s.fresh, false);
  assert.equal(s.sync_truncated.length, 1);
  assert.equal(s.sync_truncated[0].name, "comments");
  assert.equal(s.sync_truncated[0].pages, 40);
  assert.equal(s.sync_truncated[0].at, new Date(T0).toISOString());
  assert.equal(Math.max(...ctx.rec.commentPages), 41, "上限の次の 1 ページまでしか読まない");
  assert.equal(posts(ctx.m.calls).length, 0, "launch の POST は 0 回");
  assert.equal(dispatches(ctx.m.calls).length, 0, "watchdog の dispatch も 0 回");
  assert.equal(s.counters.launched, 0);
  assert.ok(s.log.some((l: any) => l.kind === "truncated" && l.note === "comments pages=40"));

  // 旧実装相当: 同じ fixture を昇順 40 ページで読んで fresh のまま launch する
  const old = await boot({ comments: FX48, issues }, { live: true });
  await old.app.engine.fullSync((await (old.app.engine as any).d.gh()) as Gh);
  await legacyComments(old);
  old.app.engine.meta.syncTruncated = undefined; // 旧実装は打ち切りを記録しない
  await markFresh(old);
  await old.app.engine.launch((await (old.app.engine as any).d.gh()) as Gh);
  assert.ok(posts(old.m.calls).length > 0, "旧実装は fresh=true のまま launch の POST をする");
});

test("(b') dry-run でも打ち切りは記録し fresh=false にする。GitHub へは何も書かない", async () => {
  const ctx = await boot({ comments: FX48, issues: [openIssue(601)] }, { env: { COMMENT_MAX_PAGES: "40" } });
  await ctx.app.engine.tick();
  assert.equal(ctx.status().fresh, false);
  assert.equal(ctx.status().counters.wouldLaunch, 0, "fresh=false の間は would-launch も記録しない");
  assert.equal(ctx.status().counters.wouldDispatch, 0);
  assert.equal(ctx.m.calls.filter((c) => c.method !== "GET" && !c.url.includes("/app/") && !c.url.includes("/app-manifests/")).length, 0);
});

// ---------------------------------------------------------------- (c) 窓の端に届いて止まった
test("(c) 窓の端に届いて止まった (上限未満) → fresh=true で launch する", async () => {
  const ctx = await boot({ comments: FX48, issues: [openIssue(601), openIssue(602)] }, { live: true });
  await ctx.app.engine.tick();
  const s = ctx.status();
  assert.equal(s.fresh, true);
  assert.deepEqual(s.sync_truncated, []);
  assert.ok(Math.max(...ctx.rec.commentPages) < 80);
  assert.deepEqual(posts(ctx.m.calls).map((c) => c.url.match(/issues\/(\d+)\//)?.[1]), ["601", "602"]);
  assert.equal(dispatches(ctx.m.calls).length, 1);
});

// ---------------------------------------------------------------- (d) ちょうど上限の件数
test("(d) 窓内がちょうど上限 (8,000 件 = 80 ページ) でも誤って fresh=false にしない。1 件多ければ打ち切り", async () => {
  const inWin = (n: number, older: number) => {
    const recent = makeComments(n, 20, [], T0 - 1000); // 窓の中
    const old = makeComments(older, 20, [], T0 - 30 * H); // 窓の外 (30 時間前まで)
    return [...old, ...recent].map((c, i) => ({ ...c, id: 1 + i }));
  };
  // 窓内ちょうど 8,000 件 + 窓の外の古いコメントあり: 81 ページ目は窓の外だけ
  let ctx = await boot({ comments: inWin(8000, 500), issues: [openIssue(601)] });
  await ctx.app.engine.fullSync((await (ctx.app.engine as any).d.gh()) as Gh);
  assert.equal(ctx.status().fresh, true, "窓内 8,000 件 + 窓の外あり");
  assert.deepEqual(ctx.status().sync_truncated, []);
  assert.equal(ctx.status().last_full_sync_comment_rest_calls, 81, "窓内の件数 / 100 の切り上げ + 1");
  // コメントが全部で 8,000 件ちょうど (次のページが空)
  ctx = await boot({ comments: inWin(8000, 0), issues: [openIssue(601)] });
  await ctx.app.engine.fullSync((await (ctx.app.engine as any).d.gh()) as Gh);
  assert.equal(ctx.status().fresh, true, "全部で 8,000 件ちょうど");
  assert.equal(ctx.status().last_full_sync_comment_rest_calls, 81, "次の 1 ページ (空) を読んで確かめる");
  // 窓内 8,001 件: 打ち切り
  ctx = await boot({ comments: inWin(8001, 500), issues: [openIssue(601)] });
  await ctx.app.engine.fullSync((await (ctx.app.engine as any).d.gh()) as Gh);
  assert.equal(ctx.status().fresh, false, "窓内 8,001 件は上限を超える");
  assert.equal(ctx.status().sync_truncated[0].name, "comments");
});

// ---------------------------------------------------------------- (e) 解消
test("(e) 打ち切りの後に解消したら、次の同期で自動で fresh=true に戻る (launch も再開する)", async () => {
  const clock = { t: T0 };
  const w: World = { comments: FX48, issues: [openIssue(601)] };
  const ctx = await boot(w, { live: true, env: { COMMENT_MAX_PAGES: "40" }, now: clock });
  await ctx.app.engine.tick();
  assert.equal(ctx.status().fresh, false);
  assert.equal(posts(ctx.m.calls).length, 0);
  // 窓内のコメントが上限に収まるようになった (reconcile は直近 7 分の窓だけを読む)
  w.comments = FX48.filter((c) => c.created_at >= iso(T0 - 2 * H));
  clock.t += 5 * 60_000;
  await ctx.app.engine.tick();
  const s = ctx.status();
  assert.equal(s.fresh, true);
  assert.deepEqual(s.sync_truncated, []);
  assert.ok(s.log.some((l: any) => l.kind === "recovered" && l.note === "comments"));
  assert.deepEqual(posts(ctx.m.calls).map((c) => c.url.match(/issues\/(\d+)\//)?.[1]), ["601"]);
  assert.equal(dispatches(ctx.m.calls).length, 1, "watchdog も再開");
});

// ---------------------------------------------------------------- (f) open issue 3,000 件超
test("(f) open issue が 3,000 件超 → fresh=false。ちょうど 3,000 件なら fresh=true。打ち切ったときは一覧に無い issue を close したとみなさない", async () => {
  let ctx = await boot({ issues: manyIssues(3001) }, { live: true });
  await send(ctx.app, "issues", issuePayload(99)); // 同期前に open と思っていたが一覧に無い
  await ctx.app.engine.tick();
  let s = ctx.status();
  assert.equal(s.fresh, false);
  assert.equal(s.sync_truncated[0].name, "issues_open");
  assert.equal(s.sync_truncated[0].pages, 30);
  assert.equal(posts(ctx.m.calls).length, 0);
  assert.equal(ctx.app.engine.s.issues["99"].state, "open", "打ち切った一覧に無いことは close の証拠にならない");

  ctx = await boot({ issues: manyIssues(3000) }, { live: true });
  await send(ctx.app, "issues", issuePayload(99));
  await ctx.app.engine.tick();
  s = ctx.status();
  assert.equal(s.fresh, true, "ちょうど 3,000 件");
  assert.equal(ctx.app.engine.s.issues["99"].state, "closed", "打ち切っていなければ従来どおり close とみなす");
});

// ---------------------------------------------------------------- 他の一覧
test("run の一覧が上限 (300 件) を超えたら打ち切り。一覧に無い run を completed とみなさない", async () => {
  const runs = (n: number) => Array.from({ length: n }, (_, i) => ({ id: 5000 + i, event: "issue_comment", display_title: `r${i}`, status: "in_progress", conclusion: null, updated_at: "2026-10-14T11:59:00Z" }));
  let ctx = await boot({ runs: { in_progress: runs(301) } });
  await send(ctx.app, "workflow_run", runPayload(9, "in_progress"));
  await ctx.app.engine.fullSync((await (ctx.app.engine as any).d.gh()) as Gh);
  assert.equal(ctx.status().fresh, false);
  assert.equal(ctx.status().sync_truncated[0].name, "runs_in_progress");
  assert.equal(ctx.app.engine.s.runs["9"].status, "in_progress", "打ち切ったときは完了とみなさない");
  ctx = await boot({ runs: { in_progress: runs(300) } });
  await send(ctx.app, "workflow_run", runPayload(9, "in_progress"));
  await ctx.app.engine.fullSync((await (ctx.app.engine as any).d.gh()) as Gh);
  assert.equal(ctx.status().fresh, true);
  assert.equal(ctx.app.engine.s.runs["9"].status, "completed");
});

test("PR: 全体同期は open を全件・closed を窓の中だけ読む。open が 3,000 件超なら打ち切り。reconcile は起点より古いところで止める", async () => {
  const clock = { t: T0 };
  const closed = [prObj(300, "closed", T0 - 1 * H), prObj(299, "closed", T0 - 23 * H), prObj(298, "closed", T0 - 25 * H), prObj(297, "closed", T0 - 26 * H)];
  const w: World = { pullsOpen: [prObj(400, "open", T0 - 100 * H)], pullsClosed: closed };
  const ctx = await boot(w, { now: clock });
  await send(ctx.app, "pull_request", { action: "opened", repository: { full_name: R }, pull_request: prObj(777, "open", T0 - 5 * H, "77-x") }); // webhook の close を取りこぼした PR
  await ctx.app.engine.fullSync((await (ctx.app.engine as any).d.gh()) as Gh);
  const prs = ctx.app.engine.s.prs;
  assert.deepEqual(Object.keys(prs).sort(), ["299", "300", "400", "777"], "窓の外の closed (298, 297) は読まない。更新が古い open (400) は読む");
  assert.equal(prs["400"].state, "open");
  assert.equal(prs["777"].state, "closed", "open の一覧に無い PR は closed とみなす");
  assert.equal(ctx.status().fresh, true);

  // reconcile: 起点 (reconcileAt - 2 分) 以降に更新された PR だけ
  clock.t += 6 * 60_000;
  w.pullsClosed = [prObj(310, "closed", clock.t - 60_000), prObj(309, "closed", clock.t - 10 * 60_000)];
  ctx.m.calls.length = 0;
  await ctx.app.engine.reconcile((await (ctx.app.engine as any).d.gh()) as Gh);
  assert.ok(ctx.app.engine.s.prs["310"]);
  assert.equal(ctx.app.engine.s.prs["309"], undefined, "起点より古い更新は読まない");
  assert.equal(ctx.m.calls.filter((c) => c.url.includes("/pulls?")).length, 1, "窓の端に届いたので 1 ページで終わる");
  assert.equal(ctx.status().fresh, true, "reconcile の PR 一覧は、PR が 100 件を超えても打ち切りにならない");

  // open が 3,001 件
  const big = await boot({ pullsOpen: Array.from({ length: 3001 }, (_, i) => prObj(10_000 + i, "open", T0 - H)) });
  await send(big.app, "pull_request", { action: "opened", repository: { full_name: R }, pull_request: prObj(777, "open", T0 - 5 * H, "77-x") });
  await big.app.engine.fullSync((await (big.app.engine as any).d.gh()) as Gh);
  assert.equal(big.status().fresh, false);
  assert.equal(big.status().sync_truncated[0].name, "pulls_open");
  assert.equal(big.app.engine.s.prs["777"].state, "open", "打ち切ったときは close とみなさない");
});

// ---------------------------------------------------------------- (g) 本文・題名を出さない
test("(g) /status と log にコメント本文・題名を出さない (名前・ページ数・時刻だけ)", async () => {
  const titleMark = "TITLE-SECRET-MARKER";
  const ctx = await boot(
    { comments: FX48, issues: [openIssue(601, `[CI-601] ${titleMark}`), ...manyIssues(3000)] },
    { live: true, env: { COMMENT_MAX_PAGES: "40" } },
  );
  await ctx.app.engine.tick();
  const text = JSON.stringify(ctx.status()) + JSON.stringify(ctx.app.engine.log) + JSON.stringify(ctx.app.engine.meta);
  assert.ok(text.includes("sync_truncated") && text.includes("syncTruncated"));
  for (const bad of [titleMark, "NOISE-BODY", "停止します", "PM が着手を依頼します", "fl-win64 plugins-ott"]) assert.ok(!text.includes(bad), `${bad} が含まれている`);
  const pub = await ctx.app.handle(new Request("https://pm.example/status"));
  const body = await pub.text();
  assert.ok(body.includes('"sync_truncated"') && body.includes('"fresh":false'));
  assert.ok(!body.includes(titleMark) && !body.includes("NOISE-BODY"));
  // 状態に持つコメントは bot と PM のものだけで、それ以外の本文は持たない
  const kept = JSON.stringify(ctx.app.engine.s);
  assert.ok(!kept.includes("NOISE-BODY"));
});

// ---------------------------------------------------------------- reconcile
test("reconcile のコメント一覧も新しい順に読み、起点 (reconcileAt - 2 分) より古いところで止める。上限を超えたら打ち切り", async () => {
  const clock = { t: T0 };
  const w: World = { comments: FX48, issues: [openIssue(601)] };
  const ctx = await boot(w, { now: clock });
  await ctx.app.engine.fullSync((await (ctx.app.engine as any).d.gh()) as Gh);
  clock.t += 6 * 60_000;
  const extra = makeComments(1, 1, [{ agoMin: 1, login: BOT, body: "新しい報告", issue: 601 }], clock.t);
  w.comments = [...FX48, ...extra.map((c) => ({ ...c, id: 999_999 }))];
  ctx.rec.commentPages.length = 0;
  await ctx.app.engine.reconcile((await (ctx.app.engine as any).d.gh()) as Gh);
  assert.deepEqual(ctx.rec.commentPages, [1], "直近 8 分には 100 件に満たない → 1 ページ");
  assert.equal(ctx.app.engine.s.botLast["601"].body, "新しい報告");
  assert.equal(ctx.status().fresh, true);

  // Worker が長く止まった後 (起点が 30 時間前): 上限に届いて打ち切り → fresh=false
  clock.t += 30 * H;
  w.comments = makeComments(12_000, 30, [], clock.t);
  await ctx.app.engine.reconcile((await (ctx.app.engine as any).d.gh()) as Gh);
  assert.equal(ctx.status().fresh, false);
  assert.equal(ctx.status().sync_truncated[0].name, "comments");
  assert.equal(ctx.status().sync_truncated[0].pages, 80);
});

// ---------------------------------------------------------------- 適用順への非依存
test("botLast / pmArt / launchedAt は適用の順序に依らず created_at が最新のものになる (同時刻は id が大きい方)", () => {
  const PM = ["pycabbage"];
  const mk = (id: number, login: string, at: string, body: string) => ({ action: "created", issue: { number: 7 }, comment: { id, user: { login }, created_at: at, body } });
  const cs = [
    mk(1, BOT, "2026-10-14T09:00:00Z", "bot-1"),
    mk(2, BOT, "2026-10-14T10:00:00Z", "bot-2"),
    mk(3, BOT, "2026-10-14T10:00:00Z", "bot-3 (同時刻)"),
    mk(4, "pycabbage", "2026-10-14T08:00:00Z", "/oc a\noc_artifacts: fl-win64"),
    mk(5, "pycabbage", "2026-10-14T11:00:00Z", "/oc b\noc_artifacts: fl-win64 plugins-ott"),
    mk(6, "pycabbage", "2026-10-14T11:00:00Z", "/oc c\noc_artifacts: fl-win64 toolchain-emsdk"),
    mk(7, "pycabbage", "2026-10-14T07:00:00Z", "/oc old\noc_artifacts: fl-win64 evil"),
  ];
  const run = (order: typeof cs) => {
    let s = EMPTY_STATE;
    for (const c of order) s = applyEvent(s, "issue_comment", c, BOT, PM);
    return JSON.stringify([s.botLast, s.pmArt, s.launchedAt]);
  };
  const perms = (a: typeof cs): Array<typeof cs> => (a.length <= 1 ? [a] : a.flatMap((x, i) => perms([...a.slice(0, i), ...a.slice(i + 1)]).map((p) => [x, ...p])));
  const expected = run(cs);
  const parsed = JSON.parse(expected);
  assert.equal(parsed[0]["7"].body, "bot-3 (同時刻)");
  assert.equal(parsed[1]["7"].line, "oc_artifacts: fl-win64 toolchain-emsdk");
  assert.equal(parsed[2]["7"], "2026-10-14T11:00:00Z");
  assert.equal(run([...cs].reverse()), expected, "新しい順に適用しても同じ");
  // 7! = 5040 通りの全順列
  for (const p of perms(cs)) assert.equal(run(p), expected);
});

// ---------------------------------------------------------------- 設定
test("設定: COMMENT_WINDOW_H は既定 24 で 24 未満にしない。COMMENT_MAX_PAGES は既定 80 で 1 以上", () => {
  const c = (env: Record<string, string>) => loadConfig(env, {});
  assert.deepEqual([c({}).commentWindowH, c({}).commentMaxPages], [24, 80]);
  assert.equal(c({ COMMENT_WINDOW_H: "48" }).commentWindowH, 48);
  assert.equal(c({ COMMENT_WINDOW_H: "6" }).commentWindowH, 24);
  assert.equal(c({ COMMENT_WINDOW_H: "x" }).commentWindowH, 24);
  assert.equal(c({ COMMENT_MAX_PAGES: "150" }).commentMaxPages, 150);
  assert.equal(c({ COMMENT_MAX_PAGES: "0" }).commentMaxPages, 1);
  assert.equal(c({ COMMENT_MAX_PAGES: "" }).commentMaxPages, 80);
});
