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
  // PY-135 (#3022): blank は isBlanked (scr+0x1d0) を書き、真→偽の解除で activeCounter を scr+0x1dc (仮置き 0) から戻す
  ["screen.blank", [1, 0]], ["screen.isBlanked", []], ["screen.blank", [1, 5]], ["screen.isBlanked", []],
  ["screen.setScreenActiveCounter", [7]], ["screen.blank", [0, 0]], ["screen.isBlanked", []], ["screen.getScreenActiveCounter", []],
  ["screen.blank", [2, 0]], ["screen.isBlanked", []],
  // 描画・メーター系 6 件は状態を持たず None を返す
  ["screen.fillRect", [0, 0, 10, 10, 255]], ["screen.drawRect", [1, 2, 3, 4, 5]], ["screen.eraseRect", [1, 2, 3, 4]],
  ["screen.addMeter", [0, 1, 2, 3]], ["screen.addMeter", [0, 1, 2, 3, 4]], ["screen.displayBar", [0, 1, "bar", 0.5, 3]],
  ["screen.drawText", [0, "txt", 1, 2, 3, 4]], ["screen.drawText", [0, "txt", 1, 2, 3, true]],
  // #5328: addTextLine は scr 未生成では副作用なし (PE 0xd7ac54 で呼出し自体を飛ばす)。init 後は activeCounter を scr+0x1dc から戻し unBlank を真にする
  ["screen.addTextLine", ["a", 1, 2, 3, 4]], ["screen.isUnBlank", []],
  ["screen.init", [0, 0, 0, 0, 0, 0]], ["screen.setScreenActiveCounter", [9]], ["screen.unBlank", [0]],
  ["screen.addTextLine", ["a", 1, 2, 3, 4]], ["screen.isUnBlank", []], ["screen.getScreenActiveCounter", []],
  ["screen.addTextLine", ["a", 1, 2, 3, 4, 5]], ["screen.addTextLine", ["b", true, 2, 3, 4]],
];
// 引数個数違い: mock と C は共に code 5 (Wrong number of parameters)
const arity = [
  ["screen.isBlanked", [1]], ["screen.getScreenActiveCounter", [0]],
  ["screen.unBlank", []], ["screen.setScreenActiveCounter", []],
  ["screen.fillRect", [1, 2, 3, 4]], ["screen.drawRect", [1, 2, 3, 4, 5, 6]], ["screen.eraseRect", [1, 2, 3, 4, 5]],
  ["screen.addMeter", [1, 2, 3]], ["screen.addMeter", [1, 2, 3, 4, 5, 6]], ["screen.displayBar", [0, 1, "x", 0.5]],
  ["screen.drawText", [1, "a", 1, 2, 3]], ["screen.blank", [1]],
];
// 引数の型違い (C の fl_a_int / type_ok と同じ): bool は int として受理 (true → 1)、float と str は code 5 で状態を変えない。
// 結果が状態に依存するので、初期状態の新しいエンジン 2 つで順に流し、期待値 (上の表) も直接確かめる
const typed = [
  [["screen.unBlank", [true]], { ok: null }], [["screen.isUnBlank", []], { ok: true }],
  [["screen.unBlank", [1.5]], { code: 5 }], [["screen.unBlank", ["1"]], { code: 5 }], [["screen.isUnBlank", []], { ok: true }],
  [["screen.setScreenActiveCounter", [1.5]], { code: 5 }], [["screen.setScreenActiveCounter", ["1"]], { code: 5 }],
  [["screen.getScreenActiveCounter", []], { ok: 0 }],
  [["screen.setScreenActiveCounter", [true]], { ok: null }], [["screen.getScreenActiveCounter", []], { ok: 1 }],
  [["screen.unBlank", [false]], { ok: null }], [["screen.isUnBlank", []], { ok: false }],
  // PY-135: 描画系の型違い (i は int・bool のみ、s は str のみ、d は int・bool・float)。None は既定値扱い
  [["screen.fillRect", [1, 2, 3, 4, 1.5]], { code: 5 }], [["screen.fillRect", ["1", 2, 3, 4, 5]], { code: 5 }],
  [["screen.fillRect", [1, 2, 3, 4, 5]], { ok: null }], [["screen.addMeter", [0, 1, 2, 3, "4"]], { code: 5 }],
  [["screen.displayBar", [0, 1, 2, 0.5, 3]], { code: 5 }], [["screen.displayBar", [0, 1, "x", "y", 3]], { code: 5 }],
  [["screen.displayBar", [0, 1, "x", 1, 3]], { ok: null }], [["screen.drawText", [0, 1, 1, 2, 3, 4]], { code: 5 }],
  [["screen.drawText", [0, "t", 1, 2, 3, 4.5]], { code: 5 }], [["screen.drawText", [0, "t", 1, 2, 3, 4]], { ok: null }],
  [["screen.blank", [1.5, 0]], { code: 5 }], [["screen.blank", ["1", 0]], { code: 5 }],
  [["screen.blank", [true, 0]], { ok: null }], [["screen.isBlanked", []], { ok: true }],
  // PY-135 (#3022 round 1): addMeter の成功経路 (rc>0・scr≠0) は PE 0xd7d9e0 で isUnBlank を真にし、activeCounter を scr+0x1dc (仮置き 0) にする。解析失敗 (rc≤0) は状態を変えない
  [["screen.setScreenActiveCounter", [8]], { ok: null }], [["screen.getScreenActiveCounter", []], { ok: 9 }], [["screen.isUnBlank", []], { ok: false }],
  [["screen.addMeter", [0, 1, 2, 3]], { ok: null }], [["screen.isUnBlank", []], { ok: true }], [["screen.getScreenActiveCounter", []], { ok: 0 }],
  [["screen.unBlank", [0]], { ok: null }], [["screen.setScreenActiveCounter", [5]], { ok: null }],
  [["screen.addMeter", [0, 1, 2, "3"]], { code: 5 }], [["screen.addMeter", [0, 1, 2, 3, 4, 5]], { code: 5 }],
  // #5328: addTextLine は s (str) と i (int・bool) の型違いを code 5 で返し、状態を変えない
  [["screen.addTextLine", [1, 2, 3, 4, 5]], { code: 5 }], [["screen.addTextLine", ["a", 1.5, 2, 3, 4]], { code: 5 }],
  [["screen.addTextLine", ["a", 1, 2, 3, 4]], { ok: null }], [["screen.isUnBlank", []], { ok: false }],
  [["screen.isUnBlank", []], { ok: false }], [["screen.getScreenActiveCounter", []], { ok: 5 }],
  [["screen.addMeter", [0, 1, 2, 3, 4]], { ok: null }], [["screen.isUnBlank", []], { ok: true }], [["screen.getScreenActiveCounter", []], { ok: 0 }],
];

const diffs = [];
for (const [name, args] of [...seq, ...arity]) {
  const a = run(mock, name, args);
  const b = run(wasm, name, args);
  if (JSON.stringify(a) !== JSON.stringify(b)) diffs.push({ name, args, mock: a, wasm: b });
}

const mock2 = createMockEngine();
const wasm2 = await createWasmEngine({ flprovUrl: new URL("dist/flprov.js", root), ids });
const expectDiffs = [];
for (const [[name, args], want] of typed) {
  const a = run(mock2, name, args);
  const b = run(wasm2, name, args);
  if (JSON.stringify(a) !== JSON.stringify(want) || JSON.stringify(b) !== JSON.stringify(want)) expectDiffs.push({ name, args, want, mock: a, wasm: b });
}

assert.deepEqual(diffs, [], `screen 差分 ${diffs.length} 件`);
assert.deepEqual(expectDiffs, [], `screen 型違い 期待値と不一致 ${expectDiffs.length} 件`);
console.log(JSON.stringify({ calls: seq.length + arity.length + typed.length, diffs: 0, PASS: true }));
