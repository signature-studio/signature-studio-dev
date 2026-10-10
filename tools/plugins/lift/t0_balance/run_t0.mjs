// T0 検証: Fruity Balance の SIMD kernel 2 本 (mix 0x5dee90 / peak 0x5df940) を
//   (a) lift→wasm (node)  と  (b) 実機械語 native (native_ref, MS x64 ABI)  で同一入力に対し bit 比較する。
// usage: node run_t0.mjs <workdir(lifted cjs, native_ref)> <PE dll>
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
const require = createRequire(import.meta.url);

const W = path.resolve(process.argv[2]);
const DLL = process.argv[3];
const BASE = 0x400000;
const SCR = { S: 0x1000000, D: 0x1100000, P: 0x1200000, O: 0x1200100 }; // wasm linear (低 12bit は native と同一)

// ---- 決定論 PRNG (xorshift32) ----
let st = (Number(process.env.T0_SEED || 0x1234abcd) >>> 0) || 1;
const rnd = () => { st ^= st << 13; st >>>= 0; st ^= st >>> 17; st ^= st << 5; st >>>= 0; return st; };
const f32 = new Float32Array(1), u32 = new Uint32Array(f32.buffer);
const bitsToF = (b) => { u32[0] = b >>> 0; return f32[0]; };
const rf = () => {
  const r = rnd() % 64;
  if (r === 0) return bitsToF(0x80000000);            // -0.0
  if (r === 1) return bitsToF(0x00000123);            // denormal
  if (r === 2) return bitsToF(0x7f000000);            // 大きい値
  if (r === 3) return bitsToF(0x3f800000);            // 1.0
  return ((rnd() / 4294967296) * 2 - 1) * (r < 16 ? 100 : 1);
};

const NS = [0, 1, 2, 3, 4, 5, 7, 8, 9, 15, 16, 17, 31, 33, 64, 100, 257];
const cases = [];
for (const n of NS) {
  for (let mode = 0; mode < 6; mode++) {
    for (let rep = 0; rep < 3; rep++) {
      const g = new Float32Array(8);
      if (mode === 0) { for (let i = 0; i < 8; i++) g[i] = rf(); }                         // ramp path (g[4..7] != 0)
      else if (mode === 1) { for (let i = 0; i < 4; i++) g[i] = rf(); }                    // matrix path (g[2],g[3] != 0)
      else if (mode === 2) { g[0] = 1; g[1] = 1; }                                          // unity (copy-skip)
      else if (mode === 3) { g[0] = rf(); g[1] = rf(); }                                    // scale path
      else if (mode === 4) { g[0] = 1; g[1] = rf(); }                                       // g0==1 only
      else { g[0] = rf(); g[1] = 1; }                                                       // g1==1 only
      cases.push({ kind: 0, n, padS: rnd() % 4, padD: rnd() % 4, inplace: (rep === 2 && mode !== 1) ? 1 : 0, g, tag: `mix n=${n} mode=${mode} rep=${rep}` });
    }
  }
  for (let rep = 0; rep < 3; rep++) {
    cases.push({ kind: 1, n, padS: rnd() % 4, padD: 0, inplace: 0, g: new Float32Array(8), tag: `peak n=${n} rep=${rep}` });
  }
}
for (const c of cases) {
  c.src = new Float32Array(2 * c.n + 8);
  for (let i = 0; i < 2 * c.n; i++) c.src[i] = rf();
}

// ---- cases.bin ----
let total = 4;
for (const c of cases) total += 24 + 32 + 4 * c.src.length;
const buf = Buffer.alloc(total);
let o = 0;
buf.writeUInt32LE(cases.length, o); o += 4;
for (const c of cases) {
  for (const v of [c.kind, c.n, c.padS, c.padD, c.inplace, 0]) { buf.writeUInt32LE(v >>> 0, o); o += 4; }
  for (let i = 0; i < 8; i++) { buf.writeFloatLE(c.g[i], o); o += 4; }
  for (let i = 0; i < c.src.length; i++) { buf.writeFloatLE(c.src[i], o); o += 4; }
}
fs.writeFileSync(path.join(W, 'cases.bin'), buf);

// ---- native 参照 ----
execFileSync(path.join(W, 'native_ref'), [DLL, path.join(W, 'cases.bin'), path.join(W, 'native.bin')]);
const nat = fs.readFileSync(path.join(W, 'native.bin'));
const natRes = [];
{
  let p = 0;
  for (let i = 0; i < cases.length; i++) {
    const ret = nat.readBigUInt64LE(p); p += 8;
    const nw = nat.readUInt32LE(p); p += 4;
    const words = new Uint32Array(nw);
    for (let k = 0; k < nw; k++) { words[k] = nat.readUInt32LE(p); p += 4; }
    natRes.push({ ret, words });
  }
}

