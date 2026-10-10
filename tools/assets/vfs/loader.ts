import type { ChunkTable } from './types.ts';
import { chunkUrl } from './http-source.ts';
import { decodeStoredSync } from './codec.ts';
import { createSab, SabClient } from './sab.ts';

/** 同期 chunk ローダ (cache miss 時にエンジンスレッドをブロックして取得) */
export interface SyncChunkLoader {
  /** fetcher の起動完了。ブラウザの nested Worker は親のイベントループが空かないと script を取得できないため、
   *  最初の同期 read の前に必ず await すること (さもないとデッドロックする)。 */
  readonly ready: Promise<void>;
  /** chunk を取得 (必要ならブロック)。返る view は release(idx) まで有効 */
  loadSync(idx: number): Uint8Array;
  release(idx: number): void;
  /** 非同期先読み要求。実際に発行した数を返す */
  prefetch(idxs: number[]): number;
  /** READY の先読み結果を sink へ流して解放 */
  drain(sink: (idx: number, data: Uint8Array) => void): void;
  isPending(idx: number): boolean;
  stat(): Promise<Record<string, number>>;
  close(): void;
}

export interface WorkerLike {
  postMessage(msg: unknown): void;
  terminate(): unknown;
  onMessage(cb: (m: any) => void): void;
}

export interface SabLoaderOptions {
  baseUrl: string;
  chunks: ChunkTable;
  chunkSize: number;
  nSlots?: number;
  verify?: boolean;
  concurrency?: number;
  /** fetcher Worker を生成 (node: worker_threads / browser: Worker)。nodeDecoders は node のみ true */
  spawn: () => WorkerLike;
  nodeDecoders?: boolean;
}

export class SabLoader implements SyncChunkLoader {
  private client: SabClient;
  private worker: WorkerLike;
  private statWaiters: ((m: any) => void)[] = [];
  private order: number[] = []; // 要求順 (最古から)
  readonly ready: Promise<void>;
  constructor(o: SabLoaderOptions) {
    const nSlots = o.nSlots ?? 16;
    const sab = createSab(nSlots, o.chunkSize);
    this.worker = o.spawn();
    let readyRes!: () => void;
    this.ready = new Promise<void>((r) => (readyRes = r));
    this.worker.onMessage((m) => {
      if (m.t === 'stat') this.statWaiters.shift()?.(m);
      else if (m.t === 'ready') readyRes();
    });
    this.worker.postMessage({ t: 'init', sab, baseUrl: o.baseUrl, chunks: o.chunks, verify: o.verify, concurrency: o.concurrency ?? Math.min(8, nSlots), nodeDecoders: o.nodeDecoders });
    this.client = new SabClient(sab, this.worker);
  }

  private sink: ((idx: number, data: Uint8Array) => void) | null = null;
  setSink(s: (idx: number, data: Uint8Array) => void): void {
    this.sink = s;
  }

  isPending(idx: number): boolean {
    return this.client.has(idx);
  }

  loadSync(idx: number): Uint8Array {
    if (!this.client.has(idx)) {
      while (!this.client.request(idx)) {
        // スロット枯渇: 最古の保持分を待って sink に流して空ける
        const oldest = this.order.find((i) => this.client.has(i));
        if (oldest === undefined) throw new Error('no slot and nothing held');
        const d = this.client.wait(oldest);
        this.sink?.(oldest, d);
        this.client.release(oldest);
      }
      this.order.push(idx);
    }
    return this.client.wait(idx);
  }

  release(idx: number): void {
    this.client.release(idx);
    const k = this.order.indexOf(idx);
    if (k >= 0) this.order.splice(k, 1);
  }

  prefetch(idxs: number[]): number {
    let n = 0;
    for (const i of idxs) {
      if (this.client.has(i)) continue;
      if (this.client.freeCount() <= 2) break; // 同期要求用に 2 枠残す
      if (this.client.request(i)) {
        this.order.push(i);
        n++;
      }
    }
    return n;
  }

  drain(sink: (idx: number, data: Uint8Array) => void): void {
    for (const idx of this.client.readyList()) {
      const d = this.client.wait(idx);
      sink(idx, d);
      this.release(idx);
    }
  }

  stat(): Promise<Record<string, number>> {
    return new Promise((res) => {
      this.statWaiters.push(res);
      this.worker.postMessage({ t: 'stat' });
    });
  }

  close(): void {
    this.worker.terminate();
  }
}

/** 同期 XHR ローダ (browser Worker 専用フォールバック: SAB 無し/COOP-COEP 無しの環境)。先読み不可。 */
export class SyncXhrLoader implements SyncChunkLoader {
  readonly ready = Promise.resolve();
  private last: Uint8Array | null = null;
  private baseUrl: string;
  private chunks: ChunkTable;
  constructor(baseUrl: string, chunks: ChunkTable) {
    this.baseUrl = baseUrl.endsWith('/') ? baseUrl : baseUrl + '/';
    this.chunks = chunks;
  }
  loadSync(idx: number): Uint8Array {
    const url = chunkUrl(this.baseUrl, this.chunks, idx);
    const x = new XMLHttpRequest();
    x.open('GET', url, false);
    x.responseType = 'arraybuffer';
    x.send();
    if (x.status !== 200) throw new Error(`HTTP ${x.status} ${url}`);
    this.last = decodeStoredSync(new Uint8Array(x.response as ArrayBuffer), this.chunks.k[idx], this.chunks.u[idx]);
    return this.last;
  }
  release(): void {
    this.last = null;
  }
  prefetch(): number {
    return 0;
  }
  drain(): void {}
  isPending(): boolean {
    return false;
  }
  async stat() {
    return {};
  }
  close(): void {}
}
