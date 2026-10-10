// wvfs.ts — 書込可能 VFS の論理層: case-insensitive パスツリー + 同期 file API + flush 契約。
//
// - 物理層は journal.ts (OPFS / node の SyncFile 上のアペンドジャーナル)。読み出しはジャーナル直読みで
//   メモリには index のみ。open 中 fd の書込はメモリ buffer、close/flush 点でジャーナルに PUT する。
// - flush 契約 (vreg / pathreg RegBridge と同一インタフェース名): onYield() / onPageHide()。
//   ジャーナル append は flush しない → 明示 flush 点 (onYield / onPageHide / sync / fsync / close)
//   で物理 flush する。flush 点までにプロセスが死ぬと未 flush 分は失われる (契約どおり。pagehide が最終機会)。
// - 大文字小文字は比較時のみ無視 (Win32 相当)。エントリは元ケースのパスを保持し、readdir は元ケースを
//   返す (LazyVfs manifest tree の lookup 方針と同一)。
import { Journal, WvfsError, OP_PUT, OP_DEL, OP_MKDIR, OP_RMDIR, OP_RENAME, OP_TOUCH, type Rec, type WvfsBackend } from './journal.ts';

export { WvfsError } from './journal.ts';
export type { WvfsErrCode, WvfsBackend } from './journal.ts';
export { Journal } from './journal.ts';

export interface WvfsStat {
  type: 'file' | 'dir';
  size: number;
  mtime: number;
  /** 元ケースの名前 (最終セグメント) */
  name: string;
}

export interface WvfsOptions {
  /** 単一ファイル (ジャーナル 1 レコード) の上限。既定 128MiB */
  maxFileBytes?: number;
  /** close 時に物理 flush まで行うか (既定 true。false でも sync/onYield/onPageHide で flush) */
  flushOnClose?: boolean;
}

interface Ent {
  type: 'file' | 'dir';
  /** 元ケースの絶対パス ('/a/B/c.txt')。ジャーナル記録はこれを使う */
  path: string;
  mtime: number;
  /** file: ジャーナル内データ位置 */
  loc?: { off: number; len: number };
  /** 明示 mkdir された dir (暗黙 dir は最後のファイル削除で刈り込む) */
  explicit?: boolean;
  /** unlink 済み (open fd が close で書き戻すのを防ぐ) */
  dead?: boolean;
}

/** 同一パスの open fd 間で共有する書込状態 (MEMFS の node.contents 相当。相互に read-your-writes) */
interface Shared {
  lower: string;
  ent: Ent;
  buf: Uint8Array | null; // 最初の書込で全内容を materialize
  dirty: boolean;
  refs: number;
}

interface Fd {
  sh: Shared;
  append: boolean;
  pos: number;
}

export class Wvfs {
  private j: Journal;
  private o: { maxFileBytes: number; flushOnClose: boolean };
  /** lower(path) -> ent ('/' は持たない) */
  private ents = new Map<string, Ent>();
  private shared = new Map<string, Shared>();
  private fds = new Map<number, Fd>();
  private nextFd = 3;
  private enc = new TextEncoder();
  private dec = new TextDecoder();
  readonly stats = { files: 0, dirs: 0, flushes: 0, journalAppends: 0, tornRecovered: 0 };

  private constructor(j: Journal, o: WvfsOptions = {}) {
    this.j = j;
    this.o = { maxFileBytes: o.maxFileBytes ?? 128 * 2 ** 20, flushOnClose: o.flushOnClose ?? true };
  }

  /** boot: ジャーナル再生でツリー再構築 (torn tail は journal 側で検出済み) */
  static async open(backend: WvfsBackend, o?: WvfsOptions): Promise<Wvfs> {
    const j = await Journal.open(backend);
    const w = new Wvfs(j, o);
    j.replay((r, _seq, pos) => w.applyRec(r, pos)); // 単一の scan (tornTails はここで 1 度だけ計上)
    w.stats.tornRecovered = j.stats.tornTails;
    return w;
  }

  get journal(): Journal {
    return this.j;
  }

  // ---- パス正規化 (posix 風・'.' '..' 畳み。大小は key 化時のみ lower) ----
  private norm(p: string): string {
    if (typeof p !== 'string' || p === '') throw new WvfsError('EINVAL', 'empty path');
    const segs: string[] = [];
    for (const s of p.split('/')) {
      if (s === '' || s === '.') continue;
      if (s === '..') {
        if (segs.length === 0) throw new WvfsError('EINVAL', `.. beyond root: ${p}`);
        segs.pop();
        continue;
      }
      segs.push(s);
    }
    return '/' + segs.join('/');
  }

