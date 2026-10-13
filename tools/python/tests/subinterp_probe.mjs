// PY-6 (#76) サブインタプリタ検証: flpy.wasm (CPython 3.12.1 static) で Py_NewInterpreterFromConfig が動くか。
//   node tools/python/tests/subinterp_probe.mjs [--neg]
//   PASS: "SUBINTERP OK {...}" exit 0 / FAIL: exit 2 / --neg: 期待を 1 つ壊し、その check だけが FAIL したとき "NEG-CONTROL DETECTED" exit 1
// 各 case は新しい wasm インスタンス (abort/trap が他 case に伝播しない)。flpy_subinterp_run(code, mode) の mode:
//   0 = isolated (独立 obmalloc・単相初期化 ext 拒否・OWN_GIL) / 1 = isolated + SHARED_GIL / 2 = legacy (main と obmalloc/GIL 共有)
// 「既知の挙動の固定」: 期待値は 2026-10-13 の実測 (CPython 3.12.1・emsdk 6.0.12)。_flhost を修正した場合は該当 check を更新すること。
import createFlPython from "../dist/flpy.js";

const neg = process.argv.includes("--neg");
const checks = {};
const detail = {};
const check = (name, cond, extra) => {
  checks[name] = !!cond;
  if (!cond) console.error(`FAIL ${name}`, extra === undefined ? "" : JSON.stringify(extra));
};

async function fresh() {
  const out = [];
  const M = await createFlPython({
    locateFile: (p) => new URL("../dist/" + p, import.meta.url).pathname,
    print: (t) => out.push(t), printErr: (t) => out.push("ERR " + t),
    flHostCall: (fn) => (fn === 0 ? { echo: [1], f: 1.5 } : null),
  });
  if (M.ccall("flpy_init", "number", ["string"], [""]) !== 0) throw new Error("flpy_init failed: " + M.UTF8ToString(M._flpy_last_error()));
  const sub = (code, mode) => {
    const p = M.ccall("flpy_subinterp_run", "number", ["string", "number"], [code, mode]);
    const s = M.UTF8ToString(p);
    M._flpy_free(p);
    return JSON.parse(s);
  };
  const main = (code) => {
    const rc = M.ccall("flpy_run", "number", ["string", "string"], [code, "<main>"]);
    return rc === 0 ? { ok: true } : { ok: false, err: M.UTF8ToString(M._flpy_last_error()) };
  };
  return { M, out, sub, main };
}

const FL22 = "__future__ abc ast collections copy enum functools inspect itertools json math operator os pathlib random re sys time traceback types typing zlib".split(" ");
const MODES = { isolated_own_gil: 0, isolated_shared_gil: 1, legacy: 2 };

// ---- 1. 3 構成で新規インタプリタ作成 + 実行 + 破棄、その後に main が生きている ----
for (const [label, mode] of Object.entries(MODES)) {
  const { sub, main, out } = await fresh();
  const r = sub("result = str(1 + 1)", mode);
  const alive = main("print('main alive', 2 + 2)");
  check(`${label}: Py_NewInterpreterFromConfig → run → Py_EndInterpreter が成功し main が継続`, r.ok && r.result === "2" && alive.ok && out.includes("main alive 4"), { r, alive });
}

// ---- 2. FL 同梱スクリプトが使う stdlib 22 module が isolated (OWN_GIL) でも全て import できる ----
{
  const { sub } = await fresh();
  const r = sub(`bad = {}\nfor m in ${JSON.stringify(FL22)}:\n    try: __import__(m)\n    except BaseException as e: bad[m] = repr(e)[:100]\nresult = repr(bad)`, 0);
  check("isolated: FL 同梱スクリプトの stdlib 22 module を全て import", r.ok && r.result === "{}", r);
}

// ---- 3. builtin module 66 本: isolated で拒否されるもの (単相初期化 / 未対応宣言) ----
const bi = (mode) => `import sys, importlib\nbad = {}\nnames = sorted(sys.builtin_module_names)\nfor m in names:\n    if m in ('sys', 'builtins'): continue\n    try: importlib.import_module(m)\n    except BaseException as e: bad[m] = str(e)\nimport json\nresult = json.dumps({'total': len(names), 'bad': bad})`;
{
  const a = await fresh();
  const iso = JSON.parse(a.sub(bi(0), 0).result);
  const b = await fresh();
  const leg = JSON.parse(b.sub(bi(2), 2).result);
  detail.builtin_modules = { total: iso.total, isolated_rejected: Object.keys(iso.bad).sort(), legacy_rejected: Object.keys(leg.bad) };
  const expectRejected = neg ? ["_elementtree", "_flhost", "_lsprof", "faulthandler"] : ["_elementtree", "_flhost", "_lsprof", "faulthandler", "pyexpat"];
  check("isolated: 拒否される builtin は {_elementtree,_flhost,_lsprof,faulthandler,pyexpat} の 5/66 (全て 'does not support loading in subinterpreters')",
    iso.total === 66 && JSON.stringify(Object.keys(iso.bad).sort()) === JSON.stringify(expectRejected) && Object.values(iso.bad).every((m) => /does not support loading in subinterpreters/.test(m)), iso);
  check("legacy: 66 本全て import 可 (拒否 0)", leg.total === 66 && Object.keys(leg.bad).length === 0, leg);
}

