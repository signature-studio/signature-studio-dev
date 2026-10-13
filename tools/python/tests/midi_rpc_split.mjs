// PY-8 (#80): MIDI 1 イベント (CC) の所要時間を「RPC 1 往復」「flapi ハンドラ」「Python 側の残り」に分ける。
//   node tests/midi_rpc_split.mjs [events=5000] [trials=5] [calls=20000]
// 分け方 (py_worker.mjs は改変しない):
//   rpc_rt_us   : 同一 Python プロセス内で channels.channelCount() の loop と、RPC を通さない同形 loop の差分 (1 呼出し当り)。
//                 同じ試行内で交互に計測し、負荷の揺れを揃える。
//   handler_us  : counted.call (mock engine) の時間。
//   python_us   : CC total − handler − rpc_rt (Python 配送 + device script 実行、RPC 往復を除く)。
//   NoteOn (flapi 0 回) は対照。CC − NoteOn が「flapi 1 回 + device script の CC 分岐」に当たる。
// 注意: 所要時間は mock engine (JS) の処理を含む。実 FLEngine の処理時間は含まない。
// 前提: dist/flpy.js (build_flpy.sh 済み)、work/device_Forward CCs to current plugin Port 10.py (fetch_inputs.sh 済み)。
import fs from "node:fs";
import { FlPython } from "../host/flpython.mjs";
import { createMockEngine } from "../host/fl_mock.mjs";
import { MidiScriptHost } from "../host/midi_host.mjs";

const root = new URL("../", import.meta.url);
const events = Number(process.argv[2] || 5000);
const trials = Number(process.argv[3] || 5);
const calls = Number(process.argv[4] || 20000);
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
await py.run("import channels\ndef _noop():\n    return 0");
const host = new MidiScriptHost(py);
await host.loadDeviceScript({ name: "fwd", source, port: 0 });
await host.init();

const ccMsg = Uint8Array.from([0xb0, 7, 100]);
const onMsg = Uint8Array.from([0x90, 60, 100]);
const med = (a) => { const s = [...a].sort((x, y) => x - y); return s[s.length >> 1]; };

const perCall = async (body) => {
  const t = performance.now();
  await py.run(`for _ in range(${calls}): ${body}`);
  return ((performance.now() - t) * 1000) / calls;
};
const rpcRt = [], cc = [], note = [], handler = [], python = [];
for (let t = 0; t < trials; t++) {
  const rpcWith = await perCall("channels.channelCount()");
  const rpcWithout = await perCall("_noop()");
  rpcRt.push(rpcWith - rpcWithout);

  for (let i = 0; i < 50; i++) await host.midiIn(ccMsg, { port: 0 });
  acc.n = 0; acc.handlerMs = 0;
  let t0 = performance.now();
  for (let i = 0; i < events; i++) await host.midiIn(ccMsg, { port: 0 });
  const ccTotal = ((performance.now() - t0) * 1000) / events;
  const ccHandler = (acc.handlerMs * 1000) / events;
  if (acc.n / events !== 1) throw new Error(`CC の flapi 呼出しが 1 件/イベントではない: ${acc.n / events}`);
  cc.push(ccTotal);
  handler.push(ccHandler);
  python.push(ccTotal - ccHandler - (rpcWith - rpcWithout));

  for (let i = 0; i < 50; i++) await host.midiIn(onMsg, { port: 0 });
  t0 = performance.now();
  for (let i = 0; i < events; i++) await host.midiIn(onMsg, { port: 0 });
  note.push(((performance.now() - t0) * 1000) / events);
}
const summary = {
  rpc_rt_us: med(rpcRt),
  cc_total_us: med(cc),
  cc_handler_us: med(handler),
  cc_python_us: med(python),
  noteon_total_us: med(note),
};
const r = (o) => Object.fromEntries(Object.entries(o).map(([k, v]) => [k, +v.toFixed(2)]));
console.log(JSON.stringify({
  events, trials, calls,
  load: fs.readFileSync("/proc/loadavg", "utf8").trim(),
  median: r(summary),
  per_trial: { rpc_rt_us: rpcRt.map((x) => +x.toFixed(2)), cc_total_us: cc.map((x) => +x.toFixed(2)), noteon_total_us: note.map((x) => +x.toFixed(2)) },
}));
await py.terminate();
