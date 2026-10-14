// general の状態読出しゲッター (PY-87・#2738) の差分検査: 同じ呼出し列を JS mock (host/fl_mock.mjs) と
// C provider (provider/fl_engine.c) に流し、各呼出しの戻り値・エラー code が一致することを確認する。
//   node tests/general_diff.mjs     (前提: provider/build.sh 済み)
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
  ["general.getChangedFlag", []], ["general.getUseMetronome", []],
  ["general.getPrecount", []], ["general.getRecPPQ", []],
  ["general.getVersion", []],
  // PY-94 (#2830): 状態読出し 7 件 (REPORT_PY94)
  ["general.getUndoHistoryPos", []], ["general.getUndoHistoryCount", []], ["general.getUndoHistoryLast", []],
  ["general.safeToEdit", []], ["general.getProjectTitle", []], ["general.getProjectAuthor", []], ["general.getProjectGenre", []],
];
// 引数個数違い (NOARGS の関数に引数を渡す): mock と C は共に code 5 (Wrong number of parameters)
const arity = [
  ["general.getChangedFlag", [1]], ["general.getUseMetronome", [0]],
  ["general.getPrecount", [1]], ["general.getRecPPQ", [0]],
  ["general.safeToEdit", [1]], ["general.getProjectTitle", [0]],
];

const diffs = [];
for (const [name, args] of [...calls, ...arity]) {
  const a = run(mock, name, args);
  const b = run(wasm, name, args);
  if (JSON.stringify(a) !== JSON.stringify(b)) diffs.push({ name, args, mock: a, wasm: b });
}

assert.deepEqual(diffs, [], `general 差分 ${diffs.length} 件`);
console.log(JSON.stringify({ calls: calls.length + arity.length, diffs: 0, PASS: true }));
