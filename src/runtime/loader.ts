/**
 * wasm ローダの最小実装。
 *
 * - bytes をそのまま WebAssembly.instantiate に渡す (fetchStreaming は使用しない:
 *   呼び出し側が fetch() / Node の fs.readFileSync / 生成バイト列のいずれかを渡す)。
 * - imports を接続し、exports と (あれば) memory を InstancedWasm として返す。
 * - エクスポート一覧と memory 有無を console に出力し、実機検証しやすくする。
 *
 * DOM に一切依存しない (Node のロジック検証からも直接 import できる)。
 */

import type { WasmImports } from "./imports";

export type InstancedWasm = {
  /** wasm instance の exports (関数 / memory / table 等) */
  exports: WebAssembly.Exports;
  /** wasm が自前で export している memory。無い場合は null */
  memory: WebAssembly.Memory | null;
};

/** exports から memory を引きぬく補助 (WASI/emscripten 産は大抵 export している) */
function findMemory(exports: WebAssembly.Exports): WebAssembly.Memory | null {
  const mem = (exports as { memory?: WebAssembly.Memory }).memory;
  return mem instanceof WebAssembly.Memory ? mem : null;
}

/**
 * wasm バイト列を imports 付きで instantiate する最小ローダ。
 * @param bytes    wasm モジュール全体のバイト列 (magic 0asm01 〜)
 * @param imports  名前空間 (module 名) ごとにまとめた imports 表
 */
export async function instantiateWasm(
  bytes: Uint8Array<ArrayBuffer>,
  imports: WasmImports = {},
): Promise<InstancedWasm> {
  if (bytes.length === 0) {
    throw new Error("[loader] 空 wasm バイト列です");
  }
  // TS (native 7.x) の WebAssembly 型: instantiate(bufferSource, imports) は
  // Instance 直を宣言しており実際の v8 戻り値 ({module,instance}) と不一致なため、
  // compile → instantiate(module, imports) の 2 段へ分解して型と実行時を一致させる。
  const wasmModule = await WebAssembly.compile(bytes);
  return instantiateCompiled(wasmModule, imports);
}

/**
 * コンパイル済み Module (compileStreaming / postMessage で受け取ったもの) を instantiate する。
 * instantiateWasm と同じ後処理 (exports 一覧・memory 検出・ログ) を共有する。
 * WasmImports (loose な Record) ↔ WebAssembly.Imports は unknown ブリッジで接続。
 */
export async function instantiateCompiled(
  wasmModule: WebAssembly.Module,
  imports: WasmImports = {},
): Promise<InstancedWasm & { instance: WebAssembly.Instance }> {
  const instance = await WebAssembly.instantiate(
    wasmModule,
    imports as unknown as WebAssembly.Imports,
  );
  const exports = instance.exports;

  const names = Object.keys(exports);
  const memory = findMemory(exports);
  // lifted FLEngine 級は export が数千〜数万になるため一覧は少数のときだけ出す
  const list = names.length <= 64 ? ` [${names.join(", ")}]` : "";
  console.log(
    `[loader] wasm instantiated: ${names.length} exports${list}` +
      `, memory: ${memory ? `${memory.buffer.byteLength}B` : "none"}`,
  );

  return { exports, memory, instance };
}
