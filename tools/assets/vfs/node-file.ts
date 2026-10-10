import fs from 'node:fs';
import type { SyncFile } from './types.ts';

export function openNodeSyncFile(path: string): SyncFile {
  const fd = fs.openSync(path, 'a+'); // 作成
  fs.closeSync(fd);
  const f = fs.openSync(path, 'r+');
  return {
    read: (buf, at) => fs.readSync(f, buf, 0, buf.length, at),
    write: (buf, at) => fs.writeSync(f, buf, 0, buf.length, at),
    getSize: () => fs.fstatSync(f).size,
    truncate: (n) => fs.ftruncateSync(f, n),
    flush: () => fs.fsyncSync(f),
    close: () => fs.closeSync(f),
  };
}
