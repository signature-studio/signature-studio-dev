// cab238_probe.mjs — CAB-238: 任意の (param, [0x248], 振幅) combo で processReplacing が
// 停止するか (無限ルーブ) を測る最小 probe (1 コマンド / timeout 必須)。
//   OTT_CJS=<build>.cjs V=0.9 F=1 A=0.0 timeout 30 node tools/ott/f7eval/cab238_probe.mjs
//   rc 0 = 完走, 124 (timeout) = 無限ルーブ, 他 = trap/異常
const ARENA = Number(process.env.LB_ARENA ?? 0x30310000);
const OBJ = ARENA, IN_A = ARENA + 0x10000, OU_A = ARENA + 0x20000, BUF = ARENA + 0x30000, N = 256;
const val = Number(process.env.V ?? 0.5), amp = Number(process.env.A ?? 1.0), f = Number(process.env.F ?? 0);
const m2 = await import(process.env.OTT_CJS);
const mod = await (m2.default ? m2.default() : m2());
if (mod._m6_data_install) mod._m6_data_install();
let U8 = mod.HEAPU8, U32 = mod.HEAPU32, F32 = mod.HEAPF32;
const rebind = () => { U8 = mod.HEAPU8; U32 = mod.HEAPU32; F32 = mod.HEAPF32; };
const C = (fn, ...a) => { const r = mod[fn](...a); rebind(); return r; };
const f32b = (v) => { const x = new Float32Array(1); x[0] = v; return BigInt(new Uint32Array(x.buffer)[0]); };
C('_function_18011d400', BigInt(OBJ), 0n);
for (let i = 0; i < 20; i++) C('_function_180120af0', BigInt(OBJ), BigInt(i), i === 19 ? 0n : f32b(val));
C('_function_180120800', BigInt(OBJ));
U8[OBJ + 0x248] = f;
for (let i = 0; i < N; i++) {
  F32[(BUF / 4) + i] = Math.fround((Math.sin(i * 0.05) * 0.7 + Math.sin(i * 0.011) * 0.3) * amp);
  F32[(BUF / 4) + N + i] = Math.fround(Math.cos(i * 0.13) * 0.5 * amp);
}
U32[IN_A / 4] = BUF; U32[IN_A / 4 + 2] = BUF + N * 4; U32[OU_A / 4] = BUF + N * 8; U32[OU_A / 4 + 2] = BUF + N * 12;
for (let rep = 0; rep < 2; rep++) C('_function_18011ec20', BigInt(OBJ), BigInt(IN_A), BigInt(OU_A), BigInt(N));
console.log('DONE v=%s f=%s amp=%s', val, f, amp);
