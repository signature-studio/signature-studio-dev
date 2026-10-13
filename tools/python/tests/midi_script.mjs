// PY-6 (#76) e2e: MIDI scripting ホスト (device script ローダ / 27 callback 配送 / Web MIDI 結線)。
//   node tools/python/tests/midi_script.mjs [--neg | --neg-legacy]
//   PASS: "MIDI SCRIPT OK {...}" exit 0 / FAIL: exit 2 / --neg で壊した入力を検出できたとき: "NEG-CONTROL DETECTED" exit 1 (検出できなければ exit 2)
// 前提: tools/python/dist/ (build_flpy.sh)。FL 由来ファイルは不要 (fixtures/ は本 repo の合成スクリプト。FL 同梱の device script ではない)。
//   --neg: recorder の OnDirtyChannel を消して供給 → 「27 callback 全て配送」の判定が FAIL することを確認する。
//   --neg-legacy (#601): fl_rt.load_device_script を旧実装 (登録してから exec) に差し戻す → 「読込失敗後に script が残らない」系の check が FAIL することを確認する。
import fs from "node:fs";
import assert from "node:assert/strict";
import { FlPython } from "../host/flpython.mjs";
import { createMockEngine } from "../host/fl_mock.mjs";
import { MidiScriptHost, parseMidiBytes } from "../host/midi_host.mjs";

const neg = process.argv.includes("--neg");
const negLegacy = process.argv.includes("--neg-legacy");
const root = new URL("../", import.meta.url);
const fx = (n) => fs.readFileSync(new URL(`tests/fixtures/${n}`, root), "utf8");
const ids = JSON.parse(fs.readFileSync(new URL("analysis/flapi/flapi_ids.json", root)));
const table = JSON.parse(fs.readFileSync(new URL("analysis/flapi/flapi_table.json", root)));

const checks = {};
const detail = {};
const check = (name, cond, extra) => {
  checks[name] = !!cond;
  if (!cond) console.error(`FAIL ${name}`, extra === undefined ? "" : JSON.stringify(extra));
};

const engine = createMockEngine();
const stdout = [];
const stderr = [];
const py = await FlPython.create({
  flpyUrl: new URL("dist/flpy.js", root), engine, ids,
  onStdout: (t) => stdout.push(t), onStderr: (t) => stderr.push(t),
});
await py.run("import fl_rt\nfl_rt.install_flapi()");
const host = new MidiScriptHost(py);

// ---- 1. 配送表 27 個 = FLEngine rodata の pycb* 27 個 / 引数は公開 stubs の署名 ----
const cbTable = await host.callbackTable();
const names = Object.keys(cbTable).sort();
const inBinary = [...table.midi_script_callbacks_in_binary].sort();
check("callback table == FLEngine rodata pycb* (27, OnInitAll 含む)", names.length === 27 && JSON.stringify(names) === JSON.stringify(inBinary), { names: names.length, inBinary: inBinary.length });
const argMismatch = Object.entries(table.midi_script_callbacks).filter(([k, a]) => JSON.stringify(cbTable[k]?.args) !== JSON.stringify(a));
check("callback args == 公開 stubs 署名 (26)", argMismatch.length === 0 && Object.keys(table.midi_script_callbacks).length === 26, argMismatch);
detail.callbacks = { total: names.length, byKind: Object.fromEntries(["lifecycle", "midi", "midi_out", "host"].map((k) => [k, names.filter((n) => cbTable[n].kind === k).length])) };

// ---- 2. 27 callback の配送 (recorder: 全 callback を定義) ----
const recSrc = fx("device_recorder.py") + (neg ? "\ndel OnDirtyChannel\n" : "");
const rec = await host.loadDeviceScript({ name: "rec", source: recSrc, port: null });
check("loader: 27 callback を定義した script を読込み (meta name を取得)", (neg ? rec.callbacks.length === 26 : rec.callbacks.length === 27) && /^PY-6 recorder/.test(rec.meta.name), rec);
const take = async () => (await py.call(`${rec.module}:take`, {})).ok;
const flags = (hi, hm) => py.call(`${rec.module}:set_flags`, { handle_in: hi, handle_msg: hm });

const initR = await host.init();
check("init: OnInit → OnInitAll の順で 1 回ずつ", JSON.stringify(await take()) === JSON.stringify([["OnInit", []], ["OnInitAll", []]]), initR);