  private split(p: string): { dir: string; lower: string; path: string; name: string } {
    const n = this.norm(p);
    const i = n.lastIndexOf('/');
    return {
      dir: i === 0 ? '/' : n.slice(0, i),
      lower: n.toLowerCase(),
      path: n,
      name: n.slice(i + 1),
    };
  }

  /** 暗黙 dir (親チェーン) を用意する。途中が file なら ENOTDIR */
  private ensureDirs(dirPath: string): void {
    if (dirPath === '/') return;
    let cur = '';
    for (const seg of dirPath.slice(1).split('/')) {
      cur += '/' + seg;
      const lower = cur.toLowerCase();
      const e = this.ents.get(lower);
      if (!e) {
        this.ents.set(lower, { type: 'dir', path: cur, mtime: Date.now() });
        this.stats.dirs++;
      } else if (e.type !== 'dir') {
        throw new WvfsError('ENOTDIR', `${cur} is a file`);
      }
    }
  }

  /** 既存 parent チェック (open/mkdir/rename 用: 暗黙生成しない) */
  private requireParentDir(dirPath: string): void {
    if (dirPath === '/') return;
    const e = this.ents.get(dirPath.toLowerCase());
    if (!e) throw new WvfsError('ENOENT', `${dirPath}: parent not found`);
    if (e.type !== 'dir') throw new WvfsError('ENOTDIR', `${dirPath}: parent is a file`);
  }

  private childrenCount(dirLower: string): number {
    const prefix = dirLower === '/' ? '/' : dirLower + '/';
    let n = 0;
    for (const l of this.ents.keys()) {
      if (l.startsWith(prefix) && !l.slice(prefix.length).includes('/')) n++;
    }
    return n;
  }

  /** 子孫 (自分含む) をパス順 (= 親が先) で (dir rename 用) */
  private descendantsOf(lower: string): Array<{ lower: string; e: Ent }> {
    const out: Array<{ lower: string; e: Ent }> = [];
    const prefix = lower + '/';
    for (const [l, e] of this.ents) if (l === lower || l.startsWith(prefix)) out.push({ lower: l, e });
    out.sort((a, b) => (a.lower < b.lower ? -1 : a.lower > b.lower ? 1 : 0));
    return out;
  }

  private pruneEmptyImplicitDirs(dirLower: string): void {
    // ファイル削除の後片付け: 暗黙に出来た空 dir を刈る (明示 mkdir された dir は残す)
    let cur = dirLower;
    while (cur !== '/' && cur !== '') {
      const e = this.ents.get(cur);
      if (!e || e.type !== 'dir' || e.explicit || this.childrenCount(cur) > 0) return;
      this.ents.delete(cur);
      this.stats.dirs--;
      cur = cur.slice(0, cur.lastIndexOf('/')) || '/';
    }
  }

  // ---- ジャーナル適用 (replay と live 共通)。recPos = レコード開始位置 (live は journalNow が渡す) ----
  private applyRec(r: Rec, recPos?: number): void {
    const path = this.norm(r.path);
    const lower = path.toLowerCase();
    if (lower === '/') return; // ルート自体の操作は不可
    const dir = path.slice(0, path.lastIndexOf('/')) || '/';
    const name = path.slice(path.lastIndexOf('/') + 1);
    switch (r.op) {
      case OP_PUT: {
        this.ensureDirs(dir);
        const old = this.ents.get(lower);
        if (old?.type === 'dir') throw new WvfsError('EISDIR', `${path}: is a directory`);
        const loc = recPos === undefined ? old?.loc : { off: recPos + 27 + this.enc.encode(path).length, len: r.data?.length ?? 0 };
        if (old) {
          old.mtime = r.mtime;
          old.dead = false;
          if (loc) old.loc = loc;
        } else {
          this.ents.set(lower, { type: 'file', path, mtime: r.mtime, loc });
          this.stats.files++;
        }
        break;
      }
      case OP_DEL: {
        const e = this.ents.get(lower);
        if (e && e.type === 'file') {
          e.dead = true;
          this.ents.delete(lower);
          this.stats.files--;
          this.pruneEmptyImplicitDirs(dir.toLowerCase());
        }
        break;
      }
      case OP_MKDIR: {
        this.ensureDirs(dir);
        if (!this.ents.has(lower)) {
          this.ents.set(lower, { type: 'dir', path, mtime: r.mtime, explicit: true });
          this.stats.dirs++;
        }
        break;
      }
      case OP_RMDIR: {
        const e = this.ents.get(lower);
        if (e && e.type === 'dir' && this.childrenCount(lower) === 0) {
          this.ents.delete(lower);
          this.stats.dirs--;
        }
        break;
      }
      case OP_RENAME: {
        // data = 旧パス (元ケース)
        const fromPath = this.norm(r.data ? this.dec.decode(r.data) : '');
        const fromLower = fromPath.toLowerCase();
        const e = this.ents.get(fromLower);
        if (!e) break;
        this.ents.delete(fromLower);
        if (e.type === 'file') this.ensureDirs(dir);
        const tgt = this.ents.get(lower);
        if (tgt && tgt !== e) {
          if (tgt.type === 'dir') this.stats.dirs--;
          else this.stats.files--;
        }
        e.path = path;
        e.mtime = r.mtime;
        e.dead = false;
        this.ents.set(lower, e);
        break;
      }
      case OP_TOUCH: {
        const e = this.ents.get(lower);
        if (e) e.mtime = r.mtime;
        break;
      }
    }
  }

