/**
 * AudioWorklet 向け wasm ローダ (main 側)。PERF-P3 (#162)。
 *
 * WebAssembly.Module は AudioWorklet へ postMessage できない (messageerror) ため、bytes を transfer し
 * worklet 内 (public/worklets/wasm-host-worklet.js) で compile → instantiate → pre-warm する。
 * `keepModule` なら main でも同じ bytes を compile して Module を保持する (同一プロセスの NativeModule
 * 共有で worklet 側 compile を短縮する狙い。効果の実測は tools/perf/REPORT.md §10)。
 *
 * 消去可能な TS 構文のみ (node の stripTypeScriptTypes で e2e からそのまま実行する)。
 */

export type WorkletLoadOptions = {
  /** 無音で回す pre-warm ブロック数 (128f/ブロック)。0 で無効 */
  prewarmBlocks?: number;
  /** main でも compile して Module を保持する (handle.mainModule) */
  keepModule?: boolean;
  /** 未解決 import を () => 0 で埋める (計測・スモーク用。既定 false = 未解決なら reject) */
  stubImports?: boolean;
};

export type WorkletLoadStats = {
  sampleRate: number;
  byteLength: number;
  /** worklet 内の各段 (Date.now() 差、1 ms 分解能) */
  compileMs: number;
  instantiateMs: number;
  initMs: number;
  prewarmMs: number[];
  memBytes: number;
  hasReset: boolean;
  /** main 側: keepModule 時の main compile 所要 / transfer 送出から loaded 受信まで / load() 全体 (performance.now) */
  mainCompileMs: number | null;
  roundtripMs: number;
  totalMs: number;
};

export type FirstBlocks = {
  /** 最初の 16 ブロックの process() 内処理時間 (ms, 1 ms 分解能) */
  blockMs: number[];
  captures: { in: Float32Array; out: Float32Array }[];
};

export type WasmWorkletHost = {
  node: AudioWorkletNode;
  /** keepModule 指定の load 後に入る main 側 Module */
  mainModule: WebAssembly.Module | null;
  /** bytes を transfer して worklet 内で compile+instantiate+pre-warm。bytes は detach される */
  load(bytes: ArrayBuffer, opts?: WorkletLoadOptions): Promise<WorkletLoadStats>;
  /** load 後、ノードが pull されて最初の 16 ブロックを処理し終えたとき解決 */
  firstBlocks(): Promise<FirstBlocks>;
  /** Module を直接 postMessage し、worklet が messageerror を返すか (true = 不可の再確認) */
  probeModulePost(module: WebAssembly.Module, timeoutMs?: number): Promise<boolean>;
};

type Pending = { resolve: (v: any) => void; reject: (e: Error) => void };

export async function createWasmWorkletHost(
  ctx: BaseAudioContext,
  moduleUrl = "/worklets/wasm-host-worklet.js",
): Promise<WasmWorkletHost> {
  await ctx.audioWorklet.addModule(moduleUrl);
  const node = new AudioWorkletNode(ctx, "wasm-host", {
    numberOfInputs: 1,
    numberOfOutputs: 1,
    outputChannelCount: [2],
  });
  const port = node.port;
  const pending = new Map<number, Pending>();
  let nextId = 1;
  let first: Pending | null = null;
  let firstDone: FirstBlocks | null = null;
  let meResolve: ((v: boolean) => void) | null = null;
  let meSeen = false;

  port.onmessage = (e: MessageEvent) => {
    const m = e.data;
    if (m.type === "loaded" || m.type === "error") {
      const p = pending.get(m.id);
      if (!p) return;
      pending.delete(m.id);
      if (m.type === "error") p.reject(new Error(`[worklet_loader] ${m.msg}`));
      else p.resolve(m);
    } else if (m.type === "firstblocks") {
      firstDone = { blockMs: m.blockMs, captures: m.captures };
      first?.resolve(firstDone);
    } else if (m.type === "messageerror") {
      meSeen = true;
      meResolve?.(true);
    }
  };

  const host: WasmWorkletHost = {
    node,
    mainModule: null,
    async load(bytes, opts = {}) {
      const t0 = performance.now();
      let mainCompileMs: number | null = null;
      if (opts.keepModule) {
        const tc = performance.now();
        host.mainModule = await WebAssembly.compile(bytes.slice(0));
        mainCompileMs = performance.now() - tc;
      }
      const id = nextId++;
      const t1 = performance.now();
      const reply = new Promise<any>((resolve, reject) => pending.set(id, { resolve, reject }));
      port.postMessage({ type: "load", id, bytes, opts }, [bytes]);
      const m = await reply;
      const t2 = performance.now();
      return {
        sampleRate: m.sampleRate,
        byteLength: m.byteLength,
        compileMs: m.compileMs,
        instantiateMs: m.instantiateMs,
        initMs: m.initMs,
        prewarmMs: m.prewarmMs,
        memBytes: m.memBytes,
        hasReset: m.hasReset,
        mainCompileMs,
        roundtripMs: t2 - t1,
        totalMs: t2 - t0,
      };
    },
    firstBlocks() {
      if (firstDone) return Promise.resolve(firstDone);
      return new Promise((resolve, reject) => { first = { resolve, reject }; });
    },
    probeModulePost(module, timeoutMs = 3000) {
      meSeen = false;
      return new Promise((resolve) => {
        meResolve = resolve;
        setTimeout(() => resolve(meSeen), timeoutMs);
        try {
          port.postMessage({ type: "probe", module });
        } catch {
          resolve(true); // 送出側で DataCloneError
        }
      });
    },
  };
  return host;
}
