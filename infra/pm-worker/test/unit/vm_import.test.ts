import { afterEach, describe, expect, it, vi } from "vitest";
import worker from "../../src/index.ts";
import { MAX_IMPORT_BYTES } from "../../src/vmstate.ts";
import { T0, configuredApp, issuePayload, j, markFresh, send, type Call } from "../helpers.ts";

// VM の状態の取り込み (POST /admin/import) と書き出し (GET /admin/export) (#2343)。fetch はモック。
const REPO = "signature-studio/signature-studio-dev";
const R = `/repos/${REPO}`;
const PUSH = "Bearer ghp_valid_push_token_x";
const READ = "Bearer ghp_valid_read_token_xx";
const BOGUS = "Bearer ghp_bogus_token_xxxxx";
const IMPORT = "https://pm.example/admin/import";
const EXPORT = "https://pm.example/admin/export";
const RESYNC = "https://pm.example/admin/resync";
const HOUR = 3_600_000;
const iso = (ms: number) => new Date(ms).toISOString();

const repoAuth = (c: Call) => {
  if (!c.url.endsWith(R)) return undefined;
  if (c.auth === PUSH) return j({ permissions: { push: true } });
  if (c.auth === READ) return j({ permissions: { push: false } });
  return j({ message: "Bad credentials" }, 401);
};

// 同期が叩く一覧の応答。open の issue だけは渡せる (launch の対象にするため)。
const lists = (open: unknown[] = []) => (c: Call) => {
  if (c.method !== "GET") return undefined;
  const p = new URL(c.url).pathname;
  if (p.endsWith("/actions/runs")) return j({ workflow_runs: [] });
  if (p === `${R}/issues` && c.url.includes("state=open")) return j(open);
  if (/\/repos\/[^/]+\/[^/]+\/(issues|pulls)$/.test(p) || p.endsWith("/issues/comments")) return j([]);
  return undefined;
};

const writeOk = (c: Call) => (c.method === "POST" && /\/issues\/\d+\/comments$/.test(c.url) ? j({ html_url: "x" }, 201) : undefined);
const comments = (calls: Call[]) => calls.filter((c) => c.method === "POST" && /\/issues\/\d+\/comments$/.test(c.url));

// 取り込みの正しい例。VM の 3 ファイルと pm_art の形 (launch_issues.py と issue_snapshot.py が書く形)。
const vm = (o: Record<string, unknown> = {}) => ({
  launched: { "11": "2026-10-14T11:50:00.000000+00:00" },
  relaunch: { "11": { count: 1, art: "oc_artifacts: fl-win64 toolchain-retdec" } },
  phase: { review_only: false, open_prs: 4, since: "2026-10-14T10:00:00.123456+00:00" },
  pm_art: { "12": { at: "2026-10-13T10:00:00Z", line: "oc_artifacts: fl-win64 plugins-ott" } },
  ...o,
});

const post = (ctx: { app: { handle(r: Request): Promise<Response> } }, body: unknown, query = "?apply=1", auth: string | null = PUSH) => {
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (auth) headers.authorization = auth;
  const text = typeof body === "string" ? body : JSON.stringify(body);
  return ctx.app.handle(new Request(IMPORT + query, { method: "POST", headers, body: text }));
};
const getExport = (ctx: { app: { handle(r: Request): Promise<Response> } }, auth: string | null = PUSH) =>
  ctx.app.handle(new Request(EXPORT, { headers: auth ? { authorization: auth } : {} }));

