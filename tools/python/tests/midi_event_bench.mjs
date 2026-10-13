// PY-8 (#80): MIDI 1 イベント当りの flapi 呼出し数と所要時間を実測する。
//   node tests/midi_event_bench.mjs [events=2000] [trials=3]
// 対象: 同梱 device script (Forward CCs to current plugin Port 10) を mock flapi 上で実行し、
// CC 1 件の配送 (OnMidiIn → OnMidiMsg → OnControlChange) を Worker+SAB RPC 経路で流す。
// 出力: JSON。flapi 呼出し数は FlPython.calls (RpcServer 経由の engine.call 回数) を差分で数える。
// 前提: dist/flpy.js (build_flpy.sh 済み)、work/device_Forward CCs to current plugin Port 10.py (fetch_inputs.sh 済み)。
// 注意: 所要時間は mock engine (JS) の処理を含む。実 FLEngine の処理時間は含まない。
import fs from "node:fs";
import { FlPython } from "../host/flpython.mjs";
import { createMockEngine } from "../host/fl_mock.mjs";
import { MidiScriptHost } from "../host/midi_host.mjs";

const root = new URL("../", import.meta.url);
const events = Number(process.argv[2] || 2000);
const trials = Number(process.argv[3] || 3);
const ids = JSON.parse(fs.readFileSync(new URL("analysis/flapi/flapi_ids.json", root)));
const devPath = new URL("work/device_Forward CCs to current plugin Port 10.py", root);
if (!fs.existsSync(devPath)) { console.error("入力欠落: work/device_Forward CCs to current plugin Port 10.py (fetch_inputs.sh)"); process.exit(3); }
const source = fs.readFileSync(devPath, "utf8");

const engine = createMockEngine();
const flapiCalls = { n: 0 };
const counted = { call: (name, args) => { flapiCalls.n++; return engine.call(name, args); } };
const W = (n) => fs.readFileSync(new URL(`work/${n}`, root));
const files = { "/fl/Lib/utils.py": W("utils.py"), "/fl/Lib/midi.py": W("midi.py") };
const py = await FlPython.create({ flpyUrl: new URL("dist/flpy.js", root), engine: counted, ids, files, onStdout() {}, onStderr() {} });
await py.run("import fl_rt\nfl_rt.install_flapi()");
const host = new MidiScriptHost(py);
await host.loadDeviceScript({ name: "fwd", source, port: 0 });
await host.init();

// CC: device script が device.forwardMIDICC を 1 回呼ぶ (flapi 1)。NoteOn: flapi 0 (対照。配送と Python 側処理だけ)。
const cases = { cc: Uint8Array.from([0xb0, 7, 100]), noteon: Uint8Array.from([0x90, 60, 100]) };
const out = {};
for (const [k, msg] of Object.entries(cases)) {
  const per = [];
  for (let t = 0; t < trials; t++) {
    for (let i = 0; i < 50; i++) await host.midiIn(msg, { port: 0 });
    flapiCalls.n = 0;
    const t0 = performance.now();
    for (let i = 0; i < events; i++) await host.midiIn(msg, { port: 0 });
    const dt = performance.now() - t0;
    per.push({ us_per_event: +((dt * 1000) / events).toFixed(2), flapi_per_event: +(flapiCalls.n / events).toFixed(3) });
  }
  const us = per.map((x) => x.us_per_event).sort((a, b) => a - b);
  out[k] = { us_per_event: { min: us[0], median: us[us.length >> 1], max: us[us.length - 1] }, flapi_per_event: per[0].flapi_per_event, per_trial: per };
}
console.log(JSON.stringify({ events, trials, load: fs.readFileSync("/proc/loadavg", "utf8").trim(), ...out }));
await py.terminate();
