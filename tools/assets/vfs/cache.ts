import type { SyncFile } from './types.ts';

/** 非圧縮 chunk の永続/揮発キャッシュ。キーは chunk id (内容ハッシュ)。 */
export interface ChunkCache {
  has(id: string): boolean;
  /** chunk 内 [co, co+len) を dst[dstOff..] へ。miss なら false */
  readRange(id: string, co: number, dst: Uint8Array, dstOff: number, len: number): boolean;
  put(id: string, data: Uint8Array): void;
  /** eviction 対象外に指定 (ブートセット等)。置換え指定 */
  setPinned(ids: Iterable<string>): void;
  flush(): void;
  close(): void;
  readonly stats: { slots: number; used: number; evictions: number; kind: string };
}

const HDR = 4096; // 先頭ページ = header (データは 4KiB 境界)
const MAGIC = 0x43534c46; // 'FLSC'
const VERSION = 1;

function hexToBytes(h: string): Uint8Array {
  const b = new Uint8Array(h.length / 2);
  for (let i = 0; i < b.length; i++) b[i] = parseInt(h.substr(i * 2, 2), 16);
  return b;
}
function bytesToHex(b: Uint8Array): string {
  let s = '';
  for (const x of b) s += x.toString(16).padStart(2, '0');
  return s;
}
/** 64 箇所 x 64B の fnv1a (torn write 検出用の安価なサンプリング checksum) */
function quickSum(d: Uint8Array): number {
  let h = 0x811c9dc5 ^ d.length;
  const step = Math.max(64, Math.floor(d.length / 64));
  for (let o = 0; o < d.length; o += step) {
    const e = Math.min(d.length, o + 64);
    for (let i = o; i < e; i++) h = Math.imul(h ^ d[i], 16777619);
  }
  return h >>> 0;
}

/**
 * 固定スロット LRU キャッシュ (単一 SyncFile: OPFS SyncAccessHandle / node fd)。
 * - 自己記述: 各スロット先頭 4KiB に [magic,ver,id16,len,sum,valid] → 再起動時にスキャンで index 復元 (別 index ファイル不要)
 * - 書込順: データ -> header(valid=1) の順で torn write を無効化
 * - eviction: LRU (Map 挿入順) / pinned は対象外 (pin だけで満杯なら put は失敗せず非 pin を探し、無ければ上書き不可で skip)
 */
export class SlotCache implements ChunkCache {
  private file: SyncFile;
  readonly slotBytes: number;
  private maxSlots: number;
  private map = new Map<string, { slot: number; len: number }>(); // 挿入順 = LRU (先頭が最古)
  private slotId: (string | null)[] = [];
  private free: number[] = [];
  private pinned = new Set<string>();
  private hdr = new Uint8Array(48);
  private hv = new DataView(this.hdr.buffer);
  stats = { slots: 0, used: 0, evictions: 0, kind: 'slot' };
  scanned = 0;

  constructor(file: SyncFile, chunkSize: number, maxSlots: number) {
    this.file = file;
    this.slotBytes = HDR + chunkSize;
    this.maxSlots = maxSlots;
    this.scan();
  }

  private scan(): void {
    const n = Math.min(this.maxSlots, Math.floor(this.file.getSize() / this.slotBytes));
    for (let s = 0; s < n; s++) {
      this.slotId[s] = null;
      this.file.read(this.hdr, s * this.slotBytes);
      const ok = this.hv.getUint32(0, true) === MAGIC && this.hv.getUint32(4, true) === VERSION && this.hv.getUint32(32, true) === 1;
      if (!ok) {
        this.free.push(s);
        continue;
      }
      const id = bytesToHex(this.hdr.subarray(8, 24));
      const len = this.hv.getUint32(24, true);
      if (len > this.slotBytes - HDR || this.map.has(id)) {
        this.free.push(s);
        continue;
      }
      this.map.set(id, { slot: s, len });
      this.slotId[s] = id;
      this.scanned++;
    }
    this.stats.slots = n;
    this.stats.used = this.map.size;
  }

  has(id: string): boolean {
    return this.map.has(id);
  }