const hostCalls = [
  ["OnDeInit", []], ["OnIdle", []], ["OnProjectLoad", [100]], ["OnRefresh", [4]], ["OnDoFullRefresh", []],
  ["OnUpdateBeatIndicator", [2]], ["OnDisplayZone", []], ["OnUpdateLiveMode", [3]], ["OnDirtyMixerTrack", [5]],
  ["OnDirtyChannel", [-1]], ["OnFirstConnect", []], ["OnUpdateMeters", []], ["OnWaitingForInput", []],
  ["OnSendTempMsg", ["hello", 1500]],
];
const delivered = new Set(["OnInit", "OnInitAll"]);
for (const [cb, args] of hostCalls) {
  await host.callback(cb, args);
  const got = await take();
  const ok = JSON.stringify(got) === JSON.stringify([[cb, args]]);
  if (ok) delivered.add(cb);
  else if (!neg) check(`delivery ${cb}`, false, got);
}
{
  const f = { status: 0x90, data1: 60, data2: 100, port: 0 };
  await host.callback("OnMidiOutMsg", [f]);
  const got = await take();
  const ok = got.length === 1 && got[0][0] === "OnMidiOutMsg" && got[0][1][0].status === 0x90 && got[0][1][0].data1 === 60 && got[0][1][0].data2 === 100;
  if (ok) delivered.add("OnMidiOutMsg");
  else check("delivery OnMidiOutMsg", false, got);
}
const midiCases = [
  [[0x80, 60, 0], "OnNoteOff"], [[0x90, 60, 100], "OnNoteOn"], [[0xa0, 60, 33], "OnKeyPressure"], [[0xb0, 7, 99], "OnControlChange"],
  [[0xc0, 5], "OnProgramChange"], [[0xd0, 44], "OnChannelPressure"], [[0xe0, 0, 64], "OnPitchBend"], [[0xf0, 0x7d, 1, 2, 0xf7], "OnSysEx"],
];
for (const [bytes, typeCb] of midiCases) {
  await host.midiIn(Uint8Array.from(bytes), { port: 0 });
  const got = (await take()).map((x) => x[0]);
  const ok = JSON.stringify(got) === JSON.stringify(["OnMidiIn", "OnMidiMsg", typeCb]);
  if (ok) { delivered.add("OnMidiIn"); delivered.add("OnMidiMsg"); delivered.add(typeCb); }
  else check(`midi order ${typeCb}`, false, got);
}
check("27 callback 全てが想定引数で 1 回ずつ配送", delivered.size === 27 && names.every((n) => delivered.has(n)), { delivered: delivered.size, missing: names.filter((n) => !delivered.has(n)) });

// ---- 3. handled による伝播停止 (公開 stubs 文書: callback が返った時点で handled なら以降を呼ばない) ----
await flags(true, false);
await host.midiIn(Uint8Array.from([0x90, 60, 100]));
check("OnMidiIn で handled → OnMidiIn のみ", JSON.stringify((await take()).map((x) => x[0])) === '["OnMidiIn"]');
await flags(false, true);
await host.midiIn(Uint8Array.from([0x90, 60, 100]));
check("OnMidiMsg で handled → OnNoteOn は呼ばれない", JSON.stringify((await take()).map((x) => x[0])) === '["OnMidiIn","OnMidiMsg"]');
await flags(false, false);
await host.midiIn(Uint8Array.from([0xf8])); // MIDI clock: 型別 callback なし
check("型別 callback の無い実時間メッセージ (0xF8) は OnMidiIn/OnMidiMsg のみ", JSON.stringify((await take()).map((x) => x[0])) === '["OnMidiIn","OnMidiMsg"]');
await host.midiIn(Uint8Array.from([0xf0, 0x10, 0x20, 0x30, 0xf7]));
const sx = (await take()).find((x) => x[0] === "OnSysEx");
check("sysex は status=0xF0 + 全バイト列", sx && sx[1][0].status === 0xf0 && JSON.stringify(sx[1][0].sysex) === "[240,16,32,48,247]", sx);

