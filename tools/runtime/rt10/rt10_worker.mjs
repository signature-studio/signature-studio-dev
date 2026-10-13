// RT-10 (#128): 実 FLEngine x64c lift (boot 連鎖) を Chrome Worker で fetch → compile → instantiate → boot 実行し、
// 各相の所要 (performance.now) を返す。cfg は measure.mjs が postMessage で渡す。
//   cfg: { wasmUrl, glueUrl, mode: 'stream'|'bytes', boots: N (同一 Module から作る instance 数),
//          soakSec: >0 なら instance 作成→boot→破棄を soakSec 秒ループ }
const classify = (e) => {
  if (e && e.fle_kind) return e.fle_kind + (e.fle_a !== undefined ? ':0x' + (e.fle_a >>> 0).toString(16) : '');
  return String((e && e.message) || e).slice(0, 120);
};
const mem = () => (performance.memory ? { jsHeapUsedMB: performance.memory.usedJSHeapSize / 1048576, jsHeapTotalMB: performance.memory.totalJSHeapSize / 1048576 } : {});

self.onmessage = async (ev) => {
  const cfg = ev.data;
  const out = { cfg, phases: {}, boots: [], soak: [] };
  try {
    const T0 = performance.now();
    const tg = performance.now();
    const glue = await import(cfg.glueUrl);
    out.phases.glueImportMs = performance.now() - tg;

    const tf = performance.now();
    const resp = await fetch(cfg.wasmUrl);
    out.phases.fetchHeadersMs = performance.now() - tf;
    let module;
    if (cfg.mode === 'bytes') {
      const buf = await resp.arrayBuffer();
      out.phases.fetchBodyMs = performance.now() - tf;
      const tc = performance.now();
      module = await WebAssembly.compile(buf);
      out.phases.compileOnlyMs = performance.now() - tc;
      out.phases.wasmBytes = buf.byteLength;
    } else {
      module = await WebAssembly.compileStreaming(resp);
      out.phases.fetchCompileStreamingMs = performance.now() - tf;
    }
    out.phases.fetchCompileMs = performance.now() - tf;
    const res = performance.getEntriesByName(cfg.wasmUrl).pop();
    if (res) out.phases.resource = { transferSize: res.transferSize, encodedBodySize: res.encodedBodySize, decodedBodySize: res.decodedBodySize, deliveryType: res.deliveryType, durationMs: res.duration };

    let errLines = 0;
    const make = async () => {
      const t = performance.now();
      const m = await glue.default({
        print: () => {}, printErr: () => { errLines++; },
        instantiateWasm(imports, cb) { WebAssembly.instantiate(module, imports).then((i) => cb(i, module)); return {}; },
      });
      return { m, ms: performance.now() - t };
    };
    const boot = (m) => {
      const t = performance.now();
      let threw = null;
      try { m._fle_boot_enter(0); } catch (e) { threw = classify(e); }
      const ms = performance.now() - t;
      return { bootMs: ms, units_run: Number(m._fle_units_run()), units_total: Number(m._fle_units_total()), stage: Number(m._fle_boot_stage()),
        getmem: Number(m._fle_n_getmem()), freemem: Number(m._fle_n_freemem()), threw, wasmMemMB: m.HEAPU8.length / 1048576 };
    };

    for (let i = 0; i < (cfg.boots || 1); i++) {
      const e0 = errLines;
      const { m, ms } = await make();
      const t1 = performance.now();
      const b = boot(m);
      b.instantiateMs = ms; b.errLines = errLines - e0; b.sinceT0Ms = performance.now() - T0; b.iter = i;
      Object.assign(b, mem());
      out.boots.push(b);
      if (i === 0) {
        out.phases.firstInstantiateMs = ms; out.phases.firstBootMs = b.bootMs;
        out.phases.totalToFirstBootDoneMs = performance.now() - T0;
      }
    }

    if (cfg.soakSec > 0) {
      const end = performance.now() + cfg.soakSec * 1000;
      let n = 0;
      while (performance.now() < end) {
        const e0 = errLines;
        const { m, ms } = await make();
        const b = boot(m);
        n++;
        out.soak.push({ n, t: Math.round(performance.now() - T0), instantiateMs: ms, bootMs: b.bootMs, units_run: b.units_run, stage: b.stage, errLines: errLines - e0, ...mem() });
        await new Promise((r) => setTimeout(r, 0));
      }
    }
    out.ok = true;
  } catch (e) {
    out.ok = false; out.error = String((e && e.stack) || e).slice(0, 600);
  }
  self.postMessage(out);
};
