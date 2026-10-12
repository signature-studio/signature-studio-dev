// release guard 中核 (LGL-2)。deny-list 生成 (build) と公開物走査 (scan)。依存は node 標準のみ。
//   deny-list = { denylist.json (params / ファイル sha256 / chunk id), windows.bin (代表バイト列の指紋, 昇順 u64 LE) }
//   代表バイト列 = content-defined sampling した W バイト窓の sha256 先頭 8 バイト。
//   窓の選び方は内容だけで決まる (buzhash が mask に一致する位置) ので、dist 側でオフセット・結合が変わっても一致する。
import { createHash } from "node:crypto";
import { createReadStream, existsSync, mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import path from "node:path";
import { Buffer } from "node:buffer";
import zlib from "node:zlib";

export const FORMAT = 1;
export const DEFAULTS = { window: 48, mask: 0x3ff, minDistinct: 16, minFileBytes: 512 };
const READ = 1 << 20;

// buzhash 用の決定的な表 (sha256("release-guard-v1:i") 先頭 4 バイト)
const TABLE = new Uint32Array(256);
for (let i = 0; i < 256; i++) TABLE[i] = createHash("sha256").update(`release-guard-v1:${i}`).digest().readUInt32LE(0);

const rotl = (x, n) => ((x << n) | (x >>> (32 - n))) >>> 0;

export class WindowSampler {
  constructor({ window = DEFAULTS.window, mask = DEFAULTS.mask, minDistinct = DEFAULTS.minDistinct } = {}, onWindow) {
    this.W = window;
    this.mask = mask;
    this.minDistinct = minDistinct;
    this.onWindow = onWindow;
    this.h = 0;
    this.fed = 0;
    this.tail = Buffer.alloc(0);
    this.rotW = window & 31;
  }

  feed(buf) {
    const { W, mask, minDistinct } = this;
    const tl = this.tail.length;
    const cat = tl ? Buffer.concat([this.tail, buf]) : buf;
    const base = this.fed - tl; // cat[0] のストリーム内位置
    let h = this.h;
    let fed = this.fed;
    const rotW = this.rotW;
    for (let i = tl; i < cat.length; i++) {
      const inB = cat[i];
      if (fed < W) h = (((h << 1) | (h >>> 31)) ^ TABLE[inB]) >>> 0;
      else {
        const t = TABLE[cat[i - W]];
        h = ((((h << 1) | (h >>> 31)) ^ ((t << rotW) | (t >>> (32 - rotW))) ^ TABLE[inB]) >>> 0);
      }
      fed++;
      if (fed >= W && (h & mask) === 0) {
        const win = cat.subarray(i - W + 1, i + 1);
        if (distinctBytes(win) >= minDistinct && !isText(win)) this.onWindow(fingerprint(win), base + i - W + 1);
      }
    }
    this.h = h;
    this.fed = fed;
    this.tail = Buffer.from(cat.subarray(Math.max(0, cat.length - W)));
  }
}

function distinctBytes(win) {
  const seen = new Uint8Array(256);
  let n = 0;
  for (let i = 0; i < win.length; i++) if (!seen[win[i]]) { seen[win[i]] = 1; n++; }
  return n;
}
// 全バイトが ASCII 印字/空白の窓は除外する (OSS ライセンス文・API 名一覧などリポジトリ側にも正当に存在する共有テキストの誤検知源)。
// テキスト資産の逐語コピーはファイル sha256 一致で検出する。部分コピーは検出範囲外 (REPORT 参照)
function isText(win) {
  for (let i = 0; i < win.length; i++) {
    const b = win[i];
    if (!((b >= 0x20 && b <= 0x7e) || b === 0x09 || b === 0x0a || b === 0x0d)) return false;
  }
  return true;
}
const fingerprint = (win) => createHash("sha256").update(win).digest().readBigUInt64LE(0);

export function walk(dir, acc = [], base = dir) {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isSymbolicLink()) continue;
    if (e.isDirectory()) walk(p, acc, base);
    else if (e.isFile()) acc.push({ key: path.relative(base, p).split(path.sep).join("/"), file: p });
  }
  return acc;
}

async function* readChunks(file) {
  yield* createReadStream(file, { highWaterMark: READ });
}

