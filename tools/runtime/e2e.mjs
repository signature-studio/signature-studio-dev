#!/usr/bin/env node
// ランタイム骨格の 1 コマンド e2e:
//   node tools/runtime/e2e.mjs [--prod] [--skip-stage] [--cache=http|cacheapi|none] [--compile=streaming|bytes] [--no-pump]
//   stage → Vite dev server (COOP/COEP) → headless Chrome → /?runtime=all&pump=1 →
//   各 wasm を Worker 内で fetch+compileStreaming+実行し、node (元 emcc glue) 参照値とブラウザ値を突合。
import path from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { createServer, build, preview } from "vite";
import { launchChrome } from "./lib/chrome.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "../..");
const args = new Map(process.argv.slice(2).map((a) => { const [k, v] = a.replace(/^--/, "").split("="); return [k, v ?? true]; }));
const wasmDir = path.join(here, "work/wasm");

// RT-2: 本番 pthread ビルド (shim MT + emcc glue)。--neg は非 atomic カウンタ版 (ネガティブコントロール: counter チェックが FAIL すべき)
if (!args.has("skip-stage") && !args.has("skip-mt")) {
  const prodWasm = path.join(here, "work/prod/fl-mt.wasm");
  if (args.has("neg") || args.has("rebuild-mt") || !existsSync(prodWasm)) {
    execFileSync("bash", [path.join(here, "prod/build_pthread.sh")], { stdio: ["ignore", "inherit", "inherit"], env: { ...process.env, MT_NEG: args.has("neg") ? "1" : "0" } });
  }
}
if (!args.has("skip-stage")) execFileSync(process.execPath, [path.join(here, "stage_wasm.mjs")], { stdio: ["ignore", "inherit", "inherit"] });
const manifest = JSON.parse(readFileSync(path.join(wasmDir, "manifest.json"), "utf8"));
const byId = Object.fromEntries(manifest.entries.map((e) => [e.id, e]));

// ---------------------------------------------------------------- node 参照 (元の emcc glue) ----
const OBJ = 0x30310000, IN_A = 0x30320000, OU_A = 0x30330000, BUF = 0x30340000, N = 256;
const f32b = (v) => BigInt(new Uint32Array(new Float32Array([v]).buffer)[0]);
const hex = (n) => (n >>> 0).toString(16).padStart(8, "0");
const quiet = () => ({}); // emcc glue は wasmBinary/print を受け付けない (INCOMING_MODULE_JS_API) ため既定のまま、隣の .wasm が staged と同一か別途検証