  readRange(id: string, co: number, dst: Uint8Array, dstOff: number, len: number): boolean {
    const e = this.map.get(id);
    if (!e) return false;
    if (co + len > e.len) return false;
    this.map.delete(id); // LRU touch
    this.map.set(id, e);
    const n = this.file.read(dst.subarray(dstOff, dstOff + len), e.slot * this.slotBytes + HDR + co);
    return n === len;
  }

  put(id: string, data: Uint8Array): void {
    if (this.map.has(id)) return;
    if (data.length > this.slotBytes - HDR) throw new Error('chunk larger than slot');
    let slot = this.free.pop();
    if (slot === undefined) {
      if (this.stats.slots < this.maxSlots) slot = this.stats.slots++;
      else {
        for (const [k, v] of this.map) {
          if (this.pinned.has(k)) continue;
          this.map.delete(k);
          this.slotId[v.slot] = null;
          // 旧 header を無効化してから再利用 (クラッシュ時に古い id + 新データの不整合を避ける)
          this.hv.setUint32(32, 0, true);
          this.file.write(this.hdr.subarray(0, 48), v.slot * this.slotBytes);
          slot = v.slot;
          this.stats.evictions++;
          break;
        }
        if (slot === undefined) return; // 全 slot pinned: キャッシュしない
      }
    }
    const base = slot * this.slotBytes;
    this.file.write(data, base + HDR);
    this.hv.setUint32(0, MAGIC, true);
    this.hv.setUint32(4, VERSION, true);
    this.hdr.set(hexToBytes(id), 8);
    this.hv.setUint32(24, data.length, true);
    this.hv.setUint32(28, quickSum(data), true);
    this.hv.setUint32(32, 1, true);
    this.file.write(this.hdr, base);
    this.map.set(id, { slot, len: data.length });
    this.slotId[slot] = id;
    this.stats.used = this.map.size;
  }

  setPinned(ids: Iterable<string>): void {
    this.pinned = new Set(ids);
  }

  /** 全 slot の checksum を検証し不整合を解放 (起動時 opt-in / テスト用) */
  verifyAll(): number {
    let bad = 0;
    for (const [id, e] of [...this.map]) {
      const buf = new Uint8Array(e.len);
      this.file.read(buf, e.slot * this.slotBytes + HDR);
      this.file.read(this.hdr, e.slot * this.slotBytes);
      if (quickSum(buf) !== this.hv.getUint32(28, true)) {
        this.map.delete(id);
        this.free.push(e.slot);
        bad++;
      }
    }
    return bad;
  }

  flush(): void {
    this.file.flush();
  }
  close(): void {
    this.file.flush();
    this.file.close();
  }
}

/** 揮発キャッシュ (OPFS 不可/別タブが占有中のフォールバック, node テスト)。 */
export class MemCache implements ChunkCache {
  private map = new Map<string, Uint8Array>();
  private pinned = new Set<string>();
  private bytes = 0;
  stats = { slots: 0, used: 0, evictions: 0, kind: 'mem' };
  private maxBytes: number;
  constructor(maxBytes: number) {
    this.maxBytes = maxBytes;
    this.stats.slots = Infinity;
  }
  has(id: string) {
    return this.map.has(id);
  }
  readRange(id: string, co: number, dst: Uint8Array, dstOff: number, len: number): boolean {
    const d = this.map.get(id);
    if (!d || co + len > d.length) return false;
    this.map.delete(id);
    this.map.set(id, d);
    dst.set(d.subarray(co, co + len), dstOff);
    return true;
  }
  put(id: string, data: Uint8Array): void {
    if (this.map.has(id)) return;
    this.map.set(id, data.slice());
    this.bytes += data.length;
    for (const [k, v] of this.map) {
      if (this.bytes <= this.maxBytes) break;
      if (this.pinned.has(k) || k === id) continue;
      this.map.delete(k);
      this.bytes -= v.length;
      this.stats.evictions++;
    }
    this.stats.used = this.map.size;
  }
  setPinned(ids: Iterable<string>) {
    this.pinned = new Set(ids);
  }
  flush() {}
  close() {
    this.map.clear();
  }
}
