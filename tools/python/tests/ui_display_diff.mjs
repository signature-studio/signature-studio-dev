// ui の表示・メニュー 6 関数 (PY-121 #2982) の差分検査: 同じ呼出し列を JS mock (host/fl_mock.mjs) と C provider (provider/fl_engine.c) に流し、
// 戻り値・エラー code・最後に作用先へ渡した時間引数 (頭打ち後) が一致することを確認する。
//   node tests/ui_display_diff.mjs     (前提: provider/build.sh 済み)
import fs from "node:fs";
import assert from "node:assert/strict";
import { createMockEngine } from "../host/fl_mock.mjs";
import { createWasmEngine } from "../host/fl_provider.mjs";

const root = new URL("../", import.meta.url);
const ids = JSON.parse(fs.readFileSync(new URL("analysis/flapi/flapi_ids.json", root)));
const wasm = await createWasmEngine({ flprovUrl: new URL("dist/flprov.js", root), ids });
const mock = createMockEngine();

const run = (eng, name, args) => {
  try {
    const v = eng.call(name, args);
    return { ok: v === undefined ? null : v };
  } catch (e) {
    return { code: e.flCode ?? null };
  }
};
const time = { mock: () => mock.state.displayTime, wasm: () => wasm.displayTime() };

// 正常系: 引数の個数 (PE の PyArg 書式 'iiiii|i' 等) の範囲内。時間引数は 0x7d0 (2000) で頭打ち、負の値は素通し
const ok = [
  ["ui.crDisplayRect", [0, 0, 10, 10, 100]],
  ["ui.crDisplayRect", [0, 0, 10, 10, 2000]],
  ["ui.crDisplayRect", [0, 0, 10, 10, 2001]],
  ["ui.crDisplayRect", [0, 0, 10, 10, -5, 1]],
  ["ui.miDisplayRect", [0, 8, 100]],
  ["ui.miDisplayRect", [0, 8, 5000, 1]],
  ["ui.miDisplayDockRect", [0, 4, 1, 300]],
  ["ui.miDisplayDockRect", [0, 4, 1, 9000]],
  ["ui.showNotification", [3]],
  ["ui.showNotification", [null]],
  ["ui.closeAllMenu", []],
  ["ui.closeActivePopupMenu", []],
];
// 異常系: 個数の超過・不足、型違い (文字列・小数) は code 5 (Wrong number of parameters or wrong type)
const bad = [
  ["ui.crDisplayRect", [0, 0, 0, 0]],
  ["ui.crDisplayRect", [0, 0, 0, 0, 0, 0, 0]],
  ["ui.crDisplayRect", [0, 0, "a", 0, 0]],
  ["ui.miDisplayRect", [0, 1]],
  ["ui.miDisplayRect", [0, 1, 2, 3, 4]],
  ["ui.miDisplayDockRect", [0, 1, 2]],
  ["ui.miDisplayDockRect", [0, 1, 2.5, 3]],
  ["ui.showNotification", []],
  ["ui.showNotification", ["x"]],
  ["ui.closeAllMenu", [1]],
  ["ui.closeActivePopupMenu", [0]],
];

const diffs = [];
const check = (name, args) => {
  const a = run(mock, name, args);
  const b = run(wasm, name, args);
  const ta = time.mock();
  const tb = time.wasm();
  if (JSON.stringify(a) !== JSON.stringify(b) || ta !== tb) diffs.push({ name, args, mock: a, wasm: b, displayTime: [ta, tb] });
  return a;
};
for (const [name, args] of ok) assert.deepEqual(check(name, args), { ok: null }, `${name}(${args}) は None を返す`);
for (const [name, args] of bad) assert.deepEqual(check(name, args), { code: 5 }, `${name}(${args}) は code 5`);

assert.deepEqual(diffs, [], `ui 表示 差分 ${diffs.length} 件`);
// 最後の正常な時間引数は miDisplayDockRect の 9000 → 頭打ちで 2000。異常系の呼出しは状態を変えない
assert.equal(time.wasm(), 2000, "最後の時間引数は頭打ち後の 2000");
assert.equal(time.mock(), 2000, "mock も 2000");
console.log(JSON.stringify({ ok_calls: ok.length, bad_calls: bad.length, diffs: 0, displayTime: time.wasm(), PASS: true }));
