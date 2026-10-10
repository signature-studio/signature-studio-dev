// m9_probe.mjs (M9 task 1): SVF 路線 (obj+0x248=0 強制) の係数 ramp 上流観測。
// 觀測対象:
//   - obj 各 member (0x250/0x258 ring 配列 pointer, 0x288..0x2a0 ramp ptr, 0x2dc/0x2ec/0x2f0 目標値,
//     0x2f4/0x2f8 現在値, 0x238/0x23c/0x240 mix gain, 0x2a8 ring write idx, 0x2ac ring len, 0x2b0 read idx)
//   - ramp 状態実体 {cur, gain} (ptr deref)
//   - processReplacing 内 rip 相対定数 (m6_data install 後 linear memory 0x30000000+RVA)
//   - fps box obj pointer [rbp+0x140..0x1f8]
//   - processReplacing 前後 ramp 状態 + 出力先頭 bits
// 使い方: node tools/m9/m9_probe.mjs  (MOD_PATH / T1SET / T1VAL / SVF 強制スポンサー env)
import fs from 'fs';

const VA_BASE = 0x30000000;
const MOD_PATH = process.env.MOD_PATH || new URL('.', import.meta.url).pathname + '../m8/work/ott_m8.cjs';

const mk = (await import(MOD_PATH)).default;
const mod = await mk();
const U8 = mod.HEAPU8;
const F32 = mod.HEAPF32;
const F64 = mod.HEAPF64;
const U32 = mod.HEAPU32;
if (mod._m6_data_install) mod._m6_data_install();

const f32bits = (v) => { const f = new Float32Array(1); f[0] = v; return BigInt(new Uint32Array(f.buffer)[0]); };
const rd32 = (a) => (U8[a] | (U8[a+1]<<8) | (U8[a+2]<<16) | (U8[a+3]<<24)) >>> 0;
const dvf = (a, n) => new DataView(U8.buffer, U8.byteOffset + a, n);
const f32s = (a) => { const dv = dvf(a, 4); return { bits: dv.getUint32(0, true), v: dv.getFloat32(0, true) }; };
const f64s = (a) => { const dv = dvf(a, 8); return { bits: dv.getBigUint64(0, true), v: dv.getFloat64(0, true) }; };

const fctor = mod._function_18011d400;
const fsetparam = mod._function_180120af0;
const fresume = mod._function_180120800;
const fproc = mod._function_18011ec20;

const OBJ = VA_BASE + 0x310000, IN_A = VA_BASE + 0x320000, OU_A = VA_BASE + 0x330000,
      BUF = VA_BASE + 0x340000;
const r = BigInt(fctor(BigInt(OBJ), 0n));
const obj = Number(r);
console.log('[probe] ctor rc (obj) = 0x' + obj.toString(16));
const setIdx = process.env.T1SET ? process.env.T1SET.split(',').map(Number) : [...Array(20).keys()];
const zeroIdx = process.env.T1Z ? process.env.T1Z.split(',').map(Number) : (process.env.T1Z === undefined ? [19] : []);
const T1VAL = process.env.T1VAL ? Number(process.env.T1VAL) : 0.5;
for (const i of setIdx) {
  const v = zeroIdx.includes(i) ? 0.0 : T1VAL;
  fsetparam(r, BigInt(i), v === 0 ? BigInt(0) : f32bits(v));
}
if (process.env.T1Z === undefined) { fsetparam(r, 19n, BigInt(0)); }

const ins32 = [];
for (let k = 0; k < 12; k++) ins32.push(f32s(obj + 0x288 + k * 8));
const f = (o, a, note='') => {
  const p = rd32(o + a);
  const s1 = f32s(p), s2 = f32s(p + 4);
  console.log(`  obj+0x${a.toString(16)} ptr=0x${p.toString(16)} cur=${JSON.stringify(s1.v)} (0x${s1.bits.toString(16)}) gain=${JSON.stringify(s2.v)} (0x${s2.bits.toString(16)}) ${note}`);
};

