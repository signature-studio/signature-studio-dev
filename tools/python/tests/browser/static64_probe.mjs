// PY-98 (#2858): headless Chrome 上で静的版 (flpy_static64 = MEMORY64=1 / flpy_static = wasm32) を main thread で読み、
//   読込 (validate / instantiate)・init・flpy_run の smoke・flpy_subinterp_run (1 回 + 160 回) の heap を測る。
//   結果は #result に "RESULT {json}" で出す。driver: tests/static64_browser_probe.mjs
const J = JSON.stringify;
const q = new URLSearchParams(location.search);
const name = q.get("static") || "flpy_static64";
const N = Number(q.get("n") || 160);
const out = { wasm: name, ua: navigator.userAgent, crossOriginIsolated };
const t0 = performance.now();
try {
  const bytes = new Uint8Array(await (await fetch(`/dist/${name}.wasm`)).arrayBuffer());
  out.wasm_bytes = bytes.length;
  out.validate = WebAssembly.validate(bytes);
  const printed = [];
  const create = (await import(`/dist/${name}.js`)).default;
  const M = await create({ locateFile: (p) => `/dist/${p}`, print: (t) => printed.push(t), printErr: (t) => printed.push("ERR " + t) });
  out.load_ms = Math.round(performance.now() - t0);

  // memory64 (flpy_* の pointer 引数・戻り値は i64 = BigInt)。malloc/free の glue は Number で扱える
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
  const sub = (code, mode) => {
    const p = withStr(code, (c) => M._flpy_subinterp_run(c, mode));
    const s = cstr(p);
    M._flpy_free(p);
    return JSON.parse(s);
  };

  const t1 = performance.now();
  out.init_rc = withStr("", (p) => M._flpy_init(p));
  out.init_ms = Math.round(performance.now() - t1);
  if (out.init_rc !== 0) out.init_err = cstr(M._flpy_last_error());

  const t2 = performance.now();
  out.run_rc = withStr("print(1 + 1)", (c) => withStr("<static>", (f) => M._flpy_run(c, f)));
  out.run_ms = Math.round(performance.now() - t2);
  out.run_stdout = printed.join("\n").slice(0, 200);
  if (out.run_rc !== 0) out.run_err = cstr(M._flpy_last_error());

  const heap = (n) => ({ n, bytes: M.HEAPU8.buffer.byteLength });
  out.heap = [heap(0)];
  const t3 = performance.now();
  const first = sub("result = str(1 + 1)", 0);
  out.sub_once = first;
  out.sub_once_ms = Math.round(performance.now() - t3);
  out.heap.push(heap(1));

  let okCount = 0;
  const t4 = performance.now();
  for (let i = 1; i <= N; i++) {
    const r = sub("result = str(1 + 1)", 0);
    if (r.ok && r.result === "2") okCount++;
    else if (!out.sub_first_bad) out.sub_first_bad = { i, r };
    if (i % 20 === 0 || i === N) out.heap.push(heap(i));
  }
  out.sub_loop_ms = Math.round(performance.now() - t4);
  out.sub_loop_ok = okCount;
  out.sub_loop_n = N;
  out.heap_before = out.heap[0].bytes;
  out.heap_after = out.heap[out.heap.length - 1].bytes;
  out.heap_grew = out.heap_after > out.heap_before;
  out.ok = out.validate && out.init_rc === 0 && out.run_rc === 0 && out.run_stdout.split("\n").includes("2")
    && first.ok && first.result === "2" && okCount === N;
} catch (e) { out.error = String(e && e.stack || e); out.ok = false; }
out.total_ms = Math.round(performance.now() - t0);
document.getElementById("result").textContent = "RESULT " + J(out);
