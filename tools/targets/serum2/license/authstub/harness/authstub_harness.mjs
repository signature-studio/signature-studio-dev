// SR-2b authstub ハーネスランナー: wasm の実行結果を検証する。
// 使い方: node authstub_harness.mjs <h_all.js> [--report <out.json>]
import { createRequire } from 'module';
import fs from 'fs';

const jsPath = process.argv[2] || 'h_all.js';
const reportPath = (() => {
  const i = process.argv.indexOf('--report');
  return i > 0 ? process.argv[i + 1] : null;
})();

const require = createRequire(import.meta.url);
import path from 'path';
const jsAbs = path.isAbsolute(jsPath) ? jsPath : path.resolve(process.cwd(), jsPath);
const factory = require(jsAbs); // -sMODULARIZE: factory() → Promise<Module>
const Module = await factory();
// emscripten node 出力は require 時に同期初期化される (追加の await 不要)

// bitpack 解析
const flagsPtr = Module._malloc(4);
const B = (v) => BigInt(v); // wasm i64 戻りは BigInt
function ctrlFields(packedB) {
  const p = B(packedB);
  const f = (lo, w) => Number((p >> BigInt(lo)) & ((1n << BigInt(w)) - 1n));
  return {
    ret: f(0, 8),
    demoBit: f(8, 8),
    loadEntered: f(16, 1),
    trap: f(17, 1),
    deferredFlags: f(20, 32) >>> 0, // bit20..51
  };
}
function dspFields(packedB) {
  const p = B(packedB);
  const f = (lo, w) => Number((p >> BigInt(lo)) & ((1n << BigInt(w)) - 1n));
  return {
    ret: f(0, 8),
    dialogEntered: f(8, 1),
    restoreEntered: f(9, 1),
    trap: f(10, 1),
  };
}

const results = [];
let failed = 0;
function check(name, cond, detail) {
  results.push({ name, ok: !!cond, detail });
  if (!cond) failed++;
  console.log(`  [${cond ? 'OK' : 'FAIL'}] ${name}${detail ? ' — ' + detail : ''}`);
}

console.log('== controller setState (SerumController::setState 0x1800c2b50) ==');
// marker = FUN_18007b280 の戻り (host state に書かれた demo マーカ値)。
//   1 = licensed として保存された state / 0 = demo として保存された state。
// productVersion は空文字 ("") を返す mock なので、pre では version 比較 ("" < "2.0.20") が
// 常に成立し bit=1 (demo) に落ちる — これも pre の実挙動としてそのまま検証する。
for (const marker of [1, 0]) {
  const pre = ctrlFields(Module._authstub_ctrl_case(1, marker, 1, flagsPtr));
  const post = ctrlFields(Module._authstub_ctrl_case(0, marker, 1, flagsPtr));
  check(`pre  (marker=${marker}): demo bit == 1 (未 patch: marker 0 なら即 demo, 1 でも version<2.0.20 で demo)`,
    pre.demoBit === 1, `bit=${pre.demoBit} ret=${pre.ret} load=${pre.loadEntered}`);
  check(`pre  (marker=${marker}): 0x800010 通知が発火 (deferred flags)`,
    pre.deferredFlags === 0x800010, `flags=0x${pre.deferredFlags.toString(16)}`);
  check(`post (marker=${marker}): demo bit == 0 (常時) [N2a]`,
    post.demoBit === 0, `bit=${post.demoBit} ret=${post.ret}`);
  check(`post (marker=${marker}): 0x800010 通知なし [N2b]`,
    post.deferredFlags === 0, `flags=0x${post.deferredFlags.toString(16)}`);
  check(`post (marker=${marker}): 状態ロード (FUN_1800c3080) は実行される`,
    post.loadEntered === 1, '');
  check(`post (marker=${marker}): トラップなし・kResultTrue`,
    post.trap === 0 && post.ret === 0, `ret=${post.ret}`);
}

console.log('== DSP setState (SerumDSP::setState 0x18004fad0) ==');
// found=1: host state に demoVersion キーがある (demo として保存された)。
//   patch 前はダイアログ + 復元打ち切り。patch 後は無視して復元続行。
for (const [found, version] of [[1, 2.0], [0, 2.0], [1, 12.0]]) {
  const r = dspFields(Module._authstub_dsp_case(found, Math.round(version * 10)));
  const tag = `found=${found} ver=${version}`;
  check(`${tag}: ダイアログ (FUN_1800501c0) 非実行 [N1]`, r.dialogEntered === 0,
    `ret=${r.ret} dialog=${r.dialogEntered}`);
  if (version >= 0 && version <= 11.00001) {
    check(`${tag}: 復元 (FUN_1800506b0) 実行`, r.restoreEntered === 1, '');
    check(`${tag}: 戻り値 kResultTrue(0)`, r.ret === 0, '');
  } else {
    check(`${tag}: version 範囲外 → 復元せず範囲外 path`, r.restoreEntered === 0, '');
  }
  check(`${tag}: トラップなし`, r.trap === 0, '');
}

console.log(`== 結果: ${results.length - failed}/${results.length} PASS ==`);
if (reportPath) {
  fs.writeFileSync(reportPath, JSON.stringify({ results, failed }, null, 1));
}
process.exit(failed ? 1 : 0);