// ---- wasm (lifted) ----
const create = require(path.join(W, 'k.cjs'));
const M = await create();
const pe = fs.readFileSync(DLL);
const peOff = pe.readUInt32LE(0x3c);
const nsec = pe.readUInt16LE(peOff + 6), optsz = pe.readUInt16LE(peOff + 20);
const HEAP = () => M.HEAPU8;
for (let i = 0; i < nsec; i++) {
  const e = peOff + 24 + optsz + 40 * i;
  const vs = pe.readUInt32LE(e + 8), va = pe.readUInt32LE(e + 12), rs = pe.readUInt32LE(e + 16), rp = pe.readUInt32LE(e + 20);
  const n = Math.min(vs, rs);
  if (n) HEAP().set(pe.subarray(rp, rp + n), va); // LVA = VA - 0x400000 = RVA
}
const mix = M._function_5dee90, peak = M._function_5df940;
let pass = 0, fail = 0;
const failures = [];
const groups = {};
const dbg = {};
for (let i = 0; i < cases.length; i++) {
  const c = cases[i];
  const h = HEAP();
  const dv = new DataView(h.buffer);
  h.fill(0, SCR.S, SCR.S + 0x1000);
  const srcA = SCR.S + 4 * c.padS;
  for (let k = 0; k < c.src.length; k++) dv.setFloat32(srcA + 4 * k, c.src[k], true);
  const dstA = c.inplace ? srcA : SCR.D + 4 * c.padD;
  if (!c.inplace) h.fill(0xA5, SCR.D, SCR.D + 0x1000);
  for (let k = 0; k < 8; k++) dv.setFloat32(SCR.P + 4 * k, c.g[k], true);
  let ret, words;
  if (c.kind === 0) {
    ret = M._function_5dee90(BigInt(srcA), BigInt(dstA), BigInt(c.n), BigInt(SCR.P));
    const nout = 2 * c.n + 16;
    words = new Uint32Array(nout);
    for (let k = 0; k < nout; k++) words[k] = dv.getUint32(dstA + 4 * k, true);
  } else {
    dv.setFloat32(SCR.O, 0, true); dv.setFloat32(SCR.O + 4, 0, true);
    ret = M._function_5df940(BigInt(srcA), BigInt(c.n), BigInt(SCR.O), BigInt(SCR.O + 4));
    words = new Uint32Array([dv.getUint32(SCR.O, true), dv.getUint32(SCR.O + 4, true)]);
  }
  const ref = natRes[i];
  // mix は戻り値 rax の下位 1 bit のみ意味を持つ (0/1)。peak は戻り値未定義 (比較しない)。
  let ok = words.length === ref.words.length && words.every((w, k) => w === ref.words[k]);
  let retOk = true;
  if (c.kind === 0) retOk = ((BigInt.asUintN(64, ret) & 0xffffffffn) === (ref.ret & 0xffffffffn));
  const gk = c.kind === 0 ? `mix mode${c.tag.match(/mode=(\d)/)[1]}${c.inplace ? ' inplace' : ''}` : 'peak';
  groups[gk] = groups[gk] || [0, 0];
  groups[gk][ok && retOk ? 0 : 1]++;
  if (!(ok && retOk) && !dbg[gk]) dbg[gk] = { tag: c.tag, g: Array.from(c.g), src: Array.from(c.src).slice(0, 8), wasm: Array.from(words).slice(0, 8).map(x => x.toString(16)), native: Array.from(ref.words).slice(0, 8).map(x => x.toString(16)) };
  if (ok && retOk) pass++; else { fail++; if (failures.length < 12) failures.push({ tag: c.tag, retWasm: ret.toString(16), retNative: ref.ret.toString(16), firstDiff: words.findIndex((w, k) => w !== ref.words[k]) }); }
}
const kinds = { mix: cases.filter(c => c.kind === 0).length, peak: cases.filter(c => c.kind === 1).length };
const res = { cases: cases.length, kinds, pass, fail, groups, dbg, failures };
fs.writeFileSync(path.join(W, 't0_result.json'), JSON.stringify(res, null, 1));
console.log(JSON.stringify(res));
process.exit(fail ? 1 : 0);
