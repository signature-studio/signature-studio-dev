// ui の状態ゲッター 17 件 (PY-95・#2831 の 9 件、PY-119・#2980 の 6 件、PY-128・#3005 の 2 件) と setter 2 件・getVersion (PY-130・#3007) の差分検査: 同じ呼出し列を JS mock (host/fl_mock.mjs) と
// C provider (provider/fl_engine.c) に流し、各呼出しの戻り値・エラー code が一致することを確認する。
//   node tests/ui_state_diff.mjs     (前提: provider/build.sh 済み)
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

const NOARG = ["ui.isClosing", "ui.getTimeDispMin", "ui.isMetronomeEnabled", "ui.isPrecountEnabled", "ui.isStartOnInputEnabled",
  "ui.isLoopRecEnabled", "ui.getStepEditMode", "ui.isBrowserAutoHide", "ui.getSnapMode",
  "ui.getFocusedFormID", "ui.getFocusedFormCaption", "ui.getFocusedPluginName", "ui.getHintMsg", "ui.isInPopupMenu", "ui.getProgTitle"];
// getHintValue(value, max) (PY-128・#3005): 0 除算・負の値・int32 の折返し・丸め (半分は偶数側) を含む
const hintArgs = [[50, 100], [0, 100], [-1, 100], [1, 3], [-7, 4], [7, -4], [5, 0], [0, 0], [-5, 0], [2147483647, 1], [1000000, 7], [true, 2], [3, false], [1, 8]];
// PY-130 (#3007): setter 2 件は書いた値をすぐ後の getter で読めること (同じ状態を両 engine が共有する)。getVersion は mode の型分岐
const setters = [
  ["ui.setBrowserAutoHide", [1]], ["ui.isBrowserAutoHide", []],
  ["ui.setBrowserAutoHide", [2]], ["ui.isBrowserAutoHide", []],
  ["ui.setBrowserAutoHide", [true]], ["ui.isBrowserAutoHide", []],
  ["ui.setStepEditMode", [1]], ["ui.getStepEditMode", []],
  ["ui.setStepEditMode", [0]], ["ui.getStepEditMode", []],
  ["ui.setTimeDispMin", []], ["ui.getTimeDispMin", []], ["ui.setTimeDispMin", []], ["ui.getTimeDispMin", []],
  ["ui.getVersion", []], ["ui.getVersion", [0]], ["ui.getVersion", [3]], ["ui.getVersion", [4]],
  ["ui.getVersion", [6]], ["ui.getVersion", [7]], ["ui.getVersion", [-1]], ["ui.getVersion", [true]],
  ["ui.getVersion", ["x"]],
];
const calls = [
  ...NOARG.map((name) => [name, []]),
  ["ui.getFocused", [0]], ["ui.getFocused", [true]], ["ui.getFocused", ["x"]],
  ...hintArgs.map((args) => ["ui.getHintValue", args]),
  ...setters,
];
// 引数個数違い (NOARGS の関数に引数を渡す・getFocused の 0 個と 2 個): mock と C は共に code 5 (Wrong number of parameters)
const arity = [
  ...NOARG.map((name) => [name, [1]]),
  ["ui.getFocused", []], ["ui.getFocused", [0, 1]],
  // getHintValue の個数違いと型違い (None・文字列・実数): mock と C は共に code 5 (TypeError)
  ["ui.getHintValue", []], ["ui.getHintValue", [1]], ["ui.getHintValue", [1, 2, 3]],
  ["ui.getHintValue", ["x", 1]], ["ui.getHintValue", [1.5, 2]], ["ui.getHintValue", [1, null]], ["ui.getHintValue", [null, 2]],
  ["ui.setBrowserAutoHide", []], ["ui.setBrowserAutoHide", [1, 2]], ["ui.setStepEditMode", []], ["ui.setStepEditMode", [1, 2]],
  ["ui.getVersion", [0, 1]], ["ui.getVersion", [1, 2]], ["ui.setTimeDispMin", [1]],
];

const diffs = [];
for (const [name, args] of [...calls, ...arity]) {
  const a = run(mock, name, args);
  const b = run(wasm, name, args);
  if (JSON.stringify(a) !== JSON.stringify(b)) diffs.push({ name, args, mock: a, wasm: b });
}

assert.deepEqual(diffs, [], `ui 状態ゲッター差分 ${diffs.length} 件`);
console.log(JSON.stringify({ calls: calls.length + arity.length, diffs: 0, PASS: true }));