const stateOf = (ctx: { store: { data: Map<string, Map<string, string>> } }) => JSON.stringify([...ctx.store.data].map(([b, m]) => [b, [...m]]));

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("VM の状態の取り込み・書き出し (#2343)", () => {
  it("往復: 取り込んだ値を書き出すと、同じ JSON になる (export → import → export で同一)", async () => {
    const ctx = await configuredApp({ handlers: [repoAuth, lists()] });
    const empty = (await (await getExport(ctx)).json()) as any;
    expect(empty).toEqual({ launched: {}, relaunch: {}, phase: null, pm_art: {} });
    const r = await post(ctx, vm());
    expect(r.status).toBe(200);
    expect(await r.json()).toMatchObject({ ok: true, applied: true, counts: { launched: 1, relaunch: 1, pm_art: 1 } });
    const out = (await (await getExport(ctx)).json()) as any;
    expect(out).toEqual(vm());
    // 書き出した JSON をそのまま取り込み直すと同じ
    const ctx2 = await configuredApp({ handlers: [repoAuth, lists()] });
    expect((await post(ctx2, out)).status).toBe(200);
    expect(await (await getExport(ctx2)).json()).toEqual(out);
  });

  it("(e) apply が無いときは検証だけ。保存は 1 回も起きず、書き出しも空のまま", async () => {
    const ctx = await configuredApp({ handlers: [repoAuth, lists()] });
    const before = stateOf(ctx);
    const writes = ctx.store.writes;
    const r = await post(ctx, vm(), "");
    expect(r.status).toBe(200);
    expect(await r.json()).toMatchObject({ applied: false, counts: { launched: 1 } });
    expect(ctx.store.writes).toBe(writes);
    expect(stateOf(ctx)).toBe(before);
    expect(ctx.app.engine.meta.importedAt).toBeUndefined();
  });

  it("(a) issue 番号が負・0・非数字・小数・先頭 0 のときは 400 で何も保存しない (launched・relaunch・pm_art の全部)", async () => {
    for (const bad of ["-5", "0", "abc", "1.5", "012", "12345678"]) {
      const ctx = await configuredApp({ handlers: [repoAuth, lists()] });
      const before = stateOf(ctx);
      const cases = [
        vm({ launched: { [bad]: "2026-10-14T11:50:00Z" } }),
        vm({ relaunch: { [bad]: { count: 0, art: null } } }),
        vm({ pm_art: { [bad]: { at: "2026-10-13T10:00:00Z", line: "oc_artifacts: fl-win64" } } }),
      ];
      for (const body of cases) {
        const r = await post(ctx, body);
        expect(r.status, `key=${bad}`).toBe(400);
        expect(((await r.json()) as any).error).toBe("invalid");
      }
      expect(stateOf(ctx), `key=${bad}`).toBe(before);
    }
  });

  it("(b)(i) 許可外の素材名 (relaunch.art・pm_art.line) や oc_artifacts 行でない値は 400 で何も保存しない", async () => {
    const ctx = await configuredApp({ handlers: [repoAuth, lists()] });
    const before = stateOf(ctx);
    const bodies = [
      vm({ relaunch: { "11": { count: 1, art: "oc_artifacts: fl-win64 evil-thing" } } }),
      vm({ pm_art: { "12": { at: "2026-10-13T10:00:00Z", line: "oc_artifacts: fetchsh" } } }),
      vm({ pm_art: { "12": { at: "2026-10-13T10:00:00Z", line: "fl-win64" } } }),
      vm({ pm_art: { "12": { at: "2026-10-13T10:00:00Z", line: "oc_artifacts: fl-win64 ../../etc" } } }),
    ];
    for (const b of bodies) expect((await post(ctx, b)).status).toBe(400);
    expect(stateOf(ctx)).toBe(before);
  });

  it("oc_artifacts: none (追加素材なし) は relaunch.art と pm_art.line で通り、書き出して取り込み直しても同じ JSON。none と素材名の混在は 400", async () => {
    const none = vm({
      relaunch: { "11": { count: 1, art: "oc_artifacts: none" } },
      pm_art: { "12": { at: "2026-10-13T10:00:00Z", line: "oc_artifacts: none" } },
    });
    const ctx = await configuredApp({ handlers: [repoAuth, lists()] });
    expect((await post(ctx, none)).status).toBe(200);
    const out = (await (await getExport(ctx)).json()) as any;
    expect(out).toEqual(none);
    const ctx2 = await configuredApp({ handlers: [repoAuth, lists()] });
    expect((await post(ctx2, out)).status).toBe(200);
    expect(await (await getExport(ctx2)).json()).toEqual(out);
    const before = stateOf(ctx);
    expect((await post(ctx, vm({ pm_art: { "12": { at: "2026-10-13T10:00:00Z", line: "oc_artifacts: none fl-win64" } } }))).status).toBe(400);
    expect((await post(ctx, vm({ relaunch: { "11": { count: 1, art: "oc_artifacts: none fl-win64" } } }))).status).toBe(400);
    expect(stateOf(ctx)).toBe(before);
  });

  it("現在時刻 + 5 分より後の時刻 (launched・pm_art.at) は 400 で何も保存しない。5 分以内の未来は通る", async () => {
    const ctx = await configuredApp({ handlers: [repoAuth, lists()] });
    const before = stateOf(ctx);
    const later = iso(T0 + 5 * 60_000 + 1000);
    expect((await post(ctx, vm({ launched: { "11": later }, relaunch: {}, pm_art: {} }))).status).toBe(400);
    expect((await post(ctx, vm({ launched: {}, relaunch: {}, pm_art: { "12": { at: later, line: "oc_artifacts: fl-win64" } } }))).status).toBe(400);
    expect(stateOf(ctx)).toBe(before);
    expect((await post(ctx, vm({ launched: { "11": iso(T0 + 4 * 60_000) }, relaunch: {}, pm_art: {} }))).status).toBe(200);
  });

  it("(c) 200 KB を超える JSON は 413 で何も保存しない", async () => {
    const ctx = await configuredApp({ handlers: [repoAuth, lists()] });
    const before = stateOf(ctx);
    const big = JSON.stringify(vm()) + " ".repeat(MAX_IMPORT_BYTES + 1);
    const r = await post(ctx, big);
    expect(r.status).toBe(413);
    expect(stateOf(ctx)).toBe(before);
  });

  it("(d) count=4 (範囲外) と count<0 は 400 で何も保存しない。count=3 は通る", async () => {
    const ctx = await configuredApp({ handlers: [repoAuth, lists()] });
    const before = stateOf(ctx);
    for (const count of [4, -1, 1.5]) {
      expect((await post(ctx, vm({ relaunch: { "11": { count, art: null } } }))).status, `count=${count}`).toBe(400);
    }
    expect(stateOf(ctx)).toBe(before);
    expect((await post(ctx, vm({ relaunch: { "11": { count: 3, art: null } } }))).status).toBe(200);
  });

  it("形式の欠落・未知のキー・壊れた JSON・配列は 400 (phase が無いときも含む)", async () => {
    const ctx = await configuredApp({ handlers: [repoAuth, lists()] });
    const before = stateOf(ctx);
    const { phase: _p, ...noPhase } = vm();
    const bodies: unknown[] = [noPhase, vm({ extra: 1 }), vm({ phase: { review_only: "no", open_prs: 1, since: "2026-10-14T10:00:00Z" } }), vm({ launched: { "11": "2026-10-14 11:50" } }), [], "{not json"];
    for (const b of bodies) expect((await post(ctx, b)).status).toBe(400);
    expect(stateOf(ctx)).toBe(before);
  });

  it("(f) 未認証・不明な token・読み取りだけの token は 404 で DO を変えない (import と export の両方)", async () => {
    const ctx = await configuredApp({ handlers: [repoAuth, lists()] });
    await markFresh(ctx);
    const before = stateOf(ctx);
    for (const auth of [null, BOGUS, READ]) {
      expect((await post(ctx, vm(), "?apply=1", auth)).status, `import auth=${auth}`).toBe(404);
      expect((await getExport(ctx, auth)).status, `export auth=${auth}`).toBe(404);
    }
    expect(stateOf(ctx)).toBe(before);
  });

  it("(f) 入口 (index.ts) でも未認証は 404 で DO を呼ばない。メソッドが違うときも 404", async () => {
    let doCalls = 0;
    const env = {
      STORE_KEY: "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
      REPO,
      PM: { idFromName: () => "main", get: () => ({ fetch: async () => (doCalls++, new Response("ok")) }) },
    } as any;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init?: RequestInit) => {
        const auth = new Headers(init?.headers).get("authorization");
        return auth === PUSH ? j({ permissions: { push: true } }) : j({ message: "Bad credentials" }, 401);
      }),
    );
    const req = (url: string, method: string, auth?: string) => new Request(url, { method, headers: auth ? { authorization: auth } : {}, body: method === "POST" ? "{}" : undefined });
    expect((await worker.fetch(req(IMPORT, "POST"), env)).status).toBe(404);
    expect((await worker.fetch(req(IMPORT, "POST", BOGUS), env)).status).toBe(404);
    expect((await worker.fetch(req(EXPORT, "GET"), env)).status).toBe(404);
    expect((await worker.fetch(req(IMPORT, "GET", PUSH), env)).status).toBe(404);
    expect((await worker.fetch(req(EXPORT, "POST", PUSH), env)).status).toBe(404);
    expect(doCalls).toBe(0);
    expect((await worker.fetch(req(EXPORT, "GET", PUSH), env)).status).toBe(200);
    expect(doCalls).toBe(1);
  });

  it("(g) 取り込み前は launch しない (picks が空・/status.launch_blocked=no-import)。取り込むと launch する", async () => {
    const ctx = await configuredApp({
      env: { IMPORT_REQUIRED: "1", LIVE_LAUNCH: "1", LIVE_DISPATCH: "0" },
      handlers: [repoAuth, lists([{ number: 11, title: "[CI-11] t11", body: "", state: "open", updated_at: "2026-10-14T11:00:00Z", labels: [] }]), writeOk],
    });
    expect((await send(ctx.app, "issues", issuePayload(11))).status).toBe(202);
    await markFresh(ctx);
    const s0 = ctx.app.engine.status() as any;
    expect(s0.launch_blocked).toBe("no-import");
    expect(s0.imported_at).toBeNull();
    expect(ctx.app.engine.plan().picks).toEqual([]);
    await ctx.app.engine.tick();
    expect(comments(ctx.m.calls)).toHaveLength(0);

    expect((await post(ctx, vm({ launched: {}, relaunch: {}, pm_art: {} }))).status).toBe(200);
    const s1 = ctx.app.engine.status() as any;
    expect(s1.launch_blocked).toBeNull();
    expect(s1.imported_at).not.toBeNull();
    await ctx.app.engine.tick();
    expect(comments(ctx.m.calls).map((c) => c.url)).toEqual([expect.stringContaining("/issues/11/comments")]);
  });

  it("(j) IMPORT_REQUIRED=0 なら、取り込み前でも launch する", async () => {
    const ctx = await configuredApp({
      env: { IMPORT_REQUIRED: "0", LIVE_LAUNCH: "1", LIVE_DISPATCH: "0" },
      handlers: [repoAuth, lists([{ number: 11, title: "[CI-11] t11", body: "", state: "open", updated_at: "2026-10-14T11:00:00Z", labels: [] }]), writeOk],
    });
    expect((await send(ctx.app, "issues", issuePayload(11))).status).toBe(202);
    await markFresh(ctx);
    expect((ctx.app.engine.status() as any).launch_blocked).toBeNull();
    await ctx.app.engine.tick();
    expect(comments(ctx.m.calls)).toHaveLength(1);
  });

  it("(h) launched が 2 時間前の issue は取り込み後の picks に入らず recent に入る。4 時間前なら picks に入る", async () => {
    for (const [hours, picked] of [
      [2, false],
      [4, true],
    ] as const) {
      const ctx = await configuredApp({ env: { IMPORT_REQUIRED: "1" }, handlers: [repoAuth, lists()] });
      expect((await send(ctx.app, "issues", issuePayload(11))).status).toBe(202);
      expect((await post(ctx, vm({ launched: { "11": iso(T0 - hours * HOUR) }, relaunch: {}, pm_art: {} }))).status).toBe(200);
      const p = ctx.app.engine.plan();
      expect(
        p.picks.some((x) => x.n === 11),
        `${hours}h ago`,
      ).toBe(picked);
      expect(
        p.rows.recent.some(([n]) => n === 11),
        `${hours}h ago recent`,
      ).toBe(!picked);
    }
  });

  it("同じ issue の取り込みは、より新しい launched・pm_art と、より多い relaunch の回数を残す (古い値で上書きしない)", async () => {
    const ctx = await configuredApp({ handlers: [repoAuth, lists()] });
    await post(ctx, vm({ launched: { "11": "2026-10-14T11:55:00Z" }, relaunch: { "11": { count: 2, art: null } }, pm_art: {} }));
    await post(ctx, vm({ launched: { "11": "2026-10-14T11:00:00Z" }, relaunch: { "11": { count: 1, art: null } }, pm_art: {} }));
    const out = (await (await getExport(ctx)).json()) as any;
    expect(out.launched).toEqual({ "11": "2026-10-14T11:55:00Z" });
    expect(out.relaunch).toEqual({ "11": { count: 2, art: null } });
  });

  it("取り込んだ pm_art と launchedAt は、全体同期 (POST /admin/resync) の後も残る", async () => {
    const ctx = await configuredApp({ handlers: [repoAuth, lists()] });
    expect((await post(ctx, vm())).status).toBe(200);
    const before = await (await getExport(ctx)).json();
    const r = await ctx.app.handle(new Request(RESYNC, { method: "POST", headers: { authorization: PUSH } }));
    expect(r.status).toBe(200);
    expect(await (await getExport(ctx)).json()).toEqual(before);
  });
});
