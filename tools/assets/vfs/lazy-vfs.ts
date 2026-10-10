import type { ChunkSource, FileStat, VfsStats } from './types.ts';
import type { ChunkCache } from './cache.ts';
import type { SyncChunkLoader } from './loader.ts';
import { ManifestIndex } from './manifest.ts';
import type { FileRef } from './manifest.ts';
import { normalizePath } from './path.ts';

export class VfsError extends Error {
  code: 'ENOENT' | 'EISDIR' | 'ENOTDIR' | 'EBADF' | 'EIO' | 'ESTUB';
  constructor(code: VfsError['code'], msg: string) {
    super(`${code}: ${msg}`);
    this.code = code;
  }
}

export interface LazyVfsOptions {
  index: ManifestIndex;
  cache: ChunkCache;
  loader: SyncChunkLoader;
  /** 非同期 chunk ソース (preload 用。無ければ preload 不可) */
  source?: ChunkSource;
  /** 直近 chunk のメモリ保持数 (既定 8) */
  memChunks?: number;
  /** 先読み上限 chunk 数 (既定 8)。0 で無効 */
  maxReadahead?: number;
  /** 全 chunk が <= この数のファイルは初回アクセスで丸ごと先読み (既定 4) */
  wholeFileChunks?: number;
  /** Win32 root prefix (大小無視) */
  roots?: string[];
  /** stub ファイル (wasm 化対象バイナリ等) の read 挙動 */
  stubMode?: 'error' | 'zero';
}

interface OpenFile {
  path: string;
  ref: FileRef;
  pos: number;
  lastCi: number;
  seq: number;
  touched: boolean;
}

/**
 * Worker 内で同期 read を提供する遅延取得 VFS。
 *  read -> (mem LRU) -> (ChunkCache: OPFS slot / mem) -> SyncChunkLoader(SAB で fetcher をブロッキング待ち)
 * 先読み: 連続アクセス検出 (seq) / 小ファイルは丸ごと / preload() で優先グループを並列取得。
 */
export class LazyVfs {
  private o: Required<Pick<LazyVfsOptions, 'memChunks' | 'maxReadahead' | 'wholeFileChunks' | 'stubMode'>> & LazyVfsOptions;
  private fds = new Map<number, OpenFile>();
  private nextFd = 3;
  private mem = new Map<number, Uint8Array>();
  readonly stats: VfsStats = {
    reads: 0,
    bytesRead: 0,
    chunkMemHits: 0,
    chunkCacheHits: 0,
    chunkMisses: 0,
    chunkPrefetched: 0,
    netBytesDecoded: 0,
    netWaitMs: 0,
    evictions: 0,
  };
  /** miss 毎の同期待ち時間 (ms) — 先頭 N 件。レイテンシ分布の実測用 */
  readonly missLatencies: number[] = [];

  constructor(o: LazyVfsOptions) {
    // 明示的 undefined が既定値を潰さないよう除去してから既定値とマージ
    const given = Object.fromEntries(Object.entries(o).filter(([, v]) => v !== undefined)) as unknown as LazyVfsOptions;
    this.o = { memChunks: 8, maxReadahead: 8, wholeFileChunks: 4, stubMode: 'error', ...given };
    if ('setSink' in o.loader) (o.loader as unknown as { setSink(s: (i: number, d: Uint8Array) => void): void }).setSink((i, d) => this.sinkPrefetched(i, d));
  }

  get index(): ManifestIndex {
    return this.o.index;
  }

  private norm(p: string): string {
    return normalizePath(p, this.o.roots);
  }

  // ---- 名前空間 ----
  statSync(path: string): FileStat | null {
    return this.o.index.stat(this.norm(path));
  }
  existsSync(path: string): boolean {
    return this.statSync(path) !== null;
  }
  readdirSync(path: string): FileStat[] {
    const r = this.o.index.readdir(this.norm(path));
    if (!r) throw new VfsError(this.statSync(path) ? 'ENOTDIR' : 'ENOENT', path);
    return r;
  }

