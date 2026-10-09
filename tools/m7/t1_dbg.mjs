// t1_dbg.mjs (PoC デバッグ): setParameter 合成 IR の store 経路観測
const VA_BASE = 0x30000000;
async function main() {
  const mk = (await import('./work/ott_argpass.cjs')).default || (await import('./work/ott_argpass.cjs'));
  const mod = await mk();
  const U8 = mod.HEAPU8;
  if (mod._m6_data_install) mod._m6_data_install();
  const OBJ = VA_BASE + 0x310000;
  const objNum = 0x30310000;
  const fctor = mod._function_18011d400;
  const fsetparam = mod._function_180120af0;
  const u32 = (a) => U8[a] | (U8[a+1]<<8) | (U8[a+2]<<16) | (U8[a+3]<<24);
  const f32 = (a) => new Float32Array(new Uint8Array([U8[a],U8[a+1],U8[a+2],U8[a+3]]).buffer)[0];
  const r = fctor(BigInt(OBJ), 0n);
  console.log('ctor rc', r);
  console.log('obj+0x138 (312) =', '0x' + u32(objNum+312).toString(16));
  console.log('obj+0x28  (40)  =', u32(objNum+40));
  const f32bits = (v) => { const f = new Float32Array(1); f[0] = v; return BigInt(new Uint32Array(f.buffer)[0]); };
  // r9 の予測 (obj+0x138 値 + sext(i32 obj+0x28)*108)
  console.log('--- fsetparam(obj, 0, 0.5) 前: obj+0x2dc =', f32(objNum+0x2dc));
  fsetparam(BigInt(OBJ), 0n, f32bits(0.5));
  console.log('--- fsetparam(obj, 0, 0.5) 後: obj+0x2dc =', f32(objNum+0x2dc), '(0x2dc=732)');
  console.log('obj+0x138 =', '0x' + u32(objNum+312).toString(16), 'obj+0x28 =', u32(objNum+40));
  const pbase = u32(objNum+312);
  const chunk = pbase + u32(objNum+40) * 108;
  console.log('pbase =', '0x'+pbase.toString(16), 'r9予測 chunk =', '0x'+(chunk>>>0 >>> 0).toString(16));
  console.log('mem[chunk+4] (idx0 store 先 r9+0) =', f32(chunk));
  console.log('mem[0x30310000+0x300000?] 異常ポインタ確認 (obj 変化なし)');
  // resume 実行で slots の再計算確認
  const fresume = mod._function_180120800;
  const fproc = mod._function_18011ec20;
  const IN_A = VA_BASE + 0x320000, OU_A = VA_BASE + 0x330000, BUF = VA_BASE + 0x340000;
  const F32 = mod.HEAPF32;
  const N = 256;
  for (let i = 0; i < N; i++) {
    F32[(BUF / 4) + i] = Math.fround(Math.sin(i * 0.05) * 0.7);
    F32[(BUF / 4) + N + i] = Math.fround(0.0);
  }
  F32[(BUF / 4) + 2*N] = 0; F32[(BUF / 4) + 3*N] = 0;
  mod.HEAP32[(IN_A / 4)] = BUF; mod.HEAP32[(IN_A / 4) + 1] = BUF + N * 4;
  mod.HEAP32[(OU_A / 4)] = BUF + N * 8; mod.HEAP32[(OU_A / 4) + 1] = BUF + N * 12;
  const rr = fresume(BigInt(OBJ));
  console.log('resume rc', rr);
  // process 前後の param chunk 体感 (idx0 chunk がどこから読まれるか)
  console.log('--- fproc 前後');
  console.log('process 前: obj+0x2dc =', f32(objNum+0x2dc), 'chunk =', f32(chunk));
  const rp = fproc(BigInt(OBJ), BigInt(IN_A), BigInt(OU_A), BigInt(N));
  console.log('process rc', rp);
  console.log('out[0..4] =', [0,1,2,3,4].map(i => F32[(BUF/4)+2*N+i]));
}
main().catch((e) => { console.error('[t1_dbg][FAIL]', e); process.exit(1); });
