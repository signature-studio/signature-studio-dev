// compare.mjs — ctx-fuzz 差分: native_ref の vectors.bin を wasm(lift) で再生して全バイト突合する。
//   node compare.mjs <vectors.bin> <module.cjs> <sigs.json> [--v] [--json out.json]
// sigs.json: { "<va hex>": {"params":["i64","i64","float"], "ret":"i64"} }  (kh_sigs.py が最終 .ll から生成)
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);

const args = process.argv.slice(2);
const verbose = args.includes('--v');
const zeroStack = args.includes('--zero-stack');   /* em-family: functor offset 字段の未初期化スタック読みを 0 確定 (native 側は scen_em.h の clone パッチで対にする) */
const jIdx = args.indexOf('--json');
const jsonOut = jIdx >= 0 ? args[jIdx + 1] : null;
const pos = args.filter((a, i) => !a.startsWith('--') && args[i - 1] !== '--json');
const [vecPath, modPath, sigPath] = pos;
const ARENA = 0x04000000;

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
const f32 = new Float32Array(1), u32a = new Uint32Array(f32.buffer);
const f64 = new Float64Array(1), u64a = new BigUint64Array(f64.buffer);
const bitsToF32 = (b) => { u32a[0] = Number(BigInt(b) & 0xffffffffn); return f32[0]; };
const bitsToF64 = (b) => { u64a[0] = BigInt(b); return f64[0]; };
const f32bits = (x) => { f32[0] = x; return u32a[0]; };
const H8 = () => M.HEAPU8;
const KH_SIZE = 65536n;   /* stubs.c の kh_stack[65536] と同値 */
const KH_BASE = zeroStack && M._kh_stack_ptr ? BigInt(M._kh_stack_ptr()) : 0n;

let usedPrev = 0;
const stat = { trials: 0, trialsOk: 0, calls: 0, callsOk: 0, firstFail: [], nanRet: 0 };
const byCall = {};
const hex = (n) => '0x' + n.toString(16);

/* --path-flags: 経路フラグを trial ごとに書く (native の scen_kclp.h と同じ規則: 偶数 trial = ymm 0x20 / 奇数 = scalar 0x2)。
 * 値は wasm 側 setter (kh_set_flag_a/b) で .data へ書く。KH-98 専用 */
const pfIdx = args.indexOf('--path-flags');
const pathFlags = pfIdx >= 0;
const negCtrl = args.includes('--neg-ctrl');   /* ネガコン: 合否を反転し、全 trial が FAIL になることを確かめる (KH-98) */

for (let t = 0; t < ntrials; t++) {
  const ncalls = u32(); u32();
  if (pathFlags && M._kh_set_flag_a) M._kh_set_flag_a((t & 1) ? 0x2 : 0x20);
  H8().fill(0, ARENA, ARENA + 0x10000);   /* trial 冒頭の zero 化は固定窓 (native_ref.c の ARENA_CLEAR と同一: mgr slot 0x0400F020 を含む) */
  if (KH_BASE) H8().fill(0, Number(KH_BASE + KH_SIZE - 0x48n - 0x300n), Number(KH_BASE + KH_SIZE - 0x48n + 0x40n));   /* callee フレーム窓を 0 確定 (native の clone offset パッチと対) */
  let usedNow = 0, failed = null;
  const callsInfo = [];
  for (let c = 0; c < ncalls; c++) {
    const np = u32();
    for (let i = 0; i < np; i++) { const off = u32(), len = u32(); H8().set(buf.subarray(p, p + len), ARENA + off); p += len; }
    const va = u64(); const a = [u64(), u64(), u64(), u64(), u64(), u64(), u64(), u64()]; const x = [u64(), u64(), u64(), u64()];
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
    // アリーナ全バイト
    const mem = H8().subarray(ARENA, ARENA + plen);
    let first = -1, ndiff = 0, ignored = 0;
    for (let i = 0; i < plen; i++) {
      if (mem[i] === post[i]) continue;
      if (first < 0) first = i;
      ndiff++;
    }
    if (negCtrl) { if (first < 0 && retOk) first = 0; else { first = -1; retOk = true; } }   /* ネガコン: 判定を反転 (一致を不一致、不一致を一致として数える) */
    if (first < 0 && retOk) { stat.callsOk++; byCall[key].ok++; }
    else failed = { call: c, va: key, ndiff, first, retOk, retInfo, plen, post, mem: mem.slice() };
  }
  const nreg = u32(); const regs = [];
  for (let i = 0; i < nreg; i++) { const off = u32(), len = u32(), nl = u32(); regs.push({ off, len, name: buf.toString('latin1', p, p + nl) }); p += nl; }
  usedPrev = usedNow;
  stat.trials++;
  if (!failed) stat.trialsOk++;
  else {
    let where = '';
    if (failed.first !== undefined && failed.first >= 0) {
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
console.log(`RESULT trials ${stat.trialsOk}/${stat.trials} bit-exact; calls ${stat.callsOk}/${stat.calls}; by fn ` +
  Object.entries(byCall).map(([k, v]) => `${k}:${v.ok}/${v.n}`).join(' '));
if (jsonOut) fs.writeFileSync(jsonOut, JSON.stringify({ trials: stat.trials, trialsOk: stat.trialsOk, calls: stat.calls, callsOk: stat.callsOk, byCall, fails: stat.firstFail.slice(0, 20) }, null, 1));
process.exit(stat.trialsOk === stat.trials ? 0 : 1);
