// backend-opfs.ts — OPFS (origin private file system) バックエンド。
// SyncAccessHandle は Worker 限定 (main thread では throw)。1 mount = 1 OPFS サブディレクトリ。
// 「tmpfs プロファイルでは SyncAccessHandle 書込が壊れる」実績 (CAB-21 REPORT §3) により、
// e2e は実ディスクの Chrome プロファイル (work/chrome-profiles/) を使うこと。
import type { SyncFile } from '../vfs/types.ts';
import { WvfsError, mapFsError, type WvfsBackend } from './journal.ts';

type SyncHandle = FileSystemSyncAccessHandle & {
  read(buf: ArrayBufferView, at?: FileSystemReadWriteOptions): number;
  write(buf: ArrayBufferView, at?: FileSystemReadWriteOptions): number;
};

function wrap(h: SyncHandle): SyncFile {
  return {
    read: (buf, at) => h.read(buf, { at }),
    write: (buf, at) => h.write(buf, { at }),
    getSize: () => h.getSize(),
    truncate: (n) => h.truncate(n),
    flush: () => h.flush(),
    close: () => h.close(),
  };
}

/** dirPath 例: 'fl-wvfs/home' (root からの相対。存在しない中間 dir は作る) */
export class OpfsBackend implements WvfsBackend {
  private dir: FileSystemDirectoryHandle | null = null;
  readonly dirPath: string;

  constructor(dirPath: string) {
    this.dirPath = dirPath;
  }

  private async ensure(): Promise<FileSystemDirectoryHandle> {
    if (this.dir) return this.dir;
    const nav = (globalThis as unknown as { navigator?: Navigator }).navigator;
    if (!nav?.storage?.getDirectory) throw new WvfsError('EIO', `OPFS unavailable (Worker only?): ${this.dirPath}`);
    let d = await nav.storage.getDirectory();
    for (const seg of this.dirPath.split('/').filter(Boolean)) {
      try {
        d = await d.getDirectoryHandle(seg, { create: true });
      } catch (e) {
        throw mapFsError(e, `opfs mkdir ${seg}`);
      }
    }
    this.dir = d;
    return d;
  }

  async open(name: string, opts: { create?: boolean; truncate?: boolean } = {}): Promise<SyncFile> {
    const d = await this.ensure();
    let fh: FileSystemFileHandle;
    try {
      fh = await d.getFileHandle(name, { create: !!opts.create });
    } catch (e) {
      throw mapFsError(e, `opfs open ${this.dirPath}/${name}`);
    }
    let h: SyncHandle;
    try {
      h = (await fh.createSyncAccessHandle()) as SyncHandle;
    } catch (e) {
      throw mapFsError(e, `opfs access handle ${this.dirPath}/${name}`);
    }
    if (opts.truncate) {
      h.truncate(0);
      h.flush();
    }
    return wrap(h);
  }

  async remove(name: string): Promise<void> {
    const d = await this.ensure();
    try {
      await d.removeEntry(name);
    } catch (e) {
      if ((e as DOMException).name === 'NotFoundError') return;
      throw mapFsError(e, `opfs remove ${this.dirPath}/${name}`);
    }
  }

  async exists(name: string): Promise<boolean> {
    const d = await this.ensure();
    try {
      await d.getFileHandle(name);
      return true;
    } catch (e) {
      if ((e as DOMException).name === 'NotFoundError') return false;
      throw mapFsError(e, `opfs exists ${this.dirPath}/${name}`);
    }
  }
}
