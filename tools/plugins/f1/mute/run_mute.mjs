// Fruity Mute 2 Eff_Render (0x6baaf0) 差分試験: lift→wasm (node) ⟷ 実機械語 native (native_mute)。
// usage: node run_mute.mjs <workdir(<tag>.cjs, native_mute)> <PE dll>   env: MU_SEED, MU_TAG (既定 pi; mur = 手動 oracle 修復版)
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
const require = createRequire(import.meta.url);
const W = path.resolve(process.argv[2]);
const DLL = process.argv[3];
const SCR = { T: 0x1300000, S: 0x1000000, D: 0x1100000 }; // wasm linear (低 12bit は native と同一)

let st = (Number(process.env.MU_SEED || 0x1234abcd) >>> 0) || 1;
const rnd = () => { st ^= st << 13; st >>>= 0; st ^= st >>> 17; st ^= st << 5; st >>>= 0; return st; };
const f32 = new Float32Array(1), u32 = new Uint32Array(f32.buffer);
const bitsToF = (b) => { u32[0] = b >>> 0; return f32[0]; };
const rf = () => {
  const r = rnd() % 64;
  if (r === 0) return bitsToF(0x80000000);
  if (r === 1) return bitsToF(0x00000123);
  if (r === 2) return bitsToF(0x7f7fffff);
  if (r === 3) return bitsToF(0x80000001);
  if (r === 4) return bitsToF(0x3f800000);
  return ((rnd() / 4294967296) * 2 - 1) * (r < 16 ? 100 : 1);
};
const NS = [0, 1, 2, 3, 4, 5, 7, 8, 9, 15, 16, 17, 31, 33, 64, 100, 257];
// {enabled, mode}: 無効 (copy のみ) / 有効 mode0 (fade A) / mode1 (zero) / mode2 (fade B) / mode3 (何もしない)
const EM = [[0, 0], [1, 0], [1, 1], [1, 2], [1, 3]];
const cases = [];
for (const n of NS) for (const [en, md] of EM) for (const inplace of [1, 0]) for (let rep = 0; rep < 3; rep++) {
  const c = { en, md, em: en | (md << 8), n, padS: rnd() % 4, padD: rnd() % 4, inplace, src: new Float32Array(2 * n) };
  for (let i = 0; i < 2 * n; i++) c.src[i] = rf();
  cases.push(c);
}
let total = 4;
for (const c of cases) total += 20 + 4 * c.src.length;
const buf = Buffer.alloc(total);
let o = 0;
buf.writeUInt32LE(cases.length, o); o += 4;
for (const c of cases) {
  buf.writeInt32LE(c.em, o); o += 4;
  for (const v of [c.n, c.padS, c.padD, c.inplace]) { buf.writeUInt32LE(v >>> 0, o); o += 4; }
  for (let i = 0; i < c.src.length; i++) { buf.writeFloatLE(c.src[i], o); o += 4; }
}
fs.writeFileSync(path.join(W, 'cases.bin'), buf);
execFileSync(path.join(W, 'native_mute'), [DLL, path.join(W, 'cases.bin'), path.join(W, 'native.bin')]);
const nat = fs.readFileSync(path.join(W, 'native.bin'));
const natRes = [];
{
  let p = 0;
  for (let i = 0; i < cases.length; i++) {
    const ret = nat.readBigUInt64LE(p); p += 8;
    const nd = nat.readUInt32LE(p); p += 4;
    const dst = new Uint32Array(nd); for (let k = 0; k < nd; k++) { dst[k] = nat.readUInt32LE(p); p += 4; }
    const ns = nat.readUInt32LE(p); p += 4;
    const src = new Uint32Array(ns); for (let k = 0; k < ns; k++) { src[k] = nat.readUInt32LE(p); p += 4; }
    natRes.push({ ret, dst, src });
  }
}
const TAG = process.env.MU_TAG || 'mu';
const create = require(path.join(W, TAG + '.cjs'));
const M = await create();
const pe = fs.readFileSync(DLL);
const peOff = pe.readUInt32LE(0x3c);
const nsec = pe.readUInt16LE(peOff + 6), optsz = pe.readUInt16LE(peOff + 20);
for (let i = 0; i < nsec; i++) {
  const e = peOff + 24 + optsz + 40 * i;
  const vs = pe.readUInt32LE(e + 8), va = pe.readUInt32LE(e + 12), rs = pe.readUInt32LE(e + 16), rp = pe.readUInt32LE(e + 20);
  const n = Math.min(vs, rs);
  if (n) M.HEAPU8.set(pe.subarray(rp, rp + n), va); // LVA = VA - 0x400000 = RVA
}
const groups = {};
const firstFail = {};
let pass = 0, fail = 0;
for (let i = 0; i < cases.length; i++) {
  const c = cases[i];
  const h = M.HEAPU8;
  const dv = new DataView(h.buffer);
  h.fill(0, SCR.S, SCR.S + 0x1000);
  const srcA = SCR.S + 4 * c.padS;
  for (let k = 0; k < c.src.length; k++) dv.setFloat32(srcA + 4 * k, c.src[k], true);
  const dstA = c.inplace ? srcA : SCR.D + 4 * c.padD;
  if (!c.inplace) h.fill(0xA5, SCR.D, SCR.D + 0x1000);
  h.fill(0, SCR.T, SCR.T + 0x400);
  dv.setUint8(SCR.T + 0x128, c.en); dv.setInt32(SCR.T + 0x12c, c.md, true);
  const ret = M._function_6baaf0(BigInt(SCR.T), BigInt(srcA), BigInt(dstA), BigInt(c.n));
  const nd = 2 * c.n + 16;
  const dst = new Uint32Array(nd); for (let k = 0; k < nd; k++) dst[k] = dv.getUint32(dstA + 4 * k, true);
  const src = new Uint32Array(2 * c.n); for (let k = 0; k < 2 * c.n; k++) src[k] = dv.getUint32(srcA + 4 * k, true);
  const ref = natRes[i];
  const ok = dst.every((w, k) => w === ref.dst[k]) && src.every((w, k) => w === ref.src[k]);
  const gk = `${c.inplace ? 'inplace' : 'copy'} ${c.en ? 'mode' + c.md : 'disabled'}`;
  groups[gk] = groups[gk] || [0, 0];
  groups[gk][ok ? 0 : 1]++;
  if (!ok && !firstFail[gk]) {
    const k = dst.findIndex((w, j) => w !== ref.dst[j]);
    firstFail[gk] = { n: c.n, en: c.en, mode: c.md, firstDiffWord: k, wasm: k >= 0 ? dst[k].toString(16) : null, native: k >= 0 ? ref.dst[k].toString(16) : null };
  }
  if (ok) pass++; else fail++;
}
const res = { cases: cases.length, pass, fail, groups, firstFail };
fs.writeFileSync(path.join(W, TAG + '_result.json'), JSON.stringify(res, null, 1));
console.log(JSON.stringify(res));
process.exit(0);
