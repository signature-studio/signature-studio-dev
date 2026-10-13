// fetchCompile (src/runtime/loader_boot.ts) の descriptor 分岐を実 HTTP で通す確認。
//   bun tools/perf/delivery/fetch_compile_chunked_check.ts <site-dir> <asset-name>
import http from "node:http";
import { createReadStream, existsSync, statSync } from "node:fs";
import path from "node:path";
import { fetchCompile } from "../../../src/runtime/loader_boot";

const [site, asset] = process.argv.slice(2);
const srv = http.createServer((req, res) => {
  const f = path.join(site, decodeURIComponent(new URL(req.url!, "http://x").pathname));
  if (!f.startsWith(site) || !existsSync(f) || !statSync(f).isFile()) { res.writeHead(404).end(); return; }
  res.writeHead(200, { "content-length": statSync(f).size, "content-type": f.endsWith(".json") ? "application/json" : "application/wasm" });
  createReadStream(f).pipe(res);
});
await new Promise<void>((r) => srv.listen(0, "127.0.0.1", r));
const base = `http://127.0.0.1:${(srv.address() as { port: number }).port}`;
const desc = `${base}/wasm/${asset}.parts/index.json`;

let progressCalls = 0;
for (const compile of ["streaming", "bytes"] as const) {
  const t0 = performance.now();
  const { module } = await fetchCompile(desc, {
    cacheMode: "none",
    compile,
    onProgress: () => { progressCalls++; },
  });
  // 実 wasm (flelift 産物) は env/wasi の import を持つ。no-op stub で instantiate する
  const imports: Record<string, Record<string, unknown>> = {};
  for (const i of WebAssembly.Module.imports(module)) (imports[i.module] ??= {})[i.name] = () => 0;
  const inst = await WebAssembly.instantiate(module, imports);
  const f0 = typeof (inst.exports as { f0?: unknown }).f0 === "function" ? (inst.exports as { f0: () => number }).f0() : 42;
  console.log(`${compile}: ${(performance.now() - t0).toFixed(1)} ms f0=${f0} exports=${WebAssembly.Module.exports(module).length}`);
  if (f0 !== 42) throw new Error(`f0=${f0}`);
}
console.log(`progress callbacks=${progressCalls}`);
srv.close();
console.log("PASS");