  /** live 操作のジャーナル追記 (flush しない)。レコード開始位置を返す */
  private journalNow(r: Rec): number {
    const pos = this.j.logicalEnd;
    this.j.append(r);
    this.stats.journalAppends++;
    return pos;
  }

  private liveBytes(): number {
    let n = 0;
    for (const e of this.ents.values()) if (e.type === 'file' && e.loc) n += e.loc.len;
    return n;
  }

  // ---- 参照系 (同期) ----
  statSync(p: string): WvfsStat | null {
    if (this.norm(p) === '/') return { type: 'dir', size: 0, mtime: 0, name: '' };
    const e = this.ents.get(this.split(p).lower);
    if (!e) return null;
    return { type: e.type, size: e.type === 'file' ? e.loc?.len ?? 0 : 0, mtime: e.mtime, name: e.path.slice(e.path.lastIndexOf('/') + 1) };
  }
  existsSync(p: string): boolean {
    return this.norm(p) === '/' || this.ents.has(this.split(p).lower);
  }
  isDirSync(p: string): boolean {
    return this.norm(p) === '/' || this.ents.get(this.split(p).lower)?.type === 'dir';
  }
  readdirSync(p: string): string[] {
    if (!this.isDirSync(p)) {
      throw new WvfsError(this.ents.has(this.split(p).lower) ? 'ENOTDIR' : 'ENOENT', p);
    }
    const lower = this.norm(p).toLowerCase();
    const prefix = lower === '/' ? '/' : lower + '/';
    const out: string[] = [];
    for (const [l, e] of this.ents) {
      if (!l.startsWith(prefix) || l.slice(prefix.length).includes('/')) continue;
      out.push(e.path.slice(e.path.lastIndexOf('/') + 1));
    }
    return out.sort((a, b) => (a.toLowerCase() < b.toLowerCase() ? -1 : 1));
  }

  readFileSync(p: string): Uint8Array {
    const { lower } = this.split(p);
    const e = this.ents.get(lower);
    if (!e) throw new WvfsError('ENOENT', p);
    if (e.type === 'dir') throw new WvfsError('EISDIR', p);
    const sh = this.shared.get(lower);
    if (sh?.dirty && sh.buf) return sh.buf.slice(); // dirty fd の read-your-writes
    if (!e.loc || e.loc.len === 0) return new Uint8Array(0);
    return this.j.readData(e.loc.off, e.loc.len);
  }

  // ---- 更新系 (同期) ----
  mkdirSync(p: string): void {
    const { dir, lower, path } = this.split(p);
    if (lower === '/') throw new WvfsError('EEXIST', `${p}: root exists`);
    this.requireParentDir(dir);
    if (this.ents.has(lower)) throw new WvfsError('EEXIST', p);
    this.applyRec({ op: OP_MKDIR, path, mtime: Date.now() }, undefined);
    this.journalNow({ op: OP_MKDIR, path, mtime: Date.now() });
  }

  /** 中間 dir をまとめて作る (mkdir -p)。既存は黙って通す。作った dir 数を返す */
  mkdirpSync(p: string): number {
    const n = this.norm(p);
    if (n === '/') return 0;
    let cur = '';
    let made = 0;
    for (const seg of n.slice(1).split('/')) {
      cur += '/' + seg;
      const e = this.ents.get(cur.toLowerCase());
      if (!e) {
        this.mkdirSync(cur);
        made++;
      } else if (e.type !== 'dir') {
        throw new WvfsError('ENOTDIR', cur);
      }
    }
    return made;
  }

