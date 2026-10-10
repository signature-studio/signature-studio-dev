const m2 = await import(process.env.OTT_CJS);
const mod = await (m2.default ? m2.default() : m2());
if (mod._m6_data_install) mod._m6_data_install();
// lowbase (CAB-220): V-shift 先とアリーナ (obj/buf 置き場) を env で受ける。
// 既定は元 m10 chain のレイアウト (LB_BASE=0x30000000, arena は image 直後の 64K 境界)。
const LB_BASE = Number(process.env.LB_BASE ?? 0x30000000);
const ARENA = Number(process.env.LB_ARENA ?? 0x30310000);
const OBJ = ARENA, IN_A = ARENA + 0x10000, OU_A = ARENA + 0x20000, BUF = ARENA + 0x30000;
const N = 256;
// ALLOW_MEMORY_GROWTH で memory.grow が起きると ArrayBuffer が detach するため,
// 全エクスポート呼出の後にビュー (HEAPU8/HEAPU32/HEAPF32/DataView) を張り直す。
let U8, U32, F32, dv;
const rebind = () => {
  U8 = mod.HEAPU8; U32 = mod.HEAPU32; F32 = mod.HEAPF32;
  dv = new DataView(U8.buffer, U8.byteOffset, U8.length);
};
rebind();
const C = (fn, ...a) => { const r = mod[fn](...a); rebind(); return r; };
const f32b = (v) => { const f = new Float32Array(1); f[0] = v; return BigInt(new Uint32Array(f.buffer)[0]); };
const chk = [];
const ck = (nm, cond, extra = '') => { chk.push([nm, cond]); console.log((cond ? 'OK  ' : 'FAIL'), nm, extra); };

function fillInputs() {
  for (let i = 0; i < N; i++) {
    F32[(BUF / 4) + i] = Math.fround(Math.sin(i * 0.05) * 0.7 + Math.sin(i * 0.011) * 0.3);
    F32[(BUF / 4) + N + i] = Math.fround(Math.cos(i * 0.13) * 0.5);
  }
  U32[IN_A / 4] = BUF; U32[IN_A / 4 + 2] = BUF + N * 4;
  U32[OU_A / 4] = BUF + N * 8; U32[OU_A / 4 + 2] = BUF + N * 12;
}
function setup(val) {
  C('_function_18011d400', BigInt(OBJ), 0n);
  for (let i = 0; i < 20; i++) C('_function_180120af0', BigInt(OBJ), BigInt(i), i === 19 ? 0n : f32b(val));
  C('_function_180120800', BigInt(OBJ));
  U8[OBJ + 0x248] = 0;
  fillInputs();
}

// E1
setup(0.5);
ck('E1a ctor/resume ([0x30c]/[0x310]=1/1)',
   dv.getUint32(OBJ + 0x30c, true) === 1 && dv.getUint32(OBJ + 0x310, true) === 1);
C('_function_18011ec20', BigInt(OBJ), BigInt(IN_A), BigInt(OU_A), BigInt(N));
ck('E1b processReplacing 完走', true);

// E3 .rdata 直値: π̂ と 2π̂
const lin = (va) => LB_BASE + (va - 0x180000000);
const bits64 = (p) => dv.getBigUint64(p, true);
ck('E3a .rdata π̂ = 0x4009249249249243',
   bits64(lin(0x1802056E8)) === 0x4009249249249243n,
   '(0x' + bits64(lin(0x1802056E8)).toString(16) + ')');
ck('E3b .rdata 2π̂ = 0x4019249249249243',
   bits64(lin(0x1802056F8)) === 0x4019249249249243n,
   '(0x' + bits64(lin(0x1802056F8)).toString(16) + ')');
ck('E3c outputs pointer 配列 intact', dv.getUint32(OU_A, true) === BUF + N * 8);

// E4 determinism: 強制確認のため OBJ 再初期化後, 2 回同一手順 → 出力 bits 一致
const snap = () => {
  const a = new Array(N * 2);
  for (let i = 0; i < N; i++) a[i] = dv.getUint32(BUF + N * 8 + i * 4, true);
  for (let i = 0; i < N; i++) a[N + i] = dv.getUint32(BUF + N * 12 + i * 4, true);
  return a;
};
setup(0.5);
C('_function_18011ec20', BigInt(OBJ), BigInt(IN_A), BigInt(OU_A), BigInt(N));
const ref = snap();
setup(0.5);
C('_function_18011ec20', BigInt(OBJ), BigInt(IN_A), BigInt(OU_A), BigInt(N));
const ref2 = snap();
let dsum = 0;
for (let i = 0; i < N * 2; i++) if (ref[i] !== ref2[i]) dsum++;
ck('E4 determinism (再実行で出力 bits 完全一致)', dsum === 0, '(diff cells=' + dsum + ')');

// E5 param 応答
setup(0.1);
C('_function_18011ec20', BigInt(OBJ), BigInt(IN_A), BigInt(OU_A), BigInt(N));
const cmp = snap();
let ndiff = 0;
for (let i = 0; i < N * 2; i++) if (cmp[i] !== ref[i]) ndiff++;
ck('E5 t1 出力 param 応答 (0.5 vs 0.1 bits 変化)', ndiff > 100, '(diff cells=' + ndiff + ')');

// E6 junk census ([0x248]=0)
const cens = (f248) => {
  setup(0.5); U8[OBJ + 0x248] = f248;
  C('_function_18011ec20', BigInt(OBJ), BigInt(IN_A), BigInt(OU_A), BigInt(N));
  const r = { zero: 0, normal: 0, junkHi: 0, junkTiny: 0, nan: 0, absmax: 0 };
  for (let ch = 0; ch < 2; ch++) for (let i = 0; i < N; i++) {
    const v = dv.getFloat32(BUF + N * 8 + ch * N * 4 + i * 4, true);
    const a = Math.abs(v); if (a > r.absmax) r.absmax = a;
    if (v === 0) r.zero++;
    else if (Number.isNaN(v)) r.nan++;
    else if (a >= 4) r.junkHi++;
    else if (a <= 1e-18) r.junkTiny++;
    else r.normal++;
  }
  return r;
};
const c0 = cens(0), c1 = cens(1);
console.log('[INFO] census [0x248]=0 :', JSON.stringify(c0));
console.log('[INFO] census [0x248]=1 :', JSON.stringify(c1));

const broken = chk.filter(([, c]) => !c).length;
console.log(`[m10_e2e] checks ${chk.length} / broken ${broken}`);
if (broken > 0) process.exit(1);
