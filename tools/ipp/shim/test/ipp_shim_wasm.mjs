// thunk 経路の回帰テスト (wasm): 実 Intel IPP (win64 DLL, AVX512 経路) の golden 出力を、
//   「MS x64 呼出規約どおりにレジスタブロックを組む → ipp_shim_dispatch(GetProcAddress が返した cookie)」経由で再現できるかを突合する。
// ブロックの組み立ては data/ipp_sigs.json の署名 (引数クラス) だけを使い、実装関数の export は一切呼ばない。
// 敵対的設定: 32bit 整数/float 引数のレジスタ上位 32bit は 0xDEADBEEF のゴミ (MS ABI では未定義) で渡す。
// usage: node ipp_shim_wasm.mjs <ipp_shim.wasm> <goldenDir> <ipp_sigs.json> [out.json]
import fs from 'node:fs';
const [, , wasmPath, gdir, sigPath, outPath] = process.argv;
const X = new WebAssembly.Instance(new WebAssembly.Module(fs.readFileSync(wasmPath)), { env: { emscripten_notify_memory_growth() {} } }).exports;
const SIG = Object.fromEntries(JSON.parse(fs.readFileSync(sigPath, 'utf8')).entries.map((e) => [e.name, e]));
const mem = () => new Uint8Array(X.memory.buffer);
const cstr = (s) => { const b = Buffer.from(s + '\0'); const p = X.malloc(b.length); mem().set(b, p); return p; };
const GARB = 0xDEADBEEFn << 32n;
const f32bits = (v) => { const d = new DataView(new ArrayBuffer(4)); d.setFloat32(0, v, true); return BigInt(d.getUint32(0, true)); };
const f32 = (b) => { const t = new DataView(new ArrayBuffer(4)); t.setUint32(0, b >>> 0, true); return t.getFloat32(0, true); };

// ---- ブロック: +0x00 target, +0x08 rcx rdx r8 r9, +0x28 xmm0-3, +0x48 stk, +0x80 rax, +0x88 xmm0ret ----
const BLK = X.malloc(0x100), STK = X.malloc(8 * 16);
// args: [{v: number|bigint, f32?: bool}] を署名のクラスに従って配置。数値は JS number (ポインタ/int) か、浮動小数は {f: value}。
function enc(cls, a) {
  if (cls === 'f') return GARB | f32bits(a);                                   // xmm 下位 32bit = float, 上位ゴミ
  if (cls === 'd') { const d = new DataView(new ArrayBuffer(8)); d.setFloat64(0, a, true); return d.getBigUint64(0, true); }
  if (cls === 'p') return BigInt(a >>> 0);                                      // ポインタ: ゼロ拡張
  if (cls === 'i' || cls === 'u' || cls === 'b' || cls === 'h' || cls === 'H') return GARB | BigInt(a >>> 0);  // 32bit 整数: 上位ゴミ
  throw new Error('class ' + cls);
}
function call(name, args) {
  const e = SIG[name]; if (!e || e.params.length !== args.length) throw new Error(`sig/args mismatch ${name}: ${e?.params.length} vs ${args.length}`);
  const dv = new DataView(X.memory.buffer);
  for (let o = 0; o < 0x100; o += 8) dv.setBigUint64(BLK + o, 0n, true);
  const cookie = X.ipp_shim_getproc(cstr(name)); if (!cookie) throw new Error('unresolved ' + name);
  dv.setBigUint64(BLK, cookie, true);
  e.params.forEach((p, i) => {
    const w = enc(p.cls, args[i]);
    if (i < 4) dv.setBigUint64(BLK + (p.cls === 'f' || p.cls === 'd' ? 0x28 : 0x08) + 8 * i, w, true);
    else dv.setBigUint64(STK + 8 * (i - 4), w, true);
  });
  dv.setBigUint64(BLK + 0x48, BigInt(STK), true);
  const handled = X.ipp_shim_dispatch(BLK);
  if (!handled) throw new Error('not handled ' + name);
  return Number(BigInt.asIntN(32, new DataView(X.memory.buffer).getBigUint64(BLK + 0x80, true) & 0xFFFFFFFFn));
}

