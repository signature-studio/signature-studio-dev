// channels / playlist 状態の差分検査: 同じ呼出し列を JS mock (host/fl_mock.mjs) と C provider (provider/fl_engine.c) に流し、
// 各呼出しの戻り値・エラー code と、呼出し後の状態 (channels.getChannelName 等の読出し) が一致することを確認する。
//   node tests/channels_diff.mjs     (前提: provider/build.sh 済み)
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
  ["channels.channelCount", []],
  ["channels.getChannelName", [0]],
  ["channels.getChannelName", [2]],
  ["channels.getChannelName", [3]],
  ["channels.setChannelName", [1, "Clap"]],
  ["channels.getChannelName", [1]],
  ["channels.isChannelSelected", [0]],
  ["channels.selectChannel", [1, true]],
  ["channels.isChannelSelected", [1]],
  ["channels.selectChannel", [1]],
  ["channels.isChannelSelected", [1]],
  ["channels.deselectAll", []],
  ["channels.isChannelSelected", [0]],
  ["channels.selectAll", []],
  ["channels.isChannelSelected", [0]],
  ["channels.isChannelSelected", [1]],
  ["channels.isChannelSelected", [2]],
  ["channels.deselectAll", []],
  ["channels.muteChannel", [0, true]],
  ["channels.muteChannel", [0]],
  ["channels.soloChannel", [2]],
  ["channels.getChannelVolume", [0, 0]],
  ["channels.getChannelVolume", [0, 1]],
  ["channels.setChannelVolume", [0, 0.5]],
  ["channels.getChannelVolume", [0, 0]],
  ["channels.getChannelPan", [2]],
  ["channels.setChannelPan", [2, -0.5]],
  ["channels.getChannelPan", [2]],
  ["channels.setChannelColor", [1, 0x123456]],
  ["channels.getTargetFxTrack", [0]],
  ["channels.setTargetFxTrack", [0, 5]],
  ["channels.getTargetFxTrack", [0]],
  ["channels.setGridBit", [0, 3, true]],
  ["channels.setGridBit", [0, 3, false]],
  ["channels.setGridBit", [0, 63, 1]],
  ["channels.fillEachNSteps", [0, 4, 1, 0, 0]],
  ["channels.fillEachNSteps", [1, 8, -3, 0, 0]],
  ["channels.fillEachNSteps", [1, 0]],
  ["channels.quickQuantize", [0]],
  ["channels.showEditor", [0]],
  ["channels.selectedChannel", [0, 0, 0]],
  ["channels.selectedChannel", [0, 2, 0]],
  ["channels.getChannelName", [-1]],
  ["channels.getChannelName", ["0"]],
  ["channels.getChannelName"],
  ["channels.setChannelName", [0, 5]],
  ["channels.setGridBit", [0, 64, 1]],
  ["channels.setGridBit", [0, -1, 1]],
  ["playlist.trackCount", []],
  ["playlist.getTrackName", [1]],
  ["playlist.getTrackName", [500]],
  ["playlist.getTrackName", [501]],
  ["playlist.getTrackName", [0]],
  ["playlist.setTrackName", [3, "Bass"]],
  ["playlist.getTrackName", [3]],
  ["playlist.setTrackColor", [3, 0xABCDEF]],
  ["playlist.setTrackName", [0, "x"]],
  ["playlist.setTrackColor", [501, 1]],
];

const diffs = [];
for (const [name, args] of seq) {
  const a = run(mock, name, args);
  const b = run(wasm, name, args);
  if (JSON.stringify(a) !== JSON.stringify(b)) diffs.push({ name, args, mock: a, wasm: b });
}

assert.deepEqual(diffs, [], `channels/playlist 差分 ${diffs.length} 件`);
console.log(JSON.stringify({ calls: seq.length, diffs: 0, PASS: true }));