function dumpObj(stage) {
  console.log(`--- obj dump ${stage} ---`);
  console.log('  flags: 0x248(byte)=' + U8[obj+0x248], '0x326(byte)=' + U8[obj+0x326],
      '0x30c(dword)=' + rd32(obj+0x30c), '0x310(dword)=' + rd32(obj+0x310));
  for (const a of [0x18, 0x20, 0x28, 0x140, 0x148, 0x150, 0x158, 0x160, 0x168, 0x170, 0x178, 0x180, 0x188, 0x190, 0x198, 0x1a0, 0x1a8, 0x1b0, 0x1b8, 0x1c0, 0x1c8, 0x1d0, 0x1d8, 0x1e0, 0x1e8, 0x1f0, 0x1f8, 0x200, 0x208, 0x210, 0x218, 0x220, 0x238, 0x23c, 0x240, 0x250, 0x258, 0x260, 0x274, 0x280, 0x288, 0x290, 0x298, 0x2a0, 0x2b8, 0x2bc, 0x2dc, 0x2e0, 0x2e4, 0x2e8, 0x2ec, 0x2f0, 0x2f4, 0x2f8, 0x2fc, 0x300]) {
    const { bits, v } = f32s(obj + a);
    console.log(`  obj+0x${a.toString(16).padStart(3,'0')} = ${JSON.stringify(v)} (bits 0x${bits.toString(16).padStart(8, '0')}) lo-ptr=0x${(bits>>>0).toString(16)}`);
  }
  for (const a of [0x138, 0x250, 0x258, 0x260, 0x280, 0x288, 0x290, 0x298, 0x2a0]) {
    const v = rd32(obj + a);
    console.log(`  obj+0x${a.toString(16)} dword = 0x${v.toString(16)}`);
  }
  // [obj+0x250] と [obj+0x258]: pointer arrays (8 entries each)
  for (const base of [0x250, 0x258]) {
    const arr = rd32(obj + base);
    let parts = [];
    if ((arr >>> 20) === 0x300) {
      for (let k2 = 0; k2 < 8; k2++) parts.push('0x' + rd32(arr + k2 * 8).toString(16));
      console.log(`  [obj+0x${base.toString(16)}] array @0x${arr.toString(16)}: [${parts.join(', ')}]`);
    } else {
      console.log(`  [obj+0x${base.toString(16)}] = 0x${arr.toString(16)} (non-pointer?)`);
    }
  }
  console.log('  ramp states:');
  for (const a of [0x288, 0x290, 0x298, 0x2a0]) f(obj, a);
  console.log('  ring idx: 0x2a8=' + rd32(obj+0x2a8), '0x2b0=' + rd32(obj+0x2b0), '0x2ac=' + rd32(obj+0x2ac));
}

dumpObj('post-ctor/setparam');

const rr = fresume(r);
console.log('[probe] resume rc:', rr);
dumpObj('post-resume');

// SVF 強制 (obj+0x248 = 0)
U8[obj + 0x248] = 0;
console.log('[probe] forced obj+0x248 = 0');

if (process.env.DUMP_CONST === '1') {
  // rip 相対定数 (VA = next_insn + disp). linear = 0x30000000 + (VA - 0x180000000)
  const CONSTS = [
    // [va_of_insn, insnlen(expected from dsm), disp, comment]
    [0x18011ec8a, 8, 0xcfb86, 'loopConst f32 xmm6 (entry)'],
    [0x18011ec95, 8, 0xe55c3, 'loopConst f32 xmm5 (entry)'],
    [0x18011eca0, 8, 0xe5678, 'loopConst f32 xmm4 (entry)'],
    [0x18011f936, 8, 0xe4939, 'SVF ramp mult f32 xmm9'],
    [0x18011fe40, 8, 0xe444f, 'final C f32 (0x240 mix)'],
    [0x18011fe50, 8, 0xe4423, 'final C f32 (0x23c mix)'],
    [0x18011d8f3, 8, 0xe6a15, 'ctor ramp xmm7'],
    [0x18011d8fb, 8, 0xe6a19, 'ctor ramp xmm6'],
    [0x18011d947, 8, 0xe69d5, 'ctor f32 arg1'],
    [0x18011d94f, 8, 0xd97d9, 'ctor f32 arg2'],
    [0x180120699, 8, 0xce177, 'post-loop f32 xmm6 reload'],
    [0x18011fdc0, 8, 0xe44c0, 'final f64 xmm7'],
    [0x18011fdd1, 8, 0xe454e, 'final f64 xmm11'],
    [0x18011fdda, 8, 0xe44ba, 'final f64 xmm12'],
    [0x18011fde6, 8, 0xcea49, 'final f64 xmm15'],
    [0x18011fdef, 8, 0xcea28, 'final f64 xmm14'],
    [0x18011fdf8, 8, 0xe44bf, 'final f64 xmm9'],
    [0x18011fecc, 7, 0xe439c, 'final box f64 addend'],
  ];
  console.log('--- rip constants ---');
  for (const [va, insnlen, disp, note] of CONSTS) {
    if (disp === 0 && note === 'skip') continue;
    const target = va + insnlen + disp;
    const lin = VA_BASE + (target - 0x180000000);
    const s = f32s(lin);
    const d = f64s(lin);
    console.log(`  @0x${va.toString(16)} disp 0x${disp.toString(16)} -> VA 0x${target.toString(16)} lin 0x${lin.toString(16)} f32=${JSON.stringify(s.v)} f64=${JSON.stringify(d.v)} f32bits=0x${(s.bits>>>0).toString(16)} [${note}]`);
  }
  process.exit(0);
}