// ================= 24 関数 golden 突合 (ipp_wasm_cmp.mjs と同一の判定) =================
const man = JSON.parse(fs.readFileSync(`${gdir}/manifest.json`, 'utf8')).cases, blob = fs.readFileSync(`${gdir}/blob.bin`);
const ord = (b) => (b & 0x80000000) ? -(b & 0x7fffffff) : b;
const KIND = { A: 0, B: 1, C: 2, D: 3, E: 4, G: 5, H: 6, I: 7, J: 8, A8: 9, B8: 10 };
const isF = (k) => !(k === KIND.I || k === KIND.J || k === KIND.A8 || k === KIND.B8);
const sz = (Math.max(...man.map((c) => c.u)) + 16) * 4;
const pa = X.malloc(sz), pb = X.malloc(sz), pd = X.malloc(sz);
const stats = {};
for (const c of man) {
  const o = c.blob, u4 = c.u * 4, M = mem();
  M.set(blob.subarray(o, o + u4), pa); M.set(blob.subarray(o + u4, o + 2 * u4), pb); M.set(blob.subarray(o + 2 * u4, o + 3 * u4), pd);
  const v = f32(c.v), v2 = f32(c.v2); let st;
  switch (c.kind) {
    case KIND.A: case KIND.A8: st = call(c.fn, [pa, pd, c.n]); break;
    case KIND.B: case KIND.B8: st = call(c.fn, [pd, c.n]); break;
    case KIND.C: st = call(c.fn, [pa, v, pd, c.n]); break;
    case KIND.D: st = call(c.fn, [v, pd, c.n]); break;
    case KIND.E: st = call(c.fn, [pa, pb, pd, c.n]); break;
    case KIND.G: st = call(c.fn, [pd, c.n, v]); break;
    case KIND.H: st = call(c.fn, [pd, c.n, v, v2]); break;
    case KIND.I: st = call(c.fn, [pa, pd, c.n, c.rnd, c.sfs]); break;
    case KIND.J: st = call(c.fn, [c.ival | 0, pd, c.n]); break;
    default: throw new Error('kind ' + c.kind);
  }
  const outW = new Uint32Array(mem().buffer.slice(pd, pd + u4));
  const ref = new Uint32Array(blob.buffer.slice(blob.byteOffset + o + 3 * u4, blob.byteOffset + o + 4 * u4));
  const s = stats[c.fn] ??= { cases: 0, elems: 0, exact: 0, nan_payload_diff: 0, differ: 0, max_ulp: 0, max_rel: 0, status_mismatch: 0, nonfinite_mismatch: 0 };
  s.cases++; if (st !== c.st) s.status_mismatch++;
  for (let i = 0; i < c.u; i++) {
    s.elems++;
    if (outW[i] === ref[i]) { s.exact++; continue; }
    if (isF(c.kind)) {
      const fr = f32(ref[i]), fo = f32(outW[i]);
      if (Number.isNaN(fr) && Number.isNaN(fo)) { s.nan_payload_diff++; continue; }
      s.differ++;
      if (Number.isFinite(fr) && Number.isFinite(fo)) { s.max_ulp = Math.max(s.max_ulp, Math.abs(ord(ref[i]) - ord(outW[i]))); s.max_rel = Math.max(s.max_rel, Math.abs(fr - fo) / (Math.abs(fr) + 1e-45)); } else s.nonfinite_mismatch++;
    } else s.differ++;
  }
}
const TOL = { ippsSqrt_32f_A11: { rel: 3e-4 }, ippsExp_32f_A11: { rel: 3e-4 }, ippsVectorSlope_32f: { loose: true } };
let bad = 0; const rows = [];
for (const [fn, s] of Object.entries(stats)) {
  const t = TOL[fn]; const ok = !t ? (s.differ === 0 && s.status_mismatch === 0) : t.rel ? (s.max_rel <= t.rel && s.nonfinite_mismatch === 0) : true;
  if (!ok) bad++;
  rows.push({ fn, ...s, bit_exact_all: s.differ === 0, verdict: ok ? 'PASS' : 'FAIL' });
}
for (const r of rows) console.log(r.verdict.padEnd(5), r.fn.padEnd(26), `elems=${r.elems} exact=${r.exact} nanPayloadDiff=${r.nan_payload_diff} differ=${r.differ} statusMis=${r.status_mismatch} maxUlp=${r.max_ulp} maxRel=${r.max_rel.toExponential(2)}`);
const nExact = rows.filter((r) => r.bit_exact_all).length;
console.log(`wasm thunk path vs real-IPP golden: functions=${rows.length} fail=${bad} bitExactFunctions=${nExact}`);

