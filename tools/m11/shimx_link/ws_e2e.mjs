// winstubs 結線 closure (build.sh --ws) の受入 e2e (#223)。
//   node ws_e2e.mjs <m11_sx_*_ws.cjs>        exit 0 = 全 PASS
// 1) closure を boot (m11_boot_enter) して到達点を run_trace.mjs と同じ指標で出す (constructor の winstubs_init(0) が先行)
// 2) G05: lift 側 __asm_cpuid 経由で leaf1.EDX==0x078bfbff / bit15(CMOV)=1 / leaf7.EBX bit5(AVX2)=0
// 3) G03: --wrap 経由の署名チェーン (engine ×2 + host exe) が signer_match=1
// 4) G12: CreateProcessW 成功 0 (試行 1) / WebView2Loader.dll は NULL, GetLastError=126
// 5) wasm の import/export から --wrap 結線 (__wrap_* 12 本が定義済み) を確認
import fs from 'fs';
import path from 'path';

const M11 = path.resolve(new URL('../', import.meta.url).pathname);
const cjs = path.resolve(process.argv[2]);
const m2 = await import(cjs);
const err = [];
const mod = await (m2.default || m2)({ printErr: (s) => err.push(String(s)) });
mod.HEAPU8.set(fs.readFileSync(M11 + '/work/m11_image.bin'), 0);

let fails = 0, probeChecks = 0, totalChecks = 0;
const check = (name, ok, detail) => { totalChecks++; console.log(`${ok ? 'PASS' : 'FAIL'} ${name}  ${detail ?? ''}`); if (!ok) fails++; };
// probe 由来 = sx_ws_probe_* (本 e2e 用の検査口) や wasm バイト列の直接検査で得た証拠で、lift の自然な実行経路ではない。
// 名前に [probe由来] を付け、PASS 件数を「lift が実際に踏んだ証拠」と読み違えないようにする。
const checkProbe = (name, ok, detail) => { probeChecks++; check(`[probe由来] ${name}`, ok, detail); };
const hx = (v) => '0x' + (v >>> 0).toString(16).padStart(8, '0');

// boot (到達点のみ記録。unit 18 の OOB は CAB-231 の既知停止点)
let rc = null, threw = null;
try { rc = mod._m11_boot_enter(0n, 1n); } catch (e) { if (e && e.m11_dllmain_done !== undefined) rc = BigInt(e.m11_dllmain_done); else threw = (e && e.message) || String(e); }
console.log('BOOT ' + JSON.stringify({ boot_stage: mod._m11_boot_stage(), init_count: mod._m11_init_count(), units_run: mod._m11_units_run(), units_total: mod._m11_units_total(), threw, rc: rc === null ? null : String(rc) }));

// 到達点の回帰検査: 下限 (>=) のみ。#236 / #307 が解消して先へ進んでも落ちない (threw の等値比較はしない)
check('BOOT.init_count_ge_18', mod._m11_init_count() >= 18, `init_count=${mod._m11_init_count()} (基準 18)`);
check('BOOT.units_run_ge_17', mod._m11_units_run() >= 17, `units_run=${mod._m11_units_run()}/${mod._m11_units_total()} (基準 17)`);

// boot 由来 (probe 前) の winstubs 呼出: lift IR が実際に winstubs / --wrap に束縛されている証拠
const bootStat = { cpuid: mod._sx_ws_stat(3), verify_trust: mod._sx_ws_stat(0), loadlib_calls: mod._sx_ws_stat(6), loadlib_miss: mod._sx_ws_stat(7), createprocess: mod._sx_ws_stat(4), pump_calls: mod._sx_ws_stat(9), find_window: mod._sx_ws_stat(10), sysmetrics: mod._sx_ws_stat(11), shell_calls: mod._sx_ws_stat(12) };
console.log('BOOT_WS_STATS ' + JSON.stringify(bootStat));
check('G05.boot_cpuid_from_lift', bootStat.cpuid >= 1, `boot 中に lift の __asm_cpuid → winstubs_cpuid が ${bootStat.cpuid} 回`);

