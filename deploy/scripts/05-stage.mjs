#!/usr/bin/env node
// ビルド成果物 -> Workers Static Assets 用の配備ディレクトリ (deploy/work/site) を組み立てる。書込は --out 配下のみ。
//
//   node deploy/scripts/05-stage.mjs --src tools/e2e/work/dist [--manifest tools/assets/manifest.json] [--out deploy/work/site]
//
// やること:
//   1. --src の走査 (+ 任意 --manifest の追加ファイル) を --out へ hardlink (別 FS なら copy)
//   2. 1 ファイル > --max-file (既定 24MiB; Static Assets 上限は 25MiB) を --part-size (既定 16MiB) の part に分割し、
//      <key>.parts/NNNN.<sha12>.part + <key>.parts/index.json (descriptor) を出力。元ファイルは置かない
//      クライアントは deploy/client/chunked.mjs で連結 ReadableStream -> WebAssembly.compileStreaming に流す
//   3. edge-policy.json から `_headers` を生成 (tools/hosting/headers-from-policy.mjs --check)
//   4. 制約検査 (ファイル数, 25MiB, immutable 配下のハッシュ名) と release.json の生成
// manifest 形式 (tools/assets と同じ契約): { "version":1, "files":[{ "path":"wasm/ott.1a2b3c4d.wasm", "src":"相対/絶対", "contentType":"任意" }] }
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import {
  closeSync, copyFileSync, linkSync, mkdirSync, openSync, readdirSync, readFileSync,
  readSync, rmSync, statSync, writeFileSync,
} from "node:fs";
import path from "node:path";
import { contentTypeFor, loadPolicy, POLICY_PATH } from "../lib/policy.mjs";

const MiB = 1024 * 1024;
const args = process.argv.slice(2);
const opt = (n, d) => {
  const i = args.indexOf(`--${n}`);
  return i >= 0 ? args[i + 1] : d;
};
const has = (n) => args.includes(`--${n}`);

const DEPLOY = path.resolve(import.meta.dirname, "..");
const REPO = path.resolve(DEPLOY, "..");
const src = opt("src");
const manifestPath = opt("manifest");
const out = path.resolve(opt("out", path.join(DEPLOY, "work/site")));
const maxFile = Number(opt("max-file", 24 * MiB));
const partSize = Number(opt("part-size", 16 * MiB));
const maxFiles = Number(opt("max-files", process.env.STATIC_ASSETS_MAX_FILES ?? 20000)); // Free 20,000 / Paid 100,000
const LIMIT = 25 * MiB;
if (!src && !manifestPath) throw new Error("--src か --manifest が必要");
if (partSize > LIMIT || maxFile > LIMIT) throw new Error("--part-size / --max-file は 25MiB 以下");
if (out === DEPLOY || out === REPO) throw new Error("--out が deploy/ もしくはリポジトリ root (rm -rf 対象になる)");

// tools/assets の chunk 配置 (c/ m/) と latest.json は edge-policy 正本に未収載。有効 policy に足して `_headers` へ反映する
// (正本への取込みは tools/e2e 検収後の別作業。deploy/README.md 参照)
const extraImmutable = (opt("immutable-prefix", process.env.STAGE_EXTRA_IMMUTABLE ?? "/c/,/m/")).split(",").filter(Boolean);
const extraDocument = (opt("document", process.env.STAGE_EXTRA_DOCUMENT ?? "/latest.json")).split(",").filter(Boolean);

const policy = loadPolicy();
const effective = structuredClone(policy);
for (const r of effective.responseHeaders) {
  if (r.id === "cache-immutable") r.match.pathPrefix = [...new Set([...r.match.pathPrefix, ...extraImmutable])];
  if (r.id === "cache-document") r.match.path = [...new Set([...r.match.path, ...extraDocument])];
}
effective.layout.immutablePrefixes = [...new Set([...effective.layout.immutablePrefixes, ...extraImmutable])];
effective.layout.document = [...new Set([...effective.layout.document, ...extraDocument])];

