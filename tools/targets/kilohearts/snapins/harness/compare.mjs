// compare.mjs — ctx-fuzz 差分: native_ref の vectors.bin を wasm(lift) で再生して全バイト突合する。
//   node compare.mjs <vectors.bin> <module.cjs> <sigs.json> [--tol tol.json] [--v] [--json out.json]
// sigs.json: { "<va hex>": {"params":["i64","i64","float"], "ret":"i64"} }  (kh_sigs.py が最終 .ll から生成)
// --tol (CAB-224): 指定 region×範囲を f32/f64 値とみなし、tools/liftlib/liftlib/simd/simdtest.py と
//   同一基準の相対誤差 gate で判定する (近似命令 rcpps/rsqrtps 経路の CPU 依存差を許容)。
//   tol.json: { "<region>": {"f32": [[off,len],...], "f64": [[off,len],...] } }  (off/len = region 先頭からの byte)
//   gate: |a-b| > 1.6*2^-12*max(|a|,|b|) + 1e-38 → 不一致 (両方 NaN は OK, ±inf は値一致必須)。
//   --tol 無しの既定動作 = 従来どおり全バイト bit-exact (既存 6 snapin の判定は不変)。
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);

const args = process.argv.slice(2);
const verbose = args.includes('--v');
const jIdx = args.indexOf('--json');
const jsonOut = jIdx >= 0 ? args[jIdx + 1] : null;
const tIdx = args.indexOf('--tol');
const tolPath = tIdx >= 0 ? args[tIdx + 1] : null;
const pos = args.filter((a, i) => !a.startsWith('--') && args[i - 1] !== '--json' && args[i - 1] !== '--tol');
const [vecPath, modPath, sigPath] = pos;
const ARENA = 0x04000000;

const tol = tolPath ? JSON.parse(fs.readFileSync(tolPath, 'utf8')) : null;
const TOL_GATE = 1.6 * 2 ** -12;   // liftlib simdtest.py の実 gate 値 (仕様上限 1.5*2^-12 + 余裕)
const TOL_FLOOR = 1e-38;

const buf = fs.readFileSync(vecPath);
const dv = new DataView(buf.buffer, buf.byteOffset, buf.byteLength);
let p = 0;
const u32 = () => { const v = dv.getUint32(p, true); p += 4; return v; };
const u64 = () => { const v = dv.getBigUint64(p, true); p += 8; return v; };
if (buf.toString('latin1', 0, 4) !== 'KHV2') throw new Error('bad magic');
p = 4;
const ntrials = u32(); u32();

const sigs = JSON.parse(fs.readFileSync(sigPath, 'utf8'));
const Mod = require(path.resolve(modPath));
const M = await Mod();
const H8 = () => M.HEAPU8;
const f32 = new Float32Array(1), u32a = new Uint32Array(f32.buffer);
const f64 = new Float64Array(1), u64a = new BigUint64Array(f64.buffer);
const bitsToF32 = (b) => { u32a[0] = Number(BigInt(b) & 0xffffffffn); return f32[0]; };
const bitsToF64 = (b) => { u64a[0] = BigInt(b); return f64[0]; };
const f32bits = (x) => { f32[0] = x; return u32a[0]; };

