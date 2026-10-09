// ring buffer 版: 全事象記録後に
    
// り、達成期 NaN 出生
const VA_BASE = 0x30000000;
const OPS = (op) => {
  const m = {0x01:'movss(load i32)', 0x02:'movss__17(extr)', 0x30:'movss30(xmm,xmm)'};
  const opn = {
    0x3b: '+' , 0x3a: '-', 0x52: '*', 0x5f: '/'   // 0x10+0x2b etc
  };
  const low = op & 0x0f;
  const lane = (op >> 4) & 0xf;
  let t = lane === 1 ? m[(op & 0xff) === 0x01 ? 0x01 : ((op & 0xff) === 0x02 ? 0x02 : 0)] : '';
  if ((op & 0xf0) === 0x10) t = 'lane32 ' + (opn[op & 0xff] || '?');
  if ((op & 0xf0) === 0x20) t = 'lane32c ' + (opn[op & 0xff] || '?');
  return `${''}${''}${''}${'0x' + (op>>>0).toString(16)} ${t}`;
};
async function main() {
  const mk = (await import(process.env.M8MOD || './work/ott_m8.cjs')).default || (await import(process.env.M8MOD || './work/ott_m8.cjs'));
  const mod = await mk();
  const U8 = mod.HEAPU8, F32 = mod.HEAPF32, HEAP32 = mod.HEAP32;
  if (mod._m6_data_install) mod._m6_data_install();
  const OBJ = VA_BASE + 0x310000, IN_A = VA_BASE + 0x320000, OU_A = VA_BASE + 0x330000, BUF = VA_BASE + 0x340000;
  const r = mod._function_18011d400(BigInt(OBJ), 0n);
  const objPtr = BigInt(r);
  if (process.env.FULLSWEEP === '1') for (const i of [...Array(19).keys()]) mod._function_180120af0(objPtr, BigInt(i), 1065353216n);
  mod._function_180120af0(objPtr, 19n, 0n);
  if (process.env.NORESUME !== '1') mod._function_180120800(objPtr);
  const N = 256;
  for (let i = 0; i < N; i++) F32[(BUF/4)+i] = Math.fround(Math.sin(i*0.05)*0.7);
  F32[(BUF/4)+2*N] = 0; F32[(BUF/4)+3*N] = 0;
  HEAP32[(IN_A/4)] = BUF; HEAP32[(IN_A/4)+1] = BUF + N*4;
  HEAP32[(OU_A/4)] = BUF + N*8; HEAP32[(OU_A/4)+1] = BUF + N*12;
  const rp = mod._function_18011ec20(objPtr, BigInt(IN_A), BigInt(OU_A), BigInt(N));
  const n = mod._m8dbg_n();
  console.log('[nanring] total events:', n, 'process rc:', rp);
  const hexl = (u) => '0x' + (u>>>0).toString(16).padStart(8, '0');
  const f32v = (bits) => { const f = new Float32Array(1); new Uint32Array(f.buffer)[0] = bits >>> 0; return f[0]; };
  const isnan = (b) => ((b >>> 0) & 0x7f800000) === 0x7f800000 && (b & 0x007fffff);
  // 最初の NaN 事象の絶対番号
  let firstNaN = -1;
  for (let e = Math.max(0, n - 512); e < n; e++) {
    const words = [0,1,2,3].map(k => mod._m8dbg(e*4 + k));
    if (words.some(isnan)) { firstNaN = e; break; }
  }
  console.log('[nanring] first NaN event:', firstNaN);
  if (firstNaN >= 0) {
    const start = Math.max(Math.max(0, n-512), firstNaN - 40);
    for (let e = start; e < Math.min(n, firstNaN + 12); e++) {
      const [op, a, b, rr] = [0,1,2,3].map(k => mod._m8dbg(e*4 + k));
      const mark = (isnan(op)||isnan(rr)) ? ' <<< NaN' : ((a===0x7f800000||b===0x7f800000) ? ' (inf operand)' : '');
      console.log(`  [${e}] ${OPS(op)} a=${hexl(a)}(${f32v(a)}) b=${hexl(b)}(${f32v(b)}) r=${hexl(rr)}${mark}`);
    }
  }
}
main().catch(e => { console.error(e); process.exit(1); });
