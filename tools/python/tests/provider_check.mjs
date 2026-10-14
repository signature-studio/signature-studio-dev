// flapi provider (C: fl_api_call) の ABI 検証: 表の整合・戻り型・エラー code・Python 例外写像。
//   node tests/provider_check.mjs     (前提: provider/build.sh と build_flpy.sh 済み)
import fs from "node:fs";
import assert from "node:assert/strict";
import { FlPython } from "../host/flpython.mjs";
import { createWasmEngine } from "../host/fl_provider.mjs";
import { createMockEngine } from "../host/fl_mock.mjs";

const root = new URL("../", import.meta.url);
const ids = JSON.parse(fs.readFileSync(new URL("analysis/flapi/flapi_ids.json", root)));
const table = JSON.parse(fs.readFileSync(new URL("analysis/flapi/flapi_table.json", root)));
const engine = await createWasmEngine({ flprovUrl: new URL("dist/flprov.js", root), ids });

// 1. 表の整合: ids = table 列挙順、MCP 静的参照 60 (公開 52 + ilmcp 8) が全て実装済み、それ以外は Unspecified error
const flat = Object.entries(table.modules).flatMap(([m, fs_]) => Object.keys(fs_).map((n) => `${m}.${n}`));
assert.deepEqual(flat, ids);
const mcp = new Set(Object.entries(table.modules).flatMap(([m, fs_]) => Object.entries(fs_).filter(([, v]) => v.mcp_tools.length).map(([n]) => `${m}.${n}`)));
assert.equal(mcp.size, 60);
const direct = (name, ...a) => { try { return { ok: engine.call(name, a) }; } catch (e) { return { err: e.message, code: e.flCode }; } };
const dev = new Set(["device.getPortNumber", "device.isAssigned", "device.setHasMeters", "device.forwardMIDICC", "device.midiOutMsg"]);
// 実装 = mock (host/fl_mock.mjs・host/ilmcp.mjs) が持つ MIDI 経路の 5 関数 (PY-20)
const mig = new Set(["channels.selectedChannel", "channels.fillEachNSteps", "general.getVersion", "transport.isPlaying", "ilmcp.forwardTutorialEvent"]);
// PE 解析で意味論を確定した関数 (REPORT_PY69・PY-69 #2499)。channels.setChannelPitch は未確定のため含めない
const pe39 = new Set(["channels.selectOneChannel"]);
// 公開 stub の戻り型・説明で意味論を決めた 6 関数 (REPORT_PY41 追補・REPORT_PY41_1514 追補・PY-41 #1514)。PE での範囲外 code 確認は未了
const stub41 = new Set(["channels.isChannelMuted", "channels.isChannelSolo", "channels.getChannelColor", "channels.getGridBit", "channels.channelNumber", "channels.getChannelType"]);
const pe100 = new Set(["channels.getStepParam", "channels.getCurrentStepParam"]);
// PE で状態読出しと確認した general ゲッター 4 件 (REPORT_PY87・PY-87 #2738)。値は未実測の仮置き、tests/general_diff.mjs が mock と照合
const pe87 = new Set(["general.getChangedFlag", "general.getUseMetronome", "general.getPrecount", "general.getRecPPQ"]);
// PE で dispatch 0xd843d0 経由の戻り値 None を確定した 2 関数 (REPORT_PY125・PY-125 #3001)。効果と述語偽の経路 (-2) は未確定 (REPORT_PY125)
const pe125 = new Set(["general.clearLog", "general.dumpScoreLog"]);
// stub 確定 2 関数 (REPORT_PY41_1514 追補 #2805・PY-89)。PE 0xd5bd60 / 0xd5bcd0 で範囲検査と戻り field を確認
const stub89 = new Set(["channels.getChannelIndex", "channels.getChannelMidiInPort"]);
// PE 0xd5ec60 で取得式を確定した 1 関数 (REPORT_PY115 §2・PY-115 #2951)
const pe115 = new Set(["mixer.getTrackColor"]);
let impl = 0, unimpl = 0;
for (const id of ids) {
  const r = direct(id, ...Array(40).fill(null).slice(0, 0));
  const notImpl = r.err?.startsWith("Unspecified error (not implemented:");
  if (mcp.has(id) || dev.has(id) || mig.has(id) || pe39.has(id) || stub41.has(id) || pe100.has(id) || stub89.has(id) || pe87.has(id) || pe115.has(id) || pe125.has(id)) assert.ok(!notImpl, `実装済みのはず: ${id} が未実装`);
  else assert.ok(notImpl, `${id} は未実装のはず`);
  notImpl ? unimpl++ : impl++;
}
// 実装 = MCP 静的 60 + device 5 (MIDI scripting 用、tests/device_diff.mjs が mock と照合) + MIDI 経路 5 (mig) + PE 確定 1 (pe39) + stub 確定 6 (stub41) + PE 確定 2 (pe100) + stub 確定 2 (stub89) + PE 確定 4 (pe87) + PE 確定 1 (pe115) + PE 確定 2 (pe125)
assert.equal(impl, 88); assert.equal(unimpl, 347);

// 2. エラー code (C 側): range / wrong param / 型 / unspecified
const E = (name, ...a) => direct(name, ...a);
assert.deepEqual(E("channels.getChannelName", 999), { err: "Index out of range", code: 4 });
assert.deepEqual(E("mixer.getTrackName", -1), { err: "Index out of range", code: 4 });
assert.equal(E("channels.getChannelName").code, 5);                  // 引数不足
assert.equal(E("channels.getChannelName", 0, false, 7).code, 5);     // 引数過多
assert.equal(E("channels.getChannelName", "0").code, 5);             // 型違い
assert.equal(E("channels.setChannelName", 0, 5).code, 5);
assert.equal(E("channels.setChannelVolume", 0, "x").code, 5);
assert.equal(E("general.saveUndo").code, 2);                         // 未実装 → Unspecified error
assert.equal(E("ilmcp.showHighlight", "a").code, 5);
assert.equal(E("mixer.getCurrentTempo", 1, 2).code, 5);

