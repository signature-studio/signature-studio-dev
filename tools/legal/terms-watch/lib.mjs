// 各社規約の差分監視 (LGL-5, #88) のコア。
// 取得 → テキスト化 → 範囲切出し → 正規化 → SHA-256 → 台帳比較。
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { closeSync, existsSync, mkdirSync, mkdtempSync, openSync, readdirSync, readFileSync, readSync, rmSync, statSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";

export class SourceError extends Error {
  constructor(message, kind = "error") {
    super(message);
    this.kind = kind; // "error" = 取得/解釈失敗, "skip" = 素材が無く検査できない
  }
}

const NAMED = {
  amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " ", copy: "©", reg: "®", trade: "™", sect: "§", deg: "°", middot: "·", bull: "•",
  lsquo: "‘", rsquo: "’", sbquo: "‚", ldquo: "“", rdquo: "”", bdquo: "„", ndash: "–", mdash: "—", hellip: "…", laquo: "«", raquo: "»",
  euro: "€", pound: "£", yen: "¥", cent: "¢", times: "×", divide: "÷", para: "¶", shy: "", zwj: "", zwnj: "",
  eacute: "é", egrave: "è", agrave: "à", aacute: "á", uuml: "ü", ouml: "ö", auml: "ä", szlig: "ß", ccedil: "ç", ntilde: "ñ", oacute: "ó", iacute: "í",
  Eacute: "É", Uuml: "Ü", Ouml: "Ö", Auml: "Ä",
};

export function decodeEntities(s) {
  return s.replace(/&(#x[0-9a-f]+|#\d+|[a-z][a-z0-9]*);/gi, (m, e) => {
    if (e[0] === "#") {
      const cp = e[1].toLowerCase() === "x" ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10);
      return Number.isFinite(cp) && cp > 0 && cp <= 0x10ffff ? String.fromCodePoint(cp) : m;
    }
    return e in NAMED ? NAMED[e] : m;
  });
}

// ブロック要素の境界だけ改行にする。インライン要素 (span/a/b 等) は空白を挟まない ("A<span>ny</span>" は "Any")
const HTML_BLOCK_TAG = /<\/?(?:p|div|li|h[1-6]|tr|td|th|section|table|thead|tbody|tfoot|caption|ul|ol|dl|dt|dd|br|hr|blockquote|pre|article|main|title|option|select)\b[^>]*>/gi;

// opts.stripChrome: Web ページのナビ・フッタ等 (nav/header/footer/aside/form) を落とす
export function htmlToText(html, { stripChrome = false } = {}) {
  let s = html.replace(/<!--[\s\S]*?-->/g, " ");
  s = s.replace(/<(script|style|noscript|svg|template|head)\b[\s\S]*?<\/\1\s*>/gi, (m, t) => (t.toLowerCase() === "head" ? (m.match(/<title\b[^>]*>[\s\S]*?<\/title\s*>/i)?.[0] ?? "\n") : "\n"));
  if (stripChrome) s = s.replace(/<(footer|nav|header|aside|form)\b[\s\S]*?<\/\1\s*>/gi, "\n");
  s = s.replace(HTML_BLOCK_TAG, "\n");
  s = s.replace(/<[^>]+>/g, "");
  return decodeEntities(s);
}

const RTF_DEST_SKIP = new Set([
  "fonttbl", "colortbl", "stylesheet", "info", "listtable", "listoverridetable", "pict", "header", "headerl", "headerr", "headerf", "footer", "footerl",
  "footerr", "footerf", "footnote", "generator", "themedata", "colorschememapping", "latentstyles", "datastore", "rsidtbl", "fldinst", "xmlnstbl", "object",
  "filetbl", "revtbl", "pgptbl", "mmathPr", "wgrffmtfilter", "private",
]);
const RTF_SYM = { bullet: "•", endash: "–", emdash: "—", lquote: "‘", rquote: "’", ldblquote: "“", rdblquote: "”", emspace: " ", enspace: " ", qmspace: " ", tab: "\t" };
const cp1252 = new TextDecoder("windows-1252");

