// playlist 確定 8 関数 (REPORT_PY61 §2・PY-62 #2027) の差分検査: 同じ呼出し列を JS mock (host/fl_mock.mjs) と
// C provider (provider/fl_engine.c) に流し、各呼出しの戻り値・エラー code が一致することを確認する。
//   node tests/playlist_diff.mjs     (前提: provider/build.sh 済み)
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
  // 既定値 (範囲内・境界 1 / 500、範囲外 0 / 501)
  ["playlist.getTrackColor", [1]],
  ["playlist.getTrackColor", [500]],
  ["playlist.getTrackColor", [0]],
  ["playlist.getTrackColor", [501]],
  ["playlist.isTrackMuteLock", [1]],
  ["playlist.isTrackMuteLock", [0]],
  ["playlist.getTrackActivityLevelVis", [1]],
  ["playlist.getTrackActivityLevelVis", [501]],
  ["playlist.getLiveLoopMode", [1]],
  ["playlist.getLiveTriggerMode", [500]],
  ["playlist.getLivePosSnap", [2]],
  ["playlist.getLiveTrigSnap", [3]],
  ["playlist.getLiveLoopMode", [-1]],
  // muteTrackLock (表の引数数 1〜2・main #2927): 1 個呼びと value -1 は反転。value 0/1 は設定 (下位 1 byte)。3 個は code 5 (REPORT_PY61 §3)
  ["playlist.muteTrackLock", [1]],
  ["playlist.isTrackMuteLock", [1]],
  ["playlist.muteTrackLock", [1]],
  ["playlist.isTrackMuteLock", [1]],
  ["playlist.muteTrackLock", [500]],
  ["playlist.isTrackMuteLock", [500]],
  ["playlist.isTrackMuteLock", [2]],
  ["playlist.muteTrackLock", [1, 1]],
  ["playlist.muteTrackLock", [1, 0]],
  ["playlist.isTrackMuteLock", [1]],
  // 設定は反転ではない (同じ値の 2 回目も同じ状態)・下位 1 byte (256 → 0、2 → 2)
  ["playlist.muteTrackLock", [2, 1]],
  ["playlist.muteTrackLock", [2, 1]],
  ["playlist.isTrackMuteLock", [2]],
  ["playlist.muteTrackLock", [3, 256]],
  ["playlist.isTrackMuteLock", [3]],
  ["playlist.muteTrackLock", [3, 2]],
  ["playlist.isTrackMuteLock", [3]],
  // 範囲外 index は両者とも code 4 (RANGE)
  ["playlist.muteTrackLock", [0]],
  ["playlist.muteTrackLock", [501]],
  ["playlist.getTrackColor", [-1]],
  // 型違い・引数個数違いは両者とも code 5 (型検査が範囲検査より先)
  ["playlist.muteTrackLock", ["x"]],
  ["playlist.muteTrackLock", [1.5]],
  ["playlist.muteTrackLock", [0, "x"]],
  ["playlist.muteTrackLock", []],
  ["playlist.muteTrackLock", [1, 1, 1]],
  ["playlist.getTrackColor", []],
  ["playlist.getTrackColor", [1, 2]],
  ["playlist.getTrackColor", ["a"]],
  ["playlist.isTrackMuteLock", []],
  ["playlist.getTrackActivityLevelVis", [1, 0]],
  ["playlist.getLiveTrigSnap", ["1"]],
  // setTrackColor は R/B を入替えて 0xffffff で切って格納する (PY-113・REPORT_PY113 §2)。getTrackColor は格納値の R/B を入替え alpha を立てる
  ["playlist.setTrackColor", [3, 0x123456]],
  ["playlist.getTrackColor", [3]],
  ["playlist.setTrackColor", [3, 0xFF0000FF]],
  ["playlist.getTrackColor", [3]],
  ["playlist.getTrackColor", [1]],
];

const diffs = [];
for (const [name, args] of seq) {
  const a = run(mock, name, args);
  const b = run(wasm, name, args);
  if (JSON.stringify(a) !== JSON.stringify(b)) diffs.push({ name, args, mock: a, wasm: b });
}

assert.deepEqual(diffs, [], `playlist 確定 8 関数の差分 ${diffs.length} 件`);
// 往復 get(set(v)) = 0xff000000 | v (v が 0xRRGGBB の範囲)。setter の格納式 (PY-113) の確定値を C と mock の両方で固定する
for (const eng of [mock, wasm]) {
  eng.call("playlist.setTrackColor", [3, 0x123456]);
  assert.equal(eng.call("playlist.getTrackColor", [3]), 0xff123456);
  eng.call("playlist.setTrackColor", [3, 0xff0000ff]);
  assert.equal(eng.call("playlist.getTrackColor", [3]), 0xff0000ff);
}
console.log(JSON.stringify({ calls: seq.length, diffs: 0, PASS: true }));
