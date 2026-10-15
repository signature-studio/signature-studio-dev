// 項目列挙 (PE 0x130f200 の note 判定式) の差分検査: 同じ入力を JS mock (host/fl_mock.mjs) と C provider (provider/fl_engine.c) に流し、列挙結果 (note の index 列) が一致することを確認する。
// 判定式の要点は PE の読みから手計算した spot 例で mock 側を固定する。
//   node tests/note_enum_diff.mjs     (前提: provider/build.sh 済み)
import fs from "node:fs";
import assert from "node:assert/strict";
import { createMockEngine } from "../host/fl_mock.mjs";
import { createWasmEngine } from "../host/fl_provider.mjs";

const root = new URL("../", import.meta.url);
const ids = JSON.parse(fs.readFileSync(new URL("analysis/flapi/flapi_ids.json", root)));
const wasm = await createWasmEngine({ flprovUrl: new URL("dist/flprov.js", root), ids });
const mock = createMockEngine();

// 判定式の要点 (PE 実測から手計算)。note = [start, len, ch] を start 昇順の配列で渡す。閾値は step + V
const spot = [
  // V=4・ch=1・step=6 (閾値 10): note 0 は終端 max(1, 3) = 3 で外れ、note 1 は start_q + V - 1 の項で入る (終端 7)。note 2 は ch 違い、note 3 は start_q 8 で外れ、note 4 (start 10) で反復が止まる
  [[[[0, 0, 1], [5, 1, 1], [6, 10, 2], [9, 1, 1], [10, 1, 1], [7, 1, 1]], 1, 6, 4], [1]],
  // 0 方向への切捨て: start -5 の start_q は -4 (floor なら -8 で入ってしまう)。step -5 は [-4, -1) に入らず空
  [[[[-5, 2, 1], [-2, 1, 1]], 1, -5, 4], []],
  // len <= 0 は長さ 1 とみなす (終端 start + 1)。V=1 で step = start のとき len 0・-3 も入る
  [[[[7, 0, 3], [7, -3, 3], [7, 1, 3]], 3, 7, 1], [0, 1, 2]],
];
for (const [[notes, chan, step, V], want] of spot) {
  assert.deepEqual(mock.noteEnumNotes(notes, chan, step, V), want);
}

const seeds = [1, 2, 3, 7, 42, 1234, 99999, -1];
const ns = [0, 1, 3, 12, 40, 256, 300];
const chans = [-1, 0, 1, 2, 3, 4];
const steps = [-20, -5, -1, 0, 1, 7, 50, 333, 999];
const Vs = [-1, 0, 1, 2, 3, 4, 7, 8, 16, 96, 480];
const diffs = [];
let calls = 0, nonempty = 0;
for (const seed of seeds) for (const n of ns) for (const chan of chans) for (const step of steps) for (const V of Vs) {
  calls++;
  const a = mock.noteEnumProbe(seed, n, chan, step, V);
  const b = wasm.noteEnumProbe(seed, n, chan, step, V);
  if (a.length) nonempty++;
  if (JSON.stringify(a) !== JSON.stringify(b)) diffs.push({ seed, n, chan, step, V, mock: a, wasm: b });
}
assert.ok(nonempty > calls / 10, `列挙が非空になる件数が少なすぎる (${nonempty}/${calls})`);
assert.deepEqual(diffs.slice(0, 5), [], `note 列挙の差分 ${diffs.length} 件`);
console.log(JSON.stringify({ calls, nonempty, spot: spot.length, diffs: diffs.length, PASS: diffs.length === 0 }));
