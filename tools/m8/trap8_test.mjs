// trap8_test.mjs (M8): m8 stub 群実装後の probe 直呼検証。
// tools/m6/work/trap_test.mjs と同一 probe 集合 (19 実行 + 3 skip) を ott_m8 モジュール
// で駆動するが, 引数を実機語義に合わせ是正 ( scratch 文字列は linear memory 直書き)。
//   期待: missing-function fail-fast abort 11 件のうち 10 種が m8_rt.c stub で解消
//   (#6 function_1801c24d0 は caller broken-lift OOB 待ちのため fail-fast 保持),
//   broken-lift OOB 2 件 (c69cc/c91cc) は FAIL 保持, #8 c6744 は Win API 待ち fail-fast。
const VA_BASE = 0x30000000;
(async () => {
    const m2 = await import('./work/ott_m8.cjs');
    const mod = await (m2.default ? m2.default() : m2());
    if (mod._m6_data_install) mod._m6_data_install();
    const HEAPU8 = mod.HEAPU8, F32 = mod.HEAPF32;
    const SCR = VA_BASE + 0x3a0800;
    const U16 = new Uint16Array(HEAPU8.buffer, HEAPU8.byteOffset + SCR, 64);
    const su16 = (off, str) => { for (let i = 0; i < str.length; i++) U16[off/2 + i] = str.charCodeAt(i); U16[off/2 + str.length] = 0; };
    su16(0, 'abc'); su16(8, 'abc');
    const obj = BigInt(mod._function_18011d400(BigInt(VA_BASE + 0x310000), 0n));
    const i64 = (v) => BigInt(v);
    const probe = [
      ['function_1801bfab4', 1, [i64(0)]],                          /* #1 参照値 0 stub */
      ['function_1801c0ac8', 3, [i64(SCR), SCR + 8, i64(4)]],  /* #2 wmemcmp leaf */
      ['function_1801c1438', 2, [i64(0), i64(0)]],                  /* #3 no-op */
      ['function_1801c17e0', 1, [i64(0)]],                          /* #4 leaf */
      ['function_1801c17fc', 2, [i64(3), 3]],                       /* #5 leaf */
      ['function_1801c24d0', 3, [i64(1), i64(0), i64(0)]],          /* #6 fail-fast 保持 (caller OOB 待ち) */
      ['function_1801c33e0', 0, []],                                /* #7 leaf */
      ['function_1801c6744', 4, [i64(932), 0, i64(SCR), i64(0)]],   /* #8 Win API 待ち (fail-fast 仕様) */
      ['function_1801c67a0', 1, [obj]],                             /* #9 refcount addref */
      ['function_1801c69cc', 1, [i64(0x30310000)]],                 /* broken-lift OOB (FAIL 保持) */
      ['function_1801c6a04', 3, [obj, i64(0), i64(0)]],             /* #10 xadd dec */
      ['function_1801c6a2c', 4, [i64(0), i64(0), i64(0), i64(0)]],  /* (probeOK 系) */
      ['function_1801c6b44', 2, [i64(0), i64(0)]],
      ['function_1801c721c', 2, [obj, SCR]],                   /* #11 CRT lock 族 */
      ['function_1801c78', 1, []],
      ['function_1801c8a80', 3, [i64(0), i64(0), 0]],
      ['function_1801c91cc', 4, [0x30310000, i64(0), i64(0), i64(0)]],  /* OOB FAIL 保持 */
      ['function_1801cadd', 1, [0]],
      ['function_1801cad0', 1, [0]],
      ['function_1801b4610', 1, []],
      ['function_1801b4900', 1, []],
      ['function_1801b4e30', 1, []]
    ];
    let ok = 0, fail = 0;
    for (const [n, argc, args] of probe) {
      if (!mod['_' + n]) continue;
      try { mod['_' + n](...args); ok++; console.log('OK:', n); }
      catch (e) { fail++; console.log('FAIL:', n, '|', String(e.message).slice(0, 80)); }
    }
    console.log(`[trap8] OK ${ok} / FAIL ${fail}`);
})().then(()=>{},(e)=>{ console.log('[trap8] HARNESS FAIL', e); process.exit(1); });