async function refOtt(cjs, arity) {
  const m2 = await import(cjs);
  const mod = await (m2.default ?? m2)(quiet());
  mod._m6_data_install();
  const U8 = mod.HEAPU8, U32 = mod.HEAPU32, F32 = mod.HEAPF32, dv = new DataView(U8.buffer);
  const setup = (val) => {
    mod._function_18011d400(BigInt(OBJ), 0n);
    for (let i = 0; i < 20; i++) { if (arity >= 3) mod._function_180120af0(BigInt(OBJ), BigInt(i), i === 19 ? 0n : f32b(val)); else mod._function_180120af0(BigInt(OBJ), BigInt(i)); }
    mod._function_180120800(BigInt(OBJ));
    U8[OBJ + 0x248] = 0;
    for (let i = 0; i < N; i++) { F32[BUF / 4 + i] = Math.fround(Math.sin(i * 0.05) * 0.7 + Math.sin(i * 0.011) * 0.3); F32[BUF / 4 + N + i] = Math.fround(Math.cos(i * 0.13) * 0.5); }
    U32[IN_A / 4] = BUF; U32[IN_A / 4 + 2] = BUF + N * 4; U32[OU_A / 4] = BUF + N * 8; U32[OU_A / 4 + 2] = BUF + N * 12;
  };
  const proc = () => mod._function_18011ec20(BigInt(OBJ), BigInt(IN_A), BigInt(OU_A), BigInt(N));
  const hash = () => { let h = 0x811c9dc5; for (let i = 0; i < N * 2; i++) { h ^= dv.getUint32(BUF + N * 8 + i * 4, true); h = Math.imul(h, 0x01000193) >>> 0; } return h >>> 0; };
  setup(0.5); proc(); const h1 = hash(); setup(0.1); proc(); const h3 = hash();
  return { hash0_5: hex(h1), hash0_1: hex(h3) };
}
async function refM11(cjs) {
  const m2 = await import(cjs);
  const mod = await (m2.default ?? m2)(quiet());
  let threw = null, rc = null;
  try { rc = String(mod._m11_boot_enter(0n, 1n)); } catch (e) { threw = e instanceof Error ? e.message : JSON.stringify(e); }
  return { threw, rc, stage: mod._m11_boot_stage() | 0, initCount: mod._m11_init_count() | 0, vaUsed: Number(mod._m11_va_used()), vaCalls: Number(mod._m11_va_calls()) };
}
const refs = {};
import { createHash } from "node:crypto";
const sha = (f) => createHash("sha256").update(readFileSync(f)).digest("hex");
// 参照 glue 隣の .wasm が staged と同一でなければ(別担当が再ビルド中等) 参照比較をスキップ
const sameAsStaged = (id, cjs) => { try { return sha(cjs + ".wasm") === byId[id].sha256; } catch { return false; } };
if (byId["m6-ott"] && sameAsStaged("m6-ott", path.join(root, "tools/m6/work/ott_test.cjs"))) refs["m6-ott"] = await refOtt(path.join(root, "tools/m6/work/ott_test.cjs"), 2);
if (byId["m10-ott"] && sameAsStaged("m10-ott", path.join(root, "tools/m10/work/ott_m10.cjs"))) refs["m10-ott"] = await refOtt(path.join(root, "tools/m10/work/ott_m10.cjs"), 3);
if (byId["m11-boot"] && sameAsStaged("m11-boot", path.join(root, "tools/m11/work/m11_boot.cjs"))) refs["m11-boot"] = await refM11(path.join(root, "tools/m11/work/m11_boot.cjs"));
if (byId["m1-hello"]) refs["m1-hello"] = { stdout: "hello from e2e, answer=42", rc: 0 };

