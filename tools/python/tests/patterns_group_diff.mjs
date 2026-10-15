// patterns グループ 2 件 (PY-172・#3219) の差分検査: 同じ呼出し列を JS mock (host/fl_mock.mjs) と
// C provider (provider/fl_engine.c) に流し、各呼出しの戻り値・エラー code が一致することを確認する。
// 未実装の 2 件 (getActivePatternGroup・getPatternsInGroup) は両方で code 2 (Unspecified error) のままであることも確認する。
//   node tests/patterns_group_diff.mjs     (前提: provider/build.sh 済み)
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
  ["patterns.getPatternGroupCount", []],
  ["patterns.getPatternGroupName", [0]], ["patterns.getPatternGroupName", [-1]],
  ["patterns.getPatternGroupName", [999]], ["patterns.getPatternGroupName", [true]],
  ["patterns.getPatternGroupName", [null]],
];
// 引数個数違い: mock と C は共に code 5
const arity = [
  ["patterns.getPatternGroupCount", [1]],
  ["patterns.getPatternGroupName", []], ["patterns.getPatternGroupName", [0, 1]],
];
// 型違い (整数・bool 以外): code 5
const types = [
  ["patterns.getPatternGroupName", ["x"]], ["patterns.getPatternGroupName", [1.5]],
];
// 未実装 (C 側のみ code 2 を確認。mock は未実装関数を例外にしない PoC のため差分の対象外)
const unimpl = [
  ["patterns.getActivePatternGroup", []], ["patterns.getPatternsInGroup", [0]], ["patterns.getPatternsInGroup", [-1]],
];

const diffs = [];
for (const [name, args] of [...calls, ...arity, ...types]) {
  const a = run(mock, name, args);
  const b = run(wasm, name, args);
  if (JSON.stringify(a) !== JSON.stringify(b)) diffs.push({ name, args, mock: a, wasm: b });
}
assert.deepEqual(diffs, [], `patterns グループ 差分 ${diffs.length} 件`);
for (const [name, args] of unimpl) assert.equal(run(wasm, name, args).code, 2, `${name} は未実装 (code 2) のはず`);
// 件数 0 (仮置き) の確認: 件数 0 では全索引が範囲外 (code 4)
assert.deepEqual(run(wasm, "patterns.getPatternGroupCount", []), { ok: 0 });
for (const i of [0, -1, 999]) assert.deepEqual(run(wasm, "patterns.getPatternGroupName", [i]), { code: 4 }, `getPatternGroupName(${i})`);

console.log(JSON.stringify({ calls: calls.length + arity.length + types.length + unimpl.length, diffs: 0, PASS: true }));