// ================= FFT (実 IPP golden, Pack/CCS 形式, 32f/64f 全 flag): GetSize/Init/Fwd/Inv を全て thunk 経由 =================
const fcases = JSON.parse(fs.readFileSync(`${gdir}/fft_golden.json`, 'utf8')), fblob = fs.readFileSync(`${gdir}/fft_golden.bin`);
const nrms = (a, b) => { let d = 0, r = 0; for (let i = 0; i < a.length; i++) { d += (a[i] - b[i]) ** 2; r += b[i] ** 2; } return Math.sqrt(d / (r + 1e-300)); };
let worst32 = 0, worst64 = 0, fbad = 0;
for (const c of fcases) {
  const N = 1 << c.order, es = c.dbl ? 8 : 4, T = c.dbl ? Float64Array : Float32Array, sfx = c.dbl ? '64f' : '32f';
  const rd = (k) => new T(fblob.buffer.slice(fblob.byteOffset + c.off + k * N * es, fblob.byteOffset + c.off + (k + 1) * N * es));
  const x = rd(0), fwdRef = rd(1), invRef = rd(2);
  const sp3 = X.malloc(16);
  let st = call(`ippsFFTGetSize_R_${sfx}`, [c.order, c.flag, 0, sp3, sp3 + 4, sp3 + 8]);
  const specSize = new DataView(X.memory.buffer).getInt32(sp3, true);
  const spec = X.malloc(specSize + 64), pspec = X.malloc(8);
  st |= call(`ippsFFTInit_R_${sfx}`, [pspec, c.order, c.flag, 0, spec, 0]);
  const sp = new DataView(X.memory.buffer).getUint32(pspec, true);
  const pin = X.malloc(N * es + 64), pout = X.malloc(N * es + 64);
  new T(X.memory.buffer, pin, N).set(x);
  st |= call(`ippsFFTFwd_RToPack_${sfx}`, [pin, pout, sp, 0]);
  const e1 = nrms(new T(X.memory.buffer.slice(pout, pout + N * es)), fwdRef);
  new T(X.memory.buffer, pin, N).set(fwdRef);
  st |= call(`ippsFFTInv_PackToR_${sfx}`, [pin, pout, sp, 0]);
  const e2 = nrms(new T(X.memory.buffer.slice(pout, pout + N * es)), invRef);
  // in-place 版も thunk 経由で一致 (署名 3 引数)
  new T(X.memory.buffer, pin, N).set(x);
  st |= call(`ippsFFTFwd_RToPack_${sfx}_I`, [pin, sp, 0]);
  const e3 = nrms(new T(X.memory.buffer.slice(pin, pin + N * es)), fwdRef);
  const e = Math.max(e1, e2, e3); if (c.dbl) worst64 = Math.max(worst64, e); else worst32 = Math.max(worst32, e);
  if (e > (c.dbl ? 1e-12 : 5e-6) || st) fbad++;
}
console.log(`fft via thunk vs real IPP: cases=${fcases.length} worstNRMS32f=${worst32.toExponential(2)} worstNRMS64f=${worst64.toExponential(2)} bad=${fbad}`);

// ================= 表: 420 名 / fail-soft =================
const cnt = new DataView(X.memory.buffer).getInt32(X.ipp_shim_table_count.value ?? X.ipp_shim_table_count, true);
let stubOk = true; X.ipp_shim_reset();
const sc = (n) => { const dv = new DataView(X.memory.buffer); for (let o = 0; o < 0x100; o += 8) dv.setBigUint64(BLK + o, 0n, true); dv.setBigUint64(BLK, X.ipp_shim_getproc(cstr(n)), true); dv.setBigUint64(BLK + 0x80, 0xFFn, true); X.ipp_shim_dispatch(BLK); return new DataView(X.memory.buffer).getBigUint64(BLK + 0x80, true); };
for (const n of ['ippsConv_32f', 'ippiResizeSqrPixel_8u_C4R', 'ippsFIR_32f']) if (sc(n) !== 0n) stubOk = false;
const tbl = { count: cnt, stub_calls: X.ipp_shim_stub_calls_total(), stub_distinct: X.ipp_shim_stub_distinct(), stub_failsoft_ok: stubOk, last_stub: X.ipp_shim_last_stub() };
console.log('table', JSON.stringify(tbl));
if (outPath) fs.writeFileSync(outPath, JSON.stringify({ rows, fft: { worst32, worst64, bad: fbad }, table: tbl }, null, 1));
process.exit(bad || fbad || !stubOk || cnt !== 420 || tbl.stub_distinct !== 3 ? 1 : 0);