// 最小の RTF → テキスト。\'xx (cp1252)・\uN・段落・リスト番号 (\listtext) を保持し、フォント表等の destination は捨てる
export function rtfToText(rtf) {
  const out = [];
  const stack = [];
  let skip = false;
  let uc = 1;
  let ucSkip = 0;
  const n = rtf.length;
  for (let i = 0; i < n; ) {
    const c = rtf[i];
    if (ucSkip > 0 && c !== "\\" && c !== "{" && c !== "}") {
      if (c !== "\r" && c !== "\n") ucSkip--;
      i++;
      continue;
    }
    if (c === "{") { stack.push([skip, uc]); i++; continue; }
    if (c === "}") { [skip, uc] = stack.pop() ?? [false, 1]; ucSkip = 0; i++; continue; }
    if (c === "\r" || c === "\n") { i++; continue; }
    if (c !== "\\") { if (!skip) out.push(c); i++; continue; }
    i++;
    const d = rtf[i];
    if (d === undefined) break;
    if (d === "'") {
      const byte = parseInt(rtf.slice(i + 1, i + 3), 16);
      i += 3;
      if (ucSkip > 0) { ucSkip--; continue; }
      if (!skip && Number.isFinite(byte)) out.push(cp1252.decode(Uint8Array.of(byte)));
      continue;
    }
    if (!/[a-zA-Z]/.test(d)) {
      i++;
      if (d === "*") skip = true;
      else if (d === "\\" || d === "{" || d === "}") { if (!skip) out.push(d); }
      else if (d === "~") { if (!skip) out.push(" "); }
      else if (d === "_") { if (!skip) out.push("-"); }
      else if (d === "\n" || d === "\r") { if (!skip) out.push("\n"); }
      continue;
    }
    let j = i;
    while (j < n && /[a-zA-Z]/.test(rtf[j])) j++;
    const word = rtf.slice(i, j);
    let k = j;
    if (rtf[k] === "-") k++;
    while (k < n && /\d/.test(rtf[k])) k++;
    const param = k > j ? parseInt(rtf.slice(j, k), 10) : null;
    i = rtf[k] === " " ? k + 1 : k;
    if (RTF_DEST_SKIP.has(word)) { skip = true; continue; }
    if (skip) continue;
    if (word === "par" || word === "line" || word === "sect" || word === "page") out.push("\n");
    else if (word === "uc" && param !== null) uc = param;
    else if (word === "u" && param !== null) { out.push(String.fromCharCode(param < 0 ? param + 65536 : param)); ucSkip = uc; }
    else if (word in RTF_SYM) out.push(RTF_SYM[word]);
  }
  return out.join("");
}

// 空白・符号化差の除去。大文字小文字は保持する (改定として検出したいため)。
export function normalizeText(s) {
  return s
    .normalize("NFKC")
    .replace(/[\u200B-\u200D\u2060\uFEFF\u00AD]/g, "")
    .replace(/[\u2018\u2019\u201A\u201B\u02BC\u2032]/g, "'")
    .replace(/[\u201C-\u201F\u2033]/g, '"')
    .replace(/[\u2010-\u2015\u2212]/g, "-")
    .replace(/\s+/g, " ")
    .trim();
}

export const sha256 = (data) => createHash("sha256").update(data).digest("hex");

// 行構造を残したテキストから start〜end を切り出す。start が無ければ SourceError。
export function extractSection(text, { start, end, endMode = "first", endInclusive = false } = {}) {
  let from = 0;
  if (start) {
    const m = new RegExp(start, "m").exec(text);
    if (!m) throw new SourceError(`開始マーカ /${start}/ が見つからない (ページ構造が変わった可能性)`);
    from = m.index;
  }
  let to = text.length;
  if (end) {
    const re = new RegExp(end, "gm");
    re.lastIndex = from + (start ? 1 : 0);
    let m = re.exec(text);
    if (!m) throw new SourceError(`終了マーカ /${end}/ が見つからない (ページ構造が変わった可能性)`);
    if (endMode === "last") for (let x = m; x; x = re.exec(text)) m = x;
    to = endInclusive ? m.index + m[0].length : m.index;
  }
  return text.slice(from, to);
}

function sanity(src, norm) {
  const min = src.minChars ?? 2000;
  if (norm.length < min) throw new SourceError(`正規化後 ${norm.length} 文字 < minChars ${min} (エラーページ/切出し失敗の疑い)`);
  for (const p of src.mustContain ?? []) {
    if (!norm.toLowerCase().includes(p.toLowerCase())) throw new SourceError(`必須語句 "${p}" が無い (別文書/エラーページの疑い)`);
  }
}

function versionLabel(src, text) {
  if (!src.version) return null;
  const m = new RegExp(src.version, "i").exec(text);
  return m ? (m[1] ?? m[0]).trim() : null;
}

