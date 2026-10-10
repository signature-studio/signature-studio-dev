// consumer worker: variant ごとに get_message を実装し wasm の run() を駆動する。
import { PumpRing } from "../../../src/runtime/worker_pump";

type Cfg = {
  variant: "atomics" | "asyncify" | "jspi" | "native";
  wasmUrl: string;
  depth: number;
  ringSab?: SharedArrayBuffer; // atomics
  memory?: WebAssembly.Memory; // native
  ackSab?: SharedArrayBuffer; // 非 native
  port?: MessagePort; // asyncify / jspi
};
type WMsg = { msg: number; seq: number; tPost: number };

self.onmessage = async (ev: MessageEvent<Cfg>) => {
  const cfg = ev.data;
  try { await main(cfg); } catch (e) { postMessage({ t: "error", err: String((e as Error).stack || e) }); }
};

async function main(cfg: Cfg) {
  const bytes = await (await fetch(cfg.wasmUrl)).arrayBuffer();
  const module = await WebAssembly.compile(bytes);
  const ackI32 = cfg.ackSab ? new Int32Array(cfg.ackSab) : null;
  let memory: WebAssembly.Memory | null = null;
  const writeMsg = (ptr: number, m: WMsg) => {
    const dv = new DataView(memory!.buffer);
    dv.setUint32(ptr, m.msg, true); dv.setUint32(ptr + 4, m.seq, true); dv.setFloat64(ptr + 24, m.tPost, true);
  };
  const ack = (seq: number) => { Atomics.store(ackI32!, 0, seq); Atomics.notify(ackI32!, 0); };
  const entry = (ex: Record<string, unknown>) => (cfg.depth > 0 ? () => (ex.run_deep as (d: number) => number)(cfg.depth) : () => (ex.run as () => number)());

  // --- メッセージ供給 (asyncify / jspi: MessagePort 経由, イベントループ駆動) ---
  const queue: WMsg[] = [];
  let resolver: ((m: WMsg) => void) | null = null;
  if (cfg.port) cfg.port.onmessage = (e) => { const m = e.data as WMsg; if (resolver) { const r = resolver; resolver = null; r(m); } else queue.push(m); };
  const nextMessage = () => new Promise<WMsg>((r) => (resolver = r));

  if (cfg.variant === "native") {
    memory = cfg.memory!;
    const inst = await WebAssembly.instantiate(module, { env: { memory, get_message: () => 0, ack: () => {} } });
    const ex = inst.exports as Record<string, unknown>;
    (ex.__wasm_call_ctors as (() => void) | undefined)?.();
    const ringAddr = (ex.ring_addr as () => number)();
    const ackAddr = (ex.ack_addr as () => number)();
    new PumpRing(memory.buffer as SharedArrayBuffer, ringAddr, 1024, true); // ring 初期化 (seq[i]=i)
    postMessage({ t: "ready", ringAddr, ackAddr });
    const r = entry(ex)(); // wasm 内で memory.atomic.wait32 によりブロック
    postMessage({ t: "done", handled: (ex.stats as (i: number) => number)(0), maxDepth: (ex.stats as (i: number) => number)(1), checksum: (ex.stats as (i: number) => number)(2), r });
    return;
  }

  if (cfg.variant === "atomics") {
    const ring = new PumpRing(cfg.ringSab!, 0);
    const tmp = { hwnd: 0, message: 0, wLo: 0, wHi: 0, lLo: 0, lHi: 0, time: 0, ptx: 0, pty: 0, tPost: 0 };
    const get_message = (ptr: number) => {
      for (;;) {
        const w = ring.wakeValue();
        if (ring.tryPop(tmp)) { writeMsg(ptr, { msg: tmp.message, seq: tmp.ptx, tPost: tmp.tPost }); return 1; }
        ring.wait(w, Infinity);
      }
    };
    const inst = await WebAssembly.instantiate(module, { env: { get_message, ack } });
    const ex = inst.exports as Record<string, unknown>;
    memory = ex.memory as WebAssembly.Memory;
    postMessage({ t: "ready" });
    const r = entry(ex)();
    postMessage({ t: "done", handled: (ex.stats as (i: number) => number)(0), maxDepth: (ex.stats as (i: number) => number)(1), checksum: (ex.stats as (i: number) => number)(2), r });
    return;
  }

  if (cfg.variant === "jspi") {
    const S = (WebAssembly as unknown as { Suspending: new (f: unknown) => unknown }).Suspending;
    const P = (WebAssembly as unknown as { promising: (f: unknown) => () => Promise<number> }).promising;
    const get_message = new S((ptr: number): number | Promise<number> => {
      const m = queue.shift();
      if (m) { writeMsg(ptr, m); return 1; }
      return nextMessage().then((mm) => { writeMsg(ptr, mm); return 1; });
    });
    const inst = await WebAssembly.instantiate(module, { env: { get_message, ack } });
    const ex = inst.exports as Record<string, unknown>;
    memory = ex.memory as WebAssembly.Memory;
    postMessage({ t: "ready" });
    const run = cfg.depth > 0 ? P(ex.run_deep) : P(ex.run);
    const r = cfg.depth > 0 ? await (run as unknown as (d: number) => Promise<number>)(cfg.depth) : await run();
    postMessage({ t: "done", handled: (ex.stats as (i: number) => number)(0), maxDepth: (ex.stats as (i: number) => number)(1), checksum: (ex.stats as (i: number) => number)(2), r });
    return;
  }

  // asyncify (wasm-opt --asyncify 済み)
  let ex!: Record<string, unknown>;
  let pending: WMsg | null = null;
  const get_message = (ptr: number): number => {
    const f = ex as unknown as { asyncify_get_state(): number; asyncify_stop_rewind(): void; asyncify_start_unwind(p: number): void };
    if (f.asyncify_get_state() === 2) { f.asyncify_stop_rewind(); writeMsg(ptr, pending!); pending = null; return 1; }
    const m = queue.shift();
    if (m) { writeMsg(ptr, m); return 1; }
    f.asyncify_start_unwind((ex.asyncify_area as () => number)());
    return 0;
  };
  const inst = await WebAssembly.instantiate(module, { env: { get_message, ack } });
  ex = inst.exports as Record<string, unknown>;
  memory = ex.memory as WebAssembly.Memory;
  const f = ex as unknown as { asyncify_get_state(): number; asyncify_stop_unwind(): void; asyncify_start_rewind(p: number): void };
  const area = (ex.asyncify_area as () => number)(), size = (ex.asyncify_area_size as () => number)();
  new Int32Array(memory.buffer, area, 2).set([area + 8, area + size]);
  postMessage({ t: "ready" });
  const e = entry(ex);
  let r = e() as number;
  while (f.asyncify_get_state() === 1) {
    f.asyncify_stop_unwind();
    pending = await nextMessage();
    f.asyncify_start_rewind(area);
    r = e() as number;
  }
  postMessage({ t: "done", handled: (ex.stats as (i: number) => number)(0), maxDepth: (ex.stats as (i: number) => number)(1), checksum: (ex.stats as (i: number) => number)(2), r });
}
