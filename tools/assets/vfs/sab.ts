// 同期 read を実現する SAB ブリッジ: エンジン Worker は Atomics.wait でブロックし、fetcher Worker が非同期に
// fetch+復号した chunk を SAB スラブへ書いて notify する (browser Worker / node worker_threads 共通)。
//
//   SAB layout:  Int32[HDR_INTS]  = [magic, nSlots, slotBytes, 0, 0, 0, 0, 0]
//                Int32[nSlots*4]  = per-slot [state, chunkIdx, length, errcode]
//                Uint8[nSlots*slotBytes] slab
//   state: FREE(0) -> PENDING(1, client) -> READY(2)/ERROR(3, server) -> FREE(client が copy 後)
import type { ChunkSource } from './types.ts';

export const ST_FREE = 0;
export const ST_PENDING = 1;
export const ST_READY = 2;
export const ST_ERROR = 3;
const HDR_INTS = 8;
const MAGIC = 0x53414231; // 'SAB1'

export function createSab(nSlots: number, slotBytes: number): SharedArrayBuffer {
  const ctrlBytes = (HDR_INTS + nSlots * 4) * 4;
  const dataOff = Math.ceil(ctrlBytes / 4096) * 4096;
  const sab = new SharedArrayBuffer(dataOff + nSlots * slotBytes);
  const i32 = new Int32Array(sab, 0, HDR_INTS);
  i32[0] = MAGIC;
  i32[1] = nSlots;
  i32[2] = slotBytes;
  i32[3] = dataOff;
  return sab;
}

class SabView {
  i32: Int32Array;
  u8: Uint8Array;
  nSlots: number;
  slotBytes: number;
  dataOff: number;
  constructor(sab: SharedArrayBuffer) {
    const h = new Int32Array(sab, 0, HDR_INTS);
    if (h[0] !== MAGIC) throw new Error('bad SAB');
    this.nSlots = h[1];
    this.slotBytes = h[2];
    this.dataOff = h[3];
    this.i32 = new Int32Array(sab, 0, HDR_INTS + this.nSlots * 4);
    this.u8 = new Uint8Array(sab);
  }
  ci(slot: number): number {
    return HDR_INTS + slot * 4;
  }
}

export interface Poster {
  postMessage(msg: unknown): void;
}

/** エンジン側 (同期) */
export class SabClient {
  private v: SabView;
  /** idx -> slot (PENDING/READY で保持中) */
  private held = new Map<number, number>();
  private fetcher: Poster;
  constructor(sab: SharedArrayBuffer, fetcher: Poster) {
    this.fetcher = fetcher;
    this.v = new SabView(sab);
  }
  get nSlots(): number {
    return this.v.nSlots;
  }

  private freeSlot(): number {
    const { i32, nSlots } = this.v;
    for (let s = 0; s < nSlots; s++) if (Atomics.load(i32, this.v.ci(s)) === ST_FREE && ![...this.held.values()].includes(s)) return s;
    return -1;
  }

  /** 要求を発行 (既に held ならそのまま)。空きが無ければ false */
  request(idx: number): boolean {
    if (this.held.has(idx)) return true;
    const s = this.freeSlot();
    if (s < 0) return false;
    const c = this.v.ci(s);
    Atomics.store(this.v.i32, c + 1, idx);
    Atomics.store(this.v.i32, c + 2, 0);
    Atomics.store(this.v.i32, c + 3, 0);
    Atomics.store(this.v.i32, c, ST_PENDING);
    this.held.set(idx, s);
    this.fetcher.postMessage({ t: 'req', slot: s, idx });
    return true;
  }

  /** 空きスロット数 (先読み量の制限用) */
  freeCount(): number {
    return this.v.nSlots - this.held.size;
  }
  has(idx: number): boolean {
    return this.held.has(idx);
  }

  /** READY になった保持中スロットの idx 一覧 (非ブロッキング) */
  readyList(): number[] {
    const out: number[] = [];
    for (const [idx, s] of this.held) {
      const st = Atomics.load(this.v.i32, this.v.ci(s));
      if (st === ST_READY || st === ST_ERROR) out.push(idx);
    }
    return out;
  }

  /** idx の完了を待つ。戻りの view は release(idx) まで有効 (スラブ直参照, コピー無し) */
  wait(idx: number, timeoutMs = 60000): Uint8Array {
    const s = this.held.get(idx);
    if (s === undefined) throw new Error('chunk not requested');
    const c = this.v.ci(s);
    const t0 = Date.now();
    for (;;) {
      const st = Atomics.load(this.v.i32, c);
      if (st === ST_READY) {
        const len = Atomics.load(this.v.i32, c + 2);
        const off = this.v.dataOff + s * this.v.slotBytes;
        return this.v.u8.subarray(off, off + len);
      }
      if (st === ST_ERROR) {
        this.release(idx);
        throw new Error(`fetch failed for chunk ${idx} (code ${Atomics.load(this.v.i32, c + 3)})`);
      }
      const left = timeoutMs - (Date.now() - t0);
      if (left <= 0) throw new Error(`timeout waiting chunk ${idx}`);
      Atomics.wait(this.v.i32, c, ST_PENDING, Math.min(left, 1000));
    }
  }

  release(idx: number): void {
    const s = this.held.get(idx);
    if (s === undefined) return;
    this.held.delete(idx);
    Atomics.store(this.v.i32, this.v.ci(s), ST_FREE);
  }
}

/** fetcher 側 (非同期): 要求メッセージを処理して SAB に書く */
export class SabServer {
  private v: SabView;
  inflight = 0;
  maxInflight = 0;
  private source: ChunkSource;
  constructor(sab: SharedArrayBuffer, source: ChunkSource) {
    this.source = source;
    this.v = new SabView(sab);
  }
  handle(msg: { t: string; slot: number; idx: number }): void {
    if (msg.t !== 'req') return;
    const { slot, idx } = msg;
    const c = this.v.ci(slot);
    this.inflight++;
    this.maxInflight = Math.max(this.maxInflight, this.inflight);
    this.source
      .fetchChunk(idx)
      .then((data) => {
        if (data.length > this.v.slotBytes) throw new Error('chunk > slot');
        this.v.u8.set(data, this.v.dataOff + slot * this.v.slotBytes);
        Atomics.store(this.v.i32, c + 2, data.length);
        Atomics.store(this.v.i32, c, ST_READY);
        Atomics.notify(this.v.i32, c);
      })
      .catch((e) => {
        console.error('[fetcher]', e);
        Atomics.store(this.v.i32, c + 3, 1);
        Atomics.store(this.v.i32, c, ST_ERROR);
        Atomics.notify(this.v.i32, c);
      })
      .finally(() => {
        this.inflight--;
      });
  }
}
