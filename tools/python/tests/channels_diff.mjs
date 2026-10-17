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
  ["channels.soloChannel", [0, true, false]],
  ["channels.isChannelSelected", [0]],
  ["channels.selectChannel", [1, true]],
  ["channels.isChannelSelected", [1]],
  ["channels.selectChannel", [1]],
  ["channels.isChannelSelected", [1]],
  ["channels.deselectAll", []],
  ["channels.isChannelSelected", [0]],
  ["channels.selectOneChannel", [1]],
  ["channels.isChannelSelected", [0]],
  ["channels.isChannelSelected", [1]],
  ["channels.selectChannel", [0, true]],
  ["channels.selectOneChannel", [2, false]],
  ["channels.isChannelSelected", [0]],
  ["channels.isChannelSelected", [2]],
  ["channels.selectOneChannel", [3]],
  ["channels.selectOneChannel", [-1]],
  ["channels.selectOneChannel", ["1"]],
  ["channels.selectOneChannel"],
  ["channels.selectOneChannel", [0, 1, 2]],
  ["channels.selectOneChannel", [0, "x"]],
  ["channels.selectOneChannel", [0, 1.5]],
  ["channels.selectOneChannel", [0, [1]]],
  ["channels.isChannelSelected", [2]],
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
  ["channels.setChannelPitch", [0, 0.5]],
  ["channels.setChannelPitch", [1, -2.5, 1]],
  ["channels.setChannelPitch", [2, 47.5, 2]],
  ["channels.setChannelPitch", [2, 0.5, 2]],
  ["channels.setChannelPitch", [2, 1e30, 2]],
  ["channels.setChannelPitch", [2, 1, 2, 0, true]],
  ["channels.setChannelPitch", [0, 1, 7]],
  ["channels.setChannelPitch", [0, NaN, 2]],
  ["channels.setChannelPitch", [9, NaN, 2]],
  ["channels.setChannelPitch", [9, 0.5]],
  ["channels.setChannelPitch", [0, "x"]],
  ["channels.setChannelPitch", [0]],
  ["channels.setChannelPitch", [0, 1, 0, 0, 0, 0]],
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
  ["channels.closeGraphEditor", [1]],
  ["channels.closeGraphEditor", [0]],
  ["channels.closeGraphEditor", [-1]],
  ["channels.closeGraphEditor", [true]],
  ["channels.closeGraphEditor", ["1"]],
  ["channels.closeGraphEditor", []],
  ["channels.closeGraphEditor", [1, 2]],
  ["channels.updateGraphEditor", []],
  ["channels.updateGraphEditor", [0]],
  ["channels.showGraphEditor", [true, 0, 0, 1, true]],
  ["channels.showGraphEditor", [true, 0, 0, 1]],
  ["channels.showGraphEditor", [false, 2, 16, 2, false]],
  ["channels.showGraphEditor", [true, 0, 0, 3, true]],
  ["channels.showGraphEditor", [true, 0, 0, -1]],
  ["channels.showGraphEditor", [true, 0, 0, 1.5]],
  ["channels.showGraphEditor", [true, 0, 0, "1"]],
  ["channels.showGraphEditor", [true, 0, 0]],
  ["channels.showGraphEditor", [true, 0, 0, 0, 1, 2]],
  ["channels.showGraphEditor", [true, 0, 0, 0, "x"]],
  ["channels.showCSForm", [0]],
  ["channels.showCSForm", [1, 2, true]],
  ["channels.showCSForm", [3]],
  ["channels.showCSForm", [0, "x"]],
  ["channels.showCSForm", [0, 1, 1.5]],
  ["channels.showCSForm", []],
  ["channels.focusEditor", [0]],
  ["channels.focusEditor", [2, true]],
  ["channels.focusEditor", [3]],
  ["channels.focusEditor", [-1, false]],
  ["channels.focusEditor", [0, 1.5]],
  ["channels.focusEditor", []],
  ["channels.selectedChannel", [0, 0, 0]],
  ["channels.selectedChannel", [0, 2, 0]],
  ["channels.getChannelName", [-1]],
  ["channels.getChannelName", ["0"]],
  ["channels.getChannelName"],
  ["channels.setChannelName", [0, 5]],
  ["channels.setGridBit", [0, 64, 1]],
  ["channels.setGridBit", [0, -1, 1]],
  ["channels.getGridBit", [0, 3]],
  ["channels.getGridBit", [0, 64]],
  ["channels.getGridBit", [0, -1]],
  ["channels.getGridBit", [9, 0]],
  ["channels.getGridBit", [0]],
  ["channels.isGridBitAssigned", [0]],
  ["channels.isGridBitAssigned", [0, true]],
  ["channels.isGridBitAssigned", [9]],
  ["channels.isGridBitAssigned", [-1, 0]],
  ["channels.getGridBitWithLoop", [0, 3]],
  ["channels.getGridBitWithLoop", [0, 64]],
  ["channels.getGridBitWithLoop", [0, -1]],
  ["channels.getGridBitWithLoop", [9, 0]],
  ["channels.getGridBitWithLoop", [0]],
  ["channels.isChannelMuted", [0]],
  ["channels.isChannelMuted", [2]],
  ["channels.isChannelMuted", [7]],
  ["channels.isChannelSolo", [1]],
  ["channels.soloChannel", [1]],
  ["channels.isChannelSolo", [1]],
  ["channels.getChannelColor", [1]],
  ["channels.setChannelColor", [1, 0x010203]],
  ["channels.getChannelColor", [1]],
  ["channels.getChannelColor", [-1]],
  ["channels.channelNumber", []],
  ["channels.channelNumber", [true]],
  ["channels.channelNumber", [false, 0]],
  ["channels.channelNumber", [false, 1]],
  ["channels.channelNumber", [false, 5]],
  ["channels.channelNumber", [false, -2]],
  ["channels.selectChannel", [2, true]],
  ["channels.channelNumber", [false, 1]],
  ["channels.channelNumber", [false, 9]],
  ["channels.deselectAll", []],
  ["channels.channelNumber", [true]],
  ["channels.channelNumber", [false]],
  ["channels.muteChannel", [2]],
  ["channels.isChannelMuted", [2]],
  ["channels.getChannelType", [0]],
  ["channels.getChannelType", [1]],
  ["channels.getChannelType", [2]],
  ["channels.getChannelType", [2, true]],
  ["channels.getChannelType", [2, false]],
  ["channels.getChannelType", [9]],
  ["channels.getChannelType", [-1]],
  ["channels.getChannelType", []],
  ["channels.getChannelType", ["0"]],
  ["channels.setGridBit", [0, 0, 1]],
  ["channels.setGridBit", [0, 3, 1]],
  ["channels.setGridBit", [0, 5, 1]],
  ["channels.getStepParam", [5, 7, 0, 0, 16]],
  ["channels.getStepParam", [5, 8, 0, 0, 16]],
  ["channels.getStepParam", [5, 1, 0, 0, 16]],
  ["channels.getStepParam", [7, 7, 0, 0, 16]],
  ["channels.getCurrentStepParam", [0, 5, 7]],
  ["channels.getCurrentStepParam", [0, 5, 6]],
  ["channels.getStepParam", [0, 0]],
  ["channels.getStepParam", [0, 1]],
  ["channels.getStepParam", [0, 2]],
  ["channels.getStepParam", [0, 3]],
  ["channels.getStepParam", [0, 4]],
  ["channels.getStepParam", [0, 5]],
  ["channels.getStepParam", [0, 6]],
  ["channels.getStepParam", [0, 7]],
  ["channels.getStepParam", [0, 8]],
  ["channels.getStepParam", [0, -1]],
  ["channels.getStepParam", [1, 0]],
  ["channels.getStepParam", [3, 0]],
  ["channels.getStepParam", [3, 0, 0, 3]],
  ["channels.getStepParam", [5, 0, 0, -3]],
  ["channels.getStepParam", [16, 0]],
  ["channels.getStepParam", [16, 0, 1]],
  ["channels.getStepParam", [-16, 0]],
  ["channels.getStepParam", [0, 0, 0, 0, 0]],
  ["channels.getStepParam", [0, 0, 5]],
  ["channels.getStepParam", [0, 0, 0, 0, 4]],
  ["channels.getStepParam", [0, 0, 0, 0, -16]],
  ["channels.getStepParam", [0, 0, 0, 0, 16, true]],
  ["channels.getStepParam", [0]],
  ["channels.getStepParam", ["0", 0]],
  ["channels.getCurrentStepParam", [0, 0, 0]],
  ["channels.getCurrentStepParam", [0, 0, 1, false]],
  ["channels.getCurrentStepParam", [0, 1, 0]],
  ["channels.getCurrentStepParam", [0, 3, 3, true]],
  ["channels.getCurrentStepParam", [0, 64, 0]],
  ["channels.getCurrentStepParam", [0, 0, -1]],
  ["channels.getCurrentStepParam", [2, 0, 0]],
  ["channels.getCurrentStepParam", [9, 0, 0]],
  ["channels.getCurrentStepParam", [-1, 0, 0]],
  ["channels.getCurrentStepParam", [0, 0, 0, 1, 2]],
  ["channels.getCurrentStepParam", [0, 0]],
  ["channels.getCurrentStepParam", ["0", 0, 0]],
  ["channels.getChannelIndex", [0]],
  ["channels.getChannelIndex", [2]],
  ["channels.getChannelIndex", [9]],
  ["channels.getChannelIndex", [-1]],
  ["channels.getChannelIndex", [true]],
  ["channels.getChannelIndex", [0, 1]],
  ["channels.getChannelIndex", []],
  ["channels.getChannelIndex", ["0"]],
  ["channels.getChannelMidiInPort", [0]],
  ["channels.getChannelMidiInPort", [2, true]],
  ["channels.getChannelMidiInPort", [2, false]],
  ["channels.getChannelMidiInPort", [9]],
  ["channels.getChannelMidiInPort", [-1, true]],
  ["channels.getChannelMidiInPort", [0, "x"]],
  ["channels.getChannelMidiInPort", []],
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
  // PY-115 (#2950): soloChannel の value (-1 は反転、他は現在値の下位 1 B と比較して不一致なら反転)・useGlobalIndex (型検査のみ)。isChannelSolo で状態を比べる
  ["channels.soloChannel", [0, -1]],
  ["channels.isChannelSolo", [0]],
  ["channels.soloChannel", [0, 1]],
  ["channels.isChannelSolo", [0]],
  ["channels.soloChannel", [0, 1]],
  ["channels.isChannelSolo", [0]],
  ["channels.soloChannel", [0, 0]],
  ["channels.isChannelSolo", [0]],
  ["channels.soloChannel", [0, 2]],
  ["channels.isChannelSolo", [0]],
  ["channels.soloChannel", [0, 2]],
  ["channels.isChannelSolo", [0]],
  ["channels.soloChannel", [0, 256]],
  ["channels.isChannelSolo", [0]],
  ["channels.soloChannel", [0, -1, 1]],
  ["channels.isChannelSolo", [0]],
  ["channels.soloChannel", [0, "x"]],
  // PY-146 (#2544): processRECEvent は PY-235 の成功経路 (R-other・low16 != 8) で戻り値 = value。未確定の family は code 2 (未実装)
  ["channels.processRECEvent", [0x10000000, 5, 0]], ["channels.processRECEvent", [0x40000003, -7, 2]], ["channels.processRECEvent", [-0x10000000, 100, 0x20]],
  ["channels.processRECEvent", [0x50000000, 1, 0]], ["channels.processRECEvent", [0x10000008, 9, 0]],
  ["channels.processRECEvent", [0, 1, 0]], ["channels.processRECEvent", [-0x80000000, 1, 0]],
  ["channels.processRECEvent", [0x40000005, 3, 0]], ["channels.processRECEvent", [0x40000001, 3, 0]],
  ["channels.processRECEvent", [0x40000000, -4, 0x1c]], ["channels.processRECEvent", [0x40000002, 7, 0x1]],
  ["channels.processRECEvent", [0x40000000, 3, 0x2]], ["channels.processRECEvent", [0x40000005, 3, 0x20]],
  ["channels.processRECEvent", [1, 2]], ["channels.processRECEvent", [1, 2, 3, 4]],
];

