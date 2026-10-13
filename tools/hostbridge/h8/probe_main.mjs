// probe_main.mjs — H8 probe の main thread 側。結果を window.__r に入れる。
const N_RPC = 1000, N_AUDIO = 1 << 16;
const bytes = new Uint8Array(await (await fetch('add.wasm')).arrayBuffer());
const R = { errors: [] };
const ck = (name, ok, extra = '') => { R[name] = { ok: !!ok, extra: String(extra) }; if (!ok) R.errors.push(name); };

try {
  // C1: main thread で同期 instance 生成
  const t0 = performance.now();
  const mainInst = new WebAssembly.Instance(new WebAssembly.Module(bytes), {});
  R.main_sync_instance_ms = performance.now() - t0;
  ck('C1_main_sync_instance', mainInst.exports.add(2, 3) === 5, mainInst.exports.add(2, 3));

  const rpc = new SharedArrayBuffer(8 * 4);
  const ring = new SharedArrayBuffer(4096 * 4);
  const ringCtrl = new SharedArrayBuffer(4 * 4);
  const stat = new SharedArrayBuffer(3 * 8);
  const rpcI = new Int32Array(rpc), ringI = new Int32Array(ringCtrl), statF = new Float64Array(stat);

  const worker = new Worker('probe_worker.mjs', { type: 'module' });
  const wmsg = (pred) => new Promise((res, rej) => {
    const to = setTimeout(() => rej(new Error('worker timeout')), 20000);
    worker.onmessage = (ev) => { if (pred(ev.data)) { clearTimeout(to); res(ev.data); } };
    worker.onerror = (e) => rej(new Error('worker error ' + e.message));
  });
  const inited = wmsg((d) => d.type === 'inited');
  worker.postMessage({ type: 'init', wasm: bytes.buffer.slice(0), rpc, ring, ringCtrl });
  const wi = await inited;
  // C2: Worker 内で同期 instance 生成 + 別 crossOriginIsolated 文脈
  ck('C2_worker_sync_instance', wi.add_2_3 === 5 && wi.coi === true && wi.sab === 'function', JSON.stringify(wi));
  R.worker_sync_instance_ms = wi.sync_instance_ms;

  // C3: SAB + Atomics RPC round-trip (main → worker の wasm add → main)
  let rpcOk = true, seq = 0;
  const served = wmsg((d) => d.type === 'rpc_done');
  worker.postMessage({ type: 'serve' });
  const t1 = performance.now();
  for (let k = 0; k < N_RPC; k++) {
    const a = k, b = k * 3 + 1;
    Atomics.store(rpcI, 2, a); Atomics.store(rpcI, 3, b);
    seq = Atomics.add(rpcI, 0, 1) + 1;
    Atomics.notify(rpcI, 0);
    while (Atomics.load(rpcI, 1) !== seq) {
      const w = Atomics.waitAsync(rpcI, 1, Atomics.load(rpcI, 1), 5000);
      if (w.async) await w.value;
    }
    if (Atomics.load(rpcI, 4) !== a + b) { rpcOk = false; break; }
  }
  const rpcMs = performance.now() - t1;
  R.rpc_us_per_call = (rpcMs * 1000) / N_RPC;
  ck('C3_sab_rpc_roundtrip', rpcOk, `${N_RPC} calls, ${rpcMs.toFixed(1)} ms`);
  Atomics.store(rpcI, 7, 1); Atomics.add(rpcI, 0, 1); Atomics.notify(rpcI, 0);
  await served;

  // C4: AudioWorklet 配置 + SAB ring からの供給
  const ctx = new AudioContext();
  R.audio = { sampleRate: ctx.sampleRate, state0: ctx.state };
  await ctx.audioWorklet.addModule('probe_worklet.mjs');
  const node = new AudioWorkletNode(ctx, 'ring-reader', { processorOptions: { ring, ringCtrl, stat } });
  node.connect(ctx.destination);
  await ctx.resume();
  const prod = wmsg((d) => d.type === 'produced');
  worker.postMessage({ type: 'produce', n: N_AUDIO });
  await prod;
  const deadline = performance.now() + 20000;
  while (statF[1] < N_AUDIO && performance.now() < deadline) await new Promise((r) => setTimeout(r, 20));
  const expect = (N_AUDIO * (N_AUDIO - 1)) / 2;
  R.audio.consumed = statF[1]; R.audio.sum = statF[0]; R.audio.expect_sum = expect; R.audio.process_calls = statF[2];
  R.audio.state1 = ctx.state;
  ck('C4_audioworklet_ring', statF[1] === N_AUDIO && statF[0] === expect && statF[2] > 0, `consumed ${statF[1]}/${N_AUDIO}, sum ${statF[0]} vs ${expect}, process ${statF[2]}`);
  await ctx.close();
  worker.terminate();
} catch (e) {
  R.errors.push(String(e && e.stack || e));
}
R.ok = R.errors.length === 0;
window.__r = R;
