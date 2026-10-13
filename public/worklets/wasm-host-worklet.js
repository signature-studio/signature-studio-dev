/**
 * wasm ホスト AudioWorkletProcessor ("wasm-host")。PERF-P3 (#162)。
 *
 * WebAssembly.Module は AudioWorklet へ postMessage できない (messageerror, tools/perf/REPORT.md §3) ため、
 * main から wasm bytes (ArrayBuffer) を transfer で受け取り、worklet 内で compile → instantiate → pre-warm する。
 * main 側プロトコルは src/runtime/worklet_loader.ts。
 *
 * wasm ABI (ws_v1):
 *   必須  memory, ws_buffers() -> i32 (in[128] f32 の先頭。out[128] f32 が直後に続く), ws_process(frames: i32)
 *   任意  ws_init(), ws_reset()  (ws_reset は pre-warm 後に 1 回呼ぶ: 無音ブロックで進んだ内部状態の巻き戻し)
 *
 * worklet スコープには performance が無いので時間は Date.now() (1 ms 分解能)。
 */
const Q = 128;
const NEED_FIRST = 16; // 最初の何ブロックの処理時間を報告するか
const CAPTURE = 4; // 最初の何ブロックの入出力を報告するか (検証用)

class WasmHostProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.x = null;
    this.inView = null;
    this.outView = null;
    this.blockIdx = 0;
    this.times = [];
    this.captures = [];
    this.reported = false;
    this.port.onmessageerror = () => this.port.postMessage({ type: "messageerror" });
    this.port.onmessage = (e) => {
      const m = e.data;
      if (m.type === "load") {
        this.load(m).catch((err) => this.port.postMessage({ type: "error", id: m.id, msg: String((err && err.message) || err) }));
      }
    };
  }

  async load(m) {
    const o = m.opts || {};
    const t0 = Date.now();
    const mod = await WebAssembly.compile(m.bytes);
    const compileMs = Date.now() - t0;

    const imports = {};
    const missing = [];
    for (const i of WebAssembly.Module.imports(mod)) {
      if (!o.stubImports) { missing.push(`${i.module}.${i.name}`); continue; }
      imports[i.module] ??= {};
      imports[i.module][i.name] = i.kind === "function" ? () => 0 : undefined;
    }
    if (missing.length) throw new Error(`unresolved imports (${missing.length}): ${missing.slice(0, 8).join(", ")}`);

    const t1 = Date.now();
    const inst = await WebAssembly.instantiate(mod, imports);
    const instantiateMs = Date.now() - t1;
    const x = inst.exports;
    for (const need of ["memory", "ws_buffers", "ws_process"]) {
      if (!(need in x)) throw new Error(`wasm export missing: ${need} (ABI ws_v1)`);
    }

    const t2 = Date.now();
    if (x.__wasm_call_ctors) x.__wasm_call_ctors();
    if (x.ws_init) x.ws_init();
    const initMs = Date.now() - t2;

    const bufPtr = x.ws_buffers() >>> 0;
    const mem = x.memory.buffer;
    const inView = new Float32Array(mem, bufPtr, Q);
    const outView = new Float32Array(mem, bufPtr + Q * 4, Q);

    // pre-warm: 無音ブロックを回して lazy compile / tier-up / 初回 call コストを process() の外で払う
    const prewarmBlocks = o.prewarmBlocks | 0;
    const prewarmMs = [];
    for (let b = 0; b < prewarmBlocks; b++) {
      inView.fill(0);
      const t = Date.now();
      x.ws_process(Q);
      prewarmMs.push(Date.now() - t);
    }
    if (prewarmBlocks > 0 && x.ws_reset) x.ws_reset();

    this.x = x;
    this.inView = inView;
    this.outView = outView;
    this.blockIdx = 0;
    this.times = [];
    this.captures = [];
    this.reported = false;
    this.port.postMessage({
      type: "loaded", id: m.id, sampleRate, byteLength: m.bytes.byteLength,
      compileMs, instantiateMs, initMs, prewarmMs, memBytes: mem.byteLength,
      hasReset: !!x.ws_reset, workletTime: currentTime,
    });
  }

  process(inputs, outputs) {
    const x = this.x;
    const out = outputs[0];
    if (!x) { for (const ch of out) ch.fill(0); return true; }
    const inp = inputs[0] && inputs[0][0];
    const t = Date.now();
    if (inp) this.inView.set(inp.length === Q ? inp : inp.subarray(0, Q)); else this.inView.fill(0);
    x.ws_process(Q);
    // memory.grow で buffer が替わった場合に備え view を取り直す
    if (this.outView.buffer !== x.memory.buffer) {
      const p = x.ws_buffers() >>> 0;
      this.inView = new Float32Array(x.memory.buffer, p, Q);
      this.outView = new Float32Array(x.memory.buffer, p + Q * 4, Q);
    }
    for (const ch of out) ch.set(this.outView);
    const dt = Date.now() - t;
    if (!this.reported) {
      if (this.blockIdx < CAPTURE) this.captures.push({ in: this.inView.slice(), out: this.outView.slice() });
      this.times.push(dt);
      if (++this.blockIdx >= NEED_FIRST) {
        this.reported = true;
        this.port.postMessage({ type: "firstblocks", blockMs: this.times, captures: this.captures, workletTime: currentTime });
      }
    }
    return true;
  }
}

registerProcessor("wasm-host", WasmHostProcessor);