const diffs = [];
for (const [name, args] of seq) {
  const a = run(mock, name, args);
  const b = run(wasm, name, args);
  if (JSON.stringify(a) !== JSON.stringify(b)) diffs.push({ name, args, mock: a, wasm: b });
}

// PY-224 (#3628): getGridBitWithLoop の loop 分岐 (PE 0x12d3ff0)。行 T[1] は検査用に置く (作成経路は未モデル・PY-223 待ち)。position -1..127 を両側で比べる (p >= 64 は件数以上の event 経路)
const LOOP_PAT = [1, 0, 0, 1, 0, 1, 0, 0];
LOOP_PAT.forEach((v, p) => { for (const eng of [mock, wasm]) eng.call("channels.setGridBit", [2, p, v]); });
const loopCases = [
  ["行なし", 0, 0, 0, []],
  ["flag49e 0", 1, 0, 1, [[2, 1, 72]]],
  ["flag54 0", 1, 1, 0, [[2, 1, 72]]],
  ["cid 不一致", 1, 1, 1, [[1, 1, 72]]],
  ["f4 0", 1, 1, 1, [[2, 0, 72]]],
  ["L 0 (len 23)", 1, 1, 1, [[2, 1, 23]]],
  ["L 3 (len 72)", 1, 1, 1, [[2, 1, 72]]],
  ["先頭の一致が勝つ (L 3 の後に L 5)", 1, 1, 1, [[2, 1, 72], [2, 1, 120]]],
  ["L 70 (p >= 16 で L > p と p mod L)", 1, 1, 1, [[2, 1, 1680]]],
];
// 件数以上 (p >= 16 = GRID_N) の base は event 経路。項目を入れて真になる点を含め、loop 分岐の両側で比べる
assert.equal(mock.gridItemsProbe(1, 40), 40);
assert.equal(wasm.gridItemsProbe(1, 40), 40);
const loopMoved = {};
let loopEventTrue = 0;
for (const [label, row, f49, f54, recs] of loopCases) {
  mock.setLoop(row, f49, f54, recs);
  wasm.setLoop(row, f49, f54, recs);
  let moved = 0;
  for (let p = -1; p < 128; p++) {
    const a = run(mock, "channels.getGridBitWithLoop", [2, p]);
    const b = run(wasm, "channels.getGridBitWithLoop", [2, p]);
    if (JSON.stringify(a) !== JSON.stringify(b)) diffs.push({ label, p, mock: a, wasm: b });
    if (JSON.stringify(b) !== JSON.stringify(run(wasm, "channels.getGridBit", [2, p]))) moved++;
    if (p >= 16 && a.ok === true) loopEventTrue++;
  }
  loopMoved[label] = moved;
}
assert.ok(loopEventTrue > 0, "loop 検査の件数以上で真になる点が 0 (検査が空振り)");
mock.gridItemsProbe(0, 0);
wasm.gridItemsProbe(0, 0);
mock.setLoop(0, 0, 0, []);
wasm.setLoop(0, 0, 0, []);
// 数値の期待: L 3 では p=5 は base(2)=0 (base は 1)、p=6 は base(0)=1 (base は 0)。旧挙動 (loop 分岐なし) なら逆になり FAIL する
mock.setLoop(1, 1, 1, [[2, 1, 72]]);
wasm.setLoop(1, 1, 1, [[2, 1, 72]]);
const loopExpect = [[5, { ok: false }], [6, { ok: true }], [3, { ok: true }], [4, { ok: false }]];
for (const [p, want] of loopExpect) {
  assert.deepEqual(run(mock, "channels.getGridBitWithLoop", [2, p]), want, `mock loop p=${p}`);
  assert.deepEqual(run(wasm, "channels.getGridBitWithLoop", [2, p]), want, `wasm loop p=${p}`);
}
// 先頭一致 (L 3) と末尾一致 (L 5) を区別する: 先頭なら p=5 は base(2)=0、末尾なら p=5 は p<5 でなく base(0)=1
mock.setLoop(1, 1, 1, [[2, 1, 72], [2, 1, 120]]);
wasm.setLoop(1, 1, 1, [[2, 1, 72], [2, 1, 120]]);
for (const [p, want] of [[5, { ok: false }], [6, { ok: true }]]) {
  assert.deepEqual(run(mock, "channels.getGridBitWithLoop", [2, p]), want, `mock 先頭一致 p=${p}`);
  assert.deepEqual(run(wasm, "channels.getGridBitWithLoop", [2, p]), want, `wasm 先頭一致 p=${p}`);
}
// 上限 8 件を超える setLoop は両側で throw する (C は fl_engine_loop_add が 0 を返し JS が throw)
const nine = Array.from({ length: 9 }, (_, i) => [2, 1, 72 + i]);
assert.throws(() => mock.setLoop(1, 1, 1, nine), /上限 8/);
assert.throws(() => wasm.setLoop(1, 1, 1, nine), /上限 8/);
mock.setLoop(0, 0, 0, []);
wasm.setLoop(0, 0, 0, []);

