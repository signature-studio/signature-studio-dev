// dyn_ld108.mjs — #2316 (LD-108): 41a670 の head 解除経路を修復前 / 修復後の wasm で直接呼ぶ動的確認。
// 機械語 41a69c〜41a6a3 (`mov rax,[rbp+0x50]; mov rax,[rax]; mov [head],rax`) の意味から期待値を決める。
//   head(0x13a5080 = 16404608) = N、N.next([N+0]) = 0x2222、N.child([N+8]) = 0x3333 で function_41a670(N) を呼ぶ。
//   期待: head = [N+0] = 0x2222 (修復前 IR は [N+8] = 0x3333 を書く)。
// 使い方: node dyn_ld108.mjs BASE.cjs NEW.cjs IMAGE.bin
import fs from 'fs';
const [baseCjs, newCjs, image] = process.argv.slice(2);
const S = 0x11e00000;
const HEAD = 16404608;
async function mk(cjs) {
  const mod = await (await import(cjs)).default({ printErr: () => {} });
  mod.HEAPU8.set(fs.readFileSync(image), 0);
  mod.HEAPU8.fill(0, S, S + 0x10000);
  return mod;
}
const rd64 = (m, a) => m.HEAPU8.slice(a, a + 8).reduce((v, b, i) => v | (BigInt(b) << BigInt(8 * i)), 0n);
const wr64 = (m, a, v) => { for (let i = 0; i < 8; i++) m.HEAPU8[a + i] = Number((BigInt(v) >> BigInt(8 * i)) & 0xffn); };
const N = S + 0x600;
const cases = [
  { name: '41a670 head 解除 (head=N, N.next=0x2222)', run(m) {
      wr64(m, N, 0x2222n); wr64(m, N + 8, 0x3333n); wr64(m, HEAD, BigInt(N));
      m._function_41a670(BigInt(N));
      return rd64(m, HEAD); }, want: 0x2222n },
];
const base = await mk(baseCjs), nw = await mk(newCjs);
let bad = 0;
for (const c of cases) {
  const r = {};
  for (const [k, m] of [['before', base], ['after', nw]]) {
    try { r[k] = c.run(m); } catch (e) { r[k] = 'TRAP ' + String(e.message).split('\n')[0]; }
    m.HEAPU8.fill(0, S, S + 0x10000);
    wr64(m, HEAD, 0n);
  }
  const f = (v) => typeof v === 'bigint' ? '0x' + v.toString(16) : v;
  const ok = r.after === c.want, was = r.before === c.want;
  if (!ok) bad++;
  console.log(`DYN ${c.name}: want=${f(c.want)} before=${f(r.before)} (${was ? 'PASS' : 'FAIL'}) after=${f(r.after)} (${ok ? 'PASS' : 'FAIL'})`);
}
console.log('DYN_SUMMARY after_fail=' + bad + '/' + cases.length);
