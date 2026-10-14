// PY-80 (#2633): 静的版 (flpy_static = CPython + provider を 1 wasm にリンク) でサブインタプリタを検証する。
//   SAB 版の subinterp_probe.mjs (flpy.wasm、REPORT.md §11 / REPORT_PY12.md) と同じ観点を、静的版の入口で実行する。
//   Worker / SAB / JS import なし。_flhost は静的版の provider (fl_api_call) に直結しているため、
//   サブインタプリタ内の _flhost.call は main と同じ provider の値を返すことを期待値にする。
//   node tests/static_subinterp_probe.mjs [--neg]    前提: build_cpython_wasm.sh・build_flpy_static.sh 済み
//   PASS: "STATIC SUBINTERP OK {...}" exit 0 / FAIL: exit 2 / --neg: 期待を 1 つ壊し、その check だけが FAIL したとき "STATIC SUBINTERP NEG-CONTROL DETECTED" exit 1
//   mode: 0 = isolated (独立 obmalloc・OWN_GIL) / 1 = isolated + SHARED_GIL / 2 = legacy (main と obmalloc/GIL 共有)
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = new URL("../", import.meta.url);
const DIST = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../dist");
const NAME = process.env.STATIC_WASM || "flpy_static";
// Memory64 版 (STATIC_MEM64=1|2): exported 関数のポインタ引数は BigInt (i64)。mode 引数 (i32) と戻り値の BigInt は数値に戻す。
const MEM64 = Number(process.env.STATIC_MEM64 || 0) > 0;
const I32_ARGS = { _flpy_subinterp_run: [1] };
const wrap64 = (raw) => new Proxy(raw, {
  get(t, k) {
    const v = t[k];
    if (typeof v !== "function" || typeof k !== "string" || !k.startsWith("_")) return v;
    return (...a) => {
      const args = a.map((x, i) => (typeof x === "number" && !(I32_ARGS[k] || []).includes(i) ? BigInt(x) : x));
      const r = v(...args);
      return typeof r === "bigint" ? Number(r) : r;
    };
  },
});
const create = (await import(pathToFileURL(path.join(DIST, `${NAME}.js`)).href)).default;
const ids = JSON.parse(fs.readFileSync(new URL("analysis/flapi/flapi_ids.json", root)));
const FN_CHANNEL_COUNT = ids.indexOf("channels.channelCount");
if (FN_CHANNEL_COUNT < 0) throw new Error("channels.channelCount が flapi_ids.json に無い");

const neg = process.argv.includes("--neg");
const checks = {};
const detail = {};
const check = (name, cond, extra) => {
  checks[name] = !!cond;
  if (!cond) console.error(`FAIL ${name}`, extra === undefined ? "" : JSON.stringify(extra));
};

