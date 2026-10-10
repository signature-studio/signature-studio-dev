// emscripten-wvfs.ts — Wvfs を Emscripten FS へ mount できる書込可能ファイルシステムとして公開する。
// 読み取り専用の vfs/emscripten.ts (LazyVfs → /fl) と共存する (/fl は RO、/c/home・/c/tmp は本 FS)。
//
//   const home = await Wvfs.open(new OpfsBackend('fl-wvfs/home'));
//   FS.mkdir('/c/home'); FS.mount(createWvfsFs(FS, home), {}, '/c/home');
//
// FS.syncfs 対応: mount.type.syncfs(mount, populate, callback) を実装するので
//   FS.syncfs(false, cb) で全 wvfs mount を物理 flush できる (populate=true は既に読み込まれているため no-op)。
// opts.stores に全 Wvfs を渡すと syncfs がまとめて flush する (単一 mount なら省略可)。
//
// 大文字小文字: lookup を case-insensitive に解決する (Win32 相当。既存エントリの元ケースを優先)。
import type { Wvfs, WvfsStat } from './wvfs.ts';
import { WvfsError } from './wvfs.ts';

const DIR_MODE = 16895; // 040777
const FILE_MODE = 33204; // 0100644 (rw-r--r--)
const ENOENT = 44;
const EPERM = 63;
const EIO = 29;
const EISDIR = 31;
const ENOTDIR = 54;
const ENOTEMPTY = 55;
const EBADF = 8;
const EINVAL = 28;
const EEXIST = 17;
const EFBIG = 27;

const ERRNO: Record<string, number> = {
  ENOENT, EPERM, EIO, EISDIR, ENOTDIR, ENOTEMPTY, EBADF, EINVAL, EEXIST, EFBIG,
};

function errnoOf(e: unknown): number {
  if (e instanceof WvfsError) return ERRNO[e.code] ?? EIO;
  return EIO;
}

export interface WvfsFsOptions {
  /** syncfs で一緒に flush するストア群 (省略時は [wvfs]) */
  stores?: Wvfs[];
}

