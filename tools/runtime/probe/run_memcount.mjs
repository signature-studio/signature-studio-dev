#!/usr/bin/env node
// 1 プロセス内に wasm Memory (max=4GiB 予約) を何個作れるか: プラグイン 1 インスタンス = 1 Memory 方針の上限確認。
import path from "node:path"; import { fileURLToPath } from "node:url";
import { serve } from "../lib/serve.mjs"; import { launchChrome } from "../lib/chrome.mjs";
const here = path.dirname(fileURLToPath(import.meta.url));
const srv = await serve([{ prefix: "/", dir: here }]);
const chrome = await launchChrome();
try {
  const page = await chrome.newPage(`http://127.0.0.1:${srv.port}/features.html`);
  await page.waitFor("__result", 120000);
  const r = await page.evaluate(`(async () => {
    const out = {};
    const count = (mk, cap) => { const keep = []; let err = null; const t0 = performance.now(); try { for (let i = 0; i < cap; i++) keep.push(mk()); } catch (e) { err = String(e.message || e).slice(0, 80); } return { created: keep.length, cappedAt: cap, err, ms: +(performance.now() - t0).toFixed(0) }; };
    out.wasm32_initial1_max4GiB = count(() => new WebAssembly.Memory({ initial: 1, maximum: 65536 }), 4000);
    out.wasm32_shared_initial1_max4GiB = count(() => new WebAssembly.Memory({ initial: 1, maximum: 65536, shared: true }), 4000);
    out.wasm32_initial256MiB_noMax = count(() => new WebAssembly.Memory({ initial: 4096 }), 400);
    out.wasm64_initial1_max16GiB = count(() => new WebAssembly.Memory({ address: 'i64', initial: 1n, maximum: 262144n }), 4000);
    out.wasm32_initial1_max16MiB = count(() => new WebAssembly.Memory({ initial: 1, maximum: 256 }), 4000);
    out.wasm32_initial1_max1GiB = count(() => new WebAssembly.Memory({ initial: 1, maximum: 16384 }), 4000);
    out.wasm32_shared_initial1_max256MiB = count(() => new WebAssembly.Memory({ initial: 1, maximum: 4096, shared: true }), 4000);
    return out; })()`, { timeout: 120000 });
  console.log(JSON.stringify(r, null, 1));
} finally { await chrome.close(); await srv.close(); }
