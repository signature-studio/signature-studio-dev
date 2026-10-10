// probe.js — main thread (module)。結果は window.__probe に集約し、document.title を 'probe-done' にする
const q = new URLSearchParams(location.search);
const data = q.get('data') || '/d/';
const bigName = q.get('big') || 'part-24m.bin';
const tag = q.get('tag') || location.pathname;
const res = { tag, url: location.href, dataBase: data, main: {} };
const m = res.main;
m.crossOriginIsolated = self.crossOriginIsolated;
m.isSecureContext = self.isSecureContext;
m.sab = typeof SharedArrayBuffer;
m.cores = navigator.hardwareConcurrency;
try { m.sabAlloc = new SharedArrayBuffer(1 << 20).byteLength; } catch (e) { m.sabAlloc = `ERR ${e.message}`; }

async function main() {
  const sab = typeof SharedArrayBuffer === 'function' && self.crossOriginIsolated ? new SharedArrayBuffer(64) : null;

  // no-cors <img> (cross-origin のみ意味あり): credentialless は通り、require-corp は CORP 無しで遮断される
  m.imgNoCors = await new Promise((resolve) => {
    if (!/^https?:/.test(data)) return resolve('skipped(same-origin)');
    const i = new Image();
    i.onload = () => resolve('loaded');
    i.onerror = () => resolve('blocked');
    i.src = data + 'pixel.png?t=' + Date.now();
    setTimeout(() => resolve('timeout'), 15000);
  });

  // AudioWorklet
  // headless ではオーディオデバイスが無く realtime AudioContext が起動しないことがあるため、失敗時は OfflineAudioContext で再試行する
  const workletTry = async (ctx, kind) => {
    await ctx.audioWorklet.addModule('./probe-worklet.js');
    const node = new AudioWorkletNode(ctx, 'probe-proc', { processorOptions: { sab } });
    node.connect(ctx.destination);
    const msg = new Promise((resolve, reject) => {
      node.port.onmessage = (e) => resolve(e.data);
      setTimeout(() => reject(new Error(`worklet message timeout (state=${ctx.state})`)), 8000);
    });
    if (kind === 'offline') ctx.startRendering();
    else ctx.resume?.().catch(() => {});
    const r = await msg;
    r.kind = kind;
    r.sabSeenByMain = sab ? Atomics.load(new Int32Array(sab), 2) : null;
    return r;
  };
  try {
    m.worklet = await workletTry(new AudioContext(), 'realtime');
  } catch (e1) {
    try {
      m.worklet = await workletTry(new OfflineAudioContext(1, 48000, 48000), 'offline');
      m.worklet.realtimeError = `${e1?.name}: ${e1?.message}`;
    } catch (e2) {
      m.worklet = { error: `realtime: ${e1?.message}; offline: ${e2?.name}: ${e2?.message}` };
    }
  }

  // manifest (E 方式 manifest 相当; 同一 data base から)
  let mf;
  try {
    mf = await (await fetch(data + 'probe-manifest.json', { cache: 'no-store' })).json();
  } catch (e) {
    res.fatal = `manifest fetch failed: ${e?.name}: ${e?.message}`;
    return;
  }

  // Worker
  let w;
  try {
    w = new Worker('./probe-worker.js', { type: 'module' });
  } catch (e) {
    res.fatal = `Worker ctor: ${e?.message}`;
    return;
  }
  const reply = await new Promise((resolve) => {
    w.onmessage = (e) => resolve(e.data);
    w.onerror = (e) => resolve({ ok: false, error: `worker onerror: ${e.message}` });
    w.postMessage({ data, bigName, mf, sab: sab ?? new ArrayBuffer(64), tag });
    setTimeout(() => resolve({ ok: false, error: 'worker timeout 300s' }), 300000);
  });
  res.worker = reply.ok ? reply.out : { error: reply.error };
  if (sab) res.main.sabSeenFromWorker = { v0: Atomics.load(new Int32Array(sab), 0), inc: Atomics.load(new Int32Array(sab), 1) };
}

main().catch((e) => { res.fatal = String(e?.stack ?? e); }).finally(() => {
  window.__probe = res;
  document.title = 'probe-done';
});
