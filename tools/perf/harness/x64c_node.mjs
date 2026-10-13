// node 版 (x64c_core 使用)。 node x64c_node.mjs <work/ott_x64c/v.wasm> [iters]  → JSON 1 行
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { setupOtt, measure } from './x64c_core.mjs';
import { namesFromGlue } from './x64c_names.mjs';
const f = process.argv[2], iters = +(process.argv[3] || 20000);
const mod = await WebAssembly.compile(fs.readFileSync(f));
const o = await setupOtt(mod, namesFromGlue(f.replace(/\.wasm$/, '.cjs')));
const sig = o.signature(), nz = o.nonzero();
const r = measure(o.call, () => performance.now(), { iters });
const us = (v) => +(v * 1000).toFixed(2);
console.log(JSON.stringify({ env: 'node', node: process.version, v: path.basename(f, '.wasm'), sig, nonzeroOut: nz, p50us: us(r.steady.p50), p99us: us(r.steady.p99), maxus: us(r.steady.max), batch64p50us: us(r.batch64.p50), rtf44: +(r.steady.p50 / (128 / 44.1)).toFixed(5), load: os.loadavg()[0] }));
