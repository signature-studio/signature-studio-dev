// ilmcp 8 関数の差分検査: 同じ呼出し列を JS mock (host/ilmcp.mjs 経由) と C provider (provider/fl_engine.c) に流し、
// 各呼出しの戻り値・エラー code・その後の状態 (チャンネル数 / mixer slot / highlight 名) が一致することを確認する。
//   node tests/ilmcp_diff.mjs     (前提: provider/build.sh 済み)
import fs from "node:fs";
import assert from "node:assert/strict";
import { createMockEngine } from "../host/fl_mock.mjs";
import { createWasmEngine } from "../host/fl_provider.mjs";

const root = new URL("../", import.meta.url);
const ids = JSON.parse(fs.readFileSync(new URL("analysis/flapi/flapi_ids.json", root)));
const wasm = await createWasmEngine({ flprovUrl: new URL("dist/flprov.js", root), ids });
const mock = createMockEngine();

// 結果を比較可能な形に正規化 (成功 = value、失敗 = code)
const run = (eng, name, args) => {
  try {
    const v = eng.call(name, args);
    return { ok: v === undefined ? null : v };
  } catch (e) {
    return { code: e.flCode ?? null };
  }
};

const seq = [
  // browser (戻り値の並び・エラー)
  ["ilmcp.getBrowserNames", ["Plugin database", 0]],
  ["ilmcp.getBrowserNames", ["Plugin database", 1]],
  ["ilmcp.getBrowserNames", ["Plugin database/Generators/Drum", 0]],
  ["ilmcp.getBrowserNames", ["Plugin database/Effects/", 0]],
  ["ilmcp.getBrowserNames", ["/Plugin database\\Effects\\Filter/", 1]],
  ["ilmcp.getBrowserNames", ["Plugin database/Installed", 1]],
  ["ilmcp.getBrowserNames", ["Nowhere", 0]],
  ["ilmcp.getBrowserNames", ["Plugin database/Nope", 1]],
  ["ilmcp.getBrowserNames", ["", 0]],
  ["ilmcp.getBrowserNames", ["   ", 0]],
  // channels / effects
  ["ilmcp.addChannel", ["Fruity Slicer"]],
  ["ilmcp.addChannel", ["Fruity Reeverb 2"]],          // effect は channel rack に入らない
  ["ilmcp.addChannel", ["No Such Plugin"]],
  ["ilmcp.addChannel", ["OTT"]],                       // installed effect は不可
  ["ilmcp.addChannel", ["Fruity Slicer"]],             // 重複追加は許可 (mock 同様)
  ["ilmcp.removeChannel", [4]],
  ["ilmcp.removeChannel", [99]],
  ["ilmcp.addEffect", ["Fruity Reeverb 2", 1, 0]],
  ["ilmcp.addEffect", ["Fruity Reeverb 2", 126, 9]],
  ["ilmcp.addEffect", ["Fruity Slicer", 1, 0]],        // generator は effect スロットに入らない
  ["ilmcp.addEffect", ["Nope", 1, 0]],
  ["ilmcp.addEffect", ["", 1, 0]],                     // スロット消去
  ["ilmcp.addEffect", ["OTT", 2, 3]],                  // installed effect は可
  ["ilmcp.addEffect", ["OTT", 127, 0]],                // mixer 範囲外
  ["ilmcp.addEffect", ["OTT", 2, 10]],                 // slot 範囲外
  // PR script / highlight
  ["ilmcp.storePRScript", ["my_script", "print(1)"]],
  ["ilmcp.storePRScript", ["a/b", "x"]],
  ["ilmcp.storePRScript", ["a:b", "x"]],
  ["ilmcp.storePRScript", ["", "x"]],
  ["ilmcp.runPRScript", ["print(2)"]],
  ["ilmcp.getHighlightNames", []],
  ["ilmcp.showHighlight", ["Piano roll", "Toolbar: Show Piano Roll", "cap", null, false]],
];

const diffs = [];
for (const [name, args] of seq) {
  const a = run(mock, name, args);
  const b = run(wasm, name, args);
  if (JSON.stringify(a) !== JSON.stringify(b)) diffs.push({ name, args, mock: a, wasm: b });
}

// 状態の比較: チャンネル数 (mock: st.channels / wasm: fl_engine_channel_count)
const mockN = mock.state.channels.length;
const wasmN = wasm.channelCount();
if (mockN !== wasmN) diffs.push({ state: "channel count", mock: mockN, wasm: wasmN });
// mixer slot (track 1,2 / slot 0..3)
for (const tr of [1, 2]) for (let s = 0; s < 4; s++) {
  const a = mock.state.mixer[tr].slots[s] ?? "";
  const b = run(wasm, "plugins.getPluginName", [tr, s]).ok ?? "";
  if (a !== b) diffs.push({ state: `slot ${tr}/${s}`, mock: a, wasm: b });
}

assert.deepEqual(diffs, [], `ilmcp 差分 ${diffs.length} 件`);
console.log(JSON.stringify({ calls: seq.length, state_checks: 1 + 8, diffs: 0, PASS: true }));
