// gain_harness.mjs <gain.cjs> <scen.txt> — lift IR → wasm を同一シナリオで実行し native_gain と同形式でダンプ
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const Module = await require(path.resolve(process.argv[2]))();
const lines = fs.readFileSync(process.argv[3], 'utf8').split('\n').filter(Boolean);
const hex = (u8) => Buffer.from(u8).toString('hex');
let idx = 0;
for (const line of lines) {
  const v = line.split(' ').map((x) => parseInt(x, 16));
  const n = v[3];
  const m = (sz) => { const p = Module._malloc(sz); Module.HEAPU8.fill(0, p, p + sz); return p; };
  const a1 = m(0x100), P = m(0xa000), Q = m(0x80), buf = m(32), ctx = m(0x30), L = m(n * 4 + 4), R = m(n * 4 + 4);
  const dv = () => new DataView(Module.HEAPU8.buffer);
  const w32 = (b, o, x) => dv().setUint32(b + o, x >>> 0, true);
  const w64 = (b, o, x) => { dv().setUint32(b + o, x >>> 0, true); dv().setUint32(b + o + 4, 0, true); };
  for (let i = 0; i < n; i++) { w32(L, i * 4, v[16 + i]); w32(R, i * 4, v[16 + n + i]); }
  w64(a1, 0x90, P);
  w32(P, 0x9dc4, v[0]); w32(P, 0x9e0c, v[1]); w32(P, 0x9e18, v[2]);
  Module.HEAPU8[P + 0x9e93] = v[12]; Module.HEAPU8[P + 0x9edb] = v[13]; w32(P, 0x9e50, v[14]); w32(P, 0x9e98, v[15]);
  w64(P, 0x9f30, Q);
  w64(Q, 0x28, buf); w64(Q, 0x30, buf); w64(Q, 0x38, buf + 8);
  Module.HEAPU8[a1 + 0xb0] = v[4]; w32(a1, 0xa8, v[5]); w32(a1, 0xac, v[6]); w32(a1, 0xa4, v[7]);
  w32(a1, 0xbc, v[8]); w32(a1, 0xc0, v[9]); w32(a1, 0xcc, v[10]); w32(a1, 0xd0, v[11]);
  w64(ctx, 0, L); w64(ctx, 8, R); w32(ctx, 0x28, n);
  Module._function_180afe090(BigInt(a1), BigInt(ctx));
  const H = Module.HEAPU8, end = dv().getUint32(Q + 0x30, true);
  process.stdout.write(`S${idx++} ${hex(H.subarray(a1 + 0x9c, a1 + 0x9c + 0x38))} ${hex(H.subarray(P + 0x9e50, P + 0x9e58))}${hex(H.subarray(P + 0x9e93, P + 0x9e94))}${hex(H.subarray(P + 0x9e98, P + 0x9ea0))}${hex(H.subarray(P + 0x9edb, P + 0x9edc))} ${end - buf} ${hex(H.subarray(buf, buf + 8))} ${hex(H.subarray(L, L + n * 4))} ${hex(H.subarray(R, R + n * 4))}\n`);
  for (const p of [a1, P, Q, buf, ctx, L, R]) Module._free(p);
}
