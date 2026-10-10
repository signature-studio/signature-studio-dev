registerProcessor("probe", class extends AudioWorkletProcessor {
  constructor() {
    super();
    let sab = false;
    try { new SharedArrayBuffer(8); sab = true; } catch {}
    this.port.postMessage({ sab, typeofSAB: typeof SharedArrayBuffer, isolatedGlobal: typeof crossOriginIsolated === "undefined" ? "undefined" : crossOriginIsolated });
  }
  process() { return false; }
});