assert.deepEqual(diffs, [], `channels/playlist 差分 ${diffs.length} 件`);
// PY-111 (#3747): fillEachNSteps の 4 番目の引数 (既定 100・clamp 0..127) が note の param 1 (velocity) に入る。step p の期待 = 4 番目の引数 (p mod 4 で 4 通り)
const velArgs = [[0, 37], [1, 200], [2, -5], [3, undefined]];
const velWant = (p) => [37, 127, 0, 100][p % 4];
for (const eng of [mock, wasm]) {
  for (const [off, v] of velArgs) eng.call("channels.fillEachNSteps", v === undefined ? [1, 4, off] : [1, 4, off, v]);
  for (let p = 0; p < 64; p++) assert.equal(eng.call("channels.getCurrentStepParam", [1, p, 1]), velWant(p), `param 1 step ${p}`);
}
const velDiffs = [];
for (let p = 0; p < 64; p++) {
  const a = run(mock, "channels.getCurrentStepParam", [1, p, 1]), b = run(wasm, "channels.getCurrentStepParam", [1, p, 1]);
  if (JSON.stringify(a) !== JSON.stringify(b)) velDiffs.push({ p, mock: a, wasm: b });
}
assert.deepEqual(velDiffs, [], `fillEachNSteps 4 番目の差分 ${velDiffs.length} 件`);
// ネガティブコントロール: index 範囲外の setChannelPitch は両側とも code 4 (Index out of range) になること (差分 0 が空振りでないことの確認)
assert.deepEqual(run(mock, "channels.setChannelPitch", [9, 0.5]), { code: 4 });
assert.deepEqual(run(wasm, "channels.setChannelPitch", [9, 0.5]), { code: 4 });

