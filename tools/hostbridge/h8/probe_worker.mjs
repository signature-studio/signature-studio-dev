// probe_worker.mjs — H8 probe: Worker 内で同期 WebAssembly.Instance を作り、
// SAB RPC (Atomics.wait) で受けた要求を wasm で処理し、AudioWorklet 向け ring に音声を流す。
const CAP = 4096;
let inst = null, ctrl = null, ring = null;
const log = [];
self.onmessage = (ev) => {
  const m = ev.data;
  if (m.type === 'init') {
    const t0 = performance.now();
    inst = new WebAssembly.Instance(new WebAssembly.Module(m.wasm), {});
    const ms = performance.now() - t0;
    ctrl = new Int32Array(m.rpc);
    ring = { data: new Float32Array(m.ring), ctrl: new Int32Array(m.ringCtrl) };
    self.postMessage({ type: 'inited', sync_instance_ms: ms, add_2_3: inst.exports.add(2, 3), sab: typeof SharedArrayBuffer, coi: self.crossOriginIsolated });
  } else if (m.type === 'serve') {
    serveRpc();
  } else if (m.type === 'produce') {
    produce(m.n);
    self.postMessage({ type: 'produced', n: m.n });
  }
};

// RPC: ctrl[0]=req seq (main が増やす), ctrl[1]=ack seq (worker が設定), ctrl[2..3]=a,b, ctrl[4]=result, ctrl[7]=stop
function serveRpc() {
  let last = 0;
  for (;;) {
    while (Atomics.load(ctrl, 0) === last) Atomics.wait(ctrl, 0, last, 1000);
    const seq = Atomics.load(ctrl, 0);
    if (Atomics.load(ctrl, 7) === 1) break;
    Atomics.store(ctrl, 4, inst.exports.add(Atomics.load(ctrl, 2), Atomics.load(ctrl, 3)));
    Atomics.store(ctrl, 1, seq);
    Atomics.notify(ctrl, 1);
    last = seq;
  }
  self.postMessage({ type: 'rpc_done' });
}

// ring: data[CAP] Float32, ctrl[0]=write(単調増加), ctrl[1]=read(worklet が進める)
function produce(n) {
  const { data, ctrl: rc } = ring;
  let w = Atomics.load(rc, 0);
  for (let s = 0; s < n; s += 256) {
    const chunk = Math.min(256, n - s);
    for (;;) {
      const r = Atomics.load(rc, 1);
      if (w + chunk - r <= CAP) break;
      Atomics.wait(rc, 1, r, 10);
    }
    for (let i = 0; i < chunk; i++) data[(w + i) % CAP] = s + i;
    w += chunk;
    Atomics.store(rc, 0, w);
  }
}
