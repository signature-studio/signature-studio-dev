// FFT 規模拡張テスト (wasm, thunk 経由) — CAB-139。
// 28 関数のうち実装した全・Run 系 (Pack/CCS/Perm × in/out-of-place) を order 0..16 × flag {1,2,4,8} × {32f,64f} で回す。
// 実 IPP との突合はネイティブ・オラクル (fft_oracle.c) が担うため、ここでは:
//   - 往復の解析的整合 (scale flag の意味): Inv(Fwd(x)) == x * scaleF * scaleI
//   - Pack <-> CCS の帯内一致 / Perm 往復 == Pack 往復
//   - in-place == 非 in-place (同じ core を通るため bit 一致)
//   - エラー格子 (order/flag/NULL) と work buffer あり/なし両方
// usage: node fft_wasm_ext.mjs <ipp_shim.wasm> <ipp_sigs.json>
import fs from 'node:fs';
const [, , wasmPath, sigPath] = process.argv;
const X = new WebAssembly.Instance(new WebAssembly.Module(fs.readFileSync(wasmPath)), { env: { emscripten_notify_memory_growth() {} } }).exports;
const SIG = Object.fromEntries(JSON.parse(fs.readFileSync(sigPath, 'utf8')).entries.map((e) => [e.name, e]));
const mem = () => new Uint8Array(X.memory.buffer);
const cstr = (s) => { const b = Buffer.from(s + '\0'); const p = X.malloc(b.length); mem().set(b, p); return p; };
const GARB = 0xDEADBEEFn << 32n;
const f32bits = (v) => { const d = new DataView(new ArrayBuffer(4)); d.setFloat32(0, v, true); return BigInt(d.getUint32(0, true)); };
const BLK = X.malloc(0x100), STK = X.malloc(8 * 16);
function enc(cls, a) {
  if (cls === 'f') return GARB | f32bits(a);
  if (cls === 'd') { const d = new DataView(new ArrayBuffer(8)); d.setFloat64(0, a, true); return d.getBigUint64(0, true); }
  if (cls === 'p') return BigInt(a >>> 0);
  return GARB | BigInt(a >>> 0);
}
function call(name, args) {
  const e = SIG[name]; if (!e || e.params.length !== args.length) throw new Error(`sig/args mismatch ${name}`);
  const cookie = X.ipp_shim_getproc(cstr(name)); if (!cookie) throw new Error('unresolved ' + name);
  const dv = new DataView(X.memory.buffer);   // malloc で memory growth し得るため cookie 取得後に作る
  for (let o = 0; o < 0x100; o += 8) dv.setBigUint64(BLK + o, 0n, true);
  dv.setBigUint64(BLK, cookie, true);
  e.params.forEach((p, i) => {
    const w = enc(p.cls, args[i]);
    if (i < 4) dv.setBigUint64(BLK + (p.cls === 'f' || p.cls === 'd' ? 0x28 : 0x08) + 8 * i, w, true);
    else dv.setBigUint64(STK + 8 * (i - 4), w, true);
  });
  dv.setBigUint64(BLK + 0x48, BigInt(STK), true);
  if (!X.ipp_shim_dispatch(BLK)) throw new Error('not handled ' + name);
  return Number(BigInt.asIntN(32, new DataView(X.memory.buffer).getBigUint64(BLK + 0x80, true) & 0xFFFFFFFFn));
}
const nrms = (a, b) => { let d = 0, r = 0; for (let i = 0; i < a.length; i++) { const dv = a[i] - b[i]; d += dv * dv; r += b[i] * b[i]; } return Math.sqrt(d / (r + 1e-300)); };

let fails = 0, checks = 0;
const chk = (ok, msg) => { checks++; if (!ok) { fails++; console.log('FAIL ' + msg); } };
let rs = 123456789n;
const rnd = () => { rs = (rs * 6364136223846793005n + 1442695040888963407n) & 0xFFFFFFFFFFFFFFFFn; return Number(rs >> 40n) / 0x1000000 * 2 - 1; };

// 往復の合成ゲイン: pffft/naive とも逆変換の生値は N*IDFT。flag 1,2,4 は合成で x に戻り, 8 のみ N*x。
//   flag1: N*(1/N)*1 = 1 / flag2: N*1*(1/N) = 1 / flag4: N*(1/√N)^2 = 1 / flag8: N*1*1 = N
const RT_GAIN = { 1: () => 1, 2: () => 1, 4: () => 1, 8: (N) => N };

