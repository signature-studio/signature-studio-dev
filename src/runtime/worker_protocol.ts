/**
 * main ⇄ wasm 実行 Worker 間のメッセージ型 (DOM 非依存。main / worker / node テストから共有)。
 */

export type MemoryInfo = {
  /** manifest 生成時 (stage_wasm.mjs) に wasm バイナリから読んだ値 */
  imported: boolean;
  exported: boolean;
  shared: boolean;
  memory64: boolean;
  initialPages: number;
  maximumPages: number | null;
};

export type ManifestEntry = {
  id: string;
  label: string;
  /** manifest.json からの相対 URL (ファイル名に sha256 先頭 12 桁を含む = immutable キャッシュ可) */
  file: string;
  bytes: number;
  sha256: string;
  /** worker_drivers のキー */
  program: string;
  source: string;
  memory: MemoryInfo;
  importCount: number;
  exportCount: number;
};

export type Manifest = { version: 1; generated: string; entries: ManifestEntry[] };

export type BootOptions = {
  /** wasm 取得方式。http = ブラウザ HTTP キャッシュ任せ / cacheapi = Cache Storage に自前保存 / none = 毎回 network */
  cacheMode: "http" | "cacheapi" | "none";
  /** compileStreaming (fetch と並行コンパイル) か、全バイト取得後 compile か */
  compile: "streaming" | "bytes";
  /** 実行後も Worker を残す (ポンプ検証用) */
  keepAlive: boolean;
};

export const DEFAULT_BOOT_OPTIONS: BootOptions = { cacheMode: "http", compile: "streaming", keepAlive: false };

export type ToWorker =
  | { t: "boot"; baseUrl: string; entry: ManifestEntry; opts: BootOptions; ring: SharedArrayBuffer | null }
  | { t: "ping"; n: number }
  /** ポンプ自己検証: ring を consumer として GetMessage ループし、APP_RUNTIME_STOP / WM_QUIT で結果を返す */
  | { t: "pump-selftest"; ring: SharedArrayBuffer; timerId: number; timerMs: number };

export type PumpSelfTestResult = {
  received: number;
  byMessage: Record<string, number>;
  timers: number;
  /** producer の tPost から取り出し時刻までの遅延 (ms) */
  latency: { n: number; p50: number; p90: number; p99: number; max: number };
  blockedWaits: number;
  canBlock: boolean;
  dropped: number;
};

export type Phase = "fetch" | "compile" | "instantiate" | "run";

export type Check = { name: string; ok: boolean; detail?: string };

export type ProgramResult = {
  ok: boolean;
  checks: Check[];
  data: Record<string, unknown>;
};

export type BootTimings = {
  fetchCompileMs: number;
  instantiateMs: number;
  initMs: number;
  runMs: number;
  totalMs: number;
};

export type ResourceInfo = {
  transferSize: number | null;
  decodedBodySize: number | null;
  deliveryType: string | null;
  fromCacheApi: boolean;
};

export type FromWorker =
  | { t: "progress"; phase: Phase; loaded: number; total: number; ms: number }
  | { t: "log"; stream: "stdout" | "stderr" | "info"; text: string }
  | {
      t: "result";
      id: string;
      result: ProgramResult;
      timings: BootTimings;
      resource: ResourceInfo;
      memory: { model: string; shared: boolean; bytes: number };
    }
  | { t: "error"; message: string; stack?: string }
  | { t: "pong"; n: number; tWorker: number }
  | { t: "pump-result"; result: PumpSelfTestResult };