// ---- 4. 複数 script: ポート振分け / 例外隔離 / 再読込 ----
await host.loadDeviceScript({ name: "boom", source: fx("device_raises.py"), port: 1 });
const fwd = await host.loadDeviceScript({ name: "fwd", source: fx("device_forward_cc.py"), port: 1 });
check("script ごとに独立 module", new Set([rec.module, fwd.module]).size === 2 && fwd.callbacks.join() === "OnInit,OnMidiIn,OnMidiMsg", fwd);
const r0 = await host.midiIn(Uint8Array.from([0x90, 61, 90]), { port: 0 });
check("port=0 の event は port=0 を受ける rec だけ (port None の rec のみ、port 1 の boom/fwd へは行かない)", r0.results.map((x) => x.script).join() === "rec", r0.results.map((x) => x.script));
await take();
const stderrBefore = stderr.length;
const r1 = await host.midiIn(Uint8Array.from([0x90, 62, 90]), { port: 1 });
check("port=1 の event は rec(port なし) / boom / fwd", r1.results.map((x) => x.script).sort().join() === "boom,fwd,rec", r1.results.map((x) => x.script));
const boom = r1.results.find((x) => x.script === "boom");
check("script の例外は errors に記録され traceback が stderr に出る (他 script の配送は継続)",
  boom.errors.length === 1 && /fixture boom/.test(boom.errors[0].err) && stderr.slice(stderrBefore).join("\n").includes("fixture boom") && r1.results.find((x) => x.script === "rec").called.includes("OnNoteOn"), { boom, stderr: stderr.slice(stderrBefore).length });
await take();
const initFwd = await host.init("fwd");
check("script 指定の init (fwd のみ) → fwd.OnInit が device.getPortNumber を呼ぶ", stdout.some((l) => /fixture forward-cc init, port 0/.test(l)) && initFwd[0].results.length === 1, stdout);

const rej = async (p) => { try { await p; return null; } catch (e) { return String(e.message); } };

// ---- 4b. top-level 例外で読込に失敗した script は登録されない (#601): reject / list / sys.modules / 配送 / 同名再読込 ----
if (negLegacy) {
  // 旧実装 (_scripts へ登録してから exec) に差し戻す。回帰 check だけが FAIL することの確認用
  await py.run(`
import sys, types, json, fl_rt
def _legacy_load(name, source=None, path=None, port=None):
    meta = fl_rt.parse_meta(source)
    if name in fl_rt._scripts:
        fl_rt.unload_device_script(name)
    key = "fl_device_%d" % next(fl_rt._script_seq)
    mod = types.ModuleType(key)
    mod.__file__ = path or f"<device:{name}>"
    code = compile(source, mod.__file__, "exec")
    sys.modules[key] = mod
    fl_rt._scripts[name] = {"module": mod, "port": port, "meta": meta, "path": path, "key": key}
    exec(code, mod.__dict__)
    return json.dumps({"name": name, "module": key, "meta": meta, "port": port, "callbacks": sorted(cb for cb in fl_rt.CALLBACKS if callable(getattr(mod, cb, None)))})
_fixed_load = fl_rt.load_device_script
fl_rt.load_device_script = _legacy_load
`);
}
const modCount = async () => {
  stdout.length = 0;
  await py.run(`import sys; print("fl_device modules:", sum(1 for k in sys.modules if k.startswith("fl_device_")))`);
  return Number(/fl_device modules: (\d+)/.exec(stdout.join("\n"))?.[1]);
};
const modsBefore = await modCount();
const eBad = await rej(host.loadDeviceScript({ name: "bad", source: fx("device_import_fails.py"), port: null }));
check("top-level 例外 (import no_such_module) の script は loadDeviceScript が reject (原因 ModuleNotFoundError)", /ModuleNotFoundError/.test(eBad ?? ""), eBad);
const listAfterBad = await host.listDeviceScripts();
check("読込失敗後の listDeviceScripts に bad が残らない (rec のみ)", !("bad" in listAfterBad) && "rec" in listAfterBad, Object.keys(listAfterBad));
check("読込失敗後に sys.modules へ fl_device_* が漏れない", (await modCount()) === modsBefore, { before: modsBefore });
stdout.length = 0;
const rBad = await host.midiIn(Uint8Array.from([0x90, 63, 90]), { port: 0 });
check("読込失敗後の midiIn は bad へ配送されない (OnMidiIn 未実行)", !rBad.results.some((x) => x.script === "bad") && !stdout.some((l) => /bad OnMidiIn delivered/.test(l)), { scripts: rBad.results.map((x) => x.script), stdout: stdout.slice(-3) });
await take();
const cbBad = await host.callback("OnRefresh", [4]);
check("読込失敗後の非 MIDI callback も bad へ配送されない", !cbBad.results.some((x) => x.script === "bad"), cbBad.results.map((x) => x.script));
await take();
const reBad = await host.loadDeviceScript({ name: "bad", source: "def OnInit(): pass\n", port: null });
check("失敗後に同名で読込み直せる (成功すれば登録される)", reBad.callbacks.join() === "OnInit" && "bad" in (await host.listDeviceScripts()), reBad);
await host.unloadDeviceScript("bad");
if (negLegacy) await py.run("fl_rt.load_device_script = _fixed_load");