export function analyze(src, rawText) {
  const section = src.start || src.end ? extractSection(rawText, src) : rawText;
  const text = normalizeText(section);
  sanity(src, text);
  return { text, sha256: sha256(text), chars: text.length, version: versionLabel(src, text) };
}

const BROWSER_HEADERS = {
  "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
  accept: "text/html,application/xhtml+xml,application/pdf,*/*;q=0.8",
  "accept-language": "en-US,en;q=0.9",
};

export async function fetchBytes(url, { fetchImpl = fetch, retries = 2, timeoutMs = 30000 } = {}) {
  let last;
  for (let a = 0; a <= retries; a++) {
    try {
      const res = await fetchImpl(url, { headers: BROWSER_HEADERS, redirect: "follow", signal: AbortSignal.timeout(timeoutMs) });
      if (res.status >= 500 && a < retries) { last = new Error(`HTTP ${res.status}`); await new Promise((r) => setTimeout(r, 1000 * (a + 1))); continue; }
      if (res.status !== 200) throw new SourceError(`HTTP ${res.status} ${url}`);
      return { bytes: Buffer.from(await res.arrayBuffer()), contentType: res.headers.get("content-type") ?? "", finalUrl: res.url || url };
    } catch (e) {
      if (e instanceof SourceError) throw e;
      last = e;
      if (a < retries) await new Promise((r) => setTimeout(r, 1000 * (a + 1)));
    }
  }
  throw new SourceError(`取得失敗 ${url}: ${last?.message ?? last}`);
}

