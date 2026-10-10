import type { ChunkSource, ChunkTable } from './types.ts';
import { CODEC_EXT } from './types.ts';
import { decodeStored } from './codec.ts';

export interface HttpSourceOptions {
  baseUrl: string;
  chunks: ChunkTable;
  /** 並行 fetch 上限 */
  concurrency?: number;
  retries?: number;
  /** 復号後に sha256(先頭 128bit) と id を照合 (WebCrypto/node crypto)。既定 false */
  verify?: boolean;
  fetchImpl?: typeof fetch;
  /** デバッグ/テスト用: リクエスト毎のフック */
  onFetch?: (idx: number, bytes: number, ms: number) => void;
}

export function chunkUrl(baseUrl: string, chunks: ChunkTable, i: number): string {
  const id = chunks.id.substr(i * 32, 32);
  return `${baseUrl}c/${id.slice(0, 2)}/${id}.${CODEC_EXT[chunks.k[i]]}`;
}

async function sha128hex(b: Uint8Array): Promise<string> {
  const d = new Uint8Array(await crypto.subtle.digest('SHA-256', b as BufferSource));
  let s = '';
  for (let i = 0; i < 16; i++) s += d[i].toString(16).padStart(2, '0');
  return s;
}

/** fetch ベースの非同期 chunk ソース (fetcher worker / preload で使用)。同一 idx の同時要求は 1 本化。 */
export class HttpChunkSource implements ChunkSource {
  private o: Required<Omit<HttpSourceOptions, 'onFetch' | 'fetchImpl'>> & Pick<HttpSourceOptions, 'onFetch' | 'fetchImpl'>;
  private inflight = new Map<number, Promise<Uint8Array>>();
  private active = 0;
  private waiters: (() => void)[] = [];
  bytesFetched = 0;
  requests = 0;
  constructor(opts: HttpSourceOptions) {
    this.o = { concurrency: 8, retries: 3, verify: false, ...opts, baseUrl: opts.baseUrl.endsWith('/') ? opts.baseUrl : opts.baseUrl + '/' };
  }

  fetchChunk(idx: number): Promise<Uint8Array> {
    let p = this.inflight.get(idx);
    if (!p) {
      p = this.limited(() => this.doFetch(idx)).finally(() => this.inflight.delete(idx));
      this.inflight.set(idx, p);
    }
    return p;
  }

  private async limited<T>(fn: () => Promise<T>): Promise<T> {
    while (this.active >= this.o.concurrency) await new Promise<void>((r) => this.waiters.push(r));
    this.active++;
    try {
      return await fn();
    } finally {
      this.active--;
      this.waiters.shift()?.();
    }
  }

  private async doFetch(idx: number): Promise<Uint8Array> {
    const { chunks } = this.o;
    const url = chunkUrl(this.o.baseUrl, chunks, idx);
    const usize = chunks.u[idx];
    let lastErr: unknown;
    for (let attempt = 0; attempt <= this.o.retries; attempt++) {
      const t0 = performance.now();
      try {
        this.requests++;
        const res = await (this.o.fetchImpl ?? fetch)(url);
        if (!res.ok) throw new Error(`HTTP ${res.status} ${url}`);
        const stored = new Uint8Array(await res.arrayBuffer());
        this.bytesFetched += stored.length;
        const out = await decodeStored(stored, chunks.k[idx], usize);
        if (out.length !== usize) throw new Error(`size mismatch ${out.length} != ${usize} for ${url}`);
        if (this.o.verify) {
          const h = await sha128hex(out);
          if (h !== chunks.id.substr(idx * 32, 32)) throw new Error('content hash mismatch ' + url);
        }
        this.o.onFetch?.(idx, stored.length, performance.now() - t0);
        return out;
      } catch (e) {
        lastErr = e;
        if (attempt < this.o.retries) await new Promise((r) => setTimeout(r, 50 * 2 ** attempt));
      }
    }
    throw lastErr instanceof Error ? lastErr : new Error(String(lastErr));
  }
}
