#!/usr/bin/env node
// PERF-P13 (#952) 大物 (>24MiB) wasm の配信計測: 事前非圧縮 part 連結 (deploy/client/chunked.mjs) × compileStreaming × instantiate。
//   node tools/perf/delivery/chunked_bench.mjs [--mib 32] [--wasm <実 wasm パス>] [--reps 3] [--mbps 0,100] [--out tools/perf/results/chunked.json]
//   --wasm 指定時は合成 wasm を作らず、その実ファイル (例: tools/flelift/work/lift/flel.wasm) を入力にする。
// 手順: 合成 wasm 生成 → deploy/scripts/05-stage.mjs で 16MiB part 分割 (--max-file 24MiB) → 静的サーバ (COOP/COEP 付き) →
// headless Chrome で descriptor を chunkedResponse で連結し compileStreaming → instantiate → f0()==42 を計測。
// 素材は合成 wasm (関数 ~360B のコード様バイト列。実 FLEngine wasm ではない)。
import http from "node:http";
import { createReadStream, existsSync, mkdirSync, readFileSync, statSync, writeFileSync, rmSync } from "node:fs";
import { execFileSync } from "node:child_process";
import os from "node:os";
import path from "node:path";
import { launchChrome } from "../../runtime/lib/chrome.mjs";

const here = import.meta.dirname;
const repo = path.resolve(here, "../../..");
const args = process.argv.slice(2);
const opt = (n, d) => { const i = args.indexOf(`--${n}`); return i >= 0 ? args[i + 1] : d; };
const MIB = Number(opt("mib", 32));
const REPS = Number(opt("reps", 3));
const MBPS = opt("mbps", "0").split(",").map(Number); // 0 = 無制限 (loopback)
const OUT = path.resolve(opt("out", path.join(here, "../results/chunked.json")));
const WORK = path.join(repo, "tools/perf/work/chunked");
const SRC = path.join(WORK, "src");
const SITE = path.join(WORK, "site");
rmSync(WORK, { recursive: true, force: true });
mkdirSync(path.join(SRC, "wasm"), { recursive: true });

// ---- 合成 wasm (全関数 () -> i32、f0 は 42) ----
const leb = (n) => { const o = []; do { let b = n & 0x7f; n >>>= 7; if (n) b |= 0x80; o.push(b); } while (n); return o; };
const sleb = (n) => { const o = []; for (;;) { const b = n & 0x7f; n >>= 7; if ((n === 0 && !(b & 0x40)) || (n === -1 && (b & 0x40))) { o.push(b); return o; } o.push(b | 0x80); } };
const sect = (id, body) => [id, ...leb(body.length), ...body];
function genWasm(targetBytes, bodyBytes = 360) {
  let seed = 0x9e3779b9;
  const rnd = (n) => { seed ^= seed << 13; seed >>>= 0; seed ^= seed >>> 17; seed ^= seed << 5; seed >>>= 0; return seed % n; };
  const nfun = Math.floor(targetBytes / (bodyBytes + 3));
  const bodies = [];
  for (let f = 0; f < nfun; f++) {
    const b = [1, 4, 0x7f];
    while (b.length < bodyBytes) {
      const l = rnd(4), l2 = rnd(4);
      switch (rnd(5)) {
        case 0: b.push(0x20, l, 0x41, ...sleb(rnd(4096) - 2048), 0x6a, 0x21, l2); break;
        case 1: b.push(0x41, ...sleb(rnd(65000)), 0x28, 2, ...leb(rnd(64) * 4), 0x21, l); break;
        case 2: b.push(0x20, l, 0x20, l2, 0x73, 0x41, ...sleb(rnd(255)), 0x71, 0x21, l); break;
        case 3: b.push(0x41, ...sleb(rnd(65000)), 0x20, l, 0x36, 2, ...leb(rnd(64) * 4)); break;
        default: b.push(0x20, l, 0x41, rnd(31) + 1, 0x74, 0x20, l2, 0x72, 0x21, l2);
      }
    }
    b.push(0x41, f === 0 ? 42 : 0, 0x0b);
    bodies.push([...leb(b.length), ...b]);
  }
  return Buffer.from([
    0x00, 0x61, 0x73, 0x6d, 1, 0, 0, 0,
    ...sect(1, [1, 0x60, 0, 1, 0x7f]),
    ...sect(3, [...leb(nfun), ...Array(nfun).fill(0)]),
    ...sect(5, [1, 0, 1]),
    ...sect(7, [1, 2, 0x66, 0x30, 0, 0]),
    ...sect(10, [...leb(nfun), ...bodies.flat()]),
  ]);
}

