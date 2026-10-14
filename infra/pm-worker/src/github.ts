// GitHub REST クライアント (App の installation token を使う)。fetch は注入できる (テストでモックする)。
import { b64u, fromB64u } from "./crypto.ts";
import { parseRateHeaders, type RateInfo } from "./ratelimit.ts";

export type FetchFn = (input: string, init?: RequestInit) => Promise<Response>;

// エラーには応答本文を入れない (本文に秘密や自由文が入り得るため)。
export class GhError extends Error {
  readonly method: string;
  readonly path: string;
  readonly status: number;
  constructor(method: string, path: string, status: number) {
    super(`${method} ${path.split("?")[0]} -> ${status}`);
    this.method = method;
    this.path = path;
    this.status = status;
  }
}

const der = (tag: number, body: Uint8Array): Uint8Array => {
  const len = body.length;
  const lenBytes = len < 128 ? [len] : len < 256 ? [0x81, len] : [0x82, len >> 8, len & 255];
  return Uint8Array.from([tag, ...lenBytes, ...body]);
};

// GitHub が返す private key は PKCS#1 (BEGIN RSA PRIVATE KEY)。WebCrypto は PKCS#8 だけ読めるので包む。
export function pemToPkcs8(pem: string): Uint8Array {
  const m = /-----BEGIN (RSA )?PRIVATE KEY-----([\s\S]+?)-----END (RSA )?PRIVATE KEY-----/.exec(pem);
  if (!m) throw new Error("bad pem");
  const raw = Uint8Array.from(atob(m[2].replace(/\s+/g, "")), (c) => c.charCodeAt(0));
  if (!m[1]) return raw;
  const algId = Uint8Array.from([0x30, 0x0d, 0x06, 0x09, 0x2a, 0x86, 0x48, 0x86, 0xf7, 0x0d, 0x01, 0x01, 0x01, 0x05, 0x00]);
  const body = Uint8Array.from([0x02, 0x01, 0x00, ...algId, ...der(0x04, raw)]);
  return der(0x30, body);
}

