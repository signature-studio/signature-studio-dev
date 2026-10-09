// t1_argpass.mjs (M7 PoC): m6 t1 と同一経路 (ctor → setParameter(0..18,0.5) →
//   resume → processReplacing) を ir7_argpass 3-arg signature で駆動し、
//   t1_out_argpass.hex を tools/m7/work 高 所定の固定パスに出す。
// setParameter は ir7 合成 define (obj, index, xmm2bits) — JS 側は f32 bits
// を渡す。値は m6 t1 harness と同一の 0.5 (0x3F000000) を全 param に入れる。
import fs from 'fs';

const VA_BASE = 0x30000000;
const HERE = new URL('.', import.meta.url).pathname;

async function main() {
  const mk = (await import(process.env.M8MOD || './work/ott_m8.cjs')).default || (await import(process.env.M8MOD || './work/ott_m8.cjs'));
  const mod = await mk();
  const U8 = mod.HEAPU8;
  const F32 = mod.HEAPF32;
  console.log('[t1_argpass] linear memory len:', U8.length);
  if (mod._m6_data_install) mod._m6_data_install();

  const fsetparam = mod._function_180120af0;
  const fctor = mod._function_18011d400;
  const fresume = mod._function_180120800;
  const fproc = mod._function_18011ec20;
  if (!fsetparam || !fctor || !fresume || !fproc) { console.log('[t1_argpass][FAIL] export 不足'); process.exit(1); }

  // rip 定数 (CLAMP) の敷設確認 (m6_data install = rdata 0x301e2000..)
  const cA = F32[(0x301ee808) / 4], cC = F32[(0x301ee818) / 4], cB = F32[(0x301fde90) / 4];
  console.log('[t1_argpass] const A/B/C (CLAMP):', cA, cB, cC, '(A=0.5,C=1.0 期待)');

  const OBJ = VA_BASE + 0x310000, IN_A = VA_BASE + 0x320000, OU_A = VA_BASE + 0x330000,
        BUF = VA_BASE + 0x340000;
  const r = fctor(BigInt(OBJ), 0n);
  const objPtr = BigInt(r);
  console.log('[t1_argpass] ctor rc (obj ptr): 0x' + objPtr.toString(16));
  if (objPtr <= 0n) { console.log('[t1_argpass][FAIL] ctor rc 異常'); process.exit(1); }
  const f32bits = (v) => { const f = new Float32Array(1); f[0] = v; return BigInt(new Uint32Array(f.buffer)[0]); };
  const bits05 = f32bits(0.5);
  const setIdx = (process.env.T1SET === 'none' ? []
                  : process.env.T1SET ? process.env.T1SET.split(',').map(Number)
                  : [...Array(19).keys()]);
  const zeroIdx = (process.env.T1Z ? process.env.T1Z.split(',').map(Number) : []);
  for (const i of setIdx) {
    if (i === -1) continue;
    const val = process.env.T1VAL ? Number(process.env.T1VAL) : 0.5;
    const v = zeroIdx.includes(i) ? 0.0 : val;
    fsetparam(objPtr, BigInt(i), v === 0 ? BigInt(0) : f32bits(v));
  }
  console.log('[t1_sel] zeroIdx:', zeroIdx, 'setIdx:', setIdx);
  const objNumPre = Number(objPtr);
  if (process.env.T1SVF === '1') { U8[objNumPre + 584] = 0; console.log('[t1_sel] forced obj+584=0 (SVF loop 路線)'); }
  if (process.env.T1SWEEP === '1') U8[objNumPre + 806] = 0;
  // setParameter が書込む member slots の確認 (0x2dc=732:TrapSVF等, 728, 740, 744)
  const rd32 = (a) => { const u = new DataView(new Uint8Array(4).buffer); /* dummy */ return 0; };
  const mem32 = (addr) => { const out = new Uint32Array(4); for (let k=0;k<4;k++) out[k] = U8[addr+k]; return out; };
  {
    const objNum = Number(objPtr);
    const p = (off) => {
      const b0 = U8[objNum + off], b1 = U8[objNum + off + 1], b2 = U8[objNum + off + 2], b3 = U8[objNum + off + 3];
      return (b0 | (b1<<8) | (b2<<16) | (b3<<24)) >>> 0;
    };
    console.log('[t1_argpass] obj+732 (0x2dc) =', '0x' + p(732).toString(16), '(0x3f000000 期待)');
    console.log('[t1_argpass] obj+728 (0x2d8) =', '0x' + p(728).toString(16), '(0x3f000000 期待)');
    console.log('[t1_argpass] obj+536 (5*4+0x20c) =', '0x' + p(536).toString(16), '(idx5: 5*4+0x20c)');
  }
  const objNum2 = Number(objPtr);
  if (process.env.T1SVF === '1') { U8[objNum2 + 584] = 0; console.log('[t1_sel] forced obj+584=0 (SVF loop 路線)'); }
  if (process.env.T1SWEEP === '1') U8[objNum2 + 806] = 0;
  console.log('[t1_sel] obj+806 (0x326 flag) =', U8[objNum2+806], 'obj+584 (0x248) =', U8[objNum2+584], 'obj+795..805 =', [U8[objNum2+795],U8[objNum2+796],U8[objNum2+800],U8[objNum2+803],U8[objNum2+804]]);
  const rr = fresume(objPtr);
  console.log('[t1_sel] post-resume obj+806 =', U8[objNum2+806], 'obj+584 =', U8[objNum2+584]);
  console.log('[t1_argpass] resume rc:', rr);
  const N = 256;
  for (let i = 0; i < N; i++) {
    const sig = process.env.T1SIG ? Number(process.env.T1SIG) : 0;
    const x = Math.sin(i * 0.05) * 0.7 + Math.sin(i * 0.011) * 0.3 + sig;
    const xb = Math.cos(i * 0.13) * 0.5 + sig;
    F32[(BUF / 4) + i] = Math.fround(x);
    F32[(BUF / 4) + N + i] = Math.fround(xb);
  }
  F32[(BUF / 4) + 2*N] = 0; F32[(BUF / 4) + 3*N] = 0;
  mod.HEAP32[(IN_A / 4)] = BUF;
  mod.HEAP32[(IN_A / 4) + 1] = BUF + N * 4;
  mod.HEAP32[(OU_A / 4)] = BUF + N * 8;
  mod.HEAP32[(OU_A / 4) + 1] = BUF + N * 12;
  const rp = fproc(objPtr, BigInt(IN_A), BigInt(OU_A), BigInt(N));
  console.log('[t1_argpass] process rc:', rp);
  const outData = new Float32Array(N * 2);
  for (let i = 0; i < N; i++) {
    outData[i] = F32[(BUF / 4) + 2*N + i];
    outData[i + N] = F32[(BUF / 4) + 3*N + i];
  }
  const dv = new DataView(outData.buffer);
  const hex = [];
  const uniq = new Set();
  let maxAbs = 0, nZero = 0;
  for (let i = 0; i < outData.length; i++) {
    const bits = dv.getUint32(i * 4);
    hex.push(bits.toString(16).padStart(8, '0'));
    uniq.add(bits.toString(16).padStart(8, '0'));
    const f = outData[i];
    const a = Math.abs(f);
    if (a > maxAbs) maxAbs = a;
    if (f === 0) nZero++;
  }
  const outPath = process.env.T1OUT || (HERE + 'work/t1_out_sel8.hex');
  fs.writeFileSync(outPath, hex.join('\n') + '\n');
  console.log('[t1_argpass] output written:', outPath, '(', hex.length, ')');
  console.log('[t1_argpass] unival count:', uniq.size, '/ 512  max|f32|:', maxAbs.toExponential(3), ' zero:', nZero);
  console.log('[t1_argpass] OK (run complete)');
}

main().catch((e) => { console.error('[t1_argpass][FAIL]', e); process.exit(1); });