const WASM_IN = opt("wasm", "");
const raw = WASM_IN ? readFileSync(path.resolve(WASM_IN)) : genWasm(MIB * 1024 * 1024);
const sha12 = (await import("node:crypto")).createHash("sha256").update(raw).digest("hex").slice(0, 12);
const ASSET = `big.${sha12}.wasm`;
writeFileSync(path.join(SRC, "wasm", ASSET), raw);
writeFileSync(path.join(SRC, "index.html"), "<!doctype html><title>chunked</title>");
execFileSync("node", [path.join(repo, "deploy/scripts/05-stage.mjs"), "--src", SRC, "--out", SITE, "--max-file", String(24 * 1048576), "--part-size", String(16 * 1048576), "--skip-notices-gate", "--skip-release-guard"], { stdio: "pipe" });
const desc = JSON.parse(readFileSync(path.join(SITE, `wasm/${ASSET}.parts/index.json`), "utf8"));
if (existsSync(path.join(SITE, `wasm/${ASSET}`))) throw new Error("元ファイルが残っている (分割されていない)");
console.log(`[chunked] ${raw.length} B (${(raw.length / 1048576).toFixed(1)} MiB) → ${desc.parts.length} parts (sha ${sha12})`);

// ---- 静的サーバ: site + deploy/client (ES module) + bench page ----
const ROUTES = { "/client/": path.join(repo, "deploy/client") };
const PAGE = `<!doctype html><meta charset="utf-8"><title>chunked-bench</title><script type="module" src="/bench.mjs"></script>`;
const BENCH_JS = `
import { chunkedResponse } from "/client/chunked.mjs";
window.runOnce = async (url, mode) => {
  const t0 = performance.now();
  const res = await chunkedResponse(url, { concurrency: 6 });
  const mod = mode === "streaming" ? await WebAssembly.compileStreaming(res) : await WebAssembly.compile(await res.arrayBuffer());
  const tCompiled = performance.now();
  const imports = {};
  for (const i of WebAssembly.Module.imports(mod)) {
    if (i.kind !== "function") throw new Error(\`unsupported import kind=\${i.kind} \${i.module}.\${i.name}\`);
    (imports[i.module] ??= {})[i.name] = () => 0;
  }
  const inst = await WebAssembly.instantiate(mod, imports);
  const tInst = performance.now();
  const f0 = typeof inst.exports.f0 === "function" ? inst.exports.f0() : null;
  return { fetchCompileMs: +(tCompiled - t0).toFixed(1), instantiateMs: +(tInst - tCompiled).toFixed(1), totalMs: +(tInst - t0).toFixed(1), f0, exports: WebAssembly.Module.exports(mod).length };
};
`;
// 帯域は接続ごとに掛かる (part 並列取得は接続数ぶん合算される)。計測条件ごとに切替える
let currentMbps = 0;
const srv = http.createServer((req, res) => {
  const u = new URL(req.url, "http://x");
  const hdr = { "cross-origin-opener-policy": "same-origin", "cross-origin-embedder-policy": "require-corp", "cross-origin-resource-policy": "same-origin", "cache-control": "no-store" };
  if (u.pathname === "/") { res.writeHead(200, { ...hdr, "content-type": "text/html" }).end(PAGE); return; }
  if (u.pathname === "/bench.mjs") { res.writeHead(200, { ...hdr, "content-type": "text/javascript" }).end(BENCH_JS); return; }
  const mbps = currentMbps;
  for (const [prefix, dir] of Object.entries(ROUTES)) {
    if (u.pathname.startsWith(prefix)) {
      const f = path.join(dir, u.pathname.slice(prefix.length));
      if (!existsSync(f)) { res.writeHead(404).end(); return; }
      res.writeHead(200, { ...hdr, "content-type": "text/javascript" });
      createReadStream(f).pipe(res);
      return;
    }
  }
  const f = path.join(SITE, decodeURIComponent(u.pathname));
  if (!f.startsWith(SITE) || !existsSync(f) || !statSync(f).isFile()) { res.writeHead(404).end(); return; }
  const size = statSync(f).size;
  res.writeHead(200, { ...hdr, "content-type": f.endsWith(".wasm") ? "application/wasm" : f.endsWith(".json") ? "application/json" : "application/octet-stream", "content-length": size });
  if (!mbps) { createReadStream(f).pipe(res); return; }
  // 帯域制限 (10ms 刻み): 線上の総バイトに掛かる
  const per10ms = Math.floor((mbps * 1e6) / 8 / 100);
  const buf = readFileSync(f);
  let off = 0;
  const tick = () => {
    if (res.destroyed) return;
    if (off >= buf.length) { res.end(); return; }
    res.write(buf.subarray(off, off + per10ms));
    off += per10ms;
    setTimeout(tick, 10);
  };
  tick();
});
await new Promise((r) => srv.listen(0, "127.0.0.1", r));
const base = `http://127.0.0.1:${srv.address().port}`;

