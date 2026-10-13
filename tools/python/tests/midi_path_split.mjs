// PY-8 (#80): MIDI 1 イベントの所要時間を「flapi ハンドラ内 (mock engine)」と「それ以外 (Python + RPC 転送 + Worker)」に分解する。
//   node tests/midi_path_split.mjs [events=5000] [trials=5]
// 同梱 device script (CC 1 件 = flapi 1 回) を midi_event_bench.mjs と同じ経路で流す。
// handler_us: counted.call の中の時間 (RpcServer 側で mock engine が動いている区間)。
// rest_us = total_us - handler_us: Python 実行 + RPC 往復 (Atomics) + Worker 側の処理。
// 注意: 所要時間は mock engine (JS) の処理を含む。実 FLEngine の処理時間は含まない。
import fs from "node:fs";
import { FlPython } from "../host/flpython.mjs";
import { createMockEngine } from "../host/fl_mock.mjs";
import { MidiScriptHost } from "../host/midi_host.mjs";

const root = new URL("../", import.meta.url);
const events = Number(process.argv[2] || 5000);
const trials = Number(process.argv[3] || 5);
const ids = JSON.parse(fs.readFileSync(new URL("analysis/flapi/flapi_ids.json", root)));
const devPath = new URL("work/device_Forward CCs to current plugin Port 10.py", root);
if (!fs.existsSync(devPath)) { console.error("入力欠落: work/device_Forward CCs to current plugin Port 10.py (fetch_inputs.sh)"); process.exit(3); }
const source = fs.readFileSync(devPath, "utf8");

const engine = createMockEngine();
const acc = { n: 0, handlerMs: 0 };
const counted = {
  call: (name, args) => {
    const a = performance.now();
    const r = engine.call(name, args);
    acc.handlerMs += performance.now() - a;
    acc.n++;
    return r;
  },
};
const W = (n) => fs.readFileSync(new URL(`work/${n}`, root));
const files = { "/fl/Lib/utils.py": W("utils.py"), "/fl/Lib/midi.py": W("midi.py") };
const py = await FlPython.create({ flpyUrl: new URL("dist/flpy.js", root), engine: counted, ids, files, onStdout() {}, onStderr() {} });
await py.run("import fl_rt\nfl_rt.install_flapi()");
const host = new MidiScriptHost(py);
await host.loadDeviceScript({ name: "fwd", source, port: 0 });
await host.init();

const msg = Uint8Array.from([0xb0, 7, 100]);
const med = (a) => { const s = [...a].sort((x, y) => x - y); return s[s.length >> 1]; };
const per = [];
for (let t = 0; t < trials; t++) {
  for (let i = 0; i < 50; i++) await host.midiIn(msg, { port: 0 });
  acc.n = 0; acc.handlerMs = 0;
  const t0 = performance.now();
  for (let i = 0; i < events; i++) await host.midiIn(msg, { port: 0 });
  const totalMs = performance.now() - t0;
  per.push({
    total_us: +((totalMs * 1000) / events).toFixed(2),
    handler_us: +((acc.handlerMs * 1000) / events).toFixed(2),
    rest_us: +(((totalMs - acc.handlerMs) * 1000) / events).toFixed(2),
    flapi_per_event: +(acc.n / events).toFixed(3),
  });
}
const summary = {};
for (const k of ["total_us", "handler_us", "rest_us"]) summary[k] = med(per.map((x) => x[k]));
console.log(JSON.stringify({ events, trials, load: fs.readFileSync("/proc/loadavg", "utf8").trim(), median: summary, per_trial: per }));
await py.terminate();
