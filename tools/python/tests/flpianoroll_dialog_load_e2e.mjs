// flpianoroll の残り 2 メンバ (PY-19 / #792): Score.loadScoreFromFile (仮想 FS の JSON 読込) と ScriptDialog.DialogParams (MOCK)。
// 既存の pyscript_e2e.mjs (43 checks) とは独立。FL 同梱スクリプトは使わず、FL 由来物を一切要求しない。
//   node tests/flpianoroll_dialog_load_e2e.mjs [--dump <out.json>]   (前提: build_flpy.sh 済み = dist/flpy.js)
import fs from "node:fs";
import path from "node:path";
import { FlPython } from "../host/flpython.mjs";
import { createMockEngine } from "../host/fl_mock.mjs";

const root = new URL("../", import.meta.url);
const arg = (k) => { const i = process.argv.indexOf(k); return i >= 0 ? process.argv[i + 1] : null; };
const t0 = Date.now();
const results = [];
const check = (name, ok, detail = "") => { results.push({ name, ok: !!ok, detail: String(detail) }); if (!ok) console.log("FAIL", name, detail); };

const ids = JSON.parse(fs.readFileSync(new URL("analysis/flapi/flapi_ids.json", root)));
const enc = (s) => new TextEncoder().encode(s);
const score = { PPQ: 96, tsnum: 3, tsden: 4, length: 96, notes: [{ number: 64, time: 96, length: 24, velocity: 0.9 }, { number: 67, time: 192, length: 24 }] };
const files = {
  "/work/score.json": enc(JSON.stringify(score)),
  "/work/not_object.json": enc("[1,2,3]"),
  "/work/broken.json": enc("{ not json"),
};
const py = await FlPython.create({ flpyUrl: new URL("dist/flpy.js", root), engine: createMockEngine(), ids, files, onStdout: () => {}, onStderr: () => {} });
await py.run("import fl_rt, flpianoroll; flpianoroll.install(); fl_rt.install_flapi()");

// 検査用の関数は __main__ に定義し、call で値を取り出す (py.call は {ok} | {err} を返す)
await py.run(`
def _load(path):
    flpianoroll.score.loadScoreFromFile(path)
    s = flpianoroll.score
    return {"PPQ": s.PPQ, "tsnum": s.tsnum, "tsden": s.tsden, "noteCount": s.noteCount,
            "notes": [[s.getNote(i).number, s.getNote(i).time, s.getNote(i).length] for i in range(s.noteCount)],
            "velocity0": s.getNote(0).velocity}

def _dlg():
    d = flpianoroll.ScriptDialog("T", "D")
    d.AddInputKnob("Knob", 0.5, 0, 1)
    d.AddInputCheckbox("Chk", True)
    d.AddInputCombo("Mode", "a,b,c", 2)
    d.addGroup("G")
    d.AddInputText("Name", "x")
    d.endGroup()
    before = d.DialogParams()
    d.set_values({"Knob": 0.75})
    return {"before": before, "after_knob": d.DialogParams()["Knob"], "keys": sorted(d.DialogParams().keys())}
`);

// ===== 1. loadScoreFromFile 正常系: 仮想 FS の JSON を読み、dump() と同じ内容が score に入る =====
const ok = await py.call("__main__:_load", ["/work/score.json"]);
check("loadScoreFromFile: 正常読込が成功", !!ok.ok, JSON.stringify(ok));
if (ok.ok) {
  const v = ok.ok;
  check("loadScoreFromFile: PPQ/tsnum/tsden が入る", v.PPQ === 96 && v.tsnum === 3 && v.tsden === 4, JSON.stringify(v));
  check("loadScoreFromFile: ノート 2 件・番号/時刻/長さが一致", v.noteCount === 2 &&
    JSON.stringify(v.notes) === JSON.stringify([[64, 96, 24], [67, 192, 24]]), JSON.stringify(v.notes));
  check("loadScoreFromFile: 省略フィールドは Note の既定値 (velocity 0.9 は保持)", v.velocity0 === 0.9, String(v.velocity0));
}

// ===== 2. ネガコン: 存在しないパス → FL と同じく例外 (ここでは FileNotFoundError) =====
const miss = await py.call("__main__:_load", ["/work/missing.json"]);
check("NEG-1: 存在しないパスは FileNotFoundError", !!miss.err && /FileNotFoundError/.test(miss.err), miss.err || JSON.stringify(miss.ok));

// ===== 3. ネガコン: JSON として不正 / オブジェクトでない → 例外 (黙って空 score にしない) =====
const bad = await py.call("__main__:_load", ["/work/broken.json"]);
check("NEG-2: 不正 JSON は例外 (JSONDecodeError)", !!bad.err && /JSONDecodeError/.test(bad.err), bad.err || JSON.stringify(bad.ok));
const notObj = await py.call("__main__:_load", ["/work/not_object.json"]);
check("NEG-3: JSON が object でなければ ValueError", !!notObj.err && /ValueError/.test(notObj.err), notObj.err || JSON.stringify(notObj.ok));

// ===== 4. ScriptDialog.DialogParams (MOCK): 控制値を {name: value} で返す =====
const dl = await py.call("__main__:_dlg", []);
check("DialogParams: 呼出しが成功", !!dl.ok, JSON.stringify(dl));
if (dl.ok) {
  const b = dl.ok.before;
  check("DialogParams: 既定値 (Knob 0.5 / Chk 1 / Mode 2 / group 内 Name は 'G: Name')",
    b["Knob"] === 0.5 && b["Chk"] === 1 && b["Mode"] === 2 && b["G: Name"] === "x", JSON.stringify(b));
  check("DialogParams: 控制数は 4 (group 名は接頭辞)", Object.keys(b).length === 4, JSON.stringify(Object.keys(b)));
  check("DialogParams: set_values の変更が反映される", dl.ok.after_knob === 0.75, String(dl.ok.after_knob));
}

await py.terminate();

const pass = results.filter((r) => r.ok).length;
const summary = { total: results.length, pass, fail: results.length - pass, seconds: Number(((Date.now() - t0) / 1000).toFixed(2)) };
console.log(JSON.stringify(summary));
for (const r of results) console.log(r.ok ? "PASS" : "FAIL", r.name);
const dump = arg("--dump");
if (dump) { fs.mkdirSync(path.dirname(dump), { recursive: true }); fs.writeFileSync(dump, JSON.stringify({ summary, results })); }
process.exit(pass === results.length ? 0 : 1);
