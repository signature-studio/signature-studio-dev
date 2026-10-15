// PY-108 (#2918): 静的版の subinterp 反復 (flpy_subinterp_run を N 回) で、wasm 線形メモリ (HEAPU8) と
//   サブインタプリタ内の sys.getallocatedblocks() がどう変わるかを、任意の Python コードで測る。
//   query: static (wasm 名)・mode (0 isolated / 2 legacy)・n (反復数)・code (毎回実行する Python)。
//   結果は #result に "RESULT {json}" で出す。driver: tests/static64_growth_probe.mjs
const J = JSON.stringify;
const q = new URLSearchParams(location.search);
const name = q.get("static") || "flpy_static64";
const mode = Number(q.get("mode") || 0);
const N = Number(q.get("n") || 160);
const every = Number(q.get("every") || 20);
const code = q.get("code") || "result = '1'";
const out = { wasm: name, mode, n: N, code, ua: navigator.userAgent, crossOriginIsolated };
const t0 = performance.now();
try {
  const bytes = new Uint8Array(await (await fetch(`/dist/${name}.wasm`)).arrayBuffer());
  out.wasm_bytes = bytes.length;
  out.validate = WebAssembly.validate(bytes);
  const printed = [];
  const create = (await import(`/dist/${name}.js`)).default;
  const M = await create({ locateFile: (p) => `/dist/${p}`, print: (t) => printed.push(t), printErr: (t) => printed.push("ERR " + t) });
  const is64 = typeof M._flpy_last_error() === "bigint";
  out.ptr_is_bigint = is64;
  const FP = (x) => (is64 ? BigInt(x) : Number(x));
  const Nm = (x) => Number(x);
  const cstr = (ptr) => M.UTF8ToString(Nm(ptr));
  const withStr = (s, f) => {
    const n = M.lengthBytesUTF8(s) + 1;
    const p = M._malloc(n);
    M.stringToUTF8(s, p, n);
    try { return f(FP(p)); } finally { M._free(p); }
  };
  const sub = (src, m) => {
    const p = withStr(src, (c) => M._flpy_subinterp_run(c, m));
    const s = cstr(p);
    M._flpy_free(p);
    return JSON.parse(s);
  };
  out.init_rc = withStr("", (p) => M._flpy_init(p));
  if (out.init_rc !== 0) out.init_err = cstr(M._flpy_last_error());
  const heap = () => M.HEAPU8.buffer.byteLength;
  out.heap_before = heap();
  out.samples = [{ n: 0, heap: heap() }];
  let okCount = 0;
  const t1 = performance.now();
  for (let i = 1; i <= N; i++) {
    const r = sub(code, mode);
    if (r.ok) okCount++;
    else if (!out.first_bad) out.first_bad = { i, r };
    if (i % every === 0 || i === N) out.samples.push({ n: i, heap: heap(), result: r.ok ? r.result : null });
  }
  out.loop_ms = Math.round(performance.now() - t1);
  out.ok_count = okCount;
  out.heap_after = heap();
  out.heap_grew = out.heap_after > out.heap_before;
  out.ok = out.validate && out.init_rc === 0 && okCount === N;
} catch (e) { out.error = String(e && e.stack || e); out.ok = false; }
out.total_ms = Math.round(performance.now() - t0);
document.getElementById("result").textContent = "RESULT " + J(out);
