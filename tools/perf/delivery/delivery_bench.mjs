#!/usr/bin/env node
// PERF-P10 (#170) 配信形態の計測: Content-Encoding: br (q11 事前圧縮) × compileStreaming × 帯域制限。
//   node tools/perf/delivery/delivery_bench.mjs [--mib 16] [--reps 3] [--mbps 100,0] [--out tools/perf/results/delivery.json]
// 素材は合成 wasm (関数 ~360B のコード様バイト列, 実 lift wasm ではない → 圧縮率は参考値。実 lift wasm の比は results/compress.md)。
// 帯域制限は「線上に流れるバイト数」に掛かる (br なら圧縮後)。展開は Chrome ネットワークスタックの Content-Encoding 復号。
import http from "node:http";
import { createReadStream, existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { brotliCompressSync, constants as zc } from "node:zlib";
import { createHash } from "node:crypto";
import os from "node:os";
import path from "node:path";
import { launchChrome } from "../../runtime/lib/chrome.mjs";

const here = import.meta.dirname;
const args = process.argv.slice(2);
const opt = (n, d) => { const i = args.indexOf(`--${n}`); return i >= 0 ? args[i + 1] : d; };
const MIB = Number(opt("mib", 16));
const REPS = Number(opt("reps", 3));
const MBPS = opt("mbps", "100,0").split(",").map(Number); // 0 = 無制限
const OUT = path.resolve(opt("out", path.join(here, "../results/delivery.json")));
const WORK = path.join(here, "../work/delivery");
mkdirSync(WORK, { recursive: true });

// ---- 合成 wasm: N 関数 × 約 360B。全関数 () -> i32、stack 中立な命令列で validate を通る (f0 は 42 を返す) ----
const leb = (n) => { const o = []; do { let b = n & 0x7f; n >>>= 7; if (n) b |= 0x80; o.push(b); } while (n); return o; };
const sleb = (n) => { const o = []; for (;;) { const b = n & 0x7f; n >>= 7; if ((n === 0 && !(b & 0x40)) || (n === -1 && (b & 0x40))) { o.push(b); return o; } o.push(b | 0x80); } };
const sect = (id, body) => [id, ...leb(body.length), ...body];
function genWasm(targetBytes, bodyBytes = 360) {
  let seed = 0x9e3779b9;
  const rnd = (n) => { seed ^= seed << 13; seed >>>= 0; seed ^= seed >>> 17; seed ^= seed << 5; seed >>>= 0; return seed % n; };
  const nfun = Math.floor(targetBytes / (bodyBytes + 3));
  const bodies = [];
  for (let f = 0; f < nfun; f++) {
    const b = [1, 4, 0x7f]; // 4 × i32 locals
    while (b.length < bodyBytes) {
      const l = rnd(4), l2 = rnd(4);
      switch (rnd(5)) {
        case 0: b.push(0x20, l, 0x41, ...sleb(rnd(4096) - 2048), 0x6a, 0x21, l2); break;           // local.get; i32.const; i32.add; local.set
        case 1: b.push(0x41, ...sleb(rnd(65000)), 0x28, 2, ...leb(rnd(64) * 4), 0x21, l); break;  // i32.const; i32.load; local.set
        case 2: b.push(0x20, l, 0x20, l2, 0x73, 0x41, ...sleb(rnd(255)), 0x71, 0x21, l); break;   // xor; and
        case 3: b.push(0x41, ...sleb(rnd(65000)), 0x20, l, 0x36, 2, ...leb(rnd(64) * 4)); break;  // i32.store
        default: b.push(0x20, l, 0x41, rnd(31) + 1, 0x74, 0x20, l2, 0x72, 0x21, l2);              // shl; or
      }
    }
    b.push(0x41, f === 0 ? 42 : 0, 0x0b);
    bodies.push([...leb(b.length), ...b]);
  }
  const bytes = [
    0x00, 0x61, 0x73, 0x6d, 1, 0, 0, 0,
    ...sect(1, [1, 0x60, 0, 1, 0x7f]),
    ...sect(3, [...leb(nfun), ...Array(nfun).fill(0)]),
    ...sect(5, [1, 0, 1]),
    ...sect(7, [1, 2, 0x66, 0x30, 0, 0]),
    ...sect(10, [...leb(nfun), ...bodies.flat()]),
  ];
  return Buffer.from(bytes);
}

const wasmPath = path.join(WORK, `synthetic_${MIB}MiB.wasm`);
const brPath = `${wasmPath}.br`;
if (!existsSync(wasmPath)) writeFileSync(wasmPath, genWasm(MIB * 1024 * 1024));
const raw = readFileSync(wasmPath);
const sha = createHash("sha256").update(raw).digest("hex").slice(0, 12);
let tBr = 0;
if (!existsSync(brPath)) {
  const t0 = performance.now();
  writeFileSync(brPath, brotliCompressSync(raw, { params: { [zc.BROTLI_PARAM_QUALITY]: 11, [zc.BROTLI_PARAM_LGWIN]: 24, [zc.BROTLI_PARAM_SIZE_HINT]: raw.length } }));
  tBr = performance.now() - t0;
}
const rawSize = statSync(wasmPath).size, brSize = statSync(brPath).size;
console.log(`[delivery] synthetic wasm ${rawSize} B (sha ${sha}) → br-11 ${brSize} B (${((brSize / rawSize) * 100).toFixed(1)}%)${tBr ? ` 圧縮 ${(tBr / 1000).toFixed(1)}s` : " (キャッシュ済み)"}`);

// ---- サーバ: ?enc=br|id & ?mbps=N (線上バイトの帯域制限, 10ms 刻み) ----
const srv = http.createServer((req, res) => {
  const u = new URL(req.url, "http://x");
  if (u.pathname === "/") {
    res.writeHead(200, { "content-type": "text/html", "cross-origin-opener-policy": "same-origin", "cross-origin-embedder-policy": "require-corp" });
    res.end("<!doctype html><title>delivery</title>");
    return;
  }
  if (u.pathname !== "/m.wasm") { res.writeHead(404); res.end(); return; }
  const br = u.searchParams.get("enc") === "br" && /\bbr\b/.test(String(req.headers["accept-encoding"] ?? ""));
  const file = br ? brPath : wasmPath;
  const size = statSync(file).size;
  const h = { "content-type": "application/wasm", "content-length": size, "cache-control": "no-store", "cross-origin-resource-policy": "same-origin", "cross-origin-embedder-policy": "require-corp" };
  if (br) { h["content-encoding"] = "br"; h.vary = "accept-encoding"; }
  res.writeHead(200, h);
  const mbps = Number(u.searchParams.get("mbps") || 0);
  if (!mbps) { createReadStream(file).pipe(res); return; }
  const per10ms = Math.floor((mbps * 1e6) / 8 / 100);
  const buf = readFileSync(file);
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
const port = srv.address().port;

const PAGE_JS = (url, mode) => `(async () => {
  const t0 = performance.now();
  const r = await fetch(${JSON.stringify(url)}, { cache: "no-store" });
  if (!r.ok) throw new Error("HTTP " + r.status);
  let mod;
  if (${JSON.stringify(mode)} === "streaming") mod = await WebAssembly.compileStreaming(r);
  else mod = await WebAssembly.compile(await r.arrayBuffer());
  const tCompiled = performance.now();
  const inst = await WebAssembly.instantiate(mod, {});
  const f0 = inst.exports.f0();
  const e = performance.getEntriesByType("resource").filter((x) => x.name.includes("/m.wasm")).pop();
  return { ms: +(tCompiled - t0).toFixed(1), f0, wire: e.encodedBodySize, decoded: e.decodedBodySize, transfer: e.transferSize, exports: WebAssembly.Module.exports(mod).length };
})()`;

const chrome = await launchChrome();
const rows = [];
try {
  for (const mbps of MBPS) {
    for (const enc of ["id", "br"]) {
      for (const mode of ["streaming", "bytes"]) {
        for (let rep = 0; rep < REPS; rep++) {
          const page = await chrome.newPage(`http://127.0.0.1:${port}/`);
          const load1 = os.loadavg()[0];
          const r = await page.evaluate(PAGE_JS(`/m.wasm?enc=${enc}&mbps=${mbps}`, mode), { timeout: 300000 });
          rows.push({ mbps, enc, mode, rep, loadavg1: +load1.toFixed(2), ...r });
          console.log(`mbps=${String(mbps).padStart(3)} enc=${enc.padEnd(2)} ${mode.padEnd(9)} rep${rep}: ${String(r.ms).padStart(8)} ms  wire=${r.wire} decoded=${r.decoded} f0=${r.f0} (load ${load1.toFixed(2)})`);
          try { await chrome.browser.send("Target.closeTarget", { targetId: page.targetId }); } catch {}
        }
      }
    }
  }
  const chromeVer = chrome.version;
  const med = (a) => { const s = [...a].sort((x, y) => x - y); return s[Math.floor(s.length / 2)]; };
  const summary = [];
  for (const mbps of MBPS) for (const enc of ["id", "br"]) for (const mode of ["streaming", "bytes"]) {
    const g = rows.filter((r) => r.mbps === mbps && r.enc === enc && r.mode === mode);
    summary.push({ mbps, enc, mode, medianMs: med(g.map((x) => x.ms)), minMs: Math.min(...g.map((x) => x.ms)), maxMs: Math.max(...g.map((x) => x.ms)), wire: g[0].wire, decoded: g[0].decoded });
  }
  console.log("\n要約 (中央値 ms / min–max / wire B):");
  for (const s of summary) console.log(`  mbps=${String(s.mbps).padStart(3)} enc=${s.enc.padEnd(2)} ${s.mode.padEnd(9)} ${String(s.medianMs).padStart(8)} (${s.minMs}–${s.maxMs})  wire=${s.wire}`);
  mkdirSync(path.dirname(OUT), { recursive: true });
  writeFileSync(OUT, JSON.stringify({ chrome: chromeVer, node: process.version, cpus: os.cpus().length, synthetic: { rawSize, brSize, sha }, reps: REPS, rows, summary }, null, 1));
  const bad = rows.filter((r) => r.f0 !== 42 || r.decoded !== rawSize);
  if (bad.length) { console.log(`FAIL: ${bad.length} 件で f0!=42 または展開後サイズ不一致`); process.exitCode = 1; }
  else console.log(`\nPASS: ${rows.length}/${rows.length} 件で f0()==42・decodedBodySize==${rawSize}`);
} finally {
  await chrome.close();
  srv.close();
  srv.closeAllConnections?.();
}
