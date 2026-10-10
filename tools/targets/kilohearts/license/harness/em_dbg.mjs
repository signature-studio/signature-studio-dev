// em_dbg.mjs — trial0 call0 の単発リプレイ + アリーナ差分ダンプ (デバッグ用)
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const [vecPath, modPath, sigPath] = process.argv.slice(2);
const ARENA = 0x04000000;

const buf = fs.readFileSync(vecPath);
const dv = new DataView(buf.buffer, buf.byteOffset, buf.byteLength);
let p = 0;
const u32 = () => { const v = dv.getUint32(p, true); p += 4; return v; };
const u64 = () => { const v = dv.getBigUint64(p, true); p += 8; return v; };
p = 4;
const ntrials = u32(); u32();
const sigs = JSON.parse(fs.readFileSync(sigPath, 'utf8'));
const Mod = require(path.resolve(modPath));
const M = await Mod();
const H = M.HEAPU8;

let usedPrev = 0;
for (let t = 0; t < ntrials; t++) {
  const ncalls = u32(); u32();
  H.fill(0, ARENA, ARENA + usedPrev);
  let usedNow = 0;
  for (let c = 0; c < ncalls; c++) {
    const np = u32();
    for (let i = 0; i < np; i++) { const off = u32(), len = u32(); H.set(buf.subarray(p, p + len), ARENA + off); p += len; }
    const va = u64(); const a = [u64(), u64(), u64(), u64(), u64(), u64(), u64(), u64()]; const x = [u64(), u64(), u64(), u64()];
    const rk = u32(); const rax = u64(); const xmm0 = u64();
    const plen = u32(); const post = buf.subarray(p, p + plen); p += plen;
    usedNow = Math.max(usedNow, plen);
    const sig = sigs[va.toString(16)];
    const fn = M['_function_' + va.toString(16)];
    const argv = sig.params.map((ty, k) => ty === 'i64' ? BigInt.asUintN(64, a[k]) : ty === 'i32' ? Number(a[k] & 0xffffffffn) | 0 : (() => { throw new Error(ty); })());
    let r;
    try { r = fn(...argv); } catch (e) { console.log('trial', t, 'call', c, 'TRAP', e.message); process.exit(1); }
    // 差分
    let first = -1; const ranges = [];
    for (let i = 0; i < plen; i++) {
      if (H[ARENA + i] !== post[i]) { let j = i, last = i; while (j < plen && j - last <= 8) { if (H[ARENA + j] !== post[j]) last = j; j++; } ranges.push([i, last]); i = last; }
    }
    if (ranges.length || rk) {
      console.log('trial %d call %d va=%s' , t, c, va.toString(16));
      console.log('  cursor: native=%s wasm=%s', dv.getBigUint64(p - plen - 8*14 - 4, true), dv.getBigUint64(0, true));
      for (const [s, e] of ranges.slice(0, 60)) {
        if (s < 0x4000) continue;
        console.log('  diff %x..%x (%dB) native=%s wasm=%s', s, e, e - s + 1,
          [...post.slice(s, Math.min(s + 16, e + 1))].map(x => x.toString(16).padStart(2, '0')).join(''),
          [...H.slice(ARENA + s, ARENA + Math.min(s + 16, e + 1))].map(x => x.toString(16).padStart(2, '0')).join(''));
      }
    }
  }
  const nreg = u32();
  for (let i = 0; i < nreg; i++) { u32(); u32(); const nl = u32(); p += nl; }
  usedPrev = usedNow;
}
