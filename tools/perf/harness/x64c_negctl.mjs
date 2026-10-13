// ネガティブコントロール (署名検査が壊れを検出できるか): (a) 入力 1 sample を 1 ulp ずらす → 署名が変わること, (b) wasm の 1 byte (bit0) を K 箇所反転 → 署名不一致 or 例外になる箇所数
// (b) は到達しない lift 関数 (75 関数中実行されるのは一部) の byte を壊しても無害なので検出数は K 未満になる。
//   node x64c_negctl.mjs <work/ott_x64c/v.wasm> [箇所数=20]   (names は同名 .cjs から)。 exit 0 = (a) 検出 かつ (b) 1 箇所以上検出, 1 = 検査が無効
import fs from 'node:fs';
import { setupOtt } from './x64c_core.mjs';
import { namesFromGlue } from './x64c_names.mjs';
const f = process.argv[2], K = +(process.argv[3] || 20), EXPECT = '6b1696f0';
const base = fs.readFileSync(f), names = namesFromGlue(f.replace(/\.wasm$/, '.cjs'));
const base0 = await setupOtt(await WebAssembly.compile(base), names);
new Uint32Array(base0.x.memory.buffer)[0x30340000 / 4 + 7] += 1;   // BUF の 8 番目の入力 sample を +1 ulp
const perturbed = base0.signature();
const res = { sigMismatch: 0, exception: 0, undetected: 0 };
for (let k = 0; k < K; k++) {
  const off = Math.floor(base.length * (0.1 + 0.8 * k / (K - 1)));
  const b = Buffer.from(base); b[off] ^= 1;
  let r;
  try { const o = await setupOtt(await WebAssembly.compile(b), names); const sig = o.signature(); r = sig === EXPECT ? 'undetected' : 'sigMismatch'; }
  catch (e) { r = 'exception'; }
  res[r]++;
}
console.log(JSON.stringify({ f, inputPlus1ulpSig: perturbed, inputPerturbDetected: perturbed !== EXPECT, flips: K, ...res, flipDetected: res.sigMismatch + res.exception }));
process.exit(perturbed !== EXPECT && res.sigMismatch + res.exception > 0 ? 0 : 1);
