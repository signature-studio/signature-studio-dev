// AudioWorkletGlobalScope: bytes を受けて worklet 内で compile → process() 内で ws_process。
// 時間は Date.now (ms) のみ (worklet に performance は無い)。判定は「呼出回数 / 期待回数」と「最大呼出間隔」。
const BUF = 4096, OUT = BUF + 512;
const inputAt = (b, i) => { const x = (Math.imul(b * 128 + i, 1103515245) + 12345) & 0xffff; return Math.fround(x / 32768 - 1); };
class P7 extends AudioWorkletProcessor {
  constructor() {
    super(); this.inst = null; this.n = 0; this.h = 2166136261; this.raw = []; this.run = false; this.calls = 0; this.gaps = [];
    this.port.onmessage = (e) => this.onMsg(e.data).catch((er) => this.port.postMessage({ type: 'result', error: String(er && er.stack || er).slice(0, 300) }));
    this.port.onmessageerror = () => this.port.postMessage({ type: 'msgerr' });
  }
  async onMsg(m) {
    if (m.type === 'mod') { this.gotMod = true; this.port.postMessage({ type: 'modRecv', isModule: m.mod instanceof WebAssembly.Module }); return; }
    if (m.type !== 'load') return;
    const t0 = Date.now(); const mod = await WebAssembly.compile(m.bytes); const t1 = Date.now();
    this.inst = await WebAssembly.instantiate(mod, {}); this.sr = m.sr; this.durMs = m.durMs; this.hashBlocks = m.hashBlocks;
    this.port.postMessage({ type: 'loaded', compileMs: t1 - t0, instantiateMs: Date.now() - t1 });
    this.start = Date.now(); this.last = 0; this.run = true;
  }
  process(_i, outputs) {
    if (!this.run || !this.inst) return true;
    const now = Date.now();
    if (this.last) this.gaps.push(now - this.last);
    this.last = now; this.calls++;
    const { memory, ws_process, ws_buffers } = this.inst.exports;
    const inp = new Float32Array(memory.buffer, ws_buffers(), 128);
    const b = this.n;
    for (let i = 0; i < 128; i++) inp[i] = inputAt(b, i);
    ws_process(128);
    const o = new Float32Array(memory.buffer, OUT, 128);
    if (b < this.hashBlocks) {
      const u = new Uint32Array(o.buffer, o.byteOffset, 128);
      for (let i = 0; i < 128; i++) this.h = Math.imul(this.h ^ u[i], 16777619) >>> 0;
      if (b < 8) this.raw.push(Array.from(o));
    }
    this.n++;
    outputs[0][0].set(o.map((v) => v * 0)); // 無音で出力 (聴覚への影響なし)
    if (now - this.start >= this.durMs) {
      this.run = false;
      const g = this.gaps, expected = Math.floor(this.durMs / 1000 * this.sr / 128);
      this.port.postMessage({ type: 'result', calls: this.calls, expectedCalls: expected, wallMs: now - this.start, maxGapMs: Math.max(...g), gapsOver10ms: g.filter((x) => x > 10).length, gapsOver20ms: g.filter((x) => x > 20).length,
        hash: this.h, hashBlocks: Math.min(this.hashBlocks, this.n), raw8: this.raw, sampleRate });
    }
    return true;
  }
}
registerProcessor('p7-proc', P7);
