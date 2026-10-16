import { afterEach, describe, expect, it, vi } from "vitest";
import worker from "../../src/index.ts";
import { T0, configuredApp, issuePayload, j, send, type Call } from "../helpers.ts";

// 降格の解除 (POST /demote/reset #2340) の入口ゲート (#5483 [CI-227])。
// DO 直呼びの test/demote_shadow.test.ts は入口 (index.ts) の許可リストを通らないため、この経路は検出漏れだった。
const REPO = "signature-studio/signature-studio-dev";
const R = `/repos/${REPO}`;
const PUSH = "Bearer ghp_valid_push_token_x";
const READ = "Bearer ghp_valid_read_token_xx";
const BOGUS = "Bearer ghp_bogus_token_xxxxx";
const RESET = "https://pm.example/demote/reset";
const PM_BOT = "oc-pm-for-signature-studio[bot]";
const VM = "pycabbage";
const MIN = 60_000;

// 呼び出し元の token で push 権限を示す (PUSH のみ可)。それ以外は 401 (GitHub の応答と同じ)。
const repoAuth = (c: Call) => {
  if (!c.url.endsWith(R)) return undefined;
  if (c.auth === PUSH) return j({ permissions: { push: true } });
  if (c.auth === READ) return j({ permissions: { push: false } });
  return j({ message: "Bad credentials" }, 401);
};

const ocEv = (n: number, id: number, login: string, at: number) => ({
  action: "created",
  repository: { full_name: REPO },
  issue: { number: n },
  comment: { id, user: { login }, body: "/oc\noc_artifacts: fl-win64", created_at: new Date(at).toISOString() },
});

const status = async (ctx: { app: { handle(r: Request): Promise<Response> } }) => (await (await ctx.app.handle(new Request("https://pm.example/status"))).json()) as any;

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("POST /demote/reset の入口ゲート (#5483 [CI-227])", () => {
  it("(a) 入口 (index.ts) で未認証・不明な token・読み取りだけの token・GET は 404 で、DO を呼ばない", async () => {
    let doCalls = 0;
    const env = {
      REPO,
      PM: { idFromName: () => "main", get: () => ({ fetch: async () => (doCalls++, new Response("ok")) }) },
    } as any;
    const gh = vi.fn(async (_url: string, init?: RequestInit) => {
      const auth = new Headers(init?.headers).get("authorization");
      return auth === PUSH ? j({ permissions: { push: true } }) : j({ message: "Bad credentials" }, 401);
    });
    vi.stubGlobal("fetch", gh);
    const post = (h: Record<string, string> = {}) => worker.fetch(new Request(RESET, { method: "POST", headers: h }), env);
    expect((await post()).status).toBe(404);
    expect((await post({ authorization: BOGUS })).status).toBe(404);
    expect((await post({ authorization: READ })).status).toBe(404);
    // GET は入口で 404 (405 ではない。既存の管理用の経路と同じ)。
    expect((await worker.fetch(new Request(RESET, { headers: { authorization: PUSH } }), env)).status).toBe(404);
    expect(doCalls).toBe(0);
    // 権限の確認は token のある POST の 2 回だけ (未認証・メソッド違いは確認しない)。
    expect(gh).toHaveBeenCalledTimes(2);
  });

  it("(b) 入口経由の解除: 降格した DO に push 権限つき token で POST すると 200 で reset し、mode が live に戻る", async () => {
    const ctx = await configuredApp({ live: true, handlers: [repoAuth] });
    for (const n of [11, 12]) await send(ctx.app, "issues", issuePayload(n));
    // 降格 (#2340): 同じ issue に 30 分以内に VM の /oc と PM App の /oc が付く (demote_shadow.test.ts と同じ手順)。
    await send(ctx.app, "issue_comment", ocEv(11, 1, VM, T0 + 1 * MIN));
    ctx.clock.t = T0 + 10 * MIN;
    await send(ctx.app, "issue_comment", ocEv(11, 2, PM_BOT, T0 + 10 * MIN));
    const before = await status(ctx);
    expect(before.mode).toBe("dry-run");
    expect(before.demoted_reason).toBe("double-oc #11");

    // 入口 (index.ts) から解除する。DO は env.PM.get の stub 経由で本物の PmApp を呼ぶ。
    const env = {
      REPO,
      PM: { idFromName: () => "main", get: () => ({ fetch: (r: Request) => ctx.app.handle(r) }) },
    } as any;
    vi.stubGlobal("fetch", ctx.m.f);
    const r = await worker.fetch(new Request(RESET, { method: "POST", headers: { authorization: PUSH } }), env);
    expect(r.status).toBe(200);
    expect(await r.json()).toEqual({ ok: true, reset: true });

    const after = await status(ctx);
    expect(after.mode).toBe("live");
    expect(after.demoted_reason).toBe(null);
    expect(after.counters.restored).toBe(1);
  });
});
