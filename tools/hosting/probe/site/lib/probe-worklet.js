// probe-worklet.js — AudioWorkletGlobalScope: SAB が使えるか (FL の SAB ring buffer 相当) を確認する
class ProbeProc extends AudioWorkletProcessor {
  constructor(opts) {
    super();
    const a = new Int32Array(opts.processorOptions.sab);
    Atomics.store(a, 2, 0x77);
    this.port.postMessage({ crossOriginIsolated: globalThis.crossOriginIsolated, sab: typeof SharedArrayBuffer, wrote: Atomics.load(a, 2) });
  }
  process() { return true; }
}
registerProcessor('probe-proc', ProbeProc);
