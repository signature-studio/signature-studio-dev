// Asyncify 計装による実行時オーバーヘッド (M10 OTT lifted DSP, node/V8)。通常状態(unwind しない)での processReplacing 速度比。
import { readFileSync } from "node:fs"; import path from "node:path"; import { fileURLToPath } from "node:url";
import { loadOtt, makeRunner } from "./ott_driver.mjs";
const w = path.join(path.dirname(fileURLToPath(import.meta.url)), "../work/asyncify");
const names = ["m10_O2", "m10_async_noind", "m10_async"];
const rs = {};
for (const n of names) { const o = await loadOtt(readFileSync(`${w}/${n}.wasm`)); rs[n] = makeRunner(o); rs[n].setup(0.5); rs[n].process(); }
const t = Object.fromEntries(names.map((n) => [n, []]));
for (let rep = 0; rep < 16; rep++) for (const n of (rep % 2 ? [...names].reverse() : names)) { const r = rs[n]; r.setup(0.5); const t0 = performance.now(); for (let i = 0; i < 300; i++) r.process(); if (rep) t[n].push(performance.now() - t0); }
const out = {};
for (const n of names) { const a = t[n].sort((x, y) => x - y); out[n] = { minMs: +a[0].toFixed(1), medMs: +a[a.length >> 1].toFixed(1), hash: rs[n].hash().toString(16) }; }
for (const n of names) out[n].ratioMin = +(out[n].minMs / out.m10_O2.minMs).toFixed(3), out[n].ratioMed = +(out[n].medMs / out.m10_O2.medMs).toFixed(3);
console.log(JSON.stringify(out, null, 1));
