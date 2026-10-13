// ilmcp 9 関数 (PY-3 / #82) の e2e: wasm CPython 上で FL 同梱 MCPTools.pyc の class B 8 tool + U 2 tool を実行し、
// 戻り値だけでなく FLEngine 側の状態 (チャンネル/ミキサースロット/PRScript) を検査する。
//   node tests/ilmcp_e2e.mjs                 -> PASS/FAIL (exit code)
//   node tests/ilmcp_e2e.mjs --negative X    -> ilmcp.X を壊した engine で実行し、FAIL することを確認 (exit 0 = 期待どおり FAIL)
import fs from "node:fs";
import { FlPython } from "../host/flpython.mjs";
import { createMockEngine } from "../host/fl_mock.mjs";

const root = new URL("../", import.meta.url);
const negIdx = process.argv.indexOf("--negative");
const negative = negIdx > 0 ? process.argv[negIdx + 1] : null;

const engine = createMockEngine();
if (negative) {
  const orig = engine.call.bind(engine);
  engine.call = (n, a) => (n === `ilmcp.${negative}` ? (negative === "getBrowserNames" ? [] : true) : orig(n, a));
}
const ids = JSON.parse(fs.readFileSync(new URL("analysis/flapi/flapi_ids.json", root)));
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

const st = engine.state;
const tool = async (name, args) => {
  const r = await py.call(`__main__:${name}`, args);
  return r.err !== undefined ? { err: r.err } : { ok: r.ok };
};
const results = [];
const check = (name, cond, detail = "") => results.push({ name, pass: !!cond, detail: cond ? "" : String(detail).slice(0, 200) });
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const t0 = performance.now();

// --- get_browser_names (B)
const top = (await tool("get_browser_names", { name: "Plugin database", fullRecursive: 0 })).ok;
check("browser: root children", eq(top, ["Effects/", "Generators/", "Installed/"]), JSON.stringify(top));
const all = (await tool("get_browser_names", { name: "Plugin database", fullRecursive: 1 })).ok ?? [];
const gens = all.filter((p) => p.startsWith("Generators/") && !p.endsWith("/"));
const fxs = all.filter((p) => p.startsWith("Effects/") && !p.endsWith("/"));
check("browser: recursive counts (57 native gen / 79 native fx)", gens.length === 57 && fxs.length === 79, `${gens.length}/${fxs.length}`);
check("browser: recursive has installed OTT", all.includes("Installed/Effects/VST/OTT"), "");
const sub = (await tool("get_browser_names", { name: "Plugin database/Generators/Drum", fullRecursive: 0 })).ok;
check("browser: subfolder lists leaf plugins", Array.isArray(sub) && sub.length === 10 && sub.every((x) => !x.endsWith("/")), JSON.stringify(sub));
const bad = await tool("get_browser_names", { name: "Nowhere", fullRecursive: 0 });
check("browser: unknown path -> error", bad.err !== undefined, JSON.stringify(bad));

// --- add_channel / remove_channels (B)
const n0 = st.channels.length;
const a1 = await tool("add_channel", { plugin: "Fruity Slicer" });
check("add_channel: ok text", /^Successfully added Fruity Slicer/.test(a1.ok ?? ""), JSON.stringify(a1));
check("add_channel: state +1, plugin set", st.channels.length === n0 + 1 && st.channels.at(-1).plugin === "Fruity Slicer", `${st.channels.length}`);
const a2 = await tool("add_channel", { plugin: "Fruity Reeverb 2" }); // effect は channel rack に追加不可
check("add_channel: effect name rejected, state unchanged", a2.err !== undefined && st.channels.length === n0 + 1, JSON.stringify(a2));
const a3 = await tool("add_channel", { plugin: "Fruity Slicer.fst" }); // MCPTools が拡張子を落とす
check("add_channel: extension stripped", st.channels.length === n0 + 2 && st.channels.at(-1).plugin === "Fruity Slicer", `${st.channels.length}`);
const names = () => st.channels.map((c) => c.name);
const r1 = await tool("remove_channels", { target_channels: `${n0 + 1},${n0 + 2}` });
check("remove_channels: ok text", /^Successfully removed 2 channel/.test(r1.ok ?? ""), JSON.stringify(r1));
check("remove_channels: state back to n0, originals intact", st.channels.length === n0 && eq(names(), ["Kick", "Snare", "3x Osc"]), JSON.stringify(names()));

// --- add_effect / remove_effect / reset_mixer_tracks (B)
const ae = await tool("add_effect", { plugin: "Fruity Reeverb 2", target_tracks: "1,2", slot_number: 3 });
check("add_effect: ok text", /^Added effect 'Fruity Reeverb 2' to visual slot 3/.test(ae.ok ?? ""), JSON.stringify(ae));
check("add_effect: visual slot 3 -> api slot index 2 on tracks 1,2 only",
  st.mixer[1].slots[2] === "Fruity Reeverb 2" && st.mixer[2].slots[2] === "Fruity Reeverb 2" && !st.mixer[3].slots[2], JSON.stringify(st.mixer[1].slots));