// ---------- build ----------
export async function buildDenylist({ from, manifests = [], out, params = {}, log = () => {} }) {
  const P = { ...DEFAULTS, ...params };
  if (!from?.length && !manifests.length) throw new Error("build: --from か --manifest が必要");
  const fps = new Set();
  const files = {}; // sha256 -> [label,...]
  const chunkIds = {}; // id(32hex) -> label
  const sources = [];
  for (const dir of from ?? []) {
    const root = path.resolve(dir);
    if (!existsSync(root)) throw new Error(`build: ${dir} が存在しない`);
    const label = path.basename(root);
    const list = statSync(root).isDirectory() ? walk(root) : [{ key: path.basename(root), file: root }];
    let bytes = 0;
    let nFiles = 0;
    let nHashed = 0;
    for (const f of list) {
      const h = createHash("sha256");
      const s = new WindowSampler(P, (fp) => fps.add(fp));
      let size = 0;
      for await (const c of readChunks(f.file)) { h.update(c); s.feed(c); size += c.length; }
      bytes += size;
      nFiles++;
      if (size >= P.minFileBytes) {
        const labels = (files[h.digest("hex")] ??= []);
        if (labels.length < 3) labels.push(`${label}/${f.key}`);
        nHashed++;
      }
    }
    sources.push({ label, files: nFiles, bytes, fileHashes: nHashed });
    log(`${label}: ${nFiles} files ${bytes} bytes`);
  }
  for (const mf of manifests) {
    const m = JSON.parse(readFileSync(mf, "utf8"));
    const ids = m.chunks?.id;
    if (typeof ids !== "string" || ids.length % 32) throw new Error(`manifest ${mf}: chunks.id が 32hex 連結でない`);
    let n = 0;
    for (let i = 0; i < ids.length; i += 32) { chunkIds[ids.slice(i, i + 32)] = m.name ?? path.basename(mf); n++; }
    sources.push({ label: `manifest:${m.name ?? path.basename(mf)}`, chunkIds: n });
  }
  return writeDenylist(out, P, fps, files, chunkIds, sources);
}

function writeDenylist(out, P, fps, files, chunkIds, sources) {
  const arr = BigUint64Array.from(fps);
  arr.sort();
  const bin = Buffer.from(arr.buffer, arr.byteOffset, arr.byteLength);
  const meta = { format: FORMAT, params: P, sources, windows: arr.length, files, chunkIds };
  const metaText = JSON.stringify(meta);
  const id = createHash("sha256").update(metaText).update(bin).digest("hex").slice(0, 16);
  mkdirSync(out, { recursive: true });
  writeFileSync(path.join(out, "windows.bin"), bin);
  writeFileSync(path.join(out, "denylist.json"), JSON.stringify({ id, created: new Date().toISOString(), ...meta }));
  return { id, windows: arr.length, files: Object.keys(files).length, chunkIds: Object.keys(chunkIds).length, sources };
}

export function loadDenylist(dir) {
  const jf = path.join(dir, "denylist.json");
  const bf = path.join(dir, "windows.bin");
  if (!existsSync(jf) || !existsSync(bf)) throw new DenylistMissing(`deny-list が無い: ${dir} (denylist.json / windows.bin)。生成: pnpm release-guard:build -- --from <analysis dir>`);
  const meta = JSON.parse(readFileSync(jf, "utf8"));
  if (meta.format !== FORMAT) throw new Error(`deny-list format ${meta.format} (期待 ${FORMAT})`);
  const raw = readFileSync(bf);
  if (raw.length % 8) throw new Error("windows.bin のサイズが 8 の倍数でない");
  const windows = new BigUint64Array(raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.length));
  if (windows.length !== meta.windows) throw new Error(`windows.bin 件数 ${windows.length} != denylist.json ${meta.windows}`);
  if (windows.length + Object.keys(meta.files).length + Object.keys(meta.chunkIds).length === 0) throw new Error("deny-list が空 (fail-closed)");
  return { ...meta, windowsArr: windows };
}
export class DenylistMissing extends Error {}

function has(arr, x) {
  let lo = 0;
  let hi = arr.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >>> 1;
    const v = arr[mid];
    if (v === x) return true;
    if (v < x) lo = mid + 1; else hi = mid - 1;
  }
  return false;
}

