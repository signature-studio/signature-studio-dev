const VA_BASE = 0x30000000;
(async () => {
  const m = await import('./work/ott_m8.cjs'); const mod = await (m.default ? m.default() : m());
  const U8 = mod.HEAPU8, F32 = mod.HEAPF32;
  if (mod._m6_data_install) mod._m6_data_install();
  const obj = BigInt(mod._function_18011d400(BigInt(VA_BASE + 0x310000), 0n));
  const f32bits = (v) => { const f = new Float32Array(1); f[0] = v; return BigInt(new Uint32Array(f.buffer)[0]); };
  const on = Number(obj);
  const r32 = (o) => (U8[on+o] | (U8[on+o+1]<<8) | (U8[on+o+2]<<16) | (U8[on+o+3]<<24)) >>> 0;
  console.log('pre : obj+544 =', r32(544).toString(16));
  mod._function_180120af0(obj, 5n, f32bits(0.5));
  console.log('post: obj+544 =', r32(544).toString(16), ' (0x3f000000 期待 = idx5*T1 store [rcx+5*4+0x20c])');
  console.log('post: obj+548 =', r32(548).toString(16));
  const pbase = r32(312), imod = r32(40);
  const chunk = (pbase + imod * 108) >>> 0;
  const c20 = (U8[chunk+20] | (U8[chunk+21]<<8) | (U8[chunk+22]<<16) | (U8[chunk+23]<<24)) >>> 0;
  console.log('chunk addr = 0x' + chunk.toString(16), ' chunk[idx5*4] bits = 0x' + c20.toString(16), ' (0x3f000000 期待)');
})().catch(e => { console.error(e); process.exit(1); });
