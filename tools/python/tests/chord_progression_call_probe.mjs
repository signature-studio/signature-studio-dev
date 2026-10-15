// Chord progression の代表関数を、flcpt / flrack を「読まれた属性を記録する」スタブ上で呼び、呼べた数・呼べなかった数と理由を表で出す (PY-22 #1053)。
// 前提: chord_progression_e2e.mjs と同じ (dist/flpy.js 済み、work/fl_extract/ 済み)。実 FL の戻り値は未確定 (REPORT_PY22.md)。
// flcpt.cpt の CPT 4 メンバ (addChordMarker・getChordMarker・clearChordMarkers・chordMarkerCount) は src/flcpt.py の実装 (REPORT_PY30 §2)。
// それ以外の属性と flrack は、戻り値を一切作らず例外・読まれた属性だけを記録するスタブ。本 probe は**実装の代わりではない**。
// usage: node tests/chord_progression_call_probe.mjs
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
SEEN = []
class Rec:
    def __init__(self, p):
        object.__setattr__(self, '_p', p)
    def __getattr__(self, k):
        if k.startswith('__'):
            raise AttributeError(k)
        SEEN.append(self._p + '.' + k)
        return Rec(self._p + '.' + k)
    def __call__(self, *a, **kw):
        SEEN.append(self._p + '()')
        return Rec(self._p + '()')
    def __iter__(self):
        return iter([])
    def __len__(self):
        return 0
    def __bool__(self):
        return False
    def __int__(self):
        return 0
    def __index__(self):
        return 0
    def __float__(self):
        return 0.0
    def __lt__(self, o):
        return False
    def __gt__(self, o):
        return False
import flcpt
flrack = types.ModuleType('flrack')
class _CPTRec(flcpt.CPT):
    def __getattr__(self, k):
        return getattr(Rec('cpt'), k)
flcpt.cpt = _CPTRec()
flcpt.chordPool = Rec('chordPool')
flrack.rack = types.SimpleNamespace(loop_starter_config='{"mock": true, "genres": {}, "loops": []}', flr=types.SimpleNamespace())
flrack.flr = types.SimpleNamespace()
flpianoroll.score.PPQ = 96
sys.modules['flcpt'] = flcpt
sys.modules['flrack'] = flrack
sys.modules['flpianoroll_proxy'] = flpianoroll
sys.path.insert(0, '/fl/Tools/Chord progression')
import importlib
importlib.import_module('flcpt_proxy')
import control
`);
const calls = [
  ["apply_chord_preset", "('x', 0, 0, 0, 0, 0, 0, 0)"],
  ["get_chord_name", "([0, 4, 7],)"],
  ["text_to_chord", "('Cmaj7',)"],
  ["get_chord_root", "('Cmaj7',)"],
  ["get_chord_preset_str", "()"],
  ["get_rhythm_preset_str", "('x',)"],
  ["get_chord_pool_preset_str", "('x',)"],
  ["analyse_chord", "()"],
  ["reset", "()"],
];
const rows = [];
for (const [fn, args] of calls) {
  lines.length = 0;
  await py.run(`
import control
import flcpt
flcpt.cpt.clearChordMarkers()
SEEN.clear()
_r = None
_st = 'OK'
try:
    _r = control.${fn}${args}
except BaseException as _e:
    _st = type(_e).__name__ + ': ' + str(_e)[:100]
_seen = sorted(set(SEEN))
print('ROW|${fn}|' + _st + '|' + ' '.join(_seen))
`);
  const row = lines.join("").split("\n").find((l) => l.startsWith("ROW|"));
  rows.push(row ?? `ROW|${fn}|NO_OUTPUT|`);
}
let called = 0, failed = 0;
console.log("| 関数 | 結果 | 読まれた flcpt 属性 |");
console.log("|---|---|---|");
for (const r of rows) {
  const [, fn, st, seen] = r.split("|");
  if (st === "OK") called++; else failed++;
  console.log(`| ${fn} | ${st.replace(/\|/g, "/")} | ${seen || "-"} |`);
}
console.log(JSON.stringify({ total: rows.length, called, failed }));
process.exit(0);
