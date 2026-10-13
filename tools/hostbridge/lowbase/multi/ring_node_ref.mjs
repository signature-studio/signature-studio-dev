// ring_node_ref.mjs — ring/RPC 試験の node 参照値を生成する。Chrome 側と同じ入力・同じ処理順で OTT lowbase を NBLK ブロック回す。
//   node ring_node_ref.mjs --ott <ott_hb.cjs> --host <host_vst2.wasm> --out <ref.json>
//   出力: rpc_out0 = 先頭 NRPC ブロックの L[0] (float32 のビット列), ring_sum = ring に流れる NRPC..NBLK-1 ブロックの総和 (float64), ring_floats = その要素数。
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { ModuleTable, HostBridge, EmscriptenGuest } from '../../poc/hb_bridge.mjs';
import { createRequire } from 'node:module';
import { H, NBLK, NRPC, SR, PLUGIN_VENDOR, PLUGIN_ALIAS, PATH, configure, wstr, mkAudio, processBlock, accum } from './ring_common.mjs';
const HERE = path.dirname(fileURLToPath(import.meta.url));
const arg = (k, d) => { const i = process.argv.indexOf('--' + k); return i > 0 ? process.argv[i + 1] : d; };
const OTT = arg('ott'), HOSTWASM = arg('host'), OUT = arg('out');
const require = createRequire(import.meta.url);
const factory = require(path.resolve(OTT));
const guest = new EmscriptenGuest(await factory());
const pool = [guest];
const desc = { id: 'xfer.ott.vst2#0', name: 'OTT', vendor: PLUGIN_VENDOR, format: 'vst2', arch: 'x64', aliases: [PLUGIN_ALIAS],
  exports: { VSTPluginMain: 'VSTPluginMain', main: 'VSTPluginMain' }, acquire() { return pool.pop(); }, release() {} };
const table = new ModuleTable(); table.register(desc);
const bridge = new HostBridge(table);
const inst = new WebAssembly.Instance(new WebAssembly.Module(fs.readFileSync(HOSTWASM)), bridge.imports()); bridge.attachHost(inst);
const x = inst.exports;
// host alloc の順序を Chrome worker (LOAD → mkAudio → CONFIG) と揃える (junk 読みは絶対番地に依存; lowbase REPORT §4.3)
const e = x.host_load_plugin(wstr(x, PATH(PLUGIN_VENDOR, PLUGIN_ALIAS)), SR, H);
const au = mkAudio(x);
configure(x, e);
const rpcOut0 = []; let sum = 0; let floats = 0;
for (let b = 0; b < NBLK; b++) {
  const out = processBlock(x, e, au, b * H);
  if (b < NRPC) rpcOut0.push(new Uint32Array(out.buffer.slice(0, 4))[0]);
  else { sum = accum(sum, out); floats += 2 * H; }
}
const ref = { handle_ok: e !== 0, rpc_out0_bits: rpcOut0, ring_sum: sum, ring_floats: floats };
if (OUT) fs.writeFileSync(OUT, JSON.stringify(ref, null, 1));
console.log(JSON.stringify({ handle_ok: ref.handle_ok, ring_floats: ref.ring_floats, ring_sum: ref.ring_sum }));
process.exit(ref.handle_ok ? 0 : 1);