// ---- 5. 合成 "Forward CCs" fixture: CC は device.forwardMIDICC へ、Note は転送しない ----
engine.state.midiOut.length = 0;
await host.midiIn(Uint8Array.from([0xb2, 74, 99]), { port: 1 });
await host.midiIn(Uint8Array.from([0x92, 60, 100]), { port: 1 });
await take();
const out = engine.state.midiOut;
const expectMsg = 0xb2 + (74 << 8) + (99 << 16) + (1 << 24);
check("CC → device.forwardMIDICC(status+data1<<8+data2<<16+port<<24) 1 回のみ、Note は転送なし", out.length === 1 && out[0].api === "forwardMIDICC" && out[0].message === expectMsg, out);

// ---- 6. 不正入力の拒否 (ネガティブ) ----
const e1 = await rej(host.callback("OnNoSuchCallback", []));
const e2 = await rej(host.callback("OnRefresh", []));
const e3 = await rej(host.callback("OnNoteOn", [{ status: 0x90 }]));
const e4 = await rej(host.midiIn(Uint8Array.from([0x20, 1, 2])));
check("未知 callback / 引数個数不一致 / MIDI 受信 callback の直呼びは reject", /unknown callback/.test(e1 ?? "") && /takes 1 argument/.test(e2 ?? "") && /dispatch_script_midi/.test(e3 ?? "") && /invalid MIDI message/.test(e4 ?? ""), { e1, e2, e3, e4 });
check("parseMidiBytes: 3 バイト / 2 バイト / sysex", JSON.stringify(parseMidiBytes([0xb0, 1, 2])) === '{"status":176,"data1":1,"data2":2}' && parseMidiBytes([0xc0, 7]).data2 === 0 && parseMidiBytes([0xf0, 1, 0xf7]).sysex.length === 3);

// ---- 7. flmidimsg の別名 (note/velocity/controlNum... は data1/data2 の別名。書込みが双方向に反映) ----
await py.run(`
import fl_rt
m = fl_rt.flmidimsg(0xB0, 7, 100)
m.controlNum = 11; m.velocity = 5
assert (m.data1, m.data2, m.note, m.controlVal) == (11, 5, 11, 5), (m.data1, m.data2)
m.data1 = 60
assert m.note == 60 and m.progNum == 60 and m.pressure == 60
assert len(fl_rt.flmidimsg.FIELDS) == 23
s = fl_rt.flmidimsg([0xF0, 1, 2, 0xF7])
assert s.status == 0xF0 and s.sysex == bytes([0xF0, 1, 2, 0xF7])
print("flmidimsg alias OK")
`);
check("flmidimsg: 23 field・data1/data2 別名・list からの sysex 構築", stdout.includes("flmidimsg alias OK"), stdout.slice(-3));

// ---- 7b. PoC 互換: __main__ 向け fl_rt.dispatch_midi (tests/poc_mcp.mjs の MIDI 区間と同じ入力・同じ期待) ----
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
const legacy = JSON.parse((await py.call("fl_rt:dispatch_midi", { fields_json: JSON.stringify({ status: 0x90, data1: 60, data2: 100 }) })).ok);
check("PoC 互換: dispatch_midi(__main__) = ['OnMidiMsg','OnNoteOn'] / handled=true / errors なし", JSON.stringify(legacy.called) === '["OnMidiMsg","OnNoteOn"]' && legacy.msg.handled === true && legacy.errors.length === 0, legacy);