  rmdirSync(p: string): void {
    const { lower, path } = this.split(p);
    const e = this.ents.get(lower);
    if (!e) throw new WvfsError('ENOENT', p);
    if (e.type !== 'dir') throw new WvfsError('ENOTDIR', p);
    if (lower === '/') throw new WvfsError('EINVAL', 'cannot rmdir root');
    if (this.childrenCount(lower) > 0) throw new WvfsError('ENOTEMPTY', p);
    this.applyRec({ op: OP_RMDIR, path, mtime: Date.now() }, undefined);
    this.journalNow({ op: OP_RMDIR, path, mtime: Date.now() });
  }

  unlinkSync(p: string): void {
    const { lower, path } = this.split(p);
    const e = this.ents.get(lower);
    if (!e) throw new WvfsError('ENOENT', p);
    if (e.type !== 'file') throw new WvfsError('EISDIR', p);
    this.applyRec({ op: OP_DEL, path, mtime: Date.now() }, undefined);
    this.journalNow({ op: OP_DEL, path, mtime: Date.now() });
  }

  renameSync(from: string, to: string): void {
    const f = this.split(from);
    const t = this.split(to);
    const fe = this.ents.get(f.lower);
    if (!fe) throw new WvfsError('ENOENT', from);
    if (t.lower === '/') throw new WvfsError('EINVAL', 'cannot rename to root');
    if (fe.type === 'dir' && (t.lower + '/').startsWith(f.lower + '/')) {
      throw new WvfsError('EINVAL', `cannot rename dir into itself: ${from} -> ${to}`);
    }
    this.requireParentDir(t.dir);
    const te = this.ents.get(t.lower);
    if (te && te.type === 'dir' && this.childrenCount(t.lower) > 0) throw new WvfsError('ENOTEMPTY', to);
    const now = Date.now();
    if (fe.type === 'dir') {
      const list = this.descendantsOf(f.lower);
      const newPathBase = this.norm(to);
      for (const { lower, e } of list) {
        const rest = lower === f.lower ? '' : e.path.slice(fe.path.length); // 元ケースの残り
        const newPath = rest === '' ? newPathBase : newPathBase + rest;
        this.applyRec({ op: OP_RENAME, path: newPath, mtime: now, data: this.enc.encode(e.path) }, undefined);
        this.journalNow({ op: OP_RENAME, path: newPath, mtime: now, data: this.enc.encode(e.path) });
      }
    } else {
      this.applyRec({ op: OP_RENAME, path: this.norm(to), mtime: now, data: this.enc.encode(fe.path) }, undefined);
      this.journalNow({ op: OP_RENAME, path: this.norm(to), mtime: now, data: this.enc.encode(fe.path) });
    }
  }

  writeFileSync(p: string, data: Uint8Array): void {
    const fd = this.openSync(p, { create: true, truncate: true });
    try {
      if (data.length) this.writeSync(fd, data);
    } finally {
      this.closeSync(fd);
    }
  }

  truncateSync(p: string, len: number): void {
    const { lower, path } = this.split(p);
    const e = this.ents.get(lower);
    if (!e) throw new WvfsError('ENOENT', p);
    if (e.type !== 'file') throw new WvfsError('EISDIR', p);
    const cur = this.readFileSync(p);
    const next = new Uint8Array(Math.max(0, len));
    next.set(cur.subarray(0, Math.min(cur.length, len)));
    const now = Date.now();
    const pos = this.journalNow({ op: OP_PUT, path, mtime: now, data: next });
    this.applyRec({ op: OP_PUT, path, mtime: now, data: next }, pos);
    const sh = this.shared.get(lower);
    if (sh) {
      sh.buf = next.slice(); // 開いたままの fd にも切詰め結果を見せる
      sh.dirty = false;
    }
  }

  utimesSync(p: string, mtimeMs: number): void {
    const { lower, path } = this.split(p);
    if (!this.ents.has(lower)) throw new WvfsError('ENOENT', p);
    this.applyRec({ op: OP_TOUCH, path, mtime: mtimeMs }, undefined);
    this.journalNow({ op: OP_TOUCH, path, mtime: mtimeMs });
  }

