import { afterEach, describe, expect, it, vi } from "vitest";
import worker from "../../src/index.ts";
import { MemoryStore } from "../../src/kvstore.ts";
import { T0, configuredApp, j, markFresh, type Call } from "../helpers.ts";

// 管理用の全体同期 (POST /admin/resync) と、失敗した webhook 配送の回収 (App の JWT で一覧を読み、再配送する)。fetch はモック。
const REPO = "signature-studio/signature-studio-dev";
const R = `/repos/${REPO}`;
const PUSH = "Bearer ghp_valid_push_token_x";
const READ = "Bearer ghp_valid_read_token_xx";
const BOGUS = "Bearer ghp_bogus_token_xxxxx";
const RESYNC = "https://pm.example/admin/resync";
const MIN = 60_000;

// 呼び出し元の token で push 権限を示す (PUSH のみ可)。それ以外は 401 (GitHub の応答と同じ)。
const repoAuth = (c: Call) => {
  if (!c.url.endsWith(R)) return undefined;
  if (c.auth === PUSH) return j({ permissions: { push: true } });
  if (c.auth === READ) return j({ permissions: { push: false } });
  return j({ message: "Bad credentials" }, 401);
};

// 同期が叩く一覧の応答 (空の repo)。open の issue だけは渡せる。
const repoLists = (openIssues: unknown[] = []) => (c: Call) => {
  if (c.method !== "GET") return undefined;
  const p = new URL(c.url).pathname;
  if (p.endsWith("/actions/runs")) return j({ workflow_runs: [] });
  if (p === `${R}/issues` && c.url.includes("state=open")) return j(openIssues);
  if (/\/repos\/[^/]+\/[^/]+\/(issues|pulls)$/.test(p) || p.endsWith("/issues/comments")) return j([]);
  return undefined;
};

type Delivery = { id: number; guid: string; status: string; redelivery?: boolean };

// 配送の一覧 (GET /app/hook/deliveries) と再配送 (POST .../attempts)。posted に再配送した配送 id を積む。
const hook = (list: () => Delivery[], posted: number[]) => (c: Call) => {
  if (c.method === "GET" && c.url.startsWith("https://api.github.com/app/hook/deliveries?")) return j(list());
  const m = /\/app\/hook\/deliveries\/(\d+)\/attempts$/.exec(c.url);
  if (c.method === "POST" && m) {
    posted.push(Number(m[1]));
    return j(null, 202);
  }
  return undefined;
};

const failing = (ids: number[]): Delivery[] => ids.map((id) => ({ id, guid: `g${id}`, status: "Failure" }));

