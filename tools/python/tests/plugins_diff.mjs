// plugins の値 API 3 関数 (getParamValue / getParamValueString / setParamValue) の差分検査 (PY-228 / #3656)。
// 同じ呼出し列を JS mock (host/fl_mock.mjs) と C provider (provider/fl_engine.c) に流し、戻り値・エラー code が一致することを確認する。
// 対象: 値の所在 (slotIndex -1 は channel、slotIndex >= 0 は mixer track の insert slot)、index・slotIndex・useGlobalIndex の解決、
// 範囲外 (code 4)、空 slot (code 8)、挿入・削除で値が既定に戻ること、channel 追加・削除。
//   node tests/plugins_diff.mjs     (前提: provider/build.sh 済み)
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
const val = (eng, name, args) => {
  const r = run(eng, name, args);
  assert.ok("ok" in r, `${name}(${args}) は code ${r.code}`);
  return r.ok;
};

const seq = [
  // channel (slotIndex -1): 既定値 Cutoff 0.5 / Resonance 0.2 / Gain 0.8
  ["plugins.getParamValueString", [0, 0, -1, 0]],
  ["plugins.getParamValueString", [1, 0]],
  ["plugins.getParamValueString", [2, 2]],
  ["plugins.getParamValue", [1, 0]],
  // 範囲外: paramIndex 3 / -1、channel index 3 / -1 は code 4
  ["plugins.getParamValueString", [3, 0]],
  ["plugins.getParamValueString", [-1, 0]],
  ["plugins.getParamValueString", [0, 3]],
  ["plugins.getParamValueString", [0, -1]],
  // channel の値を書く (index・slotIndex -1・useGlobalIndex の有無)。他 channel には波及しない
  ["plugins.setParamValue", [0.25, 0, 0, -1]],
  ["plugins.getParamValueString", [0, 0, -1]],
  ["plugins.getParamValueString", [0, 1, -1]],
  ["plugins.getParamValue", [0, 0]],
  ["plugins.getParamValueString", [0, 0, -1, 1]],
  ["plugins.setParamValue", [0.125, 1, 2, -1, 0, 1]],
  ["plugins.getParamValueString", [1, 2, -1]],
  ["plugins.setParamValue", [0.5, 3, 0, -1]],
  // mixer track 1 の slot 0 は空: 値の取得・設定とも code 8 (Plugin not valid)
  ["plugins.getParamValueString", [0, 1, 0]],
  ["plugins.getParamValue", [0, 1, 0]],
  ["plugins.setParamValue", [0.75, 0, 1, 0]],
  // slotIndex 範囲外 (10・-2) と track 範囲外 (127) は code 4
  ["plugins.getParamValueString", [0, 1, 10]],
  ["plugins.getParamValueString", [0, 1, -2]],
  ["plugins.getParamValueString", [0, 127, 0]],
  ["plugins.setParamValue", [0.75, 0, 1, 10]],
  // 挿入 (ilmcp.addEffect) で slot が有効になり、既定値が見える
  ["ilmcp.addEffect", ["Control Surface", 1, 0]],
  ["plugins.getParamValueString", [0, 1, 0]],
  ["plugins.getParamValueString", [2, 1, 0]],
  // slot の値を書く。slot の値は channel の値と別 (channel 0 は 25.0 % のまま)
  ["plugins.setParamValue", [0.75, 0, 1, 0]],
  ["plugins.getParamValueString", [0, 1, 0]],
  ["plugins.getParamValue", [0, 1, 0]],
  ["plugins.getParamValueString", [0, 0, -1]],
  ["plugins.getParamValueString", [0, 1, -1]],
  // paramIndex 範囲外は slot 側でも code 4 (有効な slot の上で判定)
  ["plugins.getParamValueString", [3, 1, 0]],
  // 削除 (addEffect の空名) で slot は再び空 (code 8)、再挿入で既定値に戻る
  ["ilmcp.addEffect", ["", 1, 0]],
  ["plugins.getParamValueString", [0, 1, 0]],
  ["ilmcp.addEffect", ["Control Surface", 1, 0]],
  ["plugins.getParamValueString", [0, 1, 0]],
  // channel 追加 (既定値) と削除 (以後の index は範囲外)
  ["ilmcp.addChannel", ["BassDrum"]],
  ["plugins.getParamValueString", [0, 3, -1]],
  ["plugins.setParamValue", [0.375, 2, 3, -1]],
  ["plugins.getParamValueString", [2, 3, -1]],
  ["ilmcp.removeChannel", [3]],
  ["plugins.getParamValueString", [0, 3, -1]],
  // 引数個数と型 (code 5)
  ["plugins.getParamValueString", [0]],
  ["plugins.setParamValue", [0.5, 0]],
  ["plugins.getParamValueString", ["0", 0]],
  // 最後に slot の値を書き直す (期待値の直接検査で使う)
  ["plugins.setParamValue", [0.75, 0, 1, 0]],
];

const diffs = [];
for (const [name, args] of seq) {
  const a = run(mock, name, args);
  const b = run(wasm, name, args);
  if (JSON.stringify(a) !== JSON.stringify(b)) diffs.push({ name, args, mock: a, wasm: b });
}
assert.deepEqual(diffs, [], `plugins 差分 ${diffs.length} 件`);

// 期待値の直接検査 (差分 0 だけでは両方が同じに誤る場合を防ぐ)
const str = (eng, p, i, s = -1, u) => val(eng, "plugins.getParamValueString", u === undefined ? [p, i, s] : [p, i, s, u]);
for (const eng of [mock, wasm]) {
  assert.equal(str(eng, 0, 0), "25.0 %", "channel 0 は set 後");
  assert.equal(str(eng, 0, 1), "50.0 %", "channel 1 は既定");
  assert.equal(str(eng, 1, 2), "12.5 %", "useGlobalIndex 付き set・get");
  assert.equal(str(eng, 0, 0, -1, 1), "25.0 %", "useGlobalIndex=1 は identity");
  assert.equal(str(eng, 0, 1, 0), "75.0 %", "slot の値");
  assert.equal(val(eng, "plugins.getParamValue", [0, 1, 0]).v, 0.75);
  assert.equal(str(eng, 0, 0, -1), "25.0 %", "slot の set は channel に波及しない");
}
console.log(JSON.stringify({ calls: seq.length, diffs: 0, PASS: true }));
