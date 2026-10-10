// transplant.mjs: 旧 chain (wasm) の resume 後 state に native の state 差分 qword を移植 → process 出力が native と一致するか (原因同定実験)
//   env: MOD (旧 chain), NAT (scen2_nat 出力 json: final regions), WASM0 (同 module の scen2 出力 json: 差分 region 取得用), REGIONS (例 "obj,h1,h2,h3" or "all"), SKIP_ZERO...
import fs from 'fs';
import zlib from 'zlib';
import { load } from './api.mjs';
const api = await load(process.env.MOD); const mod = api.mod; const U8 = mod.HEAPU8, U32 = mod.HEAPU32, F32 = mod.HEAPF32;
const spec = JSON.parse(fs.readFileSync(process.env.SPEC, 'utf8'));
const nat = JSON.parse(fs.readFileSync(process.env.NAT, 'utf8'));          // native: {outs, final(after process)}  → 'resume 直後' ではないので native stage dump を使う
const OBJ = 0x30310000, IN_A = 0x30320000, OU_A = 0x30330000, BUF = 0x30340000, n = spec.n ?? 256;
const inp = new Float32Array(n * 2);
for (let i = 0; i < n; i++) { inp[i] = Math.fround(Math.sin(i * 0.05) * 0.7 + Math.sin(i * 0.011) * 0.3); inp[n + i] = Math.fround(Math.cos(i * 0.13) * 0.5); }
for (let i = 0; i < n * 2; i++) F32[BUF / 4 + i] = inp[i];
U32[IN_A / 4] = BUF; U32[IN_A / 4 + 2] = BUF + n * 4; U32[OU_A / 4] = BUF + n * 8; U32[OU_A / 4 + 2] = BUF + n * 12;
api.ctor(OBJ);
(spec.params ?? []).forEach((v, i) => api.setParam(OBJ, i, v));
api.resume(OBJ);
if (spec.f248 != null) U8[OBJ + 0x248] = spec.f248;
// native 'resume' 直後 state = nat.stages.resume (scen_nat.py 出力)
const want = (process.env.REGIONS || 'obj,h1,h2,h3').split(',');
let patched = 0;
const dv = new DataView(U8.buffer, U8.byteOffset, U8.length);
for (const r of nat.stages.resume) {
  if (!(want.includes(r.k) || want[0] === 'all')) continue;
  const b = zlib.inflateSync(Buffer.from(r.z, 'base64'));
  for (let o = 0; o + 8 <= r.s; o += 8) {
    const qn = b.readBigUInt64LE(o);
    if (r.k === 'obj' && o === 0) continue;
    if (qn >= 0x180000000n && qn < 0x180400000n) continue;                // image ptr は wasm 側の別表現
    const lo = dv.getUint32(r.p + o, true), hi = dv.getUint32(r.p + o + 4, true);
    const qw = (BigInt(hi) << 32n) | BigInt(lo);
    if (qw !== qn) {
      if ((qw >> 32n) === 0n && qw >= 0x10000000n && qw < 0x36000000n && (qn >> 32n) === 0n) continue;   // heap ptr 同士
      dv.setUint32(r.p + o, Number(qn & 0xffffffffn), true); dv.setUint32(r.p + o + 4, Number(qn >> 32n), true); patched++;
    }
  }
}
api.process(OBJ, IN_A, OU_A, n);
const out = []; for (let i = 0; i < n * 2; i++) out.push(U32[(BUF + n * 8) / 4 + i]);
fs.writeFileSync(process.env.OUT, JSON.stringify({ patched, out }));
console.log('patched qwords', patched);