// PY-218 (#3596): 件数超え (position >= 64) は PE 0x12d3e20 の event 経路。項目 (pattern 1) が無ければ偽、項目を入れると channel 一致・閾値 (position+1)*24・flag 0x20 で 1/0 が決まる
const gridRun = (eng) => {
  const out = [];
  for (const i of [0, 1, 2]) for (const p of [-1, 0, 63, 64, 65, 66, 70, 200, 2147483647, 2147483648]) {
    out.push([i, p, run(eng, "channels.getGridBit", [i, p]), run(eng, "channels.getGridBitWithLoop", [i, p])]);
  }
  return out;
};
for (const eng of [mock, wasm]) {
  assert.equal(eng.gridItemsProbe(1, 0), 0);
  for (const [, p, a, b] of gridRun(eng)) if (p >= 16) assert.deepEqual([a, b], [{ ok: false }, { ok: false }], `項目無しの件数超え p=${p}`);
}
const gridDiffs = [];
let gridCalls = 0, gridTrue = 0;
for (const seed of [1, 2, 3, 42, 1234]) for (const n of [1, 5, 40, 256]) {
  assert.equal(mock.gridItemsProbe(seed, n), n);
  assert.equal(wasm.gridItemsProbe(seed, n), n);
  const a = gridRun(mock), b = gridRun(wasm);
  gridCalls += a.length * 2;
  gridTrue += a.filter(([, p, x, y]) => p >= 16 && (x.ok === true || y.ok === true)).length;
  if (JSON.stringify(a) !== JSON.stringify(b)) gridDiffs.push({ seed, n, mock: a, wasm: b });
}
assert.deepEqual(gridDiffs, [], `件数超え (event 経路) の差分 ${gridDiffs.length} 件`);
assert.ok(gridTrue > 0, "件数超えで真になる項目が 1 件も無い (検査が空振り)");
mock.gridItemsProbe(0, 0);
wasm.gridItemsProbe(0, 0);
console.log(JSON.stringify({ calls: seq.length, loop_cases: loopCases.length, loop_moved_vs_base: loopMoved, loop_event_true: loopEventTrue, diffs: 0, grid_calls: gridCalls, grid_true: gridTrue, grid_diffs: gridDiffs.length, PASS: true }));