  // ---- fd I/O ----
  openSync(path: string): number {
    const p = this.norm(path);
    const ref = this.o.index.file(p);
    if (!ref) throw new VfsError(this.o.index.stat(p) ? 'EISDIR' : 'ENOENT', path);
    const fd = this.nextFd++;
    this.fds.set(fd, { path: p, ref, pos: 0, lastCi: -2, seq: 0, touched: false });
    return fd;
  }
  closeSync(fd: number): void {
    if (!this.fds.delete(fd)) throw new VfsError('EBADF', String(fd));
  }
  fstatSync(fd: number): { size: number } {
    return { size: this.fd(fd).ref.size };
  }
  private fd(fd: number): OpenFile {
    const f = this.fds.get(fd);
    if (!f) throw new VfsError('EBADF', String(fd));
    return f;
  }

  seekSync(fd: number, pos: number): void {
    this.fd(fd).pos = pos;
  }

  /** pos 省略時は fd の現在位置から読んで進める (POSIX read 相当) */
  readSync(fd: number, dst: Uint8Array, dstOff = 0, len = dst.length - dstOff, pos?: number): number {
    const f = this.fd(fd);
    const at = pos ?? f.pos;
    const end = Math.min(f.ref.size, at + len);
    const total = end - at;
    this.stats.reads++;
    if (total <= 0) return 0;
    if (f.ref.stub) {
      if (this.o.stubMode === 'error') throw new VfsError('ESTUB', `${f.path} is a stub (wasm-lifted binary; no bytes served)`);
      dst.fill(0, dstOff, dstOff + total);
    } else {
      this.drain();
      const cs = this.o.index.chunkSize;
      let done = 0;
      while (done < total) {
        const p = at + done;
        let ci: number;
        let co: number;
        if (f.ref.off >= 0) {
          ci = f.ref.first;
          co = f.ref.off + p;
        } else {
          ci = f.ref.first + Math.floor(p / cs);
          co = p % cs;
        }
        const avail = this.o.index.chunkUsize(ci) - co;
        const take = Math.min(total - done, avail);
        this.copyFromChunk(f, ci, co, dst, dstOff + done, take);
        done += take;
      }
    }
    if (pos === undefined) f.pos = at + total;
    this.stats.bytesRead += total;
    return total;
  }

  readFileSync(path: string): Uint8Array {
    const fd = this.openSync(path);
    try {
      const size = this.fd(fd).ref.size;
      const out = new Uint8Array(size);
      let n = 0;
      while (n < size) {
        const r = this.readSync(fd, out, n, size - n, n);
        if (r <= 0) break;
        n += r;
      }
      return out;
    } finally {
      this.closeSync(fd);
    }
  }

  // ---- chunk 取得 ----
  private copyFromChunk(f: OpenFile, ci: number, co: number, dst: Uint8Array, dOff: number, len: number): void {
    const idx = this.o.index;
    const m = this.mem.get(ci);
    if (m) {
      this.mem.delete(ci);
      this.mem.set(ci, m);
      dst.set(m.subarray(co, co + len), dOff);
      this.stats.chunkMemHits++;
      this.afterAccess(f, ci, false);
      return;
    }
    const id = idx.chunkId(ci);
    if (this.o.cache.readRange(id, co, dst, dOff, len)) {
      this.stats.chunkCacheHits++;
      this.afterAccess(f, ci, false);
      return;
    }
    // miss: 同期取得
    const t0 = performance.now();
    const wasPrefetched = this.o.loader.isPending(ci);
    const data = this.o.loader.loadSync(ci);
    const dt = performance.now() - t0;
    this.stats.chunkMisses++;
    this.stats.netWaitMs += dt;
    this.stats.netBytesDecoded += data.length;
    if (!wasPrefetched && this.missLatencies.length < 20000) this.missLatencies.push(dt);
    dst.set(data.subarray(co, co + len), dOff);
    this.o.cache.put(id, data);
    this.remember(ci, data.slice());
    this.o.loader.release(ci);
    this.afterAccess(f, ci, true);
  }

  private remember(ci: number, data: Uint8Array): void {
    this.mem.set(ci, data);
    while (this.mem.size > this.o.memChunks) this.mem.delete(this.mem.keys().next().value as number);
  }

