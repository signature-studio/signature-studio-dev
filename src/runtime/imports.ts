/**
 * Win32/シム import 関数の JS 側フォワーダ (最小雛形)。
 *
 * 戦略: shim (Win32 shim) 側と FLEngine 側の import 実名テーブルが確定するまでの間、
 * wasm から要求された import をまず受けるだけの受け皿を用意する。
 * - ExportedShimFunctions: shim 側 JS 実装が提供する「名前 → 関数」の表。
 *   将来 M4 で shim 実体が確定したら、これを instantiateWasm の imports に接続する。
 * - createImportForwarder: 未実装 import が呼ばれた瞬間に fail-fast
 *   (console.error + throw) するスタブ関数を生成する。
 *   静かに no-op で返すと不具合が遠い場所で顔を出すため、呼ばれたら即落ちる方針。
 */

/** shim 側が wasm に公開する関数表 (名前 → 関数)。実名は M4 で確定予定のため loose 型 */
export type ExportedShimFunctions = Record<
  string,
  (...args: unknown[]) => unknown
>;

/** wasm imports 側の名前空間表 (module 名 → { import 名 → 関数 }) */
export type WasmImports = Record<string, Record<string, unknown>>;

/**
 * 未実装 import 用の fail-fast フォワーダを生成する。
 * 呼ばれたら console.error のうえ例外を投げる (呼び出し引数の個数だけログに出す)。
 */
export function createImportForwarder(
  name: string,
): (...args: unknown[]) => never {
  return (...args: unknown[]) => {
    console.error(
      `[imports] 未実装 import が呼ばれました: "${name}" (args=${args.length})`,
    );
    throw new Error(`[imports] fail-fast: import "${name}" は未実装です`);
  };
}

/**
 * 名前一覧からフォワーダ表を作る (imports オブジェクトに展開しやすくする補助)。
 * 例: createForwarderTable("CreateFileA", "ReadFile") → { CreateFileA: ff, ReadFile: ff }
 */
export function createForwarderTable(
  ...names: string[]
): ExportedShimFunctions {
  const table: ExportedShimFunctions = {};
  for (const name of names) table[name] = createImportForwarder(name);
  return table;
}
