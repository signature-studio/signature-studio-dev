// backend-node.ts — node fs バックエンド (単体テスト / node Emscripten probe 用)。
// SyncFile 契約 (vfs/types.ts) を node の同期 fd で実装する (vfs/node-file.ts と同型)。
import fs from 'node:fs';
import path from 'node:path';
import type { SyncFile } from '../vfs/types.ts';
import { WvfsError, mapFsError, type WvfsBackend } from './journal.ts';

/** rootDir 例: <tools/assets>/work/wvfs-test/home (存在しない中間 dir は作る) */
export class NodeBackend implements WvfsBackend {
  readonly rootDir: string;

  constructor(rootDir: string) {
    this.rootDir = rootDir;
  }

  private full(name: string): string {
    if (name.includes('/') || name.includes('..')) throw new WvfsError('EINVAL', `bad store file name: ${name}`);
    return path.join(this.rootDir, name);
  }

  private ensure(): void {
    fs.mkdirSync(this.rootDir, { recursive: true });
  }

  async open(name: string, opts: { create?: boolean; truncate?: boolean } = {}): Promise<SyncFile> {
    this.ensure();
    const f = this.full(name);
    const exists = fs.existsSync(f);
    if (!exists && !opts.create) throw new WvfsError('ENOENT', `${f}: not found`);
    let fd: number;
    try {
      // 'w+' は作成+切詰め、'r+' は位置指定 read/write 可 ('a+' は write が常に追記になるため使わない)
      fd = fs.openSync(f, exists && !opts.truncate ? 'r+' : 'w+');
    } catch (e) {
      throw mapFsError(e, `node open ${f}`);
    }
    return {
      read: (buf, at) => fs.readSync(fd, buf, 0, buf.length, at),
      write: (buf, at) => fs.writeSync(fd, buf, 0, buf.length, at),
      getSize: () => fs.fstatSync(fd).size,
      truncate: (n) => fs.ftruncateSync(fd, n),
      flush: () => fs.fsyncSync(fd),
      close: () => fs.closeSync(fd),
    };
  }

  async remove(name: string): Promise<void> {
    const f = this.full(name);
    try {
      fs.rmSync(f, { force: true });
    } catch (e) {
      throw mapFsError(e, `node remove ${f}`);
    }
  }

  async exists(name: string): Promise<boolean> {
    return fs.existsSync(this.full(name));
  }
}