export function createWvfsFs(FS: any, wvfs: Wvfs, opts: WvfsFsOptions = {}): any {
  const join = (a: string, b: string) => (a === '/' || a === '' ? '/' + b : a + '/' + b);
  const err = (n: number) => new FS.ErrnoError(n);
  const throwW = (e: unknown): never => {
    throw err(errnoOf(e));
  };
  /** lookup 用: 大小無視で解決した vpath (存在すれば元ケース、無ければ要求ケース) */
  const resolve = (parentVpath: string, name: string): string => {
    const p = join(parentVpath, name);
    if (wvfs.existsSync(p)) {
      const st = wvfs.statSync(p)!;
      return join(parentVpath, st.name); // 元ケースへ正規化
    }
    return p;
  };
  const make = (parent: any, name: string, mode: number, vpath: string, st?: WvfsStat | null) => {
    const node = FS.createNode(parent, name, mode, 0);
    node.node_ops = node_ops;
    node.stream_ops = stream_ops;
    node.size = st ? (st.type === 'dir' ? 4096 : st.size) : (mode & 0o170000) === 0o040000 ? 4096 : 0;
    node.mtime = node.atime = node.ctime = st ? st.mtime || Date.now() : Date.now();
    node.vpath = vpath;
    return node;
  };

  const node_ops = {
    getattr(node: any) {
      return {
        dev: 1,
        ino: node.id,
        mode: node.mode,
        nlink: 1,
        uid: 0,
        gid: 0,
        rdev: 0,
        size: node.size,
        atime: new Date(node.atime),
        mtime: new Date(node.mtime),
        ctime: new Date(node.ctime),
        blksize: 4096,
        blocks: Math.ceil(node.size / 4096),
      };
    },
    setattr(node: any, attr: any) {
      try {
        if (attr.size !== undefined) {
          if (FS.isDir(node.mode)) throw err(EISDIR);
          wvfs.truncateSync(node.vpath, attr.size);
          node.size = attr.size;
        }
        const ts = attr.mtime ?? attr.timestamp;
        if (ts !== undefined) {
          const ms = ts instanceof Date ? ts.getTime() : Number(ts);
          if (Number.isFinite(ms)) {
            wvfs.utimesSync(node.vpath, ms);
            node.mtime = node.ctime = ms;
          }
        }
      } catch (e) {
        throwW(e);
      }
    },
    lookup(parent: any, name: string) {
      const vpath = resolve(parent.vpath, name);
      const st = wvfs.statSync(vpath);
      if (!st) throw err(ENOENT);
      return make(parent, name, st.type === 'dir' ? DIR_MODE : FILE_MODE, vpath, st);
    },
    mknod(parent: any, name: string, mode: number) {
      const vpath = join(parent.vpath, name);
      try {
        if (FS.isDir(mode)) {
          wvfs.mkdirSync(vpath);
        } else {
          wvfs.writeFileSync(vpath, new Uint8Array(0)); // create = 空ファイルを即ジャーナルへ
        }
      } catch (e) {
        throwW(e);
      }
      return make(parent, name, FS.isDir(mode) ? DIR_MODE : FILE_MODE, vpath, wvfs.statSync(vpath));
    },
    rename(oldNode: any, newDir: any, newName: string) {
      const to = join(newDir.vpath, newName);
      try {
        wvfs.renameSync(oldNode.vpath, to);
      } catch (e) {
        throwW(e);
      }
      oldNode.vpath = to;
      oldNode.name = newName; // FS 側 hash 再登録に追従
    },
    unlink(parent: any, name: string) {
      try {
        wvfs.unlinkSync(resolve(parent.vpath, name));
      } catch (e) {
        throwW(e);
      }
    },
    rmdir(parent: any, name: string) {
      try {
        wvfs.rmdirSync(resolve(parent.vpath, name));
      } catch (e) {
        throwW(e);
      }
    },
    symlink() {
      throw err(EPERM);
    },
    readdir(node: any) {
      try {
        return ['.', '..', ...wvfs.readdirSync(node.vpath)];
      } catch (e) {
        throwW(e);
      }
    },
  };

  const stream_ops = {
    open(stream: any) {
      if (FS.isDir(stream.node.mode)) return;
      try {
        // FS.core が O_CREAT/O_TRUNC を処理済み (mknod / truncate)。append のみここで受ける
        stream.wfd = wvfs.openSync(stream.node.vpath, { append: !!(stream.flags & 1024) });
        stream.node.size = wvfs.fstatSync(stream.wfd).size;
      } catch (e) {
        throwW(e);
      }
    },
    close(stream: any) {
      if (stream.wfd === undefined) return;
      const wfd = stream.wfd;
      stream.wfd = undefined;
      try {
        wvfs.closeSync(wfd);
        const st = wvfs.statSync(stream.node.vpath);
        if (st && st.type === 'file') stream.node.size = st.size;
      } catch (e) {
        throwW(e);
      }
    },
    fsync(stream: any) {
      try {
        wvfs.fsyncSync(stream.wfd);
      } catch (e) {
        throwW(e);
      }
    },
    read(stream: any, buffer: Uint8Array, offset: number, length: number, position: number) {
      try {
        return wvfs.readSync(stream.wfd, buffer, offset, length, position);
      } catch (e) {
        throwW(e);
      }
    },
    write(stream: any, buffer: Uint8Array, offset: number, length: number, position: number) {
      try {
        const n = wvfs.writeSync(stream.wfd, buffer, offset, length, position);
        stream.node.size = Math.max(stream.node.size, (position ?? 0) + n);
        return n;
      } catch (e) {
        throwW(e);
      }
    },
    llseek(stream: any, offset: number, whence: number) {
      let pos = offset;
      if (whence === 1) pos += stream.position;
      else if (whence === 2 && FS.isFile(stream.node.mode)) pos += stream.node.size;
      if (pos < 0) throw err(EINVAL);
      try {
        wvfs.seekSync(stream.wfd, pos);
      } catch (e) {
        if (e instanceof WvfsError && e.code === 'EBADF') throw err(EBADF);
        throw err(EIO);
      }
      return pos;
    },
  };

  const stores = opts.stores ?? [wvfs];
  return {
    mount() {
      return make(null as any, '/', DIR_MODE, '');
    },
    node_ops,
    stream_ops,
    /** FS.syncfs(populate, cb) から呼ばれる (libfs.js: mount.type.syncfs(mount, populate, done)) */
    syncfs(_mount: any, populate: boolean, callback: (e: number | null) => void) {
      try {
        if (!populate) for (const s of stores) s.sync();
        callback(null);
      } catch (e) {
        callback(errnoOf(e));
      }
    },
  };
}
