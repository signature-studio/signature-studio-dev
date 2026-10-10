import { makeImports } from "../lib/emenv.mjs";
self.onmessage = async (ev) => {
  const { url, mode, run } = ev.data;
  const out = { url, mode };
  try {
    const t0 = performance.now();
    let module;
    if (mode === "streaming") {
      const res = await fetch(url);
      out.fetchHeadersMs = +(performance.now() - t0).toFixed(1);
      module = await WebAssembly.compileStreaming(res);
    } else {
      const res = await fetch(url);
      const bytes = new Uint8Array(await res.arrayBuffer());
      out.fetchBytesMs = +(performance.now() - t0).toFixed(1);
      const t1 = performance.now();
      module = await WebAssembly.compile(bytes);
      out.compileOnlyMs = +(performance.now() - t1).toFixed(1);
    }
    out.fetchCompileMs = +(performance.now() - t0).toFixed(1);
    const rt = performance.getEntriesByName(new URL(url, location.href).href).pop();
    out.transferSize = rt?.transferSize; out.deliveryType = rt?.deliveryType;
    let memory = null;
    const { imports } = makeImports(module, { getMemory: () => memory });
    const t2 = performance.now();
    const inst = await WebAssembly.instantiate(module, imports);
    out.instantiateMs = +(performance.now() - t2).toFixed(1);
    memory = inst.exports.memory;
    if (run) {
      const t3 = performance.now();
      try { inst.exports.m11_boot_enter(0n, 1n); } catch (e) { out.firstCallThrew = String(e.message || JSON.stringify(e)).slice(0, 60); }
      out.firstCallMs = +(performance.now() - t3).toFixed(1);
      const t4 = performance.now();
      try { inst.exports.m11_boot_enter(0n, 1n); } catch {}
      out.secondCallMs = +(performance.now() - t4).toFixed(1);
    }
    out.ok = true;
  } catch (e) { out.ok = false; out.err = String(e.stack || e).slice(0, 300); }
  postMessage(out);
};