const chrome = await launchChrome();
const rows = [];
const med = (a) => { const s = [...a].sort((x, y) => x - y); return s[Math.floor(s.length / 2)]; };
try {
  for (const mbps of MBPS) {
    currentMbps = mbps;
    for (const mode of ["streaming", "bytes"]) {
      for (let rep = 0; rep < REPS; rep++) {
        const load1 = os.loadavg()[0];
        const page = await chrome.newPage(`${base}/`);
        const url = JSON.stringify(`/wasm/${ASSET}.parts/index.json`);
        const r = await page.evaluate(`(async () => { for (let i = 0; i < 200 && !window.runOnce; i++) await new Promise((s) => setTimeout(s, 25)); return window.runOnce(${url}, ${JSON.stringify(mode)}); })()`, { timeout: 300000 });
        rows.push({ mbps, mode, rep, loadavg1: +load1.toFixed(2), ...r });
        console.log(`mbps=${String(mbps).padStart(3)} ${mode.padEnd(9)} rep${rep}: fetch+compile ${String(r.fetchCompileMs).padStart(8)} ms  inst ${String(r.instantiateMs).padStart(6)} ms  total ${String(r.totalMs).padStart(8)} ms  f0=${r.f0} (load ${load1.toFixed(2)})`);
        try { await chrome.browser.send("Target.closeTarget", { targetId: page.targetId }); } catch {}
      }
    }
  }
  const summary = [];
  for (const mbps of MBPS) for (const mode of ["streaming", "bytes"]) {
    const g = rows.filter((r) => r.mbps === mbps && r.mode === mode);
    const t = g.map((x) => x.totalMs);
    summary.push({ mbps, mode, medianTotalMs: med(t), minTotalMs: Math.min(...t), maxTotalMs: Math.max(...t), medianFetchCompileMs: med(g.map((x) => x.fetchCompileMs)) });
  }
  console.log("\n要約 (total = fetch→compile→instantiate, ms 中央値 (min–max)):");
  for (const s of summary) console.log(`  mbps=${String(s.mbps).padStart(3)} ${s.mode.padEnd(9)} ${String(s.medianTotalMs).padStart(8)} (${s.minTotalMs}–${s.maxTotalMs})`);
  // 合成 wasm: f0()==42 を判定。実 wasm (--wasm): f0 は無いので instantiate 成功 + export>0 を判定
  const ok = rows.filter((r) => (WASM_IN ? r.exports > 0 : r.f0 === 42 && r.exports > 0));
  mkdirSync(path.dirname(OUT), { recursive: true });
  writeFileSync(OUT, JSON.stringify({ src: WASM_IN ? path.basename(WASM_IN) : "synthetic", chrome: chrome.version, node: process.version, cpus: os.cpus().length, wasmBytes: raw.length, parts: desc.parts.length, partSize: desc.partSize, reps: REPS, rows, summary }, null, 1));
  if (ok.length !== rows.length) { console.log(`FAIL: ${rows.length - ok.length} 件で判定不合格`); process.exitCode = 1; }
  else console.log(`\nPASS: ${rows.length}/${rows.length} 件 (${WASM_IN ? "instantiate 成功" : "f0()==42"})`);
} finally {
  await chrome.close();
  srv.close();
  srv.closeAllConnections?.();
}
