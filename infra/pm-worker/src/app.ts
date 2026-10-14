// Worker の HTTP 面 (/webhook /setup /setup/callback /status /tick)。Durable Object (do.ts) の中で動く。
// 保管先・時刻・fetch は注入する。App の id / private key / webhook secret は AES-GCM で封じて保管し、応答にもログにも出さない。
import type { Config } from "./config.ts";
import { openText, randomToken, safeEqual, sealText } from "./crypto.ts";
import { Engine } from "./engine.ts";
import { Gh, InstallationAuth, type FetchFn } from "./github.ts";
import type { Store } from "./store.ts";
import { WEBHOOK_EVENTS } from "./webhook.ts";

export const APP_NAME = "oc-pm-for-signature-studio";
export const SETUP_TTL_MS = 60 * 60_000;

interface AppRecord {
  appId: number;
  slug: string;
  pemSealed: string;
  whSealed: string;
  installationId: number | null;
}

export interface AppDeps {
  store: Store;
  cfg: Config;
  storeKey: string;
  now: () => number;
  fetch: FetchFn;
  // webhook 後に Engine.tick を早める (DO の alarm)。
  scheduleSoon: () => Promise<void>;
}

const html = (body: string, status = 200): Response =>
  new Response(`<!doctype html><meta charset="utf-8"><title>${APP_NAME}</title><body>${body}</body>`, {
    status,
    headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store", "x-content-type-options": "nosniff" },
  });
const json = (o: unknown, status = 200): Response =>
  new Response(JSON.stringify(o), { status, headers: { "content-type": "application/json", "cache-control": "no-store" } });
const esc = (s: string): string => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] as string);

// 権限と購読イベントの正本。contents: write は repository_dispatch (POST /repos/{o}/{r}/dispatches) に必要 (GitHub 公式の
// 権限表)。Worker のコードは contents の他の endpoint を呼ばない。
export function buildManifest(origin: string): Record<string, unknown> {
  return {
    name: APP_NAME,
    url: "https://github.com/signature-studio/signature-studio-dev",
    hook_attributes: { url: `${origin}/webhook`, active: true },
    redirect_url: `${origin}/setup/callback`,
    public: false,
    default_permissions: { issues: "write", pull_requests: "write", contents: "write", actions: "read", metadata: "read" },
    default_events: [...WEBHOOK_EVENTS],
  };
}

export class PmApp {
  readonly engine: Engine;
  private readonly d: AppDeps;
  private creds: { appId: number; pem: string; installationId: number | null } | null = null;
  private wh: string | null = null;
  private auth: InstallationAuth | null = null;
  private gh: Gh | null = null;
  private readonly authCache = new Map<string, { ok: boolean; until: number }>();

  constructor(d: AppDeps) {
    this.d = d;
    this.engine = new Engine({
      store: d.store,
      cfg: d.cfg,
      now: d.now,
      gh: () => this.getGh(),
      pmBotLogin: () => {
        const a = d.store.get<AppRecord>("meta", "app");
        return a ? `${a.slug}[bot]` : null;
      },
    });
  }

  private record(): AppRecord | undefined {
    return this.d.store.get<AppRecord>("meta", "app");
  }

  private async getGh(): Promise<Gh | null> {
    const rec = this.record();
    if (!rec || rec.installationId === undefined) return null;
    if (!this.gh) {
      this.auth = new InstallationAuth(
        this.d.fetch,
        async () => {
          if (!this.creds) {
            const r = this.record() as AppRecord;
            this.creds = { appId: r.appId, pem: await openText(this.d.storeKey, r.pemSealed), installationId: r.installationId };
          }
          return this.creds;
        },
        this.d.now,
        (id) => {
          const r = this.record() as AppRecord;
          this.d.store.put("meta", "app", { ...r, installationId: id });
          if (this.creds) this.creds.installationId = id;
        },
      );
      this.gh = new Gh(this.d.fetch, () => (this.auth as InstallationAuth).token(), this.d.cfg.repo);
    }
    return this.gh;
  }

  private async webhookSecret(): Promise<string | null> {
    if (this.wh) return this.wh;
    const r = this.record();
    if (!r) return null;
    this.wh = await openText(this.d.storeKey, r.whSealed);
    return this.wh;
  }

  async handle(req: Request): Promise<Response> {
    const u = new URL(req.url);
    const p = u.pathname;
    if (p === "/webhook" && req.method === "POST") return this.webhook(req);
    if (p === "/setup" && req.method === "GET") return this.setup(u);
    if (p === "/setup/callback" && req.method === "GET") return this.callback(u);
    if (p === "/status" && req.method === "GET") return this.status(req);
    if (p === "/tick" && req.method === "POST") {
      const r = await this.engine.tick();
      return json({ ok: true, ready: r.ready });
    }
    return json({ error: "not found" }, 404);
  }

  // ---------------------------------------------------------------- /webhook
  private async webhook(req: Request): Promise<Response> {
    const secret = await this.webhookSecret();
    if (!secret) return json({ error: "not configured" }, 503);
    const body = await req.text();
    if (body.length > 25 * 1024 * 1024) return json({ error: "too large" }, 413);
    const r = this.engine.receive(secret, req.headers.get("x-github-event"), req.headers.get("x-hub-signature-256"), body);
    if (r.status === 401) return json({ error: "unauthorized" }, 401);
    if (r.reason === "applied") await this.d.scheduleSoon();
    return json({ ok: true, result: r.reason }, 202);
  }

