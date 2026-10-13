// run_chrome.mjs — lowbase の multi-load を headless Chrome (Worker) で実行し、node 結果 (multi_load --out) と sha256 を突合する.
//   node run_chrome.mjs --stage <dir> --node-json ml_lb.json [--nmod 4] [--nspawn 100] [--out chrome.json]
import fs from 'node:fs';
import path from 'node:path';
import { execSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
const HERE = path.dirname(fileURLToPath(import.meta.url));
const RT = path.join(HERE, '../../../runtime/lib');
const { serve } = await import(path.join(RT, 'serve.mjs'));
const { launchChrome } = await import(path.join(RT, 'chrome.mjs'));
const arg = (k, d) => { const i = process.argv.indexOf('--' + k); return i > 0 ? process.argv[i + 1] : d; };
const STAGE = arg('stage'), NODEJ = arg('node-json'), NMOD = Number(arg('nmod', 4)), NSPAWN = Number(arg('nspawn', 100)), OUT = arg('out');
fs.writeFileSync(path.join(STAGE, 'index.html'), '<!doctype html><meta charset=utf-8><title>lowbase</title><script>window.__r=null;const w=new Worker("chrome_worker.mjs",{type:"module"});w.onmessage=e=>{window.__r=e.data};w.onerror=e=>{window.__r={errors:["worker error "+e.message]}};w.postMessage({nmod:' + NMOD + ',nspawn:' + NSPAWN + ',nblk:500});</script>');
const rssChrome = () => { try { return execSync("ps -eo rss,comm | awk '/chrome/{s+=$1} END{print s/1024}'").toString().trim(); } catch { return '?'; } };
const srv = await serve([{ prefix: '/', dir: STAGE }]);
const chrome = await launchChrome();
let ok = true; const out = {};
try {
  const rss0 = Number(rssChrome());
  const page = await chrome.newPage(`http://127.0.0.1:${srv.port}/index.html`);
  const r = await page.waitForExpr('window.__r', 600000);
  out.chrome = r; out.chrome_version = chrome.version; out.chrome_rss_mb = { before: rss0, after: Number(rssChrome()) };
  console.log('INFO chrome', chrome.version, JSON.stringify({ linear_mib: r.linear_mib, interleave_ms: r.interleave_ms, spawn: r.spawn, spawn_linear_mib_total: r.spawn_linear_mib_total, rss: out.chrome_rss_mb, err: r.errors, spawn_error: r.spawn_error }));
  const nodeR = JSON.parse(fs.readFileSync(NODEJ, 'utf8'));
  const crypto = await import('node:crypto');
  const ck = (n, c, x = '') => { console.log(c ? 'OK  ' : 'FAIL', n, x); if (!c) ok = false; return { name: n, ok: !!c, extra: String(x) }; };
  out.checks = [
    ck('C1 Worker 内で OTT×' + NMOD + ' + Balance kernel が同一 host/bridge に LoadLibrary 成功', r.loaded_ok && !r.errors.length, r.errors.join('|')),
    ck('C2 Chrome Worker の OTT 出力 (500blk×128f) sha256 = node の sha256 (bit 一致)', r.ott0_sha256 === nodeR.ott_sha256_full, `${r.ott0_sha256?.slice(0, 16)} vs ${nodeR.ott_sha256_full?.slice(0, 16)}`),
    ck('C3 Chrome Worker の Balance kernel 出力 block0 sha256 = node', r.bal_first_block_sha256 === nodeR.bal_first_block_sha256, `${r.bal_first_block_sha256?.slice(0, 16)}`),
    ck(`C4 追加 ${NSPAWN} 個の OTT lowbase instance (各 24MiB initial) を Worker 内で生成`, r.spawn && r.spawn.created === NSPAWN, `created ${r.spawn?.created} in ${r.spawn?.ms.toFixed(0)} ms, linear total ${r.spawn_linear_mib_total} MiB`),
    ck('C5 OTT 128 frame 1 処理の実時間 (Chrome Worker) が予算 (128/44100 s) の中央値以内', r.frame128 && r.frame128.median_ms <= r.frame128.budget_ms, r.frame128 ? `median ${r.frame128.median_ms.toFixed(3)} ms / p99 ${r.frame128.p99_ms.toFixed(3)} ms / min ${r.frame128.min_ms.toFixed(3)} ms / budget ${r.frame128.budget_ms.toFixed(3)} ms (n=${r.frame128.n})` : 'frame128 未取得'),
  ];
} finally { await chrome.close(); await srv.close(); }
if (OUT) fs.writeFileSync(OUT, JSON.stringify(out, null, 1));
process.exit(ok ? 0 : 1);
