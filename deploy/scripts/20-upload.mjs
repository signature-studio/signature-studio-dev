#!/usr/bin/env node
// ビルド成果物 -> R2 アップロード (計画 / dry-run / 実行)。
//
//   node deploy/scripts/20-upload.mjs --src tools/e2e/work/dist --bucket webstudio-prod            # 計画のみ
//   node deploy/scripts/20-upload.mjs --src dist --manifest tools/assets/manifest.json --stats     # 圧縮見積り
//   node deploy/scripts/20-upload.mjs ... --execute [--backend cf|aws] [--skip-existing] [--purge --zone Z --host H]
//
// 入力: --src ディレクトリ走査 (+ 任意 --manifest で追加ファイル)。
//   manifest 形式: { "version": 1, "files": [ { "path": "wasm/ott.1a2b3c4d.wasm", "src": "相対/絶対 (省略時 path)", "contentType": "省略可" } ] }
//   (tools/assets の出力契約。内容アドレス名 = <name>.<hash8以上>.<ext> は生産側が付与する)
// キー配置は deploy/config/edge-policy.json の layout に従う:
//   /assets /wasm /data = immutable (ファイル名にハッシュ必須。検査し、無ければ中止)
//   /index.html, /release.json = document (最後に上げる。release.json は本スクリプトが生成)
// backend:
//   cf  (既定) cf r2 objects put。OAuth/APIトークンのみで動く。1 件 300MB 上限、Content-Type のみ設定
//        (Cache-Control は Transform Rules が付与)
//   aws S3 互換 API。R2 S3 キー必須 (R2_S3_ACCESS_KEY_ID/SECRET)。multipart で大容量可、
//        Cache-Control / Content-Encoding もオブジェクトに保存
import { createHash } from "node:crypto";
import { createReadStream, readdirSync, readFileSync, statSync, writeFileSync, mkdirSync } from "node:fs";
import { execFile } from "node:child_process";
import path from "node:path";
import zlib from "node:zlib";
import { promisify } from "node:util";
import { applyResponseHeaders, contentTypeFor, loadPolicy } from "../lib/policy.mjs";
import { cf, pool, requireEnv, zoneId } from "../lib/cf.mjs";

const execFileP = promisify(execFile);
const args = process.argv.slice(2);
const opt = (n, d) => {
  const i = args.indexOf(`--${n}`);
  return i >= 0 ? args[i + 1] : d;
};
const has = (n) => args.includes(`--${n}`);

const src = opt("src");
const manifestPath = opt("manifest");
const bucket = opt("bucket", process.env.CF_R2_BUCKET);
const backend = opt("backend", "cf");
const concurrency = Number(opt("concurrency", "6"));
const execute = has("execute");
const policy = loadPolicy();
const CF_PUT_LIMIT = 300 * 1000 * 1000; // cf r2 objects put の上限 (300MB)

if (!src && !manifestPath) throw new Error("--src か --manifest が必要");
if (!bucket) throw new Error("--bucket (または CF_R2_BUCKET) が必要");

// ---------- 計画 ----------
function walk(dir, base = dir, out = []) {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, base, out);
    else out.push({ key: path.relative(base, p).split(path.sep).join("/"), file: p });
  }
  return out;
}

const entries = new Map();
if (src) for (const f of walk(path.resolve(src))) entries.set(f.key, f);
if (manifestPath) {
  const mp = path.resolve(manifestPath);
  const m = JSON.parse(readFileSync(mp, "utf8"));
  for (const f of m.files) {
    entries.set(f.path, {
      key: f.path,
      file: path.resolve(path.dirname(mp), f.src ?? f.path),
      contentType: f.contentType,
    });
  }
}
entries.delete("release.json"); // 本スクリプトが生成する

const HASHED = /[.-][0-9A-Za-z_-]{8,}\.[A-Za-z0-9]+$/;
const isImmutable = (key) => policy.layout.immutablePrefixes.some((p) => `/${key}`.startsWith(p));
const isDocument = (key) => policy.layout.document.includes(`/${key}`);

function sha256(file) {
  return new Promise((res, rej) => {
    const h = createHash("sha256");
    createReadStream(file).on("data", (d) => h.update(d)).on("end", () => res(h.digest("hex"))).on("error", rej);
  });
}

const plan = await pool([...entries.values()], 8, async (e) => {
  const size = statSync(e.file).size;
  const key = e.key;
  return {
    key,
    file: e.file,
    size,
    sha256: await sha256(e.file),
    contentType: e.contentType ?? contentTypeFor(policy, key),
    cacheControl: applyResponseHeaders(policy, { path: `/${key}`, status: 200 }, {})["Cache-Control"],
    cls: isDocument(key) ? "document" : isImmutable(key) ? "immutable" : "mutable",
  };
});

