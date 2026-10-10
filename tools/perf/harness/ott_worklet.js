// AudioWorkletGlobalScope: Chrome 本物の AudioWorklet スレッドで OTT wasm を回す。
// emscripten glue 無しで main から postMessage された WebAssembly.Module を instantiate する
// (worklet には fetch/performance が無い → 時間は Date.now() の 1000 ブロック区間平均)。
const f32bits = (v) => { const f = new Float32Array(1); f[0] = v; return BigInt(new Uint32Array(f.buffer)[0]); };
const OBJ = 0x30310000, IN_A = 0x30320000, OU_A = 0x30330000, BUF = 0x30340000, N = 128;
class OttProc extends AudioWorkletProcessor {
  constructor() {
    super(); this.port.onmessageerror = () => this.port.postMessage({ type: 'err', msg: 'messageerror (deserialize failed)' });
    this.inst = null; this.rt = false; this.calls = 0; this.errs = 0;
    this.port.onmessage = (e) => this.onMsg(e.data).catch((err) => this.port.postMessage({ type: 'err', msg: String(err && err.stack || err) }));
  }
  async onMsg(m) {
    if (m.type === 'ping') { this.port.postMessage({ type: 'pong' }); return; }
    if (m.type === 'loadbytes') { const t = Date.now(); const mod = await WebAssembly.compile(m.bytes); this.compileMs = Date.now() - t; return this.onMsg({ type: 'load', module: mod, viaBytes: true }); }
    if (m.type === 'load') {
      const mod = m.module, imp = {};
      for (const i of WebAssembly.Module.imports(mod)) { imp[i.module] ??= {}; imp[i.module][i.name] = i.kind === 'function' ? () => 0 : undefined; }
      const t0 = Date.now();
      this.inst = await WebAssembly.instantiate(mod, imp);
      const x = this.inst.exports; if (x.__wasm_call_ctors) x.__wasm_call_ctors();
      const buf = x.memory.buffer, U8 = new Uint8Array(buf), U32 = new Uint32Array(buf), F32 = new Float32Array(buf);
      x.m6_data_install();
      x.function_18011d400(BigInt(OBJ), 0n);
      for (let i = 0; i < 20; i++) x.function_180120af0(BigInt(OBJ), BigInt(i), i === 19 ? 0n : f32bits(0.5));
      x.function_180120800(BigInt(OBJ)); U8[OBJ + 0x248] = 0;
      for (let i = 0; i < N; i++) { F32[(BUF >> 2) + i] = Math.fround(Math.sin(i * 0.05) * 0.7 + Math.sin(i * 0.011) * 0.3); F32[(BUF >> 2) + N + i] = Math.fround(Math.cos(i * 0.13) * 0.5); }
      U32[IN_A >> 2] = BUF; U32[(IN_A >> 2) + 2] = BUF + N * 4; U32[OU_A >> 2] = BUF + N * 8; U32[(OU_A >> 2) + 2] = BUF + N * 12;
      this.call = () => x.function_18011ec20(BigInt(OBJ), BigInt(IN_A), BigInt(OU_A), BigInt(N));
      this.port.postMessage({ type: 'loaded', compileMsInWorklet: this.compileMs, instantiateMs: Date.now() - t0, sampleRate, memBytes: buf.byteLength });
    } else if (m.type === 'bench') {   // ワークレットスレッド上で連続実行して区間平均
      const chunks = []; for (let c = 0; c < m.chunks; c++) { const t = Date.now(); for (let i = 0; i < m.per; i++) this.call(); chunks.push((Date.now() - t) / m.per); }
      this.port.postMessage({ type: 'bench', chunkMeanMs: chunks });
    } else if (m.type === 'rt') {      // 実時間: process() 毎に 1 ブロック
      this.rt = true; this.calls = 0; this.t0 = Date.now(); this.dropped = 0;
    } else if (m.type === 'rtstop') {
      this.rt = false; this.port.postMessage({ type: 'rt', calls: this.calls, wallMs: Date.now() - this.t0, procCalls: this.procCalls });
    }
  }
  process(inputs, outputs) {
    this.procCalls = (this.procCalls || 0) + 1;
    if (this.rt && this.call) { this.call(); this.calls++; }
    return true;
  }
}
registerProcessor('ott-proc', OttProc);
