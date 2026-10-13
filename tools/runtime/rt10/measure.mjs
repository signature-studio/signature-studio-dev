// RT-10 (#128) 実 FLEngine lift の Chrome 計測オーケストレータ。
//   node tools/runtime/rt10/measure.mjs <exp> [opts]      結果は tools/runtime/rt10/results/rt10_<exp>.jsonl に追記
//   exp: sizes | cold | warm | bw | tier | soak
//   opts: --reps N  --flags default,eager,liftoff,notier  --mode stream,bytes  --boots N  --mbps 10,100  --sec S  --wasm <dir>
// wasm/glue は tools/runtime/rt10/build_fle_boot.sh の出力 (tools/flelift/work/boot/web/)。
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import zlib from 'node:zlib';
import cp from 'node:child_process';
import { launchChrome } from '../../perf/harness/cdp.mjs';

const a = process.argv.slice(2);
const exp = a[0];
const opt = (k, d) => { const i = a.indexOf('--' + k); return i >= 0 ? a[i + 1] : d; };
const here = new URL('./', import.meta.url).pathname;
const WEB = path.resolve(opt('wasm', path.join(here, '../../flelift/work/boot/web')));
const RES = path.join(here, 'results');
fs.mkdirSync(RES, { recursive: true });
process.env.PERF_TMP ||= path.join(process.env.RUNNER_TEMP || os.tmpdir(), 'rt10_ud');
fs.mkdirSync(process.env.PERF_TMP, { recursive: true });
const jf = path.join(RES, `rt10_${exp}${opt('tag', '')}.jsonl`);   // --tag _neg 等でファイル名を分ける
const log = (o) => { fs.appendFileSync(jf, JSON.stringify(o) + '\n'); console.error(JSON.stringify(o).slice(0, 600)); };

const FLAGS = {
  default: '', eager: '--no-wasm-lazy-compilation', liftoff: '--liftoff-only', notier: '--no-wasm-dynamic-tiering',
  eagerliftoff: '--no-wasm-lazy-compilation --liftoff-only',
};
const reps = +opt('reps', 3);
const flagsList = opt('flags', 'default').split(',');
const modes = opt('mode', 'stream').split(',');
const ENC = opt('enc', 'br');   // br = 事前圧縮 .br を Content-Encoding: br で配信 / none = 無圧縮

// ---------------- server: br 事前圧縮の配信 + 帯域制限 ----------------
async function startServer() {
  const stats = { reqs: [] };
  const srv = http.createServer((req, res) => {
    const u = new URL(req.url, 'http://x');
    const m = u.pathname.match(/^\/(w|h)\/(.+)$/);
    if (!m) { res.writeHead(404); res.end(); return; }
    let file = path.join(m[1] === 'w' ? WEB : here, m[2]);
    const br = u.searchParams.get('enc') === 'br';
    if (br) file += '.br';
    if (!fs.existsSync(file)) { res.writeHead(404); res.end('nf ' + file); return; }
    const st = fs.statSync(file);
    const h = {
      'Content-Type': m[2].endsWith('.wasm') ? 'application/wasm' : m[2].endsWith('.html') ? 'text/html' : 'text/javascript',
      'Cross-Origin-Opener-Policy': 'same-origin', 'Cross-Origin-Embedder-Policy': 'require-corp', 'Cross-Origin-Resource-Policy': 'same-origin',
      'Cache-Control': u.searchParams.get('cc') || 'no-store', 'Content-Length': st.size,
    };
    if (br) h['Content-Encoding'] = 'br';
    res.writeHead(200, h);
    stats.reqs.push({ path: u.pathname + u.search, bytes: st.size });
    const bps = +(u.searchParams.get('bps') || 0);
    const rs = fs.createReadStream(file, { highWaterMark: bps ? Math.max(4096, Math.floor(bps / 100)) : 1 << 20 });
    if (!bps) { rs.pipe(res); return; }
    rs.on('data', (c) => { rs.pause(); res.write(c, () => setTimeout(() => rs.resume(), 10)); });
    rs.on('end', () => res.end());
  });
  await new Promise((r) => srv.listen(0, '127.0.0.1', r));
  return { url: `http://127.0.0.1:${srv.address().port}`, stats, close: () => new Promise((r) => { srv.closeAllConnections?.(); srv.close(r); }) };
}

