// launchMapPages.length (PY-120・#2984) の差分検査: 同じ呼出し列を JS mock (host/fl_mock.mjs) と
// C provider (provider/fl_engine.c) に流し、各呼出しの戻り値・エラー code が一致することを確認する。
//   node tests/launchmap_diff.mjs     (前提: provider/build.sh 済み)
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

// PY-138 (#3029): init (sii)・updateMap (i)・createOverlayMap (iiii) は成功時 None。副作用は未確定のため length は変わらない
const calls = [
  ["launchMapPages.length", []],
  ["launchMapPages.init", ["main", 640, 480]], ["launchMapPages.updateMap", [-1]], ["launchMapPages.updateMap", [3]],
  ["launchMapPages.createOverlayMap", [1, 2, 3, 4]], ["launchMapPages.length", []],
];
// 引数個数違い (NOARGS の関数に引数を渡す): mock と C は共に code 5 (Wrong number of parameters)
// 引数型違い・個数違い (PyArg 書式 sii・i・iiii と同じ): 共に code 5
const arity = [
  ["launchMapPages.length", [1]], ["launchMapPages.length", [0]],
  ["launchMapPages.init", ["main", 640]], ["launchMapPages.init", [1, 640, 480]], ["launchMapPages.init", ["main", 640, 480, 1]],
  ["launchMapPages.updateMap", []], ["launchMapPages.updateMap", ["x"]],
  ["launchMapPages.createOverlayMap", [1, 2, 3]], ["launchMapPages.createOverlayMap", [1, 2, 3, "x"]],
];

const diffs = [];
for (const [name, args] of [...calls, ...arity]) {
  const a = run(mock, name, args);
  const b = run(wasm, name, args);
  if (JSON.stringify(a) !== JSON.stringify(b)) diffs.push({ name, args, mock: a, wasm: b });
}

assert.deepEqual(diffs, [], `launchMapPages 差分 ${diffs.length} 件`);
assert.deepEqual(run(wasm, "launchMapPages.length", []), { ok: 0 });
console.log(JSON.stringify({ calls: calls.length + arity.length, diffs: 0, PASS: true }));
