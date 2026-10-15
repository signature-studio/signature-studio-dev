// 項目書換え規則 (PE 0x130f3d0・param 0..8) の差分検査: 同じ入力を JS mock (host/fl_mock.mjs) と C provider (provider/fl_engine.c) に流し、結果が一致することを確認する。
// PE 実測の規則の要点 (字段の clamp・delta・param 8 の代入) は手で計算した値でも固定する。
//   node tests/step_item_diff.mjs     (前提: provider/build.sh 済み)
import fs from "node:fs";
import assert from "node:assert/strict";
import { createMockEngine } from "../host/fl_mock.mjs";
import { createWasmEngine } from "../host/fl_provider.mjs";

const root = new URL("../", import.meta.url);
const ids = JSON.parse(fs.readFileSync(new URL("analysis/flapi/flapi_ids.json", root)));
const wasm = await createWasmEngine({ flprovUrl: new URL("dist/flprov.js", root), ids });
const mock = createMockEngine();

// 規則の要点 (PE 実測と一致する手計算): param 3 は [0, 0xf0] に clamp / param 8 は value の低 8 bit / param 1 は先頭項目との差分を加算
const spot = [
  [mock.stepItemProbe(3, 300, 0, 0), 0xf0],
  [mock.stepItemProbe(8, -1, 0, 0), 0xff],
  [mock.stepItemProbe(0, 200, 0, 0), 0x83],
  [mock.stepItemProbe(1, 15, 10, 20), 25],
  [mock.stepItemProbe(9, 5, 7, 7), 0],
];
for (const [got, want] of spot) assert.equal(got, want);

const params = [-1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9];
const values = [-300, -1, 0, 1, 50, 127, 128, 200, 255, 256, 300];
const seeds = [-5, 0, 10, 128, 131, 200, 255];
const diffs = [];
let calls = 0;
for (const prm of params) for (const v of values) for (const s0 of seeds) for (const s1 of seeds) {
  calls++;
  const a = mock.stepItemProbe(prm, v, s0, s1);
  const b = wasm.stepItemProbe(prm, v, s0, s1);
  if (a !== b) diffs.push({ prm, v, s0, s1, mock: a, wasm: b });
}
assert.deepEqual(diffs, [], `step item 差分 ${diffs.length} 件`);
console.log(JSON.stringify({ calls, spot: spot.length, diffs: 0, PASS: true }));
