// x87_fn_entry_wasm.mjs: x87 を含む関数 (#2989) の wasm 側ランナー。 x87_fn_native と同じ scen.txt を読み、同じ書式の結果を出す。
// #4924: ecx = WIDE_BASE の行は、image 内の広い範囲 (WIDE_BASE から WIDE_LEN) の書込みを数える (native の wide= と同じ式)。
// 使い方: node x87_fn_entry_wasm.mjs <wasm_x87.cjs> <image.bin> <scen.txt> <out.txt>
import fs from 'node:fs';
import { createRequire } from 'node:module';
const [, , modPath, imgPath, scenPath, outPath] = process.argv;
const createModule = createRequire(import.meta.url)(modPath);
const M = await createModule();
const IMG_BASE = 0x10000000, OBJ_ADDR = 0x10f80000, OBJ_WIN = 0x540;
const STK_LO = 0x10f00000 - 0x1100, STK_WIN = 0x1e0;
const WIDE_BASE = 0x10700000, WIDE_LEN = 0x900000, WIDE_SKIP_LO = 0x7fe000, WIDE_SKIP_HI = 0x800100;
const img = fs.readFileSync(imgPath);
M.HEAPU8.set(img, IMG_BASE);
const wideInit = M.HEAPU8.slice(WIDE_BASE, WIDE_BASE + WIDE_LEN);
const lines = fs.readFileSync(scenPath, 'utf8').split('\n').filter((l) => l.trim().length > 0);
const out = [];
const hex = (v, n) => (v >>> 0).toString(16).padStart(n, '0');
const wideDiff = (pre, post) => {
    const a = new Uint32Array(pre.buffer), b = new Uint32Array(post.buffer);
    let h = 0x811c9dc5, c = 0;
    for (let i = 0; i < WIDE_LEN / 4; i++) {
        const o = i * 4;
        if (o >= WIDE_SKIP_LO && o < WIDE_SKIP_HI) continue;
        if (a[i] !== b[i]) {
            h = Math.imul(h ^ o, 0x01000193) >>> 0;
            h = Math.imul(h ^ b[i], 0x01000193) >>> 0;
            c++;
        }
    }
    return hex(c, 4) + ':' + hex(h, 8);
};
lines.forEach((l, idx) => {
    const f = l.trim().split(/\s+/);
    const [va, ecx, a0, a1, a2, a3, a4, a5] = f.slice(0, 8).map((h) => parseInt(h, 16));
    const init = Buffer.from(f[8], 'hex');
    const wide = ecx === WIDE_BASE;
    if (wide) M.HEAPU8.set(wideInit, WIDE_BASE);
    M.HEAPU8.set(init, ecx);
    M.HEAPU8.fill(0, STK_LO, STK_LO + STK_WIN);
    const pre = wide ? M.HEAPU8.slice(WIDE_BASE, WIDE_BASE + WIDE_LEN) : null;
    const eax = M._ott_call32x(va, ecx, a0, a1, a2, a3, a4, a5) >>> 0;
    const st0 = M._ott_x87_st0() >>> 0;
    const st0d = hex(M._ott_x87_st0d_hi(), 8) + hex(M._ott_x87_st0d_lo(), 8);
    const depth = M._ott_x87_depth() >>> 0;
    const mem = Buffer.from(M.HEAPU8.subarray(ecx, ecx + OBJ_WIN)).toString('hex');
    const stk = Buffer.from(M.HEAPU8.subarray(STK_LO, STK_LO + STK_WIN)).toString('hex');
    const wtag = wide ? wideDiff(pre, M.HEAPU8.slice(WIDE_BASE, WIDE_BASE + WIDE_LEN)) : '-';
    out.push(`${idx.toString(16).padStart(4, '0')} va=${hex(va, 8)} eax=${hex(eax, 8)} st0=${hex(st0, 8)} st0d=${st0d} d=${depth.toString(16)} mem=${mem} stk=${stk} wide=${wtag}`);
});
fs.writeFileSync(outPath, out.join('\n') + '\n');
