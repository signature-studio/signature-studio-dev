// cab238_bitcmp.mjs — CAB-238 site 評価用: 2 つの OTT wasm を同一 harness で駆動し出力 bit を比較する。
//   MOD_A (評価対象) vs MOD_B (bit-exact 参照 = tools/ott x64c lifter)。1 instantiation を使い回し
//   (e2e_check.mjs と同一プロトコル: ctor で obj を再初期化), combo ごとに 512 cell の u32 一致数を数える。
//   出力: combo ごとに 1 行 JSON {v,f,a,cells,equal,diff,censusA,censusB} + 最後に SUMMARY 行。
const { load } = await import(new URL('../diff/api.mjs', import.meta.url).href);
const A = await load(process.env.MOD_A);
const B = await load(process.env.MOD_B);
const OBJ = 0x30310000, IN_A = 0x30320000, OU_A = 0x30330000, BUF = 0x30340000, N = 256;
const combos = JSON.parse(process.env.COMBOS ?? '[[0.5,0,1.0],[0.5,1,1.0],[1.0,0,1.0],[1.0,1,1.0],[0.1,0,1.0],[0.1,1,1.0]]');
const views = {};
for (const [k, api] of [['A', A], ['B', B]]) {
  const U8 = api.mod.HEAPU8, U32 = api.mod.HEAPU32, F32 = api.mod.HEAPF32;
  const dv = new DataView(U8.buffer, U8.byteOffset, U8.length);
  views[k] = { U8, U32, F32, dv };
}
const census = (k) => {
  const { dv } = views[k];
  const r = { zero: 0, normal: 0, junkHi: 0, junkTiny: 0, nan: 0 };
  for (let i = 0; i < N * 2; i++) {
    const v = dv.getFloat32(BUF + N * 8 + i * 4, true), a = Math.abs(v);
    if (v === 0) r.zero++; else if (Number.isNaN(v)) r.nan++;
    else if (a >= 4) r.junkHi++; else if (a <= 1e-18) r.junkTiny++; else r.normal++;
  }
  return r;
};
let totA = 0, totEq = 0;
const rows = [];
for (const [v, f, amp] of combos) {
  for (const k of ['A', 'B']) {
    const api = k === 'A' ? A : B, { U8, U32, F32 } = views[k];
    api.ctor(OBJ);
    for (let i = 0; i < 20; i++) api.setParam(OBJ, i, i === 19 ? 0 : v);
    api.resume(OBJ);
    U8[OBJ + 0x248] = f;
    for (let i = 0; i < N; i++) {
      F32[BUF / 4 + i] = Math.fround((Math.sin(i * 0.05) * 0.7 + Math.sin(i * 0.011) * 0.3) * amp);
      F32[BUF / 4 + N + i] = Math.fround(Math.cos(i * 0.13) * 0.5 * amp);
    }
    U32[IN_A / 4] = BUF; U32[IN_A / 4 + 2] = BUF + N * 4;
    U32[OU_A / 4] = BUF + N * 8; U32[OU_A / 4 + 2] = BUF + N * 12;
    for (let rep = 0; rep < 2; rep++) api.process(OBJ, IN_A, OU_A, N);
  }
  const a = views.A.U32, b = views.B.U32;
  let eq = 0; const bad = [];
  for (let i = 0; i < N * 2; i++) {
    const va = a[(BUF + N * 8) / 4 + i], vb = b[(BUF + N * 8) / 4 + i];
    if (va === vb) eq++; else if (bad.length < 6) bad.push(i);
  }
  totA += N * 2; totEq += eq;
  const row = { v, f, a: amp, cells: N * 2, equal: eq, diff: N * 2 - eq, censusA: census('A'), censusB: census('B') };
  if (N * 2 - eq) row.first_bad = bad;
  rows.push(row);
  console.log(JSON.stringify(row));
}
console.log('SUMMARY ' + JSON.stringify({ combos: combos.length, cells: totA, equal: totEq, diff: totA - totEq }));
