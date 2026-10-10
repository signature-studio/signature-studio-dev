import type { Manifest, SyncFile } from './types.ts';
import { ManifestIndex } from './manifest.ts';
import { HttpChunkSource } from './http-source.ts';
import { MemCache, SlotCache } from './cache.ts';
import type { ChunkCache } from './cache.ts';
import { LazyVfs } from './lazy-vfs.ts';
import { SabLoader, SyncXhrLoader } from './loader.ts';
import type { SyncChunkLoader, WorkerLike } from './loader.ts';

export * from './types.ts';
export { ManifestIndex } from './manifest.ts';
export { LazyVfs, VfsError } from './lazy-vfs.ts';
export { SlotCache, MemCache } from './cache.ts';
export type { ChunkCache } from './cache.ts';
export { HttpChunkSource } from './http-source.ts';
export { SabLoader, SyncXhrLoader } from './loader.ts';
export type { SyncChunkLoader, WorkerLike } from './loader.ts';
export { normalizePath } from './path.ts';
export { registerDecoders, loadNodeDecoders } from './codec.ts';
export { openIdb } from './idb.ts';
export type { IdbHandle } from './idb.ts';
export { openAssetStream, loadWasmAsset, assetKeyHash, debugCorruptOpfsChunk, debugCorruptIdbChunk, debugAssetTiers, debugDropAssetCaches } from './asset.ts';
export type { OpenAssetOptions, OpenAssetResult, AssetStats } from './asset.ts';

export async function fetchManifest(baseUrl: string, fetchImpl: typeof fetch = fetch): Promise<Manifest> {
  const base = baseUrl.endsWith('/') ? baseUrl : baseUrl + '/';
  const latest = await (await fetchImpl(base + 'latest.json')).json();
  const res = await fetchImpl(base + latest.manifest);
  if (!res.ok) throw new Error('manifest HTTP ' + res.status);
  return (await res.json()) as Manifest;
}

export interface OpenVfsOptions {
  baseUrl: string;
  manifest: Manifest;
  /** 永続キャッシュ用の SyncFile (OPFS/node)。null なら揮発 MemCache */
  cacheFile?: SyncFile | null;
  /** キャッシュ上限 (byte) */
  maxCacheBytes?: number;
  loader: 'sab' | 'xhr';
  /** loader==='sab' 時: fetcher Worker 生成 */
  spawn?: () => WorkerLike;
  nodeDecoders?: boolean;
  nSlots?: number;
  /** fetcher の並行 fetch 数 (既定 min(8, nSlots)) */
  fetchConcurrency?: number;
  roots?: string[];
  verify?: boolean;
  memChunks?: number;
  maxReadahead?: number;
}

export function openVfs(o: OpenVfsOptions): { vfs: LazyVfs; source: HttpChunkSource; cache: ChunkCache; loader: SyncChunkLoader; ready: Promise<void> } {
  const index = new ManifestIndex(o.manifest);
  const max = o.maxCacheBytes ?? 1024 * 2 ** 20;
  let cache: ChunkCache;
  if (o.cacheFile) {
    const slotBytes = 4096 + index.chunkSize;
    cache = new SlotCache(o.cacheFile, index.chunkSize, Math.max(8, Math.floor(max / slotBytes)));
  } else cache = new MemCache(max);
  const source = new HttpChunkSource({ baseUrl: o.baseUrl, chunks: o.manifest.chunks, verify: o.verify });
  let loader: SyncChunkLoader;
  if (o.loader === 'sab') {
    if (!o.spawn) throw new Error('spawn required for sab loader');
    loader = new SabLoader({ baseUrl: o.baseUrl, chunks: o.manifest.chunks, chunkSize: index.chunkSize, nSlots: o.nSlots, concurrency: o.fetchConcurrency, spawn: o.spawn, verify: o.verify, nodeDecoders: o.nodeDecoders });
  } else loader = new SyncXhrLoader(o.baseUrl, o.manifest.chunks);
  const vfs = new LazyVfs({ index, cache, loader, source, roots: o.roots, memChunks: o.memChunks, maxReadahead: o.maxReadahead });
  return { vfs, source, cache, loader, ready: loader.ready };
}
