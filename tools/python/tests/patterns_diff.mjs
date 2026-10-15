// patterns の数え・選択系 4 件 (PY-179・#3271) の差分検査: 同じ呼出し列を JS mock (host/fl_mock.mjs) と
// C provider (provider/fl_engine.c) に流し、各呼出しの戻り値・エラー code が一致することを確認する。
// 値は PE 静的状態からの仮置き (REPORT_PY179)。索引は isPatternDefault のみ [1, 999] (PE: cmp 1 / cmp 0x3e7)。
//   node tests/patterns_diff.mjs     (前提: provider/build.sh 済み)
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

const calls = [
  ["patterns.patternCount", []], ["patterns.patternNumber", []],
  ["patterns.isPatternDefault", [1]], ["patterns.isPatternDefault", [999]],
  ["patterns.isPatternDefault", [0]], ["patterns.isPatternDefault", [1000]], ["patterns.isPatternDefault", [-1]],
  ["patterns.isPatternDefault", [true]], ["patterns.isPatternDefault", [null]],
  ["patterns.isPatternSelected", [0]], ["patterns.isPatternSelected", [1]], ["patterns.isPatternSelected", [-1]],
  ["patterns.isPatternSelected", [999]], ["patterns.isPatternSelected", [true]], ["patterns.isPatternSelected", [null]],
];
// 引数個数違い: mock と C は共に code 5
const arity = [
  ["patterns.patternCount", [1]], ["patterns.patternNumber", [0]],
  ["patterns.isPatternDefault", []], ["patterns.isPatternDefault", [1, 2]],
  ["patterns.isPatternSelected", []], ["patterns.isPatternSelected", [0, 1]],
];
// 型違い (整数・bool 以外): code 5
const types = [
  ["patterns.isPatternDefault", ["x"]], ["patterns.isPatternDefault", [1.5]],
  ["patterns.isPatternSelected", ["x"]], ["patterns.isPatternSelected", [1.5]],
];

const diffs = [];
for (const [name, args] of [...calls, ...arity, ...types]) {
  const a = run(mock, name, args);
  const b = run(wasm, name, args);
  if (JSON.stringify(a) !== JSON.stringify(b)) diffs.push({ name, args, mock: a, wasm: b });
}
assert.deepEqual(diffs, [], `patterns 数え・選択系 差分 ${diffs.length} 件`);
// 仮置きの値と範囲の確認 (C 側)
assert.deepEqual(run(wasm, "patterns.patternCount", []), { ok: 999 });
assert.deepEqual(run(wasm, "patterns.patternNumber", []), { ok: 1 });
assert.deepEqual(run(wasm, "patterns.isPatternDefault", [1]), { ok: false });
assert.deepEqual(run(wasm, "patterns.isPatternDefault", [999]), { ok: false });
for (const i of [0, 1000, -1]) assert.deepEqual(run(wasm, "patterns.isPatternDefault", [i]), { code: 4 }, `isPatternDefault(${i}) は範囲外 (code 4)`);
assert.deepEqual(run(wasm, "patterns.isPatternSelected", [0]), { ok: false });
assert.deepEqual(run(wasm, "patterns.isPatternSelected", [1000]), { ok: false }, "isPatternSelected は範囲検査なし");

console.log(JSON.stringify({ calls: calls.length + arity.length + types.length, diffs: 0, PASS: true }));
