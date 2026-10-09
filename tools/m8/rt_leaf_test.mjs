// rt_leaf_test.mjs (M8): m8_rt.c の bit-exact 検証 (#2/4/5/7: tools/m7/missing11.md の
// 純計算 leaf 4 種) — dsm 実体に対する期待値を JS で計算し, wasm hand stub 返り値と突合。
// (#4/#5 は bits 突合; #2 は文字比較差分; #7 は linear memory 実値と照合。)
const VA_BASE = 0x30000000;
const ptr = BigInt;

async function main() {
  const mk = (await import('./work/ott_m8.cjs')).default || (await import('./work/ott_m8.cjs'));
  const mod = await mk();
  const U8 = mod.HEAPU8, U16 = new Uint16Array(U8.buffer, U8.byteOffset, U8.length / 2);
  if (mod._m6_data_install) mod._m6_data_install();
  const SCR = VA_BASE + 0x3a0000;   // rt leaf test 用 scratch (u16 string 領域)
  const su16 = (off, str) => { const base = (SCR + off) / 2; for (let i = 0; i < str.length; i++) U16[base + i] = str.charCodeAt(i); U16[base + str.length] = 0; };

  let ok = 0, ng = 0;
  const chk = (name, got, exp) => {
    const same = ((typeof exp === 'bigint') ? got === exp : got === exp);
    if (same) { ok++; console.log('[leaf][OK]', name, '=', got); }
    else { ng++; console.log('[leaf][NG]', name, 'got', got, 'exp', exp); }
  };
  const f64bits = (v) => { const f = new Float64Array(1); f[0] = v; return BigInt(new BigUint64Array(f.buffer)[0]); };
  const f32bits = (v) => { const f = new Float32Array(1); f[0] = v; return BigInt(new Uint32Array(f.buffer)[0]); };
  const i64b = (v) => BigInt.asUintN(64, BigInt(v));

  /* ---- #4 function_1801c17e0(rcx) — double quiet bit 付与 ---- */
  const c17e0 = mod['_function_1801c17e0'];
  for (const v of [0n, 1n, 0x0007ffffffffffffn, 0x000a000000000000n,
                   f64bits(1.5), f64bits(-2.25), f64bits(0.0), f64bits(1e-300)]) {
    const exp = v | 0x0008000000000000n;
    chk(`c17e0(0x${v.toString(16)})`, BigInt.asUintN(64, BigInt(c17e0(BigInt.asIntN(64, v)))), exp);
  }

  /* ---- #5 function_1801c17fc(rcx, rdx) — f32 quiet bit22 付与 ---- */
  const c17fc = mod['_function_1801c17fc'];
  for (const [v, junk] of [[0, 12345], [0x0007ffff, 99], [0x00000001, 7],
                           [Number(f32bits(1.5) & 0xffffffffn), 0], [Number(f32bits(-0.0) & 0xffffffffn), 3]]) {
    const exp = BigInt((v >>> 0 | 0x400000) >>> 0);
    chk(`c17fc(0x${v.toString(16)},${junk})`, BigInt.asUintN(64, BigInt(c17fc(BigInt.asIntN(64, BigInt(v)), junk))), exp);
  }

  /* ---- #2 function_1801c0ac8(rcx, rdx, r8) — wmemcmp/wcsncmp 相当 ---- */
  const c0ac8 = mod['_function_1801c0ac8'];
  su16(0, 'abc'); su16(8, 'abc'); su16(16, 'abd'); su16(24, 'ab\u0000zz');
  su16(32, 'abc'); su16(40, '\u0000');
  chk('c0ac8("abc","abc",4)',         BigInt(c0ac8(BigInt(SCR + 0),  SCR + 8, 4n)),  0n);
  chk('c0ac8("abc","abd",4)',         BigInt(c0ac8(BigInt(SCR + 0),  SCR + 16, 4n)), BigInt(-1));
  chk('c0ac8("abc","ab\\0zz",100)',   BigInt(c0ac8(BigInt(SCR + 0),  SCR + 24, 100n)), BigInt(0x63));  // 'c'(0x63)-'z'(0x7a) → -0x17
  const r_null_case = BigInt(c0ac8(BigInt(SCR + 32), SCR + 40, 100n));
  chk("c0ac8(\"abc\",\"\\0\",100) (片方 NUL)", r_null_case, BigInt(0x61));   // 'a'(0x61)-0    // 'c'(0x63) - NUL(0)
  // (注) NUL 語 到達後; 同語位置子差分。
  chk('c0ac8(n=0)', BigInt(c0ac8(BigInt(SCR), SCR + 16, 0n)), 0n);

  /* ---- #7 function_1801c33e0() — heap 状態判定 (linear memory 直読) ---- */
  const c33e0 = mod['_function_1801c33e0'];
  const g64 = (a) => { let v = 0n; for (let i = 7; i >= 0; i--) v = (v << 8n) | BigInt(U8[a + i]); return v; };
  const a1 = g64(VA_BASE + 0x260ce0), b1 = g64(VA_BASE + 0x26c520);
  const exp7 = ((b1) === (a1 | 1n)) ? 1n : 0n;
  chk('c33e0() (lit mem 実値 and 算出から期待値)', BigInt(c33e0()), exp7);

  console.log(`[leaf] bit-exact: OK=${ok} NG=${ng}`);
  process.exit(ng === 0 ? 0 : 1);
}

main().catch(e => { console.error('[leaf][FAIL]', e); process.exit(1); });