// ---- 4. 隔離の実態: isolated は __main__ / sys.modules / 型を共有しない ----
{
  const { sub, main } = await fresh();
  main("import sys\nsys.modules['marker_main'] = object()\nMAIN_ONLY = 1");
  const r = sub("import sys, json\nresult = json.dumps({'main_only_visible': 'MAIN_ONLY' in globals(), 'marker_visible': 'marker_main' in sys.modules, 'count': len(sys.modules)})", 0);
  const v = JSON.parse(r.result);
  detail.isolation = v;
  check("isolated: main の __main__ 変数と sys.modules は見えない", r.ok && v.main_only_visible === false && v.marker_visible === false, v);
}

// ---- 5. _flhost (FL 境界 module) ----
{
  const { sub, main, out } = await fresh();
  const r = sub("import _flhost\nresult = 'imported'", 0);
  check("isolated: 現行 _flhost は import 不可 (Py_mod_multiple_interpreters 未宣言)", !r.ok && /_flhost does not support loading in subinterpreters/.test(r.err), r);
  check("  └ 失敗後も main の _flhost は動作 (J 戻り値経路)", main("import _flhost\nprint('J path', _flhost.call(0, (1,)))").ok && out.includes("J path {'echo': [1], 'f': 1.5}"), out.slice(-2));
}
{
  const { sub, main } = await fresh();
  const before = main("import _flhost\n_flhost.call(0, (1,))"); // main が先に _flhost を初期化している (FL の通常運用)
  const r = sub("import _flhost\nresult = repr(_flhost.call(0, (1,)))", 2);
  let after;
  try { after = main("import _flhost\n_flhost.call(0, (1,))"); } catch (e) { after = { ok: false, err: String(e) }; }
  detail.flhost_legacy_hazard = { sub_ok: r.ok, main_after: after.err ? String(after.err).slice(0, 80) : "ok" };
  check("既知の危険: legacy サブインタプリタで _flhost を import すると static 状態 (json_loads/HostError/g_cbs) が上書きされ、破棄後の main の _flhost.call が壊れる (症状は不定: trap / NameError 等)",
    before.ok && r.ok && after.ok === false, { r, after });
}

// ---- 6. ネガティブ: サブインタプリタ内の例外は ok:false/stage:exec で報告され、握り潰されない ----
{
  const { sub, main } = await fresh();
  const r = sub("raise ValueError('probe negative control')", 0);
  check("サブインタプリタ内の例外 → ok:false stage:exec + traceback、main は継続", !r.ok && r.stage === "exec" && /probe negative control/.test(r.err) && main("x = 1").ok, r);
}

// ---- 7. 作成/破棄コスト (n=50 を 3 回) と wasm メモリ ----
{
  const { M, sub } = await fresh();
  const mem0 = M.HEAPU8.length;
  const runs = [];
  let allOk = true;
  for (let k = 0; k < 3; k++) {
    const t0 = performance.now();
    for (let i = 0; i < 50; i++) allOk &&= sub("import json, re\nresult = json.dumps([1])", 0).ok;
    runs.push(+((performance.now() - t0) / 50).toFixed(2));
  }
  detail.create_run_destroy_ms_per_interp = { n: 50, runs, min: Math.min(...runs), max: Math.max(...runs) };
  detail.wasm_memory_bytes = { before: mem0, after: M.HEAPU8.length };
  check("150 回 (50×3) の作成/実行/破棄が全て成功し wasm メモリが増えない", allOk && M.HEAPU8.length === mem0, { mem0, after: M.HEAPU8.length });
}

const failed = Object.entries(checks).filter(([, v]) => !v).map(([k]) => k);
const NEG_KEY = "isolated: 拒否される builtin は {_elementtree,_flhost,_lsprof,faulthandler,pyexpat} の 5/66 (全て 'does not support loading in subinterpreters')";
const ok = Object.keys(checks).length > 0 && (neg ? failed.length === 1 && failed[0] === NEG_KEY : failed.length === 0);
console.log((ok ? (neg ? "SUBINTERP NEG-CONTROL DETECTED " : "SUBINTERP OK ") : "SUBINTERP FAIL ") + JSON.stringify({ ok, neg, checks: Object.keys(checks).length, failed, detail }));
process.exit(ok ? (neg ? 1 : 0) : 2);