const errors = [];
for (const p of plan) {
  if (p.cls === "immutable" && !HASHED.test(p.key)) {
    errors.push(`immutable 配下にハッシュ無しのファイル名: ${p.key} (1 年 immutable で配信されるため中止。<name>.<hash>.<ext> にすること)`);
  }
  if (backend === "cf" && p.size > CF_PUT_LIMIT) {
    errors.push(`${p.key}: ${p.size}B > cf 上限 300MB。--backend aws を使う`);
  }
}
if (errors.length) {
  console.error(errors.join("\n"));
  process.exit(2);
}

const order = { immutable: 0, mutable: 1, document: 2 };
plan.sort((a, b) => order[a.cls] - order[b.cls] || a.key.localeCompare(b.key));

// release.json: 全ファイルの key/size/sha256 から決定的な buildId を作る
const buildId = createHash("sha256")
  .update(plan.map((p) => `${p.key}:${p.sha256}`).join("\n"))
  .digest("hex")
  .slice(0, 12);
const release = {
  buildId,
  createdAt: new Date().toISOString(),
  files: Object.fromEntries(plan.map((p) => [p.key, { size: p.size, sha256: p.sha256, contentType: p.contentType }])),
};
mkdirSync(path.resolve(import.meta.dirname, "../work"), { recursive: true });
const releaseFile = path.resolve(import.meta.dirname, "../work/release.json");
writeFileSync(releaseFile, JSON.stringify(release, null, 2));
plan.push({
  key: "release.json",
  file: releaseFile,
  size: statSync(releaseFile).size,
  sha256: "-",
  contentType: contentTypeFor(policy, "release.json"),
  cacheControl: applyResponseHeaders(policy, { path: "/release.json", status: 200 }, {})["Cache-Control"],
  cls: "document",
});
// index.html は release.json の直前 (document 内では index -> release の順)
plan.sort((a, b) => order[a.cls] - order[b.cls] || (a.key === "release.json") - (b.key === "release.json"));

// ---------- 表示 ----------
const fmt = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(2)}MB` : `${(n / 1e3).toFixed(1)}KB`);
console.log(`bucket=${bucket} backend=${backend} buildId=${buildId} files=${plan.length}`);
for (const cls of ["immutable", "mutable", "document"]) {
  const xs = plan.filter((p) => p.cls === cls);
  console.log(`  ${cls.padEnd(9)} ${String(xs.length).padStart(4)} files ${fmt(xs.reduce((a, p) => a + p.size, 0))}`);
}
for (const p of plan) {
  console.log(`  ${p.cls.padEnd(9)} ${p.key.padEnd(44)} ${fmt(p.size).padStart(9)}  ${p.contentType}  | ${p.cacheControl}`);
}

if (has("stats")) {
  console.log("\n圧縮見積り (配信時 br/zstd/gzip。compression rule 対象拡張子のみ)");
  let tot = { raw: 0, br: 0, zstd: 0, gz: 0 };
  for (const p of plan.filter((x) => policy.compression[0].match.ext.includes(path.extname(x.key).slice(1)))) {
    const buf = readFileSync(p.file);
    const big = buf.length > 64e6;
    const br = zlib.brotliCompressSync(buf, { params: { [zlib.constants.BROTLI_PARAM_QUALITY]: big ? 9 : 11, [zlib.constants.BROTLI_PARAM_SIZE_HINT]: buf.length } }).length;
    const zs = zlib.zstdCompressSync(buf, { params: { [zlib.constants.ZSTD_c_compressionLevel]: big ? 12 : 19 } }).length;
    const gz = zlib.gzipSync(buf, { level: 9 }).length;
    tot = { raw: tot.raw + buf.length, br: tot.br + br, zstd: tot.zstd + zs, gz: tot.gz + gz };
    console.log(`  ${p.key.padEnd(44)} raw ${fmt(buf.length).padStart(9)}  br ${(br / buf.length * 100).toFixed(1)}%  zstd ${(zs / buf.length * 100).toFixed(1)}%  gzip ${(gz / buf.length * 100).toFixed(1)}%`);
  }
  console.log(`  TOTAL raw ${fmt(tot.raw)} br ${fmt(tot.br)} zstd ${fmt(tot.zstd)} gzip ${fmt(tot.gz)}`);
}

// ---------- 実行 ----------
const s3Endpoint = () => `https://${process.env.CLOUDFLARE_ACCOUNT_ID}.r2.cloudflarestorage.com`;
const s3Env = () => ({
  ...process.env,
  AWS_ACCESS_KEY_ID: process.env.R2_S3_ACCESS_KEY_ID,
  AWS_SECRET_ACCESS_KEY: process.env.R2_S3_SECRET_ACCESS_KEY,
  AWS_DEFAULT_REGION: "auto",
  AWS_REQUEST_CHECKSUM_CALCULATION: "when_required",
  AWS_RESPONSE_CHECKSUM_VALIDATION: "when_required",
});

