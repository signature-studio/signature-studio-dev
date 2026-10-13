// PY-8 (#80): 静的リンク版 (flpy_static) で MIDI 1 イベントの配送時間を実測する。
//   node tests/static_midi_bench.mjs [events=20000] [trials=5]   出力: JSON (µs/イベント)
// 前提: build_flpy_static.sh 済み、work/ に midi.py・utils.py・device_Forward CCs to current plugin Port 10.py (fetch_inputs.sh 済み)。
// 注意: 静的版の C 側 (provider/fl_engine.c) に device.* の handler は無い。そのため device.forwardMIDICC は
//   Python 側の計数スタブに差し替える (呼出し回数 = CC 1 件あたり 1 回を計数)。C の fl_api_call は経由しない。
//   よって本計測は「静的版の Python 配送 + device script 実行」の時間で、flapi の C 呼出し自体は含まない
//   (C fl_api_call の単体コストは static_bench.mjs の c_only_us を参照)。
import fs from "node:fs";

const root = new URL("../", import.meta.url);
const events = Number(process.argv[2] || 20000), trials = Number(process.argv[3] || 5);
const J = JSON.stringify;
const stats = (a) => { const s = [...a].sort((x, y) => x - y); return { min: s[0], median: s[s.length >> 1], max: s[s.length - 1] }; };
const r3 = (x) => +x.toFixed(3);
const devSrc = fs.readFileSync(new URL("work/device_Forward CCs to current plugin Port 10.py", root), "utf8");

const M = await (await import(new URL("dist/flpy_static.js", root))).default({ locateFile: (p) => new URL(`dist/${p}`, root).pathname, print() {}, printErr() {} });
for (const [path, file] of [["/fl/Lib/midi.py", "work/midi.py"], ["/fl/Lib/utils.py", "work/utils.py"]]) {
  M.FS.mkdirTree(path.slice(0, path.lastIndexOf("/")));
  M.FS.writeFile(path, fs.readFileSync(new URL(file, root)));
}
const withStr = (s, f) => { const n = M.lengthBytesUTF8(s) + 1, p = M._malloc(n); M.stringToUTF8(s, p, n); try { return f(p); } finally { M._free(p); } };
const call = (target, args) => withStr(target, (t) => withStr(args == null ? "" : J(args), (a) => { const p = M._flpy_call_json(t, a); const s = M.UTF8ToString(p); M._flpy_free(p); return JSON.parse(s); }));
if (withStr("", (p) => M._flpy_init(p)) !== 0) { console.log("flpy_init failed:", M.UTF8ToString(M._flpy_last_error())); process.exit(1); }
M._fl_engine_reset();
const run = (code) => { if (withStr(code, (c) => withStr("<static_midi>", (f) => M._flpy_run(c, f))) !== 0) throw new Error(M.UTF8ToString(M._flpy_last_error())); };

run(`import fl_rt, time, json
fl_rt.install_flapi()
import device
_fwd_calls = [0]
def _fwd(message, mode=2):
    _fwd_calls[0] += 1
device.forwardMIDICC = _fwd
def bench_midi(n, status, d1, d2):
    fj = json.dumps({"status": status, "data1": d1, "data2": d2, "port": 0, "timestamp": 0})
    dispatch = fl_rt.dispatch_script_midi
    for _ in range(50): dispatch(fj)
    _fwd_calls[0] = 0
    t = time.perf_counter()
    for _ in range(n): dispatch(fj)
    dt = (time.perf_counter() - t) * 1e6 / n
    return {"us": dt, "fwd_per_event": _fwd_calls[0] / n}
`);
const ld = call("fl_rt:load_device_script", { name: "fwd", source: devSrc, port: 0 });
if (ld.err !== undefined) throw new Error(`load: ${ld.err}\n${ld.tb ?? ""}`);
const ini = call("fl_rt:init_scripts", { script: null });
if (ini.err !== undefined) throw new Error(`init: ${ini.err}\n${ini.tb ?? ""}`);

const cases = { cc: [0xb0, 7, 100], noteon: [0x90, 60, 100] };
const out = {};
for (const [k, [s, d1, d2]] of Object.entries(cases)) {
  const per = [];
  for (let t = 0; t < trials; t++) {
    const r = call("__main__:bench_midi", { n: events, status: s, d1, d2 });
    if (r.err !== undefined) throw new Error(`bench ${k}: ${r.err}\n${r.tb ?? ""}`);
    per.push(r.ok);
  }
  out[k] = { us_per_event: stats(per.map((x) => x.us)), fwd_per_event: per[0].fwd_per_event, per_trial: per.map((x) => r3(x.us)) };
}
console.log(J({ events, trials, load: fs.readFileSync("/proc/loadavg", "utf8").trim(), static_midi: { cc: out.cc, noteon: out.noteon } }));
