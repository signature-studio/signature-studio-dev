/**
 * help_viewer.ts — FL の Help (Help/index_offline.html ほか) を sandbox iframe に出すための純ロジック (ST-T8 #118)。DOM 非依存 (Node でテスト可)。
 * 根拠 (FLEngine 静的解析・Help 実ファイル実測): tools/startup/helpviewer/REPORT.md
 *   - FL は HTML を解釈せず Help\index_offline.html や Help\html\<topic> のパスを組み立てて開く。WebView2 は LoadLibraryW=NULL で無効 (GATES G13)。
 *   - HTML は利用者の FL インストールから実行時供給 (HelpFiles)。リポジトリ・配信物には同梱しない (mcp_panel.ts と同じ BYO 方針)。
 *   - 外部通信なし: 外部リンクは辿らない。FL の error-offline.html は読まず、本ファイルの自前ページ (buildNoticeSrcdoc) に差し替える。
 * セキュリティは iframe sandbox (allow-same-origin なし) + CSP (default-src 'none') で担保し、HTML の書換えは表示を成立させるためのもの。
 */

export const FL_INSTALL_ROOT = "C:/Program Files/Image-Line/FL Studio 2026";
export const HELP_INDEX = "index_offline.html";
const ERROR_OFFLINE = ["system", "internet", "error-offline.html"];

export type HelpTarget =
  | { kind: "help"; path: string; fragment: string }
  | { kind: "offline-notice" }
  | { kind: "external"; url: string }
  | { kind: "unsupported"; reason: string };

export type HelpFiles = { read(path: string): Promise<Uint8Array | null> };

export type NoticeKind = "offline" | "not-found" | "no-files" | "external-blocked" | "unsupported";

const unsupported = (reason: string): HelpTarget => ({ kind: "unsupported", reason });