function putCommand(p, { dry }) {
  if (backend === "cf") {
    const a = ["r2", "objects", "put", p.key, "--bucket-name", bucket, "--file", p.file, "--content-type", p.contentType];
    if (dry) a.push("--dry-run");
    return { bin: process.env.CF_BIN ?? "cf", args: a, env: process.env };
  }
  const a = [
    "s3", "cp", p.file, `s3://${bucket}/${p.key}`,
    "--endpoint-url", s3Endpoint(),
    "--content-type", p.contentType,
    "--cache-control", p.cacheControl ?? "public, max-age=300, must-revalidate",
    "--only-show-errors",
  ];
  if (dry) a.push("--dryrun");
  return { bin: "aws", args: a, env: s3Env() };
}

async function run(p, dry) {
  const c = putCommand(p, { dry });
  await execFileP(c.bin, c.args, { env: c.env, maxBuffer: 64 * 1024 * 1024 });
}

if (!execute) {
  console.log("\n[dry-run] コマンド構築の検証 (先頭 3 件, ネットワーク無し):");
  if (backend === "aws") process.env.R2_S3_ACCESS_KEY_ID ??= "dryrun";
  if (backend === "aws") process.env.R2_S3_SECRET_ACCESS_KEY ??= "dryrun";
  if (backend === "aws") process.env.CLOUDFLARE_ACCOUNT_ID ??= "dryrun-account";
  for (const p of plan.slice(0, 3)) {
    const c = putCommand(p, { dry: true });
    try {
      await execFileP(c.bin, c.args, { env: c.env });
      console.log(`  OK  ${c.bin} ${c.args.slice(0, 5).join(" ")} ...`);
    } catch (e) {
      console.log(`  NG  ${p.key}: ${String(e.stderr || e.message).split("\n")[0]}`);
    }
  }
  console.log("実行するには --execute を付ける。");
  process.exit(0);
}

if (backend === "aws") requireEnv("CLOUDFLARE_ACCOUNT_ID", "R2_S3_ACCESS_KEY_ID", "R2_S3_SECRET_ACCESS_KEY");

let existing = new Map();
if (has("skip-existing")) {
  let after;
  for (;;) {
    const a = ["r2", "objects", "list", "--bucket-name", bucket, "--per-page", "1000"];
    if (after) a.push("--start-after", after);
    const page = (await cf(a)) ?? [];
    for (const o of page) existing.set(o.key, o.size);
    if (page.length < 1000) break;
    after = page[page.length - 1].key;
  }
  console.log(`既存オブジェクト ${existing.size} 件を取得`);
}

let done = 0;
let skipped = 0;
const t0 = Date.now();
// immutable/mutable は並列、document は直列で最後 (index.html -> release.json)
for (const group of [["immutable", "mutable"], ["document"]]) {
  const items = plan.filter((p) => group.includes(p.cls));
  await pool(items, group[0] === "document" ? 1 : concurrency, async (p) => {
    if (p.cls === "immutable" && existing.get(p.key) === p.size) {
      skipped++;
      return;
    }
    await run(p, false);
    done++;
    if (done % 20 === 0) console.log(`  ... ${done}/${plan.length}`);
  });
}
console.log(`アップロード完了: ${done} 件 (skip ${skipped}) / ${((Date.now() - t0) / 1000).toFixed(1)}s`);

if (has("purge")) {
  const zone = opt("zone", process.env.CF_ZONE);
  const host = opt("host", process.env.CF_HOSTNAME);
  if (!zone || !host) throw new Error("--purge には --zone/--host が必要");
  const files = plan.filter((p) => p.cls !== "immutable").map((p) => `https://${host}/${p.key}`);
  files.push(`https://${host}/`);
  const zid = await zoneId(zone);
  for (let i = 0; i < files.length; i += 30) {
    // 1 リクエスト 30 URL まで (Free プラン上限に合わせる)
    await cf(["cache", "purge", "-z", zid, "--force", "--body", JSON.stringify({ files: files.slice(i, i + 30) })]);
  }
  console.log(`purge: ${files.length} URL`);
}
