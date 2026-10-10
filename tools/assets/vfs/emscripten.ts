// Emscripten FS バックエンド: LazyVfs を FS.mount できる読取専用ファイルシステムとして公開する。
// tools/shim/src/file.c の CreateFileW -> open(2) は、/fl に mount されたこの FS を経由して同期 read を得る。
//
//   const fsImpl = createEmscriptenFs(Module.FS, vfs);
//   Module.FS.mkdir('/fl'); Module.FS.mount(fsImpl, {}, '/fl');
//
// 設計メモ:
//  - 名前解決は lookup 時に vfs.statSync (大小無視) へ委譲 → 全 28k ノードを事前生成しない (WORKERFS との違い)
//  - 書込系は EPERM(63)。書込が必要な領域 (Settings/Presets/ユーザデータ) は別途 MEMFS/IDBFS を mount する
//  - read は stream 毎に vfs fd を遅延 open。fd = vfs 側 (先読み状態の単位)
import type { LazyVfs } from './lazy-vfs.ts';
import { VfsError } from './lazy-vfs.ts';

const DIR_MODE = 16895; // 040777
const FILE_MODE = 33060; // 0100444 (r--r--r--)
const ENOENT = 44;
const EPERM = 63;
const EIO = 29;
const EISDIR = 31;
const EINVAL = 28;

export function createEmscriptenFs(FS: any, vfs: LazyVfs): any {
  const join = (a: string, b: string) => (a ? a + '/' + b : b);
  const err = (n: number) => new FS.ErrnoError(n);
  const mtime = Date.now();

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
        atime: new Date(mtime),
        mtime: new Date(mtime),
        ctime: new Date(mtime),
        blksize: 4096,
        blocks: Math.ceil(node.size / 4096),
      };
    },
    setattr() {},
    lookup(parent: any, name: string) {
      const st = vfs.statSync(join(parent.vpath, name));
      if (!st) throw err(ENOENT);
      return make(parent, name, st.type === 'dir' ? DIR_MODE : FILE_MODE, st.size, join(parent.vpath, name));
    },
    mknod() {
      throw err(EPERM);
    },
    rename() {
      throw err(EPERM);
    },
    unlink() {
      throw err(EPERM);
    },
    rmdir() {
      throw err(EPERM);
    },
    symlink() {
      throw err(EPERM);
    },
    readdir(node: any) {
      return ['.', '..', ...vfs.readdirSync(node.vpath).map((e) => e.name)];
    },
  };

  const stream_ops = {
    open(stream: any) {
      if (FS.isDir(stream.node.mode)) return;
      try {
        stream.vfsFd = vfs.openSync(stream.node.vpath);
      } catch (e) {
        throw err(e instanceof VfsError && e.code === 'ENOENT' ? ENOENT : EIO);
      }
    },
    close(stream: any) {
      if (stream.vfsFd !== undefined) vfs.closeSync(stream.vfsFd);
    },
    read(stream: any, buffer: Uint8Array, offset: number, length: number, position: number) {
      if (position >= stream.node.size) return 0;
      try {
        return vfs.readSync(stream.vfsFd, buffer, offset, length, position);
      } catch (e) {
        throw err(e instanceof VfsError && e.code === 'ESTUB' ? EIO : EIO);
      }
    },
    write() {
      throw err(EPERM);
    },
    llseek(stream: any, offset: number, whence: number) {
      let pos = offset;
      if (whence === 1) pos += stream.position;
      else if (whence === 2 && FS.isFile(stream.node.mode)) pos += stream.node.size;
      if (pos < 0) throw err(EINVAL);
      return pos;
    },
  };

  function make(parent: any, name: string, mode: number, size: number, vpath: string) {
    const node = FS.createNode(parent, name, mode, 0);
    node.node_ops = node_ops;
    node.stream_ops = stream_ops;
    node.size = size || (mode === DIR_MODE ? 4096 : 0);
    node.vpath = vpath;
    return node;
  }

  void EISDIR;
  return {
    mount() {
      return make(null, '/', DIR_MODE, 4096, '');
    },
    node_ops,
    stream_ops,
  };
}
