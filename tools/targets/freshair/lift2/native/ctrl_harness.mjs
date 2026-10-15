// ctrl_harness.mjs <ctrl.cjs> <scen.txt> [fma 0|1] — FA-2c: lift 済み制御層 (wasm) を native_ctrl と同一シナリオで実行し同形式でダンプ。
// オブジェクトグラフは native_ctrl.c の build_tree と同一契約 (実 vtable VA / 空 std::map / blk 解放先 0x1803b4070)。
import fs from 'node:fs'; import path from 'node:path'; import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const M = await require(path.resolve(process.argv[2]))();
const lines = fs.readFileSync(process.argv[3], 'utf8').split('\n').filter(Boolean);
const FMA = Number(process.argv[4] || 0);
const dv = () => new DataView(M.HEAPU8.buffer);
const state = {};
const GRD = 64;
const al = (n) => { const p = M._malloc(n + 2 * GRD); M.HEAPU8.fill(0xa5, p, p + n + 2 * GRD); M.HEAPU8.fill(0, p + GRD, p + GRD + n); return p + GRD; };
const chk = (p, n) => { let v = 0; for (let i = 0; i < GRD; i++) { if (M.HEAPU8[p - GRD + i] !== 0xa5) v++; if (M.HEAPU8[p + n + i] !== 0xa5) v++; } return v; };
const w32 = (p, v) => dv().setUint32(p, v >>> 0, true);
const w64 = (p, v) => { const b = BigInt(v); dv().setUint32(p, Number(b & 0xffffffffn), true); dv().setUint32(p + 4, Number((b >> 32n) & 0xffffffffn), true); };
const hex = (p, n) => Buffer.from(M.HEAPU8.subarray(p, p + n)).toString('hex');
const B = (v) => BigInt(v);
const P_ = {
  process: M._fa_root_1803dfc10, fctor: M._fa_root_1803dee20, mctor: M._fa_root_1803ba840,
  slot4: M._fa_root_1803e0380, slot3: M._fa_root_1803e01a0, slot13: M._fa_root_1803e01d0,
  slot7: M._fa_root_1803df050, slot9: M._fa_root_1803df060, slot8: M._fa_root_1803df030,
  slot16: M._fa_root_1803df040, slot5: M._fa_root_1803df580, slot10: M._fa_root_1803df810,
  ctor: [M._fa_root_180774cd0, M._fa_root_180b6ed50, M._fa_root_180afde00],
};
const RET0 = 0x1803b4070n;
/* #1789 FA_TRACE9=1 (既定 OFF): setter 0x180c9d700 の入口〜出口の命令前レジスタ (--trace 0x180c9d700:0x180c9d760) を読み、
 * 0x180c9d724 (ca1480 戻り直後) の rax=out[0]・rcx=out[0]+0x10 と、0x180c9d741 (vtable 読み直前) の rcx・[rcx] を出す。
 * 行 = 81 x u64 (VA, GPR16 (rax,rcx,rdx,rbx,rsp,rbp,rsi,rdi,r8..r15), XMM16x4)。 */
