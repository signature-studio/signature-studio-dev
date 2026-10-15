// x87_fn_entry_wasm.mjs: x87 を含む関数 (#2989) の wasm 側ランナー。 x87_fn_native と同じ scen.txt を読み、同じ書式の結果を出す。
// 使い方: node x87_fn_entry_wasm.mjs <wasm_x87.cjs> <image.bin> <scen.txt> <out.txt>
import fs from 'node:fs';
import { createRequire } from 'node:module';
const [, , modPath, imgPath, scenPath, outPath] = process.argv;
const createModule = createRequire(import.meta.url)(modPath);
const M = await createModule();
const IMG_BASE = 0x10000000, OBJ_ADDR = 0x10f80000, OBJ_WIN = 0x540;
const img = fs.readFileSync(imgPath);
M.HEAPU8.set(img, IMG_BASE);
const lines = fs.readFileSync(scenPath, 'utf8').split('\n').filter((l) => l.trim().length > 0);
const out = [];
const hex = (v, n) => (v >>> 0).toString(16).padStart(n, '0');
lines.forEach((l, idx) => {
    const f = l.trim().split(/\s+/);
    const [va, ecx, a0, a1, a2, a3, a4, a5] = f.slice(0, 8).map((h) => parseInt(h, 16));
    const init = Buffer.from(f[8], 'hex');
    M.HEAPU8.set(init, OBJ_ADDR);
    const eax = M._ott_call32x(va, ecx, a0, a1, a2, a3, a4, a5) >>> 0;
    const st0 = M._ott_x87_st0() >>> 0;
    const st0d = hex(M._ott_x87_st0d_hi(), 8) + hex(M._ott_x87_st0d_lo(), 8);
    const depth = M._ott_x87_depth() >>> 0;
    const mem = Buffer.from(M.HEAPU8.subarray(OBJ_ADDR, OBJ_ADDR + OBJ_WIN)).toString('hex');
    out.push(`${idx.toString(16).padStart(4, '0')} va=${hex(va, 8)} eax=${hex(eax, 8)} st0=${hex(st0, 8)} st0d=${st0d} d=${depth.toString(16)} mem=${mem}`);
});
fs.writeFileSync(outPath, out.join('\n') + '\n');