/** セグメント列を正規化。`.`/`..` を解決し、ルートを越える・空の名前・NUL・バックスラッシュ・コロンを含むものは null。 */
function normalizeSegments(segs: string[]): string[] | null {
  const out: string[] = [];
  for (const s of segs) {
    if (s === "" || s === ".") continue;
    if (s === "..") {
      if (out.pop() === undefined) return null;
      continue;
    }
    if (/[\0\\:*?"<>|]/.test(s)) return null;
    out.push(s);
  }
  return out;
}

function splitFragment(s: string): { path: string; fragment: string } {
  const h = s.indexOf("#");
  const frag = h >= 0 ? s.slice(h + 1) : "";
  const noFrag = h >= 0 ? s.slice(0, h) : s;
  const q = noFrag.indexOf("?");
  return { path: q >= 0 ? noFrag.slice(0, q) : noFrag, fragment: frag };
}

function safeDecode(s: string): string | null {
  try {
    return decodeURIComponent(s);
  } catch {
    return null;
  }
}

const WIN_DRIVE = /^[a-zA-Z]:[\\/]/;
const SCHEME = /^([a-zA-Z][a-zA-Z0-9+.-]*):/;

/** `C:\a\b` → ["c:", "a", "b"] (ドライブ文字は小文字化、残りは normalizeSegments)。不正なら null */
function winSegments(p: string): string[] | null {
  const parts = p.replace(/\\/g, "/").split("/");
  const drive = parts.shift();
  if (drive === undefined || !/^[a-zA-Z]:$/.test(drive)) return null;
  const rest = normalizeSegments(parts);
  return rest ? [drive.toLowerCase(), ...rest] : null;
}

function underInstallRoot(absPath: string, installRoot: string): HelpTarget {
  const { path, fragment } = splitFragment(absPath);
  const segs = winSegments(path);
  const root = winSegments(installRoot);
  if (!segs || !root) return unsupported("invalid path");
  if (segs.length < root.length || root.some((r, i) => r.toLowerCase() !== segs[i]!.toLowerCase())) return unsupported("outside the FL install dir");
  const rel = segs.slice(root.length);
  if (rel.length === 3 && rel.every((s, i) => s.toLowerCase() === ERROR_OFFLINE[i])) return { kind: "offline-notice" };
  if (rel[0]?.toLowerCase() !== "help") return unsupported("not under Help/");
  const inner = rel.slice(1);
  return { kind: "help", path: inner.length ? inner.join("/") : HELP_INDEX, fragment };
}

/**
 * FL (または ShellExecuteW) から渡された絶対ターゲットを分類する。
 * 受理: Windows 絶対パス (`C:\Program Files\...\Help\x.html#f`)、`file:///C:/...`、http(s) URL。
 * 生の Windows パスは `#` 以降をフラグメントとして扱う (% は復号しない)。file: URL は % を復号する。
 */
export function classifyTarget(target: string, installRoot: string = FL_INSTALL_ROOT): HelpTarget {
  const t = target.trim();
  if (!t) return unsupported("empty target");
  if (t.includes("\0")) return unsupported("NUL in target");
  if (WIN_DRIVE.test(t)) return underInstallRoot(t, installRoot);
  const m = SCHEME.exec(t);
  if (!m) return unsupported("relative target without a base page");
  const scheme = m[1]!.toLowerCase();
  if (scheme === "http" || scheme === "https") return { kind: "external", url: t };
  if (scheme !== "file") return unsupported(`scheme ${scheme}:`);
  const rest = t.slice(5).replace(/^\/\//, "");
  const slash = rest.indexOf("/");
  const host = slash >= 0 ? rest.slice(0, slash) : rest;
  if (host !== "" && host.toLowerCase() !== "localhost") return unsupported("file: URL with a host (UNC)");
  const body = slash >= 0 ? rest.slice(slash) : "";
  const { path, fragment } = splitFragment(body);
  const dec = safeDecode(path);
  if (dec === null) return unsupported("malformed percent-encoding");
  return underInstallRoot(dec.replace(/^\/(?=[a-zA-Z]:)/, "") + (fragment ? `#${fragment}` : ""), installRoot);
}

/** ページ内リンク (相対 href) を、現在ページ (Help/ 相対パス) を基準に解決する。 */
export function resolveLink(basePath: string, href: string): HelpTarget {
  const h = href.trim();
  if (!h) return unsupported("empty href");
  if (h.includes("\0")) return unsupported("NUL in href");
  if (h.startsWith("//")) return { kind: "external", url: `https:${h}` };
  if (WIN_DRIVE.test(h) || SCHEME.test(h)) return classifyTarget(h);
  const { path, fragment } = splitFragment(h);
  if (path === "") return { kind: "help", path: basePath, fragment };
  const dec = safeDecode(path);
  if (dec === null) return unsupported("malformed percent-encoding");
  const p = dec.replace(/\\/g, "/");
  const dir = basePath.split("/").slice(0, -1);
  const segs = normalizeSegments(p.startsWith("/") ? p.split("/") : [...dir, ...p.split("/")]);
  if (!segs) return unsupported("link escapes Help/");
  return { kind: "help", path: segs.length ? segs.join("/") : HELP_INDEX, fragment };
}

export type ShellExecuteDecision =
  | { action: "help"; target: Extract<HelpTarget, { kind: "help" | "offline-notice" }>; result: 33 }
  | { action: "external-noop"; url: string; result: 33 }
  | { action: "pass" };

/**
 * ShellExecuteW(NULL, verb, file, ...) の振り分け。FL は verb=NULL で呼ぶ (0x10bdd8e: 第 2 引数 xor edx,edx) ので NULL/""/"open" を open として扱う。
 * stub_plan §5-B と同じく http(s) は 33 (成功) を返す no-op。Help 配下は viewer へ。その他は他の shell hook に任せる (pass)。
 */
export function classifyShellExecute(verb: string | null, file: string, installRoot: string = FL_INSTALL_ROOT): ShellExecuteDecision {
  const v = (verb ?? "").toLowerCase();
  if (v !== "" && v !== "open") return { action: "pass" };
  const t = classifyTarget(file, installRoot);
  if (t.kind === "help" || t.kind === "offline-notice") return { action: "help", target: t, result: 33 };
  if (t.kind === "external") return { action: "external-noop", url: t.url, result: 33 };
  return { action: "pass" };
}

// ---------------------------------------------------------------------------------------------
// 供給元 (HelpFiles)
// ---------------------------------------------------------------------------------------------

/** パス → バイト列の Map から HelpFiles を作る。大文字小文字は Windows に合わせて、完全一致が無ければ無視して引く。 */
export function filesFromMap(map: ReadonlyMap<string, Uint8Array>): HelpFiles {
  const folded = new Map<string, Uint8Array>();
  for (const [k, v] of map) folded.set(k.toLowerCase(), v);
  return { read: async (p) => map.get(p) ?? folded.get(p.toLowerCase()) ?? null };
}

// ---------------------------------------------------------------------------------------------
// HTML の準備
// ---------------------------------------------------------------------------------------------

export type PrepareOptions = {
  maxResourceBytes?: number;
  maxTotalBytes?: number;
  /** nonce / token を決定的にしたいテスト用 */
  rand?: () => string;
  /** 読込後にスクロールするフラグメント (`#` なし) */
  fragment?: string;
};

export type PageStats = {
  inlinedResources: number;
  missingResources: string[];
  skippedLarge: string[];
  scriptsRemoved: number;
  embedsRemoved: number;
  externalRefsBlocked: number;
  bytes: number;
};

export type PreparedPage = {
  pagePath: string;
  title: string;
  srcdoc: string;
  token: string;
  /** `<meta http-equiv=refresh>` の遷移先 (生の href)。呼び出し側が resolveLink して辿る */
  refresh: string | null;
  stats: PageStats;
};

const MIME: Record<string, string> = {
  png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg", gif: "image/gif", svg: "image/svg+xml", webp: "image/webp", bmp: "image/bmp", ico: "image/x-icon",
  woff: "font/woff", woff2: "font/woff2", ttf: "font/ttf", otf: "font/otf", eot: "application/vnd.ms-fontobject",
};

const defaultRand = (): string => {
  const b = new Uint8Array(16);
  crypto.getRandomValues(b);
  return Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
};

export function toBase64(bytes: Uint8Array): string {
  let s = "";
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(s);
}

const ENT: Record<string, string> = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: "\u00a0" };
export function decodeEntities(s: string): string {
  return s.replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (m, e: string) => {
    if (e[0] === "#") {
      const n = e[1] === "x" || e[1] === "X" ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10);
      return n > 0 && n <= 0x10ffff ? String.fromCodePoint(n) : m;
    }
    return ENT[e.toLowerCase()] ?? m;
  });
}

