// 48 tools を wasm CPython(Worker)+モック上で全実行し、各 tool の成否と実際に呼ばれた flapi (引数個数付き) を記録する。
//   node tests/all_tools.mjs  ->  analysis/mcp/tool_coverage.json
import fs from "node:fs";
import { FlPython } from "../host/flpython.mjs";
import { createMockEngine } from "../host/fl_mock.mjs";
import { createWasmEngine } from "../host/fl_provider.mjs";

// FL_ENGINE=wasm: provider/ の C 実装 (fl_api_call) を使う。既定は JS モック。
//   wasm のとき analysis/mcp/tool_coverage.json は更新せず tool_coverage.wasm.json に書く。
const root = new URL("../", import.meta.url);
const ids = JSON.parse(fs.readFileSync(new URL("analysis/flapi/flapi_ids.json", root)));
const useWasm = process.env.FL_ENGINE === "wasm";
const engine = useWasm ? await createWasmEngine({ flprovUrl: new URL("dist/flprov.js", root), ids }) : createMockEngine();
const py = await FlPython.create({
  flpyUrl: new URL("dist/flpy.js", root), engine, ids,
  files: {
    "/fl/Lib/midi.py": fs.readFileSync(new URL("work/midi.py", root)),
    "/fl/Lib/utils.py": fs.readFileSync(new URL("work/utils.py", root)),
    "/fl/Tools/MCPTools.pyc": fs.readFileSync(new URL("work/MCPTools.pyc", root)),
  },
  onStdout: () => {}, onStderr: () => {},
});
await py.run(`import fl_rt; fl_rt.install_flapi(); fl_rt.load_pyc("/fl/Tools/MCPTools.pyc", "__main__")`);

const J = JSON.stringify;
const A = {
  get_session_context: {},
  get_browser_names: { name: "Plugin database", fullRecursive: 0 },
  show_or_hide_window: { window_name: "mixer", state: "show" },
  get_highlight_names: {},
  show_highlight: { item: "Toolbar: Show Mixer", tutorialName: "t", tutorialCaption: "c" },
  play: {}, stop: {}, get_tempo: {}, set_tempo: { bpm: 128 },
  list_channel_names: {},
  select_channels: { target_channels: "1,2", selected: 1 },
  rename_channels: { channel_mapping: J({ 1: "Kick2" }) },
  add_channel: { plugin: "Fruity Slicer" },
  route_channels_to_mixer: { target_channels: "1", mixer_track_target: "2" },
  get_channel_volumes: { target_channels: "all" },
  set_channels_volume_db: { target_channels: "1", volume_db: "-3" },
  set_channels_volume: { target_channels: "1", volume: "0.5" },
  set_channels_pan: { target_channels: "1", pan: "0.5" },
  set_channels_colour: { target_channels: "1", colour: "red" },
  mute_channels: { target_channels: "1", muted: 1 },
  solo_channels: { target_channels: "1", value: 1 },
  set_step_sequencer_step: { target_channels: "1", step_number: 1, value: 1 },
  set_step_sequencer_pattern: { target_channels: "1", pattern: "1000100010001000" },
  set_mixer_tracks_pan: { target_tracks: "1", pan: "-0.5" },
  get_mixer_tracks_volume: { target_tracks: "1,master" },
  set_mixer_tracks_volume_db: { target_tracks: "1", volume_db: "-6" },
  set_mixer_tracks_volume_percent: { target_tracks: "1", percent: "80" },
  rename_mixer_tracks: { track_mapping: J({ 1: "Drums" }) },
  add_effect: { plugin: "Fruity Reeverb 2", target_tracks: "1", slot_number: 1 },
  remove_effect: { target_tracks: "1", slot_numbers: "1" },
  set_mixer_tracks_colour: { target_tracks: "1", colour: "#ff0000" },
  mute_mixer_tracks: { target_tracks: "1", muted: 1 },
  solo_mixer_tracks: { target_tracks: "1", value: 1 },
  reset_mixer_tracks: { target_tracks: "1" },
  get_mixer_routing: {},
  set_mixer_routing: { source_track: "1", dest_track: "5", active: 1, level: 0.5 },
  reset_mixer_routing: { target_tracks: "1" },
  open_piano_roll_for_channel: { target_channel: "1" },
  quantize_channel: { channel_number: 1 },
  get_playlist_track_names: {},
  rename_playlist_tracks: { track_mapping: J({ 1: "Drums" }) },
  set_playlist_tracks_colour: { target_tracks: "1", colour: "blue" },
  get_plugin_parameter_list: { target: "3x Osc", slot_number: -1 },
  get_plugin_parameter_value: { target: "3x Osc", param_identifier: "Cutoff", slot_number: -1 },
  set_plugin_parameter_value: { target: "3x Osc", param_identifier: "Cutoff", value: 0.9, slot_number: -1 },
  save_piano_roll_script: { script_name: "demo", source: "def createDialog():\n    pass\n" },
  run_piano_roll_script: { source: "def apply(form):\n    pass\n" },
  remove_channels: { target_channels: "4" }, // 最後 (add_channel で追加した 4 番目を削除)
};
const tools = JSON.parse((await py.call("__main__:get_mcp_tools_json", {})).ok);
const cov = [];
for (const t of tools) {
  const args = A[t.name];
  if (args === undefined) { cov.push({ name: t.name, status: "no-args-defined" }); continue; }
  const before = engine.record.length;
  const r = await py.call(`__main__:${t.name}`, args);
  const calls = engine.record.slice(before).map(([n, a]) => `${n}/${a.length}`);
  const text = r.err ? r.err : String(r.ok);
  cov.push({
    name: t.name,
    status: r.err ? "raised" : /^(error|failed)/i.test(text) || /error/i.test(text.slice(0, 40)) ? "soft-error" : "ok",
    result: text.slice(0, 160),
    api_calls: [...new Set(calls)].sort(),
    host_calls: calls.length,
  });
}
// ilmcp.showHighlight に渡された Python callable (whenDone) をホスト側から呼び戻す
const hlId = useWasm ? engine.highlightCb() : engine.state.highlight?.cb?.__cb;
let cbOk = false;
if (hlId) { const r = await py.call("fl_rt:invoke_cb", { id: hlId, args: [] }); cbOk = !r.err; }
await py.terminate();
const by = (s) => cov.filter((c) => c.status === s).length;
const summary = { total: cov.length, ok: by("ok"), soft_error: by("soft-error"), raised: by("raised"), no_args: by("no-args-defined"), host_calls: engine.record.length, callback_roundtrip: cbOk };
fs.writeFileSync(new URL(useWasm ? "analysis/mcp/tool_coverage.wasm.json" : "analysis/mcp/tool_coverage.json", root), J({ summary, tools: cov }, null, 1));
console.log(J(summary));
for (const c of cov.filter((c) => c.status !== "ok")) console.log(c.status, c.name, (c.result || "").replace(/\n/g, " ").slice(0, 160));