async function fresh() {
  const out = [];
  const raw = await create({
    locateFile: (p) => path.join(DIST, p),
    print: (t) => out.push(t), printErr: (t) => out.push("ERR " + t),
  });
  const M = MEM64 ? wrap64(raw) : raw;
  const withStr = (s, f) => { const n = M.lengthBytesUTF8(s) + 1, p = M._malloc(n); M.stringToUTF8(s, p, n); try { return f(p); } finally { M._free(p); } };
  if (withStr("", (p) => M._flpy_init(p)) !== 0) throw new Error("flpy_init failed: " + M.UTF8ToString(M._flpy_last_error()));
  M._fl_engine_reset();
  const sub = (code, mode) => {
    const p = withStr(code, (c) => M._flpy_subinterp_run(c, mode));
    const s = M.UTF8ToString(p);
    M._flpy_free(p);
    return JSON.parse(s);
  };
  const main = (code) => {
    const rc = withStr(code, (c) => withStr("<main>", (f) => M._flpy_run(c, f)));
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
const bi = `import sys, importlib\nbad = {}\nnames = sorted(sys.builtin_module_names)\nfor m in names:\n    if m in ('sys', 'builtins'): continue\n    try: importlib.import_module(m)\n    except BaseException as e: bad[m] = str(e)\nimport json\nresult = json.dumps({'total': len(names), 'bad': bad})`;
{
  const a = await fresh();
  const iso = JSON.parse(a.sub(bi, 0).result);
  const b = await fresh();
  const leg = JSON.parse(b.sub(bi, 2).result);
  detail.builtin_modules = { total: iso.total, isolated_rejected: Object.keys(iso.bad).sort(), legacy_rejected: Object.keys(leg.bad) };
  const expectRejected = neg ? ["_elementtree", "_lsprof", "faulthandler"] : ["_elementtree", "_lsprof", "faulthandler", "pyexpat"];
  check("isolated: 拒否される builtin は {_elementtree,_lsprof,faulthandler,pyexpat} の 4/66 (全て 'does not support loading in subinterpreters')",
    iso.total === 66 && JSON.stringify(Object.keys(iso.bad).sort()) === JSON.stringify(expectRejected) && Object.values(iso.bad).every((m) => /does not support loading in subinterpreters/.test(m)), iso);
  check("legacy: 66 本全て import 可 (拒否 0)", leg.total === 66 && Object.keys(leg.bad).length === 0, leg);
}

// ---- 4. 隔離の実態: isolated は __main__ / sys.modules を共有しない ----
{
  const { sub, main } = await fresh();
  main("import sys\nsys.modules['marker_main'] = object()\nMAIN_ONLY = 1");
  const r = sub("import sys, json\nresult = json.dumps({'main_only_visible': 'MAIN_ONLY' in globals(), 'marker_visible': 'marker_main' in sys.modules, 'count': len(sys.modules)})", 0);
  const v = r.ok ? JSON.parse(r.result) : null;
  detail.isolation = v;
  check("isolated: main の __main__ 変数と sys.modules は見えない", r.ok && v.main_only_visible === false && v.marker_visible === false, { r, v });
}

// ---- 5. provider 直結の _flhost: サブ内の _flhost.call が main と同じ provider の値を返す (静的版の境界) ----
{
  const SUB = `import _flhost, json\nresult = json.dumps({'cc': _flhost.call(${FN_CHANNEL_COUNT}, ()), 'name': _flhost.__name__})`;
  for (const [label, mode] of Object.entries(MODES)) {
    const { sub, main, out } = await fresh();
    const m = main(`import _flhost\nprint('MAIN_CC', _flhost.call(${FN_CHANNEL_COUNT}, ()))`);
    const mainCC = (out.find((l) => l.startsWith("MAIN_CC ")) || "").slice(8);
    const r = sub(SUB, mode);
    const v = r.ok ? JSON.parse(r.result) : null;
    detail[`flhost_${label}`] = v;
    check(`${label}: サブインタプリタで _flhost が import でき、provider の channelCount が main と一致する`,
      m.ok && r.ok && v.name === "_flhost" && String(v.cc) === mainCC && mainCC !== "", { m, r, mainCC });
  }
}

// ---- 6. ネガティブ: サブインタプリタ内の例外は ok:false/stage:exec で報告され、握り潰されない ----
{
  const { sub, main } = await fresh();
  const r = sub("raise ValueError('probe negative control')", 0);
  check("サブインタプリタ内の例外 → ok:false stage:exec + traceback、main は継続", !r.ok && r.stage === "exec" && /probe negative control/.test(r.err) && main("x = 1").ok, r);
}

// ---- 7. 作成/実行/破棄の反復コスト (n=50 を 3 回 = 150 個 / 系列)・wasm メモリ ----
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
  const withHost = await series(`import json, re, _flhost\nresult = json.dumps(_flhost.call(${FN_CHANNEL_COUNT}, ()))`, 0);
  const legacyHost = await series(`import json, re, _flhost\nresult = json.dumps(_flhost.call(${FN_CHANNEL_COUNT}, ()))`, 2);
  detail.create_run_destroy_ms_per_interp = { n: 50, isolated_json_re: base, isolated_with_flhost: withHost, legacy_with_flhost: legacyHost };
  check("150 回 (50×3) の作成/実行/破棄が 3 系列 (isolated json+re / isolated+_flhost / legacy+_flhost) とも全て成功し、各系列で wasm メモリが増えない",
    [base, withHost, legacyHost].every((x) => x.allOk && x.mem_after === x.mem_before), { base, withHost, legacyHost });
}
// 情報 (check 無し): 同一 instance で 20 回ずつ 8 区間 (160 回) の wasm メモリ推移。増加の時期 (一度きりか線形か) を見る
{
  const { M, sub } = await fresh();
  const mem = [M.HEAPU8.length];
  for (let b = 0; b < 8; b++) { for (let i = 0; i < 20; i++) sub("import json, re\nresult = '1'", 0); mem.push(M.HEAPU8.length); }
  detail.heap_bytes_after_each_20_isolated_json_re = mem;
}

const failed = Object.entries(checks).filter(([, v]) => !v).map(([k]) => k);
const NEG_KEY = "isolated: 拒否される builtin は {_elementtree,_lsprof,faulthandler,pyexpat} の 4/66 (全て 'does not support loading in subinterpreters')";
const ok = Object.keys(checks).length > 0 && (neg ? failed.length === 1 && failed[0] === NEG_KEY : failed.length === 0);
console.log((ok ? (neg ? "STATIC SUBINTERP NEG-CONTROL DETECTED " : "STATIC SUBINTERP OK ") : "STATIC SUBINTERP FAIL ") + JSON.stringify({ ok, neg, checks: Object.keys(checks).length, failed, detail }));
process.exit(ok ? (neg ? 1 : 0) : 2);
