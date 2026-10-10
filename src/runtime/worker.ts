/**
 * wasm 実行 Worker のエントリ (Vite: new Worker(new URL("./worker.ts", import.meta.url), { type: "module" }))。
 *
 * 役割: fetch → compileStreaming → instantiate → driver 実行。main thread は UI/入力/描画に専念させ、
 * ここ (wasm 実行スレッド) は将来 Win32 UI スレッド兼 GetMessage ブロッキングポンプになる。
 * pump-selftest は MessagePump (Atomics.wait) の実機検証入口。
 */

/// <reference lib="webworker" />

import { fetchCompile, describeModule } from "./loader_boot";
import { describeMemory } from "./mem";
import { DRIVERS } from "./worker_drivers";
import { MessagePump, PumpRing, WM, canBlock, newPumpMsg } from "./worker_pump";
import type { BootTimings, FromWorker, PumpSelfTestResult, ToWorker } from "./worker_protocol";

const post = (m: FromWorker) => (self as unknown as Worker).postMessage(m);
const log = (stream: "stdout" | "stderr" | "info", text: string) => post({ t: "log", stream, text });

let lastProgress = 0;
const progress = (phase: "fetch" | "compile" | "instantiate" | "run", loaded: number, total: number, force = false) => {
  const now = performance.now();
  if (!force && now - lastProgress < 50 && loaded < total) return;
  lastProgress = now;
  post({ t: "progress", phase, loaded, total, ms: now });
};

async function boot(msg: Extract<ToWorker, { t: "boot" }>): Promise<void> {
  const t0 = performance.now();
  const url = new URL(msg.entry.file, msg.baseUrl).href;
  log("info", `[worker] boot ${msg.entry.id} (${(msg.entry.bytes / 1048576).toFixed(2)} MiB) cache=${msg.opts.cacheMode} compile=${msg.opts.compile} cOI=${self.crossOriginIsolated}`);
  const { module, resource } = await fetchCompile(url, {
    cacheMode: msg.opts.cacheMode,
    compile: msg.opts.compile,
    onProgress: (l, t) => progress("fetch", l, t || msg.entry.bytes),
  });
  const tCompiled = performance.now();
  progress("compile", 1, 1, true);
  const d = describeModule(module);
  log("info", `[worker] compiled in ${(tCompiled - t0).toFixed(0)}ms: ${d.imports} imports / ${d.exports} exports`);

  const driver = DRIVERS[msg.entry.program];
  if (!driver) throw new Error(`driver '${msg.entry.program}' 未登録`);
  progress("run", 0, 1, true);
  const tRun = performance.now();
  const result = await driver({ module, entry: msg.entry, log });
  const tEnd = performance.now();
  progress("run", 1, 1, true);

  const timings: BootTimings = {
    fetchCompileMs: +(tCompiled - t0).toFixed(1),
    instantiateMs: +Number(result.data["instantiateMs"] ?? 0).toFixed(1),
    initMs: +Number(result.data["initMs"] ?? 0).toFixed(1),
    runMs: +(tEnd - tRun).toFixed(1),
    totalMs: +(tEnd - t0).toFixed(1),
  };
  const mem = result.data["memory"] as ReturnType<typeof describeMemory> | undefined;
  post({
    t: "result",
    id: msg.entry.id,
    result,
    timings,
    resource,
    memory: { model: mem?.model ?? "unknown", shared: mem?.shared ?? false, bytes: mem?.bytes ?? 0 },
  });
}

function pumpSelfTest(msg: Extract<ToWorker, { t: "pump-selftest" }>): void {
  const ring = new PumpRing(msg.ring);
  const pump = new MessagePump(ring);
  pump.setTimer(1, msg.timerId, msg.timerMs);
  const out = newPumpMsg();
  post({ t: "pong", n: -1, tWorker: performance.now() }); // consumer 準備完了 (以降このスレッドは getMessage でブロックする)
  const lat: number[] = [];
  const byMessage: Record<string, number> = {};
  let received = 0, timers = 0;
  const origin = performance.timeOrigin;
  while (pump.getMessage(out)) {
    received++;
    byMessage[out.message] = (byMessage[out.message] ?? 0) + 1;
    if (out.message === WM.TIMER) timers++;
    if (out.tPost) lat.push(origin + performance.now() - out.tPost);
    if (out.message === WM.APP_RUNTIME_STOP) pump.postQuitMessage(0);
  }
  lat.sort((a, b) => a - b);
  const q = (p: number) => (lat.length ? lat[Math.min(lat.length - 1, Math.floor(lat.length * p))]! : 0);
  const result: PumpSelfTestResult = {
    received,
    byMessage,
    timers,
    latency: { n: lat.length, p50: +q(0.5).toFixed(4), p90: +q(0.9).toFixed(4), p99: +q(0.99).toFixed(4), max: +(lat[lat.length - 1] ?? 0).toFixed(4) },
    blockedWaits: pump.stats.waits,
    canBlock: canBlock(),
    dropped: ring.dropped(),
  };
  post({ t: "pump-result", result });
}

self.onmessage = (ev: MessageEvent<ToWorker>) => {
  const msg = ev.data;
  if (msg.t === "boot") {
    boot(msg).catch((e: unknown) => post({ t: "error", message: String((e as Error)?.message ?? e), stack: (e as Error)?.stack }));
  } else if (msg.t === "ping") {
    post({ t: "pong", n: msg.n, tWorker: performance.now() });
  } else if (msg.t === "pump-selftest") {
    try {
      pumpSelfTest(msg);
    } catch (e) {
      post({ t: "error", message: String((e as Error)?.message ?? e), stack: (e as Error)?.stack });
    }
  }
};