const ae2 = await tool("add_effect", { plugin: "Nope Reverb", target_tracks: "1", slot_number: 4 });
check("add_effect: unknown plugin rejected (no slot written)", !st.mixer[1].slots[3] && !/^Added/.test(ae2.ok ?? ""), JSON.stringify(ae2));
const ae3 = await tool("add_effect", { plugin: "Fruity Slicer", target_tracks: "1", slot_number: 4 }); // generator は不可
check("add_effect: generator name rejected", !st.mixer[1].slots[3], JSON.stringify(ae3));
await tool("add_effect", { plugin: "Fruity Compressor", target_tracks: "2", slot_number: 1 });
const re = await tool("remove_effect", { target_tracks: "1", slot_numbers: "3" });
check("remove_effect: slot cleared on track 1, track 2 kept",
  !st.mixer[1].slots[2] && st.mixer[2].slots[2] === "Fruity Reeverb 2" && st.mixer[2].slots[0] === "Fruity Compressor", `${JSON.stringify(re)} ${JSON.stringify(st.mixer[2].slots)}`);
const rst = await tool("reset_mixer_tracks", { target_tracks: "2" });
check("reset_mixer_tracks: all 10 slots cleared + name restored",
  st.mixer[2].slots.every((s) => !s) && st.mixer[2].name === "Insert 2", `${JSON.stringify(rst)} ${JSON.stringify(st.mixer[2].slots)}`);

// --- save_piano_roll_script / run_piano_roll_script (B)
const src = "def createDialog():\n    pass\n\ndef apply(form):\n    pass\n";
const sv = await tool("save_piano_roll_script", { script_name: "demo", source: src });
check("save_piano_roll_script: stored verbatim", /Successfully saved/.test(sv.ok ?? "") && st.prScripts.demo === src, JSON.stringify(sv));
const svBad = await tool("save_piano_roll_script", { script_name: "../evil", source: src });
check("save_piano_roll_script: path-like name rejected", svBad.err !== undefined && !("../evil" in st.prScripts), JSON.stringify(svBad));
let ran = null;
st.prRunner = (s) => { ran = s; };
const ru = await tool("run_piano_roll_script", { source: src });
check("run_piano_roll_script: piano roll window shown + source delivered", ru.err === undefined && st.windows[4] === true && ran === src, `${JSON.stringify(ru)} win=${JSON.stringify(st.windows)}`);

// --- get_highlight_names / show_highlight (U)
const hn = (await tool("get_highlight_names", {})).ok;
check("highlight names: 21 from FLEngine rodata", typeof hn === "string" ? hn.includes("Toolbar: Show Piano Roll") && hn.includes("Toolbar: Song mode") : (Array.isArray(hn) && hn.length === 21), JSON.stringify(hn)?.slice(0, 120));
const sh = await tool("show_highlight", { item: "Toolbar: Show Mixer", tutorialName: "t", tutorialCaption: "c" });
check("show_highlight: ok text + state", /^Success/.test(sh.ok ?? "") && st.highlight?.item === "Toolbar: Show Mixer" && st.highlight.cb?.__cb, JSON.stringify(sh));
const shBad = await tool("show_highlight", { item: "Toolbar: Show Piano roll", tutorialName: "t", tutorialCaption: "c" }); // 実機は大文字 R
check("show_highlight: wrong-case name rejected (real-machine spelling is 'Piano Roll')", !/^Success/.test(shBad.ok ?? ""), JSON.stringify(shBad));
const cbId = st.highlight?.cb?.__cb;
const cb = cbId ? await py.call("fl_rt:invoke_cb", { id: cbId, args: [] }) : { err: "no callback registered" };
check("show_highlight: whenDone callable called back from host", !cb.err, JSON.stringify(cb));
check("show_highlight: whenDone re-enters ilmcp.showHighlight('','','') -> highlight cleared", st.highlight?.item === "" && st.highlight?.name === "" && st.highlight?.caption === "", JSON.stringify(st.highlight)?.slice(0, 120));

await py.terminate();
const failed = results.filter((r) => !r.pass);
const summary = { checks: results.length, pass: results.length - failed.length, fail: failed.length, ms: Math.round(performance.now() - t0), negative };
for (const f of failed) console.log("FAIL", f.name, f.detail);
console.log(JSON.stringify(summary));
if (negative) { console.log(failed.length ? `NEGATIVE-CONTROL OK (ilmcp.${negative} 破壊で ${failed.length} 件 FAIL)` : "NEGATIVE-CONTROL NOT DETECTED"); process.exit(failed.length ? 0 : 1); }
console.log(failed.length ? "FAIL" : "PASS");
process.exit(failed.length ? 1 : 0);
