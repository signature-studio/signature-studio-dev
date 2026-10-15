// cpi_pool_drive.mjs: cpi_pool_probe.sh の実行器。[dbg]・[cpi] 行を stderr から出す (#5252)。
// usage: node cpi_pool_drive.mjs <dbg.cjs> <image.bin> <ImageBase 16進> <entry VA 16進> <a0 16進>
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';

const require = createRequire(import.meta.url);
const [cjs, imgPath, baseHex, vaHex, a0Hex] = process.argv.slice(2);
const base = Number(baseHex);
const va = Number(vaHex);
const pe = readFileSync(imgPath);
const peOff = pe.readUInt32LE(0x3c);
const sizeOfImage = pe.readUInt32LE(peOff + 24 + 56);
const createModule = require(cjs);
const err = [];
const m = await createModule({ print: () => {}, printErr: (s) => { err.push(s); } });
m.HEAPU8.set(pe, base);
m._cpi_host_setup(BigInt(base), BigInt(base + sizeOfImage));
try {
  m._ott_run(va, BigInt(a0Hex), 0n, 0n, 0n, 0n, 0n, 0n, 0n);
} catch (e) {
  err.push('TRAP ' + e.message);
}
for (const l of err) if (l.includes('[dbg]') || l.includes('[cpi]') || l.startsWith('TRAP')) console.log(l);