for (const dbl of [0, 1]) {
  const sfx = dbl ? '64f' : '32f', T = dbl ? Float64Array : Float32Array, ES = dbl ? 8 : 4;
  for (let order = 0; order <= 16; order++) {
    const N = 1 << order;
    for (const flag of [1, 2, 4, 8]) {
      for (const withBuf of [1, 0]) {
        const sp3 = X.malloc(16);
        let st = call(`ippsFFTGetSize_R_${sfx}`, [order, flag, 0, sp3, sp3 + 4, sp3 + 8]);
        const specSize = new DataView(X.memory.buffer).getInt32(sp3, true), workSize = new DataView(X.memory.buffer).getInt32(sp3 + 8, true);
        if (st !== 0) { chk(false, `GetSize ${sfx} o${order} f${flag} st=${st}`); continue; }
        chk(specSize > 0 && workSize >= 2 * N * ES, `sizes ${sfx} o${order} f${flag} spec=${specSize} work=${workSize}`);
        const spec = X.malloc(specSize + 64), pspec = X.malloc(8), pbuf = withBuf ? X.malloc(workSize + 64) : 0;
        st = call(`ippsFFTInit_R_${sfx}`, [pspec, order, flag, 0, spec, 0]);
        if (st !== 0) { chk(false, `Init ${sfx} o${order} f${flag} st=${st}`); continue; }
        const sp = new DataView(X.memory.buffer).getUint32(pspec, true);
        const pin = X.malloc(N * ES + 64), pout = X.malloc((N + 2) * ES + 64), pout2 = X.malloc((N + 2) * ES + 64);
        const x = new T(N); for (let i = 0; i < N; i++) x[i] = rnd();
        const rd = (p, n) => new T(X.memory.buffer.slice(p, p + n * ES));
        const wr = (p, a) => new T(X.memory.buffer, p, a.length).set(a);
        const buf = withBuf ? pbuf : 0;
        // 非 in-place: Fwd Pack -> Inv PackToR
        wr(pin, x);
        st = call(`ippsFFTFwd_RToPack_${sfx}`, [pin, pout, sp, buf]); chk(st === 0, `Fwd_RToPack st=${st} ${sfx} o${order} f${flag} b${withBuf}`);
        const fwd = rd(pout, N);
        st = call(`ippsFFTInv_PackToR_${sfx}`, [pout, pout2, sp, buf]); chk(st === 0, `Inv_PackToR st=${st}`);
        const rt = rd(pout2, N);
        let e = nrms(rt, x.map((v) => v * RT_GAIN[flag](N)));
        chk(e <= (dbl ? 1e-12 : 2e-5), `Pack rt ${sfx} o${order} f${flag} b${withBuf} e=${e.toExponential(2)}`);
        // CCS: 帯内一致 + Inv_CCSToR
        wr(pin, x);
        st = call(`ippsFFTFwd_RToCCS_${sfx}`, [pin, pout, sp, buf]); chk(st === 0, `Fwd_RToCCS st=${st}`);
        const ccs = rd(pout, N + 2);
        let ec = 0;
        if (N >= 4) { ec = nrms(ccs.subarray(2, N), fwd.subarray(1, N - 1)); chk(ec <= (dbl ? 1e-13 : 1e-6), `CCS-Pack 一致 ${sfx} o${order} f${flag} e=${ec.toExponential(2)}`); }
        chk(ccs[1] === 0 && ccs[N + 1] === 0, `CCS 虚部 0 ${sfx} o${order}`);
        st = call(`ippsFFTInv_CCSToR_${sfx}`, [pout, pout2, sp, buf]); chk(st === 0, `Inv_CCSToR st=${st}`);
        e = nrms(rd(pout2, N), x.map((v) => v * RT_GAIN[flag](N)));
        chk(e <= (dbl ? 1e-12 : 2e-5), `CCS rt ${sfx} o${order} f${flag} e=${e.toExponential(2)}`);
        // Perm 往復 == Pack 往復
        wr(pin, x);
        st = call(`ippsFFTFwd_RToPerm_${sfx}`, [pin, pout, sp, buf]); chk(st === 0, `Fwd_RToPerm st=${st}`);
        st = call(`ippsFFTInv_PermToR_${sfx}`, [pout, pout2, sp, buf]); chk(st === 0, `Inv_PermToR st=${st}`);
        e = nrms(rd(pout2, N), rt);
        chk(e <= (dbl ? 1e-13 : 1e-6), `Perm==Pack rt ${sfx} o${order} f${flag} e=${e.toExponential(2)}`);
        // in-place 往復 == 非 in-place 往復 (bit 一致を NRMS 0 で確認)
        wr(pin, x);
        call(`ippsFFTFwd_RToPack_${sfx}_I`, [pin, sp, buf]);
        call(`ippsFFTInv_PackToR_${sfx}_I`, [pin, sp, buf]);
        const rtI = rd(pin, N);
        let bitI = true; for (let i = 0; i < N; i++) if (rtI[i] !== rt[i]) { bitI = false; break; }
        chk(bitI, `in-place==out ${sfx} o${order} f${flag} b${withBuf}`);
        // in-place CCS (容量 N+2 で入力を置く)
        if (N >= 2) {
          const pin2 = X.malloc((N + 2) * ES + 64); wr(pin2, x);
          call(`ippsFFTFwd_RToCCS_${sfx}_I`, [pin2, sp, buf]);
          const ccsI = rd(pin2, N + 2);
          let same = true; for (let i = 0; i < N + 2; i++) if (ccsI[i] !== ccs[i]) { same = false; break; }
          chk(same, `CCS_I==CCS ${sfx} o${order} f${flag} b${withBuf}`);
        }
      }
    }
  }
  // エラー格子 (実 IPP 実測と同じ値: order<0=-17, flag不正=-18, NULL=-8)
  const gs = (o, f) => call(`ippsFFTGetSize_R_${sfx}`, [o, f, 0, sp3, sp3 + 4, sp3 + 8]);
  const sp3 = X.malloc(16);
  chk(gs(-1, 1) === -17 && gs(-5, 8) === -17, `GS order<0 ${sfx}`);
  chk(gs(8, 0) === -18 && gs(8, 3) === -18 && gs(8, 9) === -18 && gs(8, 16) === -18, `GS flag不正 ${sfx}`);
  chk(gs(17, 1) === 0 && gs(26, 1) === 0 && gs(27, 1) === -17, `GS order 上限 ${sfx}`);
  chk(gs(8, 1) === 0, `GS 正常 ${sfx}`);
  const specSize = new DataView(X.memory.buffer).getInt32(sp3, true);
  const spec = X.malloc(specSize + 64), pspec = X.malloc(8);
  chk(call(`ippsFFTInit_R_${sfx}`, [0, 8, 1, 0, spec, 0]) === -8, `Init ppSpec=NULL ${sfx}`);
  chk(call(`ippsFFTInit_R_${sfx}`, [pspec, 8, 1, 0, 0, 0]) === -8, `Init pSpec=NULL ${sfx}`);
  chk(call(`ippsFFTInit_R_${sfx}`, [pspec, 8, 3, 0, spec, 0]) === -18, `Init flag不正 ${sfx}`);
  chk(call(`ippsFFTInit_R_${sfx}`, [pspec, 8, 1, 0, spec, 0]) === 0, `Init 正常 ${sfx}`);
  const sp = new DataView(X.memory.buffer).getUint32(pspec, true);
  const pin = X.malloc(2048 + 64), pout = X.malloc(2058 + 64);
  chk(call(`ippsFFTFwd_RToPack_${sfx}`, [pin, pout, 0, 0]) === -8, `Run spec=NULL ${sfx}`);
  chk(call(`ippsFFTFwd_RToPack_${sfx}`, [0, pout, sp, 0]) === -8, `Run src=NULL ${sfx}`);
  chk(call(`ippsFFTFwd_RToPack_${sfx}`, [pin, 0, sp, 0]) === -8, `Run dst=NULL ${sfx}`);
  chk(call(`ippsFFTFwd_RToPack_${sfx}`, [pin, pout, sp, 0]) === 0, `Run buf=NULL 許容 ${sfx}`);
}
console.log(`fft_wasm_ext: checks=${checks} fails=${fails}`);
process.exit(fails ? 1 : 0);