const rss = (b) => {
  const r = b.procs().filter((x) => x.type === 'renderer').sort((x, y) => y.rssMB - x.rssMB)[0];
  return r ? { rssMB: r.rssMB, hwmMB: r.hwmMB, vmsizeMB: r.vmsizeMB } : null;
};

// 1 回: (新規 or 既存) Chrome で page を開き worker に cfg を渡して結果を得る。
async function runOnce(srv, cfg, { flags = 'default', cpus = null, browser = null, ud = null, keepUd = false, sample = 0 } = {}) {
  const b = browser || await launchChrome({ jsFlags: FLAGS[flags] ?? flags, cpus, ud, keepUd });
  const la = os.loadavg()[0];
  const out = { exp, flags, cpus, load: la, chrome: b.version.product };
  let series = [], timer = null;
  try {
    const p = await b.newPage(`${srv.url}/h/rt10.html`);
    if (sample) timer = setInterval(() => { const r = rss(b); if (r) series.push({ t: Date.now() - t0, ...r }); }, sample);
    const t0 = Date.now();
    const res = await p.eval(`rt10Run(${JSON.stringify(cfg)})`, { timeout: (cfg.soakSec || 0) * 1000 + 900000 });
    out.wallMs = Date.now() - t0;
    out.isolated = await p.eval('window.rt10Isolated');
    Object.assign(out, res);
    out.rss = rss(b);
    if (series.length) out.rssSeries = series;
  } catch (e) { out.ok = false; out.error = String(e.message).slice(0, 400); }
  finally { if (timer) clearInterval(timer); if (!browser) await b.close(); }
  return out;
}

const url = (srv, f, q) => `${srv.url}/w/${f}?${q}`;
const base = (srv, o = {}) => ({ wasmUrl: url(srv, 'fleweb.wasm', o.q || `enc=${ENC}`), glueUrl: url(srv, 'fleweb.mjs', 'enc=none'), mode: 'stream', boots: 1, ...o.cfg });

async function main() {
  const srv = await startServer();
  try {
    if (exp === 'cold') {
      for (const fl of flagsList) for (const mode of modes) for (let r = 0; r < reps; r++)
        log(await runOnce(srv, base(srv, { cfg: { mode } }), { flags: fl, sample: 250 }).then((o) => ({ ...o, rep: r, mode })));
    } else if (exp === 'bw') {
      for (const mbps of opt('mbps', '10,50,100,1000').split(',').map(Number)) for (const fl of flagsList) for (const mode of modes) {
        const bps = Math.round(mbps * 1e6 / 8);
        for (let r = 0; r < reps; r++)
          log(await runOnce(srv, base(srv, { q: `enc=${ENC}&bps=${bps}`, cfg: { mode } }), { flags: fl }).then((o) => ({ ...o, rep: r, mode, mbps })));
      }
    } else if (exp === 'warm') {
      // 同一 profile で 3 回ロード (1 回目 = HTTP cache cold、2・3 回目 = immutable で cache hit)。さらに browser 再起動後 (ud 再利用) を 1 回。
      for (const fl of flagsList) for (let r = 0; r < reps; r++) {
        const ud = fs.mkdtempSync(path.join(process.env.PERF_TMP, 'warm-'));
        const q = `enc=${ENC}&cc=public,max-age=31536000,immutable`;
        const cfg = base(srv, { q, cfg: {} });
        let b = await launchChrome({ jsFlags: FLAGS[fl] ?? fl, ud, keepUd: true });
        for (let i = 0; i < 3; i++) log(await runOnce(srv, cfg, { flags: fl, browser: b }).then((o) => ({ ...o, rep: r, load_no: i + 1, restart: false })));
        await b.close();
        b = await launchChrome({ jsFlags: FLAGS[fl] ?? fl, ud, keepUd: true });
        log(await runOnce(srv, cfg, { flags: fl, browser: b }).then((o) => ({ ...o, rep: r, load_no: 4, restart: true })));
        await b.close();
        fs.rmSync(ud, { recursive: true, force: true });
      }
    } else if (exp === 'tier') {
      const boots = +opt('boots', 6);
      for (const fl of flagsList) for (let r = 0; r < reps; r++)
        log(await runOnce(srv, base(srv, { cfg: { boots } }), { flags: fl }).then((o) => ({ ...o, rep: r })));
    } else if (exp === 'soak') {
      const sec = +opt('sec', 180);
      for (const fl of flagsList)
        log(await runOnce(srv, base(srv, { cfg: { soakSec: sec } }), { flags: fl, sample: 5000 }).then((o) => ({ ...o, soakSec: sec })));
    } else throw new Error('unknown exp ' + exp);
  } finally { await srv.close(); }
}