// ---------------------------------------------------------------- browser ----
// --prod: `vite build` した dist/ を `vite preview` で配信 (本番バンドル = Worker 分離チャンクの動作確認)
let vite, port;
if (args.has("prod")) {
  await build({ root, logLevel: "warn" });
  vite = await preview({ root, logLevel: "warn", preview: { port: 0, host: "127.0.0.1", strictPort: false } });
  port = vite.httpServer.address().port;
  vite.close = () => new Promise((r) => vite.httpServer.close(r));
} else {
  vite = await createServer({ root, logLevel: "warn", server: { port: 0, host: "127.0.0.1", strictPort: false } });
  await vite.listen();
  port = vite.httpServer.address().port;
}
const chrome = await launchChrome();
const results = [];
let exitCode = 0;
const ck = (name, ok, detail = "") => { results.push({ name, ok, detail }); console.log(`${ok ? "OK  " : "FAIL"} ${name}${detail ? "  — " + detail : ""}`); if (!ok) exitCode = 1; };
try {
  const q = new URLSearchParams({ runtime: "all" });
  if (!args.has("no-pump")) q.set("pump", "1");
  for (const k of ["cache", "compile"]) if (args.get(k)) q.set(k, args.get(k));
  const url = `http://127.0.0.1:${port}/?${q}`;
  console.log(`[e2e] ${chrome.version}  ${url}`);
  const page = await chrome.newPage(url);
  const rep = await page.waitForExpr("window.__runtime && window.__runtime.state !== 'running' && window.__runtime", 300000);
  ck("crossOriginIsolated (COOP/COEP)", rep.crossOriginIsolated === true);
  ck("runtime state == done", rep.state === "done", rep.error ?? "");
  for (const run of rep.runs) {
    ck(`${run.id}: driver checks`, run.ok && !run.error, run.error ?? run.checks.filter((c) => !c.ok).map((c) => c.name).join("; "));
    const ref = refs[run.id], d = run.data;
    if (run.id === "mt-boot") {
      const e = byId["mt-boot"], r = run.resource;
      for (const c of run.checks) if (c.name.startsWith("4 thread")) ck(`mt-boot: ${c.name}`, c.ok, c.detail ?? "");
      // 事前圧縮 (br) 配信: 展開後サイズ = manifest.bytes、転送量は圧縮後 (HTTP キャッシュ命中時は 0)
      ck("mt-boot: wasm は Content-Encoding: br で配信 (decodedBodySize == manifest.bytes, transferSize < decoded)",
        r.decodedBodySize === e.bytes && (r.transferSize === 0 || (r.transferSize > 0 && r.transferSize < e.bytes)),
        `decoded=${r.decodedBodySize} transfer=${r.transferSize} encoded(br)=${e.encodedBytes?.wasm} raw=${e.bytes} delivery=${r.deliveryType}`);
      ck("mt-boot: ファイル名が内容 hash (sha256 先頭 12 桁)", e.file === `mt-boot.${e.sha256.slice(0, 12)}.wasm` && /^mt-boot\.[0-9a-f]{12}\.mjs$/.test(e.glue ?? ""), `${e.file} / ${e.glue}`);
      if (args.has("neg")) console.log(`[neg] mt-boot counter=${d.counter} (期待: 4000000 未満 → 上の counter チェックが FAIL)`);
      continue;
    }
    if (!ref) continue;
    let same;
    if (run.id === "m1-hello") same = d.stdout === ref.stdout && d.rc === ref.rc;
    else if (run.id === "m11-boot") same = ["threw", "rc", "stage", "initCount", "vaUsed", "vaCalls"].every((k) => d[k] === ref[k]);
    else same = d.hash0_5 === ref.hash0_5 && d.hash0_1 === ref.hash0_1;
    ck(`${run.id}: ブラウザ(Worker) == node(emcc glue) 参照`, same, same ? JSON.stringify(ref) : `browser=${JSON.stringify(d)} ref=${JSON.stringify(ref)}`.slice(0, 400));
  }
  if (rep.pump) {
    const p = rep.pump;
    ck("pump: Worker で Atomics.wait 可 (canBlock)", p.canBlock === true);
    ck("pump: 全 MOUSEMOVE 受信 (loss 0)", (p.byMessage[0x200] ?? 0) === 2000 && p.dropped === 0, `got ${p.byMessage[0x200]}, dropped ${p.dropped}`);
    ck("pump: WM_TIMER が発火 (≥3)", p.timers >= 3, `timers=${p.timers}`);
    ck("pump: ブロッキング wait が実際に発生", p.blockedWaits > 100, `waits=${p.blockedWaits}`);
    console.log(`[pump] latency(ms) p50=${p.latency.p50} p90=${p.latency.p90} p99=${p.latency.p99} max=${p.latency.max} n=${p.latency.n}`);
  }
  console.log("\n[e2e] 起動時間 (ms)  id: fetch+compile / run / total  [wasm MiB]  transfer");
  for (const r of rep.runs) console.log(`  ${r.id.padEnd(10)} ${String(r.timings.fetchCompileMs).padStart(8)} / ${String(r.timings.runMs).padStart(8)} / ${String(r.timings.totalMs).padStart(8)}  [${(r.wasmBytes / 1048576).toFixed(2)}]  transferSize=${r.resource.transferSize} delivery=${r.resource.deliveryType}`);
  if (page.exceptions.length) ck("page exceptions == 0", false, page.exceptions[0].slice(0, 300));
  mkdirSync(path.join(here, "work"), { recursive: true });
  writeFileSync(path.join(here, "work/e2e_result.json"), JSON.stringify({ chrome: chrome.version, report: rep, refs, results }, null, 1));
} catch (e) {
  console.error("[e2e] FAILED:", e.stack || e);
  exitCode = 1;
} finally {
  await chrome.close();
  await vite.close();
}
console.log(exitCode === 0 ? "\n[e2e] ALL OK" : "\n[e2e] FAILED");
process.exit(exitCode);
