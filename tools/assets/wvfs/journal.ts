// journal.ts — 書込可能 VFS の物理層: SyncFile (OPFS SyncAccessHandle / node fd) 上の
// アペンドジャーナル型ストア + A/B スーパーブロック。
//
// torn-write 安全設計 (CAB-21 の OPFS 実装規約「データを先に書き、commit を後に書く」を踏襲):
//  - 1 レコード = [recLen][crc][seq][op][pathLen][dataLen][mtime][path][data]。
//    先に write() してから flush() する。flush 前に死んでも (torn tail) 再生時に
//    recLen/crc 検証で最終不完全レコードを検出して捨てる → 既コミット state は常に無傷。
//  - スーパーブロック (root ファイル) は 2 スロット A/B。ジャーナル切替 (compaction) は
//    「新ジャーナルを書き切って flush してから」スロット 1 本 (4KiB 中 2KiB) を差し替える。
//    スロット書込中の torn write は他方のスロットが残るので起動時に gen 最大の正当スロットを選ぶ。
//  - 既存 LazyVfs (vfs/cache.ts SlotCache の 4KiB header + 固定配置) とは別ファイル系統で共存。
//
// 読み出しはジャーナル直読み (SyncAccessHandle の同期 read)。メモリには index のみ保持する。
import type { SyncFile } from '../vfs/types.ts';

export type WvfsErrCode =
  | 'ENOENT' | 'EEXIST' | 'EISDIR' | 'ENOTDIR' | 'ENOTEMPTY' | 'EBADF'
  | 'EIO' | 'ENOSPC' | 'EBUSY' | 'EINVAL' | 'EFBIG' | 'EPERM';

export class WvfsError extends Error {
  code: WvfsErrCode;
  constructor(code: WvfsErrCode, msg: string) {
    super(`${code}: ${msg}`);
    this.code = code;
  }
}

/** DOMException / node エラーを WvfsError へ (quota 限界は ENOSPC, 単一 writer 違反は EBUSY) */
export function mapFsError(e: unknown, what: string): WvfsError {
  const name = (e as { name?: string })?.name ?? '';
  if (name === 'QuotaExceededError') return new WvfsError('ENOSPC', `${what}: storage quota exceeded`);
  if (name === 'NoModificationAllowedError') return new WvfsError('EBUSY', `${what}: file locked by another context`);
  if (name === 'NotFoundError') return new WvfsError('ENOENT', `${what}: not found`);
  const c = (e as { code?: string })?.code ?? '';
  if (c === 'ENOSPC' || c === 'EDQUOT') return new WvfsError('ENOSPC', `${what}: no space`);
  return new WvfsError('EIO', `${what}: ${String((e as Error)?.message ?? e)}`);
}

/** マウント先の物理ファイルを開く/消す抽象 (OPFS / node fs を差し替え可能にする) */
export interface WvfsBackend {
  /** create: 無ければ作る。truncate: 開くとき空にする */
  open(name: string, opts?: { create?: boolean; truncate?: boolean }): Promise<SyncFile>;
  remove(name: string): Promise<void>;
  exists(name: string): Promise<boolean>;
}

// ---- レコード形式 ----
export const OP_PUT = 1;
export const OP_DEL = 2;
export const OP_MKDIR = 3;
export const OP_RMDIR = 4;
export const OP_RENAME = 5; // data = 旧パス (utf8)
export const OP_TOUCH = 6;

export interface Rec {
  op: number;
  path: string;
  mtime: number;
  data?: Uint8Array | null;
}

const JHDR = 4096;          // ジャーナルヘッダ (1 ページ)
const SB_SIZE = 4096;       // スーパーブロックファイル (2 スロット x 2048)
const SLOT = 2048;
const REC_HEAD = 27;        // recLen(4) crc(4) seq(4) op(1) pathLen(2) dataLen(4) mtime(8)
const MAX_REC = 256 * 2 ** 20 + REC_HEAD; // 単一レコード上限 (= 単一ファイル上限)

const MAGIC_J = [0x57, 0x56, 0x4a, 0x31]; // 'WVJ1'
const MAGIC_S = [0x57, 0x56, 0x53, 0x31]; // 'WVS1'