// 入力敷設
const N = 256;
for (let i = 0; i < N; i++) {
  const x = Math.sin(i * 0.05) * 0.7 + Math.sin(i * 0.011) * 0.3;
  const xb = Math.cos(i * 0.13) * 0.5;
  F32[(BUF / 4) + i] = Math.fround(x);
  F32[(BUF / 4) + N + i] = Math.fround(xb);
}
F32[(BUF / 4) + 2 * N] = 0; F32[(BUF / 4) + 3 * N] = 0;
U32[IN_A / 4] = BUF; U32[IN_A / 4 + 1] = BUF + N * 4;
U32[OU_A / 4] = BUF + N * 8; U32[OU_A / 4 + 1] = BUF + N * 12;
const rp = fproc(r, BigInt(IN_A), BigInt(OU_A), BigInt(N));
console.log('[probe] process rc:', rp);
dumpObj('post-process');

const outL = [], outR = [];
for (let i = 0; i < 8; i++) {
   outL.push(f32s(BUF + N * 8 + i * 4));
   outR.push(f32s(BUF + N * 12 + i * 4));
}
console.log('[probe] out L[:8]:', outL.map(o => o.v), outL.map(o => '0x' + o.bits.toString(16)));
console.log('[probe] out R[:8]:', outR.map(o => o.v), outR.map(o => '0x' + o.bits.toString(16)));
// 中間 (temp)。ring [obj+0x250] etc への f64 書込み観測 (slots 0..7 各先頭)
const r0 = rd32(obj + 0x250), r1 = rd32(obj + 0x258);
console.log('[probe] ptr check: obj+0x250 word 0x' + r0.toString(16), 'obj+0x258 word 0x' + r1.toString(16));

if (process.env.EX === '1') {
  // 実験: resume 破れ (vcall drop → SR 0 / gain 1.0 / SVF param 抜け) を JS 側で補正する
  const SR = 44100;
  F32[obj / 4 + 0x268 / 4] = SR;                       // obj+0x268 (672+... wait 0x268=616)
  for (const a of [0x288, 0x290, 0x298, 0x2a0]) {
    const p = rd32(obj + a);
    F32[(p + 4) / 4] = Math.fround(SR / (SR * 300 + SR));   // gain = C6/(C6 + C7*SR)
  }
  // SVF init (function_180126040 相当)
  const PI = Math.PI;
  let svs = [];
  const fQ = Math.fround(1.0 / Math.sqrt(2.0));
  const CTAN = (x) => Math.tan(x);
  for (let k = 0; k < 16; k++) {
    const s = rd32(obj + 0x180 + k * 8);
    svs.push(s);
    U8[s + 0x2c] = SR & 255; U8[s + 0x2d] = (SR >> 8) & 255; U8[s + 0x2e] = (SR >> 16) & 255; U8[s + 0x2f] = (SR >> 24) & 255;
    F32[s / 4 + 2] = 0; F32[s / 4 + 3] = 0;
    const f = k < 8 ? 88.3 : 2500;
    const T = CTAN(PI * f / SR);
    const A = 1 / ((1 / fQ + T) * T + 1);
    F32[(s + 0) / 4] = Math.fround(T);
    F32[(s + 4) / 4] = Math.fround(1 / fQ);
    F32[(s + 0x10) / 4] = Math.fround(A);
    F32[(s + 0x14) / 4] = Math.fround(A * T);
    F32[(s + 0x18) / 4] = Math.fround(A * T * T);
  }
  console.log('[probe][EX] SVF T/A sample (unit0):', F32[svs[0] / 4], F32[(svs[0] + 0x10) / 4], 'fQ', fQ);
  // 再実行 process
  for (let i = 0; i < N; i++) {
    const x = Math.sin(i * 0.05) * 0.7 + Math.sin(i * 0.011) * 0.3;
    const xb = Math.cos(i * 0.13) * 0.5;
    F32[(BUF / 4) + i] = Math.fround(x);
    F32[(BUF / 4) + N + i] = Math.fround(xb);
  }
  U32[IN_A / 4] = BUF; U32[IN_A / 4 + 1] = BUF + N * 4;
  U32[OU_A / 4] = BUF + N * 8; U32[OU_A / 4 + 1] = BUF + N * 12;
  const rp2 = fproc(r, BigInt(IN_A), BigInt(OU_A), BigInt(N));
  console.log('[probe][EX] process rc:', rp2);
  const oL = [], oR = [];
  for (let i = 0; i < 8; i++) { oL.push(f32s(BUF + N * 8 + i * 4)); oR.push(f32s(BUF + N * 12 + i * 4)); }
  console.log('[probe][EX] out L[:8]:', oL.map(o => o.v), '\n            bits:', oL.map(o => '0x' + o.bits.toString(16)));
  console.log('[probe][EX] out R[:8]:', oR.map(o => o.v), '\n            bits:', oR.map(o => '0x' + o.bits.toString(16)));
  // ramp states after
  for (const a of [0x288, 0x290, 0x298, 0x2a0]) f(obj, a);
  console.log('[probe][EX] obj+0x108 f32 (dbg):', f32s(obj + 0x108).v, f32s(obj + 0x10c).v, f32s(obj + 0x110).v, f32s(obj + 0x114).v, f32s(obj + 0x118).v);
  console.log('[probe][EX] obj+0x2bc (raw f32):', f32s(obj + 0x2bc).v, f32s(obj + 0x2b8).v);
}

