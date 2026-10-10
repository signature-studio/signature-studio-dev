// m10_probe.mjs (M10): m10 wasm の包括 probe。
//   P1: [F8] band 係数素性 (dsm register-exact 再計算と比較)
//   P2: processReplacing [0x248]=0/1 両経路 t1 census (junk 判定 |v|>=4 or |v|<=1e-18 nonzero or NaN)
//   P3: junk 分布 (bit パターン先頭)
// 使い方: M10_DIR=tools/m10 node m10_probe.mjs
const VA_BASE = 0x30000000;
const M10 = process.env.M10_DIR + '/work/ott_m10.cjs';
const m2 = await import(M10);
const mod = await (m2.default ? m2.default() : m2());
if (mod._m6_data_install) mod._m6_data_install();
const U8 = mod.HEAPU8, U32 = mod.HEAPU32, F32 = mod.HEAPF32;
const dv = new DataView(U8.buffer, U8.byteOffset, U8.length);
const OBJ = 0x30310000, IN_A = 0x30320000, OU_A = 0x30330000, BUF = 0x30340000;
const N = 256;
const f32b = (v) => { const f = new Float32Array(1); f[0] = v; return BigInt(new Uint32Array(f.buffer)[0]); };
const dval = (p) => dv.getFloat64(p, true);

// ---- dsm register-exact 再計算 (JS double; native const 実値)
function dsmBandSetup(f0, SR, tanf = Math.tan) {
  const PIn = 3.1428571428571401292, P2n = 6.2857142857142802583;
  const W = f0 * PIn, W2 = f0 * P2n;
  let v11 = W2 * W2, v14 = v11 * v11;
  let v0 = tanf(W / SR), v10 = 4.0;
  let v1 = W2 / v0;
  let v8 = v11, v2 = v14 * 6.0, v7 = v1 * v1;
  v8 = v8 * W2;
  let v6 = W2 * Math.SQRT2;
  let v13 = v7;
  let v5 = v7 * v1;
  v8 = v8 * Math.SQRT2;
  let v9 = v11;                    // 0x18012674c (W2^2 copy, 8 倍前)
  v11 = v11 * 8.0;
  v5 = v5 * v6;                    // P
  v8 = v8 * v1;                    // Q
  v1 = v14;
  v13 = v13 * v7;                  // C1^4 (FIX1)
  v9 = v9 * v10;                   // FIX2 : 4W2^2
  let v4 = v5, v3 = v8;
  v11 = v11 * v7;                  // U
  v3 = v3 + v8;                    // 2Q
  v0 = v8 + v14;
  v9 = v9 * v7;                    // S2
  v4 = v4 + v5;                    // 2P
  v6 = v13 * 6.0;
  v1 = v1 - v8;
  v0 = v0 - v13;
  let v12 = v3 + v9 + v13 + v4 + v14;  // K
  const A16 = 4 * (v8 + v14 - v13 - v5) / v12;
  const B16 = 4 * ((v1 - v8) + v5 - v13) / v12;
  const C16 = v2 / v12;
  const A32 = (v2 - v11 + v6) / v12;
  const B32 = (v13 - v3 + v14 - v4 + v9) / v12;
  const D1 = v14 / v12, C1c = v14 * 4.0 / v12;
  const D2 = v13 * (-4.0) / v12, E2 = v6 / v12, F2 = v13 / v12;
  return { A16, A32, B16, B32, D1, C1c, C16, D2, E2, F2 };
}

// ---- 共通 setup
function setup(val, f248) {
  mod._function_18011d400(BigInt(OBJ), 0n);
  for (let i = 0; i < 20; i++) mod._function_180120af0(BigInt(OBJ), BigInt(i), i === 19 ? 0n : f32b(val));
  mod._function_180120800(BigInt(OBJ));
  U8[OBJ + 0x248] = f248;
  for (let i = 0; i < N; i++) {
    F32[(BUF / 4) + i] = Math.fround(Math.sin(i * 0.05) * 0.7 + Math.sin(i * 0.011) * 0.3);
    F32[(BUF / 4) + N + i] = Math.fround(Math.cos(i * 0.13) * 0.5);
  }
  U32[IN_A / 4] = BUF; U32[IN_A / 4 + 2] = BUF + N * 4;
  U32[OU_A / 4] = BUF + N * 8; U32[OU_A / 4 + 2] = BUF + N * 12;
}

const res = { checks: [], detail: {} };

// P1: band coefficients
setup(0.5, 0);
const exp86 = dsmBandSetup(88.2999954223633, 44100.0);
const exp25 = dsmBandSetup(2500.0, 44100.0);
let bad = 0; const tolrel = 2e-3;  // tan ulp 差 (libm代置) を含む判定閾値
res.detail.coef = [];
for (let k = 0; k < 8; k++) {
  const st = dv.getUint32(OBJ + 0x140 + 8 * k, true);
  const got = {};
  for (const nm of ['A16', 'A32', 'B16', 'B32', 'D1', 'C1c', 'C16', 'D2', 'E2', 'F2'])
    got[nm] = dval(st + ({ A16: 0x98, A32: 0xa0, B16: 0xa8, B32: 0xb0, D1: 0x68, C1c: 0x70, C16: 0x78, D2: 0x88, E2: 0x90, F2: 0x80 }[nm]), true);
  const ex = k < 4 ? exp86 : exp25;
  let dev = 0;
  for (const nm of Object.keys(got)) {
    const base = Math.abs(ex[nm]);
    if (base > 0 && Math.abs(got[nm] - ex[nm]) / base > 1e-2) bad++;
    dev = Math.max(dev, base > 1e-300 ? Math.abs(got[nm] - ex[nm]) / base : Math.abs(got[nm] - ex[nm]));
  }
  res.detail.coef.push({ k, f0: k < 4 ? 88.3 : 2500, dev });
}
res.checks.push(['P1 band係数=dsm register-exact (FIX1-4 反映, tol 1e-2 = tan ulp 実差許容)', bad === 0]);
res.detail.coefMaxDev = Math.max(...res.detail.coef.map(c => c.dev));

// P2: junk census 両経路
for (const f248 of [0, 1]) {
  setup(0.5, f248);
  let threw = null;
  try { mod._function_18011ec20(BigInt(OBJ), BigInt(IN_A), BigInt(OU_A), BigInt(N)); }
  catch (e) { threw = String(e && e.message || e).slice(0, 60); }
  const cens = { zero: 0, normal: 0, junkHi: 0, junkTiny: 0, nan: 0 };
  for (const ch of [0, 1]) {
    for (let i = 0; i < N; i++) {
      const v = dv.getFloat32(BUF + N * 8 + ch * N * 4 + i * 4, true);
      if (v === 0) { cens.zero++; continue; }
      if (Number.isNaN(v)) { cens.nan++; continue; }
      if (Math.abs(v) >= 4) cens.junkHi++;
      else if (Math.abs(v) <= 1e-18) cens.junkTiny++;
      else cens.normal++;
    }
  }
  cens.threw = threw;
  if (f248 === 0) res.detail.cens0 = cens; else res.detail.cens1 = cens;
}

console.log(JSON.stringify(res, null, 1));
