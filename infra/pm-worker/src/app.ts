// Worker の HTTP 面 (/webhook /setup /setup/callback /status /tick)。Durable Object (do.ts) の中で動く。
// 保管先・時刻・fetch は注入する。App の id / private key / webhook secret は AES-GCM で封じて保管し、応答にもログにも出さない。
import { bearerToken, canPushRepo } from "./admin.ts";
import type { Config } from "./config.ts";
import { openText, randomToken, safeEqual, sealText } from "./crypto.ts";
import { Engine } from "./engine.ts";
import { appJwt, Gh, InstallationAuth, type FetchFn } from "./github.ts";
import type { Store } from "./kvstore.ts";
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
const json = (o: unknown, status = 200, extra: Record<string, string> = {}): Response =>
  new Response(JSON.stringify(o), { status, headers: { "content-type": "application/json", "cache-control": "no-store", ...extra } });
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
  private appJwtGh: Gh | null = null;
  private readonly authCache = new Map<string, { ok: boolean; until: number }>();

  constructor(d: AppDeps) {
    this.d = d;
    this.engine = new Engine({
      store: d.store,
      cfg: d.cfg,
      now: d.now,
      gh: () => this.getGh(),
      app: () => this.getAppGh(),
      pmBotLogin: () => {
        const a = d.store.get<AppRecord>("meta", "app");
        return a ? `${a.slug}[bot]` : null;
      },
      // status・ログから取り除く実行時の secret (復号済みの webhook secret・PEM・STORE_KEY と、直近の installation token)。
      secrets: () => {
        const pem = this.creds?.pem ?? "";
        const pemLines = pem.split("\n").filter((l) => l.length >= 20 && !l.startsWith("-----"));
        return [this.wh, pem, ...pemLines, d.storeKey, this.auth?.current()].filter((x): x is string => !!x);
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
      this.gh = new Gh(this.d.fetch, () => (this.auth as InstallationAuth).token(), this.d.cfg.repo, (r) => this.engine.recordRate(r));
    }
    return this.gh;
  }

  // App の JWT で叩く REST (GET /app/hook/deliveries と再配送)。installation token とは枠が別なので、レート情報は engine に渡さない。
  private async getAppGh(): Promise<Gh | null> {
    const rec = this.record();
    if (!rec) return null;
    if (!this.creds) this.creds = { appId: rec.appId, pem: await openText(this.d.storeKey, rec.pemSealed), installationId: rec.installationId };
    const creds = this.creds;
    if (!this.appJwtGh) this.appJwtGh = new Gh(this.d.fetch, () => appJwt(creds.appId, creds.pem, Math.floor(this.d.now() / 1000)), this.d.cfg.repo);
    return this.appJwtGh;
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
    if (p === "/admin/resync" && req.method === "POST") return this.resync(req);
    return json({ error: "not found" }, 404);
  }

  // ---------------------------------------------------------------- /admin/resync (#2339)
  // 認証は入口 (index.ts) でも行い、通らなければ DO を呼ばない。ここでも同じ確認をする (未認証は 404 で状態を変えない)。
  private async resync(req: Request): Promise<Response> {
    const token = bearerToken(req.headers.get("authorization"));
    if (!token || !(await canPushRepo(token, this.d.cfg.repo, this.d.fetch))) return json({ error: "not found" }, 404);
    const gh = await this.getGh();
    if (!gh) return json({ error: "not configured" }, 503);
    let r: Awaited<ReturnType<Engine["resync"]>>;
    try {
      r = await this.engine.resync(gh);
    } catch {
      return json({ error: "sync failed" }, 502);
    }
    if (r.status === "limited") return json({ error: "rate limited", retry_after_s: r.retryAfterS }, 429, { "retry-after": String(r.retryAfterS) });
    if (r.status === "busy") return json({ error: "busy" }, 409);
    return json({ ok: true, resynced: true });
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
    // /setup は無認証。有効 (期限内) な state があれば上書きせず同じものを返す (第三者が開いても進行中の手順を壊せない。期限は延ばさない)。
    let saved = this.d.store.get<{ state: string; exp: number }>("meta", "setupState");
    if (!saved || this.d.now() > saved.exp) {
      saved = { state: randomToken(24), exp: this.d.now() + SETUP_TTL_MS };
      this.d.store.put("meta", "setupState", saved);
    }
    const state = saved.state;
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
    // state は /setup で発行したものだけを、期限内に限り受け付ける (他人が用意した code で上書きされない)。
    // /setup は同じ state を返すので第三者も state を知り得る。state は org 所有の App への変換に成功したときだけ消費する
    // (不正な code で callback を叩かれても、進行中の手順の state は失効しない)。
    if (!saved || this.d.now() > saved.exp || !safeEqual(state, saved.state)) return html("<p>Invalid or expired state. Open /setup again.</p>", 400);
    if (!/^[0-9a-f]{20,64}$/i.test(code)) return html("<p>Invalid code.</p>", 400);
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
    this.d.store.del("meta", "setupState");
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
      for (const k of ["log", "would_launch_now", "would_dispatch_pm", "last_error"]) delete s[k];
      return json(s);
    }
    if (!(await this.callerCanPush(req.headers.get("authorization")))) return json({ error: "unauthorized" }, 401);
    return json(s);
  }

  private async callerCanPush(h: string | null): Promise<boolean> {
    const token = bearerToken(h);
    if (!token) return false;
    const key = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(token)))).map((b) => b.toString(16).padStart(2, "0")).join("");
    const c = this.authCache.get(key);
    if (c && c.until > this.d.now()) return c.ok;
    const ok = await canPushRepo(token, this.d.cfg.repo, this.d.fetch);
    this.authCache.set(key, { ok, until: this.d.now() + 60_000 });
    return ok;
  }
}
