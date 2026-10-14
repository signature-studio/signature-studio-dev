// mixer 系 18 関数の差分検査: 同じ呼出し列を JS mock (host/fl_mock.mjs) と C provider (provider/fl_engine.c) に流し、
// 各呼出しの戻り値・エラー code が一致することを確認する。mock に定義が無い mixer 関数 (57 件) は対象外。
//   node tests/mixer_diff.mjs     (前提: provider/build.sh 済み)
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

const seq = [
  ["mixer.trackCount", []],
  ["mixer.getTrackName", [0]],
  ["mixer.getTrackName", [1]],
  ["mixer.getTrackName", [1, 16]],
  ["mixer.getTrackName", [126]],
  ["mixer.setTrackName", [1, "Bus A"]],
  ["mixer.getTrackName", [1]],
  ["mixer.getTrackVolume", [0]],
  ["mixer.getTrackVolume", [1, 1]],
  ["mixer.getTrackVolume", [1, 0]],
  ["mixer.setTrackVolume", [1, 0.5]],
  ["mixer.getTrackVolume", [1, 0]],
  ["mixer.getTrackVolume", [1, 1]],
  ["mixer.getTrackPan", [1]],
  ["mixer.setTrackPan", [1, -0.25]],
  ["mixer.getTrackPan", [1]],
  ["mixer.getTrackColor", [0]],
  ["mixer.getTrackColor", [2]],
  ["mixer.setTrackColor", [1, 0x123456]],
  ["mixer.getTrackColor", [1]],
  ["mixer.isTrackSelected", [0]],
  ["mixer.isTrackSelected", [2]],
  ["mixer.muteTrack", [1]],
  ["mixer.muteTrack", [1, 0]],
  ["mixer.muteTrack", [1, 1]],
  ["mixer.muteTrack", [1, -1]],
  ["mixer.soloTrack", [2]],
  ["mixer.soloTrack", [2]],
  ["mixer.focusEditor", [3, -1]],
  ["mixer.getRouteSendActive", [1, 0]],
  ["mixer.getRouteSendActive", [1, 2]],
  ["mixer.getRouteToLevel", [1, 0]],
  ["mixer.getRouteToLevel", [1, 2]],
  ["mixer.setRouteTo", [1, 2, 1]],
  ["mixer.getRouteSendActive", [1, 2]],
  ["mixer.getRouteToLevel", [1, 2]],
  ["mixer.setRouteTo", [1, 2, 0]],
  ["mixer.getRouteSendActive", [1, 2]],
  ["mixer.getRouteToLevel", [1, 2]],
  ["mixer.setRouteToLevel", [1, 0, 0.375]],
  ["mixer.getRouteToLevel", [1, 0]],
  ["mixer.getCurrentTempo", []],
  ["mixer.getCurrentTempo", [0]],
  ["mixer.getCurrentTempo", [1]],
  ["mixer.setCurrentTempo", [140]],
  ["mixer.getCurrentTempo", [1]],
  ["mixer.setCurrentTempo", [150000]],
  ["mixer.getCurrentTempo", [0]],
  ["mixer.getCurrentTempo", [1]],
  // 範囲外 index は両者とも code 4 (RANGE)
  ["mixer.getTrackName", [127]],
  ["mixer.getTrackVolume", [-1, 0]],
  ["mixer.setTrackPan", [200, 0]],
  ["mixer.getTrackColor", [127]],
];

const diffs = [];
for (const [name, args] of seq) {
  const a = run(mock, name, args);
  const b = run(wasm, name, args);
  if (JSON.stringify(a) !== JSON.stringify(b)) diffs.push({ name, args, mock: a, wasm: b });
}

assert.deepEqual(diffs, [], `mixer 差分 ${diffs.length} 件`);
// 既定経路 (未設定 track 2) の確定値 (.bss 0x15f6774 = 0xff636c71・REPORT_PY118)
assert.deepEqual(run(mock, "mixer.getTrackColor", [2]), { ok: 0xff636c71 });
assert.deepEqual(run(wasm, "mixer.getTrackColor", [2]), { ok: 0xff636c71 });
console.log(JSON.stringify({ calls: seq.length, diffs: 0, PASS: true }));
