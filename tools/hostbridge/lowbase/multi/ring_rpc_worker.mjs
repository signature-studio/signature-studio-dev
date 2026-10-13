// ring_rpc_worker.mjs — headless Chrome の dedicated Worker 内で OTT lowbase を動かす (#1174 受入 3・4)。
//   1) RPC サーバ: main thread (client) が SAB の rpc 領域へ LOAD/CONFIG/BLOCK/SHUTDOWN を書き、本 Worker は
//      Atomics.wait(REQ) で待って VSTPluginMain 経由 (host_load_plugin / host_process) で処理し、結果を RET に返す。
//   2) ring producer: RPC で処理した先頭 NRPC ブロックに続けて残り全ブロックの OTT 出力を SAB ring (Float32, L,R interleave) へ流す。
//      消費は AudioWorklet (ring_worklet.js) が行う。
// Atomics.wait は本 Worker でのみ使う。AudioWorklet 側は ring 消費 (load/store) 専用 (RT-4 #123)。
import { ModuleTable, HostBridge, EmscriptenGuest } from './hb_bridge.mjs';
import { H, NBLK, NRPC, CAP, SR, C_WR, C_RD, R_REQ, R_RESP, R_OP, R_ARG, R_RET, OP_LOAD, OP_CONFIG, OP_BLOCK, OP_SHUTDOWN, PLUGIN_VENDOR, PLUGIN_ALIAS, PATH, configure, wstr, mkAudio, processBlock, accum } from './ring_common.mjs';
globalThis.Buffer = { from: (s) => Uint8Array.from(s, (c) => c.charCodeAt(0)) };
const loadFactory = async (url) => new Function((await (await fetch(url)).text()) + '\n;return createModule;')();

const S = {};
const boot = async () => {
  const ottF = await loadFactory('ott_hb.cjs');
  const pool = [new EmscriptenGuest(await ottF())];
  const desc = { id: 'xfer.ott.vst2#0', name: 'OTT', vendor: PLUGIN_VENDOR, format: 'vst2', arch: 'x64', aliases: [PLUGIN_ALIAS],
    exports: { VSTPluginMain: 'VSTPluginMain', main: 'VSTPluginMain' }, acquire() { return pool.pop(); }, release() {} };
  const table = new ModuleTable(); table.register(desc);
  const bridge = new HostBridge(table);
  const hostBytes = await (await fetch('host_vst2.wasm')).arrayBuffer();
  const inst = new WebAssembly.Instance(new WebAssembly.Module(hostBytes), bridge.imports()); bridge.attachHost(inst);
  Object.assign(S, { x: inst.exports, bridge, e: 0, au: null });
};

// RPC サーバ。RET には Float32 として書いた値 (BLOCK は出力 L[0] のビット) を入れる。
const serveRpc = () => {
  const rpc = S.rpc, rpcF = new Float32Array(rpc.buffer);
  for (;;) {
    while (Atomics.load(rpc, R_REQ) === 0) Atomics.wait(rpc, R_REQ, 0);
    const op = Atomics.load(rpc, R_OP), arg = Atomics.load(rpc, R_ARG);
    if (op === OP_LOAD) { S.e = S.x.host_load_plugin(wstr(S.x, PATH(PLUGIN_VENDOR, PLUGIN_ALIAS)), SR, H); S.au = mkAudio(S.x); Atomics.store(rpc, R_RET, S.e); }
    else if (op === OP_CONFIG) { configure(S.x, S.e); Atomics.store(rpc, R_RET, 1); }
    else if (op === OP_BLOCK) { const out = processBlock(S.x, S.e, S.au, arg * H); rpcF[R_RET] = out[0]; }
    Atomics.store(rpc, R_REQ, 0);
    Atomics.store(rpc, R_RESP, 1);
    Atomics.notify(rpc, R_RESP);
    if (op === OP_SHUTDOWN) return;
  }
};

// ring producer: NRPC..NBLK の残りブロックを ring へ。空きが無ければ consumer の C_RD を待つ (setTimeout)。
const produce = async () => {
  const ring = S.ring, ctl = S.ctl; let wr = S.wr; let sum = S.sum; const chunk = new Float32Array(2 * H);
  for (let b = NRPC; b < NBLK; b++) {
    const out = processBlock(S.x, S.e, S.au, b * H);
    sum = accum(sum, out);
    for (let i = 0; i < H; i++) { chunk[2 * i] = out[i]; chunk[2 * i + 1] = out[H + i]; }
    for (;;) { if (CAP - (wr - Atomics.load(ctl, C_RD)) >= 2 * H) break; await new Promise((r) => setTimeout(r, 1)); }
    for (let i = 0; i < 2 * H; i++) ring[(wr + i) % CAP] = chunk[i];
    wr += 2 * H; Atomics.store(ctl, C_WR, wr); Atomics.notify(ctl, C_WR);
  }
  return { sum, wr };
};

self.onmessage = async (ev) => {
  const m = ev.data;
  if (m.type !== 'init') return;
  try {
    await boot();
    S.rpc = new Int32Array(m.rpc); S.ring = new Float32Array(m.ring); S.ctl = new Int32Array(m.ctl);
    S.wr = 0; S.sum = 0;
    postMessage({ type: 'ready' });
    serveRpc();
    postMessage({ type: 'rpc_done' });
    const r = await produce();
    postMessage({ type: 'produced', ...r });
  } catch (e) { postMessage({ type: 'error', msg: String(e && e.stack || e) }); }
};