  // ---- fd I/O (Emscripten stream_ops / 直接 API 両方から使う) ----
  openSync(p: string, opts: { create?: boolean; truncate?: boolean; append?: boolean } = {}): number {
    const { dir, lower, path } = this.split(p);
    if (lower === '/') throw new WvfsError('EISDIR', p);
    let e = this.ents.get(lower);
    if (!e) {
      if (!opts.create) throw new WvfsError('ENOENT', p);
      this.requireParentDir(dir);
      const now = Date.now();
      const pos = this.journalNow({ op: OP_PUT, path, mtime: now, data: new Uint8Array(0) });
      this.applyRec({ op: OP_PUT, path, mtime: now, data: new Uint8Array(0) }, pos);
      e = this.ents.get(lower)!;
    } else if (e.type === 'dir') {
      throw new WvfsError('EISDIR', p);
    } else if (opts.truncate) {
      this.truncateSync(p, 0);
    }
    // 同一パスの既存 open があればその shared state を使い回す (相互に書き味が見える)
    let sh = this.shared.get(lower);
    if (!sh || sh.ent !== e) {
      sh = { lower, ent: e, buf: null, dirty: false, refs: 0 };
      this.shared.set(lower, sh);
    }
    sh.refs++;
    const fd: Fd = { sh, append: !!opts.append, pos: 0 };
    const id = this.nextFd++;
    this.fds.set(id, fd);
    return id;
  }

  closeSync(fd: number): void {
    const f = this.getFd(fd);
    const sh = f.sh;
    sh.refs--;
    if (sh.refs <= 0) {
      if (sh.dirty && !sh.ent.dead) this.putShared(sh);
      this.shared.delete(sh.lower);
    }
    this.fds.delete(fd);
  }

  fstatSync(fd: number): { size: number; mtime: number } {
    const f = this.getFd(fd);
    return { size: this.fdSize(f), mtime: f.sh.ent.mtime };
  }

  seekSync(fd: number, pos: number): void {
    this.getFd(fd).pos = pos;
  }

  readSync(fd: number, dst: Uint8Array, dstOff = 0, len = dst.length - dstOff, pos?: number): number {
    const f = this.getFd(fd);
    const at = pos ?? f.pos;
    if (!Number.isInteger(at) || at < 0) throw new WvfsError('EINVAL', `bad read offset ${at}`);
    const total = Math.min(len, Math.max(0, this.fdSize(f) - at));
    if (total <= 0) return 0;
    if (f.sh.buf) {
      dst.set(f.sh.buf.subarray(at, at + total), dstOff);
    } else if (f.sh.ent.loc) {
      this.j.readInto(f.sh.ent.loc.off + at, dst.subarray(dstOff, dstOff + total));
    } else {
      return 0;
    }
    if (pos === undefined) f.pos = at + total;
    return total;
  }

  writeSync(fd: number, src: Uint8Array, srcOff = 0, len = src.length - srcOff, pos?: number): number {
    const f = this.getFd(fd);
    if (f.sh.ent.dead) return len; // unlink 済み fd への書込は捨てる (POSIX 風。close で書き戻さない)
    const at = pos ?? (f.append ? this.fdSize(f) : f.pos);
    if (!Number.isInteger(at) || at < 0) throw new WvfsError('EINVAL', `bad write offset ${at}`);
    if (len <= 0) return 0;
    if (at + len > this.o.maxFileBytes) throw new WvfsError('EFBIG', `write exceeds ${this.o.maxFileBytes}B cap (at=${at} len=${len})`);
    if (!f.sh.buf) {
      const loc = f.sh.ent.loc;
      f.sh.buf = loc && loc.len > 0 ? this.j.readData(loc.off, loc.len) : new Uint8Array(0);
    }
    if (at + len > f.sh.buf.length) {
      const grown = new Uint8Array(at + len);
      grown.set(f.sh.buf);
      f.sh.buf = grown;
    }
    f.sh.buf.set(src.subarray(srcOff, srcOff + len), at);
    f.sh.dirty = true;
    f.sh.ent.mtime = Date.now();
    if (pos === undefined) f.pos = at + len;
    return len;
  }

  ftruncateSync(fd: number, len: number): void {
    const f = this.getFd(fd);
    if (!Number.isInteger(len) || len < 0) throw new WvfsError('EINVAL', `bad ftruncate len ${len}`);
    if (!f.sh.buf) {
      const loc = f.sh.ent.loc;
      f.sh.buf = loc && loc.len > 0 ? this.j.readData(loc.off, loc.len) : new Uint8Array(0);
    }
    const next = new Uint8Array(len);
    next.set(f.sh.buf.subarray(0, Math.min(f.sh.buf.length, len)));
    f.sh.buf = next;
    f.sh.dirty = true;
    if (f.pos > len) f.pos = len;
  }

