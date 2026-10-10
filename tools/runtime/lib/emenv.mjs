// bench/spike 用: emscripten 生成 wasm (glue 無し) の最小 imports を introspection で組む。
// 本番実装は src/runtime/{imports_env,loader}.ts。ここは tools 側の依存ゼロ版 (node / browser 両用)。
export function makeImports(module, { getMemory, log = () => {}, extra = {} } = {}) {
  const imports = {};
  const missing = [];
  const wide = (v) => (typeof v === "bigint" ? Number(v) : v);
  const impl = {
    "env.emscripten_get_now": () => performance.now(),
    "env.emscripten_resize_heap": () => 0,
    "env._abort_js": () => { throw new Error("abort()"); },
    "env.exit": (c) => { throw new Error("exit(" + c + ")"); },
    "env.emscripten_err": () => {},
    "env._emscripten_runtime_keepalive_clear": () => {},
    "env.__call_sighandler": () => {},
    "wasi_snapshot_preview1.proc_exit": (c) => { throw new Error("proc_exit(" + c + ")"); },
    "wasi_snapshot_preview1.fd_close": () => 0,
    "wasi_snapshot_preview1.fd_seek": () => 70,
    "wasi_snapshot_preview1.fd_fdstat_get": () => 0,
    "wasi_snapshot_preview1.fd_read": () => 0,
    "wasi_snapshot_preview1.fd_write": (fd, iov, iovcnt, pnum) => {
      const m = getMemory(); const dv = new DataView(m.buffer);
      const ptr = wide(iov), n = wide(iovcnt); let tot = 0, s = "";
      const u8 = new Uint8Array(m.buffer);
      for (let i = 0; i < n; i++) {
        const base = wide(dv.getUint32(ptr + i * 8, true)), len = dv.getUint32(ptr + i * 8 + 4, true);
        s += new TextDecoder().decode(u8.subarray(base, base + len)); tot += len;
      }
      log(fd, s);
      dv.setUint32(wide(pnum), tot, true);
      return 0;
    },
    ...extra,
  };
  for (const { module: mod, name, kind } of WebAssembly.Module.imports(module)) {
    if (kind !== "function") continue;
    const key = `${mod}.${name}`;
    (imports[mod] ??= {})[name] = impl[key] ?? (() => { throw new Error(`fail-fast: unimplemented import ${key}`); });
    if (!impl[key]) missing.push(key);
  }
  return { imports, missing };
}
