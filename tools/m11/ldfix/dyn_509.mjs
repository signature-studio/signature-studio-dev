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
  // 40fe90 (LD-216): 機械語 40fe99 `mov rcx,[rcx]` (*arg1 = N) → 40fe9c `call 410010(N,0)`。410010 は p=N から [p-0x78] を辿る鎖の走査 (副作用なし)。
  //   [C]=N, [N-0x78]=M, [M]=0 → 410010 は rax=0 で `mov al,1` → 戻り 1 → 40fe90 は al≠0 で 1。修復前は *arg1 を渡さず C を渡すため [C-0x78]=0 → 0。
  { name: '40fe90 (*arg1 を鎖の先頭に渡す)', run(m) {
      const C = S + 0x800, N = S + 0x900, M = S + 0xa00;
      wr64(m, C, BigInt(N)); wr64(m, N - 0x78, BigInt(M)); wr64(m, M, 0n);
      return BigInt.asUintN(64, m._function_40fe90(BigInt(C))); }, want: 1n },
  // 40fe90 対照: arg1 = 0 は 40fe97 `je` で即 0 を返す (副作用なし・修復前後で同じ)
  { name: '40fe90 null (arg1=0 は 0)', run(m) {
      return BigInt.asUintN(64, m._function_40fe90(0n)); }, want: 0n },
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
  //   修復前は array 基点 (`mov rdx,[rcx]` = *arg1) と value (`*arg2`) が IR で落ちて FAIL。修復後は両方を load 値に置換して PASS (#4439)。
  { name: '47ad70 (配列の線形探索: index を返す)', run(m) {
      const T = S + 0x800, A = S + 0x900, V = S + 0x880;
      wr64(m, T, BigInt(A)); wr64(m, T + 8, 3n);
      wr64(m, A, 0x10n); wr64(m, A + 8, 0x20n); wr64(m, A + 16, 0x30n); wr64(m, V, 0x20n);
      return BigInt.asUintN(64, m._function_47ad70(BigInt(T), BigInt(V))); }, want: 1n },
  // 806740 (#5273): 機械語 420530 が this+0x6ac と arg2 の不一致を返すので書込み経路 806784 に入る。806784 `call 806820` が this+0x6ac..0x6bc へ arg2 の 16B をコピー (0x6bc は書かない)。
  //   80678f `mov rax,[rdi]` (rdi = r8 = arg3) → 806792 `mov [rbx+0x6bc],rax` (rbx = this)。期待: this+0x6bc = *arg3 (修復前は arg3 のポインタ値を書く)。
  //   その後の 8067c0 の呼出先 (8087c0・8085d0・808610・808930) は this+0x6bc を書かないことを静的に確認 (#5273)。
  { name: '806740 (*arg3 を this+0x6bc へ)', run(m) {
      const T = S + 0x800, R = S + 0x880, V = S + 0x900;
      wr64(m, V, 0x1122334455667788n); wr64(m, R, 0x10n); wr64(m, R + 8, 0x20n);
      m._function_806740(BigInt(T), BigInt(R), BigInt(V), 0n);
      return rd64(m, T + 0x6bc); }, want: 0x1122334455667788n },
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
  if (!ok) bad++;
  console.log(`DYN ${c.name}: want=${f(c.want)} before=${f(r.before)} (${was ? 'PASS' : 'FAIL'}) after=${f(r.after)} (${ok ? 'PASS' : 'FAIL'})`);
}
console.log('DYN_SUMMARY after_fail=' + bad + '/' + cases.length + ' known=0');
