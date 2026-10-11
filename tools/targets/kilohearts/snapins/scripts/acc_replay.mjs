/* acc_replay.mjs — harness/compare.mjs とは別実装の wasm リプレイヤ (規則 37 の独立再計算)。
 *   node acc_replay.mjs <vectors.bin> <module.cjs> <sigs.json>
 *
 * KHV2 書式 (native_ref.c の書き込み側から読み起こした仕様):
 *   "KHV2" u32 ntrials u32 pad
 *   per trial: u32 ncalls u32 pad
 *     per call: u32 npatch { u32 off, u32 len, bytes }  u64 va
 *               u64 a[4] (rcx,rdx,r8,r9)  u64 x[4] (xmm0..3 下位64bit)
 *               u32 retkind, u64 rax, u64 xmm0  u32 plen, bytes post[plen]
 *     u32 nreg { u32 off, u32 len, u32 namelen, name }      ← trial 末尾
 *
 * compare.mjs との差異 (= 別実装のポイント):
 *   1. 差分検出は **バイト単位** (compare.mjs は 4B word 単位で集計し index を丸める)。
 *      word 丸めで見落とす "同 word 内の別バイト差分" も捕捉する。
 *   2. 戻り値判定を独立に実装 (rk=3 は BigInt 変換未対応を避け undefined ガード、
 *      rk=4 は Float64Array 経由で 64bit 比較)。compare.mjs の rk=3 は `BigInt(r)` で
 *      float が来ると例外になる経路があるため、ここでは安全側に倒す。
 *   3. **tol gate を持たない** = 常に bit-exact 判定 (compare.mjs は --tol で近似許容)。
 *      tol 対象 3 本 (resonator/stereo/delay) は §13 主張どおり exact 一致するはずで、
 *      これは tol を外した stricter な検証になる (規則 41 の対照にもなる)。
 *   4. region 名は trial 末尾テーブルから読み、不一致 byte の位置を region+offset で報告
 *      (compare.mjs は word index のみ)。
 *
 * メモリモデルは KHV2 の仕様 (compare.mjs と共通):
 *   trial 開始時 [ARENA, ARENA+usedPrev) を 0 fill (usedPrev = 前 trial の max plen)。
 *   patch 適用 → call → post[plen] と [ARENA, ARENA+plen) を比較。
 */
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const [vecPath, modPath, sigPath] = process.argv.slice(2);
const ARENA = 0x04000000;
const verbose = process.argv.includes('--v');

const buf = fs.readFileSync(vecPath);
if (buf.toString('latin1', 0, 4) !== 'KHV2') throw new Error('bad magic');
let p = 4;
const u32 = () => { const v = buf.readUInt32LE(p); p += 4; return v; };
const u64 = () => { const v = buf.readBigUInt64LE(p); p += 8; return v; };
const ntrials = u32(); u32();

const sigs = JSON.parse(fs.readFileSync(sigPath, 'utf8'));
const Mod = require(path.resolve(modPath));
const M = await Mod();
const H8 = () => M.HEAPU8;

const f32 = new Float32Array(1);
const f32u = new Uint32Array(f32.buffer);
const f64 = new Float64Array(1);
const f64u = new BigUint64Array(f64.buffer);

