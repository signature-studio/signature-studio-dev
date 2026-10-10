// 同一 OPFS ファイルの 2 つ目の SyncAccessHandle が拒否されること (別タブ相当) を確認
import { openOpfsSyncFile } from '../../vfs/opfs.ts';
(self as any).onmessage = async (e: MessageEvent) => {
  const f = await openOpfsSyncFile(e.data as string);
  if (f) f.close();
  (self as any).postMessage(f ? 'opened' : null);
};
