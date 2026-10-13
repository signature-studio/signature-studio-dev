// PY-6 (#76) 受入条件: FL 同梱 device script "Forward CCs to current plugin Port 10" が wasm Python 上で動くこと。
//   node tools/python/tests/midi_bundled_device.mjs [--neg]
//   入力 (利用者の FL から供給。git 非管理): tools/python/work/{device_Forward CCs to current plugin Port 10.py, midi.py, utils.py}  (fetch_inputs.sh が配置)
//   exit 0 = PASS / 2 = FAIL / 3 = **NOT VERIFIED (入力が無い。受入条件は未検証)** / --neg で壊した入力を検出できたとき 1
//   入力が無いときに exit 0 にしない (= 「検証していないのに緑」を作らない)。
//   --neg: midi.py を供給しない → 同梱 script の `import midi` が失敗し、「script を読込める」の判定が FAIL することを確認する。
//   --neg-mutate: 実 script のポート定数 (10 << 24) を (11 << 24) に書換える → 転送 message の判定だけが FAIL することを確認する (検出できたとき exit 1)。
//   実ファイルの挙動 (FL 26.1.7.5653 / win64 block24618 を読んで確定): OnMidiIn は `event.status == midi.MIDI_CONTROLCHANGE` (0xB0 の完全一致 = ch0 の CC のみ) のとき
//     device.forwardMIDICC(status + (data1<<8) + (data2<<16) + (10<<24), 2) を呼び handled=True。それ以外は handled=False で OnMidiMsg へ進む (OnMidiMsg も handled=False)。
import fs from "node:fs";
import { FlPython } from "../host/flpython.mjs";
import { createMockEngine } from "../host/fl_mock.mjs";
import { MidiScriptHost } from "../host/midi_host.mjs";

const neg = process.argv.includes("--neg");
const negMutate = process.argv.includes("--neg-mutate");
const root = new URL("../", import.meta.url);
const W = (n) => new URL(`work/${n}`, root);
const devName = "device_Forward CCs to current plugin Port 10.py";
const need = [devName, "midi.py", "utils.py"];
const missing = need.filter((n) => !fs.existsSync(W(n)));
if (missing.length) {
  console.error(`MIDI BUNDLED NOT VERIFIED: 入力が無い: ${missing.join(", ")} (tools/python/work/)。fl-win64 素材 (または mac FL) から fetch_inputs.sh で配置すること。`);
  process.exit(3);
}

const ids = JSON.parse(fs.readFileSync(new URL("analysis/flapi/flapi_ids.json", root)));
const engine = createMockEngine();
const out = [];
const err = [];
const files = { "/fl/Lib/utils.py": fs.readFileSync(W("utils.py")) };
if (!neg) files["/fl/Lib/midi.py"] = fs.readFileSync(W("midi.py"));
const py = await FlPython.create({ flpyUrl: new URL("dist/flpy.js", root), engine, ids, files, onStdout: (t) => out.push(t), onStderr: (t) => err.push(t) });
await py.run("import fl_rt\nfl_rt.install_flapi()");
const host = new MidiScriptHost(py);
const checks = {};
const check = (n, c, x) => { checks[n] = !!c; if (!c) console.error(`FAIL ${n}`, x === undefined ? "" : JSON.stringify(x)); };

