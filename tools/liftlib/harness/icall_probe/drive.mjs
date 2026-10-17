// drive.mjs — probe_dispatch(target, site) を 1 回呼ぶ。abort は JS 例外になり diff.py の wasm_trap 経路 (crash=1) に相当する。
//   node drive.mjs <module.cjs> <target-hex> <site-hex>
import path from 'node:path';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const [modPath, tgt, site] = process.argv.slice(2);
const M = await require(path.resolve(modPath))();
let crashed = 0, msg = '';
try {
  M._probe_dispatch(BigInt('0x' + tgt), BigInt('0x' + site));
  msg = 'ok';
} catch (e) {
  crashed = 1;
  msg = String(e && e.message ? e.message : e).split('\n')[0];
}
console.log(JSON.stringify({ module: path.basename(path.dirname(path.resolve(modPath))), target: tgt, site, crashed, msg }));
