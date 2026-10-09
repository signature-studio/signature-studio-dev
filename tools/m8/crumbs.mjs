const VA_BASE = 0x30000000;
async function main() {
  const mk = (await import('./work/ott_m8.cjs')).default || (await import('./work/ott_m8.cjs'));
  const mod = await mk();
  const U8 = mod.HEAPU8, F32 = mod.HEAPF32, HEAP32 = mod.HEAP32;
  if (mod._m6_data_install) mod._m6_data_install();
  const A = 805423104; // 0x30000000 + 0x3B0000 (breadcrumb area)
  const OBJ = VA_BASE + 0x310000, IN_A = VA_BASE + 0x320000, OU_A = VA_BASE + 0x330000, BUF = VA_BASE + 0x340000;
  const obj = BigInt(mod._function_18011d400(BigInt(OBJ), 0n));
  const f32bits = (v) => { const f = new Float32Array(1); f[0] = v; return BigInt(new Uint32Array(f.buffer)[0]); };
  for (const i of [...Array(19).keys()]) mod._function_180120af0(obj, BigInt(i), f32bits(0.5));
  mod._function_180120af0(obj, 19n, 0n);
  mod._function_180120800(obj);
  const N = 256;
  for (let i = 0; i < N; i++) { F32[(BUF/4)+i] = Math.fround(Math.sin(i*0.05)*0.7); F32[(BUF/4)+N+i]=0; }
  F32[(BUF/4)+2*N]=0; F32[(BUF/4)+3*N]=0;
  HEAP32[(IN_A/4)]=BUF; HEAP32[(IN_A/4)+1]=BUF+N*4;
  HEAP32[(OU_A/4)]=BUF+N*8; HEAP32[(OU_A/4)+1]=BUF+N*12;
  HEAP32[A/4] = 0;
  mod._function_18011ec20(obj, BigInt(IN_A), BigInt(OU_A), BigInt(N));
  const names = {1:'entry',2:'18011ec49',3:'18011ec77',4:'18011f950',5:'18011efb0',6:'18011fd8c',7:'1801207f1(dirty)'};
  const out = {};
  for (const k of Object.keys(names)) { out[names[k]] = HEAP32[(805424128 + 4*k)/4]; }
  console.log('breadcrumbs (hit counts):', JSON.stringify(out));
}
main().catch(e => { console.error(e); process.exit(1); });
