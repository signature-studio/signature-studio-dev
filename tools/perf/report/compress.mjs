// 実 wasm (M11 boot closure 5.65MB, OTT) の転送サイズ: gzip-9 / brotli-11 / zstd-19 / xz-9
import fs from 'node:fs'; import zlib from 'node:zlib'; import cp from 'node:child_process';
const W = new URL('../work/', import.meta.url).pathname;
const out = [];
for (const [nm, f] of [['m11_boot snapshot(-O0, 8,936 funcs; 実験の K=1 原本)', 'huge/k1.wasm'], ['m11 -O1', 'm11/o1/m11.wasm'], ['m11 -O2', 'm11/o2/m11.wasm'], ['ott o2', 'ott/o2/ott.wasm'], ['ott o0 (M10)', 'ott/o0/ott.wasm']]) {
  const p = W + f; if (!fs.existsSync(p)) continue;
  const b = fs.readFileSync(p);
  const t0 = Date.now();
  const gz = zlib.gzipSync(b, { level: 9 }).length;
  const br = zlib.brotliCompressSync(b, { params: { [zlib.constants.BROTLI_PARAM_QUALITY]: 11, [zlib.constants.BROTLI_PARAM_LGWIN]: 24, [zlib.constants.BROTLI_PARAM_SIZE_HINT]: b.length } }).length;
  let zs = NaN, xz = NaN;
  try { zs = +cp.execSync(`zstd -19 --long=27 -q -c ${p} | wc -c`).toString(); } catch {}
  try { xz = +cp.execSync(`xz -9e -T0 -c ${p} | wc -c`).toString(); } catch {}
  out.push({ name: nm, bytes: b.length, gzip9: gz, brotli11: br, zstd19: zs, xz9e: xz, sec: (Date.now() - t0) / 1000 });
}
fs.writeFileSync(new URL('../results/compress.json', import.meta.url).pathname, JSON.stringify(out, null, 1));
console.log('| wasm | bytes | gzip-9 | brotli-11 | zstd-19 | xz-9e |\n|---|--:|--:|--:|--:|--:|');
for (const o of out) console.log(`| ${o.name} | ${o.bytes} | ${o.gzip9} (${(o.gzip9 / o.bytes * 100).toFixed(1)}%) | ${o.brotli11} (${(o.brotli11 / o.bytes * 100).toFixed(1)}%) | ${o.zstd19} (${(o.zstd19 / o.bytes * 100).toFixed(1)}%) | ${o.xz9e} (${(o.xz9e / o.bytes * 100).toFixed(1)}%) |`);