  /** 先読み結果を cache へ (fetcher が埋めた READY を回収) */
  private sinkPrefetched(ci: number, data: Uint8Array): void {
    this.o.cache.put(this.o.index.chunkId(ci), data);
    this.stats.chunkPrefetched++;
  }
  private drain(): void {
    this.o.loader.drain((i, d) => this.sinkPrefetched(i, d));
  }

  private afterAccess(f: OpenFile, ci: number, wasMiss: boolean): void {
    if (this.o.maxReadahead <= 0 || f.ref.off >= 0) {
      f.lastCi = ci;
      return;
    }
    // 大ファイル (専用 chunk): 連続検出 + 初回丸ごと
    const last = f.ref.first + Math.ceil(f.ref.size / this.o.index.chunkSize) - 1;
    const seqHit = ci === f.lastCi + 1 || (ci === f.lastCi && f.seq > 0);
    if (ci === f.lastCi + 1) f.seq++;
    else if (ci !== f.lastCi) f.seq = 0;
    f.lastCi = ci;
    let want = 0;
    if (!f.touched) {
      f.touched = true;
      const n = last - f.ref.first + 1;
      if (n <= this.o.wholeFileChunks) want = n - 1;
    }
    if (seqHit || wasMiss) want = Math.max(want, Math.min(this.o.maxReadahead, 2 ** Math.min(f.seq + 1, 4)));
    if (want <= 0) return;
    const list: number[] = [];
    for (let k = ci + 1; k <= Math.min(last, ci + want); k++) {
      if (this.mem.has(k) || this.o.cache.has(this.o.index.chunkId(k))) continue;
      list.push(k);
    }
    if (list.length) this.o.loader.prefetch(list);
  }

  // ---- ヒント API ----
  /** 配下ファイルの chunk を非同期先読み要求 (ブロックしない)。発行数を返す */
  prefetchPath(path: string, maxChunks = 16): number {
    const idx = this.o.index;
    const p = this.norm(path);
    const set: number[] = [];
    for (const [, ref] of idx.walkFiles(p)) {
      for (const c of idx.fileChunks(ref)) {
        if (!this.o.cache.has(idx.chunkId(c)) && !set.includes(c)) set.push(c);
        if (set.length >= maxChunks) break;
      }
      if (set.length >= maxChunks) break;
    }
    return this.o.loader.prefetch(set);
  }

  /** グループ (T0 / T0p / T1 ...) の全 chunk を並列取得して cache に入れる (非同期; 起動前に呼ぶ)。pin=true で eviction 対象外 */
  async preload(group: string | number[], opts: { concurrency?: number; pin?: boolean; onProgress?: (done: number, total: number, bytes: number) => void } = {}): Promise<{ chunks: number; fetched: number; bytes: number; ms: number }> {
    const src = this.o.source;
    if (!src) throw new Error('preload requires an async ChunkSource');
    const idx = this.o.index;
    const list = typeof group === 'string' ? idx.groupChunks(group) : group;
    const need = list.filter((c) => !this.o.cache.has(idx.chunkId(c)));
    const t0 = performance.now();
    let done = 0;
    let bytes = 0;
    let k = 0;
    const conc = opts.concurrency ?? 8;
    await Promise.all(
      Array.from({ length: conc }, async () => {
        while (k < need.length) {
          const c = need[k++];
          const d = await src.fetchChunk(c);
          this.o.cache.put(idx.chunkId(c), d);
          bytes += d.length;
          opts.onProgress?.(++done, need.length, bytes);
        }
      })
    );
    if (opts.pin) this.pinChunks(list);
    return { chunks: list.length, fetched: need.length, bytes, ms: performance.now() - t0 };
  }

  private pinned = new Set<string>();
  pinChunks(list: number[]): void {
    for (const c of list) this.pinned.add(this.o.index.chunkId(c));
    this.o.cache.setPinned(this.pinned);
  }
  pinGroup(name: string): void {
    this.pinChunks(this.o.index.groupChunks(name));
  }

  debugState(): { memChunks: number; memLimit: number; maxReadahead: number } {
    return { memChunks: this.mem.size, memLimit: this.o.memChunks, maxReadahead: this.o.maxReadahead };
  }

  clearMemory(): void {
    this.mem.clear();
  }

  close(): void {
    this.o.cache.flush();
    this.o.loader.close();
  }
}
