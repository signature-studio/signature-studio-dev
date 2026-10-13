// probe_worklet.mjs — AudioWorklet 側。SAB ring から読み出すだけ (Atomics.wait は使わない)。
const CAP = 4096;
class RingReader extends AudioWorkletProcessor {
  constructor(opts) {
    super();
    const o = opts.processorOptions;
    this.data = new Float32Array(o.ring);
    this.ctrl = new Int32Array(o.ringCtrl);
    this.stat = new Float64Array(o.stat);
  }
  process(_inputs, outputs) {
    const out = outputs[0][0];
    const w = Atomics.load(this.ctrl, 0), r = Atomics.load(this.ctrl, 1);
    const n = Math.min(w - r, out.length);
    let sum = 0;
    for (let i = 0; i < n; i++) { const v = this.data[(r + i) % CAP]; out[i] = v; sum += v; }
    for (let i = n; i < out.length; i++) out[i] = 0;
    if (n > 0) {
      Atomics.store(this.ctrl, 1, r + n);
      Atomics.notify(this.ctrl, 1);
      this.stat[0] += sum;
      this.stat[1] += n;
    }
    this.stat[2] += 1;
    return true;
  }
}
registerProcessor('ring-reader', RingReader);
