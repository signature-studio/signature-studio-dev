// ui の picker・エディタ起動 2 関数 (PY-133 #3014) の差分検査: 同じ呼出し列を JS mock (host/fl_mock.mjs) と C provider (provider/fl_engine.c) に流し、
// 戻り値とエラー code が一致することを確認する。作用先は未モデル (戻り None と個数・型の検査だけ)。
//   node tests/ui_editor_diff.mjs     (前提: provider/build.sh 済み)
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

// 正常系: PE の PyArg 書式の範囲内。showPicker は 'i|i' (1..2)、openEventEditor は 'Ii|i' (2..3)。戻り None
const ok = [
  ["ui.showPicker", [0]],
  ["ui.showPicker", [3, 1]],
  ["ui.showPicker", [-1, -1]],
  ["ui.openEventEditor", [0, 0]],
  ["ui.openEventEditor", [7, 2, 1]],
  ["ui.openEventEditor", [4294967296, 1, true]],
];
// 異常系: 個数の超過・不足、型違い (文字列・小数) は code 5 (Wrong number of parameters or wrong type)
const bad = [
  ["ui.showPicker", []],
  ["ui.showPicker", [1, 2, 3]],
  ["ui.showPicker", ["x"]],
  ["ui.showPicker", [1.5]],
  ["ui.openEventEditor", [1]],
  ["ui.openEventEditor", [1, 2, 3, 4]],
  ["ui.openEventEditor", ["x", 0]],
  ["ui.openEventEditor", [1, 2.5]],
];

const diffs = [];
const check = (name, args) => {
  const a = run(mock, name, args);
  const b = run(wasm, name, args);
  if (JSON.stringify(a) !== JSON.stringify(b)) diffs.push({ name, args, mock: a, wasm: b });
  return a;
};
for (const [name, args] of ok) assert.deepEqual(check(name, args), { ok: null }, `${name}(${args}) は None を返す`);
for (const [name, args] of bad) assert.deepEqual(check(name, args), { code: 5 }, `${name}(${args}) は code 5`);

assert.deepEqual(diffs, [], `ui picker・エディタ 差分 ${diffs.length} 件`);
console.log(JSON.stringify({ ok_calls: ok.length, bad_calls: bad.length, diffs: 0, PASS: true }));
