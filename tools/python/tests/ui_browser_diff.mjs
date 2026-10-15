// ui のブラウザ 3 関数 (PY-132 #3013) の差分検査: 同じ呼出し列を JS mock (host/fl_mock.mjs) と C provider (provider/fl_engine.c) に流し、
// 戻り値・エラー code・最後に要求した開閉の分岐 (browserOp: 0 なし・1 切替・2 閉じる・3 開く) が一致することを確認する。
//   node tests/ui_browser_diff.mjs     (前提: provider/build.sh 済み)
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
const op = { mock: () => mock.state.browserOp, wasm: () => wasm.browserOp() };

// 正常系: toggleBrowserNode は '|i' (既定 -1)。値 -1 → 切替 (1)、0 → 閉じる (2)、1 → 開く (3)、他は分岐なし (0)。NOARGS 2 件は None
const ok = [
  ["ui.toggleBrowserNode", []],
  ["ui.toggleBrowserNode", [null]],
  ["ui.toggleBrowserNode", [-1]],
  ["ui.toggleBrowserNode", [0]],
  ["ui.toggleBrowserNode", [7]],
  ["ui.toggleBrowserNode", [1]],
  ["ui.selectBrowserMenuItem", []],
  ["ui.previewBrowserMenuItem", []],
];
// 異常系: 個数の超過・型違い (文字列・小数) は code 5。異常系の呼出しは分岐を変えない
const bad = [
  ["ui.toggleBrowserNode", [0, 1]],
  ["ui.toggleBrowserNode", ["x"]],
  ["ui.toggleBrowserNode", [1.5]],
  ["ui.selectBrowserMenuItem", [1]],
  ["ui.previewBrowserMenuItem", [0]],
];

const diffs = [];
const check = (name, args) => {
  const a = run(mock, name, args);
  const b = run(wasm, name, args);
  const oa = op.mock();
  const ob = op.wasm();
  if (JSON.stringify(a) !== JSON.stringify(b) || oa !== ob) diffs.push({ name, args, mock: a, wasm: b, browserOp: [oa, ob] });
  return a;
};
for (const [name, args] of ok) assert.deepEqual(check(name, args), { ok: null }, `${name}(${args}) は None を返す`);
for (const [name, args] of bad) assert.deepEqual(check(name, args), { code: 5 }, `${name}(${args}) は code 5`);

assert.deepEqual(diffs, [], `ui ブラウザ 差分 ${diffs.length} 件`);
// 最後に成功した toggle は [1] (開く = 3)。異常系の後も分岐は 3 のまま
assert.equal(op.wasm(), 3, "最後の toggle (1) は開く (3)");
assert.equal(op.mock(), 3, "mock も 3");
console.log(JSON.stringify({ ok_calls: ok.length, bad_calls: bad.length, diffs: 0, browserOp: op.wasm(), PASS: true }));
