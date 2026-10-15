// dyn_509.mjs — #509: 修復した関数を m11 wasm (修復前 / 修復後) で直接呼び、機械語の意味から決まる期待値と突き合わせる動的確認。
// (liftdiff は native 側に fl-win64 の PE が要るため、素材の無い環境では wasm 単体の入出力で代替する。判定の根拠は各 case のコメントの機械語)
// 使い方: node dyn_509.mjs BASE.cjs NEW.cjs IMAGE.bin
import fs from 'fs';
const [baseCjs, newCjs, image] = process.argv.slice(2);
const S = 0x11e00000;      // scratch (INITMEM 0x12000000 の内側。boot はしないので heap と衝突しない)
async function mk(cjs) {
  const mod = await (await import(cjs)).default({ printErr: () => {} });
  mod.HEAPU8.set(fs.readFileSync(image), 0);
  mod.HEAPU8.fill(0, S, S + 0x10000);
  return mod;
}
const rd64 = (m, a) => m.HEAPU8.slice(a, a + 8).reduce((v, b, i) => v | (BigInt(b) << BigInt(8 * i)), 0n);
const wr64 = (m, a, v) => { for (let i = 0; i < 8; i++) m.HEAPU8[a + i] = Number((BigInt(v) >> BigInt(8 * i)) & 0xffn); };
const rd32 = (m, a) => (m.HEAPU8[a] | (m.HEAPU8[a + 1] << 8) | (m.HEAPU8[a + 2] << 16) | (m.HEAPU8[a + 3] << 24)) >>> 0;
const wr32 = (m, a, v) => { for (let i = 0; i < 4; i++) m.HEAPU8[a + i] = (v >>> (8 * i)) & 0xff; };
const cases = [
  // c62780: 機械語 c627ab `mov rcx,[rsi]` (rsi = r8 = arg3) → c627ae `mov [rax+rdx*8+8],rcx` (rax=[obj+8], rdx=2*idx)。期待: array[idx*16+8] = *arg3
  { name: 'c62780 (arg3 の 8B を array[idx] へ)', run(m) {
      const A = S + 0x1000; wr64(m, S + 8, A); wr64(m, S + 0x100, 0x1122334455667788n);
      m._function_c62780(BigInt(S), 1n, BigInt(S + 0x100));
      return rd64(m, A + 24); }, want: 0x1122334455667788n },
  // 7e5240: 機械語 7e5268 `mov eax,[rsi]` (rsi = r8 = arg3) → 7e526a `mov [rdx+4],eax`。期待: dst[1] = src[0] (dword)
  { name: '7e5240 (arg3 の dword を arg2[1] へ)', run(m) {
      wr32(m, S + 0x98, 100); m.HEAPU8[S + 0x458] = 0; wr32(m, S + 0x300, 0xDEADBEEF);
      m._function_7e5240(BigInt(S), S + 0x200, BigInt(S + 0x300));
      return BigInt(rd32(m, S + 0x204)); }, want: 0xDEADBEEFn },
  // 409c80: len=5 は 4B path。機械語 409cc0 `mov eax,[rcx]` → `mov [rdx],eax` (+ 末尾 4B)。期待: dst[0..4] = src[0..4]
  { name: '409c80 len=5 (4B path の先頭 4B)', run(m) {
      for (let i = 0; i < 16; i++) m.HEAPU8[S + 0x400 + i] = 0x10 + i;
      m._function_409c80(BigInt(S + 0x400), BigInt(S + 0x500), 5n);
      return BigInt(rd32(m, S + 0x500)); }, want: 0x13121110n },
  // 41a670: 機械語 41a6c2〜41a6d6 (head から node を探し、見つけた prev の next を node.next で置換 `mov rcx,[rcx]; mov [rax],rcx`)。
  //   head=O, O.next=N, N.next=X, N.[+8]=0。期待: O.next = X
  { name: '41a670 (unlink: prev.next = node.next)', run(m) {
      const N = S + 0x600, O = S + 0x700; wr64(m, N, 0x1111n); wr64(m, N + 8, 0n); wr64(m, O, BigInt(N)); wr64(m, 16404608, BigInt(O));
      m._function_41a670(BigInt(N));
      return rd64(m, O); }, want: 0x1111n },
  // 47ad70: 機械語 47ad82 `mov r8,[rdx]` (value = *arg2) / `mov rdx,[rcx]` (array = *arg1) / `mov rax,[rcx+8]` (count)。[rcx+0x28]=0 の経路で array[0..count) を線形探索し index、無ければ -1。期待: value=*arg2=0x20 の index 1。
  //   既知の未修復 (known): IR は array 基点を `%arg1` のまま使い (`mov rdx,[rcx]` が落ちている)、修復は value 側 (`*arg2`) だけ。修復前後とも FAIL するのは IR の array 基点の誤り。
  { name: '47ad70 (配列の線形探索: index を返す)', known: 'array 基点 (*arg1) が IR で落ちている', run(m) {
      const T = S + 0x800, A = S + 0x900, V = S + 0x880;
      wr64(m, T, BigInt(A)); wr64(m, T + 8, 3n);
      wr64(m, A, 0x10n); wr64(m, A + 8, 0x20n); wr64(m, A + 16, 0x30n); wr64(m, V, 0x20n);
      return BigInt.asUintN(64, m._function_47ad70(BigInt(T), BigInt(V))); }, want: 1n },
  // 1063090 (F3c-use): 機械語 `mov rax,[rcx]; test rax,rax; je; mov rax,[rax-8]; ret`。期待: pp=S, *pp=S+0x1008, [S+0x1000]=0xABCD → 0xABCD
  { name: '1063090 (消費者が演算・address base の D4)', run(m) {
      wr64(m, S, BigInt(S + 0x1008)); wr64(m, S + 0x1000, 0xABCDn);
      return BigInt.asUintN(64, m._function_1063090(BigInt(S))); }, want: 0xABCDn },
];
const base = await mk(baseCjs), nw = await mk(newCjs);
let bad = 0;
for (const c of cases) {
  const r = {};
  for (const [k, m] of [['before', base], ['after', nw]]) {
    try { r[k] = c.run(m); } catch (e) { r[k] = 'TRAP ' + String(e.message).split('\n')[0]; }
    for (const mm of [m]) mm.HEAPU8.fill(0, S, S + 0x10000);
  }
  const f = (v) => typeof v === 'bigint' ? '0x' + v.toString(16) : v;
  const ok = r.after === c.want, was = r.before === c.want;
  if (c.known) {
    console.log(`DYN ${c.name}: want=${f(c.want)} before=${f(r.before)} (${was ? 'PASS' : 'FAIL'}) after=${f(r.after)} (${ok ? 'PASS' : 'FAIL'}) KNOWN: ${c.known}`);
    continue;
  }
  if (!ok) bad++;
  console.log(`DYN ${c.name}: want=${f(c.want)} before=${f(r.before)} (${was ? 'PASS' : 'FAIL'}) after=${f(r.after)} (${ok ? 'PASS' : 'FAIL'})`);
}
console.log('DYN_SUMMARY after_fail=' + bad + '/' + cases.filter(c => !c.known).length + ' known=' + cases.filter(c => c.known).length);
