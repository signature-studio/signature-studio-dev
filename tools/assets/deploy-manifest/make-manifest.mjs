#!/usr/bin/env node
// 配備 manifest の生産側 (#63)。消費側は deploy/scripts/05-stage.mjs --manifest (契約は deploy/README.md):
//   { "version":1, "files":[{ "path":"wasm/ott.1a2b3c4d5e6f.wasm", "src":"<manifest からの相対/絶対>", "contentType":"..." }] }
//
//   node tools/assets/deploy-manifest/make-manifest.mjs --out <dir> --add wasm=tools/runtime/work/wasm [--add dest=<file|dir> ...]
//
//   --add <dest>=<src>  src がディレクトリなら再帰して <dest>/<相対> に、ファイルなら <dest>/<basename> に配置
//   --out <dir>         内容アドレス名のファイル + deploy-manifest.json をここへ出力 (src は manifest からの相対)
//   --check-only        --out へ書かず検査だけ行う
//
// 規則:
//   - immutable 配下 (edge-policy layout.immutablePrefixes) かつ document 以外は <stem>.<sha256 先頭 12 hex>.<ext> にする。
//     既にハッシュ付きの名前 (05-stage の HASHED 判定と同じ) はそのまま (tools/runtime/stage_wasm.mjs 出力は冪等)。
//   - immutable 外・document (/wasm/manifest.json 等) は名前を変えない。
//   - contentType は edge-policy の contentTypes から明示 (拡張子未登録は defaultContentType)。
//   - 配備先で衝突する path・予約名 (_headers/_redirects/release.json)・不正 path は中止。
//   - /wasm/manifest.json (ランタイムのブート manifest) が入る場合、entries[].file/glue の存在と sha256 を突合する
//     (ローダは manifest 経由で hash 名を解決するため、ここが食い違うと実行時に 404)。
import { createHash } from "node:crypto";
import { closeSync, copyFileSync, linkSync, mkdirSync, openSync, readdirSync, readFileSync, readSync, rmSync, statSync, writeFileSync } from "node:fs";
import path from "node:path";
import { contentTypeFor, loadPolicy } from "../../../deploy/lib/policy.mjs";

export const HASHED = /[.-][0-9A-Za-z_-]{8,}\.[A-Za-z0-9]+$/; // 05-stage.mjs と同一
export const RESERVED = ["_headers", "_redirects", "release.json"];
export const MANIFEST_NAME = "deploy-manifest.json";
export const HASH_LEN = 12;

export function sha256File(file) {
  const h = createHash("sha256");
  const fd = openSync(file, "r");
  const buf = Buffer.allocUnsafe(4 << 20);
  try {
    for (let n; (n = readSync(fd, buf, 0, buf.length, null)) > 0; ) h.update(buf.subarray(0, n));
  } finally { closeSync(fd); }
  return h.digest("hex");
}

export function hashedName(base, sha) {
  const i = base.lastIndexOf(".");
  if (i <= 0) throw new Error(`拡張子の無いファイル名はハッシュ名にできない: ${base}`);
  return `${base.slice(0, i)}.${sha.slice(0, HASH_LEN)}${base.slice(i)}`;
}

function walk(dir, acc = [], rel = "") {
  for (const e of readdirSync(path.join(dir, rel), { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
    const r = rel ? `${rel}/${e.name}` : e.name;
    if (e.isDirectory()) walk(dir, acc, r);
    else acc.push(r);
  }
  return acc;
}

function checkKey(key) {
  if (!key || key.startsWith("/") || key.split("/").some((s) => s === ".." || s === "." || s === "")) throw new Error(`不正な path: ${JSON.stringify(key)}`);
  if (RESERVED.includes(key)) throw new Error(`予約名は配備できない (05-stage が生成/破棄する): ${key}`);
}

/** adds: [{dest, src}] -> 純粋な計画 (ファイルは書かない)。 */
export function plan(adds, policy = loadPolicy()) {
  const immutable = policy.layout.immutablePrefixes;
  const documents = new Set(policy.layout.document);
  const byKey = new Map();
  for (const { dest, src } of adds) {
    const abs = path.resolve(src);
    const st = statSync(abs);
    const items = st.isDirectory() ? walk(abs).map((rel) => ({ rel, file: path.join(abs, rel) })) : [{ rel: path.basename(abs), file: abs }];
    for (const { rel, file } of items) {
      const sha = sha256File(file);
      let key = [dest.replace(/\/+$/, ""), rel].filter(Boolean).join("/");
      const isDoc = documents.has(`/${key}`);
      const inImmutable = immutable.some((p) => `/${key}`.startsWith(p));
      let renamed = false;
      if (inImmutable && !isDoc && !HASHED.test(key)) {
        const d = path.posix.dirname(key);
        key = (d === "." ? "" : `${d}/`) + hashedName(path.posix.basename(key), sha);
        renamed = true;
      }
      checkKey(key);
      const prev = byKey.get(key);
      if (prev && prev.sha256 !== sha) throw new Error(`path 衝突 (内容が異なる): ${key} <- ${prev.from} / ${file}`);
      byKey.set(key, { path: key, from: file, size: statSync(file).size, sha256: sha, contentType: contentTypeFor(policy, key), renamed, immutable: inImmutable && !isDoc });
    }
  }
  return [...byKey.values()].sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : 0));
}

