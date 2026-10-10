// run-probe.mjs <name> <url> [--runs N]  — headless Chrome (/usr/bin/google-chrome) で probe ページを実行し、結果 JSON を work/results/<name>.json に保存・要約表示する
import fs from 'node:fs';
import path from 'node:path';
import puppeteer from 'puppeteer-core';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.resolve(here, '../work/results');
fs.mkdirSync(OUT, { recursive: true });
const [name, url, ...rest] = process.argv.slice(2);
if (!name || !url) { console.error('usage: run-probe.mjs <name> <url> [--runs N]'); process.exit(2); }
const runs = Number(rest[rest.indexOf('--runs') + 1] || 1) || 1;
const chrome = process.env.CHROME ?? '/usr/bin/google-chrome';
// プロファイル (OPFS/Cache Storage の実体) の置き場。既定は work/ (実ディスク)。PROFILE_DIR=/tmp 等 (tmpfs) だと空き容量不足で OPFS 書込が失敗しうる
const profileRoot = process.env.PROFILE_DIR ?? path.resolve(here, '../work');
fs.mkdirSync(profileRoot, { recursive: true });

const all = [];
for (let r = 0; r < runs; r++) {
  const userDataDir = fs.mkdtempSync(path.join(profileRoot, 'chrome-profile-'));
  const browser = await puppeteer.launch({ executablePath: chrome, userDataDir, headless: true, args: ['--no-sandbox', '--autoplay-policy=no-user-gesture-required', '--disable-features=PrivateNetworkAccessChecks'] });
  const page = await browser.newPage();
  await page.setCacheEnabled(false);
  const logs = [], failed = [];
  page.on('console', (m) => { if (['error', 'warning'].includes(m.type())) logs.push(`${m.type()}: ${m.text()}`.slice(0, 300)); });
  page.on('requestfailed', (q) => failed.push(`${q.method()} ${q.url().slice(0, 140)} :: ${q.failure()?.errorText}`));
  let docHdr = null;
  page.on('response', (res) => {
    if (res.request().isNavigationRequest() && !docHdr) {
      const h = res.headers();
      docHdr = { status: res.status(), coop: h['cross-origin-opener-policy'], coep: h['cross-origin-embedder-policy'], corp: h['cross-origin-resource-policy'], server: h['server'], cfRay: h['cf-ray'] };
    }
  });
  const t0 = Date.now();
  let result = null, err = null, accessCookie = null;
  try {
    if (process.env.CF_ACCESS_FILE) {
      // Access 配下の検証: service token ヘッダで 1 回だけ認証 -> CF_Authorization cookie を取得し、以降は cookie のみで動かす
      const tk = JSON.parse(fs.readFileSync(process.env.CF_ACCESS_FILE, 'utf8'));
      await page.setExtraHTTPHeaders({ 'CF-Access-Client-Id': tk.client_id, 'CF-Access-Client-Secret': tk.client_secret });
      const r0 = await page.goto(new URL('/', url).href, { waitUntil: 'load', timeout: 60000 });
      await page.setExtraHTTPHeaders({});
      const ck = (await page.cookies()).find((c) => c.name === 'CF_Authorization');
      accessCookie = { preauthStatus: r0?.status(), cookie: !!ck, httpOnly: ck?.httpOnly, sameSite: ck?.sameSite, secure: ck?.secure, expiresInMin: ck ? Math.round((ck.expires - Date.now() / 1000) / 60) : null };
    }
    await page.goto(url, { waitUntil: 'load', timeout: 60000 });
    await page.waitForFunction(() => document.title === 'probe-done', { timeout: 600000, polling: 500 });
    result = await page.evaluate(() => window.__probe);
  } catch (e) { err = String(e?.message ?? e); }
  await browser.close();
  fs.rmSync(userDataDir, { recursive: true, force: true });
  all.push({ run: r, accessCookie, wallSec: +((Date.now() - t0) / 1000).toFixed(1), docHdr, result, err, logs: logs.slice(0, 8), failed: failed.slice(0, 8) });
}
fs.writeFileSync(path.join(OUT, `${name}.json`), JSON.stringify({ name, url, runs: all }, null, 1));

// 要約
const pick = (r) => {
  const p = r.result, w = p?.worker ?? {}, m = p?.main ?? {};
  return {
    run: r.run, wallSec: r.wallSec, accessCookie: r.accessCookie, err: r.err ?? p?.fatal ?? w?.error,
    doc: r.docHdr && `${r.docHdr.status} coop=${r.docHdr.coop} coep=${r.docHdr.coep}`,
    isolated: `main=${m.crossOriginIsolated} worker=${w.worker?.crossOriginIsolated} sab=${m.sabAlloc}`,
    worklet: m.worklet && (m.worklet.error ?? `iso=${m.worklet.crossOriginIsolated} sab=${m.worklet.sab} seen=${m.worklet.sabSeenByMain} kind=${m.worklet.kind}`),
    imgNoCors: m.imgNoCors,
    full: w.fullGet && (w.fullGet.error ?? `${w.fullGet.status} ${w.fullGet.MBps}MB/s ttfb=${w.fullGet.ttfbMs}ms bad=${w.fullGet.badPieces} bytes=${w.fullGet.bytes}`),
    range: w.range && (w.range.error ?? Object.fromEntries(Object.entries(w.range).filter(([k]) => k !== 'ms').map(([k, v]) => [k, v.error ?? `${v.status}${v.same ? '✓' : '✗'}`]))),
    rangePar: w.rangeParallel && (w.rangeParallel.error ?? `${JSON.stringify(w.rangeParallel.statuses)} bad=${w.rangeParallel.badPieces} ${w.rangeParallel.MBps}MB/s`),
    chunks: w.chunks && (w.chunks.error ?? `n=${w.chunks.n} st=${JSON.stringify(w.chunks.statuses)} bad=${w.chunks.badIds} ${w.chunks.MBps}MB/s ${w.chunks.reqPerSec}req/s p50=${w.chunks.p50ms}ms p95=${w.chunks.p95ms}ms cacheStorage=${w.chunks.cacheStorageHit}`),
    ext: w.ext && Object.fromEntries(Object.entries(w.ext).filter(([k]) => k !== 'ms').map(([k, v]) => [k, v.error ?? `${v.status} ${v.ct} ce=${v.ce} ${v.bytes}/${v.expected}`])),
    cond: w.conditional && (w.conditional.error ?? `etag=${!!w.conditional.etag} inm=${w.conditional.ifNoneMatchStatus} 404=${w.conditional.status404}`),
    wasm: w.wasmStreaming && (w.wasmStreaming.error ?? `ok=${w.wasmStreaming.ok} ct=${w.wasmStreaming.ct}`),
    wasmParts: w.wasmParts && (w.wasmParts.error ?? `ok=${w.wasmParts.ok} parts=${w.wasmParts.parts} ${w.wasmParts.sec}s`),
    noCorsFetch: w.noCorsFetch && (w.noCorsFetch.error ?? `${w.noCorsFetch.type}`),
    headBig: w.headBig && (w.headBig.error ?? JSON.stringify(w.headBig.headers)),
    logs: r.logs, failed: r.failed,
  };
};
console.log(JSON.stringify({ name, url, runs: all.map(pick) }, null, 1));
