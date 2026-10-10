/**
 * 巨大 wasm 用ローダ (loader.ts の instantiateWasm の上位互換ではなく、ブート経路専用の補助群)。
 *
 * - fetchCompile: fetch → (進捗カウント) → WebAssembly.compileStreaming。ダウンロードとコンパイルが並行する。
 * - buildImports: Module.imports() を introspection し、実装 provider を優先、無ければ fail-fast フォワーダで埋める。
 * - initEmscripten: `emscripten_stack_init` → `__wasm_call_ctors` の定型初期化。
 * DOM 非依存 (Worker 内で動く)。
 */

import { createImportForwarder } from "./imports";
import type { ResourceInfo } from "./worker_protocol";

export type FetchCompileOptions = {
  cacheMode: "http" | "cacheapi" | "none";
  compile: "streaming" | "bytes";
  onProgress?: (loaded: number, total: number) => void;
};

const CACHE_NAME = "rt-wasm-v1";

async function openResponse(url: string, mode: FetchCompileOptions["cacheMode"]): Promise<{ res: Response; fromCacheApi: boolean }> {
  if (mode === "cacheapi" && typeof caches !== "undefined") {
    const c = await caches.open(CACHE_NAME);
    const hit = await c.match(url);
    if (hit) return { res: hit, fromCacheApi: true };
    const net = await fetch(url, { cache: "no-store" });
    if (!net.ok) throw new Error(`[loader] fetch ${url}: HTTP ${net.status}`);
    await c.put(url, net.clone());
    return { res: net, fromCacheApi: false };
  }
  const res = await fetch(url, { cache: mode === "none" ? "no-store" : "default" });
  if (!res.ok) throw new Error(`[loader] fetch ${url}: HTTP ${res.status}`);
  return { res, fromCacheApi: false };
}

/**
 * 進捗用に body を clone で並行消費する。compileStreaming には「元の Response」をそのまま渡す
 * (Response を作り直すと Chromium の wasm code cache 連携 (HTTP キャッシュ側 metadata) が外れるため)。
 */
function countClone(res: Response, onProgress?: (loaded: number, total: number) => void): Promise<void> {
  const total = Number(res.headers.get("content-length") ?? 0);
  if (!onProgress) return Promise.resolve();
  const body = res.clone().body;
  if (!body) return Promise.resolve();
  return (async () => {
    const r = body.getReader();
    let loaded = 0;
    for (;;) {
      const { done, value } = await r.read();
      if (done) break;
      loaded += value.byteLength;
      onProgress(loaded, total);
    }
  })();
}

function resourceInfo(url: string, fromCacheApi: boolean): ResourceInfo {
  const abs = new URL(url, (globalThis as { location?: { href: string } }).location?.href).href;
  const ents = performance.getEntriesByName(abs) as Array<PerformanceResourceTiming & { deliveryType?: string }>;
  const e = ents[ents.length - 1];
  return {
    transferSize: e ? e.transferSize : null,
    decodedBodySize: e ? e.decodedBodySize : null,
    deliveryType: e?.deliveryType ?? null,
    fromCacheApi,
  };
}

export async function fetchCompile(
  url: string,
  opts: FetchCompileOptions,
): Promise<{ module: WebAssembly.Module; resource: ResourceInfo }> {
  const { res, fromCacheApi } = await openResponse(url, opts.cacheMode);
  let module: WebAssembly.Module;
  if (opts.compile === "streaming") {
    const counting = countClone(res, opts.onProgress);
    module = await WebAssembly.compileStreaming(res);
    await counting;
  } else {
    const bytes = new Uint8Array(await res.arrayBuffer());
    opts.onProgress?.(bytes.length, bytes.length);
    module = await WebAssembly.compile(bytes);
  }
  return { module, resource: resourceInfo(url, fromCacheApi) };
}

export type ImportTable = Record<string, Record<string, unknown>>;

/**
 * Module の関数 import を provider ("module.name" → 関数) で解決。未解決は fail-fast フォワーダ
 * (呼ばれた瞬間に throw: 静かな no-op で後方不具合にしない — imports.ts の方針と同一)。
 * memory / table / global import は extra で明示的に渡す。
 */
export function buildImports(
  module: WebAssembly.Module,
  providers: Array<Record<string, unknown>>,
  extra: ImportTable = {},
): { imports: ImportTable; unresolved: string[] } {
  const imports: ImportTable = {};
  for (const [m, o] of Object.entries(extra)) imports[m] = { ...o };
  const unresolved: string[] = [];
  for (const d of WebAssembly.Module.imports(module)) {
    const bucket = (imports[d.module] ??= {});
    if (d.name in bucket) continue;
    if (d.kind !== "function") throw new Error(`[loader] ${d.module}.${d.name} (${d.kind}) は extra で渡してください`);
    const key = `${d.module}.${d.name}`;
    let impl: unknown;
    for (const p of providers) if (key in p) { impl = p[key]; break; }
    if (impl === undefined) {
      unresolved.push(key);
      impl = createImportForwarder(key);
    }
    bucket[d.name] = impl;
  }
  return { imports, unresolved };
}

export function initEmscripten(exports: WebAssembly.Exports): string[] {
  const done: string[] = [];
  const e = exports as Record<string, unknown>;
  for (const name of ["emscripten_stack_init", "__wasm_call_ctors"]) {
    const f = e[name];
    if (typeof f === "function") {
      (f as () => void)();
      done.push(name);
    }
  }
  return done;
}

/** manifest 生成側と同じ: import/export 数の概算 (起動ログ用) */
export function describeModule(module: WebAssembly.Module): { imports: number; exports: number; unresolvedKinds: Record<string, number> } {
  const kinds: Record<string, number> = {};
  const imps = WebAssembly.Module.imports(module);
  for (const i of imps) kinds[i.kind] = (kinds[i.kind] ?? 0) + 1;
  return { imports: imps.length, exports: WebAssembly.Module.exports(module).length, unresolvedKinds: kinds };
}
