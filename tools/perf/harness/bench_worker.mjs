// Chrome Dedicated Worker 内ベンチ (AudioWorklet と同じ非メインスレッド条件). node_one.mjs と同一手順。
import * as B from './bench_core.mjs';
self.onmessage = async (e) => {
  try {
    const { kind = 'ott', variant, iters = 20000, head = 300 } = e.data;
    const out = { env: 'chrome-worker', kind, variant, crossOriginIsolated: self.crossOriginIsolated, ua: navigator.userAgent };
    const glue = `/w/${kind === 'ott' ? 'ott' : kind}/${variant}/${kind === 'ott' ? 'ott' : kind}.mjs`;
    const t0 = performance.now();
    const mk = (await import(glue)).default;
    out.importMs = performance.now() - t0;
    const t1 = performance.now();
    const mod = await mk();
    out.createMs = performance.now() - t1;   // fetch + (streaming) compile + instantiate
    let call;
    if (kind === 'ott') { Object.assign(out, B.ottInit(mod)); out.signature = B.ottSignature(mod); call = () => B.ottBlock(mod); }
    else { out.signature = B.m5Signature(mod, kind); B.m5Init(mod, kind); call = () => B.m5Block(mod, kind); }
    const t2 = performance.now(); call(); out.firstCallMs = performance.now() - t2;
    const r = B.runBlocks(call, { warmup: 300, iters, head, batch: kind === 'ott' ? 1 : 64 });
    out.head = r.head.map((x) => +x.toFixed(4)); out.steady = r.steady;
    { const per = new Float64Array(100); for (let i = 0; i < 100; i++) { const t = performance.now(); for (let b = 0; b < 64; b++) call(); per[i] = (performance.now() - t) / 64; } out.batch64 = B.stats(per); }
    out.rtf44 = r.steady.p50 / B.BUDGET.k44; out.rtf48 = r.steady.p50 / B.BUDGET.k48; out.rtf44p99 = r.steady.p99 / B.BUDGET.k44;
    if (kind === 'ott') out.checksum = B.ottChecksum(mod);
    postMessage({ type: 'done', result: out });
  } catch (err) { postMessage({ type: 'err', msg: String(err && err.stack || err) }); }
};
