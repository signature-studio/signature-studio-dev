(async () => {
    const m2 = await import('./work/ott_m8.cjs');
    const mod = await (m2.default ? m2.default() : m2());
    if (mod._m6_data_install) mod._m6_data_install();
    try { console.log('bf664 rc', mod._function_1801bf664(BigInt(0))); } catch (e) { console.log('FAIL', e.message, (e.stack||'').split('\n')[1]); }
    // M6b 検証結果 (2026-10): 0x30260ce0 の RAW DLL 値 = LE [0x32,0xA2,0xDF,0x2D]
    //   = 0x2DDFA232 (= 769630770, f32 bits では 2.542419e-11)。IR 側 global_var_
    //   literal (i32 769630770) と m6_data install は**一致** (旧 t3 コメントの
    //   期待値 0x2DEB8762 = 769756514 (2.6776e-11) は誤り — 実データ照合で
    //   型取り違え無しと確認)。bf664 rc は CRT lock (be668/be6bc) no-op 化のため
    //   RetDec 部分 lift 状態の生戻り値 (照合対象外)。
    const U8 = mod.HEAPU8;
    console.log('mem[0x30260ce0..] =', [U8[0x30260ce0], U8[0x30260ce0+1], U8[0x30260ce0+2], U8[0x30260ce0+3]]);
    console.log('mem[0x3026c388..] =', [U8[0x3026c388], U8[0x3026c388+1], U8[0x3026c388+2], U8[0x3026c388+3]]);
    // M6b OK 判定: mem 値 == DLL 実データ (0x2DDFA232) 一致を検収
    const ok = U8[0x30260ce0] === 0x32 && U8[0x30260ce0 + 1] === 0xA2 && U8[0x30260ce0 + 2] === 0xDF && U8[0x30260ce0 + 3] === 0x2D;
    console.log(ok ? '[t3][OK] mem[0x30260ce0] == 0x2DDFA232 (DLL 実データと一致; RetDec 型取り違え無し)' : '[t3][FAIL] mem 不一致');
    if (!ok) process.exit(1);
})();