if (exp === 'sizes') {
  // wasm の構成と圧縮率。brotli は事前圧縮 (.br) も生成する (q11, lgwin 24 = Chrome が復号できる最大窓)。
  const f = path.join(WEB, opt('name', 'fleweb.wasm'));
  const buf = fs.readFileSync(f);
  const u8 = new Uint8Array(buf);
  const leb = (o) => { let r = 0, s = 0, i = o; for (;;) { const x = u8[i++]; r += (x & 0x7f) * 2 ** s; s += 7; if (!(x & 0x80)) break; } return [r, i]; };
  const secs = {}; let o = 8, funcs = 0, imports = 0, exportsN = 0;
  while (o < u8.length) {
    const id = u8[o++]; const [size, p] = leb(o); let name = String(id);
    if (id === 0) { const [nl, q] = leb(p); name = 'custom:' + Buffer.from(u8.subarray(q, q + nl)).toString(); }
    secs[name] = (secs[name] || 0) + size;
    if (id === 3) funcs = leb(p)[0]; if (id === 2) imports = leb(p)[0]; if (id === 7) exportsN = leb(p)[0];
    o = p + size;
  }
  const res = { exp, file: path.relative(path.resolve(here, '../../..'), f), bytes: buf.length, sections: secs, funcCount: funcs, importCount: imports, exportCount: exportsN, sections_legend: '1=type 2=import 3=function 5=memory 7=export 10=code 11=data' };
  const t = (fn) => { const s = process.hrtime.bigint(); const v = fn(); return [v, Number(process.hrtime.bigint() - s) / 1e9]; };
  if (opt('compress', '1') === '1') {
    const [br, brS] = t(() => zlib.brotliCompressSync(buf, { params: { [zlib.constants.BROTLI_PARAM_QUALITY]: 11, [zlib.constants.BROTLI_PARAM_LGWIN]: 24, [zlib.constants.BROTLI_PARAM_SIZE_HINT]: buf.length } }));
    fs.writeFileSync(f + '.br', br);
    const [, brD] = t(() => zlib.brotliDecompressSync(br));
    const [gz, gzS] = t(() => zlib.gzipSync(buf, { level: 9 }));
    res.brotli = { q11_lgwin24_bytes: br.length, ratio: buf.length / br.length, compressSec: brS, decompressNodeSec: brD };
    res.gzip9 = { bytes: gz.length, ratio: buf.length / gz.length, compressSec: gzS };
    try {
      const z = cp.spawnSync('zstd', ['-19', '-T4', '--long=27', '-c', f], { maxBuffer: 1 << 30 });
      res.zstd19 = { bytes: z.stdout.length, ratio: buf.length / z.stdout.length };
    } catch {}
  }
  log(res);
  process.exit(0);
} else { await main(); process.exit(0); }
