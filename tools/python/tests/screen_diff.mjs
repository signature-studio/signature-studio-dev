// screen 状態の 5 関数 (PY-121・#2985) の差分検査: 同じ呼出し列を JS mock (host/fl_mock.mjs) と
// C provider (provider/fl_engine.c) に流し、各呼出しの戻り値・エラー code が一致することを確認する。状態を持つので順序どおりに流す。
//   node tests/screen_diff.mjs     (前提: provider/build.sh 済み)
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

// 順序どおりの呼出し列 (状態の遷移を含む)。int32 の折返し (2147483647 + 1) も含める
const seq = [
  ["screen.isBlanked", []], ["screen.isUnBlank", []], ["screen.getScreenActiveCounter", []],
  ["screen.setScreenActiveCounter", [5]], ["screen.getScreenActiveCounter", []],
  ["screen.setScreenActiveCounter", [-2]], ["screen.getScreenActiveCounter", []],
  ["screen.setScreenActiveCounter", [2147483647]], ["screen.setScreenActiveCounter", [1]], ["screen.getScreenActiveCounter", []],
  ["screen.unBlank", [1]], ["screen.isUnBlank", []],
  ["screen.unBlank", [0]], ["screen.isUnBlank", []],
  ["screen.unBlank", [2]], ["screen.isUnBlank", []],
];
// 引数個数違い: mock と C は共に code 5 (Wrong number of parameters)
const arity = [
  ["screen.isBlanked", [1]], ["screen.getScreenActiveCounter", [0]],
  ["screen.unBlank", []], ["screen.setScreenActiveCounter", []],
];

const diffs = [];
for (const [name, args] of [...seq, ...arity]) {
  const a = run(mock, name, args);
  const b = run(wasm, name, args);
  if (JSON.stringify(a) !== JSON.stringify(b)) diffs.push({ name, args, mock: a, wasm: b });
}

assert.deepEqual(diffs, [], `screen 差分 ${diffs.length} 件`);
console.log(JSON.stringify({ calls: seq.length + arity.length, diffs: 0, PASS: true }));