// ---------- allow-list ----------
// { "entries": [ { "path": "glob (任意)", "sha256": "hex (任意)", "kinds": ["file","chunk","window"] (既定: 全部), "reason": "必須" } ] }
export function loadAllowlist(file) {
  if (!file || !existsSync(file)) return [];
  const j = JSON.parse(readFileSync(file, "utf8"));
  return (j.entries ?? []).map((e, i) => {
    if (!e.reason || typeof e.reason !== "string") throw new Error(`allow-list ${file} entries[${i}]: reason が必須`);
    if (!e.path && !e.sha256) throw new Error(`allow-list ${file} entries[${i}]: path か sha256 が必要`);
    const kinds = e.kinds ?? ["file", "chunk", "window"];
    for (const k of kinds) if (!["file", "chunk", "window"].includes(k)) throw new Error(`allow-list entries[${i}]: 不正な kind ${k}`);
    return { ...e, kinds, re: e.path ? globToRe(e.path) : null };
  });
}
export function globToRe(g) {
  let s = "";
  for (let i = 0; i < g.length; i++) {
    const c = g[i];
    if (c === "*") { if (g[i + 1] === "*") { s += ".*"; i++; if (g[i + 1] === "/") i++; } else s += "[^/]*"; }
    else if (c === "?") s += "[^/]";
    else s += c.replace(/[.+^${}()|[\]\\]/g, "\\$&");
  }
  return new RegExp(`^${s}$`);
}
const allowed = (allow, key, sha, kind) => allow.find((e) => e.kinds.includes(kind) && (!e.re || e.re.test(key)) && (!e.sha256 || e.sha256 === sha));

// ---------- scan ----------
export const minOf = (it) => { let m = Infinity; for (const v of it) if (v < m) m = v; return m; };
const CHUNK_KEY = /(?:^|\/)c\/[0-9a-f]{2}\/([0-9a-f]{32})\.(?:raw|br|zst)$/;
const DECODERS = { ".br": zlib.createBrotliDecompress, ".zst": zlib.createZstdDecompress, ".gz": zlib.createGunzip };

async function scanStream(source, dl, wantHash) {
  const h = createHash("sha256");
  const found = new Map();
  const s = new WindowSampler(dl.params, (fp, off) => { if (has(dl.windowsArr, fp) && !found.has(fp)) found.set(fp, off); });
  let size = 0;
  for await (const c of source) {
    if (wantHash) h.update(c);
    s.feed(c);
    size += c.length;
  }
  return { sha256: h.digest("hex"), size, windows: found };
}

async function* decoded(file, ext) {
  const dec = DECODERS[ext]();
  const rs = createReadStream(file, { highWaterMark: READ });
  rs.on("error", (e) => dec.destroy(e));
  rs.pipe(dec);
  yield* dec;
}

export async function scanEntry(entry, dl, allow, { minHits = 1 } = {}) {
  const { key, file } = entry;
  const hits = [];
  const notes = [];
  const suppressed = [];
  const add = (kind, detail, sha) => {
    const a = allowed(allow, key, sha, kind);
    (a ? suppressed : hits).push({ kind, ...detail, ...(a ? { allowedBy: a.reason } : {}) });
  };
  const raw = await scanStream(readChunks(file), dl, true);
  const m = key.match(CHUNK_KEY);
  if (m && dl.chunkIds[m[1]] !== undefined) add("chunk", { id: m[1], from: dl.chunkIds[m[1]] }, raw.sha256);
  if (raw.size >= dl.params.minFileBytes && dl.files[raw.sha256]) add("file", { sha256: raw.sha256, matches: dl.files[raw.sha256] }, raw.sha256);
  const check = (r, label) => {
    if (r.windows.size >= minHits) add("window", { stream: label, distinctWindows: r.windows.size, firstOffset: minOf(r.windows.values()) }, raw.sha256);
  };
  check(raw, "raw");
  const ext = path.extname(key).toLowerCase();
  let dsha;
  if (DECODERS[ext]) {
    try {
      const d = await scanStream(decoded(file, ext), dl, true);
      dsha = d.sha256;
      if (d.size >= dl.params.minFileBytes && dl.files[d.sha256]) add("file", { sha256: d.sha256, stream: `decoded(${ext})`, matches: dl.files[d.sha256] }, raw.sha256);
      if (m && dl.chunkIds[m[1]] === undefined && d.size === 0) notes.push("decoded size 0");
      check(d, `decoded(${ext})`);
    } catch (e) {
      notes.push(`decode ${ext} 失敗 (raw のみ走査): ${e.code ?? e.message}`);
    }
  }
  return { key, size: raw.size, sha256: raw.sha256, decodedSha256: dsha, hits, suppressed, notes };
}

