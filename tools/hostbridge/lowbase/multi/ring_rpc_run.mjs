// ring_rpc_run.mjs — #1174 受入 3・4 の headless Chrome 検証 (lowbase_e2e.sh から呼ぶ)。
//   受入 4 (RPC): page(main thread) が SAB の rpc 領域へ LOAD/CONFIG/BLOCK を書き、Worker が Atomics.wait で受けて
//                 VSTPluginMain 経由 (host_load_plugin / host_process) で処理し RET を返す往復。先頭 NRPC ブロックの出力ビットが node 参照と一致。
//   受入 3 (ring): Worker が残りブロックを SAB ring へ流し、AudioWorklet (ring_worklet.js) が ring を消費。消費量と総和が node 参照と一致。
//   node ring_rpc_run.mjs --stage <dir> --ref <ring_ref.json> [--out <result.json>]
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { H, NBLK, NRPC, CAP, R_REQ, R_RESP, R_RET, OP_LOAD, OP_CONFIG, OP_BLOCK, OP_SHUTDOWN } from './ring_common.mjs';
const HERE = path.dirname(fileURLToPath(import.meta.url));
const RT = path.join(HERE, '../../../runtime/lib');
const { serve } = await import(path.join(RT, 'serve.mjs'));
const { launchChrome } = await import(path.join(RT, 'chrome.mjs'));
const arg = (k, d) => { const i = process.argv.indexOf('--' + k); return i > 0 ? process.argv[i + 1] : d; };
const STAGE = arg('stage'), REF = arg('ref'), OUT = arg('out');
const ref = JSON.parse(fs.readFileSync(REF, 'utf8'));

const PAGE = `
const NBLK=${NBLK}, NRPC=${NRPC}, H=${H}, CAP=${CAP}, R_REQ=${R_REQ}, R_RESP=${R_RESP}, R_RET=${R_RET};
const OP_LOAD=${OP_LOAD}, OP_CONFIG=${OP_CONFIG}, OP_BLOCK=${OP_BLOCK}, OP_SHUTDOWN=${OP_SHUTDOWN};
const R = { ok: false, errors: [] };
window.__r = null;
(async () => {
  try {
    const ring = new SharedArrayBuffer(CAP * 4), ctl = new SharedArrayBuffer(8), rpc = new SharedArrayBuffer(64);
    const ctlI = new Int32Array(ctl), rpcI = new Int32Array(rpc);
    const w = new Worker('ring_rpc_worker.mjs', { type: 'module' });
    const ready = new Promise((res, rej) => { w.onmessage = (ev) => { if (ev.data.type === 'ready') res(); if (ev.data.type === 'error') rej(new Error(ev.data.msg)); }; });
    w.postMessage({ type: 'init', ring, ctl, rpc });
    await ready;
    const I = (v) => v >>> 0;
    const call = async (op, arg) => {
      Atomics.store(rpcI, 2, op); Atomics.store(rpcI, 3, arg); Atomics.store(rpcI, R_RESP, 0);
      Atomics.store(rpcI, R_REQ, 1); Atomics.notify(rpcI, R_REQ);
      while (Atomics.load(rpcI, R_RESP) === 0) await Atomics.waitAsync(rpcI, R_RESP, 0).value;
      return Atomics.load(rpcI, R_RET);
    };
    const t0 = performance.now();
    R.handle = await call(OP_LOAD, 0);
    await call(OP_CONFIG, 0);
    R.rpc_out0_bits = [];
    for (let b = 0; b < NRPC; b++) R.rpc_out0_bits.push(I(await call(OP_BLOCK, b)));
    R.rpc_ms = performance.now() - t0;
    await call(OP_SHUTDOWN, 0);
    const actx = new AudioContext({ sampleRate: 44100 });
    await actx.audioWorklet.addModule('ring_worklet.js');
    const total = (NBLK - NRPC) * 2 * H;
    const node = new AudioWorkletNode(actx, 'ring-consumer', { numberOfInputs: 0, numberOfOutputs: 1, processorOptions: { ring, ctl, cap: CAP, H, total } });
    node.connect(actx.destination);
    const done = new Promise((res) => { node.port.onmessage = (ev) => { if (ev.data.done) res(ev.data); }; });
    await actx.resume();
    R.worklet = await Promise.race([done, new Promise((_, rej) => setTimeout(() => rej(new Error('worklet timeout')), 120000))]);
    R.ring_consumed = Atomics.load(ctlI, 1);
    R.ok = true;
  } catch (e) { R.errors.push(String(e && e.stack || e)); }
  window.__r = R;
})();
`;
fs.writeFileSync(path.join(STAGE, 'ring_page.mjs'), PAGE);
fs.writeFileSync(path.join(STAGE, 'index.html'), '<!doctype html><meta charset=utf-8><title>ring-rpc</title><script src="ring_page.mjs"></script>');

const srv = await serve([{ prefix: '/', dir: STAGE }]);
const chrome = await launchChrome();
let ok = false; const out = {};
try {
  const page = await chrome.newPage(`http://127.0.0.1:${srv.port}/index.html`);
  const r = await page.waitForExpr('window.__r', 600000);
  out.chrome = r; out.chrome_version = chrome.version;
  const checks = [];
  const ck = (n, c, x = '') => { console.log(c ? 'OK  ' : 'FAIL', n, x); checks.push({ name: n, ok: !!c, extra: String(x) }); return !!c; };
  const rpcOk = r.ok && r.handle !== 0 && Array.isArray(r.rpc_out0_bits);
  const rpcMatch = rpcOk && JSON.stringify(r.rpc_out0_bits) === JSON.stringify(ref.rpc_out0_bits);
  const workletDone = r.ok && r.worklet && r.worklet.done;
  const consumedOk = workletDone && r.ring_consumed === ref.ring_floats;
  const sumMatch = workletDone && r.worklet.sum === ref.ring_sum;
  const results = [
    ck(`A4 RPC: Worker が Atomics.wait で LOAD/CONFIG/BLOCK×${NRPC} を受け VSTPluginMain 経由で処理し RET が返る`, rpcOk, `handle ${r.handle} rpc ${r.rpc_ms ? r.rpc_ms.toFixed(1) : '?'} ms`),
    ck(`A4b RPC 出力 (先頭 ${NRPC} ブロック L[0] のビット) = node 参照`, rpcMatch, JSON.stringify(r.rpc_out0_bits)),
    ck(`A3a AudioWorklet が ring を消費 (消費量 = 期待 ${ref.ring_floats} float)`, consumedOk, `consumed ${r.ring_consumed}`),
    ck('A3b AudioWorklet の総和 = node 参照 (bit 一致)', sumMatch, `worklet ${r.worklet && r.worklet.sum} vs ref ${ref.ring_sum}`),
  ];
  if (r.errors.length) console.log('FAIL errors', r.errors.join('|'));
  ok = results.every(Boolean) && !r.errors.length;
  out.checks = checks;
} finally { await chrome.close(); await srv.close(); }
if (OUT) fs.writeFileSync(OUT, JSON.stringify(out, null, 1));
process.exit(ok ? 0 : 1);