  /** fsync(fd) 相当: このファイルをジャーナルへ置いて物理 flush まで行う */
  fsyncSync(fd: number): void {
    const f = this.getFd(fd);
    if (f.sh.dirty && !f.sh.ent.dead) {
      this.putShared(f.sh);
      this.j.flush();
      this.stats.flushes++;
    }
  }

  private getFd(fd: number): Fd {
    const f = this.fds.get(fd);
    if (!f) throw new WvfsError('EBADF', String(fd));
    return f;
  }

  private fdSize(f: Fd): number {
    if (f.sh.buf) return f.sh.buf.length;
    return f.sh.ent.loc?.len ?? 0;
  }

  /** shared 状態をジャーナルへ PUT (fd は開いたまま。物理 flush はしない = flush 点契約) */
  private putShared(sh: Shared): void {
    const now = Date.now();
    const pos = this.journalNow({ op: OP_PUT, path: sh.ent.path, mtime: now, data: sh.buf ?? new Uint8Array(0) });
    this.applyRec({ op: OP_PUT, path: sh.ent.path, mtime: now, data: sh.buf ?? new Uint8Array(0) }, pos);
    sh.dirty = false;
  }

  // ---- flush 契約 (vreg / pathreg RegBridge と同一インタフェース名) ----

  /** dirty fd を全部ジャーナルへ (物理 flush はまとめて) */
  flushDirty(): void {
    for (const sh of this.shared.values()) if (sh.dirty && !sh.ent.dead) this.putShared(sh);
  }

  /** FS.syncfs 相当。dirty fd → ジャーナル → 物理 flush */
  sync(): void {
    this.flushDirty();
    this.j.flush();
    this.stats.flushes++;
  }

  /** メッセージポンプの yield 点。dirty かつ/または compaction 要なら Promise を返す (待たなくても良い) */
  onYield(): Promise<void> | undefined {
    if (this.dirtyCount() === 0 && !this.j.shouldCompact(this.liveBytes())) return undefined;
    this.sync();
    return this.maybeCompact();
  }

  /** pagehide / visibilitychange(vhidden) 発火口。最終保存機会 (強制 flush) */
  onPageHide(): void {
    this.sync();
  }

  private dirtyCount(): number {
    let n = 0;
    for (const sh of this.shared.values()) if (sh.dirty && !sh.ent.dead) n++;
    return n;
  }

  /** ジャーナルが膨らんでいたら生存レコードだけで作り直す */
  async maybeCompact(): Promise<void> {
    if (!this.j.shouldCompact(this.liveBytes())) return;
    await this.compactNow();
  }

  /** 明示 compaction (生存エントリのみの新ジャーナルへ作り直し + スーパーブロック差し替え) */
  async compactNow(): Promise<{ before: number; after: number }> {
    this.flushDirty();
    const now = Date.now();
    const dirs: Rec[] = [];
    const files: Rec[] = [];
    for (const e of this.ents.values()) {
      if (e.type === 'dir') {
        if (e.explicit) dirs.push({ op: OP_MKDIR, path: e.path, mtime: e.mtime });
      } else {
        const data = e.loc && e.loc.len > 0 ? this.j.readData(e.loc.off, e.loc.len) : new Uint8Array(0);
        files.push({ op: OP_PUT, path: e.path, mtime: e.mtime || now, data });
      }
    }
    const before = this.j.logicalEnd;
    const locs = await this.j.compact([...dirs, ...files]);
    for (const [path, loc] of locs) {
      const e = this.ents.get(path.toLowerCase());
      if (e && e.type === 'file') e.loc = loc;
    }
    return { before, after: this.j.logicalEnd };
  }

  /** graceful shutdown: flush + 物理層 close (冪等) */
  private closedFlag = false;
  async close(): Promise<void> {
    if (this.closedFlag) return;
    this.closedFlag = true;
    this.flushDirty();
    if (this.o.flushOnClose) this.j.flush();
    await this.j.close();
  }

  /** デバッグ: 生の状態 */
  debugState(): { journalId: number; journalBytes: number; liveBytes: number; files: number; dirs: number; fds: number } {
    return {
      journalId: this.j.journalId,
      journalBytes: this.j.logicalEnd,
      liveBytes: this.liveBytes(),
      files: this.stats.files,
      dirs: this.stats.dirs,
      fds: this.fds.size,
    };
  }
}
