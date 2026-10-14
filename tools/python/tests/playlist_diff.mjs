// playlist 系の差分検査 (PY-102 #2883): 同じ呼出し列を JS mock (host/fl_mock.mjs) と C provider (provider/fl_engine.c) に流し、
// 各呼出しの戻り値・エラー code が一致することを確認する。対象は playlist.muteTrackLock (表 np=2・nmin=1)。
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
  ["playlist.trackCount", []],
  // 2 個呼出し (value 指定): 表の np=2 で dispatch を通り、handler が値を読む
  ["playlist.muteTrackLock", [1, 1]],
  ["playlist.muteTrackLock", [1, 0]],
  ["playlist.muteTrackLock", [1, -1]],
  ["playlist.muteTrackLock", [1, 2]],
  ["playlist.muteTrackLock", [1, 256]],
  ["playlist.muteTrackLock", [1, -2]],
  ["playlist.muteTrackLock", [1, true]],
  // 1 個呼出し・value 省略 (None) は既定 -1 (反転)
  ["playlist.muteTrackLock", [1]],
  ["playlist.muteTrackLock", [1, null]],
  ["playlist.muteTrackLock", [500, -1]],
  // 範囲外 index は両者とも code 4 (RANGE)
  ["playlist.muteTrackLock", [0, 1]],
  ["playlist.muteTrackLock", [501, 1]],
  ["playlist.muteTrackLock", [-1, -1]],
  // 引数個数違反 (np=2・nmin=1) と型違い (dispatch が先に見るため index 範囲より優先) は code 5
  ["playlist.muteTrackLock", []],
  ["playlist.muteTrackLock", [1, 1, 1]],
  ["playlist.muteTrackLock", ["1", 1]],
  ["playlist.muteTrackLock", [1, "x"]],
  ["playlist.muteTrackLock", [1, 0.5]],
  ["playlist.muteTrackLock", [501, "x"]],
  // 同じ playlist の隣接 API が壊れていないこと
  ["playlist.getTrackName", [1]],
  ["playlist.setTrackName", [1, "Drums"]],
  ["playlist.getTrackName", [1]],
];

const diffs = [];
for (const [name, args] of seq) {
  const a = run(mock, name, args);
  const b = run(wasm, name, args);
  if (JSON.stringify(a) !== JSON.stringify(b)) diffs.push({ name, args, mock: a, wasm: b });
}
assert.deepEqual(diffs, [], `playlist 差分 ${diffs.length} 件`);

// mock 単体の状態遷移 (C 側は状態を外部に出していないため、意味論の確認は mock だけで行う)
// 0 → 1 (反転) → 0 (明示 0) → 1 (明示 1) → 反転 0 → 2 (下位 1 byte) → 256 (下位 byte 0) → -2 (254) → 反転 0
const m2 = createMockEngine();
const steps = [[1, null, 1], [1, 0, 0], [1, 1, 1], [1, -1, 0], [1, 2, 2], [1, 256, 0], [1, -2, 254], [1, undefined, 0]];
for (const [i, v, want] of steps) {
  if (v === undefined) m2.call("playlist.muteTrackLock", [i]); else m2.call("playlist.muteTrackLock", [i, v]);
  assert.equal(m2.state.playlist[i - 1].lock, want, `mock lock (v=${v})`);
}
assert.equal(m2.state.playlist[1].lock, 0, "他 track は不変");

console.log(JSON.stringify({ calls: seq.length, diffs: 0, mock_state_steps: steps.length, PASS: true }));