export async function appJwt(appId: number | string, pem: string, nowSec: number): Promise<string> {
  const enc = new TextEncoder();
  const head = b64u(enc.encode(JSON.stringify({ alg: "RS256", typ: "JWT" })));
  const claims = b64u(enc.encode(JSON.stringify({ iat: nowSec - 60, exp: nowSec + 540, iss: String(appId) })));
  const key = await crypto.subtle.importKey("pkcs8", pemToPkcs8(pem), { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("RSASSA-PKCS1-v1_5", key, enc.encode(`${head}.${claims}`));
  return `${head}.${claims}.${b64u(sig)}`;
}

export { fromB64u };

export const DISPATCH_TYPES = ["oc-watchdog"] as const;
export type DispatchType = (typeof DISPATCH_TYPES)[number];

export interface GhResponse<T = any> {
  status: number;
  json: T;
}

export interface ListResult<T> {
  items: T[];
  truncated: boolean;
  pages: number;
}

export class Gh {
  remaining: number | null = null;
  calls = 0;
  private readonly f: FetchFn;
  private readonly token: () => Promise<string>;
  private readonly onRate?: (r: RateInfo) => void;
  readonly repo: string;
  constructor(f: FetchFn, token: () => Promise<string>, repo: string, onRate?: (r: RateInfo) => void) {
    this.f = f;
    this.token = token;
    this.repo = repo;
    this.onRate = onRate;
  }

  async req<T = any>(method: string, path: string, body?: unknown, okStatuses: number[] = []): Promise<GhResponse<T>> {
    const t = await this.token();
    const r = await this.f("https://api.github.com" + path, {
      method,
      headers: {
        authorization: `Bearer ${t}`,
        accept: "application/vnd.github+json",
        "x-github-api-version": "2022-11-28",
        "user-agent": "signature-studio-pm-worker",
        ...(body === undefined ? {} : { "content-type": "application/json" }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    this.calls++;
    // 成功・失敗を問わず全応答のヘッダを見る。ヘッダの無い応答では何も更新しない。
    const rate = parseRateHeaders(r.headers);
    if (rate) {
      if (rate.remaining !== undefined) this.remaining = rate.remaining;
      this.onRate?.(rate);
    }
    if (!r.ok && !okStatuses.includes(r.status)) {
      void r.body?.cancel();
      throw new GhError(method, path, r.status);
    }
    const json = r.status === 204 ? null : await r.json().catch(() => null);
    return { status: r.status, json: json as T };
  }

  // per_page=100 を page で辿る。maxPages で打ち切る (呼び出し側が上限を決める)。
  // stop は『この項目以降は窓の外』の判定 (一覧が窓の外へ向かって並んでいるときだけ使う)。最初に当たった項目より後ろは捨てて、そこで終える。
  // truncated は『上限で止めたが、まだ続きがある』。上限ちょうどで読み尽くしたときに誤判定しないよう、次の 1 ページを読んで確かめる。
  // pages は結果に使ったページ数 (確認のために読んだ次の 1 ページは数えない)。
  async list<T = any>(
    path: string,
    maxPages: number,
    pick: (j: any) => T[] = (j) => j,
    stop?: (item: T) => boolean,
  ): Promise<ListResult<T>> {
    const sep = path.includes("?") ? "&" : "?";
    const read = async (page: number): Promise<{ items: T[]; last: boolean }> => {
      const { json } = await this.req("GET", `${path}${sep}per_page=100&page=${page}`);
      let items = pick(json) ?? [];
      let last = items.length < 100;
      const at = stop ? items.findIndex(stop) : -1;
      if (at >= 0) {
        items = items.slice(0, at);
        last = true;
      }
      return { items, last };
    };
    const out: T[] = [];
    for (let page = 1; page <= maxPages; page++) {
      const r = await read(page);
      out.push(...r.items);
      if (r.last) return { items: out, truncated: false, pages: page };
    }
    const next = await read(maxPages + 1);
    return { items: out, truncated: next.items.length > 0, pages: maxPages };
  }

  comment(n: number, body: string) {
    return this.req("POST", `/repos/${this.repo}/issues/${n}/comments`, { body });
  }

  // Worker が送る repository_dispatch は oc-watchdog だけ。payload は event_type のみで、client_payload (自由な値) は付けない。
  // oc-fix は PR 番号・理由・素材名の client_payload が要り、検証と送信は Actions の watchdog.sh が行う。
  dispatch(eventType: DispatchType) {
    if (!DISPATCH_TYPES.includes(eventType)) throw new Error("dispatch type not allowed");
    return this.req("POST", `/repos/${this.repo}/dispatches`, { event_type: eventType });
  }
}

// installation token をメモリにキャッシュ (有効 60 分のうち 50 分使う)。
export class InstallationAuth {
  private tok: { v: string; until: number } | null = null;
  private readonly f: FetchFn;
  private readonly creds: () => Promise<{ appId: number | string; pem: string; installationId: number | null }>;
  private readonly now: () => number;
  private readonly onInstallation: (id: number) => void;
  constructor(
    f: FetchFn,
    creds: () => Promise<{ appId: number | string; pem: string; installationId: number | null }>,
    now: () => number,
    onInstallation: (id: number) => void,
  ) {
    this.f = f;
    this.creds = creds;
    this.now = now;
    this.onInstallation = onInstallation;
  }

  // 直近に発行した token (ログ・status から取り除く対象を知るため)。期限切れでも返す。無ければ null。
  current(): string | null {
    return this.tok?.v ?? null;
  }

  async token(): Promise<string> {
    if (this.tok && this.now() < this.tok.until) return this.tok.v;
    const c = await this.creds();
    const jwt = await appJwt(c.appId, c.pem, Math.floor(this.now() / 1000));
    const h = { authorization: `Bearer ${jwt}`, accept: "application/vnd.github+json", "user-agent": "signature-studio-pm-worker" };
    let id = c.installationId;
    if (!id) {
      const r = await this.f("https://api.github.com/app/installations?per_page=100", { headers: h });
      if (!r.ok) throw new GhError("GET", "/app/installations", r.status);
      const list = (await r.json()) as Array<{ id: number }>;
      if (list.length !== 1) throw new Error(`installations: expected 1, got ${list.length}`);
      id = list[0].id;
      this.onInstallation(id);
    }
    const r = await this.f(`https://api.github.com/app/installations/${id}/access_tokens`, { method: "POST", headers: h });
    if (!r.ok) throw new GhError("POST", "/app/installations/{id}/access_tokens", r.status);
    const j = (await r.json()) as { token: string };
    this.tok = { v: j.token, until: this.now() + 50 * 60_000 };
    return j.token;
  }
}