const escAttr = (s: string): string => s.replace(/&(?![a-z#][a-z0-9]*;)/gi, "&amp;").replace(/"/g, "&quot;");

function decodeText(bytes: Uint8Array): string {
  const head = new TextDecoder("latin1").decode(bytes.subarray(0, 2048));
  const m = /<meta[^>]+charset\s*=\s*["']?\s*([a-z0-9_-]+)/i.exec(head);
  if (m) {
    try {
      return new TextDecoder(m[1]!).decode(bytes);
    } catch {
      /* 未知のラベルは UTF-8 で読む */
    }
  }
  return new TextDecoder("utf-8").decode(bytes);
}

type Attr = { name: string; value: string | null };
const ATTR_RE = /([^\s"'<>/=]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?/g;
function parseAttrs(s: string): Attr[] {
  const out: Attr[] = [];
  ATTR_RE.lastIndex = 0;
  for (let m = ATTR_RE.exec(s); m; m = ATTR_RE.exec(s)) out.push({ name: m[1]!.toLowerCase(), value: m[2] ?? m[3] ?? m[4] ?? null });
  return out;
}
const getAttr = (attrs: Attr[], n: string): string | null => attrs.find((a) => a.name === n)?.value ?? null;
const buildTag = (name: string, attrs: Attr[], selfClose: boolean): string =>
  `<${name}${attrs.map((a) => (a.value === null ? ` ${a.name}` : ` ${a.name}="${escAttr(a.value)}"`)).join("")}${selfClose ? " /" : ""}>`;

const TAG_RE = /<!--[\s\S]*?-->|<!doctype[^>]*>|<(\/?)([a-zA-Z][a-zA-Z0-9:-]*)((?:"[^"]*"|'[^']*'|[^>"'])*)>/gi;
const DROP_WITH_BODY = new Set(["script", "iframe", "frame", "object", "applet", "noembed"]);
const DROP_VOID = new Set(["embed", "base", "param"]);

type Ctx = {
  files: HelpFiles;
  stats: PageStats;
  maxRes: number;
  maxTotal: number;
  used: number;
};

async function inlineResource(ctx: Ctx, fromPath: string, ref: string): Promise<string | null> {
  const t = resolveLink(fromPath, decodeEntities(ref));
  if (t.kind === "external") {
    ctx.stats.externalRefsBlocked++;
    return null;
  }
  if (t.kind !== "help") return null;
  const bytes = await ctx.files.read(t.path);
  if (!bytes) {
    ctx.stats.missingResources.push(t.path);
    return null;
  }
  if (bytes.length > ctx.maxRes || ctx.used + bytes.length > ctx.maxTotal) {
    ctx.stats.skippedLarge.push(t.path);
    return null;
  }
  ctx.used += bytes.length;
  ctx.stats.inlinedResources++;
  const ext = t.path.slice(t.path.lastIndexOf(".") + 1).toLowerCase();
  return `data:${MIME[ext] ?? "application/octet-stream"};base64,${toBase64(bytes)}`;
}

const CSS_URL_RE = /url\(\s*(?:"([^"]*)"|'([^']*)'|([^)\s]*))\s*\)/gi;
async function rewriteCss(ctx: Ctx, css: string, cssPath: string): Promise<string> {
  const parts: string[] = [];
  let last = 0;
  const src = css.replace(/@import[^;]*;/gi, "/* import removed */");
  CSS_URL_RE.lastIndex = 0;
  for (let m = CSS_URL_RE.exec(src); m; m = CSS_URL_RE.exec(src)) {
    const ref = m[1] ?? m[2] ?? m[3] ?? "";
    parts.push(src.slice(last, m.index));
    last = m.index + m[0].length;
    const after = src.slice(last, last + 40);
    if (/^data:/i.test(ref)) parts.push(m[0]);
    else if (ref.startsWith("#")) parts.push(m[0]);
    else if (/\.eot(?:[?#]|$)/i.test(ref) || /^\s*format\(\s*["']?svg/i.test(after)) parts.push('url("data:,")'); // 旧式フォント (EOT / SVG フォント) は埋め込まない
    else parts.push(`url("${(await inlineResource(ctx, cssPath, ref)) ?? "data:,"}")`);
  }
  parts.push(src.slice(last));
  return parts.join("");
}

function nameOfTarget(path: string): string {
  return path.slice(path.lastIndexOf("/") + 1);
}

const CSP = (nonce: string) =>
  `default-src 'none'; img-src data:; style-src 'unsafe-inline'; font-src data:; script-src 'nonce-${nonce}'; base-uri 'none'; form-action 'none'; frame-src 'none'; connect-src 'none'; media-src 'none'; object-src 'none'`;

const jsStr = (s: string): string => JSON.stringify(s).replace(/</g, "\\u003c").replace(/\u2028/g, "\\u2028").replace(/\u2029/g, "\\u2029");

function bridgeScript(token: string, nonce: string, fragment: string): string {
  const js =
    `(function(){var T=${jsStr(token)};function go(h){var id=h;try{id=decodeURIComponent(h)}catch(x){}var el=document.getElementById(id)||document.getElementsByName(id)[0];if(el&&el.scrollIntoView)el.scrollIntoView()}` +
    (fragment ? `window.addEventListener("load",function(){go(${jsStr(fragment)})});` : "") +
    `document.addEventListener("click",function(e){var n=e.target;while(n&&!(n.nodeType===1&&n.tagName==="A"&&n.hasAttribute("href")))n=n.parentNode;` +
    `if(!n)return;e.preventDefault();var h=n.getAttribute("href");if(h.charAt(0)==="#"){go(h.slice(1));return}` +
    `parent.postMessage({flHelp:T,href:h},"*")},true)})();`;
  return `<script nonce="${nonce}">${js}</script>`;
}

/**
 * Help ページを読み、sandbox iframe の srcdoc にできる自己完結 HTML へ書き換える。
 *  - script / iframe / object / embed / base / form 系を除去 (CSP でも止まるが二重に落とす)、on* 属性と target を除去
 *  - 相対 CSS / 画像 / フォントを同一 Help 内から data: に埋込み (見つからないものは stats.missingResources)
 *  - 外部 URL の参照は除去して件数を数える。リンクのクリックは bridge が親へ postMessage し、親が resolveLink で辿る
 */
export async function prepareHelpPage(files: HelpFiles, pagePath: string, opts: PrepareOptions = {}): Promise<PreparedPage | null> {
  const bytes = await files.read(pagePath);
  if (!bytes) return null;
  const rand = opts.rand ?? defaultRand;
  const nonce = rand();
  const token = rand();
  const ctx: Ctx = {
    files,
    stats: { inlinedResources: 0, missingResources: [], skippedLarge: [], scriptsRemoved: 0, embedsRemoved: 0, externalRefsBlocked: 0, bytes: 0 },
    maxRes: opts.maxResourceBytes ?? 2 * 1024 * 1024,
    maxTotal: opts.maxTotalBytes ?? 24 * 1024 * 1024,
    used: 0,
  };
  const html = decodeText(bytes);
  const out: string[] = [];
  let refresh: string | null = null;
  let title = "";
  let last = 0;
  TAG_RE.lastIndex = 0;
  const skipTo = (from: number, tag: string): number => {
    const close = new RegExp(`</${tag}\\s*>`, "i");
    close.lastIndex = 0;
    const m = close.exec(html.slice(from));
    return m ? from + m.index + m[0].length : html.length;
  };
  for (let m = TAG_RE.exec(html); m; m = TAG_RE.exec(html)) {
    out.push(html.slice(last, m.index));
    last = m.index + m[0].length;
    if (m[0].startsWith("<!--") || /^<!doctype/i.test(m[0])) continue;
    const closing = m[1] === "/";
    const name = m[2]!.toLowerCase();
    const rawAttrs = m[3]!;
    if (closing) {
      if (!DROP_WITH_BODY.has(name) && !DROP_VOID.has(name) && name !== "form") out.push(m[0]);
      continue;
    }
    if (DROP_WITH_BODY.has(name)) {
      if (name === "script") ctx.stats.scriptsRemoved++;
      else ctx.stats.embedsRemoved++;
      if (!/\/\s*$/.test(rawAttrs)) {
        last = skipTo(last, name);
        TAG_RE.lastIndex = last;
      }
      continue;
    }
    if (DROP_VOID.has(name)) {
      ctx.stats.embedsRemoved++;
      continue;
    }
    if (name === "form") continue;
    const attrs = parseAttrs(rawAttrs);
    if (name === "title") {
      const e = html.indexOf("</", last);
      title = decodeEntities(html.slice(last, e < 0 ? last : e)).trim();
    }
    if (name === "meta") {
      const he = (getAttr(attrs, "http-equiv") ?? "").toLowerCase();
      if (he === "refresh") {
        const r = /url\s*=\s*["']?([^"';]+)/i.exec(decodeEntities(getAttr(attrs, "content") ?? ""));
        if (r && refresh === null) refresh = r[1]!.trim();
        continue;
      }
      if (he === "content-security-policy" || he === "set-cookie") continue;
      out.push(m[0]);
      continue;
    }
    if (name === "link") {
      const rel = (getAttr(attrs, "rel") ?? "").toLowerCase();
      const href = getAttr(attrs, "href");
      if (!/\bstylesheet\b/.test(rel) || href === null) continue;
      const t = resolveLink(pagePath, decodeEntities(href));
      if (t.kind === "external") {
        ctx.stats.externalRefsBlocked++;
        continue;
      }
      if (t.kind !== "help") continue;
      const cssBytes = await files.read(t.path);
      if (!cssBytes) {
        ctx.stats.missingResources.push(t.path);
        continue;
      }
      ctx.stats.inlinedResources++;
      out.push(`<style data-src="${escAttr(nameOfTarget(t.path))}">${await rewriteCss(ctx, decodeText(cssBytes), t.path)}</style>`);
      continue;
    }
    if (name === "style") {
      const e = skipTo(last, "style");
      const inner = html.slice(last, e).replace(/<\/style\s*>$/i, "");
      out.push(`<style>${await rewriteCss(ctx, inner, pagePath)}</style>`);
      last = e;
      TAG_RE.lastIndex = last;
      continue;
    }
    let changed = false;
    const next: Attr[] = [];
    for (const a of attrs) {
      if (a.name.startsWith("on") || a.name === "srcdoc" || a.name === "background" || a.name === "srcset" || a.name === "ping") {
        changed = true;
        continue;
      }
      if (name === "a" && (a.name === "target" || a.name === "download")) {
        changed = true;
        continue;
      }
      if (a.name === "style" && a.value && /url\(/i.test(a.value)) {
        next.push({ name: "style", value: await rewriteCss(ctx, a.value, pagePath) });
        changed = true;
        continue;
      }
      if ((name === "img" || name === "input") && a.name === "src" && a.value !== null) {
        const d = await inlineResource(ctx, pagePath, a.value);
        if (d) next.push({ name: "src", value: d });
        changed = true;
        continue;
      }
      if ((name === "video" || name === "audio" || name === "source" || name === "track") && (a.name === "src" || a.name === "poster")) {
        changed = true;
        continue;
      }
      if (name === "a" && a.name === "href" && a.value !== null) {
        const t = resolveLink(pagePath, decodeEntities(a.value));
        if (t.kind === "external") ctx.stats.externalRefsBlocked++;
      }
      next.push(a);
    }
    if (changed) out.push(buildTag(m[2]!, next, /\/\s*$/.test(rawAttrs)));
    else out.push(m[0]);
  }
  out.push(html.slice(last));
  const srcdoc =
    `<!DOCTYPE html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${CSP(nonce)}"></head><body>` +
    out.join("") +
    bridgeScript(token, nonce, opts.fragment ?? "") +
    `</body></html>`;
  ctx.stats.bytes = srcdoc.length;
  return { pagePath, title, srcdoc, token, refresh, stats: ctx.stats };
}

// ---------------------------------------------------------------------------------------------
// 自前ページ (FL の error-offline.html の差替え)
// ---------------------------------------------------------------------------------------------

const NOTICE_TEXT: Record<NoticeKind, { en: [string, string]; ja: [string, string] }> = {
  offline: {
    en: ["You're offline", "The browser edition makes no external connections. FL Cloud and online manuals are unavailable."],
    ja: ["オフラインです", "ブラウザ版は外部通信を行いません。FL Cloud やオンラインのマニュアルは利用できません。"],
  },
  "not-found": {
    en: ["Page not found", "This Help page is not in the supplied Help folder."],
    ja: ["ページが見つかりません", "このヘルプページは供給された Help フォルダにありません。"],
  },
  "no-files": {
    en: ["Help files are not supplied", "Choose the Help folder of your own FL Studio installation. It is not bundled with this site."],
    ja: ["ヘルプのファイルが未供給です", "お手元の FL Studio の Help フォルダを選択してください。このサイトには同梱されていません。"],
  },
  "external-blocked": {
    en: ["External link blocked", "The browser edition does not open external sites from Help."],
    ja: ["外部リンクは開きません", "ブラウザ版はヘルプから外部サイトを開きません。"],
  },
  unsupported: {
    en: ["Cannot show this target", "The requested location is outside the supported Help files."],
    ja: ["この場所は表示できません", "要求された場所は対応する Help ファイルの範囲外です。"],
  },
};

const escHtml = (s: string): string => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

/** FL 由来物を一切含まない通知ページ (script なし・CSP 全遮断)。detail は表示用の短い文字列 (エスケープ済みで出す)。 */
export function buildNoticeSrcdoc(kind: NoticeKind, lang: "en" | "ja" = "en", detail = ""): string {
  const [h, p] = NOTICE_TEXT[kind][lang];
  return (
    `<!DOCTYPE html><html lang="${lang}"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">` +
    `<style>body{margin:0;padding:48px 24px;background:#142028;color:#cdcdcd;font:14px/1.5 system-ui,sans-serif;text-align:center}` +
    `.box{max-width:360px;margin:auto;padding:32px 20px;background:#2b3a44;border-radius:6px}h1{font-size:20px;margin:0 0 16px}p{margin:0 0 8px;text-align:left}code{word-break:break-all;color:#9ab}</style></head>` +
    `<body><div class="box"><h1>${escHtml(h)}</h1><p>${escHtml(p)}</p>${detail ? `<p><code>${escHtml(detail)}</code></p>` : ""}</div></body></html>`
  );
}
