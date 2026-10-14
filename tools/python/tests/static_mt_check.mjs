// PY-80 (#2856): pthread 版の静的リンク (flpy_static_pthread) で、複数スレッドから tool を呼ぶ検証。
//   (1) 単一スレッドの 48 tool 列 (static_check.mjs と同じ順序・同じ引数) の結果を、stock 静的版の記録
//       (work/tool_coverage.flpy_static.json = static_check.mjs の出力) と tool 別に突き合わせる。
//   (2) tool ごとに engine を reset してから単一スレッドで 1 回呼んだ結果 (基準) と、T 本のスレッドで同時に呼んだ各結果
//       (flpy_mt_call: PyThreadState_New + PyEval_RestoreThread で GIL を受け渡す) を status・result で突き合わせる。
//       host_calls は全スレッド合計が「同じ初期状態から逐次に T 回呼んだ合計」に一致すること (取りこぼし・二重計上が無いこと) を見る。
//   前提: CPY_PTHREADS=1 bash build_cpython_wasm.sh && CPY_PTHREADS=1 bash build_flpy_static.sh
//         node tests/static_check.mjs (stock 静的版の記録 work/tool_coverage.flpy_static.json を作る)
//   node tests/static_mt_check.mjs        STATIC_WASM=<name> で別ビルド (既定 flpy_static_pthread)
//   node tests/static_mt_check.mjs <tool> REPORT_PY97.md §4 の再現 (reset → 同じ tool を逐次 2 回の host_calls)
import fs from "node:fs";
import { A } from "./tool_args.mjs";

const root = new URL("../", import.meta.url);
const name = process.env.STATIC_WASM || "flpy_static_pthread";
const J = JSON.stringify;
let fails = 0;
const fail = (m) => { fails++; console.log("FAIL", m); };

const create = (await import(new URL(`dist/${name}.js`, root))).default;
const M = await create({ locateFile: (p) => new URL(`dist/${p}`, root).pathname, print() {}, printErr() {} });
for (const [path, file] of [["/fl/Lib/midi.py", "work/midi.py"], ["/fl/Lib/utils.py", "work/utils.py"], ["/fl/Tools/MCPTools.pyc", "work/MCPTools.pyc"]]) {
  M.FS.mkdirTree(path.slice(0, path.lastIndexOf("/")));
  M.FS.writeFile(path, fs.readFileSync(new URL(file, root)));
}
const withStr = (s, f) => { const n = M.lengthBytesUTF8(s) + 1, p = M._malloc(n); M.stringToUTF8(s, p, n); try { return f(p); } finally { M._free(p); } };
const initRc = withStr("", (p) => M._flpy_init(p));
if (initRc !== 0) { console.log("flpy_init failed:", M.UTF8ToString(M._flpy_last_error())); process.exit(1); }
if (typeof M._flpy_mt_call !== "function") { console.log(`${name} に flpy_mt_call が無い (CPY_PTHREADS=1 でビルドしたか)`); process.exit(1); }
M._fl_engine_reset();
const run = (code) => { const rc = withStr(code, (c) => withStr("<static_mt>", (f) => M._flpy_run(c, f))); if (rc !== 0) throw new Error(M.UTF8ToString(M._flpy_last_error())); };
const callRaw = (target, args) => withStr(target, (t) => withStr(args == null ? "" : J(args), (a) => { const p = M._flpy_call_json(t, a); const s = M.UTF8ToString(p); M._flpy_free(p); return JSON.parse(s); }));
const mtCall = (n, target, args) => withStr(target, (t) => withStr(args == null ? "" : J(args), (a) => { const p = M._flpy_mt_call(n, t, a); if (!p) throw new Error("flpy_mt_call が NULL を返した (malloc 失敗)"); const s = M.UTF8ToString(p); M._flpy_free(p); return JSON.parse(s); }));
const textOf = (r) => (r.err ? r.err : String(r.ok));
const full = (r) => ({ raised: !!r.err, text: textOf(r) });
const norm = (r) => ({ raised: !!r.err, text: textOf(r).slice(0, 160) }); // stock 記録 (static_check.mjs) と同じ先頭 160 字

run(`import fl_rt; fl_rt.install_flapi(); fl_rt.load_pyc("/fl/Tools/MCPTools.pyc", "__main__")`);
const tools = JSON.parse(callRaw("__main__:get_mcp_tools_json", {}).ok);
const names = tools.map((t) => t.name).filter((n) => A[n] !== undefined);
if (names.length !== 48) fail(`tool 数 ${names.length} != 48`);

// §4 の再現: `node tests/static_mt_check.mjs <tool>` は reset → 同じ tool を逐次 2 回呼び、各回の status・host_calls を出して終了する
if (process.argv[2]) {
  if (!names.includes(process.argv[2])) { console.log(`未知の tool: ${process.argv[2]}`); process.exit(1); }
  M._fl_engine_reset();
  const calls = [1, 2].map(() => { M._flpy_trace_reset(0); const from = Number(M._flpy_host_calls()); const r = norm(callRaw(`__main__:${process.argv[2]}`, A[process.argv[2]])); return { ...r, host_calls: Number(M._flpy_host_calls()) - from }; });
  console.log(J({ tool: process.argv[2], calls }));
  process.exit(0);
}

