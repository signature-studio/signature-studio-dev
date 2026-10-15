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
  // PY-125 (#3001): 戻り値 None。dumpScoreLog は time (必須 int) と silent (任意 int)
  ["general.clearLog", []], ["general.dumpScoreLog", [0]], ["general.dumpScoreLog", [-7, 1]],
];
// 引数個数違い (NOARGS の関数に引数を渡す): mock と C は共に code 5 (Wrong number of parameters)
const arity = [
  ["general.getChangedFlag", [1]], ["general.getUseMetronome", [0]],
  ["general.getPrecount", [1]], ["general.getRecPPQ", [0]],
  ["general.safeToEdit", [1]], ["general.getProjectTitle", [0]],
  // PY-125: 個数違い・型違い (code 5)
  ["general.clearLog", [1]], ["general.dumpScoreLog", []], ["general.dumpScoreLog", [0, 1, 2]],
  ["general.dumpScoreLog", ["x"]],
  ["general.setRecPPQ", [24]], ["general.setRecPPQ", [960]], ["general.setRecPPQ", [23]], ["general.setRecPPQ", [961]],
  ["general.setNumerator", [1]], ["general.setNumerator", [16]], ["general.setNumerator", [0]], ["general.setNumerator", [17]],
  ["general.setDenominator", [2]], ["general.setDenominator", [16]], ["general.setDenominator", [1]], ["general.setDenominator", [17]],
  ["general.setUndoHistoryPos", [0]], ["general.setUndoHistoryPos", [-5]], ["general.setUndoHistoryCount", [3]], ["general.setUndoHistoryLast", [7]],
];

const diffs = [];
for (const [name, args] of [...calls, ...arity]) {
  const a = run(mock, name, args);
  const b = run(wasm, name, args);
  if (JSON.stringify(a) !== JSON.stringify(b)) diffs.push({ name, args, mock: a, wasm: b });
}

assert.deepEqual(diffs, [], `general 差分 ${diffs.length} 件`);
console.log(JSON.stringify({ calls: calls.length + arity.length, diffs: 0, PASS: true }));