function walk(dir, base = dir, acc = []) {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, base, acc);
    else acc.push({ key: path.relative(base, p).split(path.sep).join("/"), file: p });
  }
  return acc;
}
const entries = new Map();
if (src) for (const f of walk(path.resolve(src))) entries.set(f.key, f);
if (manifestPath) {
  const mp = path.resolve(manifestPath);
  for (const f of JSON.parse(readFileSync(mp, "utf8")).files) {
    entries.set(f.path, { key: f.path, file: path.resolve(path.dirname(mp), f.src ?? f.path), contentType: f.contentType });
  }
}
for (const reserved of ["_headers", "_redirects", "release.json"]) entries.delete(reserved); // 本スクリプトが生成

const HASHED = /[.-][0-9A-Za-z_-]{8,}\.[A-Za-z0-9]+$/;
const ID_NAMED = /^[0-9a-f]{16,}\.[A-Za-z0-9]+$/; // tools/assets の c/<xx>/<id>.raw
const isImmutable = (key) => effective.layout.immutablePrefixes.some((p) => `/${key}`.startsWith(p));
const isDocument = (key) => effective.layout.document.includes(`/${key}`);

const errors = [];
const warnings = [];
for (const e of entries.values()) {
  e.size = statSync(e.file).size;
  if (isImmutable(e.key) && !isDocument(e.key) && !HASHED.test(e.key) && !ID_NAMED.test(path.posix.basename(e.key))) {
    errors.push(`immutable 配下にハッシュ無しのファイル名: ${e.key} (1 年 immutable で配信されるため中止。<name>.<hash>.<ext> にすること)`);
  }
}
if (!entries.has("index.html")) warnings.push("index.html が無い (ルート / が 404 になる)");
if (errors.length) {
  console.error(errors.join("\n"));
  process.exit(2);
}

rmSync(out, { recursive: true, force: true });
mkdirSync(out, { recursive: true });
const place = (key, from) => {
  const to = path.join(out, key);
  mkdirSync(path.dirname(to), { recursive: true });
  try { linkSync(from, to); } catch { copyFileSync(from, to); }
};

function sha256File(file) {
  const h = createHash("sha256");
  const fd = openSync(file, "r");
  const buf = Buffer.allocUnsafe(4 * MiB);
  try {
    for (let n; (n = readSync(fd, buf, 0, buf.length, null)) > 0; ) h.update(buf.subarray(0, n));
  } finally { closeSync(fd); }
  return h.digest("hex");
}

// 1 パスで part 分割 + 全体 sha256
function splitFile(e) {
  const dirKey = `${e.key}.parts`;
  const whole = createHash("sha256");
  const fd = openSync(e.file, "r");
  const parts = [];
  try {
    for (let off = 0, i = 0; off < e.size; off += partSize, i++) {
      const len = Math.min(partSize, e.size - off);
      const buf = Buffer.allocUnsafe(len);
      for (let got = 0; got < len; ) got += readSync(fd, buf, got, len - got, off + got);
      whole.update(buf);
      const sha = createHash("sha256").update(buf).digest("hex");
      const name = `${String(i).padStart(4, "0")}.${sha.slice(0, 12)}.part`;
      const to = path.join(out, dirKey, name);
      mkdirSync(path.dirname(to), { recursive: true });
      writeFileSync(to, buf);
      parts.push({ name, size: len, sha256: sha });
    }
  } finally { closeSync(fd); }
  const desc = {
    v: 1,
    path: e.key,
    size: e.size,
    sha256: whole.digest("hex"),
    contentType: e.contentType ?? contentTypeFor(policy, e.key),
    partSize,
    parts,
  };
  writeFileSync(path.join(out, dirKey, "index.json"), JSON.stringify(desc));
  return desc;
}

const files = {};
const chunked = {};
for (const e of [...entries.values()].sort((a, b) => a.key.localeCompare(b.key))) {
  if (e.size > maxFile) {
    const d = splitFile(e);
    chunked[e.key] = { descriptor: `${e.key}.parts/index.json`, size: d.size, sha256: d.sha256, parts: d.parts.length, contentType: d.contentType };
  } else {
    place(e.key, e.file);
    files[e.key] = { size: e.size, sha256: sha256File(e.file), contentType: e.contentType ?? contentTypeFor(policy, e.key) };
  }
}