// G05 (lift __asm_cpuid → winstubs_cpuid)
const edx = mod._sx_ws_probe_cpuid(1, 3), ebx7 = mod._sx_ws_probe_cpuid(7, 1), ecx1 = mod._sx_ws_probe_cpuid(1, 2);
const l0 = [1, 3, 2].map((r) => mod._sx_ws_probe_cpuid(0, r));
check('G05.leaf1.edx', edx === 0x078bfbff, `edx=${hx(edx)}`);
check('G05.cmov', ((edx >>> 15) & 1) === 1, `cmov=${(edx >>> 15) & 1}`);
check('G05.leaf1.ecx_sse2_profile', ecx1 === 0, `ecx=${hx(ecx1)} (SSE3 以降なし)`);
check('G05.leaf7.avx2', ((ebx7 >>> 5) & 1) === 0, `ebx=${hx(ebx7)} avx2=${(ebx7 >>> 5) & 1}`);
check('G05.leaf0.vendor', l0[0] === 0x756e6547 && l0[1] === 0x49656e69 && l0[2] === 0x6c65746e, 'GenuineIntel');
check('G05.stat_counted', mod._sx_ws_stat(3) === bootStat.cpuid + 6, `winstubs cpuid calls=${mod._sx_ws_stat(3)} (boot ${bootStat.cpuid} + probe 6)`);

// G03 (engine module ×2 + host exe=0)
const s1 = mod._sx_ws_probe_g03(1), s2 = mod._sx_ws_probe_g03(1), s3 = mod._sx_ws_probe_g03(0);
checkProbe('G03.engine_self_1', s1 === 1, `signer_match=${s1}`);
checkProbe('G03.engine_self_2', s2 === 1, `signer_match=${s2}`);
checkProbe('G03.host_exe', s3 === 1, `signer_match=${s3}`);
checkProbe('G03.verify_trust_wrapped', mod._sx_ws_stat(0) === 6, `__wrap_WinVerifyTrust 計数=${mod._sx_ws_stat(0)} (VERIFY+CLOSE ×3)`);

// G12
const g12 = mod._sx_ws_probe_g12();
checkProbe('G12.create_process_success', mod._sx_ws_stat(5) === 0 && (g12 & 1) === 0, `attempts=${mod._sx_ws_stat(4)} success=${mod._sx_ws_stat(5)}`);
checkProbe('G12.webview2_null_126', (g12 & 2) === 0 && (g12 >> 8) === 126, `loaded=${(g12 >> 1) & 1} err=${g12 >> 8}`);
checkProbe('G12.loadlib_blocked', mod._sx_ws_stat(8) >= 1, `blocked=${mod._sx_ws_stat(8)}`);

// --wrap 結線: wasm の function section に __wrap_ 12 本分の実体があること (wrap_list.txt と突合)
const wl = fs.readFileSync(path.join(M11, '../startup/winstubs/wrap_list.txt'), 'utf8').split('\n').filter((l) => l && !l.startsWith('#'));
const wasmBytes = fs.readFileSync(cjs + '.wasm');
const nameSec = Buffer.from(wasmBytes).toString('latin1');
const wrapped = wl.filter((n) => nameSec.includes('__wrap_' + n));
check('WRAP.count', wl.length === 12, `wrap_list.txt=${wl.length} 本`);
checkProbe('WRAP.symbols_in_wasm', wrapped.length === wl.length, `__wrap_* 名が name section に ${wrapped.length}/${wl.length}`);

// loadlib_miss ログ (lift 実機で取得できること = 受入 2)
const miss = [];
for (let i = 0; i < 32; i++) { const p = mod._sx_ws_loadlib_miss(i); if (!p) break; miss.push(mod.UTF8ToString(p)); }
console.log('LOADLIB_MISS ' + JSON.stringify(miss));
checkProbe('LOG.loadlib_miss_available', miss.length >= 1, `${miss.length} 件 (WebView2Loader.dll を含む=${miss.some((m) => /webview2loader/i.test(m))})`);

console.log(`CHECKS total=${totalChecks} probe由来=${probeChecks} 非probe=${totalChecks - probeChecks}`);
console.log(fails ? `RESULT FAIL (${fails})` : 'RESULT PASS');
process.exit(fails ? 1 : 0);