// tol 用: region 名 → {entries: [{off, len, ty}], absFloor}
const tolMap = new Map();
if (tol) {
  for (const [name, spec] of Object.entries(tol)) {
    const arr = [];
    for (const ty of ['f32', 'f64']) for (const e of (spec[ty] || [])) arr.push({ off: e[0], len: e[1], ty: e[2] || ty });
    if (arr.length) tolMap.set(name, { entries: arr, absFloor: spec.absFloor || TOL_FLOOR });
  }
}
const tolAt = (regs, off) => {
  for (const r of regs) {
    if (off >= r.off && off < r.off + r.len) {
      const rel = off - r.off, spec = tolMap.get(r.name);
      if (!spec) return null;
      for (const s of spec.entries) if (rel >= s.off && rel < s.off + s.len) return { ty: s.ty, where: `${r.name}+0x${rel.toString(16)}`, floor: spec.absFloor };
      return null;
    }
  }
  return null;
};
const isNan32 = (b) => (b & 0x7f800000) === 0x7f800000 && (b & 0x7fffff) !== 0;
const isNan64hi = (w32hi) => (w32hi & 0x7ff00000) === 0x7ff00000;
// simdtest.py compare_form と同一の gate (+ absFloor: 音声経路の離散化増幅分会)。戻り: 'exact' | {ok, rel, abs}
const gate = (wa, wb, ty, floor) => {
  if (wa === wb) return { ok: true, exact: true };
  const fl = floor === undefined ? TOL_FLOOR : floor;
  if (ty === 'f32') {
    const a = bitsToF32(wa), b = bitsToF32(wb);
    if (isNan32(wa >>> 0) && isNan32(wb >>> 0)) return { ok: true, nan: true };
    if (!Number.isFinite(a) || !Number.isFinite(b)) return { ok: a === b };
    const abs = Math.abs(a - b), rel = abs / Math.max(Math.abs(a), Math.abs(b));
    return abs > TOL_GATE * Math.max(Math.abs(a), Math.abs(b)) + fl ? { ok: false, rel, abs } : { ok: true, rel, abs };
  }
  const a = bitsToF64(wa), b = bitsToF64(wb);
  const na = isNan64hi(Number((wa >> 32n) & 0xffffffffn)) && (wa & 0xfffffffffffffn) !== 0n;
  const nb = isNan64hi(Number((wb >> 32n) & 0xffffffffn)) && (wb & 0xfffffffffffffn) !== 0n;
  if (na && nb) return { ok: true, nan: true };
  if (!Number.isFinite(a) || !Number.isFinite(b)) return { ok: a === b };
  const abs = Math.abs(a - b), rel = abs / Math.max(Math.abs(a), Math.abs(b));
  return abs > TOL_GATE * Math.max(Math.abs(a), Math.abs(b)) + fl ? { ok: false, rel, abs } : { ok: true, rel, abs };
};

let usedPrev = 0;
const stat = { trials: 0, trialsOk: 0, calls: 0, callsOk: 0, firstFail: [],
  tolWords: 0, tolExact: 0, tolApprox: 0, tolMaxRel: 0, tolMaxAbs: 0, tolBad: 0 };
const byCall = {};
const hex = (n) => '0x' + n.toString(16);