// ---- 8. Web MIDI 結線 (fake MIDIAccess: node には Web MIDI が無い。ブラウザ実機は midi_ui_check.mjs) ----
class FakeInput {
  constructor(id, name) { this.id = id; this.name = name; this.type = "input"; this.state = "connected"; this.onmidimessage = null; }
  send(b) { this.onmidimessage?.({ data: Uint8Array.from(b), timeStamp: 1.5 }); }
}
await host.unloadDeviceScript("boom");
await host.unloadDeviceScript("fwd");
const inA = new FakeInput("A", "Keys"), inB = new FakeInput("B", "Pads");
const access = { inputs: new Map([["A", inA], ["B", inB]]), onstatechange: null };
const errs = [];
const detach = host.attachWebMidi(access, { portMap: { Pads: 7 }, onError: (e) => errs.push(String(e)) });
await take();
const N = 200;
for (let i = 0; i < N; i++) inA.send([0x90, i % 128, 100]); // await なしで連投 (到着順の保存を見る)
inB.send([0xb0, 1, 2]);
const inC = new FakeInput("C", "Late");
access.inputs.set("C", inC);
access.onstatechange({ port: inC });
inC.send([0xc0, 9]);
await host.listDeviceScripts(); // 直列キューの最後尾 = 全配送完了
const log = await take();
const noteOns = log.filter((x) => x[0] === "OnNoteOn");
check(`Web MIDI: ${N} 件連投が到着順に OnNoteOn (data1 = i % 128)・port 連番`, noteOns.length === N && noteOns.every((x, i) => x[1][0].data1 === i % 128 && x[1][0].port === 0), { n: noteOns.length });
const cc = log.find((x) => x[0] === "OnControlChange"), pc = log.find((x) => x[0] === "OnProgramChange");
check("Web MIDI: portMap{Pads:7} が効く / 接続後に増えた入力も結線 (連番 port=1)", cc?.[1][0].port === 7 && pc?.[1][0].port === 1, { cc: cc?.[1][0], pc: pc?.[1][0] });
check("Web MIDI: 配送エラー 0 (host.midiIn の reject 無し)", errs.length === 0, errs);
detach();
check("detach: 全入力のリスナ解除", inA.onmidimessage === null && inB.onmidimessage === null && inC.onmidimessage === null && access.onstatechange === null);

// ---- 9. 配送コスト (Worker + SAB RPC・フル配送 = OnMidiIn + OnMidiMsg + OnNoteOn の 3 callback) ----
await take();
const M = 1000;
const t0 = performance.now();
for (let i = 0; i < M; i++) await host.midiIn(Uint8Array.from([0x90, 60, 100]));
const seqMs = performance.now() - t0;
const t1 = performance.now();
const ps = [];
for (let i = 0; i < M; i++) ps.push(host.midiIn(Uint8Array.from([0x90, 60, 100])));
await Promise.all(ps);
const pipeMs = performance.now() - t1;
await take();
detail.latency = { events: M, sequential_us_per_event: Math.round((seqMs * 1000) / M), pipelined_us_per_event: Math.round((pipeMs * 1000) / M) };

await py.terminate();
const KEY = "27 callback 全てが想定引数で 1 回ずつ配送";
// --neg-legacy: 旧ローダ (登録してから exec) に差し戻す → 読込失敗の回帰 check (下の 3 本) が FAIL し、それ以外は全て PASS のとき検出成功
const LEGACY_KEYS = ["読込失敗後の listDeviceScripts に bad が残らない (rec のみ)", "読込失敗後に sys.modules へ fl_device_* が漏れない", "読込失敗後の midiIn は bad へ配送されない (OnMidiIn 未実行)"];
const failedKeys = Object.entries(checks).filter(([, v]) => !v).map(([k]) => k);
const detected = negLegacy
  ? LEGACY_KEYS.every((k) => failedKeys.includes(k)) && failedKeys.every((k) => LEGACY_KEYS.includes(k) || /^読込失敗後の非 MIDI|^失敗後に同名/.test(k))
  : checks[KEY] === false && Object.entries(checks).every(([k, v]) => k === KEY || v);
const ok = Object.keys(checks).length > 0 && (neg || negLegacy ? detected : Object.values(checks).every(Boolean));
console.log((ok ? (neg || negLegacy ? "MIDI SCRIPT NEG-CONTROL DETECTED " : "MIDI SCRIPT OK ") : "MIDI SCRIPT FAIL ") + JSON.stringify({ ok, neg, negLegacy, checks: Object.keys(checks).length, failed: Object.entries(checks).filter(([, v]) => !v).map(([k]) => k), detail, hostStats: host.stats }));
process.exit(ok ? (neg || negLegacy ? 1 : 0) : 2);
