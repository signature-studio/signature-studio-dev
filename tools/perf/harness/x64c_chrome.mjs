// Chrome (headless=new) 上で bit-exact OTT (x64c wasm) を Dedicated Worker / 実 AudioWorklet で計測。
//   node x64c_chrome.mjs <tag> <worker|worklet> <variants,comma> [--noclock (worklet: SAB 時計 worker 無し・bench のみ)] [--reps 3] [--iters 20000] [--blocks 3000] [--sr 48000] [--cpus 0-3]
// 前提: bash tools/perf/build/ott_x64c_build.sh <variants> 済み。 names.json は本スクリプトが生成する。
import fs from 'node:fs';
import os from 'node:os';
import { startServer } from './server.mjs';
import { launchChrome } from './cdp.mjs';
import { execFileSync } from 'node:child_process';
const a = process.argv.slice(2);
const [tag, mode, vlist] = a;
const opt = (k, d) => { const i = a.indexOf('--' + k); return i >= 0 ? a[i + 1] : d; };
const noclock = a.includes('--noclock');
const reps = +opt('reps', 3), iters = +opt('iters', 20000), blocks = +opt('blocks', 3000), sr = +opt('sr', 48000), cpus = opt('cpus', null);
const here = new URL('./', import.meta.url).pathname;
execFileSync('node', [here + 'x64c_names.mjs', here + '../work/ott_x64c'], { stdio: 'ignore' });
const srv = await startServer({ '/w': here + '../work', '/h': here });
fs.mkdirSync(here + '../results/x64c/', { recursive: true });
const jf = here + `../results/x64c/${mode}${noclock ? '-noclock' : ''}_${tag}.jsonl`;
for (let r = 0; r < reps; r++) {
  const b = await launchChrome({ cpus, extraArgs: mode === 'worklet' ? ['--use-fake-ui-for-media-stream'] : [] });
  try {
    for (const v of vlist.split(',')) {
      const la = os.loadavg()[0];
      const p = await b.newPage(`${srv.url}/h/x64c.html`);
      try {
        const opts = mode === 'worker' ? { variant: v, iters } : { variant: v, blocks, sampleRate: sr, noclock };
        const res = await p.eval(mode === 'worker' ? `runWorker(${JSON.stringify(opts)})` : `runWorklet(${JSON.stringify(opts)})`, { timeout: 300000 });
        res.rep = r; res.loadStart = la; res.loadEnd = os.loadavg()[0]; res.chrome = b.version.product; res.v8 = b.version.jsVersion;
        fs.appendFileSync(jf, JSON.stringify(res) + '\n');
        if (mode === 'worker') console.error(`worker/${v}/${r} p50=${(res.steady.p50 * 1000).toFixed(2)}us p99=${(res.steady.p99 * 1000).toFixed(2)} b64p50=${(res.batch64.p50 * 1000).toFixed(2)} rtf44=${res.rtf44.toFixed(5)} compile=${res.compileMs.toFixed(0)}ms sig=${res.signature} load=${la.toFixed(2)}`);
        else if (noclock) console.error(`worklet-noclock/${v}/${r} sig=${res.signature} bench=${res.bench.meanUsPerBlock.toFixed(2)}us chunks(ms/${res.bench.per}blk)=${res.bench.chunkMs.join(',')} load=${la.toFixed(2)}`);
        else console.error(`worklet/${v}/${r} sig=${res.signature} bench=${res.bench.meanUsPerBlock.toFixed(2)}us rt p50=${res.rt.durUs.p50.toFixed(2)} p99=${res.rt.durUs.p99.toFixed(2)} max=${res.rt.durUs.max.toFixed(1)} over-budget=${res.rt.overBudget} gap p50=${res.rt.gapUs.p50.toFixed(0)}us procCalls=${res.rt.procCalls} tpu=${res.rt.ticksPerUs.toFixed(1)} load=${la.toFixed(2)}`);
        if (mode === 'worker') await p.eval('killWorker()');
      } catch (e) { console.error(`${mode}/${v}/${r} FAIL ${String(e.message).slice(0, 400)}`); fs.appendFileSync(jf, JSON.stringify({ mode, variant: v, rep: r, error: String(e.message).slice(0, 400) }) + '\n'); }
      await b.send('Target.closeTarget', { targetId: p.targetId }).catch(() => {});
    }
  } finally { await b.close(); }
}
await srv.close();
console.error('done', jf);
process.exit(0);
