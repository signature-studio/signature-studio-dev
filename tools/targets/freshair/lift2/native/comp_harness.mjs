// comp_harness.mjs <comp.cjs> <scen.txt> [fma 0|1] — lift 済み Compressor process (wasm) を native_comp と同一シナリオで実行し同形式でダンプ。
// 各バッファは前後 64B の canary (0xA5) 付き (メモリ閉込検査, native 側 gr_alloc と同一規約)。違反時は "|GUARD" を出力。
import fs from 'node:fs'; import path from 'node:path'; import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const M = await require(path.resolve(process.argv[2]))();
const lines = fs.readFileSync(process.argv[3], 'utf8').split('\n').filter(Boolean);
const FMA = Number(process.argv[4] || 0);
const PROC = M._fa_root_180775220;
const dv = () => new DataView(M.HEAPU8.buffer);
const GRD = 64;
const al = (n) => { const p = M._malloc(n + 2 * GRD); M.HEAPU8.fill(0xa5, p, p + n + 2 * GRD); M.HEAPU8.fill(0, p + GRD, p + GRD + n); return p + GRD; };
const chk = (p, n) => { let v = 0; for (let i = 0; i < GRD; i++) { if (M.HEAPU8[p - GRD + i] !== 0xa5) v++; if (M.HEAPU8[p + n + i] !== 0xa5) v++; } return v; };
const w32 = (p, v) => dv().setUint32(p, v >>> 0, true);
const w64 = (p, v) => { dv().setUint32(p, v >>> 0, true); dv().setUint32(p + 4, 0, true); };
const r32 = (p) => dv().getUint32(p, true);
const hex = (p, n) => Buffer.from(M.HEAPU8.subarray(p, p + n)).toString('hex');
const flagPtr = Number(M._fa_va2ptr(0x1813070f8n));
let guardViol = 0;
const out = [];
for (const line of lines) {
  const t = line.split(' ').map((x) => parseInt(x, 16)); let ti = 0;
  const sidx = t[ti++], ncalls = t[ti++], vcap = t[ti++];
  const S = al(0x200), P = al(0xa400), Q = al(0x80), ctx = al(0x40), sc = al(0x80), VT = al(32 * 8);
  // vbuf は native (native_comp.c) と同一規約: plain calloc (先頭ポインタ) — grow が machine/C 側 free の対象とするため
  // canary (内部ポインタ) にすると free(begin) が dlmalloc の chunk header を誤解釈して OOB する (REPORT §10.1)。
  const vbuf = (() => { const p = M._malloc(64); M.HEAPU8.fill(0, p, p + 64); return p; })();
  w64(S + 0x90, P); w64(P + 0xa098, VT); w32(VT + 12 * 8, 0x7F000001); w64(P + 0xa128, Q);
  w64(Q + 0x28, vbuf); w64(Q + 0x30, vbuf); w64(Q + 0x38, vbuf + vcap);
  w32(P + 0xa118, 0xffffffff); w32(flagPtr, FMA);
  let o = 'S' + sidx; let bad = false;
  for (let c = 0; c < ncalls; c++) {
    const nW = t[ti++];
    for (let w = 0; w < nW; w++) {
      let rg = t[ti++]; const off = t[ti++], val = t[ti++]; const bw = rg >= 0x10; rg &= 0xf;
      const base = rg === 0 ? S : rg === 1 ? P : rg === 2 ? ctx : Q;
      if (bw) M.HEAPU8[base + off] = val & 0xff; else w32(base + off, val);
    }
    const n = t[ti++];
    const L = al((n + 1) * 4), R = al((n + 1) * 4), SL = al((n + 1) * 4), SR = al((n + 1) * 4);
    for (let i = 0; i < n; i++) { w32(L + 4 * i, t[ti + i]); w32(R + 4 * i, t[ti + n + i]); }
    ti += 2 * n;
    const hasSC = t[ti++];
    if (hasSC) { for (let i = 0; i < n; i++) { w32(SL + 4 * i, t[ti + i]); w32(SR + 4 * i, t[ti + n + i]); } ti += 2 * n; }
    w64(ctx, L); w64(ctx + 8, R); w32(ctx + 0x28, n); w64(ctx + 0x18, sc);
    w64(sc, SL); w64(sc + 8, SR); w64(sc + 24, SL); w64(sc + 32, SR);
    w32(P + 0xa118, hasSC ? 0 : 0xffffffff);
    const sp = M.stackSave();
    try { PROC(BigInt(S), BigInt(ctx)); }
    catch (e) { M.stackRestore(sp); o += ' |ERR'; if (process.env.FA_DBG) console.error('ERR', String(e).slice(0, 80), String(e.stack || '').split('\n').slice(1, 4).join(' | ')); bad = true; break; }
    const gv = chk(S, 0x200) + chk(P, 0xa400) + chk(Q, 0x80) + 0   /* vbuf は free 対象ゆえ canary 検査外 (native と同一) */
             + chk(ctx, 0x40) + chk(sc, 0x80)
             + chk(L, (n + 1) * 4) + chk(R, (n + 1) * 4) + chk(SL, (n + 1) * 4) + chk(SR, (n + 1) * 4);
    guardViol += gv;
    if (gv) o += ' |GUARD';
    o += ' |' + hex(S + 0x98, 0x70) + ' ' + hex(P + 0x9f70, 0x10) + hex(P + 0x9fb0, 0x10) + hex(P + 0x9ff8, 8) + hex(P + 0xa000, 8) + hex(P + 0xa040, 4);
    const bp = r32(Q + 0x28), ep = r32(Q + 0x30), cp = r32(Q + 0x38);
    o += ' ' + (ep - bp) + ' ' + (cp - bp) + ' ' + hex(bp, Math.min(32, ep - bp)) + ' ' + hex(L, n * 4) + ' ' + hex(R, n * 4);
  }
  out.push(o);
}
console.log(out.join('\n'));
console.error('guard violations: %d', guardViol);
if (process.env.FA_COV_OUT && M._fa_cov_ptr) {      // カバレッジ版: bitmap を JSON で書出し
  const p0 = Number(M._fa_cov_ptr()); const rep = JSON.parse(fs.readFileSync(process.env.FA_COV_REP, 'utf8'));
  const hit = {}; for (const [va, idx] of Object.entries(rep.cov_map)) hit[va] = M.HEAPU8[p0 + idx];
  fs.writeFileSync(process.env.FA_COV_OUT, JSON.stringify(hit));
}