let usedPrev = 0, calls = 0, callsOk = 0, trialsOk = 0, bytesCmp = 0, firstDiff = null;
const byVa = {};
for (let t = 0; t < ntrials; t++) {
  const ncalls = u32(); u32();
  H8().fill(0, ARENA, ARENA + usedPrev);          // KHV2 仕様: 前 trial の使用域のみ 0 化
  let trialFailed = null, usedNow = 0;
  for (let c = 0; c < ncalls; c++) {
    const np = u32();
    for (let i = 0; i < np; i++) {
      const off = u32(), len = u32();
      if (ARENA + off + len > H8().length) { trialFailed = { c, why: 'patch outside heap' }; break; }
      H8().set(buf.subarray(p, p + len), ARENA + off);
      p += len;
    }
    const va = u64();
    const a = [u64(), u64(), u64(), u64()], x = [u64(), u64(), u64(), u64()];
    const rk = u32(), rax = u64(), xmm0 = u64();
    const plen = u32(); const post = buf.subarray(p, p + plen); p += plen;
    usedNow = Math.max(usedNow, plen);
    const key = va.toString(16);
    const sig = sigs[key];
    if (!sig) { if (!firstDiff) firstDiff = { t, c, va: key, why: 'no sig' }; if (!trialFailed) trialFailed = { c, why: 'no sig' }; continue; }
    const fn = M['_function_' + key];
    if (!fn) { if (!firstDiff) firstDiff = { t, c, va: key, why: 'wasm export missing' }; if (!trialFailed) trialFailed = { c, why: 'no export' }; continue; }
    const argv = sig.params.map((ty, k) => ty === 'i64' ? BigInt.asUintN(64, a[k])
      : ty === 'i32' ? Number(a[k] & 0xffffffffn) | 0
        : ty === 'float' ? (f32u[0] = Number(x[k] & 0xffffffffn), f32[0])
          : ty === 'double' ? (f64u[0] = BigInt(x[k]), f64[0])
            : null);
    let r, trap = null;
    try { r = fn(...argv); } catch (e) { trap = e.message; }
    calls++;
    const st = byVa[key] || (byVa[key] = { n: 0, ok: 0 });
    st.n++;
    if (trap) {
      if (!firstDiff) firstDiff = { t, c, va: key, why: 'trap: ' + trap };
      if (!trialFailed) trialFailed = { c, why: 'trap: ' + trap };
      continue;
    }
    // --- 戻り値 (独立実装) ---
    let retOk = true, retInfo = '';
    if (rk === 1) {
      const got = typeof r === 'bigint' ? Number(r & 0xffffffffn) : (typeof r === 'number' && !Number.isInteger(r) ? (f32[0] = r, f32u[0]) : (typeof r === 'number' ? (r >>> 0) : null));
      retOk = got !== null && got === Number(rax & 0xffffffffn);
      retInfo = 'ret i32 want %d got %s';
    } else if (rk === 2) {
      const got = typeof r === 'number' ? (f32[0] = r, f32u[0]) : null;
      retOk = got !== null && got === Number(xmm0 & 0xffffffffn);
      retInfo = 'ret f32';
    } else if (rk === 3) {
      retOk = (typeof r === 'bigint') ? BigInt.asUintN(64, r) === rax
        : (typeof r === 'number' && Number.isInteger(r) ? BigInt.asUintN(64, BigInt(r)) === rax : false);
      retInfo = 'ret i64';
    } else if (rk === 4) {
      retOk = typeof r === 'number' ? (f64[0] = r, f64u[0] === BigInt.asUintN(64, xmm0)) : false;
      retInfo = 'ret f64';
    }
    // --- arena 全バイト (バイト単位で比較 = word 丸めなし) ---
    const mem = H8().subarray(ARENA, ARENA + plen);
    let bad = -1;
    for (let i = 0; i < plen; i++) if (mem[i] !== post[i]) { bad = i; break; }
    bytesCmp += plen;
    if (!retOk || bad >= 0) {
      if (!firstDiff) firstDiff = { t, c, va: key, why: !retOk ? retInfo : 'byte diff @' + bad,
        want: !retOk ? '0x' + (xmm0 & 0xffffffffn).toString(16) : post[bad], got: !retOk ? String(r) : mem[bad] };
      if (!trialFailed) trialFailed = { c, why: !retOk ? retInfo : 'byte diff @' + bad };
    } else { st.ok++; callsOk++; }
  }
  const nreg = u32(); const regs = [];
  for (let i = 0; i < nreg; i++) {
    const off = u32(), len = u32(), nl = u32();
    regs.push({ off, len, name: buf.toString('latin1', p, p + nl) });
    p += nl;
  }
  if (trialFailed) {
    let where = '';
    const f = firstDiff;
    if (f && f.t === t && typeof f.want === 'number') {
      const r = regs.find(g => f.want >= g.off && f.want < g.off + g.len);
      where = r ? r.name + '+0x' + (f.want - r.off).toString(16) : '0x' + f.want.toString(16);
    }
    trialFailed.where = where;
    if (verbose) console.error('FAIL trial ' + t + ' call ' + trialFailed.c + ' ' + trialFailed.why + ' ' + where);
  } else trialsOk++;
  usedPrev = usedNow;
}
console.log(JSON.stringify({ trials: ntrials, trialsOk, calls, callsOk, arenaBytes: bytesCmp, byVa: Object.keys(byVa).length, firstDiff }));
