// device 5 関数の差分検査: 同じ呼出し列を JS mock (host/fl_mock.mjs) と C provider (provider/fl_engine.c) に流し、
// 各呼出しの戻り値・エラー code と、forwardMIDICC / midiOutMsg の呼出し件数が一致することを確認する。
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


const diffs = [];
for (const [name, args] of seq) {
  const a = run(mock, name, args);
  const b = run(wasm, name, args);
  if (JSON.stringify(a) !== JSON.stringify(b)) diffs.push({ name, args, mock: a, wasm: b });
}

const mockOut = mock.state.midiOut.length;
const wasmOut = wasm.midiOutCount();
if (mockOut !== wasmOut) diffs.push({ state: "midiOut count", mock: mockOut, wasm: wasmOut });

assert.deepEqual(diffs, [], `device 差分 ${diffs.length} 件`);
assert.deepEqual(rejectDiffs, [], `署名違反が code 5 で拒否されない ${rejectDiffs.length} 件`);
console.log(JSON.stringify({ calls: seq.length, rejects: rejects.length, midi_out: wasmOut, diffs: 0, PASS: true }));
