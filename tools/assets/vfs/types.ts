// manifest v1 + VFS 共通型。仕様の正本は ../MANIFEST.md
export const MANIFEST_VERSION = 1;

/** 0=raw 1=br 2=zstd (chunk 配列 k) */
export const CODEC_NAMES = ['raw', 'br', 'zst'] as const;
export type CodecName = (typeof CODEC_NAMES)[number];
export const CODEC_EXT: Record<number, string> = { 0: 'raw', 1: 'br', 2: 'zst' };

/** ファイル葉: [size, firstChunk, off, flags?]  off>=0: firstChunk 内の off から (pack)、off=-1: firstChunk から ceil(size/chunkSize) 個の連続 chunk
 *  flags bit0 = stub (本体なし: wasm 化/再ビルド対象バイナリ。size のみ)。size=0 は [0] */
export type FileEntry = [size: number, first?: number, off?: number, flags?: number];
export interface DirEntry {
  [name: string]: DirEntry | FileEntry;
}

export interface ChunkTable {
  n: number;
  /** 16byte(sha256 先頭) hex を連結 (32 文字 x n) */
  id: string;
  /** 非圧縮サイズ */
  u: number[];
  /** 格納サイズ (codec 適用後) */
  c: number[];
  /** codec 番号 */
  k: number[];
}

export interface Manifest {
  v: 1;
  name: string;
  created: string;
  /** 論理 chunk 最大サイズ (byte) */
  chunkSize: number;
  /** pack 化する小ファイル上限 */
  smallMax: number;
  /** 配布レイアウト: objects = c/<id[0:2]>/<id>.<ext> を個別 GET、 */
  layout: 'objects';
  chunks: ChunkTable;
  /** 優先度グループ -> [firstChunk, count] の列 (連続範囲) */
  groups: Record<string, [number, number][]>;
  tree: DirEntry;
  stats: Record<string, number | string>;
}

export interface FileStat {
  type: 'file' | 'dir';
  size: number;
  /** 正規 (元ケース) 名 */
  name: string;
  stub: boolean;
}

/** 非同期チャンクソース: 復号後 (非圧縮) のバイト列を返す */
export interface ChunkSource {
  fetchChunk(idx: number): Promise<Uint8Array>;
}

/** 同期ファイル (OPFS SyncAccessHandle / node fs 共通) */
export interface SyncFile {
  read(buf: Uint8Array, at: number): number;
  write(buf: Uint8Array, at: number): number;
  getSize(): number;
  truncate(n: number): void;
  flush(): void;
  close(): void;
}

export interface VfsStats {
  reads: number;
  bytesRead: number;
  chunkMemHits: number;
  chunkCacheHits: number;
  chunkMisses: number;
  chunkPrefetched: number;
  netBytesDecoded: number;
  netWaitMs: number;
  evictions: number;
}
