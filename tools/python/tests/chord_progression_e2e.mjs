// Chord progression (System/Tools/Chord progression) の pyc 39 本 + pyscript 2 本の import / エントリポイント実行 (PY-7 #78)。
// 前提: `FL_WIN64_DIR=<fl-win64 展開先> bash build_flpy.sh` 済み (dist/flpy.js)、
//       `FL_WIN64_DIR=<fl-win64 展開先>/extracted "$PY312" analysis/extract_pyc_blocks.py work/fl_extract` 済み
//       (`$PY312` = `work/build-native/install/bin/python3.12`・FL 由来・gitignore)。
// 実 FL の戻り値は未確定。import 時に要る値 (flrack.rack.loop_starter_config の JSON・flpianoroll.score.PPQ・rack.flr 等) は
// tests 側の mock 値で固定する。mock 値は根拠なし (REPORT の表に明記)。実 FL 照合は #81 (PY-9)。
// usage: node tests/chord_progression_e2e.mjs [--neg]    (--neg: 先頭 1 バイトを壊した pyc で FAIL になることを確認)
import fs from "node:fs";
import path from "node:path";
import { FlPython } from "../host/flpython.mjs";
import { createMockEngine } from "../host/fl_mock.mjs";

const root = new URL("../", import.meta.url);
const neg = process.argv.includes("--neg");
const t0 = Date.now();
const ext = new URL("work/fl_extract/", root);
const extRoot = ext.pathname;
const enc = (s) => new TextEncoder().encode(s);

// 実行対象: 39 pyc (MCPTools 除く) と pyscript 2 本。pyscript は control / control_rack の import 先が正本。
const pycs = [];
const walk = (d, base = "") => {
  for (const f of fs.readdirSync(d, { withFileTypes: true })) {
    const rel = base ? `${base}/${f.name}` : f.name;
    if (f.isDirectory()) walk(path.join(d, f.name), rel);
    else if (f.name.endsWith(".pyc") && f.name !== "MCPTools.pyc") pycs.push(rel);
  }
};
walk(extRoot);
pycs.sort();

// mock 値 (根拠なし): import 時の参照のみを満たす。FL 実機の値ではない。
const MOCK_LOOP_STARTER_CONFIG = JSON.stringify({ mock: true, note: "mock (根拠なし)", genres: {}, loops: [] });
const MOCK_PPQ = 96;

const files = {};
for (const rel of pycs) files[`/fl/Tools/Chord progression/${rel}`] = fs.readFileSync(path.join(extRoot, rel));
// 実データ: rack.load_config が asset_io.load_asset("Notes/genres") で読む drum patterns (block24797, 平文 JSON = genres を持つ)。
// load_asset は <path>.jz (zlib 圧縮) が無ければ <path> を平文で読む。pattern_presets.cpt は FL 付随の未抽出データ → 空の mock (根拠なし)。
files["/fl/Tools/Chord progression/Notes/genres"] = fs.readFileSync(path.join(extRoot, "drum_patterns.json"));
files["/fl/Tools/Chord progression/Notes/pattern_presets.cpt"] = enc("");
files["/fl/Tools/Chord progression/cpt.pyscript"] = fs.readFileSync(path.join(extRoot, "pyscript/cpt.pyscript"));
files["/fl/Tools/Chord progression/stack.pyscript"] = fs.readFileSync(path.join(extRoot, "pyscript/stack.pyscript"));
if (neg) {
  const bad = files["/fl/Tools/Chord progression/Chords/data.pyc"];
  files["/fl/Tools/Chord progression/Chords/data.pyc"] = Uint8Array.from([bad[0] ^ 0xff, ...bad.subarray(1)]);
}

const ids = JSON.parse(fs.readFileSync(new URL("analysis/flapi/flapi_ids.json", root)));
const py = await FlPython.create({
  flpyUrl: new URL("dist/flpy.js", root),
  engine: createMockEngine(),
  ids,
  files,
  onStdout: () => {},
  onStderr: () => {},
});

