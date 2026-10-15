// P19: AudioWorkletGlobalScope で実 OTT (ottl.wasm) を 1 instance (= 1 Memory) だけ instantiate し、
// その中に M 個の OTT 処理オブジェクトを畳み込んで駆動する (shared_worker.mjs の AudioWorklet 版)。
// 駆動: render quantum (128 frame) ごとに全 obj を 1 block ずつ process する。
// 時刻は Date.now() (AudioWorkletGlobalScope に performance は無い。分解能 1 ms)。
// 手順と判定は shared_worker.mjs と同一: 各 obj の署名が 6b1696f0 (単独 instance の既知値) に一致すること。
const OBJ0 = 0x31000000, STRIDE = 0x40000;
const IN0 = 0x34000000, OU0 = 0x34000080, BUF0 = 0x34100000;
const N = 128;
const SIG_BLOCKS = 1000, WARM_BLOCKS = 300;
const slot = (i) => ({ obj: OBJ0 + i * STRIDE, inA: IN0 + i * 0x100, ouA: OU0 + i * 0x100, buf: BUF0 + i * 0x2000 });
const f32b = (v) => { const f = new Float32Array(1); f[0] = v; return BigInt(new Uint32Array(f.buffer)[0]); };
const p50 = (a) => { const s = [...a].sort((x, y) => x - y); return s[s.length >> 1]; };

class P19Shared extends AudioWorkletProcessor {
  constructor({ processorOptions: o }) {
    super();
    this.m = o.m; this.blk = o.blk; this.reps = o.reps; this.phase = 'sig'; this.k = 0; this.rep = 0;
    this.per = []; this.done = false;
    try {
      const imports = {
        env: { _abort_js() { throw new Error('abort'); }, emscripten_resize_heap() { return 0; } },
        wasi_snapshot_preview1: { fd_close() { return 0; }, fd_write() { return 0; }, fd_seek() { return 0; } },
      };
      const x = new WebAssembly.Instance(new WebAssembly.Module(o.wasm), imports).exports;
      x.__wasm_call_ctors();
      x.ott_data_install();
      this.x = x;
      this.U32 = new Uint32Array(x.memory.buffer); this.F32 = new Float32Array(x.memory.buffer);
      const run = (va, a, xs = []) => BigInt.asUintN(64, x.ott_run(0x30000000 + (va - 0x180000000), BigInt(a[0] ?? 0), BigInt(a[1] ?? 0), BigInt(a[2] ?? 0), BigInt(a[3] ?? 0), BigInt(xs[0] ?? 0), BigInt(xs[1] ?? 0), BigInt(xs[2] ?? 0), BigInt(xs[3] ?? 0)));
      this.ctor = (obj) => run(0x18011d400, [obj, 0]);
      this.setParam = (obj, i, v) => run(0x180120af0, [obj, i], [0, 0, f32b(v)]);
      this.resume = (obj) => run(0x180120800, [obj]);
      this.ottProcess = (obj, inA, ouA, n) => run(0x18011ec20, [obj, inA, ouA, n]);
      const { U32, F32 } = this;
      for (let i = 0; i < this.m; i++) {
        const s = slot(i);
        this.ctor(s.obj); for (let p = 0; p < 19; p++) this.setParam(s.obj, p, 0.5); this.resume(s.obj);
        for (let k = 0; k < N * 2; k++) F32[s.buf / 4 + k] = Math.fround(Math.sin(k * 0.05) * 0.5);
        U32[s.inA / 4] = s.buf; U32[s.inA / 4 + 2] = s.buf + N * 4; U32[s.ouA / 4] = s.buf + N * 8; U32[s.ouA / 4 + 2] = s.buf + N * 12;
      }
      this.h = new Array(this.m).fill(0x811c9dc5 >>> 0);
      this.sigs = new Array(this.m).fill(null);
    } catch (e) {
      this.port.postMessage({ ok: false, error: 'init: ' + String(e && e.message || e).slice(0, 300) });
      this.done = true;
    }
  }

  step(k) {
    const { U32, m } = this;
    for (let i = 0; i < m; i++) {
      const s = slot(i);
      this.ottProcess(s.obj, s.inA, s.ouA, N);
      if (this.phase === 'sig' && (k <= 8 || k === SIG_BLOCKS)) {
        let h = this.h[i];
        for (let j = 0; j < 2 * N; j++) h = Math.imul(h ^ U32[s.buf / 4 + 2 * N + j], 16777619) >>> 0;
        this.h[i] = h;
        if (k === SIG_BLOCKS) this.sigs[i] = h.toString(16);
      }
    }
  }

  process() {
    if (this.done) return false;
    try {
      if (this.phase === 'sig') {
        this.k++;
        this.step(this.k);
        if (this.k === SIG_BLOCKS) { this.phase = 'warm'; this.k = 0; }
      } else if (this.phase === 'warm') {
        this.step(0);
        if (++this.k === WARM_BLOCKS) { this.phase = 'bench'; this.k = 0; this.t = Date.now(); }
      } else {
        this.step(0);
        if (++this.k === this.blk) {
          this.per.push((Date.now() - this.t) * 1000 / (this.blk * this.m));
          this.rep++; this.k = 0;
          if (this.rep === this.reps) {
            const uniq = [...new Set(this.sigs)];
            this.port.postMessage({ ok: true, r: {
              runtime_ua: 'AudioWorkletGlobalScope', m: this.m, instances: 1, blk: this.blk,
              us_per_block_p50: +p50(this.per).toFixed(2), us_per_block_min: +Math.min(...this.per).toFixed(2), us_per_block_max: +Math.max(...this.per).toFixed(2),
              rtf44_per_obj: +(p50(this.per) / (N / 44.1 * 1000)).toFixed(5),
              sig: uniq, sig_n: this.sigs.length, sig_ok: uniq.length === 1 && uniq[0] === '6b1696f0',
              memory_mib: +(this.x.memory.buffer.byteLength / 2 ** 20).toFixed(1),
            } });
            this.done = true;
            return false;
          }
          this.t = Date.now();
        }
      }
    } catch (e) {
      this.port.postMessage({ ok: false, error: String(e && e.message || e).slice(0, 300) });
      this.done = true;
      return false;
    }
    return true;
  }
}

registerProcessor('p19-shared', P19Shared);
