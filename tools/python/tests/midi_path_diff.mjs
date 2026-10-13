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
  ["general.getVersion", [1]],
  ["transport.isPlaying", []],
  ["transport.isPlaying", [0]],
  ["transport.start", []],
  ["transport.isPlaying", []],
  ["transport.stop", []],
  ["transport.isPlaying", []],
  ["channels.selectedChannel", []],
  ["channels.selectedChannel", [true, 1]],
  ["channels.selectedChannel", ["x"]],
  ["channels.selectedChannel", [false, 0, 0, 9]],
  ["channels.fillEachNSteps", [0, 4, 0, 100]],
  ["channels.fillEachNSteps", [0, 4]],
  ["channels.fillEachNSteps", [0]],
  ["channels.fillEachNSteps", [1, 2, 1]],
  ["channels.fillEachNSteps", [2, 4, -3]],
  ["channels.fillEachNSteps", [1, 4, 0, 100, true, 9]],
  ["channels.fillEachNSteps", [0, 0]],
  ["channels.fillEachNSteps", [0, -1]],
  ["channels.fillEachNSteps", ["a", 4]],
  ["channels.fillEachNSteps", [0.5, 4]],
  ["channels.fillEachNSteps", [999, 4]],
  ["channels.fillEachNSteps", [0, 1, -100000000]],
  ["channels.fillEachNSteps", [0, 1, -9e18]],
  ["channels.fillEachNSteps", [1, 2, -9e18]],
  ["channels.fillEachNSteps", [2, 3, -7]],
  ["channels.fillEachNSteps", [0, 1e18, 1]],
  ["ilmcp.forwardTutorialEvent", ["a", 1]],
  ["ilmcp.forwardTutorialEvent", []],
];

// 戻り値と code に加えて副作用 (チャンネル 0..2 の全ステップ) を比べる。どちらも 1 呼出し毎に照合する
const grid = (eng, wasmSide) => {
  const out = [];
  for (let c = 0; c < 3; c++) for (let p = 0; p < 64; p++) out.push(wasmSide ? eng.gridBit(c, p) : eng.state.channels[c].steps[p] ? 1 : 0);
  return out.join("");
};

let diffs = 0, lit = 0;
for (const [name, args] of cases) {
  const a = norm(run(wasm, name, args));
  const b = norm(run(mock, name, args));
  const ga = grid(wasm, true), gb = grid(mock, false);
  const same = JSON.stringify(a) === JSON.stringify(b) || (a.err && b.err && a.code === b.code);
  if (!same || ga !== gb) { diffs++; console.log("DIFF", name, JSON.stringify(args), "wasm", JSON.stringify(a), "mock", JSON.stringify(b), ga === gb ? "" : "grid"); }
  lit = Math.max(lit, (ga.match(/1/g) || []).length);
}
console.log(JSON.stringify({ cases: cases.length, diffs, lit_steps: lit, PASS: diffs === 0 }));
assert.equal(diffs, 0);
assert.ok(lit > 0, "副作用の検査が空だと意味がない");