// mock module (flcpt / flrack / flpianoroll の未実装属性は fl_api が None を返す仕様のまま。ここでは import に要る値だけ固定)
await py.run(`
import sys, types, json
import fl_rt, flpianoroll, fl_api
fl_rt.install_flapi()
import flcpt
flrack = types.ModuleType('flrack')
# flcpt.cpt の 4 メンバは src/flcpt.py (根拠あり: REPORT_PY30 §2)。型名は空の dummy。
# mock 値 (根拠なし)。import 時に参照される名前だけを満たす。
flcpt.chordPool = types.SimpleNamespace()
import json as _json
_lsc = _json.load(open('/fl/Tools/Chord progression/Notes/genres', encoding='utf-8'))
_lsc = {'mock': True, 'note': 'mock (根拠なし): FL 実機の loop_starter_config ではない。同梱 drum patterns の genres を流用', 'version': _lsc.get('version'), 'compatible_from': _lsc.get('compatible_from'), 'genres': _lsc.get('genres', {}), 'loops': []}
flrack.rack = types.SimpleNamespace(loop_starter_config=_json.dumps(_lsc), flr=types.SimpleNamespace())
flrack.flr = types.SimpleNamespace()
flpianoroll.score.PPQ = ${MOCK_PPQ}
sys.modules['flcpt'] = flcpt
sys.modules['flrack'] = flrack
sys.modules['flpianoroll_proxy'] = flpianoroll
sys.path.insert(0, '/fl/Tools/Chord progression')
`);
// flcpt_proxy / flrack_proxy は FL 同梱の補助 module (pyc)。import の時点で ChordMarker 等の属性が要るので、先に読み込む。
await py.run(`
import importlib
for _m in ('flcpt_proxy',):
    try:
        importlib.import_module(_m)
    except Exception as _e:
        print('proxy load failed', _m, _e)
`);

// 各 pyc を module 名で import (sys.path 経由の通常 import と同じ順序は問わない)。失敗は detail に残す。
const results = [];
for (const rel of pycs) {
  const mod = rel.slice(0, -4).replace(/\//g, ".").replace(/\.__init__$/, "");
  let r;
  try {
    await py.run(`import importlib; importlib.import_module(${JSON.stringify(mod)})`);
    r = { name: rel, ok: true, detail: "import ok" };
  } catch (e) {
    const lines = String(e.message ?? e).split("\n").map((l) => l.trim()).filter(Boolean);
    const err = lines.filter((l) => /(Error|Exception)\b/.test(l) && !/^Error: exec:$/.test(l)).pop() ?? lines[0];
    r = { name: rel, ok: false, detail: err.slice(0, 240) };
  }
  results.push(r);
}
// pyscript 2 本: トップレベルの exec (エントリポイント相当)。cpt は control、stack は control_rack を import するため、その依存が通るかで決まる。
for (const name of ["cpt", "stack"]) {
  let r;
  try {
    await py.run(`exec(compile(open('/fl/Tools/Chord progression/${name}.pyscript', encoding='utf-8').read(), '${name}.pyscript', 'exec'), {'__name__': '${name}'})`);
    r = { name: `${name}.pyscript`, ok: true, detail: "exec ok" };
  } catch (e) {
    const lines = String(e.message ?? e).split("\n").map((l) => l.trim()).filter(Boolean);
    const err = lines.filter((l) => /(Error|Exception)\b/.test(l) && !/^Error: exec:$/.test(l)).pop() ?? lines[0];
    r = { name: `${name}.pyscript`, ok: false, detail: err.slice(0, 240) };
  }
  results.push(r);
}
const sec = ((Date.now() - t0) / 1000).toFixed(1);
const pass = results.filter((r) => r.ok).length;
for (const r of results) console.log(r.ok ? "PASS" : "FAIL", r.name, r.detail);
console.log(JSON.stringify({ total: results.length, pass, fail: results.length - pass, mock: true, sec }));
// 規約: 不合格は非 0 exit (緑にしない)。--neg は意図的に壊した入力で FAIL になることを確認するため、FAIL 時 exit 1 が正。
process.exit(pass === results.length ? 0 : 1);