export async function scanEntries(entries, dl, allow = [], opts = {}) {
  const results = [];
  let bytes = 0;
  for (const e of entries) {
    const r = await scanEntry(e, dl, allow, opts);
    bytes += r.size;
    results.push(r);
  }
  const bad = results.filter((r) => r.hits.length);
  return {
    denylist: dl.id,
    files: results.length,
    bytes,
    failed: bad.length,
    suppressed: results.filter((r) => r.suppressed.length).map((r) => ({ key: r.key, suppressed: r.suppressed })),
    notes: results.filter((r) => r.notes.length).map((r) => ({ key: r.key, notes: r.notes })),
    violations: bad.map((r) => ({ key: r.key, size: r.size, sha256: r.sha256, hits: r.hits })),
  };
}

// stage 05 と同じ入力契約 (--src dir + --manifest {files:[{path,src}]}) から走査対象を作る。manifest が後勝ち。
export function collectEntries({ src = [], manifests = [], list, root }) {
  const map = new Map();
  for (const d of src) for (const f of walk(path.resolve(d))) map.set(f.key, f);
  for (const mf of manifests) {
    const mp = path.resolve(mf);
    for (const f of JSON.parse(readFileSync(mp, "utf8")).files) map.set(f.path, { key: f.path, file: path.resolve(path.dirname(mp), f.src ?? f.path) });
  }
  if (list) {
    const base = path.resolve(root ?? ".");
    for (const line of readFileSync(list, "utf8").split("\n").map((l) => l.trim()).filter((l) => l && !l.startsWith("#"))) {
      map.set(line, { key: line, file: path.resolve(base, line) });
    }
  }
  return [...map.values()].sort((a, b) => a.key.localeCompare(b.key));
}

export const DEFAULT_DENYLIST = path.resolve(import.meta.dirname, "work/denylist");
export const DEFAULT_ALLOWLIST = path.resolve(import.meta.dirname, "allowlist.json");

export function formatViolations(rep) {
  const L = [`release-guard: FAIL — ${rep.failed}/${rep.files} files が deny-list (${rep.denylist}) に一致`];
  for (const v of rep.violations) {
    for (const h of v.hits) L.push(`  ${v.key} (${v.size} B): ${h.kind} ${JSON.stringify(Object.fromEntries(Object.entries(h).filter(([k]) => k !== "kind")))}`);
  }
  L.push("  許容する場合は tools/legal/release-guard/allowlist.json に reason 付きで追加 (docs/LEGAL.md §6 の運用形態に従う)");
  return L.join("\n");
}

// deploy 側 (05-stage / 20-worker) 用ゲート。skip 時は理由付きで警告して通す (明示フラグ時のみ呼ぶこと)。
export async function gate({ entries, skip, label, denylist = process.env.RELEASE_GUARD_DENYLIST ?? DEFAULT_DENYLIST, allowlist = process.env.RELEASE_GUARD_ALLOWLIST ?? DEFAULT_ALLOWLIST }) {
  if (skip) {
    console.error(`!! release-guard (${label}) を --skip-release-guard で無効化した。FL/プラグイン由来バイト列の混入は検査されていない`);
    return { skipped: true };
  }
  let dl;
  try { dl = loadDenylist(denylist); } catch (e) {
    console.error(`release-guard (${label}): ${e.message}\n  (fail-closed。意図的に省略するなら --skip-release-guard)`);
    process.exit(e instanceof DenylistMissing ? 4 : 5);
  }
  const rep = await scanEntries(entries, dl, loadAllowlist(allowlist));
  if (rep.failed) {
    console.error(formatViolations(rep));
    process.exit(6);
  }
  console.error(`release-guard (${label}): PASS ${rep.files} files ${rep.bytes} B (deny-list ${rep.denylist}${rep.suppressed.length ? `, allow-list で許容 ${rep.suppressed.length} files` : ""})`);
  return { skipped: false, denylist: rep.denylist, files: rep.files, bytes: rep.bytes, suppressed: rep.suppressed.length };
}
