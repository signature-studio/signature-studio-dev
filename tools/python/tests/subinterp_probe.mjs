// PY-6 (#76) サブインタプリタ検証: flpy.wasm (CPython 3.12.1 static) で Py_NewInterpreterFromConfig が動くか。
//   node tools/python/tests/subinterp_probe.mjs [--neg]      (FLPY_DIST=<dir> で別ビルドの flpy.js を対象にできる。既定 ../dist)
//   PASS: "SUBINTERP OK {...}" exit 0 / FAIL: exit 2 / --neg: 期待を 1 つ壊し、その check だけが FAIL したとき "NEG-CONTROL DETECTED" exit 1
//   本物のネガコン (修正前 flpy.c をビルドして FAIL することを確認): tests/subinterp_negcontrol_old.sh
// 各 case は新しい wasm インスタンス (abort/trap が他 case に伝播しない)。flpy_subinterp_run(code, mode) の mode:
//   0 = isolated (独立 obmalloc・単相初期化 ext 拒否・OWN_GIL) / 1 = isolated + SHARED_GIL / 2 = legacy (main と obmalloc/GIL 共有)
// PY-12 (#587): _flhost は per-module state + Py_mod_multiple_interpreters 宣言済み。期待値は CPython 3.12.1・emsdk の実測。
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
const DIST = process.env.FLPY_DIST ? path.resolve(process.env.FLPY_DIST) : path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../dist");
const { default: createFlPython } = await import(pathToFileURL(path.join(DIST, "flpy.js")).href);

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
    locateFile: (p) => path.join(DIST, p),
    print: (t) => out.push(t), printErr: (t) => out.push("ERR " + t),
    flHostCall: (fn) => {
      if (fn === 0) return { echo: [1], f: 1.5 };
      if (fn === 1) throw Object.assign(new Error("boom"), { flCode: 3 });
      return null;
    },
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
  const expectRejected = neg ? ["_elementtree", "_lsprof", "faulthandler"] : ["_elementtree", "_lsprof", "faulthandler", "pyexpat"];
  check("isolated: 拒否される builtin は {_elementtree,_lsprof,faulthandler,pyexpat} の 4/66 (_flhost は含まない。全て 'does not support loading in subinterpreters')",
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

// ---- 5. _flhost (FL 境界 module): per-module state。3 構成それぞれで import でき、破棄後も main の _flhost が壊れない ----
const SUB_FLHOST = `import _flhost, json
r0 = _flhost.call(0, (1,))
cb = lambda: 0
_flhost.call(0, (cb,))
try:
    _flhost.call(1, ())
    herr = None
except _flhost.HostError as e:
    herr = list(e.args)
result = json.dumps({'j': r0, 'cb_ids': sorted(_flhost._cbs), 'herr': herr, 'name': _flhost.__name__})`;
for (const [label, mode] of Object.entries(MODES)) {
  const { sub, main, out } = await fresh();
  const b = main("import _flhost\nM_CB = lambda: 0\n_flhost.call(0, (M_CB,))\nprint('main cbs before', sorted(_flhost._cbs))"); // main が先に _flhost を初期化 (FL の通常運用)
  const r = sub(SUB_FLHOST, mode);
  const v = r.ok ? JSON.parse(r.result) : null;
  detail[`flhost_${label}`] = v;
  check(`${label}: サブインタプリタで _flhost が import でき、call (J 戻り値) / callable 登録 / HostError(code,msg) が動く`,
    b.ok && r.ok && JSON.stringify(v.j) === JSON.stringify({ echo: [1], f: 1.5 }) && v.herr && v.herr[0] === 3 && v.herr[1] === "boom" && v.name === "_flhost", { r, out: out.slice(-3) });
  check(`${label}: サブの callback 表は main と独立 (sub の id は 1 から採番し、表は {1})`, r.ok && JSON.stringify(v.cb_ids) === "[1]", { r });
  const a = main("import _flhost\nprint('main after J', _flhost.call(0, (1,)))\nprint('main after cbs', sorted(_flhost._cbs))\ntry:\n    _flhost.call(1, ())\nexcept _flhost.HostError as e:\n    print('main after herr', list(e.args))\n_flhost.call(0, (M_CB,))\nprint('main after cbs2', sorted(_flhost._cbs))");
  check(`${label}: 破棄後も main の _flhost.call / HostError / _cbs が壊れない (cbs は main 自身の {1,2} のみ)`,
    a.ok && out.includes("main after J {'echo': [1], 'f': 1.5}") && out.includes("main after cbs [1]") && out.includes("main after herr [3, 'boom']") && out.includes("main after cbs2 [1, 2]"), { a, out: out.slice(-6) });
}
{
  // sub 内に居る間に main 側の状態が書き換わらないこと: main の _cbs を sub 実行前後で比較 (legacy = obmalloc 共有でも)
  const { sub, main, out } = await fresh();
  main("import _flhost\nfor i in range(3): _flhost.call(0, (lambda: i,))\nprint('main cbs n', len(_flhost._cbs))");
  sub("import _flhost\nfor i in range(5): _flhost.call(0, (lambda: i,))\nresult = str(len(_flhost._cbs))", 2);
  main("import _flhost\nprint('main cbs n2', len(_flhost._cbs))");
  check("legacy: sub が callable を 5 個登録しても main の _cbs は 3 のまま", out.includes("main cbs n 3") && out.includes("main cbs n2 3"), out.slice(-3));
}

// ---- 6. ネガティブ: サブインタプリタ内の例外は ok:false/stage:exec で報告され、握り潰されない ----
{
  const { sub, main } = await fresh();
  const r = sub("raise ValueError('probe negative control')", 0);
  check("サブインタプリタ内の例外 → ok:false stage:exec + traceback、main は継続", !r.ok && r.stage === "exec" && /probe negative control/.test(r.err) && main("x = 1").ok, r);
}

// ---- 7. 作成/破棄コスト (n=50 を 3 回 = 150 個 / 系列)・wasm メモリ。_flhost 有無・module namespace 分離 (device script 方式) との比較 ----
// 系列ごとに新しい wasm インスタンス (メモリ比較を系列間で汚さない)。
{
  const series = async (code, mode) => {
    const { M, sub } = await fresh();
    const mem0 = M.HEAPU8.length;
    const runs = [];
    let allOk = true;
    for (let k = 0; k < 3; k++) {
      const t0 = performance.now();
      for (let i = 0; i < 50; i++) allOk &&= sub(code, mode).ok;
      runs.push(+((performance.now() - t0) / 50).toFixed(2));
    }
    return { runs, min: Math.min(...runs), max: Math.max(...runs), allOk, mem_before: mem0, mem_after: M.HEAPU8.length };
  };
  const base = await series("import json, re\nresult = json.dumps([1])", 0);
  const withHost = await series("import json, re, _flhost\nresult = json.dumps(_flhost.call(0, (1,)))", 0);
  const legacyHost = await series("import json, re, _flhost\nresult = json.dumps(_flhost.call(0, (1,)))", 2);
  // 比較対象: main 内で module namespace を新規作成して同等コードを exec (PY-6 #76 が採用した device script の分離方式)
  const { main, out } = await fresh();
  main("import time, types, json, re, _flhost\nruns = []\nfor k in range(3):\n    t0 = time.perf_counter()\n    for i in range(50):\n        m = types.ModuleType('dev%d_%d' % (k, i))\n        exec('import json, re, _flhost\\nresult = json.dumps(_flhost.call(0, (1,)))', m.__dict__)\n    runs.append(round((time.perf_counter() - t0) / 50 * 1000, 3))\nprint('NS_RUNS', json.dumps(runs))");
  const nsLine = out.find((l) => l.startsWith("NS_RUNS "));
  const ns = nsLine ? JSON.parse(nsLine.slice(8)) : null;
  detail.create_run_destroy_ms_per_interp = { n: 50, isolated_json_re: base, isolated_with_flhost: withHost, legacy_with_flhost: legacyHost };
  detail.module_namespace_exec_ms = ns && { n: 50, runs: ns, min: Math.min(...ns), max: Math.max(...ns) };
  check("150 回 (50×3) の作成/実行/破棄が 3 系列 (isolated json+re / isolated+_flhost / legacy+_flhost) とも全て成功し、各系列で wasm メモリが増えない",
    !!ns && ns.length === 3 && [base, withHost, legacyHost].every((x) => x.allOk && x.mem_after === x.mem_before), { base, withHost, legacyHost, ns });
}
// 情報 (check 無し): 150 個を超えると線形メモリが増える。_flhost 無し (json+re のみ) でも、修正前 flpy.c のビルドでも同じ閾値で増える = 本 PR 起因ではない既存の挙動
{
  const { M, sub } = await fresh();
  const mem = [M.HEAPU8.length];
  for (let b = 0; b < 6; b++) { for (let i = 0; i < 50; i++) sub("import json, re\nresult = '1'", 0); mem.push(M.HEAPU8.length); }
  detail.wasm_memory_after_each_50_isolated_json_re = mem;
}

const failed = Object.entries(checks).filter(([, v]) => !v).map(([k]) => k);
const NEG_KEY = "isolated: 拒否される builtin は {_elementtree,_lsprof,faulthandler,pyexpat} の 4/66 (_flhost は含まない。全て 'does not support loading in subinterpreters')";
const ok = Object.keys(checks).length > 0 && (neg ? failed.length === 1 && failed[0] === NEG_KEY : failed.length === 0);
console.log((ok ? (neg ? "SUBINTERP NEG-CONTROL DETECTED " : "SUBINTERP OK ") : "SUBINTERP FAIL ") + JSON.stringify({ ok, neg, checks: Object.keys(checks).length, failed, detail }));
process.exit(ok ? (neg ? 1 : 0) : 2);
