// hs_fwsmoke.mjs — framework smoke を stderr も見て実行 (検証中の詳細観測用)。
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { resolve as pathResolve } from 'node:path';
const [IMG, CJS] = [process.argv[2], process.argv[3]];
const req = createRequire(import.meta.url);
const img = readFileSync(IMG);
const mod = await req(pathResolve(CJS))();
mod.HEAPU8.set(img, 0x400000);
for (let o = 0; o < 0x100; o++) mod.HEAPU8[0x8a1000 + o] = 0;
try {
  mod._function_6c13a0(0x400000n, 1n, 0n, 0n);
  console.error('[smoke] returned');
} catch (e) { console.error('[smoke] threw: ' + (e.message || '').split('\n')[0]); }
console.error('[smoke] dispatch=%d ff=%d lastSite=0x%s lastTarget=0x%s',
  mod._fw_dispatch_count(), mod._fw_ff_count(),
  mod._fw_last_site().toString(16), mod._fw_last_target().toString(16));
