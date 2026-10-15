// dyn_ld115.mjs — #2447 (LD-115): 666a60 のループ内 store を修復前 / 修復後の wasm で直接呼ぶ動的確認。
// 機械語 666b0c〜666b13 (`mov r8,[rbp+0x28]; mov r8,[r8]; mov [rcx+0x10],r8`) の意味から期待値を決める。
//   P = arg1 (rbp+0x28)、[P] = N (function_409470 が確保した object)、count = arg2、arg3 = r8d、slot(i) = N+0x40+32*i。
//   期待: 各 i で slot(i) = { +0: 0, +8: arg3+i, +16: N (= [P]), +24: 0 }。修復前 IR は +16 に slot アドレス (N+0x40+32*i) を書く。
// 初期化: survey と同じく m11_set_survey(1) → m11_boot_enter (DllMain 相当) → unit 0・1 を m11_call_unit で実行
//   (unit を流さないと function_409470 (確保) が heap 未初期化で trap する。unit 0 だけでは足りない、と実測)。
// 3 版を比べる: BASE = 現行 ldfix のみ / MID = + 回数初期値 (count) / NEW = + ループ内 store (count+store)。
// 期待 (機械語どおり): BASE は回数 0 で trap、MID は slot.f16 だけ FAIL (slot アドレスが入る)、NEW は全 PASS。
// #2513 (LD-116): 任意の 5 版目 AFTER116.cjs (= NEW + entry の回数 0 早期脱出, fix_ld116.py) を渡すと、次を追加で測る。
//   arg2=3: AFTER116 の結果が NEW と同一 (ret・count・tag・slot 4 欄すべて)。
//   arg2=0: NEW は機械語と違い trap する (既知の欠陥・陰性対照)。AFTER116 は trap せず ret=0・count=0・tag=2。
// 使い方: node dyn_ld115.mjs BASE.cjs MID.cjs NEW.cjs IMAGE.bin [AFTER116.cjs]
import fs from 'fs';
const [baseCjs, midCjs, newCjs, image, after116Cjs] = process.argv.slice(2);
const P = 0x11f00000;
const ARG4 = 0x11f00100;
const COUNT = 3n, ARG3 = 5n;
async function mk(cjs) {
  const mod = await (await import(cjs)).default({ printErr: () => {} });
  mod.HEAPU8.set(fs.readFileSync(image), 0);
  mod._m11_set_survey(1);
  const sp = mod._emscripten_stack_get_current();
  try { mod._m11_boot_enter(0n, 1n); } catch (e) { if (!(e && e.m11_dllmain_done !== undefined)) throw e; mod.__emscripten_stack_restore(sp); }
  for (const i of [0, 1]) { try { mod._m11_call_unit(i); } catch (e) { if (e && e.m11_dllmain_done !== undefined) mod.__emscripten_stack_restore(sp); } }
  return mod;
}
const rd = (m, a, n) => m.HEAPU8.slice(a, a + n).reduce((v, b, i) => v | (BigInt(b) << BigInt(8 * i)), 0n);
const wr = (m, a, n, v) => { for (let i = 0; i < n; i++) m.HEAPU8[a + i] = Number((BigInt(v) >> BigInt(8 * i)) & 0xffn); };
const hex = (v) => (typeof v === 'bigint' ? '0x' + v.toString(16) : v);
function run(m, count = COUNT) {
  wr(m, P, 8, 0n);
  wr(m, ARG4, 16, 0x1111n);
  const ret = m._function_666a60(BigInt(P), count, ARG3, ARG4);
  const N = rd(m, P, 8);
  const want = [], got = [];
  for (let i = 0n; i < count; i++) {
    const s = Number(N) + 0x40 + 32 * Number(i);
    want.push({ f0: 0n, f8: ARG3 + i, f16: N, f24: 0n });
    got.push({ f0: rd(m, s, 8), f8: rd(m, s + 8, 8), f16: rd(m, s + 16, 8), f24: rd(m, s + 24, 8) });
  }
  return { N, ret, want, got, count: rd(m, Number(N), 4), tag: rd(m, Number(N) + 4, 4) };
}
const judge = (r) => {
  if (r.trap) return 'TRAP';
  if (r.count !== COUNT || r.tag !== 2n) return 'FAIL(count)';
  if (r.ret !== COUNT) return `FAIL(ret=${hex(r.ret)})`;
  for (let i = 0; i < r.want.length; i++)
    for (const f of ['f0', 'f8', 'f16', 'f24'])
      if (r.got[i][f] !== r.want[i][f]) return `FAIL(slot${i}.${f})`;
  return 'PASS';
};
const mods = { base: await mk(baseCjs), mid: await mk(midCjs), after: await mk(newCjs) };
let bad = 0;
const res = {};
const line = (k, r, j) => `DYN 666a60 ${k}: N=${hex(r.N)} ret=${hex(r.ret)} count=${hex(r.count)} slot0.f16=${hex(r.got[0].f16)} slot1.f16=${hex(r.got[1].f16)} slot2.f16=${hex(r.got[2].f16)} -> ${j}`;
for (const k of ['base', 'mid', 'after']) {
  let r;
  try { r = run(mods[k]); } catch (e) { console.log(`DYN 666a60 ${k}: TRAP ${String(e.message).split('\n')[0]}`); if (k === 'after') bad++; continue; }
  const j = judge(r);
  res[k] = r;
  if (k === 'after' && j !== 'PASS') bad++;
  console.log(line(k, r, j));
}
console.log(`DYN_SUMMARY after_fail=${bad}/1`);

if (after116Cjs) {
  const sig = (r) => [r.N, r.ret, r.count, r.tag, ...r.got.flatMap((g) => [g.f0, g.f8, g.f16, g.f24])].map(hex).join(' ');
  let zbad = 0;
  const r3 = run(await mk(after116Cjs), COUNT);
  const same3 = res.after !== undefined && sig(r3) === sig(res.after);
  const j3 = judge(r3);
  if (j3 !== 'PASS' || !same3) zbad++;
  console.log(line('after116 arg2=3', r3, `${j3} (NEW と同一: ${same3})`));
  for (const [k, cjs] of [['new arg2=0', newCjs], ['after116 arg2=0', after116Cjs]]) {
    let j;
    try { const r0 = run(await mk(cjs), 0n); j = `ret=${hex(r0.ret)} count=${hex(r0.count)} tag=${hex(r0.tag)} -> ${r0.ret === 0n && r0.count === 0n && r0.tag === 2n ? 'PASS' : 'FAIL'}`; } catch (e) { j = `TRAP ${String(e.message).split('\n')[0]}`; }
    console.log(`DYN 666a60 ${k}: ${j}`);
    if (k.startsWith('after116') && !j.endsWith('PASS')) zbad++;
  }
  console.log(`DYN_SUMMARY ld116_fail=${zbad}/2`);
}
