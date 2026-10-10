#!/usr/bin/env node
// headless Chrome で probe ページを実行し結果 JSON を出力する。Access 配下は service token で 1 回認証 (CF_Authorization cookie 発行) 後 cookie のみで動かす。
//   node deploy/probe/run.mjs <url> [--token deploy/work/secrets/<name>.json] [--out result.json] [--timeout-min 10]
// puppeteer-core は tools/hosting/node_modules を使う (ルート package.json は不変)。プロファイルは実ディスク (deploy/work/) に置く。
import { createRequire } from "node:module";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";

const require = createRequire(path.resolve(import.meta.dirname, "../../tools/hosting/package.json"));
const puppeteer = require("puppeteer-core");
const args = process.argv.slice(2);
const opt = (n, d) => { const i = args.indexOf(`--${n}`); return i >= 0 ? args[i + 1] : d; };
const url = args[0];
if (!url || url.startsWith("--")) throw new Error("usage: run.mjs <url> [--token file] [--out file]");
const profileRoot = path.resolve(import.meta.dirname, "../work/chrome-profiles");
mkdirSync(profileRoot, { recursive: true });
const userDataDir = mkdtempSync(path.join(profileRoot, "p-"));
const browser = await puppeteer.launch({ executablePath: process.env.CHROME ?? "/usr/bin/google-chrome", userDataDir, headless: true, args: ["--no-sandbox"] });
const page = await browser.newPage();
await page.setCacheEnabled(false);
const logs = [], failed = [];
page.on("console", (m) => { if (["error", "warning"].includes(m.type())) logs.push(`${m.type()}: ${m.text()}`.slice(0, 300)); });
page.on("requestfailed", (q) => failed.push(`${q.url().slice(0, 140)} :: ${q.failure()?.errorText}`));
let doc = null;
page.on("response", (r) => {
  if (r.request().isNavigationRequest() && !doc) {
    const h = r.headers();
    doc = { status: r.status(), coop: h["cross-origin-opener-policy"], coep: h["cross-origin-embedder-policy"], corp: h["cross-origin-resource-policy"] };
  }
});
let result = null, err = null, access = null;
const t0 = Date.now();
try {
  if (opt("token")) {
    const tk = JSON.parse(readFileSync(opt("token"), "utf8"));
    await page.setExtraHTTPHeaders({ "CF-Access-Client-Id": tk.client_id, "CF-Access-Client-Secret": tk.client_secret });
    const r0 = await page.goto(new URL("/release.json", url).href, { waitUntil: "load", timeout: 90000 });
    await page.setExtraHTTPHeaders({});
    const ck = (await page.cookies()).find((c) => c.name === "CF_Authorization");
    access = { preauthStatus: r0?.status(), cookie: !!ck, httpOnly: ck?.httpOnly, secure: ck?.secure, sameSite: ck?.sameSite };
    doc = null;
  }
  await page.goto(url, { waitUntil: "load", timeout: 90000 });
  await page.waitForFunction(() => document.title === "probe-done", { timeout: Number(opt("timeout-min", 10)) * 60000, polling: 500 });
  result = await page.evaluate(() => window.__probe);
} catch (e) { err = String(e?.message ?? e); }
await browser.close();
rmSync(userDataDir, { recursive: true, force: true });
const summary = { url, wallSec: +((Date.now() - t0) / 1000).toFixed(1), access, doc, result, err, logs: logs.slice(0, 8), failed: failed.slice(0, 8) };
if (opt("out")) writeFileSync(opt("out"), JSON.stringify(summary, null, 1));
console.log(JSON.stringify(summary, null, 1));
const ok = !err && result?.main?.crossOriginIsolated && result.main.sab && result.worker?.crossOriginIsolated && result.worker.sab
  && result.worklet?.sab && result.small?.ct === "application/wasm" && result.chunked.length > 0 && result.chunked.every((c) => !c.error) && !result.errors.length;
console.log(ok ? "PROBE OK" : "PROBE NG");
process.exit(ok ? 0 : 1);
