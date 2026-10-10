// scen2_wasm.mjs: 汎用 scenario runner (wasm 側)。SPEC(json 文字列 or file): {params:[...], p19, n, nproc, f248, sig, sr}
//   出力 JSON: { alog, inp(b64 f32le), outs:[block毎 u32 配列], final: [{k,p,s,z}] }
import fs from 'fs';
import zlib from 'zlib';
import { load } from './api.mjs';
const ARENA = Number(process.env.LB_ARENA);   // lb_layout.py の固定アリーナ (OBJ/IN/OUT/BUF)
const api = await load(process.env.MOD);
const mod = api.mod;
// 小 memory 版は heap が memory.grow し得る → 各 API 呼出後に view を取り直す
let U8, U32, F32; const refresh = () => { U8 = mod.HEAPU8; U32 = mod.HEAPU32; F32 = mod.HEAPF32; }; refresh();
for (const k of ['ctor', 'setParam', 'resume', 'process']) { const f = api[k]; api[k] = (...a) => { const r = f(...a); refresh(); return r; }; }
const spec = JSON.parse(fs.existsSync(process.env.SPEC) ? fs.readFileSync(process.env.SPEC, 'utf8') : process.env.SPEC);
const OBJ = ARENA + 0x10000, IN_A = ARENA + 0x20000, OU_A = ARENA + 0x30000, BUF = ARENA + 0x40000;
const ALOG = mod._ott_alog_addr();
const n = spec.n ?? 256, nproc = spec.nproc ?? 1;
const z = (a) => zlib.deflateSync(Buffer.from(a)).toString('base64');
const inp = new Float32Array(n * 2 * nproc);
let seed = 12345;
for (let b = 0; b < nproc; b++) for (let i = 0; i < n; i++) {
  const t = b * n + i, sg = spec.sig ?? 0;
  let l = Math.sin(t * 0.05) * 0.7 + Math.sin(t * 0.011) * 0.3 + sg, r = Math.cos(t * 0.13) * 0.5 + sg;
  const kind = spec.inkind ?? 'sine';
  if (kind === 'zero') { l = 0; r = 0; }
  else if (kind === 'dc') { l = 0.9; r = -0.6; }
  else if (kind === 'impulse') { l = t === 5 ? 1 : 0; r = t === 9 ? -1 : 0; }
  else if (kind === 'square') { l = (Math.floor(t / 20) & 1) ? 1 : -1; r = (Math.floor(t / 33) & 1) ? 0.8 : -0.8; }
  else if (kind === 'noise') { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; l = (seed / 2 ** 31) - 1; seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; r = (seed / 2 ** 31) - 1; }
  else if (kind === 'tiny') { l = 1e-30 * Math.sin(t * 0.3); r = 1e-38 * Math.cos(t * 0.2); }   // 非正規数域
  else if (kind === 'decay') { const e = Math.exp(-t * 0.02); l = e * Math.sin(t * 0.05); r = e * 0.5; }
  inp[b * 2 * n + i] = Math.fround(l);
  inp[b * 2 * n + n + i] = Math.fround(r);
}
api.ctor(OBJ);
if (spec.sr) new DataView(U8.buffer, U8.byteOffset, U8.length).setFloat32(OBJ + 0x18, spec.sr, true);
(spec.params ?? []).forEach((v, i) => { if (v !== null) api.setParam(OBJ, i, v); });
if (spec.p19 !== undefined) api.setParam(OBJ, 19, spec.p19);
api.resume(OBJ);
if (spec.f248 !== undefined && spec.f248 !== null) U8[OBJ + 0x248] = spec.f248;
U32[IN_A / 4] = BUF; U32[IN_A / 4 + 2] = BUF + n * 4; U32[OU_A / 4] = BUF + n * 8; U32[OU_A / 4 + 2] = BUF + n * 12;
const outs = [];
for (let b = 0; b < nproc; b++) {
  for (let i = 0; i < n * 2; i++) F32[BUF / 4 + i] = inp[b * 2 * n + i];
  api.process(OBJ, IN_A, OU_A, n);
  const o = []; for (let i = 0; i < n * 2; i++) o.push(U32[(BUF + n * 8) / 4 + i]);
  outs.push(o);
}
const na = U32[ALOG / 4]; const alog = [];
for (let i = 0; i < na; i++) alog.push([U32[ALOG / 4 + 2 + 2 * i], U32[ALOG / 4 + 3 + 2 * i]]);
const regs = [['obj', OBJ, 0x1000], ...alog.map(([p, s], i) => ['h' + i, p, s])];
const final = regs.map(([k, p, s]) => ({ k, p, s, z: z(U8.slice(p, p + s)) }));
fs.writeFileSync(process.env.OUT, JSON.stringify({ spec, n, alog, outs, final, inp: z(new Uint8Array(inp.buffer)) }));
console.log('[scen2_wasm] ok blocks', nproc, 'allocs', na);
