// poc_gain_compare.mjs — vectors.json (native 実機出力) と wasm(lift) 出力を bit 突合する。
//   node poc_gain_compare.mjs work/vectors.json work/kh_gain.cjs
import fs from 'node:fs';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);

const [vecPath, modPath] = process.argv.slice(2);
const V = JSON.parse(fs.readFileSync(vecPath, 'utf8'));
const KhGain = require(process.cwd() + '/' + modPath);
const M = await KhGain();

const hex2u8 = (h) => Uint8Array.from(h.match(/../g) ?? [], (x) => parseInt(x, 16));
const u8hex = (u) => Array.from(u, (x) => x.toString(16).padStart(2, '0')).join('');
const alloc = (n) => { const p = M._malloc(n + 16); M.HEAPU8.fill(0, p, p + n + 16); return p; };
const w32 = (p, v) => { new DataView(M.HEAPU8.buffer).setUint32(p, v >>> 0, true); };
const w64 = (p, v) => { w32(p, v); w32(p + 4, 0); };
const r64lo = (p) => new DataView(M.HEAPU8.buffer).getUint32(p, true);
const bytes = (p, n) => M.HEAPU8.slice(p, p + n);

const self = alloc(0xb0), ctx = alloc(0x3200), P = alloc(16), Q = alloc(0x80), Vv = alloc(0x80), vec = alloc(32), buf = alloc(0x30);
w64(ctx + 0x3188, P); w64(ctx + 0x3198, Q); w64(ctx + 0x31b0, Vv); w32(ctx + 0x3180, 100);
M.HEAPU8[self + 0x78] = 1;

let ok = 0, bad = 0;
const fail = [];
V.blocks.forEach((b, bi) => {
  const n = b.n;
  const L = alloc(n * 4 + 16), R = alloc(n * 4 + 16);
  M.HEAPU8.set(hex2u8(b.inL), L); M.HEAPU8.set(hex2u8(b.inR), R);
  w64(buf + 0, L); w64(buf + 8, R); w32(buf + 0x28, n);
  w32(P, b.mode); w32(P + 4, b.gain_p); w32(Q + 0x28, b.q28);
  M.HEAPU8[Q + 0x5c] = M.HEAPU8[Q + 0x7c] = b.dirty;
  w32(self + 0x84, b.coef); w32(self + 0x94, b.coef);
  w64(Vv + 0x68, vec); w64(Vv + 0x70, vec + (b.vroom ? 32 : 0));
  // self_in の一致 (状態引継ぎ検証)
  const sin = u8hex(bytes(self, 0xa0));
  const sinOk = sin === b.self_in;
  M._function_1804b0380(BigInt(self), BigInt(ctx), BigInt(buf));
  const got = {
    outL: u8hex(bytes(L, n * 4)), outR: u8hex(bytes(R, n * 4)), self_out: u8hex(bytes(self, 0xa0)),
    P: u8hex(bytes(P, 16)), Q: u8hex(bytes(Q, 0x80)), vpushed: (r64lo(Vv + 0x68) - vec) / 4, vec: u8hex(bytes(vec, 32)),
  };
  const items = ['outL', 'outR', 'self_out', 'P', 'Q', 'vpushed', 'vec'].map((k) => [k, got[k] === b[k] || (k === 'vpushed' && got[k] == b[k])]);
  const allOk = sinOk && items.every(([, o]) => o);
  allOk ? ok++ : bad++;
  console.log(`block ${bi} n=${n} mode=${b.mode}: self_in ${sinOk ? 'OK' : 'DIFF'} ` + items.map(([k, o]) => `${k}=${o ? 'OK' : 'DIFF'}`).join(' ') + (allOk ? '  => PASS' : '  => FAIL'));
  if (!allOk) fail.push(bi);
});
console.log(`RESULT: ${ok}/${ok + bad} blocks bit-exact (wasm lift == native x86 machine code)`);
process.exit(bad ? 1 : 0);