let traceFrom = 0;
const traceSetter = (sidx) => {
  const base = Number(M._fa_trace_ptr()), n = Number(M._fa_trace_count()); const rd = (p) => dv().getBigUint64(p, true);
  for (let r = traceFrom; r < n; r++) {
    const row = base + r * 81 * 8, va = Number(rd(row));
    if (va !== 0x180c9d729 && va !== 0x180c9d741 && va !== 0x180c9d74c) continue;
    const rax = rd(row + 8), rcx = rd(row + 16), rsp = Number(rd(row + 8 + 4 * 8));
    const out0 = va === 0x180c9d729 ? rd(rsp + 0x48) : null;
    const inHeap = rcx > 0n && rcx + 8n <= BigInt(M.HEAPU8.length);
    const vt = va === 0x180c9d741 && inHeap ? rd(Number(rcx)) : null;
    console.error('TRACE9 S' + sidx + ' va=' + va.toString(16) + ' rax=' + rax.toString(16) + ' rcx=' + rcx.toString(16) +
      ' out0=' + (out0 === null ? 'n/a' : out0.toString(16)) + ' vt=' + (vt === null ? 'n/a' : vt.toString(16)));
  }
  traceFrom = n;
};
const mdummy = al(32);                                            // model ctor arg2: [arg2+4] を M+0xa088 に写す (0)
const CHAIN = [1, 0, 1, 0, 2, 0, 2, 2];
const flagPtr = Number(M._fa_va2ptr(0x1813070f8n));
let guardViol = 0;
if (M._fa_heap_zero) M._fa_heap_zero(1);      // FA-2c: machine heap 0 初期化 (native 側と determinism 揃え)
const out = [];
for (const line of lines) {
  const t = line.split(' ').map((x) => parseInt(x, 16)); let ti = 0;
  const sidx = t[ti++], ncalls = t[ti++], vcap = t[ti++];
  const F = al(0x400), Mo = al(0xc000), ctx = al(0x100);
  const Ck = [], Wk = [], Pk = [], Qk = [], blk = [], Rgk = [], vbuf = [];
  P_.mctor(B(Mo), B(mdummy));                                    // FreshAirDspModel 実機 ctor (0x1803ba840)。arg2 は非 NULL 必須 (native と同一ダミー)
  for (let k = 0; k < 8; k++) {
    const C = al(0x2200), W = al(0x1400), P = al(0xa400), Q = al(0x80), Bk = al(0x30), RG = al(0x80010), RB = al(0x30);
    const vb = (() => { const p = M._malloc(64); M.HEAPU8.fill(0, p, p + 64); return p; })();  // plain malloc (FA-2b 規約)
    P_.ctor[CHAIN[k]](B(W), B(P), 0n, 0n);                       // 実機 wrapper ctor (0xa000×2 を machine 側 HeapAlloc で確保)
    const VT = al(32 * 8); w32(VT + 12 * 8, 0x7f000001);          // host vtable token (comp harness と同一)
    w64(P + 0xa098, VT); w64(P + 0xa128, Q); w64(P + 0x9f30, Q);
    w64(Q + 0x28, vb); w64(Q + 0x30, vb); w64(Q + 0x38, vb + vcap);
    w32(P + 0xa118, 0xffffffff); w32(P + 0xa11c, 0xffffffff);
    w64(P + 0x9f98, RG); w64(P + 0x9fa0, RB);
    w64(RB + 0x10, RB + 0x10); w32(RB + 8, 0x40); w32(RB + 0xc, 0x40); w64(RB + 0x18, RET0); w64(RB + 0x20, RET0);
    w64(C + 0x2d0, C + 0x2d0); w64(C + 0x328, process.env.FA_ALT9 ? C + 0x2d8 : C + 0x2d0);   // FA_ALT9: native_ctrl.c と同じネガコン (静的分岐強制)
    w64(C + 0x2e0, C + 0x600); w64(C + 0x600, W);
    w64(C + 0x338, C + 0x610); w64(C + 0x610, W);
    w64(C + 0x318, C + 0x2100);
    w64(C + 0x21b0, C + 0x21b8);                                  // map._Myhead = H
    for (let i = 0; i < 3; i++) w64(C + 0x21b8 + i * 8, C + 0x21b8);
    M.HEAPU8[C + 0x21d0] = 1; M.HEAPU8[C + 0x21d1] = 1;           // H._Isnil
    if (process.env.FA_NODE1) { const N = al(0x40), Z = al(0x40), NB = al(0x30);   // FA-16: native_ctrl.c と同一の 1 ノード (FA_NODE1=1 のみ)
      M.HEAPU8[N + 0x20] = 1; M.HEAPU8[N + 0x21] = 0;
      w64(N + 0x00, C + 0x21b8); w64(N + 0x08, C + 0x21b8); w64(N + 0x10, C + 0x21b8);
      w64(N + 0x28, Z); w64(N + 0x30, NB);
      w64(NB, NB + 0x10); w32(NB + 8, 0x40); w32(NB + 0xc, 0x40); w64(NB + 0x18, RET0); w64(NB + 0x20, RET0);
      w64(C + 0x21b8 + 0x00, N); w64(C + 0x21b8 + 0x08, N); w64(C + 0x21b8 + 0x10, N); }
    w64(C + 0x370, C + 0x620); w64(C + 0x480, C + 0x620);         // param block +0x10 = mgr (native_ctrl と同一のダミー mgr)
    w64(C + 0x620 + 0x10, C + 0x1900);
    w64(C + 0x1900 + 0x19a8, C + 0x1a00); w64(C + 0x1900 + 0x19b0, C + 0x1c00);
    w64(C + 0x1c00 + 0, C + 0x1c10); w32(C + 0x1c08, 0x40); w32(C + 0x1c0c, 0x40); w64(C + 0x1c18, RET0); w64(C + 0x1c20, RET0);
    w64(Bk + 0, Bk + 0x10); w32(Bk + 8, 0x40); w32(Bk + 0xc, 0x40);
    w64(Bk + 0x18, RET0); w64(Bk + 0x20, RET0);
    w64(Mo + 0xb000 + k * 16, C); w64(Mo + 0xb000 + k * 16 + 8, Bk);
    Ck.push(C); Wk.push(W); Pk.push(P); Qk.push(Q); blk.push(Bk); Rgk.push(RG); vbuf.push(vb);
  }
  w64(Mo + 0xa090, Mo + 0xb000); w64(Mo + 0xa098, Mo + 0xb080); w64(Mo + 0xa0a0, Mo + 0xb080);
  P_.fctor(B(F), B(Mo), 0n, 0n);                                  // FreshAirDsp 実機 ctor
  w32(flagPtr, FMA);
  let o = 'S' + sidx; let bad = false;
  for (let c = 0; c < ncalls; c++) {
    const nW = t[ti++];
    for (let w = 0; w < nW; w++) {
      let rg = t[ti++]; const off = t[ti++], val = t[ti++]; const bw = rg >= 0x100; const reg = rg & 0xff;
      const base = reg === 0 ? F : reg === 1 ? Mo : reg === 2 ? ctx :
        (reg & 0xf0) === 0x10 ? Wk[reg & 15] : (reg & 0xf0) === 0x20 ? Pk[reg & 15] : Ck[reg & 15];
      if (bw) M.HEAPU8[base + off] = val & 0xff; else w32(base + off, val);
    }
    const n = t[ti++];
    const L = al((n + 1) * 4), R = al((n + 1) * 4);
    if (!state.sc) { state.sc = al(0x80); state.io = al(0x100); state.sl = al(2049 * 4); state.sr = al(2049 * 4); }
    M.HEAPU8.fill(0, state.sc, state.sc + 0x80);
    for (let i = 0; i < n; i++) { w32(L + 4 * i, t[ti + i]); w32(R + 4 * i, t[ti + n + i]); }
    ti += 2 * n;
    const op = t[ti++];
    w64(ctx, L); w64(ctx + 8, R); w32(ctx + 0x28, n); M.HEAPU8[ctx + 0x60] = 0;
    w64(state.sc, state.sl); w64(state.sc + 8, state.sr); w64(state.sc + 24, state.sl); w64(state.sc + 32, state.sr);
    w64(ctx + 0x18, state.sc); w64(ctx + 0x70, state.io); w32(ctx + 0x78, 0);
    for (let k2 = 0; k2 < 8; k2++) w32(Pk[k2] + 0xa118, 0xffffffff);  // sidechain off (harness 契約)
    const sp = M.stackSave(); let ret = 0n;
    try {
      switch (op) {
        case 1: { const sb = t[ti++]; P_.slot4(B(F), new Float32Array(new Uint32Array([sb]).buffer)[0]); break; }
        case 2: P_.slot3(B(F)); break;
        case 3: P_.slot13(B(F)); break;
        case 4: ret = P_.slot7(B(F)); break;
        case 5: ret = P_.slot9(B(F)); break;
        case 6: ret = P_.slot8(B(F)); break;
        case 7: ret = P_.slot16(B(F), B(ctx)); break;
        case 8: P_.slot5(B(F), B(ctx)); break;
        case 9: P_.slot10(B(F), B(ctx)); break;
        default: P_.process(B(F), B(ctx));
      }
    } catch (e) { M.stackRestore(sp); o += ' |ERR'; if (process.env.FA_DBG) console.error('ERR', String(e).slice(0, 90), String(e.stack || '').split('\n').slice(1, 4).join(' | ')); bad = true;
      if (process.env.FA_TRACE9 && M._fa_trace_ptr) traceSetter(sidx); }
    if (bad) { /* canary 検査省略 (native も ERR 後 skip) */ }
    else {
      let gv = chk(F, 0x400) + chk(Mo, 0xc000) + chk(ctx, 0x100) + chk(L, (n + 1) * 4) + chk(R, (n + 1) * 4);
      for (let k = 0; k < 8; k++) gv += chk(Ck[k], 0x2200) + chk(Wk[k], 0x1400) + chk(Pk[k], 0xa400) + chk(Qk[k], 0x80) + chk(blk[k], 0x30) + chk(Rgk[k], 0x80010);
      guardViol += gv;
      if (gv) o += ' |GUARD';
      o += ' |' + (BigInt(ret) & 0xffffffffffffffffn).toString(16);   // native (%llx, 符号なし) と書式を合わせる
      o += ' ' + hex(F + 0x10, 0x20) + hex(F + 0x38, 0x18) + hex(F + 0x58, 0x10) + hex(F + 0x70, 0x20) + hex(F + 0x98, 0x38);
      o += ' ' + hex(Number(dv().getBigUint64(F + 0x30, true)), 0x10) + hex(Number(dv().getBigUint64(F + 0x50, true)), 0x10);
      o += ' ' + hex(Mo + 0x9ba4, 1) + hex(Mo + 0x9bec, 1) + hex(Mo + 0x9cc4, 1);
      o += ' ' + hex(Mo + 0x9dc4, 0x10) + hex(Mo + 0x9e0c, 0x10) + hex(Mo + 0x9e50, 0x20);
      o += ' ' + hex(ctx + 0x10, 1) + hex(ctx + 0x40, 1) + hex(ctx + 0x58, 8) + hex(ctx + 0x70, 0x10);
      for (let k = 0; k < 8; k++) {
        const W = Wk[k];
        o += ' ' + hex(W + 0x10, 0x20) + hex(W + 0x38, 0x18) + hex(W + 0x58, 0x10) + hex(W + 0x70, 0x20) + hex(W + 0x98, 0x78);
        o += ' ' + hex(Number(dv().getBigUint64(W + 0x30, true)), 0x10) + hex(Number(dv().getBigUint64(W + 0x50, true)), 0x10);
        const P = Pk[k];
        o += ' ' + hex(P + 0x9dc4, 0x80) + hex(P + 0x9e50, 0x100) + hex(P + 0x9f60, 0xe8);
        o += ' ' + (dv().getInt32(P + 0xa118, true) === -1 ? '01' : '00');
        const bp = Number(dv().getBigUint64(Qk[k] + 0x28, true)), ep = Number(dv().getBigUint64(Qk[k] + 0x30, true)), cp = Number(dv().getBigUint64(Qk[k] + 0x38, true));
        o += ' ' + (ep - bp) + ' ' + (cp - bp) + ' ' + hex(bp, Math.min(32, ep - bp));
        const C = Ck[k];
        o += ' ' + hex(C + 0x420, 4) + hex(C + 0x428, 8) + hex(C + 0x530, 4) + hex(C + 0x538, 8);
        o += ' ' + hex(C + 0x5d0, 1) + hex(C + 0x5e8, 4);
        o += ' ' + hex(Number(dv().getBigUint64(P + 0x9f98, true)), 8);
      }
      o += ' ' + hex(L, n * 4) + ' ' + hex(R, n * 4);
    }
    if (bad) break;
  }
  out.push(o);
}
console.log(out.join('\n'));
console.error('guard violations: %d', guardViol);
