import { generateKeyPairSync } from "node:crypto";
import { PmApp } from "../src/app.ts";
import { loadConfig } from "../src/config.ts";
import { b64u } from "../src/crypto.ts";
import { SIGNAL_VER } from "../src/engine.ts";
import { signBody } from "../src/hmac.ts";
import { MemoryStore } from "../src/kvstore.ts";

export const T0 = Date.parse("2026-10-14T12:00:00Z");
export const STORE_KEY = b64u(new Uint8Array(32).fill(7));
export const WH_SECRET = "wh-secret-for-tests";
export const BOT = "opencode-for-signature-studio[bot]";
// 停止印 (oc-fix-limit) の作者 = job の GITHUB_TOKEN (#2639)
export const MARK = "github-actions[bot]";

export interface Call {
  method: string;
  url: string;
  body: any;
  auth: string | null;
}

export type Handler = (c: Call) => Response | undefined | Promise<Response | undefined>;

export function rsaPems(): { pkcs1: string; pkcs8: string } {
  const { privateKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
  return {
    pkcs1: privateKey.export({ type: "pkcs1", format: "pem" }) as string,
    pkcs8: privateKey.export({ type: "pkcs8", format: "pem" }) as string,
  };
}

export const j = (o: unknown, status = 200, headers: Record<string, string> = {}): Response =>
  new Response(status === 204 ? null : JSON.stringify(o), { status, headers: { "content-type": "application/json", ...headers } });

// 呼び出しを全て記録する fetch モック。handlers を順に試し、どれも答えなければ 599 を返す (想定外の呼び出しを検出する)。
export function mockFetch(handlers: Handler[]) {
  const calls: Call[] = [];
  const f = async (url: string, init: RequestInit = {}): Promise<Response> => {
    const h = new Headers(init.headers as any);
    const c: Call = { method: init.method ?? "GET", url, body: init.body ? JSON.parse(String(init.body)) : undefined, auth: h.get("authorization") };
    calls.push(c);
    for (const fn of handlers) {
      const r = await fn(c);
      if (r) return r;
    }
    return j({ message: "unexpected" }, 599);
  };
  return { f, calls };
}

// App 作成済み・Install 済みの状態を、本物の manifest flow で作る。
export async function configuredApp(opts: { live?: boolean; now?: { t: number }; handlers?: Handler[]; env?: Record<string, string>; store?: MemoryStore } = {}) {
  const clock = opts.now ?? { t: T0 };
  const pems = rsaPems();
  const store = opts.store ?? new MemoryStore();
  const m = mockFetch([
    (c) => (c.url.includes("/app-manifests/") ? j({ id: 4242, slug: "oc-pm-for-signature-studio", pem: pems.pkcs1, webhook_secret: WH_SECRET, owner: { login: "signature-studio" } }, 201) : undefined),
    (c) => (c.url.endsWith("/app/installations?per_page=100") ? j([{ id: 77 }]) : undefined),
    (c) => (c.url.endsWith("/app/installations/77/access_tokens") ? j({ token: "ghs_installation_token_value" }, 201) : undefined),
    ...(opts.handlers ?? []),
  ]);
  let soon = 0;
  const app = new PmApp({
    store,
    // 既定は VM の状態を取り込み済み扱い (IMPORT_REQUIRED=0)。取り込みの前提を見るテストだけ IMPORT_REQUIRED を "1" にする (#2343)。
    cfg: loadConfig({ LIVE: opts.live ? "1" : undefined, IMPORT_REQUIRED: "0", ...(opts.env ?? {}) }, {}),
    storeKey: STORE_KEY,
    now: () => clock.t,
    fetch: m.f,
    scheduleSoon: async () => {
      soon++;
    },
  });
  const page = await app.handle(new Request("https://pm.example/setup"));
  const html = await page.text();
  const state = /state=([^"&]+)/.exec(html)?.[1] as string;
  const cb = await app.handle(new Request(`https://pm.example/setup/callback?code=${"a".repeat(40)}&state=${state}`));
  return { app, store, m, clock, pems, cb, soon: () => soon, state };
}

export function send(app: PmApp, event: string, payload: unknown, sig?: string | null) {
  const body = JSON.stringify(payload);
  const s = sig === undefined ? signBody(WH_SECRET, body) : sig;
  return app.handle(
    new Request("https://pm.example/webhook", {
      method: "POST",
      body,
      headers: { "x-github-event": event, ...(s ? { "x-hub-signature-256": s } : {}) },
    }),
  );
}

export const REPO = { full_name: "signature-studio/signature-studio-dev" };

export const issuePayload = (n: number, o: Partial<{ title: string; body: string; labels: string[]; state: string; at: string; blocked: number }> = {}) => ({
  action: "opened",
  repository: REPO,
  issue: {
    number: n,
    title: o.title ?? `[CI-${n}] t${n}`,
    body: o.body ?? "",
    state: o.state ?? "open",
    updated_at: o.at ?? "2026-10-14T11:00:00Z",
    labels: (o.labels ?? []).map((name) => ({ name })),
    issue_dependencies_summary: { total_blocked_by: o.blocked ?? 0 },
  },
});

export const runPayload = (id: number, status: string, o: { event?: string; title?: string; at?: string; created?: string } = {}) => ({
  action: status === "completed" ? "completed" : "in_progress",
  repository: REPO,
  workflow_run: {
    id,
    event: o.event ?? "issue_comment",
    display_title: o.title ?? `run ${id}`,
    status,
    conclusion: status === "completed" ? "success" : null,
    updated_at: o.at ?? "2026-10-14T11:30:00Z",
    created_at: o.created,
  },
});

export const commentPayload = (n: number, login: string, body: string, at = "2026-10-14T11:00:00Z") => ({
  action: "created",
  repository: REPO,
  issue: { number: n },
  comment: { user: { login, type: login.endsWith("[bot]") ? "Bot" : "User" }, body, created_at: at },
});

// engine を「同期済み」にする (fullSyncAt / reconcileAt を now に置く)。
export async function markFresh(ctx: { app: PmApp; store: MemoryStore; clock: { t: number } }) {
  const meta = ctx.store.get<any>("meta", "main") ?? {};
  meta.fullSyncAt = ctx.clock.t;
  meta.signalVer = SIGNAL_VER;
  meta.reconcileAt = ctx.clock.t;
  ctx.store.put("meta", "main", meta);
  ctx.app.engine.meta = meta;
}