for (let t = 0; t < ntrials; t++) {
  const ncalls = u32(); u32();
  H8().fill(0, ARENA, ARENA + usedPrev);
  let usedNow = 0, failed = null;
  const pending = [];
  for (let c = 0; c < ncalls; c++) {
    const np = u32();
    for (let i = 0; i < np; i++) { const off = u32(), len = u32(); H8().set(buf.subarray(p, p + len), ARENA + off); p += len; }
    const va = u64(); const a = [u64(), u64(), u64(), u64()]; const x = [u64(), u64(), u64(), u64()];
    const rk = u32(); const rax = u64(); const xmm0 = u64();
    const plen = u32(); const post = buf.subarray(p, p + plen); p += plen;
    usedNow = Math.max(usedNow, plen);
    if (failed) continue;
    const key = va.toString(16);
    const sig = sigs[key];
    if (!sig) { failed = { call: c, va: key, why: 'no lifted function for this VA' }; continue; }
    const fn = M['_function_' + key];
    if (!fn) { failed = { call: c, va: key, why: 'wasm export missing' }; continue; }
    const argv = sig.params.map((ty, k) => ty === 'i64' ? BigInt.asUintN(64, a[k]) : ty === 'i32' ? Number(a[k] & 0xffffffffn) | 0 : ty === 'float' ? bitsToF32(x[k]) : ty === 'double' ? bitsToF64(x[k]) : (() => { throw new Error('param type ' + ty); })());
    let r;
    try { r = fn(...argv); } catch (e) { failed = { call: c, va: key, why: 'wasm trap: ' + e.message + (verbose ? '\n' + String(e.stack).split('\n').slice(1, 7).join('\n') : '') }; stat.calls++; continue; }
    stat.calls++; byCall[key] = byCall[key] || { n: 0, ok: 0 }; byCall[key].n++;
    // 戻り値
    let retOk = true, retInfo = '';
    if (rk === 1) { const got = typeof r === 'bigint' ? Number(r & 0xffffffffn) : (typeof r === 'number' && !Number.isInteger(r) ? f32bits(r) : (r >>> 0)); const want = Number(rax & 0xffffffffn); retOk = got === want; retInfo = `ret i32 want ${want} got ${got}`; }
    else if (rk === 2) { const got = typeof r === 'number' ? f32bits(r) : null; const want = Number(xmm0 & 0xffffffffn); retOk = got === want; retInfo = `ret f32 want ${hex(want)} got ${got === null ? typeof r : hex(got)}`; }
    else if (rk === 4) { const got = typeof r === 'number' ? (f64[0] = r, u64a[0]) : null; retOk = got === xmm0; retInfo = `ret f64 want ${xmm0.toString(16)} got ${got === null ? typeof r : got.toString(16)}`; }
    else if (rk === 3) { const got = BigInt.asUintN(64, BigInt(r)); retOk = got === rax; retInfo = `ret i64 want ${rax} got ${got}`; }
    // アリーナ全バイト → 4B word 単位の差分収集 (判定は trial 末尾: region 辞書は calls の後に記録される)
    const mem = H8().subarray(ARENA, ARENA + plen);
    const diffWords = [];
    for (let i = 0; i < plen; i += 4) {
      const j = Math.min(i + 4, plen);
      let same = true;
      for (let k = i; k < j; k++) if (mem[k] !== post[k]) { same = false; break; }
      if (!same) diffWords.push(i);
    }
    if (!diffWords.length && retOk) { stat.callsOk++; byCall[key].ok++; }
    else if (!diffWords.length) failed = { call: c, va: key, ndiff: 0, first: -1, retOk, retInfo, plen, post, mem: mem.slice() };
    else pending.push({ call: c, va: key, retOk, retInfo, plen, post, mem: mem.slice(), diffWords });
  }
  const nreg = u32(); const regs = [];
  for (let i = 0; i < nreg; i++) { const off = u32(), len = u32(), nl = u32(); regs.push({ off, len, name: buf.toString('latin1', p, p + nl) }); p += nl; }
  // tol 統計: tol region 内の全 word 数 (trial 末尾で確定)
  if (tol) {
    for (const r of regs) {
      const spec = tolMap.get(r.name);
      if (!spec) continue;
      const lo = Math.max(r.off, 0), hi = Math.min(r.off + r.len, usedNow);
      for (const s of spec.entries) {
        const a = Math.max(s.off, lo - r.off), b = Math.min(s.off + s.len, hi - r.off);
        if (b > a) stat.tolWords += Math.ceil((b - a) / (s.ty === 'f64' ? 8 : 4));
      }
    }
  }
  // tol 判定
  for (const ci of pending) {
    let approx = 0, bad = null, exactBad = null;
    const seen = new Set();
    for (const w of ci.diffWords) {
      if (tol) {
        const tinf = tolAt(regs, w);
        if (tinf) {
          if (tinf.ty === 'f64') {
            const w8 = w & ~7;
            if (seen.has(w8)) continue;
            seen.add(w8);
            const waB = Buffer.from(ci.post.buffer, ci.post.byteOffset + w8, 8).readBigUInt64LE(0);
            const wbB = Buffer.from(ci.mem.buffer, ci.mem.byteOffset + w8, 8).readBigUInt64LE(0);
            const g = gate(waB, wbB, 'f64', tinf.floor);
            if (g.exact) continue;
            if (g.ok) { approx++; stat.tolApprox++; if (g.rel > stat.tolMaxRel) stat.tolMaxRel = g.rel; if (g.abs > stat.tolMaxAbs) stat.tolMaxAbs = g.abs; continue; }
            stat.tolBad++; if (!bad) bad = { w: w8, wa: waB, wb: wbB, where: tinf.where };
            continue;
          }
          const wa = Buffer.from(ci.post.subarray(w, w + 4)).readUInt32LE(0);
          const wb = Buffer.from(ci.mem.subarray(w, w + 4)).readUInt32LE(0);
          const g = gate(wa, wb, 'f32', tinf.floor);
          if (g.exact) continue;
          if (g.ok) { approx++; stat.tolApprox++; if (g.rel > stat.tolMaxRel) stat.tolMaxRel = g.rel; if (g.abs > stat.tolMaxAbs) stat.tolMaxAbs = g.abs; continue; }
          stat.tolBad++; if (!bad) bad = { w, wa, wb, where: tinf.where };
          continue;
        }
      }
      if (exactBad === null) {
        const r = regs.find((g) => w >= g.off && w < g.off + g.len);
        exactBad = { w, where: r ? r.name + '+0x' + (w - r.off).toString(16) : hex(w) };
      }
    }
    if (ci.retOk && !bad && !exactBad) { stat.callsOk++; byCall[ci.va].ok++; }
    else if (!failed) failed = { call: ci.call, va: ci.va, ndiff: ci.diffWords.length, first: (bad || exactBad || { w: ci.diffWords[0] }).w, retOk: ci.retOk, retInfo: ci.retInfo, plen: ci.plen, post: ci.post, mem: ci.mem, tolBad: bad, exactBad };
    if (process.env.TOL_DEBUG) {
      let worst = null;
      for (const w of ci.diffWords) {
        const wa = Buffer.from(ci.post.subarray(w, w + 4)).readUInt32LE(0), wb = Buffer.from(ci.mem.subarray(w, w + 4)).readUInt32LE(0);
        const g = gate(wa, wb, 'f32');
        const abs = g && g.abs !== undefined ? g.abs : Math.abs(bitsToF32(wa) - bitsToF32(wb));
        if (!worst || abs > worst.abs) worst = { w, abs, wa, wb };
      }
      if (worst && (!stat._worst || worst.abs > stat._worst.abs)) {
        stat._worst = { ...worst, trial: t, call: ci.call };
        const r = regs.find((g) => worst.w >= g.off && worst.w < g.off + g.len);
        console.log(`WORST trial ${t} call ${ci.call} @${r ? r.name + '+0x' + (worst.w - r.off).toString(16) : hex(worst.w)} abs ${worst.abs.toExponential(3)} want ${hex(worst.wa)}(${bitsToF32(worst.wa)}) got ${hex(worst.wb)}(${bitsToF32(worst.wb)})`);
      }
    }
  }
  usedPrev = usedNow;
  stat.trials++;
  if (!failed) stat.trialsOk++;
  else {
    let where = '';
    if (failed.exactBad) where = `exact-region diff @${failed.exactBad.where}`;
    else if (failed.tolBad) where = `tol gate EXCEED @${failed.tolBad.where} want ${hex(failed.tolBad.wa)} got ${hex(failed.tolBad.wb)}`;
    else if (failed.first !== undefined && failed.first >= 0) {
      const r = regs.find((g) => failed.first >= g.off && failed.first < g.off + g.len);
      const w = failed.first & ~3;
      const want = Buffer.from(failed.post.subarray(w, w + 4)).readUInt32LE(0), got = Buffer.from(failed.mem.subarray(w, w + 4)).readUInt32LE(0);
      where = `first diff @arena+${hex(failed.first)} ${r ? r.name + '+' + hex(failed.first - r.off) : '(unmapped)'} want ${hex(want)} got ${hex(got)} ndiff=${failed.ndiff}`;
    }
    let words = '';
    if (verbose && failed.post) {
      const dd = [];
      for (let w = 0; w < failed.plen && dd.length < 14; w += 4) {
        const a = Buffer.from(failed.post.subarray(w, w + 4)).readUInt32LE(0), b = Buffer.from(failed.mem.subarray(w, w + 4)).readUInt32LE(0);
        if (a !== b) { const r = regs.find((g) => w >= g.off && w < g.off + g.len); dd.push(`${r ? r.name + '+' + hex(w - r.off) : hex(w)}:${hex(a)}/${hex(b)}`); }
      }
      words = '\n      diffs(want/got): ' + dd.join(' ');
    }
    const msg = `trial ${t} call ${failed.call} fn ${failed.va}: ${failed.why || ''} ${where} ${failed.retOk === false ? failed.retInfo : ''}${words}`;
    stat.firstFail.push(msg);
    if (verbose || stat.firstFail.length <= 5) console.log('FAIL', msg);
  }
}
const tolTotal = stat.tolApprox + stat.tolBad;
const tolTag = tol ? ` tol(1.6*2^-12 gate): approx ${stat.tolApprox} / diff-words, maxrel ${stat.tolMaxRel.toExponential(3)}, maxabs ${stat.tolMaxAbs.toExponential(3)}, exceed ${stat.tolBad}` : '';
console.log(`RESULT trials ${stat.trialsOk}/${stat.trials}${tol ? ' [tolerance]' : ' bit-exact'}; calls ${stat.callsOk}/${stat.calls}; by fn ` +
  Object.entries(byCall).map(([k, v]) => `${k}:${v.ok}/${v.n}`).join(' ') + tolTag);
if (jsonOut) fs.writeFileSync(jsonOut, JSON.stringify({ trials: stat.trials, trialsOk: stat.trialsOk, calls: stat.calls, callsOk: stat.callsOk, byCall, tol: { words: stat.tolWords, exact: stat.tolWords - tolTotal, approx: stat.tolApprox, maxRel: stat.tolMaxRel, maxAbs: stat.tolMaxAbs, bad: stat.tolBad }, fails: stat.firstFail.slice(0, 20) }, null, 1));
process.exit(stat.trialsOk === stat.trials ? 0 : 1);
