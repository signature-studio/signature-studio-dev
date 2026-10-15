// ui 送出キー 15 関数 (PE 0xfdd2c0 → 0x8186a0 → SendInput。REPORT_PY140) の差分検査: 同じ呼出し列を JS mock (host/fl_mock.mjs) と C provider (provider/fl_engine.c) に流し、
// 戻り値・エラー code・送出キーの記録 (VK・修飾・回数) が一致することを確認する。PE の確定値は手で書いた期待値でも固定する。
//   node tests/ui_keys_diff.mjs     (前提: provider/build.sh 済み)
import fs from "node:fs";
import assert from "node:assert/strict";
import { createMockEngine } from "../host/fl_mock.mjs";
import { createWasmEngine } from "../host/fl_provider.mjs";

const root = new URL("../", import.meta.url);
const ids = JSON.parse(fs.readFileSync(new URL("analysis/flapi/flapi_ids.json", root)));
const wasm = await createWasmEngine({ flprovUrl: new URL("dist/flprov.js", root), ids });
const mock = createMockEngine();

const run = (eng, name, args) => {
  eng.keyClear();
  try {
    const v = eng.call(name, args);
    return { ok: v === undefined ? null : v, keys: keysOf(eng) };
  } catch (e) {
    return { code: e.flCode ?? null, keys: keysOf(eng) };
  }
};
const keysOf = (eng) => Array.from({ length: eng.keyN() }, (_, i) => [eng.keyGet(i, 0), eng.keyGet(i, 1), eng.keyGet(i, 2)]);

// PE 期待値 (REPORT_PY140 の表): [VK, 修飾, 回数] の列
const expect = [
  ["ui.up", [3], [[0x26, 0, 3]]],
  ["ui.down", [1], [[0x28, 0, 1]]],
  ["ui.left", [2], [[0x25, 0, 2]]],
  ["ui.right", [1], [[0x27, 0, 1]]],
  ["ui.cut", [], [[0x58, 4, 1]]],
  ["ui.copy", [], [[0x43, 4, 1]]],
  ["ui.paste", [], [[0x56, 4, 1]]],
  ["ui.insert", [], [[0x2d, 0, 1]]],
  ["ui.delete", [], [[0x2e, 0, 1]]],
  ["ui.enter", [], [[0x0d, 0, 1]]],
  ["ui.escape", [], [[0x1b, 0, 1]]],
  ["ui.yes", [], [[0x59, 0, 1]]],
  ["ui.no", [], [[0x4e, 0, 1]]],
  ["ui.nextWindow", [], [[0x09, 0, 1]]],
  ["ui.selectWindow", [1], [[0x09, 0, 1]]],
  ["ui.selectWindow", [0], [[0x09, 1, 1]]],
  ["ui.selectWindow", [-1], [[0x09, 1, 1]]],
];
// 回数 arg <= 0 の矢印は送出 leaf で r8d <= 0 のため 0x8186a0 が何もしない (REPORT_PY140)。キー 0 件
const zeroCount = [["ui.up", [0]], ["ui.down", [-2]], ["ui.left", [0]], ["ui.right", [0]]];

const diffs = [];
let calls = 0;
const check = (name, args, want) => {
  calls++;
  const a = run(mock, name, args);
  const b = run(wasm, name, args);
  if (JSON.stringify(a) !== JSON.stringify(b)) diffs.push({ name, args, mock: a, wasm: b });
  if (want !== undefined) {
    const got = JSON.stringify(b.keys);
    assert.equal(got, JSON.stringify(want), `${name}(${args}) の送出キーが PE と違う: ${got}`);
  }
};
for (const [name, args, keys] of expect) check(name, args, keys);
for (const [name, args] of zeroCount) check(name, args, []);
// 引数の型違い・個数違いは code 5 (他の関数と同じ)、戻り値は 0 (PY-141 までの仮置き)
check("ui.up", ["x"], undefined);
check("ui.cut", [1], undefined);
check("ui.selectWindow", [], undefined);
check("ui.selectWindow", [1, 2], undefined);
check("ui.selectWindow", [true], undefined);

assert.deepEqual(diffs, [], `ui 送出キー差分 ${diffs.length} 件`);
console.log(JSON.stringify({ calls, diffs: 0, PASS: true }));
