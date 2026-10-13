// ui (ウィンドウ表示状態) の差分検査: 同じ呼出し列を JS mock (host/fl_mock.mjs) と C provider (provider/fl_engine.c) に流し、
// 各呼出しの戻り値・エラー code が一致することを確認する。
//   node tests/ui_diff.mjs     (前提: provider/build.sh 済み)
// 範囲外 index (0..63 の外) は C 側が code 4 (Index out of range) を返し、mock は範囲検査をしない。
// この差は意図的な未解決として分けて報告する (本体の差分 0 とは別扱い)。
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

const inRange = [
  ["ui.getVisible", [0]], ["ui.getVisible", [1]], ["ui.getVisible", [2]],
  ["ui.getVisible", [3]], ["ui.getVisible", [4]], ["ui.getVisible", [5]],
  ["ui.hideWindow", [0]], ["ui.getVisible", [0]],
  ["ui.showWindow", [1]], ["ui.getVisible", [1]],
  ["ui.hideWindow", [4]], ["ui.getVisible", [4]],
  ["ui.showWindow", [5]], ["ui.getVisible", [5]],
  ["ui.hideWindow", [5]], ["ui.getVisible", [5]],
  ["general.getVersion", []],
];
const outOfRange = [
  ["ui.getVisible", [-1]], ["ui.getVisible", [64]], ["ui.showWindow", [100]],
];

const diffs = [];
for (const [name, args] of inRange) {
  const a = run(mock, name, args);
  const b = run(wasm, name, args);
  if (JSON.stringify(a) !== JSON.stringify(b)) diffs.push({ name, args, mock: a, wasm: b });
}

const known = [];
for (const [name, args] of outOfRange) {
  const a = run(mock, name, args);
  const b = run(wasm, name, args);
  if (JSON.stringify(a) !== JSON.stringify(b)) known.push({ name, args, mock: a, wasm: b });
}

assert.deepEqual(diffs, [], `ui 差分 ${diffs.length} 件`);
assert.equal(known.length, outOfRange.length, "範囲外の差分が消えた: 未解決事項の記録を更新する");
console.log(JSON.stringify({ calls: inRange.length, diffs: 0, outOfRangeKnownDiffs: known.length, PASS: true }));
