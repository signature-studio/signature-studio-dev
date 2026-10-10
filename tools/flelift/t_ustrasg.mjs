// t_ustrasg.mjs — M11 unit#18 chain の _UStrAsg (0x4133f0) + Move (0x409c80) スモーク (flelift 版)。
//  - UStrAsg case1/case3: zero-disp load (D7 級) + lock xadd 経路 (旧 x64c は fail-fast)
//  - case2 (literal → UStrAlloc → FastMM GetMem) は Delphi System 初期化 (mm table は .bss 0) が必要で
//    本 smoke の範囲外 → Move 直接呼出で string/SSE2/AVX 経路を検証 (CAB-5/M11 boot は後続)
const m = await (await import('./work/lift/flel.cjs')).default();
m._fle_data_install(); m._fle_init();
const U8 = m.HEAPU8, dv = new DataView(U8.buffer);
const slot = 0x20000000, str = 0x20001000 + 12;
let fail = 0;
// 1) UStrAsg(dest=&slot(=0), src=0)
dv.setBigUint64(slot, 0n, true);
try { m._fle_run(0x4133f0, BigInt(slot), 0n, 0n, 0n, 0n, 0n, 0n, 0n); console.log('case1 (src=0, old=0) OK slot=', dv.getBigUint64(slot, true)); } catch (e) { fail++; console.log('case1 TRAP', String(e).slice(0, 120)); }
// 2) refcounted (refcnt=1): lock xadd 経路
dv.setInt32(str - 8, 1, true); dv.setBigUint64(slot, 0n, true);
try { m._fle_run(0x4133f0, BigInt(slot), BigInt(str), 0n, 0n, 0n, 0n, 0n, 0n); console.log('case2 (refcnt/lock xadd) OK slot=0x' + dv.getBigUint64(slot, true).toString(16), 'refcnt', dv.getInt32(str - 8, true)); } catch (e) { fail++; console.log('case2 TRAP', String(e).slice(0, 160)); }
// 3) Move (0x409c80 = dispatcher 本体, rcx=src rdx=dst r8=n) — UStrAsg literal 経路の call 0x409c80 と同一
//    (0x409c40 は n>0x40 前提の slow-path 断片で単独呼出は未定義動作ゆえ使わない)
const src = 0x20002000, dst = 0x20003000;
for (const n of [0x188, 0x40, 0x24, 0x18, 3, 1, 0]) {
  for (let i = 0; i < n; i++) U8[src + i] = (i * 7 + 3) & 0xff;
  U8.fill(0xcc, dst, dst + n + 64);
  try { m._fle_run(0x409c80, BigInt(src), BigInt(dst), BigInt(n), 0n, 0n, 0n, 0n, 0n); let ok = true;
    for (let i = 0; i < n; i++) if (U8[dst + i] !== ((i * 7 + 3) & 0xff)) { ok = false; break; }
    console.log(`Move(n=${n}) ${ok ? 'OK' : 'DIFF'}`); if (!ok) fail++;
  } catch (e) { fail++; console.log(`Move(n=${n}) TRAP`, String(e).slice(0, 120)); }
}
process.exit(fail ? 1 : 0);
