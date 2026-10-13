// setter_harness.mjs <fset.cjs> <scen.txt> [fma] — native_setter と同一シナリオを lift 済み wasm (ctor/setter/process) で実行し同形式でダンプ。
// シナリオ毎に module を新規 instantiate (native 側のシナリオ毎 fork と同じ隔離)。
import fs from 'node:fs'; import path from 'node:path'; import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const factory = require(path.resolve(process.argv[2]));
const lines = fs.readFileSync(process.argv[3], 'utf8').split('\n').filter(Boolean);
const FMA = Number(process.argv[4] || 0);
const out = [];
for (const line of lines) {
  const M_ = await factory();
  const dv = () => new DataView(M_.HEAPU8.buffer);
  const al = (n) => { const p = M_._malloc(n); M_.HEAPU8.fill(0, p, p + n); return p; };
  const w32 = (p, v) => dv().setUint32(p, v >>> 0, true);
  const w64 = (p, v) => { dv().setUint32(p, v >>> 0, true); dv().setUint32(p + 4, 0, true); };
  const hex = (p, n) => Buffer.from(M_.HEAPU8.subarray(p, p + n)).toString('hex');
  const t = line.split(' ').map((x) => parseInt(x, 16)); let ti = 0;
  const sidx = t[ti++], type = t[ti++], nset = t[ti++];
  const M = al(0xa400), dummy = al(32);
  let o = 'S' + sidx;
  try { M_._fa_root_180b4c040(BigInt(M), BigInt(dummy)); } catch (e) { console.log(o + ' |CTORERR'); if (process.env.FA_DBG) console.error(String(e.stack).slice(0, 300)); out.push(o + ' |CTORERR'); continue; }
  for (let k = 0; k < nset; k++) {
    const id = t[ti++], v = t[ti++];
    try { M_._fa_root_1803debc0(BigInt(M), id, v | 0); } catch (e) { o += ' |SETERR'; if (process.env.FA_DBG) console.error(String(e.stack).slice(0, 300)); }
  }
  const ncalls = t[ti++]; let seed = BigInt(t[ti++]);
  const S = al(0x1400), ctx = al(0x80), n = 64;
  const f32 = new Float32Array(1), u32 = new Uint32Array(f32.buffer);
  f32[0] = 48000; w32(S + 0x98, u32[0]); w64(S + 0x90, M); w32(M + 0x9dc4, type);
  w32(Number(M_._fa_va2ptr(0x1813070f8n)), FMA);
  const rng = () => { seed = (seed * 6364136223846793005n + 1442695040888963407n) & 0xffffffffffffffffn; return Number(seed >> 33n); };
  for (let c = 0; c < ncalls; c++) {
    const L = al(n * 4 + 4), R = al(n * 4 + 4);
    for (let i = 0; i < n; i++) {
      const l = Math.fround(Math.fround((((rng() & 0xffffff) - 8388608)) / 8388608.0) * 0.5);
      const r = Math.fround(Math.fround(Math.fround(-l) * Math.fround(0.7)) + Math.fround(0.01));
      f32[0] = l; w32(L + 4 * i, u32[0]); f32[0] = r; w32(R + 4 * i, u32[0]);
    }
    w64(ctx, L); w64(ctx + 8, R); w32(ctx + 0x28, n); M_.HEAPU8[ctx + 0x60] = 0;
    const sp = M_.stackSave();
    try { M_._fa_root_180b6f050(BigInt(S), BigInt(ctx)); } catch (e) { M_.stackRestore(sp); o += ' |PROCERR'; if (process.env.FA_DBG) console.error(String(e.stack).slice(0, 300)); break; }
    o += ' |' + hex(L, n * 4) + ' ' + hex(R, n * 4) + ' ' + [0x9dc4, 0x9e0c, 0x9e54, 0x9e9c, 0x9ee4].map((x) => hex(M + x, 4)).join('');
  }
  out.push(o);
}
console.log(out.join('\n'));
