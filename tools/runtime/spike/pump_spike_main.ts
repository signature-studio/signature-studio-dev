import { PumpRing } from "../../../src/runtime/worker_pump";
declare global { interface Window { __result?: unknown } }
const base = "/wasm/"; // runner が RUNTIME_WASM_DIR=work/spike で配信
const N = Number(new URLSearchParams(location.search).get("n") ?? 3000);
const BURST = Number(new URLSearchParams(location.search).get("burst") ?? 50000);

async function runCase(variant: "atomics" | "asyncify" | "jspi" | "native", depth: number, phases: string[]) {
  const wasmUrl = base + (variant === "native" ? "native" : variant === "asyncify" ? "asyncify" : "plain") + ".wasm";
  const consumer = new Worker(new URL("./pump_spike_worker.ts", import.meta.url), { type: "module" });
  const producer = new Worker(new URL("./pump_spike_producer.ts", import.meta.url), { type: "module" });
  const ackSab = new SharedArrayBuffer(64);
  const ch = new MessageChannel();
  let ringSab: SharedArrayBuffer | undefined, memory: WebAssembly.Memory | undefined;
  if (variant === "atomics") ringSab = PumpRing.create(1024).sab;
  if (variant === "native") memory = new WebAssembly.Memory({ initial: 32, maximum: 32, shared: true });
  const ready = new Promise<{ ringAddr?: number; ackAddr?: number }>((res, rej) => {
    consumer.onmessage = (e) => { if (e.data.t === "ready") res(e.data); else if (e.data.t === "error") rej(new Error(e.data.err)); };
    consumer.onerror = (e) => rej(new Error(String(e.message)));
  });
  const done = new Promise<Record<string, unknown>>((res) => { const prev = consumer.onmessage; consumer.addEventListener("message", (e) => { if (e.data.t === "done") res(e.data); }); void prev; });
  consumer.postMessage({ variant, wasmUrl, depth, ringSab, memory, ackSab, port: ch.port2 }, [ch.port2]);
  const r = await ready;
  const result = new Promise<Record<string, unknown>>((res, rej) => { producer.onmessage = (e) => { if (e.data.t === "result") res(e.data.out); }; producer.onerror = (e) => rej(new Error(String(e.message))); });
  const isNative = variant === "native";
  producer.postMessage({
    variant, depth, n: N, burst: BURST, phases,
    ackSab: isNative ? (memory!.buffer as SharedArrayBuffer) : ackSab, ackIndex: isNative ? r.ackAddr! / 4 : 0,
    ring: variant === "atomics" ? { sab: ringSab!, byteOffset: 0 } : isNative ? { sab: memory!.buffer as SharedArrayBuffer, byteOffset: r.ringAddr! } : undefined,
    port: variant === "asyncify" || variant === "jspi" ? ch.port1 : undefined,
  }, variant === "asyncify" || variant === "jspi" ? [ch.port1] : []);
  const out = await result;
  if (phases.includes("quit")) out.consumer = await done;
  consumer.terminate(); producer.terminate();
  return out;
}

const res: Record<string, unknown>[] = [];
try {
  const order = (new URLSearchParams(location.search).get("order") ?? "atomics,native,jspi,asyncify").split(",") as Array<"atomics" | "native" | "jspi" | "asyncify">;
  for (const v of order) res.push(await runCase(v, 0, ["pingpong", "nested", "burst", "quit"]));
  for (const v of order) res.push(await runCase(v, 64, ["pingpong"]));
  window.__result = { ok: true, res };
} catch (e) { window.__result = { ok: false, err: String((e as Error).stack || e) }; }
document.getElementById("o")!.textContent = JSON.stringify(window.__result, null, 1);