/** /wasm/manifest.json (ランタイムのブート manifest) と配備ファイル集合の突合。問題の配列を返す。 */
export function crossCheckBootManifest(files) {
  const boot = files.find((f) => f.path === "wasm/manifest.json");
  if (!boot) return { checked: false, problems: [] };
  const by = new Map(files.map((f) => [f.path, f]));
  const problems = [];
  let j;
  try { j = JSON.parse(readFileSync(boot.from, "utf8")); } catch (e) { return { checked: true, problems: [`wasm/manifest.json が JSON でない: ${e.message}`] }; }
  for (const en of j.entries ?? []) {
    for (const [field, name] of [["file", en.file], ["glue", en.glue]]) {
      if (!name) continue;
      const f = by.get(`wasm/${name}`);
      if (!f) { problems.push(`${en.id}.${field}=${name} が配備集合に無い`); continue; }
      if (field === "file" && en.sha256 && en.sha256 !== f.sha256) problems.push(`${en.id}.file=${name} の sha256 不一致 (manifest ${en.sha256.slice(0, 12)} / 実体 ${f.sha256.slice(0, 12)})`);
      if (field === "file" && en.bytes != null && en.bytes !== f.size) problems.push(`${en.id}.file=${name} の bytes 不一致 (manifest ${en.bytes} / 実体 ${f.size})`);
    }
  }
  return { checked: true, problems };
}

export function build(files) {
  return { version: 1, files: files.map((f) => ({ path: f.path, src: f.path, contentType: f.contentType, size: f.size, sha256: f.sha256 })) };
}

function place(from, to) {
  mkdirSync(path.dirname(to), { recursive: true });
  rmSync(to, { force: true });
  try { linkSync(from, to); } catch { copyFileSync(from, to); }
}

function main() {
  const args = process.argv.slice(2);
  const adds = [];
  let out;
  let checkOnly = false;
  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--add") {
      const v = args[++i] ?? "";
      const k = v.indexOf("=");
      if (k < 0) throw new Error("--add は <dest>=<src>");
      adds.push({ dest: v.slice(0, k), src: v.slice(k + 1) });
    } else if (args[i] === "--out") out = args[++i];
    else if (args[i] === "--check-only") checkOnly = true;
    else throw new Error(`不明な引数: ${args[i]}`);
  }
  if (!adds.length) throw new Error("--add が必要");
  if (!out && !checkOnly) throw new Error("--out が必要 (検査のみなら --check-only)");
  const files = plan(adds);
  const cc = crossCheckBootManifest(files);
  if (cc.problems.length) { console.error(cc.problems.join("\n")); process.exit(2); }
  if (!checkOnly) {
    const o = path.resolve(out);
    for (const f of files) place(f.from, path.join(o, f.path));
    writeFileSync(path.join(o, MANIFEST_NAME), JSON.stringify(build(files), null, 1) + "\n");
  }
  console.log(JSON.stringify({
    out: out ? path.resolve(out) : null, manifest: out ? path.join(path.resolve(out), MANIFEST_NAME) : null, files: files.length,
    totalBytes: files.reduce((a, f) => a + f.size, 0), renamed: files.filter((f) => f.renamed).length, bootManifestChecked: cc.checked,
  }));
}

if (import.meta.url === `file://${process.argv[1]}`) {
  try { main(); } catch (e) { console.error(e.message); process.exit(1); }
}
