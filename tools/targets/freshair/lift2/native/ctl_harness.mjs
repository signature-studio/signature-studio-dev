// ctl_harness.mjs <ctl.cjs> <scen.txt> [fma] — FA-2c: lift 済み FreshAirDsp 制御層 (wasm) を
// native_freshair と同一シナリオ・同一グラフ構築で実行し同形式でダンプ。
// 各ブロックは前後 256B canary (0xA5) 付き (native gr_alloc と同一規約)。
import fs from 'node:fs'; import path from 'node:path'; import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const M = await require(path.resolve(process.argv[2]))();
const lines = fs.readFileSync(process.argv[3], 'utf8').split('\n').filter(Boolean);
const FMA = Number(process.argv[4] || 0);
const PROC = M._fa_root_1803dfc10;
const dv = () => new DataView(M.HEAPU8.buffer);
const GRD = 256;
const al = (n) => { const p = M._malloc(n + 2 * GRD); M.HEAPU8.fill(0xa5, p, p + n + 2 * GRD); M.HEAPU8.fill(0, p + GRD, p + GRD + n); return p + GRD; };
const chk = (p, n) => { let v = 0; for (let i = 0; i < GRD; i++) { if (M.HEAPU8[p - GRD + i] !== 0xa5) v++; if (M.HEAPU8[p + n + i] !== 0xa5) v++; } return v; };
const calloc0 = (n) => { const p = M._malloc(n); M.HEAPU8.fill(0, p, p + n); return p; };
const w32 = (p, v) => dv().setUint32(p, v >>> 0, true);
const w64 = (p, v) => { dv().setUint32(p, v >>> 0, true); dv().setUint32(p + 4, (v / 4294967296) >>> 0, true); };
const r32 = (p) => dv().getUint32(p, true);
const hex = (p, n) => Buffer.from(M.HEAPU8.subarray(p, p + n)).toString('hex');
const flagPtr = Number(M._fa_va2ptr(0x1813070f8n));

const VT_FRESHAIR = 0x1810cab70, VT_COMP = 0x1810E1BE8, VT_FILTER = 0x1810FAAD0, VT_GAIN = 0x1810F8870;
const R_F = 0, R_PH = 1, R_CH = 2, R_DS = 0xa, R_DP = 0x12, R_MASK = 0x1f, R_BYTE = 0x20;
const NCH = 8, SZ_F = 0xd0, SZ_PH = 0xa400, SZ_CH = 0xc00, SZ_DS = 0x200, SZ_DP = 0xa400, EVN = 128;
const vtOf = (t) => t === 0 ? VT_COMP : t === 1 ? VT_FILTER : VT_GAIN;

// host vtable: token 0x7F000001 at slot +0x60 (FA-2b 規約)
function mkVT() { const vt = al(32 * 8); w32(vt + 12 * 8, 0x7F000001); return vt; }
const VTPL = mkVT();

// 空 std::map: reg+0xb0 = header {_Parent(+8) = 自身, isnil}
function mapEmpty(reg, hn) { w64(hn + 8, hn); M.HEAPU8[hn + 0x19] = 1; w64(reg + 0xb0, hn); }
// 3 node BST (root 0x158, left 0x157, right 0x15a)
function mapMacros(reg, hn, ns, holders, blks) {
  const keys = [0x157, 0x158, 0x15a];
  for (let k = 0; k < 3; k++) {
    const n = ns[k];
    w32(n + 0x20, keys[k]); w64(n + 0x28, holders[k]); w64(n + 0x30, blks[k]);
    w64(n + 0x00, hn); w64(n + 0x10, hn);
  }
  w64(hn + 8, ns[1]); w64(hn + 0, ns[0]); w64(hn + 0x10, ns[2]); M.HEAPU8[hn + 0x19] = 1;
  w64(ns[1] + 0x00, ns[0]); w64(ns[0] + 8, ns[1]);
  w64(ns[1] + 0x10, ns[2]); w64(ns[2] + 8, ns[1]);
  w64(ns[1] + 8, hn);
  w64(reg + 0xb0, hn);
}