// _headers: 実エッジ挙動に合わせた変換 + 突合検査 (tools/hosting/headers-from-policy.mjs)
const effFile = path.join(DEPLOY, "work/edge-policy.effective.json");
mkdirSync(path.dirname(effFile), { recursive: true });
writeFileSync(effFile, JSON.stringify(effective, null, 2));
let headerCheck;
try {
  execFileSync("node", [path.join(REPO, "tools/hosting/headers-from-policy.mjs"), "--check", "--policy", effFile, "--out", path.join(out, "_headers")], { stdio: ["ignore", "ignore", "pipe"] });
} catch (e) {
  console.error(String(e.stderr));
  process.exit(3);
}
headerCheck = "ok";

// Static Assets 固有の補正 (実エッジ実測, probe): Content-Type は拡張子由来の既定 (charset 無し) なので policy.contentTypes を `_headers` で上書きする
// (上書きは 1 値になる)。mutable prefix には policy の既定 Cache-Control を明示する (Static Assets 既定は max-age=0, must-revalidate)。
// `!` を伴わない独立ブロックとして末尾に追加する (headers-from-policy の累積セマンティクスと干渉させない)
const defaultCc = policy.responseHeaders.find((r) => r.id === "cache-default")?.set["Cache-Control"];
const extra = [];
extra.push(`/\n  Content-Type: ${policy.contentTypes.html}`, `/index.html\n  Content-Type: ${policy.contentTypes.html}`);
for (const [ext, ct] of Object.entries(policy.contentTypes)) if (ext !== "html") extra.push(`/*.${ext}\n  Content-Type: ${ct}`);
if (defaultCc) for (const pre of policy.layout.mutablePrefixes ?? []) extra.push(`${pre}*\n  Cache-Control: ${defaultCc}`);
const hf = path.join(out, "_headers");
const hText = readFileSync(hf, "utf8") + `\n# stage: Content-Type 補正 / mutable prefix の Cache-Control\n${extra.join("\n\n")}\n`;
writeFileSync(hf, hText);
const nBlocks = hText.split("\n").filter((l) => l && !l.startsWith("#") && !l.startsWith(" ")).length;
if (nBlocks > 100) {
  console.error(`_headers のブロック数 ${nBlocks} > 100`);
  process.exit(3);
}

// release.json (buildId は全 file/part の内容ハッシュから決定的に作る)
const idSrc = [
  ...Object.entries(files).map(([k, v]) => `${k}:${v.sha256}`),
  ...Object.entries(chunked).map(([k, v]) => `${k}:${v.sha256}`),
].join("\n");
const buildId = createHash("sha256").update(idSrc).digest("hex").slice(0, 12);
const release = { buildId, createdAt: new Date().toISOString(), files, chunked };
writeFileSync(path.join(out, "release.json"), JSON.stringify(release, null, 1));

// 制約検査 (配備ファイル総数は part / index.json を含む。_headers と _redirects は数えない)
const all = walk(out).filter((f) => !["_headers", "_redirects"].includes(f.key));
const over = all.filter((f) => statSync(f.file).size > LIMIT);
if (all.length > maxFiles) errors.push(`ファイル数 ${all.length} > ${maxFiles} (Free 20,000 / Paid 100,000。STATIC_ASSETS_MAX_FILES で上書き)`);
for (const f of over) errors.push(`25MiB 超: ${f.key}`);
const totalBytes = all.reduce((a, f) => a + statSync(f.file).size, 0);
console.log(JSON.stringify({
  out, buildId, deployedFiles: all.length, totalBytes, chunkedFiles: Object.keys(chunked).length,
  chunked: Object.fromEntries(Object.entries(chunked).map(([k, v]) => [k, { parts: v.parts, size: v.size }])),
  headers: headerCheck, headerBlocks: nBlocks, extraImmutable, extraDocument, warnings,
}, null, 1));
if (errors.length) {
  console.error(errors.join("\n"));
  process.exit(2);
}
