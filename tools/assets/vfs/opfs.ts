import type { SyncFile } from './types.ts';

/** OPFS の SyncAccessHandle (Worker 限定) を SyncFile 化する。別タブが同一ファイルを占有中なら null。 */
export async function openOpfsSyncFile(name: string, dirName = 'fl-vfs'): Promise<SyncFile | null> {
  const nav = (globalThis as unknown as { navigator?: Navigator }).navigator;
  if (!nav?.storage?.getDirectory) return null;
  const root = await nav.storage.getDirectory();
  const dir = await root.getDirectoryHandle(dirName, { create: true });
  const fh = await dir.getFileHandle(name, { create: true });
  let h: FileSystemSyncAccessHandle;
  try {
    h = await fh.createSyncAccessHandle();
  } catch (e) {
    if ((e as DOMException).name === 'NoModificationAllowedError') return null;
    throw e;
  }
  return {
    read: (buf, at) => h.read(buf, { at }),
    write: (buf, at) => h.write(buf, { at }),
    getSize: () => h.getSize(),
    truncate: (n) => h.truncate(n),
    flush: () => h.flush(),
    close: () => h.close(),
  };
}

export async function removeOpfsFile(name: string, dirName = 'fl-vfs'): Promise<void> {
  const root = await navigator.storage.getDirectory();
  const dir = await root.getDirectoryHandle(dirName, { create: true });
  await dir.removeEntry(name).catch(() => {});
}

/** 空き容量に応じたキャッシュ上限の提案 (quota の 40%, 上限 cap) */
export async function suggestMaxBytes(cap = 4 * 2 ** 30): Promise<number> {
  const est = await navigator.storage?.estimate?.();
  const quota = est?.quota ?? 2 * 2 ** 30;
  const used = est?.usage ?? 0;
  return Math.max(256 * 2 ** 20, Math.min(cap, Math.floor((quota - used) * 0.4)));
}
