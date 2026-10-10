// Chrome (headless=new) 側ベンチ。Worker 内で OTT / M5 カーネルを実行して results/chrome_<tag>.json に集約。
//   node chrome_bench.mjs <tag> <kind> <variants,comma> [--modes default,liftoff,tf] [--reps 3] [--iters 20000] [--cpus 0-3]
import fs from 'node:fs';
import os from 'node:os';
import { startServer } from './server.mjs';
import { launchChrome } from './cdp.mjs';
const a = process.argv.slice(2);
const [tag, kind, vlist] = a;
const opt = (k, d) => { const i = a.indexOf('--' + k); return i >= 0 ? a[i + 1] : d; };
const modes = opt('modes', 'default').split(',');
const reps = +opt('reps', 3), iters = +opt('iters', 20000), cpus = opt('cpus', null);
const JSF = { default: '', liftoff: '--liftoff-only', tf: '--no-liftoff', eager: '--no-wasm-lazy-compilation' };
const here = new URL('./', import.meta.url).pathname;
const srv = await startServer({ '/w': here + '../work', '/h': here });
const jf = new URL(`../results/chrome_${tag}.jsonl`, import.meta.url).pathname;
fs.mkdirSync(new URL('../results/', import.meta.url).pathname, { recursive: true });
const done = new Set(fs.existsSync(jf) ? fs.readFileSync(jf, 'utf8').split('\n').filter(Boolean).map((l) => { const j = JSON.parse(l); return j.error ? "" : `${j.kind}/${j.variant}/${j.mode}/${j.rep}`; }) : []);
const out = [];
for (const m of modes) for (let r = 0; r < reps; r++) {
  const b = await launchChrome({ jsFlags: JSF[m], cpus });
  try {
    for (const v of vlist.split(',')) {
      if (done.has(`${kind}/${v}/${m}/${r}`)) continue;
      const la = os.loadavg()[0];
      const p = await b.newPage(`${srv.url}/h/bench.html`);
      try {
        const res = await p.eval(`runBench(${JSON.stringify({ kind, variant: v, iters, head: 300 })})`, { timeout: 300000 });
        const pr = b.procs().filter((x) => x.type === 'renderer').sort((x, y) => y.rssMB - x.rssMB)[0];
        res.mode = m; res.rep = r; res.load = la; res.chrome = b.version.product; res.v8 = b.version.jsVersion;
        res.rendererRssMB = pr?.rssMB; res.rendererHwmMB = pr?.hwmMB; res.rendererVmSizeMB = pr?.vmsizeMB;
        out.push(res); fs.appendFileSync(jf, JSON.stringify(res) + '\n');
        console.error(`${kind}/${v}/${m}/${r} p50=${res.steady.p50.toFixed(4)}ms p99=${res.steady.p99.toFixed(4)} rtf44=${res.rtf44.toFixed(5)} create=${res.createMs.toFixed(0)}ms sig=${res.signature} rss=${pr?.rssMB?.toFixed(0)}MB`);
        await p.eval('killWorker()');
      } catch (e) { console.error(`${kind}/${v}/${m}/${r} FAIL ${String(e.message).slice(0, 300)}`); const ej = { kind, variant: v, mode: m, rep: r, error: String(e.message).slice(0, 300) }; out.push(ej); fs.appendFileSync(jf, JSON.stringify(ej) + '\n'); }
      await b.send('Target.closeTarget', { targetId: p.targetId }).catch(() => {});
    }
  } finally { await b.close(); }
}
await srv.close();
console.error('done', jf);
process.exit(0);