  // ---------------------------------------------------------------- manifest flow
  private setup(u: URL): Response {
    if (this.record()) return html("<p>Already configured. Setup is closed.</p>", 409);
    const state = randomToken(24);
    this.d.store.put("meta", "setupState", { state, exp: this.d.now() + SETUP_TTL_MS });
    const manifest = JSON.stringify(buildManifest(u.origin));
    const org = this.d.cfg.org;
    const action = `https://github.com/organizations/${encodeURIComponent(org)}/settings/apps/new?state=${encodeURIComponent(state)}`;
    return html(
      `<h1>${APP_NAME}</h1><p>Organization <b>${esc(org)}</b> に GitHub App を作成します。下のボタン → GitHub で「Create GitHub App」→ 次の画面で「Install」。</p>` +
        `<form method="post" action="${esc(action)}"><input type="hidden" name="manifest" value="${esc(manifest)}"><button type="submit">Create GitHub App</button></form>`,
    );
  }

  private async callback(u: URL): Promise<Response> {
    if (this.record()) return html("<p>Already configured. Setup is closed.</p>", 409);
    const code = u.searchParams.get("code") ?? "";
    const state = u.searchParams.get("state") ?? "";
    const saved = this.d.store.get<{ state: string; exp: number }>("meta", "setupState");
    // state は /setup で発行したものだけを、1 回・期限内に限り受け付ける (他人が用意した code で上書きされない)。
    if (!saved || this.d.now() > saved.exp || !safeEqual(state, saved.state)) return html("<p>Invalid or expired state. Open /setup again.</p>", 400);
    if (!/^[0-9a-f]{20,64}$/i.test(code)) return html("<p>Invalid code.</p>", 400);
    this.d.store.del("meta", "setupState");
    const r = await this.d.fetch(`https://api.github.com/app-manifests/${code}/conversions`, {
      method: "POST",
      headers: { accept: "application/vnd.github+json", "user-agent": "signature-studio-pm-worker" },
    });
    if (!r.ok) {
      void r.body?.cancel();
      return html(`<p>GitHub conversion failed (${r.status}). Open /setup again.</p>`, 502);
    }
    const j = (await r.json()) as { id?: number; slug?: string; pem?: string; webhook_secret?: string; owner?: { login?: string } };
    // /setup は無認証なので、第三者が自分の App を作って code を持ち込んでも保存しない (owner が org の App だけ受け付ける)。
    if (j.owner?.login?.toLowerCase() !== this.d.cfg.org.toLowerCase()) return html("<p>App owner is not the expected organization.</p>", 403);
    if (!Number.isInteger(j.id) || !j.pem || !j.webhook_secret || !/^[\w-]{1,64}$/.test(j.slug ?? "")) {
      return html("<p>Unexpected response from GitHub.</p>", 502);
    }
    const rec: AppRecord = {
      appId: j.id as number,
      slug: j.slug as string,
      pemSealed: await sealText(this.d.storeKey, j.pem),
      whSealed: await sealText(this.d.storeKey, j.webhook_secret),
      installationId: null,
    };
    this.d.store.put("meta", "app", rec);
    return html(
      `<p>Created. 次に <a href="https://github.com/apps/${esc(rec.slug)}/installations/new">Install</a> を押し、signature-studio-dev を選んでください。` +
        `(鍵と secret は暗号化して保管し、ここには表示しません。)</p>`,
    );
  }

  // ---------------------------------------------------------------- /status
  // 既定は集計だけ。detail=1 は、呼び出し側が自分の GitHub token (Authorization: Bearer) で repo の push 権限を示したときだけ。
  // token は保存せず、結果 (真偽) を 60 秒だけ token のハッシュで覚える。
  private async status(req: Request): Promise<Response> {
    const detail = new URL(req.url).searchParams.get("detail") === "1";
    const rec = this.record();
    // App の bot ログイン (公開情報)。Actions 側の vars.OC_PM_BOT_LOGIN にはこの値を設定する。
    const s = this.engine.status({ configured: !!rec, installed: !!rec?.installationId, pm_bot_login: rec ? `${rec.slug}[bot]` : null });
    if (!detail) {
      for (const k of ["log", "would_launch_now", "last_error"]) delete s[k];
      return json(s);
    }
    if (!(await this.callerCanPush(req.headers.get("authorization")))) return json({ error: "unauthorized" }, 401);
    return json(s);
  }

  private async callerCanPush(h: string | null): Promise<boolean> {
    const m = /^Bearer (\S{10,255})$/.exec(h ?? "");
    if (!m) return false;
    const key = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(m[1])))).map((b) => b.toString(16).padStart(2, "0")).join("");
    const c = this.authCache.get(key);
    if (c && c.until > this.d.now()) return c.ok;
    const r = await this.d.fetch(`https://api.github.com/repos/${this.d.cfg.repo}`, {
      headers: { authorization: `Bearer ${m[1]}`, accept: "application/vnd.github+json", "user-agent": "signature-studio-pm-worker" },
    });
    let ok = false;
    if (r.ok) {
      const j = (await r.json()) as { permissions?: { push?: boolean; admin?: boolean } };
      ok = !!(j.permissions?.push || j.permissions?.admin);
    } else void r.body?.cancel();
    this.authCache.set(key, { ok, until: this.d.now() + 60_000 });
    return ok;
  }
}
