import path from 'node:path'; import fs from 'node:fs'; import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const M = await require(path.resolve(process.argv[2]))();
const lines = fs.readFileSync(process.argv[3], 'utf8').split('\n').filter(Boolean);
const flagPtr = Number(M._fa_va2ptr(0x1813070f8n));
const buf = new DataView(new ArrayBuffer(4));
const out = [];
for (const l of lines) {
  const [x, y, f] = l.split(' ').map((v) => parseInt(v, 16));
  new DataView(M.HEAPU8.buffer).setUint32(flagPtr, f, true);
  buf.setUint32(0, x >>> 0, true); const fx = buf.getFloat32(0, true);
  buf.setUint32(0, y >>> 0, true); const fy = buf.getFloat32(0, true);
  const sp = M.stackSave(); try { const r = M._fa_root_18103fd60(fx, fy); buf.setFloat32(0, r, true); out.push('R ' + buf.getUint32(0, true).toString(16).padStart(8, '0')); }
  catch (e) { out.push("ERR"); M.stackRestore(sp); }
}
console.log(out.join('\n'));
if (process.env.FA_COV_OUT && M._fa_cov_ptr) {
  const p0 = Number(M._fa_cov_ptr()); const rep = JSON.parse(fs.readFileSync(process.env.FA_COV_REP, 'utf8'));
  const hit = {}; for (const [va, idx] of Object.entries(rep.cov_map)) hit[va] = M.HEAPU8[p0 + idx];
  fs.writeFileSync(process.env.FA_COV_OUT, JSON.stringify(hit));
}
