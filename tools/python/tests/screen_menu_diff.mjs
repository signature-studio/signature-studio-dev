// screen 初期化・メニュー系 10 件 (PY-136・#3025) の差分検査: 同じ呼出し列を JS mock (host/fl_mock.mjs) と
// C provider (provider/fl_engine.c) に流し、各呼出しの戻り値・エラー code が一致することを確認する。scr の生成・破棄で状態が変わるので順序どおりに流す。
//   node tests/screen_menu_diff.mjs     (前提: provider/build.sh 済み)
import fs from "node:fs";
import assert from "node:assert/strict";
import { createMockEngine } from "../host/fl_mock.mjs";
import { createWasmEngine } from "../host/fl_provider.mjs";

const root = new URL("../", import.meta.url);
const ids = JSON.parse(fs.readFileSync(new URL("analysis/flapi/flapi_ids.json", root)));
const newWasm = () => createWasmEngine({ flprovUrl: new URL("dist/flprov.js", root), ids });
const wasm = await newWasm();
const mock = createMockEngine();

const run = (eng, name, args) => {
  try {
    const v = eng.call(name, args);
    return { ok: v === undefined ? null : v };
  } catch (e) {
    return { code: e.flCode ?? null };
  }
};

// 順序どおりの呼出し列 (scr の生成・破棄を含む)。scr 未生成 (init 前・deInit 後) は hideMenu・menuShowing・setup が code 2、他は None
const seq = [
  ["screen.menuShowing", []], ["screen.hideMenu", []], ["screen.setup", [1, 2, 3, 4, 5, 6]],
  ["screen.keepDisplayActive", []], ["screen.update", []], ["screen.menuItemClick", []], ["screen.menuNext", []], ["screen.menuPrev", []],
  ["screen.deInit", []], ["screen.init", [1, 2, 3, 4, 5, 6]],
  ["screen.menuShowing", []], ["screen.setup", [7, 8, 9, 10, 11, 12]], ["screen.hideMenu", []], ["screen.menuShowing", []],
  ["screen.keepDisplayActive", []], ["screen.update", []], ["screen.menuItemClick", []], ["screen.menuNext", []], ["screen.menuPrev", []],
  ["screen.init", [0, 0, 0, 0, 0, 0]], ["screen.menuShowing", []],
  ["screen.deInit", []], ["screen.deInit", []], ["screen.menuShowing", []], ["screen.setup", [1, 2, 3, 4, 5, 6]],
];
// 引数個数違い: mock と C は共に code 5 (update は flapi 表どおり 0 引数)
const arity = [
  ["screen.init", [1, 2, 3, 4, 5]], ["screen.setup", [1, 2, 3, 4, 5]], ["screen.deInit", [1]],
  ["screen.menuShowing", [0]], ["screen.update", [1]], ["screen.hideMenu", [0]],
];
// 引数の型違い (fl_dispatch.c type_ok と同じ): bool は int として受理、float と str は code 5 (scr の有無より先に判定)。
// 結果が状態に依存するので、初期状態の新しいエンジン 2 つで順に流し、期待値も直接確かめる
const typed = [
  [["screen.setup", [1, 2, 3, 4, 5, 6]], { code: 2 }], [["screen.setup", [1.5, 2, 3, 4, 5, 6]], { code: 5 }],
  [["screen.init", ["1", 2, 3, 4, 5, 6]], { code: 5 }], [["screen.init", [1, 2, 3, 4, 5, 2.5]], { code: 5 }],
  [["screen.init", [true, 2, 3, 4, 5, 6]], { ok: null }], [["screen.menuShowing", []], { ok: false }],
  [["screen.setup", [true, 2, 3, 4, 5, 6]], { ok: null }],
  [["screen.keepDisplayActive", []], { ok: null }], [["screen.update", []], { ok: null }],
  [["screen.deInit", []], { ok: null }], [["screen.menuShowing", []], { code: 2 }],
];

const diffs = [];
for (const [name, args] of [...seq, ...arity]) {
  const a = run(mock, name, args);
  const b = run(wasm, name, args);
  if (JSON.stringify(a) !== JSON.stringify(b)) diffs.push({ name, args, mock: a, wasm: b });
}

const mock2 = createMockEngine();
const wasm2 = await newWasm();
const expectDiffs = [];
for (const [[name, args], want] of typed) {
  const a = run(mock2, name, args);
  const b = run(wasm2, name, args);
  if (JSON.stringify(a) !== JSON.stringify(want) || JSON.stringify(b) !== JSON.stringify(want)) expectDiffs.push({ name, args, want, mock: a, wasm: b });
}

assert.deepEqual(diffs, [], `screen 初期化・メニュー差分 ${diffs.length} 件`);
assert.deepEqual(expectDiffs, [], `screen 初期化・メニュー型違い 期待値と不一致 ${expectDiffs.length} 件`);
console.log(JSON.stringify({ calls: seq.length + arity.length + typed.length, diffs: 0, PASS: true }));
