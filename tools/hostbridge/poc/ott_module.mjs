// ott_module.mjs — OTT plugin module descriptor (registry entry) : 事前 prewarm した emscripten instance プールを guest として払い出す.
//   実運用では desc.acquire() は `new WebAssembly.Instance(compiledModule, imports)` (同期) になる (HOSTBRIDGE.md §2.2).
import { EmscriptenGuest } from './hb_bridge.mjs';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));

export function makeOttDesc({ cjs = path.join(HERE, '../work/ott_hb.cjs') } = {}) {
  const require = createRequire(import.meta.url);
  const factory = require(cjs);
  const pool = [];
  const desc = {
    id: 'xfer.ott.vst2', name: 'OTT', vendor: 'Xfer Records', format: 'vst2', arch: 'x64',
    aliases: ['OTT_x64.dll', 'OTT.dll'],
    exports: { VSTPluginMain: 'VSTPluginMain', main: 'VSTPluginMain' }, // PE export 表 (OTT_vst2_win64.dll と同一)
    instancesCreated: 0,
    async prewarm(n) { for (let i = 0; i < n; i++) { const mod = await factory(); pool.push(new EmscriptenGuest(mod)); desc.instancesCreated++; } },
    acquire() { const g = pool.pop(); if (!g) throw new Error('hostbridge: instance pool empty (prewarm 不足)'); return g; },
    release(g) { g.mod = null; },
    poolSize: () => pool.length,
  };
  return desc;
}
