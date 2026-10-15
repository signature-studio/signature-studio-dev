// entry_wasm.mjs: ia32 lift の wasm 側ランナー (#1223)。 native_entry と同じ scen.txt を読み、同じ書式の結果を出す。
// 使い方: node entry_wasm.mjs <wasm_entry.cjs> <image.bin> <scen.txt> <out.txt>
import fs from 'node:fs';
import { createRequire } from 'node:module';
const [, , modPath, imgPath, scenPath, outPath] = process.argv;
const createModule = createRequire(import.meta.url)(modPath);
const M = await createModule();
const IMG_BASE = 0x10000000, OBJ_ADDR = 0x10f80000, OBJ_LEN = 0x80, HEAP_ADDR = 0x10800000;
const img = fs.readFileSync(imgPath);
M.HEAPU8.set(img, IMG_BASE);
const lines = fs.readFileSync(scenPath, 'utf8').split('\n').filter((l) => l.trim().length > 0);
const out = [];
const TEB_ADDR = M._ott_teb_addr(), TEB_LEN = 64;
M._ott_set_teb();
lines.forEach((l, idx) => {
    const f = l.trim().split(/\s+/);
    const [va, ecx, a0, a1, a2, a3] = f.slice(0, 6).map((h) => parseInt(h, 16));
    const init = Buffer.from(f[6], 'hex');
    M.HEAPU8.set(init, OBJ_ADDR);
    const hasTeb = f.length > 7;
    M.HEAPU8.fill(0, TEB_ADDR, TEB_ADDR + TEB_LEN);
    if (hasTeb) M.HEAPU8.set(Buffer.from(f[7], 'hex'), TEB_ADDR);
    const eax = M._ott_call32(va, ecx, a0, a1, a2, a3) >>> 0;
    const mem = Buffer.from(M.HEAPU8.subarray(OBJ_ADDR, OBJ_ADDR + OBJ_LEN)).toString('hex');
    const heap = Buffer.from(M.HEAPU8.subarray(HEAP_ADDR, HEAP_ADDR + 64)).toString('hex');
    const teb = hasTeb ? ' teb=' + Buffer.from(M.HEAPU8.subarray(TEB_ADDR, TEB_ADDR + TEB_LEN)).toString('hex') : '';
    out.push(`${idx.toString(16).padStart(4, '0')} va=${va.toString(16).padStart(8, '0')} eax=${eax.toString(16).padStart(8, '0')} mem=${mem} heap=${heap}${teb}`);
});
fs.writeFileSync(outPath, out.join('\n') + '\n');