export function decodeBody(bytes, contentType = "") {
  let cs = /charset=([\w-]+)/i.exec(contentType)?.[1];
  if (!cs) cs = /<meta[^>]+charset=["']?([\w-]+)/i.exec(bytes.subarray(0, 4096).toString("latin1"))?.[1];
  try {
    return new TextDecoder(cs ?? "utf-8").decode(bytes);
  } catch {
    return new TextDecoder("utf-8").decode(bytes);
  }
}

const PDF_PY = path.join(import.meta.dirname, "pdf_text.py");
export const PYPDF_PIN = "pypdf==5.9.0";
export function pdfToText(bytes) {
  const dir = mkdtempSync(path.join(process.env.RUNNER_TEMP ?? os.tmpdir(), "terms-pdf-"));
  try {
    const f = path.join(dir, "in.pdf");
    writeFileSync(f, bytes);
    const r = spawnSync("uv", ["run", "--quiet", "--with", PYPDF_PIN, "python", PDF_PY, f], { encoding: "utf8", maxBuffer: 64 << 20 });
    if (r.error) throw new SourceError(`PDF 抽出に uv が必要: ${r.error.message}`);
    if (r.status !== 0) throw new SourceError(`PDF 抽出失敗 (exit ${r.status}): ${(r.stderr || "").trim().slice(-300)}`);
    return r.stdout;
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

// FL インストーラ抽出物 (FL_WIN64_DIR) から、内容署名で文書を探す (block 番号はビルドごとに変わり得るため名前に依存しない)
export function locateFlFile(flDir, match) {
  if (!flDir || !existsSync(flDir)) throw new SourceError(`FL 抽出物 dir が無い: ${flDir ?? "(未設定)"} (fl-win64 素材が要る)`, "skip");
  const root = existsSync(path.join(flDir, "extracted")) ? path.join(flDir, "extracted") : flDir;
  const nameRe = new RegExp(match.name ?? "_DATA\\.bin$");
  const headRe = new RegExp(match.headRegex);
  const bodyRes = (match.containsRegex ?? []).map((r) => new RegExp(r));
  const hits = new Map();
  const buf = Buffer.alloc(8192);
  for (const name of readdirSync(root)) {
    if (!nameRe.test(name)) continue;
    const f = path.join(root, name);
    const st = statSync(f);
    if (!st.isFile() || st.size > (match.maxBytes ?? 4_000_000) || st.size < 64) continue;
    const fd = openSync(f, "r");
    let head;
    try { head = buf.toString("latin1", 0, readSync(fd, buf, 0, buf.length, 0)); } finally { closeSync(fd); }
    if (!headRe.test(head)) continue;
    const data = readFileSync(f);
    const body = data.toString("latin1");
    if (!bodyRes.every((r) => r.test(body))) continue;
    hits.set(name, data);
  }
  if (!hits.size) throw new SourceError(`FL 抽出物内に署名 /${match.headRegex}/ の文書が無い (${root})`);
  const distinct = new Set([...hits.values()].map(sha256));
  if (distinct.size > 1) throw new SourceError(`署名に一致する文書が内容違いで ${distinct.size} 種ある: ${[...hits.keys()].join(", ")}`);
  const [name, data] = hits.entries().next().value;
  return { name, data };
}

// 1 件の source を取得してテキスト化する。戻り値: { raw: 生テキスト, origin }
export async function acquire(src, ctx) {
  if (src.kind === "fl-extracted") {
    const { name, data } = locateFlFile(ctx.flDir, src.match);
    const raw = src.format === "rtf" ? rtfToText(data.toString("latin1")) : htmlToText(decodeBody(data));
    return { raw, origin: `fl-win64:${name}`, bytes: data.length };
  }
  if (src.kind === "file") {
    const p = src.pathEnv ? process.env[src.pathEnv] : src.path;
    if (!p) throw new SourceError(`${src.pathEnv ?? "path"} が未設定 (${src.note ?? "ローカル素材が要る"})`, "skip");
    if (!existsSync(p)) throw new SourceError(`ファイルが無い: ${p}`, "skip");
    const data = readFileSync(p);
    const raw = src.format === "rtf" ? rtfToText(data.toString("latin1")) : src.format === "html" ? htmlToText(decodeBody(data), { stripChrome: !!src.stripChrome }) : decodeBody(data);
    return { raw, origin: `file:${path.basename(p)}`, bytes: data.length };
  }
  if (src.kind === "url") {
    const { bytes, contentType, finalUrl } = await fetchBytes(src.url, { fetchImpl: ctx.fetchImpl });
    const fmt = src.format ?? (/pdf/i.test(contentType) ? "pdf" : "html");
    let raw;
    if (fmt === "pdf") {
      if (bytes.subarray(0, 5).toString("latin1") !== "%PDF-") throw new SourceError(`PDF 以外が返った (${contentType})`);
      raw = pdfToText(bytes);
    } else raw = fmt === "text" ? decodeBody(bytes, contentType) : htmlToText(decodeBody(bytes, contentType), { stripChrome: src.stripChrome !== false });
    return { raw, origin: finalUrl, bytes: bytes.length };
  }
  throw new SourceError(`未知の kind: ${src.kind}`);
}

export function loadLedger(file) {
  if (!existsSync(file)) return { schema: 1, docs: {} };
  const l = JSON.parse(readFileSync(file, "utf8"));
  if (l.schema !== 1 || typeof l.docs !== "object") throw new Error(`台帳 ${file} の schema が不正`);
  return l;
}

const sortKeys = (o) => (Array.isArray(o) ? o.map(sortKeys) : o && typeof o === "object" ? Object.fromEntries(Object.keys(o).sort().map((k) => [k, sortKeys(o[k])])) : o);
export const serializeLedger = (l) => JSON.stringify(sortKeys(l), null, 2) + "\n";

export function renderLedgerMd(ledger, sources) {
  const L = [
    "<!-- 自動生成: pnpm terms-watch (tools/legal/terms-watch)。人手編集禁止。正本は docs/LEGAL_TERMS_LEDGER.json -->",
    "",
    "# LEGAL_TERMS_LEDGER — 各社規約の取得台帳 (LGL-5)",
    "",
    "事実整理であり法的助言ではない。本文は保存せず、正規化テキストの SHA-256 のみ記録する (正規化規則・運用は `tools/legal/terms-watch/REPORT.md`)。",
    "",
    "| id | 発行元 / 文書 | 版表記 | SHA-256 (正規化テキスト) | 文字数 | 初回取得 | 最終取得 | 要レビュー | 履歴 |",
    "|---|---|---|---|---:|---|---|---|---:|",
  ];
  for (const s of sources) {
    const d = ledger.docs[s.id];
    if (!d) { L.push(`| \`${s.id}\` | ${s.vendor} / ${s.title} | — | (未取得) | — | — | — | — | 0 |`); continue; }
    L.push(`| \`${s.id}\` | ${s.vendor} / ${s.title} | ${d.current.version ?? "文書内に版表記なし"} | \`${d.current.sha256}\` | ${d.current.chars} | ${d.firstSeen} | ${d.lastChecked} | ${d.pendingReview ? "**要レビュー**" : "—"} | ${d.history.length} |`);
  }
  L.push("", "## 出典", "");
  for (const s of sources) L.push(`- \`${s.id}\`: ${s.kind === "url" ? s.url : s.kind === "fl-extracted" ? "FL インストーラ抽出物 (fl-win64) 内の同梱文書" : (s.note ?? "ローカルファイル")}`);
  const hist = sources.filter((s) => ledger.docs[s.id]?.history.length);
  if (hist.length) {
    L.push("", "## 変更履歴", "");
    for (const s of hist) for (const h of ledger.docs[s.id].history) L.push(`- \`${s.id}\` ${h.supersededAt}: \`${h.sha256.slice(0, 16)}…\` (版表記 ${h.version ?? "なし"}, 初回取得 ${h.firstSeen}) → \`${ledger.docs[s.id].current.sha256.slice(0, 16)}…\``);
  }
  return L.join("\n") + "\n";
}

// 比較して台帳を更新する。戻り値の results[].status:
//   NEW / UNCHANGED / CHANGED / PENDING (未レビューの変更が残っている) / ERROR / SKIP
export async function runCheck({ sources, ledger, ctx, now = new Date().toISOString(), snapshotDir = null, only = null }) {
  const results = [];
  for (const src of sources) {
    if (only && !only.includes(src.id)) continue;
    const r = { id: src.id, status: "ERROR", detail: "", optional: !!src.optional };
    results.push(r);
    try {
      const got = await acquire(src, ctx);
      const doc = analyze(src, got.raw);
      Object.assign(r, { sha256: doc.sha256, version: doc.version, chars: doc.chars, origin: got.origin });
      if (snapshotDir) {
        mkdirSync(path.join(snapshotDir, src.id), { recursive: true });
        writeFileSync(path.join(snapshotDir, src.id, `${doc.sha256}.txt`), doc.text.replace(/(?<=[.;:] )(?=[A-Z0-9(])/g, "\n") + "\n");
      }
      const cur = { sha256: doc.sha256, chars: doc.chars, version: doc.version, origin: got.origin };
      const prev = ledger.docs[src.id];
      if (!prev) {
        ledger.docs[src.id] = { firstSeen: now.slice(0, 10), lastChecked: now.slice(0, 10), pendingReview: false, current: { ...cur, firstSeen: now.slice(0, 10) }, history: [] };
        r.status = "NEW";
      } else if (prev.current.sha256 === doc.sha256) {
        prev.lastChecked = now.slice(0, 10);
        prev.current.version = doc.version;
        r.status = prev.pendingReview ? "PENDING" : "UNCHANGED";
      } else {
        prev.history.push({ sha256: prev.current.sha256, chars: prev.current.chars, version: prev.current.version, firstSeen: prev.current.firstSeen, supersededAt: now.slice(0, 10) });
        r.previous = { sha256: prev.current.sha256, version: prev.current.version };
        prev.current = { ...cur, firstSeen: now.slice(0, 10) };
        prev.lastChecked = now.slice(0, 10);
        prev.pendingReview = true;
        r.status = "CHANGED";
      }
    } catch (e) {
      if (e instanceof SourceError) { r.status = e.kind === "skip" ? "SKIP" : "ERROR"; r.detail = e.message; } else { r.status = "ERROR"; r.detail = `${e?.stack ?? e}`; }
    }
  }
  return results;
}

export function ackDocs(ledger, ids, now = new Date().toISOString()) {
  const target = ids.includes("all") ? Object.keys(ledger.docs) : ids;
  const done = [];
  for (const id of target) {
    const d = ledger.docs[id];
    if (!d) throw new Error(`台帳に ${id} が無い`);
    if (d.pendingReview) { d.pendingReview = false; d.reviewedAt = now.slice(0, 10); done.push(id); }
  }
  return done;
}

// 終了コード: 0 全件一致 (NEW は基準線の記録のみ) / 1 差分あり or 未レビュー変更 / 3 検証不能 (取得失敗・素材なし) / 優先は 1 > 3
//   素材なし (SKIP) は既定で 3。sources.json で optional:true の source は警告のみ (--strict で 3)。--allow-skip は全 SKIP を許容
export function exitCodeFor(results, { allowSkip = false, strict = false } = {}) {
  if (results.some((r) => r.status === "CHANGED" || r.status === "PENDING")) return 1;
  if (results.some((r) => r.status === "ERROR" || (r.status === "SKIP" && !allowSkip && (strict || !r.optional)))) return 3;
  return 0;
}
