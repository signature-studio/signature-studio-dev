// cab238_outhash.mjs — CAB-238 検収④ (出力 SHA 分離) 用: liftlib の ott_outhash.mjs と
// 同一プロトコル (ctor → setParameter 20 → resume → [0x248] → process×2 → 出力 512 cell の SHA-256)
// で、combo ごとに進捗を出し、env DROP=<combo key> を指定した combo だけを飛ばせるようにしたもの。
// (既定 (auto f7,p1) ビルドは params=0.9 / [0x248]=1 / amp=0 で processReplacing が停止しない —
//  §5.2 の無限ループ事象 — ため 41 combo で測定する。liftlib 側 recipe は LIFTLIB-2 スコープなので
//  ここ (tools/ott) に同じ手順の測定器を置く)
import crypto from 'node:crypto';
const ARENA = Number(process.env.LB_ARENA ?? 0x30310000);
const OBJ = ARENA, IN_A = ARENA + 0x10000, OU_A = ARENA + 0x20000, BUF = ARENA + 0x30000, N = 256;
const f32b = (v) => { const f = new Float32Array(1); f[0] = v; return BigInt(new Uint32Array(f.buffer)[0]); };
const DROP = (process.env.DROP ?? '').split(',').filter(Boolean);
const res = {};
for (const val of [0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0]) for (const f248 of [0, 1]) for (const amp of [0.0, 0.3, 1.0]) {
  const key = `p${val}_f${f248}_a${amp}`;
  if (DROP.includes(key)) { console.error('SKIP ' + key); continue; }
  const t0 = Date.now();
  const m2 = await import(process.env.OTT_CJS);
  const mod = await (m2.default ? m2.default() : m2());
  if (mod._m6_data_install) mod._m6_data_install();
  let U8 = mod.HEAPU8, U32 = mod.HEAPU32, F32 = mod.HEAPF32;
  const rebind = () => { U8 = mod.HEAPU8; U32 = mod.HEAPU32; F32 = mod.HEAPF32; };
  const C = (fn, ...a) => { const r = mod[fn](...a); rebind(); return r; };
  C('_function_18011d400', BigInt(OBJ), 0n);
  for (let i = 0; i < 20; i++) C('_function_180120af0', BigInt(OBJ), BigInt(i), i === 19 ? 0n : f32b(val));
  C('_function_180120800', BigInt(OBJ));
  U8[OBJ + 0x248] = f248;
  for (let i = 0; i < N; i++) {
    F32[(BUF / 4) + i] = Math.fround((Math.sin(i * 0.05) * 0.7 + Math.sin(i * 0.011) * 0.3) * amp);
    F32[(BUF / 4) + N + i] = Math.fround(Math.cos(i * 0.13) * 0.5 * amp);
  }
  U32[IN_A / 4] = BUF; U32[IN_A / 4 + 2] = BUF + N * 4; U32[OU_A / 4] = BUF + N * 8; U32[OU_A / 4 + 2] = BUF + N * 12;
  for (let rep = 0; rep < 2; rep++) C('_function_18011ec20', BigInt(OBJ), BigInt(IN_A), BigInt(OU_A), BigInt(N));
  const h = crypto.createHash('sha256').update(Buffer.from(U8.slice(BUF + N * 8, BUF + N * 16))).digest('hex').slice(0, 16);
  res[key] = h;
  console.error('combo %s %dms', key, Date.now() - t0);
}
console.log(JSON.stringify(res));
