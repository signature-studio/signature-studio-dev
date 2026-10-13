// ring_worklet.js — AudioWorklet 側。SAB ring を消費するだけ (Atomics.load/store のみ・Atomics.wait は使わない; RT-4 #123)。
// 処理: 128 frame ごとに ring から 2H float (L,R interleave) を読み、総和を取り、消費量 C_RD を store する。
class RingConsumer extends AudioWorkletProcessor {
  constructor(opts) {
    super();
    const p = opts.processorOptions;
    this.ring = new Float32Array(p.ring); this.bits = new Uint32Array(p.ring); this.ctl = new Int32Array(p.ctl);
    this.CAP = p.cap; this.H = p.H; this.total = p.total; this.rd = 0; this.sum = 0; this.done = false;
    this.port.onmessage = (ev) => { if (ev.data === 'report') this.port.postMessage({ rd: this.rd, sum: this.sum, floats: this.rd, done: this.done }); };
  }
  process() {
    if (this.done) return true;
    const need = 2 * this.H;
    if (Atomics.load(this.ctl, 0) - this.rd < need) return true;
    for (let i = 0; i < need; i++) this.sum = (this.sum + this.bits[(this.rd + i) % this.CAP]) >>> 0;
    this.rd += need; Atomics.store(this.ctl, 1, this.rd);
    if (this.rd >= this.total) { this.done = true; this.port.postMessage({ rd: this.rd, sum: this.sum, done: true }); }
    return true;
  }
}
registerProcessor('ring-consumer', RingConsumer);
