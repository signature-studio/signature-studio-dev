// wasm_runner.mjs — lift→wasm 側ランナー (native_runner と同じシナリオ/出力形式)。
//   node wasm_runner.mjs <module.cjs> <wasm_func> <sig.json> <scenarios.txt> <out.txt>
//   sig.json: wasm 関数の引数リスト [{"slot":0,"ty":"i64"},{"xmm":1,"ty":"i32"}, ...]
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const [modPath, fname, sigPath, scenPath, outPath] = process.argv.slice(2);
let M = await require(path.resolve(modPath))();
const mk = async () => { M = await require(path.resolve(modPath))(); };
const sig = JSON.parse(fs.readFileSync(sigPath, 'utf8'));
if (!M['_' + fname]) { console.error('no export _' + fname); process.exit(3); }
const GUARD = 64;
const lines = fs.readFileSync(scenPath, 'utf8').split('\n');
const out = [];
let bufs = [], pf = [], args = [], scen = -1, step = 0, dead = false;
const find = (nm) => { const i = bufs.findIndex((b) => b.name === nm); if (i < 0) throw new Error('no buffer ' + nm); return i; };
const dv = () => new DataView(M.HEAPU8.buffer);
const freeAll = () => { try { for (const b of bufs) M._free(b.p); } catch (e) { /* ヒープ破損: 次シナリオ前に再初期化 */ } bufs = []; pf = []; args = []; };
const applyPtr = (f) => { const a = bufs[f.db].p + f.doff; dv().setUint32(bufs[f.sb].p + f.so, a >>> 0, true); dv().setUint32(bufs[f.sb].p + f.so + 4, 0, true); };
const unhex = (h) => { const n = h.length / 2, u = new Uint8Array(n); for (let i = 0; i < n; i++) u[i] = parseInt(h.substr(2 * i, 2), 16); return u; };
const hex = (u) => Buffer.from(u).toString('hex');
function dumpAll() {
  for (let bi = 0; bi < bufs.length; bi++) {
    const b = bufs[bi], n = b.n + GUARD;
    const tmp = Uint8Array.from(M.HEAPU8.subarray(b.p, b.p + n));
    let tok = '';
    for (const f of pf) if (f.sb === bi) {
      const v = dv().getUint32(b.p + f.so, true) + dv().getUint32(b.p + f.so + 4, true) * 4294967296;
      tmp.fill(0, f.so, f.so + 8);
      let t = null;
      for (const d of bufs) if (v >= d.p && v < d.p + d.n + GUARD) { t = d.name + '+' + (v - d.p); break; }
      if (t === null) t = 'raw:' + v.toString(16);
      tok += f.so + '=' + t + ';';
    }
    out.push('D ' + b.name + ' ' + hex(tmp) + ' ' + (tok || '-'));
  }
}
for (const line of lines) {
 try {
  if (!line) continue;
  const w = line.split(' ');
  if (dead && w[0] !== 'S' && w[0] !== 'E') continue;
  switch (w[0]) {
    case 'S': freeAll(); scen = parseInt(w[1]); step = 0; dead = false; break;
    case 'B': {
      const sz = parseInt(w[2]); const p = M._malloc(sz + GUARD + 16);
      M.HEAPU8.fill(0, p, p + sz + GUARD + 16); M.HEAPU8.set(unhex(w[3]), p);
      bufs.push({ name: w[1], p, n: sz }); break;
    }
    case 'P': { const f = { sb: find(w[1]), so: parseInt(w[2]), db: find(w[3]), doff: parseInt(w[4]) }; pf.push(f); applyPtr(f); break; }
    case 'UP': {
      const sb = find(w[1]), so = parseInt(w[2]); let f = pf.find((x) => x.sb === sb && x.so === so);
      if (!f) { f = { sb, so }; pf.push(f); }
      f.db = find(w[3]); f.doff = parseInt(w[4]); applyPtr(f); break;
    }
    case 'U': M.HEAPU8.set(unhex(w[3]), bufs[find(w[1])].p + parseInt(w[2])); break;
    case 'A': args.push({ slot: parseInt(w[1]), kind: w[2], v: w[3] }); break;
    case 'C': {
      const slotval = (a) => a.kind === 'ptr' ? BigInt(bufs[find(a.v)].p) : BigInt('0x' + a.v);
      // native_runner と同じ MS x64 ABI 分割 (LIFTLIB-3): f32/f64 の A 行は xmm 仮引数
      // (%xmmK_bits), それ以外は gpr 仮引数 (%argN) に対応させる。位置対応だと
      // RetDec が誤解析した余分な %argN (tan = 実体 xmm0 1 引数なのに %arg1..3) が
      // f64 の値を横取りし %xmm0_bits が 0 になる (tan 1/40 の主因)。
      const fa = [], ga = [];
      for (const a of args) (a.kind === 'f32' || a.kind === 'f64' ? fa : ga).push(a);
      // native_runner と同じ独立カウンタ: K 番目の float 引数 → xmm K (native の c.xmm[K])。
      // %xmmK_bits 仮引数は K 番目の float 引数に対応させる (SR-4: xmm1 だけを読む関数で xmm1_bits が
      // 先頭の float 引数 (= native では xmm0) を拾う不一致の修正。xmm0 から連続する既存 sig では従来と同じ)。
      // gpr 仮引数は登場順に ga
      let gi = 0;
      const call = [];
      for (const s of sig) {
        const a = (s.xmm !== undefined) ? fa[s.xmm] : ga[gi++];
        const v = a ? slotval(a) : 0n;
        if (s.ty === 'i32') call.push(Number(v & 0xFFFFFFFFn)); else call.push(BigInt.asUintN(64, v));
      }
      let crashed = 0, ret = 0n;
      try { ret = M['_' + fname](...call); } catch (e) { crashed = 1; if (process.env.LL_VERBOSE) console.error('trap:', String(e).slice(0, 200)); }
      out.push(`R ${scen} ${step} ${crashed} ${crashed ? '0'.padStart(16, '0') : BigInt.asUintN(64, BigInt(ret ?? 0)).toString(16).padStart(16, '0')} ${'0'.padStart(16, '0')}`);
      if (crashed) { dead = true; await mk(); bufs = []; pf = []; args = []; step++; break; }
      dumpAll(); step++; break;
    }
    case 'E': out.push('E ' + scen); break;
  }
 } catch (e) {
  if (process.env.LL_VERBOSE) console.error('runner exception:', String(e).slice(0, 300));
  out.push(`R ${scen} ${step} 1 ${'0'.padStart(16, '0')} ${'0'.padStart(16, '0')}`);
  dead = true; await mk(); bufs = []; pf = []; args = []; step++;
 }
}
fs.writeFileSync(outPath, out.join('\n') + '\n');
