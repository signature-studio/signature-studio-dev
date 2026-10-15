// device 5 関数の差分検査: 同じ呼出し列を JS mock (host/fl_mock.mjs) と C provider (provider/fl_engine.c) に流し、
// 各呼出しの戻り値・エラー code と、forwardMIDICC / midiOutMsg の呼出し件数が一致することを確認する。
// PY-227 (#3655): midiOutMsg が送った 32bit word の列 (arg4 は channel ≥ 0 のとき bit 24–31) と、device 割当 (-7)・送出先 (-6) の経路も比べる。
//   node tests/device_diff.mjs     (前提: provider/build.sh 済み)
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
  ["device.getPortNumber", []],
  ["device.isAssigned", []],
  ["device.setHasMeters", []],
  ["device.forwardMIDICC", [0x90 | (60 << 8) | (100 << 16) | (10 << 24), 2]],
  ["device.forwardMIDICC", [0xB0]],
  ["device.midiOutMsg", [0x90, 0, 60, 100]],
  ["device.midiOutMsg", [0xB0]],
  ["device.midiOutMsg", [0xB0, 2, 1, 127, 9]],
  ["device.midiOutMsg", [0x90, 1, 60, 100, 127]],
  ["device.midiOutMsg", [0xB0, -1, 1, 2, 9]],
  ["device.midiOutMsg", [0x1FF, 0x0F, 300, 40000, -1]],
];

// mock は引数の個数・型を検査しない (既知の差)。C 側は署名どおりに拒否する (code 5) ことだけを wasm 単独で確認。
// midiOutMsg は FLEngine の書式 (i|iiii) で 5 個まで受理する (PY-102 / #2927)。6 個目から拒否する。
const rejects = [
  ["device.forwardMIDICC", []],
  ["device.forwardMIDICC", [1, "x"]],
  ["device.midiOutMsg", [0xB0, 2, 1, 127, 9, 9]],
  ["device.midiOutMsg", [0xB0, "x"]],
];
const rejectDiffs = rejects.map(([name, args]) => ({ name, args, wasm: run(wasm, name, args) }))
  .filter((r) => r.wasm.code !== 5);

// PY-227: device 割当 [dev, link] を変えて -7 (device 無し)・-6 (送出先無し) を通す。PE 0xd747f0 は device を見てから送出先を見る (channel によらず先に判定)。
const linkSeq = [
  [[1, 1], ["device.midiOutMsg", [0x90, 1, 60, 100]]],
  [[0, 1], ["device.midiOutMsg", [0x90, 1, 60, 100]]],
  [[1, 0], ["device.midiOutMsg", [0x90, 1, 60, 100]]],
  [[1, 0], ["device.midiOutMsg", [0xB0]]],
  [[0, 0], ["device.midiOutMsg", [0xB0, 2, 1, 127, 9]]],
  [[1, 1], ["device.midiOutMsg", [0xB0, 2, 1, 127, 9]]],
];
const linkExpectCodes = ["ok", 7, 6, 6, 7, "ok"];
const codeOf = (r) => ("code" in r ? r.code : "ok");

const diffs = [];
for (const [name, args] of seq) {
  const a = run(mock, name, args);
  const b = run(wasm, name, args);
  if (JSON.stringify(a) !== JSON.stringify(b)) diffs.push({ name, args, mock: a, wasm: b });
}
const linkCodes = [];
for (const [[dev, link], [name, args]] of linkSeq) {
  mock.state.devAssigned = !!dev;
  mock.state.linkAssigned = !!link;
  wasm.setDeviceLink(dev, link);
  const a = run(mock, name, args);
  const b = run(wasm, name, args);
  linkCodes.push(codeOf(b));
  if (JSON.stringify(a) !== JSON.stringify(b)) diffs.push({ name, args, dev, link, mock: a, wasm: b });
}

const mockOut = mock.state.midiOut.length;
const wasmOut = wasm.midiOutCount();
if (mockOut !== wasmOut) diffs.push({ state: "midiOut count", mock: mockOut, wasm: wasmOut });

// 送った word 列 (midiOutMsg のみ)。期待値は式の手計算 (両側が同じ誤りを持つ場合も落とす)
const expectWords = [0x643C90, 0xB0, 0x097F01B2, 0x7F643C91, 0xB0, 0x9B412DFF, 0x643C91, 0x097F01B2];
const mockWords = mock.state.midiOut.filter((m) => m.api === "midiOutMsg").map((m) => m.word);
const wasmWords = wasm.midiWords();
if (JSON.stringify(mockWords) !== JSON.stringify(wasmWords)) diffs.push({ state: "midi word", mock: mockWords, wasm: wasmWords });
if (JSON.stringify(wasmWords) !== JSON.stringify(expectWords)) diffs.push({ state: "midi word expect", expect: expectWords, wasm: wasmWords });
if (JSON.stringify(linkCodes) !== JSON.stringify(linkExpectCodes)) diffs.push({ state: "link codes", expect: linkExpectCodes, wasm: linkCodes });

assert.deepEqual(diffs, [], `device 差分 ${diffs.length} 件`);
assert.deepEqual(rejectDiffs, [], `署名違反が code 5 で拒否されない ${rejectDiffs.length} 件`);
console.log(JSON.stringify({
  calls: seq.length, link_calls: linkSeq.length, rejects: rejects.length, midi_out: wasmOut,
  midi_words: wasmWords.map((w) => w.toString(16).padStart(8, "0")), link_codes: linkCodes,
  diffs: 0, PASS: true,
}));
