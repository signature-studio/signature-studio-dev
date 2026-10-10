// filter_harness.mjs <filter.cjs> <scen.txt> [fma] — lift 済み Filter process (wasm) を native_filter と同一シナリオで実行し同形式でダンプ。
// 各バッファは前後 64B の canary (0xA5) 付き (メモリ閉込検査, native 側 gr_alloc と同一規約)。違反時は "|GUARD" を出力。
import fs from 'node:fs'; import path from 'node:path'; import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const M = await require(path.resolve(process.argv[2]))();
const lines = fs.readFileSync(process.argv[3], 'utf8').split('\n').filter(Boolean);
const FMA = Number(process.argv[4] || 0);
const PROC = M._fa_root_180b6f050;
const dv = () => new DataView(M.HEAPU8.buffer);
const GRD = 64;
const al = (n) => { const p = M._malloc(n + 2 * GRD); M.HEAPU8.fill(0xa5, p, p + n + 2 * GRD); M.HEAPU8.fill(0, p + GRD, p + GRD + n); return p + GRD; };
const chk = (p, n) => { let v = 0; for (let i = 0; i < GRD; i++) { if (M.HEAPU8[p - GRD + i] !== 0xa5) v++; if (M.HEAPU8[p + n + i] !== 0xa5) v++; } return v; };
const w32 = (p, v) => dv().setUint32(p, v >>> 0, true);
const w64 = (p, v) => { dv().setUint32(p, v >>> 0, true); dv().setUint32(p + 4, 0, true); };
const hex = (p, n) => Buffer.from(M.HEAPU8.subarray(p, p + n)).toString('hex');
const flagPtr = Number(M._fa_va2ptr(0x1813070f8n));
let guardViol = 0;
const out = [];
for (const line of lines) {
  const t = line.split(' ').map((x) => parseInt(x, 16)); let ti = 0;
  const sidx = t[ti++], ncalls = t[ti++];
  const S = al(0x1400), P = al(0xa400), ctx = al(0x80);
  w64(S + 0x90, P); w32(flagPtr, FMA);
  let o = 'S' + sidx;
  for (let c = 0; c < ncalls; c++) {
    const nW = t[ti++];
    for (let w = 0; w < nW; w++) {
      let rg = t[ti++]; const off = t[ti++], val = t[ti++]; const bw = rg >= 0x10; rg &= 0xf;
      const base = rg === 0 ? S : rg === 1 ? P : ctx;
      if (bw) M.HEAPU8[base + off] = val & 0xff; else w32(base + off, val);
    }
    const n = t[ti++];
    const L = al((n + 1) * 4), R = al((n + 1) * 4);
    for (let i = 0; i < n; i++) { w32(L + 4 * i, t[ti + i]); w32(R + 4 * i, t[ti + n + i]); }
    ti += 2 * n;
    w64(ctx, L); w64(ctx + 8, R); w32(ctx + 0x28, n); M.HEAPU8[ctx + 0x60] = 0;
    const sp = M.stackSave();
    try { PROC(BigInt(S), BigInt(ctx)); }
    catch (e) { M.stackRestore(sp); o += ' |ERR'; if (process.env.FA_DBG) console.error('ERR', String(e.stack).slice(0, 300)); break; }
    const gv = chk(S, 0x1400) + chk(P, 0xa400) + chk(ctx, 0x80) + chk(L, (n + 1) * 4) + chk(R, (n + 1) * 4);
    guardViol += gv;
    if (gv) o += ' |GUARD';
    o += ' |' + hex(S + 0x98, 8) + hex(S + 0xa0, 0x20 * 16) + hex(S + 0x4a0, 0x20 * 16) + hex(S + 0xca0, 0x12e0 + 0x30 - 0xca0) + ' ' + hex(L, n * 4) + ' ' + hex(R, n * 4);
  }
  out.push(o);
}
console.log(out.join('\n'));
console.error('guard violations: %d', guardViol);
