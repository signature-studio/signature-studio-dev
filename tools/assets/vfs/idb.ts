// IndexedDB 最小ラッパ (asset キャッシュ用)。ブラウザ main / Worker の両方で動く。
// bytes (Uint8Array) のみを保存する。WebAssembly.Module は保存しない (構造化複製は可能だが
// エンジン固有の最適化に寄せず、他 tier / 再取得との整合を bytes 単位で保つ方針)。

export interface IdbHandle {
  get<T = unknown>(store: string, key: IDBValidKey): Promise<T | undefined>;
  put(store: string, key: IDBValidKey, value: unknown): Promise<void>;
  del(store: string, key: IDBValidKey): Promise<void>;
  keys(store: string): Promise<IDBValidKey[]>;
  close(): void;
}

export function openIdb(name: string, stores: string[], version = 1): Promise<IdbHandle | null> {
  const g = globalThis as unknown as { indexedDB?: IDBFactory };
  if (!g.indexedDB) return Promise.resolve(null);
  return new Promise((res) => {
    let req: IDBOpenDBRequest;
    try {
      req = g.indexedDB!.open(name, version);
    } catch {
      return res(null);
    }
    req.onupgradeneeded = () => {
      const db = req.result;
      for (const s of stores) if (!db.objectStoreNames.contains(s)) db.createObjectStore(s);
    };
    req.onsuccess = () => {
      const db = req.result;
      db.onversionchange = () => db.close();
      res({
        get: (store, key) =>
          new Promise((res2, rej) => {
            const tx = db.transaction(store, 'readonly');
            const r = tx.objectStore(store).get(key);
            r.onsuccess = () => res2(r.result);
            r.onerror = () => rej(r.error);
          }),
        put: (store, key, value) =>
          new Promise((res2, rej) => {
            const tx = db.transaction(store, 'readwrite');
            tx.objectStore(store).put(value, key);
            tx.oncomplete = () => res2();
            tx.onerror = () => rej(tx.error);
            tx.onabort = () => rej(tx.error);
          }),
        del: (store, key) =>
          new Promise((res2, rej) => {
            const tx = db.transaction(store, 'readwrite');
            tx.objectStore(store).delete(key);
            tx.oncomplete = () => res2();
            tx.onerror = () => rej(tx.error);
          }),
        keys: (store) =>
          new Promise((res2, rej) => {
            const tx = db.transaction(store, 'readonly');
            const r = tx.objectStore(store).getAllKeys();
            r.onsuccess = () => res2(r.result);
            r.onerror = () => rej(r.error);
          }),
        close: () => db.close(),
      });
    };
    req.onerror = () => res(null);
    req.onblocked = () => res(null);
  });
}