let guardViol = 0;
const out = [];
for (const line of lines) {
  const t = line.split(' ').map((x) => parseInt(x, 16)); let ti = 0;
  const sidx = t[ti++], ncalls = t[ti++], chain = t[ti++];
  const mid = t[ti++], high = t[ti++], trim = t[ti++];
  const nP = t[ti++];
  const ctype = []; for (let i = 0; i < 8; i++) { const v = (chain >>> (2 * i)) & 3; ctype.push(v === 3 ? 2 : v); }
  // ---- グラフ構築 (native_freshair.c build_graph と同一)
  const F = al(SZ_F), PH = al(SZ_PH);
  const fbuf1 = al(0xa000), fbuf2 = al(0xa000);
  const sc = al(0x80), io = al(0x100), nobj = al(0x180);
  const vec = calloc0(0x200);
  w64(F, 0x00, VT_FRESHAIR); M.HEAPU8[F + 0x10] = 1;
  w32(F, 0x18, 0x40); w64(F, 0x1c, 0x2800);
  w32(F, 0x28, 0); w64(F, 0x30, fbuf1);
  w32(F, 0x38, 0x40); w64(F, 0x3c, 0x2800);
  w32(F, 0x48, 0); w64(F, 0x50, fbuf2);
  w64(F, 0x70, 0);
  w32(F, 0x78, 0); w32(F, 0x7c, 0x3f800000); w32(F, 0x80, 0x3f800000); w32(F, 0x84, 0x3f800000);
  M.HEAPU8[F + 0x88] = 0;
  w32(F, 0x58, 0);
  w64(F, 0x68, PH); w64(F, 0x90, PH);
  w32(F, 0x9c, 0x3d23d70a);
  w64(F, 0xa4, 0); w32(F, 0xac, 0); w32(F, 0xb0, 0x3df5c28f);
  w32(F, 0xbc, 0x800000); w32(F, 0xc0, 0x800000); w32(F, 0xc4, 0x3f800000);
  w64(PH, 0xa090, vec); w64(PH, 0xa098, vec + 16 * NCH); w64(PH, 0xa0a0, vec + 0x200);
  w64(nobj, 0x28, nobj + 0x40); w64(nobj, 0x30, nobj + 0x40); w64(nobj, 0x38, nobj + 0x40 + 0x100);
  w64(PH, 0xa1a8, nobj);
  const CH = [], DS = [], DP = [], Q = [], REG = [], REGH = [];
  for (let i = 0; i < NCH; i++) {
    const ch = al(SZ_CH), ds = al(SZ_DS), dp = al(SZ_DP), q = al(0x80);
    const vbuf = calloc0(64);
    const arrA = al(16), arrB = al(16), ev = al(EVN * 16);
    const bufL = al(0x8000), bufR = al(0x8000);
    const hn = al(0x28), hn2 = al(0x28), hnH = al(0x28);
    const reg = al(0x100), regh = al(0x100);
    const holders = [al(0x400), al(0x400), al(0x400)];
    const blks = [al(0x20), al(0x20), al(0x20)];
    const nodes = [al(0x40), al(0x40), al(0x40)];
    w64(ds, 0x00, vtOf(ctype[i]));
    w32(ds, 0x58, 0); w32(ds, 0x5c, 0x7fffffff); M.HEAPU8[ds + 0x60] = 0;
    w64(ds, 0x68, dp); w32(ds, 0x70, 0);
    w32(ds, 0x78, 0); w32(ds, 0x7c, 0x3f800000); w32(ds, 0x80, 0x3f800000);
    w32(ds, 0x84, 0x3f800000); M.HEAPU8[ds + 0x88] = 0;
    w32(ds, 0x8c, 0);
    w32(ds, 0x1c, 0); w32(ds, 0x24, 0); w64(ds, 0x30, bufL); w32(ds, 0x28, 0);
    w32(ds, 0x3c, 0); w32(ds, 0x44, 0); w64(ds, 0x50, bufR); w32(ds, 0x48, 0);
    w64(ds, 0x90, dp); w32(ds, 0x98, 0x4650c000);
    w64(dp, 0xa098, VTPL); w32(dp, 0xa118, 0xffffffff); w64(dp, 0xa128, q);
    w64(q, 0x28, vbuf); w64(q, 0x30, vbuf); w64(q, 0x38, vbuf + 64);
    w64(ch, 0x2d0, ch); w64(ch, 0x328, ch);
    w64(arrA, 0, ds); w64(arrB, 0, ds);
    w64(ch, 0x2e0, arrA); w64(ch, 0x338, arrB);
    w64(ch, 0x360 + 0x10, PH); w64(ch, 0x360 + 0x30, ev); w64(ch, 0x360 + 0x48, 0);
    w32(ch, 0x5e8, 0);
    if (i === 0) mapMacros(reg, hn, nodes, holders, blks); else mapEmpty(reg, hn2);
    w64(ch, 0x318, reg);
    for (let k = 0; k < 3; k++) {
      const h = holders[k];
      w64(h, 0x2d0, h); w64(h, 0x328, h);
      mapEmpty(regh, hnH);
      w64(h, 0x318, regh);
      w32(blks[k], 8, 1);
    }
    w64(vec + 16 * i, 0, ch); w64(vec + 16 * i + 8, blks[0]);
    CH.push(ch); DS.push(ds); DP.push(dp); Q.push(q); REG.push(reg); REGH.push(regh);
  }
  w32(PH, 0x9dc4, mid); w32(PH, 0x9e0c, high); w32(PH, 0x9e60, trim);
  // ---- reg code → block
  const base = (rg) => {
    rg &= R_MASK;
    if (rg === R_F) return F;
    if (rg === R_PH) return PH;
    if (rg >= R_CH && rg < R_DS) return CH[rg - R_CH];
    if (rg >= R_DS && rg < R_DP) return DS[rg - R_DS];
    if (rg >= R_DP && rg < R_DP + NCH) return DP[rg - R_DP];
    return 0;
  };
  const applyWrite = (rg, off, val) => {
    const bw = rg >= R_BYTE; const b = base(rg);
    if (!b) return;
    if (bw) M.HEAPU8[b + off] = val & 0xff; else w32(b + off, val);
  };
  for (let w = 0; w < nP; w++) { const rg = t[ti++], off = t[ti++], val = t[ti++]; applyWrite(rg, off, val); }
  let o = 'S' + sidx;
  for (let c = 0; c < ncalls; c++) {
    const n = t[ti++];
    const L = al((n + 1) * 4), R = al((n + 1) * 4), SL = al((n + 1) * 4), SR = al((n + 1) * 4);
    for (let i = 0; i < n; i++) { w32(L + 4 * i, t[ti + i]); w32(R + 4 * i, t[ti + n + i]); }
    ti += 2 * n;
    const nP2 = t[ti++];
    for (let w = 0; w < nP2; w++) { const rg = t[ti++], off = t[ti++], val = t[ti++]; applyWrite(rg, off, val); }
    const ctx = al(0x80);
    w64(ctx, 0x00, L); w64(ctx, 0x08, R); w64(ctx, 0x18, sc); w32(ctx, 0x28, n); w64(ctx, 0x70, io); w32(ctx, 0x78, 0);
    M.HEAPU8.fill(0, sc, sc + 0x80);
    w64(sc, 0x00, SL); w64(sc, 0x08, SR); w64(sc, 24, SL); w64(sc, 32, SR);
    w32(flagPtr, FMA);
    const sp = M.stackSave();
    try { PROC(BigInt(F), BigInt(ctx)); }
    catch (e) { M.stackRestore(sp); o += ' |ERR'; if (process.env.FA_DBG) console.error('ERR', String(e).slice(0, 90), String(e.stack || '').split('\n').slice(1, 4).join(' | ')); break; }
    let gv = chk(F, SZ_F) + chk(PH, SZ_PH);
    for (let i = 0; i < NCH; i++) gv += chk(CH[i], SZ_CH) + chk(DS[i], SZ_DS) + chk(DP[i], SZ_DP) + chk(Q[i], 0x80);
    gv += chk(ctx, 0x80) + chk(sc, 0x80) + chk(L, (n + 1) * 4) + chk(R, (n + 1) * 4);
    guardViol += gv;
    if (gv) o += ' |GUARD';
    o += ' |' + hex(F + 0x10, 0x20) + hex(F + 0x38, 0x18) + hex(F + 0x58, 0x78);
    o += ' ' + hex(PH + 0x9e98, 0x50) + hex(PH + 0x9f70, 0x60);
    const vb = r32(PH + 0xa090), ve = r32(PH + 0xa098);
    o += ' ' + (ve - vb);
    const nb = r32(PH + 0xa1a8);
    const nbgn = r32(nb + 0x28), nend = r32(nb + 0x30);
    o += ' ' + (nend - nbgn) + hex(nb + 0x40, Math.min(32, nend - nbgn));
    for (let i = 0; i < NCH; i++) {
      o += ' ' + M.HEAPU8[CH[i] + 0x5d0].toString(16).padStart(2, '0')
        + '|' + dv().getInt32(CH[i] + 0x5e8, true)
        + '|' + dv().getUint32(CH[i] + 0x360 + 0x48, true)
        + '|' + dv().getInt32(DS[i] + 0x58, true);
      o += '|' + M.HEAPU8[DS[i] + 0x60].toString(16).padStart(2, '0')
        + '|' + dv().getInt32(DS[i] + 0x5c, true)
        + '|' + dv().getInt32(DS[i] + 0x28, true);
      o += '|' + M.HEAPU8[DS[i] + 0x8c].toString(16).padStart(2, '0');
      o += '|' + hex(DS[i] + 0x1c, 8);
      o += '|' + hex(DP[i] + 0x9f70, 0x10) + hex(DP[i] + 0x9fb0, 0x10) + hex(DP[i] + 0x9ff8, 8) + hex(DP[i] + 0xa000, 8);
    }
    o += ' ' + hex(L, n * 4) + ' ' + hex(R, n * 4);
  }
  out.push(o);
}
console.log(out.join('\n'));
console.error('guard violations: %d', guardViol);
