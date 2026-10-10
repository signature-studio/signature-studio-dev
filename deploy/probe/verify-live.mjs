#!/usr/bin/env node
// 実デプロイ URL に対する隔离 (crossOriginIsolated / SAB) の実機検証。CAB-35 用 (deploy/probe/run.mjs の production 版)。
//   node deploy/probe/verify-live.mjs <url> [--token deploy/work/secrets/<name>.json] [--boot m1-hello|all|none] [--pumpN 2000] [--out file]
//
// 検査 (全部 PASS で exit 0):
//   1. main: crossOriginIsolated === true かつ new SharedArrayBuffer() 成功
//   2. module Worker (blob, 同一 origin = 同一 COI agent cluster): crossOriginIsolated + SAB 生成
//   3. 実配備の module Worker (assets/worker-*.js) を ?runtime=<boot>&pumpN=<N> で起動:
//      - manifest (/wasm/manifest.json) から wasm を Worker 内 fetch/compile して driver 実行 (m1-hello は stdout 突合)
//      - pump self-test: main⇔Worker の SAB リング + Atomics.wait ブロッキング (blockedWaits>0, canBlock=true)
//      AudioWorklet SAB は tools/e2e の audioworklet check が担当 (別実施)。
// プロファイルは実ディスク (deploy/work/chrome-profiles) に置く (OPFS/tmpfs 制約)。
import { createRequire } from "node:module";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";

const require = createRequire(path.resolve(import.meta.dirname, "../../tools/hosting/package.json"));
const puppeteer = require("puppeteer-core");
const args = process.argv.slice(2);
const opt = (n, d) => { const i = args.indexOf(`--${n}`); return i >= 0 ? args[i + 1] : d; };
const url = args[0];
if (!url || url.startsWith("--")) throw new Error("usage: verify-live.mjs <url> [--token file] [--boot m1-hello|all|none] [--pumpN 2000] [--out file]");
const boot = opt("boot", "m1-hello");
const pumpN = Number(opt("pumpN", 2000));

const profileRoot = path.resolve(import.meta.dirname, "../work/chrome-profiles");
mkdirSync(profileRoot, { recursive: true });
const userDataDir = mkdtempSync(path.join(profileRoot, "v-"));
const browser = await puppeteer.launch({ executablePath: process.env.CHROME ?? "/usr/bin/google-chrome", userDataDir, headless: true, args: ["--no-sandbox"] });
const page = await browser.newPage();
await page.setCacheEnabled(false);
const logs = [];
page.on("console", (m) => logs.push(`${m.type()}: ${m.text()}`.slice(0, 220)));

const failures = [];
const check = (name, ok, detail = "") => { if (!ok) failures.push(name); console.log(`${ok ? "ok " : "NG "} ${name}${detail ? ` — ${detail}` : ""}`); };

let access = null;
if (opt("token")) {
  const tk = JSON.parse(readFileSync(opt("token"), "utf8"));
  await page.setExtraHTTPHeaders({ "CF-Access-Client-Id": tk.client_id, "CF-Access-Client-Secret": tk.client_secret });
  const r0 = await page.goto(new URL("/release.json", url).href, { waitUntil: "load", timeout: 90000 });
  await page.setExtraHTTPHeaders({});
  const ck = (await page.cookies()).find((c) => c.name === "CF_Authorization");
  access = { preauthStatus: r0?.status(), cookie: !!ck };
  check("service token 認証 (CF_Authorization cookie 発行)", !!ck, `preauth=${r0?.status()}`);
}

// 1) main + 2) blob module Worker
await page.goto(url, { waitUntil: "load", timeout: 90000 });
const main = await page.evaluate(async () => {
  const sab = (() => { try { new SharedArrayBuffer(16); return true; } catch { return false; } })();
  const w = await new Promise((resolve) => {
    const src = "self.onmessage = (e) => { let sab = false; try { new SharedArrayBuffer(16); sab = true; } catch {} postMessage({ coi: self.crossOriginIsolated, sab, type: self.constructor.name }); };";
    const wk = new Worker(URL.createObjectURL(new Blob([src], { type: "text/javascript" })), { type: "module" });
    wk.onmessage = (ev) => { resolve(ev.data); wk.terminate(); };
    wk.postMessage({});
  });
  return { coi: crossOriginIsolated, sab, secure: isSecureContext, worker: w };
});
check("main: crossOriginIsolated=true", main.coi === true, `secure=${main.secure}`);
check("main: SharedArrayBuffer 生成", main.sab === true);
check("module Worker: crossOriginIsolated=true", main.worker?.coi === true, `type=${main.worker?.type}`);
check("module Worker: SharedArrayBuffer 生成", main.worker?.sab === true);

// 3) 実配備 module Worker での boot + pump self-test (SAB リング)
let report = null;
if (boot !== "none") {
  const u = new URL(url);
  u.search = `?runtime=${boot}&pump=1&pumpN=${pumpN}`;
  await page.goto(u.href, { waitUntil: "load", timeout: 90000 });
  try {
    await page.waitForFunction(() => window.__runtime && window.__runtime.state !== "running", { timeout: 180000, polling: 500 });
    report = await page.evaluate(() => window.__runtime);
  } catch (e) {
    failures.push("runtime boot: state が done/error にならない (timeout)");
    report = { state: "timeout", error: String(e?.message ?? e), runs: [] };
  }
  check(`runtime boot (${boot}): state=done`, report.state === "done", report.error ?? "");
  const runs = report.runs ?? [];
  for (const r of runs) {
    const bad = (r.checks ?? []).filter((c) => !c.ok);
    check(`boot ${r.id}: checks 全 ok`, r.ok === true && bad.length === 0, r.ok ? `total ${r.timings?.totalMs}ms` : bad.map((c) => `${c.name}: ${c.detail}`).join(" | ").slice(0, 200));
  }
  if (report.pump) {
    check("pump self-test (SAB リング + Atomics.wait): blockedWaits>0 / canBlock / dropped=0",
      report.pump.blockedWaits > 0 && report.pump.canBlock === true && report.pump.dropped === 0,
      `received=${report.pump.received} timers=${report.pump.timers} blockedWaits=${report.pump.blockedWaits} p50=${report.pump.latency.p50}ms p99=${report.pump.latency.p99}ms`);
  } else {
    check("pump self-test 実施", false, "report.pump が無い");
  }
}

// boot panel のログ (Worker からの postMessage を pre に表示)。実配備 module Worker の cOI=true をここで確認
const panelText = await page.evaluate(() => [...document.querySelectorAll("pre")].map((p) => p.textContent).join("\n"));
const workerLog = (panelText.match(/\[worker\][^\n]*cOI=true[^\n]*/) ?? [])[0] ?? null;
check("Worker 内ログ cOI=true (実配備 module Worker)", !!workerLog, workerLog ?? (panelText.slice(0, 150) || "(log 無し)"));
await browser.close();
rmSync(userDataDir, { recursive: true, force: true });

const summary = { url: String(url), boot, pumpN, access, main, report, panelText: panelText.slice(0, 2000), failures };
if (opt("out")) writeFileSync(opt("out"), JSON.stringify(summary, null, 1));
console.log(failures.length ? `LIVE NG: ${failures.join(", ")}` : "LIVE OK");
process.exit(failures.length ? 1 : 0);
