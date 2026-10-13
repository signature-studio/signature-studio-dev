// PY-20: C provider (fl_api_call) と JS mock の MIDI 経路 5 関数の戻り値・code 差分検査。
//   node tests/midi_path_diff.mjs     (前提: provider/build.sh 済み。Python 不要)
// 同じ呼出し列を両方に流し、戻り値 (型込み) と FL エラー code が一致することを確認する。
import fs from "node:fs";
import assert from "node:assert/strict";
import { createWasmEngine } from "../host/fl_provider.mjs";
import { createMockEngine } from "../host/fl_mock.mjs";

const root = new URL("../", import.meta.url);
const ids = JSON.parse(fs.readFileSync(new URL("analysis/flapi/flapi_ids.json", root)));
const wasm = await createWasmEngine({ flprovUrl: new URL("dist/flprov.js", root), ids });
const mock = createMockEngine();

const run = (eng, name, args) => {
  try { return { ok: eng.call(name, args) }; } catch (e) { return { err: e.message, code: e.flCode }; }
};
// None は JS の undefined (mock) と null (wasm) の両方を含むため同一視する
const norm = (r) => {
  if (r.err !== undefined) return r;
  const v = r.ok;
  if (v === undefined || v === null) return { ok: null };
  if (typeof v === "object" && "v" in v) return { ok: v.v, t: v.t };
  return { ok: v };
};

const cases = [
  ["general.getVersion", []],
  ["transport.isPlaying", []],
  ["transport.start", []],
  ["transport.isPlaying", []],
  ["transport.stop", []],
  ["transport.isPlaying", []],
  ["channels.selectedChannel", []],
  ["channels.selectedChannel", [true, 1]],
  ["channels.fillEachNSteps", [0, 4, 0, 100]],
  ["channels.fillEachNSteps", [1, 2, 1]],
  ["channels.fillEachNSteps", [999, 4]],
  ["ilmcp.forwardTutorialEvent", ["a", 1]],
  ["ilmcp.forwardTutorialEvent", []],
];

let diffs = 0;
for (const [name, args] of cases) {
  const a = norm(run(wasm, name, args));
  const b = norm(run(mock, name, args));
  const same = JSON.stringify(a) === JSON.stringify(b) || (a.err && b.err && a.code === b.code);
  if (!same) { diffs++; console.log("DIFF", name, JSON.stringify(args), "wasm", JSON.stringify(a), "mock", JSON.stringify(b)); }
}
console.log(JSON.stringify({ cases: cases.length, diffs, PASS: diffs === 0 }));
assert.equal(diffs, 0);