// ---- crc32 (レコード/ヘッダ完全性) ----
const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();
export function crc32(d: Uint8Array, off = 0, end = d.length): number {
  let c = 0xffffffff;
  for (let i = off; i < end; i++) c = CRC_TABLE[(c ^ d[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function jname(id: number): string {
  return `jrn-${id}.bin`;
}

function encodeRec(seq: number, r: Rec): Uint8Array {
  const pathB = new TextEncoder().encode(r.path);
  if (pathB.length > 0xffff) throw new WvfsError('EINVAL', `path too long: ${r.path}`);
  const data = r.data ?? null;
  if (data && data.length > MAX_REC - REC_HEAD - pathB.length) {
    throw new WvfsError('EFBIG', `${r.path}: record too large (${data.length}B > ${MAX_REC}B cap)`);
  }
  const recLen = REC_HEAD + pathB.length + (data ? data.length : 0);
  const buf = new Uint8Array(recLen);
  const v = new DataView(buf.buffer);
  v.setUint32(0, recLen, true);
  v.setUint32(8, seq >>> 0, true);
  buf[12] = r.op;
  v.setUint16(13, pathB.length, true);
  v.setUint32(15, data ? data.length : 0, true);
  v.setFloat64(19, r.mtime, true);
  buf.set(pathB, 27);
  if (data) buf.set(data, 27 + pathB.length);
  v.setUint32(4, crc32(buf, 8, recLen), true);
  return buf;
}

export interface JournalStats {
  journalId: number;
  journalBytes: number;
  seq: number;
  tornTails: number;
  anomalies: number;
  compactions: number;
}

export class Journal {
  private sb: SyncFile;
  private file: SyncFile | null = null;
  private backend: WvfsBackend;
  private activeSlot = 1; // 初回 commit は slot 0 に書く
  private gen = 0;
  private seqN = 0;
  private _journalId = 1;
  /** flush 済み物理長 (デバッグ/検証用) */
  readonly stats: JournalStats = { journalId: 1, journalBytes: JHDR, seq: 0, tornTails: 0, anomalies: 0, compactions: 0 };

  private constructor(backend: WvfsBackend, sb: SyncFile) {
    this.backend = backend;
    this.sb = sb;
  }

  /** boot: スーパーブロック解釈 → (caller が) ジャーナル再生。torn tail は再生時に捨てる */
  static async open(backend: WvfsBackend): Promise<Journal> {
    const sb = await backend.open('root', { create: true }).catch((e) => { throw mapFsError(e, 'root'); });
    if (sb.getSize() < SB_SIZE) {
      sb.truncate(SB_SIZE); // 2 スロット分をゼロで確保 (slot 1 の存在判定をサイズで行うため)
      sb.flush();
    }
    const j = new Journal(backend, sb);
    const slots = j.readSlots();
    const maxGen = Math.max(0, ...slots.all.filter((s) => s.valid).map((s) => s.gen));
    let needCommit = false;
    if (slots.best) {
      j.gen = slots.best.gen;
      j._journalId = slots.best.journalId;
      j.activeSlot = slots.best.slot;
      // compaction で旧ジャーナルが消えた後、fallback 先が「削除済み journalId」を
      // 指す場合がある → 実在する方へ落ちる (どちらも無ければ空で作り直す)
      if (!(await backend.exists(jname(j._journalId)))) {
        const candidates = slots.all.filter((s) => s.slot !== slots.best!.slot && s.valid);
        let other: { gen: number; journalId: number; slot: number; valid: boolean } | undefined;
        for (const c of candidates) {
          if (await backend.exists(jname(c.journalId))) { other = c; break; }
        }
        if (other) {
          j.gen = other.gen;
          j._journalId = other.journalId;
          j.activeSlot = other.slot;
        } else {
          j.gen = maxGen; // journalId は維持し、空ジャーナルで再出発
        }
        needCommit = true; // slot 状態を今の解像に揃える
      }
    } else {
      needCommit = true; // 新規 store
    }
    j.file = await backend.open(jname(j._journalId), { create: true });
    const size0 = j.file.getSize();
    if (!j.checkJournalHeader()) {
      if (slots.best || size0 > 0) j.stats.anomalies++; // ヘッダ壊れで再生できない中身があった
      j.file.truncate(0);
      j.writeJournalHeader();
      j.logicalEnd = JHDR;
    }
    j.stats.journalId = j._journalId;
    j.stats.journalBytes = j.file.getSize();
    if (needCommit) j.commitSuperblock(); // 新規 store / fallback 後の整合
    return j;
  }

  get journalId(): number {
    return this._journalId;
  }
  /** 論理終端 = 最後の正当レコードの末尾 (torn tail は含まない)。追記はここから上書きする */
  get logicalEnd(): number {
    return this._end;
  }
  private set logicalEnd(v: number) {
    this._end = v;
  }
  private _end = JHDR;

  // ---- スーパーブロック ----
  private readSlots(): { best: { gen: number; journalId: number; slot: number } | null; all: Array<{ gen: number; journalId: number; slot: number; valid: boolean }> } {
    const head = new Uint8Array(20);
    const all: Array<{ gen: number; journalId: number; slot: number; valid: boolean }> = [];
    let best: { gen: number; journalId: number; slot: number } | null = null;
    for (const slot of [0, 1]) {
      if (this.sb.getSize() < (slot + 1) * SLOT) break;
      this.sb.read(head, slot * SLOT);
      const v = new DataView(head.buffer);
      let magicOk = true;
      for (let i = 0; i < 4; i++) if (head[i] !== MAGIC_S[i]) magicOk = false;
      const valid = magicOk && v.getUint32(4, true) === 1 && v.getUint32(16, true) === crc32(head, 0, 16);
      if (!valid) {
        all.push({ gen: 0, journalId: 0, slot, valid: false });
        continue;
      }
      const gen = v.getUint32(8, true);
      const s = { gen, journalId: v.getUint32(12, true), slot, valid: true };
      all.push(s);
      if (!best || gen > best.gen) best = { gen, journalId: s.journalId, slot };
    }
    return { best, all };
  }

  private commitSuperblock(): void {
    const gen = this.gen + 1;
    const buf = new Uint8Array(20);
    const v = new DataView(buf.buffer);
    buf.set(MAGIC_S, 0);
    v.setUint32(4, 1, true);
    v.setUint32(8, gen, true);
    v.setUint32(12, this._journalId, true);
    v.setUint32(16, crc32(buf, 0, 16), true);
    const slot = 1 - this.activeSlot;
    this.sb.write(buf, slot * SLOT);
    this.sb.flush();
    this.activeSlot = slot;
    this.gen = gen;
  }

  private writeJournalHeader(): void {
    const buf = new Uint8Array(JHDR);
    buf.set(MAGIC_J, 0);
    const v = new DataView(buf.buffer);
    v.setUint32(4, 1, true);
    v.setUint32(8, this._journalId, true);
    v.setUint32(12, JHDR, true);
    v.setUint32(4092, crc32(buf, 0, 4092), true);
    this.file!.write(buf, 0);
    this.file!.flush();
  }

  private checkJournalHeader(): boolean {
    if (this.file!.getSize() < JHDR) return false;
    const buf = new Uint8Array(JHDR);
    this.file!.read(buf, 0);
    for (let i = 0; i < 4; i++) if (buf[i] !== MAGIC_J[i]) return false;
    const v = new DataView(buf.buffer);
    if (v.getUint32(4, true) !== 1) return false;
    return v.getUint32(4092, true) === crc32(buf, 0, 4092);
  }

  // ---- 再生 ----
  /** 各レコードを順に cb へ (pos = レコード開始位置)。戻り: 論理終端 (最後の正当レコードの末尾) */
  replay(cb: ((r: Rec, seq: number, pos: number) => void) | null = null): number {
    const f = this.file!;
    const size = f.getSize();
    let pos = JHDR;
    const head = new Uint8Array(REC_HEAD);
    let torn = false;
    while (pos + REC_HEAD <= size) {
      f.read(head, pos);
      const v = new DataView(head.buffer);
      const recLen = v.getUint32(0, true);
      if (recLen < REC_HEAD || recLen > MAX_REC || pos + recLen > size) { torn = true; break; }
      const buf = new Uint8Array(recLen);
      buf.set(head.subarray(0, REC_HEAD));
      if (recLen > REC_HEAD) {
        const rest = buf.subarray(REC_HEAD);
        const n = f.read(rest, pos + REC_HEAD);
        if (n !== rest.length) { torn = true; break; }
      }
      if (v.getUint32(4, true) !== crc32(buf, 8, recLen)) { torn = true; break; }
      const pathLen = v.getUint16(13, true);
      const dataLen = v.getUint32(15, true);
      const op = v.getUint8(12);
      if (27 + pathLen + dataLen !== recLen || op < 1 || op > 6) { torn = true; break; }
      const path = new TextDecoder().decode(buf.subarray(27, 27 + pathLen));
      const data = dataLen > 0 ? buf.slice(27 + pathLen) : null;
      const seq = v.getUint32(8, true);
      cb?.({ op, path, mtime: v.getFloat64(19, true), data }, seq, pos);
      if (seq >= this.seqN) this.seqN = seq + 1;
      pos += recLen;
    }
    if (torn) this.stats.tornTails++;
    this.logicalEnd = pos;
    this.stats.journalBytes = size;
    return pos;
  }

  // ---- 追記 ----
  /** レコードを追記する (flush はしない。sync()/flush() の flush 点契約)。書いたバイト数を返す */
  append(r: Rec): number {
    const buf = encodeRec(this.seqN, r);
    const f = this.file!;
    let n: number;
    try {
      n = f.write(buf, this.logicalEnd);
    } catch (e) {
      throw mapFsError(e, `journal append (${r.path})`);
    }
    if (n !== buf.length) throw new WvfsError('EIO', `journal short write (${n}/${buf.length}) at ${this.logicalEnd}`);
    this.seqN++;
    this.logicalEnd += n;
    this.stats.seq = this.seqN;
    this.stats.journalBytes = this.logicalEnd;
    return n;
  }

  /** 物理 flush (FS.syncfs 相当の本体)。既に flush 済みなら安価 */
  flush(): void {
    try {
      this.file!.flush();
    } catch (e) {
      throw mapFsError(e, 'journal flush');
    }
  }

  /** ジャーナルに載っているデータを dst へ同期読み出しする。読めたバイト数を返す */
  readInto(off: number, dst: Uint8Array): number {
    if (dst.length === 0) return 0;
    const n = this.file!.read(dst, off);
    if (n !== dst.length) throw new WvfsError('EIO', `journal short read (${n}/${dst.length}) at ${off}`);
    return n;
  }

  /** ジャーナルに載っているデータを同期読み出しする */
  readData(off: number, len: number): Uint8Array {
    const buf = new Uint8Array(len);
    this.readInto(off, buf);
    return buf;
  }

  /** 既定額を超えていたら compaction すべきか (liveBytes = 生存データ合計) */
  shouldCompact(liveBytes: number): boolean {
    const used = this.logicalEnd - JHDR;
    return used > Math.max(4 * 2 ** 20, 4 * liveBytes + 2 ** 20);
  }

  /** 生存レコードだけの新ジャーナルへ作り直し、スーパーブロックを差し替える (torn 安全順序)。
   *  戻り: path -> 新ジャーナル内のデータ位置 (live はユニークパス前提) */
  async compact(live: Rec[]): Promise<Map<string, { off: number; len: number }>> {
    const oldId = this._journalId;
    const newId = oldId + 1;
    const nf = await this.backend.open(jname(newId), { create: true, truncate: true });
    const prev = this.file;
    const prevEnd = this.logicalEnd;
    const prevSeq = this.seqN;
    this.file = nf;
    this._journalId = newId;
    this.logicalEnd = JHDR;
    const locs = new Map<string, { off: number; len: number }>();
    try {
      this.writeJournalHeader();
      this.logicalEnd = JHDR;
      const enc = new TextEncoder();
      for (const r of live) {
        const recStart = this.logicalEnd;
        this.append(r);
        locs.set(r.path, { off: recStart + REC_HEAD + enc.encode(r.path).length, len: r.data?.length ?? 0 });
      }
      this.flush();
    } catch (e) {
      // 失敗時は旧ジャーナルのまま (スーパーブロックは未更新)。新側は後片付け
      this.file = prev;
      this._journalId = oldId;
      this.logicalEnd = prevEnd;
      this.seqN = prevSeq;
      try { await nf.close(); } catch {}
      try { await this.backend.remove(jname(newId)); } catch {}
      throw e;
    }
    this.replay(); // 自検証: 新ジャーナルの論理終端を確定 (torn 無しのはず)
    try { prev!.close(); } catch { /* 既に閉じている等は無視 */ }
    this.commitSuperblock();
    // もう一方 (旧 journalId が残った) スロットも新ジャーナルへ差し替える。これで
    // 単一スロット破損の fallback が「削除済みの旧ジャーナル」を指さなくなる
    this.commitSuperblock();
    this.stats.compactions++;
    this.stats.journalId = newId;
    this.stats.journalBytes = this.logicalEnd;
    try { await this.backend.remove(jname(oldId)); } catch { /* 容量リーク (非致命) */ }
    return locs;
  }

  // ---- デバッグ / 検証用 (e2e の torn-write 注入) ----
  /** 論理終端以降に生バイトを書き散らす (logicalEnd は進めない = クラッシュ直後の torn tail を模す) */
  debugTornTail(bytes: number): void {
    const garbage = new Uint8Array(bytes);
    crypto.getRandomValues(garbage);
    garbage[0] = 0xff; garbage[1] = 0xff; garbage[2] = 0xff; garbage[3] = 0x7f; // 巨大 recLen に見える先頭
    this.file!.write(garbage, this.logicalEnd);
    this.file!.flush();
  }

  /** 現行 (active) スロットを壊す → 次回起動は他スロット (gen-1) で復旧するはず */
  debugCorruptActiveSlot(): void {
    const garbage = new Uint8Array(SLOT);
    crypto.getRandomValues(garbage);
    this.sb.write(garbage, this.activeSlot * SLOT);
    this.sb.flush();
  }

  private _closed = false;

  async close(): Promise<void> {
    if (this._closed) return; // 冪等 (二重 close でも no-op)
    this._closed = true;
    this.flush();
    if (this.file) {
      try { this.file.close(); } catch {}
      this.file = null;
    }
    try { this.sb.close(); } catch {}
  }
}
