// 手動デコード (サーバが Content-Encoding を付けない/ブラウザが zstd を知らない場合のフォールバック)。
// 通常経路: R2 オブジェクトに Content-Encoding: br|zstd を付与 -> fetch/XHR がネイティブ復号するので不要。

export type Decoder = (stored: Uint8Array) => Uint8Array | Promise<Uint8Array>;
export interface Decoders {
  br?: Decoder;
  zst?: Decoder;
}

let registered: Decoders = {};
export function registerDecoders(d: Decoders): void {
  registered = { ...registered, ...d };
}

export async function loadNodeDecoders(): Promise<void> {
  const zlib = await import('node:zlib');
  registerDecoders({
    br: (b) => zlib.brotliDecompressSync(b),
    zst: (b) => zlib.zstdDecompressSync(b),
  });
}

/** codec: 0 raw / 1 br / 2 zst。stored.length が usize なら復号済み (ネイティブ Content-Encoding) とみなす */
export async function decodeStored(stored: Uint8Array, codec: number, usize: number): Promise<Uint8Array> {
  if (codec === 0 || stored.length === usize) return stored;
  const d = codec === 1 ? registered.br : registered.zst;
  if (!d) throw new Error(`chunk is stored with codec ${codec} but neither Content-Encoding nor a decoder is available`);
  const out = await d(stored);
  if (out.length !== usize) throw new Error(`decoded size ${out.length} != ${usize}`);
  return out;
}

export function decodeStoredSync(stored: Uint8Array, codec: number, usize: number): Uint8Array {
  if (codec === 0 || stored.length === usize) return stored;
  const d = codec === 1 ? registered.br : registered.zst;
  if (!d) throw new Error(`codec ${codec}: no Content-Encoding and no decoder registered`);
  const out = d(stored);
  if (out instanceof Promise) throw new Error('async decoder in sync path');
  if (out.length !== usize) throw new Error(`decoded size ${out.length} != ${usize}`);
  return out;
}