// 2b. ilmcp.getBrowserNames は host/ilmcp.mjs と同じ木を返す (JS 側の期待値を独立に計算して照合)。
//   不明パス・長大な入力は code 1 (Invalid value) の FL エラーになり、engine は壊れない。
const ILM = JSON.parse(fs.readFileSync(new URL("analysis/ilmcp/plugin_catalog.json", root))).entries;
const expectList = (path, rec) => {
  const parts = path.split("/").map((s) => s.trim()).filter(Boolean);
  const tree = { dirs: new Map(), items: [] };
  for (const e of ILM) {
    let m = tree;
    for (const d of e.path) { if (!m.dirs.has(d)) m.dirs.set(d, { dirs: new Map(), items: [] }); m = m.dirs.get(d); }
    m.items.push(e);
  }
  let n = tree;
  for (const d of parts.slice(1)) n = n.dirs.get(d);
  const out = [];
  const walk = (node, prefix) => {
    for (const d of [...node.dirs.keys()].sort((a, b) => a.localeCompare(b))) {
      out.push(`${prefix}${d}/`);
      if (rec) walk(node.dirs.get(d), `${prefix}${d}/`);
    }
    for (const e of [...node.items].sort((a, b) => a.name.localeCompare(b.name))) out.push(`${prefix}${e.name}`);
  };
  walk(n, "");
  return out;
};
for (const [p, r] of [["Plugin database", 0], ["Plugin database", 1], ["Plugin database/Generators/Drum", 0], ["Plugin database/Effects", 1]]) {
  assert.deepEqual(E("ilmcp.getBrowserNames", p, r).ok, expectList(p, r), `getBrowserNames(${p}, ${r})`);
}
assert.equal(E("ilmcp.getBrowserNames", "Nowhere", 0).code, 1);
assert.equal(E("ilmcp.getBrowserNames", "Plugin database/Nope", 1).code, 1);
assert.equal(E("ilmcp.getBrowserNames", "\x01".repeat(100000), 0).code, 1);
assert.equal(E("general.saveUndo").code, 2);                         // 直後も engine は正常

// 3. 戻り型は C 側 (整数値の float でも D): Python 側で type を見る
const py = await FlPython.create({
  flpyUrl: new URL("dist/flpy.js", root), engine, ids, files: { "/fl/Lib/midi.py": fs.readFileSync(new URL("work/midi.py", root)) },
  onStdout: () => {}, onStderr: () => {},
});
await py.run(`
import fl_rt
fl_rt.install_flapi()
import channels, mixer, plugins, ilmcp
R = []
channels.setChannelVolume(0, 1)            # int 引数 → float 引数に変換
R.append(("vol", type(channels.getChannelVolume(0)).__name__, channels.getChannelVolume(0)))
mixer.setTrackPan(1, 0)
R.append(("pan", type(mixer.getTrackPan(1)).__name__))
R.append(("tempo_f", type(mixer.getCurrentTempo()).__name__))
R.append(("tempo_i", type(mixer.getCurrentTempo(True)).__name__))
R.append(("cnt", type(channels.channelCount()).__name__))
R.append(("sel", type(channels.isChannelSelected(0)).__name__))
R.append(("none", mixer.setTrackName(1, "x")))
R.append(("kw", channels.getChannelName(value=0, useGlobalIndex=False)))  # kwlist はバイナリ由来 (stubs の index ではなく value)
R.append(("json", type(ilmcp.getBrowserNames("Plugin database", 0)).__name__))
def exc(f, *a):
    try: f(*a)
    except Exception as e: return (type(e).__name__, str(e)[:40])
R.append(("range", exc(channels.getChannelName, 999)))
R.append(("type", exc(channels.getChannelName, "a")))
R.append(("unimpl", exc(__import__("general").saveUndo)))
import json
RESULT = json.dumps(R)
`);
const lines = [];
py.onStdout = (t) => lines.push(t);
await py.run(`print("RES" + RESULT)`);
await py.terminate();
const res = JSON.parse(lines.find((l) => l.startsWith("RES")).slice(3));
const m = Object.fromEntries(res.map((x) => [x[0], x.slice(1)]));
assert.deepEqual(m.vol, ["float", 1.0]);
assert.deepEqual(m.pan, ["float"]);
assert.deepEqual(m.tempo_f, ["float"]);
assert.deepEqual(m.tempo_i, ["int"]);
assert.deepEqual(m.cnt, ["int"]);
assert.deepEqual(m.sel, ["bool"]);
assert.deepEqual(m.none, [null]);
assert.deepEqual(m.kw, ["Kick"]);
assert.deepEqual(m.json, ["list"]);
assert.deepEqual(m.range[0], ["IndexError", "Index out of range"]);
assert.equal(m.type[0][0], "TypeError");
assert.equal(m.unimpl[0][0], "RuntimeError");
// 6. 省略表現: 引数の None は省略 (既定値) と同じ。JS mock (fl_mock.mjs) と C provider で結果が一致する
const mock = createMockEngine();
for (const a of [[0], [0, null], [0, -1]]) {
  assert.equal(engine.call("plugins.getPluginName", a), mock.call("plugins.getPluginName", a), `getPluginName(${a})`);
}
console.log(JSON.stringify({ functions: ids.length, implemented: impl, unimplemented: unimpl, mcp_static: mcp.size, PASS: true }));