let devSrc = fs.readFileSync(W(devName), "utf8");
if (negMutate) {
  if (!devSrc.includes("(10 << 24)")) { console.error("--neg-mutate: 書換え対象 (10 << 24) が実 script に無い (FL 版が違う?)"); process.exit(3); }
  devSrc = devSrc.replace("(10 << 24)", "(11 << 24)");
}
let info = null;
try {
  info = await host.loadDeviceScript({ name: "bundled", source: devSrc, port: 10 });
} catch (e) {
  console.error(String(e.message).split("\n").slice(0, 6).join("\n"));
}
const KEY = "同梱 script を読込める (import midi/utils/device... が解決し top-level が実行できる)";
check(KEY, info !== null);
if (info) {
  check("定義 callback = {OnInit, OnMidiIn, OnMidiMsg} (scripts_inventory.json の top-level 関数と一致)", info.callbacks.join() === "OnInit,OnMidiIn,OnMidiMsg", info.callbacks);
  const i = await host.init();
  check("OnInit が例外なく完了", i[0].results[0].called.join() === "OnInit" && i[0].results[0].errors.length === 0, i[0]);
  const trace = {};
  const run = async (label, bytes) => {
    const n0 = engine.record.length;
    const r = await host.midiIn(Uint8Array.from(bytes), { port: 10 });
    const calls = engine.record.slice(n0).map(([name, a]) => `${name}(${JSON.stringify(a)})`);
    trace[label] = { called: r.results[0].called, errors: r.results[0].errors, handled: r.results[0].msg.handled, api: calls };
    return trace[label];
  };
  for (const [label, bytes] of [["cc1_ch0", [0xb0, 1, 64]], ["cc74_ch5", [0xb5, 74, 99]], ["cc7_ch0", [0xb0, 7, 100]], ["note_on", [0x90, 60, 100]], ["note_off", [0x80, 60, 0]], ["pitch_bend", [0xe0, 0, 64]], ["program_change", [0xc0, 5]], ["sysex", [0xf0, 0x7d, 1, 0xf7]]]) await run(label, bytes);
  check("全イベント種別 (CC/Note/PB/PC/sysex) の配送で script の例外 0", Object.values(trace).every((t) => t.errors.length === 0), trace);
  const impl = new Set(engine.implemented());
  const unimpl = [...new Set(engine.record.map((r) => r[0]))].filter((n) => !impl.has(n));
  check("script が呼んだ flapi は全て mock が実装済み (未実装 API は None を返す=無言の差異になるため検出)", unimpl.length === 0, unimpl);
  const fwd = engine.state.midiOut.filter((m) => m.api === "forwardMIDICC");
  const msgOf = (st, d1, d2) => st + (d1 << 8) + (d2 << 16) + (10 << 24);
  check("実 script: ch0 の CC 2 件 (CC1/CC7) だけが device.forwardMIDICC(status+(d1<<8)+(d2<<16)+(10<<24), 2) に渡る (入力 port ではなく定数 10)",
    JSON.stringify(fwd) === JSON.stringify([{ api: "forwardMIDICC", message: msgOf(0xb0, 1, 64), mode: 2 }, { api: "forwardMIDICC", message: msgOf(0xb0, 7, 100), mode: 2 }]), fwd);
  check("転送した CC は OnMidiIn で handled=True になり OnMidiMsg へ進まない", ["cc1_ch0", "cc7_ch0"].every((k) => trace[k].handled === true && trace[k].called.join() === "OnMidiIn"), trace);
  check("ch5 の CC (0xB5) は status 完全一致 (== MIDI_CONTROLCHANGE) に合わないため転送されない (実 script の挙動。公開 stubs 文書の例 status=191 (0xBF) は ch を含む形)", trace.cc74_ch5.api.length === 0 && trace.cc74_ch5.handled === false, trace.cc74_ch5);
  check("Note/PB/PC/sysex は転送せず handled=False で OnMidiIn → OnMidiMsg まで進む", ["note_on", "note_off", "pitch_bend", "program_change", "sysex"].every((k) => trace[k].api.length === 0 && trace[k].handled === false && trace[k].called.join() === "OnMidiIn,OnMidiMsg"), trace);
  console.log("trace", JSON.stringify(trace));
}
await py.terminate();
const failed = Object.entries(checks).filter(([, v]) => !v).map(([k]) => k);
const MUT = "実 script: ch0 の CC 2 件";
const ok = neg ? failed.length > 0 && failed[0] === KEY : negMutate ? failed.length === 1 && failed[0].startsWith(MUT) : failed.length === 0;
console.log((ok ? (neg || negMutate ? "MIDI BUNDLED NEG-CONTROL DETECTED " : "MIDI BUNDLED OK ") : "MIDI BUNDLED FAIL ") + JSON.stringify({ ok, neg, negMutate, checks: Object.keys(checks).length, failed }));
process.exit(ok ? (neg || negMutate ? 1 : 0) : 2);
