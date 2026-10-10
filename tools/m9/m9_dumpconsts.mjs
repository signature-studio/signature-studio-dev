// m9_dumpconsts.mjs: runtime linear memory (m6 install 後) から dsm で必要な rdata 定数を読む。
// linear = 0x30000000 + (VA - 0x180000000)
import fs from 'fs';

const VA_BASE = 0x30000000;
const MOD_PATH = process.env.MOD_PATH || new URL('.', import.meta.url).pathname + '../m8/work/ott_m8.cjs';
const mk = (await import(MOD_PATH)).default;
const mod = await mk();
const U8 = mod.HEAPU8;
if (mod._m6_data_install) mod._m6_data_install();
const lin = (va) => VA_BASE + (va - 0x180000000);
const f32 = (va) => { const o = lin(va); const dv = new DataView(U8.buffer, U8.byteOffset + o, 4); return dv.getFloat32(0, true); };
const f64 = (va) => { const o = lin(va); const dv = new DataView(U8.buffer, U8.byteOffset + o, 8); return dv.getFloat64(0, true); };
const bits32 = (va) => { const o = lin(va); return (U8[o] | (U8[o+1]<<8) | (U8[o+2]<<16) | (U8[o+3]<<24)) >>> 0; };
const bits64 = (va) => { const o = lin(va); let lo = 0n; for (let k = 7; k >= 0; k--) lo = (lo << 8n) | BigInt(U8[o + k]); return lo; };

const addrs = JSON.parse(fs.readFileSync(new URL('work/const_addrs.json', import.meta.url)));
for (const [name, va, kind] of addrs) {
  if (kind === 'f64') console.log(`${name} VA 0x${va.toString(16)} f64=${f64(va)} bits64=0x${bits64(va).toString(16)}`);
  else console.log(`${name} VA 0x${va.toString(16)} f32=${f32(va)} bits32=0x${bits32(va).toString(16).padStart(8, '0')}`);
}
