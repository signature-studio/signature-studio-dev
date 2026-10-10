/**
 * main thread 側ブート: manifest 取得 → Worker 起動 → 進捗/ログ中継。
 *
 * 設計 (DESIGN.md §3):
 *   - wasm の fetch + compileStreaming は Worker 内で行う (main thread を塞がない / ダウンロードとコンパイルが並行)。
 *   - 取得はブラウザ HTTP キャッシュ (hash 入りファイル名 + immutable) が既定。Chromium は streaming compile した
 *     モジュールのコードキャッシュを HTTP キャッシュ側に保持する。IndexedDB への WebAssembly.Module 保存は
 *     Chrome 154 で DataCloneError (実測) のため採用しない。Cache API は cacheMode="cacheapi" の明示 opt-in。
 *   - Worker 間で Module を共有する場合は postMessage(module) (構造化 clone は Module を共有できる: 実測 OK)。
 */

import {
  DEFAULT_BOOT_OPTIONS,
  type BootOptions,
  type FromWorker,
  type Manifest,
  type ManifestEntry,
  type Phase,
  type PumpSelfTestResult,
  type ToWorker,
} from "./worker_protocol";
import { PumpRing, WM } from "./worker_pump";

export type ResultMsg = Extract<FromWorker, { t: "result" }>;

export type BootUi = {
  onProgress?: (phase: Phase, loaded: number, total: number) => void;
  onLog?: (stream: "stdout" | "stderr" | "info", text: string) => void;
};

export async function loadManifest(url = "/wasm/manifest.json"): Promise<{ manifest: Manifest; baseUrl: string }> {
  const abs = new URL(url, location.href).href;
  const res = await fetch(abs, { cache: "no-cache" });
  if (!res.ok) throw new Error(`manifest 取得失敗: ${abs} HTTP ${res.status}`);
  return { manifest: (await res.json()) as Manifest, baseUrl: abs };
}

export function spawnRuntimeWorker(): Worker {
  return new Worker(new URL("./worker.ts", import.meta.url), { type: "module", name: "fl-runtime" });
}

/** 1 プログラムを新規 Worker で起動し、結果メッセージを待つ。 */
export function bootProgram(
  baseUrl: string,
  entry: ManifestEntry,
  opts: Partial<BootOptions> = {},
  ui: BootUi = {},
): Promise<{ result: ResultMsg; worker: Worker }> {
  const o: BootOptions = { ...DEFAULT_BOOT_OPTIONS, ...opts };
  const worker = spawnRuntimeWorker();
  return new Promise((resolve, reject) => {
    worker.onmessage = (ev: MessageEvent<FromWorker>) => {
      const m = ev.data;
      switch (m.t) {
        case "progress":
          ui.onProgress?.(m.phase, m.loaded, m.total);
          break;
        case "log":
          ui.onLog?.(m.stream, m.text);
          break;
        case "result":
          if (!o.keepAlive) worker.terminate();
          resolve({ result: m, worker });
          break;
        case "error":
          worker.terminate();
          reject(new Error(`[worker] ${m.message}\n${m.stack ?? ""}`));
          break;
      }
    };
    worker.onerror = (e) => {
      worker.terminate();
      reject(new Error(`[worker] uncaught: ${e.message}`));
    };
    const msg: ToWorker = { t: "boot", baseUrl, entry, opts: o, ring: null };
    worker.postMessage(msg);
  });
}

const yieldMacrotask = (() => {
  const ch = new MessageChannel();
  let res: (() => void) | null = null;
  ch.port1.onmessage = () => { const r = res; res = null; r?.(); };
  return () => new Promise<void>((r) => { res = r; ch.port2.postMessage(0); });
})();

/**
 * ブロッキングポンプの実機検証: Worker 内 MessagePump (Atomics.wait) に対し
 * main thread から ring 経由でメッセージを流し、遅延分布/タイマー/WM_QUIT を測る。
 */
export async function runPumpSelfTest(n = 2000, timerMs = 10): Promise<PumpSelfTestResult> {
  if (!crossOriginIsolated) throw new Error("pump self-test には crossOriginIsolated が必要");
  const worker = spawnRuntimeWorker();
  const ring = PumpRing.create(1024);
  let ready!: () => void;
  const readyP = new Promise<void>((r) => (ready = r));
  const done = new Promise<PumpSelfTestResult>((resolve, reject) => {
    worker.onmessage = (ev: MessageEvent<FromWorker>) => {
      if (ev.data.t === "pump-result") resolve(ev.data.result);
      else if (ev.data.t === "pong") ready();
      else if (ev.data.t === "error") reject(new Error(ev.data.message));
    };
    worker.onerror = (e) => reject(new Error(e.message));
  });
  worker.postMessage({ t: "pump-selftest", ring: ring.sab, timerId: 7, timerMs } satisfies ToWorker);
  await readyP; // Worker 起動 + consumer 準備完了を待ってから流す (起動遅延を遅延統計に混ぜない)
  const t0 = performance.now();
  for (let i = 0; i < n; i++) {
    let ok = ring.push({ message: WM.MOUSEMOVE, ptx: i, pty: i, tPost: performance.timeOrigin + performance.now() });
    while (!ok) { await yieldMacrotask(); ok = ring.push({ message: WM.MOUSEMOVE, ptx: i, pty: i, tPost: performance.timeOrigin + performance.now() }); }
    await yieldMacrotask();
  }
  // タイマーが ≥3 回発火する時間を確保 (固定 sleep ではなく経過時間条件で待つ)
  while (performance.now() - t0 < timerMs * 4) await yieldMacrotask();
  ring.push({ message: WM.APP_RUNTIME_STOP });
  try {
    return await done;
  } finally {
    worker.terminate();
  }
}
