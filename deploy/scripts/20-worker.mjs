#!/usr/bin/env node
// Workers Static Assets (Worker コード無し) を wrangler でデプロイする。
//   node deploy/scripts/20-worker.mjs --phase closed|open|release [--name N] [--site deploy/work/site] [--dry-run]
//
// 実測 (deploy/REPORT.md): workers.dev を有効化した直後、Access が効くまで数秒間 **無認証で 200** が返ることがある。
// そこで本物の asset は Access の 302 を確認してから載せる:
//   closed   workers_dev=false。**placeholder** asset (空の index.html) でデプロイ。Worker は存在するが URL が無い (Access の worker_id 取得用)
//   open     workers_dev=true。placeholder のまま公開 URL を作り、**無認証 302 になるまで待つ** (最大 180 秒、経過を表示)
//   release  workers_dev=true。本物の asset (--site) を載せる。Access 確認後なので無保護で公開される瞬間は無い
// 順序: closed -> (40-access.mjs --apply) -> open -> release
// 設定の正本は deploy/wrangler.jsonc。name / workers_dev / assets.directory だけ実行時に上書きし deploy/work/wrangler.<name>.jsonc に出す。
// 終了時、workers.dev の URL を deploy/work/<name>.url に書く。
import { spawnSync } from "node:child_process";
import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";

const DEPLOY = path.resolve(import.meta.dirname, "..");
const args = process.argv.slice(2);
const opt = (n, d) => {
  const i = args.indexOf(`--${n}`);
  return i >= 0 ? args[i + 1] : d;
};
const phase = opt("phase");
if (!["closed", "open", "release"].includes(phase)) throw new Error("--phase closed|open|release が必要");
const base = JSON.parse(readFileSync(path.join(DEPLOY, "wrangler.jsonc"), "utf8"));
const name = opt("name", process.env.WORKER_NAME ?? base.name);
const realSite = path.resolve(opt("site", path.join(DEPLOY, "work/site")));
const placeholder = path.join(DEPLOY, "work/placeholder");
if (phase !== "release") {
  rmSync(placeholder, { recursive: true, force: true });
  mkdirSync(placeholder, { recursive: true });
  writeFileSync(path.join(placeholder, "index.html"), "<!doctype html><title>placeholder</title>\n");
  writeFileSync(path.join(placeholder, "_headers"), "/*\n  Cross-Origin-Opener-Policy: same-origin\n  Cross-Origin-Embedder-Policy: require-corp\n  Cross-Origin-Resource-Policy: same-origin\n");
}
const site = phase === "release" ? realSite : placeholder;
const cfg = {
  ...base,
  name,
  workers_dev: phase !== "closed",
  preview_urls: false, // Access worker 型なら preview も保護されるが、そもそも発行しない (version URL は 404 になる: 実測)
  assets: { ...base.assets, directory: site, ...(process.env.ASSETS_HTML_HANDLING ? { html_handling: process.env.ASSETS_HTML_HANDLING } : {}) },
};
if (cfg.main) throw new Error("wrangler.jsonc に main がある: Worker コード無し (Static Assets のみ) が前提");
mkdirSync(path.join(DEPLOY, "work"), { recursive: true });
const file = path.join(DEPLOY, "work", `wrangler.${name}.jsonc`);
writeFileSync(file, JSON.stringify(cfg, null, 2));
console.log(`## wrangler deploy [${phase}] name=${name} site=${site}`);
const argv = ["wrangler", "deploy", "--config", file];
if (args.includes("--dry-run")) argv.push("--dry-run");
const r = spawnSync("bunx", argv, { cwd: DEPLOY, encoding: "utf8", env: { ...process.env, NO_COLOR: "1", FORCE_COLOR: "0" }, maxBuffer: 64 * 1024 * 1024 });
const text = `${r.stdout}${r.stderr}`.replace(/\x1b\[[0-9;]*m/g, "");
process.stdout.write(text);
if (r.status !== 0) process.exit(r.status ?? 1);
const m = text.match(new RegExp(`https://${name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\.([a-z0-9-]+)\\.workers\\.dev`));
if (phase !== "closed" && !args.includes("--dry-run")) {
  if (!m) throw new Error("workers.dev URL を出力から取得できなかった");
  writeFileSync(path.join(DEPLOY, "work", `${name}.url`), `${m[0]}\n`);
  console.log(`URL: ${m[0]}`);
  if (phase === "open") {
    // 無認証アクセスが Access の 302 になるまで待つ (placeholder しか載っていないので、途中の 200 は無害)
    const seen = [];
    const t0 = Date.now();
    let ok = false;
    while (Date.now() - t0 < 180000) {
      let st;
      try { st = (await fetch(`${m[0]}/`, { redirect: "manual" })).status; } catch (e) { st = `ERR`; }
      if (seen.at(-1)?.[0] !== st) seen.push([st, ((Date.now() - t0) / 1000).toFixed(1)]);
      if (st === 302) { ok = true; break; }
      await new Promise((r) => setTimeout(r, 1000));
    }
    console.log(`公開直後の無認証応答の推移 [status, 経過秒]: ${JSON.stringify(seen)}`);
    if (!ok) throw new Error("180 秒待っても Access の 302 にならない: 本物の asset は載せない (release しないこと)");
  }
}
