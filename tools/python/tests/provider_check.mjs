// flapi provider (C: fl_api_call) の ABI 検証: 表の整合・戻り型・エラー code・Python 例外写像。
//   node tests/provider_check.mjs     (前提: provider/build.sh と build_flpy.sh 済み)
import fs from "node:fs";
import assert from "node:assert/strict";
import { FlPython } from "../host/flpython.mjs";
import { createWasmEngine } from "../host/fl_provider.mjs";

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
let impl = 0, unimpl = 0;
for (const id of ids) {
  const r = direct(id, ...Array(40).fill(null).slice(0, 0));
  const notImpl = r.err?.startsWith("Unspecified error (not implemented:");
  if (mcp.has(id)) assert.ok(!notImpl, `MCP 使用 ${id} が未実装`);
  else assert.ok(notImpl, `${id} は未実装のはず`);
  notImpl ? unimpl++ : impl++;
}
assert.equal(impl, 60); assert.equal(unimpl, 375);

// 2. エラー code (C 側): range / wrong param / 型 / unspecified
const E = (name, ...a) => direct(name, ...a);
assert.deepEqual(E("channels.getChannelName", 999), { err: "Index out of range", code: 4 });
assert.deepEqual(E("mixer.getTrackName", -1), { err: "Index out of range", code: 4 });
assert.equal(E("channels.getChannelName").code, 5);                  // 引数不足
assert.equal(E("channels.getChannelName", 0, false, 7).code, 5);     // 引数過多
assert.equal(E("channels.getChannelName", "0").code, 5);             // 型違い
assert.equal(E("channels.setChannelName", 0, 5).code, 5);
assert.equal(E("channels.setChannelVolume", 0, "x").code, 5);
assert.equal(E("general.getVersion").code, 2);                       // 未実装 → Unspecified error
assert.equal(E("ilmcp.showHighlight", "a").code, 5);
assert.equal(E("mixer.getCurrentTempo", 1, 2).code, 5);

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
R.append(("kw", channels.getChannelName(index=0, useGlobalIndex=False)))
R.append(("json", type(ilmcp.getBrowserNames("db", 0)).__name__))
def exc(f, *a):
    try: f(*a)
    except Exception as e: return (type(e).__name__, str(e)[:40])
R.append(("range", exc(channels.getChannelName, 999)))
R.append(("type", exc(channels.getChannelName, "a")))
R.append(("unimpl", exc(__import__("general").getVersion)))
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
assert.deepEqual(m.json, ["dict"]);
assert.deepEqual(m.range[0], ["IndexError", "Index out of range"]);
assert.equal(m.type[0][0], "TypeError");
assert.equal(m.unimpl[0][0], "RuntimeError");
console.log(JSON.stringify({ functions: ids.length, implemented: impl, unimplemented: unimpl, mcp_static: mcp.size, PASS: true }));
