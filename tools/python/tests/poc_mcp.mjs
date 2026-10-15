// PoC: wasm CPython (Worker) + flapi モック(FLEngine 模擬, SAB 同期 RPC) 上で FL 同梱 MCPTools.pyc を実行する。
//   node tests/poc_mcp.mjs     (前提: fetch_inputs.sh / build_cpython_wasm.sh / build_flpy.sh / analysis 生成物)
import fs from "node:fs";
import assert from "node:assert/strict";
import { FlPython } from "../host/flpython.mjs";
import { createMockEngine } from "../host/fl_mock.mjs";
import { McpBridge } from "../host/mcp_rpc.mjs";

const root = new URL("../", import.meta.url);
const ids = JSON.parse(fs.readFileSync(new URL("analysis/flapi/flapi_ids.json", root)));
const engine = createMockEngine();
const stdout = [];
const t0 = performance.now();
const py = await FlPython.create({
  flpyUrl: new URL("dist/flpy.js", root),
  engine,
  ids,
  files: {
    "/fl/Lib/midi.py": fs.readFileSync(new URL("work/midi.py", root)),
    "/fl/Lib/utils.py": fs.readFileSync(new URL("work/utils.py", root)),
    "/fl/Tools/MCPTools.pyc": fs.readFileSync(new URL("work/MCPTools.pyc", root)),
  },
  onStdout: (t) => stdout.push(t),
  onStderr: (t) => stdout.push("ERR " + t),
});
const tInit = performance.now() - t0;

await py.run(`
import fl_rt
n = fl_rt.install_flapi()
print("flapi functions installed:", n)
m = fl_rt.load_pyc("/fl/Tools/MCPTools.pyc", "__main__")
print("MCPTools loaded as __main__; python", __import__("sys").version.split()[0])
`);

const tools = JSON.parse((await py.call("__main__:get_mcp_tools_json", {})).ok);
assert.equal(tools.length, 48, "FL の get_mcp_tools_json() と同じ 48 tools");

const call = async (name, args = {}) => {
  const r = await py.call(`__main__:${name}`, args);
  if (r.err) throw new Error(`${name}: ${r.err}\n${r.tb}`);
  return r.ok;
};

const results = {};
// --- tool 1: get_tempo / set_tempo (mixer.getCurrentTempo / setCurrentTempo) ---
results.get_tempo = await call("get_tempo");
await call("set_tempo", { bpm: 140 });
assert.equal(engine.state.tempo, 140);
results.get_tempo_after = await call("get_tempo");
// --- tool 2: play / stop (transport.start/stop) ---
await call("play");
assert.equal(engine.state.playing, true);
await call("stop");
assert.equal(engine.state.playing, false);
// --- tool 3: list_channel_names, set volume (dB), mute, rename, mixer ---
results.list_channel_names = await call("list_channel_names");
results.set_channels_volume_db = await call("set_channels_volume_db", { target_channels: "Kick", volume_db: "-6" });
assert.ok(engine.state.channels[0].vol < 0.78125);
results.rename_channels = await call("rename_channels", { channel_mapping: JSON.stringify({ Snare: "Clap" }) });
assert.equal(engine.state.channels[1].name, "Clap");
results.mute_channels = await call("mute_channels", { target_channels: "Clap", muted: 1 });
assert.equal(engine.state.channels[1].mute, true);
results.get_mixer_tracks_volume = await call("get_mixer_tracks_volume", { target_tracks: "1" });
results.set_mixer_routing = await call("set_mixer_routing", { source_track: "1", dest_track: "5", active: 1, level: 0.5 });
results.get_session_context = await call("get_session_context");
results.get_plugin_parameter_list = await call("get_plugin_parameter_list", { target: "3x Osc", slot_number: -1 });
results.set_plugin_parameter_value = await call("set_plugin_parameter_value", { target: "3x Osc", param_identifier: "Cutoff", value: 0.9, slot_number: -1 });
// PY-228 (#3656): 値は channel ごとに持つ (3x Osc = channel 2)。他 channel (Kick = 0) と params[] の既定値は変わらない
assert.ok(Math.abs(engine.state.channels[2].pv[0] - 0.9) < 1e-9);
assert.ok(Math.abs(engine.state.channels[0].pv[0] - 0.5) < 1e-9);
results.get_plugin_parameter_value = await call("get_plugin_parameter_value", { target: "3x Osc", param_identifier: "Cutoff", slot_number: -1 });
assert.match(results.get_plugin_parameter_value, /String Value: '90\.0 %'/);
results.add_channel = await call("add_channel", { plugin: "Fruity Slicer" });

// --- MIDI scripting 経路 (device script 相当) ---
await py.run(`
import sys
seen = []
def OnMidiMsg(msg):
    seen.append(("msg", msg.status, msg.data1, msg.data2))
def OnNoteOn(msg):
    seen.append(("noteon", msg.note, msg.velocity)); msg.handled = True
sys.modules["__main__"].OnMidiMsg = OnMidiMsg
sys.modules["__main__"].OnNoteOn = OnNoteOn
`);
const mid = await py.call("fl_rt:dispatch_midi", { fields_json: JSON.stringify({ status: 0x90, data1: 60, data2: 100 }) });
const midOut = JSON.parse(mid.ok);
assert.deepEqual(midOut.called, ["OnMidiMsg", "OnNoteOn"]);
assert.equal(midOut.msg.handled, true);

// --- MCP JSON-RPC 面 (TMCPServer 相当) ---
const mcp = new McpBridge(py);
const lst = await mcp.handle({ jsonrpc: "2.0", id: "1", method: "tools/list" });
assert.equal(lst.result.tools.length, 48);
assert.ok(lst.result.tools[0].inputSchema);
const tc = await mcp.handle({ jsonrpc: "2.0", id: "2", method: "tools/call", params: { name: "get_tempo", arguments: {} } });
assert.equal(tc.result.isError, false);
assert.match(tc.result.content[0].text, /Current tempo is 140/);
const bad = await mcp.handle({ jsonrpc: "2.0", id: "3", method: "tools/call", params: { name: "no_such_tool", arguments: {} } });
assert.equal(bad.result.isError, true);

// --- 計測: 往復コスト ---
const N = 2000;
const t1 = performance.now();
await py.run(`
import channels
for _ in range(${N}): channels.channelCount()
`);
const perCallUs = ((performance.now() - t1) * 1000) / N;

await py.terminate();

const apiUsed = [...new Set(engine.record.map((r) => r[0]))].sort();
const out = {
  tools: tools.length,
  init_ms: Math.round(tInit),
  host_calls: engine.record.length,
  distinct_api_called: apiUsed.length,
  roundtrip_us_per_flapi_call: Math.round(perCallUs),
  midi: midOut,
  mcp_jsonrpc: { list: lst.result.tools.length, call: tc.result.content[0].text, unknown_tool_isError: bad.result.isError },
  sample: {
    get_tempo: results.get_tempo, get_tempo_after: results.get_tempo_after,
    list_channel_names: results.list_channel_names,
    volume_db: results.set_channels_volume_db,
    plugin_param_list: results.get_plugin_parameter_list,
  },
};
console.log(JSON.stringify(out, null, 1));
console.log("python stdout:", stdout.join(" | "));
fs.writeFileSync(new URL("work/poc_result.json", root), JSON.stringify({ ...out, apiUsed, results }, null, 1));
console.log("POC OK");
