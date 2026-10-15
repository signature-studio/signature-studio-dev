// arrangement の PE 根拠で実装した 6 関数 (PY-152・#2983) の差分検査: 同じ呼出し列を JS mock (host/fl_mock.mjs) と
// C provider (provider/fl_engine.c) に流し、各呼出しの戻り値・エラー code が一致することを確認する。
//   node tests/arrangement_diff.mjs     (前提: provider/build.sh 済み)
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
  ["arrangement.currentTime", [1]], ["arrangement.currentTime", [true]], ["arrangement.currentTime", [null]],
  ["arrangement.selectionClear", []],
  ["arrangement.selectionSet", [1, 2]], ["arrangement.selectionSet", [1, 2, true, false, 0]],
  ["arrangement.liveSelection", [1, true]], ["arrangement.addAutoTimeMarker", [1, "Marker"]],
  ["arrangement.jumpToMarker", [1]], ["arrangement.jumpToMarker", [-1, true]],
];
// 引数個数違い: mock と C は共に code 5 (Wrong number of parameters)
const arity = [
  ["arrangement.currentTime", []], ["arrangement.currentTime", [1, 2]],
  ["arrangement.selectionClear", [1]],
  ["arrangement.selectionSet", [1]], ["arrangement.selectionSet", [1, 2, 3, 4, 5, 6]],
  ["arrangement.liveSelection", [1]], ["arrangement.addAutoTimeMarker", [1]],
  ["arrangement.jumpToMarker", []], ["arrangement.jumpToMarker", [1, 2, 3]],
];
// 型違い: 整数・bool 以外 (文字列・小数) と、str 引数の None は code 5
const types = [
  ["arrangement.currentTime", ["x"]], ["arrangement.selectionSet", [1, "x"]],
  ["arrangement.liveSelection", [1, 1.5]], ["arrangement.addAutoTimeMarker", [1, 2]],
  ["arrangement.addAutoTimeMarker", [1, null]], ["arrangement.jumpToMarker", ["x"]],
];

const diffs = [];
for (const [name, args] of [...calls, ...arity, ...types]) {
  const a = run(mock, name, args);
  const b = run(wasm, name, args);
  if (JSON.stringify(a) !== JSON.stringify(b)) diffs.push({ name, args, mock: a, wasm: b });
}

assert.deepEqual(diffs, [], `arrangement 差分 ${diffs.length} 件`);
console.log(JSON.stringify({ calls: calls.length + arity.length + types.length, diffs: 0, PASS: true }));
