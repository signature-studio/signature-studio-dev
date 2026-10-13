// AudioWorkletGlobalScope: 実 AudioWorklet スレッドで bit-exact OTT (x64c wasm) を回す。
// worklet には performance/fetch が無い → 時間は SAB カウンタ時計 (x64c_clock.js が Atomics.store を回し続ける) の差分、
// ticks→µs の換算は process() 駆動の全区間での (カウンタ総進行 / Date.now 総経過) で較正する。
import { setupOtt } from './x64c_core.mjs';
class X64cOtt extends AudioWorkletProcessor {
  constructor(o) {
    super();
    this.clk = new Uint32Array(o.processorOptions.sab);
    this.o = null; this.rt = false;
    this.port.onmessage = (e) => this.onMsg(e.data).catch((err) => this.port.postMessage({ type: 'err', msg: String(err && err.stack || err) }));
  }
  async onMsg(m) {
    if (m.type === 'load') {
      const t0 = Date.now();
      const mod = await WebAssembly.compile(m.bytes);
      const t1 = Date.now();
      this.o = await setupOtt(mod, m.names);
      this.port.postMessage({ type: 'loaded', compileMsInWorklet: t1 - t0, setupMs: Date.now() - t1, sampleRate, memBytes: this.o.memBytes, signature: this.o.signature(), nonzeroOut: this.o.nonzero() });
    } else if (m.type === 'bench') {
      const call = this.o.call, clk = this.clk, chunkMs = [], chunkTicks = [];
      for (let c = 0; c < m.chunks; c++) {
        const d0 = Date.now(), c0 = Atomics.load(clk, 0);
        for (let i = 0; i < m.per; i++) call();
        chunkTicks.push((Atomics.load(clk, 0) - c0) >>> 0); chunkMs.push(Date.now() - d0);
      }
      this.port.postMessage({ type: 'bench', per: m.per, chunkMs, chunkTicks });
    } else if (m.type === 'rt') {
      this.want = m.blocks; this.dur = new Uint32Array(m.blocks); this.gap = new Uint32Array(m.blocks); this.n = 0;
      this.lastEntry = -1; this.totalTicks = 0; this.dFirst = 0; this.procCalls0 = this.procCalls || 0; this.rt = true;
    }
  }
  process(inputs, outputs) {
    this.procCalls = (this.procCalls || 0) + 1;
    if (this.rt) {
      const clk = this.clk, c0 = Atomics.load(clk, 0);
      if (this.lastEntry >= 0) { this.gap[this.n] = (c0 - this.lastEntry) >>> 0; this.totalTicks += this.gap[this.n]; }
      if (this.lastEntry < 0) this.dFirst = Date.now();
      this.lastEntry = c0;
      this.o.call();
      this.dur[this.n] = (Atomics.load(clk, 0) - c0) >>> 0;
      if (++this.n >= this.want) {
        this.rt = false;
        this.port.postMessage({ type: 'rt', n: this.n, wallMs: Date.now() - this.dFirst, totalTicks: this.totalTicks, procCalls: this.procCalls - this.procCalls0, sampleRate, dur: this.dur, gap: this.gap });
      }
    }
    return true;
  }
}
registerProcessor('x64c-ott', X64cOtt);
