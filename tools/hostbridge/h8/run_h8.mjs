// run_h8.mjs — H8 browser probe の実行器 (headless Chrome)。
//   node tools/hostbridge/h8/run_h8.mjs [--out h8.json]
// 検証項目 (probe_main.mjs の C1〜C4):
//   C1 main thread で同期 WebAssembly.Instance が作れ、export が呼べる
//   C2 Worker 内で同期 WebAssembly.Instance が作れる (crossOriginIsolated=true, SAB 利用可)
//   C3 SAB + Atomics.wait/notify による RPC が Worker の wasm を呼び、往復が全件一致する
//   C4 AudioWorklet を配置し、Worker が SAB ring に書いた音声を消費して総和が一致する
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const HERE = path.dirname(fileURLToPath(import.meta.url));
const RT = path.join(HERE, '../../runtime/lib');
const { serve } = await import(path.join(RT, 'serve.mjs'));
const { launchChrome } = await import(path.join(RT, 'chrome.mjs'));
const arg = (k, d) => { const i = process.argv.indexOf('--' + k); return i > 0 ? process.argv[i + 1] : d; };
const OUT = arg('out');

// add(i32,i32)->i32 の最小 wasm を手で組む (外部素材なし)
function addWasm() {
  const sec = (id, body) => [id, body.length, ...body];
  const str = (s) => [s.length, ...Buffer.from(s)];
  return new Uint8Array([
    0x00, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00,
    ...sec(1, [1, 0x60, 2, 0x7f, 0x7f, 1, 0x7f]),          // type
    ...sec(3, [1, 0]),                                      // function
    ...sec(7, [1, ...str('add'), 0x00, 0]),                 // export "add"
    ...sec(10, [1, 7, 0, 0x20, 0, 0x20, 1, 0x6a, 0x0b]),    // code
  ]);
}

const STAGE = fs.mkdtempSync(path.join(process.env.RUNNER_TEMP || os.tmpdir(), 'h8-'));
for (const f of ['probe_main.mjs', 'probe_worker.mjs', 'probe_worklet.mjs']) fs.copyFileSync(path.join(HERE, f), path.join(STAGE, f));
fs.writeFileSync(path.join(STAGE, 'add.wasm'), addWasm());
fs.writeFileSync(path.join(STAGE, 'index.html'),
  '<!doctype html><meta charset=utf-8><title>h8</title><script type="module" src="probe_main.mjs"></script>');

const srv = await serve([{ prefix: '/', dir: STAGE }]);
const chrome = await launchChrome({ extraArgs: ['--enable-features=SharedArrayBuffer'] });
let ok = false, R = null;
try {
  const page = await chrome.newPage(`http://127.0.0.1:${srv.port}/index.html`);
  R = await page.waitForExpr('window.__r', 120000);
  ok = !!R.ok;
  R.chrome_version = chrome.version;
  for (const k of Object.keys(R)) if (k.startsWith('C')) console.log(R[k].ok ? 'OK  ' : 'FAIL', k, R[k].extra);
  console.log('INFO', JSON.stringify({ main_ms: R.main_sync_instance_ms, worker_ms: R.worker_sync_instance_ms, rpc_us: R.rpc_us_per_call, audio: R.audio, errors: R.errors }));
} catch (e) {
  console.log('FAIL run', String(e && e.stack || e));
} finally {
  await chrome.close(); await srv.close();
  fs.rmSync(STAGE, { recursive: true, force: true });
}
if (OUT && R) fs.writeFileSync(OUT, JSON.stringify(R, null, 1));
console.log(ok ? 'RESULT PASS' : 'RESULT FAIL');
process.exit(ok ? 0 : 1);