// (1) 単一スレッド列 (static_check.mjs と同じ: reset なし・同順)
M._flpy_trace_reset(0);
const seq = [];
for (const n of names) {
  const from = Number(M._flpy_host_calls());
  const r = callRaw(`__main__:${n}`, A[n]);
  seq.push({ name: n, ...norm(r), host_calls: Number(M._flpy_host_calls()) - from });
}
const stockPath = new URL("work/tool_coverage.flpy_static.json", root);
if (!fs.existsSync(stockPath)) { fail("stock 静的版の記録が無い (先に node tests/static_check.mjs)"); }
else {
  const stock = JSON.parse(fs.readFileSync(stockPath, "utf8")).tools;
  let seqDiff = 0;
  for (const s of seq) {
    const o = stock.find((x) => x.name === s.name);
    const ok = o && J({ raised: o.status === "raised", text: o.result, host_calls: o.host_calls }) === J({ raised: s.raised, text: s.text, host_calls: s.host_calls });
    if (!ok) { seqDiff++; fail(`単一スレッド ${s.name}: stock=${J(o && { status: o.status, result: o.result, host_calls: o.host_calls }).slice(0, 120)} pthread=${J({ raised: s.raised, text: s.text, host_calls: s.host_calls }).slice(0, 120)}`); }
  }
  console.log(J({ phase: "single_vs_stock", tools: seq.length, diff: seqDiff, host_calls: seq.reduce((a, s) => a + s.host_calls, 0) }));
}

// (2) tool ごとに reset → 基準 (単一) → reset → T スレッド同時。T=2 は全 48 tool、T=4 は重い 2 tool
const heavy = new Set(["get_session_context", "get_mixer_routing"]);
const rows = [];
let mtDiff = 0;
const t0 = performance.now();
for (const n of names) {
  for (const T of heavy.has(n) ? [2, 4] : [2]) {
    M._fl_engine_reset();
    M._flpy_trace_reset(0);
    let from = Number(M._flpy_host_calls());
    const ref = full(callRaw(`__main__:${n}`, A[n]));
    const refCalls = Number(M._flpy_host_calls()) - from;
    // 同じ初期状態から逐次に T 回呼んだ合計が基準。状態を変える tool (例: piano roll を開く) は 2 回目以降の回数が変わるため、T × 基準ではなく逐次合計と比べる
    M._fl_engine_reset();
    M._flpy_trace_reset(0);
    from = Number(M._flpy_host_calls());
    for (let i = 0; i < T; i++) callRaw(`__main__:${n}`, A[n]);
    const seqCalls = Number(M._flpy_host_calls()) - from;
    M._fl_engine_reset();
    M._flpy_trace_reset(0);
    from = Number(M._flpy_host_calls());
    const outs = mtCall(T, `__main__:${n}`, A[n]);
    const mtCalls = Number(M._flpy_host_calls()) - from;
    if (!Array.isArray(outs) || outs.length !== T) { fail(`${n} T=${T}: 結果数が一致しない ${J(outs).slice(0, 120)}`); continue; }
    const same = outs.map((o) => { const x = full(o); return x.raised === ref.raised && x.text === ref.text; }); // 比較は全文 (記録だけ 160 字)
    const bad = same.filter((x) => !x).length;
    if (bad) { mtDiff += bad; fail(`${n} T=${T}: スレッド結果が基準と不一致 ${bad}/${T} (基準=${J(ref).slice(0, 100)} 先頭=${J(full(outs[0])).slice(0, 100)})`); }
    if (mtCalls !== seqCalls) { fail(`${n} T=${T}: host_calls 合計 ${mtCalls} != 逐次 ${seqCalls}`); }
    rows.push({ name: n, threads: T, ref_raised: ref.raised, ref_text: ref.text.slice(0, 160), ref_host_calls: refCalls, seq_host_calls: seqCalls, mt_host_calls: mtCalls, thread_match: same.filter(Boolean).length });
  }
}
const wallMs = Math.round(performance.now() - t0);
const summary = { wasm: name, runs: rows.length, threads_2_tools: names.length, threads_4_tools: heavy.size, thread_mismatch: mtDiff, wall_ms: wallMs };
console.log(J(summary));
fs.mkdirSync(new URL("work/", root), { recursive: true });
fs.writeFileSync(new URL(`work/mt_check.${name}.json`, root), J({ summary, single: seq, rows }, null, 1));
console.log(fails ? `STATIC MT CHECK FAIL (${fails})` : "STATIC MT CHECK OK");
process.exit(fails ? 1 : 0);