// 1 回の点検を、前回から 6 分進めて走らせる (再配送の走査は 5 分ごと)。
async function scanAfter(ctx: { clock: { t: number }; app: { engine: { tick(): Promise<unknown> } } }, minutes = 6) {
  ctx.clock.t += minutes * MIN;
  await ctx.app.engine.tick();
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("失敗した webhook 配送の回収 (#2339)", () => {
  it("(a) status=OK の配送は再配送しない。同じ guid に OK の配送があれば回収済みとして触らない", async () => {
    const posted: number[] = [];
    const list: Delivery[] = [
      { id: 1, guid: "g1", status: "OK" },
      { id: 2, guid: "g2", status: "Failure" },
      { id: 3, guid: "g3", status: "OK", redelivery: true },
      { id: 4, guid: "g3", status: "Failure" },
    ];
    const ctx = await configuredApp({ env: { LIVE_REDELIVER: "1" }, handlers: [repoAuth, repoLists(), hook(() => list, posted)] });
    await markFresh(ctx);
    await scanAfter(ctx);
    expect(posted).toEqual([2]);
    const s = ctx.app.engine.status() as any;
    expect(s.counters.redelivered).toBe(1);
    expect(s.hook_failed_last_scan).toBe(2);
    expect(s.last_redeliver_scan).not.toBeNull();
  });

  it("(b) 同じ guid は 3 回まで。4 回目は再配送しない (走査を 4 回走らせても POST は 3 回)", async () => {
    const posted: number[] = [];
    const ctx = await configuredApp({ env: { LIVE_REDELIVER: "1" }, handlers: [repoAuth, repoLists(), hook(() => failing([2]), posted)] });
    await markFresh(ctx);
    for (let i = 0; i < 4; i++) await scanAfter(ctx);
    expect(posted).toEqual([2, 2, 2]);
    expect((ctx.app.engine.status() as any).counters.redelivered).toBe(3);
  });

  it("走査 1 回の再配送は 10 件まで。試行の少ないものから送るので、残りは次の走査で送られる", async () => {
    const posted: number[] = [];
    // 一覧は新しい順 (GitHub と同じ)。古い配送は 101、新しい配送は 112。
    const ids = Array.from({ length: 12 }, (_, i) => 112 - i);
    const ctx = await configuredApp({ env: { LIVE_REDELIVER: "1" }, handlers: [repoAuth, repoLists(), hook(() => failing(ids), posted)] });
    await markFresh(ctx);
    await scanAfter(ctx);
    expect(posted).toHaveLength(10);
    expect(new Set(posted).size).toBe(10);
    await scanAfter(ctx);
    expect(posted.length).toBeLessThanOrEqual(20);
    expect(posted.slice(10, 12).sort((a, b) => a - b)).toEqual([111, 112]);
  });

  it("(f) 再送された配送 (redelivery: true) が失敗しても、それを再送しない (連鎖させない)。元の配送だけが上限まで再送される", async () => {
    const posted: number[] = [];
    const list: Delivery[] = [
      { id: 9, guid: "x9", status: "Failure", redelivery: true },
      { id: 2, guid: "g2", status: "Failure" },
    ];
    const ctx = await configuredApp({ env: { LIVE_REDELIVER: "1" }, handlers: [repoAuth, repoLists(), hook(() => list, posted)] });
    await markFresh(ctx);
    await scanAfter(ctx);
    expect(posted).toEqual([2]);
  });

  it("既定 (LIVE_REDELIVER 未設定) は POST しない。一覧を読んで送るはずだった件数だけ数え、同じ guid は 1 回だけ数える", async () => {
    const posted: number[] = [];
    const ctx = await configuredApp({ handlers: [repoAuth, repoLists(), hook(() => failing([2, 5]), posted)] });
    await markFresh(ctx);
    await scanAfter(ctx);
    await scanAfter(ctx);
    expect(posted).toEqual([]);
    const s = ctx.app.engine.status() as any;
    expect(s.counters.wouldRedeliver).toBe(2);
    expect(s.counters.redelivered).toBe(0);
    expect(s.log.some((l: any) => l.kind === "would-redeliver")).toBe(true);
  });

  it("失敗した配送の一覧読み出しが落ちても、同期と tick は止めない (lastError にも残さない)", async () => {
    const ctx = await configuredApp({
      env: { LIVE_REDELIVER: "1" },
      handlers: [repoAuth, repoLists(), (c: Call) => (c.url.startsWith("https://api.github.com/app/hook/deliveries") ? j({ message: "boom" }, 500) : undefined)],
    });
    await markFresh(ctx);
    await scanAfter(ctx);
    const s = ctx.app.engine.status() as any;
    expect(s.last_error).toBeNull();
    expect(s.fresh).toBe(true);
    expect(s.log.some((l: any) => l.kind === "error" && /hook deliveries/.test(l.note))).toBe(true);
  });
});

describe("POST /admin/resync (#2339)", () => {
  it("(c) 未認証・不明な token・読み取りだけの token は 404 で、DO の状態もストアも変えない (GitHub の同期も走らない)", async () => {
    const ctx = await configuredApp({ handlers: [repoAuth, repoLists()] });
    await markFresh(ctx);
    const writes = ctx.store.writes;
    const before = JSON.stringify([...ctx.store.data].map(([b, m]) => [b, [...m]]));
    const calls0 = ctx.m.calls.length;
    for (const auth of [null, BOGUS, READ]) {
      const h: Record<string, string> = auth ? { authorization: auth } : {};
      const r = await ctx.app.handle(new Request(RESYNC, { method: "POST", headers: h }));
      expect(r.status, `auth=${auth}`).toBe(404);
    }
    expect(ctx.store.writes).toBe(writes);
    expect(JSON.stringify([...ctx.store.data].map(([b, m]) => [b, [...m]]))).toBe(before);
    const sync = ctx.m.calls.slice(calls0).filter((c) => !c.url.endsWith(R));
    expect(sync).toEqual([]);
  });

  it("(c) 入口 (index.ts) で未認証なら DO を呼ばず 404。GET も 404", async () => {
    let doCalls = 0;
    const env = {
      STORE_KEY: "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
      REPO,
      PM: { idFromName: () => "main", get: () => ({ fetch: async () => (doCalls++, new Response("ok")) }) },
    } as any;
    const gh = vi.fn(async (url: string, init?: RequestInit) => {
      const auth = new Headers(init?.headers).get("authorization");
      return auth === PUSH ? j({ permissions: { push: true } }) : j({ message: "Bad credentials" }, 401);
    });
    vi.stubGlobal("fetch", gh);
    const post = (h: Record<string, string> = {}) => worker.fetch(new Request(RESYNC, { method: "POST", headers: h }), env);
    expect((await post()).status).toBe(404);
    expect((await post({ authorization: BOGUS })).status).toBe(404);
    expect((await worker.fetch(new Request(RESYNC, { headers: { authorization: PUSH } }), env)).status).toBe(404);
    expect(doCalls).toBe(0);
    expect(gh).toHaveBeenCalledTimes(1);
    expect((await post({ authorization: PUSH })).status).toBe(200);
    expect(doCalls).toBe(1);
  });

  it("(d) 1 時間に 3 回呼ぶと 3 回目は 429 (GitHub の同期は走らせない)。1 時間たてば再び通る", async () => {
    const ctx = await configuredApp({ handlers: [repoAuth, repoLists()] });
    await markFresh(ctx);
    const call = () => ctx.app.handle(new Request(RESYNC, { method: "POST", headers: { authorization: PUSH } }));
    expect((await call()).status).toBe(200);
    ctx.clock.t += MIN;
    expect((await call()).status).toBe(200);
    ctx.clock.t += MIN;
    const calls = ctx.m.calls.length;
    const third = await call();
    expect(third.status).toBe(429);
    expect(third.headers.get("retry-after")).toBe(String(Math.ceil((T0 + 60 * MIN - (T0 + 2 * MIN)) / 1000)));
    expect(ctx.m.calls.length - calls).toBe(1);
    ctx.clock.t = T0 + 61 * MIN;
    expect((await call()).status).toBe(200);
  });

  it("(e) resync の後も永続状態 (launchedAt・relaunch・planned・counters) は失われない", async () => {
    const store = new MemoryStore();
    const launchedAt = "2026-10-14T11:50:00.000Z";
    const relaunch = { count: 2, art: "oc_artifacts: fl-win64" };
    store.put("launchedAt", "11", launchedAt);
    store.put("relaunch", "11", relaunch);
    store.put("relaunch", "np:12", { count: 1 });
    store.put("meta", "planned", { "11": T0 - 1000 });
    store.put("meta", "main", {
      counters: { launched: 5, dispatched: 2, wouldLaunch: 0, wouldDispatch: 0, reconciles: 3, pmDispatched: 0, wouldDispatchPm: 0 },
      fullSyncAt: T0 - 60 * MIN,
      reconcileAt: T0 - 60 * MIN,
    });
    const open = [{ number: 11, title: "[CI-11] t", body: "", state: "open", updated_at: "2026-10-14T11:00:00Z", labels: [] }];
    const ctx = await configuredApp({ store, handlers: [repoAuth, repoLists(open)] });
    await markFresh(ctx);
    const r = await ctx.app.handle(new Request(RESYNC, { method: "POST", headers: { authorization: PUSH } }));
    expect(r.status).toBe(200);
    expect(store.get("launchedAt", "11")).toBe(launchedAt);
    expect(store.get("relaunch", "11")).toEqual(relaunch);
    expect(store.get("relaunch", "np:12")).toEqual({ count: 1 });
    expect(store.get("meta", "planned")).toEqual({ "11": T0 - 1000 });
    const s = ctx.app.engine.status() as any;
    expect(s.counters).toMatchObject({ launched: 5, dispatched: 2, reconciles: 3 });
    expect(ctx.app.engine.s.launchedAt["11"]).toBe(launchedAt);
    expect(s.open_issues).toBe(1);
    expect(s.log.some((l: any) => l.kind === "resync")).toBe(true);
  });
});
