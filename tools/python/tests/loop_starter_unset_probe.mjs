// flrack.rack.loop_starter_config を未設定にしたときの挙動を、rack.Rack.load_config を直接呼んで実測する (PY-168 #3182)。
// 前提: chord_progression_e2e.mjs と同じ (dist/flpy.js 済み、work/fl_extract/ 済み)。
// usage: node tests/loop_starter_unset_probe.mjs
import fs from "node:fs";
import path from "node:path";
import { FlPython } from "../host/flpython.mjs";
import { createMockEngine } from "../host/fl_mock.mjs";

const root = new URL("../", import.meta.url);
const extRoot = new URL("work/fl_extract/", root).pathname;
const files = {};
const walk = (d, base = "") => {
  for (const f of fs.readdirSync(d, { withFileTypes: true })) {
    const rel = base ? `${base}/${f.name}` : f.name;
    if (f.isDirectory()) walk(path.join(d, f.name), rel);
    else if (f.name.endsWith(".pyc")) files[`/fl/Tools/Chord progression/${rel}`] = fs.readFileSync(path.join(d, f.name));
  }
};
walk(extRoot);
files["/fl/Tools/Chord progression/Notes/genres"] = fs.readFileSync(path.join(extRoot, "drum_patterns.json"));
files["/fl/Tools/Chord progression/Notes/pattern_presets.cpt"] = new TextEncoder().encode("");
const ids = JSON.parse(fs.readFileSync(new URL("analysis/flapi/flapi_ids.json", root)));
const lines = [];
const py = await FlPython.create({
  flpyUrl: new URL("dist/flpy.js", root), engine: createMockEngine(), ids, files,
  onStdout: (t) => lines.push(t), onStderr: (t) => lines.push(t),
});
await py.run(`
import sys, types
import fl_rt, flpianoroll, fl_api
fl_rt.install_flapi()
import flcpt
flrack = types.ModuleType('flrack')
flrack.rack = types.SimpleNamespace(flr=types.SimpleNamespace())
flpianoroll.score.PPQ = 96
sys.modules['flcpt'] = flcpt
sys.modules['flrack'] = flrack
sys.modules['flpianoroll_proxy'] = flpianoroll
sys.path.insert(0, '/fl/Tools/Chord progression')
import rack
_st = 'OK'
try:
    rack.Rack().load_config()
except BaseException as _e:
    _st = type(_e).__name__ + ': ' + str(_e)[:100]
print('ROW|load_config|' + _st)
`);
const row = lines.join("").split("\n").find((l) => l.startsWith("ROW|"));
console.log("| 呼び出し | 結果 |");
console.log("|---|---|");
console.log(`| rack.Rack().load_config() (loop_starter_config 未設定) | ${(row ?? "NO_OUTPUT").split("|")[2]} |`);
process.exit(0);
